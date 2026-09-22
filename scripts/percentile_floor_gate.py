#!/usr/bin/env python3
"""Gate over `percentile_index_audit.py`, katgpt-rs scope only.

The report and the gate are deliberately separate files, for the reason
`cfg_gated_target_audit.py` and `cfg_gated_floor_gate.py` are: the report must
stay runnable over sibling repos whose owners have not taken this class of
work, and a report that exits 1 on them is a report nobody runs.

What this adds over the report: a `DEGENERATE` site introduced by a new commit
reds the push that adds it, **before** its number is quoted in a
`.benchmarks/` table as though it were a tail. Print-only or asserted — a
misleading number in a benchmark doc is the input to somebody's promote/demote
decision.

Exit 0 = pass, 1 = a pin moved, 2 = the instrument itself is untrustworthy
(the auditor's own `selftest()` failed, in which case no verdict is possible).
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import percentile_index_audit as pia  # noqa: E402

REPO = os.path.dirname(HERE)
PINS = os.path.join(HERE, "percentile_floors.txt")


def read_pins(path):
    pins = {}
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            key, _, val = line.partition("=")
            pins[key.strip()] = int(val.strip())
    return pins


def pin_failures(measured: dict, pins: dict) -> list[str]:
    """The gate's VERDICT arithmetic, extracted so an arm can reach it.

    Issue 790 T4. `percentile_index_audit.selftest()` runs on every invocation
    and it is the CLASSIFIER's arm — it cannot reach a single line of this
    file, which is Issue 775's sentence and the reason `arm_reach_audit`
    reported all 8 of this module's mutants as NO-ARM. The direction of each
    comparison IS the verdict: `>` where `>=` belongs silently tolerates one
    extra finding, and a floor compared the wrong way passes on a blind walk.

    `max_` = ceiling (over is a failure), `min_` = floor (under is a failure).
    A key with NEITHER prefix used to be silently unchecked — a pin that
    asserts nothing, which is worse than a missing one because it reads as
    coverage. It is a failure now; every live key already carries a prefix.
    """
    failures: list[str] = []
    for key, got in measured.items():
        pinned = pins.get(key)
        if pinned is None:
            failures.append(f"{key}: no pin in {os.path.basename(PINS)}")
            continue
        is_max, is_min = key.startswith("max_"), key.startswith("min_")
        if not (is_max or is_min):
            failures.append(
                f"{key}: neither a max_ nor a min_ pin, so its direction is "
                f"undefined and it was compared against NOTHING — rename it"
            )
            continue
        over = is_max and got > pinned
        under = is_min and got < pinned
        if over or under:
            failures.append(
                f"{key}: measured {got}, pinned {'<= ' if over else '>= '}{pinned}"
            )
    return failures


def gate_selftest() -> list[str]:
    """Arms over THIS file's pin arithmetic, which the classifier cannot reach."""
    fails: list[str] = []

    def eq(label, got, want):
        if got != want:
            fails.append(f"    {label}: got {got!r}, want {want!r}")

    def n(measured, pins):
        return len(pin_failures(measured, pins))

    # A ceiling: equal is fine, over is not, under is fine.
    eq("max_ at the pin passes", n({"max_x": 3}, {"max_x": 3}), 0)
    eq("max_ over the pin fails", n({"max_x": 4}, {"max_x": 3}), 1)
    eq("max_ under the pin passes", n({"max_x": 2}, {"max_x": 3}), 0)
    # A floor: equal is fine, under is not, over is fine.
    eq("min_ at the pin passes", n({"min_y": 3}, {"min_y": 3}), 0)
    eq("min_ under the pin fails", n({"min_y": 2}, {"min_y": 3}), 1)
    eq("min_ over the pin passes", n({"min_y": 4}, {"min_y": 3}), 0)
    # The two directions must not be interchangeable.
    eq("a floor is not a ceiling", n({"min_y": 99}, {"min_y": 3}), 0)
    eq("a ceiling is not a floor", n({"max_x": 0}, {"max_x": 3}), 0)
    # An unpinned key and an undirected key are both failures, never silence.
    eq("an unpinned key fails", n({"max_x": 0}, {}), 1)
    eq("a key with no max_/min_ prefix fails", n({"x": 0}, {"x": 0}), 1)
    # read_pins: comments, blanks and whitespace. Nothing reached this either —
    # `arm_reach_audit` reported the `if not line: continue` skip surviving a
    # dropped-`not` mutation, which would process blank lines and skip real ones.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "pins.txt")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("# a comment\n\n  max_x = 3   # trailing comment\nmin_y=4\n")
        eq("pins parse: comments, blanks and whitespace dropped",
           read_pins(p), {"max_x": 3, "min_y": 4})

    eq("every live measured key is directed",
       all(k.startswith(("max_", "min_")) for k in
           ("max_degenerate", "max_degenerate_asserted", "max_weak_asserted",
            "max_trunc_var", "min_sites_scanned")), True)
    return fails


