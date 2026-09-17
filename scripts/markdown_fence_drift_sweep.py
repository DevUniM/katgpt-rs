#!/usr/bin/env python3
"""Run the unterminated-fence verdict over EVERY contract repo, not just this one.

`scripts/markdown_fence_gate.py` is katgpt-rs-scoped by construction — it walks
`REPO_ROOT` and `docs_gate.yml` has a single checkout, so it could never see a
sibling. That is the right shape for a per-push CI gate and the wrong shape for
"is anybody ELSE about to render half a document as code?"

The workspace answer to that question was just bought and is being held by
nothing. Issue 756 took the population from **19 files / 611 swallowed lines**
to zero, across three repos and 5048 tracked `.md`:

    katgpt-rs   1bf768cd + ed455885   12      riir-ai    a1a205681 + 6e73d89c5   5
    riir-train  d761a375 + ca21b763    2
    mmorpg-remaster 99064c5      1  (the sweep's own first catch, 2026-09-12)

Twelve of those nineteen were in this repo, where a gate now stands. The other
**seven** were in repos where one edit puts them back with no word from any
gate — and the class is silent by construction: a swallowed section still
renders, just as a code listing, so nothing errors and nobody notices until a
parser mis-phases on it. That is how the class was found in the first place
(`rust-optimize/SKILL.md`'s unclosed ```text ate `skill_repo_set_gate.py`'s own
first canary).

This is the sixth instance of one shape in this workspace, and every one of
them found something the moment it was pointed anywhere but here:

    Issue 702  ci_gate_coverage              one repo -> 7 dead workflows
    Issue 725  numbering_drift_sweep         one repo -> 35 duplicate numbers
    2026-09-06 required_features_drift_sweep one repo -> clean, and pinned there
    2026-09-06 percentile_drift_sweep        one repo -> clean, and pinned there
    2026-09-07 trap_sentinel_drift_sweep     one repo -> 1 finding, pinned + proven inert
    this file  markdown_fence_drift_sweep    one repo -> clean at 19 repos / 5058 files;
                                       its first workspace run (2026-09-12, 20 repos after
                                       mmorpg-remaster joined the set) caught 1 finding
                                       in the new repo — repaired + floored the same day

Why BOTH pins, and why the walk floor is not redundant
------------------------------------------------------
`max_unterminated = 0` is green over whatever the walk can SEE, and the walk
shells out to `git ls-files` — a regression there takes the population to 0 and
the ceiling passes, indistinguishable from a clean repo. `min_md_files` is the
quantity that actually moves when the walk goes blind, and unlike the trap
sweep's population floor it is non-zero in **every** repo (the smallest,
riir-kat, has 3 tracked `.md`), so one floor does the whole job here.

It is deliberately SLACK against churn (~55-60% of measured) and TIGHT against
blindness: consolidating a `.plans` tree or removing a resolved-issue batch
legitimately shrinks the count, and a floor that ratcheted to the last
measurement would red that cleanup and teach whoever hit it that the sweep is
noise. A walk regression drops these by an order of magnitude, not by a third.

katgpt-rs's floor is NOT free: it must equal `markdown_fence_gate.MIN_FILES`,
and this sweep ASSERTS that rather than trusting it — same quantity, two files,
the pattern `docs_gate_paths_sync.py` uses for the two trigger lists and
`trap_sentinel_drift_sweep.py` for `POPULATION_FLOOR`.

No membership pin, deliberately
-------------------------------
`trap_sentinel_gate.py` pins its set by NAME because a count is not a checksum
over a set. That argument does not apply here: the verdict is DERIVED from the
file's own fence structure, and there is no repaired-file list to lose. Every
way to reintroduce the defect lands on `max_unterminated`; every way to lose
sight of it lands on `min_md_files`.

Why this is NOT in scripts/docs_gate.sh's CHECKS
------------------------------------------------
Identical to the other five sweeps: CI has one checkout, the siblings are
private and simply absent, so this would either red on every run or derive an
EMPTY population and print a confident green over zero repos.

    this script               workstation, on demand, every contract repo
    markdown_fence_gate.py    CI, per-push (docs_gate.sh), katgpt-rs only

⚠ The reported line is the DANGLING fence, NOT necessarily the defect — one
stray fence inverts the pairing of every fence after it, so two of riir-train's
repairs were 495 and 21 lines UPSTREAM of what was reported. Read the first
non-blank body line before editing: code means a closer is missing, prose means
the fence itself is the orphan, and a same-length nested fence (riir-ai
`.issues/094`) needs the OUTER pair widened to ```` — deleting the "extra"
fence leaves the inner code rendering as prose permanently.

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
# the gate can never disagree about what "unterminated" means — and the fence
# parser under them both is `skill_repo_set_gate.fenced_blocks`, imported
# rather than re-derived (Issue 755: a second copy of a rule this subtle is a
# second thing to get wrong).
import markdown_fence_gate as mfg  # noqa: E402
from skill_repo_set_gate import derive_repos  # noqa: E402
from sweep_population import population_verdict, pin_row_exempt  # noqa: E402
from worktree_state import (HeadDelta, head_delta,  # noqa: E402
                            sweep_advisory)

REPO_ROOT = HERE.parent
WORKSPACE = REPO_ROOT.parent
PINS = HERE / "markdown_fence_drift_floors.txt"

FIELDS = ("min_md_files", "max_unterminated")



def md_population(repo: Path) -> tuple[set[str], set[str]]:
    """`(walk, untracked)` — this sweep's own population, split by trackedness.

    The same two `git ls-files` invocations `mfg.unterminated` walks with, so
    the split cannot disagree with the thing it is splitting. `--exclude-standard`
    keeps gitignored vendored drops out of both halves.
    """
    def listing(*args) -> set[str]:
        out = subprocess.run(["git", "-C", str(repo), "ls-files", *args],
                             capture_output=True, encoding="utf-8",
                             errors="replace")
        if out.returncode != 0:
            return set()
        return {ln.strip().replace(chr(92), "/")
                for ln in out.stdout.splitlines() if ln.strip()}

    tracked = listing("*.md")
    untracked = listing("--others", "--exclude-standard", "*.md")
    return tracked | untracked, untracked


def head_fences(walk: set):
    """`head_delta`'s per-file reclassifier."""

    def rescan(rel: str, src: str | None) -> list:
        # None = absent from HEAD. Unreachable for this sweep's tracked half
        # unless a file is staged-and-never-committed, which is exactly the
        # case it must not invent a row for.
        if src is None or rel not in walk:
            return []
        return mfg.scan_text(rel, src)

    return rescan


