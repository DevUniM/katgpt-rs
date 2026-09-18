# Issue 825: Training-free Coulomb crowd redistribution via DEC Poisson solve (Research 468 v3 delta, arXiv:2608.01692 Prop 2)

**Status:** T1+T2 MEASURED 2026-09-18 ([Bench 815](../.benchmarks/815_coulomb_redistribution_poc.md)) — endpoint gate **FAIL** at the issue fixture (MAE 0.119 vs ≤ 0.01; targets 0.6/0.4, landed 0.481/0.519), T3's negative-result clause FIRES — the bench + this file are the reproducible artifact, then removal per noise-reduction. The miss is the first-arrival READOUT, not the solve: conservation PASS (8.9e-8), zero trapped mass, zero-alloc PASS, and the miss shrinks monotonically with refinement (0.119 → 0.078 → 0.037 at 12 → 48 → 108 zones = discretization error in the absorbing-chain proportional split). The paper's 20× bias does NOT transfer to graphs — the naive distance-field baseline is 0.48×–2.21× (better or comparable), and which naive form wins flips across sizes. Re-open conditions recorded in Bench 815 §The finding: a characteristic-preserving (no-merge-splitting) readout, a zone resolution where the gate passes, and a consumer story that survives both.

**Source:** [Research 468](../.research/468_Beckmann_Transport_Divergence_Constraint_CCE_MFG_Dynamics.md)
§5 modelless row "Transport-field `b` construction — solve `δ(j) = μ₀ − ρ` for `j`
(a Poisson solve on the cochain)". That row was noted but never filed; the CCE
PoC triage (Issues 573/574/575) adjudicated the *constraint* use of the Beckmann
equation (FAIL → transition kernel PASS → Plan 569) and did not consume the
*construction* use. Paper v3 (2026-08-13, after the 2026-08-06 distillation)
strengthens exactly this row — **Proposition 2**: with `ν ≡ 1` and the canonical
Coulomb field

```
b(x) = ∇φ,   Δφ = μ₀ − μ₁,   b(x) = (1/ω_d) ∫ (x−y)/|x−y|^d (μ₀ − μ₁)(dy)
```

the first-hitting map of the autonomous flow `Ẋ = b(X)` transports `μ₀ → μ₁`
exactly, finite hitting time a.e., **zero training** (mini-batch estimation of
the target charge term suffices). Targets must be singular — atomic targets
(`k = 0`, `μ₁ = Σ_j p_j δ_{x_j}`, `d ≥ 2`) qualify; the paper explicitly flags
discrete generation as the natural fit. **A zone graph is exactly the atomic
case**: zones = vertices, current NPC density = `μ₀` (rank-0 cochain), desired
density = `μ₁` (weighted atoms on vertices).

## Why

The shipped cousins do NOT cover this — signal-diff (§3.6, one read each):

| Cousin | Consumes | Builds potential from density? | Endpoint guarantee? |
|---|---|---|---|
| `DecFlowField::compute` (Plan 251 T20, katgpt-dec `flow.rs`) | hand-built goal potential (distance field / Q-field) | **No** — potential is caller-supplied | **No** |
| `FlowFieldCache` postmax (katgpt-core `src/flow/cache.rs`) | LeoHead Q-values ("follow the gradient toward the strongest attractor") | **No** | **No** |

Neither constructs the potential FROM a source→sink density difference, and
neither asserts where the population *ends up*. BTM's Coulomb construction does
both: `Δφ = μ₀ − μ₁` is a Poisson solve on the zone cochain (`hodge_laplacian`
ships, Plan 251), the resulting gradient flow is mass-conserving **by
construction** (`δdφ = Δφ` exact — the Plan 314 `belief_mass_divergence`
steady-state check generalized to `μ₀ ≠ μ₁`), and first-arrival endpoints carry
provably-conserved mass with correct target weights.

**Game reframe (step 4):** crowd redistribution — spawn rebalancing after a
zone depletes, day/night migration, event-driven herding. Per-NPC behavior:
follow the zone edge flow out of the current zone; arrivals land on target
zones in the authored proportions. Selling point sentence: "our NPC crowds
redistribute across the world via closed-form mass-conserving flows — no
training, provable conservation, exact arrival at the target population
distribution." Naive attract-fields get mode weights wrong — the paper measures
**20×** endpoint-weight bias for the EqM-style rescaled field vs 0.005 MAE for
the consistent construction (2D, 5 atoms); that bias experiment is the direct
analog of the GOAT gate axis here.

