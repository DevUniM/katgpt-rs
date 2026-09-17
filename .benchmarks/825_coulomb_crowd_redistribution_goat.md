# Issue 825 T1+T2 — Coulomb crowd redistribution via a DEC Poisson solve: GOAT results

**Date:** 2026-09-18
**Primitive:** PoC only — no crate API added (see §Promotion)
**Feature:** `dec_operators` (default-on inside `katgpt-core`, reached through
its default `tropical_algebra`; **opt-in at the root package**, where
`dec_operators = ["katgpt-core/dec_operators"]` is not in the 135-flag default
set). The bench consumes the shipped DEC substrate and adds nothing to it, so
this row describes where the substrate already sits, not a promotion.
**Bench:** `cargo bench -p katgpt-core --features dec_operators --bench bench_825_coulomb_crowd_redistribution_goat`
**Hardware:** Windows 11 / i7-13700K (x86_64), release profile
**Box state at measurement:** ~22 GB free physical, commit 30/63 GB, no other
heavy job resident — recorded per AGENTS.md §Feature Flag Discipline, because a
latency number without its box state is not a measurement. The only timing here
is a 5.3 µs solve on a 12-vertex graph, which is not a load-sensitive figure;
the three gates that matter are correctness, not latency.

## Verdict: **ALL FOUR GATES PASS**

| Gate | Metric | Value | Threshold | Verdict |
|---|---|---|---|---|
| G1 conservation | `max\|δ(j) − (μ₁−μ₀)\|` | **5.96e-8** | ≤ 1e-6 | **PASS ✅** |
| G1 conservation | `\|Σᵥ δ(j)[v]\|` | **0.0** | ≤ 1e-6 | **PASS ✅** |
| G1 conservation | `belief_mass_divergence(j)` vs mass moved | **2.000000 vs 2.000000** | ≤ 1e-4 | **PASS ✅** |
| G2 endpoint | MAE vs `μ₁` at N=1e6 | **2.9e-5** | ≤ 0.01 | **PASS ✅** |
| G2 endpoint | MAE decay 1e3 → 1e6 | **40×** | ≥ 4× | **PASS ✅** |
| G2 endpoint | walkers hitting the step cap | **0** | = 0 | **PASS ✅** |
| G3 bias analog | naive MAE / Coulomb MAE | **3809×** | ≥ 10× | **PASS ✅** |
| G4 alloc | allocations / 100 refined solves | **0** | = 0 | **PASS ✅** |

## The setup

A 4×3 zone graph (12 vertices, 17 edges) built with `CellComplex::from_edges`.
`μ₀` is the current crowd, uniform over the 9 non-sink zones. `μ₁` is the
authored target: three sinks at **deliberately unequal** weights
`{0: 0.5, 3: 0.3, 11: 0.2}` — the whole bias question is whether a field can
carry those weights, and equal weights would answer it by construction.

Solve `L(φ) = μ₁ − μ₀`, take `j = d(φ)`, route walkers by positive outflow.

### The sign convention is part of the result

The paper writes `Δφ = μ₀ − μ₁` for the continuum Laplacian, which is negative
semidefinite. This repo's `graph_laplacian` is `δd = D − A`, its **positive**
semidefinite negation. So the solve is `L(φ) = μ₁ − μ₀`, `φ` is the paper's
potential negated, mass flows toward *increasing* `φ`, and sinks are potential
maxima. Getting this backwards produces a field that pushes every NPC away from
its target **while every conservation assert still passes** — so it is written
next to the solve rather than inferred.

## What transferred, and it is stronger than the issue expected

Issue 825 carried this caveat:

> **Continuum Coulomb field is NOT directly the discrete solve.** Prop 2 lives
> in `ℝ^d` with the fundamental solution; the DEC analog is the *graph
> Laplacian* Poisson solve — transport property transfer is unproven and is
> exactly what the PoC tests.

**It transfers, and by a different argument than the paper's.** Prop 2 needs a
finite-hitting-time result for the continuum flow. On a graph with atomic
targets none of that is required:

1. `δ(j) = δ(d(φ)) = L(φ) = μ₁ − μ₀` is an **identity**, not an approximation.
   Mass balance at every vertex is `inflow + μ₀ = outflow + μ₁`.
2. A gradient flow is **acyclic** — `φ` strictly increases along every
   positive-flow edge, so a positive-flow cycle would need `φ(v) > φ(v)`.
   Routing therefore terminates, with no hitting-time argument.
3. Routing proportional to positive outflow, absorbing at `v` with probability
   `μ₁(v) / (inflow(v) + μ₀(v))`, is an exact flow decomposition: the expected
   endpoint distribution **is** `μ₁`.

So the endpoint match is not a lucky numerical outcome; it is conservation read
one layer down. G2's job is to confirm the implementation realises it, which is
why the gate is on the **decay** and not on one MAE — see below.

## G2 is a sampling measurement and the gate had to be built for that

| N | MAE vs `μ₁` | MAE·√N |
|---:|---:|---:|
| 1,000 | 0.001167 | 0.0369 |
| 10,000 | 0.000567 | 0.0567 |
| 100,000 | 0.000365 | 0.1154 |
| 1,000,000 | 0.000029 | 0.0292 |

Because the expected endpoint distribution is exactly `μ₁`, the residual is
Monte-Carlo noise and falls like `1/√N`. **An assert at one N cannot tell
"exact plus noise" from "biased by less than the tolerance"** — that is this
repo's own fixture-cannot-express-the-mechanism failure — so the gate asserts
the decay (measured 40×, bar 4×, the ideal being ≈31.6× for 1000× the
walkers). Walker start positions are apportioned deterministically by largest
remainder, so the only sampling noise in the number is the routing itself.

