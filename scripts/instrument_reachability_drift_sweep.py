#!/usr/bin/env python3
"""The instrument-reachability verdict over every contract repo, PINNED.

Issue 787 T6. Shipping the gate without this would be the defect Issue 783
records — a rule landed in one instrument and never generalised — committed
inside the issue that exists *because* a census missed something. Twelve other
verdict classes here carry both halves, and the asymmetry in 783 was not a
judgement call that was made; it was a step that was skipped.

The class transfers because the premise does: every contract repo has its own
`AGENTS.md`, its own `scripts/`, and its own workflows, and every one is read
by agents who enumerate what the document names. The classifier is the gate's —
`collect()` and `reachable()`, imported, never restated — so the two can never
disagree about what "reachable" means.

⛔ The first measurement changed the pin design, and that is the finding
------------------------------------------------------------------------
Measured 2026-09-14 over 16 repos: **95 unreachable** of 152 tracked
`scripts/*.py`. riir-train alone is **61 of 61** — its `scripts/` is almost
entirely plan-scoped one-offs (`plan341_band_pool.py`,
`plan346_diversity_gate.py`, `t504_harvest.py`), and its `AGENTS.md` names none
of them.

Read that honestly: in riir-train the predicate **over-captures**. A plan
artifact is not an instrument, and "nobody can find it from AGENTS.md" is the
expected, correct state for a script whose whole life was one plan task. The
per-repo gate's membership pin — a row and a REASON for each — is right for the
repo that owns it; it is not right for the rows in the other fifteen repos,
whose judgement calls are not this repo's to make. (Both counts are printed by
the run — take them from its summary line, never from this paragraph.)

So the sweep is a **RATCHET**, not a membership set:

    max_unreachable   pinned at each repo's measured count

That is the strongest claim this repo can honestly make about somebody else's
tree, and it is still actionable at exactly the margin that matters: the commit
that adds ANOTHER unfindable script reds. It is deliberately NOT the
`suite_membership_audit` outcome (1,203 rows, report-only, no verdict at all) —
the objection there was that the rows are load-bearing test targets and no
per-commit action follows from the number. Here the action is immediate and
local: name it, invoke it from something named, or decide it is ephemeral.

⚠ And it is deliberately not the Issue 785 rule either. That rule forbids
ratcheting a bucket whose meaning is *unanswered*, because such a bucket is a
backlog with no owner. This bucket means *unfindable*, every row has an owner,
and the ratchet is on the DERIVATIVE — it constrains what lands next, not what
already landed.

Two floors, and in 6 of 16 repos neither bites
-----------------------------------------------
`min_scripts` catches the walk going blind. `min_roots` catches the permissive
direction: with fewer roots, MORE scripts read as unreachable — so a shrinking
root set inflates the finding count rather than hiding it, and the floor is
about the instrument, not the tree.

⚠ Six repos have **0 tracked `scripts/*.py`** (riir-auth, riir-game-sdk,
riir-kat, riir-neuron-db, riir-viewbridge, mmorpg-remaster), so both
quantities are 0 there and neither detects anything — Issue 783's population
shape, stated as a measurement rather than assumed. What rescues those rows is
that the gate's `DOC_ROOTS` handling is a REFUSAL and not a floor: a repo whose
`AGENTS.md` the walk cannot see is an instrument failure, not a clean zero.

`min_roots` also cannot be shared: it is 1 in riir-shader and 13 in katgpt-rs.

Why this is NOT in scripts/docs_gate.sh's CHECKS
------------------------------------------------
Identical to the other fourteen sweeps: CI has one checkout, the siblings are
private and simply absent, so this would either red on every run or derive an
EMPTY population and print a confident green over zero repos. The per-repo half
— `instrument_reachability_gate.py`, membership-pinned with a reason per row —
is the CI-side assertion.

Exit 0 clean, 1 on drift above the pins, **2 if the instrument itself is
untrustworthy**. `--canary` runs the adversary arms.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# DRY: the closure is the per-push gate's, so the sweep and the gate can never
# disagree about what "reachable" means.
import instrument_reachability_gate as irg  # noqa: E402

# The repo that owns the membership pin — derived, never typed.
SELF = irg.REPO_ROOT.name
from skill_repo_set_gate import derive_repos  # noqa: E402
from sweep_population import open_repo, population_verdict, pin_row_exempt  # noqa: E402
from worktree_state import (  # noqa: E402
    deferral_line, delta_of, head_overlay, sweep_advisory)

REPO_ROOT = HERE.parent
WORKSPACE = REPO_ROOT.parent
PINS = HERE / "instrument_reachability_floors.txt"

FIELDS = ("min_scripts", "min_roots", "max_unreachable")


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


def classify(repo: Path) -> tuple[list[str], list[str], list[str]]:
    """(scripts, roots, unreachable) — the gate's own closure, per repo."""
    scripts, roots = irg.collect(repo)
    unreached = sorted(set(scripts) - irg.reachable(repo, scripts, roots))
    return scripts, roots, unreached


