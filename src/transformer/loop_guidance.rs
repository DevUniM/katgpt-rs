//! LoopCD recurrent-depth contrast guidance (Plan 617, arXiv:2610.02185).
//!
//! The probe_guidance combine family (Issue 865) with its weak side
//! re-sourced to a **completed loop iteration `k`** of the weight-shared
//! looped forward — modelless, zero training, aligned by construction (same
//! block, same head, same prefix; only compute differs):
//!
//! ```text
//! logit mode:   z_k = head(h_k)             # one extra scratch head pass
//!               z′  = z_R + ω·(z_R − z_k)   # = affine_combine(z_R, z_k, 1+ω)
//! hidden mode:  h′  = h_R + ω·(h_R − h_k)   # blended BEFORE head; ONE head pass
//! adaptive:     ω   = ω_max·[1 − (p₁ − p₂)] # top-two softmax margin of z_R
//! ```
//!
//! # Deviations pinned here (verdict-review honesty)
//!
//! - **Hidden-mode adaptive ω consumes the PREVIOUS decode step's margin.**
//!   The Eq-4 gate is computed in-step from `softmax(z_R)` in logit mode
//!   (z_R exists pre-guidance). Hidden mode's one-head-pass law means h_R is
//!   never read out, so the margin comes from the decoder's last actual
//!   output distribution (carried in [`LoopGuidance::last_margin`]; the
//!   decoder's current belief — settled tokens stay settled, guidance
//!   sharpens, margin grows, ω → 0). First call falls back to the fixed
//!   `config.omega`. A pinned unit test keeps this honest.
//! - **ω = 0 posture is a structural no-op** (no capture pass, no combine,
//!   no margin carry) — cheaper than "armed but identity", and
//!   bit-identical by construction rather than by f32 identity argument.
//!
//! # Precedence vs the exit family (Plan 617 T1.3)
//!
//! `AdvantageMarginGate` / `GainCostLoopHalter` / `LoopResidualExit` operate
//! on UNGUIDED per-iteration readouts and decide whether to keep looping.
//! Guidance transforms whichever prediction is FINALLY decoded (exit-
//! iteration or loop-R): the exits never see guided logits, the final decode
//! always does. The two mechanisms compose; neither subsumes the other.
//!
//! # Zero-alloc (T1.5)
//!
//! Scratch is pre-sized at [`LoopGuidance::new`] and only `resize`d (a
//! no-op at matching capacity) inside the forward — steady-state decode
//! allocates zero bytes with guidance armed (pinned by the counting-
//! allocator gate test).
//!
//! # Reference-capture contract
//!
//! `h_k` is captured at the END of loop iteration `ref_loop` (1-based) —
//! the completed-iteration state, post residual-gate. If the loop exits
//! (any halter/gate fires) BEFORE `ref_loop` completes, no reference exists
//! and guidance is a no-op for that step (documented; `ref_loop = 1` with
//! the default exits cannot happen — every exit family runs at `tau ≥ 1`
//! i.e. after iteration 1 completes, which is exactly the default capture
//! point). `ref_loop ≥ loop_count + 1` never captures → permanent no-op;
//! `validate()` warns via refusal only for the structurally-invalid 0.

#![cfg(feature = "loop_guidance")]

/// Which space the contrast re-ranks in.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum GuidanceMode {
    /// `z′ = z_R + ω·(z_R − z_k)` on the final logits. One extra scratch
    /// head pass at the capture iteration (two head passes per guided step).
    Logits,
    /// `h′ = h_R + ω·(h_R − h_k)` on the hidden state before the head.
    /// Single head pass per guided step (the coda/head cost is unchanged).
    Hidden,
}

