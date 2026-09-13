#!/usr/bin/env python3
"""AUDIT (report, exit 0): is `.highwater` a sound OWNERSHIP witness?

Issue 768 T3. The citation instruments (`issue_citation_gate.py`,
`citation_drift_sweep.py`) resolve number ownership from three witnesses —
worktree files, `git log` history, `heading_allocated()` — and a fourth is
proposed: `n <= .highwater ⇒ n was allocated here`. The Numbering Discipline
(read value+1, write back, never reuse) makes that an implication IF AND ONLY
IF the counter is CONTIGUOUS: every step +1, never a jump, never a reset.
A counter that jumped 765→768 would make the witness claim 766 and 767 for
numbers nobody ever allocated — and a witness that over-claims does not
merely miss findings, it VALIDATES wrong addresses (the exact failure class
the witness exists to prevent, inverted).

Two views, because neither alone can decide it:

  A (static)   numbers `n <= hw` with NO witness in `allocated()` — the
               over-claim EXPOSURE. Cannot distinguish "file-and-removed
               same day" (legitimately allocated, the Issue 766 class) from
               "never allocated" (a jump) — that is View B's job.
  B (dynamic)  the counter's own committed transitions over git history —
               a step > +1 is a GAP (numbers skipped: never allocated by
               anyone), a step < 0 is a RESET (monotonicity broken). Either
               one red-lines the witness for that repo+kind.

⛔ The `.benchmarks` kind is SEMANTICALLY NOT UNIFORM across the workspace:
riir-auth's `.benchmarks/.highwater` counts RECORDS while its files are named
after PLAN numbers (its AGENTS.md says so) — `n <= hw` claims nothing there.
The audit prints every kind but flags that one; the WITNESS (if landed per
Issue 768 T4) must be kind-aware, not blanket.

Report, not a gate (exit 0) — findings here inform the Issue 768 landing
decision; nothing reds off this script. Population derived (BOUNDARY.md +
`.git`), same source as every instrument in this family; an EMPTY population
exits 2 (instrument blind), never a green over zero repos.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import issue_citation_gate as icg  # noqa: E402

REPO_ROOT = HERE.parent
WORKSPACE = Path(os.environ.get("WORKSPACE_ROOT", str(REPO_ROOT.parent)))

# riir-auth's bench counter is COUNT-based (AGENTS.md: "the highwater counts
# bench RECORDS"); files are named for PLAN numbers. One documented exception,
# named inline where it is excused from witness semantics.
COUNT_BASED_BENCH = {"riir-auth"}


def counter_transitions(repo: Path, subdir: str) -> list[tuple[int, int]]:
    """Committed (old, new) value transitions, oldest first.

    `git log --reverse -p` over the counter file; each hunk's -old/+new pair
    is one transition. Merge commits that leave the value unchanged emit no
    hunk and no transition. A repo without history for the file (never
    committed, or not a git repo) returns [] — the caller reports that shape
    rather than guessing.
    """
    r = subprocess.run(
        ["git", "-C", str(repo), "log", "--all", "--reverse", "-p",
         "--format=format:__C__", "--", f"{subdir}/.highwater"],
        capture_output=True, text=True,
    )
    out: list[tuple[int, int]] = []
    old = new = None
    for line in r.stdout.splitlines():
        if line.startswith("__C__"):
            old = new = None
            continue
        m = re.match(r"^-(\d+)\s*$", line)
        if m:
            old = int(m.group(1))
            continue
        m = re.match(r"\+(\d+)\s*$", line)
        if m:
            new = int(m.group(1))
            if old is not None:
                out.append((old, new))
            old = new = None
    return out


def walk_transitions(transitions: list[tuple[int, int]]) -> dict:
    """Classify a transition timeline: gaps, resets, dual-bumps.

    `current` walks the timeline; a transition whose `old` is NOT `current`
    comes from a diverged lineage (two branches each bumped the counter —
    the intra-repo dual-allocation shape). Those are counted, not condemned:
    a dual-bump spends the SAME number twice and creates no gap.
    """
    gaps: list[tuple[int, int]] = []
    resets: list[tuple[int, int]] = []
    duals = 0
    current: int | None = None
    for old, new in transitions:
        if current is None:
            current = new
            if new - old > 1:
                gaps.append((old, new))
            continue
        if old != current:
            duals += 1
            base = current
        else:
            base = old
        if new > base + 1:
            gaps.append((base, new))
        elif new < base:
            resets.append((base, new))
        current = max(current, new)
    return {"gaps": gaps, "resets": resets, "duals": duals,
            "final": current}


def selftest() -> list[str]:
    fails: list[str] = []
    # gap: 765 -> 768 skips 766/767
    if walk_transitions([(765, 768)])["gaps"] != [(765, 768)]:
        fails.append("gap: a +3 step must record (765, 768)")
    # clean: three +1 steps
    w = walk_transitions([(1, 2), (2, 3), (3, 4)])
    if w["gaps"] or w["resets"] or w["final"] != 4:
        fails.append("clean: +1 steps must produce no findings")
    # reset: 766 -> 763
    if walk_transitions([(765, 766), (766, 763)])["resets"] != [(766, 763)]:
        fails.append("reset: a negative step must record (766, 763)")
    # dual-bump: two branches each 765->766, then 766->767
    w = walk_transitions([(765, 766), (765, 766), (766, 767)])
    if w["duals"] != 1 or w["gaps"] or w["final"] != 767:
        fails.append("dual: a diverged-lineage bump is counted, not a gap")
    # initial creation at N: the first transition's old is the pre-counter
    # state; a first hunk 0->100 is a jump from nothing, recorded as a gap
    # only when it skips (old != 0). Creation 0->1 is clean.
    if walk_transitions([(0, 1)])["gaps"]:
        fails.append("creation: 0->1 must be clean")
    if walk_transitions([(0, 100)])["gaps"] != [(0, 100)]:
        fails.append("creation: 0->100 must record the skipped 1..99")
    return fails


def main() -> int:
    fails = selftest()
    if fails:
        print("✗ highwater contiguity audit SELFTEST FAILED:")
        for f in fails:
            print(f"    {f}")
        return 2

    repos = icg.contract_repos(WORKSPACE)
    if not repos:
        print(f"✗ derived population is EMPTY under {WORKSPACE} — refusing "
              f"to report over zero repos")
        return 2

    rows = gaps_total = resets_total = 0
    print(f"highwater contiguity audit — {len(repos)} contract repo(s), "
          f"kinds {', '.join(icg.KINDS)}\n")
    print(f"{'repo/kind':<34s} {'hw':>5s} {'witnessed':>9s} {'missing':>7s} "
          f"{'gaps':>4s} {'resets':>6s} {'duals':>5s}  notes")
    for repo in sorted(repos, key=lambda p: p.name):
        for kind, sub in icg.KINDS.items():
            hw_f = repo / sub / ".highwater"
            if not hw_f.is_file():
                continue
            try:
                hw = int(hw_f.read_text(encoding="utf-8").strip().split()[-1])
            except (ValueError, IndexError, OSError):
                print(f"{repo.name}/{kind:<26s}  MALFORMED counter — "
                      f"numbering_gate.py owns that verdict")
                continue
            witnessed = icg.allocated(repo, sub)
            missing = [n for n in range(1, hw + 1) if n not in witnessed]
            tr = counter_transitions(repo, sub)
            w = walk_transitions(tr) if tr else {"gaps": [], "resets": [],
                                                 "duals": 0, "final": None}
            rows += 1
            gaps_total += len(w["gaps"])
            resets_total += len(w["resets"])
            notes = []
            if repo.name in COUNT_BASED_BENCH and kind == "Bench":
                notes.append("COUNT-BASED counter (records, not numbers) — "
                             "witness EXCLUDED by design")
            if not tr:
                notes.append("no committed history for the counter")
            elif w["final"] is not None and w["final"] != hw:
                notes.append(f"history final {w['final']} != worktree {hw} "
                             f"(uncommitted bump, the in-flight case)")
            if w["gaps"]:
                notes.append("GAPS " + ", ".join(f"{a}->{b}" for a, b in w["gaps"][:4]))
            if w["resets"]:
                notes.append("RESETS " + ", ".join(f"{a}->{b}" for a, b in w["resets"][:4]))
            if missing and len(missing) > 8:
                notes.append(f"{len(missing)} unwitnessed (file-and-removed "
                             f"class, or jump children)")
            print(f"{repo.name}/{kind:<26s} {hw:>5d} {hw - len(missing):>9d} "
                  f"{len(missing):>7d} {len(w['gaps']):>4d} "
                  f"{len(w['resets']):>6d} {w['duals']:>5d}  "
                  f"{'; '.join(notes) if notes else ''}")
    print(f"\n{rows} counter(s) audited · {gaps_total} gap(s) · "
          f"{resets_total} reset(s)")
    if gaps_total == 0 and resets_total == 0:
        print("✓ no counter ever jumped or reset — `n <= hw ⇒ allocated` "
              "holds for every numbered kind; the Issue 768 witness is "
              "SOUND up to the COUNT-BASED exclusions")
    else:
        print("✗ counter jumps/resets found — the witness would over-claim "
              "there; Issue 768 T4 must exclude those repo/kind pairs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