# Everything that can CHANGE a verdict here, not just what findings sit on:
# the closure starts at the ROOTS, so a dirty `AGENTS.md` moves other scripts
# in and out of the unreachable set. Naming only `scripts/*.py` would overlay
# the findings and leave the cause reading the worktree.
SCOPE = (*irg.DOC_ROOTS, "scripts/*.py",
         *(irg.WORKFLOW_DIR + "/*" + sfx for sfx in irg.WORKFLOW_SUFFIXES))


def adjudicate(repo: Path, scripts: list[str], roots: list[str],
               unreached: list[str]):
    """The unreachable rows, split COMMITTED / UNCOMMITTED / MASKED.

    Issue 822. The DISPLAY reads the worktree; the PINS read `.head`. This is
    the CROSS-FILE half of T2 — `head_delta`'s per-file shortcut is unsound for
    a transitive closure, so the classifier re-runs whole with HEAD's bytes
    overlaid on the dirty files, and `delta_of` compares the two complete sets.

    Cost: one extra closure over a repo whose population is already walked,
    and ONLY when something in `SCOPE` is dirty. An empty overlay short-circuits
    — a helper that re-classifies on every clean run is one that stops being
    called.
    """
    overlay = head_overlay(repo, SCOPE)
    if not overlay:
        return delta_of(unreached, unreached, lambda r: r)

    def read(_repo, rel, _o=overlay):
        # `in` and `.get()` say different things: None means TRACKED BUT NOT IN
        # HEAD — a staged-but-never-committed file, Issue 822's measured case —
        # and it must read as absent, not as the worktree's bytes.
        if rel in _o:
            return _o[rel] or ""
        return irg.read(_repo, rel)

    # The POPULATION moves too, which a row-level read alone misses (Issue
    # 797): a staged-only script is in `git ls-files` and in no commit, so it
    # is not part of what HEAD would report and cannot be an unreachable row
    # there. Same for a root.
    absent = {rel for rel, src in overlay.items() if src is None}
    head_scripts = [p for p in scripts if p not in absent]
    head_roots = [r for r in roots if r not in absent]
    head_unreached = sorted(
        set(head_scripts) - irg.reachable(repo, head_scripts, head_roots,
                                          read=read))
    return delta_of(unreached, head_unreached, lambda r: r)


def selftest() -> list[str]:
    fails: list[str] = []

    # The gate's own arms cover the closure; INVOKING them here is what makes
    # "shared classifier" an assertion rather than an import statement.
    fails += [f"gate selftest: {f}" for f in irg.selftest()]
    for attr in ("collect", "reachable", "DOC_ROOTS"):
        if not hasattr(irg, attr):
            fails.append(f"gate lost `{attr}` — the sweep shares its closure "
                         f"and must not fall back to a copy")

    # katgpt-rs's own two floors are the gate's constants, not this file's
    # opinion — same quantity, two files, which is the drift `docs_gate_paths_
    # sync.py` exists for one axis over.
    if PINS.is_file():
        try:
            mine = parse_pins(PINS).get(REPO_ROOT.name, {})
        except ValueError as e:
            fails.append(f"own pins unreadable: {e}")
            mine = {}
        for field, owned in (("min_scripts", irg.MIN_SCRIPTS),
                             ("min_roots", irg.MIN_ROOTS)):
            if mine and mine.get(field) != owned:
                fails.append(
                    f"pin drift: {PINS.name} says {field}={mine.get(field)} for "
                    f"{REPO_ROOT.name}, the gate owns {owned} — change both")

    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        p = ws / "p.txt"
        p.write_text("# c\nrepo-a 40 8 7  # trailing\n\n", encoding="utf-8")
        if parse_pins(p) != {"repo-a": dict(zip(FIELDS, (40, 8, 7)))}:
            fails.append("pin parse: 4-field row not read correctly")
        p.write_text("repo-a 1 2\n", encoding="utf-8")
        try:
            parse_pins(p)
            fails.append("pin parse: short row accepted")
        except ValueError:
            pass

    return fails + adjudicate_arms()


