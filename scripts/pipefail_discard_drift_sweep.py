#!/usr/bin/env python3
"""Run the pipefail measurement-discard verdict over EVERY contract repo.

`scripts/pipefail_discard_audit.py` is the classifier/report half; this file
is the verdict half — per-repo floors + expected rows pinned by MEMBERSHIP,
the same two-half shape as the other eleven drift sweeps in `scripts/`.
The asymmetry this closes is the standard one: a report that only ever runs
on the repo that filed the class never learns what its neighbours carry
(Issues 782/783: the eighth and ninth instances pointed outward found real
rows; this one found 53, three of them in CI gate scripts that could die
before printing their own failure).

Why BOTH floors
---------------
`max_findings = 0`-style ceilings are green over whatever the walk can SEE,
and the walk shells out to `git ls-files` — a regression takes the
population to 0 and every ceiling passes, indistinguishable from a clean
repo. So each repo pins `min_sh_files` (moves when the WALK goes blind) and
`min_sites` (moves when the CLASSIFIER goes blind on an unchanged tree),
both at ~60% of the measured value: slack against churn, tight against
blindness (the trap_sentinel_drift_floors convention).

Membership, deliberately
------------------------
Findings are pinned by membership in `pipefail_discard_expected.txt`
(line-free `repo:rel:digest#n` keys, one REQUIRED reason per row, reds in
BOTH directions — a new unpinned finding reds, and a pinned row that no
longer fires reds, because the row and the repair belong in the same
commit). A count cannot do this: 53 findings pinned as deliberate tripwires
plus live kills would be green on any swap that kept the total.

The `#=` comment on each row is the source line the digest was taken from,
VERIFIED on every run — a comment nothing can red is a comment that drifts
into a lie (the arm_reach_survivors_expected precedent).

Why this is NOT in scripts/docs_gate.sh's CHECKS
------------------------------------------------
Identical to the other sweeps: CI has one checkout, the siblings are
private and simply absent, so it would either red on every run or derive an
EMPTY population and print a confident green over zero repos.

    pipefail_discard_audit.py        classifier/report — workstation, exit 0
    this file                        verdict — workstation, on demand, all repos

Exit 0 clean, 1 on drift above the pins, **2 if the instrument itself is
untrustworthy** — an unreliable instrument is not the same finding as drift.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# DRY: the classifier is the report's, so the sweep can never disagree with
# it about what kills (Issue 755: a second copy of a rule this subtle is a
# second thing to get wrong).
import pipefail_discard_audit as pda  # noqa: E402
from skill_repo_set_gate import derive_repos  # noqa: E402
from sweep_population import population_verdict, pin_row_exempt  # noqa: E402
from worktree_state import (head_delta, ordinal_keys,  # noqa: E402
                            sweep_advisory)
from tracked_walk import tracked_files  # noqa: E402

REPO_ROOT = HERE.parent
WORKSPACE = REPO_ROOT.parent
PINS = HERE / "pipefail_discard_drift_floors.txt"
EXPECTED = HERE / "pipefail_discard_expected.txt"
# the fix commit for the founding specimen (riir-ai perf_rematch.sh, the
# `|| true` at the names= substitution tail, 2026-09-07)
PROVE_REPO = "riir-ai"
PROVE_REL = "scripts/perf_rematch.sh"

FIELDS = ("min_sh_files", "min_sites", "max_findings", "max_unparsed")
KEY_RE = re.compile(r"^(\S+):(\S+):([0-9a-f]{8})#(\d+)$")

# ONE list, read by the worktree advisory AND by the HEAD re-classification.
# Issue 822 T5a measured the cost of the second copy: `instrument_reachability`
# carried a hand-typed glob list beside its advisory naming `.yml` and not
# `.yaml`, so a dirty root sat silently outside its own declared population.
# ⚠ The trailing comma is load-bearing — `("*.sh")` is a STRING, and iterating
# it yields characters, so `fnmatch(rel, "*")` matches every file in the repo.
# It was written that way here until Issue 822 T5e; `_coerce` caught it, which
# is why the advisory was right anyway, and why the helper coerces at all.
SCOPE = ("*.sh",)


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


def parse_expected(path: Path) -> dict[str, tuple[str, str]]:
    """{key: (reason, source-line)} — a reasonless row is REFUSED: a row
    whose reason is 'not written yet' is a backlog wearing a pin."""
    rows: dict[str, tuple[str, str]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^(\S+)\s+(.+?)\s*#\=\s?(.*)$", line)
        if not m:
            raise ValueError(f"malformed expected row: {raw!r}")
        key, reason, source = m.group(1), m.group(2).strip(), m.group(3).strip()
        if not reason:
            raise ValueError(f"REASONLESS expected row (refused): {raw!r}")
        if not KEY_RE.match(key):
            raise ValueError(f"malformed expected key: {key!r}")
        if key in rows:
            raise ValueError(f"duplicate expected key: {key!r}")
        rows[key] = (reason, source)
    return rows


def keyed_rows(name: str, findings) -> list:
    """`[(membership key, finding)]` for one repo's findings.

    ONE builder, called by the worktree pass, the HEAD pass and `measure_keys`
    — the ordinal has to be assigned from the same base on both sides of an
    Issue 822 comparison or every row looks moved. It can be assigned PER FILE
    (which is how `head_delta`'s rescan calls it) precisely because `rel` is
    part of the address, so a file's ordinals never depend on another file's.

    The disambiguation itself is `worktree_state.ordinal_keys` (T5d), not a
    third transcription of it; the ADDRESS stays this sweep's own, because the
    membership pin file is keyed on `repo:rel:digest#n`.
    """
    ordered = sorted(findings, key=lambda f: (f["rel"], f["line"]))
    return [(pda.finding_key(name, f["rel"], f["text"], key[-1] + 1), f)
            for key, f in ordinal_keys(
                ordered,
                lambda f: (name, f["rel"], pda.make_digest(f["text"])))]


def head_findings(name: str, walk: set[str]):
    """`head_delta`'s per-file reclassifier for this sweep's two verdicts.

    Per-file row independence holds by construction: `audit_repo` calls
    `scan_text` on ONE file's bytes and every verdict this sweep reports —
    GUARDED by an earlier `if grep -q` on the same pattern, LOCAL-MASKED,
    INERT — is decided inside that one scan. So the cheap shortcut is sound
    and costs |dirty n *.sh| `git show` calls, zero on an ordinary run.

    `walk` is the sweep's OWN tracked population, passed in rather than
    re-derived: `fnmatch`'s `*` crosses `/`, so the scope glob admits paths
    `tracked_files` excludes, and a row invented there reads as MASKED — a
    hard red nobody can repair.
    """

    def rescan(rel: str, src: str | None) -> list:
        # None = absent from HEAD (staged but never committed). Nothing
        # committed to classify, so the worktree's row is UNCOMMITTED.
        if src is None or rel not in walk:
            return []
        sc = pda.scan_text(src)
        if sc.unparsed:
            # `audit_repo`'s own answer for an unparsed file: its sites are
            # not trustworthy evidence. Never folded into either direction —
            # counting them clean hides exposure, counting them findings
            # INVENTS a MASKED row nobody can repair.
            return []
        return keyed_rows(name, [{"rel": rel, "line": s.line, "sub": s.sub,
                                  "text": s.text} for s in sc.findings])

    return rescan


def adjudicate(repo: Path, res):
    """One repo's findings split COMMITTED / UNCOMMITTED / MASKED (Issue 822).

    A named seam rather than five lines inline: this is the verdict
    arithmetic, and `arm_reach_audit`'s standing finding in this repo is that
    the classifier is well armed and the verdict is not.

    ⛔ BOTH of this sweep's verdicts read the result, not just the count. The
    membership wall is the one that would otherwise fail in the DANGEROUS
    direction: an uncommitted row demands a pin nobody can write, and a MASKED
    row — pinned, committed, hidden by somebody's worktree — reads as "pinned
    row no longer fires", whose documented remedy is to DELETE the row. That
    drops the only pointer to a live defect.
    """
    kept, _vendored = tracked_files(repo, "*.sh")
    walk = {p.relative_to(repo).as_posix() for p in kept}
    return head_delta(
        repo, SCOPE, keyed_rows(res.name, res.findings),
        lambda r: r[1]["rel"], lambda r: r[0],
        head_findings(res.name, walk))


def measure_keys(deltas) -> dict:
    """{key: finding} over what a COMMIT of these repos would produce.

    Issue 822 — `.head` is `committed + masked`, never `committed`: a MASKED
    row is by definition one the worktree does not show, and it is exactly the
    row the membership wall must still demand a pin for.
    """
    return {key: f for delta in deltas for key, f in delta.head}


def _temp_repo(files: dict[str, str]):
    """A real git repo (tracked_files shells out to `git ls-files`; a bare
    temp dir would exercise the FALLBACK and certify the wrong branch)."""
    tmp = tempfile.TemporaryDirectory()
    repo = Path(tmp.name)
    subprocess.run(["git", "-C", str(repo), "init", "-q"],
                   capture_output=True, check=True)
    for rel, text in files.items():
        f = repo / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"],
                   capture_output=True, check=True)
    return tmp, repo


def selftest() -> list[str]:
    """Both verdicts FIRE through the real walk, the controls do NOT, and
    the parsers refuse what they must. Silent failure here reads as a clean
    workspace, so every arm is loud."""
    fails: list[str] = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    kill = ('set -euo pipefail\n'
            'names="$(grep -E \'pid=\' "$cl" | head -1 | paste -sd \';\' -)"\n')
    guarded = ('set -euo pipefail\n'
               'names="$(grep -E \'pid=\' "$cl" | head -1 '
               "| paste -sd ';' - || true)\"\n")

    # 1. the founding shape fires, through the walk, with the site counted
    tmp, repo = _temp_repo({"scripts/a.sh": kill})
    with tmp:
        res = pda.audit_repo(repo)
        check((res.files, len(res.findings)) == (1, 1),
              f"planted kill: files={res.files} findings={len(res.findings)}, "
              f"expected 1/1")
        check(res.findings[0]["sub"] == pda.PIPEFAIL_KILL,
              f"planted kill classified {res.findings[0]['sub']}")

    # 2. CONTROL: the repaired form produces NO finding — or the sweep reds
    #    on every correct repair and gets switched off
    tmp, repo = _temp_repo({"scripts/a.sh": guarded})
    with tmp:
        res = pda.audit_repo(repo)
        check((len(res.findings), res.guarded) == (0, 1),
              f"control: repaired shape gave findings={len(res.findings)} "
              f"guarded={res.guarded}")

    # 3. walk boundaries: an UNTRACKED script is nobody's population
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        subprocess.run(["git", "-C", str(repo), "init", "-q"],
                       capture_output=True, check=True)
        (repo / "a.sh").write_text("v=$(ls)\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "a.sh"],
                       capture_output=True, check=True)
        (repo / "un.sh").write_text(kill, encoding="utf-8")
        files, _ = tracked_files(repo, "*.sh")
        check(len(files) == 1,
              f"walk boundaries: walked {len(files)} .sh, expected 1 — the "
              f"untracked kill script must not join the population")

    # 4. pin parser: arity ENFORCED, comments stripped
    with tempfile.TemporaryDirectory() as td:
        pins = Path(td) / "pins.txt"
        pins.write_text("# c\nr 5 42 2 0  # trailing\n\n")
        if parse_pins(pins) != {"r": dict(zip(FIELDS, (5, 42, 2, 0)))}:
            fails.append("pin parse: 5-field row not read correctly")
        pins.write_text("r 1 2\n")
        try:
            parse_pins(pins)
            fails.append("pin parse: short row accepted")
        except ValueError:
            pass

        # 5. expected parser: a reasonless row is refused, a good row reads
        with tempfile.TemporaryDirectory() as td2:
            exp = Path(td2) / "exp.txt"
            exp.write_text("r:a.sh:" + pda.make_digest(kill) + "#1   why   #= "
                           "names=\n")
            got = parse_expected(exp)
            check(list(got) == [f"r:a.sh:{pda.make_digest(kill)}#1"]
                  and got[f"r:a.sh:{pda.make_digest(kill)}#1"] == ("why",
                                                                   "names="),
                  "expected parse: well-formed row misread")
            exp.write_text("r:a.sh:" + "0" * 8 + "#1   #= x\n")
            try:
                parse_expected(exp)
                fails.append("expected parse: REASONLESS row accepted")
            except ValueError:
                pass

    # 6. digest stability: the identity is the stripped TEXT, not the line
    check(pda.make_digest(" x ") == pda.make_digest("x"),
          "digest: leading/trailing space changed the identity")

    # 7. population derivation: BOUNDARY.md + a .git DIRECTORY, both required
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

    # 8. Issue 822 — the worktree is not the repo. Both verdicts here read
    #    the result, and the MEMBERSHIP one fails in the dangerous direction:
    #    the documented remedy for "pinned row no longer fires" is to DELETE
    #    the row, which drops the only pointer to a live defect.
    fails += head_arms()
    if SCOPE != ("*.sh",):
        fails.append(f"SCOPE is {SCOPE} — the advisory and the HEAD "
                     f"re-classification read this one list, and a BARE "
                     f"STRING here is a character sequence, not one pattern")
    return fails


def head_arms() -> list[str]:
    """`adjudicate` end to end against REAL git — Issue 822.

    A mock of git would assert the mock, and every one of the three pieces
    (`head_overlay` finding the dirty file, `scan_text` re-reading HEAD's
    bytes, `delta_of`'s arithmetic) has its own way of being silently inert.
    ~0.5s, and it is the only thing in this sweep proving the pins stopped
    reading the working tree.
    """
    fails: list[str] = []
    kill = ('set -euo pipefail\n'
            'names="$(grep -E \'pid=\' "$cl" | head -1 | paste -sd \';\' -)"\n')
    guarded = ('set -euo pipefail\n'
               'names="$(grep -E \'pid=\' "$cl" | head -1 '
               "| paste -sd ';' - || true)\"\n")

    def git(root, *args):
        subprocess.run(("git", "-C", str(root)) + args,
                       capture_output=True, check=True)

    def fixture(td: str, committed: str, worktree: str) -> Path:
        repo = Path(td) / "r"
        (repo / "scripts").mkdir(parents=True)
        (repo / "scripts" / "a.sh").write_text(committed, encoding="utf-8")
        git(repo.parent, "init", "-q", "r")
        git(repo, "config", "user.email", "arm@example.invalid")
        git(repo, "config", "user.name", "arm")
        git(repo, "add", "-A")
        git(repo, "-c", "commit.gpgsign=false", "commit", "-qm", "base")
        (repo / "scripts" / "a.sh").write_text(worktree, encoding="utf-8")
        return repo

    # a. UNCOMMITTED — the worktree kills, HEAD does not. SHOWN, never
    #    adjudicated: neither the count ceiling nor the membership wall may
    #    demand a pin for a line no commit contains.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, guarded, kill)
        res = pda.audit_repo(repo)
        if len(res.findings) != 1:
            fails.append("head arm: the worktree pass found no kill — every "
                         "comparison in this arm is vacuous")
        d = adjudicate(repo, res)
        if len(d.uncommitted) != 1:
            fails.append(f"adjudicate: a worktree-only kill is not "
                         f"UNCOMMITTED ({d}) — the pins read the tree")
        if d.head or measure_keys([d]):
            fails.append("adjudicate: an UNCOMMITTED row reached `.head`, so "
                         "the membership wall demands a pin nobody can write")

    # b. MASKED — the silent direction, and the one whose documented remedy
    #    is destructive. HEAD carries the kill; this worktree hides it.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, kill, guarded)
        res = pda.audit_repo(repo)
        if res.findings:
            fails.append("head arm: the worktree pass found a kill where the "
                         "MASKED direction needs none")
        d = adjudicate(repo, res)
        if len(d.masked) != 1:
            fails.append(f"adjudicate: a committed kill the worktree hides "
                         f"was not recovered as MASKED ({d})")
        if len(d.head) != 1 or len(measure_keys([d])) != 1:
            fails.append("adjudicate: a MASKED row is missing from `.head`, "
                         "so `pinned row no longer fires` would tell somebody "
                         "to DELETE the pin on a live defect")

    # c. A clean tree costs NOTHING — no overlay, no rescan. A helper that
    #    re-reads anyway on every run is one sweeps stop calling.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, kill, kill)
        res = pda.audit_repo(repo)
        d = adjudicate(repo, res)
        if len(d.committed) != 1 or d.uncommitted or d.masked:
            fails.append(f"adjudicate: a clean tree's rows are not all "
                         f"COMMITTED ({d})")

    # d. A file absent from HEAD yields nothing — the measured Issue 822 case
    #    was a row on a file `git log` could not see at all.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, guarded, guarded)
        (repo / "scripts" / "new.sh").write_text(kill, encoding="utf-8")
        git(repo, "add", "scripts/new.sh")
        res = pda.audit_repo(repo)
        d = adjudicate(repo, res)
        if len(d.uncommitted) != 1 or d.head:
            fails.append(f"adjudicate: a staged-but-never-committed file's "
                         f"kill was adjudicated as committed ({d})")

    # e. The key is LINE-FREE: padding above a kill must not report it as
    #    UNCOMMITTED *and* MASKED at once.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, kill, "# padding\n# padding\n" + kill)
        res = pda.audit_repo(repo)
        d = adjudicate(repo, res)
        if d.uncommitted or d.masked or len(d.committed) != 1:
            fails.append(f"row key: a line shift reported one kill as both "
                         f"UNCOMMITTED and MASKED ({d})")
    return fails


def locate_fix_sha(ai_repo: Path) -> str:
    """The newest commit in the line's own history (`git log -L`).

    NOT `git log -S 'names='` — -S counts OCCURRENCES, and adding `|| true`
    does not change the count, so -S finds the line's BIRTH commit
    (a95184e4d, 2026-09-03) whose parent predates the line entirely. -L
    walks every commit that TOUCHED the line, newest first — the fix is
    its first hit (512b74939, measured).
    """
    shown = subprocess.run(
        ["git", "-C", str(ai_repo), "show", f"HEAD:{PROVE_REL}"],
        capture_output=True, check=True).stdout.decode("utf-8", "replace")
    idx = next(i for i, l in enumerate(shown.split("\n"), 1)
               if 'names="$(grep' in l)
    out = subprocess.run(
        ["git", "-C", str(ai_repo), "log", "--format=%h",
         f"-L{idx},{idx}:{PROVE_REL}"],
        capture_output=True, check=True).stdout.decode("utf-8", "replace")
    m = re.search(r"^([0-9a-f]{7,40})\s", out, re.M)
    if not m:
        raise RuntimeError(f"no commit found touching {PROVE_REL}:{idx}")
    return m.group(1)


def prove_fires(sha: str | None) -> int:
    """The ceiling nobody has watched fail certifies nothing: extract the
    founding specimen at fix~1 (unguarded — must FIND) and at fix (guarded
    — must be CLEAN), from git archive of the real history."""
    ai = WORKSPACE / PROVE_REPO
    if not (ai / ".git").exists():
        print(f"  ⛔ {PROVE_REPO} not on this box — --prove-fires cannot run")
        return 2
    if sha is None:
        sha = locate_fix_sha(ai)
        print(f"  located the fix commit by -L line history: {sha}")
    rc = 0
    with tempfile.TemporaryDirectory() as td:
        for rev, want in ((f"{sha}~1", True), (sha, False)):
            out = Path(td) / rev.replace("~", "_")
            out.mkdir(parents=True)
            tar = out.with_suffix(".tar")
            r = subprocess.run(
                ["git", "-C", str(ai), "archive", "--format=tar", "-o",
                 str(tar), rev, PROVE_REL], capture_output=True)
            if r.returncode != 0:
                print(f"  ⛔ git archive {rev} failed: "
                      f"{r.stderr.decode('utf-8', 'replace').strip()}")
                return 2
            subprocess.run(["tar", "-xf", str(tar), "-C", str(out)],
                           capture_output=True, check=True)
            src = out / PROVE_REL
            sc = pda.scan_text(src.read_text(encoding="utf-8",
                                             errors="replace"))
            n = len(sc.findings)
            ok = (n >= 1) if want else (n == 0)
            rc = rc or (0 if ok else 2)
            print(f"  {'✓' if ok else '✗'} {rev}: {n} finding(s), "
                  f"want {'>=1' if want else '0'} — "
                  f"sites={len(sc.sites)} guarded={sc.guarded}")
    if rc:
        print("  ⛔ --prove-fires did not reproduce the known answer")
    return rc


def main() -> int:
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass  # not a TextIOWrapper (embedded / detached); keep old behavior

    ap = argparse.ArgumentParser()
    ap.add_argument("--prove-fires", nargs="?", const="auto", default=None,
                    metavar="SHA",
                    help="known-answer check against the perf_rematch fix "
                         "(default SHA: located via -L line history)")
    args = ap.parse_args()

    if args.prove_fires is not None:
        print("pipefail measurement-discard sweep — --prove-fires\n")
        fails = selftest()
        if fails:
            for f in fails:
                print(f"  ✗ {f}")
            print("✗ SELFTEST FAILED — instrument untrustworthy")
            return 2
        return prove_fires(None if args.prove_fires == "auto"
                           else args.prove_fires)

    fails = selftest()
    if fails:
        print("✗ pipefail discard sweep SELFTEST FAILED — instrument "
              "untrustworthy:")
        for f in fails:
            print(f"    {f}")
        return 2

    if not PINS.is_file() or not EXPECTED.is_file():
        print(f"✗ pins/expected file missing: {PINS} / {EXPECTED}")
        return 2
    try:
        pins = parse_pins(PINS)
        expected = parse_expected(EXPECTED)
    except ValueError as e:
        print(f"✗ pin file unreadable: {e}")
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
    deltas = []
    tot = {"sh": 0, "sites": 0, "find": 0, "unp": 0}
    n_uncommitted = n_masked = 0
    for name in names:
        repo = WORKSPACE / name
        res = pda.audit_repo(repo)
        # Issue 822 — the DISPLAY reads the worktree (it is what the files say
        # today, and hiding that would be its own lie); the PINS read `.head`,
        # which is the only thing a commit of this checkout would reproduce.
        delta = adjudicate(repo, res)
        deltas.append(delta)
        n_uncommitted += len(delta.uncommitted)
        n_masked += len(delta.masked)
        held = {k for k, _f in delta.uncommitted}
        n_sites = (res.guarded + res.cond + res.inert + res.clean
                   + len(res.findings) + len(res.local))
        tot["sh"] += res.files
        tot["sites"] += n_sites
        tot["find"] += len(res.findings)
        tot["unp"] += len(res.unparsed)

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
            if res.files < row["min_sh_files"]:
                flags.append(f"walk FLOOR breached: {res.files} tracked .sh < "
                             f"{row['min_sh_files']} — files were removed, or "
                             f"`git ls-files` went blind and the zeros below "
                             f"mean nothing")
            if n_sites < row["min_sites"]:
                flags.append(f"classifier FLOOR breached: {n_sites} site(s) < "
                             f"{row['min_sites']} — the walk is intact but "
                             f"the classifier found nothing")
            if len(delta.head) > row["max_findings"]:
                flags.append(f"findings {len(delta.head)} committed > pinned "
                             f"{row['max_findings']}")
            # UNPARSED stays on the WORKTREE, deliberately, with the two
            # floors above: it is the instrument admitting it cannot read the
            # tree it just read, which is a property of THIS checkout and not
            # of any commit.
            if len(res.unparsed) > row["max_unparsed"]:
                flags.append(f"UNPARSED {len(res.unparsed)} > pinned "
                             f"{row['max_unparsed']} — the instrument "
                             f"admitting it cannot read, never a pass")

        status = "✗" if flags else ("·" if res.findings else "✓")
        split = ""
        if held or delta.masked:
            split = (f" [{len(delta.committed)} committed"
                     + (f", {len(held)} uncommitted" if held else "")
                     + (f", {len(delta.masked)} MASKED" if delta.masked else "")
                     + "]")
        print(f"{status} {name:22s} sh={res.files:<3d} sites={n_sites:<4d} "
              f"findings={len(res.findings)} guarded={res.guarded} "
              f"local={len(res.local)} unparsed={len(res.unparsed)}{split}")
        for key, f in keyed_rows(res.name, res.findings):
            print(f"      ⛔ {f['sub']:14s} {f['rel']}:{f['line']}"
                  + (" [UNCOMMITTED — not adjudicated]" if key in held else ""))
        # A MASKED row is NOT in the worktree list — that is what MASKED means
        # — so it is printed from the HEAD side or it is printed nowhere, and
        # the membership wall then demands a pin for a row nobody can see.
        for _key, f in delta.masked:
            print(f"      ⛔ {f['sub']:14s} {f['rel']}:{f['line']} "
                  f"[MASKED — committed, hidden by this worktree]")
        for f in flags:
            bad = True
            print(f"      ✗ {f}")

    # membership: every measured key must be pinned (with its source line
    # intact), and every pinned row on a PRESENT repo must still fire.
    seen = measure_keys(deltas)
    present = set(names)
    for key, f in sorted(seen.items()):
        if key not in expected:
            bad = True
            print(f"      ✗ UNPINNED finding {key} — pin it with a reason, or "
                  f"fix it and drop nothing")
        elif expected[key][1] != f["text"]:
            bad = True
            print(f"      ✗ STALE WARRANT {key} — the #= comment no longer "
                  f"matches the line; re-pin from the measured text")
    pinned_repos = {k.split(":", 1)[0] for k in expected}
    for key in sorted(expected):
        repo_name = key.split(":", 1)[0]
        if repo_name not in present:
            continue          # absent repos ride the population verdict below
        if key not in seen:
            bad = True
            print(f"      ✗ pinned row no longer fires: {key} — the assert "
                  f"was fixed or moved; drop the row in that same commit")
    if not expected and pinned_repos:
        bad = True            # unreachable guard for an empty pin set

    # The population axis, shared (Issues 779 + 782): UNREGISTERED reds in
    # every posture, UNSEEN reds without the marker, the same set DEFERS
    # loudly with it. Never auto-detected.
    pop_lines, deferred, pop_fail = population_verdict(pins, names)

    # Issue 797 — the worktree is not the repo. This run reads files that
    # concurrent sessions are editing, so a finding may sit on a line no
    # commit contains. ADVISORY, never a failure: a sweep that hard-reds on
    # an ordinary dirty worktree is a sweep nobody runs. It rides the FINAL
    # line in BOTH directions (the `deferred` precedent) and is SILENT
    # unless the dirty set meets this sweep's own population — the shell scripts and their pipelines.
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

    print(f"\n{len(names)} contract repo(s) · {tot['sh']} tracked .sh · "
          f"{tot['sites']} site(s) · {tot['find']} FINDING · "
          f"{tot['unp']} UNPARSED · {len(expected)} pinned row(s)")
    print("  scope: the EMPTY-CAPABLE member set is grep/egrep/fgrep/rg/"
          "ripgrep v1; other failure-prone members (test -f, curl -sf, git "
          "grep no-match via caller) are out of scope and documented in the "
          "audit's Divergences.")

    if bad:
        print("✗ pipefail discard sweep FAILED — see the ✗ rows above")
        for _d in deferred:
            print(f"  ⚠ {_d}")
        print("    The repair is one neutralizer: `|| true` at the "
              "substitution tail (or a trailing `|| cmd`). Deliberate "
              "tripwires get a pinned row with a reason, never a raised "
              "ceiling.")
        return 1
    _line = "✓ pipefail discard sweep PASSED — every repo within its pins, " \
            "every pinned row firing"
    if deferred:
        _line += "; DEFERRED: " + "; ".join(deferred)
    print(_line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
