# Issue 790 — an arm that exists and runs may still reach nothing

**Filed:** 2026-09-14 · **Status:** RESOLVED (T1–T4 + T6 landed; **T5 DECLINED on a measurement** — see below) · **Branch:** develop

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

## T6 (2026-09-15) — the BASELINE bucket, and the exec namespace

T5 stayed blocked (sandbox), so T6 went at the item T2 left behind: the
`--include-all` population, whose arm reach had never been measured because the
run was abandoned once at 7.5 minutes and written up as "budget hours".

**Measuring the cost first moved the answer twice, in both directions.** A
static census put `--include-all` at **55 modules / 2382 mutants**, and a
per-module arm timing (run each arm ONCE, multiply by that module's mutant
count) predicted **765s serial** — minutes, not hours, so the standing note was
wrong in the pessimistic direction. That prediction then under-predicted the
real run, for a reason the same measurement exposed.

### ⛔ Finding 1 — seven classifiers CRASHED on their own unmutated source

The per-module timing printed a verdict per module, and seven of them read
`CRASHED` at **0.000s/arm**: `platform_dead_code_audit`,
`len_derived_binding_audit`, `required_features_build_audit`,
`cfg_gated_target_audit`, `cfg_row_implication_audit`,
`all_ignored_target_audit`, `suite_membership_audit` — **796 of the 2382
mutants**, a third of the population, every one of them a vacuous verdict.

Every one failed at the same line, and it was the harness's:

```
AttributeError: 'NoneType' object has no attribute '__dict__'
    ns = sys.modules.get(cls.__module__).__dict__     # dataclasses
```

`run_arm` exec'd into a **bare dict** with `__name__ = "__arm_reach__"`, a name
nothing has registered, so `@dataclass` cannot resolve its defining namespace.
The seven are exactly the seven classifiers that model findings as a dataclass.
This is the **third** bucket-boundary defect in this instrument and the second
in `run_arm` — after the CRASHED-vs-KILLED phase split — and the pattern is the
same each time: *the harness reporting a property of itself as a property of the
code it judges.*

It was invisible to T1–T4 because **no module in the default CHECKS population
defines a dataclass**. `trap_sentinel_gate` and `platform_dead_code_floor_gate`
mention one, but they IMPORT it from their classifier through the ordinary
machinery. A boundary only the wider population crosses is a boundary the
narrow population cannot report.

`_exec_namespace` builds a real `types.ModuleType`, registers it, and restores
any prior entry — the audit exec's dozens of modules under one name and a leaked
entry would hand the next one somebody else's globals.

⚠ **The bare-dict direction is a PREMISE, not an assertion.** CPython ≤3.12
guards that lookup (`if cls.__module__ in sys.modules: … else: globals = {}`)
and 3.14 does not. The first arm written for this hard-asserted "the bare dict
dies", which would have red on the M3 — a premise harness that never varies the
axis it claims about, which is what `trap_launder_premise_matrix` exists to stop
doing. The self-test asserts only the positive (a `@dataclass` module EXECs in
the registered namespace), which is sufficient wherever the defect is live;
`dataclass_premise()` measures the other side and the report prints which side
this interpreter is on.

### ⛔ Finding 2 — BASELINE: an arm that already fails scores PERFECT reach

The same census showed three modules returning **KILLED on unmutated source**.
The harness had never asked. An arm that is already failing kills every mutant,
so the module reports 100% reach having distinguished nothing — and it does not
merely escape the gate's `MIN_KILLED` floor, it **inflates** it. The CRASHED
half is the milder twin: every mutant reads CRASHED and the row says nothing at
full price (the seven above were 796 such runs).

`audit_module` now measures the baseline FIRST. `BASELINE-RED` and
`BASELINE-CRASH` are module-level verdicts, the mutants are counted but **not
run**, and neither is pooled into KILLED, SURVIVED or `UNREACHED`. The last is
not fussiness: a BASELINE-bad row satisfies UNREACHED's arithmetic by accident
(`killed == 0`), and the two diagnoses have opposite remedies — UNREACHED says
*the arm cannot express this* and sends the reader to widen an arm that is not
the problem. The gate walls both at 0.

The three, adjudicated:

| module | why | verdict |
|---|---|---|
| `len_derived_drift_sweep` | its `canary`'s "baseline green" arm runs the REAL workspace and reds on `⛔ UNSEEN` | ENVIRONMENT — passes with `DOCS_GATE_PARTIAL_CLONE=1` |
| `instrument_reachability_drift_sweep` | same shape, same marker | ENVIRONMENT |
| `required_features_touched_gate` | **a genuinely broken arm** — see below | REPAIRED |

The first two are the reason the BASELINE message names the environment before
anything else: a sweep whose canary runs the real workspace makes its own
arm-reach verdict environment-dependent, and `--include-all` must be run with
the same markers the gates get.

### ⛔ Finding 3 — `required_features_touched_gate.selftest` was Windows-broken

Not environmental. Three of its eight selection cases (`target-source`,
`src-on`, `prefix`) were **unsatisfiable on Windows**, so the arm raised
`SystemExit(2)` every time anyone ran it on this box. `select()` matches with
`str(f)` and with `os.sep`; the fixture compared POSIX string literals
(`"/w/a/tests/t_a.rs"`) against a `Path`, which stringifies with backslashes.
Every fixture path is built through `Path` on **both** sides now, which is
behaviour-identical on POSIX.

⚠ The PRODUCTION path was never affected — `changed_files` resolves through
`(repo / ln).resolve()`, so both sides are native there. But an arm that cannot
run on a developer box is an arm that stops being run, and this one had been
silently unrunnable on half the workstations since it was written. **It was
found by a harness looking for something else**, which is the argument for
running `--include-all` at all.

### ⛔ Finding 5 — a mutant that never RETURNS, and the hang is the mild half

The `--include-all` run this task exists to take was still burning 98% of a
core at **two hours**, against a 13-minute prediction. It was not slow. One
mutant of `restatement_theorem_audit` — `+ -> -` at `parse_def`'s
`name = toks[kw + 1]` — feeds a downstream loop that then never exits, and
`run_arm` had **no bound of any kind**.

⛔ **Interrupting it without a bucket is strictly worse than the hang.** A
watchdog raises `KeyboardInterrupt`; `except BaseException` in the arm phase
reads that as *the arm noticed*; the non-terminating mutant is credited
**KILLED**. That is the fourth distinct way this instrument has produced a
false-perfect, and the only one where the fix would have introduced it.

`TIMEOUT` is its own verdict with CRASHED's standing, the flag is checked
before the kill, and the rows are named individually so a reader can go look.
The deadline is **derived** — 10x the module's own baseline arm, floored at
30s — because one typed constant cannot mean the same thing to a 0.03s gate
and an 8.3s workspace sweep. Measured: 127 mutants, previously unbounded, now
**33s with exactly 1 TIMEOUT**.

⚠ The watchdog is a `threading.Timer` + `_thread.interrupt_main()`, not
`SIGALRM`, which is POSIX-only while this workstation is Windows. It reaches a
pure-Python loop and **not** a blocking C call, and there is a narrow race
where a timer fires just after the arm returns — `audit_module` catches that
too, so the worst outcome is one adjacent mutant mislabelled TIMEOUT, never a
false KILL and never a hang. A subprocess per mutant would be airtight at
~2400 interpreter starts; naming the 10% the cheap version misses is the
point of writing it down.

⚠ And the cost prediction that started T6 was **invalidated by the defect it
found**: the per-module arm timing measured the seven dataclass modules at
0.000s/arm *because they crashed*, so the 765s figure was computed over a
population a third of which was not running at all. Read it as the lower bound
it turned out to be.

### ⛔ Finding 6 — two more Windows-unrunnable instruments, one of them PRODUCTION

`required_features_build_audit` read **BASELINE-RED**: its `selftest` raised
`AttributeError: module 'os' has no attribute 'statvfs'`. That is not an arm
defect — `free_gib` is production code, so **the entire module was unimportable
on Windows**, and with it `disk_headroom_ok`, the REFUSE that keeps the report
from filling a disk. Repaired with `shutil.disk_usage(...).free`, the same
quantity `f_bavail * f_frsize` computes and cross-platform. It now measures
**55 killed / 58 live of 117** where it previously measured nothing at all.

Generalised rather than fixed in place, per this repo's own standing lesson: a
workspace-wide sweep for POSIX-only Python (`os.statvfs`, `os.getuid`,
`os.fork`, `signal.SIGALRM`, `fcntl`, `termios`, `pwd`, `grp`, `os.uname`) over
every tracked `*.py` in all 16 repos found **no other live call site** — only
the comments explaining these two. The class is closed, and the sweep is the
evidence rather than the assumption.