def adjudicate_arms() -> list[str]:
    """`adjudicate`, two-sided, against a real git tree.

    UNCOMMITTED alone passes on an implementation that ignores HEAD and MASKED
    alone on one that ignores the worktree, so both directions are asserted —
    and the third arm is the one a row-level read alone misses: the POPULATION
    moves too (Issue 797 measured `n_cites` 601 vs 607 for exactly this).
    """
    fails: list[str] = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    def git(cwd, *args):
        subprocess.run(["git", "-C", str(cwd), *args], check=True,
                       capture_output=True)

    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "r"
        (repo / "scripts").mkdir(parents=True)
        git(repo.parent, "init", "-q", "-b", "main", "r")
        git(repo, "config", "user.email", "t@t")
        git(repo, "config", "user.name", "t")
        # AGENTS.md is a ROOT, so its bytes decide OTHER files' verdicts —
        # which is the whole reason this sweep cannot use the per-file
        # shortcut.
        (repo / "AGENTS.md").write_text("run scripts/a.py and scripts/b.py\n",
                                        encoding="utf-8")
        (repo / "scripts/a.py").write_text("a\n", encoding="utf-8")
        (repo / "scripts/b.py").write_text("b\n", encoding="utf-8")
        (repo / "scripts/c.py").write_text("c\n", encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "base")

        def now():
            sc, ro, un = classify(repo)
            return sc, ro, un, adjudicate(repo, sc, ro, un)

        sc, ro, un, d = now()
        check(un == ["scripts/c.py"], f"fixture: unreachable={un}, want c only")
        check(not d.uncommitted and not d.masked,
              f"a clean tree produced a split: {d}")

        # ── UNCOMMITTED: an uncommitted ROOT edit invents a finding ─────────
        (repo / "AGENTS.md").write_text("run scripts/a.py\n", encoding="utf-8")
        sc, ro, un, d = now()
        check(un == ["scripts/b.py", "scripts/c.py"],
              f"the worktree edit did not strand b.py: {un}")
        check([r for r in d.uncommitted] == ["scripts/b.py"],
              f"UNCOMMITTED direction: {d.uncommitted}")
        check(not d.masked, f"an invented row was also MASKED: {d.masked}")
        check(sorted(d.head) == ["scripts/c.py"],
              f"the pins' view is not HEAD's own answer: {d.head}")

        # ── MASKED: an uncommitted ROOT edit HIDES a committed finding ──────
        (repo / "AGENTS.md").write_text(
            "run scripts/a.py and scripts/b.py and scripts/c.py\n",
            encoding="utf-8")
        sc, ro, un, d = now()
        check(un == [], f"the worktree edit did not reach c.py: {un}")
        check([r for r in d.masked] == ["scripts/c.py"],
              f"MASKED direction — a committed row the worktree hides: "
              f"{d.masked}")
        check(sorted(d.head) == ["scripts/c.py"],
              f"a MASKED row is missing from the pins' view: {d.head}")

        # ── the POPULATION moves too ────────────────────────────────────────
        # A STAGED-only script is in `git ls-files` and in NO commit, so HEAD
        # cannot report it as unreachable. Counting it would adjudicate another
        # session's in-flight file against a tracked ceiling.
        git(repo, "checkout", "--", "AGENTS.md")
        (repo / "scripts/staged.py").write_text("s\n", encoding="utf-8")
        git(repo, "add", "scripts/staged.py")
        sc, ro, un, d = now()
        check("scripts/staged.py" in sc,
              "the fixture's staged file is not in the walk")
        check("scripts/staged.py" in un,
              f"the worktree did not report the staged file: {un}")
        check("scripts/staged.py" in d.uncommitted,
              f"a staged-only script was adjudicated: {d.uncommitted}")
        check("scripts/staged.py" not in d.head,
              f"a file in no commit entered the pins' view: {d.head}")

    return fails


