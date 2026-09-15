#!/usr/bin/env python3
"""The VERDICT half of `wasm32_surface_audit.py` — pinned, every contract repo.

The audit (Issues 737 #7, 738, 774) is already cross-repo: it derives its own
population. What it has never had is a **verdict**. Nothing pins its buckets, so
a package that falls out of coverage is a line in a report somebody runs on
demand, and the workspace-wide standing lived in AGENTS.md as a hand-typed
sentence (Issue 785):

    Standing (measured 2026-09-14, post-774): 26 NAMED · 2 BY-DEP ·
    0 UNRESOLVED · 1 UNCOVERED over 216 files / 29 packages / 20 repos

That is the shape Issue 784 closed one instrument over, where the same kind of
hand-typed cross-repo total went **46%** stale without a single run noticing.
"Not stale today" is exactly the state 784's figure was in for eleven days.

Why this class deserves a wall
------------------------------
An UNCOVERED package is code that has never compiled and that nothing will ever
tell you about, because the arch it is gated on is one no lane passes.
Measured, seal-remake (`.issues/010` T2, katgpt-rs Issue 738): a positive
`#[cfg(target_arch = "wasm32")]` block that no row built and that had been
**uncompilable since it was written** — it called a `cfg(not(wasm32))`
function.

UNRESOLVED is walled at 0 rather than ratcheted. The audit already refuses to
fold it into either neighbour — "a human has not answered it, and that is the
bucket's job" — and a ratchet on a bucket whose whole meaning is *unanswered*
converts it into a backlog.

UNCOVERED is pinned by MEMBERSHIP, not by count
-----------------------------------------------
The one standing row, `seal-online-remaster: seal-poc-submodule`, is a
deliberate negative control: excluded from its repo's CI, depended on by
nothing, and that repo is read-only from here (arm-vs-row is its owner's call).
A `max_uncovered = 1` count would go green on the day that row is repaired and
a different package regresses. A count is not a checksum over a set — the rule
`trap_sentinel_gate.py` is built on. The names live in
`scripts/wasm32_uncovered_expected.txt`; the cardinality falls out.

⚠ The walk floor is the ONLY blindness detector, and it is vacuous in 7 repos
----------------------------------------------------------------------------
`min_files` and `min_packages` are both **0 in 7 of 16** repos, because those
repos have no wasm32 surface at all — and unlike `orphaned_attr_drift_sweep`
(where both floors bite in all 16) there is no third quantity to fall back on.
So this sweep pins a **global** `TOTALS` row as well as the per-repo ones: a
per-repo floor catches one repo going blind, and the total catches the
instrument going blind everywhere at once.

That is not hypothetical. The audit's own walk shells out to `git grep -E`,
which is **POSIX ERE** — a Python `\\s` in the pattern matches nothing, and the
first version of this audit reported a walk of **0 files** with a confident
bucket breakdown over it. It was caught only because the walk size prints next
to the verdict. `TOTALS` is that observation turned into an assertion.

Why this is NOT in scripts/docs_gate.sh's CHECKS
------------------------------------------------
Identical to the other thirteen sweeps: CI has one checkout, the siblings are
private and simply absent, so this would either red on every run or derive an
EMPTY population and print a confident green over zero repos.

    this script               workstation, on demand, every contract repo
    wasm32_surface_audit.py   the same classifier, as a REPORT (exit 0)

Exit 0 clean, 1 on drift above the pins, **2 if the instrument itself is
untrustworthy** — an unreliable instrument is not the same finding as drift.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# DRY: the classifier is the report's. The 738 derived-row upgrade and the 774
# path-dep closure ARE the instrument — they are what separate 25 NAMED from 17
# false UNCOVERED — so a second copy would be the two-parsers-disagree trap the
# required-features family documents (Issue 755).
import wasm32_surface_audit as wsa  # noqa: E402
from skill_repo_set_gate import derive_repos  # noqa: E402
from sweep_population import population_verdict  # noqa: E402
from worktree_state import sweep_advisory  # noqa: E402

REPO_ROOT = HERE.parent
WORKSPACE = REPO_ROOT.parent
PINS = HERE / "wasm32_surface_drift_floors.txt"
EXPECTED = HERE / "wasm32_uncovered_expected.txt"

FIELDS = ("min_files", "min_packages", "max_unresolved")
TOTALS = "TOTALS"  # the reserved global row — see the docstring

NAMED = "✓ named"
DERIVED = "✓ derived"
BYDEP = "✓ by-dep"
UNRES = "? UNRESOLVED"
UNCOV = "✗ UNCOVERED"


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


def parse_expected(path: Path) -> set[tuple[str, str]]:
    """`<repo> <package>` pairs — the UNCOVERED set, by NAME."""
    out: set[tuple[str, str]] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            raise ValueError(f"malformed expected row (want 2 fields): {raw!r}")
        out.add((parts[0], parts[1]))
    return out


def selftest() -> list[str]:
    """Pin that the classifier is reachable through `classify_repo` and lands
    the verdicts this sweep's pins are written against, and that the two
    parsers refuse malformed input.

    The bucket boundaries themselves are self-tested INSIDE the audit
    (`--self-test`, five canary verdicts including the optional-dep negative),
    and that self-test is invoked here rather than re-implemented: two copies
    of a classifier canary is the exact duplication this file exists to avoid.
    """
    fails: list[str] = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    # 1. the audit's own five-verdict canary, through this process. It builds a
    #    throwaway git repo with named / by-dep / uncovered / optional-not-
    #    credited / workspace-table-resolved crates and asserts each verdict.
    #    If the buckets drift, this sweep's pins mean something else.
    try:
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = wsa.self_test()
        check(rc == 0, f"the audit's five-verdict canary FAILED:\n{buf.getvalue()}")
    except Exception as e:  # noqa: BLE001 — an instrument that cannot run is a finding
        fails.append(f"the audit's canary could not run: {e!r}")

    # 2. `classify_repo` is the extracted entry point (Issue 785 T1) and returns
    #    the buckets this file reads. An EMPTY repo must classify, not raise —
    #    7 of 16 contract repos have no wasm32 surface at all.
    with tempfile.TemporaryDirectory() as td:
        s = wsa.classify_repo(Path(td))
        check(s.hits == {} and s.files_walked == 0,
              f"an empty tree did not classify as empty: {s}")
        check(s.verdicts() == {} and s.bucket(UNCOV) == [],
              "an empty surface produced buckets")

    # 3. the verdict STRINGS this file compares against are the audit's own.
    #    A rename there would otherwise silently empty every bucket here and
    #    print a clean sweep.
    for label, want in (("named", NAMED), ("derived", DERIVED), ("by-dep", BYDEP),
                        ("unresolved", UNRES), ("uncovered", UNCOV)):
        got = {
            "named": wsa.verdict_for("p", {"p"}, set(), set(), False),
            "derived": wsa.verdict_for("p", set(), {"p"}, set(), False),
            "by-dep": wsa.verdict_for("p", set(), set(), {"p"}, False),
            "unresolved": wsa.verdict_for("p", set(), set(), set(), True),
            "uncovered": wsa.verdict_for("p", set(), set(), set(), False),
        }[label]
        check(got == want, f"verdict string drift for {label}: {got!r} != {want!r}")

    # 4. population derivation: BOUNDARY.md + a .git DIRECTORY, both required.
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "real").mkdir()
        (ws / "real" / "BOUNDARY.md").write_text("x")
        (ws / "real" / ".git").mkdir()
        (ws / "worktree-shaped").mkdir()
        (ws / "worktree-shaped" / "BOUNDARY.md").write_text("x")
        (ws / "worktree-shaped" / ".git").write_text("gitdir: elsewhere")
        if derive_repos(ws) != ["real"]:
            fails.append(f"population derivation wrong: {derive_repos(ws)}")

        # 5. both parsers: arity ENFORCED, comments stripped.
        pins = ws / "pins.txt"
        pins.write_text("# c\nrepo-a 8 2 0  # trailing\n\n")
        if parse_pins(pins) != {"repo-a": dict(zip(FIELDS, (8, 2, 0)))}:
            fails.append("pin parse: 4-field row not read correctly")
        pins.write_text("repo-a 1 2\n")
        try:
            parse_pins(pins)
            fails.append("pin parse: short row accepted")
        except ValueError:
            pass
        exp = ws / "exp.txt"
        exp.write_text("# c\nrepo-a pkg-b  # trailing\n\n")
        if parse_expected(exp) != {("repo-a", "pkg-b")}:
            fails.append("expected parse: 2-field row not read correctly")
        exp.write_text("repo-a\n")
        try:
            parse_expected(exp)
            fails.append("expected parse: short row accepted")
        except ValueError:
            pass
    return fails


def main() -> int:
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass  # not a TextIOWrapper (embedded / detached); keep old behavior

    fails = selftest()
    if fails:
        print("✗ wasm32 surface sweep SELFTEST FAILED — instrument untrustworthy:")
        for f in fails:
            print(f"    {f}")
        return 2

    for path, what in ((PINS, "pins"), (EXPECTED, "expected-UNCOVERED")):
        if not path.is_file():
            print(f"✗ {what} file missing: {path}")
            return 2
    try:
        pins = parse_pins(PINS)
        expected = parse_expected(EXPECTED)
    except ValueError as e:
        print(f"✗ expectation file unreadable: {e}")
        return 2
    if TOTALS not in pins:
        print(f"✗ pins file declares no {TOTALS} row — the per-repo floors are "
              f"0 in 7 of 16 repos, so without the global floor an instrument "
              f"that goes blind EVERYWHERE still passes")
        return 2
    if len(pins) < 2:
        print("✗ pins file declares NO repos — an empty expectation set is refused")
        return 2

    names = derive_repos(WORKSPACE)
    if not names:
        print(f"✗ derived population is EMPTY under {WORKSPACE} — refusing to "
              f"report a green over zero repos")
        return 2

    bad = False
    tot_files = tot_pkgs = tot_named = tot_bydep = tot_unres = 0
    seen_uncov: set[tuple[str, str]] = set()

    for name in names:
        s = wsa.classify_repo(WORKSPACE / name)
        v = s.verdicts()
        named = sum(1 for x in v.values() if x in (NAMED, DERIVED))
        bydep = len(s.bucket(BYDEP))
        unres = s.bucket(UNRES)
        uncov = s.bucket(UNCOV)
        tot_files += s.files_walked
        tot_pkgs += len(s.hits)
        tot_named += named
        tot_bydep += bydep
        tot_unres += len(unres)
        seen_uncov |= {(name, p) for p in uncov}

        row = pins.get(name)
        flags = []
        if row is None:
            flags.append("UNPINNED — add a row (or it can never red)")
        else:
            if s.files_walked < row["min_files"]:
                flags.append(f"walk FLOOR breached: {s.files_walked} wasm32-"
                             f"mentioning .rs < {row['min_files']} — the browser "
                             f"surface shrank, or `git grep` went blind and the "
                             f"buckets below mean nothing")
            if len(s.hits) < row["min_packages"]:
                flags.append(f"package FLOOR breached: {len(s.hits)} package(s) "
                             f"with positive cfgs < {row['min_packages']} — the "
                             f"walk is intact but the POSITIVE-cfg filter "
                             f"matched nothing")
            if len(unres) > row["max_unresolved"]:
                flags.append(f"UNRESOLVED {len(unres)} > pinned "
                             f"{row['max_unresolved']} — never a pass, and never "
                             f"folded into a neighbour")
        for pkg in uncov:
            if (name, pkg) not in expected:
                flags.append(f"UNCOVERED {pkg} is not in "
                             f"{EXPECTED.name} — no wasm32 row in this repo can "
                             f"reach it, so its arm compiles nowhere")

        status = "✗" if flags else ("·" if (uncov or unres) else "✓")
        print(f"{status} {name:22s} files={s.files_walked:<4d} pkgs={len(s.hits):<3d} "
              f"named+derived={named} by-dep={bydep} unresolved={len(unres)} "
              f"uncovered={len(uncov)}")
        for pkg in unres:
            print(f"      ? UNRESOLVED  {pkg}  ({s.hits[pkg]} positive site(s))")
        for pkg in uncov:
            mark = "pinned" if (name, pkg) in expected else "⛔ NEW"
            print(f"      ✗ UNCOVERED   {pkg}  ({s.hits[pkg]} positive site(s)) "
                  f"[{mark}]")
        for f in flags:
            bad = True
            print(f"      ✗ {f}")

    # A pinned row that STOPPED being UNCOVERED is a finding in the other
    # direction: the expectation file now certifies nothing, and the next real
    # regression at that address would read as "already known". Only checked
    # for repos this run actually measured — a partial clone is the population
    # verdict's job, not this check's.
    for repo, pkg in sorted(expected - seen_uncov):
        if repo in names:
            bad = True
            print(f"✗ {repo}: {pkg} is pinned UNCOVERED in {EXPECTED.name} but "
                  f"is now COVERED — drop the row in the commit that covered "
                  f"it, or the pin stops asserting anything")

    # The global floor. Per-repo floors are 0 in 7 of 16 repos (no wasm32
    # surface at all), so an instrument that goes blind everywhere at once
    # passes every one of them. Measured precedent: the first version of this
    # audit walked 0 files, from a Python `\s` handed to POSIX ERE `git grep`.
    g = pins[TOTALS]
    if tot_files < g["min_files"]:
        bad = True
        print(f"✗ {TOTALS}: walk FLOOR breached — {tot_files} wasm32-mentioning "
              f".rs across the whole population < {g['min_files']}. This is the "
              f"only floor that bites when the grep itself regresses.")
    if tot_pkgs < g["min_packages"]:
        bad = True
        print(f"✗ {TOTALS}: package FLOOR breached — {tot_pkgs} < "
              f"{g['min_packages']}")
    if tot_unres > g["max_unresolved"]:
        bad = True
        print(f"✗ {TOTALS}: UNRESOLVED {tot_unres} > {g['max_unresolved']}")

    # The population axis, shared (Issues 793 + 782).
    pop_lines, deferred, pop_fail = population_verdict(
        [k for k in pins if k != TOTALS], names)

    # Issue 796 — the worktree is not the repo. This run reads files that
    # concurrent sessions are editing, so a finding may sit on a line no
    # commit contains. ADVISORY, never a failure: a sweep that hard-reds on
    # an ordinary dirty worktree is a sweep nobody runs. It rides the FINAL
    # line in BOTH directions (the `deferred` precedent) and is SILENT
    # unless the dirty set meets this sweep's own population — the cfg sites + every lane definition that could name them.
    deferred.extend(sweep_advisory(
        names, ("*.rs", "Cargo.toml", ".github/workflows/*.yml",
     "scripts/*.sh"), root=WORKSPACE))
    for _line in pop_lines:
        print(_line)
    if pop_fail:
        bad = True

    print(f"\n{len(names)} contract repo(s) · {tot_files} wasm32-mentioning .rs "
          f"· {tot_pkgs} package(s) with positive cfgs · {tot_named} NAMED · "
          f"{tot_bydep} BY-DEP · {tot_unres} UNRESOLVED · {len(seen_uncov)} "
          f"UNCOVERED")
    # State the scope where it is READ, not only in the docstring.
    print("  scope: the POSITIVE cfg only. `not(target_arch = \"wasm32\")` is an "
          "ordinary native-only guard and counting it inflates everything. "
          "BY-DEP is reachability through non-optional in-repo path deps, never "
          "folded into NAMED — that coverage dies by a dep-graph edit in "
          "someone else's manifest.")

    if bad:
        print("✗ wasm32 surface sweep FAILED — see the ✗ rows above")
        for _d in deferred:
            print(f"  ⚠ {_d}")
        print("    A new UNCOVERED package is an arm that compiles NOWHERE — "
              "seal-remake's was uncompilable from the day it was written. The "
              "repair is a lane row, or deleting a dead arm; it is not a pin.")
        return 1
    _line = "✓ wasm32 surface sweep PASSED — every repo within its pins"
    if deferred:
        _line += "; DEFERRED: " + "; ".join(deferred)
    print(_line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
