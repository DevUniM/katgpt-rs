# Issue 865: Probe guidance for the dLLM decode lane (unblock Research 68's shelved self_guidance)

**Status:** Open — distillation at [Research 578](../.research/578_Probe_Guidance_Language_Flow.md) (arXiv:2609.19356); implementation not started
**Date:** 2026-09-21
**Research:** [katgpt-rs/.research/578_Probe_Guidance_Language_Flow.md](../.research/578_Probe_Guidance_Language_Flow.md)
**Cousins:** Research 68 §7.2 (the shelved `self_guidance` proposal — blocker eroded), Research 44 (ELF CFG/progressive distillation), `mls_aggregate` (Plan 104, landed)

---

## Problem

The D2F/SetDiffusion decode lane ships quality knobs (τ_conf, τ_act, denoise_steps, multistep) but **no guidance** — no way to trade diversity for quality at inference by extrapolating along a strong−weak prediction difference. Research 68 documented the exact affine form (`logits_guided = (1+w)·logits − w·intermediate_logits`) and shelved it as "needs weight training". That blocker no longer holds: (a) riir-train trains the exact probe class we need (`nextlat_*` → `LatentDynamicsMLP` on frozen hidden states), and (b) arXiv:2609.19356 shows the weak side needs only a ~2%-FLOP early-layer MLP probe, not a mid-layer LM head — and that **early layers are the right tap point** (late layers collapse the guidance direction).

## Why now (the paper's deltas)

1. Cheap-weak law: 3–7% trunk compute, ~20k steps, matched-width MLP connector, early-layer position.
2. Autoguidance mechanism: weak must come from the low-entropy region before the entropy climbout (validates correlated-dynamics requirement; relevant to weak-model/teacher checkpoint selection in riir-train).
3. Amortization loop: guidance distills into weights in <10k steps and can be re-probed iteratively (FLM distills cleanly; ELF collapses — measure, don't assume).

## Tasks

- [ ] **T1** `probe_guidance` feature (katgpt-forward, opt-in): affine combine at the D2F logits step in `d2f_decode_block_prompt_q_core` — `logits' = logits + (λ−1)·(logits − probe_logits)`, `λ: f32` config knob (λ=1 must be bit-identical to unguided — G1), zero-alloc combine, no guidance when the probe is absent.
- [ ] **T2** Weak-side probe artifact: `LatentDynamicsMLP`-class probe reading an early-layer hidden state, trained against the denoise target on a frozen trunk (stop-grad). Training rides the riir-train `nextlat_*` lane pattern (~20k steps, frozen trunk); the artifact loads via the freeze/thaw wire (BLAKE3-checked), consistent with the modelless consumption rule.
- [ ] **T3** GOAT gate: λ-sweep Pareto (quality proxy vs unigram-entropy-style diversity) on the mini-dLLM lane vs (a) unguided D2F and (b) a dropout-autoguidance arm; G1 λ=1 bit-identity, G2 quality at matched diversity, G3 no-regression at λ=1, G4 alloc-free combine. Promote to default only if a modelless gain holds (quality gate must pass modellessly per the promotion rule).
- [ ] **T4** (stretch) AR experiment arm: tuned-lens-style probe steering AR decode logits — the unpublished composition (Tuned Lens substrate × O'Brien-Lewis/DoLa consumer); baseline = DoLa-style shared-head contrast. PoC discipline (§3.6): no quality-parity claim without head-to-head.
- [ ] **T5** Record the entropy-climbout checkpoint law + the iterative probe→distill amortization loop as recipe rows for riir-train (weak-model teacher selection), cross-ref Research 578 §3.

## Acceptance

- λ=1 bit-identical to unguided decode (test).
- λ-sweep Pareto recorded in `.benchmarks/` with the box state (load class) noted.
- No regression to the default D2F path with the feature off.

## Non-goals

- No new training pipeline in katgpt-rs (probe training lives riir-train-side, riding `nextlat_*`).
- No CFG/self-conditioning port (ELF-specific wiring).
- No league tg128/pp claims (quality knob, not a speed knob).
