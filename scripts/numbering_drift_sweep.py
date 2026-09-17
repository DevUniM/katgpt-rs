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
from skill_repo_set_gate import (  # noqa: E402 — Issue 815's marker, shared not re-read
    KNOWN_EXTRA_MARKER,
    known_extra_state,
)
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


PIN_FIELDS = ("min_files", "max_dup", "max_above", "max_malformed",
              "max_resets", "min_numbers", "max_hist")


def parse_rows(path: Path) -> dict[str, dict[str, int]]:
    rows: dict[str, dict[str, int]] = {}
    want = 1 + len(PIN_FIELDS)
    # pins carry UTF-8 punctuation; the locale codec (cp1252 on Windows) cannot decode it (2026-09-06 4090-box catch)
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != want:
            raise ValueError(f"malformed pin row (want {want} fields): {raw!r}")
        rows[parts[0]] = {k: int(v) for k, v in zip(PIN_FIELDS, parts[1:])}
    return rows


def audit(repo: Path) -> dict:
    """One repo -> its six finding classes + the two populations behind them.

    ⛔ `dup` and `hist` are NOT two views of one thing and must never be pooled
    (Issue 820). `dup` reads the WORKTREE through `tracked_paths`, so it sees a
    collision only while both holders are still on disk — and a document closed
    under the noise-reduction rule is DELETED, so the case where both have
    closed leaves nothing to read and the row is green. That is the MAJORITY
    case: measured 2026-09-17 over the derived population, `dup` totalled 0
    workspace-wide and `hist` totalled 183.

    `hist` is `numbering_gate.historical_collisions` — Issue 795's recovery,
    IMPORTED rather than re-derived, because the `-M` rename exclusion it
    carries is subtle enough that a second copy is a second thing to get wrong
    (Issue 755, and the reason the gate's own docstring gives for importing it
    from `citation_weight`). It ran in one repo of sixteen for two days: the
    gate is katgpt-rs-scoped by construction and this sweep — the cross-repo
    verdict half of that exact gate — never picked it up.

    ⚠ `hist` deliberately does NOT apply `dup`'s untracked split. An untracked
    holder is a colleague's WIP and not a defect *for a worktree class*; for a
    history class the other holder was REMOVED and was never going to be in
    anybody's worktree, so requiring two tracked copies would discard every row
    the class exists for. An untracked WIP beside a removed number is reported,
    and it is reported correctly — that number is about to be held twice.
    """
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
    # ── the HISTORY class (Issue 820). Its population is `n_numbers` and not
    # `n_files`, and the two break SEPARATELY, which is why both are floored:
    # `n_files` counts tracked documents on disk, `n_numbers` counts distinct
    # numbers recovered from `git log -M --diff-filter=D` PLUS disk. A git-log
    # regression leaves `n_files` untouched and collapses `n_numbers` to the
    # on-disk count, and every ceiling then passes green over a blind walk.
    hist_rows, n_numbers = ng.historical_collisions(repo, list(SERIAL_DIRS))
    hist = [f"{d}/{num:03d} x{len(stems)}: {' · '.join(stems)}"
            for d, num, stems in hist_rows]
    return {"dup": dup, "above": above, "malformed": malformed,
            "resets": resets, "unbumped": unbumped, "hist": hist,
            "n_files": n_serial, "n_numbers": n_numbers}


