# Bench 843 — Plan 602 Phase 3: AR-ness × w cross-tab + the residual gap-predictor G3 gate

**Status:** COMPLETE — G3 PASS (no-regression floor, both regimes) + regime discrimination demonstrated; promotion decision below.
**Date:** 2026-09-20
**Plan:** [602](../.plans/602_decode_order_arness_instrument.md) · **Research:** [575](../.research/575_dQwen3.5_Hybrid_Attention_DLM.md) (arXiv:2609.20751)
**Feature:** `decode_order_metrics` (root: implies `set_diffusion`; core+forward forwards)
**Instrument:** `src/benchmark/diffusion.rs::bench_ar_ness_w_sweep` + `tests/bench_602_ar_ness_cross_tab.rs`
**Box:** 4090 workstation (Windows/MSVC), DEBUG profile for the shape/G3 assertions — numbers below are shape-verdicts, not perf claims (the profile is part of the claim; the G3 gate is a quality-retention verdict, profile-independent in its pass/fail semantics).

## 1. T3.1 — the cross-tab (the measured explanation axis)

One `train_mini_set_causal` model at the SW-SetDLM default (w=0.5, L=8/V=8/300ep/lr 0.01 —
the validated GOAT-fixture shape; **L=16 measured to diverge to NaN weights at this lr**, recorded in the bench comment). Inference-w sweep, 16 seeded greedy decodes each (τ=0.5, temp 0), plus the mdlm parallel endpoint:

| w | ALR | AGR | NELBO | NFE | conv |
|---|-----|-----|-------|-----|------|
| 0.10 | 1.000 | 1.000 | 0.0000 | 8.0 | 16/16 |
| 0.30 | 0.804 | 0.944 | 0.0000 | 8.0 | 16/16 |
| **0.50** | **0.589** | **0.797** | 0.0001 | 8.0 | 16/16 |
| 0.70 | 0.580 | 0.701 | 0.0001 | 8.0 | 16/16 |
| 0.90 | 0.536 | 0.562 | 0.0001 | 8.0 | 16/16 |
| 1.00 | 0.518 | 0.547 | 0.0001 | 8.0 | 16/16 |
| mdlm | 0.000 | 0.000 | (degenerate floor) | 1.0 | 16/16 |

**Reading.** The winner (w=0.5) sits at ALR 0.589 — the paper's hybrid band (local AR-ness
0.63–0.65 for the DLM comparators), globally left-to-right (AGR 0.797). The axis semantics
pinned in-code: eligibility is CUMULATIVE (`gen_step <= current_step`), so permutation
schedules decode with singleton outer steps — w acts through ORDER correlation; the true
parallel endpoint is the separate mdlm arm (ALR = 0 by the ties-discordant contract). NELBO
is saturated on the pattern cell (Bench-809 Cell-A class) — the quality discriminator is
the real-text lane (§2). The calibrated signature table ships as
`katgpt_core::ORDER_STATS_TO_W_TABLE` — the predictor's calibration, one place to re-measure.

## 2. T3.2 — the residual gap-predictor + G3 (real-text lane, both regimes)

Two denoiser models (Bench-809 Cell-B protocol: Austen char-level, 2048/512 blocks, 40ep,
mask 0.5 — the **denoiser** objective; the clean-token objective degenerates to identity
copy, nelbo→0.0000 measured, the g5 lesson reproduced on the first run): one trained under
AR reveal, one under uniform reveal. Final masked NLL: AR 2.754, UNI 2.908.

**The probe journey (measured, kept honest in the test output):**

1. *mdlm-endpoint probe* (all-eligible-at-once, nearest-row prediction): does NOT
   discriminate — a confident model commits everything on pass 0 → all-ties → (0,0) for
   both regimes. A τ-calibration sweep (0.15–0.55) was added; at the most-discriminating
   τ=0.15 the separation is 0.262 but BOTH map to w*=1, and that arm FAILS retention
   (AR: 3.001 vs best-fixed 2.711, retention 0.903 < 0.95). Recorded as the wrong posture.
2. *residual probe* (decode under the KNOWN w=0.5 schedule; measure ΔALR vs the
   calibrated 0.589): **AR-trained ΔALR = +0.144, UNI-trained ΔALR = +0.015** — the model's
   AR-drag, the paper's actual measurement posture. `predict_w_residual(alr, agr, 0.5)`
   (SHIFT=2): w*_AR = **0.211**, w*_UNI = **0.470**.

**G3 table (denoiser NLL on held-out, fixed reveal arms vs predictor-chosen):**

| model | w* | NLL(w*) | fixed w=0.1 | w=0.5 | w=1.0 | retention vs best fixed |
|---|---|---|---|---|---|---|
| AR-trained | 0.211 | 2.7925 | 2.711 | 2.960 | 3.001 | **0.9708** ≥ 0.95 ✓ |
| UNI-trained | 0.470 | 2.8816 | 2.866 | 2.884 | 2.891 | **0.9946** ≥ 0.95 ✓ |

**Verdict: G3 PASS on the no-regression floor (T3.3's retention ≥ 0.95, both regimes) +
regime discrimination demonstrated** (w*_AR < w*_UNI, asserted). The improvement axis:
the predictor does not BEAT the best fixed arm (w=0.1 wins both fixtures by a hair) — what
it does is **regime-adaptive avoidance of the worst arm**: on the AR-regime model the naive
incumbent w=0.5 costs +0.25 NLL and w=1.0 costs +0.29; the predictor lands at 2.79, within
3% of the oracle-best without knowing the regime a-priori, from ONE 8-decode probe.
On the order-agnostic model every arm ties (as theory predicts) and the predictor holds 0.995.

## 3. Gates summary

| gate | result |
|---|---|
| T3.1 shape: endpoint span, uniform≈0.5, mdlm undercut, label parse | PASS (2 tests) |
| T3.2 discrimination: w*_AR < w*_UNI via the residual probe | PASS (asserted) |
| T3.2 G3 no-regression: retention ≥ 0.95 both regimes | PASS (0.9708 / 0.9946) |
| T3.3 retention floor constant wired as the G3 tolerance | PASS (RETENTION=0.95) |
| Predictor unit contracts (table inversion, endpoints, conservatism, residual shift) | PASS (core 2100/2063 on/off) |

## 4. Promotion decision

**decode_order_metrics stays OPT-IN.** G3's no-regression floor passes and discrimination
is real, but (a) the improvement target (predictor strictly beats fixed at matched NFE) is
NOT met on this fixture — the best fixed arm edges it on both models; (b) the fixture is
micro-scale real-text (L=9, V=32); the paper's regime claims are 2–9B-parameter hybrids.
The honest state: the instrument + predictor are validated as measurement/adaptivity
substrate; promotion to default waits for a consumer that needs it (riir-train Plan 414's
decode-order readout on adapted-model trajectories is the designated next customer) or a
fixture where the improvement axis clears. Per the plan's standing rule: demote silently
if a future re-gate fails.

## 5. Reproduce

```bash
cargo test -p katgpt-core --lib --features decode_order_metrics   # 2100 (predictor contracts)
cargo test --test bench_602_ar_ness_cross_tab --features decode_order_metrics -- --nocapture  # ~4 min (G3 trains 2 models)
cargo run --release --features decode_order_metrics --release -- bench   # the harness lane (Phase 12)
```
