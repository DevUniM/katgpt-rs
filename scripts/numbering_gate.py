#!/usr/bin/env python3
"""Issue 724 T4 — the `.plans/`/`.issues/`/`.research/`/`.proposals/` numbering gate.

Every cross-reference in this workspace is by number, so a number allocated
twice means `Plan N` resolves to two documents and a reader following a citation
cannot tell which. AGENTS.md's Numbering Discipline says `.highwater` prevents
this; nothing checked that it was consulted, and it repeatedly was not:

  * `f98f7b51` (2026-07-15) resolved ELEVEN `.plans/` collisions by hand, and a
    new one landed three days later (`449`, both copies still in HEAD until
    Issue 724 T2). A one-time cleanup with no gate behind it buys three days.
  * `.plans/.highwater` read 585 while `586_*` existed, and `.benchmarks/`
    700 while `701_*` existed — i.e. `value + 1` was ALREADY TAKEN in two
    directories at once. The loaded state is the normal state unless something
    checks.

Scope, floors and ceilings are DATA, in `scripts/numbering_floors.txt`, which
also carries the measured reason `.benchmarks/` and `.docs/` are excluded. Read
that file before widening this one.

Report + gate. Exit 0 clean, 1 on drift, **2 if the instrument itself is
untrustworthy** (selftest failure) — an unreliable instrument is not the same
finding as drift, and must not be reported as one.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
import pathlib

# ── vocabulary: DATA, not derived from the tree ────────────────────────────
# Deriving both the scope and the population from one walk is what makes a
# gate permanently green (the workspace rule). The scope is pinned; only the
# population is derived.
NUMBERED = re.compile(r"^(\d+)_.+\.md$")
HIGHWATER = ".highwater"


def parse_pins(path: Path) -> dict[str, int]:
    pins: dict[str, int] = {}
    # UTF-8-explicit: the locale codec (cp1252 on Windows) cannot decode pins with non-ASCII prose (2026-09-06 catch)
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        key, val = (p.strip() for p in line.split("=", 1))
        pins[key] = int(val)
    return pins


def tracked_paths(repo: Path, dirs: list[str]) -> set[str]:
    """The set of git-TRACKED paths under `dirs`, as repo-relative strings.

    One subprocess call. An untracked file is a colleague's in-flight work, not
    a repo defect -- but it becomes one the moment it is committed, so the two
    populations are kept apart rather than pooled.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "ls-files", "--", *dirs],
            capture_output=True, encoding="utf-8", errors="replace", check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return set()
    return {ln.strip() for ln in out.splitlines() if ln.strip()}


def read_highwater(d: Path) -> tuple[int | None, str | None]:
    """-> (value, malformed_raw). Exactly one of the two is None.

    ABSENT and MALFORMED are deliberately NOT the same verdict, and conflating
    them is what made the above-highwater ceiling blind. Not every numbered
    directory carries an allocator, so a missing file is legal; a file that is
    PRESENT and unparseable disables the `max > highwater` check while looking
    identical to a clean directory in the output — the exact "instrument goes
    blind, ceiling passes" shape numbering_floors.txt's floors exist to catch,
    one field over.

    Measured 2026-09-05 across the 16 contract repos: FIVE such files, all the
    same cause — `echo -n <N> > .highwater` under a shell whose builtin `echo`
    does not implement `-n`, so the flag itself lands in the file (`-n 872`).
    None of them is a bare integer; every one of them silently disarms the
    check for its directory.
    """
    f = d / HIGHWATER
    return parse_highwater(f.read_text(errors="replace", encoding="utf-8")
                           if f.is_file() else None)


