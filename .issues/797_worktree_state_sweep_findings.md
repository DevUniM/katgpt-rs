# Issue 797 (allocated as 796; renumbered — the other session allocated 796 the same hour and pushed first) — a sweep reads the WORKTREE, so a finding may exist in NO commit (2026-09-15)

**Status:** open
**Class:** instrument / cross-repo sweep family
**Found by:** trying to close the last standing CROSS row in `citation_drift_sweep.py`

## The finding

Every instrument in the sweep family walks the **working tree**. This
workspace runs five-plus concurrent agent sessions against **shared
worktrees** — `staged_set_audit.py` exists for exactly that hazard one axis
over — so a sweep's finding may sit on a line that no commit contains, and a
sweep's clean repo may be clean only because somebody's uncommitted edit
removed the offending line.

Measured 2026-09-15 on this box (16 of 20 repos, `DOCS_GATE_PARTIAL_CLONE=1`),
`citation_drift_sweep.audit()` run twice per dirty repo — once over the
worktree, once with every dirty in-scope document replaced by its HEAD blob:

| repo | dirty tracked | in scope | worktree | HEAD |
|---|---|---|---|---|
| riir-ai | 6 | `HISTORY.md` | **CROSS = 1** | **CROSS = 0** |
| seal-remake | 1 | — | — | — |

The workspace's **entire** standing CROSS finding was an artifact. HEAD carries
`Filed … from the riir-train Research 453 session`; an uncommitted edit by
another session strips the `riir-train` qualifier, and the sweep reports an
unfollowable citation at `HISTORY.md:250`.

It cost a session: the row was carried across a context boundary as backlog,
described as *"blocked — that session has `HISTORY.md` itself uncommitted"*.
The correct verdict was not *blocked*; it was **there is nothing to fix**, and
no amount of reading the sweep's output could say which.

The POPULATION moves too, and that is the half a row-level read misses: the
same two runs measured `n_cites` **601 (worktree) vs 607 (HEAD)** and
`ambiguous` **162 vs 163** — the other session's uncommitted deletion of a
30-line block took six citations out of the denominator. A floor or ratchet
re-pinned from such a run bakes another session's in-flight edit into a
tracked expectations file, where it reds on every other box.

## The two directions, and the second is the silent one

- **UNCOMMITTED** — the worktree carries a row HEAD does not. A *false
  accusation*: the repair means editing a file another session holds open, and
  if they discard the edit the finding evaporates. Loud, wastes time.
- **MASKED** — HEAD carries a row the worktree does not. A *false green*: the
  defect is committed, in the repo, and the sweep says the repo is clean. This
  direction has **never been measured**, and by this repo's own doctrine
  ("a silent green is the worse direction") it is the one that matters.
  Measured today: **0** — which is a measurement, not an absence of the class.

## Why this is one shared mechanism, not one sweep's fix

The standing failure mode, now recorded six times (Issues 777, 778, 793, 782,
783, 789): *a rule landed in one instrument and never generalised.* All the
sweeps take the same shape and all of them read the worktree.

## Tasks

- **T1** — `scripts/worktree_state.py`, one copy: `dirty_files()`,
  `head_text()`, and a three-valued verdict (COMMITTED / UNCOMMITTED /
  MASKED) that is never pooled. Self-test, two-sided arms.
- **T2** — wire the repo-level advisory into every sweep at the existing
  `population_verdict()` call site. **ADVISORY, not a failure**: a sweep that
  hard-reds on an ordinary dirty worktree is a sweep nobody runs — the
  cries-wolf outcome AGENTS.md names. It rides the FINAL line in both
  directions, the `DEFERRED` precedent.
- **T3** — wire the row-level UNCOMMITTED/MASKED split into
  `citation_drift_sweep.py`, where the class was measured and where findings
  carry a `file:line` address. The DISPLAY reads the worktree; the PINS read
  HEAD.
- **T4** — AGENTS.md section; arm-reach pins refreshed; docs gate green.
