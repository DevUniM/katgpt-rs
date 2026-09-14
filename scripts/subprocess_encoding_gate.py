#!/usr/bin/env python3
"""Gate on a `subprocess` call that decodes with the SYSTEM locale (Issue 778).

`text=True` — and its older spelling `universal_newlines=True` — decode the
child's pipe with `locale.getencoding()`. Every box that could notice is
UTF-8: macOS, `ubuntu-latest`, and the M3 workstation. The Windows workstation
is **cp874**, and every instrument in `scripts/` prints `✓`, `✗`, `⛔` and
em-dashes. Measured there on this repo's own `git log -3 --format=%s`:

    raw bytes         b'... TRACKS \\xe2\\x80\\x94 one walk ...'    (U+2014)
    text=True          0xe42 0x20ac 0x201d    <- three cp874 chars, silently
    encoding="utf-8"   0x2014                 <- correct

Two failure modes, and the crash is the better one:

1. **Silent mojibake.** rc 0, a plausible string, and a caller matching
   `re.search(r"FAILED — (\\d+)", out)` — em-dash in the pattern, mojibake in
   the text — matches nothing and reads a confident **zero findings**.
2. **`stdout = None` with the returncode PRESERVED.** Where a byte is
   undefined in the locale codec the decode raises inside `subprocess`'s
   reader THREAD, where the exception dies. `run()` returns normally.
   `citation_drift_sweep.gate_says()` got `(rc=0, stdout=None)` and only the
   next `re.search` made it visible.

`PYTHONIOENCODING=utf-8` does not fix mode 1 and makes mode 2 MORE likely: it
pins the CHILD's encoder, so the child emits correct UTF-8 that the parent
then decodes as cp874.

## Why a gate and not a sweep-and-done

`staged_set_audit.py` has carried the correct form — and a comment naming this
exact defect, dated 2026-09-04 — since the day it was written, and 27 other
call sites went on being added without it. Nothing in CI can ever red on this,
because both runners are UTF-8. A per-push ceiling is the only instrument that
survives contact with the next person to type `text=True`.

## Two classes, pinned separately

- **DECODE** — a `subprocess` call with `text=True` / `universal_newlines=True`
  and no `encoding=`. The parent's read.
- **CHILD-ENCODER** — a call that launches `sys.executable` without
  `PYTHONIOENCODING` in its `env=`. The child's WRITE: our own gates print
  `✓`, and on a non-UTF-8 box that write raises before a single byte reaches
  the pipe the DECODE class is about. Pinned separately because they are found
  by different halves of this classifier and a shared pin would hide which one
  regressed.

Floors, not just ceilings: a ceiling of 0 is green over whatever the walk can
see, so the population (tracked `*.py` files AND `subprocess` call sites) is
pinned underneath it. Self-test runs on every invocation, both directions.

The scan is over the **AST**, not over text. The first version paren-matched
and reported four offenders in this very file — every one of them a FIXTURE
STRING in its own `selftest()`. The repairs available then were to exempt the
gate from itself or to obfuscate its own test data, and an exempt gate
certifies nothing. A file the parser cannot read is **UNPARSED** and reds; it
is never folded into the pass column.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tracked_walk import tracked_files  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

# Measured 2026-09-14 on katgpt-rs: 60 tracked .py, 44 subprocess call sites.
# Slack against ordinary churn, tight against a walk or parse regression —
# the same rule every floor in this repo carries.
FLOOR_PY_FILES = 40
FLOOR_CALLS = 30

# Structural, not textual. An earlier paren-matching version scanned this very
# file and reported FOUR offenders — every one of them a FIXTURE STRING inside
# `selftest()`. A gate that cannot read its own source without tripping on its
# own test data would have to be exempted from itself, and an exempt gate
# certifies nothing. `ast` sees string literals as literals.
SUBPROCESS_FUNCS = {"run", "Popen", "check_output", "check_call", "call"}


def _is_subprocess_call(node: ast.Call) -> bool:
    f = node.func
    return (isinstance(f, ast.Attribute) and f.attr in SUBPROCESS_FUNCS
            and isinstance(f.value, ast.Name) and f.value.id == "subprocess")


def _kw_true(node: ast.Call, name: str) -> bool:
    for k in node.keywords:
        if k.arg == name and isinstance(k.value, ast.Constant) and k.value.value is True:
            return True
    return False


def _has_kw(node: ast.Call, name: str) -> bool:
    return any(k.arg == name for k in node.keywords)


def _launches_python(node: ast.Call) -> bool:
    """`sys.executable` appearing anywhere in the call, as CODE."""
    for sub in ast.walk(node):
        if (isinstance(sub, ast.Attribute) and sub.attr == "executable"
                and isinstance(sub.value, ast.Name) and sub.value.id == "sys"):
            return True
    return False


def _pins_child_encoder(node: ast.Call) -> bool:
    """`PYTHONIOENCODING` as a string CONSTANT anywhere in the call — normally
    the key of the `env=` dict. A constant and not a source-text match, so a
    comment or a docstring mentioning the name never counts as pinning it."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and sub.value == "PYTHONIOENCODING":
            return True
    return False


