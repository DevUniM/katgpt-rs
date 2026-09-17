#!/usr/bin/env python3
"""Run the toolchain-override verdict over EVERY contract repo, not just one.

`scripts/toolchain_override_audit.py` is a REPORT (always exit 0 on a real
scan — the platform_dead_code_audit law: the population spans repos whose
owners have not taken the intake). This file is the VERDICT half, the same
two-halves shape eleven other classes in `scripts/` carry: the audit prints,
the sweep pins. Pointing a class outward has found something every time the
family has tried it — `subprocess_encoding_drift_sweep.py`'s docstring keeps
the running table (its own first sweep: 29 DECODE + 2 CHILD-ENCODER over 5
repos) — and this class was BORN cross-repo: intake P14 (k) is a riir-ai +
riir-game-sdk finding, recorded from katgpt-rs because katgpt-rs hosts the
shared audit-instrument family.

Why BOTH floors, and why the walk floor carries the weight here
---------------------------------------------------------------
`max_drift = 0` is green over whatever the walk can SEE, and the walk shells
out to `git ls-files` — a regression takes the population to 0 and every
ceiling passes, indistinguishable from a clean repo. So the population is
pinned underneath: `min_files` (~55-60% of measured, per repo) moves when the
WALK goes blind; `max_unresolved` is a COUNTED ceiling (not a wall) because a
TOKEN value genuinely cannot be evaluated statically — pinned at its measured
value with the reason in the floors file, never folded into clean.

No membership pin here, deliberately
------------------------------------
`toolchain_override_expected.txt` starts DELIBERATELY EMPTY (header only).
The marker vocabulary is the in-source escape hatch for a deliberate
override, so no occurrence needs an expectation row: a deliberate override
becomes DELIBERATE by carrying `# toolchain-override-deliberate: <reason>`,
and DRIFT/UNRESOLVED rows that merely AWAIT their marker edits are NOT
pinned — a row reading "not written yet" is a backlog wearing a pin (the
Issue-785 rule). The 2026-09-15 landing reded on katgpt-rs (2) and riir-ai
(1) for exactly that reason: the rows were deliberate by PROSE only, and
the wall held until the in-source markers landed in the owning repos later
the same day (the two netem markers as comment blocks above their
docker-run HEAD lines — marker rule (c) — the other three directly above
their occurrences). Since then: 0 DRIFT workspace-wide, 3 DELIBERATE,
1 UNRESOLVED-MARKED, sweep green. That red was the instrument working,
not a defect.

Why this is NOT in scripts/docs_gate.sh's CHECKS
------------------------------------------------
Identical to the other sweeps: CI has one checkout, the siblings are private
and simply absent, so this would either red on every run or derive an EMPTY
population and print a confident green over zero repos. Workstation, on
demand, every contract repo.

UNPARSED files (a .py triple-quote region never closed) red their repo
UNCONDITIONALLY — never a ceiling, never folded into clean: a runaway
docstring swallowing the rest of a file is the instrument admitting it
cannot see (the trap-sentinel law), and an admission must not be
optionally green.

    toolchain_override_audit.py        report, exit 0, any repos you name
    toolchain_override_drift_sweep.py  verdict, every contract repo, pinned

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

# DRY: the classifier, the walk and the pin parser are the audit's, so the
# sweep and the report can never disagree about what an occurrence is
# (Issue 755: a second copy of a rule this subtle is a second thing to get
# wrong).
import toolchain_override_audit as toa  # noqa: E402
from skill_repo_set_gate import derive_repos  # noqa: E402
from sweep_population import population_verdict, pin_row_exempt  # noqa: E402
from worktree_state import sweep_advisory  # noqa: E402

REPO_ROOT = HERE.parent
WORKSPACE = REPO_ROOT.parent
PINS = toa.PINS

ACTION = ("DRIFT", "UNRESOLVED", "UNRESOLVED-MARKED")


def repo_flags(scan: toa.RepoScan, row: dict | None) -> list[str]:
    """The per-repo verdict policy — self-tested below, so the arithmetic is
    not welded to main() (the Issue-789 extraction lesson)."""
    if row is None:
        return ["UNPINNED — add a row (or it can never red)"]
    flags: list[str] = []
    if scan.walked < row["min_files"]:
        flags.append(
            f"walk FLOOR breached: {scan.walked} scannable file(s) < "
            f"{row['min_files']} — files were removed, or `git ls-files` "
            f"went blind and the zero below means nothing")
    n_drift = scan.count("DRIFT")
    if n_drift > row["max_drift"]:
        flags.append(
            f"DRIFT {n_drift} > pinned {row['max_drift']} — an unmarked "
            f"override building at a different toolchain than the pin "
            f"declares; add the in-source marker or fix the value, never "
            f"raise the wall")
    n_unres = scan.count("UNRESOLVED")
    if n_unres > row["max_unresolved"]:
        flags.append(
            f"UNRESOLVED {n_unres} > pinned {row['max_unresolved']} — a "
            f"TOKEN override the classifier cannot evaluate")
    if scan.unparsed:
        flags.append(
            f"{len(scan.unparsed)} file(s) the scanner could not fully read "
            f"({', '.join(scan.unparsed)}) — UNPARSED is the instrument "
            f"admitting it cannot see, never a pass")
    return flags


def parse_pins(path: Path) -> dict:
    return toa.parse_pins(path)          # one parser, two consumers


def _plant(value: str, marked: bool = False) -> str:
    """A planted occurrence line, token built at RUNTIME so this file's own
    source carries no occurrence and the katgpt-rs self-scan stays clean."""
    m = f"# {toa.MARKER}: the image bakes this toolchain\n" if marked else ""
    return m + f"docker run -e {toa.TRIGGER}={value} \\\n    --rm\n"


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args],
                   check=True, capture_output=True)


def _measure(files: dict[str, str], with_pin: bool = True) -> toa.RepoScan:
    """`toa.scan_repo` over a REAL git repo. `tracked_files` shells out to
    `git ls-files` and falls back to an rglob walk when that set is EMPTY, so
    a temp dir with nothing staged would exercise the FALLBACK and certify
    the branch these arms are not aimed at (the Issue-775 vendor arm's exact
    failure — one exclusion, two code paths)."""
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        _git(repo, "init", "-q")
        for rel, text in files.items():
            f = repo / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(text, encoding="utf-8")
        if with_pin:
            (repo / "rust-toolchain.toml").write_text(toa.PIN_TOML,
                                                      encoding="utf-8")
        (repo / "Cargo.toml").write_text(toa.CARGO_TOML, encoding="utf-8")
        _git(repo, "add", "-A")
        return toa.scan_repo(repo, "t")


def selftest() -> list[str]:
    """Pin that DRIFT fires through the TRACKED walk, that the marker repair
    flips it, that the verdict arithmetic moves in both directions, and that
    the population/pin plumbing holds. Each arm fails silently otherwise, and
    a silent failure reports a clean workspace."""
    fails: list[str] = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    # 1. DRIFT fires through the tracked walk — the P14 specimen shape.
    res = _measure({"a.sh": _plant("1.95.0")})
    if (res.walked, res.count("DRIFT"), res.count("DELIBERATE")) != (3, 1, 0):
        fails.append(f"planted DRIFT: walked={res.walked} "
                     f"drift={res.count('DRIFT')} delib={res.count('DELIBERATE')}"
                     f", expected 3/1/0")

    # 2. CONTROL: the marker repair must flip it, or the sweep reds on every
    #    correct repair and gets switched off.
    res = _measure({"a.sh": _plant("1.95.0", marked=True)})
    if (res.count("DRIFT"), res.count("DELIBERATE")) != (0, 1):
        fails.append(f"control: a marked override produced "
                     f"drift={res.count('DRIFT')} "
                     f"delib={res.count('DELIBERATE')}, expected 0/1")

    # 3. MATCH is clean and DRIFT is not, same walk: the value side moves.
    res = _measure({"a.sh": _plant("1.98.1")})
    if (res.count("MATCH"), res.count("DRIFT")) != (1, 0):
        fails.append(f"planted MATCH: match={res.count('MATCH')} "
                     f"drift={res.count('DRIFT')}, expected 1/0")

    # 4. UNPINNED-REPO: Cargo.toml without a pin file is the INFO row, and a
    #    literal override there is NO-PIN-OVERRIDE (never DRIFT).
    res = _measure({"a.sh": _plant("stable")}, with_pin=False)
    if not res.unpinned_repo or res.count("NO-PIN-OVERRIDE") != 1:
        fails.append(f"no-pin arm: unpinned={res.unpinned_repo} "
                     f"no-pin={res.count('NO-PIN-OVERRIDE')}, expected "
                     f"True/1")

    # 5. verdict arithmetic, both directions: the wall, the floor, the
    #    unpinned row, and a clean repo producing NO flag.
    clean = toa.RepoScan("t", Path("."), "1.98.1", True, 3, 0, [], False)
    if repo_flags(clean, {"min_files": 2, "max_drift": 0,
                          "max_unresolved": 0}) != []:
        fails.append("repo_flags: a clean repo above its floor was flagged")
    drifting = toa.RepoScan("t", Path("."), "1.98.1", True, 3, 0,
                            [toa.Occ("a.sh", 1, "1.95.0", "DRIFT", "assign",
                                     "x")], False)
    flags = repo_flags(drifting, {"min_files": 5, "max_drift": 0,
                                  "max_unresolved": 0})
    if len(flags) != 2 or not any("walk FLOOR" in f for f in flags) \
            or not any("DRIFT 1" in f for f in flags):
        fails.append(f"repo_flags: a below-floor drift repo produced {flags}")
    if repo_flags(drifting, None)[0][:9] != "UNPINNED ":
        fails.append("repo_flags: an unpinned repo was not flagged UNPINNED")

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

        # 7. pin parser: arity ENFORCED, comments stripped (delegated to the
        #    audit's parser — this arm pins the DELEGATION).
        pins = ws / "pins.txt"
        pins.write_text("# c\nrepo-a 40 0 0  # trailing\n\n")
        if parse_pins(pins) != {"repo-a": {"min_files": 40, "max_drift": 0,
                                           "max_unresolved": 0}}:
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
        print("✗ toolchain override sweep SELFTEST FAILED — instrument "
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
        print("✗ pins file declares NO repos — an empty expectation set is "
              "refused")
        return 2

    names = derive_repos(WORKSPACE)
    if not names:
        print(f"✗ derived population is EMPTY under {WORKSPACE} — refusing "
              f"to report a green over zero repos")
        return 2

    bad = False
    tot_walked = 0
    tot = {v: 0 for v in toa.VERDICTS}
    tot_unpinned = tot_unparsed = 0

    for name in names:
        scan = toa.scan_repo(WORKSPACE / name, name)
        # Issue 821: guard at the CALL SITE, not inside repo_flags —
        # that function is pure policy and its own arm asserts the
        # UNPINNED branch, which must keep firing for repos that do
        # owe a row. The marker is a population question, not a policy
        # one, and this sweep is the family's one non-uniform shape.
        row = pins.get(name)
        flags = ([] if (row is None and pin_row_exempt(name))
                 else repo_flags(scan, row))
        for v in toa.VERDICTS:
            tot[v] += scan.count(v)
        tot_walked += scan.walked
        tot_unpinned += 1 if scan.unpinned_repo else 0
        tot_unparsed += len(scan.unparsed)

        status = "✗" if flags else ("·" if scan.count("DRIFT")
                                    or scan.count("UNRESOLVED") else "✓")
        pin_txt = scan.pin if scan.pin else ("UNREAD" if scan.pin_file
                                             else "none")
        print(f"{status} {name:22s} pin={pin_txt:7s} files={scan.walked:<5d} "
              f"occ={len(scan.occs):<3d} (match {scan.count('MATCH')} · "
              f"delib {scan.count('DELIBERATE')} · "
              f"drift {scan.count('DRIFT')} · "
              f"unres {scan.count('UNRESOLVED')}"
              f"+{scan.count('UNRESOLVED-MARKED')} · "
              f"no-pin {scan.count('NO-PIN-OVERRIDE')})")
        for o in scan.occs:
            if o.verdict not in ACTION:
                continue
            mark = "⛔" if o.verdict == "DRIFT" else "⚠"
            print(f"      {mark} {o.verdict:<18s} {o.addr():<58s} {o.line}")
        if scan.unpinned_repo:
            print("      ℹ UNPINNED-REPO — root Cargo.toml with no "
                  "rust-toolchain.toml (intake P14 (k)(ii))")
        for rel in scan.unparsed:
            print(f"      ⚠ UNPARSED          {rel}")
        for f in flags:
            bad = True
            print(f"      ✗ {f}")

    # The population axis, shared (Issues 779 + 782): UNREGISTERED reds in
    # every posture, UNSEEN reds without the marker, and the same set DEFERS
    # loudly with it. Never auto-detected — a genuine removal whose row update
    # was forgotten is set-identical to a partial clone from the walk alone.
    pop_lines, deferred, pop_fail = population_verdict(pins, names)

    # Issue 797 — the worktree is not the repo. This run reads files that
    # concurrent sessions are editing, so a finding may sit on a line no
    # commit contains. ADVISORY, never a failure: a sweep that hard-reds on
    # an ordinary dirty worktree is a sweep nobody runs. It rides the FINAL
    # line in BOTH directions (the `deferred` precedent) and is SILENT
    # unless the dirty set meets this sweep's own population — every scannable file plus the root toolchain pin they are read against.
    deferred.extend(sweep_advisory(
        names, ("*.sh", "*.yml", "*.yaml", "*.toml", "*.py", "Dockerfile*"), root=WORKSPACE))
    for _line in pop_lines:
        print(_line)
    if pop_fail:
        bad = True

    print(f"\n{len(names)} contract repo(s) · {tot_walked} scannable tracked "
          f"file(s) · " + " · ".join(f"{v.lower().replace('_', '-')} {tot[v]}"
                                     for v in toa.VERDICTS)
          + f" · {tot_unpinned} UNPINNED-REPO · {tot_unparsed} UNPARSED")
    print("  scope: hardcoded toolchain overrides in tracked "
          ".sh/.yml/.yaml/.toml/.py + Dockerfile paths vs the repo ROOT pin")
    print("  repair: add `# toolchain-override-deliberate: <reason>` on the "
          "line, directly above it, or above the head of the "
          "continuation command carrying it — or change the value to the "
          "pin. Never raise the wall; never pin a pending marker as "
          "expected.")

    if bad:
        print("✗ toolchain override sweep FAILED — see the ✗ rows above")
        for _d in deferred:
            print(f"  ⚠ {_d}")
        return 1
    _line = "✓ toolchain override sweep PASSED — every repo within its pins"
    if deferred:
        _line += "; DEFERRED: " + "; ".join(deferred)
    print(_line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
