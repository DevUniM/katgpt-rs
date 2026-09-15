#!/usr/bin/env python3
"""GATE: every docs_gate.sh CHECK must invoke a validation arm — UNCONDITIONALLY.

Issue 789. `platform_dead_code_floor_gate.py` landed with "six canary arms over
the gate's own pin arithmetic, **which the classifier's self-test cannot
reach**". That sentence is in AGENTS.md, it is correct, and it names a rule.
The rule landed in ONE gate and was never generalised — the sixth recorded
instance of that shape here (Issues 777, 778, 793, 782, 783). Measured when
this file was written: SIX of the twenty CHECKS invoked no arm at all, their
own or delegated, carrying 2,050 lines of per-push logic whose failure path no
test had ever executed.

`docs_gate.sh`'s own header is the argument: *"An assertion nobody invokes is
decoration, and a red one nobody invokes is worse: it trains the next reader to
assume the tool is broken."* Two of the three checks that file was written for
were RED on develop when it landed. This is the same sentence one level in.

WHY UNCONDITIONAL IS THE PREDICATE, and not merely "has an arm".
`docs_gate.sh` runs each check as `"$PY" "$script"` — with **no arguments**. An
arm reachable only behind `'--canary' in sys.argv` therefore never fires on a
push, and that is not hypothetical: `population_sync_gate.py`'s eight adversary
arms, landed by Issue 788 the DAY BEFORE this gate, were flag-gated and ran on
no push at all. They cost 0.17s. A flag-name census (or a plain "does it define
a selftest?" census) reports that gate as covered, which is how the
representation you measure decides the answer you get.

DELEGATION IS CREDITED, and must be. Four checks reach their arm through the
classifier they import — `percentile_floor_gate` calls
`percentile_index_audit.selftest()`, and `cfg_row_implication_gate`,
`trap_sentinel_gate` and `platform_dead_code_floor_gate` do the same for
theirs. That is the DRY answer (Issue 755's rule) and refusing it would push
every gate toward a second copy of a rule it does not own. ⛔ Issue 789's FIRST
census got this wrong in the over-reporting direction: it grepped CLI flag
strings, credited none of the four, and claimed nine bare checks where there
were six.

WHAT THIS DOES NOT ASSERT — say it out loud rather than let a green read as
total. That an arm EXISTS and RUNS is not that it is any good: an arm whose
perturbation reds nothing certifies nothing, and Issue 789 found seven such
arms while writing the ones this gate now counts. Arm QUALITY is not statically
decidable and is not claimed here. What is claimed is strictly weaker and still
worth a push: no CHECK reaches a verdict with its own arithmetic untested by
anything.

Exit 0 = every CHECK invokes an arm (or is pinned with a reason).
Exit 1 = a CHECK does not, or a pin has gone stale in either direction.
Exit 2 = the instrument itself went blind (a floor breached, a file unparsed).
"""

from __future__ import annotations

import ast
import contextlib
import io
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# The CHECKS array is parsed by the check that owns that parser, not by a
# second copy of the regex (Issue 755). It already exits 2 on an array it
# cannot read, which is the behaviour this gate wants anyway.
from docs_gate_checks_sync import parse_checks  # noqa: E402

SH = HERE / "docs_gate.sh"
PINS = HERE / "check_validation_expected.txt"

# The vocabulary of a validation arm. ⚠ This set is the PERMISSIVE direction
# and the floor below guards it: an empty ARM_NAMES reds every check and is
# impossible to miss, while a set that quietly WIDENS (add `main`, say) greens
# every check silently. Issue 787's `min_roots` lesson, one instrument over.
ARM_NAMES = {
    "selftest",
    "self_test",
    "selftest_scoping",
    "canary",
    "gate_selftest",
    "prove_fires",
}

# Floors. Both are blindness detectors and neither is redundant:
#   MIN_CHECKS  the CHECKS parse (a gate over zero checks passes vacuously)
#   MIN_ARMED   the ARM_NAMES resolution (a walk that finds every check and
#               credits none of them means the AST pass stopped working, which
#               is indistinguishable from "nobody wrote any arms" without this)
MIN_CHECKS = 15
MIN_ARMED = 15


