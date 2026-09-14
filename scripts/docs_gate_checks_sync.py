#!/usr/bin/env python3
"""GATE: docs_gate.sh's CHECKS array vs the AGENTS.md table that documents it.

The CHECKS array and AGENTS.md's "one line per check" table are hand-duplicated
lists of the same thing, and NOTHING compared them. That is precisely the shape
`docs_gate_paths_sync.py` already gates one axis over (docs_gate.yml's two
hand-duplicated trigger `paths:` lists) — the second instance of a class is
where you stop calling it a one-off.

Found because it had already drifted: docs_gate.sh described
`population_sync_gate.py` as "the **six** independent contract-repo
predicates" while the script's own docstring and AGENTS.md's table both said
**seven** (Issue 734 added the seventh). Six months of a wrong number sitting
in the output a human reads on every run.

TWO assertions, and they are deliberately different in strictness:

1. **MEMBERSHIP** of script names, both directions. Not cardinality — a count
   that MATCHES is not a checksum over a set, and the workspace has been
   burned by exactly that. A check registered but undocumented is invisible to
   whoever reads AGENTS.md to learn what the gate does; a documented check
   that is not registered is a check nobody runs.

2. **QUANTITY WORDS** in the two descriptions, after issue references are
   stripped. NOT the prose: the two lists legitimately differ in emphasis
   (`by membership` vs `by MEMBERSHIP`, `set -u abort` vs `abort`), and a gate
   demanding byte-identity here would be a gate people route around. What may
   NOT differ is a NUMBER — "six" vs "seven", "two lists" vs "three lists" —
   because a quantity is a claim, and a claim drifting between two copies is
   how this was found. Issue/plan numbers are stripped first: they are
   addresses, not quantities, and a row may cite one in the array and omit it
   in the table without contradicting anything (measured: 1 of 15 rows does).

Exit 0 clean, 1 on drift, **2 if the instrument is untrustworthy** (either
list unparseable, or a floor breached). A parser that silently reads ZERO rows
reports perfect agreement between two empty sets.
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
SH = HERE / "docs_gate.sh"
AGENTS = REPO_ROOT / "AGENTS.md"

# The AGENTS.md table is located by its SECTION heading, not by "any table row
# whose first cell looks like a .py file". A bare document-wide scan happens to
# work today and silently absorbs the next unrelated table somebody adds.
SECTION = "## Docs gate + drift sweeps"

# Floor: below this the parse went blind and two empty sets agree perfectly.
MIN_ROWS = 10

_CHECKS_BLOCK = re.compile(r"^CHECKS=\(\n(.*?)^\)$", re.S | re.M)
_CHECK_ROW = re.compile(r'^\s*"([^:"]+):(.*)"\s*$')
_TABLE_ROW = re.compile(r"^\|\s*`([A-Za-z0-9_]+\.py)`\s*\|\s*(.*?)\s*\|\s*$", re.M)

# Addresses, not quantities — stripped before the quantity comparison.
_ISSUE_REF = re.compile(r"\b(?:Issues?|Plans?|Research|Bench(?:mark)?s?)\s+\d[\d,\s/]*", re.I)
_QUANTITY = re.compile(
    r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b", re.I
)


def quantities(desc: str) -> list[str]:
    return sorted(q.lower() for q in _QUANTITY.findall(_ISSUE_REF.sub(" ", desc)))


def parse_checks(text: str) -> dict[str, str]:
    m = _CHECKS_BLOCK.search(text)
    if not m:
        print("✗ INSTRUMENT: no CHECKS=( ... ) array in docs_gate.sh — the array was "
              "renamed or reformatted; this gate cannot read it and must not report clean")
        raise SystemExit(2)
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        row = _CHECK_ROW.match(line)
        if row:
            out[row.group(1).split("/")[-1]] = row.group(2)
    return out


def parse_table(text: str) -> dict[str, str]:
    start = text.find(SECTION)
    if start < 0:
        print(f"✗ INSTRUMENT: AGENTS.md has no {SECTION!r} heading — the section was "
              "retitled; the table cannot be located")
        raise SystemExit(2)
    nxt = text.find("\n## ", start + len(SECTION))
    body = text[start : nxt if nxt > 0 else len(text)]
    return {m.group(1): m.group(2) for m in _TABLE_ROW.finditer(body)}


def selftest() -> list[str]:
    """Known-answer arms over the two parsers and the quantity extractor.

    Issue 789. This gate exists because two hand-duplicated lists drifted and
    nothing compared them; it then ran for days with nothing comparing IT to a
    known answer. Every arm below is an input whose correct output is decidable
    by reading it, which is the only kind this gate's arithmetic admits: the
    live inputs are the very files under test, so a "does it agree with itself"
    check would be vacuous.

    Pure string work — runs unconditionally at the top of `main()`.
    """
    import contextlib

    fails: list[str] = []

    def eq(label, got, want):
        if got != want:
            fails.append(f"    {label}: got {got!r}, want {want!r}")

    @contextlib.contextmanager
    def expect_exit(label: str, code: int):
        """Assert SystemExit(code), with the arm's own output SWALLOWED.

        Both refusal paths print an `✗ INSTRUMENT:` line before raising, and a
        clean run that prints two of them is a gate whose next reader assumes
        it is broken — the exact failure `docs_gate.sh`'s header warns about.
        """
        sink = io.StringIO()
        try:
            with contextlib.redirect_stdout(sink):
                yield
        except SystemExit as e:
            if e.code != code:
                fails.append(f"    {label}: exited {e.code!r}, want {code!r}")
            if "INSTRUMENT" not in sink.getvalue():
                fails.append(f"    {label}: exited {code} without saying why "
                             f"(no ✗ INSTRUMENT line) — a bare refusal is "
                             f"indistinguishable from a crash")
            return
        fails.append(f"    {label}: did not exit at all")

    # ── quantities(): an ADDRESS is not a quantity ─────────────────────────
    eq("a quantity survives", quantities("two hand-duplicated lists"), ["two"])
    eq("a digit is a quantity", quantities("710 row(s) scanned"), ["710"])
    eq("case is folded", quantities("Seven predicates"), ["seven"])
    eq("an issue address is stripped", quantities("membership (Issue 749)"), [])
    eq("a plan address is stripped", quantities("the rule (Plan 340)"), [])
    eq("a comma-listed address is stripped whole",
       quantities("a number allocated twice (Issues 724, 725)"), [])
    eq("a slash-composed address is stripped whole",
       quantities("the floor rule (Research 322 / Plan 340)"), [])
    eq("an address does not eat the quantity after it",
       quantities("the ten predicates must agree (Issue 788)"), ["ten"])
    eq("a task suffix does not extend the address",
       quantities("the row rule (Issue 513 T6) over two lists"), ["two"])
    # The input order is deliberately the REVERSE of the sorted order: with
    # "three ... two" both orders coincide and the arm cannot see `sorted()`
    # being dropped (measured — it read INERT under exactly that perturbation).
    eq("quantities are sorted, not positional",
       quantities("two lists and three rows"), ["three", "two"])
    eq("no quantity is an empty list, not None",
       quantities("membership both ways"), [])

    # ── parse_checks(): the array, and refusing to read zero ──────────────
    sample_sh = (
        'CHECKS=(\n'
        '  "scripts/alpha.py:first, with two lists"\n'
        '  "beta.py:second (Issue 749)"\n'
        ')\n'
    )
    eq("rows parse, basename only",
       parse_checks(sample_sh), {"alpha.py": "first, with two lists",
                                 "beta.py": "second (Issue 749)"})
    # A renamed or reformatted array must exit 2 — a parser that reads zero
    # rows reports perfect agreement between two empty sets.
    with expect_exit("a missing CHECKS array exits 2", 2):
        parse_checks("CHECK_LIST=(\n  \"alpha.py:x\"\n)\n")

    # ── parse_table(): SCOPED to the section, not a document-wide scan ─────
    sample_ag = (
        f"# doc\n\n{SECTION}\n\n"
        "| check | asserts |\n|---|---|\n"
        "| `alpha.py` | first, with two lists |\n"
        "| `beta.py` | second (Issue 749) |\n"
        "\n## Some Other Section\n\n"
        "| check | asserts |\n|---|---|\n"
        "| `gamma.py` | an unrelated table somebody added later |\n"
    )
    eq("the table parses inside its section",
       parse_table(sample_ag), {"alpha.py": "first, with two lists",
                                "beta.py": "second (Issue 749)"})
    eq("a later section's table is NOT absorbed",
       "gamma.py" in parse_table(sample_ag), False)
    with expect_exit("a retitled section exits 2", 2):
        parse_table("# doc\n\n## Retitled\n\n| `alpha.py` | x |\n")

    # The two extractors must agree on a row that is genuinely identical, and
    # disagree on one that drifts by a NUMBER while the prose merely differs in
    # emphasis — the whole asymmetry this gate is built on.
    eq("emphasis-only difference is not drift",
       quantities("pinned by membership") == quantities("pinned by MEMBERSHIP"), True)
    eq("a number difference IS drift",
       quantities("the six predicates") == quantities("the seven predicates"), False)

    return fails


def main() -> int:
    # The canary runs first. A parser that goes blind here does not report a
    # finding — it reports perfect agreement between two empty sets, which is
    # why the floors below and these arms both exist (exit 2, not 1).
    arm_failures = selftest()
    if arm_failures:
        print("✗ INSTRUMENT: docs_gate_checks_sync's own selftest does not pass, so "
              "the comparison below would be unreadable:")
        for f in arm_failures:
            print(f)
        return 2

    checks = parse_checks(io.open(SH, encoding="utf-8").read())
    table = parse_table(io.open(AGENTS, encoding="utf-8").read())

    for label, rows in (("docs_gate.sh CHECKS", checks), ("AGENTS.md table", table)):
        if len(rows) < MIN_ROWS:
            print(f"✗ INSTRUMENT: parsed {len(rows)} rows from {label} < floor {MIN_ROWS} — "
                  f"the parser went blind; two empty sets agree perfectly")
            return 2

    findings: list[str] = []
    only_sh = sorted(set(checks) - set(table))
    only_ag = sorted(set(table) - set(checks))
    for name in only_sh:
        findings.append(f"  {name} — in CHECKS, NOT in the AGENTS.md table: a check "
                        f"nobody reading the contract knows runs")
    for name in only_ag:
        findings.append(f"  {name} — in the AGENTS.md table, NOT in CHECKS: a documented "
                        f"check that nothing runs")

    for name in sorted(set(checks) & set(table)):
        a, b = quantities(checks[name]), quantities(table[name])
        if a != b:
            findings.append(
                f"  {name} — QUANTITY drift: docs_gate.sh says {a or '(none)'}, "
                f"AGENTS.md says {b or '(none)'}\n"
                f"      sh:     {checks[name][:110]}\n"
                f"      AGENTS: {table[name][:110]}")

    print(f"  {len(checks)} CHECKS row(s) vs {len(table)} AGENTS.md table row(s); "
          f"membership + quantity words compared (prose deliberately not)")
    if findings:
        print(f"✗ docs_gate CHECKS sync FAILED — {len(findings)} divergence(s)")
        for f in findings:
            print(f)
        return 1
    print(f"✓ docs_gate CHECKS sync PASSED — {len(checks)} rows agree by membership, "
          f"0 quantity drift")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
