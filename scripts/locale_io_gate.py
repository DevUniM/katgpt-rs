#!/usr/bin/env python3
"""Gate on text I/O that decodes/encodes with the SYSTEM locale (Issue 829).

`Path.read_text()`, `Path.write_text()` and builtin `open()` in text mode use
`locale.getencoding()` when no `encoding=` is given. This is
`subprocess_encoding_gate.py`'s class one seam over — the FILE seam rather
than the PIPE seam — and it went unlooked-at for the same reason: macOS,
`ubuntu-latest` and the M3 are all UTF-8, so **nothing that could notice ever
runs it**, while this repo's instruments write and read `✓`, `⛔` and em
dashes on every path.

## How it was found, which is the argument for a gate

Not by a census. `citation_drift_sweep.selftest()` writes a fixture HISTORY.md
with a bare `write_text` and reads it back with `encoding="utf-8",
errors="replace"`. On the Windows workstation (**cp874**) U+2014 encodes to
the single byte `0x97`, so the fixture's em dashes came back as U+FFFD. Every
arm in that file had been passing over a corrupted fixture; it was invisible
until Issue 828 wrote an arm whose subject WAS the dash, and that arm then
failed for a reason that made no sense (`(1, 5)` in the harness, `(3, 6)` by
hand, same bytes).

That is the failure mode to internalise: a locale write does not raise and
does not look wrong. It makes a test pass **for the wrong reason**, and the
louder the fixture, the longer it hides.

## The population, and why it is the whole tree

Tracked `*.py`, not `scripts/*.py`. `subprocess_encoding_gate`'s first real
run found a site in `.agents/skills/doc-sync/tools/`, outside `scripts/`
entirely, and this one's census found two more in `.benchmarks/` and
`.agents/`. The seam is a Python idiom, not a directory.

## Two floors, and they break separately

`min_py_files` is the WALK: a `git ls-files` regression takes the population
to zero and the ceiling is green over nothing. `min_io_calls` is the
PREDICATE: the walk is intact, the AST pass finds no text I/O at all, and the
ceiling is green over nothing again. Neither detects the other.

## AST, never text

A `write_text(` inside a fixture string is not a call. This repo has met that
exact false positive three times — `subprocess_encoding_gate` moved to an AST
because its text scanner "reported four offenders in the gate's own file,
every one a fixture string inside its `selftest()`"; `platform_dead_code_audit`
masks literals; `wasm32_surface_audit` reads attributes. A file the parser
cannot read is **UNPARSED** and reds, never folded into the pass column.

    scripts/locale_io_gate.py                # this repo, per push
    scripts/locale_io_gate.py ../riir-ai     # or one, by path
    scripts/locale_io_gate.py --canary       # the arms over its own pin arithmetic
    scripts/locale_io_gate.py --prove-fires 072a083b
"""

from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tracked_walk import tracked_files  # noqa: E402
from locale_io_fix import sites as unencoded_sites  # noqa: E402 — ONE classifier, shared with the repair half

import console_safe  # noqa: E402

console_safe.apply()

REPO_ROOT = Path(__file__).resolve().parent.parent

# Measured 2026-09-18 on katgpt-rs: 87 tracked .py, 643 text-I/O call sites
# (Issue 830 widened the classifier from three call NAMES to the text-mode
# file-object class, so the site count is not comparable to the 635 measured
# against the three-name predicate hours earlier).
# Slack against ordinary churn, tight against a walk or parse regression.
FLOOR_PY_FILES = 60
FLOOR_IO_CALLS = 450

# Exemptions, by MEMBERSHIP with a REASON per row. Deliberately EMPTY: a row
# reading "not repaired yet" is a backlog wearing a pin (Issue 785's rule),
# and the repair is one mechanical pass (`scripts/locale_io_fix.py`).
EXPECTED = REPO_ROOT / "scripts" / "locale_io_expected.txt"

PATH_METHODS = {"write_text", "read_text"}


def _text_io_calls(tree: ast.AST) -> int:
    """Every text-I/O call, encoded or not — the PREDICATE floor's population.

    Counting only the offenders would make the floor a restatement of the
    ceiling, and *a pin that restates its own input cannot fail*.
    """
    n = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr in PATH_METHODS:
            n += 1
        elif isinstance(node.func, ast.Name) and node.func.id == "open":
            n += 1
    return n


