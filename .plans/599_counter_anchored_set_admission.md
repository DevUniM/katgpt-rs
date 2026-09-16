# Plan 599: Counter-Anchored Set Admission — Modelless Fan-Out Gate

**Date:** 2026-09-16
**Research:** [katgpt-rs/.research/564_R4T_Counter_Anchored_Fanout_Retrieval.md](../.research/564_R4T_Counter_Anchored_Fanout_Retrieval.md)
**Source paper:** [arXiv:2603.06397](https://arxiv.org/abs/2603.06397) — "Efficient, Property-Aligned Fan-Out Retrieval via RL-Compiled Diffusion" (R4T, ICML 2026)
**Target:** `crates/katgpt-core/src/set_admission.rs` (new module, sibling of `certified_frontier.rs`) + Cargo feature `set_admission = []`
**Status:** Active — Phase 0 (planned; PRIMARY track — the trained twin is riir-train Plan 412, SECONDARY by the serving-envelope rule)

---

## Goal

Ship the modelless extraction of R4T's counter-anchor reward as a **selection-time set-admission operator**: greedy admission over candidates scoring `g(x) + α·a(x,q₀) + κ·log(1 + x̂ᵀM⁻¹x̂)` under a colinearity cap, with Sherman–Morrison rank-1 maintenance (O(d²) = 64 FLOPs/admission at d=8), an incremental participation-ratio collapse tripwire, an **exact** cosine-kernel Vendi certificate via d×d eigenduality (reusing `certified_frontier::vendi_diversity`), and a collapse→re-fan-out θ-ladder. Consumers: `ShardIndex` diverse retrieval (opt-in extension) and the riir-clippy healer set-rerank (issue 121). GOAT gate: brute-force parity + known-answer certificates (G1), ≤10 µs full gate @ 512 candidates (G2), no-regression on `certified_frontier`/`diverse_retrieval` suites (G3), zero-alloc (G4).

**Honest scoping:** the greedy modular+logdet surrogate is classical DPP MAP territory — the (1−1/e) bound applies to the surrogate, exact Vendi certifies post-hoc. The novel parts are the counter-anchor composition, the certificate loop, and the recovery ladder. The d=8 ceiling (Vendi ≤ min(K,d)) is reported as saturation, never hidden.

## Phase 0 — Pin the math

### Tasks

- [ ] **T0.1** Fix kernel = cosine (eigenduality requires linear/cosine; document the RBF→Nyström degradation as out of scope).
- [ ] **T0.2** Write the L1/L2 property-test spec: (L1) a modular-only objective over a duplicate-tolerant pool admits an effective-rank-1 set; (L2) zeroing each anchor weight makes the corresponding degenerate family (paraphrase-collapse / semantic-drift / coordinate-gaming) reachable; the full triple excludes all three interiors.

## Phase 1 — Core primitive (`set_admission.rs`, feature `set_admission`)

### Tasks

- [ ] **T1.1** `SetAdmissionConfig { alpha_align, kappa_div, theta_coll, rho_vendi }` + `Default` (R4T's reward proportions 0.6/0.2/0.2 as the starting sweep point for α/κ, not a claim).
- [ ] **T1.2** Greedy admission: seed = argmax modular score; each admission adds `g(x) + α·cos(x,q₀) + κ·log(1 + x̂ᵀM⁻¹x̂)` with `M⁻¹` maintained by Sherman–Morrison rank-1 update into a fixed `[f32; 64]` scratch; reject candidates with `cos(x,s) > theta_coll` for any admitted `s` (the `ColinearityBatchGate` 0.95 precedent).
- [ ] **T1.3** `participation_ratio(G)` incremental estimator — `(tr G)²/tr(G²)` off the maintained Gram; O(d²) per item, no eigensolve, no logs (the between-certifications fast path).
- [ ] **T1.4** `cosine_kernel_eigs_into(x̂: &[[f32; D]], out: &mut [f32])` — d×d symmetric Jacobi eigensolve on the Gram (eigenduality: exact Vendi for cosine kernels, K-independent cost); certificate = `vendi_diversity(eigs)` (consume, never fork).
- [ ] **T1.5** L1/L2 property tests per T0.2 + known answers: identical set ⇒ Vendi = PR = 1; orthonormal set ⇒ both = min(K,d); PR/Vendi rank-correlation ≥ 0.95 over 10⁴ random sets (empirical pin — different functionals that agree on ordering).

## Phase 2 — Latent fan-out construction (query expansion, modelless)

### Tasks

- [ ] **T2.1** Tangent-cap direction bank: orthonormal basis ⊥ q₀; B maximally-separated unit directions via `sphere_exclusion_coverage` (frozen table, ~1 KB at B=32,d=8); candidates `cᵢ(θ) = cosθ·q₀ + sinθ·(U tᵢ)`.
- [ ] **T2.2** θ-ladder: smallest θ with `minᵢ cos(cᵢ, N(cᵢ)) ≥ τ`; tripwire fire ⇒ next rung (the collapse→re-fan-out recovery loop; the CGSP fire-and-inject shape).
- [ ] **T2.3** Local-PCA variant: kNN covariance (8×8) eigendecomposition; fan-out `x̂₀ + scale·Q√Λ·zᵢ` over fixed low-discrepancy `{zᵢ}`, renormalize, snap. (Corpus-adaptive second moment = the dominant corpus-conditionality a diffusion student would learn.)
- [ ] **T2.4** Optional arm: deterministic exp-tilt reweight `wᵢ ∝ exp(λ·Ψ(cᵢ))` + `systematic_resample_into` (the `distributional_steering` machinery) as the RL-fixed-point replacement — measure, don't assume.

## Phase 3 — GOAT gates

### Tasks

- [ ] **T3.1 G1 correctness:** brute-force parity for n ≤ 20, K ≤ 5 (enumerate all C(n,K) subsets: greedy ≥ (1−1/e)·OPT on the surrogate; report the greedy==OPT rate); grounding invariant — every post-snap candidate is a corpus point by identity; θ-ladder monotonicity (larger θ ⇒ strictly larger mean pairwise angle).
- [ ] **T3.2 G2 perf:** admission step ≤ 200 ns; full gate ≤ 10 µs @ C = 512; PR update ≤ 100 ns; exact certificate ≤ 1 µs @ K = 32 (criterion bench, quiet-box CPU figure cited).
- [ ] **T3.3 G3 no-regression:** `certified_frontier` benches + downstream `diverse_retrieval` test suite stay green/unchanged when the gate is wired opt-in.
- [ ] **T3.4 G4 alloc:** zero-alloc asserts over 1000 admission cycles (stack scratch only; the 96-byte wedge precedent).
- [ ] **T3.5 Saturation honesty:** the certificate reports `saturated = (vendi ≥ 0.95·min(K,d))` beside collapse — the L6 ceiling is a first-class output, never silent.

## Phase 4 — Consumers (opt-in wiring; promotion only on gate wins)

### Tasks

- [ ] **T4.1** riir-neuron-db: `retrieve_diverse_counter_anchored(context, k, cfg, guard)` under `diverse_retrieval` — the existing pure-diversity path stays DEFAULT (demote only if the counter-anchored arm wins the eval; seed-identity test `test_retrieve_diverse_seed_is_cosine_nearest` must stay green — it pins the anchor term).
- [ ] **T4.2** riir-clippy consumer per issue 121: set-level rerank of the merged seven-domain span pool + Vendi axis in `retrieval_eval` + collapse→re-fan-out recovery; `detect_collapse` stays as the eval axis, not the guard.
- [ ] **T4.3** Game-runtime follow-up (riir-ai, recorded in Research 564 §2.2): AnyRAG evidence slates / zone-attention triad — file as its own issue when the substrate lands.
- [ ] **T4.4** Self-adaptive follow-up (track b): re-freeze improved direction banks from runtime evidence into a `MerkleFrozenEnvelope` (1 KB artifact; BLAKE3 round-trip bit-identity tests).

## GOAT gate rule

Feature flag `set_admission` (opt-in) until G1–G4 pass AND a consumer eval shows a win; then promote per stack-slot discipline and demote the loser (pure-diversity admission) if the counter-anchored arm dominates the same slot. **Report-the-Floor check:** this primitive claims no distribution/interval/coverage — the (1−1/e) is a surrogate bound and exact Vendi is the honesty instrument, so the conformal floor rule is not triggered (recorded here so the next re-gate doesn't re-litigate).

**Cross-refs:** riir-train Plan 412 (trained twin; this plan's modelless baseline is its GOAT gate) · riir-clippy issue 121 (fastest consumer) · Research 496 SPADE (frozen designer + corpus grounding — the precedent that the modelless arm is strong) · Research 510 ActFlow (sphere-exclusion/Vendi scoreboards this consumes).