/// LoopCD guidance configuration (Plan 617 T0.1).
///
/// Defaults are the structural no-op: `omega = 0.0` (bit-identical off),
/// `ref_loop = 1` (the first completed iteration — Huginn's hidden lane
/// needs a later burn-in reference; hyperparameter transfer is out of
/// scope, the fixture pins the mechanism).
#[derive(Clone, Copy, Debug)]
pub struct LoopGuidanceConfig {
    /// Logit-space or hidden-space contrast.
    pub mode: GuidanceMode,
    /// Fixed strength ω. Ignored when `adaptive` (except as the first-step
    /// fallback in hidden mode). Must be ≥ 0 — negative ω universally
    /// degrades (paper §G.1), refused at validation.
    pub omega: f32,
    /// Adaptive-gate cap: `ω_t = ω_max·[1 − (p₁ − p₂)] ∈ [0, ω_max]`.
    /// Must be ≥ `omega`.
    pub omega_max: f32,
    /// Margin-gate the strength per step (`ω = ω_max·[1 − (p₁ − p₂)]`)
    /// instead of applying the fixed `omega`.
    pub adaptive: bool,
    /// 1-based loop index whose completed hidden state becomes the weak
    /// reference `h_k`. Default 1. 0 is refused.
    pub ref_loop: usize,
}

impl Default for LoopGuidanceConfig {
    fn default() -> Self {
        Self {
            mode: GuidanceMode::Logits,
            omega: 0.0,
            omega_max: 0.0,
            adaptive: false,
            ref_loop: 1,
        }
    }
}

impl LoopGuidanceConfig {
    /// Structural validation (Plan 617 T0.1): `omega ≥ 0` (negative ω
    /// universally degrades per the paper's §G.1 — refuse, never clamp),
    /// `omega_max ≥ omega`, `ref_loop ≥ 1`.
    pub fn validate(&self) -> Result<(), &'static str> {
        if !self.omega.is_finite() || self.omega < 0.0 {
            return Err("loop_guidance: omega must be finite and >= 0 (negative omega universally degrades, paper §G.1)");
        }
        if !self.omega_max.is_finite() || self.omega_max < self.omega {
            return Err("loop_guidance: omega_max must be finite and >= omega");
        }
        if self.ref_loop == 0 {
            return Err("loop_guidance: ref_loop is 1-based and must be >= 1");
        }
        Ok(())
    }

    /// True when this config can change any output. The ω=0 posture
    /// (fixed-ω with `omega == 0`, or adaptive with `omega_max == 0`) is a
    /// structural no-op: the forward skips capture AND combine entirely.
    #[inline]
    pub fn is_armed(&self) -> bool {
        if self.adaptive {
            self.omega_max > 0.0
        } else {
            self.omega > 0.0
        }
    }
}

/// Caller-owned guidance state: config + pre-sized scratch + the hidden
/// mode's carried margin. Construct once per decode session (the
/// `LoopDeepRun` precedent), pass `Some(&mut g)` per `forward_looped` call.
///
/// The struct is self-resetting per call: `forward_looped` clears
/// `captured` on entry, so a `LoopGuidance` reused across steps is correct
/// without caller bookkeeping.
pub struct LoopGuidance {
    /// Validated at construction (`expect` — a bad config is a programmer
    /// error; use [`LoopGuidanceConfig::validate`] for fallible checks).
    pub config: LoopGuidanceConfig,
    /// `h_k` scratch (hidden mode), n_embd.
    scratch_hidden: Vec<f32>,
    /// `z_k` scratch (logit mode), vocab_size.
    scratch_logits: Vec<f32>,
    /// Whether the reference was captured this call.
    captured: bool,
    /// Hidden mode: the softmax top-two margin of the PREVIOUS step's final
    /// logits (`None` before the first step → fixed-`omega` fallback).
    last_margin: Option<f32>,
}

impl LoopGuidance {
    /// Pre-sizes scratch (the ONE allocation of the object's lifetime) and
    /// validates the config.
    pub fn new(config: LoopGuidanceConfig, vocab_size: usize, n_embd: usize) -> Self {
        config
            .validate()
            .expect("loop_guidance: invalid config passed to LoopGuidance::new");
        Self {
            config,
            scratch_hidden: Vec::with_capacity(n_embd),
            scratch_logits: Vec::with_capacity(vocab_size),
            captured: false,
            last_margin: None,
        }
    }