def arm_calls(tree: ast.AST) -> list[tuple[str, list[str]]]:
    """[(arm name, enclosing `if` tests)] for every call to an ARM_NAMES name.

    A bare `selftest()` and a delegated `audit.selftest()` both count — the
    attribute form IS the DRY answer and must not be penalised. The guard list
    is what separates "runs on every push" from "runs when somebody types a
    flag": an empty list means nothing stands between module entry and the
    call.
    """
    out: list[tuple[str, list[str]]] = []

    def walk(node: ast.AST, guards: list[str]) -> None:
        for child in ast.iter_child_nodes(node):
            g = guards
            if isinstance(node, ast.If):
                test = ast.unparse(node.test)
                if child in node.body:
                    g = guards + [test]
                elif child in node.orelse:
                    g = guards + [f"not ({test})"]
            if isinstance(child, ast.Call):
                fn = child.func
                name = (fn.id if isinstance(fn, ast.Name)
                        else fn.attr if isinstance(fn, ast.Attribute) else None)
                if name in ARM_NAMES:
                    out.append((name, g))
            walk(child, g)

    walk(tree, [])
    return out


def read_pins(path: Path) -> dict[str, str]:
    """{script: reason}. A reasonless row is REFUSED, not defaulted.

    `instrument_unreferenced_expected.txt`'s rule, and for the same reason: the
    next reader has to be able to judge the exemption, and "it is in the file"
    is not a judgement. The file is expected to be EMPTY of real exemptions —
    every CHECK here has an arm — so a row appearing at all is a claim somebody
    must write down.
    """
    pins: dict[str, str] = {}
    if not path.is_file():
        return pins
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        name, _, reason = line.partition(":")
        name, reason = name.strip(), reason.strip()
        if not reason:
            print(f"✗ INSTRUMENT: {path.name} row {name!r} carries no reason — an "
                  f"exemption the next reader cannot judge is not an exemption")
            raise SystemExit(2)
        pins[name] = reason
    return pins


def classify(scripts_dir: Path, names: list[str]) -> dict[str, dict]:
    """{check: {unconditional, guarded, delegated, error}}."""
    out: dict[str, dict] = {}
    for n in names:
        path = scripts_dir / n
        row: dict = {"unconditional": [], "guarded": [], "error": None}
        if not path.is_file():
            row["error"] = "registered in CHECKS but absent from scripts/"
            out[n] = row
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as e:
            # UNPARSED is the instrument admitting it cannot read, and it is
            # never the safe direction: a file that does not parse has no
            # measurable arms and would otherwise read as a bare check.
            row["error"] = f"does not parse ({e.msg} at line {e.lineno})"
            out[n] = row
            continue
        for arm, guards in arm_calls(tree):
            (row["unconditional"] if not guards else row["guarded"]).append(
                (arm, guards))
        out[n] = row
    return out


def main(argv: list[str]) -> int:
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass

    if "--canary" in argv[1:]:
        return canary()
    if "--prove-fires" in argv[1:]:
        i = argv.index("--prove-fires")
        if i + 1 >= len(argv):
            print("✗ --prove-fires needs a commit-ish")
            return 2
        return prove_fires(argv[i + 1])

    failures = selftest()
    if failures:
        print("✗ INSTRUMENT: check_validation_gate's own selftest does not pass — a "
              "gate that cannot resolve an arm reports every check as bare (or, "
              "worse, every check as covered):")
        for f in failures:
            print(f)
        return 2

    names = list(parse_checks(SH.read_text(encoding="utf-8")))
    pins = read_pins(PINS)
    rows = classify(HERE, names)

    if len(names) < MIN_CHECKS:
        print(f"✗ INSTRUMENT: parsed {len(names)} CHECKS row(s) < floor {MIN_CHECKS} "
              f"— the array went unreadable; a gate over a handful of checks passes "
              f"for the wrong reason")
        return 2

    armed = [n for n, r in rows.items() if r["unconditional"]]
    if len(armed) < MIN_ARMED:
        print(f"✗ INSTRUMENT: credited {len(armed)} armed check(s) of {len(names)} < "
              f"floor {MIN_ARMED} — the AST resolution stopped working, which looks "
              f"exactly like nobody having written any arms")
        return 2

    problems: list[str] = []
    for n in sorted(rows):
        r = rows[n]
        if r["error"]:
            problems.append(f"  ⛔ {n} — {r['error']}")
            continue
        if r["unconditional"]:
            continue
        if n in pins:
            continue
        if r["guarded"]:
            how = "; ".join(f"{a} behind `{' and '.join(g)}`"
                            for a, g in r["guarded"])
            problems.append(
                f"  ✗ {n} — its arm is FLAG-GATED and so never runs: {how}. "
                f"docs_gate.sh invokes every check as `\"$PY\" \"$script\"`, with "
                f"no arguments. Call it unconditionally in main() (swallow the "
                f"output on success) and keep the flag as the verbose mode.")
        else:
            problems.append(
                f"  ✗ {n} — invokes NO validation arm, its own or delegated. Its "
                f"verdict arithmetic is asserted by nothing; a regression in it "
                f"does not error, it reclassifies. Add a selftest() called at the "
                f"top of main() (exit 2, not 1 — a broken instrument has no "
                f"verdict), or pin it in {PINS.name} with a reason.")

    # The pins red in BOTH directions. A row for a check that has since grown an
    # arm is a stale exemption that would hide the next regression in it.
    for n, reason in sorted(pins.items()):
        if n not in rows:
            problems.append(f"  ⛔ {n} — pinned in {PINS.name} but not a CHECK at "
                            f"all (reason on file: {reason})")
        elif rows[n]["unconditional"]:
            problems.append(f"  ⛔ {n} — pinned as exempt but now invokes an arm "
                            f"unconditionally; drop the row (reason on file: "
                            f"{reason})")

    if problems:
        print(f"✗ check-validation gate FAILED — {len(problems)} of {len(names)} "
              f"CHECKS row(s)")
        for p in problems:
            print(p)
        print("    See AGENTS.md § A gate whose own failure path is asserted by "
              "nothing.")
        return 1

    print(f"    ✓ check-validation gate PASSED — all {len(names)} docs_gate CHECKS "
          f"invoke a validation arm unconditionally, {len(pins)} pinned exemption(s), "
          f"floors {MIN_CHECKS}/{MIN_ARMED} (delegated arms credited)")
    return 0


