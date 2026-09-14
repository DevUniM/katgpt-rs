# Issue 790 — an arm that exists and runs may still reach nothing

**Filed:** 2026-09-14 · **Status:** OPEN (T1 + T4 landed; T2 + T3 remain) · **Branch:** develop

## Progress

**T1 landed** (`ee0961e4`) — `scripts/arm_reach_audit.py`, 27 self-test arms,
documented in AGENTS.md. **T4 landed** — all four NO-ARM gates now carry a
`gate_selftest` over their own pin arithmetic, so **NO-ARM is 0**.

Standing after T4 (2026-09-14): **21 modules · 521 mutants · ~73s · 127
KILLED · 127 SURVIVED (live) · 155 survived in exempt functions · 112
CRASHED · 0 NO-ARM · 5 UNREACHED**.

Two operator-set changes were forced by the T4 work and both were measured
rather than guessed:

- `if __name__ == "__main__"` is **skipped**, not exempted. It is the entry
  point, not a decidable rule; no arm can kill it; and it is in all 61 tracked
  scripts, so it would have scaled with every arm added. Skipped rather than
  exempted so it does not inflate the mutant total `MIN_MUTANTS` floors.
- **Off-by-one** (`+`↔`-`) was added because comparison operators alone left
  `markdown_fence_gate` reading UNREACHED while its arms asserted real
  behaviour: its only real decision is `n_lines - first`, and no comparison
  touches it. This repo's whole percentile section is about an index landing
  on `n-1`, so this is the operator class that matters most here. A `+` flip
  on a string concat raises `TypeError` and lands in CRASHED — its own bucket,
  labelled *evidence of nothing*.

### T4, per gate

| gate | before | after |
|---|---|---|
| `percentile_floor_gate` | NO-ARM (8) | 7 killed, **0 live survivors** |
| `cfg_row_implication_gate` | NO-ARM (12) | 2 killed, **0 live survivors** |
| `trap_sentinel_gate` | NO-ARM (8) | 6 killed, 1 survivor (an I/O refusal path) |
| `markdown_fence_gate` | NO-ARM (5) | 1 killed, 3 survivors (1 EQUIVALENT, 2 in the git walk) |

Each needed a small extraction first, which is the finding underneath the
finding: the verdict arithmetic was **inline in `main()` alongside its own
error messages**, so it was unreachable by construction. `pin_failures`,
`verdict_problems` and `scan_text` are pure functions now, and `main` is the
shell it always should have been.

⚠ `percentile_floor_gate.pin_failures` gained a **refusal** in the process: a
pin key with neither a `max_` nor a `min_` prefix used to be silently
unchecked — a pin that asserts nothing, which is worse than a missing one
because it reads as coverage. Every live key already carries a prefix, so the
change is behaviour-preserving today.

### T3's backlog, and the 5 UNREACHED

`agents_repo_set_gate`, `bench_doc_audit`, `cfg_gated_floor_gate`,
`orphaned_attr_gate`, `required_features_static_gate` all have arms that kill
**zero** mutants under these operators. That is where T3 should start, and it
is NOT the same claim as "their arms are worthless" — `docs_gate_checks_sync`
has 20 hand-verified arms and kills 1, because its logic lives in regex
literals this harness does not mutate.

---


## How this was found

Issue 789 (closed hours before this file) made every `docs_gate.sh` CHECK
invoke a validation arm, and had to state one caveat out loud in its own gate's
docstring:

> ⚠ **What this does NOT assert:** that an arm EXISTS and RUNS is not that it is
> any good: an arm whose perturbation reds nothing certifies nothing … Arm
> QUALITY is not statically decidable and is not claimed here.

The first half is true and the second half is too strong. Quality is not
*statically* decidable — but **reach** is measurable by execution, and Issue 789
measured it 53 times by hand. **Seven of those arms certified nothing** until
they were re-aimed:

