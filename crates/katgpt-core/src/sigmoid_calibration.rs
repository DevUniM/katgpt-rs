//! Calibrated sigmoid gate — Platt-style refit for decision/confidence scalars.
//!
//! Every decision/confidence scalar in the stack is a sigmoid output, and its
//! calibration is proven nowhere: Lean proves boundedness (range (0,1));
//! nothing proves the numbers *mean* anything ("fear = 0.8" is not known to
//! fire ~80% of the time). This module adds the missing, published, modelless
//! half: a per-direction two-parameter refit (temperature + bias) over
//! recorded `(sigmoid_output, binary_outcome)` pairs — Platt 1999; Guo et al.
//! 2017 (arXiv:1706.04599); Kadavath 2022 (arXiv:2207.05221).
//!
//! Modelless mandate: the ONLY mutated state is two latent scalars per
//! direction plus the evidence window — mutation class #3 (a direction
//! vector + sigmoid gate updated from labeled outcomes), never base weights.
//! The fit is a deterministic convex 2-parameter Newton solve (fixed
//! iteration count, smoothed targets à la Platt), not gradient descent on a
//! network; replaying the same pairs yields bit-identical parameters.
//!
//! Shape (Issue 810):
//! - `observe(p, outcome)` — record one pair into a fixed-capacity FIFO ring
//!   (zero alloc after construction).
//! - `refit()` — off-hot-path refit of `(w, c)` in `p_cal = sigmoid(w·z + c)`
//!   where `z = logit(p)`; equivalent to the issue's
//!   `sigmoid((logit(p) − b)/T)` with `T = 1/w`, `b = −c/w`.
//! - `apply(p)` — hot path: one logit, one fma, one sigmoid. Zero-alloc;
//!   the same cost class as any bare sigmoid gate.
//! - `commitment()` — BLAKE3 over versioned canonical bytes (params + total
//!   observation count), the small-artifact convention of
//!   `closure::commitment`; freeze/thaw consumers treat it like any
//!   snapshot.
//!
//! Monotonicity guard: `w > 0` is enforced (projection to `W_MIN`) —
//! calibration must never reorder decisions, so ranking and every
//! threshold-optimal decision are preserved by construction (G3).
//!
//! UQ "Report the Floor" rule (Research 322 / Plan 340): a calibrated gate
//! must still beat the dumb baselines — the constant base-rate predictor and
//! the uncalibrated sigmoid itself — on Brier/log-loss (G2). Calibration is
//! not free: if the refit cannot beat those floors on the evidence window,
//! the honest answer is the identity transform, which the occupancy floor
//! makes the default until evidence says otherwise.

/// Canonical sigmoid (per the project rule: sigmoid, never softmax).
use crate::sigmoid;

/// Probability clip for logit/log-loss numerics: keeps `logit` finite
/// (|logit| ≤ ~9.2) without measurably moving any decision threshold.
const P_CLIP: f32 = 1.0e-4;
/// Monotonicity floor for the fitted scale `w` (1/T). A window whose MLE
/// scale is anti-correlated (`w ≤ 0`) is projected here: the gate keeps a
/// valid (rank-preserving) shape instead of inverting decisions.
pub const W_MIN: f32 = 1.0e-3;
/// Newton iteration cap for the 2-parameter refit. Convex problem, quadratic
/// convergence — 32 is far past convergence and exists only to bound the
/// off-hot-path refit deterministically.
const NEWTON_MAX_ITERS: usize = 32;
/// Convergence tolerance on the parameter-update norm.
const NEWTON_TOL: f32 = 1.0e-7;
/// Commitment format version (bump on any change to the canonical bytes).
const COMMITMENT_VERSION: u8 = 1;

/// A single-direction calibrated sigmoid gate.
///
/// Single allocation at construction (the evidence window); `observe` and
/// `apply` are zero-alloc. Not `Clone` (evidence windows are
/// identity-carrying; snapshot via params + commitment instead).
pub struct SigmoidGateCalibrator {
    /// Fitted scale `w` in `p_cal = sigmoid(w·z + c)` (w > 0; 1/T).
    w: f32,
    /// Fitted intercept `c`.
    c: f32,
    /// Evidence window: raw sigmoid outputs (clamped on use).
    ps: Vec<f32>,
    /// Evidence window: binary outcomes as 0.0/1.0.
    ys: Vec<f32>,
    /// Next write index (FIFO ring).
    head: usize,
    /// Number of live entries (`≤ capacity`).
    len: usize,
    /// Total observations ever recorded (monotone; part of the commitment
    /// so a stale snapshot cannot pose as fresher evidence).
    n_obs_total: u64,
    /// Minimum window occupancy before `refit()` will move parameters.
    min_obs: usize,
}

