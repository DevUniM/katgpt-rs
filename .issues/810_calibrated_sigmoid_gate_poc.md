# Issue 810: Calibrated sigmoid gate (Platt-style refit) — poc/proof

**Status:** OPEN — filed from Research 562 (TypeSafe "System One Models"/Jev distill, 2026-09-16)
**Repo:** katgpt-rs (primitive) → riir-ai (first consumers)
**Kind:** poc + proof (optimization task; plan comes after the PoC proves the gain, per GOAT discipline)

## Problem

Every decision/confidence scalar in the stack is a sigmoid output — ActionBridge
`sigmoid_confidence` (riir-ai `arg_runtime/pipeline.rs`), the 5 affect scalars
(`project_belief_to_raw_signature`), belief-decay, curiosity gates, CLR verifier —
and their calibration is proven **nowhere** except CLR's own ECE gate (≤0.10,
measured 0.0087). Lean proves boundedness (range (0,1)); nothing proves the
numbers *mean* anything ("fear=0.8" is not known to fire ~80% of the time).
Research 562 (Jev distill) prices this gap: calibrated confidence is the part of
the "System One" pitch that is real, published (Platt/Guo/Kadavath), and missing
here.

## Proposed primitive (modelless, track-b)

`katgpt-core` new module `sigmoid_calibration` behind feature flag
`sigmoid_calibration`:

- Record `(sigmoid_output, binary outcome)` pairs per direction (ring buffer, fixed capacity).
- Refit 2 params (temperature `T`, bias `b`): `p_cal = sigmoid((logit(p) - b) / T)` — small convex fit over recorded pairs; refit on cadence or EMA. No base-weight mutation, zero-alloc hot path (apply is one logit+sigmoid).
- Freeze/version the params (BLAKE3-committed snapshot, freeze/thaw consumed like any snapshot).
- Monotonicity guard: `T > 0` enforced (calibration must never reorder decisions).

## Gates

- **G1 (calibration):** decision-level ECE after fit ≤ uncalibrated ECE, target ≤ 0.05 on a fixture corpus. **Decision-level** (chosen action vs outcome), not only per-scalar — the composite-calibration lesson from Research 562 §5.3.
- **G2 (floor):** Brier/log-loss beats the Bench-706-style sigmoid floor (`sigmoid(k·(match_fraction−0.5))` convention); cite Research 322 Report-the-Floor rule.
- **G3 (no regression):** decision accuracy unchanged (G3 = ranking preserved via T>0 guard; ABSTAIN rate within band).
- **G4:** alloc-free apply path; params fit is off-hot-path.

## Consumers (in order)

1. CLR verifier — already ECE-gated; becomes first calibrated consumer (its gate tightens from "bounded" to "calibrated").
2. ActionBridge `sigmoid_confidence` + ABSTAIN threshold — calibrated p makes the threshold meaningful.
3. The 5 affect scalars — local monotone transform only; raw sync boundary untouched (still raw 5-scalar sync, sigmoid not softmax).
4. (follow-on, riir-clippy) outcome-fitted `W_EVO`/`W_RATE` selection weights — `EvolveRecorder::record_outcome` already fires on every applied fix.

## Related

- Research: katgpt-rs `.research/562_Typesafe_SystemOne_Jev_Calibrated_Decisions.md`
- Substrate to consume (never re-derive): `ConformalIntervalCalibrator` (Plan 340), CLR ECE harness (Bench 284), Bench 706 Brier-vs-floor precedent.
- Prior art: Platt 1999; Guo et al. 2017 (arXiv:1706.04599); Kadavath 2022 (arXiv:2207.05221); RLCR (arXiv:2507.16806) for the training-track variant if a trained head ever exists.