### ⛔ Finding 7 — NO-ARM vs UNREACHED, decided twice and differently

`restatement_drift_sweep` defines exactly one arm, `prove_fires`, which is
never invoked. `audit_module` handled that correctly. The REPORT did not: it
asked `if not r["arms"]`, which is False for a module whose only arm is
`prove_fires`, so the row rendered as **UNREACHED** — *"this arm killed
nothing", remedy: widen the arm* — when the truth is **NO-ARM** — *there is no
arm, remedy: write one*. The gate's `classify` had it right the whole time.

Issue 755's shape exactly: **a rule expressed twice is a rule that will be
expressed differently.** One predicate now, `has_runnable_arm`, armed on the
`prove_fires`-only case in both directions.

### ⛔ Finding 8 — the blocking-C-call wedge has a MECHANISM, and it is the box

The TIMEOUT watchdog's documented blind spot — "reaches a pure-Python loop and
NOT a blocking C call" — stopped being hypothetical the same day. Two runs
wedged at **~3.5% CPU with no direct children** and the watchdog thread alive
with an undeliverable interrupt: one at 36 minutes, one at 2 hours.

The mechanism is not in this instrument. The workstation carries **167 live
`git.exe` processes, ten of them 117 hours old**, all at ~0 CPU. They hold the
write end of pipes a Python parent is still reading, so `subprocess` blocks
forever — and it looks like "slow", not "wedged", because there is no child
left to point at.

Two consequences, and the first is the one to carry forward:

1. **Drive any workspace-wide Python run module by module under an EXTERNAL
   `timeout`.** In-process watchdogs cannot see this class at all. The
   per-module walk covered 53 of 55 modules in ~35 minutes and lost exactly one
   module when a wedge was killed, against two abandoned whole-run attempts
   that produced nothing.
2. `len_derived_drift_sweep` and `platform_dead_code_audit` are the **2 of 55**
   this box could not measure. They are reported UNMEASURED rather than folded
   into any bucket — a report whose population shrank silently is the blindness
   this whole family of instruments exists to refuse.

### ⚠ Finding 9 — a starved box makes a gate report FINDINGS, not an error

Landing T6 left the workstation resource-starved (see Finding 8), and the docs
gate then failed **2 of 21** on a tree that had just passed. Both were
environmental and both passed on re-run in isolation, but they failed
*differently* and only one of them was honest:

- `cfg_gated_floor_gate` died with `OSError [WinError 1450] Insufficient system
  resources` out of `os.path.realpath`. Unmistakable.
- `bench_doc_audit` printed **`checked 97 labels, 56 mismatches`** — a
  well-formed verdict, a plausible number, and completely wrong. On re-run:
  **97 labels, 0 mismatches.**

⚠ The MECHANISM is inferred, not measured, and is recorded as such: the audit
compares doc labels against the Cargo default closure, so manifest reads that
fail would empty the closure and make every `on by default` label mismatch —
the loud direction. **The quiet direction is the one to worry about**: had the
*docs* side failed to read instead, it would have checked 0 labels and printed
a confident green, and `checked 97 labels` is the only thing in the output that
would have shown it. The audit does print that population; nothing gates it.

Candidate repair, NOT landed here because the mechanism is unverified: a label
FLOOR, the same blindness detector every sweep in this family carries. Worth
one measurement before writing.

#### RESOLVED 2026-09-15 — the measurement, and it refutes both halves above

One forced failure mode at a time, against this repo's real tree:

| forced failure              | verdict printed                    | exit |
|-----------------------------|------------------------------------|------|
| every `.md` read raises     | `checked 0 labels, 0 mismatches`   |  0   |
| every manifest read raises  | `checked 0 labels, 0 mismatches`   |  0   |
| 10% of manifest reads raise | `checked 97 labels, 1 mismatches`  |  1   |
| 50% of manifest reads raise | `checked 97 labels, 24 mismatches` | 24   |

⛔ **The manifest direction is not loud.** An empty default closure makes every
label UNRESOLVABLE rather than mismatched, so it prints the same confident green
the docs direction does — two silent zeros, not one and one.

⛔ **And the proposed floor would not have caught the run that was observed.**
A PARTIAL read keeps the label count at its full 97 and corrupts only the model
the labels are judged against; the observed verdict sits above any floor
calibrated on 97, every time. The floor bounds the TOTAL failures and is
necessary; it is not sufficient, and writing it alone would have closed this
finding while leaving the actual failure standing.

