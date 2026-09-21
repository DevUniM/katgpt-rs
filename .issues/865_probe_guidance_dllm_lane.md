# Issue 865: Probe guidance for the dLLM decode lane (unblock Research 68's shelved self_guidance)

**Status:** Open — T1 LANDED 2026-09-21 (mechanism + seam + G1); T2 inference half LANDED 2026-09-21 (artifact wire + consumer + tap contract); T2 training half / T3 / T4 / T5 open. Distillation at [Research 578](../.research/578_Probe_Guidance_Language_Flow.md) (arXiv:2609.19356); catalog row `.docs/09_feature_catalog/opt_in_features.md` §120.

## Substrate check (substrate-first skill, 2026-09-21)
- Searched: `self_guidance` / `probe_guidance` / `autoguidance` / `classifier-free` / `contrastive decoding` / `dola` / `tuned_lens` / `logits_guided` across `crates/**/*.rs` — zero guidance/CFG substrate exists (Research 68 §7.2 documented the affine form, no code).
- Found: `LatentDynamicsMLP` — the T2 probe CLASS — already ships in `katgpt-speculative/src/belief_drafter.rs` (Plan 217); T2 trains/loads an artifact of that class rather than inventing one. D2F context already carries `xr`/`x_norm` per-position residuals — `ProbeCtx` exposes them as field slices (disjoint-borrow contract), so T1 needs no forward-kernel tap changes; early-layer tap points are T2's to add.
- Decision: BUILD NEW mechanism in `katgpt-forward` (the issue IS the filed record); consume `LatentDynamicsMLP` for T2. Architectural rules checked: modelless-first (probe = frozen artifact via freeze/thaw, no runtime training — consistent); latent-space decode knob, not synced, no bridge concerns; zero-alloc hot path (flat buffers only).
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

- [x] **T1** `probe_guidance` feature (katgpt-forward, opt-in): affine combine at the D2F logits step in `d2f_decode_block_prompt_q_core` — `logits' = logits + (λ−1)·(logits − probe_logits)`, `λ: f32` config knob (λ=1 must be bit-identical to unguided — G1), zero-alloc combine, no guidance when the probe is absent. **LANDED 2026-09-21**: `WeakLogitProbe: Send + Sync` + `ProbeCtx` + `D2fContext::{set_guidance, clear_guidance}` + `D2fPipeline::set_guidance` + zero-alloc 8-wide chunked combine in `crates/katgpt-forward/src/d2f_context.rs`; call site after the multistep blend, before sampling. 9 tests (G1 λ=1 poison-probe bit-identity end-to-end + kernel formula at λ∈{0,0.5} + no-op arms + probe==logits fixed point + override-divergence + pipeline wiring); clippy clean at default/probe_guidance/all-features. Design notes: λ lives on `D2fContext` (not `D2fDecodeConfig` — 52 literal constructions; `set_guidance` is the zero-churn seam); the feature implies `dllm` (the combine lives in the dllm-gated d2f module — a bare flag compiles to nothing, the green-zero trap); `Send + Sync` supertrait keeps `D2fContext` auto-Send+Sync for the tri_mode verifiers (caught by `--all-features`).
- [-] **T2** Weak-side probe artifact: `LatentDynamicsMLP`-class probe reading an early-layer hidden state, trained against the denoise target on a frozen trunk (stop-grad). Training rides the riir-train `nextlat_*` lane pattern (~20k steps, frozen trunk); the artifact loads via the freeze/thaw wire (BLAKE3-checked), consistent with the modelless consumption rule.
  - [x] **T2a (inference half, LANDED 2026-09-21)** — the artifact wire + consumer: `katgpt-speculative::probe_artifact` (new opt-in feature `probe_artifact` = `["belief_drafter"]`, the blake3 dep rides it) — `ProbeArtifact` = connector `LatentDynamicsMLP` (class reused, now `Clone`) + shared trunk `lm_head` `[vocab*n_embd]` + `tap_layer` + monotonic `version` + BLAKE3 commitment over every payload byte (wire magic `NLPA` v1, LE); `from_parts` validates shape, `from_bytes`/`load_from_bin` re-verify the commitment BEFORE returning weights (`CommitmentMismatch` on any tamper/truncation/trailing byte). Consumer: `katgpt_forward::weak_probe_mlp::MlpWeakProbe` (gated `probe_guidance`, which now forwards `katgpt-speculative/probe_artifact`) — per block position: tapped hidden → connector (zero `next_emb`, the training convention: block positions are mask tokens whose embeddings carry no per-position signal) → shared head → weak logits; zero-alloc (scratch/latent/zeros allocated once). Tap contract: `ProbeCtx` gained `tap: &'a [f32]` (T2's reserved extension); the single-layer D2F kernel provides ONLY the layer-0 tap (the pre-layer input residual — `tap` aliases `xr`, whose stale "final-layer" doc was fixed), and `MlpWeakProbe::new` REJECTS artifacts declaring a deeper tap (fail-loud at construction, never a decode-time misread) — deeper taps need the multi-layer kernel extension. 15 tests: 8 wire (commitment = BLAKE3(payload), byte+file roundtrip, tampered weight / tampered commitment / truncation / bad magic / bad format version / trailing byte, shape validation), 5 consumer (deeper-tap rejection names the mismatch, direct forward+matmul equivalence, block_start offset, file roundtrip output identity, purity + full-write poison), 2 end-to-end (λ=1 artifact-path bit-identity; λ=0.5 engages the weak side). Clippy clean at probe_artifact / probe_guidance / all-features / default.
  - [ ] **T2b (training half)** — the riir-train lane: frozen trunk (mini-dLLM via the katgpt-rs root dep, optional in riir-train-engine), tap layer-0 residuals over noised inputs, train the connector (hand-rolled f32 backward, the `nextlat_baseline` pattern) against the denoise target CE through the FROZEN shared head (stop-grad is structural — trunk + head never update), emit `ProbeArtifact::save_to_bin` (~20k steps target); then a GOAT-shaped acceptance row (probe trains to > trivial CE on heldout + the katgpt-rs consumer loads + guides with it). GPU scale-up (Bonsai-scale multi-layer tap) is a separate issue once the multi-layer kernel extension exists.
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
