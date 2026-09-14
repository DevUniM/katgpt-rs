# Bench 763 — PC-ALM Dual-Wave Kernel GOAT (Issue 775, Research 554)

**Status:** COMPLETE — ALL GATES PASS (2026-09-14, M3 Max, quiet-ish box under multi-agent load)
**Feature:** `dual_wave = []` in BOTH `katgpt-core` (`dual` module) and `katgpt-dec` (`wave_kernel` module) — opt-in
**Paper:** PC-ALM, arXiv:2605.31022 ("Deep Learning without Backpropagation via Augmented Lagrangian Predictive Coding")

## The primitive

The interleaved primal-dual pair on constraint operators — the ballistic
(hyperbolic) twin of the shipped heat-kernel family (`heat_kernel`,
`sheaf_admm`'s z-diffusion, leaky `evolve_belief` — all parabolic,
O(√T) reach):

- **katgpt-core `dual`** (T1–T4): `dual_accumulate_into` (λ ← λ + α·r),
  `target_shift_into` (ŷ − λ/ρ, completing the square), `composite_credit_into`
  (e = λ + ρr), `dual_energy`, Jury setters (`jury_eta_max = 4/(σ̂²(2ρ+α))`,
  `jury_alpha_max = 4/(ησ̂²) − 2ρ`), regime classifier
  `{Monotone, DampedOscillatory, Unstable}` (annulus radius √(1−ηρσ²),
  α-independent det — the annulus law), arrival laws (`t_infl = L/√(αη)`,
  `alpha_reach = L²/(ηT²)`, `budget_ticks = 2L`), `normalize_spectral_into`
  (unit-σ conditioning), and `adjoint_readout_{init,tick,into}` — the
  exact-adjoint-at-KKT readout (λ → −δ, LeCun 1988 App. A) with
  Jury-set rates from power-iteration σ̂² on the STACKED constraint
  operator's AᵀA (the accurate estimate matters: the Gershgorin bound
  `(1+σ̂)²` overshrinks η ~2× and kills convergence — measured).
- **katgpt-dec `wave_kernel`** (T5, T9): `wave_step_into` — the joint (h, λ)
  recurrence on `CochainField` pairs over `CellComplex` chains (primal
  rank-k + dual rank-(k+1) on the coboundary surface; consumes
  `exterior_derivative_into`/`codifferential_into` verbatim; zero-alloc via
  `WaveScratch`), and `hodge_triage` — exact/harmonic/coexact residual
  classification (the harmonic class is unabsorbable by ANY α —
  unit-proven: `harmonic_residual_not_absorbed_by_any_alpha`).

α = 0 is bit-identical to the incumbent diffusion step `h ← h − η·(ρ·δᵀδh)`
(same operators, same order — unit-pinned; the dual stays exactly zero).

## G2 — reach (the ballistic-vs-diffusive law, paper Eq 23)

Path graphs, inject 1.0 at vertex 0, detect |h[L−1]| ≥ 1e-3. Wave
(α=1, self-calibrated η=1/4, ρ=1) vs its own α=0 diffusion twin (same η, ρ —
the honest A/B: only α differs).

| L | wave | heat | t_infl=2L | heat/wave |
|---|------|------|-----------|-----------|
| 16 | 18 | 44 | 32 | 2.44 |
| 64 | 97 | 954 | 128 | 9.84 |
| 128 | 212 | 4687 | 256 | 22.11 |

**PASS** — wave linear (≈ 1.66·L, inside the 2L prediction band, ≤ 4L gate),
heat quadratic, ratio ×9 growth across the sweep (gate ×2). This is the
paper's O(T)-vs-O(√T) law, measured on the shipped DEC substrate.

## G4 — latency + zero-alloc (the T7 gate)

| Workload | mean | gate | allocs (steady state) |
|---|---|---|---|
| K=100 (10×10 grid, dim 8 — the sheaf_admm G4 shape) | **2.38 µs** | < 5 µs | **0** |
| K=1024 (32×32 grid, dim 8) | **29.9 µs** | < 50 µs (linear-class) | **0** |

**PASS** — same budget class as `sheaf_admm_step` (1.808 µs at K=100/d_v=8
with T=5 inner steps; the wave step is 2 coboundaries + 1 codifferential).

