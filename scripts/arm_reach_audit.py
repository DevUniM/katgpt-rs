#!/usr/bin/env python3
"""An arm that exists and RUNS may still reach nothing — Issue 790.

Issue 789 made every `docs_gate.sh` CHECK invoke a validation arm and had to
state the limit of that claim in its own docstring: *"an arm whose perturbation
reds nothing certifies nothing … Arm QUALITY is not statically decidable and is
not claimed here."* The first half is true. The second is too strong — quality
is not *statically* decidable, but **reach** is measurable by execution, and
Issue 789 measured it 53 times BY HAND, finding **seven** arms that certified
nothing until they were re-aimed. A census done by hand is a census that stops
being done.

So: classic mutation testing, scoped small enough to be free. Mutate a module's
source OUTSIDE its own arm functions, re-exec it, run its arm, and ask whether
the arm noticed.

This file is the REPORT. The VERDICT half is `scripts/arm_reach_gate.py`
(Issue 790 T2): it pins every live survivor by MEMBERSHIP with a reason per row
and walls UNPINNED at 0. Read this one while fixing; run that one to find out
whether a commit added a decision line no arm reaches.

    KILLED     the arm noticed. The only good outcome.
    SURVIVED   no arm distinguishes this line's behaviour. The finding.
    NO-ARM     the module has no arm of its own, so every mutant survives
               VACUOUSLY. Never pooled with either neighbour — see below.
    CRASHED    the mutant dies at import or before the arm runs. Trivially
               "noticed" and evidence of nothing; its own bucket.

⛔ **NO-ARM is the bucket that carries a real finding, and pooling it either way
destroys it.** Four CHECKS are in that state by design: `percentile_floor_gate`,
`cfg_row_implication_gate`, `trap_sentinel_gate` and `markdown_fence_gate`
**delegate** their arm to the classifier they import. Issue 789 credits that,
correctly — it is Issue 755's DRY answer. But a classifier's self-test **cannot
reach its consumer's pin arithmetic**, which is the exact sentence Issue 775
wrote when it added six arms over `platform_dead_code_floor_gate`'s own
arithmetic. Issue 789 generalised that sentence one level too shallowly: it
asked whether an arm runs, never whether the arm can SEE the gate it guards.
Pooling NO-ARM into SURVIVED overstates the gap; pooling it into KILLED hides it
completely.

⚠ **EQUIVALENT mutants are the known false-positive class, and they are the
BULK, not the exception.** A surviving mutant may be semantically equivalent to
the original (`>=` where the operands can never be equal), and a mutation in a
line the arm was never meant to reach — `main()`'s printing and exit shell —
survives *correctly*. So the quantity here is **arm REACH per function**, never
a quality score, and a function's rows are read once and then pinned by
membership with a reason. Reading the raw SURVIVED total as a defect count is
the misreading this paragraph exists to prevent.

⚠ **`--include-all` widens the population past the CHECKS set and its verdicts
are NOT comparable** to the default run: a sweep script's arm is written to
cover its *classifier*, and its `main()` is a much larger I/O shell than a
gate's. Two populations, two baselines.

⛔ **And it is a different COST class, not merely more modules.** The CHECKS
population is 22 modules / 552 mutants / **158s** (measured twice, 2026-09-15).
`--include-all` pulls in the eleven cross-repo drift sweeps, whose arms are
WORKSPACE-WIDE WALKS, so every mutant pays a 16-repo walk: a run was
**abandoned at 7.5 minutes without completing** — a LOWER BOUND, not a
measurement of the whole run, and quoted as one. Budget it as a deliberate
investigation, never as "the same report with a flag". The verdict half
(`arm_reach_gate.py`) deliberately does NOT use this population.

Exit 0 = the report ran (findings or not).
Exit 2 = the instrument went blind (a floor breached, or its own self-test
failed — a mutation harness that generates no mutants reports a perfect score).
"""

from __future__ import annotations

import ast
import contextlib
import io
import os
import sys
import time
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from docs_gate_checks_sync import parse_checks  # noqa: E402 — the CHECKS parser, reused not re-derived

SH = HERE / "docs_gate.sh"

# The arm vocabulary. Kept in sync with `check_validation_gate.ARM_NAMES` by
# ASSERTION rather than by hope — see `selftest`. Two copies of a vocabulary is
# two things to get wrong (Issue 755), and this one cannot simply import it
# because the two instruments answer different questions about it: that gate
# asks "is an arm CALLED", this one asks "which bodies must not be MUTATED".
ARM_NAMES = {
    "selftest",
    "self_test",
    "selftest_scoping",
    "canary",
    "gate_selftest",
    "prove_fires",
}

# ⛔ The arms actually INVOKED are a strict subset, and the exclusion is
# `prove_fires`. It is not a reach arm: it is a known-answer validation against
# a FROZEN commit, so it `git archive`s a tree and its verdict is a fact about
# history that no mutation of the working source can change. Running it per
# mutant is 436 git invocations — measured at 80.2s against 4.4s without, with
# the child's output escaping `redirect_stdout` (a subprocess writes to fd 1,
# not to `sys.stdout`) and littering the report with fixture filenames.
#
# Its BODY is still excluded from mutation, because it is still an arm; only
# the invocation is skipped. The two sets answer different questions and
# collapsing them was the first version's defect.
RUN_ARMS = ARM_NAMES - {"prove_fires"}

