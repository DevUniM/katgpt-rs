# Bench 815 — Coulomb crowd-redistribution PoC (Issue 825 T1+T2)

**Date:** 2026-09-18
**Issue:** [Issue 825](../.issues/825_coulomb_crowd_redistribution_dec.md) — T1 (DEC Coulomb PoC on a toy zone graph) + T2 (the 20×-bias analog gate). The negative/honest-mixed outcome clause of the issue's T3 applies: the endpoint gate FAILS at the issue fixture, and the refinement axis localizes the failure to the first-arrival readout, not the solve.
**Instrument:** `crates/katgpt-dec/benches/bench_815_coulomb_redistribution_poc.rs` — `CARGO_TARGET_DIR=/tmp/bench815 cargo bench -p katgpt-dec --bench bench_815_coulomb_redistribution_poc -- --nocapture` (exit 0 only if the issue fixture passes all three T1 gates).
**Box:** M3 Max (16 cores), macOS 26.6.2, ~34 GB/64 GB RAM with sibling agent sessions active (moderate load), release bench profile, single process; no GPU (pure CPU), no competing compute consumer during the run.
**Deps:** zero new — the solve is a local f64 pinned Gaussian elimination, distances are BFS hop counts, flows use the shipped DEC operators (`exterior_derivative_into`, `codifferential`). All arrays fixed-size (MAX_V = 144) — the G4 zero-alloc gate reads 0 allocations at every case.

## The construction (what landed)

The discrete BTM Prop-2 analog, exactly as the issue specified: solve
`Lφ = μ₀ − μ₁` on the zone graph (grounded at vertex 0 — the Laplacian is
singular on the constant mode; the fixture guarantees Σρ = 0 so the projected
system is consistent), take `j = d₀φ`, and route mass by first-arrival: at
each vertex the leaving flow on edge e is `sign(v,e) · j[e]` clamped ≥ 0,
normalized per vertex (the issue's "NPC follows the outgoing edge
proportional to positive flow"), sinks absorb.

Two en-route corrections are part of the record (both measured, not derived):

1. **The conservation gate is POINTWISE, not an L1-near-zero check.** The
   issue's "(a) δ(j) = μ₀ − μ₁ to fp tolerance (reuse
   `belief_mass_divergence`)" conflates the two: this is a SOURCED flow —
   `δ₁(j) = ρ` by construction, so `‖δ₁(j)‖₁ = ‖ρ‖₁ = 2.0` is the CORRECT
   value, not a violation. `belief_mass_divergence` (the Plan-314
   steady-state check) asserts divergence ≈ 0 and is the wrong instrument
   for `μ₀ ≠ μ₁`. The landed gate asserts `max_v |δ₁(j)[v] − ρ[v]| ≤ 1e-3`
   via `codifferential` — measured 8.9e-8 (12 zones) / 1.8e-7 (48, 108).
2. **Flow direction is `-∇φ` and the naive baseline must share the pit
   convention.** The Coulomb solve makes sources Laplacian peaks and sinks
   pits; the naive attract field must be built as `φ_naive = +Σ w_j·dist`
   (sinks = pits too) or the shared downhill readout routes its mass
   nowhere (measured: naive MAE pinned at exactly 0.500 = all trapped,
   before the sign unification).

## Gate results

| Gate | 12 zones (issue fixture) | 48 zones | 108 zones |
|---|---|---|---|
| T1a conservation (`max|δ₁(j)−ρ|` ≤ 1e-3) | **PASS** 8.9e-8 | PASS 1.8e-7 | PASS 1.8e-7 |
| T1b endpoint MAE vs μ₁ (gate ≤ 0.01) | **FAIL** 0.1190 | FAIL 0.0782 | FAIL 0.0366 |
| T1c G4 zero-alloc solve path | **PASS** 0 allocs, 3.1 µs | PASS 0, 22.8 µs | PASS 0, 108 µs |
| T2 naive-sum MAE | 0.2151 | 0.0320 | 0.0811 |
| T2 naive-max MAE | 0.0569 | 0.2845 | 0.3310 |
| T2 ratio naive-best/Coulomb (gate ≥ 10×) | **FAIL** 0.48× | FAIL 0.41× | FAIL 2.21× |

Coulomb endpoints at the issue fixture (targets 0.6/0.4): **[0.4810, 0.5190]**
— the solve puts the heavy sink only 8 points ahead of the light one.

## The finding (honest, and why it is not the paper's 20×)

1. **The solve transfers; the READOUT does not.** Conservation holds to fp
   noise and mass always arrives (trapped = 0 everywhere — no plateaus), so
   `Lφ = ρ` → downhill routing is sound as a *flow*. But the endpoint
   distribution misses the target weights by 0.12 at the issue fixture and
   the miss shrinks monotonically with refinement (0.119 → 0.078 → 0.037 at
   12 → 48 → 108 zones). That is the signature of **discretization error in
   the absorbing-chain first-arrival readout**, not a broken construction:
   the continuum Prop-2 guarantee is carried by continuous characteristic
   lines of `−∇φ`, and the graph analog replaces characteristic merging with
   per-vertex proportional splitting, which does not preserve the hitting
   measure on coarse graphs. Extrapolation says a real zone graph (500+
   zones) would land under 0.01 — but that is extrapolation, not a gate.
2. **The paper's 20× bias result does not transfer to the naive baseline on
   graphs.** The 20× is for the CONTINUOUS EqM-style rescaled field; on the
   graph, the naive distance-field baseline is competitive-to-better at toy
   scale (0.48× at 12 zones) and only degrades relative to Coulomb as the
   graph grows (2.21× at 108 zones, still far under the 10× gate) — and
   which naive FORM wins flips between sizes (max-form at 12, sum-form at
   48), so the baseline itself is unstable across resolutions. The honest
   reading: **on zone graphs, a hand-built distance field is a strong
   baseline, and the Coulomb solve's distributional endpoint guarantee is
   NOT its differentiator at game-relevant scales.**

## Verdict

**Issue 825 T1+T2: FAIL on the issue's own gate (endpoint MAE ≤ 0.01 at the
fixture) — T3's negative-result clause fires.** Per the issue: "If T1 or T2
fails, this issue closes as a negative-result artifact (the Issue 573
precedent — a falsified transfer is a valid outcome; keep the test as the
reproducible artifact)." The bench IS that artifact.

What a future re-open would need (recorded, not speculated): (a) a
characteristic-preserving readout (per-particle trajectory integration with
no proportional splitting at merge vertices) to isolate whether the hitting
measure survives when merging is exact — the continuum guarantee's actual
discrete analog; (b) a zone-graph resolution where the ≤ 0.01 gate actually
passes, plus the naive baseline re-measured there (its instability across
sizes is itself unexplained); (c) a consumer story that survives (a) — the
redistribution director wants *arrival proportions*, and if only a
trajectory-integrating readout delivers them, the proportional-routing
consumer contract (NPCs decide locally from the edge flow) is the thing that
cannot ship.

## Cost model

Solve is O(n³) Gaussian on the free vertices (the PoC's f64 pinned
elimination): 3.1 µs @ 12 zones, 22.8 µs @ 48, 108 µs @ 108 — per
redistribution EVENT, not per tick (cacheable, the issue's own caveat). A
production `coulomb_flow` would swap the elimination for the shipped
iterative machinery or a Cholesky on the SPD grounded Laplacian; the G4
zero-alloc shape is already proven (0 allocations at every size).