def scan_text(src: str) -> tuple[list[str], list[str], int]:
    """(decode_offenders, child_offenders, calls_seen) for one source text.

    Raises `SyntaxError` on an unparseable source. The caller must surface
    that rather than counting it as clean — an instrument admitting it cannot
    read is the trap audit's UNPARSED verdict, and pooling it into the pass
    column is how a classifier goes blind and still prints zero.
    """
    tree = ast.parse(src)
    decode: list[str] = []
    child: list[str] = []
    calls = 0
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and _is_subprocess_call(node)):
            continue
        calls += 1
        head = " ".join(ast.unparse(node).split())[:90]
        if ((_kw_true(node, "text") or _kw_true(node, "universal_newlines"))
                and not _has_kw(node, "encoding")):
            decode.append(f"{node.lineno}: {head}")
        if _launches_python(node) and not _pins_child_encoder(node):
            child.append(f"{node.lineno}: {head}")
    return decode, child, calls


def scan(repo: Path) -> tuple[dict, dict, int, int, list[str]]:
    """(decode, child, py_files, calls, unparsed) over the repo's TRACKED *.py."""
    decode: dict = {}
    child: dict = {}
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
            d, c, n = scan_text(src)
        except SyntaxError as e:
            unparsed.append(f"{rel}:{e.lineno}: {e.msg}")
            continue
        calls += n
        if d:
            decode[rel] = d
        if c:
            child[rel] = c
    return decode, child, len(files), calls, unparsed


def selftest() -> list[str]:
    """Both directions on every invocation. The false-NEGATIVE direction is
    the one that matters: a regex regression prints `0 offenders` forever,
    which is indistinguishable from the clean state this asserts."""
    fails: list[str] = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    # DECODE — positive, single line and wrapped, plus the old spelling.
    for label, src in {
        "one-line": 'subprocess.run(cmd, capture_output=True, text=True)\n',
        "wrapped": ("subprocess.run(\n    cmd,\n    capture_output=True,\n"
                    "    text=True,\n)\n"),
        "universal_newlines": 'subprocess.run(cmd, universal_newlines=True)\n',
    }.items():
        d, _, n = scan_text(src)
        check(len(d) == 1, f"DECODE missed the {label} form: {d}")
        check(n == 1, f"{label}: call span miscounted ({n})")

    # DECODE — negatives. The wrapped one is the arm that matters: a
    # line-scoped matcher passes the one-liner and fails this.
    for label, src in {
        "one-line-pinned": 'subprocess.run(cmd, text=True, encoding="utf-8")\n',
        "wrapped-pinned": ("subprocess.run(\n    cmd,\n    capture_output=True,\n"
                           "    text=True,\n    encoding=\"utf-8\",\n"
                           "    errors=\"replace\",\n)\n"),
        "bytes-mode": 'subprocess.run(cmd, capture_output=True)\n',
        "not-a-call": 'x = True  # a bare kwarg in prose, no subprocess call\n',
        # A non-True value is not this defect: `text=flag` is somebody's own
        # switch and `text=False` is bytes mode.
        "text-not-true": 'subprocess.run(cmd, text=flag)\n',
        # ⚑ The detector's own BOUNDARY, added by Issue 790 T3: every negative
        # above is still a `subprocess.<func>` call, so nothing tested the
        # three conjuncts that decide whether a call IS one. A bare-name call
        # exercises the `isinstance(f, ast.Attribute)` term, and an
        # attribute call on another object exercises `f.value.id ==
        # "subprocess"` — `sp.run(...)` is an alias somebody else owns, and
        # `self.run(...)` is an ordinary method.
        "bare-name call": 'run(cmd, text=True)\n',
        "another module's run": 'sp.run(cmd, text=True)\n',
        "a method named run": 'self.run(cmd, text=True)\n',
        "a nested attribute": 'a.b.run(cmd, text=True)\n',
        "an unrelated builtin call": 'print(cmd, text=True)\n',
    }.items():
        d, _, n = scan_text(src)
        check(d == [], f"DECODE false positive on {label}: {d}")
    check(scan_text('x = True\n')[2] == 0,
          "a bare assignment outside any call was counted as a call site")

    # A STRING containing the offending source is data, not code. This arm is
    # not hypothetical: an earlier paren-matching version of this scanner
    # reported four offenders in THIS file, every one of them a fixture string
    # in the block above, and the only repairs available were to exempt the
    # gate from itself or to obfuscate its own test data.
    d, c, n = scan_text('SRC = "subprocess.run(cmd, text=True)"\n'
                        'DOC = """subprocess.run([sys.executable, s], text=True)"""\n')
    check((d, c, n) == ([], [], 0),
          f"a string literal was scanned as code: decode={d} child={c} calls={n}")

    # And the inverse: an UNPARSEABLE file must raise, not read as clean. The
    # trap audit's UNPARSED lesson — a classifier that cannot read must say so.
    try:
        scan_text("def f(:\n")
        fails.append("an unparseable source did not raise — it would count as clean")
    except SyntaxError:
        pass

    # CHILD-ENCODER — both directions.
    d, c, _ = scan_text('subprocess.run([sys.executable, s], capture_output=True,\n'
                        '               encoding="utf-8")\n')
    check(len(c) == 1, f"CHILD-ENCODER missed an unpinned python child: {c}")
    check(d == [], f"CHILD-ENCODER arm leaked into DECODE: {d}")
    _, c, _ = scan_text('subprocess.run([sys.executable, s], capture_output=True,\n'
                        '               encoding="utf-8",\n'
                        '               env={**os.environ, "PYTHONIOENCODING": "utf-8"})\n')
    check(c == [], f"CHILD-ENCODER false positive on a pinned child: {c}")
    _, c, _ = scan_text('subprocess.run(["git", "log"], capture_output=True,\n'
                        '               encoding="utf-8")\n')
    check(c == [], "a non-python child was reported as CHILD-ENCODER")

    # The two classes are independent: one call can be BOTH, and pooling them
    # would report one offender where two pins should move.
    d, c, _ = scan_text('subprocess.run([sys.executable, s], text=True)\n')
    check(len(d) == 1 and len(c) == 1,
          f"a call in both classes was not counted in both: decode={d} child={c}")

    return fails


