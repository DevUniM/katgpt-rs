# Issue 804 (2026-09-16) — 28 instruments CRASH when run the way AGENTS.md says to run them

**Status:** OPEN
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

## Cross-repo

⚠ **Unmeasured, deliberately.** The population question ("does this repo have
instruments that print non-ASCII?") plainly generalises, but the *exposure*
does not: it needs a non-UTF-8 console, and this workstation is the only box
in the workspace known to have one. Whether a sweep half is worth having is a
measurement somebody should take (`scripts/*.py` counts: riir-train 58+,
riir-ai 7, riir-clippy several) and not an answer to assume from symmetry —
`check_validation_gate`'s Issue 789 T4 precedent, where re-measuring the
population is what said "no sweep".