    /// The object's own view of whether it can change output this call
    /// (config armed AND a reference captured). Exposed for tests.
    #[inline]
    pub fn guidance_active(&self) -> bool {
        self.config.is_armed() && self.captured
    }

    /// Whether the reference was captured THIS call (pub(crate): the tf-loop
    /// macro guards against double capture — its `Layer` mode revisits the
    /// capture point once per layer).
    #[inline]
    pub(crate) fn guidance_captured(&self) -> bool {
        self.captured
    }

    /// Hidden mode: the margin the NEXT step's adaptive gate will consume.
    #[inline]
    pub fn last_margin(&self) -> Option<f32> {
        self.last_margin
    }

    // ── hooks called from forward_looped / forward_training_free_loop ──

    /// Per-call reset: clears the capture flag (scratch contents are dead
    /// once `captured == false`, no zeroing needed).
    #[inline]
    pub(crate) fn begin_step(&mut self) {
        self.captured = false;
    }

    /// Capture `h_k` at the completed `ref_loop` iteration (the caller has
    /// already checked `tau + 1 == ref_loop`). Hidden mode stashes the
    /// state; logit mode runs the ONE extra scratch head pass.
    #[inline]
    pub(crate) fn capture_reference(
        &mut self,
        hidden: &[f32],
        weights_lm_head: &[f32],
        vocab_size: usize,
        n_embd: usize,
    ) {
        debug_assert!(!self.captured, "capture_reference called twice per step");
        match self.config.mode {
            GuidanceMode::Hidden => {
                self.scratch_hidden.resize(hidden.len(), 0.0);
                self.scratch_hidden.copy_from_slice(hidden);
            }
            GuidanceMode::Logits => {
                self.scratch_logits.resize(vocab_size, 0.0);
                crate::transformer::standard_lm_head(
                    &mut self.scratch_logits,
                    hidden,
                    weights_lm_head,
                    vocab_size,
                    n_embd,
                );
            }
        }
        self.captured = true;
    }

    /// Apply the contrast at the readout site. Returns the ω that was used
    /// (0.0 = skipped — not armed, no reference, or ω computed to exactly 0).
    ///
    /// - Hidden mode: `hidden ← affine_combine(hidden, h_k, 1+ω)` IN PLACE,
    ///   called BEFORE the head (the caller then reads out h′ — one head
    ///   pass total). `hidden` must be `Some` in this mode.
    /// - Logit mode: `logits ← affine_combine(logits, z_k, 1+ω)`, called
    ///   AFTER the head on h_R (the in-step Eq-4 margin reads these
    ///   pre-guidance logits — correct at the call site by construction).
    pub(crate) fn apply_at_readout(
        &mut self,
        hidden: Option<&mut [f32]>,
        logits: &mut [f32],
    ) -> f32 {
        if !self.config.is_armed() || !self.captured {
            return 0.0;
        }
        let omega = self.current_omega(logits);
        if omega == 0.0 {
            return 0.0;
        }
        let lam = 1.0 + omega;
        match self.config.mode {
            GuidanceMode::Hidden => {
                let h = hidden.expect("hidden mode apply_at_readout requires the hidden slice");
                katgpt_core::contrast_combine::affine_combine(
                    h,
                    &self.scratch_hidden[..h.len()],
                    lam,
                );
            }
            GuidanceMode::Logits => {
                katgpt_core::contrast_combine::affine_combine(
                    logits,
                    &self.scratch_logits[..logits.len()],
                    lam,
                );
            }
        }
        omega
    }

