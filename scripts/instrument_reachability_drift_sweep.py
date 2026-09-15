#!/usr/bin/env python3
"""The instrument-reachability verdict over every contract repo, PINNED.

Issue 787 T6. Shipping the gate without this would be the defect Issue 783
records — a rule landed in one instrument and never generalised — committed
inside the issue that exists *because* a census missed something. Twelve other
verdict classes here carry both halves, and the asymmetry in 783 was not a
judgement call that was made; it was a step that was skipped.

The class transfers because the premise does: every contract repo has its own
`AGENTS.md`, its own `scripts/`, and its own workflows, and every one is read
by agents who enumerate what the document names. The classifier is the gate's —
`collect()` and `reachable()`, imported, never restated — so the two can never
disagree about what "reachable" means.

⛔ The first measurement changed the pin design, and that is the finding
------------------------------------------------------------------------
Measured 2026-09-14 over 16 repos: **95 unreachable** of 152 tracked
`scripts/*.py`. riir-train alone is **61 of 61** — its `scripts/` is almost
entirely plan-scoped one-offs (`plan341_band_pool.py`,
`plan346_diversity_gate.py`, `t504_harvest.py`), and its `AGENTS.md` names none
of them.

Read that honestly: in riir-train the predicate **over-captures**. A plan
artifact is not an instrument, and "nobody can find it from AGENTS.md" is the
expected, correct state for a script whose whole life was one plan task. The
per-repo gate's membership pin — a row and a REASON for each — is right for the
repo that owns it and 7 rows; it is not right for 95 rows across 15 repos whose
judgement calls are not this repo's to make.

So the sweep is a **RATCHET**, not a membership set:

    max_unreachable   pinned at each repo's measured count

That is the strongest claim this repo can honestly make about somebody else's
tree, and it is still actionable at exactly the margin that matters: the commit
that adds ANOTHER unfindable script reds. It is deliberately NOT the
`suite_membership_audit` outcome (1,203 rows, report-only, no verdict at all) —
the objection there was that the rows are load-bearing test targets and no
per-commit action follows from the number. Here the action is immediate and
local: name it, invoke it from something named, or decide it is ephemeral.

⚠ And it is deliberately not the Issue 785 rule either. That rule forbids
ratcheting a bucket whose meaning is *unanswered*, because such a bucket is a
backlog with no owner. This bucket means *unfindable*, every row has an owner,
and the ratchet is on the DERIVATIVE — it constrains what lands next, not what
already landed.

Two floors, and in 5 of 16 repos neither bites
-----------------------------------------------
`min_scripts` catches the walk going blind. `min_roots` catches the permissive
direction: with fewer roots, MORE scripts read as unreachable — so a shrinking
root set inflates the finding count rather than hiding it, and the floor is
about the instrument, not the tree.

⚠ Five repos have **0 tracked `scripts/*.py`** (riir-auth, riir-game-sdk,
riir-kat, riir-neuron-db, riir-viewbridge, seal-online-remaster), so both
quantities are 0 there and neither detects anything — Issue 783's population
shape, stated as a measurement rather than assumed. What rescues those rows is
that the gate's `DOC_ROOTS` handling is a REFUSAL and not a floor: a repo whose
`AGENTS.md` the walk cannot see is an instrument failure, not a clean zero.

`min_roots` also cannot be shared: it is 1 in riir-shader and 13 in katgpt-rs.

Why this is NOT in scripts/docs_gate.sh's CHECKS
------------------------------------------------
Identical to the other fourteen sweeps: CI has one checkout, the siblings are
private and simply absent, so this would either red on every run or derive an
EMPTY population and print a confident green over zero repos. The per-repo half
— `instrument_reachability_gate.py`, membership-pinned with a reason per row —
is the CI-side assertion.

Exit 0 clean, 1 on drift above the pins, **2 if the instrument itself is
untrustworthy**. `--canary` runs the adversary arms.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# DRY: the closure is the per-push gate's, so the sweep and the gate can never
# disagree about what "reachable" means.
import instrument_reachability_gate as irg  # noqa: E402
from skill_repo_set_gate import derive_repos  # noqa: E402
from sweep_population import population_verdict  # noqa: E402
from worktree_state import sweep_advisory  # noqa: E402

REPO_ROOT = HERE.parent
WORKSPACE = REPO_ROOT.parent
PINS = HERE / "instrument_reachability_floors.txt"

FIELDS = ("min_scripts", "min_roots", "max_unreachable")


def parse_pins(path: Path) -> dict[str, dict[str, int]]:
    rows: dict[str, dict[str, int]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 1 + len(FIELDS):
            raise ValueError(
                f"malformed pin row (want {1 + len(FIELDS)} fields): {raw!r}")
        rows[parts[0]] = dict(zip(FIELDS, (int(v) for v in parts[1:])))
    return rows


def classify(repo: Path) -> tuple[list[str], list[str], list[str]]:
    """(scripts, roots, unreachable) — the gate's own closure, per repo."""
    scripts, roots = irg.collect(repo)
    unreached = sorted(set(scripts) - irg.reachable(repo, scripts, roots))
    return scripts, roots, unreached


