#!/usr/bin/env python3
"""Issue 796 — measure the FP rate of the allocation-time dual-allocation gate.

Issue 791 T3 and Issue 795 both deferred a gate that reds when a commit
allocates a document number its remote parent already allocated, on the same
unmeasured quantity: its false-positive rate against the legitimate shape —
"a long-lived branch allocates ahead of its remote". This probe measures it.

The gate's would-be verdict at a historical moment is computed from data git
retains anyway:

    L = numbers ADDED under the numbered dirs in merge_base..local_tip
    R = numbers ADDED under the numbered dirs in merge_base..remote_tip
    RED  iff L ∩ R ≠ ∅   (both sides allocated since the divergence)
    else GREEN — including the one-sided-ahead case, which is exactly the
    shape the deferral feared and which is green BY CONSTRUCTION: if only one
    side allocated since the merge base, the intersection is empty.

Historical (local_tip, remote_tip) pairs come from the reflogs. The sampling
moments are the UNION of both timelines' entry timestamps — local-tip changes
AND remote-tracking moves. The union is load-bearing, not decoration: a fetch
moves origin/develop WITHOUT moving HEAD, so pairing only at local-tip changes
never samples the divergence-discovery moment, which is precisely when a
pre-pull/pre-push gate would have run (measured: this probe's first cut saw
48 green pairs in katgpt-rs and missed its own 791 RED). Reflog retention
(~90 d default) bounds the lookback honestly; the evaluated-pair count is the
blindness floor and a run with ZERO divergent pairs refuses rather than
printing a green zero.

A RED is not automatically a TRUE POSITIVE: a renumber that rename detection
misses, a cherry-pick that duplicated rather than replaced, or a same-session
push+fetch would all read as RED. The probe prints the intersection numbers
and the commits that added them on each side; the classification is recorded
in the issue file by hand. Report-only — exit 0 on every real scan, exit 2 on
a blind one.

    scripts/dual_allocation_fp_probe.py <repo> [<repo> ...]
"""

from __future__ import annotations

import bisect
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# The numbered dirs the numbering discipline governs (795's population —
# .benchmarks deliberately excluded: its leading number is the OWNING plan,
# a family per owner, measured 2026-09-04).
NUMBERED_DIRS = (".issues", ".plans", ".research", ".proposals")

NUM_RE = re.compile(r"^(\d+)_.*\.md$")


def git(repo: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, encoding="utf-8", errors="replace")
    if out.returncode != 0:
        return ""
    return out.stdout


def parse_reflog_ts(s: str) -> datetime | None:
    """`2026-09-15 10:00:00 +0700` -> aware datetime; None if unparseable.

    datetime.strptime with %z (not fromisoformat: it rejects the space
    separator and the colon-less offset on pre-3.11 interpreters).
    """
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S %z")
    except ValueError:
        return None


def numbers_added(repo: Path, rng: str, memo: dict) -> set[int]:
    """Numbers whose files were ADDED under the numbered dirs within rng.

    -M is load-bearing (791 T1's finding): without rename detection a
    RENUMBER reports as an add at its new number and the probe would count a
    resolved collision as a fresh allocation.
    """
    if rng in memo:
        return memo[rng]
    paths = list(NUMBERED_DIRS)
    out = git(repo, "log", "-M", "--diff-filter=A", "--name-only",
              "--format=", rng, "--", *paths)
    found: set[int] = set()
    for line in out.splitlines():
        name = os.path.basename(line.strip())
        m = NUM_RE.match(name)
        if m:
            found.add(int(m.group(1)))
    memo[rng] = found
    return found


def reflog_timeline(repo: Path, ref: str) -> list[tuple[datetime, str]]:
    """(entry_time, sha) points for a ref, oldest first, consecutive deduped.

    With --date=iso the %gd selector renders as the ENTRY time, which is what
    the pairing needs — the commit's author date is when the change was
    written, not when the tip moved.
    """
    out = git(repo, "reflog", "show", "--date=iso", "--format=%H%x00%gd", ref)
    pts: list[tuple[datetime, str]] = []
    for line in out.splitlines():
        if "\x00" not in line:
            continue
        sha, selector = line.split("\x00", 1)
        m = re.search(r"\{([^}]*)\}", selector)
        if not m or sha.strip("0") == "":
            continue
        ts = parse_reflog_ts(m.group(1))
        if ts is None:
            continue
        if pts and pts[-1][1] == sha:
            continue
        pts.append((ts, sha))
    pts.reverse()                         # git prints newest-first; pairing bisects ascending
    return pts


