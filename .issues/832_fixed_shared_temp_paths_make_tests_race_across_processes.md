# Issue 832: 25 tests wrote to FIXED `env::temp_dir()` paths, so any two concurrent runs truncate each other — and the matrix's TRANSIENT bucket was where that hid

**Status:** FIXED 2026-09-18 for all 25 tracked test sites (T1). **T2 — the
gate — is the open task**, and it is what keeps the class from coming back.
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

## T2 — the gate (OPEN, and it is the point)

A census done by hand is a census that stops being done. 13 sites in this
workspace already had the unique-path form and 25 did not, which means the rule
was known and un-enforced — this repo's own most-repeated shape.

- [ ] **T2 — `scripts/shared_temp_path_gate.py`**, a `docs_gate.sh` CHECK:
  red on a tracked `*.rs` calling `env::temp_dir().join(<string literal>)`
  where the literal carries no per-process discriminator. Needs the usual
  furniture: membership-pinned exemptions with a reason per row (the two
  examples above are the initial contents, and the file must red on a stale
  row), two floors (the tracked-`*.rs` walk AND the `temp_dir` call-site count
  — Issue 783's lesson, they go blind separately), a `selftest` arm invoked
  unconditionally per `check_validation_gate`, `console_safe` per Issue 804,
  and a row in the AGENTS.md CHECKS table per `docs_gate_checks_sync`.
- [ ] **T3 — the cross-repo half.** `env::temp_dir()` is not a katgpt-rs idiom;
  the sibling Rust repos have tests too. Per the family rule, **re-measure the
  population before deciding** — `check_validation_gate`'s Issue 789 T4
  measured ONE and correctly declined a sweep, and `console_encoding`'s Issue
  804 assumed the same answer and was wrong by seven repos. Do not carry either
  answer across; count first.
- [ ] **T4 — widen the predicate deliberately.** `env::temp_dir()` is one
  spelling. `TempDir::new()` from the `tempfile` crate is already unique;
  a hand-rolled `PathBuf::from("/tmp/...")` or `./target/test_scratch` is not,
  and neither is visible to a `temp_dir` grep. Measure the other spellings
  before pinning a floor, or the floor describes one spelling's population.

## Standing

The x86_64 matrix's cell-5 red is closed by T1. Its other red
(`test_bench_171_thinking_prune_goat`) is a different defect and is
[Issue 831](831_bench_171_p3_bar_is_a_coin_flip_on_x86_64.md) — that one is a
genuinely load-sensitive bar, and the TRANSIENT reasoning the top of this issue
criticises is exactly right for it. The two reds looked alike in the summary
line and needed opposite diagnoses.