    /// The ω this step uses: fixed, or margin-gated (Eq 4). Logit mode
    /// computes the margin IN-STEP from the pre-guidance logits; hidden
    /// mode consumes the carried previous-step margin (fallback: fixed).
    #[inline]
    fn current_omega(&self, pre_guidance_logits: &[f32]) -> f32 {
        if !self.config.adaptive {
            return self.config.omega;
        }
        let margin = match self.config.mode {
            GuidanceMode::Logits => top_two_margin(pre_guidance_logits),
            GuidanceMode::Hidden => match self.last_margin {
                Some(m) => m,
                None => return self.config.omega,
            },
        };
        self.config.omega_max * (1.0 - margin)
    }

    /// Hidden mode: record the top-two margin of THIS step's final (post-
    /// guidance) logits — the decoder's actual output distribution — as
    /// the next step's adaptive-ω input. Logit mode must NOT call this
    /// (its gate is in-step, pre-guidance; a carried margin would be a
    /// second, different semantic). No-op in logit mode by design.
    #[inline]
    pub(crate) fn record_output_margin(&mut self, final_logits: &[f32]) {
        if self.config.is_armed() && self.config.mode == GuidanceMode::Hidden {
            self.last_margin = Some(top_two_margin(final_logits));
        }
    }
}

/// Top-two softmax probability gap `p₁ − p₂` of `logits`, zero-allocation.
///
/// Two passes over the slice (no full-softmax buffer): pass 1 finds the top
/// two values; pass 2 accumulates `exp(v − z₁)` for the shared denominator —
/// `p₁ = 1/denom` and `p₂ = exp(z₂−z₁)/denom`, so the margin is exact
/// without materializing either probability:
/// `p₁ − p₂ = (1 − exp(z₂ − z₁)) / Σexp(v − z₁)`.
///
/// Short-circuits: `< 2` elements → 0.0 (no margin); any non-finite value →
/// 1.0 (fail CLOSED — a broken logit row reads settled so ω is withheld;
/// guidance must never maximize contrast strength on a broken step).
pub fn top_two_margin(logits: &[f32]) -> f32 {
    if logits.len() < 2 {
        return 0.0;
    }
    // Pass 1: top two, branch-light.
    let mut z1 = f32::NEG_INFINITY;
    let mut z2 = f32::NEG_INFINITY;
    for &v in logits {
        if !v.is_finite() {
            // Fail closed: a broken logit row reads SETTLED (margin 1 → ω 0,
            // guidance withheld). The step is already broken; maximizing
            // contrast strength on it would only make it worse.
            return 1.0;
        }
        if v > z1 {
            z2 = z1;
            z1 = v;
        } else if v > z2 {
            z2 = v;
        }
    }
    if !z2.is_finite() {
        // Single-finite row: degenerate. Fail CLOSED — report settled (ω
        // withheld); a broken row must not maximize contrast strength.
        return 1.0;
    }
    // Pass 2: shared-shift softmax pieces. p1 = 1/denom and p2 =
    // exp(z2−z1)/denom share the denominator, so the margin is exact without
    // materializing p1: (1 − exp(z2−z1)) / Σexp(v − z1).
    let mut denom = 0.0f32;
    for &v in logits {
        denom += (v - z1).exp();
    }
    (1.0 - (z2 - z1).exp()) / denom
}

/// Eq 4: `ω = ω_max·[1 − (p₁ − p₂)]` — full strength on contested tokens,
/// withheld on settled ones. Exposed for the concentration pin test.
#[inline]
pub fn adaptive_omega(omega_max: f32, margin: f32) -> f32 {
    omega_max * (1.0 - margin)
}

/// Default config for tests/examples: adaptive logit-mode guidance at the
/// paper's generation-strength window midpoint (the window is
/// checkpoint-specific; this is a starting posture, not a transfer claim).
pub fn default_adaptive_config() -> LoopGuidanceConfig {
    LoopGuidanceConfig {
        mode: GuidanceMode::Logits,
        omega: 0.25,
        omega_max: 0.5,
        adaptive: true,
        ref_loop: 1,
    }
}
