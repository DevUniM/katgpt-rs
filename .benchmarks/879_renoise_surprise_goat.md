# Bench 879 — Issue 875 T4: target-anchored renoise-CE surprise GOAT

**Status:** GOAT PASS (G1 + G2-quality + G2-latency + G3-consumer + G4) — 2026-09-23
**Commit:** (this commit) · **Session:** 4090-queue-triage continuation, worktree `wt875t4`
**Gate:** `tests/bench_875_renoise_surprise_goat.rs` (`required-features = ["renoise_ce_surprise"]`) + in-module `renoise_ce::tests::surprise` (14 tests)

## What shipped

`renoise_ce_surprise` (opt-in `renoise_ce_surprise = ["renoise_ce"]`, katgpt-core + root passthrough) — the target-anchored renoise-CE probe mode, PFD's resolve-against-the-teacher variant (Research 582 / arXiv:2605.09071). Same k-draw loop, NFE budget, and allocation profile as the incumbent `renoise_ce_score`; the ONE semantic delta: each re-resolved draw is scored against a caller-supplied frozen TARGET anchor instead of the candidate itself. The score stops being self-consistency ("is this state a stable fixed point of the operator") and becomes **distributional surprise** ("where does this state flow, relative to what the prior expected").

Implementation note: the three public score fns (`renoise_ce_score`, `renoise_ce_score_horizon`, `renoise_ce_surprise`) now share one private `renoise_k_draws` loop (anchor + per-draw level closure). The incumbent's RNG stream and float op order are preserved exactly — the fixed-level closure consumes no rng draws; validated by the untouched default-suite count (2063/0) and `bench_406` 5/5.

## The gate world — flow-relative novelty (the shell)

Every candidate sits at the SAME whitened radius R = 0.9·L from the prior center (L = 2.6 = the foreign attractor's distance). Stable states point away from the foreign attractor (cos ≤ 0.30); planted states point into its capture cap (cos ≥ 0.75). D = 8, k = 8, level 0.40, house noise ×2.0 (T2's constants), α = 0.9 snap+contract operator, one deterministic fastrand seed (87_504).

- **Plain distance is blind by construction** — all candidates are equidistant from the prior anchor (asserted in G1: shell holds to < 0.01).
- **Self-consistency ANTI-ranks novelty** — a state resting comfortably in ANY basin (foreign included) is the most self-stable; incumbent precision 0.000 is the measured proof of the mode's motivating gap.
- Only the flow through the operator, scored against the prior anchor, separates.

## Results (release, equal k=8 budget)

| arm | precision@32 (novelty) |
|---|---|
| `renoise_ce_surprise` (T4) | **1.000** |
| incumbent `renoise_ce_score` (self-consistency) | **0.000** (anti-ranked) |
| plain whitened distance (no operator) | **0.500** (chance on the shell) |

Python mirror sweep (`k875t4_sim.py` v7, 200 seeds): surprise 1.000±0.002 (min 0.969), incumbent 0.000, plain 0.428 — margins ≥ 2 candidates held **200/200 seeds**; the pinned Rust seed sits mid-distribution.

**G2-latency:** median surprise/incumbent **0.9994** (−0.1%, 41/41 interleaved rounds survived, shared `ab_timing` harness, release) — unchanged class, as expected from an identical loop shape.

**G3 consumer sketch:** consolidation surprise ordering — rank shards by surprise descending; the Raven/δ-Mem sleep-cycle admission head is ≥ 0.90 planted at HALF budget (k=4) and the deferral tail is ≥ 0.90 stable. Ordering-only; no consolidation behavior rides the score.

**G4:** zero allocs on the score path with fixed-array State (TrackingAllocator, 64 runs) — pinned in-module.

**G3 no-regression:** default lib 2063/0 (count unchanged), `bench_406_renoise_ce_goat` 5/5, `--no-default-features` clean (bare + feature), wasm32 clean (bare + feature), clippy `-D warnings` clean at default / `horizon_weights,renoice_ce_surprise` / the new test target.

## Honest regime boundary

The shell world isolates the mechanism the mode exists for. Sim sweeps of NEARBY worlds (v5 single-reading noisy-offset, v6 window worlds, Gaussian + heavy-tailed spikes, σ_obs × shift grids, 60 seeds each) showed: **where pointwise distance already sees the displacement, plain distance is a strong ranker (0.87–0.95+) and the mode adds little or nothing** — its win is flow-relative novelty (basin membership invisible pointwise), not generic drift detection. Consumers should reach for this mode when novelty is defined against a prior AND the operator's basin structure is the discriminator — the consolidation-ordering case (a shard whose content flows to a foreign basin under the consolidation operator is novel regardless of its pointwise distance to the prior centroid). Also recorded: the observation-noise ceiling — with a single noisy reading baked into the candidate, ~Φ(−s/2) of planted shards are information-theoretically indistinguishable (their obs canceled the displacement); windows/multi-reading states are the consolidation-faithful remedy and remain consumer territory.

`tau` does NOT transfer between modes (anchor changed — same caveat class as T2). NOT a UQ primitive (ranking signal only).

## Verdict

Stays **OPT-IN** (`renoice_ce_surprise`, implies `renoise_ce`) per the no-default-consumer rule; promotion is Issue 875 T5's verdict. T4 CLOSED.
