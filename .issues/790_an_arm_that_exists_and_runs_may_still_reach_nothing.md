# Issue 790 — an arm that exists and runs may still reach nothing

**Filed:** 2026-09-14 · **Status:** OPEN (T1–T4 landed; **T5, the sweep half, remains**) · **Branch:** develop

## Progress

**T1 landed** (`ee0961e4`) — `scripts/arm_reach_audit.py`, 27 self-test arms,
documented in AGENTS.md. **T4 landed** — all four NO-ARM gates now carry a
`gate_selftest` over their own pin arithmetic, so **NO-ARM is 0**.

Standing after T2 (2026-09-15): **22 modules · 552 mutants · 157.6s · 360
KILLED · 31 SURVIVED (live) · 0 CRASHED · 0 NO-ARM · 0 UNREACHED**, every live
survivor pinned with a reason. (After T3/T4 it was 21 modules · 519 mutants ·
317 KILLED · 47 SURVIVED; T2 closed 16 of the 47 as real gaps.)

⛔ **The first post-T4 figure was `127 KILLED · 112 CRASHED · 5 UNREACHED`, and
the CRASHED column was a DEFECT IN THIS HARNESS rather than a property of the
gates.** `run_arm` wrapped the module `exec` and the arm CALL in one `try`, so
an arm that signals by RAISING — `required_features_static_gate.selftest`
returns `None` and raises `SystemExit(2)`, and others do the same — had every
mutant it caught filed as CRASHED, and those modules could never show a KILL
at all. The phases are separate now: an import failure is CRASHED (*evidence of
nothing*), a raise while the arm runs is KILLED (the arm noticing). 127 → 243
killed, CRASHED to 0, UNREACHED 5 → 1. **The harness was blaming the gates for
its own bucket boundary** — the third time in this instrument that a bucket
boundary WAS the finding.

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

### T3 so far — UNREACHED is 0

Of the six modules that read UNREACHED, **five were the CRASHED misfiling
above** and one was a genuine gap: `required_features_static_gate`'s pin
READER, whose line filter (`not line or "=" not in line`) and REQUIRED_PINS
completeness check had no arm at all. The pin reader is load-bearing in the
quiet direction — a filter that drops a real row, or a completeness check that
passes on an incomplete file, hands `main` a dict with a missing key and the
gate then compares a measurement against nothing. Both refusal paths are
pinned now, with their own `✗` output SWALLOWED and merely asserted to have
been said.

### T3, read module by module: 123 -> 47

Final standing: **519 mutants · 317 KILLED · 47 SURVIVED (live) · 155 in exempt
functions · 0 CRASHED · 0 NO-ARM · 0 UNREACHED**, with **9 of 21 modules at
zero live survivors**.

**The pattern, in every single module: the CLASSIFIER was well armed and the
VERDICT was not.** `bench_doc_audit` had fixtures drawn from real workspace
shapes for its reachability model AND a `TOKENIZER_CASES` table for its line
grammar — and nothing whatsoever for the function that joins them, where 17 of
its 44 survivors sat. `cargo_comment_audit` had a 20-arm precedence ladder and
nothing for the scope choice that consumes it (19 of 21 survivors).
`issue_citation_gate` had 39 arms and none on `ci_deferred`, the line it prints
on every partial-clone and CI run (8 of 16). All three take a repo path, so
every one was armable the entire time.

Six of my own arms were degenerate and were re-aimed, all the same shape — a
fixture whose values are SYMMETRIC under the mutation it targets:

| the inert arm | what discriminates it |
|---|---|
| 1 local + 1 cross-repo citation | 2 and 1 |
| a single-digit citation HEAD (`1-0 == 1+0`) | the list TAIL form |
| `f"{n} single-digit"` as a substring | `-1 single-digit` contains it; anchor on `INSTRUMENT: ` |
| a two-def file for a span computation | THREE defs, walk in the middle |
| a 3-hop closure for an iteration bound | a pure chain — and then a PROOF that no graph discriminates it |
| every floor driven to pin MINUS ONE | the value exactly AT the pin |

