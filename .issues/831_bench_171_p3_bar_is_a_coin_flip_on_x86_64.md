# Issue 831: `bench_171_thinking_prune_goat` P3 asserts `>0%` while its own comment predicts 30–60% — it fails 20% of runs on an idle x86_64 box, and the result depends on how the harness is invoked

**Status:** OPEN — measurement recorded, repair NOT applied (the bar encodes a
promotion claim; see §What must not be done)
**Found by:** `scripts/x86_64_execution_matrix.sh`, 2026-09-18, cell 8
(`katgpt-rs --tests --release`, `+avx2`). The matrix's wall fired:
`✗ UNPINNED failing test(s): test_bench_171_thinking_prune_goat`.
**File:** `tests/bench_171_thinking_prune_goat.rs:322` (P3)
**Subject:** Plan 171 Thinking Prune, `PrunerSchedule::FrozenBaseGuard`

## The assertion

`tests/bench_171_thinking_prune_goat.rs:320-325`:

```rust
// We expect ~30-60% speedup (2/3 of hops skip the work).
assert!(
    ns_frozen < ns_uniform,
    "FrozenBaseGuard should be faster than Uniform with expensive screener \
     (got {ns_frozen}ns vs {ns_uniform}ns, {speedup_pct:.1}%)",
);
```

**The comment states 30–60%. The assertion accepts any speedup above zero.**
Nothing in between is checked, so a result of +0.1% and a result of +55% are the
same verdict.

## What it actually measures

All runs below: idle x86_64 box (i7-13700K, ~22 GB free, no other heavy job),
the matrix's own `+avx2` release binary run directly out of
`/f/scratch/target/release/deps/` per AGENTS.md's diagnose-by-binary rule,
`--exact test_bench_171_thinking_prune_goat`.

| mode | runs | verdict | observed speedup |
|---|---|---|---|
| captured (what `cargo test` and the matrix use) | 20 | **16 pass / 4 FAIL** | failing runs: −1.9%, −2.5%, −2.2%, −5.0% |
| captured, earlier batch | 10 | **6 pass / 4 FAIL** | failing runs: −0.8%, −1.2%, −2.5%, −5.1% |
| `--nocapture` | 12 | **12 pass** | +0.9%, +1.9%, +4.6%, +7.8%, +11.7%, +6.0%, +3.7%, +3.1%, +3.7%, +7.6%, +11.4%, +3.9% |

The in-cell run that started this read **−0.8%** (1341752.5 ns vs 1331353 ns).

Three things follow, and they are separable:

1. **A ~20% failure rate on identical source and an idle box.** The bar sits at
   0% and the distribution straddles it.
2. **The claimed 30–60% appears in NO run, in either mode.** The best single
   observation across 42 runs is +11.7%.
3. ⛔ **The verdict depends on how the harness is invoked.** Captured mode fails
   ~20% of the time; `--nocapture` passed 12/12 with every value positive.
   Neither mode prints anything inside the timed loops, so this is the harness's
   own behaviour (libtest captures by spawning the test on a separate thread)
   leaking into a wall-clock measurement. **A benchmark whose answer moves with
   `--nocapture` is not measuring its subject.** It also means the passing
   values in captured mode are *unobservable* — stdout is discarded on success —
   so the row this gate reports green has no recorded number at all.

## The fixture may not be able to express the mechanism

Two facts from the same run:

- P1 prints `Uniform=1536 nodes, FrozenBaseGuard=1536 nodes` for **every seed**.
  P1's assertion is `FrozenBaseGuard >= Uniform`, which equality satisfies — so
  P1 passes while telling us both schedules build the SAME tree on this fixture.
  `ExpensiveScreener { base_relevance: 0.7 }` accepts every candidate, so
  screening prunes nothing.
- P3 therefore is not measuring "2 of 3 hops skip work that changes the tree".
  It measures only the **call cost** of a synthetic screener
  (`work_per_call: 100`) against the cost of building a 1536-node tree three
  times, at `iters = 200`.

