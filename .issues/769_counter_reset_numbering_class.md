# Issue 769: teach the numbering drift sweep the COUNTER-RESET class (backward .highwater moves are number-reuse-shaped)

**Status:** OPEN — filed from Issue 768's T3 measurement (HISTORY 2026-09-13); no code touched yet.
**Origin:** `highwater_contiguity_audit.py`'s first workspace run measured **31 counter resets** (committed `.highwater` transitions where the value moved BACKWARD) alongside 332 gaps over 73 counters — katgpt-rs Bench `564→204`/`564→205` (two lineages), katgpt-rs Issue `577→25`, riir-train Issue `517→511` + `519→512`, riir-train Bench ×8, riir-chain Issue ×4, seal-game-editor Issue `141→137` + Plan `108→107`, riir-shader Issue `11→9`, and single-step resets in riir-ai/riir-clippy. seal-game-editor's worktree counters also sit BELOW their committed history max (150 < 152, 191 < 194).

## Why it matters

A gap only SKIPS numbers (never allocated — no collision). A RESET is worse: after `517→511`, the numbers 512..517 can be allocated AGAIN — the never-reuse rule broken by construction, the `.issues/121` collision class reborn at counter granularity. Each reset is either (a) a genuine double-allocation waiting to bite, or (b) a merge artifact where two lineages bumped independently and the loser's file won — and the sweep cannot tell them apart without per-repo archaeology, which is exactly what a FINDING row is for.

## Tasks

- [ ] T1 — port `walk_transitions()` + the reset detector from `highwater_contiguity_audit.py` into `numbering_drift_sweep.py` as a per-repo check class (the audit stays report-only; the sweep gets the verdict + a pinned ceiling per repo derived from the first measured run).
- [ ] T2 — first run + adjudication: for each reset, `git log` the commits around the transition to classify double-allocation vs merge artifact; record the verdicts in the landing note (the precedent: `citation_drift_sweep.py`'s hand-adjudicated CROSS rows, Issue 751 T1).
- [ ] T3 — the seal-game-editor worktree-below-history shape (counter UN-bumped in the worktree) gets its own row class; that repo is read-only to workspace agents — its rows REPORT to the owner, never auto-repair.

## Non-goals

- The GAP class (332 findings) is deliberately NOT swept: a skipped number never collides with anything, and a gap ceiling would red on every legitimate rebaseline (riir-neuron-db's deliberate 33→589). Report-only in the audit, forever.
