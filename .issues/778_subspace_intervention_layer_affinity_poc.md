# Issue 778: Subspace-Intervention POC — probe-weight SVD triad + layer-affinity sweep over frozen readouts

**Status:** Open — POC, modelless (closed-form probes, zero GD)
**Research:** [katgpt-rs/.research/557_Subspace_Intervention_Probe_SVD_Layer_Affinity.md](../.research/557_Subspace_Intervention_Probe_SVD_Layer_Affinity.md) (arXiv:2607.01987)

## Goal

Turn the paper's post-hoc diagnostic into one measured POC over our existing
frozen-feature consumers, answering three questions the workspace currently
cannot:

1. **Layer affinity (M3 — zero substrate today):** which transformer layer
   maximizes probe fidelity per behavior label? `FutureBehaviorProbe::new`
   takes a caller-supplied `layer: usize` with no measurement behind it; the
   same hand-picking applies to `SteeringHook`/`CollectingHook` layer params
   (riir-ai `latent_steering_bridge.rs`).
2. **Aligned vs random at matched budget (M2 — documented deferred eval):**
   `katgpt-attn/src/funcattn_compose/spectral_pre_rotate.rs:29-31` defers
   "random basis vs eigen-aligned basis at matched param budget" per the
   plan's Gain-tier opt-in policy. The paper's three-arm protocol is that eval.
3. **Stable core vs stochastic tail (M5):** across probe seeds, which singular
   directions are stable (>0.93 similarity at k≤16 in the paper) — i.e. what
   must a freeze/thaw artifact commit, and what is noise?

## Method (all closed-form; no riir-train dependency)

- Probes: ridge fit `W = YᵀX(XᵀX + λI)⁻¹` over labeled activation banks
  (existing oracle-labeled fixtures; FutureBehaviorProbe's mean-difference
  pairs are the same data source). Modelless per R557 Path 0.
- Basis: `thin_svd_into` (`katgpt-core/src/subspace_phase_gate.rs`) on W.
- Arms: aligned top-k `ZV_kV_kᵀ`, random orthonormal k-control, orthogonal
  residual `Z − ZV_kV_kᵀ` — all through the frozen head. The triad already
  exists as a synthetic testbed in riir-ai `causal_validation/micro.rs`; this
  promotes it to a protocol on real fixture banks.
- Stability: `svcca_into` (`katgpt-core/src/data_probe/cca.rs`) across ≥3
  probe seeds (λ jitter + bank bootstrap).

## Tasks

- [ ] **T1** Fixture bank: assemble (layer, activations, label) banks from one
  existing oracle-labeled source (probe-bank fixtures or FutureBehaviorProbe
  pairs); record bank BLAKE3 for reproducibility.
- [ ] **T2** Ridge probe fit per layer + `thin_svd_into` on W; rank-recovery
  curves (k ∈ {4,8,16,32,64,128}) — quantifies the low-rank claim (M4) on OUR
  signal, not KV.
- [ ] **T3** Three-arm intervention through the frozen head; gate: aligned ≫
  random at matched k (paper: random/residual collapse <0.18 vs aligned
  ~0.9). **This closes the `spectral_pre_rotate.rs` deferred eval.**
- [ ] **T4** Layer-affinity sweep per behavior label → peak-layer table;
  propose re-pinning `FutureBehaviorProbe` layer params from measurement.
- [ ] **T5** Seed-stability split via `svcca_into` across ≥3 seeds → stable
  core size k*; record the freeze-policy implication (commit core only vs
  full bank).
- [ ] **T6** Verdict note appended to R557 §"PoC Addendum" with raw numbers;
  close or file follow-up plan accordingly.

## Outcome criteria (negative results are a legitimate close)

- If affinity curves are flat (no peak) → record refutation, close; the
  hand-picked layer is then fine.
- If aligned ≯ random at matched k → the eigen-aligned claim is refuted on
  our fixtures; `spectral_pre_rotate`'s deferral becomes a permanent decline.
- If T5 shows no stable core → freeze policy unchanged; record.
- Any positive arm → follow-up plan (feature flag + bench per GOAT gate rule).

Isolated target dir per global rule (`CARGO_TARGET_DIR=/tmp/...`), cleanup
after. No new deps.
