# Issue 819: Sigmoid prior-logit lane + sink stability forecast (Research 566, arXiv:2601.15380)

**Status:** Open — modelless poc/proof task; GOAT gate decides promote (feature-gated throughout)

**Source:** [Research 566](../.research/566_EOT_Attention_Prior_Logit_Sigmoid_Analog.md) — "You Need Better Attention Priors" (arXiv:2601.15380, ICML 2026) + the note's sigmoid-EOT derivation (no published prior art; verified 2026-09-17).

**Why:** Two actionable, zero-training extractions land on shipped substrate:

1. **Sink stability forecast** — the paper's margin law (`Ψ ≤ (L−1)/(e^δ+L−1)`, δ ~ ln L) turns our *descriptive* sink classifier (`data_probe/sink_classify.rs`, Plan 287) into a *predictive* one: a measured prior/content logit margin δ forecasts the context length a sink head protects (N ≈ e^δ). No published diagnostic does this.
2. **Prior-logit lane** — the sigmoid-EOT closed form `g*_j = σ(s_j/τ + logit π_j)` generalizes the shipped constant `SigmoidFusionConfig.logit_bias` (Plan 364 = constant-π special case) to a **key-dependent** prior logit `ℓ_j` — the sigmoid counterpart of the paper's rank-1 sink lane u(j). The margin law is *stricter* for sigmoid (uniform prior ⇒ context mass grows linearly in L; no normalization to absorb noise), which gives the negative-bias default its first-principles stability footing.

Modelless throughout: closed forms + measured logits; no training, no weight mutation.

## Tasks

- [ ] **T1 — Margin + forecast on the sink classifier.** Extend `SinkDiagnostic` (feature-gated, e.g. `sink_margin_forecast`) with `margin: Option<f32>` (prior-logit margin for the sink lane proxy: measured sink-key logit minus context logit centroid, or content-score range ω when no structural lane exists — define and document the estimator) + `forecast_stable_positions(delta: f32) -> f32` returning `e^δ`. Zero-alloc, scratch extends `StableRankScratch` convention. G1: forecast agrees with brute-force sensitivity sims on toy margins; G3: O(1) post-scan.
- [ ] **T2 — Per-key prior-logit lane.** `SigmoidFusionConfig` gains `#[cfg(feature = "prior_logit_lane")] prior_logits: Option<&[f32]>` (or an owned SmallVec-style fixed cap) consumed as `gate = σ(ndot/τ + bias_or_lane)`; `None` = bit-identical constant path (extend the `logit_bias_zero_is_bit_identical_at_every_input` test pattern to the lane-off path). Mirrors in `sigmoid_fuse_scaled_into`. G1 + G5 bit-identity, G4 zero-alloc.
- [ ] **T3 — Length-aware law + docs.** Module doc: the sigmoid margin law `‖Δo‖ ≤ ε·(L−1)·e^{ω−δ}` ⇒ δ ≳ ω + ln L, the uniform-prior linear-growth instability, and the constant-bias reading as maximum-entropy-style default prior. Test: planted-distractor toy where per-key lane beats constant bias in low-signal selectivity (G2).
- [ ] **T4 (optional, training-track, gated behind T1–T3 + owner pull).** 0.4B Kimi-K3 test-arch arm: RoPE baseline vs +learnable spectral prior lanes vs +sink lane (paper's App-F parameterization; MLA's existing content+rope lane split is the structural slot). Axes: ppl + passkey/NIAH extrapolation, ~hours-class on the 4090. Graduates to a riir-train plan only on owner pull.
- [ ] **T5 — Cross-refs.** Landing note in Research 566 §4 table (filed → landed), one-line pointers from Research 258 / 392 if not already present.

## Non-goals

- No retrofit of served GGUF checkpoints (Bonsai/qwen3.8): prior lanes are an architecture change.
- No HLA port (negative transfer: linear attention cannot express negative spectral weights — paper App C).
- No riir-train plan filed now (no from-scratch retrain on the roadmap).

## References

- Research 566 (this issue's parent note)
- Research 258 / Plan 287 (`sink_aware_attn` classifier — T1's host)
- Research 392 / Plan 411 (`ssmax_temperature`, `gold_share_probe` — composing content-axis fix; signal-diff recorded in Research 566 §2)
- Plan 364 (`logit_bias` field — T2's constant special case)