Landed (`30f6c523`): `BlindRead` aborts on an `OSError` over a file the walk
just listed — exit **2**, never 1, because `1` means "mismatches were found"
and an instrument that could not read has found nothing. A `TOMLDecodeError`
keeps its warning; that is real content to walk past. Plus the two floors
(`MIN_DOCS` the walk, `MIN_LABELS` the read+tokenizer over a full-size walk),
and the verdict line now carries its population: `checked 97 labels over 439
doc(s)`.

⚠ The census hazard bit while MEASURING, which is worth more than the finding:
the first pass patched `Path.read_text`, reported the manifest direction CLEAN,
and had never touched it — manifests are read with `cargo.open("rb")` +
tomllib. A measurement over one representation is blind to whatever that
representation omits (Issue 787's lesson, in a two-line harness).

Arm reach on the module: 9 live survivors → 3.

### ⛔ Finding 4 — the gate caught the commit that changed it

The `if r.get("baseline", …) != A.BASE_OK:` branch added to `measure()` read
**UNPINNED** on the very next run. That is T4's pattern once more: the bucket
DECISION sat inline in `measure()` between two calls into the audit, so it was
unreachable by construction. Extracted to `classify(row) -> str` — pure, armed
in both the per-bucket direction and the ORDER direction (a `BASELINE-RED` row
with `killed == 0` must not read UNREACHED; `NO-ARM` must precede BASELINE).

Four pins in `measure()` went stale in the same commit and were removed with it,
and four NEW survivors appeared — the `if bucket == "…"` dispatch. The tempting
move was to pin those as I/O shell. They are not: one real
`measure(only=["markdown_fence_gate"])` costs 0.6s and reaches all four, because
each flip mis-routes a healthy row into a bucket that shows up in the return
value. **Pinning a row an arm can reach for 0.6s is a backlog wearing a pin**
(Issue 785) — the same adjudication T2 had to make about a third of its 47.
The arm asserts the ROUTING and deliberately not the survivor SET, which
changes whenever somebody arms a module.

## T5, re-examined after T6 — half the blocker is gone, and the shape changed

T5 was blocked on "a sandbox story", because all eleven existing sweeps are
STATIC readers and this one would **execute** ~700 mutated copies of another
repo's gate scripts. Two of the three worries T6 answers directly, and the
third got worse.

1. **Concurrent writers and stray writes — answered by `git archive`.** The
   `--prove-fires` idiom already in `platform_dead_code_drift_sweep` and
   `check_validation_gate` extracts a FROZEN tree into a scratch directory.
   That gives a snapshot immune to the sibling's in-flight worktree, and
   relative writes land in scratch.
2. ⛔ **"Its arms may read metrics blobs" — answered by BASELINE, which did
   not exist when T5 was written.** A `git archive` tree carries tracked files
   only, so a script whose arm needs an untracked artifact fails, or fails to
   import, on its own UNMUTATED source. Before T6 that was the dangerous case:
   it would have scored **100% KILLED** and reported perfect reach for a repo
   the sweep could not actually measure. Now it is `BASELINE-RED` /
   `BASELINE-CRASH` — counted, never pooled, never a pass. **The bucket that
   makes executing foreign arms safe to INTERPRET is the one T6 landed.**
3. ⚠ **What is left is an ADMISSION question, and it is static.** A scratch
   tree does not contain an absolute path, a `..` traversal back into the real
   workspace, or a `cargo`/network spawn. Those are readable from the AST
   before anything runs, and the answer is a bucket in this repo's own idiom:
   `UNSAFE-TO-EXECUTE`, reported, never folded into a pass — the
   `UNRESOLVED is not clean` rule, one axis over.

⛔ **But the COST measurement moved the design, and it is the open question
now.** T5 assumed "~700 executions" was the scary number. T6 measured this
repo's own 55-module `--include-all` at **hour-class** on a quiet 16-core box —
not because there are many mutants, but because a sweep's arm is a
workspace-wide 16-repo walk and **every mutant pays one**. A workspace sweep
over 18 arm-bearing sibling scripts is therefore not a sweep-shaped thing at
all: it cannot run on demand next to the other eleven, and a "sweep" nobody can
afford to run is the failure mode this repo has now recorded a dozen times.

So T5's honest next step was **not** "write the sweep" but to run the
admission classifier over the sibling population first, and decide between a
per-repo on-demand tool and a sweep over the ADMITTED subset.

### The measurement (2026-09-15) — the subset sweep is REFUTED

A static screen over every tracked, arm-bearing `scripts/*.py` in the
workspace, flagging what a `git archive` scratch tree cannot supply — absolute
paths, `..` traversal out of the tree, `subprocess` spawns, `cargo`-class
children, file writes:

| repo | arm-bearing | mutants | flag-FREE |
|---|---|---|---|
| riir-train | 14 (all `planNNN_*`) | 577 | 1 |
| riir-clippy | 1 | 148 | 0 |
| riir-ai | 2 | 56 | 1 |
| **sibling total** | **17** | **781** | **2** |

⛔ **Two of seventeen are admissible.** A sweep restricted to the admitted
subset would derive a population of **2** and print a confident green over it
— which is the population-of-ONE argument Issue 789 T4 used to decline its own
sweep, and the reason `ci_gate_coverage.py` is kept out of the CHECKS set. The
subset option is refuted, not deferred.

⚠ The screen OVER-captures by construction and is quoted as a screen, not a
verdict: `ABS` fires on any string starting with `/` and `HEAVY` on any string
containing `cargo`, comments included. The load-bearing columns are **WRITE
(8 of 17)** and **SPAWN (3)**, which no amount of tightening removes.

⚠ The population itself is **17 today, not the 18** T5 measured a day earlier
(riir-ai 2, not 3) — a reminder that the sibling count is a claim and not a
checksum.

And the remaining option is weakened by the same table: **577 of the 781
sibling mutants are in riir-train `planNNN_*` scripts**, which
`instrument_reachability_drift_sweep` already measured as plan-SCOPED one-offs
where this class of predicate over-captures. So the sweep would spend ~74% of
its budget on scripts whose whole life was one plan task.

### Resolution: T5 is DECLINED, on a measurement, not blocked

No sweep half. What the measurement supports instead is the modest thing: the
report should accept a repo path so an owner can run it on their own tree, on
demand, in the repo where the arms and their fixtures actually live. That is
**not** landed here — executing another repo's code needs the archive and the
admission bucket, and neither earns its keep for a 2-module admitted set.

**Do not add a sweep here by symmetry with the other eleven** — the same
sentence Issue 789 T4 had to write, for the same reason, one instrument over.

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

  ⚠ **RESOLVED — see "T5, re-examined after T6" above: DECLINED on a
  measurement (2 of 17 sibling scripts admissible), not blocked.** The
  original analysis follows.

  ⚠ **Both were measured before building anything, and both answers moved.**

  1. **The population's SHAPE, not its size, is the finding.** All 14
     riir-train scripts are `planNNN_*.py` — and they are not trivial one-offs
     (`plan341_ab_gate.py` is 579 lines and returns a pre-registered gate
     verdict), they are **plan-SCOPED**: substantive decision code whose whole
     life is one plan task. riir-ai's 3 and riir-clippy's 1 are ordinary
     standing instruments. So the honest split is **4 instruments + 14
     plan-scoped**, which is `instrument_reachability_drift_sweep`'s shape
     exactly, and the answer it reached applies: constrain the **DERIVATIVE**
     (the commit that adds another unreached decision line reds) and leave
     existing rows to their own repo to adjudicate. A wall is wrong here.
  2. ⛔ **This sweep would EXECUTE other repos' code, and all eleven existing
     sweeps are STATIC.** They read files. This one mutates a module, `exec`s
     it, and runs its arm — 14 riir-train plan scripts × ~50 mutants is ~700
     executions of someone else's gate scripts, whose arms may read metrics
     blobs or write artifacts, in a repo another agent writes concurrently.
     That is a material architectural difference from the family, not a
     mechanical copy of it, and T5 is BLOCKED on a sandbox story (a
     `git archive` of the sibling into a scratch tree, the `--prove-fires`
     idiom one axis over?) rather than on effort. **Do not land it by symmetry
     with the other eleven.**
- **T6** — ✅ **LANDED.** The `--include-all` population, measured. Four
  findings, three of them defects in things that were already green: the exec
  namespace (796 mutants reading CRASHED for a harness reason), the missing
  BASELINE bucket (an already-failing arm scores PERFECT), a Windows-broken arm
  in `required_features_touched_gate`, and this gate catching its own new
  branch. See the T6 section above.
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
