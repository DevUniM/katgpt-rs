#!/usr/bin/env python3
"""GATE: an item declared ungated whose EVERY use is behind a platform cfg.

The verdict half of `platform_dead_code_audit.py` (Issue 775), scoped to this
repo — the same split, and for the same reason, as
`cfg_gated_target_audit.py` / `cfg_gated_floor_gate.py` and
`percentile_index_audit.py` / `percentile_floor_gate.py`: the report must stay
runnable over sibling repos whose owners have not taken this class of work, and
a report that exits 1 on them is a report nobody runs.

## Why this class needs a gate more than most

Every other lint in this workspace is caught by a compiler somewhere. This one
is caught by a compiler **nowhere automatic**: `full_gate.yml` is
macOS/aarch64, `wasm32_gate.yml` is wasm32, and the x86_64-native lane that
actually emits `dead_code` for an aarch64-only helper is a WORKSTATION lane.
`ea4c2873` — `const NEON_U8: usize = 16;` declared ungated, used only inside an
`#[cfg(target_arch = "aarch64")]` fn — was found by a human reading a Windows
`--all-features` build. Five specimens turned up in two days across two repos
once anyone looked (riir-clippy intake P22).

An instrument that closes that hole and is itself run by nothing has moved the
hole one level up, which is exactly what Issue 775 filed.

## The three arms, and why each is not the other

1. **The classifier's own 24-arm self-test, FIRST.** `audit.selftest()` pins
   the buckets in both directions over synthetic trees, end to end (walk ->
   mask -> scan -> resolve -> classify). A gate whose classifier stopped
   classifying reports a green zero over everything — the failure this repo
   keeps re-finding. Exit **2**, never 1: an untrustworthy instrument is a
   different verdict from drift.

2. **This gate's OWN comparison logic, pinned in both directions.**
   `gate_selftest()` runs `evaluate()` against a synthetic green measurement
   and then against one perturbation per pin, and requires each to breach. The
   audit's self-test cannot reach this half — it pins the classifier, not the
   pin arithmetic — and a `measured` key that stops matching a pin name is
   silently never compared. Cost: microseconds, because it is pure arithmetic
   over a dict.

   That is the cheap half of "a ceiling nobody has watched fail certifies
   nothing". The expensive half — `--prove-fires ea4c2873`, which extracts the
   real known-answer tree and requires NEON_U8 PRESENT at `~1` and absent at
   the fix — lives in `platform_dead_code_drift_sweep.py`, where it runs by
   DEFAULT. It is not in this per-push path on cost grounds, stated rather
   than buried: measured 2026-09-14, this gate is ~6.2s and `--prove-fires`
   adds ~5.6s (two `git archive` extractions plus two 268-file audits) against
   a whole-docs-gate budget of ~13s CPU. Running it here would nearly double
   the per-push gate to re-prove, on every push, a fact about a frozen commit.
   It is accepted here too (`--prove-fires`), for anyone who wants both in one
   command.

3. **Two floors and a membership pin**, in `platform_dead_code_floors.txt` —
   the reasoning lives there, next to the numbers it justifies.

Exit 0 clean · 1 on drift · **2 if the instrument is untrustworthy** (either
self-test failed, or the pins file parsed to nothing — a parser that returns no
pins disarms every ceiling under it).
"""

from __future__ import annotations

import contextlib
import importlib
import io
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

REPO = HERE.parent
PINS = HERE / "platform_dead_code_floors.txt"

NUMERIC_KEYS = ("max_findings", "min_rs_files", "min_candidate_decls")


def load_audit():
    """Import the report half, or REFUSE — never fall back to a local copy.

    Issue 755's rule: a second copy of a classifier this subtle is a second
    thing to get wrong. If the report is gone, this gate has no verdict to
    read and must say so rather than print a green over an absence.
    """
    path = HERE / "platform_dead_code_audit.py"
    if not path.is_file():
        print(f"✗ platform dead_code floor gate FAILED — {path} is MISSING; the "
              f"classifier this gate reads its verdicts from is gone, so a green "
              f"here would mean nothing")
        raise SystemExit(2)
    # A plain import, NOT spec_from_file_location + exec_module: the report
    # half uses @dataclass, and a module executed without being registered in
    # `sys.modules` makes `dataclasses._is_type` dereference a None module —
    # the gate dies with an AttributeError from inside the stdlib, which reads
    # like a broken gate rather than a missing classifier. HERE is already on
    # sys.path, so the name resolves to the file probed above.
    return importlib.import_module("platform_dead_code_audit")


