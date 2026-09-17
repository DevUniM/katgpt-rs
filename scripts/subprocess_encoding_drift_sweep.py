#!/usr/bin/env python3
"""Run the locale-decoding verdict over EVERY contract repo, not just this one.

`scripts/subprocess_encoding_gate.py` (Issue 778) is katgpt-rs-scoped by
construction — it walks `REPO_ROOT` and `docs_gate.yml` has a single checkout,
so it could never see a sibling. That is the right shape for a per-push CI gate
and the wrong shape for "is anybody ELSE about to read a child's pipe through
the system locale?"

Eleven other verdict classes here carry BOTH halves. 778 shipped with one, and
the asymmetry was not a judgement call — it was a step that was skipped. This
is the seventh instance of one shape in this workspace, and the seventh time
pointing it anywhere but here found something (Issue 783):

    Issue 702  ci_gate_coverage              one repo -> 7 dead workflows
    Issue 725  numbering_drift_sweep         one repo -> 35 duplicate numbers
    2026-09-06 required_features_drift_sweep one repo -> clean, and pinned there
    2026-09-06 percentile_drift_sweep        one repo -> clean, and pinned there
    2026-09-07 trap_sentinel_drift_sweep     one repo -> 1 finding, proven inert
    2026-09-12 markdown_fence_drift_sweep    one repo -> 1 finding in a repo that
                                             joined AFTER the landing measurement
    this file  subprocess_encoding_sweep     one repo -> 29 DECODE + 2
                                             CHILD-ENCODER over 5 repos

The 31 at landing (2026-09-14), all repaired in the same change:

    riir-train 12+1 · riir-clippy 9+1 · riir-ai 6 · riir-dapps 1 · mmorpg-editor 1

Two of them were not latent. `riir-clippy/scripts/gen_dashboard.py:552` reads
`git log --pretty=%s` across the sibling repos, and every commit subject in this
workspace uses an em-dash; `riir-train/scripts/plan344_phase0_full_bandwidth.py`
reads a `git ls-files` list and then opens the paths.

Why BOTH floors, and why the walk floor carries the weight here
---------------------------------------------------------------
`max_decode = 0` is green over whatever the walk can SEE, and the walk shells
out to `git ls-files` — a regression takes the population to 0 and the ceiling
passes, indistinguishable from a clean repo. So the population is pinned
underneath it, in two independent quantities: `min_py_files` moves when the
WALK goes blind, `min_calls` when the AST PASS breaks on an unchanged tree.

⚠ Unlike the fence sweep — whose single `min_md_files` is non-zero in all 20
repos and so bites everywhere — `min_calls` is **0 in 10 of 16 repos measured**,
because those repos have `.py` files and no `subprocess` at all. A parse floor
of 0 cannot detect anything. In exactly those repos the walk floor is the only
blindness detector there is, which is why both are pinned and neither is
derived from the other.

katgpt-rs's two floors are NOT free: they must equal
`subprocess_encoding_gate.FLOOR_PY_FILES` / `FLOOR_CALLS`, and this sweep
ASSERTS that rather than trusting it — same quantity, two files, the pattern
`docs_gate_paths_sync.py` uses for the two trigger lists and
`trap_sentinel_drift_sweep.py` for `POPULATION_FLOOR`.

No membership pin, deliberately
-------------------------------
`trap_sentinel_gate.py` pins its set by NAME because a count is not a checksum
over a set. That does not apply here: the verdict is DERIVED from each call's
own keywords and there is no repaired-file list to lose. Every way to
reintroduce the defect lands on a ceiling; every way to go blind to it lands on
a floor.

Why this is NOT in scripts/docs_gate.sh's CHECKS
------------------------------------------------
Identical to the other eleven sweeps: CI has one checkout, the siblings are
private and simply absent, so this would either red on every run or derive an
EMPTY population and print a confident green over zero repos.

    this script                   workstation, on demand, every contract repo
    subprocess_encoding_gate.py   CI, per-push (docs_gate.sh), katgpt-rs only

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
# the gate can never disagree about what "decodes with the system locale"
# means (Issue 755: a second copy of a rule this subtle is a second thing to
# get wrong).
import subprocess_encoding_gate as seg  # noqa: E402
from skill_repo_set_gate import derive_repos  # noqa: E402
from sweep_population import population_verdict, pin_row_exempt  # noqa: E402
from tracked_walk import tracked_files  # noqa: E402
from worktree_state import (head_delta, line_free,  # noqa: E402
                            ordinal_keys, sweep_advisory)

REPO_ROOT = HERE.parent
WORKSPACE = REPO_ROOT.parent
PINS = HERE / "subprocess_encoding_drift_floors.txt"

FIELDS = ("min_py_files", "min_calls", "max_decode", "max_child")


def keyed(rows) -> list:
    """`[(key, rel, kind, row)]` for a row set, ordinals assigned in order.

    A LINE-FREE key, Issue 822. ⛔ The rows this sweep prints are
    `"{lineno}: {call text}"`, and a line-bearing key reports EVERY row in an
    edited file as UNCOMMITTED *and* MASKED at once — any insertion above a
    call shifts it. So the line is dropped and the call's own unparsed text
    carries the identity, with an ORDINAL for the two-identical-calls case.

    ⛔ **Both rules are `worktree_state`'s now (T5d), not this file's.** T5c
    solved them here, inline, and the next sweep that needed them would have
    copied them — the never-generalised shape AGENTS.md records nine times.
    `line_free` is the stricter half of what this file had: it strips a prefix
    only when it is a bare integer, so a row whose own text begins `note: …`
    comes back whole instead of being silently beheaded.
    """
    return [(k, rel, kind, row)
            for k, (rel, kind, row) in
            ordinal_keys(rows, lambda t: (t[0], t[1], line_free(t[2])))]


def flatten(decode: dict, child: dict) -> list:
    """The two buckets as one addressed row list, kind preserved.

    ONE delta rather than two, because the ordinal in `row_key` has to be
    assigned over the whole address space at once; the caller splits `.head`
    back by kind for the two separate pins.
    """
    return ([(rel, "DECODE", r) for rel in sorted(decode) for r in decode[rel]]
            + [(rel, "CHILD", r) for rel in sorted(child) for r in child[rel]])


def head_offenders(walk: set):
    """`head_delta`'s per-file reclassifier for this sweep's two ceilings.

    Per-file row independence holds by construction: `scan_text` is an AST pass
    over ONE module's source. `walk` is the sweep's own tracked population,
    passed in rather than re-derived — `fnmatch`'s `*` crosses `/`, so the
    scope glob admits paths the walk excludes, and a row invented there reads
    as MASKED, a hard red nobody can repair.
    """

    def rescan(rel: str, src: str | None) -> list:
        # None = absent from HEAD (staged but never committed): nothing
        # committed to classify, so the worktree's row is UNCOMMITTED.
        if src is None or rel not in walk:
            return []
        try:
            decode, child, _ = seg.scan_text(src)
        except SyntaxError:
            # UNPARSED at HEAD is the instrument admitting it cannot read, and
            # it has its own bucket one level up. Never folded into either
            # ceiling — counting it as clean hides exposure, counting it as an
            # offender invents it.
            return []
        return ([(rel, "DECODE", r) for r in decode]
                + [(rel, "CHILD", r) for r in child])

    return rescan


def adjudicate(repo: Path, decode: dict, child: dict, walk: set):
    """The offender rows, split COMMITTED / UNCOMMITTED / MASKED (Issue 822).

    A named seam, not four lines inline: this is the verdict arithmetic, and
    `arm_reach_audit`'s standing finding in this repo is that the classifier is
    well armed and the verdict is not.
    """
    rows = keyed(flatten(decode, child))
    rescan = head_offenders(walk)
    return head_delta(
        repo, ("*.py",), rows,
        lambda r: r[1], lambda r: r[0],
        lambda rel, src: keyed(rescan(rel, src)))


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


def split_arms() -> list[str]:
    """The Issue 822 split, two-sided, against a real git tree.

    UNCOMMITTED alone passes on an implementation that ignores HEAD and MASKED
    alone on one that ignores the worktree, so both directions are asserted.
    The LINE-FREE key gets its own arm because this is the first sweep wired
    whose rows carry a line number, and it is the shape most of the remaining
    ones have.
    """
    fails: list[str] = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    def git(cwd, *args):
        subprocess.run(["git", "-C", str(cwd), *args], check=True,
                       capture_output=True)

    BAD = 'import subprocess\nsubprocess.run(["x"], text=True)\n'
    OK = ('import subprocess\n'
          'subprocess.run(["x"], encoding="utf-8")\n')

    # ── the key is LINE-FREE ────────────────────────────────────────────────
    # ⛔ Any insertion above a call shifts its line, so a line-bearing key
    # reports every row in an edited file as UNCOMMITTED *and* MASKED at once.
    a = keyed([("f.py", "DECODE", "12: subprocess.run(['x'], text=True)")])
    b = keyed([("f.py", "DECODE", "99: subprocess.run(['x'], text=True)")])
    check(a[0][0] == b[0][0],
          f"the row key is line-bearing: {a[0][0]} vs {b[0][0]}")
    # ...and two IDENTICAL calls in one file stay distinct.
    two = keyed([("f.py", "DECODE", "1: same(x)"),
                 ("f.py", "DECODE", "7: same(x)")])
    check(two[0][0] != two[1][0],
          f"two identical calls collapsed to one key: {two}")
    # ...while the same text in a DIFFERENT file, or a different KIND, is a
    # different address rather than an ordinal of the first.
    other = keyed([("g.py", "DECODE", "1: same(x)"),
                   ("f.py", "CHILD", "1: same(x)")])
    check(len({two[0][0], other[0][0], other[1][0]}) == 3,
          f"the address is not (file, kind, text): {other}")

    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "r"
        repo.mkdir(parents=True)
        git(repo.parent, "init", "-q", "-b", "main", "r")
        git(repo, "config", "user.email", "t@t")
        git(repo, "config", "user.name", "t")
        (repo / "committed.py").write_text(BAD, encoding="utf-8")
        (repo / "clean.py").write_text(OK, encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "base")

        def now():
            dec, chi, _n, _c, _u = seg.scan(repo)
            walk = {str(f.relative_to(repo)).replace(chr(92), "/")
                    for f in tracked_files(repo, "*.py")[0]}
            return dec, chi, adjudicate(repo, dec, chi, walk)

        dec, chi, d = now()
        check(len(d.committed) == 1 and not d.uncommitted and not d.masked,
              f"a clean tree produced a split: {d}")

        # ── UNCOMMITTED: the worktree INVENTS an offender ───────────────────
        (repo / "clean.py").write_text(OK + BAD.split(chr(10), 1)[1],
                                       encoding="utf-8")
        dec, chi, d = now()
        check(len(d.uncommitted) == 1,
              f"UNCOMMITTED direction: {d.uncommitted}")
        check(not d.masked, f"an invented row was also MASKED: {d.masked}")
        # The committed offender in the OTHER file is untouched and still
        # adjudicated — the bucket `split_rows` gets wrong.
        check(len(d.head) == 1 and d.head[0][1] == "committed.py",
              f"the pins' view lost the committed row: {d.head}")

        # ── MASKED: the worktree HIDES a committed offender ─────────────────
        git(repo, "checkout", "--", "clean.py")
        (repo / "committed.py").write_text(OK, encoding="utf-8")
        dec, chi, d = now()
        check(not dec and not chi,
              f"the fixture did not hide the offender: {dec} {chi}")
        check(len(d.masked) == 1 and d.masked[0][1] == "committed.py",
              f"MASKED direction: {d.masked}")
        check(len(d.head) == 1,
              f"a MASKED row is missing from the pins' view: {d.head}")

        # ── a STAGED-only file has no HEAD blob ─────────────────────────────
        git(repo, "checkout", "--", "committed.py")
        (repo / "staged.py").write_text(BAD, encoding="utf-8")
        git(repo, "add", "staged.py")
        dec, chi, d = now()
        check([r[1] for r in d.uncommitted] == ["staged.py"],
              f"a staged-only file's row was not UNCOMMITTED: {d.uncommitted}")
        check(all(r[1] != "staged.py" for r in d.masked),
              f"a file absent from HEAD produced a MASKED row: {d.masked}")

        # ── an UNPARSED file at HEAD is neither offender nor clean ──────────
        # ⛔ Counting it as an offender INVENTS a MASKED row — a hard red
        # nobody can repair; counting it as clean hides exposure. It has its
        # own bucket one level up and must reach neither ceiling.
        (repo / "broken.py").write_text("def f(\n", encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "broken")
        (repo / "broken.py").write_text(OK, encoding="utf-8")
        dec, chi, d = now()
        check(all(r[1] != "broken.py" for r in d.masked),
              f"an UNPARSED HEAD blob produced a MASKED row: {d.masked}")

        # ── the KEY must carry every field a CEILING reads ──────────────────
        # ⛔ `head_delta` puts a key-matched row in `committed` carrying the
        # WORKTREE's object, so a field the key omits is one where the worktree
        # silently overrides HEAD. This sweep has TWO ceilings partitioned by
        # KIND, so kind is identity, not an attribute. Measured on a peer's
        # toolchain_override, where omitting the analogous field made a
        # committed DRIFT count as zero.
        #
        # One call that is BOTH classes at HEAD, and only CHILD in the worktree.
        BOTH = ("import subprocess, sys" + chr(10)
                + "subprocess.run([sys.executable], text=True)" + chr(10))
        CHILD_ONLY = ("import subprocess, sys" + chr(10)
                      + "subprocess.run([sys.executable], encoding=" + chr(34)
                      + "utf-8" + chr(34) + ")" + chr(10))
        git(repo, "checkout", "--", ".")
        (repo / "both.py").write_text(BOTH, encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "both")
        (repo / "both.py").write_text(CHILD_ONLY, encoding="utf-8")
        dec, chi, d = now()
        kinds_masked = {r[2] for r in d.masked if r[1] == "both.py"}
        check("DECODE" in kinds_masked,
              f"the DECODE row HEAD carries was ABSORBED by the worktree's "
              f"CHILD row — kind is not in the key: masked={d.masked}")
        check(not any(r[1] == "both.py" and r[2] == "DECODE"
                      for r in d.head if r in d.committed),
              "a vanished DECODE row was reported as committed")

        # ── the WALK guard ──────────────────────────────────────────────────
        # `fnmatch`'s `*` crosses `/`, so the scope glob admits a path the
        # walk excludes; a row invented there reads as MASKED.
        check(head_offenders(set())("committed.py", BAD) == [],
              "a path outside the sweep's own walk produced a row")

    return fails


def selftest() -> list[str]:
    """Pin that both verdicts FIRE through the gate's own `scan()`, that the
    controls do NOT, and that the walk's boundaries hold. Each fails silently
    otherwise, and a silent failure reports a clean workspace.

    Measured through `scan()` and not `scan_text()` on purpose: `scan_text` is
    already self-tested inside the gate, and what this sweep adds is the WALK
    around it — the half that can go blind per-repo.
    """
    fails: list[str] = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    def measure(files: dict[str, str], gitignore: str = "", add: bool = True):
        """(decode_n, child_n, py_files, calls, unparsed) over a real git repo.

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
            dec, chi, nf, nc, unp = seg.scan(repo)
            return (sum(len(v) for v in dec.values()),
                    sum(len(v) for v in chi.values()), nf, nc, unp)

    # 1. DECODE fires, through the walk, with the call counted.
    d, c, nf, nc, unp = measure(
        {"a.py": "import subprocess\nsubprocess.run(cmd, text=True)\n"})
    if (d, c, nf, nc, unp) != (1, 0, 1, 1, []):
        fails.append(f"planted DECODE: got decode={d} child={c} files={nf} "
                     f"calls={nc} unparsed={unp}, expected 1/0/1/1/[]")

    # 2. CONTROL: the repaired form must produce NO finding, or the sweep reds
    #    on every correct repair and gets switched off.
    d, c, nf, nc, _ = measure(
        {"a.py": 'import subprocess\nsubprocess.run(cmd, text=True,\n'
                 '               encoding="utf-8", errors="replace")\n'})
    if (d, c, nf, nc) != (0, 0, 1, 1):
        fails.append(f"control: a repaired call produced decode={d} child={c}")

    # 3. CHILD-ENCODER fires, and does not leak into DECODE.
    d, c, _, _, _ = measure(
        {"a.py": 'import subprocess, sys\nsubprocess.run([sys.executable, s],\n'
                 '               encoding="utf-8")\n'})
    if (d, c) != (0, 1):
        fails.append(f"planted CHILD-ENCODER: decode={d} child={c}, expected 0/1")

    # 4. UNPARSED surfaces rather than reading as clean — the trap audit's
    #    lesson, and the one direction where a blind instrument prints a green.
    d, c, nf, nc, unp = measure({"a.py": "def f(:\n"})
    if len(unp) != 1 or (d, c, nc) != (0, 0, 0):
        fails.append(f"an unparseable file did not surface as UNPARSED: {unp}")

    # 5. walk boundaries, both directions in ONE measurement. TRACKED-only
    #    (Issue 777): an UNTRACKED file is not the repo's population, and a
    #    GITIGNORED one certainly is not. Two tracked files, not one — a count
    #    of 1 cannot distinguish "the untracked file was excluded" from "the
    #    walk collapsed to a single file".
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        subprocess.run(["git", "-C", str(repo), "init", "-q"],
                       capture_output=True, check=True)
        (repo / ".gitignore").write_text("ignored/\n", encoding="utf-8")
        (repo / "a.py").write_text("import subprocess\n", encoding="utf-8")
        (repo / "b.py").write_text("import subprocess\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "a.py", "b.py",
                        ".gitignore"], capture_output=True, check=True)
        (repo / "untracked.py").write_text(
            "import subprocess\nsubprocess.run(x, text=True)\n", encoding="utf-8")
        (repo / "ignored").mkdir()
        (repo / "ignored" / "v.py").write_text(
            "import subprocess\nsubprocess.run(x, text=True)\n", encoding="utf-8")
        dec, _chi, nf, _nc, _unp = seg.scan(repo)
        if nf != 2:
            fails.append(f"walk boundaries: walked {nf} .py, expected 2 (the two "
                         f"tracked yes, the untracked and gitignored ones no)")
        if dec:
            fails.append(f"walk boundaries: an untracked/gitignored file produced "
                         f"{dec} — the sweep would report findings in trees no "
                         f"repo owns")

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
        pins.write_text("# c\nrepo-a 40 30 0 0  # trailing\n\n", encoding="utf-8")
        if parse_pins(pins) != {"repo-a": dict(zip(FIELDS, (40, 30, 0, 0)))}:
            fails.append("pin parse: 5-field row not read correctly")
        pins.write_text("repo-a 1 2\n", encoding="utf-8")
        try:
            parse_pins(pins)
            fails.append("pin parse: short row accepted")
        except ValueError:
            pass
    # Issue 822: the split's arms are the ONLY execution this wiring gets —
    # this sweep reports 0 findings workspace-wide and has no --canary.
    return fails + split_arms()


