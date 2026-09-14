#!/usr/bin/env python3
"""GATE: a fenced code block that is never closed swallows the rest of its file.

Everything after an unterminated ` ``` ` renders as code — headings, tables,
the nav footer, all of it. Measured 2026-09-12 across 19 contract repos: **19**
such files over 5048 tracked `.md`, swallowing **611** lines. The largest,
`.plans/048_research_audit_fixes.md`, opened a ```bibtex block under "Research
Citations" and never closed it, turning the following 146 lines — an entire
second document section — into a code listing.

It is also a PARSE hazard, which is why this gate lives beside the others: a
scanner that toggles in/out state on every fence line mis-phases permanently
from that point and thereafter scans the complement (prose read as code, code
read as prose), reporting clean either way. That is not hypothetical here —
`.agents/skills/rust-optimize/SKILL.md`'s unclosed ```text swallowed
`skill_repo_set_gate.py`'s own first canary, which is how the class was found.
Its `fenced_blocks()` is CommonMark-ish for that reason, and is imported here
rather than re-derived (Issue 755: a second copy of a rule this subtle is a
second thing to get wrong).

⚠ **The reported line is the DANGLING fence, NOT necessarily the defect.** A
single stray fence inverts the pairing of every fence after it, so the dangling
one may be a legitimate CLOSER whose partner was consumed upstream. Two of the
three shapes were measured in the workspace:

    missing closer  a block opens under a heading and the file ends inside it
    stray fence     an orphan ``` between two prose paragraphs (delete it)
    missing opener  console output that was meant to be fenced and is not

Locate the defect before repairing: read the first non-blank body line. Code
means the closer is missing; prose means the fence itself is the orphan.

Exit 0 clean, 1 on an unterminated fence, **2 if the instrument went blind**
(the walk collapsed below its floor — a ceiling over zero files is green for
the wrong reason).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from skill_repo_set_gate import fenced_blocks, selftest  # noqa: E402 — reused, not re-derived

REPO_ROOT = HERE.parent

# The walk's own floor. 1517 tracked `.md` at landing (2026-09-12); floored well
# under so ordinary churn does not red it, but a `ls-files` regression that
# returns nothing cannot print a confident green over zero files.
MIN_FILES = 800


def scan_text(rel: str, text: str) -> list[tuple[str, int, int]]:
    """[(path, opening line, lines swallowed)] for one document.

    Extracted from `unterminated` by Issue 790 T4 so an arm can reach it. The
    parser's own `selftest` (imported, and invoked in `main`) is the
    CLASSIFIER's arm — it cannot reach a line of THIS file, which is Issue
    775's sentence and why `arm_reach_audit` reported all 5 of this module's
    mutants as NO-ARM. The two decisions here are the `last < 0` sentinel test
    and the swallowed-line arithmetic, and the second is what a reader acts on.
    """
    n_lines = len(text.splitlines())
    return [(rel, first, n_lines - first)
            for first, last, _body, _prev in fenced_blocks(text) if last < 0]


def gate_selftest() -> list[str]:
    """Arms over THIS file's own arithmetic, not the shared parser's."""
    fails: list[str] = []

    def eq(label, got, want):
        if got != want:
            fails.append(f"    {label}: got {got!r}, want {want!r}")

    eq("a terminated document yields nothing",
       scan_text("a.md", "x\n```\ny\n```\nz"), [])
    # 5 lines, fence opens on 2 => 3 lines render as code to EOF.
    eq("the swallowed count is lines-from-the-fence-to-EOF",
       scan_text("a.md", "x\n```\ny\nz\nw"), [("a.md", 2, 3)])
    eq("a fence on the LAST line swallows nothing but is still reported",
       scan_text("a.md", "x\n```"), [("a.md", 2, 0)])
    eq("a fence on the FIRST line swallows the whole file",
       scan_text("a.md", "```\ny\nz"), [("a.md", 1, 2)])
    # The tilde family reaches this file too (Issue 789 T1), and the row must
    # carry the same arithmetic rather than being silently dropped.
    eq("a tilde fence is reported with the same arithmetic",
       scan_text("a.md", "x\n~~~\ny\nz\nw"), [("a.md", 2, 3)])
    # The `last < 0` sentinel test is the only thing separating a finding from
    # a closed block; a `<=` would be equivalent and a `>` inverts the gate.
    eq("a terminated block is never reported no matter how long",
       scan_text("a.md", "```\n" + "y\n" * 50 + "```"), [])
    eq("the floor is a floor, not a ceiling", MIN_FILES > 0, True)
    return fails


def unterminated(repo: Path) -> tuple[list[tuple[str, int, int]], int]:
    """([(path, opening line, lines swallowed)], files walked)."""
    out: list[tuple[str, int, int]] = []
    # TRACKED **plus** untracked-not-ignored. Tracked-only is not enough and the
    # miss was measured on this gate's own landing: `.issues/756` carried a live
    # unterminated fence while the gate reported a clean 1517 files, because the
    # file was still untracked when it ran. It only becomes visible one commit
    # after the damage. `--exclude-standard` keeps gitignored vendored drops out
    # — walking the filesystem instead reported 25 findings in a vendored tree no
    # repo owns (`trap_exit_launder_audit.py`'s precedent, one axis over).
    listing = []
    for args in (["ls-files", "*.md"],
                 ["ls-files", "--others", "--exclude-standard", "*.md"]):
        listing += subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, encoding="utf-8", errors="replace",
        ).stdout.splitlines()      # NOT .split() — a tracked path may hold a space
    walked = 0
    for rel in listing:
        f = repo / rel
        if not f.is_file():
            continue
        walked += 1
        out += scan_text(rel, f.read_text(encoding="utf-8", errors="replace"))
    return out, walked


def main() -> int:
    # The parser's canary, before any verdict. A mis-phasing scanner reports
    # clean in BOTH directions (prose read as code and code read as prose), so
    # its failure is not a finding — it means no verdict is possible. Issue 789:
    # this gate ran for two days over 1517 files on a parser whose own first
    # canary had been destroyed by the very bug it guards and never replaced,
    # and which could not see a `~~~` fence at all.
    arm_failures = selftest()
    if arm_failures:
        print("✗ INSTRUMENT: the shared fence parser's selftest does not pass — "
              "a mis-phasing scanner reports clean either way, so the verdict "
              "below would mean nothing:")
        for f in arm_failures:
            print(f)
        return 2

    # …and THIS file's own arithmetic, which the parser's arm cannot reach
    # (Issue 775's sentence, Issue 790 T4).
    gate_failures = gate_selftest()
    if gate_failures:
        print("✗ INSTRUMENT: markdown_fence_gate's own arithmetic does not pass its "
              "arms, so the swallowed-line counts below would be unreadable:")
        for f in gate_failures:
            print(f)
        return 2

    findings, walked = unterminated(REPO_ROOT)

    if walked < MIN_FILES:
        print(f"✗ INSTRUMENT: walked {walked} tracked .md file(s) < floor {MIN_FILES} — "
              f"the population went blind; a clean verdict below would mean nothing")
        return 2

    if findings:
        for rel, line, swallowed in sorted(findings, key=lambda r: -r[2]):
            print(f"  ⛔ {rel}:{line} — fence never closed, {swallowed} line(s) "
                  f"render as code to EOF")
        print(f"✗ markdown fence gate FAILED — {len(findings)} unterminated fence(s) "
              f"over {walked} .md file(s). The reported line is the DANGLING "
              f"fence, not necessarily the defect: read the first non-blank body line "
              f"— code means a closer is missing, prose means the fence is an orphan.")
        return 1

    print(f"✓ markdown fence gate PASSED — 0 unterminated fence(s) over {walked} "
          f".md file(s), tracked + untracked-not-ignored (floor {MIN_FILES})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