# Functions whose mutants survive CORRECTLY: the I/O shell an arm is not meant
# to reach. Pinned by NAME with the reason on the row, the Issue 789 idiom.
# ⚠ This is the permissive direction — every name added here removes rows from
# the finding set — so it is deliberately tiny and the floor below guards it.
EXEMPT_FUNCTIONS = {
    "main": "the CLI shell: argv dispatch, printing and exit codes, which an "
            "arm is not meant to reach",
}

# Floors. Both are blindness detectors and neither is redundant:
#   MIN_MODULES  the population walk (a report over zero modules is perfect)
#   MIN_MUTANTS  the mutation operators (a harness that generates no mutants
#                reports 100% killed, which is the same output as perfection)
MIN_MODULES = 15
MIN_MUTANTS = 200

KILLED, SURVIVED, CRASHED = "KILLED", "SURVIVED", "CRASHED"

# The BASELINE verdict — a module-level bucket, never a mutant-level one.
# `BASE_RED` is the dangerous direction: an arm that fails on its own
# unmutated source kills every mutant and reports PERFECT reach.
BASE_OK, BASE_RED, BASE_CRASH = "OK", "BASELINE-RED", "BASELINE-CRASH"

_CMP_FLIP = {
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
    ast.Lt: ast.LtE, ast.LtE: ast.Lt,
    ast.Gt: ast.GtE, ast.GtE: ast.Gt,
    ast.In: ast.NotIn, ast.NotIn: ast.In,
}
_CMP_NAME = {
    ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=",
    ast.Gt: ">", ast.GtE: ">=", ast.In: "in", ast.NotIn: "not in",
}


def arm_names_in(tree: ast.AST) -> set[str]:
    """Arm functions DEFINED in this module (not merely called).

    The distinction matters here and not in `check_validation_gate`: a module
    that only *calls* a delegated arm has no body of its own to protect from
    mutation, and — more to the point — no arm that could notice one.
    """
    return {f.name for f in ast.walk(tree)
            if isinstance(f, ast.FunctionDef) and f.name in ARM_NAMES}


def _is_main_guard(node: ast.AST) -> bool:
    """`__name__ == "__main__"` — the entry point, not a decidable rule."""
    return (isinstance(node, ast.Compare)
            and isinstance(node.left, ast.Name) and node.left.id == "__name__"
            and len(node.comparators) == 1
            and isinstance(node.comparators[0], ast.Constant)
            and isinstance(node.comparators[0].value, str))


