# Issue 777 — an instrument whose population is a FILESYSTEM walk audits code no repo owns

**Status:** OPEN

**Date:** 2026-09-14
**Source:** the first workspace run of `percentile_drift_sweep.py` from the
  Windows workstation. It red on two rows, and BOTH reds are artifacts of the
  walk, not findings.

## The class

Two audits in this family already landed the repair and the family never
generalised it:

- **Issue 734** (`trap_exit_launder_audit.py`): "Population derived
  (BOUNDARY.md + `.git`) and restricted to **tracked** `*.sh`: walking the
  filesystem instead reported 25 findings in a **gitignored** vendored drop no
  repo owns."
- **Issue 738 T3** (`platform_dead_code_audit.py`, `wasm32_surface_audit.py`):
  tracked-only, `vendor/` excluded with its count printed on the per-repo line.

`scripts/percentile_index_audit.py` and `scripts/len_derived_binding_audit.py`
still walk the filesystem behind a hand-typed directory-name skip set
(`{"target", ".git", "node_modules", ".venv"}`). A name list cannot express
"not ours" — and it is wrong in three independent ways, all three measured on
this box.

## The three measured instances

Tracked vs filesystem `.rs` count, 16 repos on this box (the other 14 are
delta 0):

| repo | filesystem walk | `git ls-files` | delta |
|---|---|---|---|
| seal-online-remaster | 2015 | 611 | **+1404** |
| riir-train | 1177 | 1129 | **+48** |

**1. A gitignored NESTED REPOSITORY — findings attributed to the wrong repo.**
`seal-online-remaster/mmorpg/` is `.gitignore:82 /mmorpg/` **and has its own
`.git`**. It supplies 19 of the 23 percentile sites the sweep attributes to
seal-online-remaster, *including the sole finding*:

```
✗ seal-online-remaster   rs=2015  sites=23   trunc_var=1
      mmorpg\crates\mmorpg-bot\src\metrics.rs:129
          let index = ((sorted.len() as f64) * percentile) as usize;
      ✗ trunc_var 1 > pinned 0
```

That is a real defect shape in *somebody's* code, but it is not
seal-online-remaster's, and the repair the sweep asks for cannot be made in
the repo it names. Worse than a false positive: a **correctly-shaped finding
at the wrong address**, which is the exact failure mode
`issue_citation_gate.py` exists for one axis over.

**2. Build artifacts under a directory the skip set does not name.**
riir-train's 48 untracked `.rs` are cargo OUT_DIR generated sources
(`glutin_wgl_sys`, `serde_core`, `thiserror`) under `.runs/target-release/`,
`.runs/target-cuda/`, `.runs/target-v2cpu/`, `.runs/target-bench/`. The skip
set names `target`; none of those IS `target`. Third-party generated code,
counted as riir-train's.

**3. The floor that inflation fabricated.** `percentile_drift_floors.txt` pins
riir-train `min_rs_files = 2500`. riir-train has **1129 tracked / 1177
filesystem** `.rs` files, and the row has never been edited since it was
created (`580a275b`). 2500 is not reachable by any walk of this repo — it was
measured over a box's transient build trees, so the row is a pin that reds
everywhere except the machine and the hour that produced it. The
cross-check is in this repo: `platform_dead_code_drift_floors.txt`, whose walk
IS tracked-only, records riir-train at **1129 .rs**.

A floor is the pin that catches an instrument going blind. A floor measured
over content the repo does not own catches nothing and reds forever — it
teaches whoever hits it that the sweep is noise, which is the one outcome a
gate cannot survive.

## The second defect in the same file

`percentile_index_audit.py:820` — `root = "/Users/katopz/git"`, hard-coded.
The no-argument invocation AGENTS.md documents as "all contract repos
(derived)" is a **traceback, exit 1**, on every box whose workspace is not at
that path:

```
FileNotFoundError: [WinError 3] The system cannot find the path specified: '/Users/katopz/git'
```

It is the only script in `scripts/` with a hard-coded home path, and
`skill_repo_set_gate.py:64` already carries the rule in a comment ("NOT
hard-coded to /Users/katopz/git — a gate against …"). Every sibling audit
derives from `__file__`. The sweep half survives only because it imports the
module and never calls `main()`.

## Tasks

- [ ] T1 (P0) — `scripts/tracked_walk.py`: the canonical population walk, ONE
  copy. `git ls-files` under a `.git` probe (`git -C` walks UP, so a non-repo
  directory inside a repo would be listed with its PARENT's paths), filesystem
  fallback for extracted/`git archive` trees that have no `.git`, `vendor/`
  excluded with the count RETURNED so callers can print it. Extracted verbatim
  from `platform_dead_code_audit.list_rs_files`, which repoints at it — three
  copies of a rule is how the rule stops being applied. Self-test covering all
  three instances above plus the fallback.
- [ ] T2 (P0) — `percentile_index_audit.py`: consume T1; derive `root` from
  `__file__`; print the excluded count on the per-repo line (an exclusion
  nobody can see is a population change nobody can audit).
- [ ] T3 (P1) — `len_derived_binding_audit.py`: same walk. Workspace-wide with
  the same skip set; **latent today** (its vocabulary is GPU-binding-specific
  and matched nothing in either drop), which is the point — it is one drop
  away from instance 1.
- [ ] T4 (P1) — re-pin `percentile_drift_floors.txt` against the repaired walk:
  riir-train's fabricated 2500 and seal-online-remaster's row (pinned 335 on a
  611-file observation, so the FLOOR was right and the ceiling was reading
  mmorpg). Re-pin deliberately, with the measured numbers in the row comment.
- [ ] T5 (P2) — `orphaned_attr_gate.py` is the same walk, katgpt-rs-scoped, and
  clean **only because this repo's delta is 0**. Either consume T1 or record
  why the scope makes it safe.

## Not in scope

- The `mmorpg/crates/mmorpg-bot/src/metrics.rs:129` truncation itself. Once
  the walk is tracked-only the site leaves this workspace's population
  entirely; it belongs to whatever repo owns that nested checkout, and filing
  it from here would be the wrong-address defect a second time.
- `restatement_theorem_audit.py` and `suite_membership_audit.py` also walk the
  filesystem, but both are scoped to a named subtree (`.proofs/`, `PIN_DIRS`)
  rather than to a repo root, so neither can reach a drop at the root. Checked,
  not repaired.
