#!/usr/bin/env python3
"""The workstation sweeps' POPULATION verdict — one copy (Issue 779).

Every drift sweep in `scripts/` pins per-repo rows and then has to answer the
same question about the rows it did NOT see: is a pinned repo missing because
it was retired and somebody forgot the row, or because this box carries a
subset of the workspace? Those are set-identical from the walk alone, which is
why the answer is an **explicit marker** and never an inference
(`DOCS_GATE_PARTIAL_CLONE=1`, Issue 765).

Seven sweeps carried this loop, byte-identical, copy-pasted:

    for name in sorted(set(pins) - present):
        bad = True
        print(f"✗ {name}: pinned but ABSENT from the derived walk — it was "
              f"retired (drop the row in that commit) or the walk went blind")

and hard-red on a known partial-clone box with every content assertion green.
A sweep that always reds is a sweep nobody runs, and its findings go unread
with it — measured: the percentile sweep's Issue-777 findings (a fabricated
floor, a correctly-shaped defect at the wrong address) sat behind four of these
reds for as long as the rows had existed. The raw remedy text is also the
dangerous one: "drop the row in that commit", offered on the box least
qualified to decide that, deletes live repos from the canonical set.

Three verdicts, and they are not interchangeable:

- **UNREGISTERED** — on this box, absent from `repo_set.txt`. A repo JOINING
  the workspace. Reds in EVERY posture; no amount of partial checkout explains
  a directory that is right there.
- **UNSEEN** — pinned (or in the snapshot) and not on this box, WITHOUT the
  marker. Never a pass: the instrument could not measure a repo it claims to
  cover.
- **DEFERRED** — the same set, WITH the marker. Reported loudly on the sweep's
  final line, so a green never reads as a claim about repos this run never
  touched.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from skill_repo_set_gate import PARTIAL_MARKER, partial_clone_state  # noqa: E402


def population_verdict(pins, present) -> tuple[list[str], list[str], int]:
    """(lines, deferred, failures) for the rows this run could not measure.

    `pins`     — the repo names this sweep has a row for.
    `present`  — the repo names the derived walk actually found.

    `lines` print immediately (they are findings). `deferred` ride the sweep's
    FINAL line in both directions — a deferral printed only on failure is a
    deferral nobody reads on the run that passes.
    """
    present = sorted(set(present))
    lines: list[str] = []
    deferred: list[str] = []
    failures = 0

    marker_on, snap_absent, unregistered = partial_clone_state(present)

    if unregistered:
        lines.append(
            "⛔ UNREGISTERED (on this box, absent from repo_set.txt — regenerate "
            "it on the canonical workstation and commit): "
            + ", ".join(unregistered))
        failures += len(unregistered)

    # The snapshot widens the set deliberately: a repo in `repo_set.txt` that
    # this sweep has no row for is still a repo this run did not measure, and
    # the per-sweep UNPINNED check cannot see it — that check only fires on
    # repos the walk FOUND.
    absent = sorted((set(pins) | set(snap_absent)) - set(present))
    if absent:
        if marker_on:
            deferred.append(
                f"{len(absent)} contract repo(s) not on this box "
                f"({', '.join(absent)}) — DEFERRED by {PARTIAL_MARKER}=1, "
                "NOT measured by this run")
        else:
            lines.append(
                "⛔ UNSEEN (a contract repo this run could not measure — never a "
                f"pass; set {PARTIAL_MARKER}=1 on a box you KNOW carries a "
                "subset, or remove the row if the repo is genuinely gone): "
                + ", ".join(absent))
            failures += len(absent)

    return lines, deferred, failures


def selftest() -> list[str]:
    """Both postures, and the arm that must red under BOTH.

    Written against the real `repo_set.txt`, because the helper's whole job is
    to compare against that file and a stubbed snapshot would test the stub.
    The arms therefore assert RELATIVE movement (a repo removed from `present`
    becomes absent; a fabricated name becomes unregistered) rather than exact
    counts, which depend on the box.
    """
    import os

    from skill_repo_set_gate import SNAPSHOT

    fails: list[str] = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    if not SNAPSHOT.is_file():
        return ["repo_set.txt is missing — the helper cannot be self-tested"]
    snap = [l.strip() for l in SNAPSHOT.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")]
    check(len(snap) >= 10, f"repo_set.txt reads {len(snap)} repos — too few to "
                           "exercise the arms; the parse is broken")

    saved = os.environ.get(PARTIAL_MARKER)
    try:
        # ── no marker ──────────────────────────────────────────────────────
        os.environ.pop(PARTIAL_MARKER, None)
        lines, deferred, n = population_verdict(snap, snap)
        check((lines, deferred, n) == ([], [], 0),
              f"a complete population was not clean: {lines} {deferred} {n}")

        lines, deferred, n = population_verdict(snap, snap[:-1])
        check(n == 1 and deferred == [] and any("UNSEEN" in l for l in lines),
              f"a missing repo without the marker must be UNSEEN: {lines} {n}")

        # ── marker on ──────────────────────────────────────────────────────
        os.environ[PARTIAL_MARKER] = "1"
        lines, deferred, n = population_verdict(snap, snap[:-1])
        check(n == 0 and len(deferred) == 1 and lines == [],
              f"a missing repo WITH the marker must defer, not red: {lines} {n}")
        check(snap[-1] in deferred[0] and PARTIAL_MARKER in deferred[0],
              f"the deferral names neither the repo nor the marker: {deferred}")

        # UNREGISTERED reds under the marker too — this is the arm that proves
        # the marker is not a blanket amnesty.
        lines, deferred, n = population_verdict(snap, snap + ["a-repo-that-joined"])
        check(n == 1 and any("UNREGISTERED" in l for l in lines),
              f"an unregistered repo did not red under the marker: {lines} {n}")

        # A sweep with NO row for a repo the snapshot knows is still missing a
        # measurement — the per-sweep UNPINNED check cannot see it, because
        # that check only fires on repos the walk found.
        lines, deferred, n = population_verdict([], snap[:-1])
        check(len(deferred) == 1 and snap[-1] in deferred[0],
              f"the snapshot did not widen an empty pin set: {deferred}")
    finally:
        if saved is None:
            os.environ.pop(PARTIAL_MARKER, None)
        else:
            os.environ[PARTIAL_MARKER] = saved

    return fails


def main() -> int:
    fails = selftest()
    if fails:
        print("sweep_population selftest FAILED:")
        for f in fails:
            print("  ✗ " + f)
        return 1
    print("✓ sweep_population selftest — 7 assertion(s): complete population "
          "clean, UNSEEN without the marker, DEFERRED with it (naming repo + "
          "marker), UNREGISTERED reds under the marker, snapshot widens an "
          "empty pin set")
    return 0


if __name__ == "__main__":
    sys.exit(main())
