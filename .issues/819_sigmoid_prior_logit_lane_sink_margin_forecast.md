# Issue 819: Sigmoid prior-logit lane + sink stability forecast (Research 566, arXiv:2601.15380)

**Status:** Resolved 2026-09-17 — T1–T3 + T5 LANDED (Bench 813 G1–G4 ALL PASS); both features opt-in (no-default-consumer rule); T4 owner-gated, closed unclaimed

**Source:** [Research 566](../.research/566_EOT_Attention_Prior_Logit_Sigmoid_Analog.md) — "You Need Better Attention Priors" (arXiv:2601.15380, ICML 2026) + the note's sigmoid-EOT derivation (no published prior art; verified 2026-09-17).

**Landing record:** [Bench 813](../.benchmarks/813_prior_lane_margin_goat.md) — lane ratio 1.004× (≤1.10 gate), forecast 1.3 ns, 0 allocs, 14 new tests, feature-off builds bit-identical (2063 default-lib green). Honest deviations (lane home = ParallaxConfig multi-key, not SigmoidFusionConfig single-key; total-logit margin estimator; no scratch extension needed) recorded there.

**Why:** Two actionable, zero-training extractions land on shipped substrate:

1. **Sink stability forecast** — the paper's margin law (`Ψ ≤ (L−1)/(e^δ+L−1)`, δ ~ ln L) turns our *descriptive* sink classifier (`data_probe/sink_classify.rs`, Plan 287) into a *predictive* one: a measured prior/content logit margin δ forecasts the context length a sink head protects (N ≈ e^δ). No published diagnostic does this.
2. **Prior-logit lane** — the sigmoid-EOT closed form `g*_j = σ(s_j/τ + logit π_j)` generalizes the shipped constant `SigmoidFusionConfig.logit_bias` (Plan 364 = constant-π special case) to a **key-dependent** prior logit `ℓ_j` — the sigmoid counterpart of the paper's rank-1 sink lane u(j). The margin law is *stricter* for sigmoid (uniform prior ⇒ context mass grows linearly in L; no normalization to absorb noise), which gives the negative-bias default its first-principles stability footing.

Modelless throughout: closed forms + measured logits; no training, no weight mutation.

## Tasks

- [x] **T1 — Margin + forecast on the sink classifier.** LANDED: `SinkDiagnostic.margin: Option<f32>` + `forecast_stable_positions(δ) = e^δ` behind `sink_margin_forecast`. Estimator = mean sink-column logit − mean context logit (exact closed form `δ̂ = (n·c̄_s − R̄)/(n−1)`), `[1e-6, 1−1e-6]` logit clamp, computed by the full-map scan paths only (single-column = `None`, no context). G1: planted-margin recovery (constant + query-varying) + brute-force sensitivity sims agree with the bound; G3: O(1) forecast (1.3 ns) + O(n²) pass in the col_sums class. NOTE: the scratch extension proved unnecessary — two scalar accumulators.
- [x] **T2 — Per-key prior-logit lane.** LANDED behind `prior_logit_lane`: `ParallaxConfig::prior_logits: Option<Arc<[f32]>>` (multi-key host — the engram kernel is single-key where the lane degenerates to `logit_bias` assignment; deviation documented in Bench 813). `None` = bit-identical (lane-off branch is the literal pre-lane loop; zeros-lane also output-identical — tested). Mirrors at BOTH score sites (core + parallax-correction loop); prior enters AFTER SSMax (unscaled), BEFORE normalization. G1 + G5 bit-identity, G4 zero-alloc (lane-on == lane-off == 0). An `Option<&[f32]>` field was tried and REVERTED (E0392 unused lifetime when the field is cfg'd out in parallax-without-lane builds).
- [x] **T3 — Length-aware law + docs.** LANDED: `parallax_attn` module docs (law `‖Δo‖ ≲ ε·(L−1)·e^{ω−δ}` ⇒ δ ≳ ω + ln L; uniform-prior linear-growth instability; constant-bias = max-ent default prior), `SigmoidFusionConfig::logit_bias` doc (constant-prior special case + per-call expression), `sink_classify` module docs (estimator). G2 test: planted-distractor — constant bias provably cancels to uniform (b ∈ {−4,−1,0,2} verified), per-key lane breaks the symmetry at the KL-prior closed form.
- [-] **T4 (optional, training-track, gated behind T1–T3 + owner pull).** Deferred per the gate — no owner pull; no riir-train plan filed. The recipe sketch stands in Research 566 §6 (0.4B Kimi-K3 test-arch, RoPE baseline vs +spectral lanes vs +sink lane, ppl + passkey/NIAH axes, ~hours-class on the 4090).
- [x] **T5 — Cross-refs.** Research 566 §4 table (filed → landed), Research 258/392 one-line pointers, issue status line.

## Non-goals

- No retrofit of served GGUF checkpoints (Bonsai/qwen3.8): prior lanes are an architecture change.
- No HLA port (negative transfer: linear attention cannot express negative spectral weights — paper App C).
- No riir-train plan filed now (no from-scratch retrain on the roadmap).

## References

- Research 566 (this issue's parent note)
- Research 258 / Plan 287 (`sink_aware_attn` classifier — T1's host)
- Research 392 / Plan 411 (`ssmax_temperature`, `gold_share_probe` — composing content-axis fix; signal-diff recorded in Research 566 §2)
- Plan 364 (`logit_bias` field — T2's constant special case)
