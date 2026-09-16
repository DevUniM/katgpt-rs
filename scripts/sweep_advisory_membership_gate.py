#!/usr/bin/env python3
""""Every sweep" must be a MEMBERSHIP assertion, not a count in prose.

Issue 797 T5. The Issue-797 worktree advisory landed in all sixteen sweeps that
existed that morning, and AGENTS.md said so — "wired into all sixteen sweeps",
a hand-typed figure. **Two hours later there were eighteen**: a concurrent
session landed `pipefail_discard_drift_sweep.py` and
`toolchain_override_drift_sweep.py`, neither wired, and nothing noticed. The
prose was stale before the commit that wrote it had finished being pushed.

That is the standing failure mode of this repo, recorded seven times now
(Issues 777, 778, 793, 782, 783, 789, 797): **a rule landed in one instrument
and never generalised.** Every previous instance was repaired by grepping the
family by hand and fixing the copies. This one is repaired by making the family
gate itself: a new `*_drift_sweep.py` that does not call `sweep_advisory()`
REDS, so the next one cannot land unwired.

The quantity to gate is NOT the count — this repo already has the rule written
for `cfg_gated_floor_gate`: *a set is gateable where its cardinality is not.* A
count is green on a swap (one sweep wired, one unwired, total unchanged), and
it goes stale the moment the family grows, which is precisely what happened.

⚠ **What this does NOT assert:** that the patterns a sweep passes actually name
its own population. A sweep that calls `sweep_advisory(names, ("*.lean",))`
over a Rust walk is silent forever and reads as wired. That is a per-sweep read
and is not statically decidable — the same limit `check_validation_gate`
records about arm QUALITY. Read the verdict as the weaker thing it is.

Exemptions are pinned by MEMBERSHIP with a REASON per row
(`scripts/sweep_advisory_expected.txt`); a reasonless row is refused, and a row
whose sweep has since been wired REDS — a pin file that only ever loosens is a
backlog wearing a pin (Issue 785's rule).

    scripts/sweep_advisory_membership_gate.py    # the verdict AND the arms

The arms run UNCONDITIONALLY, behind no flag: `docs_gate.sh` invokes each check
as `"$PY" "$script"` with no arguments, so an arm behind `'--canary' in
sys.argv` never fires on a push (Issue 789's finding, measured on the eight
adversary arms that had landed the day before). They cost ~0.05s.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
from pathlib import Path

# Issue 804: this instrument is documented as directly invokable, and its
# verdict glyphs (✓ ✗ ⛔ ⚠) kill it on a non-UTF-8 console — no verdict at
# all, findings unread. docs_gate.sh's PYTHONIOENCODING only covers runs
# that go through the wrapper.
import console_safe  # noqa: E402

console_safe.apply()

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent

PINS = HERE / "sweep_advisory_expected.txt"
GLOB = "*_drift_sweep.py"
# ⛔ Its FIRST run found that this was ONE name where there are two. A sweep
# whose findings carry a file:line address wires the RICHER row-level split and
# calls `worktree_advisory()` directly with its UNCOMMITTED and MASKED counts;
# `sweep_advisory()` is the repo-level convenience over it.
# `citation_drift_sweep` is wired more thoroughly than any other member and read
# UNWIRED. A predicate that names one of two entry points reports the most
# careful caller as the defect — so the criterion is the MECHANISM, by set.
WANTED = ("sweep_advisory", "worktree_advisory")

# Two floors, failing differently.
#   MIN_SWEEPS  the WALK — a glob that matches nothing reports every sweep
#               wired and prints a confident green over zero of them.
#   MIN_WIRED   the AST RESOLUTION — a walk that finds every sweep and credits
#               none looks exactly like nobody having wired any, and the
#               obvious remedy is to pin them all.
MIN_SWEEPS = 15
MIN_WIRED = 15


def tracked_sweeps(root: Path) -> list[str]:
    """The family, as git tracks it. A filesystem walk would count a scratch
    copy somebody left in `scripts/` as a member of the contract."""
    if not (root / ".git").is_dir():
        return sorted(p.name for p in (root / "scripts").glob(GLOB))
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "scripts/" + GLOB],
        capture_output=True, encoding="utf-8", errors="replace")
    if out.returncode != 0:
        return sorted(p.name for p in (root / "scripts").glob(GLOB))
    return sorted(Path(p).name for p in out.stdout.split() if p.strip())


def calls_advisory(src: str) -> bool:
    """Does this module CALL `sweep_advisory`, not merely mention it?

    AST, not text, for the reason `subprocess_encoding_gate` moved to one: a
    text scanner reports the fixture strings inside this file's own arms, and
    the repairs on offer are to exempt the gate from itself or to obfuscate its
    test data. An exempt gate certifies nothing.

    An IMPORT alone is not enough either — an unused import is exactly what a
    half-finished wiring looks like, and it is the state the two Issue-797
    stragglers would have been in had somebody started and stopped.
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = (fn.id if isinstance(fn, ast.Name)
                else fn.attr if isinstance(fn, ast.Attribute) else "")
        if name in WANTED:
            return True
    return False