def pin_flags(got: dict, row: dict[str, int]) -> list[str]:
    """One repo's audit + its pin row -> the failures, in reading order.

    EXTRACTED out of main() (Issue 820 T4). It sat inline between two calls
    into the classifier, so `selftest` could not reach it and the classifier's
    own arms structurally cannot: Issue 775's sentence, in the instrument that
    quotes it. An arm that re-derived the predicate instead would assert an
    abstraction and leave this path free to disagree with it.
    """
    flags = []
    if got["n_files"] < row["min_files"]:
        flags.append(f"population FLOOR breached: {got['n_files']} < {row['min_files']}")
    if got["n_numbers"] < row["min_numbers"]:
        flags.append(
            f"HISTORY WALK floor breached: {got['n_numbers']} < {row['min_numbers']} "
            f"— `git log -M --diff-filter=D` recovered fewer numbers than the "
            f"removed-holder walk has ever seen; every ceiling below is green "
            f"over a blind instrument (Issue 820)")
    if len(got["hist"]) > row["max_hist"]:
        flags.append(
            f"historical collisions {len(got['hist'])} > pinned {row['max_hist']} "
            f"— a number is held by 2+ documents across HISTORY, which the "
            f"worktree `dup` column cannot see once both holders have closed "
            f"(Issues 795 + 820)")
    if len(got["dup"]) > row["max_dup"]:
        flags.append(f"duplicates {len(got['dup'])} > pinned {row['max_dup']}")
    if len(got["above"]) > row["max_above"]:
        flags.append(f"stale allocators {len(got['above'])} > pinned {row['max_above']}")
    if len(got["malformed"]) > row["max_malformed"]:
        flags.append(f"malformed allocators {len(got['malformed'])} > pinned {row['max_malformed']}")
    if len(got["resets"]) > row["max_resets"]:
        flags.append(
            f"counter resets {len(got['resets'])} > pinned {row['max_resets']} "
            f"— a commit (or merge resolution) landed below its parents' max: "
            f"the re-climb re-spends numbers (Issues 769+770)")
    return flags


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

        # ── the HISTORY class (Issue 820). `historical_collisions` shells out
        # to git and returns {} in a non-repo, so the fixture's two on-disk
        # `.plans/001_*` holders are the whole row set here — which is the arm
        # for the DISK half. Stub the git half to pin the union: a number whose
        # holders were both REMOVED is exactly the case `dup` cannot see, and
        # it must land in `hist` and NOT in `dup`.
        from citation_weight import removed_by_number as _real_rbn
        import citation_weight as _cw

        got5 = audit(repo)
        if len(got5["hist"]) != 1 or ".plans/001" not in got5["hist"][0]:
            fails.append(f"hist: two on-disk holders of one number must report: {got5['hist']}")
        if got5["n_numbers"] < 1:
            fails.append(f"hist: the history population must count the numbers walked: {got5['n_numbers']}")

        _cw.removed_by_number = (
            lambda r, d: {9: {"009_gone_a", "009_gone_b"}} if d == ".plans" else {})
        try:
            got6 = audit(repo)
        finally:
            _cw.removed_by_number = _real_rbn
        if not any(".plans/009" in h for h in got6["hist"]):
            fails.append(f"hist: a number whose holders were both REMOVED must "
                         f"report — this is the class `dup` cannot see: {got6['hist']}")
        if any("009" in d for d in got6["dup"]):
            fails.append(f"hist: a removed-only collision leaked into the tracked "
                         f"`dup` class — the two must never be pooled: {got6['dup']}")
        if got6["n_numbers"] <= got5["n_numbers"]:
            fails.append(f"hist: the history walk must widen the population it "
                         f"floors ({got6['n_numbers']} <= {got5['n_numbers']})")

        # ── Issue 815's marker, the half this module SELECTS. `[0]` is the
        # acknowledged set and `[1]` the stale one, and taking the wrong index
        # would excuse exactly the repos the marker refuses to excuse while
        # demanding pin rows for the ones it does — a silent inversion with no
        # visible symptom, since both are lists of repo names.
        import os as _os
        _snap = _os.environ.get(KNOWN_EXTRA_MARKER)
        try:
            _os.environ[KNOWN_EXTRA_MARKER] = "here-extra,gone-extra"
            _ack, _stale = known_extra_state(["here-extra", "other"])
            if set(_ack) != {"here-extra"}:
                fails.append(f"known-extra: the acknowledged half must be the "
                             f"repos PRESENT on the box, got {_ack}")
            if set(_stale) != {"gone-extra"}:
                fails.append(f"known-extra: a named repo absent from the box is "
                             f"STALE and excuses nothing, got {_stale}")
        finally:
            if _snap is None:
                _os.environ.pop(KNOWN_EXTRA_MARKER, None)
            else:
                _os.environ[KNOWN_EXTRA_MARKER] = _snap

        # row parser: 8 fields, comments stripped, arity enforced
        pins = ws / "pins.txt"
        pins.write_text("# c\nrepo-a\t10\t0\t0\t0\t0\t7\t2  # trailing\n\n")
        if parse_rows(pins) != {"repo-a": {"min_files": 10, "max_dup": 0,
                                           "max_above": 0, "max_malformed": 0,
                                           "max_resets": 0, "min_numbers": 7,
                                           "max_hist": 2}}:
            fails.append("row parse: 8-field row not read correctly")
        # ⚠ a 6-field row is the PRE-820 shape and must be REFUSED, not read
        # with the new columns defaulted: a defaulted `min_numbers = 0` is a
        # floor that cannot fail, and `max_hist = 0` would red every repo.
        # Both directions of arity, so the parser cannot only ever loosen.
        for bad_row in ("repo-a 1 2 3 4 5\n", "repo-a 1 2 3 4 5 6 7 8\n"):
            pins.write_text(bad_row)
            try:
                parse_rows(pins)
                fails.append(f"row parse: wrong-arity row accepted: {bad_row!r}")
            except ValueError:
                pass

        # ── the VERDICT arithmetic for the two new columns, which no
        # classifier reaches (Issue 775's rule). It calls `pin_flags`, the
        # function main() calls: re-deriving the predicate here would assert
        # an ABSTRACTION and leave the production path free to disagree with
        # it — the defect AGENTS.md records against injected probes, and the
        # reason `pin_flags` was extracted out of main() at all.
        row = {"min_files": 0, "max_dup": 9, "max_above": 9, "max_malformed": 9,
               "max_resets": 9, "min_numbers": 5, "max_hist": 1}
        base = {k: [] for k in ("dup", "above", "malformed", "resets", "hist")}
        for n_hist, n_num, want in ((1, 5, False), (2, 5, True),
                                    (1, 4, True), (0, 5, False), (0, 4, True)):
            got_f = pin_flags({**base, "hist": ["x"] * n_hist,
                               "n_files": 0, "n_numbers": n_num}, row)
            if bool(got_f) != want:
                fails.append(f"verdict: hist={n_hist} nums={n_num} "
                             f"flags={got_f}, want fired={want}")
        # and the classes must be DISTINGUISHABLE in the message, or a reader
        # cannot tell a blind walk from a real new collision
        blind = pin_flags({**base, "n_files": 0, "n_numbers": 0}, row)
        grew = pin_flags({**base, "hist": ["x", "y"], "n_files": 0, "n_numbers": 9}, row)
        if not (blind and "WALK floor" in blind[0]):
            fails.append(f"verdict: a blind history walk must name itself: {blind}")
        if not (grew and "historical collisions" in grew[0]):
            fails.append(f"verdict: a new collision must name itself: {grew}")
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

    show_hist = "--hist-rows" in sys.argv

    repos = contract_repos(WORKSPACE)
    if not repos:
        print(f"✗ derived population is EMPTY under {WORKSPACE} — refusing to "
              f"report a green over zero repos")
        return 2

    seen = {p.name for p in repos}
    # Only the ACKNOWLEDGED half excuses a missing pin row. A STALE entry (a
    # name that is gone from the box, or that repo_set.txt has since
    # registered) excuses nothing, so the marker cannot only ever loosen —
    # `population_verdict` below is what reports it.
    acknowledged_extra = set(known_extra_state(sorted(seen))[0])
    bad = False
    tot_dup = tot_above = tot_mal = tot_reset = tot_unb = tot_hist = 0

    for repo in repos:
        got = audit(repo)
        row = pins.get(repo.name)
        tot_hist += len(got["hist"])
        tot_dup += len(got["dup"])
        tot_above += len(got["above"])
        tot_mal += len(got["malformed"])
        tot_reset += len(got["resets"])
        tot_unb += len(got["unbumped"])
        if row is None:
            # ⛔ Issue 815's marker reached `population_verdict` and NOT this
            # loop, so a box carrying acknowledged extras printed "not
            # measured and not expected to be" on its final line and demanded
            # a pin row for the same three repos six hundred lines earlier.
            # A sweep that reds in every posture on repos the contract does
            # not claim is a sweep nobody runs — and the UNPINNED wall must
            # stay absolute for everything else, which is why the marker takes
            # NAMES: `=1` would excuse the next unregistered repo too.
            flags = ([] if repo.name in acknowledged_extra else
                     ["UNPINNED — add a row (or it can never red)"])
            if repo.name in acknowledged_extra:
                print(f"      · outside the contract, acknowledged by "
                      f"{KNOWN_EXTRA_MARKER} — no pin row is owed, and none of "
                      f"the columns above was adjudicated")
        else:
            flags = pin_flags(got, row)
        # unbumped is REPORT-ONLY (Issue 770 finding 4): a checkout-state
        # quantity is a function of which branch the box carries — printed
        # like the citation sweep's undecided rows, never pinned, never red.
        status = "✗" if flags else ("·" if (got["dup"] or got["above"] or got["malformed"]
                                    or got["resets"] or got["unbumped"]) else "✓")
        print(f"{status} {repo.name:22s} files={got['n_files']:<5d} nums={got['n_numbers']:<5d} "
              f"dup={len(got['dup'])} hist={len(got['hist'])} "
              f"stale={len(got['above'])} malformed={len(got['malformed'])} "
              f"resets={len(got['resets'])} unbumped={len(got['unbumped'])}")
        # ⚠ hist rows are printed only when the pin BREACHES, or on demand via
        # --hist-rows. The standing backlog is 183 rows workspace-wide and
        # dumping it every run is how a sweep stops being read (the cries-wolf
        # failure docs_gate.sh's preamble records); it lives in the pin file's
        # comments, which is where a backlog is adjudicated from.
        if show_hist or (row is not None and len(got["hist"]) > row["max_hist"]):
            for r in got["hist"]:
                print(f"      historical: {r}")
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

        # ── T3: katgpt-rs does not RESTATE its own gate, it CROSS-CHECKS it.
        # This sweep imports the gate's `historical_collisions`, so comparing
        # the two counts would be true by construction — a pin that restates
        # its own input cannot fail (the full_gate Layer 2c rule). What is NOT
        # automatic is the gate's VERDICT over those rows: the ≥ era_boundary
        # MEMBERSHIP wall and the legacy RATCHET live in
        # number_collisions_expected.txt, which this sweep never reads
        # otherwise, so a pin gone stale there was invisible here.
        # `trap_sentinel_drift_sweep` vs `trap_sentinel_gate.POPULATION_FLOOR`,
        # one instrument over: where a sweep re-states a quantity its per-push
        # gate owns, it ASSERTS the two agree rather than trusting them.
        if repo.name == REPO_ROOT.name:
            try:
                rows, _ = ng.historical_collisions(repo, list(SERIAL_DIRS))
                scalars, cpins = ng.parse_collision_pins(
                    REPO_ROOT / "scripts" / "number_collisions_expected.txt")
                gate_fails, _notes = ng.collision_verdict(rows, scalars, cpins)
            except (OSError, ValueError, KeyError) as e:
                bad = True
                print(f"      ✗ gate cross-check UNREADABLE: {e} — the "
                      f"delegation is asserted, never assumed")
            else:
                for gf in gate_fails:
                    bad = True
                    print(f"      ✗ numbering_gate would RED on this: {gf}")

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
          f"{tot_hist} historical collision(s) · "
          f"{tot_above} stale allocator(s) · {tot_mal} malformed allocator(s) · "
          f"{tot_reset} counter reset(s) · {tot_unb} un-bumped counter(s) [report-only]")
    print(f"  ⛔ `tracked duplicate` and `historical collision` are NOT two "
          f"views of one quantity (Issue 820). The first reads the worktree, "
          f"so it goes green the moment both holders CLOSE — and every number "
          f"here is expected to end up removed under the noise-reduction rule. "
          f"The second recovers them from `git log -M --diff-filter=D` (Issue "
          f"795) and is the majority case — {tot_dup} vs {tot_hist} on THIS "
          f"run, derived, because a landing figure typed here would be a claim "
          f"about history rather than a measurement. Rows print when a pin "
          f"breaches, or on demand with --hist-rows.")
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
