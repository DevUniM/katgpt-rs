#!/usr/bin/env python3
"""GATE: a skill SKILL.md whose bytes exceed the ceiling — the 104KB class.

Measured 2026-09-21, the third occurrence of the same growth arc: doc-sync
crossed 100KB (compacted 09-05 to 39KB, re-compacted 09-11 to 48KB, pruned
09-21 from 104KB), boundary-guard crossed 100KB (compacted 09-08, user-
directed, re-compacted 09-11, pruned 09-21 from 71KB), and research sat at
69KB of instruction body. The one-line-per-row convention HELD every time —
the cadence is the bloat: ~8-10 run-log rows/day x ~700B/row is +60KB/month,
so every prose-only "keep it compact" rule regrows the file between
compactions. This gate makes the ceiling mechanical.

CEILING is 80KB, deliberately above each file's 60KB prose maintenance rule
(prune the run log to the newest 15 rows): the gate is the backstop that
forces the prune, not the prune itself. Population is DERIVED — every
.agents/skills/*/SKILL.md joins by existing, so a new skill cannot outgrow
the ceiling unseen.

Exit 0 clean, 1 on an over-ceiling skill file, 2 if the instrument went
blind (the walk found fewer files than the floor — a ceiling over zero
files is green for the wrong reason, the Issue-713 class).
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# Issue 804: directly invokable instruments must survive a non-UTF-8 console.
import console_safe  # noqa: E402

console_safe.apply()

REPO_ROOT = HERE.parent
SKILLS_DIR = REPO_ROOT / ".agents" / "skills"

# 80 * 1024. The backstop; each file's own prose carries the tighter 60KB
# prune rule (see the 2026-09-21 prunes in doc-sync and boundary-guard).
CEILING = 81_920

# 8 skills at landing (2026-09-21): boundary-guard, doc-sync, feature-gate-audit,
# goat-audit, proposal, research, rust-optimize, substrate-first. Floored under
# so churn does not red it, but a walk that collapses to zero cannot print a
# confident green.
MIN_SKILLS = 8


def scan(sizes: dict[str, int], ceiling: int = CEILING) -> list[str]:
    """Sorted findings for {skill-name: bytes} — pure, so an arm can reach it."""
    return [f"{name}: {size}B > {ceiling}B ceiling"
            for name, size in sorted(sizes.items()) if size > ceiling]


def walk_sizes() -> dict[str, int]:
    """{skill-name: byte size} for every .agents/skills/*/SKILL.md on disk."""
    return {p.parent.name: p.stat().st_size
            for p in sorted(SKILLS_DIR.glob("*/SKILL.md"))}


def gate_selftest() -> list[str]:
    """Arms over this file's own arithmetic (the Issue-775 sentence: a shared
    parser's arm cannot reach a line of THIS file)."""
    fails: list[str] = []

    def eq(label, got, want):
        if got != want:
            fails.append(f"    {label}: got {got!r}, want {want!r}")

    eq("at the ceiling is clean", scan({"a": CEILING}), [])
    eq("one byte over the ceiling fires",
       scan({"a": CEILING + 1}), [f"a: {CEILING + 1}B > {CEILING}B ceiling"])
    eq("under is clean regardless of count",
       scan({"a": 1, "b": 2, "c": CEILING - 1}), [])
    eq("findings are name-sorted, not size-sorted",
       [f.split(":")[0] for f in scan({"z": CEILING + 9, "a": CEILING + 1})],
       ["a", "z"])
    eq("an empty walk scans clean by arithmetic — the FLOOR in main() is the "
       "only blindness guard, which is why it exits 2", scan({}), [])
    eq("the floor is below the population it guards", MIN_SKILLS >= 1, True)
    eq("the ceiling is a ceiling", CEILING > 0, True)

    # The WALK on the real tree: the derived population must actually be
    # derivable before any verdict means anything (a glob regression that
    # returns zero files would otherwise print a confident green).
    sizes = walk_sizes()
    eq("the walk finds the skills on disk", len(sizes) >= MIN_SKILLS, True)
    eq("every walked size is a positive int",
       all(isinstance(v, int) and v > 0 for v in sizes.values()), True)
    return fails


def main() -> int:
    arm_failures = gate_selftest()
    if arm_failures:
        print("✗ INSTRUMENT: skill_size_gate's own arithmetic does not pass its "
              "arms, so the byte counts below would be unreadable:")
        for f in arm_failures:
            print(f)
        return 2

    sizes = walk_sizes()
    if len(sizes) < MIN_SKILLS:
        print(f"✗ INSTRUMENT: walked {len(sizes)} skill SKILL.md file(s) < floor "
              f"{MIN_SKILLS} — the population went blind; a clean verdict below "
              f"would mean nothing")
        return 2

    findings = scan(sizes)
    if findings:
        for f in findings:
            print(f"  ⛔ .agents/skills/{f.replace(':', '/SKILL.md:', 1)}")
        print(f"✗ skill size gate FAILED — {len(findings)} of {len(sizes)} skill "
              f"file(s) exceed the {CEILING}B ceiling. Prune the run log to the "
              f"newest 15 rows (the documented maintenance rule) — recovery via "
              f"`git log -p -- <file>`")
        return 1

    largest = max(sizes.items(), key=lambda kv: kv[1])
    print(f"✓ skill size gate PASSED — {len(sizes)} skill file(s) within "
          f"{CEILING}B; largest {largest[0]} at {largest[1]}B")
    return 0


if __name__ == "__main__":
    sys.exit(main())
