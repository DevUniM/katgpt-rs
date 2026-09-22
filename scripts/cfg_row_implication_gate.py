#!/usr/bin/env python3
"""Gate on katgpt-rs having no target that compiles to NOTHING at its own row.

The verdict half of `cfg_row_implication_audit.py`, katgpt-rs-scoped and split
from the report for the reason every gate in this family is: the report must
stay runnable over siblings whose owners have not taken Issue 513, and a report
that exits 1 on them is a report nobody runs.

Gateable because it needs **no compiler** — the whole question is decided by a
manifest's feature graph and a source file's leading `#![cfg]`. And worth
gating because the defect is invisible to everything else: the row exists, so
`cfg_gated_target_audit.py` counts the reader as protected; the target builds,
so `required_features_build_audit.py` reports BUILDS; the harness prints
`ok. 0 passed` and cargo exits 0. Measured 2026-09-06, riir-train `054a39a2`:
fixing one such row took a target from 0 passed to 1 passed — an assertion
that had never executed at any revision.

## Pins (scripts/cfg_row_implication_floors.txt)

`max_empty_at_row` is a **WALL at 0**, not a ratchet: a row that compiles its
own target to nothing is never legitimate.

`max_unresolved` is a wall too, at katgpt-rs's measured 0 — but read it as the
narrower claim it is. UNRESOLVED means a predicate this report declines to rule
on (`any(feature = ...)`, or a feature under `not(...)`), not a clean row. A
sibling legitimately has them; this repo happens not to.

`min_rows_scanned` and `min_with_cfg` are **FLOORS**, for the reason every
floor in this family exists: the two ceilings above go green over whatever the
tokenizer can NAME, so a scanner regression takes the population to ~0 and both
ceilings pass, indistinguishable from a clean repo. That is not hypothetical
here — an early cut of the scanner reported two riir-train targets as "source
unreadable" (they use cargo's DIRECTORY form, `tests/<name>/main.rs`) and
silently skipped them.

Exit 0 clean · 1 drift · 2 the instrument is untrustworthy.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cfg_row_implication_audit as cria  # noqa: E402

FLOORS = Path(__file__).resolve().parent / "cfg_row_implication_floors.txt"
REQUIRED_PINS = {"max_empty_at_row", "max_unresolved", "min_rows_scanned", "min_with_cfg"}


def read_pins(path: Path) -> dict[str, int]:
    pins: dict[str, int] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        key, _, val = line.partition("=")
        pins[key.strip()] = int(val.strip())
    return pins


def pin_failures(measured: dict[str, int], pins: dict[str, int]) -> list[str]:
    """The gate's VERDICT arithmetic, extracted so an arm can reach it.

    Issue 790 T4. `cria.selftest()` runs first on every invocation and it is
    the CLASSIFIER's arm — it cannot reach a line of this file, which is Issue
    775's sentence and why `arm_reach_audit` reported all 12 of this module's
    mutants as NO-ARM. The four comparisons were inline in `main` with their
    messages, so the direction of each one was asserted by nothing: a ceiling
    compared as a floor passes on every count, and a floor compared as a
    ceiling passes on a walk that went blind — the exact failure the two floors
    exist to catch.

    The messages stay here with the arithmetic rather than in `main`: a reader
    who needs to know why a floor is a floor needs it next to the comparison.
    """
    ceilings = {
        "max_empty_at_row": ("empty_at_row", "EMPTY-AT-ROW", ""),
        "max_unresolved": ("unresolved", "UNRESOLVED", ""),
    }
    floors = {
        "min_rows_scanned": (
            "rows_scanned", "rows scanned",
            " — the manifest walk shrank, so both ceilings above are vacuous"),
        "min_with_cfg": (
            "with_cfg", "rows carry a leading #![cfg]",
            " — the source scanner narrowed, so a green here is a green over nothing"),
    }
    out: list[str] = []
    for key, (m_key, label, tail) in ceilings.items():
        if measured[m_key] > pins[key]:
            out.append(f"{label} {measured[m_key]} > pinned {pins[key]}{tail}")
    for key, (m_key, label, tail) in floors.items():
        if measured[m_key] < pins[key]:
            out.append(f"only {measured[m_key]} {label} < floor {pins[key]}{tail}")
    return out


def gate_selftest() -> list[str]:
    """Arms over THIS file's pin arithmetic, which `cria.selftest` cannot reach."""
    fails: list[str] = []

    def eq(label, got, want):
        if got != want:
            fails.append(f"    {label}: got {got!r}, want {want!r}")

    pins = {"max_empty_at_row": 0, "max_unresolved": 2,
            "min_rows_scanned": 700, "min_with_cfg": 400}
    ok = {"empty_at_row": 0, "unresolved": 2, "rows_scanned": 710, "with_cfg": 479}

    eq("the live shape passes", pin_failures(ok, pins), [])
    # Each ceiling, one at a time: equal passes, over fails.
    eq("a ceiling at its pin passes",
       pin_failures({**ok, "unresolved": 2}, pins), [])
    eq("a ceiling over its pin fails",
       len(pin_failures({**ok, "unresolved": 3}, pins)), 1)
    eq("the empty-at-row ceiling fails on ONE row",
       len(pin_failures({**ok, "empty_at_row": 1}, pins)), 1)
    # Each floor, one at a time: equal passes, under fails. A floor compared
    # the wrong way is the blind-walk green these exist to prevent.
    eq("a floor at its pin passes",
       pin_failures({**ok, "rows_scanned": 700}, pins), [])
    eq("a floor under its pin fails",
       len(pin_failures({**ok, "rows_scanned": 699}, pins)), 1)
    eq("the with-cfg floor is independent of the row floor",
       len(pin_failures({**ok, "with_cfg": 399}, pins)), 1)
    # A walk that collapses to nothing must red on BOTH floors, not neither.
    eq("a fully blind walk fails both floors",
       len(pin_failures({"empty_at_row": 0, "unresolved": 0,
                         "rows_scanned": 0, "with_cfg": 0}, pins)), 2)
    # The pin keys and the measured keys must stay in step.
    eq("every REQUIRED_PIN is consumed by the arithmetic",
       REQUIRED_PINS - set(ceiling_and_floor_keys()), set())

    # read_pins: comments, blanks and whitespace. Nothing reached this — the
    # `if not line: continue` skip survived a dropped-`not` mutation, which
    # processes blank lines and skips real ones.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "pins.txt"
        p.write_text("# a comment\n\n  max_unresolved = 2   # trailing\n"
                     "min_with_cfg=400\n", encoding="utf-8")
        eq("pins parse: comments, blanks and whitespace dropped",
           read_pins(p), {"max_unresolved": 2, "min_with_cfg": 400})
    return fails


