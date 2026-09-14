# Issue 784 — the orphaned-attr gate's cross-repo claim is hand-run, and Issue 777 invalidated it by 46%

Filed 2026-09-14. Class: stale measurement / generalisation gap.

## The claim

`scripts/orphaned_attr_gate.py` is the **last** row in `docs_gate.sh`'s CHECKS
whose class is cross-repo (Rust source, present in every repo) and which has no
workstation sweep half. Issue 783 closed that gap for `subprocess_encoding`;
this is the one it left.

The consequence is already measurable, and it is not hypothetical drift — the
gate's own docstring carries the cross-repo figure **as the argument for why it
can be a gate at all**:

> **Re-measured 2026-09-06**, after ~500 sibling commits: still zero in all 16 —
> **11,132 `.rs` files, 49,624 outer-`#[cfg]` sites, 0 orphaned**. The site count
> is the part worth keeping: a zero over 49,624 sites is evidence; a zero over a
> walk that has gone blind is not.

That paragraph is right about the principle and wrong about the number.
**Issue 777 landed today** (`820bf8b6`) and migrated this gate to
`tracked_walk.tracked_files`. Re-measured over the tracked walk, same 16 repos,
2026-09-14:

| quantity | docstring (2026-09-06, filesystem walk) | measured (tracked walk) | drop |
|---|---|---|---|
| `.rs` files | 11,132 | **8,694** | 22% |
| outer-`#[cfg]` sites | 49,624 | **26,598** | **46%** |
| orphaned | 0 | **0** | — |

The verdict is unchanged. The **evidence** behind it is not: 23,026 of the
49,624 sites the paragraph offers as its warrant were in trees no repo owns —
seal-online-remaster's gitignored `mmorpg/` nested repository (1404 `.rs`),
riir-ai's vendored `wgpu-hal` fork, riir-train's cargo `OUT_DIR` sources under
`.runs/target-*`. This is Issue 777's second-order damage one class over: 777
repaired the two `percentile_drift_floors.txt` rows it measured and
`percentile_drift_floors.txt`'s own prose, and left every OTHER prose
restatement of the same walk standing.

## The second stale site

`grep` for the figure finds two live copies, not one:

- `scripts/orphaned_attr_gate.py:38-39` — above.
- `.docs/10_audits/percentile_index_tail_support.md:121` — "the workspace walk
  is 11,132 `.rs` files", in the audit note whose floors file was itself
  corrected at 777. The floors file records both figures, dated, with the
  mechanism named; the `.docs` note it belongs to does not.

`scripts/percentile_drift_floors.txt` is the control and shows the repair that
was made correctly: the pre-777 line kept as a dated measurement record, the
post-777 line next to it, and the 2,438-file delta attributed rather than
asserted.

## Why the sweep is the actual repair

Correcting two numbers is a five-minute edit that the next walk change will
invalidate again. The reason the figure went stale is structural: **it is
hand-run.** The gate audits one repo per invocation, somebody has been typing
the workspace total into its docstring by hand since 2026-09-03, and nothing
re-asserts it. That is the same shape the gate's own docstring already warns
about two paragraphs down:

> until 2026-09-04 its PASS line printed "measured 0 across 19 repos" on every
> run — a cross-repo claim no run had made, with a count that had gone stale two
> commits earlier.

The fix applied then was to stop the PASS line making the claim. The fix
available now is to make the claim **measured**.

## Tasks

- **T1** — `scripts/orphaned_attr_drift_sweep.py`: the verdict over every
  contract repo. Import `orphaned_attr_gate.scan` rather than re-deriving the
  OUTER-`#[cfg]` narrowing (that narrowing is the instrument — it takes 2,044
  sites to 0 — and a second copy of it is a second thing to get wrong). Pins in
  `scripts/orphaned_attr_drift_floors.txt`; population axis is
  `sweep_population.population_verdict` (Issues 779 + 782).
- **T2** — **Two floors.** `min_rs_files` catches a WALK regression;
  `min_cfg_sites` catches a PARSE one, and only the second moves when the
  regex breaks on an unchanged tree. Unlike Issue 783's population, **both are
  non-zero in all 16 repos measured** (the smallest, riir-viewbridge, has 24
  files / 20 sites), so both bite everywhere — state that as a measured
  difference from 783, not as an assumption.
- **T3** — katgpt-rs's two floors must equal `orphaned_attr_gate.FLOOR_FILES` /
  `FLOOR_CFG_SITES`, **asserted** rather than trusted.
- **T4** — correct both stale prose sites, in the
  `percentile_drift_floors.txt` style: keep the pre-777 figure as a dated
  record, put the tracked-walk figure next to it, and name the mechanism.
  ⚠ Do NOT simply overwrite the old number — a reader who cannot see that the
  population definition changed will read a 46% drop as deleted code.
- **T5** — AGENTS.md: the sweep joins the workstation family list, and the
  orphaned-attr row acquires its second half.

## What this issue does NOT claim

That 0 orphaned will hold. It has held over three independent measurements
across two population definitions, which is the strongest form of the claim
available, and the gate exists because the class cost two days of broken
release builds once. Four of 20 repos are absent from this box and stay
`DEFERRED` per Issue 779.
