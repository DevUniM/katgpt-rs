# Issue 775: PC-ALM wave-mode dual kernel + closed-form rate laws (katgpt-dec / katgpt-core)

**Status:** Open — POC/proof task (research → [Research 554](../.research/554_PC_ALM_Ballistic_Dual_Wave_Credit_Propagation.md), [arXiv:2605.31022](https://arxiv.org/abs/2605.31022))

The shipped dual substrate (`sheaf_admm`, R438/Plan 407; `heat_kernel` family; leaky `evolve_belief`) is entirely **diffusion-mode**: credit/anomaly signals through a chain of L cells reach usable amplitude in O(L²) steps. PC-ALM proves the 1:1-interleaved primal-dual pair propagates **ballistically** — damped-wave dispersion `μ±(k) ≈ exp(−½ρη_h k² ± i√(αη_h)k)`, group velocity √(αη_h), reach `T√(αη_h)` in T steps — with closed-form laws making it certifiably stable. This issue lands the modelless extraction: the wave twin + the laws + the adjoint readout, all feature-gated with α=0 bit-identical to incumbent.

## Tasks

### Phase 1 — `dual` module (katgpt-core)

- [ ] **T1** `dual` module: dual accumulator `λ ← λ + α·r`, completing-the-square target shift `ŷ − λ/ρ`, composite credit `e = λ + ρ·r`, `dual_energy(λ, ρ)`. Fixed-size `[f32; N]`, zero-alloc, no deps.
- [ ] **T2** Closed-form rate setters: `jury_eta_max(σ̂², ρ, α) = 4/(σ̂²(2ρ+α))`, `jury_alpha_max(η, σ̂², ρ) = 4/(ησ̂²) − 2ρ`, regime classifier `{Monotone, DampedOscillatory, Unstable}` from (η, σ², ρ, α) incl. the annulus radius `√(1−η_hρσ²)` and phase `cosθ` formula (paper C.6).
- [ ] **T3** Arrival-time laws: `t_infl ≈ L/√(αη_h)`, `α_reach ≈ L²/(η_h T²)` (≈ 4(L/T)² at η_h=1/λ_max), budget picker `T = 2L`. Unit tests pin the paper's self-calibration (T=2L, λ_max≈4 ⇒ α≈1).
- [ ] **T4** Feature flag `dual_wave = []` (opt-in); α=0 paths proven bit-identical to non-dual baselines (test).

### Phase 2 — wave kernel (katgpt-dec, beside `heat_kernel`)

- [ ] **T5** `wave_kernel.rs`: joint (h, λ) recurrence on `CochainField` pairs over `CellComplex` chains; per-mode eigenvalues populate the predicted annulus (test against closed form).
- [ ] **T6** GOAT gate G2 — **reach bench**: anomaly injected at one end of an L-cell path graph, ticks-to-detectable at the far end. PASS: wave `≈ L/√(αη_h)` beats heat `≈ L²/(ρη_h)` by the predicted margin (not just "faster"). Sweep L ∈ {16, 64, 128} using the path-graph workloads `bench_407_*` already build.
- [ ] **T7** GOAT gate G4 — zero-alloc + latency: one wave step at K=1000 vertices within the same budget class as `sheaf_admm_step` benches (<5 µs mean at K=100 scale).

### Phase 3 — exact-adjoint readout (the "backprop without backprop" primitive)

- [ ] **T8** Adjoint readout: run the interleaved iteration on a frozen toy layered map with a terminal scalar; return λ as dJ/d(node). GOAT gate G1: cosine(λ, explicit-reverse-mode) ≥ 0.9 at T=2L on frozen random MLP chains (paper Fig 5 diagnostic, replicated modellessly) + spot-check vs finite differences.
- [ ] **T9** Hodge triage helper: `hodge_decompose(residual flow)` classification — exact (dual absorbs; keep iterating) / harmonic (no local fix; escalate) / coexact (circulating; break). Unit test: a harmonic residual provably not absorbed by any α.
- [ ] **T10** Docs: `.docs/` entry cross-linking R438 ↔ R554 (diffusion mode ↔ wave mode as one family); clippy clean; gates run via the repo's standard lanes.

## Acceptance

GOAT gates above pass behind `dual_wave`; promotion to default only if the reach bench margin holds at game-relevant depths (else stays opt-in with the laws documented). Close with commit hash referenced in R554.
