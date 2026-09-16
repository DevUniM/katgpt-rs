# Issue 813: Set-causal custom-order seam — probability-ordered / t\*-gated reveal arm

**Status:** FILED 2026-09-17 — owed seam from [Issue 811](811_confidence_commit_anchor_rule.md) T3-deferred / [Plan 600](../.plans/600_flashar_confidence_commit_upgrade.md) T3 ("file the seam issue when this plan opens its T6" — T6 LANDED 2026-09-16). Allocated as 813: first taken as 812 from the stale `.highwater`, renumbered same-commit when `scripts/numbering_gate.py` recovered the removed historical holder `812_bench_doc_audit_blindread_context_split` (the recycled-number class the gate exists for — `ls` + `.highwater` alone do not see removed allocations).
**Date:** 2026-09-17
**Blocking:** the Plan-381 sweep-bench probability-ordered arm (t\*-gated confidence-ordered reveal vs uniform/ar/mdlm)

## The gap

`train_mini_set_causal` and `evaluate_set_causal_nelbo` accept `&PositionOffsetSchedule` only. A probability-ordered arm needs to feed a per-sequence, confidence-derived reveal ORDER — not a fixed positional schedule — so the sweep bench cannot race the t\*-gated probability-ordered reveal against the uniform/ar/mdlm arms.

The pure-math half already ships (Issue 811 T3-partial): `commit_time_star(V, σ, a)` (katgpt-core `ignition_schedule`) + `probability_order(confidence)` (katgpt-core `set_diffusion_schedule`, confidence-descending / stable ties / NaN-last). The DBTM rule that generates the per-position confidence signal also ships (`select_confidence_anchors_into`, Plan 600). The missing piece is only the seam.

## The ask

1. A custom-order reveal seam in the set-causal train/eval path: either `train_mini_set_causal_with_order(..., order: &[usize], ...)` / `evaluate_set_causal_nelbo_with_order(...)`, or a `PositionOffsetSchedule::Custom(Vec<usize>)` variant — whichever keeps the existing callers byte-identical (default = the incumbent uniform schedule; the same opt-in-plus-parity discipline Plan 600 used).
2. A sweep-bench arm consuming it: t\*-gated probability-ordered reveal vs uniform/ar/mdlm on the Plan-381 lane (the deferred T3 measurement).
3. Keep it opt-in/gated; no default-path change.

## Acceptance

- Byte-identity: default-schedule callers unchanged (parity pin, the Plan 600 T6/T7 pattern).
- The sweep arm runs on the existing bench lane and records the arm table.
- `probability_order` + `commit_time_star` consumed, not re-implemented (substrate-first).

## Notes

- Plan 600 T8/T9 resolved 2026-09-17 ([Bench 600](../.benchmarks/600_flashar_confidence_commit_goat.md)): the confidence-commit rule measured green on the non-saturated pattern corpus (G1 non-inferiority, G2 2.0–3.9× steps, G4 alloc-free, T9 KL 0.996× incumbent) — promotion to default stays deferred on real-text corpus honesty. This issue is the remaining measured-gap follow-on from the same research line (Research 563 / arXiv:2609.15903 §4.3 Thm 4.1).