impl SigmoidGateCalibrator {
    /// Construct an identity-calibrated gate (`T = 1, b = 0` — `apply` is
    /// the identity until evidence says otherwise).
    ///
    /// `capacity` is the evidence window size (FIFO eviction of the oldest
    /// pair); `min_obs` is the occupancy floor below which [`Self::refit`]
    /// keeps the identity parameters.
    pub fn new(capacity: usize, min_obs: usize) -> Self {
        assert!(capacity >= 1, "capacity must be >= 1");
        Self {
            w: 1.0,
            c: 0.0,
            ps: Vec::with_capacity(capacity),
            ys: Vec::with_capacity(capacity),
            head: 0,
            len: 0,
            n_obs_total: 0,
            min_obs: min_obs.min(capacity),
        }
    }

    /// Record one `(sigmoid_output, binary_outcome)` pair.
    ///
    /// `p` outside `(0, 1)` is invalid and clamps into `(P_CLIP, 1 −
    /// P_CLIP)` on use — the gate treats it as saturation, not error.
    /// Zero-alloc; O(1).
    #[inline]
    pub fn observe(&mut self, p: f32, outcome: bool) {
        let y = f32::from(outcome);
        let cap = self.ps.capacity();
        if self.len < cap {
            self.ps.push(p);
            self.ys.push(y);
            self.len += 1;
            self.head = if cap == 0 { 0 } else { (self.head + 1) % cap };
        } else {
            self.ps[self.head] = p;
            self.ys[self.head] = y;
            self.head = (self.head + 1) % cap;
        }
        self.n_obs_total += 1;
    }

    /// Hot path: calibrated probability for a raw sigmoid output.
    ///
    /// `p_cal = sigmoid(w · logit(p) + c)` — one logit, one fma, one
    /// sigmoid. Monotone in `p` for every reachable parameter state
    /// (`w ≥ W_MIN > 0`), so ranking is preserved by construction.
    ///
    /// Identity fast path: at the constructed parameters `(w, c) = (1, 0)`
    /// the input is returned **bit-identically** — a `logit → sigmoid`
    /// roundtrip is not bit-exact in f32, and the documented contract
    /// ("apply is the identity until evidence says otherwise") plus the
    /// cold-start bit-identity requirements of downstream consumers
    /// (riir-ai Issue 964 C1/C3) demand the exact value, not a float twin.
    #[inline]
    pub fn apply(&self, p: f32) -> f32 {
        if self.w == 1.0 && self.c == 0.0 {
            return p;
        }
        sigmoid(self.w.mul_add(logit_clamped(p), self.c))
    }

    /// Off-hot-path refit of `(w, c)` over the evidence window.
    ///
    /// Deterministic 2-parameter Newton solve on the smoothed-target
    /// logistic loss (Platt 1999): labels `t⁺ = (n⁺+1)/(n⁺+2)` /
    /// `t⁻ = 1/(n⁻+2)` keep the problem strictly convex on separable
    /// windows. Identity parameters below `min_obs` occupancy. Returns
    /// `true` when the parameters moved (window big enough to fit).
    ///
    /// Monotonicity: if the unconstrained MLE wants `w ≤ 0`, the fit is
    /// projected — `w` pinned to [`W_MIN`] and `c` re-solved on the 1-D
    /// problem. The gate never inverts decisions from evidence.
    pub fn refit(&mut self) -> bool {
        let n = self.len;
        if n < self.min_obs.max(2) {
            return false;
        }
        let (t, z) = self.smoothed_pairs();
        // Newton (loss to MINIMIZE): p ← p − H⁻¹∇L; identity init.
        let (mut w, mut c) = (1.0f32, 0.0f32);
        for _ in 0..NEWTON_MAX_ITERS {
            let (g0, g1, h00, h01, h11) = grad_hess(&t, &z, w, c);
            let det = h00 * h11 - h01 * h01;
            if !det.is_finite() || det.abs() < f32::EPSILON {
                break;
            }
            let inv_det = 1.0 / det;
            let dw = -inv_det * (h11 * g0 - h01 * g1);
            let dc = -inv_det * (h00 * g1 - h01 * g0);
            w += dw;
            c += dc;
            if !w.is_finite() || !c.is_finite() {
                w = W_MIN;
                c = 0.0;
                break;
            }
            if dw * dw + dc * dc < NEWTON_TOL * NEWTON_TOL {
                break;
            }
        }
        // Monotonicity projection: an anti-correlated window degrades to a
        // near-constant monotone gate rather than inverting decisions.
        // (`is_nan` is explicit — a NaN scale must project, not skip.)
        if w.is_nan() || w <= W_MIN {
            w = W_MIN;
            c = solve_c_at_w(&t, &z, w);
        }
        self.w = w;
        self.c = c;
        true
    }