def main():
    # Prints carry glyphs the Windows locale codecs cannot encode (checked
    # 2026-09-06 on cp874: check/cross/middot/arrow FAIL, em-dash OK); keep the
    # locale encoding and degrade only the fatal chars to escapes -- the
    # staged_set_audit house pattern (utf-8 pinning would mojibake legacy consoles).
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass  # not a TextIOWrapper (embedded / detached); keep old behavior
    # The auditor's selftest runs first and exits 2 on failure. Without it a
    # tokenizer regression would take every count to zero and this gate would
    # certify the repo clean on the strength of an instrument that had gone
    # blind.
    pia.selftest()
    # …and THIS file's own arithmetic, which that selftest cannot reach
    # (Issue 775's sentence, Issue 790 T4).
    arm_failures = gate_selftest()
    if arm_failures:
        print("✗ INSTRUMENT: percentile_floor_gate's own pin arithmetic does not "
              "pass its arms, so the comparison below would be unreadable:")
        for f in arm_failures:
            print(f)
        return 2

    pins = read_pins(PINS)
    findings = []
    for f in pia.walk_rs(REPO):
        findings += pia.audit_file(f, os.path.relpath(f, REPO))

    # DRY: the classification lives in the report, so this gate and the
    # cross-repo sweep can never disagree about what a DEGENERATE is. The
    # WEAK/TRUNC_VAR asymmetry (WEAK counted only when `asserted`, TRUNC_VAR
    # regardless) is documented at `pia.tally`.
    t = pia.tally(findings)
    degenerate, deg_asserted = t["degenerate"], t["degenerate_asserted"]
    weak_asserted, trunc_var = t["weak_asserted"], t["trunc_var"]

    measured = {
        "max_degenerate": len(degenerate),
        "max_degenerate_asserted": len(deg_asserted),
        "max_weak_asserted": len(weak_asserted),
        "max_trunc_var": len(trunc_var),
        "min_sites_scanned": len(t["sites"]),
    }

    failures = pin_failures(measured, pins)

    label = "percentile floor gate"
    if failures:
        print(f"✗ {label} FAILED")
        for f in failures:
            print(f"    {f}")
        for r in degenerate + weak_asserted + trunc_var:
            if r["verdict"] == pia.TRUNC_VAR:
                # p is a parameter here, so p/n/idx/support are all None and
                # printing them tells the reader nothing. The line is the finding.
                print(f"      {r['file']}:{r['line']}  {r['text']}")
            else:
                print(
                    f"      {r['file']}:{r['line']}  p={r['p']} n={r['n']} "
                    f"idx={r['idx']} support={r['support']} "
                    f"asserted={r['asserted']}"
                )
        print("    A 'p99' whose index is n-1 IS the max. Use nearest rank")
        print("    (ceil(p*n)-1) and report tail support, or drop the column")
        print("    when the sample count cannot support the quantile at all.")
        print("    See AGENTS.md § A reported \"p99\" is often the MAX.")
        return 1

    print(
        f"    ✓ {label} PASSED — {len(pins)} pins held "
        f"({measured['min_sites_scanned']} sites scanned, "
        f"0 degenerate, 0 asserted-weak, 0 trunc-var)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
