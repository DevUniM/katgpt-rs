# Issue 765 — the docs gate's 3 workstation-only instruments red with a MISLEADING remedy on a partial clone (the 4090 box class)

**Status:** OPEN (filed 2026-09-13, 4090 session — hit while resolving Issue 764)

## The trap

The 4090 box carries a **partial clone** of the workspace: 14 contract repos
under `E:\git`, not 20. `katgpt-web`, `riir-dao`, `riir-deployer`,
`riir-esp32`, `riir-shader`, `riir-viewbridge` are not cloned there (and
`seal`/`SealM` are non-repo dirs, correctly excluded by the `.git` predicate).

Running `./scripts/docs_gate.sh` on that box (with the documented env preconditions
`python3` on PATH + `PYTHONIOENCODING=utf-8` — both also missing there by default)
reds exactly 3 of 17 checks:

| check | failure line | the misleading part |
|---|---|---|
| `skill_repo_set_gate.py` | "repo_set.txt is stale vs the live workspace — gone [6 repos] — **regenerate it and commit**" | Following the remedy corrupts the committed canonical set: `repo_set.txt` is correct for the FULL workspace (the M3); regenerating on the partial clone would delete 6 true repos from it |
| `population_sync_gate.py` | "repo_set.txt disagrees with the derived walk: only-in-file=[6]" | Same remedy implied, same corruption if executed |
| `issue_citation_gate.py` | "derived 14 contract repos < floor 15 — the population went blind" | This one correctly refuses rather than suggests a fix — but it cannot distinguish "instrument blind" from "box partially cloned" |

The other 14 checks run green on the partial clone (verified 2026-09-13 while
closing Issue 764: the clean-HEAD worktree control showed the same 3 reds
without the working-tree change — pre-existing/environment, not drift).

This is the same env-red-vs-drift-red separation the gate header already
documents for `python3`/`PYTHONIOENCODING` ("5 of 8 checks red for
environment, not drift"); the partial-clone axis is the missing member.

## Proposed fix (workstation session or owner adjudication)

The true workspace total is already pinned in prose (AGENTS.md repo-count
paragraph: 20 repos, named) and in the committed `scripts/repo_set.txt`. So a
gate running on ANY box can classify the disagreement without network:

- **disk ⊂ file** (every "gone" repo IS in the canonical file/AGENTS list) →
  **partial clone**: print a workstation-deferral line (the CI precedent —
  `issue_citation_gate`'s `DOCS_GATE_CI` marker — is the idiom), exit green
  for the population axis, do NOT suggest regeneration.
- **file ⊂ disk** (a repo on disk missing from the file) → genuine staleness:
  keep the hard red + regenerate remedy (current behavior is correct here).
- Symmetric disagreement → keep the hard red.

Applies to `skill_repo_set_gate.py`, `population_sync_gate.py`, and
`issue_citation_gate.py`'s floor message (report "partial clone (N of M
present)" when the missing set is exactly disk ⊂ file).

## Alternatives (owner call)

1. Clone the 6 repos on the 4090 (makes the gate fully runnable there; costs
   disk + sync discipline on a box that currently only needs 4 of them).
2. Accept the red on the 4090 + a one-line note in the box-specific context
   (cheapest; the trap remains for the next session that greps no further
   than the failure line).

## Validation

- Partial-clone sim (worktree of katgpt-rs alone, or the real 4090 box): 3
  checks print the deferral line, gate green or red only on genuine drift.
- Full-workspace run (M3): behavior unchanged — the disk ⊂ file branch never
  fires when all 20 are present.
- The disk ⊂ file classification must read the CANONICAL sources
  (`repo_set.txt` + the AGENTS count paragraph via `agents_repo_set_gate`),
  never the live walk alone.

## Related

- Issue 764 (the resolution session that hit this).
- AGENTS.md docs-gate table (the `population_sync_gate` / `skill_repo_set_gate`
  rows describe workstation scope; the remedy text is the gap).