def read_pins(path: Path) -> dict:
    """`key = value` numerics plus repeatable `modref = <path>:<name>` rows."""
    pins: dict = {"modref": set()}
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip()
            if key == "modref":
                pins["modref"].add(val)
            elif key in NUMERIC_KEYS:
                pins[key] = int(val)
            else:
                # Never ignored: a typo'd pin name would otherwise sit in the
                # file looking load-bearing while comparing nothing.
                print(f"✗ INSTRUMENT: unknown pin {key!r} in {path.name} — a pin this "
                      f"gate does not read is a pin that certifies nothing")
                raise SystemExit(2)
    missing = [k for k in NUMERIC_KEYS if k not in pins]
    if missing:
        print(f"✗ INSTRUMENT: {path.name} is missing pin(s) {', '.join(missing)} — "
              f"a parser that returns nothing for both 'absent' and 'malformed' "
              f"disarms every ceiling below it")
        raise SystemExit(2)
    return pins


def evaluate(measured: dict, pins: dict) -> list[str]:
    """The whole verdict, as a pure function — so it can be canaried.

    `measured` is {files, candidates, findings (int), modref (set of
    "<path>:<name>")}. Returns breach descriptions; empty = pass.
    """
    bad: list[str] = []

    if measured["files"] < pins["min_rs_files"]:
        bad.append(f"min_rs_files: walked {measured['files']} tracked .rs < floor "
                   f"{pins['min_rs_files']} — the WALK went blind; a ceiling over "
                   f"zero files is green for the wrong reason")
    if measured["candidates"] < pins["min_candidate_decls"]:
        bad.append(f"min_candidate_decls: {measured['candidates']} candidate decl(s) "
                   f"< floor {pins['min_candidate_decls']} — the PARSE went blind "
                   f"(the walk can be intact while the token pass yields nothing)")
    if measured["findings"] > pins["max_findings"]:
        bad.append(f"max_findings: {measured['findings']} > ceiling "
                   f"{pins['max_findings']} — an item is dead on every platform but "
                   f"one, and no automatic lane compiles the one that says so")

    unpinned = sorted(measured["modref"] - pins["modref"])
    if unpinned:
        bad.append("MOD-REF row(s) not pinned (a `mod` decl referenced only from "
                   "platform-gated code — read it once, then pin it or gate it): "
                   + ", ".join(unpinned))
    gone = sorted(pins["modref"] - measured["modref"])
    if gone:
        bad.append("pinned MOD-REF row(s) no longer measured — either the module was "
                   "gated/removed (good: drop the pin in that commit) or the "
                   "classifier stopped seeing it (not good, and set-identical from "
                   "here): " + ", ".join(gone))
    return bad


# ── the gate's OWN canary: one perturbation per pin, both directions ─────────
_CANARY_PINS = {"max_findings": 0, "min_rs_files": 100, "min_candidate_decls": 1000,
                "modref": {"a/b.rs:m"}}
_CANARY_GREEN = {"files": 200, "candidates": 2000, "findings": 0,
                 "modref": {"a/b.rs:m"}}
_CANARY_ARMS = (
    ("a walk collapse",           {"files": 99}),
    ("a parse collapse",          {"candidates": 999}),
    ("one new finding",           {"findings": 1}),
    ("an UNPINNED MOD-REF row",   {"modref": {"a/b.rs:m", "c/d.rs:n"}}),
    ("a pinned MOD-REF row gone", {"modref": set()}),
    # The swap is the arm a CARDINALITY pin cannot fail: one row out, one row
    # in, count unchanged at 1. It is why the pin is membership.
    ("a MOD-REF SWAP (count unchanged)", {"modref": {"c/d.rs:n"}}),
)


# ⚑ Issue 790 T3: `_CANARY_ARMS` drives each floor to pin MINUS ONE, which a
# `<` and a `<=` both reject — so `arm_reach_audit` reported both floor
# comparisons SURVIVING a `< -> <=` flip. A floor is pinned only by the two
# values either side of it, and the value AT the pin is the one a `<=` gets
# wrong: it reds the very measurement the pin declares acceptable, which is a
# gate that cannot be satisfied at all.
_CANARY_AT_FLOOR = (
    ("files exactly AT min_rs_files",         {"files": 100}),
    ("candidates exactly AT min_candidate_decls", {"candidates": 1000}),
    ("findings exactly AT max_findings",      {"findings": 0}),
)


def gate_selftest() -> list[str]:
    fails = []
    if evaluate(_CANARY_GREEN, _CANARY_PINS):
        fails.append("the GREEN canary measurement reports a breach — this gate "
                     "would red on a clean repo")
    for label, delta in _CANARY_ARMS:
        if not evaluate({**_CANARY_GREEN, **delta}, _CANARY_PINS):
            fails.append(f"the pin comparison is INERT for: {label}")
    for label, delta in _CANARY_AT_FLOOR:
        if evaluate({**_CANARY_GREEN, **delta}, _CANARY_PINS):
            fails.append(f"a measurement exactly at its pin REDS: {label} — the "
                         f"comparison is off by one and the pin cannot be met")
    fails += _read_pins_arms()
    return fails