⚠ Three fixtures also failed against perfectly correct code until a real
asymmetry was understood: `find_cargo_defaults` (the UNION closure) resolves
through the package graph and returns an EMPTY set for a manifest with no
`[package] name`, while the per-manifest closure reads the same file fine. It
is pinned as its own arm now, in both files that build fixture manifests.

**The 47 that remain are characterised, not unread**, and each is documented at
the line it lives on. Three classes: provably EQUIVALENT redundant guards (a
`find() < 0` whose search starts after an earlier match; a set membership test
`or`-ed with another; a `last < 0` sentinel that is never 0), the
**git/subprocess I/O shell** an arm cannot enter without spawning the auditor
it reads, and message-formatting arithmetic. Do NOT read 47 as a defect count.

⛔ **The paragraph above is SUPERSEDED — see the T2 section.** "Characterised,
not unread" was true of the reading; it was not true of the classification.
About a third of those 47 were real gaps wearing an EQUIVALENT label, and that
only surfaced when T2 tried to write one defensible sentence per row.

⚠ Wall clock moved **~73s -> ~370s** across T3, and that is the arms working:
several gates now build fixture repos per mutant. The price of reach.

---


### T2 — the verdict half, and what writing the reasons found

⛔ **T3's three-class characterisation of the 47 was TOO GENEROUS, and the way
that surfaced is the transferable part.** A pin file demands one sentence per
row. For about a third of them the sentence could not be written: they were
plain functions over plain data — `_parse_feature_spec`, `parse_status_phrase`,
the `local_default_closure` walk, the three manifest READERS that decide which
packages enter the model at all, `_tracked_manifests`' two fallback returns —
with no fixture repo and no subprocess between an arm and the decision. They
were **real gaps wearing an EQUIVALENT label**. Pinning them would have been a
backlog wearing a pin, which is exactly what Issue 785 forbids.

**Writing the reason IS the adjudication.** A classification made while reading
a list is a different act from one made while defending each row in writing,
and only the second catches this. **47 → 21** in the original population (the
final pin file holds **31**: those 21 plus the 10 in the gate's own `measure()`,
which joins the population because the gate gates itself):

| module | before | after | what closed it |
|---|---|---|---|
| `bench_doc_audit` | 23 | **3** | `pure_rule_arms` + `manifest_reader_arms` + 4 end-to-end fixtures |
| `cfg_gated_floor_gate` | 4 | 2 | `sole_row` EXTRACTED from `measure()` (and it was written twice) |
| `markdown_fence_gate` | 3 | 1 | a throwaway git repo with a tracked-but-DELETED `.md` |
| `skill_repo_set_gate` | 3 | 2 | the `len(derived) > 1` blindness guard at its exact boundary |
| `trap_sentinel_gate` | 1 | **0** | `load_audit` took a `path` parameter |

Two repairs are worth carrying forward as patterns rather than fixes:

- **`cfg_gated_floor_gate.sole_row`** — the one-row refusal sat inline in
  `measure()`, between two `subprocess.run` calls, written TWICE. Extracted, it
  arms in three lines. This is T4's finding again ("the verdict arithmetic sat
  inline in `main()` beside its own error messages, unreachable by
  construction"), and the DRY win came free with the reach.
- **`trap_sentinel_gate.load_audit(path)` but NOT
  `platform_dead_code_floor_gate.load_audit`** — the two look identical and the
  answer differs. trap_sentinel's probed path is the one
  `spec_from_file_location` receives, so an arm tests the real thing.
  platform_dead_code probes a path and then imports by NAME through `sys.path`
  (deliberately: a dataclass-bearing module must be in `sys.modules`), so
  parameterising its probe would assert a refusal for a path it does not then
  load. Same shape, different code, different verdict — the row is pinned with
  that argument rather than armed.

