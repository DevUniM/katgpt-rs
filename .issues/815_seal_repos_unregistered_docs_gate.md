# Issue 815 — seal-* repos on the 4090 box are UNREGISTERED: skill_repo_set_gate + population_sync_gate red on every docs-gate run there

**Status:** OPEN — owner decision required (workspace-contract scope); evidence + options below.

## The measured red

On the Windows 4090 workstation, three sibling directories exist on disk that
`scripts/repo_set.txt` does not know:

- `E:\git\seal-game-editor`
- `E:\git\seal-online-remaster`
- `E:\git\seal-remake`

The two population checks classify on-disk-but-unregistered repos as
**UNREGISTERED**, which by AGENTS.md "reds in every posture" (the
`DOCS_GATE_PARTIAL_CLONE=1` marker covers *absent* repos, never unknown
ones — an unregistered repo is a repo JOINING and must be loud):

- `skill_repo_set_gate` — FAIL
- `population_sync_gate` — FAIL

Measured on the Plan 600 T8/T9 landing session (2026-09-17, HEAD `5c6cb58e`):
**2 of 25 docs-gate checks fail, both on this, zero on content.** Every other
check is green on that box.

## Why this is not self-servable from the box

AGENTS.md pins the workspace as **20 repos** and `seal-*` are not in that
list. Three of the possible repairs are contract changes, and one touches a
read-only surface:

1. **Join the contract** — add the three repos to `scripts/repo_set.txt`,
   the AGENTS.md repo count, and (per the boundary rules) their root
   `BOUNDARY.md` contracts + `ci_boundary_contract.sh` population. NOTE:
   `seal-online-remaster` main/develop are READ-ONLY by standing instruction
   ("seal-online-remaster main and develop branch is read only, any repos
   that's not included in workspace is read only") — a contract row that
   expects commits from workspace agents would violate that.
2. **Known-extra posture** — extend the partial-clone marker semantics with a
   second, explicit opt-in marker ("known-extra repos on this box"),
   never auto-detected, same discipline as `DOCS_GATE_PARTIAL_CLONE=1`.
3. **Box hygiene** — the repos do not belong on the workspace box at all;
   move them out of the workspace root (owner-owned action; NOT an agent
   `rm`/`mv` — see the NEVER-relocate rule).

Option 3 without a decision would just move the red to the next box that
carries them.

## Precedent

The same shape as a partial clone, one bucket over: UNSEEN (absent, no
marker) got the marker; UNREGISTERED (present, unregistered) was left loud
on purpose — "a repo JOINING, reds in every posture". Whether seal-* ARE
joining is exactly the owner question this issue asks.

## Verification

After the owner call lands, `python scripts/docs_gate.sh` on the 4090 box
must print 25/25 (or the deferral rides the final line under the chosen
marker). This issue closes when the box is green or the repos are gone from
it.
