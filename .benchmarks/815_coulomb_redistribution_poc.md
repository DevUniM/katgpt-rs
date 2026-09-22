# Bench 815 — Coulomb crowd-redistribution PoC (Issue 825 T1+T2)

**Date:** 2026-09-18
**Issue:** Issue 825 — T1 (DEC Coulomb PoC on a toy zone graph) + T2 (the 20×-bias analog gate); issue file removed per the noise-reduction rule, this doc + git history are the record.
**Status:** ⛔ **RETRACTED AND REPAIRED 2026-09-18** — the original run's FAIL was two defects in this bench's own walker, not a property of the construction. See § Retraction. Every gate passes.
**Instrument:** `crates/katgpt-dec/benches/bench_815_coulomb_redistribution_poc.rs` — `cargo bench -p katgpt-dec --features coulomb_flow --bench bench_815_coulomb_redistribution_poc` (exit 0 only if the issue fixture passes all three T1 gates). Gated `coulomb_flow` since the repair: the stopping rule now comes from the shipped `katgpt_dec::CrowdRouter`.
**Box (original run):** M3 Max (16 cores), macOS 26.6.2, ~34 GB/64 GB RAM with sibling agent sessions active (moderate load), release bench profile, single process; no GPU (pure CPU), no competing compute consumer during the run.
**Box (repair run):** shikuwa — i7-13700K (16 cores), Windows 11, 31.8 GB RAM at ~16 GB free, release bench profile, single process, one sibling agent session active on an unrelated repo. The two boxes are named separately on purpose: the latency column below is NOT comparable across them, and the correctness columns are exact values that are.
**Deps:** zero new — the solve is a local f64 pinned Gaussian elimination, distances are BFS hop counts, flows use the shipped DEC operators (`exterior_derivative_into`, `codifferential`). All arrays fixed-size (MAX_V = 144) — the G4 zero-alloc gate reads 0 allocations at every case.

## The construction (what landed)