def parse_pins(path: Path) -> tuple[dict[str, str], list[str]]:
    """({sweep: reason}, errors). A reasonless row is an ERROR, not a pin."""
    pins: dict[str, str] = {}
    errs: list[str] = []
    if not path.is_file():
        return pins, errs
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, _, reason = line.partition("#")
        name, reason = name.strip(), reason.strip()
        if not reason:
            errs.append(f"{path.name}:{n}: `{name}` has NO reason — a row "
                        f"nobody had to justify is a backlog wearing a pin")
            continue
        pins[name] = reason
    return pins, errs


def verdict(root: Path, pins: dict[str, str]) -> tuple[list[str], list[str],
                                                       list[str], int]:
    """(wired, unwired, stale_pins, n_sweeps) for one repo."""
    sweeps = tracked_sweeps(root)
    wired, unwired = [], []
    for name in sweeps:
        p = root / "scripts" / name
        if not p.is_file():
            continue
        (wired if calls_advisory(p.read_text(encoding="utf-8", errors="replace"))
         else unwired).append(name)
    # A pin whose sweep is wired, or gone, no longer describes anything. Both
    # directions red: the file must not be allowed to only ever loosen.
    stale = [n for n in pins if n in wired or n not in sweeps]
    return wired, unwired, stale, len(sweeps)


# ───────────────────────────── arms ───────────────────────────────────────

def _fixture(tmp: Path, bodies: dict[str, str]) -> Path:
    root = tmp / "repo"
    (root / "scripts").mkdir(parents=True)
    for name, body in bodies.items():
        (root / "scripts" / name).write_text(body, encoding="utf-8")
    return root


WIRED_SRC = ("from worktree_state import sweep_advisory\n"
             "def main():\n"
             "    deferred.extend(sweep_advisory(names, ('*.rs',), root=W))\n")
IMPORT_ONLY_SRC = ("from worktree_state import sweep_advisory\n"
                   "def main():\n"
                   "    pass\n")
MENTION_ONLY_SRC = ('S = "call sweep_advisory here one day"\n'
                    "def main():\n"
                    "    pass\n")


def classifier_arms() -> list[str]:
    fails: list[str] = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    check(calls_advisory(WIRED_SRC), "a real call was not credited")
    check(not calls_advisory(IMPORT_ONLY_SRC),
          "an IMPORT with no call was credited — that is exactly what a "
          "half-finished wiring looks like")
    check(not calls_advisory(MENTION_ONLY_SRC),
          "a STRING mentioning the name was credited — this gate's own arms "
          "carry such strings, and a text scanner reports them as wiring")
    check(calls_advisory("import m\ndef f():\n    m.sweep_advisory(a, b)\n"),
          "a qualified `module.sweep_advisory(...)` call was not credited")
    # The row-level entry point counts too, and this arm exists because the
    # gate's first run reported `citation_drift_sweep` — the most thoroughly
    # wired member in the family — as UNWIRED.
    check(calls_advisory("def f():\n    worktree_advisory(s, u, m)\n"),
          "the ROW-LEVEL entry point was not credited: a sweep that wires the "
          "richer split reads as the defect")
    check(not calls_advisory("def f(:\n"),
          "an UNPARSED module was credited — silence is not evidence")
    return fails