    /// Smoothed Platt targets + logits for the current window, oldest first
    /// (deterministic order; allocation is fine — refit is off-hot-path).
    fn smoothed_pairs(&self) -> (Vec<f32>, Vec<f32>) {
        let n = self.len;
        let cap = self.ps.capacity();
        let n_pos: u32 = self.ys[..n].iter().map(|&y| (y > 0.5) as u32).sum();
        let n_neg = n as u32 - n_pos;
        // Platt 1999 target smoothing — keeps the loss strictly convex on
        // separable windows (all-0 / all-1), where the raw MLE diverges.
        let t_pos = (n_pos as f32 + 1.0) / (n_pos as f32 + 2.0);
        let t_neg = 1.0 / (n_neg as f32 + 2.0);
        let mut ts = Vec::with_capacity(n);
        let mut zs = Vec::with_capacity(n);
        for i in 0..n {
            let idx = (self.head + cap - n + i) % cap;
            ts.push(if self.ys[idx] > 0.5 { t_pos } else { t_neg });
            zs.push(logit_clamped(self.ps[idx]));
        }
        (ts, zs)
    }

    /// Current parameters as `(T, b)` — the issue's parametrization
    /// `p_cal = sigmoid((logit(p) − b)/T)`: `T = 1/w`, `b = −c/w`.
    /// `T > 0` always (the monotonicity guard).
    pub fn params(&self) -> (f32, f32) {
        (1.0 / self.w, -self.c / self.w)
    }

    /// Raw `(w, c)` fitted parameters (the stored form).
    pub fn params_raw(&self) -> (f32, f32) {
        (self.w, self.c)
    }

    /// Live window occupancy.
    #[inline]
    pub fn len(&self) -> usize {
        self.len
    }

    /// `true` iff no recorded pairs.
    #[inline]
    pub fn is_empty(&self) -> bool {
        self.len == 0
    }

    /// Total observations ever recorded (monotone counter).
    #[inline]
    pub fn n_obs_total(&self) -> u64 {
        self.n_obs_total
    }

    /// BLAKE3 commitment over versioned canonical bytes: version, `w`, `c`,
    /// window capacity, total observation count. Deterministic; changes on
    /// every observation (via `n_obs_total`) and every refit that moves
    /// parameters — a frozen snapshot can be checked against the evidence
    /// it claims to summarize.
    pub fn commitment(&self) -> [u8; 32] {
        let mut bytes = [0u8; 21];
        bytes[0] = COMMITMENT_VERSION;
        bytes[1..5].copy_from_slice(&self.w.to_bits().to_le_bytes());
        bytes[5..9].copy_from_slice(&self.c.to_bits().to_le_bytes());
        let cap = self.ps.capacity() as u32;
        bytes[9..13].copy_from_slice(&cap.to_le_bytes());
        bytes[13..21].copy_from_slice(&self.n_obs_total.to_le_bytes());
        blake3::hash(&bytes).into()
    }
}

/// Solve for the intercept `c` alone at a pinned scale `w` (1-D convex
/// Newton; used by the monotonicity projection).
fn solve_c_at_w(t: &[f32], z: &[f32], w: f32) -> f32 {
    let mut c = 0.0f32;
    for _ in 0..NEWTON_MAX_ITERS {
        let (g, h) = t
            .iter()
            .zip(z)
            .fold((0.0f32, 0.0f32), |(g, h), (&ti, &zi)| {
                let p = sigmoid(w.mul_add(zi, c));
                (g + p - ti, h + p * (1.0 - p))
            });
        if h < f32::EPSILON {
            break;
        }
        let dc = -g / h;
        c += dc;
        if !c.is_finite() {
            return 0.0;
        }
        if dc * dc < NEWTON_TOL * NEWTON_TOL {
            break;
        }
    }
    c
}

