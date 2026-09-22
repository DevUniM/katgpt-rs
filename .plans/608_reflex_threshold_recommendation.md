# Plan 608 — reflex Issue 009: the threshold-recommendation surface (the jimothy steal)

**Status:** COMPLETE 2026-09-22 — T1–T4 ALL LANDED. T1+T3+T4 at riir-reflex `a732bcf6a`; T2 at riir-reflex `0dc2397` (rebased clean on the sibling's `e4bf657`, pushed) — the byte-identical migration held: pure-swap diff over 14 suites NORMALIZED-IDENTICAL (noise set {latency, seconds, date, git_sha} validated by double-baseline), disclosure measured ADDITIVE-ONLY (14 new `threshold_recommendation` keys, zero changed values), 3 in-module migration gates added. Issue 009 CLOSED; site-side rendering rides the reflex-site repo.

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
- [x] **T2 — harness consumption** LANDED at riir-reflex `0dc2397` (2026-09-22).
  The collision was cleared WITHOUT touching the sibling's in-flight worktree:
  the migration ran in an isolated `git worktree` at `bf8ebe5` (detached;
  the sibling's uncommitted fmt/families WIP untouched; commit rebased onto
  their landed `e4bf657` and pushed `HEAD:develop`). Evidence: baseline
  double-run fixed the noise set {latency_p50/p99, seconds, date_utc,
  git_sha — the runner reads the cwd's HEAD, which a sibling commit moved
  mid-run}; pure-swap run NORMALIZED-IDENTICAL on results.json + TABLES.md
  identical beyond the run-line sha over all 14 suites (`--skip-laya` — the
  fit block lives in `run_modelless` only, the laya lane shares nothing);
  disclosure step measured ADDITIVE-ONLY by recursive diff (exactly 14 new
  `threshold_recommendation` keys, zero changed values). The runner's
  `quantile` fn is deleted — its law frozen as the oracle in 3 in-module
  gates (`threshold_migration_tests`); `LaneResult.threshold_recommendation`
  + the TABLES.md `gate-fit (ρ=.30)` column land the T3 tail. Probe labels
  use `slot.pick` with eval_engine's Noul [no,yes] wire flip mirrored
  (the percentile posture selects on score only — labels feed the
  accuracy disclosure, never the threshold).
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