def pin_arms() -> list[str]:
    """The gate's own pin arithmetic, which the classifier cannot reach."""
    fails: list[str] = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        f = tmp / "pins.txt"

        f.write_text("# comment\n\na_drift_sweep.py  # deliberate: reason here\n",
                     encoding="utf-8")
        pins, errs = parse_pins(f)
        check(pins == {"a_drift_sweep.py": "deliberate: reason here"} and not errs,
              f"a well-formed pin did not parse: {pins} {errs}")

        f.write_text("b_drift_sweep.py\n", encoding="utf-8")
        pins, errs = parse_pins(f)
        check(pins == {} and len(errs) == 1,
              f"a REASONLESS row was accepted as a pin: {pins} {errs}")

        pins, errs = parse_pins(tmp / "absent.txt")
        check((pins, errs) == ({}, []),
              "an absent pin file was an error rather than an empty set")

        # ── the verdict, over a synthetic family ──────────────────────────
        root = _fixture(tmp, {
            "x_drift_sweep.py": WIRED_SRC,
            "y_drift_sweep.py": MENTION_ONLY_SRC,
            "not_a_sweep.py": MENTION_ONLY_SRC,
        })
        wired, unwired, stale, n = verdict(root, {})
        check((wired, unwired, n) == (["x_drift_sweep.py"],
                                      ["y_drift_sweep.py"], 2),
              f"the verdict mis-partitioned: {wired} {unwired} {n}")
        check("not_a_sweep.py" not in wired + unwired,
              "a non-sweep entered the population")

        # A pin removes the unwired row from the finding set …
        _, unwired, stale, _ = verdict(root, {"y_drift_sweep.py": "r"})
        check(unwired == ["y_drift_sweep.py"] and stale == [],
              f"a pinned row was not still reported as unwired: {unwired}")
        # … and a pin on a WIRED sweep is STALE, which reds. This is the
        # direction a pin file left to loosen would never catch.
        _, _, stale, _ = verdict(root, {"x_drift_sweep.py": "r"})
        check(stale == ["x_drift_sweep.py"],
              f"a pin on an already-wired sweep did not read STALE: {stale}")
        # A pin naming a sweep that no longer exists is stale too.
        _, _, stale, _ = verdict(root, {"gone_drift_sweep.py": "r"})
        check(stale == ["gone_drift_sweep.py"],
              f"a pin for a DELETED sweep did not read STALE: {stale}")

        # The walk floor's premise: an empty family must not read as perfect.
        empty = _fixture(tmp / "e", {"not_a_sweep.py": WIRED_SRC})
        _, _, _, n = verdict(empty, {})
        check(n == 0, f"an empty family did not report 0 sweeps: {n}")
        check(MIN_SWEEPS > 0 and MIN_WIRED > 0,
              "a floor of 0 is not a floor — an empty walk would pass")
    return fails