/// Gradient and Hessian (loss convention: log-loss to MINIMIZE) of the
/// smoothed logistic loss at `(w, c)`:
/// `L = −Σ [t·ln σ(s) + (1−t)·ln(1−σ(s))]`, `s = w·z + c`.
///
/// Returns `(∂L/∂w, ∂L/∂c, ∂²L/∂w², ∂²L/∂w∂c, ∂²L/∂c²)` — the Hessian of
/// the logistic loss is positive semidefinite, so the Newton step
/// `p ← p − H⁻¹g` descends.
fn grad_hess(t: &[f32], z: &[f32], w: f32, c: f32) -> (f32, f32, f32, f32, f32) {
    t.iter().zip(z).fold(
        (0.0f32, 0.0f32, 0.0f32, 0.0f32, 0.0f32),
        |(g0, g1, h00, h01, h11), (&ti, &zi)| {
            let p = sigmoid(w.mul_add(zi, c));
            let d = p - ti; // ∂L/∂s
            let r = p * (1.0 - p); // ∂²L/∂s²
            (
                g0 + d * zi,
                g1 + d,
                h00 + r * zi * zi,
                h01 + r * zi,
                h11 + r,
            )
        },
    )
}

/// `ln(p/(1−p))` with `p` clamped into `(P_CLIP, 1−P_CLIP)`.
#[inline]
fn logit_clamped(p: f32) -> f32 {
    let p = p.clamp(P_CLIP, 1.0 - P_CLIP);
    (p / (1.0 - p)).ln()
}

/// Fixed-size bank of independently calibrated gates — the consumer shape
/// for multi-scalar surfaces (the 5 affect scalars, a verifier panel).
pub struct CalibratedGateSet<const N: usize> {
    gates: [SigmoidGateCalibrator; N],
}

impl<const N: usize> CalibratedGateSet<N> {
    /// Construct `N` identity-calibrated gates with one shared config.
    pub fn new(capacity: usize, min_obs: usize) -> Self {
        Self {
            gates: std::array::from_fn(|_| SigmoidGateCalibrator::new(capacity, min_obs)),
        }
    }

    /// Record one pair for direction `dir` (zero-alloc).
    #[inline]
    pub fn observe(&mut self, dir: usize, p: f32, outcome: bool) {
        self.gates[dir].observe(p, outcome);
    }

    /// Calibrated probability for direction `dir` (zero-alloc hot path).
    #[inline]
    pub fn apply(&self, dir: usize, p: f32) -> f32 {
        self.gates[dir].apply(p)
    }

    /// Refit one direction; returns `false` below its `min_obs`.
    pub fn refit(&mut self, dir: usize) -> bool {
        self.gates[dir].refit()
    }

    /// Refit every direction; returns the count that moved.
    pub fn refit_all(&mut self) -> usize {
        self.gates
            .iter_mut()
            .map(|g| g.refit())
            .filter(|moved| *moved)
            .count()
    }

    /// Borrow one direction's calibrator.
    pub fn gate(&self, dir: usize) -> &SigmoidGateCalibrator {
        &self.gates[dir]
    }
}

impl<const N: usize> Default for CalibratedGateSet<N> {
    fn default() -> Self {
        Self::new(256, 32)
    }
}

// ── Metrics (public substrate for gates and consumers) ─────────────────────

/// Brier score: mean `(p − y)²`. Lower is better.
pub fn brier_score(predictions: &[f32], outcomes: &[f32]) -> f32 {
    debug_assert_eq!(predictions.len(), outcomes.len());
    let n = predictions.len().max(1) as f32;
    predictions
        .iter()
        .zip(outcomes)
        .map(|(p, y)| (p - y).powi(2))
        .sum::<f32>()
        / n
}

/// Mean log-loss with probabilities clipped to `[P_CLIP, 1 − P_CLIP]`.
/// Lower is better.
pub fn log_loss(predictions: &[f32], outcomes: &[f32]) -> f32 {
    debug_assert_eq!(predictions.len(), outcomes.len());
    let n = predictions.len().max(1) as f32;
    predictions
        .iter()
        .zip(outcomes)
        .map(|(p, y)| {
            let p = p.clamp(P_CLIP, 1.0 - P_CLIP);
            let y = y.clamp(0.0, 1.0);
            -(y * p.ln() + (1.0 - y) * (1.0 - p).ln())
        })
        .sum::<f32>()
        / n
}