def pair_events(local: list[tuple[datetime, str]],
                remote: list[tuple[datetime, str]]) -> list[tuple[str, str]]:
    """Union-sample both timelines -> deduped (local_sha, remote_sha) pairs.

    At each event time from EITHER timeline, the pair is the tip each ref
    held at that moment — the state a gate invocation would have seen. A pair
    needs both refs to already exist (no backdating before a ref's first
    entry). Consecutive identical pairs collapse: nothing moved between them.
    """
    lts = [d for d, _ in local]
    rts = [d for d, _ in remote]
    pairs: list[tuple[str, str]] = []
    for t in sorted(set(lts) | set(rts)):
        i = bisect.bisect_right(lts, t) - 1
        j = bisect.bisect_right(rts, t) - 1
        if i < 0 or j < 0:
            continue
        pair = (local[i][1], remote[j][1])
        if not pairs or pairs[-1] != pair:
            pairs.append(pair)
    return pairs


def merge_base(repo: Path, a: str, b: str, memo: dict) -> str:
    key = (a, b) if a <= b else (b, a)
    if key not in memo:
        memo[key] = git(repo, "merge-base", a, b).strip()
    return memo[key]


def upstream_of_head(repo: Path) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD@{upstream}"],
        capture_output=True, encoding="utf-8", errors="replace")
    return out.stdout.strip() if out.returncode == 0 else ""


def probe_repo(repo: Path) -> dict:
    """All paired divergence points of one repo, with the gate's verdict."""
    r = {"repo": repo.name, "in_sync": 0, "one_sided": 0, "divergent": 0,
         "reds": [], "skipped": ""}
    up = upstream_of_head(repo)
    if not up:
        r["skipped"] = "no upstream"
        return r
    local = reflog_timeline(repo, "HEAD")
    remote = reflog_timeline(repo, up)
    if not local or not remote:
        r["skipped"] = f"reflog empty (HEAD={len(local)}, {up}={len(remote)})"
        return r
    memo: dict = {}
    for lsha, rsha in pair_events(local, remote):
        if lsha == rsha:
            r["in_sync"] += 1
            continue
        mb = merge_base(repo, lsha, rsha, memo)
        if not mb or mb in (lsha, rsha):
            r["one_sided"] += 1        # the feared shape: green by construction
            continue
        r["divergent"] += 1
        left = numbers_added(repo, f"{mb}..{lsha}", memo)
        right = numbers_added(repo, f"{mb}..{rsha}", memo)
        hit = left & right
        if hit:
            add_paths = list(NUMBERED_DIRS)
            r["reds"].append({
                "numbers": sorted(hit),
                "local_tip": lsha[:8], "remote_tip": rsha[:8],
                "left_commits": git(repo, "log", "-M", "--diff-filter=A",
                                    "--format=%h %s", f"{mb}..{lsha}",
                                    "--", *add_paths).strip().splitlines()[:6],
                "right_commits": git(repo, "log", "-M", "--diff-filter=A",
                                     "--format=%h %s", f"{mb}..{rsha}",
                                     "--", *add_paths).strip().splitlines()[:6],
            })
    return r


