# Issue 781: `slt` selection primitive — RLCT λ + WBIC for artifact/rank selection

**Status:** Open — research-backed (R558, arXiv:2010.11560 distillation); T0 novelty gate before estimator work.

Ship a feature-gated `katgpt-core` module `slt` (singular learning theory selection math) behind `slt = []`:

- `rlct_reduced_rank(a: usize, b: usize, r: usize) -> f64` — `λ(r) = r·(a+b−r)/2` (Aoyagi–Watanabe 2005). One line; full-rank limit `r=min(a,b) ⇒ ab/2 = d/2` is the property-test anchor.
- `wbic(n: u64, loss_nats: f64, lambda: f64) -> f64` — `nL + λ·log n`.
- `free_energy(n: u64, loss_nats: f64, lambda: f64, m: u32) -> f64` — `nL + λ·log n − (m−1)·loglog n`.
- `bayes_gap(lambda: f64, n: u64) -> f64` — the `λ/n` generalization-gap predictor (UQ-bearing — floor-gated, T3).
- `sigmoid_wbic_weight(wbic_a, wbic_b, tau) -> f32` — pairwise mixture weight `σ(−ΔWBIC/τ)` for the shipped `rating`/Elo consumers (sigmoid-not-softmax compliant).
- Zero-alloc, no deps, `f64` internals (log-domain), `#[must_use]` throughout.

## Tasks

- [ ] T0 — **Novelty gate on the noise-sweep λ̂ estimator** (R558 §2.3): dedicated prior-art search for Gaussian-perturbation V(t) power-law-fit λ estimation on frozen weights (`λ̂ = m/Σ ln(u_max/uⱼ)` form). Kill or keep BEFORE implementing the estimator. The closed-form arithmetic (λ(r), WBIC) has no such gate — it is published math consumed, not claimed.
- [ ] T1 — `slt` module: the five functions above + property tests (full-rank limit, λ(r) monotonicity, WBIC interior optimum in r, `λ ≤ d/2` ceiling assertion).
- [ ] T2 — GOAT gate G1/G2: **planted-rank recovery** — synthetic reduced-rank regression, known true rank r*; WBIC recovers r*, raw loss picks r_max, BIC over-penalizes to r_min. Bench: selection O(k), alloc-free (G4).
- [ ] T3 — UQ floor gate (R558 §7): `bayes_gap` must beat `d/2n` (BIC's own prediction — the incumbent floor) and constant-gap on CRPS/coverage/Winkler across synthetic families. Cannot beat floor ⇒ FAIL, demote to recorded.
- [ ] T4 — (T0-keep only) noise-sweep estimator `noise_sweep_lambda(loss_fn, w0, dirs, scratch…)` on LoRA-shaped overlays: calibration targets — quadratic bowl ⇒ d/2; planted RRR ⇒ r(a+b−r)/2; R558's ReLU toy ⇒ ≈0.53 vs d/2=10.5. Deterministic under fixed seed (G3 bit-identical).
- [ ] T5 — GOAT verdict: if G1–G4 + floor pass → promote `slt` to default (BMR/Plan 597 precedent: pure math, no interaction surface). Demote losers (any lane where raw-loss selection ties WBIC on held-out).
- [ ] T6 — post-GOAT consumer wiring (file in consumer repos, not here): freeze/thaw WBIC tie-break + sigmoid mixture weights (riir-ai); free-energy cross-n ledger in Raven/δ-Mem merge/keep ranking (riir-neuron-db); dendritic-overlay rank pricing.

## Notes

- Routing: this issue is the modelless track; the sampling-based λ̂ (SGLD) lives in riir-train Plan 404 (LLC diagnostic + λ-guided LoRA rank sweep). T4 is the potential modelless rescue of that instrument.
- Anti-Laplace rule recorded (R558 §5): no Hessian/curvature-based generalization prediction or model selection — the paper measured that instrument class at ~10³× the true λ.
- Pre-implementation: run `substrate-first` (closest cousins verified in R558 §2.2 — `effective_rank` is measure-class-wrong here, BMR/Beta-LCB are complementary axes, no duplication).