def scan_text(src: str) -> tuple[list[str], int]:
    """(offender rows, text-I/O call sites) for one source text.

    Raises `SyntaxError` on unparseable input; the caller must surface that
    rather than count it clean.
    """
    rows = []
    for node in unencoded_sites(src):
        head = " ".join(ast.unparse(node).split())[:90]
        rows.append(f"{node.lineno}: {head}")
    return rows, _text_io_calls(ast.parse(src))


def scan(repo: Path) -> tuple[dict, int, int, list[str]]:
    """(offenders by file, tracked .py, io call sites, unparsed) for a repo."""
    out: dict = {}
    unparsed: list[str] = []
    calls = 0
    files, _ = tracked_files(repo, "*.py")
    for p in files:
        rel = str(p.relative_to(repo)).replace("\\", "/")
        try:
            src = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            unparsed.append(f"{rel}: unreadable")
            continue
        try:
            rows, n = scan_text(src)
        except SyntaxError as e:
            unparsed.append(f"{rel}:{e.lineno}: {e.msg}")
            continue
        calls += n
        if rows:
            out[rel] = rows
    return out, len(files), calls, unparsed


def read_expected() -> tuple[set[str], list[str]]:
    """(exempt paths, complaints). A reasonless row is REFUSED."""
    exempt: set[str] = set()
    bad: list[str] = []
    if not EXPECTED.is_file():
        return exempt, ["scripts/locale_io_expected.txt is missing — the "
                        "exemption set is the permissive direction and must "
                        "exist even when empty"]
    for i, line in enumerate(
            EXPECTED.read_text(encoding="utf-8").splitlines(), 1):
        row = line.strip()
        if not row or row.startswith("#"):
            continue
        path, _, reason = row.partition("#")
        path = path.strip()
        if not reason.strip():
            bad.append(f"{EXPECTED.name}:{i}: `{path}` has no reason — a pin "
                       "without one is a backlog wearing a pin")
            continue
        exempt.add(path)
    return exempt, bad


def verdict(offenders: dict, py_files: int, calls: int, unparsed: list[str],
            exempt: set[str]) -> list[str]:
    """The gate's own pin arithmetic, EXTRACTED so an arm can reach it.

    Inline in `main()` beside its error messages it is unreachable by
    construction — Issue 789's finding, which cost four gates an arm each.
    """
    problems: list[str] = []
    live = {k: v for k, v in offenders.items() if k not in exempt}
    n = sum(len(v) for v in live.values())
    if unparsed:
        problems.append(f"{len(unparsed)} file(s) the parser could not read — "
                        "UNPARSED is the instrument admitting it cannot see, "
                        "never a pass")
    if n:
        problems.append(f"{n} text-I/O call(s) use the system locale — run "
                        "`scripts/locale_io_fix.py <paths>`")
    # A stale exemption reds too, so the file cannot only ever loosen.
    for path in sorted(exempt - set(offenders)):
        problems.append(f"stale exemption `{path}` — it has no offending site "
                        "now, so the row certifies nothing")
    if py_files < FLOOR_PY_FILES:
        problems.append(f"walk FLOOR breached: {py_files} tracked .py < "
                        f"{FLOOR_PY_FILES} — the ceiling above is green over a "
                        "population that shrank")
    if calls < FLOOR_IO_CALLS:
        problems.append(f"parse FLOOR breached: {calls} text-I/O call site(s) < "
                        f"{FLOOR_IO_CALLS} — the walk is intact but the AST "
                        "pass found nothing")
    return problems