def canary() -> int:
    """Perturb each axis and REQUIRE a red. See the gate's `canary()` for why
    this is a flag and not a transcript."""
    import contextlib
    import io

    global PINS, classify, adjudicate

    td = Path(tempfile.mkdtemp())
    pins_src = PINS.read_text(encoding="utf-8")
    real_pins = PINS
    real_classify = classify
    real_adjudicate = adjudicate
    results = []

    fails = selftest()
    if fails:
        print("✗ SELFTEST FAILED before the canary — untrustworthy:")
        for f in fails:
            print(f"    {f}")
        return 2

    def arm(name, want_rc, want_text, pins=None, classify_fn=None,
            adjudicate_fn=None):
        global PINS, classify, adjudicate
        PINS = td / "p.txt"
        PINS.write_text(pins if pins is not None else pins_src, encoding="utf-8")
        classify = classify_fn or real_classify
        adjudicate = adjudicate_fn or real_adjudicate
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                rc = main([], run_selftest=False)
        finally:
            PINS = real_pins
            classify = real_classify
            adjudicate = real_adjudicate
        out = buf.getvalue()
        ok = rc == want_rc and want_text in out
        print(f"  {'✓' if ok else '✗'} {name}  (rc={rc}, want {want_rc})")
        if not ok:
            print(f"        wanted: {want_text}")
            for ln in [l for l in out.splitlines() if l.startswith(("✗", "⛔"))][:3]:
                print(f"        got: {ln}")
        results.append(ok)

    def bump(field_idx, delta):
        """Rewrite katgpt-rs's row, one field, by delta. Anchored on the row
        rather than on a literal, so the arm cannot silently stop perturbing
        when the pin is re-measured — the Issue 786 canary failure."""
        out = []
        hit = False
        for raw in pins_src.splitlines(keepends=True):
            body = raw.split("#", 1)[0]
            parts = body.split()
            if len(parts) == 1 + len(FIELDS) and parts[0] == REPO_ROOT.name:
                parts[1 + field_idx] = str(int(parts[1 + field_idx]) + delta)
                out.append("  ".join(parts) + "\n")
                hit = True
            else:
                out.append(raw)
        if not hit:
            raise AssertionError(f"canary: no {REPO_ROOT.name} row to perturb")
        return "".join(out)

    def hold(n=1):
        """Issue 822: the same ghost rows, but UNCOMMITTED — on a file that
        differs from HEAD, so no commit contains the finding."""
        def fn(repo, scripts, roots, unreached):
            d = real_adjudicate(repo, scripts, roots, unreached)
            if repo.resolve() != REPO_ROOT:
                return d
            ghosts = [f"scripts/ghost{i}.py" for i in range(n)]
            return type(d)([r for r in d.committed if r not in ghosts],
                           list(d.uncommitted) + ghosts, list(d.masked))
        return fn

    def hide(n=1):
        """And the silent direction: HEAD carries rows this worktree does not.
        They are NOT in `unreached` — that is what MASKED means — so a run
        adjudicating the worktree reports this repo clean."""
        def fn(repo, scripts, roots, unreached):
            d = real_adjudicate(repo, scripts, roots, unreached)
            if repo.resolve() != REPO_ROOT:
                return d
            return type(d)(list(d.committed), list(d.uncommitted),
                           list(d.masked)
                           + [f"scripts/hidden{i}.py" for i in range(n)])
        return fn

    def ghost(repo):
        t = real_classify(repo)
        if repo.resolve() != REPO_ROOT:
            return t
        return (t[0] + ["scripts/ghost0.py"], t[1],
                t[2] + ["scripts/ghost0.py"])

    arm("baseline green", 0, "sweep PASSED")
    arm("new unreachable reds", 1, "unreachable ", classify_fn=ghost)
    # ⛔ The pair that IS Issue 822: ONE row, two provenances, opposite
    # verdicts. Injected into `classify` alone it reds (above); the same row
    # held as UNCOMMITTED must NOT, or the pins are reading the worktree.
    arm("an UNCOMMITTED row does NOT breach the ratchet", 0, "sweep PASSED",
        classify_fn=ghost, adjudicate_fn=hold())
    arm("...and is still SHOWN, never hidden", 0, "UNCOMMITTED: 1 row(s)",
        classify_fn=ghost, adjudicate_fn=hold())
    # T4: MASKED is the silent direction — a committed row the worktree hides.
    # It reds WITHOUT appearing in `unreached` at all, and two DISPLAYS need
    # two arms: the row label says which, the final line says the class exists.
    arm("a MASKED row reds though the worktree is clean", 1, "> pinned",
        adjudicate_fn=hide())
    arm("...and is labelled at the ROW", 1, "[MASKED", adjudicate_fn=hide())
    arm("...and is counted on the ADVISORY line", 1, "MASKED: 1 row(s)",
        adjudicate_fn=hide())
    arm("walk floor reds", 1, "walk FLOOR breached", pins=bump(0, 10_000))
    arm("roots floor reds", 1, "roots FLOOR breached", pins=bump(1, 10_000))
    arm("ratchet reds", 1, "> pinned", pins=bump(2, -1))
    arm("unpinned repo reds", 1, "UNPINNED",
        pins="".join(l for l in pins_src.splitlines(keepends=True)
                     if not l.split("#", 1)[0].split()[:1]
                     or l.split("#", 1)[0].split()[0] != REPO_ROOT.name))
    arm("empty pins refused", 2, "declares NO repos", pins="# nothing\n")
    arm("short row refused", 2, "unreadable", pins="repo-a 1 2\n")

    print(f"\n{sum(results)}/{len(results)} canary arm(s) PASSED")
    return 0 if all(results) else 2