def adjudicate(repo: Path, found: list) -> HeadDelta:
    """The rows, split COMMITTED / UNCOMMITTED / MASKED (Issue 822).

    ⛔ The UNTRACKED split happens FIRST and outside `head_delta`. An untracked
    document is in no commit, so its row can never be what HEAD carries — but
    `dirty_files` excludes untracked paths by design, so `head_delta` is blind
    to them and would file every one as COMMITTED. A finding on a file
    `git log` cannot see, counted into a ceiling, is this issue's whole subject.
    """
    walk, loose = md_population(repo)
    rows = [r for r in found if r[0].replace(chr(92), "/") not in loose]
    held = [r for r in found if r[0].replace(chr(92), "/") in loose]
    d = head_delta(
        repo, ("*.md",), rows,
        lambda r: r[0], lambda r: r[0].replace(chr(92), "/"),
        head_fences(walk))
    return HeadDelta(d.committed, list(d.uncommitted) + held, d.masked)


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


def adjudicate_arms() -> list[str]:
    """`adjudicate`, two-sided, against a real git tree.

    The UNTRACKED arm is the sharpest specimen of Issue 822 in the family: a
    finding on a file `git log` cannot see, which every other sweep's
    population makes impossible and this one's makes routine.
    """
    fails: list[str] = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    def git(cwd, *args):
        subprocess.run(["git", "-C", str(cwd), *args], check=True,
                       capture_output=True)

    NL = chr(10)
    TICK = chr(96) * 3
    OPEN = TICK + "rust" + NL + "let x = 1;" + NL          # never closed
    CLOSED = TICK + "rust" + NL + "let x = 1;" + NL + TICK + NL

    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "r"
        repo.mkdir(parents=True)
        git(repo.parent, "init", "-q", "-b", "main", "r")
        git(repo, "config", "user.email", "t@t")
        git(repo, "config", "user.name", "t")
        (repo / "a.md").write_text(OPEN, encoding="utf-8")
        (repo / "b.md").write_text(CLOSED, encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "base")

        def now():
            found, _walked = mfg.unterminated(repo)
            return found, adjudicate(repo, found)

        found, d = now()
        check(len(found) == 1, f"fixture: found={found}, want 1")
        check(len(d.committed) == 1 and not d.uncommitted and not d.masked,
              f"a clean tree produced a split: {d}")

        # ── the key is `rel` ALONE, and that is a MEASUREMENT ────────────────
        # At most ONE unterminated fence exists per document: everything after
        # an unterminated open is inside it. Asserted here so the key's premise
        # is checked rather than remembered.
        two_opens = OPEN + TICK + "rust" + NL + "let y = 2;" + NL
        check(len(mfg.scan_text("x.md", two_opens)) == 1,
              f"two opens reported more than one row — the key needs an "
              f"ordinal after all: {mfg.scan_text('x.md', two_opens)}")

        # ── UNCOMMITTED: the worktree INVENTS an unterminated fence ──────────
        (repo / "b.md").write_text(OPEN, encoding="utf-8")
        found, d = now()
        check([r[0] for r in d.uncommitted] == ["b.md"],
              f"UNCOMMITTED direction: {d.uncommitted}")
        check(not d.masked, f"an invented row was also MASKED: {d.masked}")
        check([r[0] for r in d.head] == ["a.md"],
              f"the pins' view lost the committed row: {d.head}")

        # ── MASKED: the worktree CLOSES a committed fence ────────────────────
        git(repo, "checkout", "--", "b.md")
        (repo / "a.md").write_text(CLOSED, encoding="utf-8")
        found, d = now()
        check(not found, f"the fixture did not close the fence: {found}")
        check([r[0] for r in d.masked] == ["a.md"], f"MASKED direction: {d.masked}")
        check(len(d.head) == 1,
              f"a MASKED row is missing from the pins' view: {d.head}")

        # ── ⛔ UNTRACKED: in NO commit, so never adjudicated ─────────────────
        # This sweep walks tracked PLUS untracked-not-ignored (its own landing
        # miss: `.issues/756` carried a live fence while untracked). An
        # untracked file cannot be in HEAD, and `dirty_files` excludes it by
        # design — so without the explicit split it lands in `committed` and is
        # counted against the ceiling. That is Issue 822's defect exactly.
        git(repo, "checkout", "--", "a.md")
        (repo / "loose.md").write_text(OPEN, encoding="utf-8")
        found, d = now()
        check(any(r[0] == "loose.md" for r in found),
              f"the walk did not see the untracked file: {found}")
        check(any(r[0] == "loose.md" for r in d.uncommitted),
              f"an UNTRACKED file's row was adjudicated — it is in no commit: "
              f"{d.uncommitted}")
        check(all(r[0] != "loose.md" for r in d.head),
              f"a file in no commit entered the pins' view: {d.head}")
        # ...and it does NOT become MASKED either, which would be a red nobody
        # can repair.
        check(all(r[0] != "loose.md" for r in d.masked),
              f"an untracked file was reported MASKED: {d.masked}")
        (repo / "loose.md").unlink()

        # ── a STAGED-only file has no HEAD blob ─────────────────────────────
        (repo / "new.md").write_text(OPEN, encoding="utf-8")
        git(repo, "add", "new.md")
        found, d = now()
        check(any(r[0] == "new.md" for r in d.uncommitted),
              f"a staged-only file's row was not UNCOMMITTED: {d.uncommitted}")
        check(all(r[0] != "new.md" for r in d.head),
              f"a file in no commit entered the pins' view: {d.head}")

        # ── the WALK guard ──────────────────────────────────────────────────
        check(head_fences(set())("a.md", OPEN) == [],
              "a path outside the sweep's own walk produced a row")

    return fails


