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
from worktree_state import sweep_advisory  # noqa: E402

REPO_ROOT = HERE.parent
WORKSPACE = REPO_ROOT.parent
PINS = HERE / "subprocess_encoding_drift_floors.txt"

FIELDS = ("min_py_files", "min_calls", "max_decode", "max_child")


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
        pins.write_text("# c\nrepo-a 40 30 0 0  # trailing\n\n")
        if parse_pins(pins) != {"repo-a": dict(zip(FIELDS, (40, 30, 0, 0)))}:
            fails.append("pin parse: 5-field row not read correctly")
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

    for name in names:
        repo = WORKSPACE / name
        decode, child, py_files, calls, unparsed = seg.scan(repo)
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
            if n_dec > row["max_decode"]:
                flags.append(f"DECODE {n_dec} > pinned {row['max_decode']}")
            if n_chi > row["max_child"]:
                flags.append(f"CHILD-ENCODER {n_chi} > pinned {row['max_child']}")
        if unparsed:
            flags.append(f"{len(unparsed)} file(s) the parser could not read — "
                         f"UNPARSED is the instrument admitting it cannot see, "
                         f"never a pass")

        status = "✗" if flags else ("·" if (n_dec or n_chi) else "✓")
        vend = f" vendored={vendored}" if vendored else ""
        print(f"{status} {name:22s} py={py_files:<4d} calls={calls:<4d} "
              f"decode={n_dec} child={n_chi}{vend}")
        for rel in sorted(decode):
            for r in decode[rel]:
                print(f"      ⛔ DECODE        {rel}:{r}")
        for rel in sorted(child):
            for r in child[rel]:
                print(f"      ⛔ CHILD-ENCODER {rel}:{r}")
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
        names, ("*.py",), root=WORKSPACE))
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
