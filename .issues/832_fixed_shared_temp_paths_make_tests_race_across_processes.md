# Issue 832: 25 tests wrote to FIXED `env::temp_dir()` paths, so any two concurrent runs truncate each other — and the matrix's TRANSIENT bucket was where that hid

**Status:** T1 (the 25 sites), T2 (the gate), T3 (the cross-repo sweep) and
T4 (the other spellings) are all **DONE 2026-09-18**. T5 — the 98 sibling
sites the T3 measurement found — is open and is each repo owner's to
adjudicate.
**Found by:** `scripts/x86_64_execution_matrix.sh`, 2026-09-18. Cell 5
(`katgpt-rs --lib --all-features`) went red and cell 7 (`katgpt-types`) reported
two failures the confirm step then filed as TRANSIENT.

## The defect

A test that writes to `std::env::temp_dir().join("fixed_name.bin")` is not safe
against **another process running the same test**. This workspace runs 5+
concurrent agent sessions against shared worktrees (AGENTS.md § *Before
committing in a shared worktree*), and its own instruments overlap by design:
`test_gate`, `full_gate`, `x86_64_execution_matrix` and any hand-run `cargo
test` can all be in flight at once, each with its own target dir but all sharing
**one** system temp directory.

Writer semantics do the rest: `create` truncates. Process A writes and flushes,
process B truncates the same path, A reads back — and gets zero bytes.

## The evidence, and it is not circumstantial

**(a) Reproduced on demand.** `pruners::bomber::replay::tests::writer_writes_and_counts_samples`
(`src/pruners/bomber/replay.rs:414`, path `bomber_replay_test/test_replay.bin`),
run as two concurrent copies of the matrix's own debug binary, 12 pairs:

```
1 failure in 24 runs — panicked at src\pruners\bomber\replay.rs:458:9:
  left: 0    right: 5
```

Byte-identical to the matrix's cell-5 failure. Alone, it passes every time.

**(b) Five tests failing at once with the same message** — the matrix's
`.cell_katgpt-types.log`, third run:

```
tests_types::test_domain_latent_save_load_roundtrip          "File too small for gpart header"
tests_types::test_gpart_save_load_roundtrip                  "File too small for gpart header"
tests_types::test_lora_load_first_returns_only_first_adapter "File too small for lora header"
tests_types::test_lora_load_multi_adapter_returns_all        "File too small for lora header"
tests_types::test_lora_load_single_adapter_returns_one_element_vec  "File too small for lora header"
test result: FAILED. 258 passed; 5 failed
```

*"File too small for header"* is a read of a truncated file. The five tests use
five **different** filenames, so this is not an intra-binary collision — it is
another `katgpt-types` test binary truncating all five. All five are in the set
repaired below.

## ⛔ The part worth carrying forward: TRANSIENT is not a diagnosis

The matrix's confirm step did its job — *"a load-sensitive bar passes the second
time and a real failure does not"* — and filed
`lora::tests::weight_epoch_stable_for_identical_adapters` as **TRANSIENT,
failed in the cell, PASSED alone**. That is a true statement and the wrong
conclusion. This class passes alone **by construction**: there is no second
process. "Not reproducible alone" separates a load-sensitive *bar* from a real
regression, and does nothing at all to a *concurrency* defect, which is a
permanent property of the test rather than of the box.

⚠ **A caveat this issue owes its own evidence rule:** the lora epoch test was
NOT reproduced by a 3-way concurrent stress (0 failures in 45 runs, both pre-
and post-fix). Its payload is identical on every run, so a colliding write
usually lands the same bytes — the window is real but narrow. It is repaired
with the rest because it is the same shape, not because this issue measured it.
(a) and (b) are the measured evidence; do not read them onto that row.

## T1 — what was repaired (2026-09-18)

25 sites across 8 files, `join("name")` → `join(format!("name_{}", std::process::id()))`,
which is the pattern this repo **already** uses in
`katgpt-transformer/src/contiguous.rs`, `katgpt-core/src/content_store/fetcher.rs`,
and the three `katgpt-pruners` sites — so the fix is the existing house rule
applied to the sites that missed it, not a new abstraction. 13 already-unique
sites were left alone.

