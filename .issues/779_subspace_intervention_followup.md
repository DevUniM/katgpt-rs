# Issue 779: Subspace-intervention follow-up — lib promotion + FUNCATTN arm + real-bank affinity

**Status:** Open
**Research:** [katgpt-rs/.research/557_Subspace_Intervention_Probe_SVD_Layer_Affinity.md](../.research/557_Subspace_Intervention_Probe_SVD_Layer_Affinity.md) §"PoC Addendum" (Issue 778 resolved — protocol validated on planted ground truth)

## Context

Issue 778's POC validated the three-arm subspace-intervention protocol on a
synthetic tiered bank: affinity sweep recovers planted peaks 8/8; projection
identity exact; residual collapse 0.021; aligned-vs-random contrast 1.96× at
matched k=4. Positive arms → follow-up per the issue's outcome criteria.

## Tasks

- [ ] **T1** Promote the protocol from the test harness to
  `katgpt_core::subspace_intervention` behind an opt-in feature (house
  no-default-consumer rule): `three_arm_eval`, `affinity_sweep`, and
  `basis_similarity` as reusable functions over `thin_svd_into`; zero new
  deps; G1 identity + G4 alloc gates from the harness become unit tests.
- [ ] **T2** Wire the FUNCATTN-tensor arm: run the triad on
  `spectral_pre_rotate`'s calibrated eigenbasis vs a random basis at matched
  param budget — closes the deferred eval at
  `katgpt-attn/src/funcattn_compose/spectral_pre_rotate.rs:29-31` on REAL
  in-tree tensors (the POC closed it at protocol level only).
- [ ] **T3** Real-bank affinity run: capture (layer, activation, label) banks
  from a real model run (riir-ai `latent_steering_bridge` CollectingHook or
  riir-train fixture pipeline; the models: gemma-2-2b / MiniCPM5-1B), sweep
  layer affinity per behavior label, and re-pin `FutureBehaviorProbe` layer
  params from measurement if a peak emerges (flat curve ⇒ hand-picked layer
  is fine — a legitimate negative close).
- [ ] **T4** Record verdicts in R557; GOAT gate any promoted surface
  (feature flag + bench per the house rule).

## Notes

- The POC's honest physics findings carry over as design constraints: the
  discriminator is the aligned-vs-random CONTRAST (random retains ≈k/D SNR at
  k=rank — it does not collapse to chance); span-stability, not
  direction-stability, is the freeze-policy axis in weak-signal regimes.