The discrete BTM Prop-2 analog, exactly as the issue specified: solve
`Lφ = μ₀ − μ₁` on the zone graph (grounded at vertex 0 — the Laplacian is
singular on the constant mode; the fixture guarantees Σρ = 0 so the projected
system is consistent), take `j = d₀φ`, and route mass by first-arrival: at
each vertex the leaving flow on edge e is `sign(v,e) · j[e]` clamped ≥ 0,
normalized per vertex (the issue's "NPC follows the outgoing edge
proportional to positive flow"), stopping at `v` with probability
`μ₁(v) / (inflow(v) + μ₀(v))` — the flow decomposition's own absorption rule,
taken from the shipped `katgpt_dec::CrowdRouter::consistent_absorption`. ⛔ The
original landed `stop[sink] = 1.0` instead; see § Retraction.

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

## Gate results (repaired instrument, shikuwa, 2026-09-18)

| Gate | 12 zones (issue fixture) | 48 zones | 108 zones |
|---|---|---|---|
| T1a conservation (`max|δ₁(j)−ρ|` ≤ 1e-3) | **PASS** 8.9e-8 | PASS 1.8e-7 | PASS 1.8e-7 |
| T1b endpoint MAE vs μ₁ (gate ≤ 0.01) | **PASS** 0.000000 | PASS 0.000000 | PASS 0.000000 |
| T1b trapped mass | 0.0 | −1.2e-16 | −1.9e-16 |
| T1c G4 zero-alloc solve path | **PASS** 0 allocs, 2.6 µs | PASS 0, 10.0 µs | PASS 0, 49.1 µs |
| T2 naive-sum MAE | 0.2681 | 0.1794 | 0.1289 |
| T2 naive-max MAE | 0.0950 | 0.0595 | 0.0861 |
| T2 ratio naive-best/Coulomb (gate ≥ 10×) | **PASS** ≥ 95 000× | PASS ≥ 59 473× | PASS ≥ 86 142× |

Coulomb endpoints at the issue fixture (targets 0.6/0.4): **[0.600000,
0.400000]**, at every refinement.

⚠ **The T2 ratio is a LOWER BOUND, not a measurement.** This readout is exact,
so its residual is the f32 cochain's noise floor — the first repaired run
printed `1.5e7×`, which is a number about `f32`, not about the method. The
instrument divides by an explicit `FP_FLOOR = 1e-6` (the T1a residual is
~1.8e-7 at 108 zones, so nothing below that is resolvable here) and prints
`≥`. Read it as *"clears the 10× bar by orders of magnitude"* and nothing
finer. The per-NPC SAMPLED figure — where a real ratio can be measured,
because sampling error is real error — is Bench 825's 1312×.

## Retraction — the original run's FAIL was this bench's walker, twice over

⛔ **The first version of this document concluded "the solve transfers, the
READOUT does not" and closed Issue 825 as a negative result. That conclusion
was wrong, and so was its diagnosis.** Both defects were in `absorb()`; the
solve was correct all along and its own gate (T1a) said so.

**Defect 1 — a sink absorbed 100%.** The walker skipped sinks (`if packet[v]
== 0.0 || is_sink[v] { continue; }`) and banked their whole packet at the end.
The flow decomposition says a vertex stops a passing particle with
probability `μ₁(v) / (inflow(v) + μ₀(v))`, which equals 1 only when the vertex
has no outflow. Measured on this file's own `(4,3,5)` fixture via the shipped
`CrowdRouter::consistent_absorption`: sink `n−2` carries `out_flow = 0.209`
and a consistent absorption of **0.657**. Sinks `n−1` and `n−2` are adjacent
on a grid, so mass headed for the heavy sink passes through the light one and
was stranded there — which is exactly the shape of the miss, the light sink
over-collecting by the amount the heavy one lost (`[0.4810, 0.5190]` against
`[0.6, 0.4]`, one excess = one deficit = 0.119).

**Defect 2 — the proportional split was order-dependent.** Inside the split
loop the share was computed as `packet[v] * (p / total)` while `packet[v]` was
being decremented by that same loop, so the second out-edge was sized from the
already-reduced remainder. Mass is still conserved (the residue re-forwards on
the next pass and the geometric series sums to 1), but the *proportions* are
not: with two out-edges at `p₁ + p₂ = 1` the first receives
`p₁ / (p₁ + p₂²)` rather than `p₁`. It is invisible in a conservation check
and invisible at a vertex of degree 1, which is why T1a passed throughout.
This is the defect that moved the NAIVE arm's numbers too (naive-sum MAE
0.2151 → 0.2681 at 12 zones) — both arms shared the walker, so the retraction
covers the baseline as well.

**What the refinement axis was actually showing.** `0.119 → 0.078 → 0.037`
was read as *"converging, therefore discretization error"*. It was the two
adjacent sinks becoming a smaller share of a growing graph's transport. The
trend was real and the inference from it was not — a monotone sequence is
consistent with a great many mechanisms, and the one it was attributed to
(proportional splitting failing to carry the continuum hitting measure)
happens to be the one the corrected readout proves is FINE: the split is
exact, and the endpoint distribution is `μ₁` identically at every resolution.

**How it was caught.** Not by re-reading the bench. Two sessions implemented
Issue 825 concurrently and landed opposite verdicts; the other one shipped the
`coulomb_flow` primitive with a `CrowdRouter` whose absorption rule is derived
in its module docs. Running THIS bench's three fixtures through THAT readout
returned MAE `0.0 / 1.2e-7 / 3.0e-8` where this bench read `0.119 / 0.078 /
0.037`. A disagreement between two implementations is a cheaper oracle than
either implementation's own self-consistency, and neither run alone could have
produced it — this bench's gates were all internally satisfied at the moment it
declared a negative result.

**What changed, and what deliberately did not.** The stopping rule is now
`CrowdRouter::consistent_absorption`, imported rather than copied, so the two
benches on this primitive cannot disagree about it again. The f64 Gaussian
solver and the deterministic mass-packet walker stay local: their independence
from Bench 825's CG solve and sampled walk is the whole reason this bench was
repaired instead of deleted, and it is what makes the agreement meaningful.
The naive arm keeps `stop[sink] = 1.0` — a hand-built attract field carries no
target weights, so first-arrival is the only rule it can offer, and handing it
the Coulomb absorption vector would hand it the answer.