def _read_pins_arms() -> list[str]:
    """Arms over the pin READER — the fifth unarmed one this audit found.

    Every floor gate in this repo had one, and the reader is load-bearing in
    the QUIET direction: a filter that drops a real row, or a completeness
    check that passes on an incomplete file, hands `evaluate` a dict with a
    missing key. This reader has two behaviours the others do not — a
    repeatable `modref` row and a REFUSAL on an unknown pin name — and both
    were asserted by nothing.
    """
    import tempfile
    fails: list[str] = []

    def refuses(label: str, body: str) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "pins.txt"
            p.write_text(body, encoding="utf-8")
            sink = io.StringIO()
            try:
                with contextlib.redirect_stdout(sink):
                    read_pins(p)
            except SystemExit as e:
                if e.code != 2 or "INSTRUMENT" not in sink.getvalue():
                    fails.append(f"{label}: exited {e.code} saying "
                                 f"{sink.getvalue()!r}; want 2 with a reason")
                return
            fails.append(f"{label}: was ACCEPTED")

    numeric = "\n".join(f"{k} = {v}" for k, v in
                        (("max_findings", 0), ("min_rs_files", 100),
                         ("min_candidate_decls", 1000)))
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "pins.txt"
        p.write_text(f"# a comment\n\n{numeric}\n"
                     f"modref = a/b.rs:m\nmodref = c/d.rs:n   # repeatable\n   \n",
                     encoding="utf-8")
        got = read_pins(p)
        want = {"max_findings": 0, "min_rs_files": 100,
                "min_candidate_decls": 1000, "modref": {"a/b.rs:m", "c/d.rs:n"}}
        if got != want:
            fails.append(f"read_pins parsed {got}, want {want} — comments, blanks "
                         f"and whitespace-only lines must all be dropped, every "
                         f"numeric row kept, and `modref` ACCUMULATED not replaced")

    # Both refusals. The unknown-pin one is the interesting direction: a typo'd
    # name would otherwise sit in the file looking load-bearing while comparing
    # nothing — the reader's own comment says so, and nothing checked it.
    refuses("an unknown pin name", f"{numeric}\nmax_findigns = 0\n")
    refuses("a file missing a required numeric pin",
            numeric.replace("min_rs_files = 100", ""))
    return fails


def main() -> int:
    # A cp874/cp1252 console cannot encode this file's glyphs and the
    # UnicodeEncodeError masquerades as a gate failure. Degrade only the fatal
    # chars (the staged_set_audit house pattern) rather than pinning utf-8,
    # which mojibakes legacy consoles.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass

    audit = load_audit()

    if audit.selftest():          # prints its own 24 arms; 2 = classifier MISS
        print("✗ platform dead_code floor gate FAILED — the classifier's own "
              "self-test does not pass, so every count below is unreadable")
        return 2
    instrument = gate_selftest()
    if instrument:
        for f in instrument:
            print(f"✗ INSTRUMENT: {f}")
        return 2

    if "--prove-fires" in sys.argv:
        # Accepted, not required — see the docstring's arm 2. The sweep runs
        # this by default; here it is opt-in so the per-push budget stays ~6s.
        rc = audit.prove_fires(REPO, "ea4c2873", "NEON_U8", "crates/katgpt-pruners")
        if rc:
            return rc

    pins = read_pins(PINS)
    res = audit.audit_repo(REPO)
    measured = {
        "files": res.files,
        "candidates": res.candidates,
        "findings": len(res.findings),
        "modref": {f"{m.rel}:{m.name}" for m in res.mod_rows},
    }
    bad = evaluate(measured, pins)

    if bad:
        print("✗ platform dead_code floor gate FAILED")
        for b in bad:
            print(f"    {b}")
        for f in res.findings:
            print(audit.row_line(f, "⛔"))
        for m in res.mod_rows:
            print(audit.row_line(m, "·"))
        print("    The repair is one attribute: give the declaration the same cfg "
              "its uses already carry. Do NOT raise the ceiling — see "
              "AGENTS.md § An item can be dead on a platform NO lane compiles.")
        return 1

    print(f"    ✓ platform dead_code floor gate PASSED — 0 finding(s) over "
          f"{measured['files']} tracked .rs file(s) (floor {pins['min_rs_files']}) "
          f"/ {measured['candidates']} candidate decl(s) (floor "
          f"{pins['min_candidate_decls']}), {len(pins['modref'])} pinned MOD-REF "
          f"row(s) still measured, {len(_CANARY_ARMS)} pin canary arm(s) armed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