def walk_arms() -> list[str]:
    """`tracked_sweeps` against a REAL git tree, both branches.

    The synthetic fixtures below have no `.git`, so they take the FALLBACK
    walk and the `git ls-files` half was reached by nothing — measured by
    `arm_reach_audit`, four live survivors in one function. Its whole documented
    purpose lives on that branch: a scratch copy somebody left in `scripts/` is
    not a member of the contract, and only git can say so.
    """
    fails: list[str] = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    def git(cwd, *args):
        subprocess.run(["git", "-C", str(cwd), *args], check=True,
                       capture_output=True)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "repo"
        (root / "scripts").mkdir(parents=True)
        (root / "scripts" / "a_drift_sweep.py").write_text(WIRED_SRC,
                                                           encoding="utf-8")
        (root / "scripts" / "helper.py").write_text(WIRED_SRC, encoding="utf-8")
        git(root, "init", "-q", "-b", "main")
        git(root, "config", "user.email", "t@t")
        git(root, "config", "user.name", "t")
        git(root, "add", "-A")
        git(root, "commit", "-qm", "init")

        check(tracked_sweeps(root) == ["a_drift_sweep.py"],
              f"the tracked walk did not return the committed sweep: "
              f"{tracked_sweeps(root)}")

        # The branch's REASON: an untracked scratch copy is not a member.
        (root / "scripts" / "zz_scratch_drift_sweep.py").write_text(
            MENTION_ONLY_SRC, encoding="utf-8")
        check(tracked_sweeps(root) == ["a_drift_sweep.py"],
              f"an UNTRACKED scratch copy entered the population — that is "
              f"exactly what asking git instead of the filesystem is for: "
              f"{tracked_sweeps(root)}")
        # …and the fallback, one directory over, DOES see it. Both halves, so
        # the arm cannot pass by taking the branch it was not aimed at.
        nogit = Path(td) / "extracted"
        (nogit / "scripts").mkdir(parents=True)
        (nogit / "scripts" / "zz_scratch_drift_sweep.py").write_text(
            MENTION_ONLY_SRC, encoding="utf-8")
        check(tracked_sweeps(nogit) == ["zz_scratch_drift_sweep.py"],
              f"the no-.git FALLBACK did not walk the filesystem \u2014 an extracted "
              f"tree is a legitimate population, not an error: "
              f"{tracked_sweeps(nogit)}")

        # The verdict end-to-end over the real tree, so the git branch is
        # reached by the PRODUCTION path and not only by the helper.
        wired, unwired, stale, n = verdict(root, {})
        check((wired, unwired, n) == (["a_drift_sweep.py"], [], 1),
              f"the verdict over a real git tree disagreed with the walk: "
              f"{wired} {unwired} {n}")
    return fails


def selftest() -> list[str]:
    return classifier_arms() + pin_arms() + walk_arms()


def main() -> int:
    fails = selftest()
    if fails:
        print("✗ sweep-advisory membership gate SELFTEST FAILED — instrument "
              "untrustworthy:")
        for f in fails:
            print("    ✗ " + f)
        return 2

    pins, errs = parse_pins(PINS)
    for e in errs:
        print("✗ " + e)
    wired, unwired, stale, n = verdict(REPO_ROOT, pins)

    if n < MIN_SWEEPS:
        print(f"✗ INSTRUMENT: the walk found {n} sweep(s) < floor {MIN_SWEEPS} "
              f"— the family went blind and every row below passes vacuously")
        return 2
    if len(wired) < MIN_WIRED:
        print(f"✗ INSTRUMENT: {len(wired)} wired < floor {MIN_WIRED} — a walk "
              f"that finds every sweep and credits none looks exactly like "
              f"nobody having wired any, and the obvious remedy is to pin "
              f"them all")
        return 2

    bad = bool(errs)
    for name in stale:
        bad = True
        print(f"✗ STALE pin `{name}` — it is wired now, or gone. Remove the "
              f"row; a pin file that only ever loosens is a backlog")
    for name in unwired:
        if name in pins:
            print(f"  · pinned unwired: {name} — {pins[name]}")
            continue
        bad = True
        print(f"✗ UNWIRED {name} — it calls neither of "
              f"{'/'.join(w + '()' for w in WANTED)}, so its findings "
              f"and floors describe whatever the working tree happened to say "
              f"(Issue 797). Wire it at the population_verdict() call site, or "
              f"pin it in {PINS.name} with a reason")

    if bad:
        return 1
    print(f"✓ sweep-advisory membership gate PASSED — all {len(wired)} tracked "
          f"{GLOB} call {' or '.join(w + '()' for w in WANTED)} "
          f"(floors {MIN_SWEEPS}/{MIN_WIRED}), "
          f"{len(pins)} pinned exemption(s), 0 stale. ⚠ It does NOT assert the "
          f"patterns name each sweep's own population — that is a per-sweep "
          f"read, not statically decidable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
