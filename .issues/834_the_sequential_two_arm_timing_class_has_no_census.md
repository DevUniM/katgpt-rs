# Issue 834: the sequential two-arm timing class had no census — three members were found by tripping over them, and the treatment ships in one repo of sixteen

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

### Measurement (2026-09-18, 16 repos on this box)

```
  ADOPTED        7   uses tests/common/ab_timing.rs
  SEQUENTIAL   131   the class
  UNRESOLVED   865   NOT clean; needs a per-target read
  population  2677 target file(s) / 9621 tracked *.rs
```

Per repo, the ones that carry any: **katgpt-rs 60 · riir-ai 52 · riir-train
11 · riir-neuron-db 6 · riir-chain 1**, and **ADOPTED is 0 in every repo but
katgpt-rs.**

⚠ **Read 131 as a magnitude, corroborated by predicates that disagree.**
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
  865 unresolved rows. Read it for candidates; never bulk-convert.

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