| file | sites |
|---|---|
| `crates/katgpt-types/src/tests_types.rs` | 11 |
| `crates/katgpt-types/src/lora.rs` | 4 |
| `crates/katgpt-transformer/src/mtp.rs` | 3 |
| `crates/katgpt-speculative/src/domino_lora.rs` | 2 |
| `tests/bench_228_vocab_channel_goat.rs` | 2 |
| `crates/katgpt-percepta/src/compile.rs` | 1 |
| `crates/katgpt-speculative/src/rt_turbo/projection.rs` | 1 |
| `src/pruners/bomber/replay.rs` | 1 |

Verification: the bomber reproduction above no longer fires; `katgpt-types`
141 lib tests green; 45 concurrent runs of the lora epoch test clean.

⚠ **Two `examples/` sites are deliberately NOT repaired** —
`examples/collapse_aware_thinking_demo.rs:195` (`collapse_aware_demo`) and
`examples/gpart_adapter_demo.rs:55` (`gpart_adapter_demo.bin`). A demo's temp
path is meant to be findable by a human afterwards, and no gate runs two
examples concurrently. They are named here so a future census reads this line
instead of re-deriving the question.

⚠ **`cargo fmt -p <crate>` is NOT the way to format this change.** It reformats
~1300 unrelated lines: of the 8 touched files only 6 are rustfmt-clean at HEAD
(`crates/katgpt-percepta/src/compile.rs` and `src/pruners/bomber/replay.rs` are
not). The repair formatted the 6 with `rustfmt` per file and hand-wrapped the
one over-length line in the other two.

## T2 — the gate (DONE, and it is the point)

A census done by hand is a census that stops being done. 13 sites in this
workspace already had the unique-path form and 27 did not — 25 repaired above,
2 adjudicated as deliberate — which means the rule was known and un-enforced,
this repo's own most-repeated shape.