def _enclosing_function(tree: ast.AST) -> dict[int, str]:
    """{line: innermost enclosing function name} for every line in a body.

    Innermost wins, so a nested helper inside `main` is attributed to the
    helper and a row in `main`'s own body to `main`. Built by walking outward
    first and letting deeper definitions overwrite — a function defined inside
    another necessarily has a narrower span.
    """
    out: dict[int, str] = {}
    funcs = [f for f in ast.walk(tree)
             if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for f in sorted(funcs, key=lambda f: (f.end_lineno or f.lineno) - f.lineno,
                    reverse=True):
        for ln in range(f.lineno, (f.end_lineno or f.lineno) + 1):
            out[ln] = f.name
    return out


def mutants(src: str, arms: set[str]):
    """Yield (description, function, line, mutated_source).

    Lines inside an ARM BODY are never mutated: an arm that fails because its
    own expectation was edited has noticed nothing, and counting it KILLED
    would make every arm look perfect. Same reason `platform_dead_code_audit`
    excludes its own self-test fixtures.
    """
    tree = ast.parse(src)
    # An arm's own helpers are arm code too, by an explicit NAMING convention
    # (`*_arms`) rather than by call-graph inference. ⛔ The inference version
    # was written first and was WRONG: "a function called only from an arm" also
    # describes a pure rule whose only in-module caller happens to be its arm,
    # and this file's own fixtures caught it excluding the very `rule()` they
    # were testing. Name-based is narrower, predictable, and says so out loud.
    excluded = arms | {f.name for f in ast.walk(tree)
                       if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))
                       and f.name.endswith("_arms")}
    arm_spans = [(f.lineno, f.end_lineno or f.lineno) for f in ast.walk(tree)
                 if isinstance(f, ast.FunctionDef) and f.name in excluded]
    # The whole BODY of `if __name__ == "__main__":`, not just its test. It is
    # CLI dispatch — `if "--canary" in sys.argv[1:]` and friends — which is the
    # entry point by another name, and no arm is imported as `__main__` so none
    # can ever reach it. Measured: `population_sync_gate`'s flag dispatch
    # survived as a finding until this span was skipped.
    arm_spans += [(n.lineno, n.end_lineno or n.lineno) for n in ast.walk(tree)
                  if isinstance(n, ast.If) and _is_main_guard(n.test)]
    owner = _enclosing_function(tree)

    def in_arm(ln: int) -> bool:
        return any(a <= ln <= b for a, b in arm_spans)

    # Index every candidate node by identity, then re-parse per mutant so each
    # mutation is applied to a pristine tree. Cheaper than it looks (~3 ms) and
    # it removes any chance of two mutations compounding.
    def candidates(t):
        out = []
        for i, node in enumerate(ast.walk(t)):
            ln = getattr(node, "lineno", None)
            if ln is None or in_arm(ln):
                continue
            if _is_main_guard(node):
                # `if __name__ == "__main__"` is the ENTRY POINT, not
                # arithmetic. No arm can kill it — flipping it either does
                # nothing (the module is exec'd under another name anyway) or
                # runs `main()` at import and lands in CRASHED. Either way it
                # is noise, and it is in all 61 tracked scripts, so it would
                # scale with every arm added. Skipped, not exempted: it must
                # not inflate the mutant total either, because that total is
                # what `MIN_MUTANTS` floors.
                continue
            if (isinstance(node, ast.Compare) and len(node.ops) == 1
                    and type(node.ops[0]) in _CMP_FLIP):
                op = type(node.ops[0])
                out.append((i, "cmp", f"{_CMP_NAME[op]} -> "
                                     f"{_CMP_NAME[_CMP_FLIP[op]]}", ln))
            elif isinstance(node, ast.BoolOp):
                kind = "and -> or" if isinstance(node.op, ast.And) else "or -> and"
                out.append((i, "bool", kind, ln))
            elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
                out.append((i, "not", "drop `not`", ln))
            elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
                out.append((i, "const", f"{node.value} -> {not node.value}", ln))
            elif (isinstance(node, ast.BinOp)
                  and isinstance(node.op, (ast.Add, ast.Sub))):
                # OFF-BY-ONE, added by Issue 790 T4 for a measured reason: this
                # repo's whole percentile section is about an index landing on
                # n-1, and `markdown_fence_gate.scan_text`'s only real decision
                # is `n_lines - first`. With comparison operators alone that
                # module read UNREACHED while its arms asserted real behaviour.
                #
                # `+` is also string and list concatenation here, so a flip
                # often raises TypeError. That lands in CRASHED — its own
                # bucket, labelled "evidence of nothing" — rather than being
                # mistaken for a kill.
                flip = "- -> +" if isinstance(node.op, ast.Sub) else "+ -> -"
                out.append((i, "arith", flip, ln))
        return out

    for idx, kind, desc, ln in candidates(tree):
        fresh = ast.parse(src)
        target = list(ast.walk(fresh))[idx]
        if kind == "cmp":
            target.ops = [_CMP_FLIP[type(target.ops[0])]()]
        elif kind == "bool":
            target.op = ast.Or() if isinstance(target.op, ast.And) else ast.And()
        elif kind == "not":
            # Replacing the UnaryOp in its parent is fiddly; mutate in place by
            # turning `not X` into `bool(X)`-equivalent via a second `not`.
            target.operand = ast.UnaryOp(op=ast.Not(), operand=target.operand)
        elif kind == "const":
            target.value = not target.value
        elif kind == "arith":
            target.op = ast.Add() if isinstance(target.op, ast.Sub) else ast.Sub()
        ast.fix_missing_locations(fresh)
        try:
            code = compile(fresh, "<mutant>", "exec")
        except (ValueError, SyntaxError, TypeError):
            continue
        yield desc, owner.get(ln, "<module>"), ln, code


@contextlib.contextmanager
def _silence():
    """Suppress output at the FILE DESCRIPTOR level, not just `sys.stdout`.

    `contextlib.redirect_stdout` rebinds a Python name; a subprocess inherits
    fd 1 and writes straight past it. Measured: several arms shell out to git
    (`instrument_reachability_gate.canary` builds a synthetic repo), and their
    children printed fixture filenames into the middle of this report — ten
    lines of `scripts/orphan.py` and friends above the header, on a run whose
    Python-level redirect was working perfectly.
    """
    devnull = os.open(os.devnull, os.O_WRONLY)
    saved = (os.dup(1), os.dup(2))
    try:
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        with contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()):
            yield
    finally:
        os.dup2(saved[0], 1)
        os.dup2(saved[1], 2)
        for fd in (*saved, devnull):
            os.close(fd)


_MOD_NAME = "__arm_reach__"


@contextlib.contextmanager
def _exec_namespace(path: Path):
    """A REAL module object, registered in `sys.modules`, not a bare dict.

    ⛔ This was the harness's third bucket-boundary defect and it was invisible
    in the default population: `dataclasses` resolves a class's defining
    namespace through `sys.modules.get(cls.__module__).__dict__`, so a module
    exec'd into a plain dict under a name nothing has registered raises
    `AttributeError: 'NoneType' object has no attribute '__dict__'` at the
    `@dataclass` line — at IMPORT, which this harness correctly files as
    CRASHED, *evidence of nothing*.

    Measured 2026-09-15: SEVEN modules died that way, every one of them a
    classifier that models its findings as a dataclass — `platform_dead_code`,
    `len_derived_binding`, `required_features_build`, `cfg_gated_target`,
    `cfg_row_implication`, `all_ignored_target`, `suite_membership` — carrying
    **796 of `--include-all`'s 2382 mutants**. All seven read CRASHED on their
    own UNMUTATED source, so the harness was reporting a property of its own
    exec namespace as a property of their code. The default CHECKS population
    defines no dataclass and was unaffected, which is exactly why this survived
    T1–T4: a boundary only the wider population crosses.

    A prior registration is saved and restored — the audit exec's dozens of
    modules under one name and a leaked entry would hand the next one somebody
    else's globals.
    """
    mod = types.ModuleType(_MOD_NAME)
    mod.__file__ = str(path)
    prev = sys.modules.get(_MOD_NAME)
    sys.modules[_MOD_NAME] = mod
    try:
        yield mod.__dict__
    finally:
        if prev is None:
            sys.modules.pop(_MOD_NAME, None)
        else:
            sys.modules[_MOD_NAME] = prev


