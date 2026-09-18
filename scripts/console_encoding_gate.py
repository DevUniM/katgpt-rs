#!/usr/bin/env python3
"""An instrument that cannot PRINT its verdict has no verdict (Issue 804).

Every instrument here prints `✓`, `✗`, `⛔`, `⚠` and em-dashes. On a console
whose encoding is not UTF-8 — the Windows workstation is **cp874** — `print()`
raises `UnicodeEncodeError` and the process dies before saying anything:

    UnicodeEncodeError: 'charmap' codec can't encode character '\\u2713'

`scripts/docs_gate.sh` exports `PYTHONIOENCODING=utf-8`, so every per-push
CHECK survives *when the gate runs it*. Nothing protects an instrument run
DIRECTLY — which is how AGENTS.md documents most of them
(`scripts/percentile_index_audit.py ../riir-ai`). So the class concentrates in
exactly the instruments with **no automatic lane**: the workstation sweeps and
audits, the ones AGENTS.md says are "found by census and not by symptom".

⛔ **The cost is not a crash, it is UNREAD FINDINGS.**
`restatement_drift_sweep.py` was the one member of the 18-sweep family without
the defence, so it was the one nobody on this box could run at all — its 4
repos / 255 theorems were not *unknown*, they were *unlooked at*, while the
family was reported green. 42 of 70 in-population instruments already carried
the fix verbatim; 28 did not, and nothing said which. The ninth recorded
instance of this repo's standing failure mode (Issues 777, 778, 793, 782, 783,
789, 797, 785): a rule landed in some instruments and never generalised.

The quantity to gate is NOT the count — *a set is gateable where its
cardinality is not* (`cfg_gated_floor_gate`'s rule). A count is green on a
swap and stale the moment the family grows.

    scripts/console_encoding_gate.py    # the verdict AND the arms

The arms run UNCONDITIONALLY, behind no flag: `docs_gate.sh` invokes each check
as `"$PY" "$script"` with no arguments, so an arm behind `'--canary' in
sys.argv` never fires on a push (Issue 789's finding).

⚠ **What this does NOT assert:** that the output is *readable* on such a
console. It is not — `\\u2713` is worse than `✓`. The claim is only that the
instrument RUNS and reports its verdict rather than dying, which is the
difference between a finding being read and a finding not existing.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
from pathlib import Path

import console_safe  # noqa: E402
import worktree_state  # noqa: E402

console_safe.apply()

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
PINS = HERE / "console_encoding_expected.txt"
GLOB = "*.py"

# Two floors, failing differently.
#   MIN_POPULATION  the WALK + the population predicate. A glob that matches
#                   nothing, or a predicate that classifies everything as
#                   exempt, reports every instrument defended and prints a
#                   confident green over zero of them.
#   MIN_DEFENDED    the AST RESOLUTION. A walk that finds every instrument and
#                   credits none looks exactly like nobody having defended any,
#                   and the obvious remedy is to pin them all.
MIN_POPULATION = 55
MIN_DEFENDED = 55


def tracked_scripts(root: Path) -> list[str]:
    """The family, as git tracks it — a scratch copy left in `scripts/` is not
    a member of the contract, and only git can say so. An extracted tree with
    no `.git` is a legitimate population, not an error (`tracked_walk`'s rule),
    so it falls back to the filesystem.

    ⛔ The guard is `worktree_state.is_checkout`, DELEGATED (Issue 836 T2).
    It was a private `(root / ".git").is_dir()`, which says NO to a `git
    worktree` — so a run from inside one fell to the glob and got a different
    population. Measured, this repo, one untracked scratch script planted in
    the worktree's `scripts/`: the gate printed `✗ UNDEFENDED
    zz_scratch_probe.py`, demanding a repair to a file git does not track and
    no contract claims. With the delegation the worktree run is byte-identical
    to the ordinary one (83 in population, PASSED, both).
    """
    if not worktree_state.is_checkout(root):
        return sorted(p.name for p in (root / "scripts").glob(GLOB))
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "scripts/" + GLOB],
        capture_output=True, encoding="utf-8", errors="replace")
    if out.returncode != 0:
        return sorted(p.name for p in (root / "scripts").glob(GLOB))
    # `ls-files scripts/*.py` matches nested paths too (`scripts/kimi_ref/…`);
    # those are reference dumps, not instruments, and their own directory is
    # the boundary. Only the top level is in scope.
    return sorted(Path(p).name for p in out.stdout.split()
                  if p.strip() and p.count("/") == 1)


def in_population(src: str) -> bool | None:
    """Is this module an INSTRUMENT that could print a non-encodable glyph?

    Two conjuncts, and both are needed:

    - a `__main__` entry point — a library with no entry point is only ever
      reached through an importer that has its own defence, and pinning it
      would grow the population with rows nothing can fail on;
    - a **string literal** containing non-ASCII. Deliberately read from the
      AST and not the text, because a comment cannot be printed: 6 of this
      repo's tracked scripts carry non-ASCII in prose only. A docstring counts
      — `argparse` prints it for `--help`.

    Returns `None` for a module that does not parse: UNPARSED is the instrument
    admitting it cannot see, never folded into either answer.
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    has_main = any(
        isinstance(n, ast.Compare)
        and isinstance(n.left, ast.Name) and n.left.id == "__name__"
        and any(isinstance(c, ast.Constant) and c.value == "__main__"
                for c in n.comparators)
        for n in ast.walk(tree))
    if not has_main:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if any(ord(ch) > 127 for ch in node.value):
                return True
    return False


def is_defended(src: str) -> bool:
    """Does this module DEFEND its streams — by either accepted form?

    AST, not text, for the reason `subprocess_encoding_gate` moved to one: a
    text scanner reports the fixture strings inside this file's own arms, and
    the repairs on offer are to exempt the gate from itself or to obfuscate its
    test data. An exempt gate certifies nothing.

    ⛔ TWO forms are credited and that is deliberate, not laxity. 42 instruments
    inline `sys.stdout.reconfigure(errors=…)` in `main()` and 28 call
    `console_safe.apply()`; rewriting 42 working instruments to import a
    five-line helper is a larger diff and a larger risk than the duplication
    costs. The property worth asserting is *the streams are defended*, not
    *this function was called* — the same reason `sweep_advisory_membership_gate`
    accepts either of its two entry points after condemning its most careful
    caller for naming only one.

    An IMPORT alone is not enough: an unused `import console_safe` is exactly
    what a half-finished repair looks like.
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = (fn.id if isinstance(fn, ast.Name)
                else fn.attr if isinstance(fn, ast.Attribute) else "")
        if name == "reconfigure":
            # `stream.reconfigure(errors=...)`. A bare `reconfigure()` with no
            # `errors=` sets nothing relevant and must not be credited.
            if any(kw.arg == "errors" for kw in node.keywords):
                return True
        elif name == "apply":
            # `console_safe.apply()` — qualified, or bare after
            # `from console_safe import apply`.
            if isinstance(fn, ast.Attribute):
                owner = fn.value
                if isinstance(owner, ast.Name) and owner.id == "console_safe":
                    return True
            elif "console_safe" in src:
                return True
    return False


def parse_pins(path: Path) -> tuple[dict[str, str], list[str]]:
    """({script: reason}, errors). A reasonless row is an ERROR, not a pin."""
    pins: dict[str, str] = {}
    errs: list[str] = []
    if not path.is_file():
        return pins, errs
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, _, reason = line.partition("#")
        name, reason = name.strip(), reason.strip()
        if not reason:
            errs.append(f"{path.name}:{n}: `{name}` has NO reason — a row "
                        f"nobody had to justify is a backlog wearing a pin")
            continue
        pins[name] = reason
    return pins, errs


def verdict(root: Path, pins: dict[str, str]):
    """(defended, undefended, unparsed, stale_pins, n_population)."""
    defended, undefended, unparsed = [], [], []
    for name in tracked_scripts(root):
        p = root / "scripts" / name
        if not p.is_file():
            continue
        src = p.read_text(encoding="utf-8", errors="replace")
        member = in_population(src)
        if member is None:
            unparsed.append(name)
            continue
        if not member:
            continue
        (defended if is_defended(src) else undefended).append(name)
    n = len(defended) + len(undefended)
    # A pin whose script is defended, or gone from the population, no longer
    # describes anything. Both directions red: the file must not only loosen.
    stale = [n_ for n_ in pins if n_ not in undefended]
    return defended, undefended, unparsed, stale, n


# ───────────────────────────── arms ───────────────────────────────────────

MAIN = 'if __name__ == "__main__":\n    sys.exit(main())\n'
GLYPH = 'def main():\n    print("\\u2713 ok")\n'
ASCII_ONLY = 'def main():\n    print("ok")\n'
INLINE = ('def main():\n'
          '    sys.stdout.reconfigure(errors="backslashreplace")\n'
          '    print("\\u2713 ok")\n')
HELPER = ('import console_safe\n'
          'console_safe.apply()\n'
          'def main():\n'
          '    print("\\u2713 ok")\n')


def classifier_arms() -> list[str]:
    fails: list[str] = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    # ── population ──
    check(in_population(GLYPH + MAIN) is True,
          "an entry-point module printing a non-ASCII glyph was not in scope")
    check(in_population(ASCII_ONLY + MAIN) is False,
          "an ASCII-only instrument entered the population — it cannot fail")
    check(in_population(GLYPH) is False,
          "a LIBRARY with no __main__ entered the population: it is only "
          "reached through an importer that has its own defence")
    check(in_population('# ✓ a comment\n' + ASCII_ONLY + MAIN) is False,
          "non-ASCII in a COMMENT put a module in scope — a comment cannot be "
          "printed, and reading the text instead of the AST is how that "
          "mistake is made")
    check(in_population('"""doc ✓"""\n' + ASCII_ONLY + MAIN) is True,
          "a DOCSTRING glyph was not in scope — argparse prints it for --help")
    check(in_population("def f(:\n") is None,
          "an UNPARSED module got a boolean answer — silence is not evidence")
    # The entry-point test is a CONJUNCTION and both halves must bite: a
    # `__name__` comparison against some other constant is not an entry point,
    # and crediting it would put every `if __name__ == "__mp_main__":` guard
    # in scope.
    check(in_population(GLYPH + 'if __name__ == "__mp_main__":\n    main()\n')
          is False,
          "a __name__ comparison against a NON-__main__ constant was read as "
          "an entry point")
    # The ASCII boundary is `> 127`, not `>= 127`: U+007F is DEL, it encodes
    # fine in every single-byte codec, and a module whose only non-ASCII is a
    # DEL cannot fail the way this gate is about.
    check(in_population('def main():\n    print("\\x7f")\n' + MAIN) is False,
          "U+007F (DEL) put a module in scope — it is ASCII and encodes "
          "everywhere; the boundary is > 127, not >= 127")

    # ── defence ──
    check(is_defended(INLINE), "the inline reconfigure form was not credited")
    check(is_defended(HELPER), "the console_safe.apply() form was not credited")
    check(is_defended("from console_safe import apply\napply()\n"),
          "the bare `apply()` after a from-import was not credited")
    check(not is_defended(GLYPH), "an undefended module was credited")
    check(not is_defended("import console_safe\ndef main():\n    pass\n"),
          "an IMPORT with no call was credited — that is exactly what a "
          "half-finished repair looks like")
    check(not is_defended('S = "call console_safe.apply() one day"\n'),
          "a STRING mentioning the call was credited — this gate's own arms "
          "carry such strings, and a text scanner reports them as defence")
    check(not is_defended("def f():\n    x.reconfigure()\n"),
          "a bare reconfigure() with no errors= was credited — it sets "
          "nothing relevant")
    check(not is_defended("def f():\n    apply()\n"),
          "a bare apply() in a module that never mentions console_safe was "
          "credited — `apply` is far too common a name to credit blind")
    # The owner test is a CONJUNCTION and both halves must bite. `apply` is a
    # method name on pandas frames, on `functools`, on half the config objects
    # in this workspace — crediting `anything.apply()` would make the gate
    # pass on modules that never heard of this module.
    check(not is_defended("import console_safe\ndef f():\n    other.apply()\n"),
          "`other.apply()` was credited as the console_safe call — the owner "
          "name is what distinguishes them, and the import alone is not it")
    check(not is_defended("def f(:\n"),
          "an UNPARSED module was credited as defended")
    return fails


def _fixture(tmp: Path, bodies: dict[str, str]) -> Path:
    root = tmp / "repo"
    (root / "scripts").mkdir(parents=True)
    for name, body in bodies.items():
        (root / "scripts" / name).write_text(body, encoding="utf-8")
    return root


def pin_arms() -> list[str]:
    """The gate's own pin arithmetic, which the classifier cannot reach."""
    fails: list[str] = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        f = tmp / "pins.txt"

        f.write_text("# c\n\na.py  # deliberate: reason here\n", encoding="utf-8")
        pins, errs = parse_pins(f)
        check(pins == {"a.py": "deliberate: reason here"} and not errs,
              f"a well-formed pin did not parse: {pins} {errs}")

        f.write_text("b.py\n", encoding="utf-8")
        pins, errs = parse_pins(f)
        check(pins == {} and len(errs) == 1,
              f"a REASONLESS row was accepted as a pin: {pins} {errs}")

        pins, errs = parse_pins(tmp / "absent.txt")
        check((pins, errs) == ({}, []),
              "an absent pin file was an error rather than an empty set")

        root = _fixture(tmp, {
            "good.py": HELPER + MAIN,
            "bad.py": GLYPH + MAIN,
            "plain.py": ASCII_ONLY + MAIN,
            "lib.py": GLYPH,
            "broken.py": "def f(:\n" + MAIN,
        })
        d, u, unp, stale, n = verdict(root, {})
        check((d, u, n) == (["good.py"], ["bad.py"], 2),
              f"the verdict mis-partitioned: {d} {u} {n}")
        check(unp == ["broken.py"],
              f"UNPARSED was not reported separately: {unp}")
        check("plain.py" not in d + u and "lib.py" not in d + u,
              "an out-of-population module entered the finding set")

        # A pin keeps the row reported but off the finding set …
        _, u, _, stale, _ = verdict(root, {"bad.py": "r"})
        check(u == ["bad.py"] and stale == [],
              f"a pinned row was not still reported as undefended: {u}")
        # … and a pin on a DEFENDED script is STALE, which reds. This is the
        # direction a pin file left to loosen would never catch.
        _, _, _, stale, _ = verdict(root, {"good.py": "r"})
        check(stale == ["good.py"],
              f"a pin on an already-defended script did not read STALE: {stale}")
        _, _, _, stale, _ = verdict(root, {"gone.py": "r"})
        check(stale == ["gone.py"],
              f"a pin for a DELETED script did not read STALE: {stale}")

        empty = _fixture(tmp / "e", {"plain.py": ASCII_ONLY + MAIN})
        _, _, _, _, n = verdict(empty, {})
        check(n == 0, f"an empty population did not report 0: {n}")
        check(MIN_POPULATION > 0 and MIN_DEFENDED > 0,
              "a floor of 0 is not a floor — an empty walk would pass")
    return fails


def walk_arms() -> list[str]:
    """`tracked_scripts` against a REAL git tree, both branches.

    The fixtures above have no `.git`, so they take the FALLBACK walk and the
    `git ls-files` half would be reached by nothing — the survivor class
    `arm_reach_audit` reports for exactly this shape.
    """
    fails: list[str] = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    def git(cwd, *args):
        subprocess.run(["git", "-C", str(cwd), *args], check=True,
                       capture_output=True)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "repo"
        (root / "scripts" / "kimi_ref").mkdir(parents=True)
        (root / "scripts" / "a.py").write_text(HELPER + MAIN, encoding="utf-8")
        (root / "scripts" / "kimi_ref" / "dump.py").write_text(
            GLYPH + MAIN, encoding="utf-8")
        git(root, "init", "-q", "-b", "main")
        git(root, "config", "user.email", "t@t")
        git(root, "config", "user.name", "t")
        git(root, "add", "-A")
        git(root, "commit", "-qm", "init")

        check(tracked_scripts(root) == ["a.py"],
              f"the tracked walk did not return the committed instrument, or "
              f"pulled in a NESTED reference dump: {tracked_scripts(root)}")

        (root / "scripts" / "zz_scratch.py").write_text(GLYPH + MAIN,
                                                        encoding="utf-8")
        check(tracked_scripts(root) == ["a.py"],
              f"an UNTRACKED scratch copy entered the population — asking git "
              f"instead of the filesystem is exactly for that: "
              f"{tracked_scripts(root)}")
        nogit = Path(td) / "extracted"
        (nogit / "scripts").mkdir(parents=True)
        (nogit / "scripts" / "zz_scratch.py").write_text(GLYPH + MAIN,
                                                         encoding="utf-8")
        check(tracked_scripts(nogit) == ["zz_scratch.py"],
              f"the no-.git FALLBACK did not walk the filesystem: "
              f"{tracked_scripts(nogit)}")

        # Issue 836 T2 — the THIRD branch, and the one the two above cannot
        # reach: a checkout whose `.git` is a FILE. Both arms above pass under
        # either spelling, so without this one the delegation is unasserted
        # and a revert to `.is_dir()` is silent.
        _main, wt = worktree_state.worktree_fixture(Path(td) / "wtf")
        check((wt / ".git").is_file(),
              "the fixture's .git is not a FILE — `git worktree add` no longer "
              "produces the shape this arm is about, so it asserts nothing")
        check(tracked_scripts(wt) == ["a.py"],
              f"in a WORKTREE the walk fell back to the filesystem and counted "
              f"an untracked scratch file as a contract member: "
              f"{tracked_scripts(wt)}. The guard is `is_checkout`, not "
              f"`.git`.is_dir() — Issue 836")

        d, u, _, _, n = verdict(root, {})
        check((d, u, n) == (["a.py"], [], 1),
              f"the verdict over a real git tree disagreed with the walk: "
              f"{d} {u} {n}")
    return fails


def selftest() -> list[str]:
    return classifier_arms() + pin_arms() + walk_arms() + console_safe.selftest()


def main() -> int:
    fails = selftest()
    if fails:
        print("✗ console-encoding gate SELFTEST FAILED — instrument "
              "untrustworthy:")
        for f in fails:
            print("    ✗ " + f)
        return 2

    pins, errs = parse_pins(PINS)
    for e in errs:
        print("✗ " + e)
    defended, undefended, unparsed, stale, n = verdict(REPO_ROOT, pins)

    if n < MIN_POPULATION:
        print(f"✗ INSTRUMENT: the population is {n} < floor {MIN_POPULATION} — "
              f"the walk or the population predicate went blind, and every row "
              f"below passes vacuously")
        return 2
    if len(defended) < MIN_DEFENDED:
        print(f"✗ INSTRUMENT: {len(defended)} defended < floor {MIN_DEFENDED} — "
              f"a walk that finds every instrument and credits none looks "
              f"exactly like nobody having defended any")
        return 2

    bad = bool(errs)
    for name in unparsed:
        bad = True
        print(f"✗ UNPARSED {name} — the instrument admitting it cannot read; "
              f"never folded into the pass column")
    for name in stale:
        bad = True
        print(f"✗ STALE pin `{name}` — it is defended now, or out of the "
              f"population. Remove the row; a pin file that only ever loosens "
              f"is a backlog")
    for name in undefended:
        if name in pins:
            print(f"  · pinned undefended: {name} — {pins[name]}")
            continue
        bad = True
        print(f"✗ UNDEFENDED {name} — it prints a non-ASCII glyph and neither "
              f"calls console_safe.apply() nor reconfigures its streams, so on "
              f"a non-UTF-8 console it dies with NO verdict and its findings go "
              f"unread (Issue 804). Add the call, or pin it in {PINS.name} with "
              f"a reason")

    if bad:
        return 1
    print(f"✓ console-encoding gate PASSED — all {len(defended)} in-population "
          f"tracked scripts/{GLOB} defend their streams (floors "
          f"{MIN_POPULATION}/{MIN_DEFENDED}), {len(pins)} pinned exemption(s), "
          f"0 stale, 0 unparsed. ⚠ It does NOT claim the output is READABLE on "
          f"such a console — only that the instrument reports its verdict "
          f"instead of dying")
    return 0


if __name__ == "__main__":
    sys.exit(main())
