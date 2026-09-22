# Issue 875: PFD horizon weighting + target-anchored renoise probe (Research 582 modelless arm)

**Status:** OPEN — poc tier, opt-in feature, no default promotion without GOAT

**Source:** [Research 582](../.research/582_Probability_Flow_Distillation_Wasserstein_Gradient_Flow.md) (arXiv:2605.09071 Probability-Flow Distillation). Sibling filings: riir-train `.issues/569` (training arm), riir-ai `.issues/996` (crowd fusion).

**Problem.** Three paper-stated closed forms with in-stack consumers ship nowhere in the workspace:

1. **The (T−t) horizon weighting law** — averaging a uniformly-sampled-t partial integral gives effective weight (T−s) (Fubini swap on the triangular domain): low-noise observations get max weight, decaying linearly to **exactly zero at t=T**. `twist_step_into` is span-normalized β/KL-budget; `renoise_ce` averages k_draws flat; `dllm_solver` switching is entropy- (state-) driven — nothing weights by remaining horizon.
2. **The w(t) closed-form schedule** `w(t) = ½(T−t)g(t)²c(t,0)²` with `c(t,0)=exp(−∫a)` — offline-computable over a discrete t-grid → a committed O(1) lookup table (the `katgpt-attn/static_cal.rs` Sinkhorn→table precedent, except this table is exact closed form, no iteration).
3. **Time-annealed t-sampling range** — iteration-count-indexed anneal of the sampled noise range toward low noise (orthogonal to the shipped state-indexed entropy switching), plus the zero-terminal-weight truncation corollary (skipping t near T is first-order lossless because w(T)=0).

Plus one probe mode:

4. **Target-anchored round-trip** — `renoise_ce` ships perturb→re-resolve-through-the-SAME-operator→drift; PFD's variant resolves against a TARGET prior (frozen scorer), turning the drift score from self-consistency into distributional surprise against the target. Consumer: consolidation surprise ranking (which shards enter the Raven/δ-Mem sleep cycle first) — the `[f32; 8]` score convention already fits `NeuronShard.hla_moments`.

## Tasks

- [x] **T1** `horizon_weights` utility in katgpt-core (pure fn + optional committed table, BLAKE3 `commit`/`verify` per the StaticCalTable pattern): `w(t) = ½(T−t)g(t)²c(t,0)²` over a discrete grid; normalized (T−s)/T variant for generic horizon weighting. G1: table vs closed-form recompute bit-match; G2 lookup vs per-call exp/pow (ns/op); G4 fixed `[f32; N]`, zero-alloc. **Name-collision note:** `horizon_decay` already exists in `katgpt-core` `hint_regret/memory.rs` — that is `r̂·σ(−λ·Δt)` staleness fading (mechanism-distinct from remaining-horizon accumulation weighting); name the new utility to avoid the collision (e.g. `remaining_horizon_weights`).
- [ ] **T2** Wire T1 as an opt-in weighting in ONE consumer: `renoise_ce` k_draws averaged under (T−t) weights (draw t non-uniformly per the law) — vs flat averaging. Quality gate: selectivity precision@k against a planted-drift oracle on a synthetic mixture; latency unchanged class.
- [ ] **T3** Time-anneal struct for `dllm_solver` sampling ranges (`[0.02T, 0.98T] → [0.02T, 0.70T]` late-iteration shape, iteration-indexed) + zero-terminal-weight truncation predicate. Gate: quality-at-fixed-budget vs flat range on the toy harness built by riir-train 569 C9 (shared fixture; do not duplicate).
- [ ] **T4** Target-anchored `RenoiseCeProbe` probe mode (re_resolve against a caller-supplied target scorer) + a consolidation-ordering sketch consumer (score rides existing passes; ordering-only, no behavior change). Gate: precision@k vs oracle novelty (drift injected at known shards).
- [ ] **T5** GOAT verdict per task (G1 correctness, G2 perf, G3 no-regression, G4 alloc) recorded here; promote-to-default only on modelless gain; demote/retire losers.


**T1 GOAT verdict (2026-09-22, commit 02d5813d):** PASS - G1 table/pure-fn bit-match (to_bits) in-module + e2e root gate, independent f64 oracle rel < 1e-5; G2 (release, shared ab_timing harness) table lookup 2.13 ns/op vs the STRONG per-call baseline (caller-held integral, one exp) 9.68 ns/op - median b/a 0.2222 (4.5x faster), 41/41 interleaved rounds; G3 opt-in + default-off (no default-path surface); G4 fixed [f32; 64], 0 allocs on build + 1024 lookups (TrackingAllocator). Stays opt-in per the no-default-consumer rule - promotion rides T2.

**Non-goals:** KL `MeasureReward` row (documented module non-goal — density estimation; `MmdReward` is the shipped measure-level analog); negative-CFG helper (no consumer in katgpt-core — routed to riir-train 569 C4); any W2-geometry claim (the exactness theorem is continuous-space, linear-drift scoped — we adopt the schedules, not the theorem).