def selftest() -> list[str]:
    """Known-answer arms over the resolver. A gate about arms needs its own.

    The classifier's bucket boundaries ARE the finding here, exactly as in
    `wasm32_surface_audit` (which produced three confident wrong answers before
    a right one), so every arm below is a fixture whose correct bucket is
    decidable by reading it.
    """
    fails: list[str] = []

    def eq(label, got, want):
        if got != want:
            fails.append(f"    {label}: got {got!r}, want {want!r}")

    def arms(src: str):
        calls = arm_calls(ast.parse(src))
        return (sorted(a for a, g in calls if not g),
                sorted(a for a, g in calls if g))

    eq("a bare unconditional call is credited",
       arms("def main():\n    selftest()\n"), (["selftest"], []))
    eq("a DELEGATED call through an import is credited",
       arms("import audit\ndef main():\n    audit.selftest()\n"),
       (["selftest"], []))
    eq("a call inside a nested block is still unconditional",
       arms("def main():\n    for x in y:\n        selftest()\n"),
       (["selftest"], []))
    # The distinction the whole gate turns on.
    eq("⚑ a flag-gated call is GUARDED, not credited",
       arms("def main():\n    if '--canary' in sys.argv:\n        canary()\n"),
       ([], ["canary"]))
    eq("⚑ the `__main__` + flag dispatch shape is GUARDED",
       arms("if __name__ == '__main__':\n"
            "    if '--canary' in sys.argv[1:]:\n        canary()\n"),
       ([], ["canary"]))
    eq("an else-branch call is guarded too",
       arms("def main():\n    if x:\n        pass\n    else:\n        selftest()\n"),
       ([], ["selftest"]))
    eq("a definition without a call is not an arm",
       arms("def selftest():\n    return []\n"), ([], []))
    eq("an unrelated call is not an arm",
       arms("def main():\n    audit_repo()\n"), ([], []))
    eq("both an unconditional and a guarded arm are reported separately",
       arms("def main():\n    gate_selftest()\n"
            "    if '--prove-fires' in sys.argv:\n        prove_fires()\n"),
       (["gate_selftest"], ["prove_fires"]))

    return fails


