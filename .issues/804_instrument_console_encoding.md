# Issue 804 (2026-09-16) — 28 instruments CRASH when run the way AGENTS.md says to run them

**Status:** RESOLVED 2026-09-16 — repair landed, and the cross-repo axis is
MEASURED and gated (see the bottom section), not deferred
**Severity:** MEDIUM — loud, not silent; but the consequence is that a whole
sweep's findings go **unread** on the only box that can run them
**Population:** tracked `scripts/*.py` with a `__main__` entry point that
print non-ASCII: **70**, of which **42 defend their stream encoding and 28 do
not** (measured 2026-09-16)
**Found by:** running the drift-sweep family end to end on the Windows
workstation — `restatement_drift_sweep.py` died at its first `✓`, and then
`pipefail_discard_audit.py` died at its own self-test's first `✓`

---

## The defect

Every instrument in `scripts/` prints `✓`, `✗`, `⛔`, `⚠` and em-dashes. On a
console whose encoding is not UTF-8 — the Windows workstation is **cp874** —
`print()` raises `UnicodeEncodeError` and the process dies with no verdict:

```text
  File ".../encodings/cp874.py", line 19, in encode
    return codecs.charmap_encode(input, self.errors, encoding_table)[0]
UnicodeEncodeError: 'charmap' codec can't encode character '✓'
```

`scripts/docs_gate.sh` exports `PYTHONIOENCODING=utf-8`, so every CHECK
survives *when the gate runs it*. Nothing protects the instrument when it is
run **directly** — which is exactly how AGENTS.md documents most of them:

```bash
scripts/percentile_index_audit.py ../riir-ai   # or one, by path
scripts/platform_dead_code_audit.py ../riir-ai
scripts/trap_exit_launder_audit.py ../riir-ai
scripts/pipefail_discard_audit.py              # every contract repo, on demand
```

⛔ **The wrapper is the reason this was invisible.** A per-push CHECK is
protected by `docs_gate.sh`; a workstation sweep or audit is not, and the
workstation sweeps are the ones whose whole purpose is to be run by hand on
the one box that has the workspace. So the class concentrates in exactly the
instruments with no automatic lane — the ones AGENTS.md already calls "found
by census and not by symptom".

## Why it is worse than a crash

`restatement_drift_sweep.py` is the specimen. It was the **one member of the
18-sweep family** without the defence, so it was the one nobody on this box
could run at all. Its findings — 4 repos, 19 `.lean`/8/26/15 files, 255
theorems — were not "unknown"; they were *unlooked at*, while the sweep
family was being reported as green. AGENTS.md's own rule for this shape:
**a sweep that always reds is a sweep nobody runs.** A sweep that always
*crashes* is the same thing with a worse error message.

## The population, measured

```text
tracked scripts/*.py            76
  in population (__main__ + non-ASCII)   70
  exempt (library-only or ASCII-only)     6
  defended                               42
  MISSING                                28
```

42 of 70 already carry the fix, verbatim, in `main()`:

```python
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="backslashreplace")
    except (AttributeError, ValueError):
        pass  # not a TextIOWrapper (embedded / detached); keep old behavior
```

So this is the **ninth** recorded instance of the shape AGENTS.md names over
and over: a rule landed in some instruments and never generalised, with no
mechanism to say which ones have it (Issues 777, 778, 793, 782, 783, 789,
797, 785).

## Why `backslashreplace` and not `encoding="utf-8"`

The console encoding is **not ours to choose** — forcing UTF-8 on a cp874
console produces mojibake in the terminal rather than an exception, which is
the silent direction. `backslashreplace` degrades `✓` to a visible `✓`
and keeps every ASCII character exact, so a verdict line stays greppable and
a reader can see that a glyph was substituted. It is also what the 42 already
do, so the repair is "finish the job", not "choose a new policy".

`PYTHONIOENCODING=utf-8` in a wrapper is a *third* answer and it is the one
that already exists; it is not sufficient, because it only covers invocations
that go through the wrapper.

## The repair

1. `scripts/console_safe.py` — the defence in one place, with the arms.
2. The 28 call it. The 42 that inline it are left alone: rewriting working
   instruments to import a 5-line helper is a larger diff and a larger risk
   than the duplication costs, and the gate below accepts either form,
   because the property it asserts is *the streams are defended*, not *this
   function was called*.