def dataclass_premise() -> bool:
    """Does THIS interpreter need `_exec_namespace`'s registration?

    True when a `@dataclass` fails to build in a bare-dict namespace — i.e.
    when `dataclasses` resolves the defining module unguarded. Measured rather
    than assumed because the two live boxes disagree: CPython ≤3.12 guards it
    (`if cls.__module__ in sys.modules: … else: globals = {}`), 3.14 does not.
    Reported, never gated: a premise that varies by interpreter belongs in the
    output next to the verdict, the `trap_launder_premise_matrix` rule.
    """
    src = ("from dataclasses import dataclass\n"
           "@dataclass\nclass _P:\n    n: int\n")
    try:
        with _silence():
            exec(compile(src, "<premise>", "exec"), {"__name__": _MOD_NAME})
    except BaseException:
        return True
    return False


def run_arm(code, path: Path, arms: set[str]) -> str:
    """KILLED if any arm in this module reports a failure, else SURVIVED.

    An arm is EITHER a `-> list[str]` shape (failures returned) or an
    `-> int` shape (rc, 0 = pass). Both are live in this repo and neither is
    being rewritten for the harness's convenience; a shape the harness cannot
    read is CRASHED, never SURVIVED.
    """
    # ⛔ The two phases are separated DELIBERATELY, and conflating them was this
    # harness's own defect. A mutant that breaks the module at IMPORT noticed
    # nothing (CRASHED, evidence of nothing). An exception raised while the ARM
    # RUNS is the arm noticing — and several arms here signal exactly that way:
    # `required_features_static_gate.selftest` returns None and raises
    # SystemExit(2) on failure, so under the first version every mutant it
    # caught was filed as CRASHED and the module could never show a KILL at all.
    with _exec_namespace(path) as ns:
        try:
            with _silence():
                exec(code, ns)
        except BaseException:
            return CRASHED
        try:
            with _silence():
                for name in sorted(arms & RUN_ARMS):
                    fn = ns.get(name)
                    if not callable(fn):
                        continue
                    result = fn()
                    # Three live arm shapes, none being rewritten for the
                    # harness's convenience: `-> list[str]` (failures
                    # returned), `-> int` (rc, 0 = pass), and `-> None` +
                    # raise. The first two are read here; the third is the
                    # `except` below.
                    if isinstance(result, list) and result:
                        return KILLED
                    if isinstance(result, int) and result != 0:
                        return KILLED
        except BaseException:
            return KILLED
    return SURVIVED


def audit_module(path: Path) -> dict:
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return {"error": f"does not parse ({e.msg} line {e.lineno})"}
    arms = arm_names_in(tree)
    row = {"arms": sorted(arms), "killed": 0, "crashed": 0,
           "survived": [], "total": 0, "error": None, "baseline": BASE_OK}
    # NO-ARM is about arms that can be RUN. A module whose only arm is
    # `prove_fires` has nothing that could notice a mutation of its own source.
    if not (arms & RUN_ARMS):
        # NO-ARM. Mutants are still COUNTED — the population figure is what
        # tells a reader how much arithmetic is going unwatched — but they are
        # not run, because the answer would be a vacuous SURVIVED for every one.
        row["total"] = sum(1 for _ in mutants(src, set()))
        return row
    # ⛔ THE BASELINE. Ask the arm about the UNMUTATED source first, because
    # both wrong answers here are silent and one of them looks perfect:
    #   · arm already FAILS unmutated → every mutant reads KILLED, the module
    #     scores 100% reach, and it has distinguished nothing. That is the
    #     "runner that always says KILLED" hazard the gate's MIN_KILLED floor
    #     names — but MIN_KILLED is global, so one module in this state is
    #     invisible to it *and inflates it*.
    #   · module will not EXEC unmutated → every mutant reads CRASHED, which
    #     is honest per-mutant but pools into a module row saying nothing.
    # Neither is folded into KILLED or SURVIVED, and the mutants are counted
    # but not RUN: running them buys a column of identical vacuous verdicts at
    # full price (the seven dataclass modules were 796 of them).
    base = run_arm(compile(src, str(path), "exec"), path, arms)
    if base != SURVIVED:
        row["baseline"] = BASE_RED if base == KILLED else BASE_CRASH
        row["total"] = sum(1 for _ in mutants(src, arms))
        return row
    for desc, func, ln, code in mutants(src, arms):
        row["total"] += 1
        verdict = run_arm(code, path, arms)
        if verdict == KILLED:
            row["killed"] += 1
        elif verdict == CRASHED:
            row["crashed"] += 1
        else:
            row["survived"].append((func, ln, desc))
    return row