def main(argv: list[str]) -> int:
    fails = selftest()
    if fails:
        print("✗ subprocess-encoding gate SELFTEST FAILED — the verdict below "
              "cannot be trusted:")
        for f in fails:
            print("    " + f)
        return 2

    repo = Path(argv[1]).resolve() if len(argv) > 1 else REPO_ROOT
    decode, child, py_files, calls, unparsed = scan(repo)
    n_dec = sum(len(v) for v in decode.values())
    n_chi = sum(len(v) for v in child.values())

    problems: list[str] = []
    for rel in sorted(decode):
        for row in decode[rel]:
            print(f"    ⛔ DECODE        {rel}:{row}")
    for rel in sorted(child):
        for row in child[rel]:
            print(f"    ⛔ CHILD-ENCODER {rel}:{row}")
    for row in unparsed:
        print(f"    ⛔ UNPARSED      {row}")
    if unparsed:
        problems.append(f"{len(unparsed)} file(s) the parser could not read — "
                        "UNPARSED is the instrument admitting it cannot see, "
                        "never a pass")
    if n_dec:
        problems.append(f"{n_dec} call(s) decode with the system locale "
                        '(add encoding="utf-8", errors="replace")')
    if n_chi:
        problems.append(f"{n_chi} python child(ren) run without PYTHONIOENCODING "
                        '(add env={**os.environ, "PYTHONIOENCODING": "utf-8"})')
    if py_files < FLOOR_PY_FILES:
        problems.append(f"walk FLOOR breached: {py_files} tracked .py < "
                        f"{FLOOR_PY_FILES} — the ceilings above are green over "
                        "a population that shrank")
    if calls < FLOOR_CALLS:
        problems.append(f"parse FLOOR breached: {calls} subprocess call site(s) "
                        f"< {FLOOR_CALLS} — the walk is intact but the AST pass "
                        "found nothing")

    if problems:
        print(f"✗ subprocess-encoding gate FAILED — {len(problems)} problem(s) "
              f"over {py_files} tracked .py file(s) / {calls} subprocess call site(s)")
        for p in problems:
            print("    ✗ " + p)
        print("    text=True decodes with locale.getencoding(). On a non-UTF-8 box "
              "that is silent mojibake, or stdout=None with the returncode intact "
              "— see Issue 778.")
        return 1

    print(f"✓ subprocess-encoding gate PASSED — 0 locale-decoding call(s), "
          f"0 unpinned python child(ren), 0 unparsed over {py_files} tracked "
          f".py file(s) (floor {FLOOR_PY_FILES}) / {calls} subprocess call "
          f"site(s) (floor {FLOOR_CALLS})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