def selftest() -> list[str]:
    fails = []
    if NUM_RE.match("776_windows_cpu.md").group(1) != "776":
        fails.append("num: prefix not extracted")
    if NUM_RE.match("README.md") or NUM_RE.match("007.md"):
        fails.append("num: matched a non-numbered name")
    if parse_reflog_ts("2026-09-15 10:00:00 +0700") is None:
        fails.append("ts: the corpus's own reflog format did not parse")
    if parse_reflog_ts("not a date") is not None:
        fails.append("ts: garbage parsed as a date")
    # reflog order: git prints NEWEST first, pairing needs ascending — the
    # rewrite that added union sampling initially lost this reverse and the
    # real-data pair count collapsed from 48 to 1
    import unittest.mock as mock
    fake = "\n".join([
        "aaaa\x00HEAD@{2026-09-15 10:00:00 +0700}",
        "bbbb\x00HEAD@{2026-09-15 09:58:00 +0700}",
    ])
    with mock.patch.object(sys.modules[__name__], "git", lambda *a, **k: fake):
        pts = reflog_timeline(Path("."), "HEAD")
    if [p[1] for p in pts] != ["bbbb", "aaaa"]:
        fails.append(f"reflog: newest-first not reversed: {pts}")

    t1 = parse_reflog_ts("2026-09-15 10:01:00 +0700")
    t2 = parse_reflog_ts("2026-09-15 10:02:00 +0700")
    t3 = parse_reflog_ts("2026-09-15 10:03:00 +0700")
    # the divergence-discovery shape: local tip A, then a FETCH brings B at
    # t2 (HEAD does not move — a local-only sampler never sees this instant),
    # then local moves to C at t3. The t2 sample must pair (A, B).
    got = pair_events([(t1, "A"), (t3, "C")], [(t2, "B")])
    if got != [("A", "B"), ("C", "B")]:
        fails.append(f"pair: fetch-moment sampling lost: {got}")
    # in-sync convergence: while the remote ref does not exist (t1), no pair
    # is sampleable; the first moment both exist is the converged (B, B)
    got = pair_events([(t1, "A"), (t2, "B")], [(t2, "B")])
    if got != [("B", "B")]:
        fails.append(f"pair: in-sync convergence wrong: {got}")
    # consecutive identical pairs collapse
    got = pair_events([(t1, "A"), (t3, "A")], [(t2, "B"), (t3, "B")])
    if got != [("A", "B")]:
        fails.append(f"pair: dedupe failed: {got}")
    # a ref younger than the other yields no backdated pairs
    t0 = parse_reflog_ts("2026-09-15 10:00:00 +0700")
    got = pair_events([(t0, "A")], [(t2, "B")])
    if got != [("A", "B")]:
        fails.append(f"pair: pre-history backdated: {got}")
    return fails


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    fails = selftest()
    if fails:
        print("✗ dual_allocation_fp_probe SELFTEST FAILED:")
        for f in fails:
            print(f"    {f}")
        return 2

    total = {"in_sync": 0, "one_sided": 0, "divergent": 0, "reds": 0}
    for arg in sys.argv[1:]:
        repo = Path(arg).resolve()
        if not (repo / ".git").exists():
            print(f"— {repo.name}: no .git, skipped")
            continue
        r = probe_repo(repo)
        if r["skipped"]:
            print(f"— {r['repo']}: {r['skipped']}")
            continue
        total["in_sync"] += r["in_sync"]
        total["one_sided"] += r["one_sided"]
        total["divergent"] += r["divergent"]
        total["reds"] += len(r["reds"])
        print(f"{r['repo']}: {r['in_sync']} in-sync, {r['one_sided']} one-sided "
              f"(green by construction), {r['divergent']} divergent evaluated, "
              f"{len(r['reds'])} RED")
        for red in r["reds"]:
            print(f"    RED {red['numbers']} — local {red['local_tip']} vs "
                  f"remote {red['remote_tip']}")
            for side in ("left_commits", "right_commits"):
                for c in red[side]:
                    print(f"        [{side[0]}] {c}")
    print(f"\nTOTAL: {total['divergent']} divergent pair(s) "
          f"({total['one_sided']} one-sided green, {total['in_sync']} in-sync), "
          f"{total['reds']} RED")
    if total["divergent"] == 0 and total["one_sided"] == 0:
        print("⛔ BLIND — no pair evaluated at all; reflogs may be absent or "
              "too shallow. This is not a green zero.")
        return 2
    print("Classification (TP vs FP) is by hand per RED row — the probe "
          "prints the adding commits, the issue file records the verdict.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
