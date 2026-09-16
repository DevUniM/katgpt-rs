# Plan 600 — FlashAR Confidence-Commit Upgrade: promote the DBTM κ∪floor anchor rule behind `flashar_anchor` (Issue 811 PoC winner)

**Status:** PLANNED — no code landed yet; the PoC evidence lives in [Issue 811](../.issues/811_confidence_commit_anchor_rule.md) (arm table + termination property, this repo `develop`).

## Why (measured, one paragraph)

Issue 811's three-arm head-to-head on the trained mini-D2F (24 sequences, block=8, paired seeds, harness parity-pinned byte-identical to the production decode): the confidence rule extracts MORE anchors from the SAME Round-1 AR walk than the stride rule (8.0 vs 4.0 at κ=0.5), the DBTM floor empties the block 3.1–4.7× faster than the matched-threshold stride arm at κ ∈ {0.9, 0.99} (1.04–1.50 vs 3.25–7.00 fill steps at k=8; 134–194 µs vs 424–915 µs), quality is at parity everywhere (≤1.2σ on 192 samples; the best-quality cell is a confidence arm), and termination-within-k is property-proven at every (κ, k) cell including κ=0.999. The all-mask baseline (0.031–0.062 accuracy) confirms the anchor round carries the signal — selection rule quality is about how much of it survives the walk.

## Tasks

- [x] T1 PoC harness (three arms, one trained mini-D2F, paired rng) — Issue 811, shipped in the PoC commit
- [x] T2 arm table at NFE {1,2,4,8} × κ {0.5,0.9,0.99} — recorded in Issue 811
- [x] T3-partial pure math: `commit_time_star` (ignition_schedule) + `probability_order` (set_diffusion_schedule)
- [-] T3 Plan-381 sweep-bench arm (t\*-gated probability-ordered reveal vs uniform/ar/mdlm) — DEFERRED: `train_mini_set_causal`/`evaluate_set_causal_nelbo` take `&PositionOffsetSchedule` only; a probability-ordered arm needs a custom-order seam in the set-causal train/eval path. File the seam issue when this plan opens its T6.
- [x] T4 verdict — PASS on the steps/termination axis at quality parity (the honest scope: quality is anchor-dominated on the toy and does not separate; no regression measured)
- [-] T5 UGC cross-check (confidence-greedy reveal KL vs the UGC certificate, Caveat #1) — DEFERRED: load-bearing only when the upgrade claims a QUALITY gain on real text; the PoC pass is on steps/termination at quality parity. Fold the KL measurement into this plan's G1 gate list before any default-promotion claim.
- [ ] T6 `ConfidenceAnchorConfig` in `katgpt-forward::flashar_anchor`: `{ kappa: f32, floor: bool }` beside the existing `AnchorConfig` (stride stays the DEFAULT — demote-on-loss rule); selector fn consumed by a new `anchor_then_fill_with` entry point, zero changes to the existing signature
- [ ] T7 Round-1 walk change: record (argmax, max-softmax q) per position inside `predict_anchors` (out-param, gated by the config) — the walk cost is unchanged; sampled-context propagation stays byte-identical (parity test pins this)
- [ ] T8 Real-text GOAT gates before any default promotion: G1 quality on a non-saturated corpus (the toy is anchor-dominated — accuracy does not separate arms; use the eval set from the Plan-381/116 lane), G2 steps-to-converge + wall per block at matched quality, G3 no-regression on the strided incumbent (byte-identical with the config off), G4 alloc-free fill path (the candidate Vec is pre-allocated + reused)
- [ ] T9 UGC KL cross-check (Issue 811 T5) measured on the same corpus as T8-G1
- [ ] T10 Docs: `.docs/` entry + AGENTS feature-list line for the new config knob (opt-in; no default change without T8+T9 green)

## Acceptance

Production seam lands opt-in under the existing `flashar_anchor` feature with the strided incumbent untouched (G3 byte-identical); promotion to default requires T8 all-green + T9 on real text — never on this toy's numbers alone.