def main(argv: list[str], run_selftest: bool = True) -> int:
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass

    if "--canary" in argv:
        return canary()

    fails = selftest() if run_selftest else []
    if fails:
        print("✗ instrument-reachability sweep SELFTEST FAILED — untrustworthy:")
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

    bad = False
    tot_s = tot_r = tot_u = 0
    n_uncommitted = n_masked = 0
    per_repo: dict[str, tuple[int, int]] = {}

    for name in names:
        repo = open_repo(name, WORKSPACE)
        scripts, roots, unreached = classify(repo)

        # ── Issue 822: the DISPLAY reads the worktree, the PINS read HEAD ───
        # A ratchet is a claim about the repo, and a repo's state is its
        # commits. This workspace runs concurrent sessions against shared
        # worktrees, so a row here may sit on a file no commit contains — and
        # re-pinning from such a run bakes another session's in-flight edit
        # into a tracked file, where it reds on every other box.
        delta = adjudicate(repo, scripts, roots, unreached)
        n_uncommitted += len(delta.uncommitted)
        n_masked += len(delta.masked)

        tot_s += len(scripts)
        tot_r += len(roots)
        tot_u += len(unreached)
        per_repo[name] = (len(scripts), len(unreached))

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
            if len(scripts) < row["min_scripts"]:
                flags.append(f"walk FLOOR breached: {len(scripts)} tracked "
                             f"scripts/*.py < {row['min_scripts']} — the walk "
                             f"went blind and the count below means nothing")
            if len(roots) < row["min_roots"]:
                flags.append(f"roots FLOOR breached: {len(roots)} < "
                             f"{row['min_roots']} — with fewer roots MORE "
                             f"scripts read as unreachable, so this floor is "
                             f"about the instrument, not the tree")
            if len(delta.head) > row["max_unreachable"]:
                flags.append(f"unreachable {len(delta.head)} committed > "
                             f"pinned {row['max_unreachable']} — a new script "
                             f"that no root and no documented instrument names")
                held, hidden = set(delta.uncommitted), set(delta.masked)
                for p in sorted(set(delta.head) | set(unreached)):
                    # Never hidden — hiding them is the lie Issue 797 refuses —
                    # but labelled, so the reader can see which rows the pin
                    # did and did not adjudicate.
                    tag = ("  [UNCOMMITTED — not adjudicated]" if p in held
                           else "  [MASKED — committed, and this worktree "
                                "hides it]" if p in hidden else "")
                    print(f"      ⛔ {name}/{p}{tag}")

        status = "✗" if flags else ("·" if unreached else "✓")
        # T3: the count stays honest in BOTH directions. A bare total invites
        # the one action Issue 822 exists to prevent — typing it into the pin.
        split = ""
        if delta.uncommitted or delta.masked:
            split = (f" ({len(delta.head)} committed"
                     + (f" + {len(delta.uncommitted)} uncommitted"
                        if delta.uncommitted else "")
                     + (f", {len(delta.masked)} MASKED" if delta.masked else "")
                     + ")")
        print(f"{status} {name:22s} scripts={len(scripts):<3d} "
              f"roots={len(roots):<3d} unreachable={len(unreached)}{split}")
        for f in flags:
            bad = True
            print(f"      ✗ {f}")

    pop_lines, deferred, pop_fail = population_verdict(pins, names)

    # Issue 797 — the worktree is not the repo. This run reads files that
    # concurrent sessions are editing, so a finding may sit on a line no
    # commit contains. ADVISORY, never a failure: a sweep that hard-reds on
    # an ordinary dirty worktree is a sweep nobody runs. It rides the FINAL
    # line in BOTH directions (the `deferred` precedent) and is SILENT
    # unless the dirty set meets this sweep's own population — the scripts
    # walked plus every ROOT the closure starts from.
    #
    # ⛔ `SCOPE`, not a second hand-typed list. The one that was here named
    # `.yml` and not `.yaml`, so a dirty `.yaml` workflow — a root, able to
    # move scripts in and out of the unreachable set — was silently out of
    # scope. Same quantity, two places: `docs_gate_paths_sync.py` one axis over.
    deferred.extend(sweep_advisory(names, SCOPE, root=WORKSPACE,
                                   uncommitted_rows=n_uncommitted,
                                   masked_rows=n_masked))
    for _line in pop_lines:
        print(_line)
    if pop_fail:
        bad = True

    print(f"\n{len(names)} contract repo(s) · {tot_s} tracked scripts/*.py · "
          f"{tot_r} root(s) · {tot_u} unreachable")
    # ⛔ Every figure in this paragraph is DERIVED from the run above. The
    # first version typed them, and on 2026-09-15 it printed "95 rows across
    # 15 repos" directly beneath its own measured "94 unreachable" — a number
    # contradicting the line above it, in a sweep whose whole subject is
    # records drifting away from what they describe. The typed pair was
    # never right either: it read the workspace TOTAL as the
    # everyone-else count and 16-minus-self as the number of repos actually
    # carrying rows.
    own = per_repo.get(SELF, (0, 0))[1]
    others = [(n, sc, u) for n, (sc, u) in per_repo.items() if n != SELF and u]
    n_other_rows = sum(u for _, _, u in others)
    top = max(others, key=lambda t: t[2], default=None)
    top_txt = (f", and in {top[0]} ({top[2]} of {top[1]}) the predicate "
               f"OVER-CAPTURES — a plan-scoped one-off is not an instrument"
               if top else "")
    print(f"  the ceiling is a RATCHET, not a wall, and only here: this "
          f"repo's own {own} row(s) are pinned by MEMBERSHIP with a reason "
          f"each in instrument_reachability_gate.py. {n_other_rows} row(s) "
          f"across {len(others)} other repo(s) carrying any are not this "
          f"repo's judgement calls to make{top_txt}. The ratchet constrains "
          f"what lands NEXT.")

    if bad:
        print("✗ instrument-reachability sweep FAILED — see the ✗ rows above")
        for _d in deferred:
            print(f"  {deferral_line(_d)}")
        return 1
    _line = "✓ instrument-reachability sweep PASSED — every repo within its pins"
    if deferred:
        _line += "; DEFERRED: " + "; ".join(deferred)
    print(_line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
