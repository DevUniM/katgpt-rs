# Issue 848: `develop` was RED for 6h40m — one commit privatised a delegation target and deleted a shared fixture, and both of that module's EXTERNAL callers are docs-gate CHECKS

**Status:** **RESOLVED** for the two breakages (both repaired, docs gate
29/29 green). **T2–T4 open** — the class, the lane, and the wall.

Broken at `6c6ca2ee` (2026-09-19 01:11:24 +0700), found 2026-09-19 07:51
+0700 — **6h40m**, ended by a hand run of `scripts/docs_gate.sh` on a
freshly-rebased `develop`, by a session doing something else entirely.
Nothing automatic found it,
and nothing automatic could have: CI is MAIN-ONLY since 2026-09-09 and this
landed on `develop`.

## The two breakages, both in `6c6ca2ee`

`6c6ca2ee` ("fix(842): one alias-open seam for the sweep family") reworked
`scripts/worktree_state.py`'s own arms. In doing so it:

1. **renamed `is_checkout` → `_is_checkout`** and updated the seven in-module
   callers — but not the two EXTERNAL ones; and
2. **deleted `worktree_fixture` outright.**

Both names are consumed by `console_encoding_gate.py` and
`sweep_advisory_membership_gate.py`, which are **docs-gate CHECKS**. Both
died with

```
AttributeError: module 'worktree_state' has no attribute 'is_checkout'
AttributeError: module 'worktree_state' has no attribute 'worktree_fixture'
```

— not a wrong verdict, **no verdict**, which is Issue 804's class one seam
over: a gate that dies has findings that are not *unknown* but *unlooked at*.

## Both names were documented as PUBLIC, in the repository, by the change's own inputs

This is not a judgement call that went the other way. Each name carried a
written contract, and each contract names the consumers:

- **`AGENTS.md:1204`** — *"`worktree_state.is_checkout` — **delegate to it
  too**, and it is the spelling `tracked_walk.py` had right all along."* The
  whole point of Issue 836 T2 was to make three private copies delegate to
  one public probe.
- **`worktree_fixture`'s own docstring**, deleted along with it: *"Public,
  because the three delegating consumers each owe an arm proving they take
  the git branch in a worktree, and that arm needs exactly this fixture."*

So the change removed the two names whose reason for existing was that
external modules use them, in a workspace whose own instrument census exists
because *"a census that reads the document cannot see an instrument the
document omits"*. Here the document said the right thing and nothing read it.

## Why nothing caught it — three lanes, three reasons, all correct individually

Python has no link step, so an unresolved attribute is a RUNTIME error and
only an execution finds it. Every lane that could execute these two gates was
out of reach:

| lane | why it did not fire |
|---|---|
| `docs_gate.yml` | `push: branches: [main]` since 2026-09-09 (Actions spending call). A `develop` push starts nothing. |
| a local `docs_gate.sh` run | ran by the author before the rename, or not at all — the gate is ~100 s wall here |
| `full_gate.sh` / `test_gate.sh` / `x86_64_execution_matrix.sh` | none of them runs `scripts/*.py`; they are Rust lanes |
| `arm_reach_gate.py` | EXECUTES these modules and would have died at import — but it is a **workstation** verdict, not a CHECK, measured at 157.6 s |

This is AGENTS.md's own `⛔ On a non-macOS workstation` paragraph, one
language over: *"the per-crate gate that landed it was right for what it
changed; nothing read what it changed for everyone else."* There it was 24
`error[E0560]` on `develop` for ten hours behind a green `test_gate`. Here it
is two dead CHECKS behind a green everything-else, and the interval is the
same order — 6h40m, ended by a hand run rather than by a lane.

⛔ **The sharper reading is that the repair for one class opened another.**
`6c6ca2ee` is a good commit — it closed Issue 842 across 19 sweeps, landed
sibling repairs in three repos and re-pinned ten floors from first real
measurements. The breakage is in the housekeeping *beside* the repair, which
is exactly where this workspace's own §staged-set discipline says to look and
exactly where nobody looks.

## The repair

- `is_checkout` restored to its public spelling (10 references).
- `worktree_fixture` restored verbatim from `6c6ca2ee~1`, with a comment at
  the definition recording why it is public, so the next rework reads the
  contract at the line rather than in a docstring it is deleting.
- `scripts/worktree_state.py` self-test: **144 assertions**, clean.
- `scripts/docs_gate.sh`: **29/29**.

## Tasks

- [x] **T1 — Repair both names and re-green the docs gate.**
- [ ] **T2 — The CLASS: a tracked `scripts/*.py` naming an attribute another
      tracked module does not define.** Statically decidable for `import X` +
      `X.attr` and for `from X import name`, which is how every cross-module
      reference in `scripts/` is written. **Measured two-sided against a known
      answer**, which is the part that makes it shippable rather than
      plausible:

      | ref | findings |
      |---|---|
      | `6c6ca2ee~1` (before the break) | **0** |
      | `origin/develop` (after it) | **4** — exactly the two names x two consumers, no others |
      | the repaired working tree | **0** |

      90 tracked `scripts/*.py`, 0 unparsed, **0 false positives** in either
      direction. ⚠ STATED blind spots, to be printed on the verdict line
      rather than remembered: **11 `getattr` sites**, re-exports, and a name
      bound only inside a function. And the walk must be the whole `scripts/`
      tree rather than the CHECKS set — the two victims here happen to be
      CHECKS and the next one need not be.
- [ ] **T3 — The LANE, and it is the more general finding.** T2's gate would
      have caught these two. It would NOT have caught a `TypeError` from a
      changed signature, a moved constant, or any other runtime break — and
      the general instrument for that already exists and already executes
      every module: `arm_reach_gate.py` dies at `BASELINE-CRASH` on an
      unimportable module. It is kept out of the CHECKS set for a measured
      reason (157.6 s against a ~13 s budget). The question is whether a
      **cheap import-only** pass belongs in the docs gate — `python -c "import
      m"` over 91 modules, which is the part of `arm_reach_gate`'s baseline
      that costs almost nothing. Measure it before answering.
- [ ] **T4 — Does the class generalise?** `console_encoding_drift_sweep`
      measured seven sibling repos carrying `scripts/*.py`; riir-train alone
      has 61. **Count before deciding**, on `check_validation_gate` 789 T4's
      own correction: that issue declined a sweep on a population of one, and
      `console_encoding_gate` inherited the answer and was wrong by seven
      repos.

## What this is NOT

- **Not an argument against the main-only CI call.** That is an owner
  decision about Actions spend and it stands. What the table above measures is
  that the resulting `develop` lane is **zero**, not reduced —
  `ci_gate_coverage.py` already prints exactly that finding for 12 of 16
  repos, and this is the first time it cost this repo a red `develop` in
  Python rather than in Rust.
- **Not a reason to re-privatise nothing.** A module is free to narrow its
  surface; what it owes is the grep. Both names here were greppable in one
  command, and the deleted one told the reader who its callers were.
