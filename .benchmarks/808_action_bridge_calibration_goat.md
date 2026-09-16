# Bench 808: ActionBridge Confidence-Calibration GOAT — riir-ai Issue 964 C2 (second `sigmoid_calibration` consumer)

**Date:** 2026-09-16
**Issue:** [riir-ai 964 C2](../../riir-ai/.issues/964_sigmoid_calibration_consumers.md) · substrate: katgpt-rs Issue 810 · first consumer: Bench 807 (`clr_calibration`)
**Surface:** `sigmoid_calibration` feature (no new flag) — `bridge::calibrated::CalibratedActionBridge<A, D>`
**Gate:** `benches/bench_808_action_bridge_calibration_goat.rs` (katgpt-core, `harness = false`)
**Run:**
```bash
CARGO_TARGET_DIR=/tmp/bench808 cargo bench -p katgpt-core \
  --features sigmoid_calibration,action_bridge --no-default-features \
  --bench bench_808_action_bridge_calibration_goat -- --nocapture
```

## What landed

`CalibratedActionBridge<A, D>` (`crates/katgpt-core/src/bridge/calibrated.rs`)
wraps `ActionBridge` with the Platt calibrator: observe
`(raw sigmoid confidence, action_succeeded)` whenever the outcome of a
selected action is known (riir-engine `arg_runtime` Step 9's
`InfoOutcomeStatus` is the production signal), refit off-hot-path, and report
the CALIBRATED confidence against the ABSTAIN threshold — a threshold on an
uncalibrated score is a threshold on a number whose meaning is proven
nowhere; calibrated, `conf < τ` becomes a statement about outcome
probability.

**The argmax invariant**: the winner is chosen on raw scores exactly as
`select_action` does; one strictly monotone transform on the shared score
scale cannot reorder it — calibration never changes WHICH action wins, only
what its confidence means. Pinned by gate, not just argued.

## Gate results (deterministic, planted overconfidence `p_true = sigmoid(1.4·logit(p) − 0.3)`, train/test 4096/4096, A=4, D=3)

| Gate | Measure | Result | Pass? |
|---|---|---|---|
| G1 | decision-level ECE (test split) | 0.0220 → **0.0088** (2.5×; ≤ 0.05) | ✅ |
| G1 | planted-transform recovery | (T, b) = (0.732, 0.171) vs planted (0.714, 0.214) — within 0.05 | ✅ |
| G2 | log-loss (Report the Floor) | cal 0.3952 < raw 0.3997 < base-rate floor 0.4615 | ✅ |
| G2 | Brier (Report the Floor) | cal 0.1259 < raw 0.1265 < base-rate floor 0.1435 | ✅ |
| G3a | cold start | confidences + ABSTAIN decisions bit-identical | ✅ |
| G3b | argmax invariant after real refit | 0 winner mismatches | ✅ |
| G3c | ABSTAIN operating point (τ=0.75) | raw 0.3315 → cal 0.2764; oracle 0.2866 — error 0.0451 → **0.0102** (4.4× closer, katgpt-rs G3 fire-rate shape) | ✅ |
| G4 | observe+select allocs (4096-loop) | **0** (per-thread `counting_allocator!`, Issue 714 idiom) | ✅ |

## Honest caveats

- **The planted overconfidence is mild at the corpus level** (raw ECE 0.0220
  vs Bench 807's 0.0924): with A=4 ternary directions and D=3, raw
  confidences cluster high, so the planted transform moves less mass. The
  G2 margins are correspondingly thin (log-loss Δ0.0045) — real but not
  dramatic; the ABSTAIN operating-point movement (G3c, 4.4× toward oracle)
  is the load-bearing consumer-level result.
- **Recovery bias**: fitted b=0.171 vs planted 0.214 — within the 0.05 band
  but not the ~0.002 recovery of Bench 807; the A=4 decision corpus has less
  low-confidence mass to pin the intercept (few points below p=0.1).
- **The riir-ai pipeline half remains**: `arg_runtime/pipeline.rs` Step 8
  still calls the bare bridge; wiring `CalibratedActionBridge` + observing
  at Step 9 (`InfoOutcomeStatus`) is the riir-ai follow-on this bench
  unblocks. The primitive, gates, and contract all live here.

## No-regression evidence

- katgpt-core `--lib` default: 2060/0 (floor holds).
- Bridge tests: 21/21 at `sigmoid_calibration,action_bridge` (17 prior + 4
  new); doctest 1/1.
- `cargo check -p katgpt-core --no-default-features` clean (isolation);
  default + `sigmoid_calibration` clean.
- clippy `-D warnings --all-targets` at `sigmoid_calibration` clean.