def parse_highwater(raw: str | None) -> tuple[int | None, str | None]:
    """`read_highwater`'s rule over TEXT — Issue 822 T5h.

    ABSENT is `None` text, not empty text: `git show HEAD:<dir>/.highwater`
    answers `None` for a file HEAD does not carry and `""` for one it carries
    empty, and those are different verdicts here (legal vs MALFORMED). A caller
    that pooled them would report a directory that never had an allocator as a
    disarmed one, and the reverse.

    Extracted so a HEAD-side re-classification reads the SAME rule rather than
    a second copy of it (Issue 755) — the `read_highwater` docstring above is
    the whole warrant for why this parse is subtle enough to matter.
    """
    if raw is None:
        return None, None
    raw = raw.strip()
    try:
        return int(raw), None
    except ValueError:
        return None, raw


def scan(repo: Path, dirname: str, tracked: set[str]):
    """-> (numbers -> [(name, is_tracked)], highwater, n_files, malformed_raw)."""
    d = repo / dirname
    if not d.is_dir():
        return {}, None, 0, None
    by_num, n = group_numbered((e.name for e in d.iterdir()), dirname, tracked)
    hw, hw_bad = read_highwater(d)
    return by_num, hw, n, hw_bad


def group_numbered(names, dirname: str, tracked: set[str]):
    """-> (numbers -> [(name, is_tracked)], n_numbered). PURE over a LISTING.

    Issue 822 T5h. `scan` above takes its listing from the filesystem, and the
    HEAD side of a provenance split has no filesystem to take it from — a
    committed listing is `git ls-tree`, which is 0.05s against the ~30s a
    materialised tree costs (measured on riir-ai, 1601 paths). Splitting the
    rule out is what lets both sides run it instead of one side re-deriving it.

    The subtlety being shared, and it is the reason this is not re-typed at the
    call site: `int()`, never the literal prefix — `075` and `75` are the same
    "Plan 75" to every citation in the corpus, so they must collide here too.
    """
    by_num: dict[int, list[tuple[str, bool]]] = {}
    n = 0
    for name in sorted(names):
        m = NUMBERED.match(name)
        if not m:
            continue
        n += 1
        by_num.setdefault(int(m.group(1)), []).append(
            (name, f"{dirname}/{name}" in tracked))
    return by_num, n


def unmeasurable(repo: Path) -> str | None:
    """Why `repo` cannot be measured, or `None` if it can.

    `tracked_paths` converts a git failure into an EMPTY SET, which is the
    same value a repo with no numbered files would produce. Downstream that
    becomes `0 numbered file(s)` in every directory, and the ceilings above
    the floors are then evaluated over nothing — so a typo'd path prints ten
    `STALE pin ...: pinned as a collision and no longer one — remove the row`
    lines and `legacy collisions 0 < ratchet 61 — re-pin DOWN in this commit`
    before the floor breach that is the real verdict.

    ⛔ Both of those remedies DELETE the only record of a collision, and this
    repo has already run that incident for real: a pin was removed as "stale"
    in the commit that closed its issue, and `develop` went red for every
    later run (AGENTS.md § Numbering Discipline). The floors do red — exit is
    1, not 0 — so nothing here was silently wrong; what was wrong is that the
    destructive advice is printed FIRST and the reason it is bogus LAST,
    which is this document's own most-repeated failure.

    So refuse up front, with the exit code this module already reserves for
    "the instrument cannot be trusted" (2) rather than the one that means
    "the repo has findings" (1).

    ⚠ The check is toplevel EQUALITY, not "did `rev-parse` succeed". `git -C`
    walks UP, so a subdirectory of a real repo answers happily and then
    resolves every path relative to the wrong root — `tracked_walk.py` records
    the same hazard for its own `.git` probe. An arm pins that case, because
    the cheaper check passes it.
    """
    if not repo.is_dir():
        return f"not a directory: {repo}"
    try:
        top = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--show-toplevel"],
            capture_output=True, encoding="utf-8", errors="replace", check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return f"not a git repository, or git unavailable: {repo}"
    # No `if not top` branch: `check=True` means the call SUCCEEDED, and a
    # successful `--show-toplevel` always prints a path (a bare repo fails at
    # 128 with "must be run in a work tree" and is caught above). It would be
    # an unarmable line, and removing it loses nothing even if some git did
    # return empty — `Path("").resolve()` is the cwd, which fails the
    # equality below and refuses anyway, just with a less precise message.
    if Path(top).resolve() != repo:
        return (f"not a repository ROOT: {repo} sits inside {Path(top).resolve()} "
                f"— every path below would resolve against the wrong root")
    return None