def selftest() -> list[str]:
    """Both directions, every invocation. The false-NEGATIVE direction is the
    one that matters: a classifier regression prints `0 offenders` forever,
    which is the same output as the clean state this asserts."""
    fails: list[str] = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    for label, src in {
        "write_text": 'p.write_text(s)\n',
        "read_text": 'p.read_text()\n',
        "open default": 'open(p)\n',
        "open explicit text mode": 'open(p, "w")\n',
        "wrapped": 'p.write_text(\n    s,\n)\n',
    }.items():
        rows, _ = scan_text(src)
        check(len(rows) == 1, f"missed the {label} form: {rows}")

    for label, src in {
        "pinned write": 'p.write_text(s, encoding="utf-8")\n',
        "pinned read": 'p.read_text(encoding="utf-8", errors="replace")\n',
        "pinned open": 'open(p, encoding="utf-8")\n',
        "binary read": 'open(p, "rb")\n',
        "binary keyword": 'open(p, mode="wb")\n',
        "write_bytes": 'p.write_bytes(b)\n',
        "kwargs splat is UNKNOWN": 'open(p, **kw)\n',
    }.items():
        rows, _ = scan_text(src)
        check(rows == [], f"false positive on {label}: {rows}")

    # A STRING containing the offending source is DATA. Not hypothetical —
    # three instruments in this repo have shipped this exact false positive.
    rows, n = scan_text('SRC = "p.write_text(s)"\nDOC = """open(p)"""\n')
    check((rows, n) == ([], 0),
          f"a string literal was scanned as code: rows={rows} calls={n}")

    # UNPARSED must RAISE, not read clean.
    try:
        scan_text("def f(:\n")
        fails.append("an unparseable source did not raise — it would read clean")
    except SyntaxError:
        pass

    # The PREDICATE floor counts compliant calls too, or it restates the
    # ceiling and cannot fail.
    _, n = scan_text('p.write_text(s, encoding="utf-8")\nopen(q, "rb")\n')
    check(n == 2, f"the floor population excluded compliant calls: {n}")

    return fails


def canary() -> list[str]:
    """Arms over this gate's OWN pin arithmetic, which `selftest` cannot reach.

    Issue 775's rule: a classifier's self-test asserts the classifier. The
    verdict — floors, exemption staleness, the UNPARSED wall — is a second
    body of logic, and four gates in this repo had none until it was measured.
    """
    fails: list[str] = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    ok = ({}, FLOOR_PY_FILES, FLOOR_IO_CALLS, [], set())
    check(verdict(*ok) == [], "the clean case is not clean")

    check(len(verdict({"a.py": ["1: p.write_text(s)"]}, FLOOR_PY_FILES,
                      FLOOR_IO_CALLS, [], set())) == 1,
          "an offender did not produce a problem")
    check(verdict({"a.py": ["1: p.write_text(s)"]}, FLOOR_PY_FILES,
                  FLOOR_IO_CALLS, [], {"a.py"}) == [],
          "an exemption did not suppress its own row")
    check(len(verdict({}, FLOOR_PY_FILES, FLOOR_IO_CALLS, [], {"a.py"})) == 1,
          "a STALE exemption did not red — the file could only ever loosen")
    check(len(verdict({}, FLOOR_PY_FILES, FLOOR_IO_CALLS, ["x.py: boom"],
                      set())) == 1,
          "UNPARSED did not red — an instrument that cannot read read clean")
    check(len(verdict({}, FLOOR_PY_FILES - 1, FLOOR_IO_CALLS, [], set())) == 1,
          "the WALK floor did not fire")
    check(len(verdict({}, FLOOR_PY_FILES, FLOOR_IO_CALLS - 1, [], set())) == 1,
          "the PREDICATE floor did not fire")
    # The two floors are independent: a run under BOTH must report both, or
    # repairing one hides the other.
    check(len(verdict({}, FLOOR_PY_FILES - 1, FLOOR_IO_CALLS - 1, [],
                      set())) == 2,
          "the two floors were pooled into one problem")
    check(FLOOR_PY_FILES > 0 and FLOOR_IO_CALLS > 0,
          "a floor pinned at 0 or less cannot fail")

    # The exemption READER, the permissive direction — a reasonless row must
    # be refused, or the file silently widens.
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "e.txt"
        global EXPECTED
        keep = EXPECTED
        try:
            EXPECTED = p
            p.write_text("# a comment\na.py  # a stated reason\n",
                         encoding="utf-8")
            ex, bad = read_expected()
            check(ex == {"a.py"} and bad == [],
                  f"a reasoned row was not read: {ex} {bad}")
            p.write_text("a.py\n", encoding="utf-8")
            ex, bad = read_expected()
            check(ex == set() and len(bad) == 1,
                  f"a REASONLESS row was accepted: {ex} {bad}")
            EXPECTED = Path(td) / "absent.txt"
            ex, bad = read_expected()
            check(len(bad) == 1,
                  "a MISSING exemption file read as an empty, valid one")
        finally:
            EXPECTED = keep
    return fails


