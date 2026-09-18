# Issue 840: 17 of 19 drift sweeps open contract repo names DIRECTLY — on an alias box they measure a directory that does not exist

**Status:** OPEN — measured 2026-09-18 on the M3 box while landing Issue 837
T2; found by the console_encoding drift sweep red with walk-floor breaches
whose repos it had just VISITED. Fix is family-wide (one shared open seam),
not per-sweep.

## The defect

`derive_repos` returns CONTRACT names: on a box whose on-disk sibling names
differ from the contract spellings, `repo_alias.local.txt` translates the
on-disk names INTO the contract vocabulary, and every pin and floor file is
keyed on the contract name. AGENTS.md states the other half of the contract:

> Instruments that OPEN sibling files by the contract name need the on-disk
> spelling back — `repo_alias.disk()` is the reverse half

Measured 2026-09-18: exactly **2 of 19 `*_drift_sweep.py` import
`repo_alias` at all** (`docs_drift_sweep.py`, `numbering_drift_sweep.py`).
The other 17 open `WORKSPACE / <contract-name>` directly — and on this box
the contract names `mmorpg-editor` / `mmorpg-remake` / `mmorpg-remaster` are
alias-mapped to `seal-game-editor` / `seal-remake` / `seal-online-remaster`,
so the opened directory DOES NOT EXIST and every tracked-file walk on it
falls back to a glob over a nonexistent path and returns 0.

## Measured (the same run, one sweep after another)

| sweep | repo | pin (min walk) | measured | verdict line |
|---|---|---|---|---|
| console_encoding | mmorpg-editor | 1 | walk=0 | `walk FLOOR breached` |
| console_encoding | mmorpg-remake | 3 | walk=0 | `walk FLOOR breached` |
| orphaned_attr | mmorpg-editor | 128 rs | rs=0 | floor breach |
| orphaned_attr | mmorpg-remaster | 335 rs | rs=0 | floor breach |
| platform_dead_code | mmorpg-editor | 140 rs / 3650 cand | 0 / 0 | floor breach |
| subprocess_encoding | mmorpg-editor | 1 py / 1 call | 0 / 0 | floor breach |
| wasm32_surface | mmorpg-remake | 12 files | files=0 | floor breach |

The pins are not wrong — they were typed from the real repos (the alias
census can see them; these sweeps cannot). The sweeps red on a box state the
pins describe CORRECTLY, in the direction that reads as drift: every red
above is a TRUE pin measured against the WRONG DIRECTORY.

Two stale-pin findings in the same run are the same defect one level up:
`wasm32_surface_drift_sweep.py` reported mmorpg-remaster's
`wasm32_uncovered_expected.txt` rows (`mmorpg-core`,
`mmorpg-poc-submodule`) as "pinned UNCOVERED but now COVERED" — adjudicated
against the empty directory the sweep opened, not the repo.

## The fix shape (one mechanism, not 17 patches)

A shared open seam in `sweep_population.py` (every sweep already imports it):

```python
def open_repo(name: str) -> Path:
    """The on-disk spelling of a contract repo name — repo_alias.disk() with
    the workspace root applied. Every sweep opens repos through this, never
    `WORKSPACE / name` directly."""
    return WORKSPACE / repo_alias.disk(name)
```

and each sweep's `repo = WORKSPACE / name` becomes `repo = open_repo(name)`.
The `tracked_*` walks that take a root keep working unchanged — they receive
the resolved directory. `worktree_state` functions that take the repo path
ride along automatically.

## What this is NOT

- Not a pin error: re-pinning the mmorpg-* floors to 0 would bake an
  alias-box artifact into tracked files the way Issue 797's in-flight edits
  do (and `console_encoding_drift_floors.txt`'s own header already records
  the mmorpg-remake repair history against the real repo).
- Not the partial-clone case: the repos ARE on disk — `derive_repos` visits
  them, `population_verdict` counts them present, and the sweep then reads
  nothing from them. That mismatch (visited but unreadable) is the tell that
  distinguishes this from an absent repo.
