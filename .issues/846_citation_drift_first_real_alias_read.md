# Issue 846: the citation sweep's first REAL read of the alias-mapped repos surfaced ~35 file-addressed citation defects

**Status:** OPEN — filed 2026-09-19, katgpt-rs Issue 842's close-out run. The
842 fix (sweep_population.open_repo + repo_alias.real) made
citation_drift_sweep read seal-remake / seal-game-editor /
seal-online-remaster for the FIRST time, and re-classified the whole
workspace with REAL allocation reads. The previously-green pins were typed
through the broken zero-read; the rows below are TRUE findings, not sweep
noise. Measured: `citation_drift_sweep.py` rc=1 on this box, 2026-09-19.

## The findings (per repo, per the run's own table)

| repo | finding | pin |
|---|---|---|
| mmorpg-remake (seal-remake) | CROSS 15 > 0 (cites=121 — its docs were measured EMPTY before 842) | cross wall 0 |
| riir-dapps | CROSS 4 > 0 | cross wall 0 |
| riir-clippy | CROSS 3 > 0 | cross wall 0 |
| riir-dao | CROSS 3 > 0 | cross wall 0 |
| riir-game-sdk | CROSS 7 > 0 | cross wall 0 |
| riir-ai | IN-LOCAL-RANGE 8 > 6 | re-pinned 6 → 8 in the same commit — the 842 fix made the aliased repos' allocations RESOLVE, so rows moved into the more-correct in-range bucket; a reclassification, not new defects |

## The shape of a row

Specimen (seal-remake `HISTORY.md:610`):

> Plan 192 -> katgpt-rs/mmorpg-editor/riir-ai/riir-train [⛔MISLEADING: the
> only crate in the window is riir-dapps/riir-neuron-db, which does NOT own
> 192]

The citation's owner-qualifier names repos that do not own the number, while
the surrounding window's crates name the real owner — the qualifier was
written for the PRE-migration world (the 2026-09-16 owner migration moved
seal-core/seal-edge-worker — and whole plan-number namespaces with them —
between repos, and docs citing the old addresses were never re-qualified).
Every red repo sits upstream or downstream of that migration.

## Why not fixed here

Each row needs a per-row editorial read: open the cited document window,
determine which repo ACTUALLY owns the number, and rewrite the qualifier.
~35 rows across 6 repos, several of which carry concurrent sessions' WIP —
bulk-qualifying them without the reads would manufacture false attributions,
and bulk re-pinning the CROSS walls from 0 to measured would absorb real
defects ("do NOT raise a ceiling to clear a red"). The sweep prints exact
`file:line` addresses, so the repair pass is mechanical once somebody reads
each row — it is the natural next citation-hygiene unit.

## Reopen/clear condition

The sweep stays RED with these true findings until each row is qualified or
re-owned. Repair commit(s) should cite this issue; the floors rows re-pin to
the measured residual in the SAME commit as the repairs.