def prove_fires(commit: str) -> int:
    """Known-answer validation against a frozen tree.

    `072a083b` is Issue 828's landing commit: the whole repo bar
    `citation_drift_sweep.py` still carried the defect there, so this gate
    must RED with a large finding count. Opt-in, on the
    `platform_dead_code_floor_gate` precedent — a `git archive` to re-derive a
    fact about a frozen commit is worth a workstation run, not a per-push one.
    """
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        tar = root / "t.tar"
        with open(tar, "wb") as fh:
            subprocess.run(["git", "-C", str(REPO_ROOT), "archive", commit],
                           stdout=fh, check=True)
        subprocess.run(["tar", "-xf", str(tar), "-C", str(root)], check=True)
        tar.unlink()
        found, files, calls, unparsed = scan(root)
        n = sum(len(v) for v in found.values())
        print(f"  {commit}: {n} offender(s) over {files} .py / {calls} call(s), "
              f"{len(unparsed)} unparsed")
        if n < 100:
            print(f"✗ prove-fires FAILED — {commit} carried the defect "
                  f"repo-wide and this gate found only {n}")
            return 1
    print(f"✓ prove-fires PASSED — the gate reds on {commit}")
    return 0


def main(argv: list[str]) -> int:
    fails = selftest()
    if "--canary" in argv:
        fails += canary()
    if fails:
        print("✗ locale-io gate SELFTEST FAILED — the verdict below cannot be "
              "trusted:")
        for f in fails:
            print("    " + f)
        return 2
    if "--canary" in argv:
        print("✓ locale-io gate canary PASSED — the classifier and its own pin "
              "arithmetic both assert")
        return 0
    if "--prove-fires" in argv:
        return prove_fires(argv[argv.index("--prove-fires") + 1])

    args = [a for a in argv[1:] if not a.startswith("--")]
    repo = Path(args[0]).resolve() if args else REPO_ROOT
    # A named sibling is a REPORT, not a verdict: the floors above are THIS
    # repo's measured population, and applying them to a repo with three
    # Python files reports a `parse FLOOR breached` that is true of the pin
    # and false of the tree. Per-repo floors are the SWEEP's
    # (`locale_io_drift_floors.txt`); here they would be a claim about
    # somebody else's tree made from this one's numbers.
    foreign = repo != REPO_ROOT
    exempt, bad = read_expected()
    offenders, py_files, calls, unparsed = scan(repo)
    if foreign:
        exempt, bad = set(), []
        problems = [p for p in verdict(offenders, py_files, calls, unparsed,
                                       exempt)
                    if "FLOOR breached" not in p]
    else:
        problems = bad + verdict(offenders, py_files, calls, unparsed, exempt)

    for rel in sorted(offenders):
        if rel in exempt:
            continue
        for row in offenders[rel]:
            print(f"    ⛔ LOCALE-IO  {rel}:{row}")
    for row in unparsed:
        print(f"    ⛔ UNPARSED   {row}")

    if problems:
        print(f"✗ locale-io gate FAILED — {len(problems)} problem(s) over "
              f"{py_files} tracked .py file(s) / {calls} text-I/O call site(s)")
        for p in problems:
            print("    ✗ " + p)
        print("    read_text/write_text/open use locale.getencoding() with no "
              "encoding=. On a non-UTF-8 box that is a silent round-trip "
              "through the wrong codec — a fixture that still passes, for the "
              "wrong reason. See Issue 829.")
        return 1

    if foreign:
        print(f"✓ locale-io REPORT — 0 locale-dependent text-I/O call(s), 0 "
              f"unparsed over {py_files} tracked .py file(s) / {calls} "
              f"text-I/O call site(s) in {repo.name}. Floors and exemptions "
              f"are katgpt-rs's and are NOT applied here — the per-repo pins "
              f"live in locale_io_drift_floors.txt.")
        return 0
    print(f"✓ locale-io gate PASSED — 0 locale-dependent text-I/O call(s), "
          f"0 unparsed, {len(exempt)} exemption(s) over {py_files} tracked .py "
          f"file(s) (floor {FLOOR_PY_FILES}) / {calls} text-I/O call site(s) "
          f"(floor {FLOOR_IO_CALLS})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
