# Issue 783 — the subprocess-encoding gate is katgpt-rs-only, and pointing it anywhere else finds 31

Filed 2026-09-14. Class: instrument scope / generalisation gap.

## The claim

`scripts/subprocess_encoding_gate.py` (Issue 778) is a **per-push gate** in
`docs_gate.sh`'s CHECKS, and it walks `REPO_ROOT`. That is the right shape for
CI's single checkout and the wrong shape for "is anybody ELSE about to read a
child's pipe through the system locale?"

Eleven other verdict classes in this repo carry BOTH halves — a katgpt-rs-scoped
per-push gate and a workstation `*_drift_sweep.py` over every contract repo.
778 shipped with one half. That asymmetry is not a judgement call that was made;
it is a step that was skipped, and it is the standing failure mode this
workspace has now recorded four times (Issues 777 tracked-walk, 778 itself,
779 sweep-population, 782 the three quiet sweeps).

## The measurement

`subprocess_encoding_gate.scan()` already takes a repo path, so the question is
answerable today. 16 of 20 repos on this box (`DOCS_GATE_PARTIAL_CLONE=1`),
2026-09-14:

| repo | tracked .py | subprocess calls | DECODE | CHILD-ENCODER |
|---|---|---|---|---|
| katgpt-rs | 62 | 44 | 0 | 0 |
| riir-ai | 8 | 8 | **6** | 0 |
| riir-clippy | 5 | 12 | **9** | **1** |
| riir-dapps | 1 | 1 | **1** | 0 |
| riir-train | 68 | 15 | **12** | **1** |
| seal-game-editor | 2 | 2 | **1** | 0 |
| (10 others) | 17 | 0 | 0 | 0 |
| **total** | **163** | **82** | **29** | **2** |

Same shape as every prior sweep in this family: **one repo clean, the workspace
not.** The precedent list is in `markdown_fence_drift_sweep.py`'s docstring —
this is the seventh instance.

## Two rows that are not latent

Most of the 29 are `git`/`cargo` calls whose output is plausibly ASCII. Two are
reading text this workspace is *known* to fill with em-dashes:

- `riir-clippy/scripts/gen_dashboard.py:552` —
  `git -C <d> log --since=… --pretty=%s` across the sibling repos. Every commit
  subject in this workspace uses `—`. On cp874 that is mode 1 (silent mojibake)
  at best; where a byte is undefined it is mode 2 (`stdout = None`, returncode
  preserved) and the dashboard renders a confident empty section.
- `riir-train/scripts/plan344_phase0_full_bandwidth.py:318` —
  `git ls-files '*.md'` then reads those files; a non-ASCII path decodes wrong
  and the read fails at a filename nobody can see in the output.

`riir-clippy/scripts/bench036_interleaved_ab.py:218` and
`riir-train/scripts/plan339_340_closeout.py:64` are the CHILD-ENCODER pair: a
`sys.executable` spawn of a script in `scripts/`, i.e. a child that prints `✓`
and `⛔`, with no `PYTHONIOENCODING` in its env.

## Tasks

- **T1** — `scripts/subprocess_encoding_drift_sweep.py`: the 778 verdict over
  every contract repo. Import `subprocess_encoding_gate.scan` rather than
  re-deriving the classifier (Issue 755: a second copy of a rule this subtle is
  a second thing to get wrong). Pins in
  `scripts/subprocess_encoding_drift_floors.txt`. The population axis is
  `sweep_population.population_verdict` (Issues 779 + 782) — no twelfth copy of
  that loop.
- **T2** — **Two floors, not one** (the rule every sweep in this family
  carries). `min_py_files` catches a WALK regression; `min_calls` catches a
  PARSE one, and only the second moves when the AST pass breaks on an unchanged
  tree. ⚠ `min_calls` is **0 in 10 of 16 repos** — those repos have `.py` files
  and no `subprocess` at all — so unlike the fence sweep's single floor, the
  parse floor cannot carry the blindness argument by itself and the walk floor
  is load-bearing in exactly the repos where the ceiling is vacuous.
- **T3** — katgpt-rs's two floors are NOT free: they must equal
  `subprocess_encoding_gate.FLOOR_PY_FILES` / `FLOOR_CALLS`, and the sweep must
  **assert** that rather than trusting it (`docs_gate_paths_sync.py` one axis
  over; `trap_sentinel_drift_sweep.py` for `POPULATION_FLOOR`).
- **T4** — repair the 31, and pin **0/0** everywhere rather than ratcheting a
  backlog. A ceiling above zero on a class whose repair is a two-token kwarg
  teaches whoever reads it that the class is tolerated.
- **T5** — AGENTS.md: the sweep joins the workstation family list, and the 778
  section says it has both halves.

## What this issue does NOT claim

That a ceiling of 0 workspace-wide will hold. Four of 20 repos are absent from
this box; their rows are `UNSEEN`/`DEFERRED` per Issue 779's verdict and are
owed a measurement on the next full checkout, exactly like
`platform_dead_code_drift_sweep`'s four unpinned rows.
