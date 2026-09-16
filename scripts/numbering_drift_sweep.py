#!/usr/bin/env python3
"""Run the numbering gate's checks over EVERY contract repo, not just this one.

`scripts/numbering_gate.py` is katgpt-rs-scoped by construction: its pins live
in `scripts/numbering_floors.txt`, which says "katgpt-rs scope only" in its
first line, and `docs_gate.yml` has a single checkout so it could never see a
sibling. That is the right shape for a per-push CI gate and the wrong shape for
the question "is anyone else allocating numbers twice?" — which nothing had
ever asked. Measured the first time it was asked (2026-09-05):

    32 tracked duplicate numbers across 4 sibling repos, in ALLOCATOR-SERIAL
    directories, while katgpt-rs — the one repo with a gate — had zero.
     5 `.highwater` files that are not integers at all, every one of them
       `echo -n <N> > .highwater` writing its own flag into the file, which
       DISARMS the above-highwater check for that directory (Issue 725).

This is the same shape as Issue 702 one instrument over: an auditor that
accepts a repo path, pointed at exactly one repo for months, so a sibling with
the defect is indistinguishable from a sibling nobody looked at.

Why this is NOT in scripts/docs_gate.sh's CHECKS
------------------------------------------------
Identical reasoning to scripts/docs_drift_sweep.py: CI has one checkout, the
siblings are private and simply absent, so this would either red on every run
or derive an empty population and print a confident green over zero repos.

    this script              workstation, on demand, every contract repo
    numbering_gate.py        CI, per-push (docs_gate.sh), katgpt-rs only

Vocabulary vs population
------------------------
The population (which repos exist) is DERIVED — BOUNDARY.md + a `.git` dir,
never typed, per Issue 703. The expectations are COMMITTED, in
`scripts/numbering_drift_floors.txt`, because deriving both from one walk is
what makes a cross-repo gate permanently green.

Ceilings here are a RATCHET, not a wall. 32 duplicates exist today across repos
this session does not own; resolving one is a citation-weight arbitration
(Issue 724 T2's precedent: the file with 27 inbound mentions keeps the number,
the other moves), not a rename. So each repo's ceiling is pinned at its
MEASURED count: a new collision reds immediately, and the standing backlog is
visible in the pins rather than silently tolerated. Lower a pin in the commit
that resolves a collision.

Scope, which is the load-bearing decision
-----------------------------------------
Duplicate + above-highwater checks run ONLY over allocator-serial directories
(`.plans/.issues/.research/.proposals`). `.benchmarks/` and `.docs/` are
excluded for exactly the reason numbering_floors.txt gives: there the leading
number is the OWNING plan/issue and a family per owner is the intended
convention, so "duplicate" is not decidable without knowing which convention a
given file follows — and a gate must not guess.

The MALFORMED check runs over every numbered directory including those two,
because a file that is not an integer is undecidable under no convention.

Report + gate. Exit 0 clean, 1 on drift above the pins, **2 if the instrument
itself is untrustworthy** (selftest failure) — an unreliable instrument is not
the same finding as drift and must not be reported as one.

The counter-transition classes (Issues 769 + 770, landed 2026-09-13)
---------------------------------------------------------------------
`.highwater` is not only checked for CONTENT (malformed / above-max) but for
HISTORY: `highwater_contiguity_audit.py`'s walker classifies every commit
that touched the counter against ITS OWN PARENTS' blob values (the Issue-770
repair — the 769 walker ordered all refs' hunks by commit DATE, which
manufactured phantom resets from lineage interleaving and could not see
MERGE commits at all; `git log -p` emits no merge diffs). Two classes are
verdicts here —

  resets     a commit (or merge resolution) whose counter value is below
             max(parent values). After `517→511` the re-climb re-spends
             numbers — the never-reuse rule broken by construction, the
             `.issues/121` collision class at counter granularity. Each row
             names the commit that DID it (merge commits included — a merge
             taking the lower side IS the hazard). First corrected
             adjudication (Issue 770): 27 resets workspace-wide, a mix of
             stale-lineage writebacks and merge resolutions taking the lower
             side; historical hazard absorbed by gap fast-forwards and
             push-wins renumbers; the max_dup column proves no live file
             duplicates. Pinned at the MEASURED count per repo — a NEW reset
             reds immediately, the standing history stays visible in the pins.
  unbumped   the WORKTREE counter sits below its committed history max on
             HEAD — a checkout/branch state, not a commit. REPORT-ONLY,
             deliberately unpinned (Issue 770 finding 4): the quantity is a
             function of which branch the box carries (mmorpg-editor's
             bevy worktree vs other refs' 194), so a pin would be ref-set
             dependent and red on a box that owes nothing — the class the
             AGENTS.md "a verdict the box can invalidate should refuse" law
             assigns to printing, never gating.

Both run over EVERY dir carrying a `.highwater`, not just SERIAL_DIRS — a
backward move is anomalous under number- and count-based conventions alike
(the malformed check's precedent). HEAD-reachable only, never --all: pins
must be a function of the branch the box carries, not of which refs happen
to be fetched.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numbering_gate as ng  # noqa: E402  (DRY: one scanner, two cadences)
import highwater_contiguity_audit as hca  # noqa: E402  (DRY: one transition walker, two cadences — Issue 769)
from sweep_population import population_verdict  # noqa: E402
from worktree_state import sweep_advisory  # noqa: E402
import repo_alias  # noqa: E402 — the machine-local name codec (see its docstring)

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = REPO_ROOT.parent
PINS = Path(__file__).resolve().parent / "numbering_drift_floors.txt"

# DATA, not derived from the tree — see the module docstring's scope section.
SERIAL_DIRS = (".plans", ".issues", ".research", ".proposals")
ALL_DIRS = SERIAL_DIRS + (".benchmarks", ".docs")


def contract_repos(workspace: Path) -> list[Path]:
    """Derived population: a root BOUNDARY.md AND a .git DIRECTORY.

    The `.git` test is a directory test on purpose — a worktree's `.git` is a
    FILE, and a throwaway worktree of a repo already in the walk would be
    counted twice (the trap scripts/repo_set.txt's own derivation documents).
    Names pass through the machine-local alias codec (`repo_alias.py`) so the
    returned paths carry the CONTRACT spelling every tracked pin is keyed on.
    """
    return [workspace / n for n in repo_alias.apply(
        p.name for p in workspace.iterdir()
        if (p / "BOUNDARY.md").is_file() and (p / ".git").is_dir()
    )]


def parse_rows(path: Path) -> dict[str, dict[str, int]]:
    rows: dict[str, dict[str, int]] = {}
    # pins carry UTF-8 punctuation; the locale codec (cp1252 on Windows) cannot decode it (2026-09-06 4090-box catch)
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 6:
            raise ValueError(f"malformed pin row (want 6 fields): {raw!r}")
        repo, mn, dup, above, mal, resets = parts
        rows[repo] = {
            "min_files": int(mn), "max_dup": int(dup),
            "max_above": int(above), "max_malformed": int(mal),
            "max_resets": int(resets),
        }
    return rows


def audit(repo: Path) -> dict:
    """One repo -> its five finding classes + the population that produced them."""
    tracked = ng.tracked_paths(repo, list(ALL_DIRS))
    dup, above, malformed, resets, unbumped = [], [], [], [], []
    n_serial = 0
    for dirname in ALL_DIRS:
        by_num, hw, n, hw_bad = ng.scan(repo, dirname, tracked)
        if hw_bad is not None:
            malformed.append(f"{dirname}/.highwater = {hw_bad!r}")
        if dirname not in SERIAL_DIRS:
            continue                       # family convention — not decidable
        n_serial += n
        for num, files in sorted(by_num.items()):
            if sum(1 for _, tr in files if tr) < 2:
                continue                   # untracked = a colleague's WIP
            names = " · ".join(nm for nm, _ in files)
            dup.append(f"{dirname}/{num:03d} ×{len(files)}: {names}")
        if hw is not None and by_num and max(by_num) > hw:
            above.append(f"{dirname}: max {max(by_num)} > .highwater {hw}")
    # ── the counter-transition classes (Issues 769 + 770): every dir WITH a
    # counter, judged per-commit against its own parents (merge commits
    # included). The walker is the audit's, imported not re-implemented.
    for dirname in ALL_DIRS:
        hw_f = repo / dirname / ".highwater"
        if not hw_f.is_file():
            continue
        events = hca.counter_history(repo, dirname)
        if not events:
            continue                       # never committed — nothing to walk
        w = hca.classify_history(events, repo=repo)
        for a, b, h in w["resets"]:
            resets.append(f"{dirname}: {a}->{b} @ {h[:10]} "
                          f"({hca.commit_subject(repo, h)[:48]})")
        try:
            wt = int(hw_f.read_text(encoding="utf-8").strip().split()[-1])
        except (ValueError, IndexError, OSError):
            continue                       # malformed — ng's class owns it
        if w["final"] is not None and wt < w["final"]:
            unbumped.append(f"{dirname}: worktree {wt} < history max {w['final']} "
                            f"(checkout state — REPORT only)")
    return {"dup": dup, "above": above, "malformed": malformed,
            "resets": resets, "unbumped": unbumped, "n_files": n_serial}


def selftest() -> list[str]:
    """Pin the scope split and the row parser. Both fail SILENTLY otherwise."""
    import tempfile

    fails = []
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        # a repo with one duplicate in a SERIAL dir and one in a FAMILY dir
        repo = ws / "fake-repo"
        (repo / ".plans").mkdir(parents=True)
        (repo / ".benchmarks").mkdir()
        for nm in ("001_a.md", "001_b.md"):
            (repo / ".plans" / nm).write_text("x")
            (repo / ".benchmarks" / nm).write_text("x")
        (repo / ".benchmarks" / ng.HIGHWATER).write_text("-n 7\n")
        (repo / "BOUNDARY.md").write_text("x")

        # tracked_paths() shells out to git; an untracked file is not a defect,
        # so a non-repo would report ZERO duplicates and pass vacuously. Pin
        # that the split is what decides, by driving audit() with a stub.
        real = ng.tracked_paths
        ng.tracked_paths = lambda r, d: {
            ".plans/001_a.md", ".plans/001_b.md",
            ".benchmarks/001_a.md", ".benchmarks/001_b.md",
        }
        try:
            got = audit(repo)
        finally:
            ng.tracked_paths = real

        if len(got["dup"]) != 1:
            fails.append(f"scope: expected 1 serial-dir duplicate, got {got['dup']}")
        if any(".benchmarks" in r for r in got["dup"]):
            fails.append("scope: a .benchmarks family number was reported as a duplicate")
        if len(got["malformed"]) != 1 or ".benchmarks" not in got["malformed"][0]:
            fails.append(f"scope: malformed check must cover family dirs too: {got['malformed']}")
        if got["n_files"] != 2:
            fails.append(f"population: counted {got['n_files']} serial files, expected 2")

        # the untracked split must still hold — one tracked copy is not a defect
        ng.tracked_paths = lambda r, d: {".plans/001_a.md"}
        try:
            got2 = audit(repo)
        finally:
            ng.tracked_paths = real
        if got2["dup"]:
            fails.append(f"untracked split broken: {got2['dup']}")

        # counter-transition classes (Issues 769 + 770): stub the walker's
        # history reader — a per-commit reset is reported with its commit; a
        # worktree below the history max is REPORTED (unbumped). The stub
        # spans BOTH arms: the Issue-770 review caught the landed version
        # restoring the real walker between them, so the in-flight arm read a
        # non-git tempdir and asserted nothing (mutation-proof: inverting the
        # guard passed clean).
        (repo / ".issues").mkdir(exist_ok=True)
        (repo / ".issues" / ng.HIGHWATER).write_text("3\n")
        real_hist = hca.counter_history
        real_cls = hca.classify_history
        hca.counter_history = (
            lambda r, d: [{"hash": "h2", "value": 3, "base": 4, "kind": "reset"}]
            if d == ".issues" else [])
        hca.classify_history = (
            lambda ev, repo=None, is_ancestor=None:
            {"gaps": [], "duals": 0, "final": 4,
             "resets": [(4, 3, "h2")]})
        try:
            got3 = audit(repo)
            (repo / ".issues" / ng.HIGHWATER).write_text("5\n")
            got4 = audit(repo)
        finally:
            hca.counter_history = real_hist
            hca.classify_history = real_cls
        if len(got3["resets"]) != 1 or "4->3" not in got3["resets"][0]:
            fails.append(f"reset: a per-commit reset must be reported: {got3['resets']}")
        if len(got3["unbumped"]) != 1 or "3 < history max 4" not in got3["unbumped"][0]:
            fails.append(f"unbumped: worktree 3 < history max 4 must report: {got3['unbumped']}")
        # a counter climbing in the worktree (in-flight) is NOT unbumped
        if got4["unbumped"]:
            fails.append(f"in-flight: worktree 5 > history max 4 must not report: {got4['unbumped']}")

        # population derivation: BOUNDARY.md + a .git DIR, both required
        (ws / "no-boundary").mkdir()
        (ws / "no-boundary" / ".git").mkdir()
        (ws / "worktree-shaped").mkdir()
        (ws / "worktree-shaped" / "BOUNDARY.md").write_text("x")
        (ws / "worktree-shaped" / ".git").write_text("gitdir: elsewhere")
        if [p.name for p in contract_repos(ws)] != []:
            fails.append("population: admitted a repo with no .git dir")
        (repo / ".git").mkdir()
        if [p.name for p in contract_repos(ws)] != ["fake-repo"]:
            fails.append("population: derivation is not BOUNDARY.md + .git dir")

        # row parser: 6 fields, comments stripped, arity enforced
        pins = ws / "pins.txt"
        pins.write_text("# c\nrepo-a\t10\t0\t0\t0\t0  # trailing\n\n")
        if parse_rows(pins) != {"repo-a": {"min_files": 10, "max_dup": 0,
                                           "max_above": 0, "max_malformed": 0,
                                           "max_resets": 0}}:
            fails.append("row parse: 6-field row not read correctly")
        pins.write_text("repo-a 1 2 3 4 5 6\n")
        try:
            parse_rows(pins)
            fails.append("row parse: 7-field row accepted")
        except ValueError:
            pass
    return fails


def main() -> int:
    # Prints carry glyphs the Windows locale codecs cannot encode (checked
    # 2026-09-06 on cp874: check/cross/middot/arrow FAIL, em-dash OK); keep the
    # locale encoding and degrade only the fatal chars to escapes -- the
    # staged_set_audit house pattern (utf-8 pinning would mojibake legacy consoles).
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass  # not a TextIOWrapper (embedded / detached); keep old behavior
    fails = selftest()
    if fails:
        print("✗ numbering sweep SELFTEST FAILED — instrument untrustworthy:")
        for f in fails:
            print(f"    {f}")
        return 2

    if not PINS.is_file():
        print(f"✗ pins file missing: {PINS}")
        return 2
    try:
        pins = parse_rows(PINS)
    except ValueError as e:
        print(f"✗ pins file unreadable: {e}")
        return 2
    if not pins:
        print("✗ pins file declares NO repos — an empty expectation set is refused")
        return 2

    repos = contract_repos(WORKSPACE)
    if not repos:
        print(f"✗ derived population is EMPTY under {WORKSPACE} — refusing to "
              f"report a green over zero repos")
        return 2

    seen = {p.name for p in repos}
    bad = False
    tot_dup = tot_above = tot_mal = tot_reset = tot_unb = 0

    for repo in repos:
        got = audit(repo)
        row = pins.get(repo.name)
        tot_dup += len(got["dup"])
        tot_above += len(got["above"])
        tot_mal += len(got["malformed"])
        tot_reset += len(got["resets"])
        tot_unb += len(got["unbumped"])
        flags = []
        if row is None:
            flags.append("UNPINNED — add a row (or it can never red)")
        else:
            if got["n_files"] < row["min_files"]:
                flags.append(f"population FLOOR breached: {got['n_files']} < {row['min_files']}")
            if len(got["dup"]) > row["max_dup"]:
                flags.append(f"duplicates {len(got['dup'])} > pinned {row['max_dup']}")
            if len(got["above"]) > row["max_above"]:
                flags.append(f"stale allocators {len(got['above'])} > pinned {row['max_above']}")
            if len(got["malformed"]) > row["max_malformed"]:
                flags.append(f"malformed allocators {len(got['malformed'])} > pinned {row['max_malformed']}")
            if len(got["resets"]) > row["max_resets"]:
                flags.append(f"counter resets {len(got['resets'])} > pinned {row['max_resets']} — a commit (or merge resolution) landed below its parents' max: the re-climb re-spends numbers (Issues 769+770)")
        # unbumped is REPORT-ONLY (Issue 770 finding 4): a checkout-state
        # quantity is a function of which branch the box carries — printed
        # like the citation sweep's undecided rows, never pinned, never red.
        status = "✗" if flags else ("·" if (got["dup"] or got["above"] or got["malformed"]
                                    or got["resets"] or got["unbumped"]) else "✓")
        print(f"{status} {repo.name:22s} files={got['n_files']:<5d} "
              f"dup={len(got['dup'])} stale={len(got['above'])} malformed={len(got['malformed'])} "
              f"resets={len(got['resets'])} unbumped={len(got['unbumped'])}")
        for r in got["malformed"]:
            print(f"      malformed:  {r}")
        for r in got["above"]:
            print(f"      stale:      {r}")
        for r in got["dup"]:
            print(f"      duplicate:  {r}")
        for r in got["resets"]:
            print(f"      reset:      {r}")
        for r in got["unbumped"]:
            print(f"      unbumped:   {r}")
        for f in flags:
            bad = True
            print(f"      ✗ {f}")

    # The population axis, shared (Issue 793): UNREGISTERED reds in every
    # posture, UNSEEN reds without the marker, and the same set DEFERS loudly
    # with it. Never auto-detected — a genuine removal whose row update was
    # forgotten is set-identical to a partial clone from the walk alone.
    pop_lines, deferred, pop_fail = population_verdict(pins, seen)

    # Issue 797 — the worktree is not the repo. This run reads files that
    # concurrent sessions are editing, so a finding may sit on a line no
    # commit contains. ADVISORY, never a failure: a sweep that hard-reds on
    # an ordinary dirty worktree is a sweep nobody runs. It rides the FINAL
    # line in BOTH directions (the `deferred` precedent) and is SILENT
    # unless the dirty set meets this sweep's own population — the numbered directories + the HISTORY headings the oracle reads.
    deferred.extend(sweep_advisory(
        seen, (".issues/*", ".plans/*", ".docs/*", ".research/*",
     ".proposals/*", "HISTORY.md"), root=WORKSPACE))
    for _line in pop_lines:
        print(_line)
    if pop_fail:
        bad = True

    print(f"\n{len(repos)} contract repo(s) · {tot_dup} tracked duplicate(s) · "
          f"{tot_above} stale allocator(s) · {tot_mal} malformed allocator(s) · "
          f"{tot_reset} counter reset(s) · {tot_unb} un-bumped counter(s) [report-only]")
    print(f"  resets are judged per-commit against each commit's OWN parents "
          f"(Issue 770: the 769 walker's date-ordered interleaving manufactured "
          f"phantoms and never saw merges; this walk blames the commit that did "
          f"it — merge resolutions taking the lower side included). Pinned at "
          f"measured as a ratchet — a NEW reset reds at its pin. unbumped rows "
          f"are checkout state (branch-dependent), printed, never gated.")
    # Say the scope at the point of READING, not only in the docstring. A green
    # `dup=0` is green over SERIAL_DIRS only, and riir-ai carried four genuine
    # cross-topic `.benchmarks/` collisions (617/619, resolved 2026-09-05) while
    # this line printed `dup=0` for it — the number was right and the reader's
    # inference from it was not.
    family = "/".join(d for d in ALL_DIRS if d not in SERIAL_DIRS)
    print(f"  scope: duplicate + stale checks cover {'/'.join(SERIAL_DIRS)} ONLY; "
          f"{family} share numbers by OWNER convention (a family per plan/issue "
          f"is intended) and are malformed-checked only — see "
          f"{PINS.name} for the measured reason. A `dup=0` above is NOT a claim "
          f"about {family}.")
    if bad:
        print("✗ numbering sweep FAILED — see the ✗ rows above")
        for _d in deferred:
            print(f"  ⚠ {_d}")
        return 1
    _line = "✓ numbering sweep PASSED — nothing above its pinned ratchet"
    if deferred:
        _line += "; DEFERRED: " + "; ".join(deferred)
    print(_line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