def canary() -> int:
    """`--canary`: prove the gate's own verdict arithmetic fires, both ways.

    `selftest` covers the RESOLVER. These arms cover what the resolver's output
    is then used FOR — the bucket-to-verdict step, the floors, and the pin file
    in both directions. The 775 split: a classifier's self-test cannot reach
    its consumer's arithmetic.
    """
    import tempfile

    results: list[bool] = []

    def arm(name: str, ok: bool, detail: str = "") -> None:
        print(f"  {'✓' if ok else '✗'} {name}" + (f"  — {detail}" if not ok else ""))
        results.append(ok)

    fails = selftest()
    arm("the resolver's own arms pass", not fails, "; ".join(fails))

    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "armed.py").write_text("def main():\n    selftest()\n", encoding="utf-8")
        (d / "flagged.py").write_text(
            "import sys\ndef main():\n"
            "    if '--canary' in sys.argv:\n        canary()\n", encoding="utf-8")
        (d / "bare.py").write_text("def main():\n    return 0\n", encoding="utf-8")
        (d / "broken.py").write_text("def main(:\n", encoding="utf-8")

        rows = classify(d, ["armed.py", "flagged.py", "bare.py", "broken.py",
                            "absent.py"])
        arm("an armed check is credited", bool(rows["armed.py"]["unconditional"]))
        arm("a flag-gated check is NOT credited",
            not rows["flagged.py"]["unconditional"]
            and bool(rows["flagged.py"]["guarded"]))
        arm("a bare check is neither",
            not rows["bare.py"]["unconditional"] and not rows["bare.py"]["guarded"])
        arm("an unparseable check is an ERROR, never a bare check",
            "does not parse" in (rows["broken.py"]["error"] or ""))
        arm("a registered-but-missing check is an ERROR",
            "absent" in (rows["absent.py"]["error"] or ""))

        # The pin file, both directions.
        pin_path = d / "pins.txt"
        pin_path.write_text("# comment\nbare.py: a reason\n", encoding="utf-8")
        arm("a reasoned pin parses", read_pins(pin_path) == {"bare.py": "a reason"})
        pin_path.write_text("bare.py\n", encoding="utf-8")
        # The refusal prints its own ✗ INSTRUMENT line before raising, and a
        # passing canary that emits one is a canary whose next reader stops
        # trusting the output. Swallowed, then asserted to have been said.
        sink = io.StringIO()
        try:
            with contextlib.redirect_stdout(sink):
                read_pins(pin_path)
            arm("a reasonless pin is REFUSED", False, "it was accepted")
        except SystemExit as e:
            arm("a reasonless pin is REFUSED",
                e.code == 2 and "INSTRUMENT" in sink.getvalue(),
                f"exited {e.code}, said {sink.getvalue()!r}")

    # The ARM_NAMES vocabulary is the permissive direction: a widened set greens
    # everything silently, so the floor is not enough on its own — the set is
    # asserted not to contain the one name that would make it vacuous.
    arm("ARM_NAMES does not include `main` (which would credit every check)",
        "main" not in ARM_NAMES)
    arm("ARM_NAMES is non-empty", bool(ARM_NAMES))
    arm("MIN_ARMED is a floor under the live CHECKS count, not over it",
        MIN_ARMED <= MIN_CHECKS)

    print(f"\n{sum(results)}/{len(results)} canary arm(s) PASSED")
    return 0 if all(results) else 2


def prove_fires(commitish: str) -> int:
    """Known-answer validation against a tree whose answer is independently known.

    A ceiling nobody has watched fail is a pin nobody has validated
    (`restatement_drift_sweep`'s rule). `6804d983` is the commit that FILED
    Issue 789, so its `scripts/` is the measured pre-fix state: six CHECKS with
    no arm at all, plus `population_sync_gate`'s flag-gated canary. This gate
    must red there, and must name those seven.

    Opt-in rather than per-push, on the `platform_dead_code_floor_gate`
    precedent: a `git archive` to re-prove a fact about a frozen commit is
    worth a workstation run and not a push. Only `scripts/` is extracted —
    everything this gate reads lives there.
    """
    import subprocess
    import tempfile

    expected = {
        "cargo_comment_audit.py",
        "count_features.py",
        "docs_gate_checks_sync.py",
        "issue_citation_gate.py",
        "markdown_fence_gate.py",
        "population_sync_gate.py",   # flag-gated, not bare — the Issue 789 T2 case
        "skill_repo_set_gate.py",
    }
    with tempfile.TemporaryDirectory() as td:
        tar = Path(td) / "t.tar"
        r = subprocess.run(
            ["git", "-C", str(HERE.parent), "archive", "-o", str(tar),
             commitish, "scripts"],
            capture_output=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            print(f"✗ git archive {commitish} failed: {r.stderr.strip()}")
            return 2
        subprocess.run(["tar", "-xf", str(tar), "-C", td],
                       capture_output=True, encoding="utf-8", errors="replace")
        old = Path(td) / "scripts"
        names = list(parse_checks((old / "docs_gate.sh").read_text(encoding="utf-8")))
        rows = classify(old, names)
        unarmed = {n for n, row in rows.items() if not row["unconditional"]}

    print(f"▸ at {commitish}: {len(names)} CHECKS, {len(unarmed)} without an "
          f"unconditional arm")
    for n in sorted(unarmed):
        kind = "flag-gated" if rows[n]["guarded"] else "no arm at all"
        print(f"    ✗ {n} — {kind}")
    if unarmed == expected:
        print(f"✓ prove-fires PASSED — this gate reds at {commitish}, naming "
              f"exactly the {len(expected)} checks Issue 789 measured")
        return 0
    print(f"✗ prove-fires FAILED — expected {sorted(expected)}, got {sorted(unarmed)}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
