# Issue 811: Confidence-Commit Anchor Rule (DBTM κ ∪ floor) + t\* Schedule for the D2F Reveal Lane

**Status:** Open — PoC-first (defend-wrong §3.6: the quality claim requires a head-to-head on a trained mini-D2F; architectural reasoning is not sufficient)
**Date:** 2026-09-16
**Research:** [`.research/563_DBTM_Discrete_Beckmann_One_Step_Language.md`](../.research/563_DBTM_Discrete_Beckmann_One_Step_Language.md)
**Source:** Tang & Wang, arXiv:2609.15903 §5.1 (Eq 26 commit rule), §4.3 (Thm 4.1 t\*), Table 9/11/12
**Consumers:** `crates/katgpt-forward/src/flashar_anchor.rs` (`anchor_then_fill`), `katgpt_core::set_diffusion_schedule` (`PositionOffsetSchedule`), the Plan-381 schedule-sweep bench lane

## Context

DBTM's inference scheme commits tokens by **confidence/quality with a floor** — per round r of budget k:
`Δ𝒞_r = {ℓ : q_ℓ ≥ κ} ∪ top_{n_r}(q)`, `n_r = ⌈|R_r|/(k−r+1)⌉` — guaranteeing termination in exactly k forward calls, then renoises the rest and reapplies the same map (refinement, not ODE integration; their Table 9: one map application beats 64-step Euler integration of the learned field).

Two documented gaps make this actionable here:

1. **UGC's own Caveat #1** (`katgpt-core/src/ugc_schedule.rs`): its KL certificate covers *random-order* Bernoulli/fixed-cardinality reveal, "**NOT confidence-threshold (greedy per-token) reveal**". The confidence-greedy cell is uncovered — DBTM's rule + floor is exactly that cell, with the paper's Table 11 evidence that κ-adaptive commit beats fixed-cardinality at NFE ≥ 4.
2. **FlashAR `anchor_then_fill` selects anchors by STRIDE** (positional, fixed) — content-blind. The confidence signal already ships: DiffusionSampler (Plan 116) computes per-position confidence from the denoiser's own output (AUC 0.76–0.78 on micro-D2F).

Secondary arm — the **t\* commitment law** `t* = 1 − (1 + σ·√(2 ln V))^(−1/a)` (REM-derived; mode-collapse boundary for early supervision, safe-anchor boundary after): a 3-parameter closed form in the `IgnitionSchedule` timing-law family (Bench 666), consumable as a `PositionOffsetSchedule` variant (probability-ordered / t\*-gated reveal) where UGC must *estimate* its grid from data. Their Table 12: anchoring before t\* collapses modes, after t\* slows convergence — a principled constant where the lane currently sweeps by hand.

## PoC scope (T1–T3 before any feature lands)

Three competitors on the SAME trained mini-D2F (the `train_mini_dllm` pattern harness FlashAR's own tests use):

1. **strided anchor** ( incumbent — `AnchorConfig` stride)
2. **confidence-commit** (q = max-softmax per position, threshold κ, NO floor)
3. **confidence-commit + floor** (κ ∪ ⌈|R|/(k−r+1)⌉ — the DBTM rule)

Metrics: exact-pattern accuracy / generative quality at NFE ∈ {1, 2, 4, 8}; wall-clock; termination-within-k proof (property test for arm 3); renoise-vs-hold ablation for committed-context treatment.

## Tasks

- [ ] T1 PoC harness: extend the flashar training-coupled test rig to run all three arms on one trained mini-D2F checkpoint (seeded, `CARGO_TARGET_DIR=/tmp/...`, clean up)
- [ ] T2 Run the arm table at NFE {1,2,4,8} × κ {0.5, 0.9, 0.99}; record verdict table in this issue
- [ ] T3 t\* schedule arm: `PositionOffsetSchedule` probability-ordered variant vs `uniform/ar/mdlm` on the Plan-381 sweep bench (mini scale); t\* recorded as the derived anchor constant
- [ ] T4 Verdict: if commit+floor beats strided at ≥2 NFE points without quality regression → plan the `flashar_anchor` upgrade behind its existing feature flag (demote-on-loss rule applies to the strided default); if not → record the negative here and close
- [ ] T5 If T4 passes: UGC cross-check — does the confidence-greedy reveal KL stay within the UGC certificate's constant-factor class on the toy ensemble (their Caveat #1 question, measured not asserted)

## Acceptance

- Measured table committed here (or a bench file ref) before any promotion; property test for the k-round termination guarantee; honest negative recorded if arm 3 ≤ arm 1.