def selftest() -> list[str]:
    """Pin the classifier. Every failure mode below is SILENT otherwise."""
    fails = []

    # 0. the REFUSAL, four ways. Arm 3 is the one that earns its keep: the
    #    obvious implementation ("did `rev-parse --show-toplevel` succeed?")
    #    passes it, because `git -C` walks UP out of any subdirectory.
    import subprocess as _sp, tempfile as _tf, pathlib as _pl
    with _tf.TemporaryDirectory() as _td:
        _root = _pl.Path(_td).resolve()
        _missing = _root / "no_such_dir"
        if unmeasurable(_missing) is None:
            fails.append("unmeasurable() accepted a path that does not exist")
        elif "not a directory" not in unmeasurable(_missing):
            fails.append("unmeasurable() misreported a missing path")

        _plain = _root / "plain"
        _plain.mkdir()
        _why = unmeasurable(_plain)
        if _why is None:
            fails.append("unmeasurable() accepted a directory that is not a git repo")
        elif "not a git repository" not in _why:
            # The REASON, not just the refusal. Dropping `check=True` still
            # refuses — an errored `rev-parse` prints nothing, and
            # `Path("").resolve()` is the cwd, which fails the root-equality
            # test — but it refuses as "not a repository ROOT", sending the
            # reader to look for a parent repo that does not exist. Measured:
            # with the message unasserted, that mutant SURVIVES.
            fails.append(f"unmeasurable() refused a non-repo for the wrong reason: {_why}")

        _repo = _root / "repo"
        (_repo / "sub").mkdir(parents=True)
        try:
            _sp.run(["git", "-C", str(_repo), "init", "-q", "-b", "main"],
                    capture_output=True, check=True)
        except (_sp.CalledProcessError, FileNotFoundError):
            fails.append("unmeasurable() arms need git and it is unavailable — "
                         "the refusal is asserted by NOTHING")
        else:
            if unmeasurable(_repo) is not None:
                fails.append(f"unmeasurable() refused a real repo root: {unmeasurable(_repo)}")
            _sub = unmeasurable(_repo / "sub")
            if _sub is None:
                fails.append("unmeasurable() accepted a SUBDIRECTORY of a repo — "
                             "`git -C` walks up, so every path below would "
                             "resolve against the wrong root")
            elif "ROOT" not in _sub:
                fails.append(f"unmeasurable() refused a subdirectory for the wrong reason: {_sub}")

    # 1. the regex admits the real shapes and rejects the non-numbered ones
    for name in ("075_foo_bar.md", "0_x.md", "586_pot_scale.md"):
        if not NUMBERED.match(name):
            fails.append(f"regex rejected a real numbered file: {name}")
    for name in ("README.md", ".highwater", "notes.md", "0_.md", "abc_1.md"):
        if NUMBERED.match(name):
            fails.append(f"regex admitted a non-numbered file: {name}")

    # 2. zero-padding must NOT hide a collision -- `075` and `75` are one number
    if int("075") != int("75"):
        fails.append("zero-pad normalization broken")

    # 3. pin parsing: comments stripped, dotted keys kept
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "pins.txt"
        p.write_text(
            "# a comment\nmax_duplicate_numbers = 0\n"
            "min_files.plans = 400  # trailing comment\n\nnot a pin line\n", encoding="utf-8"
        )
        pins = parse_pins(p)
        if pins.get("max_duplicate_numbers") != 0:
            fails.append("pin parse: ceiling missing")
        if pins.get("min_files.plans") != 400:
            fails.append("pin parse: trailing comment not stripped")
        if len(pins) != 2:
            fails.append(f"pin parse: expected 2 pins, got {len(pins)}")

    # 4. the tracked/untracked split -- the whole reason this gate can land
    #    green today, so a regression here silently turns a WIP file into a
    #    failure or (worse) a committed collision into a warning.
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        (repo / ".plans").mkdir()
        for nm in ("001_a.md", "001_b.md", "002_c.md"):
            (repo / ".plans" / nm).write_text("x", encoding="utf-8")
        (repo / ".plans" / HIGHWATER).write_text("2", encoding="utf-8")
        by_num, hw, n, hw_bad = scan(repo, ".plans", {".plans/001_a.md", ".plans/002_c.md"})
        if hw_bad is not None:
            fails.append(f"clean highwater misread as malformed: {hw_bad!r}")
        if n != 3:
            fails.append(f"scan counted {n}, expected 3")
        if hw != 2:
            fails.append(f"scan read highwater {hw}, expected 2")
        if sorted(by_num) != [1, 2]:
            fails.append(f"scan grouped {sorted(by_num)}, expected [1, 2]")
        flags = dict((nm, tr) for nm, tr in by_num.get(1, []))
        if flags != {"001_a.md": True, "001_b.md": False}:
            fails.append(f"tracked split wrong: {flags}")

        # 5. above-highwater must be DETECTED, not just tolerated
        (repo / ".plans" / "009_over.md").write_text("x", encoding="utf-8")
        by2, hw2, _, _ = scan(repo, ".plans", set())
        if max(by2) <= (hw2 or 0):
            fails.append("above-highwater case did not construct")

    # 6. ABSENT vs MALFORMED must not collapse. Both read as `hw is None`, so
    #    without this pin a corrupted allocator is indistinguishable from a
    #    directory that never had one — and the above-highwater ceiling passes
    #    over both. Canaried with the real observed corruption, not a synthetic
    #    one: `echo -n 872` writing its own flag into the file.
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        hw, bad = read_highwater(d)
        if (hw, bad) != (None, None):
            fails.append(f"absent highwater misclassified: {(hw, bad)}")
        (d / HIGHWATER).write_text("-n 872\n", encoding="utf-8")
        hw, bad = read_highwater(d)
        if hw is not None or bad != "-n 872":
            fails.append(f"malformed highwater not detected: {(hw, bad)}")
        (d / HIGHWATER).write_text("  0872  \n", encoding="utf-8")
        hw, bad = read_highwater(d)
        if (hw, bad) != (872, None):
            fails.append(f"padded/zero-padded highwater misread: {(hw, bad)}")

    # Called from HERE, not from main(): `arm_reach_audit` invokes an arm
    # only by the names in its vocabulary, so a helper wired into main()
    # is measured as reaching nothing (measured on the commit that added
    # it — nine collision_verdict decisions read SURVIVED with the arms
    # already written and passing).
    fails += collision_arms()

    return fails


