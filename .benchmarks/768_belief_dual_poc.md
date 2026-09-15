# Bench 768 — Belief Dual State POC (Issue 952 §B T3)

**Status:** RECORD — bench landed, T3 closed CONDITIONAL. Alert-lane use DECLINED;
slow-pressure-variable use viable at the measured operating point
(α=0.5, ρ=3, arming 600 ticks). Reopen triggers in Issue 952 §B.

**Date:** 2026-09-15 · **Bench:** `belief_dual_bench` (`benches/belief_dual_bench.rs`,
`[[bench]]` `required-features = ["sense_composition"]`, harness=false — opt-in
lane, nothing default changes; `sense_composition` itself is transitively default
via `schema_centroid`, the bench runs at default features).

## What was prototyped

Issue 952 §B: `evolve_belief` is a leaky integrator with no steady-state-
elimination property. The POC wraps the UNCHANGED `ReconstructionState` with a
per-NPC dual state `λ ∈ [f32; 8]` + a slow-expectation EMA track (β = 0.03,
the shipped `temporal_deriv_alpha_slow` default):

```text
arming (600 ticks):  λ frozen; expectation primes on the baseline regime
armed tick:          a'_m = a_m − max(0, λ_m)/ρ        (one-sided per-tick
                                                        evidence demotion)
                     accumulate(a') + evolve_belief()   (SHIPPED path, verbatim)
                     λ ← clamp(λ + α·(belief − expectation), ±4)
readout:             sigmoid(⟨λ, d⟩), d = sustained-error axis (kind 2 → dim 2)
```

The dual's ENTIRE footprint is the demoted stream; the belief step is the
shipped `evolve_belief` untouched. λ=0 (α=0 / arming) demotes nothing
(`a − 0.0/ρ == a` bit-for-bit) — α=0 is the incumbent **by construction**, and
G1 measures it anyway (`to_bits` equality, every tick, 400-tick mixed schedule
incl. a kind-0 burst exercising the KIND_MAP wrap dims 6/7).

## Gates (pre-committed before v1 ran; laws unchanged since)

| gate | law | operational (800-tick) | equilibrium (6000-tick) |
|---|---|---|---|
| G1 | α=0 bit-identical to incumbent | PASS | PASS |
| G2a/b/c | sustained S3: fires ≥0.90 / holds (band ≤0.05) / clears ≤0.60 after removal | 0.982 / 0.000 / **PASS** | 0.949 / 0.001 / 0.018 **PASS** |
| G2d/e | transient T2 fires ≥0.50 then clears | **FAIL** (0.500 — never fires) | 0.982 → 0.018 **PASS** |
| G3 | sustained ladder monotone + transients < S1 | **FAIL** (clamp ties) | **PASS** (0.569 < 2.478 < 2.927 < 4.000; T at 0.018/0.500 < S1 0.638) |
| G4 | zero alloc / 1000 dual ticks | PASS (0) | PASS |
| G5 | λ bounded, plateau converged, operating point exists | **FAIL** | **PASS** (band 0.001/0.016 at α=0.5, ρ=3) |

**Verdict: CONDITIONAL** — every law holds at the equilibrium horizon; nothing
grades within the operational (~1000-tick) horizon.

## Why (the measured mechanisms)

1. **v1 (additive shift on the cumulative gather) — honest NEGATIVE.** All
   sustained cells pinned at +λ_max (ties, no ranking); the transient railed
   to −λ_max during warmup descent and never fired (peak 0.018); strong
   anomalies drove the shifted total negative → `leaky_step`'s degenerate
   guard froze the belief → the alarm never cleared (G2c 0.982 forever).
   Mechanisms: the kernel's all-dims-sink warmup makes
   `belief − expectation < 0` persistently (the dual integrates the init
   transient unless armed); the additive shift is not commensurate with
   cumulative evidence O(10..100); an 8-tick burst is sub-resolution (the
   cumulative share crosses the kernel's 50% neutrality boundary only after
   ~26 ticks at amp 1.5 — crossing time scales with the accumulated baseline).
2. **Multiplicative share demotion — rejected analytically (not measured):**
   its steady state pins the long-run share at the same 50% boundary for EVERY
   amplitude (the required demotion factor is amplitude-independent), so λ*
   cannot be graded — ranking impossible by construction. The per-tick
   additive demotion's equilibrium IS graded: **λ* = ρ·(a − 0.22)** (the
   stream reduction pinning the long-run share at 50%) — measured ladder
   monotone at α=0.5/ρ=3.
3. **The horizon finding (the CONDITIONAL's substance):** the dual feedback
   loop closes through the kernel's CUMULATIVE evidence (infinite memory), so
   the graded equilibrium is a thousands-of-ticks object. Within 800 ON-ticks
   λ is clamp-transient and its endpoint is governed by nonlinear
   share-crossing times, not amplitude (measured non-monotone across the
   α×ρ grid). At 6000 ticks the λ* plateaus emerge, stable and graded.
   **At 20 Hz: the pressure variable takes minutes to develop — a mood/
   desperation-grade accumulator, never an alert lane.**
4. **Aftermath-dip semantics (G3 v3.1 amendment):** the strong transient's
   post-burst recovery sink rails λ to −4 (end 0.018) — sustained *negative*
   deviation after the event, which the issue does not specify. The strict
   total order's T2>T1 edge is recorded-not-gated; the gated law is the
   issue's: sustained ranking + transients below weakest sustained.
5. **Weak transients (amp 0.5) are invisible to ANY detector on this kernel:**
   the burst never pushes the cumulative share over the 50% boundary, so the
   primal itself never responds — the dual cannot see what the primal cannot
   see.

## Operating point

α = 0.5, ρ = 3.0 (arming 600 ticks, β = 0.03, λ_max = 4.0). The
`WaveParams::self_calibrated` constants (α=1, ρ=1) do NOT transfer — measured
across both horizons; ρ=3 matches the demotion to the per-tick activation
scale (streams O(0.05..1)). Full sweep tables print from the bench.

Latency: dual tick 25 ns vs incumbent 5 ns (5.0×, informational) — trivially
cheap at 1000-NPC scale (~25 µs/tick aggregate), zero-alloc.

## Dispositions

- **No crate change.** The prototype is bench-local; promotion of a
  `belief_dual` lane would need a consumer that wants a *slow pressure
  variable* (Issue 952 §C's desperation-as-λ is the natural one — see T4).
- **Alert-lane framing DECLINED** (operational-horizon FAIL) — same disposition
  shape as Issue 952 §A T2's decline; the reopen triggers live in the issue.
- The one-sided demotion + arming phase are part of the viable formulation —
  an un-armed or two-sided variant re-introduces the measured v1 failures.

## Reproduce

```bash
CARGO_TARGET_DIR=/tmp/belief_dual cargo bench --bench belief_dual_bench
```
