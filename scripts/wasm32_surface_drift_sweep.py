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
Measured, mmorpg-remake (`.issues/010` T2, katgpt-rs Issue 738): a positive
`#[cfg(target_arch = "wasm32")]` block that no row built and that had been
**uncompilable since it was written** — it called a `cfg(not(wasm32))`
function.

UNRESOLVED is walled at 0 rather than ratcheted. The audit already refuses to
fold it into either neighbour — "a human has not answered it, and that is the
bucket's job" — and a ratchet on a bucket whose whole meaning is *unanswered*
converts it into a backlog.

UNCOVERED is pinned by MEMBERSHIP, not by count
-----------------------------------------------
The one standing row, `mmorpg-remaster: mmorpg-poc-submodule`, is a
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

import subprocess
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
from sweep_population import open_repo, population_verdict, pin_row_exempt  # noqa: E402
from worktree_state import (HeadDelta, delta_of, head_tree,  # noqa: E402
                            sweep_advisory)

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

# ONE list, read by the worktree advisory AND by the HEAD re-classification,
# and DERIVED rather than typed. It must name every file that can CHANGE a
# verdict, not only the ones findings sit on — here that is three classes:
# the `.rs` walk, the manifests (`Cargo.toml` decides BY-DEP through the
# path-dep closure and decides which package a file even belongs to), and the
# lane rows, which are the audit's own `LANE_GLOBS`.
#
# ⛔ The advisory used to carry a hand-typed FOURTH copy of this —
# `("*.rs", "Cargo.toml", ".github/workflows/*.yml", "scripts/*.sh")` — and it
# disagreed with the classifier in three ways at once: `LANE_GLOBS` is
# `scripts/*` and `.github/*` (ANY file type, not just `.sh`/`.yml`), a
# `Cargo.toml` below the root is a manifest too, and `.yaml` was missing
# exactly as it was in T5a. A dirty lane file in any of those was silently
# outside this sweep's declared population. Taking the globs from `wsa` is
# what stops the fifth copy.
SCOPE = ("*.rs", "*.toml", *wsa.LANE_GLOBS)


def adjudicate(repo: Path, s):
    """This repo's package verdicts, split COMMITTED / UNCOMMITTED / MASKED.

    ⛔ **`head_tree`, not `head_overlay`, and the reason is measured.** Both
    cheaper instruments assume the classifier takes its text from ONE
    interceptable place. `wasm32_surface_audit` does not: it shells out to
    `git grep` for the walk, to `git ls-files` twice (manifests, lane rows),
    and reads files directly besides. An overlay that missed any one of those
    four seams would build a verdict half from HEAD and half from the
    worktree, which is worse than either half alone. So HEAD is materialised
    and the classifier runs unmodified.

    ⛔ **The VERDICT is in the key**, for the reason T5f measured one sweep
    over: `delta_of` puts a key-matched row in `committed` carrying the
    WORKTREE's object, so any field the key omits is one where the worktree
    silently overrides HEAD — and every ceiling here partitions by verdict
    (`max_unresolved` counts UNRESOLVED, the membership file pins UNCOVERED).
    A package that is UNCOVERED at HEAD and covered in somebody's uncommitted
    lane edit must stay counted; keyed on the package NAME alone it would not.

    Cost: a tree copy per repo with dirt in SCOPE, and ZERO on a clean run —
    `head_tree` yields None and this returns the worktree rows untouched.
    """
    rows = [(pkg, v) for pkg, v in s.verdicts().items()]
    with head_tree(repo, SCOPE) as tree:
        if tree is None:
            return HeadDelta(rows, [], [])
        head = wsa.classify_repo(tree)
        return delta_of(rows, list(head.verdicts().items()), lambda r: r)


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
        (ws / "real" / "BOUNDARY.md").write_text("x", encoding="utf-8")
        (ws / "real" / ".git").mkdir()
        (ws / "worktree-shaped").mkdir()
        (ws / "worktree-shaped" / "BOUNDARY.md").write_text("x", encoding="utf-8")
        (ws / "worktree-shaped" / ".git").write_text("gitdir: elsewhere", encoding="utf-8")
        if derive_repos(ws) != ["real"]:
            fails.append(f"population derivation wrong: {derive_repos(ws)}")

        # 5. both parsers: arity ENFORCED, comments stripped.
        pins = ws / "pins.txt"
        pins.write_text("# c\nrepo-a 8 2 0  # trailing\n\n", encoding="utf-8")
        if parse_pins(pins) != {"repo-a": dict(zip(FIELDS, (8, 2, 0)))}:
            fails.append("pin parse: 4-field row not read correctly")
        pins.write_text("repo-a 1 2\n", encoding="utf-8")
        try:
            parse_pins(pins)
            fails.append("pin parse: short row accepted")
        except ValueError:
            pass
        exp = ws / "exp.txt"
        exp.write_text("# c\nrepo-a pkg-b  # trailing\n\n", encoding="utf-8")
        if parse_expected(exp) != {("repo-a", "pkg-b")}:
            fails.append("expected parse: 2-field row not read correctly")
        exp.write_text("repo-a\n", encoding="utf-8")
        try:
            parse_expected(exp)
            fails.append("expected parse: short row accepted")
        except ValueError:
            pass

    # 4. SCOPE is DERIVED from the audit's own lane globs, not typed. The
    #    assertion is the delegation itself: a fifth hand-typed copy is how
    #    this list came to disagree with the classifier in three ways at once.
    for g in wsa.LANE_GLOBS:
        if g not in SCOPE:
            fails.append(f"SCOPE lost the lane glob {g!r} — a dirty lane file "
                         f"is then outside this sweep's declared population "
                         f"while still moving every verdict in the repo")
    for g in ("*.rs", "*.toml"):
        if g not in SCOPE:
            fails.append(f"SCOPE lost {g!r} — the walk and the manifests are "
                         f"the other two verdict-changing inputs")

    fails += head_arms()
    return fails