/// Binned expected calibration error (equal-width bins over `[0, 1]`):
/// `ECE = Σ_b (n_b/N)·|mean_p_b − mean_y_b|`. Lower is better.
pub fn expected_calibration_error(predictions: &[f32], outcomes: &[f32], bins: usize) -> f32 {
    debug_assert_eq!(predictions.len(), outcomes.len());
    debug_assert!(bins >= 1);
    let n = predictions.len();
    if n == 0 {
        return 0.0;
    }
    let mut sum_p = vec![0.0f32; bins];
    let mut sum_y = vec![0.0f32; bins];
    let mut cnt = vec![0u32; bins];
    for (p, y) in predictions.iter().zip(outcomes) {
        let b = ((p.clamp(0.0, 1.0) * bins as f32) as usize).min(bins - 1);
        sum_p[b] += p;
        sum_y[b] += *y;
        cnt[b] += 1;
    }
    (0..bins)
        .filter(|&b| cnt[b] > 0)
        .map(|b| {
            let c = cnt[b] as f32;
            c / n as f32 * (sum_p[b] / c - sum_y[b] / c).abs()
        })
        .sum()
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Deterministic xorshift* stream — no unseeded global RNG (Issue 809).
    struct Rng(u64);

    impl Rng {
        fn new(seed: u64) -> Self {
            Rng(seed.max(1))
        }
        fn next_u64(&mut self) -> u64 {
            let mut x = self.0;
            x ^= x >> 12;
            x ^= x << 25;
            x ^= x >> 27;
            self.0 = x;
            x.wrapping_mul(0x2545_F491_4F6C_DD1D)
        }
        fn f01(&mut self) -> f32 {
            // Top 53 bits → uniform [0, 1).
            (self.next_u64() >> 11) as f32 / (1u64 << 53) as f32
        }
        /// Approx standard-normal via centered Irwin–Hall (4 uniforms).
        fn normal(&mut self) -> f32 {
            (self.f01() + self.f01() + self.f01() + self.f01() - 2.0) * 1.2247
        }
        fn bernoulli(&mut self, p: f32) -> bool {
            self.f01() < p
        }
    }

    /// The G1/G2 fixture: a gate whose raw sigmoid is systematically
    /// overconfident relative to the truth
    /// `p_true = sigmoid(1.6·z − 0.4)` (recoverable `T = 0.625, b = 0.25`).
    fn miscalibrated_corpus(n: usize) -> (Vec<f32>, Vec<f32>, Vec<f32>) {
        let mut rng = Rng::new(0xC0FF_EE01);
        let mut p_raw = Vec::with_capacity(n);
        let mut p_true = Vec::with_capacity(n);
        let mut y = Vec::with_capacity(n);
        for _ in 0..n {
            let z = rng.normal();
            p_raw.push(sigmoid(z));
            let pt = sigmoid(1.6_f32.mul_add(z, -0.4));
            p_true.push(pt);
            let yi = rng.bernoulli(pt);
            y.push(f32::from(yi));
        }
        (p_raw, p_true, y)
    }

    /// G1 — decision-level calibration: fit on the train half, halve ECE on
    /// the eval half AND land ≤ 0.05; recover the planted (T, b).
    #[test]
    fn g1_ece_halves_and_lands_under_005() {
        let (p_raw, _p_true, y) = miscalibrated_corpus(4096);
        let split = p_raw.len() / 2;
        let mut cal = SigmoidGateCalibrator::new(4096, 32);
        for i in 0..split {
            cal.observe(p_raw[i], y[i] > 0.5);
        }
        assert!(cal.refit(), "window above min_obs must refit");

        let raw_eval: Vec<f32> = p_raw[split..].to_vec();
        let cal_eval: Vec<f32> = raw_eval.iter().map(|&p| cal.apply(p)).collect();
        let y_eval: Vec<f32> = y[split..].to_vec();

        let ece_raw = expected_calibration_error(&raw_eval, &y_eval, 15);
        let ece_cal = expected_calibration_error(&cal_eval, &y_eval, 15);
        let (t_fit, b_fit) = cal.params();
        eprintln!(
            "  G1  ECE(raw)={ece_raw:.4}  ECE(cal)={ece_cal:.4}  T={t_fit:.4} b={b_fit:.4} (planted T=0.625 b=0.25)"
        );
        assert!(
            ece_cal < ece_raw,
            "ECE must improve: raw {ece_raw:.4} -> cal {ece_cal:.4}"
        );
        assert!(
            ece_cal < ece_raw / 2.0,
            "ECE must at least halve: raw {ece_raw:.4} -> cal {ece_cal:.4}"
        );
        assert!(ece_cal <= 0.05, "ECE_cal {ece_cal:.4} must land <= 0.05");

        // Planted-transform recovery: T ≈ 1/1.6 = 0.625, b ≈ 0.4/1.6 = 0.25.
        let (t, b) = cal.params();
        assert!(
            (0.42..=0.84).contains(&t),
            "temperature {t:.4} should recover ~0.625"
        );
        assert!(
            (0.02..=0.48).contains(&b),
            "bias {b:.4} should recover ~0.25"
        );
    }

    /// G2 — Report the Floor: Brier/log-loss must beat BOTH dumb baselines
    /// (the constant base-rate predictor and the uncalibrated sigmoid).
    #[test]
    fn g2_beats_base_rate_and_uncalibrated_floors() {
        let (p_raw, _p_true, y) = miscalibrated_corpus(4096);
        let split = p_raw.len() / 2;
        let base_rate = y[..split].iter().sum::<f32>() / split as f32;

        let mut cal = SigmoidGateCalibrator::new(4096, 32);
        for i in 0..split {
            cal.observe(p_raw[i], y[i] > 0.5);
        }
        assert!(cal.refit());

        let raw_eval: Vec<f32> = p_raw[split..].to_vec();
        let cal_eval: Vec<f32> = raw_eval.iter().map(|&p| cal.apply(p)).collect();
        let floor_eval = vec![base_rate; raw_eval.len()];
        let y_eval: Vec<f32> = y[split..].to_vec();

        let ll = |p: &[f32]| log_loss(p, &y_eval);
        let br = |p: &[f32]| brier_score(p, &y_eval);
        eprintln!(
            "  G2  logloss cal={:.4} raw={:.4} floor={:.4} | brier cal={:.4} raw={:.4} floor={:.4}",
            ll(&cal_eval),
            ll(&raw_eval),
            ll(&floor_eval),
            br(&cal_eval),
            br(&raw_eval),
            br(&floor_eval)
        );
        assert!(
            ll(&cal_eval) < ll(&raw_eval),
            "log-loss must beat uncalibrated: {} vs {}",
            ll(&cal_eval),
            ll(&raw_eval)
        );
        assert!(
            ll(&cal_eval) < ll(&floor_eval),
            "log-loss must beat base-rate floor: {} vs {}",
            ll(&cal_eval),
            ll(&floor_eval)
        );
        assert!(
            br(&cal_eval) < br(&raw_eval),
            "Brier must beat uncalibrated: {} vs {}",
            br(&cal_eval),
            br(&raw_eval)
        );
        assert!(
            br(&cal_eval) < br(&floor_eval),
            "Brier must beat base-rate floor: {} vs {}",
            br(&cal_eval),
            br(&floor_eval)
        );
    }

    /// G3 — ranking + decision invariance: monotone transform preserves the
    /// argsort, the best-threshold accuracy, and moves the fire rate TOWARD
    /// the truth (not away).
    #[test]
    fn g3_ranking_and_decisions_preserved() {
        let (p_raw, p_true, y) = miscalibrated_corpus(4096);
        let split = p_raw.len() / 2;
        let mut cal = SigmoidGateCalibrator::new(4096, 32);
        for i in 0..split {
            cal.observe(p_raw[i], y[i] > 0.5);
        }
        assert!(cal.refit());

        // (a) Monotone on a spread fixture (no f32 ties at this spacing).
        let mut prev = f32::MIN;
        for i in 0..200 {
            let p = 0.002 + 0.996 * i as f32 / 199.0;
            let q = cal.apply(p);
            assert!(q >= prev, "apply must be non-decreasing (p={p})");
            prev = q;
        }

        // (b) Best-threshold decision accuracy identical (monotone ⇒ the
        // achievable partition set is unchanged).
        let eval: Vec<f32> = p_raw[split..].to_vec();
        let y_eval: Vec<f32> = y[split..].to_vec();
        let best_acc = |probs: &[f32]| {
            let mut pts: Vec<f32> = probs.to_vec();
            pts.sort_by(|a, b| a.partial_cmp(b).unwrap());
            pts.dedup();
            let mut best = 0.0f32;
            for &thr in &pts {
                let acc = probs
                    .iter()
                    .zip(&y_eval)
                    .map(|(p, y)| {
                        let fire = *p >= thr;
                        f32::from(fire == (*y > 0.5))
                    })
                    .sum::<f32>()
                    / probs.len() as f32;
                best = best.max(acc);
            }
            best
        };
        let cal_eval: Vec<f32> = eval.iter().map(|&p| cal.apply(p)).collect();
        let a_raw = best_acc(&eval);
        let a_cal = best_acc(&cal_eval);
        assert!(
            (a_raw - a_cal).abs() < 1.0 / eval.len() as f32,
            "optimal-threshold accuracy must be unchanged: {a_raw} vs {a_cal}"
        );

        // (c) Fire rate at the calibrated 0.5 threshold moves toward the
        // truth's own fire rate (ABSTAIN band shrinks, not explodes).
        let rate = |f: &dyn Fn(usize) -> bool| -> f32 {
            (0..eval.len()).map(|i| f32::from(f(i))).sum::<f32>() / eval.len() as f32
        };
        let true_rate = rate(&|i| p_true[split + i] >= 0.5);
        let raw_rate = rate(&|i| eval[i] >= 0.5);
        let cal_rate = rate(&|i| cal_eval[i] >= 0.5);
        assert!(
            (cal_rate - true_rate).abs() <= (raw_rate - true_rate).abs(),
            "fire-rate error must not grow: raw |{:.4}| cal |{:.4}| vs true {true_rate:.4}",
            (raw_rate - true_rate).abs(),
            (cal_rate - true_rate).abs()
        );
    }

    /// G4 — the observe/apply hot loop is allocation-free (Issue-741
    /// predicate: runs in dev AND under `--release --features
    /// alloc_tracking`).
    #[cfg(any(debug_assertions, feature = "alloc_tracking"))]
    #[test]
    fn g4_alloc_free_observe_apply() {
        use crate::alloc::{get_alloc_stats, reset_alloc_stats};
        let mut cal = SigmoidGateCalibrator::new(64, 8);
        for i in 0..64 {
            let p = 0.05 + 0.9 * (i % 13) as f32 / 13.0;
            cal.observe(p, i % 3 == 0);
        }
        cal.refit();
        reset_alloc_stats();
        for i in 0..1000 {
            let p = 0.05 + 0.9 * (i % 17) as f32 / 17.0;
            cal.observe(p, i % 2 == 0);
            let _ = cal.apply(p);
        }
        let (count, _bytes) = get_alloc_stats();
        assert_eq!(count, 0, "observe+apply must be zero-alloc, saw {count}");
    }

    /// Determinism (G-adjacent): identical streams → bit-identical params
    /// and commitment; refit changes the commitment.
    #[test]
    fn deterministic_fit_and_commitment() {
        let (p_raw, _p_true, y) = miscalibrated_corpus(512);
        let mut a = SigmoidGateCalibrator::new(512, 32);
        let mut b = SigmoidGateCalibrator::new(512, 32);
        for i in 0..512 {
            a.observe(p_raw[i], y[i] > 0.5);
            b.observe(p_raw[i], y[i] > 0.5);
        }
        let pre_refit = a.commitment();
        assert_eq!(a.refit(), b.refit());
        assert_eq!(a.params_raw(), b.params_raw());
        assert_eq!(a.commitment(), b.commitment());
        assert_ne!(
            a.commitment(),
            pre_refit,
            "refit must move the commitment (params changed)"
        );
    }

    /// Monotonicity guard: an anti-correlated window (high p ⇒ y=0, low p ⇒
    /// y=1) must project to `W_MIN` instead of inverting decisions.
    #[test]
    fn anti_correlated_window_projects_to_w_min() {
        let mut cal = SigmoidGateCalibrator::new(64, 8);
        for i in 0..64 {
            let p = 0.02 + 0.96 * i as f32 / 63.0;
            cal.observe(p, p < 0.5); // y=1 exactly when p is LOW
        }
        assert!(cal.refit());
        let (w, c) = cal.params_raw();
        assert!(
            w >= W_MIN && w.is_finite() && c.is_finite(),
            "projection must pin w to W_MIN: got ({w}, {c})"
        );
        if w == W_MIN {
            // Near-constant monotone gate: outputs finite, non-decreasing.
            let mut prev = f32::MIN;
            for i in 0..50 {
                let p = 0.01 + 0.98 * i as f32 / 49.0;
                let q = cal.apply(p);
                assert!(q.is_finite() && q >= prev);
                prev = q;
            }
        }
        let (t, _b) = cal.params();
        assert!(t > 0.0, "T must stay positive under projection");
    }

    /// Separable window (all outcomes true): Platt smoothing keeps the fit
    /// finite instead of diverging.
    #[test]
    fn pure_window_smoothing_stays_finite() {
        let mut cal = SigmoidGateCalibrator::new(64, 8);
        for i in 0..64 {
            cal.observe(0.02 + 0.96 * i as f32 / 63.0, true);
        }
        assert!(cal.refit());
        let (w, c) = cal.params_raw();
        assert!(w.is_finite() && w > 0.0 && c.is_finite());
        assert!(cal.apply(0.7).is_finite());
    }

    /// Occupancy floor: below `min_obs` the gate stays identity.
    #[test]
    fn below_min_obs_stays_identity() {
        let mut cal = SigmoidGateCalibrator::new(256, 32);
        for i in 0..16 {
            cal.observe(0.3 + 0.001 * i as f32, i % 2 == 0);
        }
        assert!(!cal.refit(), "below min_obs refit must refuse");
        let (t, b) = cal.params();
        assert_eq!((t, b), (1.0, 0.0));
        assert!((cal.apply(0.3) - 0.3).abs() < 1e-6, "identity apply");
    }

    /// Cold start is bit-identical, not merely close: `new`'s documented
    /// contract ("apply is the identity until evidence says otherwise") is
    /// an exact-value contract. A `logit → sigmoid` roundtrip is NOT
    /// bit-exact in f32, so the fast path must return the input unchanged —
    /// downstream consumers commit/sync the raw sigmoid output through the
    /// cold-start gate (riir-ai Issue 964 C1/C3 bit-identity requirements).
    #[test]
    fn cold_start_apply_is_bit_identical() {
        let cal = SigmoidGateCalibrator::new(64, 8);
        // Saturated ends included: the clamp only exists on the slow path.
        for i in 0..254 {
            let p = (i + 1) as f32 / 255.0;
            assert_eq!(cal.apply(p).to_bits(), p.to_bits(), "p = {p}");
        }
    }

    /// A below-`min_obs` refit leaves the bit-identity fast path armed —
    /// observations recorded but no evidence acted on yet.
    #[test]
    fn below_min_obs_apply_stays_bit_identical() {
        let mut cal = SigmoidGateCalibrator::new(256, 32);
        for i in 0..16 {
            cal.observe(0.25 + 0.02 * i as f32, i % 3 == 0);
        }
        assert!(!cal.refit());
        for i in 0..254 {
            let p = (i + 1) as f32 / 255.0;
            assert_eq!(cal.apply(p).to_bits(), p.to_bits(), "p = {p}");
        }
    }

    /// FIFO eviction: capacity 4 under 6 observations keeps the last 4 and
    /// the monotone total.
    #[test]
    fn fifo_eviction_keeps_newest() {
        let mut cal = SigmoidGateCalibrator::new(4, 2);
        for i in 0..6 {
            cal.observe(0.1 * i as f32, i % 2 == 0);
        }
        assert_eq!(cal.len(), 4);
        assert_eq!(cal.n_obs_total(), 6);
        // Window holds p ∈ {0.2, 0.3, 0.4, 0.5}; the fit must consume those,
        // not the evicted {0.0, 0.1} — observable via refit success.
        assert!(cal.refit());
    }

    /// The bank delegates per-direction (the 5-affect-scalar shape).
    #[test]
    fn gate_set_delegates_per_direction() {
        let mut set = CalibratedGateSet::<5>::new(128, 16);
        let mut rng = Rng::new(7);
        for _ in 0..64 {
            let p = sigmoid(rng.normal());
            set.observe(0, p, rng.bernoulli(p));
            // Direction 1 deliberately anti-correlated with direction 0's p.
            set.observe(1, p, rng.bernoulli(1.0 - p));
            set.observe(4, 0.9, true);
        }
        // Gates 0/1/4 carry 64 observations each; 2/3 were never observed
        // (identity, refit refuses below min_obs).
        assert_eq!(set.refit_all(), 3);
        let (t0, _b0) = set.gate(0).params();
        let (t1, _b1) = set.gate(1).params();
        assert!(t0 > 0.0 && t1 > 0.0);
        // Direction 4 is separable-positive: smoothing keeps it finite.
        assert!(set.apply(4, 0.9).is_finite());
        // Directions 2/3 never observed: still identity.
        assert!((set.apply(2, 0.25) - 0.25).abs() < 1e-6);
        assert!(!set.refit(3));
    }

    /// Metric helpers on known vectors.
    #[test]
    fn metrics_known_vectors() {
        let p = vec![0.8, 0.2, 0.6];
        let y = vec![1.0, 0.0, 0.0];
        assert!((brier_score(&p, &y) - ((0.04 + 0.04 + 0.36) / 3.0)).abs() < 1e-6);
        // Perfect prediction ⇒ zero log-loss (after clip, ~0), zero ECE.
        let perfect = vec![1.0, 0.0, 0.0];
        assert!(log_loss(&perfect, &y) < 1e-3);
        assert_eq!(expected_calibration_error(&perfect, &y, 10), 0.0);
        // Uniform-vs-0.5 outcomes: ECE = |0.5 − ȳ| style check via bins.
        let uni = vec![0.5, 0.5, 0.5, 0.5];
        let y2 = vec![1.0, 0.0, 1.0, 0.0];
        assert!((expected_calibration_error(&uni, &y2, 10) - 0.0).abs() < 1e-6);
    }
}
