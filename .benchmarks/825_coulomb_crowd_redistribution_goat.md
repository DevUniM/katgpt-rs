# Issue 825 — Coulomb crowd redistribution via a DEC Poisson solve: GOAT results

**Date:** 2026-09-18 (T1+T2), re-measured against the shipped crate API 2026-09-18 (T3)
**Primitive:** `CoulombFlowField` + `CrowdRouter` in `katgpt-dec`
(`src/coulomb.rs`), over the public `poisson_solve` / `poisson_solve_into` in
`src/hodge.rs`
**Feature:** `coulomb_flow` — **OPT-IN** in both `katgpt-dec` (where the
primitive lives) and `katgpt-core` (`coulomb_flow = ["dec_operators",
"katgpt-dec/coulomb_flow"]`, the `pca_global` / `se2_equivariant_lift`
passthrough shape). Not promoted to default-on: all four gates pass, but the
consumer wiring is riir-ai's per the boundary contract, so there is no
default-path consumer in this repo.
**Bench:** `cargo bench -p katgpt-core --features coulomb_flow --bench bench_825_coulomb_crowd_redistribution_goat`

⛔ **T1/T2 measured a PoC that carried its own CG, refinement loop and routing
tables inside the bench file.** T3 promoted all three into `katgpt-dec` and
re-pointed the bench, so the numbers below now describe the SHIPPED code. A
GOAT gate that measures a private transcription of the primitive certifies the
transcription — the sibling-arm defect AGENTS.md records for
`dash_attn/channel_aware.rs`, one instrument over.
**Hardware:** Windows 11 / i7-13700K (x86_64), release profile
**Box state at measurement:** T1/T2 ~22 GB free physical, commit 30/63 GB, no
other heavy job. ⚠ The T3 re-measurement was taken with the x86_64 execution
matrix ALSO running on this box (~22 GB free, `cargo bench -j 6` against the
matrix's own tree) — recorded per AGENTS.md §Feature Flag Discipline, because a
latency number without its box state is not a measurement. **That is disclosed
rather than re-run because no gate here is load-sensitive:** G1 and G4 are exact
(a residual and an allocation count), and G2/G3 are MAE ratios over fixed seeds.
The only timing is the 11.1 µs solve on a 12-vertex graph, which is reported and
gated by nothing — and which is 2× the PoC's 5.3 µs precisely because of the
concurrent load, so do not read it as a regression.

## Verdict: **ALL FOUR GATES PASS**

Re-measured 2026-09-18 against the shipped `coulomb_flow` API (T3). The T1/T2
column is kept beside it because two of the four MOVED, and the reasons are the
finding rather than noise.

| Gate | Metric | T1/T2 (PoC) | T3 (shipped) | Threshold | Verdict |
|---|---|---|---|---|---|
| G1 conservation | `max\|δ(j) − (μ₁−μ₀)\|` | 5.96e-8 | **5.96e-8** | ≤ 1e-6 | **PASS ✅** |
| G1 conservation | `\|Σᵥ δ(j)[v]\|` | 0.0 | **7.45e-8** | ≤ 1e-6 | **PASS ✅** |
| G1 conservation | `belief_mass_divergence(j)` vs mass moved | 2.000000 | **2.000000 vs 2.000000** | ≤ 1e-4 | **PASS ✅** |
| G1 diagnostic | `max\|graph_laplacian(φ) − δ(dφ)\|` | 0.0 | **0.0** | report only | — |
| G2 endpoint | exact `expected_arrivals` MAE (no RNG) | — | **1.24e-9** | ≤ 1e-5 | **PASS ✅** |
| G2 endpoint | MAE vs `μ₁` at N=1e6 | 2.9e-5 | **8.5e-5** | ≤ 0.01 | **PASS ✅** |
| G2 endpoint | MAE decay 1e3 → 1e6 | 40× | **21.7×** | ≥ 4× | **PASS ✅** |
| G2 endpoint | walkers hitting the step cap | 0 | **0** | = 0 | **PASS ✅** |
| G3 bias analog | naive MAE / Coulomb MAE | 3809× | **1312×** | ≥ 10× | **PASS ✅** |
| G4 alloc | allocations / 100 refined solves | 0 | **0** | = 0 | **PASS ✅** |

⛔ **G4 was 300 on the first T3 run, and that is the finding that justifies
re-pointing the bench at all.** The PoC carried its own CG and its own scratch
struct, and was alloc-free. `katgpt-dec`'s `cg_solve_scalar` built its five
matvec cochains per SOLVE — alloc-free across CG *iterations*, which is what its
comment claimed and all it had ever been measured for, and **3 allocations per
solve** for any caller that solves repeatedly. `poisson_solve_into`'s refinement
loop is exactly such a caller, and so is a director redistributing a crowd every
event. The gate had been certifying a transcription. Fixed by hoisting all five
into `CgScratch` with an in-place `fit_cochain` re-shape (`Vec::resize` does not
shrink capacity, so an alternating-shape caller allocates only on growth);
`hodge_decompose` gets the same win for free, and its 265 katgpt-dec lib tests
are unchanged.

⚠ **G2's two moved numbers are a DELIBERATE design change, not drift.**
`CrowdRouter::step` spends **one** uniform per NPC per step — the absorb
decision first, then the unused tail remapped onto the outgoing-flow CDF as
`(u − p)/(1 − p)`, which is uniform on `[0,1)` exactly when the absorb branch
was not taken. The PoC drew two. Two draws per NPC per tick is the dominant cost
at crowd scale, so the shipped path takes one; the stream differs, so the
sampled MAE at any fixed N differs. The DECAY (21.7× against a 4× bar, ideal
≈31.6×) and the new no-RNG `expected_arrivals` row at **1.24e-9** are what
establish the construction is unbiased — a single MAE never could.

⚠ **G3 fell 3809× → 1312× and nothing regressed.** The ratio's denominator is
the Coulomb MAE, which is sampling noise at a particular seed; the numerator
(naive MAE **0.111111**) is unchanged to six figures. Read the ratio as a
magnitude against a 10× bar, never as a measurement with three significant
figures. Both arms are now walked by the SAME `CrowdRouter::step` and differ in
exactly one vector — the absorption policy, supplied through
`from_flow_with_absorption` — so the comparison is single-variable in a way the
two-walker PoC could not be.

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
the decay (measured **21.7×**, bar 4×, the ideal being ≈31.6× for 1000× the
walkers), and cross-checks it against `expected_arrivals`, which computes the
expectation with **no RNG at all** and lands at 1.24e-9. Walker start positions are apportioned deterministically by largest
remainder, so the only sampling noise in the number is the routing itself.

`MAE·√N` wanders between 0.03 and 0.12 rather than sitting flat, which is
expected at this scale: with 12 vertices and 3 non-zero targets the constant is
itself an average over very few terms.

## G3 — the 20× bias analog, measured at 1312×, and it is TWO failures

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

The paper measured 20× in ℝ² with 5 atoms. 1312× here is not a better result
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

**`coulomb_flow`, OPT-IN, landed 2026-09-18 (T3).** The three preconditions
this section listed are met:

- the **public Poisson solve** is `poisson_solve` / `poisson_solve_into` +
  `PoissonScratch` / `PoissonStats` in `katgpt-dec::hodge` — a thin, ungated
  wrapper over the existing private `cg_solve_scalar`, plus the iterative
  refinement the PoC measured as worth ~100× on the true residual. It is
  deliberately NOT behind `coulomb_flow`: gating a linear-algebra solve behind
  a game primitive is the wrong axis, and it changes no default behaviour.
- the **bridge** is `DecFlowField::from_exact_flow`, which is the honest form of
  it — a gradient field's Hodge decomposition is `exact = itself` in closed
  form, so `DecFlowField::compute` would run a full `hodge_decompose` to
  re-derive a known answer. It returns `Option` and yields `None` off a 2D
  grid, because `to_flow_vectors` indexes by the `grid_2d` edge layout and
  `compute`'s count-based dimension inference cannot tell a general zone graph
  apart from a grid — it would return well-formed WRONG vectors.
- **not promoted to default-on.** All four gates pass and the gain is modelless,
  but there is no default-path consumer in this repo, and per the boundary
  contract the riir-ai swarm/zone wiring is riir-ai's to file.

⛔ **Scale is still open and is the one claim this record does NOT make.** 12
vertices says nothing about a real zone graph. G4 is alloc-free and the solve is
11.1 µs here; neither number transfers, and CG's iteration count on a large
sparse zone graph is unmeasured. A consumer at production scale needs its own
G2/G4 row.

## References

- Issue 825 (parent), Research 468 §5, arXiv:2608.01692 v3 Prop 2
- Plan 251 (`hodge_laplacian`, `exterior_derivative`, `DecFlowField`), Plan 314
  (`belief_mass_divergence`)
- `crates/katgpt-core/benches/bench_825_coulomb_crowd_redistribution_goat.rs`