### Superseded table (the original M3 run, kept as the record of the retracted claim)

| Gate | 12 zones | 48 zones | 108 zones |
|---|---|---|---|
| T1b endpoint MAE vs μ₁ | FAIL 0.1190 | FAIL 0.0782 | FAIL 0.0366 |
| T2 naive-sum MAE | 0.2151 | 0.0320 | 0.0811 |
| T2 naive-max MAE | 0.0569 | 0.2845 | 0.3310 |
| T2 ratio naive-best/Coulomb | FAIL 0.48× | FAIL 0.41× | FAIL 2.21× |

Coulomb endpoints at the issue fixture, as originally measured: **[0.4810,
0.5190]**.

## The finding

1. **The construction transfers exactly, and the endpoint guarantee is an
   identity rather than an approximation.** `δ(j) = ρ` is what the solve
   returns (T1a, 8.9e-8), a gradient flow is acyclic so routing terminates
   (trapped ≈ 0 at every size), and routing proportional to positive outflow
   with absorption `μ₁(v) / (inflow(v) + μ₀(v))` is an exact flow
   decomposition whose arrival distribution IS `μ₁`. The measured MAE is 0 to
   f32 resolution at 12, 48 and 108 zones — no refinement trend, because
   there is no discretization term to refine away. The only approximation a
   consumer meets is per-NPC SAMPLING, which is Bench 825's G2 axis
   (`1/√N`, measured 21.7× decay over 1e3 → 1e6 walkers).
2. **The paper's Prop-2 hypotheses are not needed on a graph.** Prop 2 argues
   finite hitting time in ℝᵈ; with atomic targets on a finite graph none of
   that machinery is required — `δ(dφ) = Δφ` is an identity and the
   decomposition above is elementary. The transfer holds by a shorter
   argument than the paper's, which is a stronger result than the paper's
   own, not a weaker one.
3. **The naive baseline is decisively worse, and how it fails is the
   interesting part.** Naive-best MAE is 0.095 / 0.059 / 0.086 across the
   three sizes against a Coulomb residual at fp resolution. ⚠ Do not quote
   the printed ratio as the measured bias factor — see the ⚠ under the gate
   table. The mechanism is the one Bench 825 reports at its own fixture: a
   hand-built distance field carries no target weights, so it can only offer
   stop-on-first-arrival, and it splits crowds by geometry instead of by the
   authored proportions.
4. ⚠ **What is still NOT measured here:** scale beyond 108 zones, a
   non-grid (irregular) zone graph, and the `to_flow_vectors` bridge. The
   O(n³) pinned elimination in this bench is a PoC solver, not the shipped
   path — `coulomb_flow` uses the CG solve in `katgpt-dec::coulomb`.

## Verdict

**Issue 825 T1+T2: PASS** on the issue's own gate (endpoint MAE ≤ 0.01 at the
fixture, conservation, zero-alloc) plus the T2 bias bar, at all three
resolutions. T3's negative-result clause does NOT fire; the `coulomb_flow`
feature ships (opt-in) and Bench 825 is its GOAT gate.

⛔ This verdict replaces a FAIL. The earlier one was an instrument defect and
the full diagnosis is in § Retraction — read that before citing either number.

## Cost model

Solve is O(n³) Gaussian on the free vertices (the PoC's f64 pinned
elimination): 3.1 µs @ 12 zones, 22.8 µs @ 48, 108 µs @ 108 on the M3;
2.6 / 10.0 / 49.1 µs on shikuwa. ⚠ Those two rows are different boxes under
different load and are not a speedup — cite one or the other with its box,
never the pair. Either way it is per redistribution EVENT, not per tick
(cacheable, the issue's own caveat).

`coulomb_flow` shipped and does NOT use this elimination: `katgpt-dec::coulomb`
solves with the crate's CG path, which is what Bench 825 gates. This PoC
solver stays here precisely because it is independent of it — two solvers and
two readouts agreeing is what the § Retraction section spends itself on. The
G4 zero-alloc shape holds in both (0 allocations at every size).
