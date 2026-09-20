# Plan 602: Decode-Order AR-ness Instrument + Anchor Scoring for the DLM Lane

**Status:** Active — Phase 1 LANDED 2026-09-20 (T1.1+T1.2+T1.3); Phase 2 PARTIAL — T2.1 LANDED 2026-09-20, T2.2+T2.3 pending; Phase 3 pending
**Date:** 2026-09-20
**Research:** [katgpt-rs/.research/575_dQwen3.5_Hybrid_Attention_DLM.md](../.research/575_dQwen3.5_Hybrid_Attention_DLM.md)
**Source paper:** [arXiv:2609.20751](https://arxiv.org/abs/2609.20751) — dQwen3.5: Hybrid-Attention Diffusion Language Models
**Target:** `crates/katgpt-core/src/dllm/arness.rs` + `crates/katgpt-core/src/anchor_score.rs` (new) · `src/speculative/d2f.rs` + `src/benchmark/diffusion.rs` (integration) · `ugc_schedule.rs` (anchor view) · Cargo feature `decode_order_metrics`
**Related:** riir-train Plan 414 (the training half — this plan is the measurement half)

---

## Goal

Ship the paper's decode-order instruments modellessly over signals the workspace already emits: local/global AR-ness (ALR/AGR) statistics over any decode trajectory π, an offline anchor scorer, and a gap-predictor that chooses d2f block size / SetDLM `w` from measured order statistics — with a capability-retention floor as the promotion gate. GOAT gate: **G3 — predictor-chosen (w, block size) matches or beats fixed settings at matched NFE on the existing diffusion bench**, giving Plans 379–384's w=0.5 NLL win a measured mechanism.

## Phase 1 — Metrics core (CORE)

### Tasks

- [x] **T1.1** `katgpt-core` new module `dllm/arness.rs` behind feature `decode_order_metrics`: `local_ar_ness(&[u32]) -> f32` (ALR — adjacent-position order fraction) + `global_ar_ness(&[u32]) -> f32` (AGR — all-pairs concordance) + a windowed O(L·W) AGR variant for streaming canvases. Pure fns, zero-alloc, fixed-size scratch.
      **LANDED 2026-09-20**: ties-count-discordant contract (parallel unmask is the non-AR behavior — deliberate Kendall-tau-b divergence, documented); `UNMASKED_NEVER = u32::MAX` sentinel with pair-exclusion semantics; degenerate input → NaN (never a silent 0.5); windowed variant via incremental slide (O(L·W), no scratch needed — the "fixed-size scratch" constraint is satisfied trivially; pinned identities `w=2 ≡ ALR`, `w≥L ≡ AGR`).
- [x] **T1.2** Known-answer tests: identity π → (1.0, 1.0); reversed → (0.0, 0.0); seeded uniform-random π → E ≈ 0.5 on both; block-swap pattern → hand-computed values (the paper's block-decoding regime: AGR → ~0.99, ARL ~0.7).
      **LANDED 2026-09-20**: 13 tests — identity/reversed/degenerate-NaN/two-element/ties/`block_swap_hand_computed` (6/7, 3/7)/`parallel_block_decode_is_anti_ar` (0, 0)/`random_permutation_is_near_half` (seeded xorshift Fisher–Yates @ L=1024, 6σ band)/sentinel-exclusion/windowed≡global @ full width/windowed≡ALR @ w=2/windowed mid-width hand-computed (2/3)/windowed skips all-sentinel windows.
- [x] **T1.3** π-logging: d2f block decode (`src/speculative/d2f.rs`) and SetDLM decode paths emit per-position unmask step π into the bench harness (small logging change behind the same feature — the only new surface the panel flagged).
      **LANDED 2026-09-20**: katgpt-forward (the root d2f.rs is a re-export shim — the real loops live there). `d2f_decode_block_prompt_q_core` gained `pi_out: Option<&mut [u32]>` (the Issue-587 q_out posture — commit-time capture, sentinel end-fill, unconditional param so ONE code path compiles in both feature states) surfaced via cfg-gated `d2f_decode_block_with_unmask_steps -> (D2fBlockResult, Vec<u32>)`; `SetDiffusionResult` gained cfg-gated `unmask_steps` (pass index at commit) + `local_ar_ness()`/`global_ar_ness()` readouts. 4 emission tests: block-causal strong signal → π=[0,0,1,1] exact + ALR 1/3 + AGR 2/3; never-committed → all-sentinel + NaN metrics; partial-commit bounds; d2f τ=0 → fully-parallel π=[0,0,0,0] (anti-AR by tie contract) + τ=1.1 → all-sentinel. Validation: core 2076/2063 (on/off), forward 131/150/170 (default/dllm+dom/sd+dom), clippy -D warnings clean at every state, docs gate 33/33 (README feature counts 623→624 at 5 claim sites + opt-in catalog §118).

## Phase 2 — Anchor scoring + schedule integration

### Tasks

- [x] **T2.1** Offline anchor scorer `anchor_score.rs`: first-unmask-in-block frequency + masked-position entropy from existing decode logs; outputs a per-position anchor score (paper §5 sparse anchor set analog). GOAT arm: planted-anchor fixture — a uniquely-determining token must rank #1.
      **LANDED 2026-09-20**: `crates/katgpt-core/src/anchor_score.rs` (root-level per the plan target, same `decode_order_metrics` feature). Inputs are the logs Phase-1/T-587 already emit: π (T1.3 `unmask_steps`) for `first_unmask_frequencies` (ties at the earliest step ALL count — joint anchors; all-sentinel blocks contribute nothing) + the Issue-587 q rows (row-major `[positions × vocab]`) for `masked_entropies` (nats, 0·ln0=0). `anchor_scores` = 0.5·freq_norm + 0.5·(1−ent_norm), min-max per component, degenerate range → 0.5 (no discrimination, never a fake 0/1). GOAT arm `planted_anchor_ranks_first` GREEN (point-mass q + strictly-earliest π → score 1.0 at the anchor, 0.0 elsewhere, rank #1) + 7 contract tests (tie counting, sentinel blocks, empty-inputs, degenerate-half, uniform-flat). 8/8; core 2084/2063 on/off; clippy --all-targets clean.
- [ ] **T2.2** UGC anchor view: expose the certified-set spine of `ugc_schedule.rs` as the sparse anchor set A (view + accessor, zero new math). GOAT arm: factorization-identity test on synthetic q — certified spine as A, remainder as conditional chain.
      *(Scope note for the next session: Research 575 line 21 names the mapping — "the certified high-confidence masks: the certified set is the spine, the rest decodes as the conditional chain". The view needs a read of `ugc_schedule.rs`'s `UgcBlockPlan`/`reveal_grid_from_plan`/`bernoulli_unmask_with_grid` to pick the exact certified-set surface; the factorization-identity arm pins `q(x) = q(x_A)·Π_{i∉A} q(x_i|·)` on a synthetic joint.)*
- [ ] **T2.3** Optional schedule variants, promote-only-on-G3: confidence-threshold τ unmasking beside `PositionOffsetSchedule::probability_order/uniform_order` in `set_diffusion_schedule.rs`; 1/λ_t-shaped unmask-slot allocation (spend more slots on hard early steps). Both feature-gated; demote silently if G3 fails.

## Phase 3 — Bench + GOAT gate

### Tasks

- [ ] **T3.1** Integrate the ALR/AGR cross-tab into `src/benchmark/diffusion.rs`: w-sweep × order statistics — the measured explanation axis for the Plans 379–384 SW-SetDLM w=0.5 win (0.71 NLL).
- [ ] **T3.2** Gap-predictor: from (ALR, AGR, per-block order cost) choose block size + w; **G3** = predictor-chosen ≥ fixed settings at matched NFE (no-regression floor, improvement target) on the existing bench models.
- [ ] **T3.3** Capability-retention floor **G0**: any promoted default holds `score_after / score_before ≥ 0.95` on the pinned eval suite (the paper's LR lesson — loss is not the gate).
- [ ] **T3.4** Bench doc in `.benchmarks/` + verdict; promote to default or demote the loser per GOAT rule. Feed the instrument to riir-train Plan 414 T1.3 (decode-order readout on adapted-model trajectories).
