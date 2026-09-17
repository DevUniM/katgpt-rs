#!/usr/bin/env python3
"""The console-encoding verdict over every contract repo, PINNED (Issue 804).

Issue 804 shipped the per-push gate and wrote the cross-repo axis down as
**"⚠ Unmeasured, deliberately"** — the population plainly generalises, but the
*exposure* needs a non-UTF-8 console and this workstation is the only box in
the workspace known to have one. That was the right thing to write and the
wrong place to stop: `check_validation_gate`'s Issue 789 T4 precedent is to
**re-measure the population before answering**, and 789's answer ("no sweep")
was earned by a measurement that returned ONE.

This one returns seven repos. Measured 2026-09-16 over the 16 repos on this
box: **144 in-population instruments, 73 defended, 71 NOT** —

    riir-train           53 of 53 undefended
    riir-clippy           5 of  5
    riir-ai               4 of  5
    mmorpg-remake           4 of  4
    mmorpg-editor      3 of  3
    riir-dapps            1 of  1
    riir-mmorpg-examples  1 of  1
    katgpt-rs             0 of 72   ← the gate landed here and nowhere else

So the asymmetry was not a judgement call that was made; it was a step that was
skipped — this repo's standing failure mode, recorded ten times now (Issues
777, 778, 793, 782, 783, 789, 797, 785, 804).

⚠ The exposure caveat SURVIVES the measurement, and it is why the ceiling is a
ratchet
--------------------------------------------------------------------------
A cp874 console is this box's property, not riir-train's. And riir-train's 53
rows are the same over-capture `instrument_reachability_drift_sweep` measured
on the identical population: that repo's `scripts/` is almost entirely
plan-scoped one-offs (`plan335_t7_decide.py`, `plan346_doc_pool.py`), 61 of 61
unreachable from its own AGENTS.md. Retro-fitting a stream defence to a script
whose whole life was one plan task is churn, and it is not this repo's call to
make in somebody else's tree.

What IS this repo's call is the derivative. So, exactly as Issue 787 T6
resolved the same shape:

    max_undefended   pinned at each repo's measured count — the commit that
                     adds ANOTHER undefended instrument reds

and the action on a red is immediate and local: one line
(`console_safe.apply()` here, the inline `reconfigure(errors=…)` anywhere
else — both are credited, because the property asserted is *the streams are
defended*, never *this function was called*).

⚠ Deliberately NOT the Issue 785 rule's target. That rule forbids ratcheting a
bucket whose meaning is *unanswered*. This bucket means *undefended*, every row
has an owner, and every row is one line from being closed.

Three floors, and in most repos none of them bites
--------------------------------------------------
    min_scripts      the WALK — a glob that matches nothing
    min_population   the PREDICATE — `__main__` + a non-ASCII STRING literal.
                     Separate from the walk because they break separately: an
                     `ast.parse` regression takes the population to 0 over an
                     unchanged walk, and then every ceiling passes.
    max_undefended   the RATCHET

⚠ HALF the population has **0 in-population instruments** (riir-auth, riir-chain,
riir-game-sdk, riir-kat, riir-neuron-db, riir-shader, riir-viewbridge,
mmorpg-remaster — and two of those, riir-chain and riir-shader, have
`scripts/*.py` that simply print nothing non-ASCII). Both quantities are 0
there and neither detects anything — Issue 783's population shape, stated as a
measurement rather than assumed. `min_scripts` is the ONLY blindness detector
in riir-chain and riir-shader, and it is vacuous in the seven with no
`scripts/` at all; nothing rescues those rows, which is the honest thing to
print rather than a floor that pretends.

katgpt-rs's `min_population` is NOT free — it must equal
`console_encoding_gate.MIN_POPULATION`, and the selftest ASSERTS that rather
than trusting it. Same quantity, two files; `docs_gate_paths_sync.py` one axis
over.

Why this is NOT in scripts/docs_gate.sh's CHECKS
------------------------------------------------
Identical to the other sweeps: CI has one checkout, the siblings are private
and simply absent, so this would either red on every run or derive an EMPTY
population and print a confident green over zero repos. The per-repo half —
`console_encoding_gate.py`, membership-pinned with a reason per row and a
deliberately EMPTY pin file — is the CI-side assertion.

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

import console_safe  # noqa: E402

console_safe.apply()

# DRY: the classifier is the per-push gate's — `tracked_scripts`,
# `in_population`, `is_defended`, imported and never restated — so the two can
# never disagree about what "defended" means.
import console_encoding_gate as ceg  # noqa: E402
from skill_repo_set_gate import derive_repos  # noqa: E402
from sweep_population import population_verdict, pin_row_exempt  # noqa: E402
from worktree_state import head_delta, sweep_advisory  # noqa: E402

# The repo that owns the membership pin — derived, never typed.
SELF = ceg.REPO_ROOT.name

REPO_ROOT = HERE.parent
WORKSPACE = REPO_ROOT.parent
PINS = HERE / "console_encoding_drift_floors.txt"

FIELDS = ("min_scripts", "min_population", "max_undefended")


def parse_pins(path: Path) -> dict[str, dict[str, int]]:
    rows: dict[str, dict[str, int]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 1 + len(FIELDS):
            # ⚠ arm_reach: the `1 + len(FIELDS)` in the MESSAGE is this
            # module's only live survivor (`+ -> -`, measured 16 killed / 1
            # survived of 22). EQUIVALENT — message-formatting arithmetic
            # changes no verdict, which is one of the three legitimate survivor
            # classes AGENTS.md names. The one in the TEST above is killed.
            raise ValueError(
                f"malformed pin row (want {1 + len(FIELDS)} fields): {raw!r}")
        rows[parts[0]] = dict(zip(FIELDS, (int(v) for v in parts[1:])))
    return rows


def classify(repo: Path) -> tuple[int, list[str], list[str], list[str]]:
    """(n_walk, defended, undefended, unparsed) — the gate's own closure.

    UNPARSED is never folded into either answer: a module `ast.parse` cannot
    read is the instrument admitting it cannot see, and counting it as defended
    would hide exposure while counting it as undefended would invent it.
    """
    names = ceg.tracked_scripts(repo)
    defended: list[str] = []
    undefended: list[str] = []
    unparsed: list[str] = []
    for name in names:
        p = repo / "scripts" / name
        if not p.is_file():
            continue
        try:
            src = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            # A path git tracks that the tree cannot read is a BLIND READ, not
            # a clean row (bench_doc_audit's Issue 790 F9 rule). It reaches the
            # floors as a missing script rather than as a silent pass.
            continue
        member = ceg.in_population(src)
        if member is None:
            unparsed.append(name)
            continue
        if not member:
            continue
        (defended if ceg.is_defended(src) else undefended).append(name)
    return len(names), defended, undefended, unparsed



def head_undefended(repo: Path, walk: set[str]):
    """`head_delta`'s per-file reclassifier for THIS sweep's ceiling.

    Issue 822. The ratchet is a claim about the repo, and a repo's state is its
    commits — but `classify` above reads the working tree, which in this
    workspace is shared with concurrent sessions. The measured breach was
    `undefended 56 > pinned 53` where one of the three new rows sat on a file
    `git log` could not see at all, staged by another session mid-commit.

    Per-file row independence holds here by construction: `in_population` and
    `is_defended` are pure functions of ONE module's source, so the cheap
    shortcut `head_delta` documents is sound and costs |dirty ∩ scripts/*.py|
    `git show` calls — zero on an ordinary run.

    `walk` is the sweep's OWN population (`tracked_scripts`), passed in rather
    than recomputed: `fnmatch`'s `*` crosses `/`, so the scope globs admit the
    nested `scripts/kimi_ref/…` reference dumps that `tracked_scripts`
    deliberately excludes, and a row invented there would read as MASKED —
    a hard red nobody can repair.
    """

    def rescan(rel: str, src: str | None) -> list[str]:
        name = rel.rsplit("/", 1)[-1]
        # None = absent from HEAD (a STAGED-but-never-committed file): there is
        # nothing committed to classify, so it yields no row and the worktree's
        # row is UNCOMMITTED.
        if src is None:
            return []
        # `tracked_scripts`'s own two rules, restated at the only other place
        # a path enters this sweep's population — and they are INDEPENDENT, so
        # each has its own arm. `fnmatch`'s `*` crosses `/`, so the scope glob
        # `scripts/*.py` admits `scripts/kimi_ref/dump.py`, whose directory is
        # the boundary; and the walk is what git TRACKS, so a scratch copy is
        # not a member. A row invented either way reads as MASKED, which is a
        # hard red nobody can repair.
        if rel.count("/") != 1:
            return []
        if name not in walk:
            return []
        member = ceg.in_population(src)
        # UNPARSED (None) and out-of-population (False) are both "not an
        # undefended row" here, and neither is folded into the answer — the
        # same rule `classify` states one function up.
        if not member or ceg.is_defended(src):
            return []
        return [name]

    return rescan


def adjudicate(repo: Path, undefended: list[str]):
    """The worktree's undefended rows, split COMMITTED / UNCOMMITTED / MASKED.

    A named seam rather than four lines inline, for the reason `arm_reach`
    keeps finding in this repo: verdict arithmetic that sits inside `main()`
    beside its own error messages is unreachable by construction, and this is
    the arithmetic Issue 822 exists to get right. The canary monkeypatches it
    exactly as it monkeypatches `classify`.
    """
    return head_delta(
        repo, ("scripts/*.py",), undefended,
        lambda n: "scripts/" + n, lambda n: n,
        head_undefended(repo, set(ceg.tracked_scripts(repo))))


def selftest() -> list[str]:
    fails: list[str] = []

    # The gate's own arms cover the classifier; INVOKING them here is what
    # makes "shared classifier" an assertion rather than an import statement.
    fails += [f"gate selftest: {f}" for f in ceg.selftest()]
    for attr in ("tracked_scripts", "in_population", "is_defended",
                 "MIN_POPULATION"):
        if not hasattr(ceg, attr):
            fails.append(f"gate lost `{attr}` — the sweep shares its closure "
                         f"and must not fall back to a copy")

    # katgpt-rs's population floor is the gate's constant, not this file's
    # opinion — same quantity, two files.
    if PINS.is_file():
        try:
            mine = parse_pins(PINS).get(SELF, {})
        except ValueError as e:
            fails.append(f"own pins unreadable: {e}")
            mine = {}
        if mine and mine.get("min_population") != ceg.MIN_POPULATION:
            fails.append(
                f"pin drift: {PINS.name} says min_population="
                f"{mine.get('min_population')} for {SELF}, the gate owns "
                f"{ceg.MIN_POPULATION} — change both")
        # The gate's own wall. A katgpt-rs ratchet above 0 would silently
        # contradict the membership pin the per-push gate enforces.
        if mine and mine.get("max_undefended") != 0:
            fails.append(
                f"pin drift: {SELF} max_undefended="
                f"{mine.get('max_undefended')}, but the per-push gate walls it "
                f"at 0 by MEMBERSHIP — a ratchet here would let a row land "
                f"that the gate refuses")

    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        p = ws / "p.txt"
        p.write_text("# c\nrepo-a 40 30 7  # trailing\n\n", encoding="utf-8")
        if parse_pins(p) != {"repo-a": dict(zip(FIELDS, (40, 30, 7)))}:
            fails.append("pin parse: 4-field row not read correctly")
        p.write_text("repo-a 1 2\n", encoding="utf-8")
        try:
            parse_pins(p)
            fails.append("pin parse: short row accepted")
        except ValueError:
            pass

        # classify() over a synthetic repo, both directions plus UNPARSED —
        # the bucket boundaries ARE the finding (the wasm32 sweep's rule), and
        # they are only testable against a tree whose answer is known.
        fake = ws / "fakerepo" / "scripts"
        fake.mkdir(parents=True)
        (fake / "bare.py").write_text(ceg.GLYPH + ceg.MAIN, encoding="utf-8")
        (fake / "inline.py").write_text(ceg.INLINE + ceg.MAIN, encoding="utf-8")
        (fake / "helper.py").write_text(ceg.HELPER + ceg.MAIN, encoding="utf-8")
        (fake / "plain.py").write_text(ceg.ASCII_ONLY + ceg.MAIN,
                                       encoding="utf-8")
        (fake / "broken.py").write_text('print("✓"\nif __name__ == '
                                        '"__main__":\n    main()\n',
                                        encoding="utf-8")
        n, dfd, und, unp = classify(ws / "fakerepo")
        if n != 5:
            fails.append(f"classify: walk saw {n} scripts, want 5")
        if sorted(dfd) != ["helper.py", "inline.py"]:
            fails.append(f"classify: defended={sorted(dfd)}, want inline+helper")
        if und != ["bare.py"]:
            fails.append(f"classify: undefended={und}, want ['bare.py']")
        if unp != ["broken.py"]:
            fails.append(f"classify: unparsed={unp}, want ['broken.py']")
        if "plain.py" in dfd or "plain.py" in und:
            fails.append("classify: an ASCII-only module entered the population")

        # ── Issue 822: the per-file HEAD reclassifier ──────────────────────
        # `classify` reads the tree; this reads one file's COMMITTED bytes. The
        # two must agree about what "undefended" means (they share `ceg`), and
        # disagree about nothing else.
        walk = {"bare.py", "inline.py", "plain.py", "broken.py"}
        rescan = head_undefended(ws / "fakerepo", walk)
        if rescan("scripts/bare.py", ceg.GLYPH + ceg.MAIN) != ["bare.py"]:
            fails.append("head_undefended: an undefended module yielded no row")
        if rescan("scripts/inline.py", ceg.INLINE + ceg.MAIN) != []:
            fails.append("head_undefended: a DEFENDED module yielded a row")
        if rescan("scripts/plain.py", ceg.ASCII_ONLY + ceg.MAIN) != []:
            fails.append("head_undefended: an out-of-population module yielded "
                         "a row")
        # A STAGED-but-never-committed file — the measured case. There is
        # nothing committed to classify, and inventing a row here would report
        # another session's in-flight file as a committed finding.
        if rescan("scripts/bare.py", None) != []:
            fails.append("head_undefended: a file absent from HEAD yielded a "
                         "row")
        # UNPARSED is not undefended, in EITHER direction: counting it would
        # invent exposure, and `classify` keeps its own bucket for it.
        # DRY by construction: the arm reads the very fixture `classify`
        # just bucketed as UNPARSED, so the two halves of this sweep
        # cannot come to disagree about what UNPARSED means.
        if rescan("scripts/broken.py",
                  (fake / "broken.py").read_text(encoding="utf-8")) != []:
            fails.append("head_undefended: an UNPARSED module yielded a row")
        # ⛔ The NESTED rule, on a basename that IS a walk member — otherwise
        # the membership test rejects the row and this arm asserts nothing.
        if rescan("scripts/kimi_ref/bare.py", ceg.GLYPH + ceg.MAIN) != []:
            fails.append("head_undefended: a NESTED reference dump entered the "
                         "population the sweep's own walk excludes")
        # ⛔ ...and the MEMBERSHIP rule, on a top-level path — otherwise the
        # nested test rejects it and this one asserts nothing either. An
        # untracked scratch copy in `scripts/` is not a member of the contract.
        if rescan("scripts/scratch.py", ceg.GLYPH + ceg.MAIN) != []:
            fails.append("head_undefended: an untracked scratch copy entered "
                         "the population git says it is not in")

    # ⛔ The canary's split arms MONKEYPATCH `adjudicate`, so nothing there
    # reaches its body — measured: 14/14 pass with `head_delta` stubbed.
    return fails + adjudicate_arms()


def adjudicate_arms() -> list[str]:
    """`adjudicate`, two-sided, against a real git tree.

    The canary's split arms monkeypatch this function, so they cannot reach its
    body. These are the arms that red when `head_delta` is stubbed — measured,
    because the canary alone does not.
    """
    fails: list[str] = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    def git(cwd, *args):
        subprocess.run(["git", "-C", str(cwd), *args], check=True,
                       capture_output=True)

    UNDEF = ceg.GLYPH + ceg.MAIN          # in population, streams undefended
    DEF = ceg.INLINE + ceg.MAIN           # in population, defended

    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "r"
        (repo / "scripts").mkdir(parents=True)
        git(repo.parent, "init", "-q", "-b", "main", "r")
        git(repo, "config", "user.email", "t@t")
        git(repo, "config", "user.name", "t")
        (repo / "scripts/bad.py").write_text(UNDEF, encoding="utf-8")
        (repo / "scripts/good.py").write_text(DEF, encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "base")

        def now():
            _n, _d, und, _u = classify(repo)
            return und, adjudicate(repo, und)

        und, d = now()
        check(und == ["bad.py"], f"fixture: undefended={und}, want bad.py")
        check(d.committed == ["bad.py"] and not d.uncommitted and not d.masked,
              f"a clean tree produced a split: {d}")

        # ── UNCOMMITTED: the worktree INVENTS an undefended instrument ──────
        (repo / "scripts/good.py").write_text(UNDEF, encoding="utf-8")
        und, d = now()
        check(sorted(und) == ["bad.py", "good.py"],
              f"the fixture edit did not strand good.py: {und}")
        check(d.uncommitted == ["good.py"],
              f"UNCOMMITTED direction: {d.uncommitted}")
        check(not d.masked, f"an invented row was also MASKED: {d.masked}")
        # ⛔ And the row HEAD carries TOO stays in the pins' view — the bucket
        # `split_rows` gets wrong, and the reason `head_delta` exists.
        check(d.head == ["bad.py"],
              f"the pins' view lost the committed row: {d.head}")

        # ── MASKED: the worktree HIDES a committed one ──────────────────────
        git(repo, "checkout", "--", "scripts/good.py")
        (repo / "scripts/bad.py").write_text(DEF, encoding="utf-8")
        und, d = now()
        check(und == [], f"the fixture did not defend bad.py: {und}")
        check(d.masked == ["bad.py"], f"MASKED direction: {d.masked}")
        check(d.head == ["bad.py"],
              f"a MASKED row is missing from the pins' view: {d.head}")

        # ── a STAGED-only file has no HEAD blob ─────────────────────────────
        git(repo, "checkout", "--", "scripts/bad.py")
        (repo / "scripts/new.py").write_text(UNDEF, encoding="utf-8")
        git(repo, "add", "scripts/new.py")
        und, d = now()
        check("new.py" in d.uncommitted,
              f"a staged-only file's row was not UNCOMMITTED: {d.uncommitted}")
        check("new.py" not in d.head,
              f"a file in no commit entered the pins' view: {d.head}")

    return fails


def canary() -> int:
    """Perturb each axis and REQUIRE a red. A pin nobody has watched fail is a
    pin that certifies nothing (`restatement_drift_sweep`'s `--prove-fires`
    rule, in the form available to a sweep with no frozen known-answer tree)."""
    import contextlib
    import io

    global PINS, classify, adjudicate

    td = Path(tempfile.mkdtemp())
    pins_src = PINS.read_text(encoding="utf-8")
    real_pins = PINS
    real_classify = classify
    real_adjudicate = adjudicate
    results: list[bool] = []

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
            for ln in [l for l in out.splitlines()
                       if l.startswith(("✗", "⛔"))][:3]:
                print(f"        got: {ln}")
        results.append(ok)

    def bump(field_idx, delta):
        """Rewrite this repo's row, one field, by delta. Anchored on the ROW
        rather than on a literal, so the arm cannot silently stop perturbing
        when the pin is re-measured — the Issue 786 canary failure."""
        out = []
        hit = False
        for raw in pins_src.splitlines(keepends=True):
            parts = raw.split("#", 1)[0].split()
            if len(parts) == 1 + len(FIELDS) and parts[0] == SELF:
                parts[1 + field_idx] = str(int(parts[1 + field_idx]) + delta)
                out.append("  ".join(parts) + "\n")
                hit = True
            else:
                out.append(raw)
        if not hit:
            raise AssertionError(f"canary: no {SELF} row to perturb")
        return "".join(out)

    def inject(extra_defended=0, extra_undefended=0, extra_unparsed=0):
        def fn(repo):
            n, d, u, p = real_classify(repo)
            if repo.name != SELF:
                return n, d, u, p
            return (n + extra_defended + extra_undefended + extra_unparsed,
                    d + [f"ghost_d{i}.py" for i in range(extra_defended)],
                    u + [f"ghost_u{i}.py" for i in range(extra_undefended)],
                    p + [f"ghost_p{i}.py" for i in range(extra_unparsed)])
        return fn

    def hold(n=1):
        """Issue 822: the same ghost rows, but UNCOMMITTED — a file that
        differs from HEAD, so no commit contains the finding."""
        def fn(repo, undefended):
            d = real_adjudicate(repo, undefended)
            if repo.name != SELF:
                return d
            ghosts = [f"ghost_u{i}.py" for i in range(n)]
            return type(d)([r for r in d.committed if r not in ghosts],
                           list(d.uncommitted) + ghosts, list(d.masked))
        return fn

    def hide(n=1):
        """And the silent direction: HEAD carries rows this worktree does not.
        They are NOT in `undefended` — that is what MASKED means — so a run
        that adjudicated the worktree would report this repo clean."""
        def fn(repo, undefended):
            d = real_adjudicate(repo, undefended)
            if repo.name != SELF:
                return d
            return type(d)(list(d.committed), list(d.uncommitted),
                           list(d.masked) + [f"ghost_m{i}.py"
                                             for i in range(n)])
        return fn

    arm("baseline green", 0, "sweep PASSED")
    arm("new undefended reds", 1, "> pinned",
        classify_fn=inject(extra_undefended=1))
    # ⛔ The pair that IS Issue 822: one row, two provenances, opposite
    # verdicts. Injecting the row into `classify` alone reds (above); the same
    # row held as UNCOMMITTED must NOT, or the pins are reading the worktree.
    arm("an UNCOMMITTED row does NOT breach the ratchet", 0, "sweep PASSED",
        classify_fn=inject(extra_undefended=1), adjudicate_fn=hold())
    arm("...and is still SHOWN, never hidden", 0, "UNCOMMITTED: 1 row(s)",
        classify_fn=inject(extra_undefended=1), adjudicate_fn=hold())
    # T4: MASKED is the silent direction — a committed row the worktree hides.
    # It must red WITHOUT appearing in `undefended` at all.
    arm("a MASKED row reds though the worktree is clean", 1, "> pinned",
        adjudicate_fn=hide())
    arm("...and is labelled at the ROW", 1, "[MASKED", adjudicate_fn=hide())
    # ⛔ Two DISPLAYS, two arms. The first version asserted only "MASKED"
    # appears somewhere, which the row label satisfies — so dropping the total
    # from the final advisory line red NOTHING. Measured.
    arm("...and is counted on the ADVISORY line", 1, "MASKED: 1 row(s)",
        adjudicate_fn=hide())
    arm("UNPARSED reds (never folded into the pass column)", 1, "UNPARSED",
        classify_fn=inject(extra_unparsed=1))
    arm("walk floor reds", 1, "walk FLOOR breached", pins=bump(0, 10_000))
    arm("population floor reds", 1, "population FLOOR breached",
        pins=bump(1, 10_000))
    arm("ratchet reds", 1, "> pinned", pins=bump(2, -1))
    arm("unpinned repo reds", 1, "UNPINNED",
        pins="".join(l for l in pins_src.splitlines(keepends=True)
                     if l.split("#", 1)[0].split()[:1] != [SELF]))
    arm("empty pins refused", 2, "declares NO repos", pins="# nothing\n")
    arm("short row refused", 2, "unreadable", pins="repo-a 1 2\n")

    print(f"\n{sum(results)}/{len(results)} canary arm(s) PASSED")
    return 0 if all(results) else 2


def main(argv: list[str], run_selftest: bool = True) -> int:
    if "--canary" in argv:
        return canary()

    fails = selftest() if run_selftest else []
    if fails:
        print("✗ console-encoding sweep SELFTEST FAILED — untrustworthy:")
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
        print(f"✗ derived population is EMPTY under {WORKSPACE} — refusing to "
              f"report a green over zero repos")
        return 2

    bad = False
    tot_w = tot_p = tot_d = tot_u = 0
    n_uncommitted = n_masked = 0
    per_repo: dict[str, tuple[int, int]] = {}

    for name in names:
        repo = WORKSPACE / name
        n_walk, defended, undefended, unparsed = classify(repo)
        n_pop = len(defended) + len(undefended)

        # ── Issue 822: the DISPLAY reads the worktree, the PINS read HEAD ───
        # `undefended` is what the files say today and is printed as such.
        # `delta.head` is what a commit of this repo would produce, and it is
        # the only thing the ratchet may adjudicate: a ceiling breached by
        # somebody's in-flight edit is a red nobody can repair, and a ceiling
        # re-pinned from one bakes that edit into a tracked file where it reds
        # on every other box.
        delta = adjudicate(repo, undefended)
        n_uncommitted += len(delta.uncommitted)
        n_masked += len(delta.masked)
        tot_w += n_walk
        tot_p += n_pop
        tot_d += len(defended)
        tot_u += len(undefended)
        per_repo[name] = (n_pop, len(undefended))

        row = pins.get(name)
        flags = []
        for u in unparsed:
            flags.append(f"UNPARSED {u} — the instrument admitting it cannot "
                         f"read; never folded into either answer")
        if row is None:
            # Issue 821: an acknowledged known-extra owes no pin row —
            # the marker reached population_verdict's FINAL line and not
            # this loop, so 8 of 9 sweeps red on repos they found
            # nothing in, hiding two live ratchet breaches.
            if not pin_row_exempt(name):
                flags.append("UNPINNED — add a row (or it can never red)")
        else:
            if n_walk < row["min_scripts"]:
                flags.append(f"walk FLOOR breached: {n_walk} tracked "
                             f"scripts/*.py < {row['min_scripts']} — the walk "
                             f"went blind and the counts below mean nothing")
            if n_pop < row["min_population"]:
                flags.append(f"population FLOOR breached: {n_pop} < "
                             f"{row['min_population']} — the PREDICATE went "
                             f"blind over an unchanged walk (an ast.parse "
                             f"regression looks exactly like this), and then "
                             f"every ceiling passes vacuously")
            if len(delta.head) > row["max_undefended"]:
                flags.append(
                    f"undefended {len(delta.head)} committed > pinned "
                    f"{row['max_undefended']} — a new instrument that prints a "
                    f"non-ASCII glyph and defends neither stream")
                held = {r for r in delta.uncommitted}
                for p in sorted(set(delta.head) | set(undefended)):
                    # Never hidden — hiding them is the lie Issue 797 refuses —
                    # but labelled, so the reader can see which rows the pin
                    # did and did not adjudicate.
                    if p in held:
                        print(f"      ⛔ {name}/scripts/{p}  [UNCOMMITTED — "
                              f"not adjudicated]")
                    elif p in set(delta.masked):
                        print(f"      ⛔ {name}/scripts/{p}  [MASKED — "
                              f"committed, and this worktree hides it]")
                    else:
                        print(f"      ⛔ {name}/scripts/{p}")

        status = "✗" if flags else ("·" if undefended else "✓")
        # T3: the count stays honest in BOTH directions. A bare total invites
        # the one action this issue exists to prevent — typing it into the pin.
        split = ""
        if delta.uncommitted or delta.masked:
            split = (f" ({len(delta.head)} committed"
                     + (f" + {len(delta.uncommitted)} uncommitted"
                        if delta.uncommitted else "")
                     + (f", {len(delta.masked)} MASKED"
                        if delta.masked else "") + ")")
        print(f"{status} {name:22s} walk={n_walk:<3d} pop={n_pop:<3d} "
              f"defended={len(defended):<3d} "
              f"undefended={len(undefended)}{split}")
        for f in flags:
            bad = True
            print(f"      ✗ {f}")

    pop_lines, deferred, pop_fail = population_verdict(pins, names)

    # Issue 797 — the worktree is not the repo. This run reads files that
    # concurrent sessions are editing, so a row may sit on a line no commit
    # contains. ADVISORY, never a failure. The globs are THIS sweep's own
    # population: the tracked top-level scripts it walks.
    deferred.extend(sweep_advisory(names, ("scripts/*.py",), root=WORKSPACE,
                                   uncommitted_rows=n_uncommitted,
                                   masked_rows=n_masked))
    for _line in pop_lines:
        print(_line)
    if pop_fail:
        bad = True

    print(f"\n{len(names)} contract repo(s) · {tot_w} tracked scripts/*.py · "
          f"{tot_p} in population · {tot_d} defended · {tot_u} undefended")
    # ⛔ Every figure below is DERIVED from the run above. A typed pair in the
    # sibling sweep's summary went stale the day a repo's tooling changed and
    # printed a count contradicting the measured total one line up.
    own = per_repo.get(SELF, (0, 0))[1]
    others = [(n, p, u) for n, (p, u) in per_repo.items() if n != SELF and u]
    n_other = sum(u for _, _, u in others)
    top = max(others, key=lambda t: t[2], default=None)
    top_txt = (f", and in {top[0]} ({top[2]} of {top[1]}) the population is "
               f"dominated by plan-scoped one-offs — the same over-capture "
               f"instrument_reachability measured on this identical walk"
               if top else "")
    blind = [n for n in names if per_repo.get(n, (0, 0))[0] == 0]
    print(f"  the ceiling is a RATCHET, not a wall, and only here: this repo's "
          f"own undefended set is walled at {own} by MEMBERSHIP in "
          f"console_encoding_expected.txt, which is deliberately EMPTY. "
          f"{n_other} row(s) across {len(others)} other repo(s) are not this "
          f"repo's judgement calls to make{top_txt}. The ratchet constrains "
          f"what lands NEXT, and every row is ONE LINE from being closed.")
    if blind:
        print(f"  ⚠ {len(blind)} repo(s) have an EMPTY population "
              f"({', '.join(blind)}) — every ceiling there is vacuous and only "
              f"min_scripts detects anything, in the two that have scripts at "
              f"all. Issue 783's population shape, printed rather than assumed.")

    if bad:
        print("✗ console-encoding sweep FAILED — see the ✗ rows above")
        for _d in deferred:
            print(f"  ⚠ {_d}")
        return 1
    _line = "✓ console-encoding sweep PASSED — every repo within its pins"
    if deferred:
        _line += "; DEFERRED: " + "; ".join(deferred)
    print(_line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