`MAE·√N` wanders between 0.03 and 0.12 rather than sitting flat, which is
expected at this scale: with 12 vertices and 3 non-zero targets the constant is
itself an average over very few terms.

## G3 — the 20× bias analog, measured at 3809×, and it is TWO failures

Baseline: `φ_naive(v) = −Σⱼ wⱼ · dist(v, sinkⱼ)`, hand-set weights, the shipped
`DecFlowField` consumption shape (a caller-supplied goal potential, no density
input). Same routing kernel; the only difference is the stopping rule, because
a hand-built attract field carries no target weights to derive one from and can
only stop on arrival at a sink. **That asymmetry is the finding, not a handicap
in the baseline**: the consistent construction knows where the crowd is
supposed to end up, and the attract field structurally cannot.

Pooling the result into one MAE would let a reader credit the whole ratio to
weight bias. It is two separate failures and the bench prints them apart:

| | Coulomb solve | naive attract field |
|---|---|---|
| reached a sink at all | 100% | **33.3%** |
| sink 0 (target 0.500) | 0.500 | 0.2222 (conditional 0.667) |
| sink 3 (target 0.300) | 0.300 | 0.1111 (conditional 0.333) |
| sink 11 (target 0.200) | 0.200 | **0.0000** (conditional 0.000) |
| MAE vs `μ₁` | 0.000029 | 0.111111 |

1. **Two-thirds of the crowd never arrives.** A sum of weighted distances has
   local minima that are not sinks, and a walker that finds one stops in open
   country. The Coulomb flow cannot do this: every non-sink vertex has strictly
   positive outflow by mass balance.
2. **The weights are wrong even conditioned on arrival** — `(0.667, 0.333,
   0.000)` against `(0.5, 0.3, 0.2)`. Sink 11 receives **nothing**: it is
   geometrically shadowed, and a field built from distances answers geometry,
   not authored proportions.

The paper measured 20× in ℝ² with 5 atoms. 3809× here is not a better result
than the paper's — it is a different and harsher graph, where the naive field
strands most of the population. Read the ratio with the split above, never
alone.

## ⛔ Two defects this bench found in its own instrument, in the order they were found

Both are recorded because each produced a plausible, well-formed, wrong number.

### 1. A CG breakdown guard on an ABSOLUTE floor discards every refinement step

The first run reported `max|δ(j) − (μ₁−μ₀)| = 1.372e-5` against a recursive CG
residual of `1e-7`. Iterative refinement was added — and the residual came back
**bit-identical**, through three rounds.

The cause was `if pap.abs() < f32::EPSILON { return }` in the CG loop. `L` is
SPD on the mean-zero subspace, so `p'Lp > 0` for every non-zero `p` and the only
real breakdown is `pap ≤ 0`. Refinement solves for a *correction* whose residual
is ~1e-5, making `pap ~ 1e-10` — legitimately tiny, and far under `f32::EPSILON`
(1.19e-7). Every refinement CG returned at that guard **before taking a single
step**. A solver that silently does nothing is indistinguishable, from its
return value, from a solver that has converged.

Fixed (`pap.is_nan() || pap <= 0.0`), the residual is **5.96e-8** and refinement
reports **0 rounds needed** — CG had been able to reach the floor all along.

### 2. A confident wrong explanation, written into a comment, refuted by its own diagnostic

Before finding the guard, the residual's stability across refinement rounds was
diagnosed as the crate's *two* forms of the rank-0 Laplacian disagreeing in f32:
the fused `graph_laplacian` against the composed `δ(d(·))`. The matvec was
switched to the composed form and a diagnostic added to print the gap.

**The diagnostic says the gap is exactly 0.** The hypothesis was wrong, and it
had already been written into a doc comment as a measured fact. Both the comment
and the G1 tolerance comment are corrected in place, and the diagnostic stays —
a claim of that shape should be re-measured on every run rather than remembered
from one.

The composed matvec is **kept**, on a principle that survives the refutation:
solve with the operator you transport with. The transport field is `j = d(φ)`
and the conservation law is read through `δ(j)`, so the operator the solve
inverts should be the one the gate measures. A fused second implementation needs
no reason to agree at the last bit — it happens to, here, and that is a
measurement rather than a guarantee.

## Promotion

**None requested, and T3's precondition is met but its scope is not this
bench's to settle.** Issue 825 T3 says that if T1+T2 pass, plan a `coulomb_flow`
feature exposing a `CoulombFlowField` constructor plus a consumer-wiring note
for riir-ai swarm/zone systems. They pass. What this record establishes is the
*mechanism*; what a feature needs in addition:

- a **public Poisson solve** in `katgpt-dec` — `cg_solve` is private there, and
  the PoC carries its own CG for exactly that reason. That is a crate API
  decision, not a bench outcome.
- scale: 12 vertices says nothing about a real zone graph. G4 is alloc-free and
  the solve is 5.3 µs here; neither number transfers.
- the `DecFlowField` / `to_flow_vectors` bridge, which the PoC does not touch.

Per the boundary contract the riir-ai consumer wiring is riir-ai's to file.

## References

- Issue 825 (parent), Research 468 §5, arXiv:2608.01692 v3 Prop 2
- Plan 251 (`hodge_laplacian`, `exterior_derivative`, `DecFlowField`), Plan 314
  (`belief_mass_divergence`)
- `crates/katgpt-core/benches/bench_825_coulomb_crowd_redistribution_goat.rs`
