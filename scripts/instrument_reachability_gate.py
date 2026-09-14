#!/usr/bin/env python3
"""An instrument no document names is invisible to the census that would find it.

Issue 787. `1a5b6571` bounded the Issue 785 close-out to "every cross-repo class
in `scripts/` whose verdict is **walled at a small number** has both halves",
and that bounded claim was **still false** by exactly one instrument —
`len_derived_binding_audit.py`, cross-repo, joined-finding buckets walled at 0,
no verdict half, closed the same day as Issue 786.

The miss is not the finding. The MECHANISM is. Both censuses enumerated the
audits **AGENTS.md documents** against their sweep halves, and AGENTS.md did not
name that audit at all. A census that reads the document cannot see an
instrument the document omits, and it reports a confident, complete-sounding
answer over the subset it can see. That is every blindness floor in this repo
one level up, with the DOCUMENTATION as the population nothing floored.

The predicate is REACHABLE, not "documented in prose"
------------------------------------------------------
Roots are `AGENTS.md`, `scripts/docs_gate.sh` and `.github/workflows/*.yml`.
From there the closure follows script → script references, so a helper invoked
by a documented instrument counts as findable. That is not a convenience; the
cases demand it. `all_ignored_target_audit.py`, `cfg_row_implication_audit.py`
and `ci_test_execution_report.py` appear in no document either, yet each is
invoked by an instrument that IS documented (`cfg_gated_floor_gate.py`,
`cfg_row_implication_gate.py`, `suite_membership_audit.py`) and each runs
per-push as a result. A bare "must be named in AGENTS.md" rule reds all three
and teaches whoever hits it to stop reading the gate.

⛔ **HISTORY.md is deliberately NOT a root.** It is the archive; its own header
says operational rules live in AGENTS.md and that it exists so agent context
stays small, so it is not loaded into a session. An instrument findable only
from the archive is precisely the instrument that stops being run — which is
what Issue 786 measured. Counting HISTORY.md would have made the 786 audit read
as reachable and this gate vacuous on the one case that motivated it.

Two floors, and the second is the one that is easy to leave out
----------------------------------------------------------------
`min_scripts` catches the WALK going blind: `git ls-files` returning nothing
makes the unreachable set empty and the ceiling passes.

`min_roots` catches the opposite direction, which is the silent one. An empty
or unreadable root set makes EVERY script unreachable, and that reds loudly all
by itself — nobody would miss it. But a root glob that quietly widens (matching
a generated file, or a directory of vendored YAML that happens to mention every
script name) makes every script REACHABLE and prints a confident green. A
ceiling cannot fail once the instrument is blind in the permissive direction,
so the root count is pinned as a floor AND the roots are required to be a
fixed, named set rather than whatever a glob returns.

Membership, not a count
------------------------
`scripts/instrument_unreferenced_expected.txt` pins the deliberately-unreachable
set by NAME with a reason per row, and reds in BOTH directions: a new
unreachable script is a finding, and a pinned row that became reachable is a
finding too (wire it up, then drop the row in that commit). A count would go
green the day one is documented and another is added.

⚠ **The closure is TEXTUAL, and that is a measured limitation, not a claim
about how carefully it was written.** A basename mentioned anywhere in a
tracked script credits reachability — including inside a string literal, a
comment, or a test fixture. It cannot be narrowed by parsing: a genuine
invocation IS a string literal (`subprocess.run([py, "scripts/x.py"])`), and
the primary root is prose. This bit on this gate's own first staged run: a
canary arm named a real exempt script as fixture data, the arm's file is itself
in the population and reachable from `docs_gate.sh`, and the subject read as
reachable. Fixtures here are synthetic paths now. The leniency direction is the
DANGEROUS one for this class — a false "reachable" hides exactly the instrument
the gate exists to surface — so treat a row that leaves the unreachable set
without a wiring commit as suspect, and check WHAT started naming it.

`--prove-fires <sha>` is a known-answer validation and it is free: at
`18dbe980~1` the Issue 786 audit was named only in HISTORY.md, so it was the
tenth unreachable script and this gate reds there. Same idiom as
`platform_dead_code_audit.py --prove-fires`, and opt-in for the same reason —
a `git archive` of a frozen tree is worth a workstation run, not a per-push one.

Exit 0 clean, 1 on drift, **2 if the instrument itself is untrustworthy**.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
EXPECTED = HERE / "instrument_unreferenced_expected.txt"

# The roots, by NAME and never by glob-of-a-glob. `.github/workflows/*.yml` is
# a glob, but over a directory whose whole purpose is workflows; the other two
# are single files, and a missing one is an instrument failure, not a finding.
DOC_ROOTS = ("AGENTS.md", "scripts/docs_gate.sh")
WORKFLOW_DIR = ".github/workflows"
WORKFLOW_SUFFIXES = (".yml", ".yaml")

# Floors, ~60% of measured (the house slack convention). `min_scripts` is the
# walk; `min_roots` is the permissive direction (see the docstring). Measured
# 2026-09-14: 63 tracked scripts/*.py, 13 roots (AGENTS.md + docs_gate.sh + 11
# workflows).
MIN_SCRIPTS = 40
MIN_ROOTS = 8


def tracked(repo: Path, *pathspec: str) -> list[str]:
    """Tracked paths, repo-relative, `/`-separated. `git ls-files` already
    normalises the separator, so no host-shaped path reaches a pin key."""
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-files", *pathspec],
        capture_output=True, encoding="utf-8", errors="replace")
    if out.returncode != 0:
        return []
    return [p for p in out.stdout.splitlines() if p]


def read(repo: Path, rel: str) -> str:
    try:
        return (repo / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def collect(repo: Path) -> tuple[list[str], list[str]]:
    """(scripts, roots) for one repo, both repo-relative and tracked."""
    scripts = [p for p in tracked(repo, "scripts/") if p.endswith(".py")]
    roots = [r for r in DOC_ROOTS if (repo / r).is_file()]
    roots += [p for p in tracked(repo, WORKFLOW_DIR)
              if p.endswith(WORKFLOW_SUFFIXES)]
    return sorted(scripts), sorted(roots)


def reachable(repo: Path, scripts: list[str], roots: list[str]) -> set[str]:
    """Transitive closure: roots name scripts, scripts name scripts.

    A script is matched by BASENAME as well as by full path, because prose and
    command blocks cite `scripts/x.py` while a sibling script may import `x`
    or spawn `HERE / "x.py"`. Basename collisions are refused by the caller —
    with two `x.py` in the tree, a basename hit cannot say which one is meant,
    and guessing would credit coverage to the wrong file.
    """
    by_name: dict[str, str] = {Path(p).name: p for p in scripts}
    reached: set[str] = set()
    frontier = list(roots)
    seen: set[str] = set()
    while frontier:
        cur = frontier.pop()
        if cur in seen:
            continue
        seen.add(cur)
        body = read(repo, cur)
        if not body:
            continue
        for name, path in by_name.items():
            if path == cur or path in reached:
                continue
            if name in body or path in body:
                reached.add(path)
                frontier.append(path)
    return reached


def parse_expected(path: Path) -> dict[str, str]:
    """path -> reason. The reason is REQUIRED: an exemption with no stated
    reason is a row nobody can adjudicate, and this file's whole job is to
    hold judgement calls somebody made on purpose."""
    rows: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2 or not parts[1].strip():
            raise ValueError(
                f"malformed exemption row (want `<path> <reason>`): {raw!r}")
        rows[parts[0]] = parts[1].strip()
    return rows


def selftest() -> list[str]:
    """Arms over the closure and the parser. The transitivity arm is the one
    that matters: without it a documented gate's helper reds, which is the
    false positive that gets a gate deleted."""
    fails: list[str] = []

    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "scripts").mkdir()
        (ws / ".github" / "workflows").mkdir(parents=True)

        def w(rel, body):
            (ws / rel).write_text(body, encoding="utf-8")

        w("AGENTS.md", "run scripts/documented.py for the thing\n")
        w("scripts/docs_gate.sh", "#!/bin/sh\necho hi\n")
        w("scripts/documented.py", 'import subprocess\nsubprocess.run(["helper.py"])\n')
        w("scripts/helper.py", "x = 1\n")
        w("scripts/orphan.py", "y = 2\n")
        w("scripts/ci_only.py", "z = 3\n")
        w(".github/workflows/w.yml", "run: python scripts/ci_only.py\n")
        w("HISTORY.md", "scripts/archive_only.py was once useful\n")
        w("scripts/archive_only.py", "q = 4\n")
        subprocess.run(["git", "init", "-q", str(ws)], capture_output=True)
        subprocess.run(["git", "-C", str(ws), "add", "-A"], capture_output=True)

        scripts, roots = collect(ws)
        want_scripts = ["scripts/archive_only.py", "scripts/ci_only.py",
                        "scripts/documented.py", "scripts/helper.py",
                        "scripts/orphan.py"]
        if scripts != want_scripts:
            fails.append(f"walk wrong: {scripts}")
        if roots != sorted([".github/workflows/w.yml", "AGENTS.md",
                            "scripts/docs_gate.sh"]):
            fails.append(f"roots wrong: {roots}")

        got = reachable(ws, scripts, roots)
        # 1. named in AGENTS.md, 2. TRANSITIVELY via a documented script,
        # 3. named in a workflow. 4/5: orphan and archive-only are NOT reached.
        want = {"scripts/documented.py", "scripts/helper.py", "scripts/ci_only.py"}
        if got != want:
            fails.append(f"closure wrong: got {sorted(got)}, want {sorted(want)}")

        # 6. HISTORY.md must NOT be a root — the arm that keeps this gate
        #    non-vacuous on the case that motivated it (Issue 786).
        if "scripts/archive_only.py" in got:
            fails.append("HISTORY.md acted as a root — the gate is vacuous on "
                         "exactly the Issue 786 case")

        # 7. a root that mentions nothing must not silently reach everything.
        if reachable(ws, scripts, ["scripts/docs_gate.sh"]) != set():
            fails.append("a root naming no script reached something")

        # 8. exemption parser: reason REQUIRED, comments stripped.
        e = ws / "e.txt"
        e.write_text("# c\nscripts/orphan.py a stated reason  # trailing\n",
                     encoding="utf-8")
        if parse_expected(e) != {"scripts/orphan.py": "a stated reason  "
                                                      "# trailing".split("#")[0].strip()}:
            fails.append(f"exemption parse wrong: {parse_expected(e)}")
        e.write_text("scripts/orphan.py\n", encoding="utf-8")
        try:
            parse_expected(e)
            fails.append("exemption parse: reasonless row accepted")
        except ValueError:
            pass

    return fails


def prove_fires(sha: str) -> int:
    """Extract `<sha>~1` and require the Issue 786 audit UNREACHABLE there.

    A known-answer tree, in the `platform_dead_code_audit.py --prove-fires`
    idiom. The parent of `18dbe980` named `len_derived_binding_audit.py` in
    HISTORY.md only, so it was the tenth unreachable script.
    """
    target = "scripts/len_derived_binding_audit.py"
    with tempfile.TemporaryDirectory() as td:
        for ref, want_unreached in ((f"{sha}~1", True), (sha, False)):
            tree = Path(td) / ref.replace("~", "_")
            tree.mkdir()
            archive = subprocess.run(
                ["git", "-C", str(REPO_ROOT), "archive", ref],
                capture_output=True)
            if archive.returncode != 0:
                print(f"✗ --prove-fires: cannot `git archive {ref}`")
                return 2
            tar = tree / "t.tar"
            tar.write_bytes(archive.stdout)
            subprocess.run(["tar", "-xf", str(tar), "-C", str(tree)],
                           capture_output=True)
            tar.unlink()
            # No `.git` in an archive: collect() falls back to nothing, so give
            # the tree one. The walk is the same either way; this only makes
            # `git ls-files` answer.
            subprocess.run(["git", "init", "-q", str(tree)], capture_output=True)
            subprocess.run(["git", "-C", str(tree), "add", "-A"],
                           capture_output=True)
            scripts, roots = collect(tree)
            if target not in scripts:
                print(f"✗ --prove-fires: {target} absent at {ref} — the arm "
                      f"proves nothing")
                return 2
            unreached = target not in reachable(tree, scripts, roots)
            ok = unreached == want_unreached
            state = "UNREACHABLE" if unreached else "reachable"
            print(f"  {'✓' if ok else '✗'} {ref}: {target} {state} "
                  f"({len(scripts)} scripts, {len(roots)} roots)")
            if not ok:
                return 2
    print("✓ --prove-fires: the gate reds at the parent and passes at the fix")
    return 0


def canary() -> int:
    """`--canary`: perturb each axis and REQUIRE the gate to red.

    `selftest()` proves the CLOSURE is right; these prove the pin arithmetic
    around it reacts. A pin nobody has watched fail certifies nothing — and the
    Issue 786 session measured that directly, on an arm whose own anchor string
    was wrong: it perturbed nothing and its green was real.

    Every arm monkeypatches MODULE state, never a tracked file, so a failed arm
    cannot leave the worktree dirty.
    """
    import contextlib
    import io

    global EXPECTED, MIN_SCRIPTS, MIN_ROOTS

    td = Path(tempfile.mkdtemp())
    exp_src = EXPECTED.read_text(encoding="utf-8")
    real_expected, real_min_s, real_min_r = EXPECTED, MIN_SCRIPTS, MIN_ROOTS
    real_collect, real_reach = collect, reachable
    results = []

    def arm(name, want_rc, want_text, exp=None, min_s=None, min_r=None,
            collect_fn=None, reach_fn=None):
        global EXPECTED, MIN_SCRIPTS, MIN_ROOTS, collect, reachable
        EXPECTED = td / "e.txt"
        EXPECTED.write_text(exp if exp is not None else exp_src, encoding="utf-8")
        MIN_SCRIPTS = real_min_s if min_s is None else min_s
        MIN_ROOTS = real_min_r if min_r is None else min_r
        collect = collect_fn or real_collect
        reachable = reach_fn or real_reach
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                rc = main([], run_selftest=False)
        finally:
            EXPECTED, MIN_SCRIPTS, MIN_ROOTS = real_expected, real_min_s, real_min_r
            collect, reachable = real_collect, real_reach
        out = buf.getvalue()
        ok = rc == want_rc and want_text in out
        print(f"  {'✓' if ok else '✗'} {name}  (rc={rc}, want {want_rc})")
        if not ok:
            print(f"        wanted: {want_text}")
            for ln in [l for l in out.splitlines() if l.startswith(("✗", "⛔"))][:3]:
                print(f"        got: {ln}")
        results.append(ok)

    # The selftest runs ONCE, here: several arms monkeypatch `collect` /
    # `reachable`, and a selftest run against a stubbed classifier reports the
    # instrument as untrustworthy instead of letting the arm assert anything.
    fails = selftest()
    if fails:
        print("✗ SELFTEST FAILED before the canary — untrustworthy:")
        for f in fails:
            print(f"    {f}")
        return 2

    base_scripts, base_roots = real_collect(REPO_ROOT)

    arm("baseline green", 0, "gate PASSED")

    # 1. a NEW unreachable script with no row.
    #    ⛔ The basename is ASSEMBLED and must NEVER appear contiguously
    #    anywhere in this file — not in the code, not in a comment. This file
    #    is in the population and is reachable from docs_gate.sh, the closure
    #    is textual, so any contiguous spelling makes the arm's own subject
    #    reachable and the arm then passes on nothing. Measured twice: once
    #    with the literal in the code, and once more with the literal in the
    #    comment written to explain the first.
    ghost = "scripts/ghost" + "_" + "tool.py"
    arm("new unreachable reds", 1, "⛔ UNREACHABLE",
        collect_fn=lambda r: (sorted(base_scripts + [ghost]), base_roots))

    # 2-3. the membership pin, the other direction: a pinned row that became
    #      reachable, and one whose file is gone.
    arm("pinned-now-reachable reds", 1, "is now reachable",
        reach_fn=lambda r, s, roots: set(s))
    arm("pinned-file-gone reds", 1, "no longer exists",
        exp=exp_src + "scripts/vanished.py a reason that outlived its file\n")

    # 4-5. the two floors. min_roots is the PERMISSIVE direction: a root set
    #      that quietly widens makes everything reachable and prints a green.
    arm("walk floor reds", 2, "walk FLOOR breached", min_s=10_000)
    arm("roots floor reds", 2, "roots FLOOR breached", min_r=10_000)

    # 6. a missing named root is an INSTRUMENT failure, not a tree finding.
    arm("missing doc root refused", 2, "root missing",
        collect_fn=lambda r: (base_scripts,
                              [x for x in base_roots if x != "AGENTS.md"]))

    # 7. a basename collision is refused — guessing credits the wrong file.
    arm("basename collision refused", 2, "basename collision",
        collect_fn=lambda r: (sorted(base_scripts + ["scripts/sub/docs_gate.py",
                                                     "scripts/docs_gate.py"]),
                              base_roots))

    # 8. an exemption with no reason is refused, never read as a bare path.
    #    ⛔ The fixture path is SYNTHETIC on purpose. The first version named a
    #    real exempt script, and the gate's own first staged run red on it:
    #    this file is itself in the population, it is reachable from
    #    docs_gate.sh, and the closure is TEXTUAL — so the canary literal made
    #    its subject reachable and the membership pin's other direction fired.
    #    A gate's fixtures must not name its own subjects.
    arm("reasonless exemption refused", 2, "unreadable",
        exp="scripts/synthetic_canary_subject_do_not_create.py\n")

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
        print("✗ instrument-reachability gate SELFTEST FAILED — untrustworthy:")
        for f in fails:
            print(f"    {f}")
        return 2

    if "--prove-fires" in argv:
        i = argv.index("--prove-fires")
        sha = argv[i + 1] if i + 1 < len(argv) else "18dbe980"
        return prove_fires(sha)

    if not EXPECTED.is_file():
        print(f"✗ expected-UNREACHABLE file missing: {EXPECTED}")
        return 2
    try:
        expected = parse_expected(EXPECTED)
    except ValueError as e:
        print(f"✗ expected-UNREACHABLE file unreadable: {e}")
        return 2

    scripts, roots = collect(REPO_ROOT)
    for name in DOC_ROOTS:
        if name not in roots:
            print(f"✗ root missing: {name} — every script would read as "
                  f"unreachable and the finding would be the instrument, not "
                  f"the tree")
            return 2
    if len(scripts) < MIN_SCRIPTS:
        print(f"✗ walk FLOOR breached: {len(scripts)} tracked scripts/*.py < "
              f"{MIN_SCRIPTS} — `git ls-files` went blind and an empty "
              f"unreachable set means nothing")
        return 2
    if len(roots) < MIN_ROOTS:
        print(f"✗ roots FLOOR breached: {len(roots)} < {MIN_ROOTS}")
        return 2

    by_name: dict[str, list[str]] = {}
    for p in scripts:
        by_name.setdefault(Path(p).name, []).append(p)
    collisions = {n: v for n, v in by_name.items() if len(v) > 1}
    if collisions:
        print(f"✗ basename collision — a basename hit cannot say which file is "
              f"meant, and guessing credits coverage to the wrong one: "
              f"{collisions}")
        return 2

    unreached = sorted(set(scripts) - reachable(REPO_ROOT, scripts, roots))

    bad = False
    for p in unreached:
        if p not in expected:
            bad = True
            print(f"⛔ UNREACHABLE: {p} — no root and no documented instrument "
                  f"names it. Name it in AGENTS.md, invoke it from something "
                  f"that is named, or add a row with a REASON to "
                  f"{EXPECTED.name}. HISTORY.md does not count: it is the "
                  f"archive and is not loaded into a session.")
    for p in sorted(set(expected) - set(unreached)):
        bad = True
        if p in scripts:
            print(f"✗ pinned UNREACHABLE is now reachable: {p} — drop the row "
                  f"in the commit that wired it up")
        else:
            print(f"✗ pinned UNREACHABLE no longer exists: {p} — drop the row "
                  f"in the commit that removed it")

    print(f"\n{len(scripts)} tracked scripts/*.py (floor {MIN_SCRIPTS}) · "
          f"{len(roots)} root(s) (floor {MIN_ROOTS}) · "
          f"{len(scripts) - len(unreached)} reachable · "
          f"{len(unreached)} unreachable, {len(expected)} pinned")
    if bad:
        print("✗ instrument-reachability gate FAILED")
        return 1
    print("✓ instrument-reachability gate PASSED — every tracked instrument is "
          "reachable from AGENTS.md, docs_gate.sh or a workflow, or is pinned "
          "with a reason")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