- [x] **T2 — `scripts/shared_temp_path_gate.py` — DONE 2026-09-18.** Landed as
  docs_gate CHECK #27, green over 2 pinned rows / 40 `env::temp_dir()` call
  sites / 16 tracked files (floors 20 / 8). ⛔ Its first `arm_reach_gate` run
  produced **23 unpinned survivors, every one in `mask`** — the hand-rolled
  lexer — because the arms tested `sites()` and never `mask()` itself, so a
  bound that merely mis-sizes a blank run distinguished nothing. Repaired by
  arming the masker directly (exact outputs plus a LENGTH-PRESERVATION
  invariant over a 16-input corpus, which is what kills an off-by-one anywhere
  in the walk) rather than by pinning 23 rows. ⚑ Two of those arms then failed
  on first run — my own expected blank runs were each one space too long. The
  code was right; the arms caught the arithmetic in the assertion, which is the
  argument for writing them. The original spec was:
  red on a tracked `*.rs` calling `env::temp_dir().join(<string literal>)`
  where the literal carries no per-process discriminator. Needs the usual
  furniture: membership-pinned exemptions with a reason per row (the two
  examples above are the initial contents, and the file must red on a stale
  row), two floors (the tracked-`*.rs` walk AND the `temp_dir` call-site count
  — Issue 783's lesson, they go blind separately), a `selftest` arm invoked
  unconditionally per `check_validation_gate`, `console_safe` per Issue 804,
  and a row in the AGENTS.md CHECKS table per `docs_gate_checks_sync`.
- [x] **T3 — the cross-repo half — DONE 2026-09-18.** Counted first, as the
  task demanded, and the count settles it: `scan()` already took a repo path,
  so the question was answerable the whole time. Measured over the 13 canonical
  repos present on this box — **100 fixed-path sites, 98 of them NOT in
  katgpt-rs**, over 458 `env::temp_dir()` calls in 285 tracked `.rs` files:

  | repo | `env::temp_dir()` | fixed sites |
  |---|---|---|
  | riir-ai | 101 | **48** |
  | riir-clippy | 124 | **24** |
  | riir-train | 45 | **12** |
  | riir-chain | 60 | **10** |
  | riir-neuron-db | 5 | 3 |
  | katgpt-rs | 40 | 2 (both adjudicated) |
  | riir-game-sdk | 5 | 1 |
  | riir-auth · riir-dapps · riir-kat · riir-mmorpg-examples · riir-shader · riir-viewbridge | 54 | 0 |

  So `check_validation_gate`'s Issue 789 T4 answer does **not** carry across —
  the population is 13, not one — and this is the tenth recorded instance of
  the never-generalised shape. Sampled for over-capture and it is not:
  riir-ai's `go_bonsai_cache_test.bin`, `go_gemma_cache_corrupt.bin` and
  `test_egl_roundtrip.bin` are `#[test]` bodies writing a fixed filename,
  byte-for-byte the shape that produced this repo's own five-at-once *"File too
  small for header"* failures.

  Landed as `scripts/shared_temp_path_drift_sweep.py` +
  `scripts/shared_temp_path_drift_floors.txt`: ceiling a **RATCHET at
  measured** (see T5), two floors that break differently, all three family-wide
  mechanisms (worktree advisory, known-extra exemption, head provenance), and
  12 canary arms over its own pin arithmetic.
  `sweep_advisory_membership_gate` confirms all three mechanisms on every
  member — **take the family size from its PASS line, never from a sentence
  here.** (Written after typing "20 sweeps" into this paragraph and watching
  the gate print 21 one command later: the new sweep was UNTRACKED, so every
  `tracked_files` walk in the docs gate had been scoring a population that did
  not include it. `git add` before believing a gate has checked new work.)

  Two design points worth keeping:
  - **No `min_rs_files` column.** Three sweeps already floor this identical
    `tracked_files(repo, "*.rs")` walk over this identical population. The
    delegation is ASSERTED (`len_derived`'s rule): a pinned repo that loses its
    non-zero row in `orphaned_attr_drift_floors.txt` reds, and a delegated file
    the sweep cannot PARSE is refused rather than read as an empty dict — a
    silent `{}` turns the assertion into the no-op it exists to prevent.
  - **katgpt-rs's row asserts the GATE'S VERDICT**, not a count. This sweep and
    the gate call the same `scan()`, so a count comparison is true by
    construction and *a pin that restates its own input cannot fail*. Asserting
    the verdict means a stale membership row in
    `shared_temp_path_expected.txt` reds the sweep too.

- [x] **T4 — the other fixed-scratch spellings — MEASURED 2026-09-18, and the
  class is EMPTY in this repo.** 10 literal-`/tmp` sites over 8 files, and not
  one is a live write hazard:
  - **4 are READ-ONLY** — the `katgpt-moka-wasm/tests/wasmi_*` `WASM_PATH`
    constants are `fs::read` of a build artifact. A reader cannot truncate, so
    the hazard this issue is about does not exist there. That distinction is
    the useful part of T4: the predicate is not `/tmp`, it is *writer
    semantics on a shared path*.
  - **3 are doc comments** (`//!` in `katgpt-pruners`) — not code.
  - **3 are `examples/`** (`hl_01_trial_log.rs`, `hl_02_hotswap.rs`) — the
    same adjudication as the two pinned `env::temp_dir()` rows: demos a human
    inspects, and no gate runs two examples concurrently.
  - The **variable-bound** spelling is 1 site (`katgpt-percepta/src/compile.rs`)
    and it is already pid-suffixed — its `.join` sits on the next line, which
    is why a line-scoped grep misses it. That remains a STATED blind spot of
    the gate rather than a finding.

  So no floor was widened: widening the predicate on a measurement of zero
  would pin a population that does not exist. The blind spots stay stated, on
  the gate's own PASS line and in its docstring, where a later census reads
  them instead of re-deriving them.

- [ ] **T5 — the 98 sibling sites are a real backlog, and they are their
  owners' to adjudicate.** The T3 ratchet's job is that the commit adding the
  NEXT one reds; it is deliberately NOT a claim the existing 98 are fine. The
  repair is the form this workspace already uses —
  `join(format!("name_{}", std::process::id()))`. Three rules apply and the
  third is why this is filed rather than done:
  - Per repo, in that repo, with its own tests run there.
  - A cross-repo repair is **not landed until it is COMMITTED in the sibling**,
    and a record here claiming one must CITE THE SIBLING SHA (Issue 798 —
    measured: two tracked files recorded sibling repairs as landed and green
    when two of five existed and both sweeps were red for six hours).
  - Some of the 98 are `examples/` and `src/bin/`, which is the
    adjudicated-not-repaired class — so this is 98 *reads*, not 98 mechanical
    edits.

  **Triaged 2026-09-18** (a site is TEST if its file carries `#[cfg(test)]` or
  lives under `tests/`), so the backlog is addressable rather than a number:

  | repo | test | example/bin | other |
  |---|---|---|---|
  | riir-ai | **42** | 4 | 2 |
  | riir-clippy | **17** | 7 | 0 |
  | riir-chain | **9** | 1 | 0 |
  | riir-train | 3 | 9 | 0 |
  | riir-game-sdk | 1 | 0 | 0 |
  | riir-neuron-db | 0 | 3 | 0 |
  | **total** | **72** | **24** | **2** |

  So the live hazard is **72 sites**, not 98, and it is concentrated: riir-ai
  and riir-clippy carry 59 of them. The 24 example/bin rows get the same read
  the two pinned rows here got — a demo's path is meant to stay findable, and
  no gate runs two examples concurrently — and the 2 `other` rows are
  non-test, non-demo code and want a per-site read before anything is assumed
  about them.

  ⚠ Do the repairs **per repo, in that repo, with its tests run there**, and
  cite the sibling SHA in whatever record claims one. riir-clippy in
  particular is written by a concurrent session as of this filing.

  **Progress 2026-09-18 — 54 of the 72 live test hazards closed**, each
  committed in the sibling before its ratchet moved (the Issue 798 rule):

  | repo | SHA | test sites closed | residual | note |
  |---|---|---|---|---|
  | riir-ai | `9d138531b` | 44 | 4 | residual all `examples/` |
  | riir-chain | `8a3b0f5` | 9 | 1 | residual all `examples/` |
  | riir-game-sdk | `ef66117` | 1 | 0 | ratchet is now a wall |
  | riir-train | — | — | 12 | dry run: **0 non-demo sites**; all 12 are `examples/`+`src/bin/` |
  | riir-neuron-db | — | — | 3 | all `examples/` |
  | riir-clippy | — | — | 24 | **the only repo with live test sites left (17)** |

  So the live-hazard backlog is **riir-clippy's 17**, and it is BLOCKED on
  contention rather than on work: a concurrent session holds 16 dirty files
  there, 7 of them in this sweep's own population. Repairing into another
  session's worktree is the shared-worktree hazard `staged_set_audit.py`
  exists for. Do it when that repo is clean; `scripts/shared_temp_path_fix.py
  ../riir-clippy --dry-run` is the whole of the work.

  ⚠ The riir-train row is the one worth reading twice: this issue's own T5
  triage table says *"riir-train 3 test"*, and the repair tool measures **0**.
  The 3 either moved or were miscounted by the file-level `#[cfg(test)]`
  heuristic the triage used. **Take the split from the tool's dry run, not
  from the table above it** — the table is a dated census and the dry run is
  the instrument.

  ⚠ Four repos carry a STALE advisory on this sweep (riir-ai 4 behind on 4
  in-scope commits among them). A count read on this box is what this
  checkout says, not what origin says — confirm before repairing there
  (Issue 798).

## Standing

⛔ **VERIFIED in the instrument that found it, 2026-09-18 @ `a77c46c0`:**
`scripts/x86_64_execution_matrix.sh` is **fully green for the first time** —
8 cells, **11177 assertions, 0 failures**, against `✗ FAILED — 2 red cell(s)`
on 2026-09-16. Cell 5 (`katgpt-rs --lib --all-features`) 577 passed, and
cell 7 (`katgpt-types`, the five-at-once *"File too small for header"* block)
263 passed. The direct two-process reproduction proved the mechanism; this
proves the repair where the defect was first seen.

⚠ Cell 8's other red, `test_bench_171_thinking_prune_goat`, also passed this
run — that is **consistent with** [Issue 831](831_bench_171_p3_bar_is_a_coin_flip_on_x86_64.md)'s
measurement (4 failures in 20 captured-mode runs) and is **not** evidence it is
fixed. A coin-flip bar passing once is the expected majority outcome; 831 stays
open.

The x86_64 matrix's cell-5 red is closed by T1. Its other red
(`test_bench_171_thinking_prune_goat`) is a different defect and is
[Issue 831](831_bench_171_p3_bar_is_a_coin_flip_on_x86_64.md) — that one is a
genuinely load-sensitive bar, and the TRANSIENT reasoning the top of this issue
criticises is exactly right for it. The two reds looked alike in the summary
line and needed opposite diagnoses.