def population(include_all: bool) -> list[Path]:
    """The modules to audit, DERIVED. Never typed.

    Default = the `docs_gate.sh` CHECKS set, because that is the population
    Issue 789 bounded its claim over and the only one with a baseline.
    `--include-all` adds every tracked `scripts/*.py` that DEFINES an arm; its
    verdicts are a separate population with a separate baseline (see the module
    docstring) and must not be compared against the default run's.
    """
    names = list(parse_checks(SH.read_text(encoding="utf-8")))
    paths = [HERE / n for n in names if (HERE / n).is_file()]
    if not include_all:
        return paths
    seen = {p.name for p in paths}
    for p in sorted(HERE.glob("*.py")):
        if p.name in seen or p.name == Path(__file__).name:
            continue
        try:
            if arm_names_in(ast.parse(p.read_text(encoding="utf-8"))):
                paths.append(p)
        except (SyntaxError, OSError):
            continue
    return paths


def selftest() -> list[str]:
    """Known-answer arms. A mutation harness needs one more than most.

    The bucket boundaries ARE the finding (`wasm32_surface_audit`'s rule, which
    produced three confident wrong answers before a right one), and this
    instrument has a second failure mode on top of that: a harness that
    generates NO mutants, or whose arm-runner always reports KILLED, prints a
    perfect score — the same output as perfection.
    """
    import tempfile

    fails: list[str] = []

    def eq(label, got, want):
        if got != want:
            fails.append(f"    {label}: got {got!r}, want {want!r}")

    # ── the vocabulary is shared with check_validation_gate: ASSERT it ─────
    try:
        import check_validation_gate as cvg
        eq("ARM_NAMES agrees with check_validation_gate's", ARM_NAMES, cvg.ARM_NAMES)
    except ImportError:
        fails.append("    check_validation_gate is not importable — the arm "
                     "vocabulary cannot be cross-checked, and two copies of a "
                     "vocabulary is two things to get wrong")

    # ── the operators: each must FIRE, and on the right node ──────────────
    def descs(src: str, arms: set[str] = frozenset()):
        return sorted(d for d, _f, _l, _c in mutants(src, arms))

    eq("RUN_ARMS excludes prove_fires and nothing else",
       ARM_NAMES - RUN_ARMS, {"prove_fires"})

    eq("`==` flips", descs("x = a == b\n"), ["== -> !="])
    eq("`<=` flips", descs("x = a <= b\n"), ["<= -> <"])
    eq("`in` flips", descs("x = a in b\n"), ["in -> not in"])
    eq("`and` flips", descs("x = a and b\n"), ["and -> or"])
    eq("`not` is dropped", descs("x = not a\n"), ["drop `not`"])
    eq("a bool constant flips", descs("x = True\n"), ["True -> False"])
    eq("a chained compare is NOT mutated (ambiguous)", descs("x = a < b < c\n"), [])
    eq("a subtraction flips (off-by-one)", descs("x = a - b\n"), ["- -> +"])
    eq("an addition flips", descs("x = a + b\n"), ["+ -> -"])
    eq("multiplication is not a site (no off-by-one meaning)",
       descs("x = a * b\n"), [])
    eq("the __main__ guard is NOT a mutation site",
       descs('if __name__ == "__main__":\n    main()\n'), [])
    eq("the __main__ guard's BODY is not a mutation site either",
       descs('if __name__ == "__main__":\n'
             '    if "--canary" in sys.argv[1:]:\n        canary()\n'
             '    main(a - b)\n'), [])
    eq("the same dispatch OUTSIDE the guard still is",
       descs('if "--canary" in sys.argv[1:]:\n    canary()\n'), ["in -> not in"])
    eq("an ordinary __name__ comparison against a NAME still is",
       descs("if __name__ == other:\n    main()\n"), ["== -> !="])
    eq("an int constant is not a mutation site", descs("x = 3\n"), [])

    # ── the arm-body exclusion: an edited expectation is not a KILL ────────
    eq("a line inside an arm body is not mutated",
       descs("def selftest():\n    return [] if a == b else ['x']\n", {"selftest"}),
       [])
    eq("the same line IS mutated when it is not an arm",
       descs("def other():\n    return [] if a == b else ['x']\n", {"selftest"}),
       ["== -> !="])
    # ⚑ An arm's own HELPER is arm code: mutating a fixture assertion reports a
    # finding against the ARM rather than the gate (Issue 790 T3, found by
    # running this audit on a gate it had just improved). The convention is the
    # NAME — `*_arms` — and not a call-graph inference.
    eq("a `*_arms` helper is arm code",
       descs("def _read_pins_arms():\n    return a == b\n"
             "def selftest():\n    return _read_pins_arms()\n", {"selftest"}), [])
    # ⛔ An ordinary helper an arm calls stays MUTABLE — it is the rule under
    # test. The first version of this exclusion inferred "called only from an
    # arm" and swallowed exactly this case; these fixtures caught it excluding
    # the very `rule()` they exist to test.
    eq("an ordinary helper an arm calls stays mutable",
       descs("def rule():\n    return a == b\n"
             "def selftest():\n    return rule()\n", {"selftest"}), ["== -> !="])

    # ── function attribution: innermost wins ──────────────────────────────
    owners = {f for _d, f, _l, _c in mutants(
        "def outer():\n    def inner():\n        return a == b\n", set())}
    eq("a nested helper owns its own rows", owners, {"inner"})

    # ── the buckets, end to end, against fixtures with known answers ──────
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)

        # An arm that DOES reach the rule -> KILLED.
        watched = d / "watched.py"
        watched.write_text(
            "def rule(n):\n    return n >= 10\n"
            "def selftest():\n"
            "    f = []\n"
            "    if rule(10) is not True: f.append('boundary 10')\n"
            "    if rule(9) is not False: f.append('boundary 9')\n"
            "    return f\n", encoding="utf-8")
        r = audit_module(watched)
        eq("a watched rule's mutants are KILLED", (r["killed"], r["survived"]),
           (r["total"], []))
        eq("the watched fixture generated mutants at all", r["total"] > 0, True)

        # The SAME rule with an arm that never calls it -> SURVIVED.
        unwatched = d / "unwatched.py"
        unwatched.write_text(
            "def rule(n):\n    return n >= 10\n"
            "def selftest():\n    return []\n", encoding="utf-8")
        r = audit_module(unwatched)
        eq("an unwatched rule's mutants SURVIVE", r["killed"], 0)
        eq("the survivor is attributed to its function",
           [f for f, _l, _d in r["survived"]], ["rule"])

        # No arm of its own -> NO-ARM, counted but not run.
        bare = d / "bare.py"
        bare.write_text("def rule(n):\n    return n >= 10\n", encoding="utf-8")
        r = audit_module(bare)
        eq("a module with no arm is NO-ARM, not SURVIVED",
           (r["arms"], r["survived"], r["killed"]), ([], [], 0))
        eq("NO-ARM mutants are still COUNTED", r["total"] > 0, True)

        # An arm that refuses via SystemExit counts as having NOTICED.
        refusing = d / "refusing.py"
        refusing.write_text(
            "import sys\n"
            "def rule(n):\n    return n >= 10\n"
            # `not rule(10)` and not `rule(9)`: flipping `>=` to `>` leaves
            # rule(9) False either way, so a fixture testing the 9 side is INERT
            # against the only operator that reaches this line (measured — it
            # was the first version of this arm, and it survived).
            "def selftest():\n"
            "    if not rule(10): sys.exit(2)\n"
            "    return []\n", encoding="utf-8")
        r = audit_module(refusing)
        eq("an arm that EXITS on a mutant has NOTICED it: KILLED, not CRASHED",
           (r["survived"], r["killed"] > 0, r["crashed"]), ([], True, 0))
        eq("the refusing fixture ran at all", r["total"] > 0, True)

        # …and the other side of that boundary: a mutant that breaks the
        # module at IMPORT noticed nothing and must NOT be credited as a kill.
        import_broken = d / "import_broken.py"
        import_broken.write_text(
            "TABLE = {'a': 1}\n"
            "KEY = 'a' if TABLE['a'] >= 1 else 'missing'\n"
            "VALUE = TABLE[KEY]\n"
            "def rule(n):\n    return n >= 10\n"
            "def selftest():\n    return []\n", encoding="utf-8")
        r = audit_module(import_broken)
        eq("a mutant that dies at IMPORT is CRASHED, never KILLED",
           (r["crashed"] > 0, r["killed"]), (True, 0))

        # An `rc`-shaped arm (int, 0 = pass) is read too.
        rc_shaped = d / "rc_shaped.py"
        rc_shaped.write_text(
            "def rule(n):\n    return n >= 10\n"
            "def canary():\n    return 0 if rule(10) and not rule(9) else 2\n",
            encoding="utf-8")
        r = audit_module(rc_shaped)
        eq("an rc-shaped arm is read, not ignored", r["survived"], [])
        eq("the rc fixture ran at all", r["total"] > 0, True)

        unparsed = d / "unparsed.py"
        unparsed.write_text("def rule(:\n", encoding="utf-8")
        eq("an unparseable module is an ERROR, never a clean row",
           "does not parse" in (audit_module(unparsed).get("error") or ""), True)

        # ── the BASELINE boundary, both directions ────────────────────────
        # ⛔ BASELINE-RED is the one that looks like success: without this
        # bucket the module below scores 100% KILLED while distinguishing
        # nothing at all, because its arm was already failing.
        base_red = d / "base_red.py"
        base_red.write_text(
            "def rule(n):\n    return n >= 10\n"
            "def selftest():\n    return ['this arm fails unmutated']\n",
            encoding="utf-8")
        r = audit_module(base_red)
        eq("an arm failing on UNMUTATED source is BASELINE-RED, not 100% killed",
           (r["baseline"], r["killed"], r["survived"]), (BASE_RED, 0, []))
        eq("a BASELINE-RED module still COUNTS its mutants (the population "
           "figure is what says how much went unwatched)", r["total"] > 0, True)

        base_crash = d / "base_crash.py"
        base_crash.write_text(
            "raise RuntimeError('unimportable')\n"
            "def rule(n):\n    return n >= 10\n"
            "def selftest():\n    return []\n", encoding="utf-8")
        r = audit_module(base_crash)
        eq("a module that will not EXEC unmutated is BASELINE-CRASH",
           (r["baseline"], r["killed"]), (BASE_CRASH, 0))

        healthy = d / "healthy.py"
        healthy.write_text(
            "def rule(n):\n    return n >= 10\n"
            "def selftest():\n    return [] if rule(10) and not rule(9) "
            "else ['x']\n", encoding="utf-8")
        eq("a healthy module is BASELINE-OK", audit_module(healthy)["baseline"],
           BASE_OK)

        # ── the exec NAMESPACE is a real module, and a dataclass proves it ──
        # Two-sided on purpose: the bare-dict arm is the measured NEGATIVE, so
        # this arm reds if the registration is removed AND stays honest about
        # what it is testing. Seven live classifiers read CRASHED under the
        # bare dict, 796 mutants of them.
        dc = d / "dc_module.py"
        dc.write_text(
            "from dataclasses import dataclass\n"
            "@dataclass\nclass Finding:\n    n: int\n"
            "def rule(n):\n    return Finding(n).n >= 10\n"
            "def selftest():\n    return [] if rule(10) and not rule(9) "
            "else ['x']\n", encoding="utf-8")
        src_dc = dc.read_text(encoding="utf-8")
        eq("a @dataclass module EXECs in a REGISTERED-module namespace",
           run_arm(compile(src_dc, str(dc), "exec"), dc, {"selftest"}), SURVIVED)
        eq("sys.modules is left exactly as it was found",
           _MOD_NAME in sys.modules, False)
        # ⚠ The bare-dict direction is a PREMISE, not an assertion, and the
        # distinction is measured: CPython ≤3.12 guards the lookup
        # (`if cls.__module__ in sys.modules: … else: globals = {}`) and 3.14
        # does not, so hard-asserting "the bare dict dies" would red on an
        # interpreter where this defect simply does not exist — a premise
        # harness that never varies the axis it claims about, which is exactly
        # what `trap_launder_premise_matrix` was written to stop doing. The
        # arm above is sufficient WHEREVER the defect is live: remove the
        # registration on 3.14 and it returns CRASHED. See `dataclass_premise`,
        # which the report prints so the axis is observed rather than assumed.
        eq("the premise is reported as a bool, never as a silent assumption",
           isinstance(dataclass_premise(), bool), True)

    # ── the exemption set is the permissive direction ─────────────────────
    eq("every EXEMPT_FUNCTIONS row carries a reason",
       all(bool(v.strip()) for v in EXEMPT_FUNCTIONS.values()), True)
    eq("EXEMPT_FUNCTIONS does not exempt everything",
       len(EXEMPT_FUNCTIONS) < 5, True)

    return fails


