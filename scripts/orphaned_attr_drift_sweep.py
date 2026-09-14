#!/usr/bin/env python3
"""Run the orphaned-`#[cfg]` verdict over EVERY contract repo, not just this one.

`scripts/orphaned_attr_gate.py` is katgpt-rs-scoped by construction — CI has a
single checkout — and it was the LAST row in `docs_gate.sh`'s CHECKS whose
class is cross-repo (Rust source, present in every repo) and which had no
workstation half (Issue 784; Issue 783 closed the same gap for
`subprocess_encoding`).

The cost of that was already measurable, and it was not hypothetical drift. The
gate's docstring carries the workspace figure **as the argument for why it can
be a gate at all** — "a zero over 49,624 sites is evidence; a zero over a walk
that has gone blind is not" — and somebody had been typing that total in by
hand since 2026-09-03. Issue 777 migrated the gate to the TRACKED walk the same
day this landed, and the hand-typed warrant did not follow:

    quantity            docstring (2026-09-06)   tracked walk (2026-09-14)
    .rs files                       11,132                        8,694   -22%
    outer-#[cfg] sites              49,624                       26,598   -46%
    orphaned                             0                            0

The verdict never moved. **23,026 of the sites offered as its warrant were in
trees no repo owns** — seal-online-remaster's gitignored `mmorpg/` nested
repository, riir-ai's vendored `wgpu-hal` fork, riir-train's cargo `OUT_DIR`
sources under `.runs/target-*`. Correcting the number is a five-minute edit the
next walk change invalidates again; making the claim MEASURED is the repair.

Eighth instance of one shape in this workspace — the precedent list is in
`markdown_fence_drift_sweep.py`'s docstring. Unlike the other seven this one
found **no new offenders**, which is the honest outcome to report: the class
has now held at 0 across three independent measurements and TWO population
definitions, and that is a stronger statement than any single count.

Why BOTH floors, and how this population differs from Issue 783's
-----------------------------------------------------------------
`max_offenders = 0` is green over whatever the walk can SEE, and the walk
shells out to `git ls-files` — a regression takes the population to 0 and the
ceiling passes, indistinguishable from a clean repo. Two independent
quantities sit under it:

    min_rs_files   moves when the WALK goes blind
    min_cfg_sites  moves when the REGEX breaks on an unchanged tree

⚠ That the second one bites is a MEASUREMENT here, not an assumption, and it is
the difference from `subprocess_encoding_drift_sweep`: there `min_calls` is 0
in 10 of 16 repos and detects nothing in the majority of the population. Here
**both quantities are non-zero in all 16** — the smallest, riir-viewbridge, has
24 tracked `.rs` and 20 outer-`#[cfg]` sites — so both floors are live
everywhere. Same two-floor shape, different warrant; do not carry one repo
set's argument onto another.

The narrowing IS the instrument, so it is imported and never restated
---------------------------------------------------------------------
`OUTER_CFG` vs `ANY_ATTR` is the whole classifier: the broad shape (any
attribute + blank line + item) is **2,044 sites** and is not gateable, because
it is dominated by whole-file INNER `#![cfg(...)]` attributes that bind to the
enclosing module and are conventionally followed by a blank line. Narrowing to
outer `#[cfg]` / `#[cfg_attr]` is what takes 2,044 to 0. A second copy of a
rule that subtle is a second thing to get wrong (Issue 755), so this sweep
imports `orphaned_attr_gate.scan` and asserts the shared floors rather than
re-deriving either.

Why this is NOT in scripts/docs_gate.sh's CHECKS
------------------------------------------------
Identical to the other twelve sweeps: CI has one checkout, the siblings are
private and simply absent, so this would either red on every run or derive an
EMPTY population and print a confident green over zero repos.

    this script              workstation, on demand, every contract repo
    orphaned_attr_gate.py    CI, per-push (docs_gate.sh), katgpt-rs only

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
# DRY: the classifier and the walk are the per-push gate's, so the sweep and
# the gate can never disagree about what "orphaned" means.
import orphaned_attr_gate as oag  # noqa: E402
from skill_repo_set_gate import derive_repos  # noqa: E402
from sweep_population import population_verdict  # noqa: E402
from tracked_walk import tracked_files  # noqa: E402

REPO_ROOT = HERE.parent
WORKSPACE = REPO_ROOT.parent
PINS = HERE / "orphaned_attr_drift_floors.txt"

FIELDS = ("min_rs_files", "min_cfg_sites", "max_offenders")


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


def selftest() -> list[str]:
    """Pin that the verdict FIRES through the gate's own `scan()`, that the
    three NEGATIVES that define the narrowing do not, and that the walk's
    boundaries hold. Each fails silently otherwise, and a silent failure
    reports a clean workspace.

    Measured through `scan()` and not the regexes: the regexes are already
    self-tested inside the gate, and what this sweep adds is the WALK around
    them — the half that can go blind per-repo.
    """
    fails: list[str] = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    def measure(files: dict[str, str], gitignore: str = "", add: bool = True):
        """`scan()` over a real git repo.

        A real `git init` + `git add`: `tracked_files` shells out to
        `git ls-files` and falls back to an rglob walk when that set is EMPTY,
        so a temp dir with nothing staged would exercise the FALLBACK and
        certify the branch these arms are not aimed at (the Issue-775 vendor
        arm's exact failure — one exclusion, two code paths).
        """
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            subprocess.run(["git", "-C", str(repo), "init", "-q"],
                           capture_output=True, check=True)
            if gitignore:
                (repo / ".gitignore").write_text(gitignore, encoding="utf-8")
            for rel, text in files.items():
                f = repo / rel
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(text, encoding="utf-8")
            if add:
                subprocess.run(["git", "-C", str(repo), "add", "-A"],
                               capture_output=True, check=True)
            return oag.scan(repo)

    # 1. the defect FIRES, with the right line, through the walk. This is the
    #    `26d055c6` shape verbatim: an attribute left behind by a deleted
    #    `use`, silently re-bound to the NEXT import.
    s = measure({"a.rs": "#[cfg(debug_assertions)]\n\nuse crate::x::Y;\n"})
    if s.files != 1 or s.cfg_sites != 1:
        fails.append(f"walk found files={s.files} sites={s.cfg_sites}, expected "
                     f"1/1 — git ls-files or the regex regressed; every arm "
                     f"below is vacuous")
    elif [(o[0], o[1]) for o in s.offenders] != [("a.rs", 1)]:
        fails.append(f"planted orphan: got {s.offenders}, expected a.rs:1")

    # 2. CONTROL: the attribute ADJACENT to its item is the correct form and is
    #    overwhelmingly the common one — a false positive here reds every repo.
    s = measure({"a.rs": "#[cfg(debug_assertions)]\nuse crate::x::Y;\n"})
    if s.offenders or s.cfg_sites != 1:
        fails.append(f"control: an adjacent attribute produced {s.offenders}")

    # 3. the NARROWING, and it is the whole instrument: an INNER `#![cfg]`
    #    binds to the enclosing module, so a blank line after it is CORRECT
    #    and conventional. Counting it is what makes the naive measurement
    #    2,044 instead of 0 — if this arm ever passes a finding, the sweep
    #    reports thousands.
    s = measure({"a.rs": '#![cfg(feature = "x")]\n\nuse crate::x::Y;\n'})
    if s.offenders or s.cfg_sites != 0:
        fails.append(f"narrowing: an INNER #![cfg] was treated as outer: "
                     f"{s.offenders} sites={s.cfg_sites}")

    # 4. the two "not the item" negatives, which are the reason the reported
    #    count is 0 rather than merely small: a following COMMENT and a
    #    following ATTRIBUTE are not items, and a blank-line RUN means the
    #    attribute dangles further down than i+2.
    for label, src in {
        "comment": "#[cfg(test)]\n\n// a note\nuse crate::x::Y;\n",
        "attribute": "#[cfg(test)]\n\n#[derive(Debug)]\nstruct S;\n",
        "blank-run": "#[cfg(test)]\n\n\nuse crate::x::Y;\n",
    }.items():
        s = measure({"a.rs": src})
        if s.offenders:
            fails.append(f"negative {label}: produced {s.offenders}")

    # 5. walk boundaries, both directions in ONE measurement. TRACKED-only
    #    (Issue 777): this is the exact axis whose absence made the docstring
    #    figure 46% too large. TWO tracked files, not one — a count of 1
    #    cannot distinguish "the untracked file was excluded" from "the walk
    #    collapsed to a single file".
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        subprocess.run(["git", "-C", str(repo), "init", "-q"],
                       capture_output=True, check=True)
        (repo / ".gitignore").write_text("vendor/\n", encoding="utf-8")
        (repo / "a.rs").write_text("fn a() {}\n", encoding="utf-8")
        (repo / "b.rs").write_text("fn b() {}\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "a.rs", "b.rs",
                        ".gitignore"], capture_output=True, check=True)
        (repo / "untracked.rs").write_text(
            "#[cfg(test)]\n\nuse crate::x::Y;\n", encoding="utf-8")
        (repo / "vendor").mkdir()
        (repo / "vendor" / "v.rs").write_text(
            "#[cfg(test)]\n\nuse crate::x::Y;\n", encoding="utf-8")
        s = oag.scan(repo)
        if s.files != 2:
            fails.append(f"walk boundaries: walked {s.files} .rs, expected 2 "
                         f"(the two tracked yes, the untracked and gitignored "
                         f"ones no)")
        if s.offenders:
            fails.append(f"walk boundaries: an untracked/gitignored file "
                         f"produced {s.offenders} — the sweep would report "
                         f"findings in trees no repo owns")

    # 6. population derivation: BOUNDARY.md + a .git DIRECTORY, both required.
    #    A `git worktree` has a .git FILE and would duplicate its parent.
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "real").mkdir()
        (ws / "real" / "BOUNDARY.md").write_text("x")
        (ws / "real" / ".git").mkdir()
        (ws / "no-boundary").mkdir()
        (ws / "no-boundary" / ".git").mkdir()
        (ws / "worktree-shaped").mkdir()
        (ws / "worktree-shaped" / "BOUNDARY.md").write_text("x")
        (ws / "worktree-shaped" / ".git").write_text("gitdir: elsewhere")
        if derive_repos(ws) != ["real"]:
            fails.append(f"population derivation wrong: {derive_repos(ws)}")

        # 7. pin parser: arity ENFORCED, comments stripped.
        pins = ws / "pins.txt"
        pins.write_text("# c\nrepo-a 1500 4000 0  # trailing\n\n")
        if parse_pins(pins) != {"repo-a": dict(zip(FIELDS, (1500, 4000, 0)))}:
            fails.append("pin parse: 4-field row not read correctly")
        pins.write_text("repo-a 1 2\n")
        try:
            parse_pins(pins)
            fails.append("pin parse: short row accepted")
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
        print("✗ orphaned-attr sweep SELFTEST FAILED — instrument untrustworthy:")
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

    # Same quantities, two files: this sweep re-states the two floors the
    # per-push gate owns for THIS repo. Asserted, not trusted — the whole
    # subject of Issue 784 is a quantity that lived in one place by hand.
    mine = pins.get(REPO_ROOT.name, {})
    for field, owned in (("min_rs_files", oag.FLOOR_FILES),
                         ("min_cfg_sites", oag.FLOOR_CFG_SITES)):
        if mine.get(field) != owned:
            print(f"✗ pin drift: {PINS.name} says {field}={mine.get(field)} for "
                  f"{REPO_ROOT.name}, orphaned_attr_gate owns {owned}. "
                  f"Same quantity, two files — change both.")
            return 1

    bad = False
    tot_files = tot_sites = tot_off = tot_vend = 0

    for name in names:
        repo = WORKSPACE / name
        s = oag.scan(repo)
        # The vendored count rides the per-repo line rather than vanishing
        # (Issue 738 T3) — riir-ai's wgpu-hal fork is a third of this
        # workspace's excluded `.rs`, and a reader comparing two runs needs to
        # see it rather than infer it.
        _kept, vendored = tracked_files(repo, "*.rs")
        tot_files += s.files
        tot_sites += s.cfg_sites
        tot_off += len(s.offenders)
        tot_vend += vendored

        row = pins.get(name)
        flags = []
        if row is None:
            flags.append("UNPINNED — add a row (or it can never red)")
        else:
            if s.files < row["min_rs_files"]:
                flags.append(f"walk FLOOR breached: {s.files} tracked .rs < "
                             f"{row['min_rs_files']} — sources were removed, or "
                             f"`git ls-files` went blind and the 0 below means "
                             f"nothing")
            if s.cfg_sites < row["min_cfg_sites"]:
                flags.append(f"parse FLOOR breached: {s.cfg_sites} outer-#[cfg] "
                             f"site(s) < {row['min_cfg_sites']} — the walk is "
                             f"intact but the regex matched nothing")
            if len(s.offenders) > row["max_offenders"]:
                flags.append(f"orphaned {len(s.offenders)} > pinned "
                             f"{row['max_offenders']}")

        status = "✗" if flags else ("·" if s.offenders else "✓")
        vend = f" vendored={vendored}" if vendored else ""
        print(f"{status} {name:22s} rs={s.files:<5d} cfg_sites={s.cfg_sites:<6d} "
              f"orphaned={len(s.offenders)}{vend}")
        for rel, line, attr, nxt in s.offenders:
            print(f"      ⛔ {rel}:{line}  {attr}  ->  binds to: {nxt}")
        for f in flags:
            bad = True
            print(f"      ✗ {f}")

    # The population axis, shared (Issues 779 + 782): UNREGISTERED reds in every
    # posture, UNSEEN reds without the marker, and the same set DEFERS loudly
    # with it. Never auto-detected — a genuine removal whose row update was
    # forgotten is set-identical to a partial clone from the walk alone.
    pop_lines, deferred, pop_fail = population_verdict(pins, names)
    for _line in pop_lines:
        print(_line)
    if pop_fail:
        bad = True

    print(f"\n{len(names)} contract repo(s) · {tot_files} tracked .rs "
          f"({tot_vend} vendored, excluded) · {tot_sites} outer-#[cfg] site(s) "
          f"· {tot_off} orphaned")
    # State the scope where it is READ, not only in the docstring. This is the
    # line Issue 784 exists to make self-measuring.
    print("  scope: OUTER `#[cfg]` / `#[cfg_attr]` only. The broad shape (any "
          "attribute + blank line + item) is ~2,044 sites and is NOT gateable "
          "— it is dominated by whole-file INNER `#![cfg]`, which binds to the "
          "enclosing module and is conventionally followed by a blank line. "
          "The narrowing IS the instrument.")

    if bad:
        print("✗ orphaned-attr sweep FAILED — see the ✗ rows above")
        for _d in deferred:
            print(f"  ⚠ {_d}")
        print("    Rust binds an attribute to the next item ACROSS a blank "
              "line, so the reported attribute applies to the item named after "
              "`binds to:`. Check what it USED to apply to before deleting the "
              "blank line — `7e34ccef` deleted one and made a wrong binding "
              "look deliberate.")
        return 1
    _line = "✓ orphaned-attr sweep PASSED — every repo within its pins"
    if deferred:
        _line += "; DEFERRED: " + "; ".join(deferred)
    print(_line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