def parse_collision_pins(path: Path) -> tuple[dict, dict[tuple[str, int], str]]:
    """-> (scalars, {(dir, number): reason}) from number_collisions_expected.txt.

    A reasonless `collision =` row is REFUSED, the Issue 789 idiom: a pin file
    is adjudicated from its reasons, and a row that carries none is a backlog
    wearing a pin (Issue 785).
    """
    scalars: dict[str, int] = {}
    rows: dict[tuple[str, int], str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        key, val = (x.strip() for x in line.split("=", 1))
        if key != "collision":
            scalars[key] = int(val)
            continue
        parts = val.split(None, 2)
        if len(parts) < 3 or not parts[2].strip():
            raise ValueError(f"collision row without a reason: {raw.strip()!r}")
        rows[(parts[0], int(parts[1]))] = parts[2].strip()
    return scalars, rows


def historical_collisions(repo: Path, dirs: list[str]) -> tuple[list[tuple[str, int, list[str]]], int]:
    """Numbers held by 2+ documents across HISTORY -> (rows, numbers walked).

    ⛔ The tracked-duplicate check one function up is correct and blind to the
    majority case. A document closed under the noise-reduction rule is DELETED,
    so a double-allocation where both sides have closed leaves NOTHING on disk
    and reads as clean — and every number this repo allocates is expected to end
    up removed. Measured 2026-09-15: 70 collisions in scope, 9 of them from one
    57-commit divergence, and this gate had never reported one (Issue 795).

    The recovery is `citation_weight.removed_by_number`, imported rather than
    re-derived: the `-M` rename exclusion it carries is subtle enough that a
    second copy would be a second thing to get wrong (Issue 755).
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from citation_weight import removed_by_number

    rows, walked = [], 0
    for dirname in dirs:
        seen = {n: set(v) for n, v in removed_by_number(repo, dirname).items()}
        d = repo / dirname
        if d.is_dir():
            for entry in d.iterdir():
                m = NUMBERED.match(entry.name)
                if m:
                    seen.setdefault(int(m.group(1)), set()).add(entry.name[:-3])
        walked += len(seen)
        for num, stems in sorted(seen.items()):
            if len(stems) > 1:
                rows.append((dirname, num, sorted(stems)))
    return rows, walked


def collision_verdict(rows, scalars, pins) -> tuple[list[str], list[str]]:
    """-> (failures, notes). Two regimes, and the split is the whole design.

    ABOVE `era_boundary` the wall is absolute and pinned by MEMBERSHIP: a new
    collision there is a live ambiguity in prose people are writing today, and
    a COUNT would be green on a swap. Reds in BOTH directions — a pinned row
    that is no longer a collision is a finding too, because the pin and its
    removal belong in the same commit.

    BELOW it, a RATCHET. Those are the pre-gate archive (`.issues/121`'s
    number-recycling era) and adjudicating them is a backlog: Issue 785's rule
    forbids ratcheting a bucket that means "unread", so they are never pinned
    with invented reasons — only counted, and the count may not grow.
    """
    boundary = scalars["era_boundary"]
    fails, notes = [], []
    live = {(d, n) for d, n, _ in rows}
    above = {(d, n) for d, n in live if n >= boundary}
    legacy = [(d, n) for d, n in live if n < boundary]

    for d, n in sorted(above - set(pins)):
        stems = next(st for dd, nn, st in rows if (dd, nn) == (d, n))
        fails.append(f"UNPINNED collision {d}/{n}: {' · '.join(stems)} — a number "
                     f"above the era boundary held by {len(stems)} documents")
    for d, n in sorted(set(pins) - above):
        fails.append(f"STALE pin {d}/{n}: pinned as a collision and no longer one "
                     f"— remove the row in the commit that resolved it")
    if len(legacy) > scalars["legacy_ratchet"]:
        fails.append(f"legacy collisions {len(legacy)} > ratchet "
                     f"{scalars['legacy_ratchet']} — a number below the era "
                     f"boundary was allocated twice AGAIN")
    elif len(legacy) < scalars["legacy_ratchet"]:
        notes.append(f"legacy collisions {len(legacy)} < ratchet "
                     f"{scalars['legacy_ratchet']} — re-pin DOWN in this commit")
    return fails, notes


def collision_arms() -> list[str]:
    """The Issue 795 verdict's OWN arithmetic, which no classifier reaches.

    Issue 775's rule, one gate over: a gate's pin arithmetic sits between two
    calls into a classifier, so the classifier's self-test cannot see it. Both
    halves are armed here — the pin PARSER (which refuses a reasonless row) and
    the two-regime verdict.
    """
    import tempfile

    fails: list[str] = []

    def eq(label, got, want):
        if got != want:
            fails.append(f"    {label}: got {got!r}, want {want!r}")

    SC = {"era_boundary": 700, "legacy_ratchet": 2}
    R = [(".issues", 100, ["a", "b"]), (".issues", 200, ["c", "d"]),
         (".issues", 800, ["e", "f"])]
    PINS = {(".issues", 800): "measured"}

    f, n = collision_verdict(R, SC, PINS)
    eq("a pinned collision above the boundary and a legacy count at the "
       "ratchet is clean", (f, n), ([], []))
    # ABOVE the boundary the wall is absolute and pinned by MEMBERSHIP: a COUNT
    # would be green on a swap, which is the whole reason it is not one.
    f, _ = collision_verdict(R, SC, {(".issues", 900): "wrong row"})
    eq("an UNPINNED collision above the boundary is a finding",
       sum(1 for x in f if x.startswith("UNPINNED")), 1)
    eq("...and a pin naming a number that is no longer a collision is ALSO one",
       sum(1 for x in f if x.startswith("STALE")), 1)
    # The membership swap: same COUNT, different set.
    f, _ = collision_verdict(
        [(".issues", 800, ["e", "f"]), (".issues", 900, ["g", "h"])], SC,
        {(".issues", 800): "m", (".issues", 900): "m"})
    eq("two pinned collisions above the boundary are clean", f, [])
    f, _ = collision_verdict(
        [(".issues", 800, ["e", "f"]), (".issues", 901, ["g", "h"])], SC,
        {(".issues", 800): "m", (".issues", 900): "m"})
    eq("a SWAP is caught in both directions, where a count would be green",
       len(f), 2)
    # BELOW it, a ratchet. Growth reds; shrinkage is a note, not a failure --
    # the verdict is "re-pin DOWN", and refusing the commit that RESOLVED a
    # collision would be the gate punishing the repair.
    f, _ = collision_verdict(R + [(".issues", 300, ["x", "y"])], SC, PINS)
    eq("a NEW legacy collision breaches the ratchet",
       sum(1 for x in f if "ratchet" in x), 1)
    f, n = collision_verdict([(".issues", 100, ["a", "b"]),
                              (".issues", 800, ["e", "f"])], SC, PINS)
    eq("a RESOLVED legacy collision is a note, never a failure",
       (f, len(n)), ([], 1))
    # The boundary is INCLUSIVE at its own value: 700 is in the walled era.
    f, _ = collision_verdict([(".issues", 700, ["a", "b"])],
                             {"era_boundary": 700, "legacy_ratchet": 0}, {})
    eq("era_boundary is inclusive — a collision AT it is walled, not legacy",
       (len(f), sum(1 for x in f if x.startswith("UNPINNED"))), (1, 1))
    # The DIRECTORY is part of the key: the same number in two directories is
    # two independent allocations and pooling them would let one vouch for
    # the other.
    f, _ = collision_verdict([(".plans", 800, ["a", "b"])], SC, PINS)
    eq("a pin is keyed by (dir, number), not by number alone", len(f), 2)

    with tempfile.TemporaryDirectory() as td:
        q = pathlib.Path(td) / "pins.txt"
        q.write_text("era_boundary = 700\nlegacy_ratchet = 5\n"
                     "a prose line carrying no equals sign at all\n"
                     "\n"
                     "collision = .issues 800 because measured\n"
                     "# collision = .issues 900 a comment is not a row\n",
                     encoding="utf-8")
        sc, rows = parse_collision_pins(q)
        eq("the parser reads the scalars", sc,
           {"era_boundary": 700, "legacy_ratchet": 5})
        eq("...and the rows, reason intact",
           rows, {(".issues", 800): "because measured"})
        eq("a commented row is not a pin", (".issues", 900) in rows, False)
        # A reasonless row is REFUSED, never silently accepted: a pin file is
        # adjudicated from its reasons, and one that carries none is a backlog
        # wearing a pin.
        q.write_text("era_boundary = 700\ncollision = .issues 800\n",
                     encoding="utf-8")
        try:
            parse_collision_pins(q)
            eq("a collision row with no reason is REFUSED", False, True)
        except ValueError:
            eq("a collision row with no reason is REFUSED", True, True)

    # ── the CLASSIFIER, over a real git tree. The two arms above test the pin
    # arithmetic; this tests what a collision IS, and it is the half that
    # decides the population everything else is a ceiling over.
    import shutil
    import subprocess
    if not shutil.which("git"):
        fails.append("    collision_arms: UNSEEN \u2014 no `git` on PATH, so "
                     "historical_collisions was asserted by NOTHING")
        return fails
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        d = root / ".issues"
        d.mkdir(parents=True)

        def git(*a):
            return subprocess.run(["git", "-C", str(root), *a],
                                  capture_output=True, encoding="utf-8",
                                  errors="replace", check=True).stdout.strip()

        git("init", "-q", "-b", "main")
        git("config", "user.email", "arm@example.invalid")
        git("config", "user.name", "arm")
        for name in ("010_first_holder.md", "010_second_holder.md",
                     "011_sole_holder.md", "012_still_here.md"):
            (d / name).write_text("x\n", encoding="utf-8")
        git("add", "-A")
        git("commit", "-q", "-m", "one")
        # 010 is held twice and BOTH are removed -- the shape the tracked
        # duplicate check cannot see, and the whole reason this exists.
        # 011 is removed and held ONCE: a closed document is not a collision.
        for name in ("010_first_holder.md", "010_second_holder.md",
                     "011_sole_holder.md"):
            (d / name).unlink()
        git("add", "-A")
        git("commit", "-q", "-m", "two")

        rows, walked = historical_collisions(root, [".issues"])
        eq("a number held twice with BOTH sides removed is a collision",
           [(dd, nn) for dd, nn, _ in rows], [(".issues", 10)])
        eq("...and both stems are reported",
           next(st for _, nn, st in rows if nn == 10),
           ["010_first_holder", "010_second_holder"])
        eq("a removed document held ONCE is not a collision",
           any(nn == 11 for _, nn, _ in rows), False)
        eq("a document still on disk and held once is not a collision",
           any(nn == 12 for _, nn, _ in rows), False)
        eq("the walk counts every number it saw, collision or not", walked, 3)
        # A live file meeting a removed one is the mixed case -- the only shape
        # the old instrument could see, and it must still be one.
        (d / "012_second_claimant.md").write_text("y\n", encoding="utf-8")
        git("add", "-A")
        git("commit", "-q", "-m", "three")
        (d / "012_second_claimant.md").unlink()
        git("add", "-A")
        git("commit", "-q", "-m", "four")
        rows, _ = historical_collisions(root, [".issues"])
        eq("a LIVE file meeting a removed one is a collision",
           sorted(nn for _, nn, _ in rows), [10, 12])
        eq("a directory that does not exist contributes nothing",
           historical_collisions(root, [".nope"]), ([], 0))

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
        print("✗ numbering gate SELFTEST FAILED — instrument untrustworthy:")
        for f in fails:
            print(f"    {f}")
        return 2

    repo = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
    why = unmeasurable(repo)
    if why:
        print(f"✗ numbering gate REFUSES — {why}")
        print("  Nothing below this line was measured. Every verdict this gate")
        print("  prints is a ceiling over a git-derived population, so an")
        print("  unreadable repo yields 0 files, 0 collisions and a page of")
        print("  `remove the row` / `re-pin DOWN` advice that would DELETE the")
        print("  only record of a real collision.")
        return 2
    pins_path = Path(__file__).resolve().parent / "numbering_floors.txt"
    if not pins_path.is_file():
        print(f"✗ pins file missing: {pins_path}")
        return 2
    pins = parse_pins(pins_path)

    dirs = sorted(k.split(".", 1)[1] for k in pins if k.startswith("min_files."))
    if not dirs:
        print("✗ pins file declares NO directories — an empty scope is refused")
        return 2
    dirs = [f".{d}" for d in dirs]

    tracked = tracked_paths(repo, dirs)
    dup_tracked: list[str] = []
    dup_untracked: list[str] = []
    above: list[str] = []
    malformed: list[str] = []
    below_floor: list[str] = []
    total = 0

    for dirname in dirs:
        by_num, hw, n, hw_bad = scan(repo, dirname, tracked)
        total += n
        if hw_bad is not None:
            malformed.append(
                f"{dirname}/.highwater is not a bare integer: {hw_bad!r} — the "
                f"above-highwater check is DISARMED for this directory"
            )
        floor = pins.get(f"min_files{dirname}", 0)
        if n < floor:
            below_floor.append(f"{dirname}: {n} numbered file(s) < floor {floor}")
        for num, files in sorted(by_num.items()):
            if len(files) < 2:
                continue
            names = " · ".join(nm for nm, _ in files)
            n_tracked = sum(1 for _, tr in files if tr)
            row = f"{dirname}/{num:03d} ×{len(files)}: {names}"
            (dup_tracked if n_tracked >= 2 else dup_untracked).append(
                row + ("" if n_tracked >= 2 else f"  [{n_tracked} tracked]")
            )
        if hw is not None and by_num and max(by_num) > hw:
            above.append(f"{dirname}: max {max(by_num)} > .highwater {hw} — `value + 1` is already taken")

    # ── historical collisions (Issue 795) ──────────────────────────────────
    cpins_path = Path(__file__).resolve().parent / "number_collisions_expected.txt"
    if not cpins_path.is_file():
        print(f"✗ collision pins file missing: {cpins_path}")
        return 2
    try:
        cscalars, cpins = parse_collision_pins(cpins_path)
    except ValueError as e:
        print(f"✗ collision pins file is malformed: {e}")
        return 2
    crows, cwalked = historical_collisions(repo, dirs)
    cfails, cnotes = collision_verdict(crows, cscalars, cpins)
    if len(dirs) < cscalars["min_dirs"]:
        cfails.append(f"scope FLOOR: {len(dirs)} dir(s) < {cscalars['min_dirs']} "
                      f"— the collision walk went blind")
    if cwalked < cscalars["min_numbers"]:
        cfails.append(f"walk FLOOR: {cwalked} number(s) < {cscalars['min_numbers']}"
                      f" — a git-history regression empties this and every "
                      f"ceiling above passes")

    max_dup = pins.get("max_duplicate_numbers", 0)
    max_above = pins.get("max_above_highwater", 0)
    max_malformed = pins.get("max_malformed_highwater", 0)
    bad = False

    if len(dup_tracked) > max_dup:
        bad = True
        print(f"✗ {len(dup_tracked)} TRACKED duplicate number(s) (pinned ≤ {max_dup}):")
        for r in dup_tracked:
            print(f"    {r}")
    if len(above) > max_above:
        bad = True
        print(f"✗ {len(above)} .highwater below its directory max (pinned ≤ {max_above}):")
        for r in above:
            print(f"    {r}")
    if len(malformed) > max_malformed:
        bad = True
        print(f"✗ {len(malformed)} malformed .highwater file(s) (pinned ≤ {max_malformed}):")
        for r in malformed:
            print(f"    {r}")
    if cfails:
        bad = True
        print(f"✗ {len(cfails)} HISTORICAL numbering collision finding(s) — a "
              f"number held by two REMOVED documents is invisible to the "
              f"tracked-duplicate check above:")
        for r in cfails:
            print(f"    {r}")
    for r in cnotes:
        print(f"  ⚠ {r}")
    if below_floor:
        bad = True
        print("✗ population FLOOR breached — every other verdict here is a ceiling,")
        print("  so a blind instrument would print a confident green over zero files:")
        for r in below_floor:
            print(f"    {r}")

    if dup_untracked:
        # Deliberately NOT a failure: a colleague's in-flight file is not a
        # repo defect. It becomes one on commit, and this gate then reds.
        print(f"  ⚠ {len(dup_untracked)} duplicate(s) involving UNTRACKED files — not a failure yet:")
        for r in dup_untracked:
            print(f"      {r}")

    if bad:
        return 1
    print(
        f"✓ numbering gate PASSED — {total} numbered file(s) over {len(dirs)} dir(s), "
        f"0 tracked duplicates, 0 stale allocators, 0 malformed allocators; "
        f"{len(crows)} historical collision(s) over {cwalked} number(s), "
        f"{len(cpins)} pinned above the era boundary"
        + (f", {len(dup_untracked)} untracked warning(s)" if dup_untracked else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