def main(argv: list[str]) -> int:
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass

    if "--self-test" in argv[1:]:
        f = selftest()
        for line in f:
            print(line)
        print(f"{'✗' if f else '✓'} arm-reach audit self-test: "
              f"{len(f)} failure(s)")
        return 2 if f else 0

    failures = selftest()
    if failures:
        print("✗ INSTRUMENT: arm_reach_audit's own self-test does not pass. A "
              "mutation harness that generates no mutants, or whose runner always "
              "reports KILLED, prints a PERFECT score — which is the same output "
              "as perfection:")
        for f in failures:
            print(f)
        return 2

    include_all = "--include-all" in argv[1:]
    only = [a for a in argv[1:] if not a.startswith("-")]

    paths = population(include_all)
    if only:
        paths = [p for p in paths if any(o in p.name for o in only)]

    t0 = time.time()
    rows = {p.name: audit_module(p) for p in sorted(paths)}
    wall = time.time() - t0

    total_mutants = sum(r.get("total", 0) for r in rows.values())
    if not only:
        if len(rows) < MIN_MODULES:
            print(f"✗ INSTRUMENT: {len(rows)} module(s) < floor {MIN_MODULES} — the "
                  f"population walk went blind; a report over a handful of modules "
                  f"is not a report over the CHECKS set")
            return 2
        if total_mutants < MIN_MUTANTS:
            print(f"✗ INSTRUMENT: generated {total_mutants} mutant(s) < floor "
                  f"{MIN_MUTANTS} — the operators stopped firing, and a harness "
                  f"with no mutants reports a perfect score")
            return 2

    no_arm = {n: r for n, r in rows.items() if not r.get("error") and not r["arms"]}
    errored = {n: r for n, r in rows.items() if r.get("error")}
    baseline_bad = {n: r for n, r in rows.items()
                    if not r.get("error") and r.get("baseline", BASE_OK) != BASE_OK}

    print(f"▸ arm REACH over {len(rows)} module(s), {total_mutants} mutant(s), "
          f"{wall:.1f}s" + ("  [--include-all: NOT comparable to the default "
                            "population]" if include_all else "")
          + f"   [py{sys.version_info.major}.{sys.version_info.minor}; "
          + ("dataclass namespace premise LIVE" if dataclass_premise()
             else "dataclass namespace premise inert here") + "]")
    print()

    survived_live: list[tuple[str, str, int, str]] = []
    survived_exempt = 0
    unreached: list[str] = []
    for name in sorted(rows):
        r = rows[name]
        if r.get("error"):
            print(f"  ⛔ {name:40s} {r['error']}")
            continue
        if not r["arms"]:
            print(f"  ▫ {name:40s} NO-ARM — {r['total']:3d} mutant(s) unwatched by "
                  f"any arm of its own (delegated; a classifier's self-test cannot "
                  f"reach its consumer's arithmetic — Issue 775)")
            continue
        if r.get("baseline", BASE_OK) != BASE_OK:
            why = ("its arm FAILS on the unmutated source, so every mutant "
                   "would read KILLED and the module would score PERFECT "
                   "reach. Check the ENVIRONMENT first: a sweep whose canary "
                   "runs the real workspace needs the same markers the gates "
                   "get (DOCS_GATE_PARTIAL_CLONE=1 on a known-subset box)"
                   if r["baseline"] == BASE_RED else
                   "the module does not EXEC unmutated, so every mutant would "
                   "read CRASHED")
            print(f"  ⛔ {name:40s} {r['baseline']} — {r['total']:3d} mutant(s) "
                  f"NOT RUN: {why}")
            continue
        live = [(f, l, d) for f, l, d in r["survived"] if f not in EXEMPT_FUNCTIONS]
        survived_exempt += len(r["survived"]) - len(live)
        survived_live += [(name, f, l, d) for f, l, d in live]
        # ⛔ A `✓` for "no live survivors" is NOT "the arm reaches something",
        # and conflating them was this report's first output. `orphaned_attr_gate`
        # printed ✓ on 0 killed / 5 crashed / 7 exempt: every mutant either died
        # at import or landed in `main`, so the arm demonstrably distinguished
        # NOTHING and the row read as the cleanest in the set. UNREACHED is its
        # own marker for exactly that shape.
        if r["killed"] == 0 and r["total"] > 0:
            unreached.append(name)
            mark = "⛔"
        else:
            mark = "✓" if not live else "✗"
        print(f"  {mark} {name:40s} {r['killed']:3d} killed  {r['crashed']:3d} crashed  "
              f"{len(live):3d} survived (+{len(r['survived']) - len(live)} exempt) "
              f"of {r['total']:3d}"
              + ("   UNREACHED: this arm killed nothing" if mark == "⛔" else ""))

    print()
    if survived_live:
        print(f"  SURVIVED — no arm distinguishes these lines' behaviour "
              f"({len(survived_live)} row(s)):")
        for name, func, ln, desc in survived_live:
            print(f"    {name}:{ln}  {func}()  {desc}")
        print()
    print(f"▸ {sum(r['killed'] for r in rows.values() if not r.get('error'))} killed · "
          f"{len(survived_live)} survived (live) · {survived_exempt} survived in "
          f"exempt functions · "
          f"{sum(r['crashed'] for r in rows.values() if not r.get('error'))} crashed · "
          f"{sum(r['total'] for r in no_arm.values())} in {len(no_arm)} NO-ARM "
          f"module(s) · {sum(r['total'] for r in baseline_bad.values())} in "
          f"{len(baseline_bad)} BASELINE-bad module(s) · {len(errored)} unparsed")
    if baseline_bad:
        print("  ⛔ BASELINE (never pooled into KILLED, and BASELINE-RED is the "
              "one that would have looked PERFECT): "
              + ", ".join(f"{n} {r['baseline']}"
                          for n, r in sorted(baseline_bad.items())))
    print("  ⚠ SURVIVED is arm REACH, not a defect count: an EQUIVALENT mutant "
          "(a `>=` whose operands can never be equal) survives correctly, and so "
          "does any mutation an arm was never meant to reach. Read each row once, "
          "then pin the equivalents. See AGENTS.md § An arm that exists and runs.")
    print("  ⚠ NO-ARM is never pooled: into SURVIVED it overstates, into KILLED it "
          "hides the Issue 775 gap entirely.")
    print("  ⚠ REACH IS MEASURED PER MODULE, so a rule asserted by a DIFFERENT "
          "module's arm reads SURVIVED. Measured: skill_repo_set_gate.derive_repos "
          "survives here and is covered by population_sync_gate's synthetic-workspace "
          "canary. This repo deliberately shares rules across modules (Issue 755), so "
          "this is the false-positive class to check FIRST on any survivor — before "
          "EQUIVALENT, and before concluding anything is untested.")
    if unreached:
        print(f"  ⛔ UNREACHED ({len(unreached)}): an arm that killed ZERO mutants. "
              f"Every one either died at import or landed in an exempt function, so "
              f"the arm distinguished nothing THESE OPERATORS can express: "
              f"{', '.join(unreached)}")
    print("  ⛔ OPERATOR SCOPE is the limit to read this by, and it is narrow: "
          "control flow and off-by-one only (comparison flips, and/or, dropped "
          "`not`, bool constants, +/-). REGEX AND STRING LITERALS ARE NOT TOUCHED "
          "— and that is where most of this repo's decision logic lives. Measured: "
          "docs_gate_checks_sync has 20 hand-verified arms that red under regex "
          "perturbation and 10 mutable sites here. A low kill count is NOT evidence "
          "an arm is weak; a SURVIVED row is evidence about one line.")
    print("  ⚠ A `find() < 0` guard flipped to `<= 0` is INERT on the -1 return and "
          "bites only at OFFSET 0, so it is killable ONLY by a fixture that begins "
          "at the match — and it is provably EQUIVALENT wherever the search starts "
          "after an earlier match (measured: 3 such rows in agents_repo_set_gate, "
          "1 in docs_gate_checks_sync). Check that before writing an arm for one.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
