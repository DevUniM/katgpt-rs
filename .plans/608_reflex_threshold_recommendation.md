# Plan 608 — reflex Issue 009: the threshold-recommendation surface (the jimothy steal)

**Status:** IN PROGRESS 2026-09-22 — T1+T3+T4 LANDED (riir-reflex `a732bcf6a`); T2 DEFERRED on a sibling collision (`src/harness/runner.rs` holds another session's uncommitted candle-lane-removal edits — T2 lands on top of that work).

## Why

Plan 607's jimothy comparison (commit `f8c7ffb5a`) named the steal
candidate for the reflex arena: jimothy ships a TRAINED per-task cutoff
recommendation as first-class model metadata
(`metadata.thresholdRecommendation = { threshold, status, targetAccuracy }`,
`null` on thin data, "applying a cutoff is your application's choice",
"validate cutoffs in your deployment environment"). The reflex T1.5
harness hand-rolls exactly this shape per suite (30th-percentile
cal-slice fit, after the birth thresholds abstained 64–100% on
real-corpus suites) — invisible to engine consumers, recomputed
implicitly every run.

The steal is the four-part CONTRACT, never the trained method (modelless:
deterministic scans over sigmoid-gate scores — no RNG, no trained
calibrator):

1. **Recommend at fit time** — once from a labeled cal slice.
2. **Return everything at run time** — abstaining stays the consumer's
   choice.
3. **Null on thin support** — and the support is DISCLOSED
   (n / n_pass / n_abstain — the tail-support law).
4. **Validate in the deployment environment** — the posture rides the
   metadata so consumers cite it with the number.

## Tasks

- [x] **T1 — the surface** (`riir-reflex/src/engine/threshold.rs`,
  re-exported `engine::*`): `threshold_recommendation(obs, posture)` with
  `Posture::Percentile { rho }` (reproduces the harness `quantile` law
  VERBATIM — ascending `total_cmp`, `idx = floor(n·ρ)` clamped to `n-1`
  — so T2 is a byte-identical migration, not a re-fit) and
  `Posture::TargetAccuracy { target }` (jimothy's shape: the LOWEST cutoff
  meeting the target, best-achievable + `TargetUnmet` disclosed when none
  does). `None` under `THIN_SUPPORT_FLOOR = 16` — the harness's own
  measured `confs.len() < 16` fallback floor, pinned by gate.
  `recommend_fused_gate()` fits both gate axes (score + distance) under
  one posture — the T2 entry point.
- [-] **T2 — harness consumption** (byte-identical migration bar).
  DEFERRED: `src/harness/runner.rs` carries a sibling session's
  uncommitted candle-lane-removal edits in the shared reflex worktree;
  editing/staging around another agent's in-flight hunks is the collision
  the workspace rules forbid. The T1-side parity gate
  (`percentile_parity_with_the_harness_quantile_law`) holds the bar — the
  runner's inline law is replicated verbatim in the gate, so drift on
  either side reds. Resume: rebase on the sibling's landed runner, swap
  the fit block for `recommend_fused_gate` at ρ=0.30 (labels from the
  probe's picks), assert table byte-identity on the current suites.
- [x] **T3 — metadata exposure**: `FusedGateRecommendation` — serde
  camelCase `{ posture, score, distance }`, JSON `null` per axis on thin
  support (jimothy's shape, numbers only). Harness-table column +
  arena-site citation ride T2 (the table writer is the consumer).
- [x] **T4 — gates** (9, in-module `#[cfg(test)]`; a new `tests/` target
  would have needed a `required-features` row in `Cargo.toml` — a file the
  sibling session holds dirty; in-module gates compile under the same
  `modelless` feature as the module): determinism (bit-identical repeat
  fits) · thin-support null (n=15 → `None` both postures; floor pinned
  == 16) · support disclosure (sums; distinct-score ρ=0.30 →
  `n_abstain == floor(n·ρ)`; NaN rows abstain deterministically) ·
  percentile parity vs the replicated harness law (the T2 bar, T1-side) ·
  target-met picks the lowest meeting cutoff (boundary arithmetic pinned
  on a 36-row fixture) · target-unmet returns best-achievable + disclosed
  status · ties pass together (support recomputed AT the threshold, never
  from prefix arithmetic) · serde shape incl. the null arms. The
  byte-identical-tables arm lands WITH T2 (it needs the runner).

## Verification posture (the shared-worktree hazard)

riir-reflex's worktree carries a sibling session's in-flight candle-lane
edits (runner.rs, lib.rs, Cargo.toml, deleted laya files), so T1 was
verified in an ISOLATED rig: `git worktree add --detach` at reflex
`b41bc7b` + a pinned katgpt-rs worktree at `c6f767d5c` (the commit reflex
HEAD was green against — isolates the build from the sibling's dirty
kv_eviction tree too). There: `cargo clippy --all-targets -- -D warnings`
clean, `cargo test` fully green (26 lib incl. 9 new + all integration
targets). Commit `a732bcf6a` staged the three named files only.

**Re-verified 2026-09-22 21:07 +07 against the MOVED katgpt-core** (the
871-T4/T5 + 873-primitive-C landings post-`c6f767d5c` — no lane had
compiled reflex HEAD × katgpt HEAD): fresh adjacent-worktree rig, reflex
`a732bcf` × katgpt `cb32f3f40`, `CARGO_TARGET_DIR` isolated, box quiet.
`cargo clippy --all-targets -- -D warnings` clean (15.25s) · `cargo test`
green — 26 lib (incl. the 9 threshold gates) + 3+8+7+24+7 integration,
0 failed. The T1 surface carries no compat debt into T2.

## Non-goals

- No TRAINED calibration — jimothy's method is the adjacent baseline named
  for comparison, never adopted (the Plan 607 stance).
- No silent abstain at the engine boundary — contract part 2 is the point.
- Not a katgpt-rs primitive — the surface is reflex engine metadata; the
  corpus-scoring substrate it consumes stays upstream (reflex BOUNDARY.md
  domain test: decision-engine serving).

## Provenance

- jimothy README verified 2026-09-22 (nominative use; quotes are its own
  wording).
- reflex measured basis: Plan 603 T1.5 (birth thresholds abstained
  64–100% on real-corpus suites; per-suite 30th-percentile fit; the
  cal-slice self-inclusion leak fixed in the same window).
- Filed as riir-reflex `.issues/009_threshold_recommendation_surface.md`
  (`b41bc7b`); executed T1/T3/T4 at `a732bcf6a`.