## G1-adjoint — the exact-adjoint readout (the T8 gate)

Frozen random linear chains (paper construction: W ~ U(−1,1)/√d, d=16),
ρ=1, α=1, η = 0.8·jury_eta_max(σ̂²_chain) — convergence-detected protocol
(tick until the feasibility residual hits its floor), cap 64L.

| L | seeds | min layer cosine(λ, −δ) | ticks to converge | ‖r‖² |
|---|---|---|---|---|
| 4 | 3 | 1.0000 | 95–114 | ~1e-9 |
| 8 | 3 | 0.9997–1.0000 | 167–226 | ~1e-9 |
| 16 | 3 | 0.9605–0.9979 | 223–264 | ~1e-9 |

**PASS (gate ≥ 0.9 at every layer, every chain)** — the raw plane returns
to forward-pass values (feasibility ~1e-9); all correction lives in λ.

### The T=2L shortcut column (the honest finite-T finding)

| L | T=2L cosine | verdict |
|---|---|---|
| 4 | 0.9746 | PASS (gated) |
| 8 | 0.9329 | PASS (gated) |
| 16 | −0.6978 | REPORTED — finite-T limitation |

Physics, made precise: the settled readout's low-mode damping needs
`ηρσ₁²·T ≳ 6` while Jury caps `ηρσ²_max < 2`; with `σ₁²/σ²_max ~ (π/L)²`
the settling budget grows ~L² — the paper's own "finite-T misaligns"
limitation. ARRIVAL stays ballistic at 2L (G2 proves that independently).
Spectral caveat (ungated): unit-spectral layers make the stacked operator a
PURE difference operator — σ₁² → 0 as L grows, so low-mode settling rings
longest there; random-init layers (the gate regime) lift those modes.

## Unit-test gates (G1 correctness, both crates)

- 11/11 `katgpt-core::dual` tests: the completing-the-square identity,
  composite credit, Jury bounds recovering PC's ηρσ² < 2 at α=0, the
  classifier against an independent f64 quadratic-formula oracle over a
  375-cell parameter grid (boundary/degenerate cells skipped with the
  rationale), annulus α-independence, α=0-always-Monotone, arrival
  self-calibration (T=2L, η=1/4 ⇒ α≈1), reverse-mode cosine, FD spot-check.
- 7/7 `katgpt-dec::wave_kernel` tests: α=0 bit-identity (same ops same
  order), δᵀδh == Lh, the annulus law MEASURED on path modes (windowed
  energy-sum decay = √(1−ηρσ²) per step, α-independent, two α arms),
  Jury instability measured dynamically (ησ²(2ρ+α) ≈ 10.8 > 4 grows),
  ballistic-beats-diffusion at L=64 (the G2 miniature), harmonic
  unabsorbability (bit-identical h and λ for α ∈ {0.5, 1, 2}), exact +
  coexact triage classes.

## Honest caveats

- The T=2L budget is NOT a settled-readout guarantee at depth (column
  above); the convergence-detected protocol is the honest consumer
  protocol, and `budget_ticks(L) = 2L` ships as the self-calibrated
  ARRIVAL budget (the regime where it is exact: σ(W)=1 difference-operator
  chains, λ_max ≈ 4 depth-independent).
- Rate derivation is a modelless heuristic for the coupled chain (the Jury
  classifier is exact per singular mode; the chain σ̂² comes from 8-round
  deterministic power iteration — measured 3.28 vs dense-truth 3.28 on the
  probe chain after the ‖z‖²-vs-‖z‖ bug fix, both recorded here because
  the first implementation shipped the square).
- Promotion to default: NOT promoted — opt-in pending a game-relevant-depth
  consumer (the honest arithmetic from R554 Q3: game zone hierarchies are
  L≈4 tiers; the feel improvement is real but modest there). The closed-form
  laws are the durable value either way.

## Run

```bash
CARGO_TARGET_DIR=/tmp/bench763 cargo bench -p katgpt-dec \
  --features dual_wave --no-default-features \
  --bench bench_775_dual_wave_goat -- --nocapture
CARGO_TARGET_DIR=/tmp/bench775adj cargo bench -p katgpt-core \
  --features dual_wave --no-default-features \
  --bench bench_775_adjoint_goat -- --nocapture
```
