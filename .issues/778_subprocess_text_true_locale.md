# Issue 778 — `subprocess.run(..., text=True)` decodes with the SYSTEM locale: mojibake, or `stdout = None` with rc 0

**Status:** OPEN

**Date:** 2026-09-14
**Source:** `citation_drift_sweep.py` crashed on the Windows workstation with
  `TypeError: expected string or bytes-like object, got 'NoneType'` — and the
  traceback was the *lucky* outcome.

## The defect

`text=True` decodes a child's pipe with `locale.getencoding()`. That is UTF-8
on macOS and on `ubuntu-latest`, so every CI lane and the M3 workstation are
immune. On this box the system locale is **cp874** (Thai ANSI), and the
instruments here all print `✓`, `✗`, `⛔` and em-dashes.

Measured, on `git log -3 --format=%s` over this repo's own commits:

```
raw bytes          b'... TRACKS \xe2\x80\x94 one walk ...'        (U+2014, em dash)
text=True          0xe42 0x20ac 0x201d      <- THREE cp874 chars, silent mojibake
encoding="utf-8"   0x2014                   <- correct
```

So there are two failure modes and the crash is the better one:

1. **Silent mojibake.** The bytes decode to *something* in cp874, the call
   returns rc 0 and a plausible string, and a caller matching
   `re.search(r"FAILED — (\d+) unqualified", r.stdout)` — an em-dash in the
   pattern, mojibake in the text — matches NOTHING and reads a **confident
   zero findings**. Nothing anywhere reports that the string was mangled.
2. **`stdout = None`, returncode PRESERVED.** Where a byte is undefined in
   cp874 (0x81-0x84, 0x86-0x8F, 0x98-0x9F, 0xDB-0xDE, 0xFC-0xFF) the decode
   raises inside `subprocess`'s reader THREAD. The exception dies in that
   thread, `run()` returns normally, and the caller gets
   `CompletedProcess(returncode=0, stdout=None)`. Measured on
   `citation_drift_sweep.gate_says()`: rc 0, stdout None, and only the
   subsequent `re.search` turned it into a visible failure.

`PYTHONIOENCODING=utf-8` does **not** fix it and makes mode 2 more likely: it
governs the CHILD's encoder, so the child correctly emits UTF-8 that the
PARENT then decodes as cp874. The variable this workspace's Windows runbook
already sets is the one that turns mode 1 into mode 2.

## Blast radius

**29 call sites across 16 scripts** carry bare `text=True`, and **zero** pass
an explicit encoding:

```
cfg_gated_floor_gate.py      citation_drift_sweep.py   citation_weight.py
ci_gate_coverage.py          docs_drift_sweep.py       feature_isolation_gate.py
highwater_contiguity_audit.py  issue_citation_gate.py  markdown_fence_gate.py
numbering_gate.py            required_features_build_audit.py
required_features_touched_gate.py  staged_set_audit.py
trap_exit_launder_audit.py   trap_launder_premise_matrix.py
wasm32_surface_audit.py
```

Most of these read `git` output, and **every commit message in this workspace
contains an em-dash**, so mode 1 is not hypothetical for any of them — it is
the normal case on this box, and it has been the normal case for every Windows
run of every one of these instruments.

This is the same shape as Issue 776 one axis over: an instrument carrying an
unstated PLATFORM premise, whose failure mode is a well-formed answer rather
than an error.

## Tasks

- [ ] T1 (P0) — Every `text=True` becomes `encoding="utf-8",
  errors="replace"`. `replace` and not `strict`: a parser that raises on one
  odd byte in a sibling's commit message is a new failure mode, and U+FFFD in
  a path is visible where mojibake is not.
- [ ] T2 (P1) — A docs-gate check: bare `text=True` in `scripts/*.py` is a
  ceiling of 0. The reason it needs a gate rather than a sweep-and-done is
  that the defect is invisible on every box that would notice it — macOS and
  `ubuntu-latest` are both UTF-8, so nothing in CI can ever red on it. Adding
  a check moves `docs_gate_checks_sync.py`'s count, the AGENTS.md table and
  both `docs_gate.yml` trigger lists, in the same commit.
- [ ] T3 (P1) — Re-run the affected instruments on this box and record which
  ones were reading mojibake. `citation_drift_sweep.py` is known (it crashed);
  the others returned plausible numbers and must be re-read, not assumed.

## Not in scope

Changing the box's locale. An instrument that only works under one `LANG` is
the defect; the box is the test case that found it.
