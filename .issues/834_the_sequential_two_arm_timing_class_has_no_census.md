# Issue 834: the sequential two-arm timing class had no census — three members were found by tripping over them, and the treatment ships in exactly ONE repo of the workspace

**Status:** T1 (the instrument) **DONE 2026-09-18**. T2 (the katgpt-rs
migration backlog) and T3 (the cross-repo question) are open and are
deliberately not mechanical.
**Origin:** [Issue 833](833_a_ratio_of_two_sequentially_timed_arms_measures_the_box.md),
which migrated `tests/bench_105_gdn2_goat.rs` GOAT 2 and asked for a
report-only census as its next artifact. Filed by session `katgpt-rs-c5`;
833 is `katgpt-rs-54`'s.

## The class

A wall-clock gate that times arm A to completion, then arm B, and asserts on
the single resulting ratio measures **the box**, not the code. Two sequential
arms of the *same* work measured **+5.2% and +21.7%** thirty seconds apart on
a loaded box (Issue 723 T5). A 10% bar cannot survive that.

`tests/common/ab_timing.rs` is the treatment and it has existed since Issue
723: interleaved `(a-chunk, b-chunk)` pairs so a drift moves BOTH arms and
cancels in the ratio, the MEDIAN across pairs so one preemption spike is
discarded, and a loud zero when the optimiser deletes an arm.

## ⛔ The finding is the DISCOVERY METHOD, not the count

| member | how it was found |
|---|---|
| the original 8 | Issue 723's census — the only one found by looking |
| a 9th | Issue 831, by walking into it |
| `bench_105` GOAT 2 | Issue 833, via `x86_64_execution_matrix.sh` reporting PASSED-ALONE |

The treatment has been available for months and its members are found by
tripping over them. That is the argument for a census, and it is the same
shape this repo has now recorded ten times: **a rule landed in one instrument
and was never generalised.**

⛔ **And the sharpest version of it is measured below: the harness itself was
never generalised.** `ab_timing.rs` lives in `katgpt-rs/tests/common/`. Every
other repo in the workspace has the class and **none has the treatment.**

## T1 — `scripts/sequential_ab_timing_audit.py` (DONE)

```bash
scripts/sequential_ab_timing_audit.py            # this repo
scripts/sequential_ab_timing_audit.py ../riir-ai # or one, by path
scripts/sequential_ab_timing_audit.py -v         # every row, not just findings
```

A **report, exit 0** — except a blindness floor or a failing self-test, which
exit **2**. The self-test runs on **every** invocation
(`platform_dead_code_audit`'s rule: an instrument that cannot classify must
not be read as `0 findings`).

Three buckets:

- **ADOPTED** — names `common/ab_timing.rs` or calls `ab_median_ratio`. Read
  off the **unmasked** text on purpose: `#[path = "..."]` puts the module path
  inside a string literal, which masking blanks.
- **SEQUENTIAL** — ≥2 `Instant::now()` **and** a ratio whose BOTH sides are
  timing-derived identifiers, minus count-like denominators. The decidable
  class.
- **UNRESOLVED** — timed, no decidable two-arm ratio. **Not "clean"**, never
  folded into either neighbour — the rule this repo already states for
  percentile UNRESOLVED, wasm32 UNRESOLVED, and `len_derived`'s 118 bind
  sites. A two-arm comparison written in a shape the regex cannot see lands
  here, and so does an ordinary single-arm latency bar that is not the class.

### Measurement (2026-09-18, the 17 contract repos on this box)

```
  ADOPTED        7   uses tests/common/ab_timing.rs
  SEQUENTIAL   130   the class
  UNRESOLVED   827   NOT clean; needs a per-target read
  population  2516 target file(s) / 9125 tracked *.rs
```