def ceiling_and_floor_keys() -> set[str]:
    """The pin keys `pin_failures` actually compares against.

    Named rather than inlined so `gate_selftest` can assert that every
    REQUIRED_PIN is CONSUMED: a required pin nobody compares is a pin that
    asserts nothing, and it reads as coverage — the same hazard
    `percentile_floor_gate.pin_failures` now refuses for an undirected key.
    """
    return {"max_empty_at_row", "max_unresolved",
            "min_rows_scanned", "min_with_cfg"}


def main(argv: list[str]) -> int:
    # Prints carry glyphs the Windows locale codecs cannot encode (checked
    # 2026-09-06 on cp874: check/cross/middot/arrow FAIL, em-dash OK); keep the
    # locale encoding and degrade only the fatal chars to escapes -- the
    # staged_set_audit house pattern (utf-8 pinning would mojibake legacy consoles).
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass  # not a TextIOWrapper (embedded / detached); keep old behavior
    # The report's selftest exits 2 on its own; run it first so an
    # untrustworthy instrument is never mistaken for moved pins.
    cria.selftest()
    # …and THIS file's own pin arithmetic, which that selftest cannot reach
    # (Issue 775's sentence, Issue 790 T4).
    arm_failures = gate_selftest()
    if arm_failures:
        print("✗ INSTRUMENT: cfg_row_implication_gate's own pin arithmetic does not "
              "pass its arms, so the verdict below would be unreadable:")
        for f in arm_failures:
            print(f)
        return 2

    if not FLOORS.is_file():
        print(f"✗ pins file missing: {FLOORS}")
        return 2
    pins = read_pins(FLOORS)
    missing = REQUIRED_PINS - set(pins)
    if missing:
        print(f"✗ pins file is missing required keys: {sorted(missing)}")
        return 2

    repo = Path(argv[0]).resolve() if argv else Path(__file__).resolve().parent.parent
    found = cria.audit_repo(repo)
    n_rows = len(found)
    empty = sum(1 for f in found if f.verdict == cria.EMPTY)
    unres = sum(1 for f in found if f.verdict == cria.UNRESOLVED)
    with_cfg = sum(1 for f in found if f.verdict != cria.NO_CFG)

    fails = pin_failures(
        {"empty_at_row": empty, "unresolved": unres,
         "rows_scanned": n_rows, "with_cfg": with_cfg}, pins)

    if fails:
        print("✗ cfg-row-implication gate FAILED:")
        for f in fails:
            print(f"    {f}")
        for f in found:
            if f.verdict == cria.EMPTY:
                print(f"    EMPTY-AT-ROW  {f.row.label}  row={f.row.features} "
                      f"MISSING {sorted(f.missing)}")
            elif f.verdict == cria.UNRESOLVED:
                print(f"    UNRESOLVED    {f.row.label}  {f.why}")
        return 1

    print(f"✓ cfg-row-implication gate PASSED — {n_rows} rows, {with_cfg} with a "
          f"leading #![cfg], {empty} empty-at-row, {unres} unresolved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