def selftest() -> list[str]:
    fails: list[str] = []

    # The gate's own arms cover the closure; INVOKING them here is what makes
    # "shared classifier" an assertion rather than an import statement.
    fails += [f"gate selftest: {f}" for f in irg.selftest()]
    for attr in ("collect", "reachable", "DOC_ROOTS"):
        if not hasattr(irg, attr):
            fails.append(f"gate lost `{attr}` — the sweep shares its closure "
                         f"and must not fall back to a copy")

    # katgpt-rs's own two floors are the gate's constants, not this file's
    # opinion — same quantity, two files, which is the drift `docs_gate_paths_
    # sync.py` exists for one axis over.
    if PINS.is_file():
        try:
            mine = parse_pins(PINS).get(REPO_ROOT.name, {})
        except ValueError as e:
            fails.append(f"own pins unreadable: {e}")
            mine = {}
        for field, owned in (("min_scripts", irg.MIN_SCRIPTS),
                             ("min_roots", irg.MIN_ROOTS)):
            if mine and mine.get(field) != owned:
                fails.append(
                    f"pin drift: {PINS.name} says {field}={mine.get(field)} for "
                    f"{REPO_ROOT.name}, the gate owns {owned} — change both")

    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        p = ws / "p.txt"
        p.write_text("# c\nrepo-a 40 8 7  # trailing\n\n", encoding="utf-8")
        if parse_pins(p) != {"repo-a": dict(zip(FIELDS, (40, 8, 7)))}:
            fails.append("pin parse: 4-field row not read correctly")
        p.write_text("repo-a 1 2\n", encoding="utf-8")
        try:
            parse_pins(p)
            fails.append("pin parse: short row accepted")
        except ValueError:
            pass

    return fails


def canary() -> int:
    """Perturb each axis and REQUIRE a red. See the gate's `canary()` for why
    this is a flag and not a transcript."""
    import contextlib
    import io

    global PINS, classify

    td = Path(tempfile.mkdtemp())
    pins_src = PINS.read_text(encoding="utf-8")
    real_pins = PINS
    real_classify = classify
    results = []

    fails = selftest()
    if fails:
        print("✗ SELFTEST FAILED before the canary — untrustworthy:")
        for f in fails:
            print(f"    {f}")
        return 2

    def arm(name, want_rc, want_text, pins=None, classify_fn=None):
        global PINS, classify
        PINS = td / "p.txt"
        PINS.write_text(pins if pins is not None else pins_src, encoding="utf-8")
        classify = classify_fn or real_classify
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                rc = main([], run_selftest=False)
        finally:
            PINS = real_pins
            classify = real_classify
        out = buf.getvalue()
        ok = rc == want_rc and want_text in out
        print(f"  {'✓' if ok else '✗'} {name}  (rc={rc}, want {want_rc})")
        if not ok:
            print(f"        wanted: {want_text}")
            for ln in [l for l in out.splitlines() if l.startswith(("✗", "⛔"))][:3]:
                print(f"        got: {ln}")
        results.append(ok)

    def bump(field_idx, delta):
        """Rewrite katgpt-rs's row, one field, by delta. Anchored on the row
        rather than on a literal, so the arm cannot silently stop perturbing
        when the pin is re-measured — the Issue 786 canary failure."""
        out = []
        hit = False
        for raw in pins_src.splitlines(keepends=True):
            body = raw.split("#", 1)[0]
            parts = body.split()
            if len(parts) == 1 + len(FIELDS) and parts[0] == REPO_ROOT.name:
                parts[1 + field_idx] = str(int(parts[1 + field_idx]) + delta)
                out.append("  ".join(parts) + "\n")
                hit = True
            else:
                out.append(raw)
        if not hit:
            raise AssertionError(f"canary: no {REPO_ROOT.name} row to perturb")
        return "".join(out)

    arm("baseline green", 0, "sweep PASSED")
    arm("new unreachable reds", 1, "unreachable ",
        classify_fn=lambda repo: (lambda t: (t[0] + ["scripts/ghost.py"], t[1],
                                             t[2] + ["scripts/ghost.py"]))(
            real_classify(repo)))
    arm("walk floor reds", 1, "walk FLOOR breached", pins=bump(0, 10_000))
    arm("roots floor reds", 1, "roots FLOOR breached", pins=bump(1, 10_000))
    arm("ratchet reds", 1, "> pinned", pins=bump(2, -1))
    arm("unpinned repo reds", 1, "UNPINNED",
        pins="".join(l for l in pins_src.splitlines(keepends=True)
                     if not l.split("#", 1)[0].split()[:1]
                     or l.split("#", 1)[0].split()[0] != REPO_ROOT.name))
    arm("empty pins refused", 2, "declares NO repos", pins="# nothing\n")
    arm("short row refused", 2, "unreadable", pins="repo-a 1 2\n")

    print(f"\n{sum(results)}/{len(results)} canary arm(s) PASSED")
    return 0 if all(results) else 2