3. `scripts/console_encoding_gate.py` — a docs-gate CHECK, gated by
   **MEMBERSHIP** over the derived population, with two floors (the walk and
   the defended count — an empty population reds loudly, a population that
   quietly *narrows* prints a green). A new instrument that prints `✓` and
   forgets the defence reds on the commit that adds it.

## What it does NOT assert

That an instrument's output is *readable* on a non-UTF-8 console — it is not,
`✓` is worse than `✓`. The claim is only that the instrument **runs and
reports its verdict** rather than dying, which is the difference between a
finding being read and a finding not existing.

## Cross-repo — MEASURED 2026-09-16, and the answer is a sweep

~~⚠ **Unmeasured, deliberately.**~~ The paragraph this replaces was right
about the *reason to hesitate* and wrong to stop there. Its own citation —
`check_validation_gate`'s Issue 789 T4 — does not say *decline a sweep when
the exposure is local*; it says **re-measure the population before
answering**, and 789 earned its "no sweep" with a measurement that returned
ONE repo. That measurement was never taken here.

Taken, over the 16 repos on this box:

```text
16 contract repos · 159 tracked scripts/*.py · 144 in population
                   ·  73 defended · 71 UNDEFENDED

  riir-train            53 of 53 undefended
  riir-clippy            5 of  5
  riir-ai                4 of  5
  seal-remake            4 of  4
  seal-game-editor       3 of  3
  riir-dapps             1 of  1
  riir-mmorpg-examples   1 of  1
  katgpt-rs              0 of 72   ← the gate landed here and nowhere else
```

Seven repos, not one. So 789's answer does **not** carry across, and the
asymmetry was the tenth instance of the shape this issue's own text names.

⚠ **The exposure caveat SURVIVES the measurement**, and it is what sets the
pin design rather than what cancels the sweep. A cp874 console is this box's
property, not riir-train's; and riir-train's 53 rows are the same over-capture
`instrument_reachability_drift_sweep` measures on this *identical* walk — that
repo's `scripts/` is 61 of 61 unreachable plan-scoped one-offs
(`plan335_t7_decide.py`, `plan346_doc_pool.py`), and retro-fitting a stream
defence to a script whose whole life was one plan task is churn in a tree this
repo does not own.

So `scripts/console_encoding_drift_sweep.py` ratchets the **derivative**,
exactly as Issue 787 T6 resolved the identical shape:

- `max_undefended` pinned at each repo's measured count — the commit that adds
  ANOTHER undefended instrument reds, and the action is one line.
- katgpt-rs is the exception and the selftest ASSERTS it: `max_undefended`
  must be **0** there, because a ratchet would let a row land that the
  per-push gate's MEMBERSHIP wall refuses, and `min_population` must equal
  `console_encoding_gate.MIN_POPULATION` — same quantity, two files.
- Three floors, because the WALK and the PREDICATE break separately: an
  `ast.parse` regression takes the population to 0 over an unchanged walk and
  every ceiling then passes vacuously. ⚠ Both are vacuous in the eight repos
  with an empty population, which the run PRINTS rather than assumes away.
- The classifier is the gate's — `tracked_scripts`, `in_population`,
  `is_defended`, imported and never restated — and the sweep INVOKES
  `ceg.selftest()`, which is what makes "shared classifier" an assertion
  rather than an import statement.
- 9 canary arms, all red under perturbation: the ratchet, both floors, a new
  undefended row, an UNPARSED row (never folded into the pass column), an
  unpinned repo, an empty pin file, a malformed row.

**Not repaired here:** the 71 rows in seven sibling repos. Each is one line,
each has an owner, and none of those trees is this repo's to churn — the
ratchet is the strongest claim katgpt-rs can honestly make about somebody
else's tree. `riir-clippy/scripts/gen_dashboard.py` is the one worth doing
first by anyone reading this: it reads `git log --pretty=%s` across the
siblings and **every commit subject in this workspace uses an em-dash**, so it
is the one row already known to be live rather than latent (it was Issue 783's
specimen one axis over).
