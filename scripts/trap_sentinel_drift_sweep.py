#!/usr/bin/env python3
"""Run the trap-sentinel verdicts over EVERY contract repo, not just this one.

`scripts/trap_sentinel_gate.py` is katgpt-rs-scoped by construction — its
`PINNED_SENTINELLED` names two files in this repo and `docs_gate.yml` has a
single checkout, so it could never see a sibling. That is the right shape for
a per-push CI gate and the wrong shape for "is anybody ELSE about to report a
PASS on an abort?"

The workspace answer to that question was just bought and is being held by
nothing. Issue 734 took the population from 38 EXPOSED to **1**, across ten
repos and 37 scripts:

    katgpt-rs             70eff640    2      riir-clippy      c152b80     2
    riir-chain            e3abbb3d   11      riir-dapps       0148fc8     2
    riir-train            4d35aed4    8      riir-auth        bd50158     1
    riir-mmorpg-examples  3f20650     6      riir-deployer    a632a4b     1
    riir-ai               a8260ad23   4      riir-viewbridge  21da73a     1
    mmorpg-remake           26a18191 + 7efe2a23                             2

Every one of those 37 sentinels is a single line that a future edit can drop
without a word from any gate. That is precisely the shape of the defect Issue
734 exists about: mmorpg-remake's guard could not fail past its layer 13 for
months because nothing objected at the time.

This is the fifth instance of one shape in this workspace, and the first two
found real defects the moment they were pointed anywhere but here:

    Issue 702  ci_gate_coverage              one repo -> 7 dead workflows
    Issue 725  numbering_drift_sweep         one repo -> 35 duplicate numbers
    2026-09-06 required_features_drift_sweep one repo -> clean, and pinned there
    2026-09-06 percentile_drift_sweep        one repo -> clean, and pinned there
    this file  trap_sentinel_drift_sweep     one repo -> 1 finding, pinned + proven inert

Why the ceilings alone hold the sentinels — no membership pin needed
-------------------------------------------------------------------
`cfg_gated_floor_gate.py` and `trap_sentinel_gate.py` both pin their sets by
MEMBERSHIP, because a count is not a checksum over a set: a swap keeps the
total stable. That argument does **not** apply here, and it is worth being
explicit about why rather than copying the stricter thing by reflex.

There, SENTINELLED was a NAME the pin had to carry. Here the verdict is
DERIVED from the file, and every way to lose a sentinel lands in a class the
ceilings already cover:

    delete the flag from an errexit script   -> EXPOSED        (max_exposed)
    delete the flag from a nounset-only one  -> PRECAUTIONARY  (max_precautionary)
    delete the whole script                  -> population floor
    remove its `set -e` / `set -u`           -> population floor
    remove its EXIT trap                     -> population floor

A membership list of 40 names would add nothing the five pins above do not
already catch, and would have to be re-typed on every legitimate rename.

Why BOTH floors, and why the walk floor is not redundant
--------------------------------------------------------
`max_exposed = 0` is green over whatever the classifier can SEE, so a
regression in `walk_sh` (it shells out to `git ls-files`) takes the
population to 0 and every ceiling passes — indistinguishable from a clean
repo. `min_population` catches that.

It cannot do the job alone: **six of the seventeen repos have a population of
ZERO** (no script with both an abort-on-error option and an EXIT trap), so
their population floor is 0 and detects nothing at all. `min_scripts` — the
size of the tracked-`*.sh` walk that produced the population — still bites
there, and it is the quantity a `git ls-files` regression actually moves.
Same argument as `percentile_drift_sweep.py`'s `min_rs_files`.

Both floors are deliberately SLACK against churn (~60% of measured) and TIGHT
against blindness: consolidating three ad-hoc gate scripts into one
legitimately shrinks the count by a third, and a floor that ratchets to the
last measurement would red that refactor and teach whoever hits it that the
sweep is noise. A walk regression drops these by an order of magnitude.

Why this is NOT in scripts/docs_gate.sh's CHECKS
------------------------------------------------
Identical to the other four sweeps: CI has one checkout, the siblings are
private and simply absent, so this would either red on every run or derive an
EMPTY population and print a confident green over zero repos.

    this script                 workstation, on demand, every contract repo
    trap_sentinel_gate.py       CI, per-push (docs_gate.sh), katgpt-rs only

Exit 0 clean, 1 on drift above the pins, **2 if the instrument itself is
untrustworthy** — an unreliable instrument is not the same finding as drift.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# DRY: the classifier, the premise measurement and the selftest are the
# report's, so the sweep, the per-push gate and the report can never disagree
# about what EXPOSED means.
import trap_exit_launder_audit as tela  # noqa: E402
import trap_sentinel_gate as tsg  # noqa: E402
from sweep_population import open_repo, population_verdict, pin_row_exempt  # noqa: E402
from worktree_state import (  # noqa: E402
    HeadDelta, deferral_line, head_delta, sweep_advisory)

REPO_ROOT = HERE.parent
WORKSPACE = REPO_ROOT.parent
PINS = HERE / "trap_sentinel_drift_floors.txt"

FIELDS = ("min_scripts", "min_population", "max_exposed", "max_precautionary",
          "max_live_forward", "max_unparsed", "max_replaced")
CLASSES = (("exposed", tela.EXPOSED), ("precautionary", tela.PRECAUTIONARY),
           ("live_forward", tela.LIVE_FORWARD), ("unparsed", tela.UNPARSED))

# ONE list, read by the worktree advisory AND by the HEAD re-classification.
# `walk_sh` IS the population — `git ls-files -z '*.sh'`, nothing else — so a
# single pattern states it exactly, and the advisory's own copy used to say the
# same thing separately. T5g measured a hand-typed copy of a population
# disagreeing with its classifier in three ways at once; one constant is why
# there cannot be a second.
SCOPE = ("*.sh",)


def row_key(r: dict) -> tuple:
    """A population row's LINE-FREE identity: `(file, verdict, replaced)`.

    ⛔ **The VERDICT is in the key, and `replaced` with it**, for the reason
    T5f measured and T5g repeated: `head_delta` files a key-matched row as
    COMMITTED carrying the WORKTREE's object, so any field the key omits is a
    field where the worktree silently overrides HEAD — and here EVERY ceiling
    partitions by exactly these two. A script that is EXPOSED at HEAD and
    SENTINELLED in somebody's uncommitted fix must stay on `max_exposed`
    (Issue 798: a repair is not landed until it is committed), and a second
    EXIT trap added uncommitted must not breach `max_replaced`.

    No line number and no ordinal: `analyse` returns at most ONE row per file,
    so the address is unique by construction — asserted by an arm rather than
    remembered, since it is the premise the whole key rests on.
    """
    return (r["file"], r["verdict"], bool(r["replaced"]))


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


def audit(repo: Path) -> dict:
    """One repo -> the gated classes + BOTH populations that produced them."""
    got = {"n_scripts": 0, "n_pop": 0, "replaced": 0, "rows": [], "walked": set()}
    for name, _ in CLASSES:
        got[name] = []
    for path in tela.walk_sh(str(repo)):
        got["n_scripts"] += 1
        # The WALK's own membership, recorded because the HEAD side needs this
        # repo's index set to adjudicate `min_scripts` — and re-deriving it
        # there would be a second copy of "the population is tracked *.sh".
        got["walked"].add(str(Path(path).relative_to(repo)).replace("\\", "/"))
        r = tela.analyse(path)
        if r is None:
            continue
        got["n_pop"] += 1
        r = dict(r, file=str(Path(path).relative_to(repo)).replace("\\", "/"))
        got["rows"].append(r)
        got["replaced"] += bool(r["replaced"])
        for name, verdict in CLASSES:
            if r["verdict"] == verdict:
                got[name].append(r)
    return got


def adjudicate(repo: Path, got: dict) -> tuple:
    """-> (`HeadDelta` over the population rows, the dict the PINS read).

    Issue 822 T5i. The classifier is per-FILE — every verdict is decided by one
    script's own text, and `function_bodies` folds in only bodies defined in
    that same file — so `head_delta`'s premise holds and the cost is
    |dirty ∩ `*.sh`| `git show` calls, zero on an ordinary run.

    ⛔ **ONE delta over the POPULATION rows, never one per class.** Each row
    carries its verdict, so four class deltas would re-partition the same rows
    four times and lose the case this exists for: a script whose verdict MOVED
    between HEAD and the worktree belongs in two buckets at once (UNCOMMITTED
    under its new verdict, MASKED under its old), which one shared key set
    gives for free and four independent ones cannot express.

    ⛔ **`min_scripts` is a FLOOR and floors are pins too** (Issue 797 measured
    the class on a population, not on a finding). HEAD's walk size is derived
    from the deltas rather than re-listed: every dirty path contributes 1 to
    the worktree side if this run's INDEX walk saw it, and 1 to the HEAD side
    if `git show` answered — so a staged-new script subtracts one and a staged
    deletion adds one, and the common case cancels exactly. Re-listing HEAD's
    `*.sh` instead would be a second copy of "the population is tracked `*.sh`"
    living one module away from `walk_sh`, which is the thing this file's own
    DRY note refuses.
    """
    seen_head: dict[str, bool] = {}

    def rescan(rel: str, src: str | None):
        seen_head[rel] = src is not None
        if src is None:
            return []
        r = tela.analyse_lines(src.splitlines())
        # `analyse` answers None for a script with no abort-on-error and no
        # EXIT handler: it is WALKED but not in the population, and the two
        # counts are floored separately for exactly that reason.
        return [] if r is None else [dict(r, file=rel)]

    delta = head_delta(repo, SCOPE, got["rows"],
                       lambda r: r["file"], row_key, rescan)
    head = dict(got)
    head["rows"] = delta.head
    head["n_pop"] = len(delta.head)
    head["n_scripts"] = (got["n_scripts"]
                         - sum(1 for rel in seen_head if rel in got["walked"])
                         + sum(1 for present in seen_head.values() if present))
    head["replaced"] = sum(1 for r in delta.head if r["replaced"])
    for name, verdict in CLASSES:
        head[name] = [r for r in delta.head if r["verdict"] == verdict]
    return delta, head


def selftest() -> list[str]:
    """Pin that the verdicts FIRE through THIS sweep's `audit()`, that the
    control does not, that the population derivation holds, and the parser.
    Each fails silently otherwise, and a silent failure reports a clean
    workspace."""
    import tempfile

    fails = []
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        repo = ws / "fake-repo"
        (repo / "scripts").mkdir(parents=True)
        (repo / "BOUNDARY.md").write_text("x", encoding="utf-8")
        (repo / ".git").mkdir()

        exposed = (
            "#!/usr/bin/env bash\nset -euo pipefail\n"
            'A="$(mktemp)"\n'
            "trap 'rm -f \"$A\"' EXIT\n"
            'echo "$SOMETHING"\necho ALL GREEN\n'
        )
        (repo / "scripts" / "g.sh").write_text(exposed, encoding="utf-8")
        # `walk_sh` asks git; a temp dir has no index, and its documented
        # fallback is an on-disk walk. Assert we actually got the file, or the
        # whole selftest silently measures an empty population.
        got = audit(repo)
        if got["n_scripts"] != 1:
            fails.append(f"walk found {got['n_scripts']} script(s), expected 1 — "
                         f"the non-git fallback in walk_sh regressed and every "
                         f"selftest arm below is vacuous")
        elif len(got["exposed"]) != 1:
            fails.append(f"planted EXPOSED script: got "
                         f"{[r['verdict'] for r in got['rows']]}")
        elif got["n_pop"] != 1:
            fails.append(f"population wrong: {got['n_pop']}")

        # nounset-only: PRECAUTIONARY, never EXPOSED (the T10 severity split —
        # measured, errexit is the precondition).
        (repo / "scripts" / "g.sh").write_text(
            exposed.replace("set -euo pipefail", "set -uo pipefail"), encoding="utf-8")
        got = audit(repo)
        if len(got["precautionary"]) != 1 or got["exposed"]:
            fails.append(f"nounset-only must be PRECAUTIONARY, got "
                         f"{[r['verdict'] for r in got['rows']]}")

        # CONTROL: a sentinelled script must produce NO finding, or the sweep
        # reds on every correct repair and gets switched off.
        (repo / "scripts" / "g.sh").write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\n"
            'A="$(mktemp)"\nDONE_FLAG=0\n'
            "cleanup() {\n    st=$?\n    rm -f \"$A\"\n"
            '    if [ "$DONE_FLAG" != "1" ] && [ "$st" = "0" ]; then\n'
            "        exit 1\n    fi\n    exit \"$st\"\n}\n"
            "trap cleanup EXIT\necho layer\nDONE_FLAG=1\n", encoding="utf-8")
        got = audit(repo)
        if any(got[name] for name, _ in CLASSES):
            fails.append("control: a sentinelled script produced a finding "
                         f"({[r['verdict'] for r in got['rows']]})")
        if got["n_pop"] != 1:
            fails.append("control: the sentinelled script left the population")

        # population derivation: BOUNDARY.md + a .git DIRECTORY, both required
        (ws / "no-boundary").mkdir()
        (ws / "no-boundary" / ".git").mkdir()
        (ws / "worktree-shaped").mkdir()
        (ws / "worktree-shaped" / "BOUNDARY.md").write_text("x", encoding="utf-8")
        (ws / "worktree-shaped" / ".git").write_text("gitdir: elsewhere", encoding="utf-8")
        if tela.repos(str(ws)) != ["fake-repo"]:
            fails.append(f"population derivation wrong: {tela.repos(str(ws))}")

        # pin parser: arity ENFORCED, comments stripped
        pins = ws / "pins.txt"
        pins.write_text("# c\nrepo-a 10 5 0 0 0 0 0  # trailing\n\n", encoding="utf-8")
        want = {"repo-a": dict(zip(FIELDS, (10, 5, 0, 0, 0, 0, 0)))}
        if parse_pins(pins) != want:
            fails.append("pin parse: 8-field row not read correctly")
        pins.write_text("repo-a 1 2 3\n", encoding="utf-8")
        try:
            parse_pins(pins)
            fails.append("pin parse: short row accepted")
        except ValueError:
            pass
    return fails + adjudicate_arms()


EXPOSED_SH = ("#!/usr/bin/env bash\nset -euo pipefail\n"
              'A="$(mktemp)"\n'
              "trap 'rm -f \"$A\"' EXIT\n"
              'echo "$SOMETHING"\necho ALL GREEN\n')
SENTINEL_SH = ("#!/usr/bin/env bash\nset -euo pipefail\nDONE=0\n"
               'A="$(mktemp)"\n'
               "cleanup() {\n  rm -f \"$A\"\n"
               "  if [ \"$DONE\" -ne 1 ]; then exit 1; fi\n}\n"
               "trap cleanup EXIT\n"
               'echo "$SOMETHING"\nDONE=1\necho ALL GREEN\n')


def adjudicate_cases() -> list[str]:
    """`adjudicate` end to end against REAL git — Issue 822 T5i.

    In `selftest`, behind no flag: this sweep has no `--canary`, and an arm
    that only runs when somebody types a flag runs on no invocation anybody
    makes (Issue 789). The fixtures are this file's own EXPOSED specimen and
    its sentinelled repair, which is the pair every arm here turns on.
    """
    import tempfile

    fails: list[str] = []

    def git(root, *args):
        subprocess.run(("git", "-C", str(root)) + args,
                       capture_output=True, check=True)

    def fixture(td: str, committed: str):
        repo = Path(td) / "r"
        (repo / "scripts").mkdir(parents=True)
        (repo / "scripts" / "g.sh").write_text(committed, encoding="utf-8")
        git(repo.parent, "init", "-q", "r")
        git(repo, "config", "user.email", "arm@example.invalid")
        git(repo, "config", "user.name", "arm")
        git(repo, "add", "-A")
        git(repo, "-c", "commit.gpgsign=false", "commit", "-qm", "base")
        return repo

    def run(repo):
        got = audit(repo)
        return (got,) + adjudicate(repo, got)

    # a. ⛔ The direction Issue 798 names: a repair that is not COMMITTED is
    #    not landed. An uncommitted sentinel must NOT clear `max_exposed`.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, EXPOSED_SH)
        (repo / "scripts" / "g.sh").write_text(SENTINEL_SH, encoding="utf-8")
        got, delta, judged = run(repo)
        if got["exposed"]:
            fails.append(f"arm a: the fixture is INERT — the worktree must "
                         f"read SENTINELLED ({got['exposed']})")
        if len(judged["exposed"]) != 1 or len(delta.masked) != 1:
            fails.append(f"adjudicate: an UNCOMMITTED fix cleared the exposed "
                         f"ceiling ({judged['exposed']}) — the committed "
                         f"script still aborts to exit 0 for everyone else")

    # b. And its mirror: a defect introduced in the worktree must not red a
    #    ceiling over a line no commit contains.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, SENTINEL_SH)
        (repo / "scripts" / "g.sh").write_text(EXPOSED_SH, encoding="utf-8")
        got, delta, judged = run(repo)
        if len(got["exposed"]) != 1:
            fails.append(f"arm b: the fixture is INERT — the worktree must "
                         f"read EXPOSED ({got['exposed']})")
        if judged["exposed"] or len(delta.uncommitted) != 1:
            fails.append(f"adjudicate: an uncommitted EXPOSED row reached the "
                         f"ceiling ({judged['exposed']}) instead of "
                         f"UNCOMMITTED")

    # c. ⛔ The VERDICT must be in the key. Keyed on the file alone, (b)'s row
    #    matches HEAD's and `head_delta` keeps the WORKTREE object — so a
    #    verdict flip reads as one COMMITTED row and both buckets stay empty.
    #    Asserted, not trusted: the row must split in BOTH directions.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, SENTINEL_SH)
        (repo / "scripts" / "g.sh").write_text(EXPOSED_SH, encoding="utf-8")
        got, delta, judged = run(repo)
        if not (delta.uncommitted and delta.masked) or delta.committed:
            fails.append(f"row key: a script whose VERDICT moved was not split "
                         f"in both directions (committed={delta.committed}, "
                         f"uncommitted={len(delta.uncommitted)}, "
                         f"masked={len(delta.masked)})")

    # d. The WALK floor. A staged-new script is in `git ls-files` and in no
    #    commit, so HEAD's walk is one SMALLER — and `min_scripts` is a pin.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, SENTINEL_SH)
        (repo / "scripts" / "new.sh").write_text(SENTINEL_SH, encoding="utf-8")
        git(repo, "add", "-A")
        got, delta, judged = run(repo)
        if got["n_scripts"] != 2 or judged["n_scripts"] != 1:
            fails.append(f"adjudicate: the walk floor read the worktree "
                         f"({got['n_scripts']}) instead of HEAD "
                         f"({judged['n_scripts']}) — a floor re-pinned from "
                         f"such a run bakes another session's `git add` into "
                         f"a tracked file")
        if judged["n_pop"] != 1:
            fails.append(f"adjudicate: HEAD's population is "
                         f"{judged['n_pop']}, expected 1")

    # e. ...and its mirror, which is the one that cannot be derived from (d):
    #    a script DELETED in the worktree is gone from `ls-files` and still in
    #    HEAD, so HEAD's walk is one LARGER. A floor that only ever shrinks
    #    with the worktree is a floor that cannot catch this.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, SENTINEL_SH)
        (repo / "scripts" / "gone.sh").write_text(EXPOSED_SH, encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "-c", "commit.gpgsign=false", "commit", "-qm", "two")
        git(repo, "rm", "-q", "scripts/gone.sh")
        got, delta, judged = run(repo)
        if got["n_scripts"] != 1 or judged["n_scripts"] != 2:
            fails.append(f"adjudicate: a worktree deletion shrank the HEAD "
                         f"walk ({judged['n_scripts']}, expected 2) — the "
                         f"committed script is still everyone else's")
        if not judged["exposed"]:
            fails.append("adjudicate: a committed EXPOSED script deleted in "
                         "this worktree left the ceiling — MASKED is the "
                         "silent direction")

    # f. The PREMISE the key rests on: `analyse` answers at most ONE row per
    #    file, so no ordinal is needed. Remembered premises are how a key
    #    collapses silently; this one is measured against the real classifier.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, EXPOSED_SH + "\ntrap 'echo second' EXIT\n")
        got, _d, _j = run(repo)
        if len({r["file"] for r in got["rows"]}) != len(got["rows"]):
            fails.append(f"premise: a file produced more than one population "
                         f"row ({got['rows']}) — the key then needs an ordinal")

    # g. A clean tree must cost NOTHING: `head_delta` short-circuits before any
    #    `git show`, and the arm that bites is the one asserting zero rescans.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, SENTINEL_SH)
        # Counted at `head_text`, which is the COST itself (one `git show` per
        # dirty file), and not at `analyse_lines` — the worktree pass calls
        # that once per script legitimately, so an arm aimed there measures
        # the classifier working rather than the short-circuit holding.
        import worktree_state as _ws
        calls = []
        real = _ws.head_text
        _ws.head_text = lambda root, rel: calls.append(rel) or real(root, rel)
        try:
            got, delta, judged = run(repo)
        finally:
            _ws.head_text = real
        if calls:
            fails.append(f"adjudicate: re-classified a CLEAN repo "
                         f"({len(calls)} `git show` call(s)) — the common case "
                         f"must cost nothing at all")
        if delta.uncommitted or delta.masked or not delta.committed:
            fails.append(f"adjudicate: a clean tree's rows are not all "
                         f"COMMITTED ({delta})")
    return fails


def adjudicate_arms() -> list[str]:
    """The cases above, plus the STUB PROBE proving they sit on the seam.

    ⛔ Aimed at `head_delta` — the helper `adjudicate` ACTUALLY calls — because
    two of this family's first three probes reported a false all-clear by
    being aimed at a function the target never invokes. A `head_delta` that
    files every row as COMMITTED is the exact regression this wiring prevents.
    """
    fails = adjudicate_cases()
    real = globals()["head_delta"]
    globals()["head_delta"] = lambda root, pat, rows, p, k, rescan: HeadDelta(
        list(rows), [], [])
    try:
        probed = adjudicate_cases()
    finally:
        globals()["head_delta"] = real
    if len(probed) < 4:
        fails.append(f"STUB PROBE: a `head_delta` that files every row as "
                     f"COMMITTED red only {len(probed)} of the provenance "
                     f"arms — they are not sitting under the seam")
    return fails


def main() -> int:
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass  # not a TextIOWrapper (embedded / detached); keep old behavior

    # The classifier's own selftest FIRST. Without it a parser regression takes
    # every count to zero and this sweep certifies the workspace clean on the
    # strength of an instrument that has gone blind.
    blind = tela.selftest()
    if blind:
        print("✗ trap sweep SELFTEST FAILED — the classifier does not pass its own:")
        for f in blind:
            print(f)
        return 2

    fails = selftest()
    if fails:
        print("✗ trap sweep SELFTEST FAILED — instrument untrustworthy:")
        for f in fails:
            print(f"    {f}")
        return 2

    # The premise is measured, not quoted — and if THIS box launders nothing,
    # every EXPOSED row below is a finding about a premise that does not hold
    # here. Say so rather than printing the rows as though it did.
    # ⛔ Measured ONCE. The two comprehensions below used to call
    # `measure_premise()` separately, which runs 32 bash subprocesses twice
    # over for two views of one measurement — and, worse, lets the two lists
    # describe two different runs.
    #
    # ⛔ And `confirms_fix` is not the same question as `as_documented`: the
    # documented table is macOS /bin/bash 3.2.57, where five cells LAUNDER, and
    # every bash >= 4.4 preserves the status there. On such a box those five
    # SHOULD read differently, and reporting them as a divergence sends the
    # reader to edit a correct document. The classification lives in
    # trap_exit_launder_audit, not in a second copy here.
    premise = tela.measure_premise()
    dead = tela.premise_harness_alive()
    launders = [] if dead else [r for r in premise if r["launders"]]
    diverged = (
        []
        if dead
        else [r for r in premise if not r["as_documented"] and not r["confirms_fix"]]
    )
    confirms = [] if dead else [r for r in premise if r.get("confirms_fix")]

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

    names = tela.repos(str(WORKSPACE))
    if not names:
        print(f"✗ derived population is EMPTY under {WORKSPACE} — refusing to "
              f"report a green over zero repos")
        return 2

    # Same quantity, two files: this sweep re-states katgpt-rs's population
    # floor that the per-push gate owns. Asserted, not trusted — the pattern
    # docs_gate_paths_sync.py uses for the two trigger lists.
    mine = pins.get(REPO_ROOT.name, {}).get("min_population")
    if mine != tsg.POPULATION_FLOOR:
        print(f"✗ pin drift: {PINS.name} says min_population={mine} for "
              f"{REPO_ROOT.name}, trap_sentinel_gate.POPULATION_FLOOR is "
              f"{tsg.POPULATION_FLOOR}. Same quantity, two files — change both.")
        return 1

    bad = False
    tot = {"n_scripts": 0, "n_pop": 0, "replaced": 0,
           "launderable": 0, "errexit": 0}
    for name, _ in CLASSES:
        tot[name] = 0

    n_uncommitted = n_masked = 0
    for name in names:
        repo = open_repo(name, WORKSPACE)
        got = audit(repo)
        # Issue 822 — the DISPLAY reads the worktree (it is what the files say
        # today); every CEILING and both FLOORS read what a commit of this
        # checkout would produce.
        delta, judged = adjudicate(repo, got)
        held = {row_key(r) for r in delta.uncommitted}
        n_uncommitted += len(delta.uncommitted)
        n_masked += len(delta.masked)
        row = pins.get(name)
        tot["n_scripts"] += got["n_scripts"]
        tot["n_pop"] += got["n_pop"]
        tot["replaced"] += got["replaced"]
        tot["errexit"] += sum(1 for r in got["rows"] if r["errexit"])
        # The bottom line, per Issue 734 T10: unsentinelled AND with at least
        # one abort SITE in the window [last trap registration, EOF). A
        # zero-trigger window provably cannot launder.
        tot["launderable"] += sum(
            1 for r in got["rows"]
            if r["verdict"] in (tela.EXPOSED, tela.LIVE_FORWARD) and r["triggers"] > 0)
        for cls, _ in CLASSES:
            tot[cls] += len(got[cls])

        flags = []
        if row is None:
            # Issue 821: an acknowledged known-extra owes no pin row —
            # the marker reached population_verdict's FINAL line and not
            # this loop, so 8 of 9 sweeps red on repos they found
            # nothing in, hiding two live ratchet breaches.
            if not pin_row_exempt(name):
                flags.append("UNPINNED — add a row (or it can never red)")
        else:
            if judged["n_scripts"] < row["min_scripts"]:
                flags.append(f"walk FLOOR breached: {judged['n_scripts']} tracked "
                             f"*.sh < {row['min_scripts']} — scripts were "
                             f"removed, or walk_sh/git ls-files went blind")
            if judged["n_pop"] < row["min_population"]:
                flags.append(f"population FLOOR breached: {judged['n_pop']} < "
                             f"{row['min_population']} — a script lost its "
                             f"`set -e`/`set -u` or its EXIT trap, or the "
                             f"classifier stopped seeing them")
            for cls, _ in CLASSES:
                if len(judged[cls]) > row[f"max_{cls}"]:
                    flags.append(f"{cls} {len(judged[cls])} committed > pinned "
                                 f"{row[f'max_{cls}']}")
            if judged["replaced"] > row["max_replaced"]:
                flags.append(f"replaced {judged['replaced']} > pinned "
                             f"{row['max_replaced']}")

        findings = [r for cls, _ in CLASSES for r in got[cls]]
        status = "✗" if flags else ("·" if findings else "✓")
        split = ""
        if held or delta.masked:
            split = (f" [{len(delta.committed)} committed"
                     + (f", {len(held)} uncommitted" if held else "")
                     + (f", {len(delta.masked)} MASKED" if delta.masked else "")
                     + "]")
        if judged["n_scripts"] != got["n_scripts"]:
            split += f" [sh at HEAD={judged['n_scripts']}]"
        print(f"{status} {name:22s} sh={got['n_scripts']:<4d} pop={got['n_pop']:<3d} "
              f"exposed={len(got['exposed'])} precautionary="
              f"{len(got['precautionary'])} live_forward="
              f"{len(got['live_forward'])} unparsed={len(got['unparsed'])} "
              f"replaced={got['replaced']}{split}")
        for r in sorted(findings, key=lambda r: -r["triggers"]):
            inert = "  <- ZERO abort sites in the window: provably cannot launder" \
                if r["triggers"] == 0 else ""
            wip = " [UNCOMMITTED — not adjudicated]" if row_key(r) in held else ""
            print(f"      {r['file']}  {r['verdict']}  "
                  f"[window {r['window']} line(s), {r['triggers']} trigger(s)]"
                  f"{inert}{wip}")
        # A MASKED row is NOT in the worktree buckets — that is what MASKED
        # means — so it prints from the HEAD side or it prints nowhere, and a
        # ceiling reds over a script nobody can see. Printed for EVERY verdict,
        # not only the four gated ones: a file SENTINELLED here and EXPOSED at
        # HEAD is precisely the row somebody must look at.
        for r in sorted(delta.masked, key=lambda r: r["file"]):
            print(f"      ⛔ {r['file']}  {r['verdict']}  [MASKED — committed, "
                  f"hidden by this worktree]")
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
    # unless the dirty set meets this sweep's own population — the shell gates.
    deferred.extend(sweep_advisory(
        names, SCOPE, root=WORKSPACE,
        uncommitted_rows=n_uncommitted, masked_rows=n_masked))
    for _line in pop_lines:
        print(_line)
    if pop_fail:
        bad = True

    print(f"\n{len(names)} contract repo(s) · {tot['n_scripts']} tracked *.sh · "
          f"{tot['n_pop']} in population ({tot['errexit']} with errexit) · "
          f"{tot['exposed']} exposed · {tot['precautionary']} precautionary · "
          f"{tot['live_forward']} live-forward · {tot['unparsed']} unparsed · "
          f"{tot['replaced']} replaced")
    print(f"  bottom line: {tot['launderable']} script(s) are unsentinelled AND "
          f"have an abort site in the window — those are the only ones that can "
          f"report a PASS on an abort today.")
    # State the scope where it is READ, not only in the docstring.
    print("  scope: PRECAUTIONARY is nounset WITHOUT errexit — measured, those "
          "aborts exit 1, so it is not laundering today and is pinned "
          "separately rather than pooled into exposed.")
    if dead:
        print(f"  ⛔ PREMISE UNSEEN on this box — {dead}. The rows above are "
              "STATIC and stand on their own; only their SEVERITY is unmeasured "
              "here. Take the premise from a POSIX workstation.")
    elif not launders:
        why = (
            " — expected: the 3.2 LAUNDER cells are FIXED on this bash "
            f"({len(confirms)} of them confirmed)"
            if confirms
            else ""
        )
        print("  ⛔ this bash LAUNDERS NOTHING in any measured arm" + why + ". Every "
              "row above is about a premise that does not hold on this box. "
              "Re-read before acting.")
    if diverged:
        print(f"  ⛔ {len(diverged)} premise cell(s) DIVERGE from the documented "
              f"table, and NOT in the direction the bash-4.4 fix explains; "
              f"run trap_exit_launder_audit.py for the matrix.")

    if bad:
        print("✗ trap sentinel sweep FAILED — see the ✗ rows above")
        for _d in deferred:
            print(f"  {deferral_line(_d)}")
        print("    A gate that ABORTS mid-run reports exit 0. The repair is a "
              "completion sentinel; see scripts/full_gate.sh (full_gate_cleanup).")
        return 1
    _line = "✓ trap sentinel sweep PASSED — every repo at or under its pins"
    if deferred:
        _line += "; DEFERRED: " + "; ".join(deferred)
    print(_line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