The mechanism is real in the code: `build_dd_tree_screened_with_schedule`
(`crates/katgpt-forward/src/dd_tree/mod.rs:98`) substitutes `NoScreeningPruner`
on intermediate hops, so those calls genuinely do not happen. The open question
is whether `work_per_call: 100` is large enough for the saved calls to be
visible above this CPU's noise — this repo's own recurring shape, *a clean null
A/B is usually a fixture that cannot express the mechanism*.

## What must not be done

⛔ **Do not raise the bar to make it pass, and do not lower it to 0.** Both are
the repair for a number that is RIGHT, and this one is not known to be. Bench
825's own note is the precedent: *"the first run sat at 1.4e-5 and the bar was
NOT moved to meet it — the solver was wrong and got fixed."*

⛔ **Do not pin it into `scripts/x86_64_matrix_expected.txt` as arch-conditional
without first measuring the aarch64 arm.** The two ISA-real rows that file
carries (`proof_g3b_swar_speedup`, `t09_throughput_inv_sqrt_16x16`) were
adjudicated as NEON/FMLA-calibrated bars x86_64 cannot reach. Nothing has
established that P3's 30–60% is reached on aarch64 either — it may never have
been measured, since `full_gate` is compile+lint and `test_gate` is `--lib`-only,
so this integration target is executed by nothing but the matrix. **A pin
written before that measurement would record a flaky bar as an architecture
difference.** The matrix's expected set is deliberately EMPTY; keep it so until
there is a reason with a number in it.

## Tasks

- [ ] **T1 — Measure the aarch64 arm**, both capture modes, ≥20 runs each,
  recorded as a distribution and not a single number. Three outcomes, three
  different repairs: 30–60% there ⇒ genuine arch difference, pin
  arch-conditionally *and* correct the fixture note; ~0% there too ⇒ the claim
  is wrong everywhere and P3 has been passing on luck since it landed; wide
  spread there ⇒ the harness defect alone.
- [ ] **T2 — Repair the harness regardless of T1.** Best-of-N over repeated
  trials, the Issue-723 `best_of_us` shape AGENTS.md already prescribes for
  `t09_throughput_inv_sqrt_16x16` (whose `bench_us(3, 20)` oscillated 2.1× for
  the same reason). Correct under every T1 outcome, and it is what makes T1's
  own numbers trustworthy. **Print the measured value on the PASS path too** —
  a captured-mode green currently records nothing.
- [ ] **T3 — Make P1 non-vacuous.** `>=` passing on exact equality is how "both
  schedules build the same tree" stayed invisible. Either assert strict
  inequality against a fixture that produces it, or assert the equality
  deliberately and move the node-count claim to where it is actually tested.
- [ ] **T4 — Re-adjudicate the fixture.** If the screener never prunes, decide
  whether `work_per_call` should rise until the mechanism is expressible, or
  whether P3's claim should be restated as "skips N screener calls" and measured
  as a **call count** — which is exact, arch-independent, and immune to every
  defect above.
- [-] **T5 (owner-gated) — promotion.** Whether `thinking_prune`'s status rests
  on this P3 row is a promotion question, not a measurement. Deferred.

## Standing

The x86_64 matrix stays RED on this row until T1/T2 land. That is correct and
deliberate: AGENTS.md's rule that *a stale pin reds too — the file must not only
ever loosen* has an inverse, which is that a row must not be pinned before it is
diagnosed.

## 2026-09-18 — one more sample, and it is NOT evidence of a fix

The Issue-832 matrix re-run (`a77c46c0`, 8 cells, 11177 assertions) came back
**fully green**, `bench_171` included. Read that as the 16-in-20 outcome this
issue already measured, not as a repair: nothing in that commit range touched
the bar, the schedule, or the harness, and a bar that fails 4 times in 20 runs
passes most of the time by construction.

⛔ The trap is the same one this issue and Issue 832 were both filed about, in
its other direction: 832's defect passed ALONE and was filed TRANSIENT, and
this one passes IN THE CELL and would now be filed FIXED. A single green run
distinguishes neither. The verdict for a load-sensitive bar needs the
distribution, which T2 is for.

