# Issue 777: Modality-Additive Belief Kernel + Ablation-Superposition Diagnostic

**Status:** Open — T1 (measurement) first; T2 gated on T1's numbers

**Source:** [Research 556](../.research/556_FLYNN_Modality_Additive_Belief_Superposition.md) — FLYNN [arXiv:2607.00025](https://arxiv.org/abs/2607.00025): connectome-wired RNN survives total vision loss (44.3% vs ≤16.5% for dropout-trained baselines) because internal states superpose LINEARLY per sensory modality (blind→full ≈ blind→left + blind→right, cosine 0.9998; matched small-world control: 0.9439 and total collapse).

**The gap (mechanism-verified):** `ReconstructionState::evolve_belief` (katgpt-sense reconstruction.rs:891) fuses the 6 `SenseKind` channels with divisive normalization + subtractive centering over the modality sum — `delta_i = (lr·t_min/total)·(k_{m[i]} − 0.5·total)`, `total = Σ all kinds`. Every dim's delta depends on ALL modalities: ablating one kind rescales every remaining modality's gain. Per-modality contributions are not separable; graceful degradation is compensation-by-lottery, not structure. Same shape in `katgpt-micro-belief` `LeakyIntegrator`.

**P1 — the diagnostic (modelless, closed-form):** for belief kernel K with per-modality channels, fix an input stream; for each subset S of modalities run to steady state; `Δ(S) = h(S) − h(∅)`; score additivity by `cos(Δ(full), Σ_m Δ({m}))` + magnitude ratio. Runs directly on our 8-dim beliefs (no PCA needed). Doubles as a runtime health probe and a G2-style gate for new kernel families (would have caught R304's AttractorKernel 569-flip failure pre-bench).

## Tasks

- [ ] **T1 — Measure P1 on shipped kernels.** Bench (criterion or plain #[test] report): superposition cosine over the 6 `SenseKind` channels on `evolve_belief` (katgpt-sense) + `LeakyIntegrator` and `AttractorKernel` (katgpt-micro-belief). Prediction from the formula: divisive normalization fails (cosine well under 1); AttractorKernel fails chaotically. Reuse the `g2_ablation_parity_smoke` harness pattern (salience_tri_gate_bench.rs:210). Record numbers in this issue; they gate T2.
- [ ] **T2 — `modality_additive` feature variant** (katgpt-sense, opt-in): restructure the fusion so each kind contributes `c_m(k_m)` with NO cross-modality terms (no `1/total` gain, no `−0.5·total` centering; per-dim retention α per FLYNN's per-class leak rates — take per-kind α from config, default to the current effective time constant). Keep zero-alloc, `[f32; 8]` layout, KIND_MAP wrap. Default path byte-identical (feature-gated branch only).
- [ ] **T3 — Blinded-belief quality bench.** Toy: fixed stimulus stream, ablate subsets of kinds; measure belief-state error vs a full-input oracle for (a) divisive kernel, (b) additive kernel. The claim to prove/refute: additive degrades linearly and predictably (cosine ≈ 1 in T1 re-run), divisive does not. Honest PoC per §3.6 — no quality-parity claim without these numbers.
- [ ] **T4 — GOAT gate.** G1 correctness (superposition cosine ≥ threshold, e.g. 0.99, on the additive variant); G2 perf (no regression vs default at full input; zero-alloc); G3 no-regression (full-input belief trajectories within tolerance of current kernel OR document behavioral change + re-pin benches); G4 alloc-free. Outcome decides: promote `modality_additive` to default if it wins, else record the negative and close.
- [ ] **T5 — (stretch) Wiring control on the cosine:** run P1 on `lif_graph` with its shipped `maslov_sneppen` degree-preserving rewiring — FLYNN's WS-dissociation method on our own substrate. Report-only.

## Constraints

- Raw sync scalars unchanged — this is think-brain/belief-kernel territory only (sync boundary rules, AGENTS.md §Latent vs Raw).
- No new deps; no connectome data (licensing, R379).
- Keep `.rs` files under 2048 lines; feature-gated code healed via `cargo heal --verify-args "--features modality_additive"`.
- Demote/record honestly if the additive variant loses T3/T4 — the diagnostic itself (T1) is a keeper either way.