⚠ One arm was WITHDRAWN rather than written: `find_own_crate_defaults` has no
`[package] name` guard at all, so it unions an unnamed manifest's defaults —
an asymmetry against `own_closures_by_pkg`, and the mirror image of the one
AGENTS.md records for `cargo_comment_audit.find_cargo_defaults` (which returns
EMPTY there). Neither behaviour is reachable: a `[features]` table with no
`[package]` is not valid cargo, and a virtual workspace manifest may not carry
features. Asserting either direction would cement an arbitrary answer to a
question no input can ask, so the omission is documented at the line instead.

#### The gate

Key design points, each forced by a measurement rather than chosen:

- **The key is LINE-FREE** —
  `<module>::<function>::<op-token>::<8-hex digest of the line TEXT>#<n>`, with
  the ordinal scoped to the WHOLE address (`len_derived_eyes_expected.txt`'s
  precedent). A line NUMBER drifts on every edit above it, and a pin file that
  reds on noise is one people delete. Two rows legitimately share an address:
  three `+` on one `print`, two `True` kwargs on one `subprocess` line.
- The digest is unreadable, so each row carries its source line in a `#= `
  comment **which the gate verifies against the observed text**. A comment
  nothing can red is a comment that drifts into a lie. ⚑ It earned its keep on
  the FIRST real run: the membership wall was clean (31 pinned = 31 observed)
  and the only failure was a hand-copied comment missing its trailing `:`.
  Without the check that row would have read, to every future human, as a line
  that is not the line it pins.
- **It gates ITSELF.** Not symmetry — an exempt gate certifies nothing
  (`subprocess_encoding_gate`'s rule). The first self-hosted run immediately
  found a degenerate arm in its own key builder: the ordinal counter's `+ 1`
  flipped to `- 1` yields `#-1`/`#-2`, still two distinct keys, so the
  count-only assertion read green. The ordinal VALUES are asserted now.
- **The two permissive sets are pinned by membership** — `EXEMPT_FUNCTIONS`
  and `ARM_NAMES` both live in the audit and SHRINK the finding set when they
  grow, and no floor notices. Adding `main` to `ARM_NAMES` would look like a
  tidy-up.
- Three floors: `MIN_MODULES` the walk, `MIN_MUTANTS` the operators,
  `MIN_KILLED` the **runner** — a runner reporting KILLED for everything empties
  the survivor set, reds every pin as "no longer survives", and the obvious
  remedy is to delete them all.
- **No `--prove-fires`**, and that is a cost measurement: the known-answer
  validation would be a full mutation run over a `git archive`d tree, minutes
  per invocation, to re-derive a fact this file already records. The 16 canary
  arm groups carry it instead.
- **Not a `docs_gate.sh` CHECK** — minutes against a ~13s budget. Workstation
  verdict, same standing as the eleven drift sweeps, reachable from AGENTS.md
  so `instrument_reachability_gate` counts it.

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
- **T2** — ✅ **LANDED.** `scripts/arm_reach_gate.py` +
  `scripts/arm_reach_survivors_expected.txt`. The answer was neither a wall on
  the count nor a ratchet: it is **MEMBERSHIP with a reason per row**, walled at
  **0 UNPINNED**, which is this repo's own rule for `cfg_gated_floor_gate` —
  *a set is gateable where its cardinality is not.* `UNREACHED` and `NO-ARM` are
  walled at 0 separately. See the T2 section below.
- **T5** — the SWEEP half, now owed. Issue 789 T4 declined a sweep on a
  measurement (population of ONE: katgpt-rs is the only repo with a
  `docs_gate.sh` CHECKS array) and the instinct was to carry that answer
  across. Re-measured for ARMS rather than CHECKS, it does not transfer:
  **18 arm-bearing `scripts/*.py` across three sibling repos** — riir-train 14
  of 58, riir-ai 3 of 7, riir-clippy 1 of 5. That is a real population and the
  class generalises. ⚠ Two things to settle first, both measured rather than
  assumed: the per-repo COST (this repo alone is minutes, and riir-train has
  58 scripts), and whether the ceiling can be a wall there or must be a
  RATCHET — `instrument_reachability_drift_sweep` found riir-train's
  `scripts/` is almost entirely plan-scoped one-offs, where the predicate
  over-captures, and the same is likely true of arm reach.
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