## 2026-09-18 — T2 + T3 DONE, and the root cause was the FIXTURE, not the bar

⛔ **`ExpensiveScreener::relevance` was not expensive. Its work was deleted.**

```rust
for i in 0..self.work_per_call { acc += (i as f32).sin() * (i as f32).cos(); }
// Prevent optimization from removing the work
let _ = acc;
```

The comment claims it prevents elimination; `let _ = acc` does no such thing.
The loop is pure and its result dropped — the exact shape **Issue 723 T5**
measured being deleted by rustc 1.98.1 + fat LTO ("a direct call with a used
result measured 16.6 µs; `let _ = f()` over the same fn in the same binary read
~0"). So P3 compared two arms that both skipped the *same free call*, the true
difference was ~0, and the SIGN of a zero is noise. That is the whole of the
coin flip.

The diagnostic that found it: with the harness repaired but the screener still
dead, scaling `work_per_call` **50x** moved the measured speedup only
0.4% → 1.5% → 3.1%. Real work does not behave like that. One `black_box(acc)`
later, at the ORIGINAL `work_per_call: 100`:

| | before | after |
|---|---|---|
| release | 0.4%, rounds 0.8847 .. 1.0400 | **64.2%**, rounds 0.3539 .. 0.3631 |
| debug | — | **63.1%**, rounds 0.3663 .. 0.3707 |

The fixture's own long-standing "~30-60% (2/3 of hops skip the work)" comment
was **right all along** and had never once been observed. T1's three outcomes
are resolved on x86_64 without needing the M3: it is not an arch difference and
the claim is not wrong — the instrument and the fixture were both broken.

- [x] **T2 — harness repaired.** `common/ab_timing.rs::ab_median_ratio`:
  interleaved `(a,b)` pairs, median of per-round ratios, per-round RANGE
  printed beside the median. ⚠ `ab_median_ratio`, **not** `best_of_us` as this
  issue's text said — that module reserves `best_of_us` for an ABSOLUTE budget
  with no second arm; P3 has two arms and a comparative claim, so taking a
  minimum per arm independently would compare two different load windows. Both
  arms are `black_box`ed at input and output (they were `let _ = f(...)`, the
  same elimination shape as the screener).
- [x] **T3 — P1 was VACUOUS and is now strict.** At the shared
  `tree_budget = 512` both schedules hit the cap and reported 1536 nodes on all
  10 seeds — `Frozen wins=0, Uniform wins=0, Ties=10` — so `>=` passed on exact
  equality every time. The budget was masking the mechanism: uncapped, the same
  fixture measures Uniform **2268** vs FrozenBaseGuard **200756**. P1 now uses
  its own `tree_budget = 4096` (Uniform reaches its natural 2268, Frozen 8948)
  and asserts `ties == 0` **and** `frozen_wins == n_trials`, with the cap named
  in the failure message. Canaried: at 512 it fails with that diagnosis.
- [x] **The bar is now 30%**, half the measured effect (the house slack
  convention). `ns_frozen < ns_uniform` was the widest bar expressible and
  still failed 4-in-20; a real 63% effect in a 2.6%-wide band supports a real
  bar, and a regression that stops skipping intermediate hops goes to ~0.

**Stability, the claim this issue exists to fix** — captured mode, the mode
that used to fail 4 of 20: **8/8 release, 5/5 debug**, plus 10/10 and 6/6
during development. 29 consecutive passes against the old harness's 80%.

⚠ **T4 is NARROWED, not closed.** The fixture CAN express the mechanism, so the
"restate P3 as a call count" option is no longer forced. What remains is that
`VaryingScreener` keys only on `depth` — it ignores `token_idx` and
`parent_tokens` — so all 10 P1 seeds produce identical counts and the trials
are a loop over one case. That is recorded at the assertion rather than fixed.

⚠ **T1 is still owed for aarch64** as a measurement, but its premise has
changed: any pre-2026-09-18 aarch64 number was taken against a deleted screener
and means nothing.
