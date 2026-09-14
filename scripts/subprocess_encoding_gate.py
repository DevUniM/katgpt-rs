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
"""

from __future__ import annotations

import re
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

LOCALE_TEXT = re.compile(r"\b(?:text|universal_newlines)\s*=\s*True\b")
CALL = re.compile(r"\bsubprocess\s*\.\s*(?:run|Popen|check_output|check_call|call)\s*\(")


def call_spans(src: str) -> list[tuple[int, int]]:
    """(start, end) of every `subprocess.*(` call, by paren matching.

    Paren matching and not a regex: these calls wrap across up to eight lines
    here, and a line-scoped match would miss every kwarg below the first one —
    which is where `encoding=` is written when it is written at all.
    """
    spans: list[tuple[int, int]] = []
    for m in CALL.finditer(src):
        depth = 0
        i = m.end() - 1
        while i < len(src):
            c = src[i]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    spans.append((m.start(), i + 1))
                    break
            i += 1
    return spans


def scan_text(src: str) -> tuple[list[str], list[str], int]:
    """(decode_offenders, child_offenders, calls_seen) for one source text."""
    decode: list[str] = []
    child: list[str] = []
    spans = call_spans(src)
    for start, end in spans:
        call = src[start:end]
        line = src.count("\n", 0, start) + 1
        head = " ".join(call.split())[:90]
        if LOCALE_TEXT.search(call) and "encoding=" not in call:
            decode.append(f"{line}: {head}")
        if "sys.executable" in call and "PYTHONIOENCODING" not in call:
            child.append(f"{line}: {head}")
    return decode, child, len(spans)


def scan(repo: Path) -> tuple[dict, dict, int, int]:
    """(decode, child, py_files, calls) over the repo's TRACKED `*.py`."""
    decode: dict = {}
    child: dict = {}
    calls = 0
    files, _ = tracked_files(repo, "*.py")
    for p in files:
        try:
            src = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        d, c, n = scan_text(src)
        calls += n
        rel = str(p.relative_to(repo)).replace("\\", "/")
        if d:
            decode[rel] = d
        if c:
            child[rel] = c
    return decode, child, len(files), calls


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
        "not-a-call": 'text=True  # a bare kwarg in prose, no subprocess call\n',
    }.items():
        d, _, n = scan_text(src)
        check(d == [], f"DECODE false positive on {label}: {d}")
    check(scan_text('text=True\n')[2] == 0,
          "a bare kwarg outside any call was counted as a call site")

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
    decode, child, py_files, calls = scan(repo)
    n_dec = sum(len(v) for v in decode.values())
    n_chi = sum(len(v) for v in child.values())

    problems: list[str] = []
    for rel in sorted(decode):
        for row in decode[rel]:
            print(f"    ⛔ DECODE        {rel}:{row}")
    for rel in sorted(child):
        for row in child[rel]:
            print(f"    ⛔ CHILD-ENCODER {rel}:{row}")
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
                        f"< {FLOOR_CALLS} — the walk is intact but the span "
                        "matcher found nothing")

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
          f"0 unpinned python child(ren) over {py_files} tracked .py file(s) "
          f"(floor {FLOOR_PY_FILES}) / {calls} subprocess call site(s) "
          f"(floor {FLOOR_CALLS})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
