# Bench 849 — KARC deployed-shape forecast-quality audit (Issue 866 T1b/T1c)

**Date:** 2026-09-22
**Issue:** katgpt-rs Issue 866 (KARC D3 split-config promotion: retrospective coverage audit)
**Bench:** `cargo run --release -p katgpt-core --example karc_deployed_shape_quality`
**Feature posture:** `karc_forecaster` DEFAULT-ON (Phase 22) — the example runs at default features, no new feature, no gate change.
**Predecessor:** [.benchmarks/308_karc_goat.md](308_karc_goat.md) §Phase 5 / §Phase 5.3 (the D3 split-config promotion record)

## The audit question

Bench 308's D3 split-config G1 contract (NRMSE ≤ 1e-3 AND threshold ≥ 8 LT)
was promoted DEFAULT-ON on 2026-07-21, but **both passing legs were measured
on `ChebyshevBasis` configs that no consumer constructs**: the NRMSE leg at
K=8/M=8/**R=2** λ=5e-2 (9.43e-4), the threshold leg at K=8/M=24/R=1 λ=5e-3
(8.16 LT). Every deployed monomorphization is `FourierBasis` at **R=1**,
period 4.0 (riir-engine `karc_bridge`):

| Tier | Monomorphization | d_h | Constructed by |
|---|---|---|---|
| Lod0 (background) | `KarcForecaster<FourierBasis<4>, 8, 4, 2>` | 64 | `karc_bridge::lod` (opt-in dispatch) |
| Lod1/HlaKarc (default) | `KarcForecaster<FourierBasis<8>, 8, 8, 4>` | 256 | `NpcKarcState` (always present) |
| Lod2 (hero) | `KarcForecaster<FourierBasis<8>, 8, 8, 8>` | 512 | `karc_bridge::lod` (opt-in dispatch) |

Issue 866 T1 asked: was the forecast-quality contract **ever measured on any
config a consumer actually constructs?**

## T1(a) — the six riir-engine runtime gates vs the equivalence test

A downstream gate ratifies coverage only if it measures **the same quantity
(forecast accuracy) against the same absolute bar (NRMSE ≤ 1e-3 / ≥ 8 LT)**.
Classification of riir-engine's six `karc_runtime` GOAT gates
(`.docs/05_reasoning/karc_runtime.md`, Plan 332):

| Gate | What it asserts | Absolute accuracy? |
|---|---|---|
| G1 | per-NPC personality **divergence**: 100 identical NPCs diverge to p95 ≥ 0.3·range after 10k ticks | ❌ relative — a uniformly-wrong forecaster diverges too (with a larger margin) |
| G2 | curiosity spike ≥ 5× the forecaster's **own** rolling median residual | ❌ self-relative ratio |
| G3 | MCTS collapse detection: recall ≥ 80% @ ≤ 10% FP | ❌ detection, not accuracy |
| G4 | freeze/thaw `Wout` byte-identity | ❌ wire exactness, orthogonal to accuracy |
| G5 | 1,000-NPC tick ≤ 5 ms | ❌ latency |
| G6 | chain commitment (owned by riir-chain Plan 007) | ❌ commitment |

**None ratifies.** The D3 contract's legs were never measured on any deployed
config, and no downstream gate supplies a substitute.

## T1(b) — the measurement

Protocol mirrors Bench 308 Phase 5: one-step NRMSE (train fit), NRMSE over
1 Lyapunov time of the autonomous rollout, ε=0.1 threshold time in LT. New
in this run: a **persistence baseline** (û_t = u_seed) to make the numbers
interpretable, and a λ sweep.

### Fixture A — Lorenz-driven leaky-belief (the deployed consumer's regime)

The runtime's own belief-update math (`katgpt_core::leaky_core::leaky_step`,
lr=0.1, max_delta=0.3, KIND_MAP gather, Σ[0..6] total) driven by deterministic
Lorenz forcing (σ=10, ρ=28, β=8/3, RK4 dt=0.025/tick; 6 sigmoid kind mixtures
sharpened ^4 and normalized to competitive shares summing to 0.9 — the
`t_min`-active regime where the dominant share exceeds `half_total`).
λ_max = 0.9057/unit by Benettin on the combined 11-dim system → 1 LT =
44.2 ticks. N_TRAIN = 2048 (= riir-engine `DEFAULT_MAX_SAMPLES`). **Synthetic
fixture caveat:** production belief trajectories are game-driven; this
fixture is regime-representative (bounded, chaotically driven, through the
real update math), not corpus-faithful. Belief stds 0.09–0.78/coord
(non-degenerate; the b5 coordinate dominates — the z-driven kind).

| Shape | λ | 1-step NRMSE | 1-LT autonomous NRMSE (persist 3.48e-1) | threshold |
|---|---|---|---|---|
| Lod0 (d_h=64) | 1e-4 | 4.14e-3 | 1.08e8 (exploded) | 0 samp = 0.00 LT |
| **Lod1 (d_h=256)** | **1e-4 (deployed default)** | **1.46e-3** | 1.32e7 (exploded) | 1 samp = 0.02 LT |
| Lod2 (d_h=512) | 1e-4 | 1.21e-3 | 1.21e7 (exploded) | 1 samp = 0.02 LT |
| Lod1 | 1e-6 | 8.92e-4 | 1.11e7 (exploded) | 1 samp = 0.02 LT |
| Lod1 | 1e-3 | 1.85e-3 | 1.86e7 (exploded) | 0 samp = 0.00 LT |
| Lod1 | 5e-2 | 3.72e-3 | 6.28e7 (exploded) | 0 samp = 0.00 LT |

Readings:

- **One-step quality at the deployed shapes is excellent** — 1.2–4.1e-3 at
  λ=1e-4 (100–300× better than the persistence baseline 3.48e-1); λ=1e-6
  reaches 8.9e-4. The deployed configs forecast the next belief tick well.
- **The autonomous rollout is violently unstable on this fixture** — error
  amplifies ~2.2×/step (1e7–1e8 over one LT; the ε=0.1 threshold trips at
  step 0–1). Cause: a linear readout on Fourier features of a
  piecewise-clamped trajectory has no Lyapunov-stable fixed point; λ cannot
  fix it (all four λ values explode).
- **This instability is irrelevant to the deployed consumer**: riir-engine's
  `tick_karc` forecasts ONE STEP from the observed delay ring
  (`forecast_now` over real observations, re-fit every `tau_reest=200`) and
  never feeds its own forecasts back. The ≥ 8 LT threshold leg measures a
  property (autonomous attractor reconstruction) that no code path in the
  deployed consumer exercises. It becomes a live constraint only for a
  future consumer that wants multi-step/autonomous rollouts (e.g. planning).

### Fixture B — double-scroll at the deployed basis family (the D3 contract's own fixture)

The exact Phase 1 ODE (arXiv:2606.19984 §A.1, LT ≈ 7.81 units ≈ 31.24
samples), fitted at the deployed (M, K) family: Fourier R=1, D=3, N=4000.
Persist = 3.03.

| Shape family | λ | 1-step NRMSE | 1-LT autonomous NRMSE | threshold |
|---|---|---|---|---|
| Lod0-family F<4> K=2 | 5e-3 | 7.73e-2 | 9.71 | 0.03 LT |
| Lod1-family F<8> K=4 | 5e-3 | 1.36e-2 | 9.96 | 0.03 LT |
| Lod2-family F<8> K=8 | 5e-3 | 5.25e-3 | 2.37 | 0.16 LT |
| Lod0-family | 1e-4 | 7.73e-2 | 9.63 | 0.03 LT |
| Lod1-family | 1e-4 | 1.16e-2 | 5.32e1 | 0.03 LT |
| Lod2-family | 1e-4 | 3.93e-3 | 1.68e1 | 0.06 LT |

**Every deployed shape fails BOTH D3 bars on the D3 contract's own fixture** —
1-LT NRMSE 2.4–53 vs ≤ 1e-3 (2,400×–53,000× over), threshold 0.03–0.16 LT vs
≥ 8 LT (50–260× under). The Lod1-family at λ=5e-3 is even ~3.3× WORSE than
predicting the previous state (9.96 vs persist 3.03). First-order Fourier
cannot reconstruct this attractor — consistent with the paper's own result
(its headline needed SECOND-order Fourier, d_h=1891) and with Bench 308
Phase 5.3's R=1 NRMSE floor (~5e-3 measured at Chebyshev K=8/M=24; here the
Fourier R=1 floor is higher still).

## T1(c) — verdict: **QUALIFY**

The D3 contract's legs measure **autonomous chaotic-attractor
reconstruction**; the deployed consumer exercises **one-step forecasting from
observed delay rings** for curiosity/divergence signals. These are different
quantities on different fixtures:

1. The compound-gate infeasibility (Phase 5.3) and this audit agree: **no
   config that any consumer constructs meets the D3 bars on the D3 fixture**
   — the promotion rode a split-config contract whose passing legs were
   measured on configs constructed by nobody. That is the contract's scope
   limitation, now recorded (Bench 308 addendum + the Phase 22 feature-def
   comment).
2. On a regime-representative belief fixture, the deployed shapes' own
   quality record is the one-step number: **1.2–4.1e-3 at the deployed
   λ=1e-4** (8.9e-4 at λ=1e-6) — the numbers T1(b) contributes become the
   deployed configs' quality record, per the issue's QUALIFY arm.
3. **DEMOTE is not warranted**: the properties the consumer actually depends
   on are separately gated (divergence/curiosity/latency/exactness — six
   runtime GOATs) and the one-step quality is strong. The absolute-accuracy
   bars are an attractor-research contract, not a consumer requirement.

## Box state

M3 Max (16-core), macOS 26.6.2, release profile, isolated
`CARGO_TARGET_DIR=/tmp/katgpt-rs-issue866`. Load ~12 (sibling wasm-opt build
active throughout — CPU-bound correctness measurement, latency-insensitive;
no GPU involvement). Deterministic fixtures — no RNG anywhere; re-runs are
byte-identical.

## Re-open conditions

- Any future consumer that rolls KARC forecasts out multi-step (planning,
  tree search) inherits the Fixture-A instability — the deployed shapes need
  an autonomous-stability measurement (and likely a different readout or
  spectral-radius constraint) BEFORE that wire.
- A production belief-trajectory corpus (real game-driven evidence) would
  upgrade Fixture A from regime-representative to corpus-faithful; the
  one-step numbers should be re-measured there before citing them as a
  quality SLA.
