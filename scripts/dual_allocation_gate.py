#!/usr/bin/env python3
"""Issue 796 — the allocation-time dual-allocation gate, CLASSIFIED.

Issue 791 T3 deferred a gate that reds when this checkout and its upstream
have both allocated document numbers since their merge base, on the unmeasured
fear: "a long-lived branch legitimately allocates ahead of its remote".
Issue 796 measured that fear MOOT (7202 one-sided pairs workspace-wide, all
green BY CONSTRUCTION — the intersection is empty whenever only one side
allocated) and measured the gate's real hazard instead: of 39 distinct
workspace divergence incidents, 31 were TWINs — the same document carried on
two post-rebase lines of history, where a naive hard gate cries wolf and the
remedy is one fetch.

So the verdict is CLASSIFIED, structurally, by filename stem per colliding
number:

    TWIN        same stem added on both sides since the merge base — your own
                rebased/cherry-picked line still sitting in the stale
                remote-tracking ref. Annotated, exit-neutral: `git fetch`
                resolves it; failing the run on it would train people to
                ignore the gate.
    INDEPENDENT different stems, same number — two distinct documents are
                about to own one number. RED, exit 1, both sides' adding
                commits named. This is the 791/780/935 class, caught while
                both sides are still diverging — one `git fetch` + a renumber
                now, instead of a citation-drift archaeology later.

One numbered document per repo view: the gate reads THIS checkout's tips
(HEAD and its upstream), not history — the historical replay is the probe's
job (`dual_allocation_fp_probe.py`). Reach limit, measured in 796: the gate
catches the divergences the running box participates in; a box-vs-box
collision on the wire is invisible here until a fetch brings it in, and the
merge-time wall (numbering_gate + 795) owns what lands despite that.

    scripts/dual_allocation_gate.py [repo]        # verdict (default: this repo)
    scripts/dual_allocation_gate.py --prove-fires # the two-session collision
                                                  # fixture, both verdicts

Exit codes: 0 = clean or TWIN-only; 1 = INDEPENDENT collision; 2 = blind
(no upstream / no reflog / self-test failure) — a gate that cannot see must
refuse, never print a green zero.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# The probe owns the shared machinery: dirs, regex, reflog-free git plumbing.
# Imported, not copied — the Issue 755 rule.
from dual_allocation_fp_probe import (  # noqa: E402
    NUMBERED_DIRS, NUM_RE, git, numbers_added, selftest as probe_selftest,
)


def upstream_of_head(repo: Path) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD@{upstream}"],
        capture_output=True, encoding="utf-8", errors="replace")
    return out.stdout.strip() if out.returncode == 0 else ""


def added_stems(repo: Path, rng: str) -> dict[int, set[str]]:
    """Number -> the filename stems added under the numbered dirs within rng."""
    out = git(repo, "log", "-M", "--diff-filter=A", "--name-only",
              "--format=", rng, "--", *NUMBERED_DIRS)
    stems: dict[int, set[str]] = {}
    for line in out.splitlines():
        base = os.path.basename(line.strip())
        m = NUM_RE.match(base)
        if m:
            stems.setdefault(int(m.group(1)), set()).add(base[:-3])
    return stems


def adding_commits(repo: Path, rng: str, want: set[int]) -> list[str]:
    """One line per commit in rng that added a file numbered in `want`."""
    out = git(repo, "log", "-M", "--diff-filter=A", "--name-only",
              "--format=%h %s", rng, "--", *NUMBERED_DIRS)
    rows: list[str] = []
    cur: str | None = None
    for line in out.splitlines():
        if re.match(r"^\w{7,} ", line):
            cur = line
        else:
            base = os.path.basename(line.strip())
            m = NUM_RE.match(base)
            if cur and m and int(m.group(1)) in want and cur not in rows:
                rows.append(cur)
    return rows[:6]


def classify(repo: Path) -> tuple[list[dict], str]:
    """(rows, skip_reason). Each row: one colliding number, classified."""
    up = upstream_of_head(repo)
    if not up:
        return [], "no upstream configured for HEAD"
    head = git(repo, "rev-parse", "HEAD").strip()
    remote_tip = git(repo, "rev-parse", up).strip()
    if not head or not remote_tip:
        return [], "cannot resolve HEAD or the upstream tip"
    mb = git(repo, "merge-base", head, remote_tip).strip()
    if not mb:
        return [], "no merge base (unrelated histories?)"
    if mb in (head, remote_tip):
        return [], ""                       # one-sided or in sync: green
    left = added_stems(repo, f"{mb}..{head}")
    right = added_stems(repo, f"{mb}..{remote_tip}")
    rows: list[dict] = []
    for n in sorted(set(left) & set(right)):
        twin = bool(left[n] & right[n])
        rows.append({
            "number": n, "twin": twin,
            "left_stems": sorted(left[n]), "right_stems": sorted(right[n]),
            "left_commits": [] if twin else
            adding_commits(repo, f"{mb}..{head}", {n}),
            "right_commits": [] if twin else
            adding_commits(repo, f"{mb}..{remote_tip}", {n}),
        })
    return rows, ""


# ── the fixture: a real two-session collision, built in a temp dir ─────────
def build_fixture(base: Path) -> Path:
    import subprocess as sp

    def run(repo: Path, *args: str) -> None:
        r = sp.run(["git", "-C", str(repo), *args], capture_output=True,
                   encoding="utf-8")
        if r.returncode != 0:
            raise RuntimeError(f"git {args}: {r.stderr}")

    root = base / "dual_alloc_fixture"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir()
    shared = root / "shared.git"
    a = root / "a"
    b = root / "b"
    run(root, "init", "-q", "-b", "main", "--bare", str(shared))
    sp.run(["git", "clone", "-q", str(shared), str(a)], check=True,
           capture_output=True)
    (a / ".issues").mkdir()
    (a / ".issues" / "README.md").write_text("x\n", encoding="utf-8")
    run(a, "add", ".issues")
    run(a, "commit", "-qm", "base")
    sp.run(["git", "-C", str(a), "push", "-q", "-u", "origin", "main"],
           check=True, capture_output=True)
    # session B forks BEFORE any allocation lands, allocates 900, pushes
    sp.run(["git", "clone", "-q", str(shared), str(b)], check=True,
           capture_output=True)
    for repo in (a, b):
        run(repo, "config", "user.email", "f@f")
        run(repo, "config", "user.name", "fixture")
    (b / ".issues" / "900_b_side.md").write_text("b\n", encoding="utf-8")
    run(b, "add", ".issues")
    run(b, "commit", "-qm", "B allocates 900")
    sp.run(["git", "-C", str(b), "push", "-q", "origin", "main"], check=True,
           capture_output=True)
    # session A allocates the SAME number locally, then fetches — the gate's
    # invocation moment. HEAD does not move on fetch; the divergence is live.
    (a / ".issues" / "900_a_side.md").write_text("a\n", encoding="utf-8")
    run(a, "add", ".issues")
    run(a, "commit", "-qm", "A allocates 900 independently")
    sp.run(["git", "-C", str(a), "fetch", "-q", "origin"], check=True,
           capture_output=True)
    return root


def prove_fires() -> list[str]:
    """The gate must RED on the constructed collision and stay exit-neutral
    on the twin shape. Both arms against real git repos, not mocks."""
    import tempfile
    import subprocess as sp
    fails: list[str] = []

    def run(repo: Path, *args: str) -> None:
        r = sp.run(["git", "-C", str(repo), *args], capture_output=True,
                   encoding="utf-8")
        if r.returncode != 0:
            raise RuntimeError(f"git {args}: {r.stderr}")

    with tempfile.TemporaryDirectory() as td:
        root = build_fixture(Path(td))
        a, b = root / "a", root / "b"
        rows, skip = classify(a)
        if skip:
            return [f"fixture skipped: {skip}"]
        indep = [r for r in rows if not r["twin"]]
        if len(indep) != 1 or indep[0]["number"] != 900:
            fails.append(f"fixture: expected exactly RED 900, got {rows}")
        elif not (indep[0]["left_commits"] and indep[0]["right_commits"]):
            fails.append("fixture: RED 900 lacks the adding-commit rows")
        # ── the TWIN arm, same fixture: BOTH sides write the SAME stem. B
        # (which owns the remote line) pushes 901; A writes 901 and stays
        # unpushed. Both sides hold 901 since mb: same stem → TWIN
        # (exit-neutral); 900 stays INDEPENDENT (RED).
        (a / ".issues" / "901_twin_doc.md").write_text("t\n", encoding="utf-8")
        run(a, "add", ".issues")
        run(a, "commit", "-qm", "A writes the twin 901")
        (b / ".issues" / "901_twin_doc.md").write_text("t2\n", encoding="utf-8")
        run(b, "add", ".issues")
        run(b, "commit", "-qm", "B writes the twin 901")
        sp.run(["git", "-C", str(b), "push", "-q", "origin", "main"],
               check=True, capture_output=True)
        sp.run(["git", "-C", str(a), "fetch", "-q", "origin"], check=True,
               capture_output=True)
        rows2, _ = classify(a)
        twins = [r for r in rows2 if r["twin"]]
        indep2 = [r for r in rows2 if not r["twin"]]
        if not any(r["number"] == 901 for r in twins):
            fails.append(f"fixture: twin 901 not classified TWIN: {rows2}")
        if [r["number"] for r in indep2] != [900]:
            fails.append(f"fixture: 900 must stay INDEPENDENT: {rows2}")
    return fails


def selftest() -> list[str]:
    fails = probe_selftest()
    if not callable(numbers_added):
        fails.append("probe import: numbers_added missing")
    return fails


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--prove-fires" in sys.argv:
        fails = prove_fires()
        if fails:
            print("✗ prove-fires FAILED — the gate cannot see its own class:")
            for f in fails:
                print(f"    {f}")
            return 2
        print("✓ prove-fires PASS — constructed collision REDs with adding "
              "commits named; twin shape classifies exit-neutral")
        return 0
    if "--self-test" in sys.argv:
        fails = selftest()
        if fails:
            print("✗ dual_allocation_gate SELFTEST FAILED:")
            for f in fails:
                print(f"    {f}")
            return 2
        print("✓ selftest PASS")
        return 0
    if len(args) > 1:
        print("usage: dual_allocation_gate.py [repo] | --prove-fires | --self-test")
        return 2
    repo = Path(args[0]).resolve() if args else Path.cwd()

    fails = selftest()
    if fails:
        print("✗ dual_allocation_gate SELFTEST FAILED — gate untrustworthy:")
        for f in fails:
            print(f"    {f}")
        return 2

    rows, skip = classify(repo)
    if skip:
        print(f"— dual_allocation_gate DEFERRED: {skip}. "
              "Not a green zero — the gate could not see.")
        return 2
    twins = [r for r in rows if r["twin"]]
    indep = [r for r in rows if not r["twin"]]
    print(f"dual_allocation_gate {repo.name}: {len(twins)} twin, "
          f"{len(indep)} independent colliding number(s)")
    for r in twins:
        print(f"  TWIN {r['number']} — same document on both lines "
              f"(rebased own work; a fetch resolves): "
              f"{r['left_stems'][:2]} vs {r['right_stems'][:2]}")
    for r in indep:
        print(f"  ⛔ INDEPENDENT {r['number']} — two documents claim one number")
        for s in r["left_stems"]:
            print(f"      [local ] {s}")
        for s in r["right_stems"]:
            print(f"      [remote] {s}")
        for c in r["left_commits"]:
            print(f"      [local ] {c}")
        for c in r["right_commits"]:
            print(f"      [remote] {c}")
    if indep:
        print("Renumber ONE side before pushing — Issue 791 T2's protocol, "
              "caught at allocation time instead of merge time.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
