# Issue 838: a shell script spawning a NATIVE child is a third encoding seam, and it is measured at zero live instances — so it is deliberately NOT gated

**Status:** MEASURED and CLOSED-as-decided 2026-09-18. No instrument landed;
the measurement is the deliverable. Re-measure before reopening.
**Found by:** `katgpt-rs-54`, while adding the box-state block to
`scripts/x86_64_execution_matrix.sh`: a `·` inside a PowerShell format string
came back mangled through this box's cp874 console. Fixed there by keeping the
child ASCII and letting bash own the separators.

## The seam

This workspace already gates two encoding seams and this is neither of them:

| seam | instrument | what it reads |
|---|---|---|
| our own prints | `console_encoding_gate.py` | a tracked `scripts/*.py` printing a non-ASCII glyph with neither stream defended |
| a Python child's PIPE | `subprocess_encoding_gate.py` | `subprocess(..., text=True)` decoding with the system locale |
| **a SHELL script's native child** | **none** | a tracked `*.sh` handing non-ASCII to `powershell.exe`/`wmic`/`cmd.exe` and reading it back |

`console_encoding_gate` reads what *our scripts print*, not what a *spawned
process hands back*, and its `PYTHONIOENCODING` defence does not reach a child
of a bash script at all. `subprocess_encoding_gate` reads Python `subprocess`
call sites; a `.sh` file has none. So the seam falls between them.

## ⛔ Why there is no gate: the population is measured at ZERO

Tracked `*.sh` across the 16 contract repos on this box, lines invoking a
native child (`powershell`/`pwsh`/`wmic`/`cmd.exe`/`cscript`/`reg.exe`/
`systeminfo`/`tasklist`):

```
  197 tracked *.sh
   43 native-child invocation line(s)
    2 carrying non-ASCII on the same line  -> BOTH ARE COMMENTS
```

The two are `riir-ai/scripts/perf_rematch.sh:509` and
`riir-train/scripts/c13_auto_gate.sh:243`, and each is prose explaining the
call. **Live instances: 0**, the one real case having been repaired at source.

So a gate here would (a) govern an empty population and (b) need the same
comment- and string-masking machinery three other instruments in this repo
have already had to grow — to suppress the only two rows it can currently
find. That is a cries-wolf instrument by construction.

⚠ **This is the `check_validation_gate` T4 shape, and it is deliberately the
OPPOSITE of the `console_encoding_gate` mistake.** 789 measured a population
of one and declined a sweep, correctly. `console_encoding_gate` then *assumed*
that answer carried across and was wrong by seven repos. The rule both
episodes teach is the same: **measure the population, then decide.** The
measurement above is the whole point of this file — the next person to meet
this class should re-run it rather than re-derive it, and should reopen if it
is no longer 0.

## What to do instead, for now

- **Keep native children ASCII.** Let the shell own separators and glyphs;
  it is one line of discipline against a seam with no instrument.
- A non-ASCII glyph in a `.sh` **comment** is harmless and is not this class —
  any future predicate must mask comments, or its first run reports the two
  rows above.

## ⚠ Adjacent gap, NOT closed here

The three-seam table is about *encoding*. `scripts/x86_64_execution_matrix.sh`
now also spawns a native child to read box state, and its first version
selected the memory source on whether `/proc/meminfo` **existed** rather than
whether it **answered** — MSYS ships a readable `/proc/meminfo` carrying no
`MemAvailable`/`CommitLimit`/`Committed_AS`. That is the
[Issue 835](835_a_path_dep_on_a_repo_in_neither_set_is_enumerated_by_nothing.md)
`.git`-FILE shape one level over: *a predicate correct on every box without
the quirk, wrong on the one box the instrument exists for, failing in the
direction that reads clean.* Repaired there by selecting on whether a method
ANSWERS and printing WHICH one did. Recorded here only because the two were
found in the same change; the generalisable half lives in 835.