def main(argv: list[str], run_selftest: bool = True) -> int:
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass

    if "--canary" in argv:
        return canary()

    fails = selftest() if run_selftest else []
    if fails:
        print("✗ instrument-reachability sweep SELFTEST FAILED — untrustworthy:")
        for f in fails:
            print(f"    {f}")
        return 2

    if not PINS.is_file():
        print(f"✗ pins file missing: {PINS}")
        return 2
    try:
        pins = parse_pins(PINS)
    except ValueError as e:
        print(f"✗ pins file unreadable: {e}")
        return 2
    if not pins:
        print("✗ pins file declares NO repos — an empty expectation set is refused")
        return 2

    names = derive_repos(WORKSPACE)
    if not names:
        print(f"✗ derived population is EMPTY under {WORKSPACE} — refusing to "
              f"report a green over zero repos")
        return 2

    bad = False
    tot_s = tot_r = tot_u = 0

    for name in names:
        repo = WORKSPACE / name
        scripts, roots, unreached = classify(repo)
        tot_s += len(scripts)
        tot_r += len(roots)
        tot_u += len(unreached)

        row = pins.get(name)
        flags = []
        if row is None:
            flags.append("UNPINNED — add a row (or it can never red)")
        else:
            if len(scripts) < row["min_scripts"]:
                flags.append(f"walk FLOOR breached: {len(scripts)} tracked "
                             f"scripts/*.py < {row['min_scripts']} — the walk "
                             f"went blind and the count below means nothing")
            if len(roots) < row["min_roots"]:
                flags.append(f"roots FLOOR breached: {len(roots)} < "
                             f"{row['min_roots']} — with fewer roots MORE "
                             f"scripts read as unreachable, so this floor is "
                             f"about the instrument, not the tree")
            if len(unreached) > row["max_unreachable"]:
                flags.append(f"unreachable {len(unreached)} > pinned "
                             f"{row['max_unreachable']} — a new script that no "
                             f"root and no documented instrument names")
                for p in unreached:
                    print(f"      ⛔ {name}/{p}")

        status = "✗" if flags else ("·" if unreached else "✓")
        print(f"{status} {name:22s} scripts={len(scripts):<3d} "
              f"roots={len(roots):<3d} unreachable={len(unreached)}")
        for f in flags:
            bad = True
            print(f"      ✗ {f}")

    pop_lines, deferred, pop_fail = population_verdict(pins, names)

    # Issue 797 — the worktree is not the repo. This run reads files that
    # concurrent sessions are editing, so a finding may sit on a line no
    # commit contains. ADVISORY, never a failure: a sweep that hard-reds on
    # an ordinary dirty worktree is a sweep nobody runs. It rides the FINAL
    # line in BOTH directions (the `deferred` precedent) and is SILENT
    # unless the dirty set meets this sweep's own population — the scripts walked + every ROOT the closure starts from.
    deferred.extend(sweep_advisory(
        names, ("scripts/*.py", "AGENTS.md", "scripts/docs_gate.sh",
     ".github/workflows/*.yml"), root=WORKSPACE))
    for _line in pop_lines:
        print(_line)
    if pop_fail:
        bad = True

    print(f"\n{len(names)} contract repo(s) · {tot_s} tracked scripts/*.py · "
          f"{tot_r} root(s) · {tot_u} unreachable")
    print("  the ceiling is a RATCHET, not a wall, and only here: this repo's "
          "own 7 rows are pinned by MEMBERSHIP with a reason each in "
          "instrument_reachability_gate.py. 95 rows across 15 repos are not "
          "this repo's judgement calls to make, and in riir-train (61 of 61) "
          "the predicate OVER-CAPTURES — a plan-scoped one-off is not an "
          "instrument. The ratchet constrains what lands NEXT.")

    if bad:
        print("✗ instrument-reachability sweep FAILED — see the ✗ rows above")
        for _d in deferred:
            print(f"  ⚠ {_d}")
        return 1
    _line = "✓ instrument-reachability sweep PASSED — every repo within its pins"
    if deferred:
        _line += "; DEFERRED: " + "; ".join(deferred)
    print(_line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