def selftest() -> list[str]:
    """Pin that the verdict FIRES through the gate's own `unterminated()`, that
    the control does NOT, that the closer-length and nesting rules are live,
    and that the walk's include/exclude boundaries hold. Each fails silently
    otherwise, and a silent failure reports a clean workspace."""
    fails = []

    def measure(files: dict[str, str], gitignore: str = "") -> tuple[list, int]:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            # A real `git init`: `unterminated()` shells out to `git ls-files`
            # and has NO on-disk fallback, so a bare temp dir would measure an
            # empty population and every arm below would pass vacuously. The
            # walk floor asserted by each caller is what catches that.
            subprocess.run(["git", "-C", str(repo), "init", "-q"],
                           capture_output=True, check=True)
            if gitignore:
                (repo / ".gitignore").write_text(gitignore, encoding="utf-8")
            for rel, text in files.items():
                f = repo / rel
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(text, encoding="utf-8")
            return mfg.unterminated(repo)

    # 1. the defect FIRES, with the right line and the right swallow count.
    #    `a.md` is 5 lines; the fence opens on 3, so 2 lines are swallowed.
    found, walked = measure({"a.md": "# T\n\n```rust\nfn main() {}\nstill code\n"})
    if walked != 1:
        fails.append(f"walk found {walked} .md, expected 1 — git ls-files or the "
                     f"untracked arm regressed; every arm below is vacuous")
    elif found != [("a.md", 3, 2)]:
        fails.append(f"planted unterminated fence: got {found}, "
                     f"expected [('a.md', 3, 2)]")

    # 2. CONTROL: a closed fence must produce NO finding, or the sweep reds on
    #    every correct repair and gets switched off.
    found, walked = measure({"a.md": "# T\n\n```rust\nfn main() {}\n```\n\ntail\n"})
    if walked != 1 or found:
        fails.append(f"control: a CLOSED fence produced {found} over {walked} file(s)")

    # 3. the riir-ai/094 shape: a ````-wrapped block quoting a ``` block. The
    #    inner fence must NOT close the outer one, or every nested doc reds.
    found, walked = measure(
        {"a.md": "````md\nquoting:\n```rust\nfn main() {}\n```\n````\n\ntail\n"})
    if walked != 1 or found:
        fails.append(f"nesting: a ````-wrapped ``` block produced {found}")

    # 4. the closer-length rule is LIVE and is the reason arm 3 works: a run
    #    SHORTER than the opener does not close it, so this file IS a finding.
    found, walked = measure({"a.md": "````text\nbody\n```\nmore\n"})
    if walked != 1 or [r[0] for r in found] != ["a.md"]:
        fails.append(f"closer length: a ``` must not close a ````, got {found}")

    # 5. walk boundaries, both directions in ONE measurement — an untracked
    #    file IS walked (the miss that cost this gate its own landing: Issue
    #    756's file was untracked when the gate ran) and a GITIGNORED one is
    #    NOT (the vendored-drop precedent from trap_exit_launder_audit).
    #    TWO visible files, not one: a count of 1 cannot distinguish "the
    #    ignored file was excluded" from "the walk collapsed to a single file".
    found, walked = measure(
        {"a.md": "ok\n", "docs/b.md": "ok\n", "vendor/bad.md": "```rust\nfn main() {}\n"},
        gitignore="vendor/\n")
    if walked != 2:
        fails.append(f"walk boundaries: walked {walked}, expected 2 "
                     f"(the two untracked .md yes, the gitignored one no)")
    if found:
        fails.append(f"walk boundaries: a GITIGNORED file produced {found} — "
                     f"the sweep would report findings in trees no repo owns")

    # 6. population derivation: BOUNDARY.md + a .git DIRECTORY, both required.
    #    A `git worktree` has a .git FILE and would duplicate its parent.
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "real").mkdir()
        (ws / "real" / "BOUNDARY.md").write_text("x", encoding="utf-8")
        (ws / "real" / ".git").mkdir()
        (ws / "no-boundary").mkdir()
        (ws / "no-boundary" / ".git").mkdir()
        (ws / "worktree-shaped").mkdir()
        (ws / "worktree-shaped" / "BOUNDARY.md").write_text("x", encoding="utf-8")
        (ws / "worktree-shaped" / ".git").write_text("gitdir: elsewhere", encoding="utf-8")
        if derive_repos(ws) != ["real"]:
            fails.append(f"population derivation wrong: {derive_repos(ws)}")

        # 7. pin parser: arity ENFORCED, comments stripped.
        pins = ws / "pins.txt"
        pins.write_text("# c\nrepo-a 800 0  # trailing\n\n", encoding="utf-8")
        if parse_pins(pins) != {"repo-a": dict(zip(FIELDS, (800, 0)))}:
            fails.append("pin parse: 3-field row not read correctly")
        pins.write_text("repo-a 1\n", encoding="utf-8")
        try:
            parse_pins(pins)
            fails.append("pin parse: short row accepted")
        except ValueError:
            pass
    # ⛔ Issue 822: `adjudicate`'s body is reached by nothing else, and
    # arm_reach_gate walls the docs_gate CHECKS set (25 modules, 0 drift
    # sweeps) rather than this.
    return fails + adjudicate_arms()


