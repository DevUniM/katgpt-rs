# Issue 802: TSD modelless residue — commitment-gap calibration tables + JSD kernel + stability features

**Status:** Open — items 2/3/5 DONE (2026-09-16, `f23b2d81b` + this commit); items 1/4 remain (each its own arc, both need the riir-poc decode rig)
**Date:** 2026-09-16
**Source:** [katgpt-rs/.research/561_TSD_Temporal_Self_Distillation.md](../.research/561_TSD_Temporal_Self_Distillation.md) (arXiv:2609.15177, Temporal Self-Distillation)
**Sibling:** riir-train Plan 409 (the model-based track; shares the measurement harness)

## Why

TSD's training loss is literally `E[V·JSD₂(p_t(ℓ), p_{t_commit}(ℓ))]` — the early-vs-commitment distribution gap. TSD shrinks that gap with gradient descent; **the gap itself is offline-measurable with zero training**, and everything measured can gate decoding.

The raw runtime gate (argmax-persistence ∧ inter-step-JSD unmasking) is **published prior art — LESS, arXiv:2606.16908** (training-free joint stability sampling, 72.1% reverse-step reduction) — do NOT file the class as novel. What LESS does NOT ship, and what this issue claims as novelty-TBD:

1. **Commitment-gap calibration tables.** Run vanilla decode over a calibration corpus; record `JSD₂(p_t(ℓ), p_{t_commit}(ℓ))` bucketed by (task class, t, t_commit−t); invert the measured conditional `P(z_t = z_{t_commit} | gate fires) ≥ p*` into gate thresholds with **stated precision**; BLAKE3-commit the table (freeze/thaw discipline). LESS uses hand-set fixed thresholds; no published commitment-gap-calibrated threshold selection surfaced in the panel search — **coverage pass required before any novelty claim**.
2. **NaN-safe bounded top-K JSD kernel** (katgpt-core, public infra): `JSD = H(M) − ½H(P) − ½H(Q)` over renormalized top-K vectors; disjoint supports → exactly ln 2, never NaN, never +∞ (KL over top-K zero-padded vectors is +∞ and NaNs poison gates). Known-answer gates + SIMD throughput bench. Prerequisite for (1) and for (4).
3. **Stability features for `DiffusionSampler`** (Plan 089 T6 predictor): `SamplerFeatures` today is single-step only (top1_prob, margin, top3_mass, entropy, step_norm, pos_norm — signal-diff verified). Add `stable_age: u8` (saturating counter: +1 iff argmax unchanged ∧ top1_prob ≥ τ_min, reset otherwise) + inter-step top-K drift. Trained-predictor fusion over stability features ≠ LESS's fixed rule (the surviving delta). **DONE 2026-09-16:** `StabilityTracker` (per-position, fixed-size state, zero-alloc) with `observe(idx, masses, top1_prob, tau_min, remasked) -> (u8, f32)`; `SamplerFeatures` gains `stable_age`/`topk_drift` (defaults 0 — back-compat; all literals use `..Default::default()`); `from_logits_into(.., Some(&mut [u32; 3]))` emits the top-3 indices from the EXISTING branchless tier shifts (masses bitwise unchanged — signal-diff pinned by test; first-index-wins on exp ties); drift = `jsd_topk_sets` (the kernel's new sets-form — same restricted-JSD law, disjoint → bitwise ln 2); `to_array_with_stability()` = the 8-feature fusion-predictor input, `to_array()` stays 6 (checkpoint contract). katgpt-forward `tri_mode` now implies `katgpt-core/jsd_topk`. 24/24 diffusion_sampler tests. Live-loop wiring (the decode loop instantiating per-position trackers) lands with (4) — it is (4)'s counter source.
4. **Commit-horizon difficulty map → verify-budget reallocation.** `horizon(ℓ) = t_commit(ℓ) − t_first_stable(ℓ)` from the free counters; tri_mode's AR-verify rejection labels are free AUC labels (G2 offline). Reallocate verify budget to high-horizon positions; graded tri_mode verdicts via the (2) kernel (accept / accept-with-drift / reject) instead of binary prefix-match. **OPEN — needs the riir-poc decode rig; the (3) counters are its measurement source.**
5. **Boundary laws (correctness conditions, ship with 3):** arm counters only above a probability mass floor (near-fully-masked argmax is noise); reset stability state on any remask (TSD's unique-commit-time assumption breaks under remasking); stride-s measurement cadence gated empirically (TSD's training-time subsampling does not prove the measurement analog). **DONE 2026-09-16 — all three enforced/tested in `StabilityTracker`:** mass floor disarms WITHOUT adopting the noisy set (next armed step compares against the last ARMED step; NaN top1_prob disarms — spelled out, not a negated comparison); remask resets to first-observation semantics; cadence documented as caller policy. Measured domain note: fast_exp returns exactly 0.0 below −87.3 — a >87.3-logit gap to a dominant mask token underflows every non-mask exp, hits the pre-existing degenerate branch (default features + [0;3] emit), and disarms coherently (pinned by test).

## POC shape

`riir-ai/crates/riir-poc/` defend-wrong rig: micro D2F model, measure the gap distribution offline, build the table, then head-to-head at matched NFE — (a) fixed threshold λ (baseline), (b) LESS-style fixed joint rule (the published class), (c) calibrated thresholds from the table. Verdict: (c) must beat (b) on frontier quality at matched NFE or the calibration residue is dead. Honest cost note: best-of-n verifier-weighted selection is a quality lever paid in n× NFE — never quote it as acceleration.

## Refusals

- Do not claim the stability-gate class as novel (LESS owns it — auditable discard in note 561 §2.2).
- Do not claim quality parity with TSD's trained gap-closing from architectural evidence alone (§3.6: the PoC above is the only admissible quality evidence).
- Naive two-pass commitment-context rehearsal is refuted (reinstates the +NFE cost TSD removes; S2D2 owns the class).