def main() -> int:
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass  # not a TextIOWrapper (embedded / detached); keep old behavior

    fails = selftest()
    if fails:
        print("✗ subprocess encoding sweep SELFTEST FAILED — instrument "
              "untrustworthy:")
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
    # per-push gate owns for THIS repo. Asserted, not trusted.
    mine = pins.get(REPO_ROOT.name, {})
    for field, owned in (("min_py_files", seg.FLOOR_PY_FILES),
                         ("min_calls", seg.FLOOR_CALLS)):
        if mine.get(field) != owned:
            print(f"✗ pin drift: {PINS.name} says {field}={mine.get(field)} for "
                  f"{REPO_ROOT.name}, subprocess_encoding_gate owns "
                  f"{owned}. Same quantity, two files — change both.")
            return 1

    bad = False
    tot_files = tot_calls = tot_dec = tot_chi = tot_unp = tot_vend = 0
    n_uncommitted = n_masked = 0

    for name in names:
        repo = WORKSPACE / name
        decode, child, py_files, calls, unparsed = seg.scan(repo)

        # ── Issue 822: the DISPLAY reads the worktree, the PINS read HEAD ───
        # A ceiling is a claim about the repo, and a repo's state is its
        # commits. This workspace runs concurrent sessions against shared
        # worktrees, so a row here may sit on a line no commit contains — and
        # re-pinning from such a run bakes another session's in-flight edit
        # into a tracked file, where it reds on every other box.
        walk = {str(f.relative_to(repo)).replace(chr(92), "/")
                for f in tracked_files(repo, "*.py")[0]}
        delta = adjudicate(repo, decode, child, walk)
        n_uncommitted += len(delta.uncommitted)
        n_masked += len(delta.masked)
        head_dec = [r for r in delta.head if r[2] == "DECODE"]
        head_chi = [r for r in delta.head if r[2] == "CHILD"]
        held = {r[0] for r in delta.uncommitted}
        hidden = {r[0] for r in delta.masked}
        # The vendored count rides the per-repo line rather than vanishing
        # (Issue 738 T3): a repo that vendors python would otherwise have its
        # numbers quietly reduced with nothing saying so.
        _kept, vendored = tracked_files(repo, "*.py")
        n_dec = sum(len(v) for v in decode.values())
        n_chi = sum(len(v) for v in child.values())
        tot_files += py_files
        tot_calls += calls
        tot_dec += n_dec
        tot_chi += n_chi
        tot_unp += len(unparsed)
        tot_vend += vendored

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
            if py_files < row["min_py_files"]:
                flags.append(f"walk FLOOR breached: {py_files} tracked .py < "
                             f"{row['min_py_files']} — files were removed, or "
                             f"`git ls-files` went blind and the 0 below means "
                             f"nothing")
            if calls < row["min_calls"]:
                flags.append(f"parse FLOOR breached: {calls} subprocess call "
                             f"site(s) < {row['min_calls']} — the walk is intact "
                             f"but the AST pass found nothing")
            if len(head_dec) > row["max_decode"]:
                flags.append(f"DECODE {len(head_dec)} committed > pinned "
                             f"{row['max_decode']}")
            if len(head_chi) > row["max_child"]:
                flags.append(f"CHILD-ENCODER {len(head_chi)} committed > "
                             f"pinned {row['max_child']}")
        if unparsed:
            flags.append(f"{len(unparsed)} file(s) the parser could not read — "
                         f"UNPARSED is the instrument admitting it cannot see, "
                         f"never a pass")

        status = "✗" if flags else ("·" if (n_dec or n_chi) else "✓")
        vend = f" vendored={vendored}" if vendored else ""
        # T3: the count stays honest in BOTH directions. A bare total invites
        # the one action Issue 822 exists to prevent — typing it into the pin.
        split = ""
        if delta.uncommitted or delta.masked:
            split = (f" ({len(head_dec)}+{len(head_chi)} committed"
                     + (f", {len(delta.uncommitted)} uncommitted"
                        if delta.uncommitted else "")
                     + (f", {len(delta.masked)} MASKED" if delta.masked else "")
                     + ")")
        print(f"{status} {name:22s} py={py_files:<4d} calls={calls:<4d} "
              f"decode={n_dec} child={n_chi}{vend}{split}")

        def _tag(key, _held=held, _hidden=hidden):
            # Never hidden — hiding them is the lie Issue 797 refuses — but
            # labelled, so the reader sees which rows the pin did not read.
            if key in _held:
                return "  [UNCOMMITTED — not adjudicated]"
            if key in _hidden:
                return "  [MASKED — committed, and this worktree hides it]"
            return ""

        for key, rel, kind, r in keyed(flatten(decode, child)):
            label = "DECODE       " if kind == "DECODE" else "CHILD-ENCODER"
            print(f"      ⛔ {label} {rel}:{r}{_tag(key)}")
        # A MASKED row is in HEAD and NOT in the worktree, so the loop above
        # cannot reach it — it has no line here to hang a label on.
        for key, rel, kind, r in delta.masked:
            label = "DECODE       " if kind == "DECODE" else "CHILD-ENCODER"
            print(f"      ⛔ {label} {rel}:{r}  [MASKED — committed, and this "
                  f"worktree hides it]")
        for r in unparsed:
            print(f"      ⛔ UNPARSED      {r}")
        for f in flags:
            bad = True
            print(f"      ✗ {f}")

    # The population axis, shared (Issues 793 + 782): UNREGISTERED reds in every
    # posture, UNSEEN reds without the marker, and the same set DEFERS loudly
    # with it. Never auto-detected — a genuine removal whose row update was
    # forgotten is set-identical to a partial clone from the walk alone.
    pop_lines, deferred, pop_fail = population_verdict(pins, names)

    # Issue 797 — the worktree is not the repo. This run reads files that
    # concurrent sessions are editing, so a finding may sit on a line no
    # commit contains. ADVISORY, never a failure: a sweep that hard-reds on
    # an ordinary dirty worktree is a sweep nobody runs. It rides the FINAL
    # line in BOTH directions (the `deferred` precedent) and is SILENT
    # unless the dirty set meets this sweep's own population — the call sites.
    deferred.extend(sweep_advisory(
        names, ("*.py",), root=WORKSPACE,
        uncommitted_rows=n_uncommitted, masked_rows=n_masked))
    for _line in pop_lines:
        print(_line)
    if pop_fail:
        bad = True

    print(f"\n{len(names)} contract repo(s) · {tot_files} tracked .py "
          f"({tot_vend} vendored, excluded) · {tot_calls} subprocess call site(s) "
          f"· {tot_dec} DECODE · {tot_chi} CHILD-ENCODER · {tot_unp} UNPARSED")
    # State the scope where it is READ, not only in the docstring.
    print("  scope: the PARENT's read (text=True / universal_newlines=True with "
          "no encoding=) and the CHILD's write (a sys.executable spawn with no "
          "PYTHONIOENCODING). PYTHONIOENCODING alone fixes neither — it pins "
          "the child's encoder and makes the parent's decode MORE likely to "
          "raise.")

    if bad:
        print("✗ subprocess encoding sweep FAILED — see the ✗ rows above")
        for _d in deferred:
            print(f"  ⚠ {_d}")
        print('    The repair is two tokens: encoding="utf-8", errors="replace" '
              'on the parent, env={**os.environ, "PYTHONIOENCODING": "utf-8"} '
              "on a python child. Do NOT raise a ceiling — see Issue 778.")
        return 1
    _line = "✓ subprocess encoding sweep PASSED — every repo within its pins"
    if deferred:
        _line += "; DEFERRED: " + "; ".join(deferred)
    print(_line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