def main() -> int:
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass  # not a TextIOWrapper (embedded / detached); keep old behavior

    fails = selftest()
    if fails:
        print("✗ markdown fence sweep SELFTEST FAILED — instrument untrustworthy:")
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

    # Same quantity, two files: this sweep re-states the walk floor that the
    # per-push gate owns for THIS repo. Asserted, not trusted.
    mine = pins.get(REPO_ROOT.name, {}).get("min_md_files")
    if mine != mfg.MIN_FILES:
        print(f"✗ pin drift: {PINS.name} says min_md_files={mine} for "
              f"{REPO_ROOT.name}, markdown_fence_gate.MIN_FILES is "
              f"{mfg.MIN_FILES}. Same quantity, two files — change both.")
        return 1

    bad = False
    tot_files = tot_found = tot_swallowed = 0

    n_uncommitted = n_masked = 0

    for name in names:
        repo = WORKSPACE / name
        found, walked = mfg.unterminated(repo)

        # ── Issue 822: the DISPLAY reads the worktree, the PINS read HEAD ───
        delta = adjudicate(repo, found)
        n_uncommitted += len(delta.uncommitted)
        n_masked += len(delta.masked)

        row = pins.get(name)
        swallowed = sum(r[2] for r in found)
        tot_files += walked
        tot_found += len(found)
        tot_swallowed += swallowed

        flags = []
        if row is None:
            # Issue 821: an acknowledged known-extra owes no pin row —
            # the marker reached population_verdict's FINAL line and not
            # this loop, so 8 of 9 sweeps red on repos they found
            # nothing in, hiding two live ratchet breaches.
            if not pin_row_exempt(name):
                flags.append("UNPINNED — add a row (or it can never red)")
        else:
            if walked < row["min_md_files"]:
                flags.append(f"walk FLOOR breached: {walked} .md < "
                             f"{row['min_md_files']} — documents were removed, "
                             f"or `git ls-files` went blind and the 0 below "
                             f"means nothing")
            if len(delta.head) > row["max_unterminated"]:
                flags.append(f"unterminated {len(delta.head)} committed > "
                             f"pinned {row['max_unterminated']}")

        status = "✗" if flags else ("·" if found else "✓")
        # T3: the count stays honest in BOTH directions. A bare total invites
        # the one action Issue 822 exists to prevent — typing it into the pin.
        split = ""
        if delta.uncommitted or delta.masked:
            split = (f" ({len(delta.head)} committed"
                     + (f" + {len(delta.uncommitted)} uncommitted"
                        if delta.uncommitted else "")
                     + (f", {len(delta.masked)} MASKED" if delta.masked else "")
                     + ")")
        print(f"{status} {name:22s} md={walked:<5d} unterminated={len(found)} "
              f"swallowed={swallowed}{split}")
        held = {r[0] for r in delta.uncommitted}
        for rel, line, swal in sorted(found, key=lambda r: -r[2]):
            # Never hidden — hiding them is the lie Issue 797 refuses — but
            # labelled. An UNTRACKED document lands here too and is the case a
            # reader most needs told apart: it is in no commit AT ALL, so the
            # fence is real and live but the ceiling cannot be about it.
            tag = "  [UNCOMMITTED — not adjudicated]" if rel in held else ""
            print(f"      {rel}:{line}  {swal} line(s) render as code to EOF"
                  f"{tag}")
        for rel, line, swal in delta.masked:
            print(f"      {rel}:{line}  {swal} line(s) render as code to EOF"
                  f"  [MASKED — committed, and this worktree hides it]")
        for f in flags:
            bad = True
            print(f"      ✗ {f}")

    # The population axis, shared (Issue 793): UNREGISTERED reds in every
    # posture, UNSEEN reds without the marker, and the same set DEFERS loudly
    # with it. Never auto-detected — a genuine removal whose row update was
    # forgotten is set-identical to a partial clone from the walk alone.
    pop_lines, deferred, pop_fail = population_verdict(pins, names)

    # Issue 797 — the worktree is not the repo. This run reads files that
    # concurrent sessions are editing, so a finding may sit on a line no
    # commit contains. ADVISORY, never a failure: a sweep that hard-reds on
    # an ordinary dirty worktree is a sweep nobody runs. It rides the FINAL
    # line in BOTH directions (the `deferred` precedent) and is SILENT
    # unless the dirty set meets this sweep's own population — the fenced documents.
    deferred.extend(sweep_advisory(
        names, ("*.md",), root=WORKSPACE))
    for _line in pop_lines:
        print(_line)
    if pop_fail:
        bad = True

    print(f"\n{len(names)} contract repo(s) · {tot_files} tracked+untracked .md · "
          f"{tot_found} unterminated fence(s) · {tot_swallowed} line(s) rendering "
          f"as code")
    # State the scope where it is READ, not only in the docstring.
    print("  scope: UNTERMINATED only. A fence indented 4+ spaces is a real "
          "fence in a list item here (73 workspace-wide), so the parser cannot "
          "exclude indentation — documents adapt, the scanner does not.")

    if bad:
        print("✗ markdown fence sweep FAILED — see the ✗ rows above")
        for _d in deferred:
            print(f"  ⚠ {_d}")
        print("    The reported line is the DANGLING fence, not necessarily the "
              "defect: read the first non-blank body line — code means a closer "
              "is missing, prose means the fence is an orphan, and a nested "
              "same-length fence needs the OUTER pair widened to ````.")
        return 1
    _line = "✓ markdown fence sweep PASSED — every repo at or under its pins"
    if deferred:
        _line += "; DEFERRED: " + "; ".join(deferred)
    print(_line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
