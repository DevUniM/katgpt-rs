# Issue 779: Subspace-intervention follow-up — lib promotion + FUNCATTN arm + real-bank affinity

**Status:** Open — T1+T2+T4 RESOLVED (Bench 766, 2026-09-15); T3 (real-bank
affinity capture) deferred — needs a real-model run via riir-ai
CollectingHook / riir-train fixtures; sibling lanes active in both repos
at deferral time. Re-file there when free, or run from riir-train.
**Research:** [katgpt-rs/.research/557_Subspace_Intervention_Probe_SVD_Layer_Affinity.md](../.research/557_Subspace_Intervention_Probe_SVD_Layer_Affinity.md) §"PoC Addendum" (Issue 778 resolved — protocol validated on planted ground truth)

## Context

Issue 778's POC validated the three-arm subspace-intervention protocol on a
synthetic tiered bank: affinity sweep recovers planted peaks 8/8; projection
identity exact; residual collapse 0.021; aligned-vs-random contrast 1.96× at
matched k=4. Positive arms → follow-up per the issue's outcome criteria.

## Tasks

- [x] **T1** Promote the protocol from the test harness to
  `katgpt_core::subspace_intervention` behind an opt-in feature (house
  no-default-consumer rule): `three_arm_eval`, `affinity_sweep`, and
  `basis_similarity` as reusable functions over `thin_svd_into`; zero new
  deps; G1 identity + G4 alloc gates from the harness become unit tests.
  (Bench 766: promotion found + fixed the POC's ridge algebra slip — the
  harness's solve collapses to `W = XᵀY`, a nearest-mean probe, NOT ridge;
  the shipped primitive computes the true `Σⱼ vⱼ(vⱼᵀM)/σⱼ` solve.)
- [x] **T2** Wire the FUNCATTN-tensor arm: run the triad on
  `spectral_pre_rotate`'s calibrated eigenbasis vs a random basis at matched
  param budget — closes the deferred eval at
  `katgpt-attn/src/funcattn_compose/spectral_pre_rotate.rs:29-31` on REAL
  in-tree tensors (the POC closed it at protocol level only).
  (Bench 766: POSITIVE — eigen-aligned 0.802 vs random 0.354 at k=2, and
  0.802 > full 0.656: the projection DENOISES; residual ≈ chance.)
- [-] **T3** Real-bank affinity run: capture (layer, activation, label) banks
  from a real model run (riir-ai `latent_steering_bridge` CollectingHook or
  riir-train fixture pipeline; the models: gemma-2-2b / MiniCPM5-1B), sweep
  layer affinity per behavior label, and re-pin `FutureBehaviorProbe` layer
  params from measurement if a peak emerges (flat curve ⇒ hand-picked layer
  is fine — a legitimate negative close). DEFERRED: cross-repo run with
  active sibling lanes; the promoted `affinity_sweep` is the ready
  instrument when a capture lane is free.
- [x] **T4** Record verdicts in R557; GOAT gate any promoted surface
  (feature flag + bench per the house rule). (Bench 766; R557 addendum
  delta; `subspace_intervention` stays OPT-IN — no default consumer yet.)

## Notes

- The POC's honest physics findings carry over as design constraints: the
  discriminator is the aligned-vs-random CONTRAST (random retains ≈k/D SNR at
  k=rank — it does not collapse to chance); span-stability, not
  direction-stability, is the freeze-policy axis in weak-signal regimes.