| the inert arm | why it reddened on nothing |
|---|---|
| `len_derived_drift_sweep` anchor | the perturbation string it searched for never appeared |
| `fenced_lines` fail-safe | its fixture had no TERMINATED block, so there was nothing for the discard to discard |
| `skill_repo_set_gate` lookbehind | aimed at the name's right side, where the trailing `/` already does the work |
| `docs_gate_checks_sync` sort | its input order already equalled the sorted order |
| `count_features` default discard | no `katgpt-core/default` entry, so the discard was unreachable |
| `population_sync_gate` canary (x8) | flag-gated — ran on no push at all (789 T2) |
| `fenced_blocks` family test | REDUNDANT: `.strip(open_ch)` already discriminates, so perturbing it reds zero arms |

That is roughly **13%** of hand-written arms reaching nothing, found only
because somebody sat and perturbed each one. A census done by hand is a census
that stops being done — the standing lesson of Issues 777-783 and 787, now on
its own instruments.

## What is actually measurable

Classic mutation testing, scoped small enough to be cheap. For each module:
mutate its source **outside** its own arm functions, re-exec, run its arm, and
ask whether the arm noticed.

Measured feasibility (2026-09-14, this box):

| | |
|---|---|
| mutable sites across the 21 CHECKS, excluding arm bodies | **436** |
| cost of one exec + arm run | **~3 ms** |
| estimated whole-population run | **under 10 s** |

Mutation operators are the ones that produced real findings by hand: comparison
flips (`==`↔`!=`, `<`↔`<=`, `>`↔`>=`, `in`↔`not in`), `and`↔`or`, dropping a
`not`, and flipping a boolean constant.

## The buckets, and why none may be pooled

- **KILLED** — the arm noticed. The only good outcome.
- **SURVIVED** — no arm distinguishes this line's behaviour. The finding.
- **NO-ARM** — the module has no arm of its own, so every mutant survives
  *vacuously*. Four CHECKS are in this state by design: `percentile_floor_gate`,
  `cfg_row_implication_gate`, `trap_sentinel_gate` and `markdown_fence_gate`
  **delegate** their arm to the classifier they import, which Issue 789 credits
  and should keep crediting — but a classifier's self-test **cannot reach its
  consumer's pin arithmetic**, which is the exact sentence Issue 775 wrote and
  Issue 789 generalised one level too shallowly. Pooling NO-ARM into SURVIVED
  would overstate; pooling it into KILLED would hide the 775 gap entirely.
- **CRASHED** — the mutant fails at import or raises before the arm runs.
  Trivially "noticed" and not evidence of anything; its own bucket.

⚠ **EQUIVALENT mutants are the known false-positive class.** A surviving mutant
may be semantically equivalent to the original (`>=` where the values can never
be equal), and mutating a line the arm is not *meant* to reach — `main()`'s
printing and exit shell — survives correctly. So the quantity is **arm REACH**
per function, not a quality score, and the exempt functions are pinned by
**membership with a reason**, exactly as Issue 789's own exemptions are.

## Tasks

- **T1** — `scripts/arm_reach_audit.py`: the report (exit 0, except a
  blindness floor). Population = tracked `scripts/*.py` with an arm, derived,
  not typed. Per-function SURVIVED rows with the mutation printed. Its own
  `--self-test` proving each operator fires and each bucket boundary holds
  against fixtures whose answer is known independently — the
  `wasm32_surface_audit` rule, which produced three confident wrong answers
  before a right one.
- **T2** — the verdict half for this repo, if and only if the SURVIVED count
  after a per-row read is small enough to WALL rather than ratchet. Decide from
  the measurement: a ratchet over a large backlog is what Issue 785 forbids.
- **T3** — read every SURVIVED row once and classify EQUIVALENT vs a real gap;
  repair the real gaps by widening the arm, and pin the equivalents by
  membership with a reason.
- **T4** — the NO-ARM four: decide per gate whether its own pin arithmetic
  earns a `gate_selftest` (the 775 shape) or whether delegation genuinely
  covers it. This is the question Issue 789's predicate was too weak to ask.

## Why a report and not a gate

Mutation reach is a *backlog* on first measurement, and a per-push gate over a
backlog is one people route around. It becomes a gate at T2, and only if the
number supports a wall. Same standing as `cfg_gated_target_audit.py` and
`percentile_index_audit.py`: the report stays runnable, the verdict half comes
after the corpus is read.