⛔ **The first figures published here were 131 / 865 / 2677 / 9621 and were
WRONG, by a defect this issue's own sibling then found.** The repo list was
built by an ad-hoc `(p / ".git").exists()` walk; the canonical predicate tests
**`.is_dir()`**, because a `git worktree` has a `.git` **FILE** — so this box's
`riir-chain.w152` worktree entered the population and riir-chain was counted
TWICE (+1 SEQUENTIAL, +38 UNRESOLVED). Corrected against
`skill_repo_set_gate.derive_repos`, 17 repos. See
[Issue 835](835_a_path_dep_on_a_repo_in_neither_set_is_enumerated_by_nothing.md),
where `population_sync_gate` refused the same hand-rolled walk in a different
instrument an hour later. **This is the argument for the section below**: a
number typed into a document is a claim about one run on one box.

Per repo, the ones that carry any: **katgpt-rs 60 · riir-ai 52 · riir-train
11 · riir-neuron-db 6 · riir-chain 1**, and **ADOPTED is 0 in every repo but
katgpt-rs.** The class generalised; the harness did not.

⚠ **Read that SEQUENTIAL figure as a magnitude, corroborated by predicates
that disagree.**
Three independent passes over overlapping populations returned **55** (833's
own looser pass over `tests/*.rs` + `crates/*/tests/*.rs`), **57** (this
instrument's ungated prototype) and **60** for katgpt-rs. That they disagree
is the honest signal; an exact number here would be drift waiting to happen.
**Take the figure from a run.**

### What it borrows rather than re-derives

`mask_file` is **imported** from `platform_dead_code_audit`, not re-written.
A text scan cannot tell a real `Instant::now()` from one inside a doc comment
or a raw-string fixture, and this workspace has met that class three times
already (`wasm32_surface_audit` reported a whole repo's count from four
fixture strings; `subprocess_encoding_gate` moved to an AST after reporting
four offenders inside its own `selftest`). A second copy of a hand-rolled
Rust lexer is a second thing to get wrong.

### The arms, and the one that was inert

Every classifier rule was perturbed and required to RED — a rule this repo
states and an earlier draft of this instrument broke:

| perturbation | verdict |
|---|---|
| drop the COUNTY (rate) filter | KILLED |
| drop the `x/x` normalisation guard | KILLED |
| drop masking | KILLED |
| read ADOPTED off the masked text | KILLED |
| `n<2` classified SEQUENTIAL | KILLED |
| `is_target` admits `src/` | KILLED |
| break the `Instant::now()` regex | KILLED |
| **`MIN_TIMED` → 0** | **SURVIVED** |

⛔ The floor survived because the floor arithmetic sat **inline in `main()`**
beside its own error strings, where no arm could reach it — this repo's
single most-repeated instrument finding, recorded for
`percentile_floor_gate`, `cfg_row_implication_gate`, `trap_sentinel_gate`,
`markdown_fence_gate` and the three weakest modules in the CHECKS population.
The repair is the same one every time: **EXTRACT it.** `floor_verdict()` is
now its own function with six arms over both floors in both directions,
including that the two report **distinguishable** causes — pooling them is
how a walk regression gets diagnosed as a broken regex — and that neither
floor is 0, since a floor of 0 can never fire.

⛔ A second, uglier one is worth recording because it nearly inverted the
whole table: the first perturbation harness classified **every** mutant as
SURVIVED. A missing transitive import made each run exit **1**, and the
harness read any non-2 as "the arm did not fire". That is precisely the
CRASHED-vs-KILLED misfiling AGENTS.md documents for `arm_reach`, reproduced
within an hour of reading it. **A mutation harness must distinguish "the arm
was silent" from "the module never ran."**

## ⚠ STATED blind spots

Written here and on the report's own output so a later census reads them
instead of re-deriving them:

- a ratio built through a **helper function**;
- a comparison expressed as a **subtraction or a percentage** rather than a
  division;
- two arms differenced off **one** `Instant::now()`;
- **arm ORIENTATION** — not statically decidable, and the part that actually
  costs time (see T2).

## Open tasks

- [ ] **T2 — the katgpt-rs backlog is 60 targets and is NOT a mechanical
  sweep.** Issue 833 T4 refuses a verdict half and this issue does not
  reopen that. Each target needs three reads that no classifier can do:
  - **Orientation.** `AbRatio::median` is a **time** ratio; roughly half
    these gates state a **throughput** claim, whose ratio is its reciprocal.
    Getting it backwards inverts the bar **silently**.
  - **Chunk size**, off the target's own printed per-round range — which does
    not exist until it has been migrated once. 833's own migration needed
    `ITERS` 500 → 5000 on a 0.73..2.99 reading.
  - **`black_box` at both ends.** The `let _ = f()` elimination shape (723
    Class A2) is orthogonal to interleaving and survives it.

  So a slice taken from this report is a slice taken from a classifier with
  827 unresolved rows. Read it for candidates; never bulk-convert.

  ⛔ **MEASURED 2026-09-18, and it reframes what the count IS.** Two
  consecutive `x86_64_execution_matrix.sh` runs fired **two DIFFERENT members**
  of this set, on a commit range that touched neither test's code:

  | run | HEAD | PASSED-ALONE row |
  |---|---|---|
  | 1 | `d7a34822` | `goat_2_gdn2_within_10pct_of_ahla_throughput` (`bench_105`) |
  | 2 | `aba3827f` | `g8_cached_faster_than_uncached` (`belief_drafter_goat.rs`) |
  | 3 | `dd8dadbb` | **none — clean**, both of the above repaired by then |

  Both were already in the DECIDED set. Both passed the same three-grep
  adjudication as load-sensitive BARs. Run 2 also confirmed `bench_105`'s
  repair **in cell**, which its 8 standalone runs could not — standalone and
  in-cell are different load regimes, and in-cell is the one that failed.

  **Run 3** (`dd8dadbb`) was **CLEAN — `failed=0`, zero PASSED-ALONE rows,
  11177 assertions.** `katgpt-rs-54` predicted a third distinct member and it
  did not fire. Recorded because it was pre-committed, and because a prediction
  reported only when it lands is not a prediction.

  ⇒ **The DECIDED count is not a backlog of latent rows awaiting their turn.
  It is a population every run SAMPLES FROM**, and which member surfaces is
  decided by what else the box was doing. That is what has been reporting
  itself as PASSED-ALONE — and, before Issue 832 renamed the bucket, as
  TRANSIENT — all along. It is the strongest argument for T2, and unlike the
  count itself it is measured rather than argued. (Credit: `katgpt-rs-54`.)

  ⚠ A corollary worth stating: **a green matrix run is not evidence this set
  is shrinking.** With sampling, the expected number of runs to observe a given
  member is a function of the population size, so converting members lowers the
  per-run hit rate long before it reaches zero.

  ⛔ **And that corollary binds THIS issue first — run 3 discriminates
  nothing.** Two readings survive it and the run cannot separate them:
  - a sampling population with its **two most fragile members now repaired**
    (run 3 is the first run in which BOTH `goat_2` and `g8` are fixed, so it
    did not sample the population runs 1 and 2 sampled), or
  - simply a quieter box.

  3 runs, 2 firings, 1 quiet: a sampling model **expects** quiet runs, so this
  is not evidence against sampling either. What it does refute is the strong
  form — *every run surfaces a member* — which nobody should have held at n=2.
  **Do not read run 3 as progress; that is exactly the inference the corollary
  above forbids**, and it is easier to catch in someone else's reasoning than
  in one's own.

  ⛔ **What WOULD discriminate, and the gap is real:** the matrix records no
  BOX STATE. AGENTS.md §Feature Flag Discipline G2 already rules that *"a
  latency number without its BOX STATE is not a measurement"* — and every
  PASSED-ALONE row is a latency-bar outcome, recorded with no free RAM, no
  commit-vs-limit, and no concurrent-job note. So runs are not comparable to
  each other even in principle, and three of them cannot be pooled into a rate.
  Logging box state per run would make the sampling claim testable instead of
  arguable. Filed as a candidate, not done — it is the matrix's call, not this
  issue's.

  ### A worked per-target read — same SHAPE, different RISK

  The repaired `tests/belief_drafter_goat.rs` has a near-twin this repo also
  ships: `tests/bench_217_belief_drafter_goat.rs:1010` runs the *identical*
  cached-vs-uncached two-arm comparison (`cached_us / uncached_us`), and my
  census flags it SEQUENTIAL. A codemod would treat them the same. A read does
  not:

  | | `belief_drafter_goat.rs` g8 (fired) | `bench_217_…:1010` (B6, not fired) |
  |---|---|---|
  | ratio expression | `cached_us / uncached_us` | `cached_us / uncached_us` — **identical** |
  | **CLAIM** | `cached_us < uncached_us / 2.0` — cache is ≥2x **FASTER** | `ratio < 2.0` — cache is not >2x **SLOWER** |
  | **direction** | a performance **WIN** | an overhead **CEILING** |
  | slack | none — the bar sits ON the claim | ~5x, and deliberate |
  | Class A2 (`let _ = f()`) | **yes, both arms** | **no** — `black_box` on both |
  | a regression | flips the sign of a near-zero margin | must cross 5x before anything notices |

  ⛔ **CLAIM DIRECTION is a THIRD axis, and a syntactic classifier is
  structurally blind to it** (`katgpt-rs-54`, verified here against both
  asserts). The two tests compute the *same expression* and assert *opposite
  things*. A **win** claim with no slack has to be precise, so
  `ab_median_ratio` is the right instrument; an **overhead ceiling** with
  deliberate room is nearer in spirit to the `best_of_us` absolute-budget
  family, and migrating it buys almost nothing because flakiness is not its
  exposure. My census keys on the ratio expression and therefore cannot see
  this at all — add it to orientation and chunk size as the reads T2 owes.

  ⚠ **"Slack" is not one smell and 834 must not let it read as one.** G2's
  10x is slack *bolted onto* a claim it was failing to measure, with "timing
  is noisy" written at the line. B6's 2x **is** the claim — a ceiling is
  supposed to have room. Same word, opposite diagnoses.

  ⚠ **B6's arms are not a paired A/B**, so a migration would need the FIXTURE
  reworked before the timing: arm A is 1000 `drafter.draft()` calls, arm B is
  1000x5 nested cache lookups living elsewhere in the function.
  ⇒ One correction to 54's reading, which **strengthens** the point: the
  pre-warm loop keys on `dt.token_idx` while the timed loop keys on `step`, so
  the pre-warm is largely **inert** rather than the thing making arm B a hit
  path. The miss closure *does* run — about five times, on iteration 1 — and
  it is the timed loop's **own** `get_or_insert` inserts that make iterations
  2..1000 hits. The arms are even less comparable than "pre-populated, so the
  closure never runs" suggests.

  So the twin is the same shape at materially lower risk, and it is a
  *candidate*, not a defect. `katgpt-rs-54` read three timing gates in the
  repaired file and reached three different correct answers — G2 is the same
  two-arm shape with an explicit 10x slack bar, which will not flake but
  **tolerates** the defect rather than measuring it (a claim-strength question
  for Plan 217's owner, not a repair); G3 is an absolute one-arm budget, the
  `best_of_us` class, where migrating to `ab_median_ratio` would be **wrong**
  because there is no second arm to ratio against.

  **Three timing gates in one file, three different correct answers.** Whatever
  T2 becomes, it cannot be a codemod.

- [ ] **T3 — the cross-repo question, MEASURED and left open deliberately.**
  The class is 71 targets outside this repo and the treatment is 0. Do **not**
  conclude "therefore a drift sweep" — `check_validation_gate` declined one on
  a measured population of one, `console_encoding_gate` assumed that answer
  carried and was wrong by seven repos, and the honest reading here is a
  third thing: a sweep would ratchet a backlog nobody has read, which is
  exactly the shape Issue 785 forbids. The prior question is whether
  `ab_timing.rs` should be a **shared crate** rather than a `#[path]`-included
  module copied per repo. That is an owner/boundary call, not a gate.

- [ ] **T4 — no verdict half, and this is a decision rather than an
  omission.** Recorded so the next reader does not add one by symmetry with
  the sweep family. Re-measure after T2; a ceiling over a bucket whose
  migration is a per-target read is a backlog wearing a pin.