**Healer reframe (priority #2, honest): no consumer.** The healer's surfaces
are discrete spans/corpora/trajectories; the transport-map axis for discrete
sequences is the DISCRETE sibling (Research 563 → Issue 811 → `flashar_anchor`,
Bench 600). The continuous Coulomb construction has no healer consumer — this
issue is game-surface only (priority #1 on the fusion ladder).

## Prior art (pinned before filing, 2026-09-17)

Claim pinned: *"training-free Coulomb transport flow (Poisson solve on the zone
graph from source−sink density) for MMORPG crowd redistribution with
exact-mass-conserving first-arrival endpoints, consuming current-vs-target
population density — distinguished from the shipped `DecFlowField`
(consumes hand-built goal potential, no density input, no endpoint guarantee)
by the solved potential + distributional endpoint guarantee."*

Search: OT-based crowd redistribution/evacuation EXISTS as an academic class —
"Macro Bi-level Optimal Transport model" for large-scale crowd evacuation (ACM
2023); OT as density-map matching loss (DM-Count, NeurIPS 2020). **Q1 weak at
the class level** — the mechanism class is published; the fusion (BTM Prop 2 +
DEC substrate + zone-graph atomic targets + per-NPC flow consumption via the
shipped `FlowField` bridge) is the stack-specific claim, unproven until the
PoC. Not Super-GOAT posture; GOAT-at-best pending PoC.

## Constraints / caveats carried from the paper

- **Codimension ≥ 2 or atomic targets only.** Codim-1 counterexamples exist
  (current passes *through* the target instead of stopping). Zone-graph
  vertices = atoms = safe. Continuous NPC space with targets on a 1D curve
  would be the broken case — do not build that variant.
- **Continuum Coulomb field is NOT directly the discrete solve.** Prop 2 lives
  in `ℝ^d` with the fundamental solution; the DEC analog is the *graph
  Laplacian* Poisson solve `hodge_laplacian(φ) = μ₀ − μ₁` — transport property
  transfer is unproven and is exactly what the PoC tests.
- Flow lines of a gradient field don't cross (collision-friendly), and the
  field is a potential — cacheable per redistribution event, not per tick.

## Tasks

- [x] **T1 — PoC: DEC Coulomb solve on a toy zone graph.** LANDED 2026-09-18 as `crates/katgpt-dec/benches/bench_815_coulomb_redistribution_poc.rs` + [Bench 815](../.benchmarks/815_coulomb_redistribution_poc.md). Fixture generalized to `run_case(w, h, n_sources)` with (4,3,5) = the issue fixture EXACTLY (sources 0..4 @ 0.2, sinks 11 @ 0.6 / 10 @ 0.4) + a refinement axis (8×6, 12×9). (a) conservation: the issue's `belief_mass_divergence` reuse was the WRONG instrument for a SOURCED flow (‖δ₁(j)‖₁ = ‖ρ‖₁ ≠ 0 by design) — the landed gate asserts the pointwise identity `max|δ₁(j)−ρ| ≤ 1e-3` via `codifferential`: PASS 8.9e-8. (b) endpoint MAE ≤ 0.01: **FAIL** — 0.1190 at the fixture, targets [0.6, 0.4] landed [0.4810, 0.5190]. (c) zero-alloc solve path: **PASS** — 0 allocations (fixed-size arrays + `exterior_derivative_into`, counting allocator, warmup-then-snapshot), 3.1/22.8/108 µs at 12/48/108 zones (per event, cacheable).
- [x] **T2 — The 20×-bias analog gate (GOAT axis).** MEASURED same bench — **FAIL, honestly**: the naive distance-field baseline (sum + max forms, pit-convention-unified with the solve so one downhill readout serves both) measures 0.48× / 0.41× / 2.21× relative MAE (Coulomb is NOT ≥10× better anywhere; at the fixture the naive-max form is BETTER: 0.057 vs 0.119). The paper's 20× is for the CONTINUOUS EqM-style rescaled field; on zone graphs the hand-built distance field is a strong, if size-unstable, baseline. The refinement axis localizes the Coulomb miss to the readout: MAE 0.119 → 0.078 → 0.037 as the graph refines 12 → 48 → 108 zones (discretization error in the absorbing-chain proportional split; trapped mass 0 everywhere — mass always arrives, just in the wrong proportions).
- [x] **T3 — Verdict.** NEGATIVE per this task's own clause: T1's endpoint gate failed, so the issue closes as a negative-result artifact (the Issue 573 precedent). The bench is the reproducible artifact. Re-open conditions in Bench 815 §The finding: (a) characteristic-preserving per-particle readout (no proportional splitting at merge vertices) — the continuum guarantee's actual discrete analog; (b) a zone resolution where ≤ 0.01 passes with the naive baseline re-measured; (c) a consumer contract that survives (a) — the director wants arrival proportions, and a trajectory-integrating readout changes what the NPC-side consumer can be. No `coulomb_flow` feature is filed; nothing to promote (no gain — the GOAT gate never passed).
- [-] **T4 (deferred) — riir-train angle.** None needed: the Coulomb case is the paper's TRAINING-FREE arm (Prop 2 needs no GD; the learned `T_θ` arm is the discrete sibling's Plan 411 territory). Unchanged by the T1/T2 verdict — the learned arm is out of this issue's scope either way.

## Non-goals

- No image/video generative modeling (the paper's primary axis — 468's Pass
  rationale stands).
- No CCE constraint re-litigation (Issues 573/574/575 adjudicated that; Plan
  569 shipped).
- No continuous-space codim-1 variant (broken by the paper's own
  counterexamples).

## References

- Research 468 (parent note; this issue = its §5 unmined row + the v3 Prop 2
  delta)
- arXiv:2608.01692 v3 — Prop 2 (Coulomb case), Eq 13; EqM bias measurement
  (20×); codim-1 counterexample note
- Plan 251 (DEC operators: `hodge_laplacian`, `exterior_derivative`),
  Plan 314 (`belief_mass_divergence`), Plan 251 T20 (`DecFlowField` +
  `to_flow_vectors` bridge)
- Issues 573 (Beckmann constraint FAIL) / 574 (transition kernel PASS) /
  575 (2-player CCE PASS) — the constraint-use triage, NOT this construction
- Research 563 / Issue 811 (discrete sibling, `flashar_anchor`)
- Prior art: MBOT crowd evacuation via OT (ACM 2023); DM-Count (NeurIPS 2020)
