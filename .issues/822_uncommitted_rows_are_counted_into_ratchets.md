# Issue 822 (2026-09-17) — an UNCOMMITTED row is counted into a RATCHET, and one just breached a pin over a file that exists in no commit

**Status:** OPEN
**Severity:** a sweep reds on another session's in-flight edit; the obvious remedy is to re-pin from it
**Owner:** unassigned — filed with the measurement, not started

## The finding

Issue 797 established the split and stated it as a rule:

> **UNCOMMITTED** — the worktree carries a row HEAD does not. **Displayed**
> (it is what the file says today, and hiding it would be its own lie) but
> **never adjudicated against a pin**. The split of responsibility, once: the
> DISPLAY reads the worktree, the PINS read HEAD.

and then wired it into exactly one sweep, for a reason it wrote down:

> The row-level UNCOMMITTED/MASKED split is wired into `citation_drift_sweep.py`
> alone, because it is the one whose findings carry a `file:line` address and
> the one where the class was measured.

The first clause of that reason has since stopped being true. `console_encoding`,
`subprocess_encoding`, `platform_dead_code`, `instrument_reachability`,
`orphaned_attr` and `len_derived` all carry **file-addressed** rows. The second
clause is what this issue is: the class has now been measured somewhere else.

## Measured, 2026-09-17

`console_encoding_drift_sweep.py`, riir-train row, both markers set:

    ✗ riir-train   walk=61  pop=56  defended=0  undefended=56
          ✗ undefended 56 > pinned 53 — a new instrument that prints a
            non-ASCII glyph and defends neither stream

56 − 53 = **3**, and the three newest rows in that repo are exactly:

| row | state in riir-train |
|---|---|
| `scripts/plan402_gguf_probe.py` | **`A ` — staged, in NO commit** |
| `scripts/plan403_fetch_lph_corpus.py` | committed today (`1939fe3c`) |
| `scripts/plan403_modelless_floors.py` | committed (`26128ecb`), **modified uncommitted** |

So the breach is **at most two** real committed findings, and it is reported as
three. One row sits on a file `git log` cannot see at all, authored by a
concurrent session that is mid-commit in that worktree right now — its index
carries staged `crates/` work as well.

⚠ This is the shape Issue 797 measured for citations and warned about for
floors, reached through a **ratchet** instead: *"A floor or ratchet re-pinned
from such a run bakes another session's in-flight edit into a tracked
expectations file, where it reds on every other box."* The pressure to do
exactly that is real — the sweep says 56, the file says 53, and typing 56 is
one keystroke. Nothing in the run distinguishes the case.

⚠ It compounds with the STALE axis (Issue 798), which fired on the same run:
riir-train is 10 commits behind origin with 8 in this sweep's population. So
the number 56 is a function of one box's checkout **and** one session's
uncommitted index, and it is being compared to a tracked constant.

## Why the advisory does not cover it

`sweep_advisory()` is wired into all 19 sweeps and it fired correctly here —
it named riir-train. But it is a **repo-level** banner that says "some files
differ from HEAD". It cannot say *which finding* is affected, and on a run with
56 rows and a 3-row breach that is not enough to act on: the reader still has
to decide whether to re-pin, and the banner gives them no way to tell.

## Proposed tasks (not started)

- [ ] **T1** — re-measure the population first, the Issue 789 T4 discipline.
      Which sweeps have file-addressed rows AND a count-based pin? A sweep
      whose pin is a MEMBERSHIP set is already immune (a new uncommitted row
      reds by name, and the name is the diagnosis), so this may be a smaller
      set than the family.
- [ ] **T2** — lift `worktree_state.split_rows`'s injected-`read` pattern into
      a shared helper those sweeps can call with their own row->path function.
      `citation_drift_sweep` re-runs its whole classifier against HEAD blobs;
      whether that is affordable for a 2415-file Rust walk is **unmeasured**
      and is the first thing to find out — the answer may be that only the
      FINDING paths need re-reading, not the whole tree.
- [ ] **T3** — the count must stay honest in both directions. Report
      `undefended 56 (53 committed + 3 uncommitted)` and adjudicate the
      committed number. Do NOT hide the 3: hiding them is the lie 797 refuses.
- [ ] **T4** — MASKED is the silent direction and is still **0 by
      measurement, not by absence of the class** — a committed defect the
      worktree hides. Any wiring must report it.

## Not in scope

- **Repairing riir-train's rows.** That worktree has another session's work
  staged in its index; touching it is the collision AGENTS.md's
  `staged_set_audit` section exists to prevent. The two committed ones are
  riir-train's to fix, and its 53-row standing backlog is the plan-scoped
  over-capture `instrument_reachability` documents for the same repo.
- **Re-pinning 53 → 56.** That is precisely the action this issue exists to
  prevent being taken blind.
