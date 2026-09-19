# Issue 848: `develop` was RED for 6h40m — one commit privatised a delegation target and deleted a shared fixture, and both of that module's EXTERNAL callers are docs-gate CHECKS

**Status:** **RESOLVED** — both breakages repaired and the class walled in
BOTH halves: `scripts/cross_module_attr_gate.py` (static, T2) and
`scripts/import_health_gate.py` (execution, T3), each a docs-gate CHECK. All
four tasks CLOSED. ⚠ No check COUNT is written here on purpose: this line
said `29/29` and was stale within the hour, twice — take it from
`docs_gate_checks_sync`'s own PASS line, which derives it.

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
- `scripts/docs_gate.sh`: green, every check (the count is the
  gate's to print, not this file's).

## Tasks

- [x] **T1 — Repair both names and re-green the docs gate.**
- [x] **T2 — DONE. The CLASS is walled: a tracked `scripts/*.py` naming an attribute another
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

      **Shipped** as `scripts/cross_module_attr_gate.py`. Live run: 0 findings
      over **86 tracked `scripts/*.py`** (floor 50) / **708 resolved
      references** (floor 200), 0 pinned exemptions, 0 unparsed. Two floors
      that fail differently — the walk, and the import RESOLUTION, which is
      the one that matters: if `_aliases` stops building the local-binding
      table every name reads trivially fine and the output is byte-identical
      to a clean repo. Exemptions are membership + a reason per row, both
      directions, and the file is deliberately EMPTY (the default for a
      dangling reference is to restore the name, not to pin it).
      `--prove-fires 6c6ca2ee` is the two-sided arm and runs opt-in, on the
      `platform_dead_code_floor_gate` precedent.

      ⛔ **The OPAQUE bucket is the one that had to be got right and is 0
      today, which is why it is DISCLOSED rather than remembered.** A module
      carrying `from x import *` has a namespace no parse of that file can
      enumerate, so nothing is claimed against it — credited with everything,
      the conservative direction for a gate whose false positive is a demand
      to "fix" working code. A silent version of that rule would report
      coverage it does not have.
- [x] **T3 — DONE. The LANE is shipped: `scripts/import_health_gate.py`**,
      and the affordability question was MEASURED rather than argued.

      T2's gate is static and catches name resolution. It cannot reach a
      circular import, a missing third-party dependency, or a `raise` in
      top-level code — those need an EXECUTION. The instrument that already
      executes every module is `arm_reach_gate`'s `BASELINE-CRASH` bucket,
      and it is out of the CHECKS set for a measured reason (157.6s against
      a ~13s CPU budget). The question was whether the IMPORT half alone fits.

      Measured over the 86 tracked top-level modules, one interpreter, each
      imported in turn:

      | | wall |
      |---|---|
      | total | **6.34s** |
      | `list_unresolved_percentile_sites` | **6.238s** |
      | the other 85, all of them | **0.10s** |

      ⛔ **98% of the lane was ONE module**, whose entire body was top-level —
      no `main()`, no `__main__` guard — so importing it ran a workspace-wide
      `.rs` walk and printed to stdout. Guarded in the same change; its import
      went **6.238s → 0.0077s**, and `arm_reach_gate` had been paying that
      6.2s once per mutant. So the answer to "is an import lane affordable"
      was NO for one measurement and YES for every other, and the difference
      was a defect rather than a budget.

      ⛔ **A per-module subprocess was measured too and is not worth 3x**:
      10.28s against 7.52s for one child importing all 86, with the
      **identical** single verdict. So the gate runs one child, and the cost
      of that choice is STATED on the verdict line rather than hidden — a
      module already imported as somebody's dependency is cached, and a
      failure caused by a previous import's side effects would be attributed
      to the wrong module.

      ⛔ **MISSING-DEP is its own bucket and is NEVER flagged**, and getting
      that wrong would have been worse than not shipping the gate. The one
      real failure here is `generate_npc_brain_model` (a macOS CoreML
      generator needing `numpy`/`coremltools`). A pinned row for it is
      correct on THIS box and STALE on any box that has numpy — so a green
      run would depend on not having installed something. A missing tracked
      SIBLING is a different statement and stays a finding, which is the
      class this whole issue is about. The split is EXTRACTED into
      `split_failures()` so an arm can reach it — the pattern AGENTS.md
      records three times: *the extraction IS the repair*, because verdict
      arithmetic inline in `main()` beside its own error messages is
      unreachable by construction.
      ⚠ STATED cost: a typo'd stdlib import (`import jsonn`) lands in
      MISSING-DEP too. The alternative is a stdlib allow-list, which goes
      stale every release and fails in the direction that INVENTS findings.

      Live: 86 of 87 import, **0.11s in one child**, docs gate green.
      Known-answer probe: a `raise` planted in a tracked module reds it, and
      the revert greens it.

      ⚑ **Landing it found two more live defects, both in the gates that
      already existed**, which is the argument for a small check over a big
      one: `subprocess_encoding_gate` red on a `PYTHONIOENCODING` env dict
      bound to a LOCAL rather than written at the call site, and
      `console_encoding_gate` red on `list_unresolved_percentile_sites` —
      which entered that gate's population for the first time because adding
      a `__main__` guard is what makes a module an INSTRUMENT by its
      predicate. A repair that grows a population is a repair that owes the
      other gates a run.

- [x] **T4 — DONE. Counted, and the two ways of counting DISAGREE by an
      order of magnitude — which is the finding.** `check_validation_gate`
      T4 declined a sweep on a population of ONE and was right;
      `console_encoding_gate` INHERITED that answer and was wrong by seven
      repos. So this was measured, not inherited — and measured twice, on
      purpose:

      | quantity | says |
      |---|---|
      | tracked `scripts/*.py` | 10 of 17 contract repos carry them, **196** files — *ship a sweep* |
      | RESOLVED sibling references | **713 of 749 are in this repo** — *there is no surface there* |

      Only the second is this class's population: a finding can only come out
      of a resolved reference, and riir-train resolves **32** across its 63
      scripts, riir-ai **2**, mmorpg-remake **2**, and every other repo
      **0** — their `scripts/` are standalone one-offs that import nothing of
      each other's. `instrument_reachability_drift_sweep` measured the same
      shape from the other side (riir-train 61 of 61 unreachable, where its
      predicate over-captures for exactly this reason).

      **Verdict: no sweep.** A `max_findings = 0` row over 36 resolvable
      references in nine repos is a wall nobody can fail, which is the
      cries-wolf instrument AGENTS.md warns gets ignored — and Issue 785's
      rule forbids the ratchet alternative, since an unread bucket is a
      backlog.

      ⛔ **But the number is not recorded in prose, because that is how every
      cross-repo figure in this workspace has gone stale.**
      `scripts/cross_module_attr_gate.py --workspace` is the census, a REPORT
      at exit 0, alias-aware (`repo_alias.disk()`), printing both columns
      every run. **What would flip the answer is a sibling's RESOLVED count
      growing, not its file count** — take the figures from a run, never from
      this table.

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