def head_arms() -> list[str]:
    """`adjudicate` end to end against REAL git — Issue 822.

    The audit's own canary already proves the five verdicts; these prove the
    PROVENANCE split on top of them, which no classifier arm can reach. The
    fixture is the audit's canary workspace shape reduced to what moves a
    verdict: one gated crate and one lane row naming it.
    """
    fails: list[str] = []

    def git(root, *args):
        subprocess.run(("git", "-C", str(root)) + args,
                       capture_output=True, check=True)

    LANE = ("name: ci\njobs:\n  b:\n    steps:\n      - run: cargo check "
            "-p canary-a --target wasm32-unknown-unknown\n")
    NO_LANE = "name: ci\njobs:\n  b:\n    steps:\n      - run: echo nothing\n"

    def fixture(td: str, committed_lane: str, worktree_lane: str | None):
        repo = Path(td) / "r"
        (repo / "crates" / "canary-a" / "src").mkdir(parents=True)
        (repo / ".github" / "workflows").mkdir(parents=True)
        (repo / "Cargo.toml").write_text(
            '[workspace]\nmembers = ["crates/canary-a"]\n', encoding="utf-8")
        (repo / "crates" / "canary-a" / "Cargo.toml").write_text(
            '[package]\nname = "canary-a"\nversion = "0.0.0"\n',
            encoding="utf-8")
        (repo / "crates" / "canary-a" / "src" / "lib.rs").write_text(
            '#[cfg(target_arch = "wasm32")]\npub fn f() {}\n',
            encoding="utf-8")
        (repo / ".github" / "workflows" / "ci.yml").write_text(
            committed_lane, encoding="utf-8")
        git(repo.parent, "init", "-q", "r")
        git(repo, "config", "user.email", "arm@example.invalid")
        git(repo, "config", "user.name", "arm")
        git(repo, "add", "-A")
        git(repo, "-c", "commit.gpgsign=false", "commit", "-qm", "base")
        if worktree_lane is not None:
            (repo / ".github" / "workflows" / "ci.yml").write_text(
                worktree_lane, encoding="utf-8")
        return repo

    def run(repo: Path):
        s = wsa.classify_repo(repo)
        return s, adjudicate(repo, s)

    # a. The fixture has to MOVE, or every arm below is vacuous — and it moves
    #    through a `.github/workflows/*.yml` edit, which the hand-typed scope
    #    this SCOPE replaced did cover. The next two do not touch `.rs` at all.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, NO_LANE, LANE)
        s, d = run(repo)
        if s.verdicts().get("canary-a") not in (NAMED, DERIVED):
            fails.append(f"head arm: the worktree lane did not cover the "
                         f"crate ({s.verdicts()}) — the fixture is inert")
        if ("canary-a", UNCOV) not in d.masked:
            fails.append(f"adjudicate: a crate UNCOVERED at HEAD and covered "
                         f"by an uncommitted lane edit was not MASKED ({d}) — "
                         f"the membership wall would call the pin stale and "
                         f"tell somebody to delete it")
        if ("canary-a", UNCOV) not in d.head:
            fails.append("adjudicate: the committed UNCOVERED verdict is "
                         "missing from `.head`, so the wall stops demanding "
                         "a pin for an arm that compiles nowhere")

    # b. And the other direction: covered at HEAD, uncovered in the worktree.
    #    The NEW-UNCOVERED wall must NOT fire on a line no commit contains.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, LANE, NO_LANE)
        s, d = run(repo)
        if ("canary-a", UNCOV) not in d.uncommitted:
            fails.append(f"adjudicate: a worktree-only UNCOVERED is not "
                         f"UNCOMMITTED ({d}) — the wall reads the tree")
        if any(x == UNCOV for _p, x in d.head):
            fails.append("adjudicate: an UNCOMMITTED UNCOVERED reached "
                         "`.head`, demanding a pin nobody can write")

    # c. ⛔ The VERDICT is in the key. Keyed on the package NAME alone, (a)'s
    #    row matches and `delta_of` keeps the WORKTREE's object, so a
    #    committed UNCOVERED reads as covered — T5f's defect, one sweep over.
    #    Asserted here rather than trusted: the two rows must differ.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, NO_LANE, LANE)
        s, d = run(repo)
        if not (d.uncommitted and d.masked):
            fails.append(f"row key: a package whose VERDICT moved was not "
                         f"split in both directions ({d}) — the key is the "
                         f"name alone and the worktree overrides HEAD")

    # d. A CLEAN tree costs nothing: `head_tree` copies a whole tree, so a
    #    sweep that pays for it every run is one nobody runs.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, LANE, None)
        calls = []
        real = wsa.classify_repo

        def counted(r):
            calls.append(r)
            return real(r)

        wsa.classify_repo = counted
        try:
            s, d = run(repo)
        finally:
            wsa.classify_repo = real
        if len(calls) != 1:
            fails.append(f"adjudicate: re-classified a CLEAN repo "
                         f"({len(calls)} calls) — `head_tree` must yield None "
                         f"and the caller must SKIP")
        if d.uncommitted or d.masked or not d.committed:
            fails.append(f"adjudicate: a clean tree's rows are not all "
                         f"COMMITTED ({d})")
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

    n_uncommitted = n_masked = 0
    for name in names:
        repo = open_repo(name, WORKSPACE)
        s = wsa.classify_repo(repo)
        v = s.verdicts()
        # Issue 822 — the DISPLAY reads the worktree (it is what the files say
        # today, and hiding that would be its own lie); the CEILING and the
        # MEMBERSHIP wall read `.head`, the only thing a commit of this
        # checkout would reproduce.
        delta = adjudicate(repo, s)
        n_uncommitted += len(delta.uncommitted)
        n_masked += len(delta.masked)
        held = {pkg for pkg, _x in delta.uncommitted}
        head_v = dict(delta.head)
        named = sum(1 for x in v.values() if x in (NAMED, DERIVED))
        bydep = len(s.bucket(BYDEP))
        unres = s.bucket(UNRES)
        uncov = s.bucket(UNCOV)
        head_unres = sorted(p for p, x in head_v.items() if x == UNRES)
        head_uncov = sorted(p for p, x in head_v.items() if x == UNCOV)
        tot_files += s.files_walked
        tot_pkgs += len(s.hits)
        tot_named += named
        tot_bydep += bydep
        tot_unres += len(unres)
        # ⛔ The OTHER direction of the membership wall — "pinned UNCOVERED but
        # now COVERED, drop the row" — reads HEAD too, and it is the
        # destructive one: an uncommitted lane edit that covers a package
        # would otherwise tell somebody to delete the only pin naming a
        # committed, uncovered arm.
        seen_uncov |= {(name, p) for p in head_uncov}

        row = pins.get(name)
        flags = []
        if row is None:
            # Issue 821: an acknowledged known-extra owes no pin row —
            # the marker reached population_verdict's FINAL line and not
            # this loop, so 8 of 9 sweeps red on repos they found
            # nothing in, hiding two live ratchet breaches.
            if not pin_row_exempt(name):
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
            if len(head_unres) > row["max_unresolved"]:
                flags.append(f"UNRESOLVED {len(head_unres)} committed > pinned "
                             f"{row['max_unresolved']} — never a pass, and never "
                             f"folded into a neighbour")
        # ⚠ Issue 821: this loop sits OUTSIDE the `row is not None` branch, so
        # excusing the pin row alone left an acknowledged known-extra reporting
        # a hard UNCOVERED finding — a verdict about a repo the marker has just
        # declared "not measured and not expected to be". An extra contributes
        # no verdict, not merely no pin row. The membership file's OTHER
        # direction (a pinned row that stopped being UNCOVERED) is untouched:
        # a row naming an extra repo still has to be removed deliberately.
        for pkg in (() if pin_row_exempt(name) else head_uncov):
            if (name, pkg) not in expected:
                flags.append(f"UNCOVERED {pkg} is not in "
                             f"{EXPECTED.name} — no wasm32 row in this repo can "
                             f"reach it, so its arm compiles nowhere")

        status = "✗" if flags else ("·" if (uncov or unres) else "✓")
        split = ""
        if held or delta.masked:
            split = (f" [{len(delta.committed)} committed"
                     + (f", {len(held)} uncommitted" if held else "")
                     + (f", {len(delta.masked)} MASKED" if delta.masked else "")
                     + "]")
        print(f"{status} {name:22s} files={s.files_walked:<4d} pkgs={len(s.hits):<3d} "
              f"named+derived={named} by-dep={bydep} unresolved={len(unres)} "
              f"uncovered={len(uncov)}{split}")
        for pkg in unres:
            print(f"      ? UNRESOLVED  {pkg}  ({s.hits[pkg]} positive site(s))"
                  + (" [UNCOMMITTED — not adjudicated]" if pkg in held else ""))
        for pkg in uncov:
            mark = "pinned" if (name, pkg) in expected else "⛔ NEW"
            print(f"      ✗ UNCOVERED   {pkg}  ({s.hits[pkg]} positive site(s)) "
                  f"[{mark}]"
                  + (" [UNCOMMITTED — not adjudicated]" if pkg in held else ""))
        # A MASKED verdict is NOT in the worktree buckets — that is what MASKED
        # means — so it prints from the HEAD side or it prints nowhere, and the
        # wall reds over a package nobody can see. Shown for every verdict, not
        # only the two adjudicated ones: a package that is `✓ by-dep` here and
        # `✗ UNCOVERED` at HEAD is exactly the row somebody must look at.
        for pkg, x in sorted(delta.masked):
            print(f"      ⛔ {x:<14s} {pkg}  [MASKED — committed, hidden by "
                  f"this worktree]")
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

    # Issue 797 — the worktree is not the repo. This run reads files that
    # concurrent sessions are editing, so a finding may sit on a line no
    # commit contains. ADVISORY, never a failure: a sweep that hard-reds on
    # an ordinary dirty worktree is a sweep nobody runs. It rides the FINAL
    # line in BOTH directions (the `deferred` precedent) and is SILENT
    # unless the dirty set meets this sweep's own population — the cfg sites + every lane definition that could name them.
    # ...and Issue 822's row counts ride with it: the per-row labels above say
    # WHICH, this says the class exists at all, and a notice printed in only
    # one of those places is one nobody reads on the run that needs it.
    deferred.extend(sweep_advisory(
        names, SCOPE, root=WORKSPACE,
        uncommitted_rows=n_uncommitted, masked_rows=n_masked))
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
              "mmorpg-remake's was uncompilable from the day it was written. The "
              "repair is a lane row, or deleting a dead arm; it is not a pin.")
        return 1
    _line = "✓ wasm32 surface sweep PASSED — every repo within its pins"
    if deferred:
        _line += "; DEFERRED: " + "; ".join(deferred)
    print(_line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
