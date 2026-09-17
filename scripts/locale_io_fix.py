#!/usr/bin/env python3
"""Add an explicit `encoding="utf-8"` to text I/O that uses the SYSTEM locale.

The repair half of `locale_io_gate.py` (Issue 829). `Path.read_text`,
`Path.write_text` and builtin `open()` in text mode decode/encode with
`locale.getencoding()` when no `encoding=` is given. macOS, `ubuntu-latest`
and the M3 are all UTF-8, so nothing that could notice ever runs it — and the
Windows workstation is **cp874**, where U+2014 round-trips through a single
byte 0x97 and comes back as U+FFFD under a UTF-8 read.

AST-driven, never a text scan: a `write_text(` inside a fixture STRING is not
a call, and this repo has met that exact false positive three times already
(`subprocess_encoding_gate`, `platform_dead_code_audit`, `wasm32_surface_audit`).

Binary mode is skipped: `open(p, "rb")` has no encoding to give.

    scripts/locale_io_fix.py --list  scripts/foo.py      # report only
    scripts/locale_io_fix.py         scripts/foo.py ...  # rewrite in place
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import console_safe  # noqa: E402

console_safe.apply()

PATH_METHODS = {"write_text", "read_text"}


def _binary(node: ast.Call) -> bool:
    mode = ""
    if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
        mode = str(node.args[1].value)
    for k in node.keywords:
        if k.arg == "mode" and isinstance(k.value, ast.Constant):
            mode = str(k.value.value)
    return "b" in mode


def sites(src: str) -> list[ast.Call]:
    """Every text-I/O call in `src` with no explicit `encoding=`.

    A `**kwargs` splat counts as UNKNOWN and is left alone: the caller may be
    supplying the encoding, and this repair may only ever be conservative.
    """
    out = []
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr in PATH_METHODS:
            pass
        elif isinstance(node.func, ast.Name) and node.func.id == "open":
            if _binary(node):
                continue
        else:
            continue
        if any(k.arg == "encoding" for k in node.keywords):
            continue
        if any(k.arg is None for k in node.keywords):   # **kwargs — UNKNOWN
            continue
        out.append(node)
    return out


def _line_starts(raw: bytes) -> list[int]:
    """Byte offset of the first byte of each 1-indexed line.

    BYTES, not characters, and that is not a detail: CPython reports
    `col_offset` as a **UTF-8 byte** offset. Computing it in characters
    desyncs by two per em dash earlier on the line, and this repo's sources
    are full of them - the first run asserted on `' '` 59664 chars in.
    A plain byte split on LF is used rather than `splitlines`, which also
    breaks on U+2028, U+0085 and form feed - separators `col_offset` does
    not count as line breaks.
    """
    starts, acc = [0, 0], 0
    for line in raw.split(b"\n"):
        acc += len(line) + 1
        starts.append(acc)
    return starts


def repair(src: str) -> tuple[str, int]:
    """(rewritten source, sites repaired). Idempotent."""
    calls = sites(src)
    if not calls:
        return src, 0
    raw = src.encode("utf-8")
    starts = _line_starts(raw)
    # The Call's end offset is one PAST its closing paren.
    points = sorted({starts[c.end_lineno] + c.end_col_offset - 1 for c in calls})
    out = raw
    for at in reversed(points):
        assert out[at:at + 1] == b")", (
            # EQUIVALENT under mutation: the arithmetic in this MESSAGE is
            # evaluated only when the assert already failed, so no input
            # distinguishes it. Adjudicated, not unarmed.
            f"expected ')' at byte {at}, got {out[at:at + 1]!r}")
        j = at - 1
        # EQUIVALENT: `>= 0` vs `> 0` differ only if the scan walks back to
        # byte 0, which needs every byte before the `)` to be whitespace -
        # impossible, since `open(` or `.write_text(` always precedes it.
        while j >= 0 and out[j:j + 1].isspace():
            j -= 1
        # Insert after the last ARGUMENT character, not before the paren: a
        # call whose `)` sits on its own line would otherwise grow a
        # leading-comma continuation line (`        , encoding="utf-8")`),
        # which is valid Python and unreviewable. `j + 1 == at` whenever
        # there is no whitespace, so the common case is unchanged.
        prev = out[j:j + 1]
        lead = b"" if prev == b"(" else (b" " if prev == b"," else b", ")
        out = out[:j + 1] + lead + b'encoding="utf-8"' + out[j + 1:]
    return out.decode("utf-8"), len(points)


def selftest() -> list[str]:
    """Arms over the rewriter's own decisions, not over its output volume."""
    fails = []

    def one(src, want_n, want_sub=None, want_absent=None):
        got, n = repair(src)
        if n != want_n:
            fails.append(f"{src!r}: repaired {n}, expected {want_n}")
        if want_sub and want_sub not in got:
            fails.append(f"{src!r}: produced {got!r}, missing {want_sub!r}")
        if want_absent and want_absent in got:
            fails.append(f"{src!r}: produced {got!r}, must not contain {want_absent!r}")
        if n:
            again, m = repair(got)
            if m or again != got:
                fails.append(f"{src!r}: NOT idempotent ({m} more)")
        try:
            ast.parse(got)
        except SyntaxError as e:
            fails.append(f"{src!r}: produced unparseable source ({e})")

    one('p.write_text(x)\n', 1, 'p.write_text(x, encoding="utf-8")')
    one('p.read_text()\n', 1, 'p.read_text(encoding="utf-8")')
    one('open(p)\n', 1, 'open(p, encoding="utf-8")')
    # binary mode has no encoding to give — positional AND keyword
    one('open(p, "rb")\n', 0)
    one('open(p, mode="wb")\n', 0)
    # ⚑ The `mode=` keyword's TWO conjuncts, which nothing above reaches: with
    # `or`, any constant keyword value containing a `b` reads as binary mode —
    # and `errors="backslashreplace"` is the exact form this repo's own
    # console defence uses, so the mutant would skip real sites in real code.
    one('open(p, errors="backslashreplace")\n', 1)
    one('open(p, mode=m)\n', 1)   # a non-constant mode is UNKNOWN, not binary
    # already explicit
    one('p.write_text(x, encoding="utf-8")\n', 0)
    one('open(p, encoding="latin-1")\n', 0)
    # a trailing comma must not become a double comma
    one('p.write_text(\n    x,\n)\n', 1, None, ',,')
    # a `)` on its own line: the kwarg joins the last ARGUMENT, never the
    # closing paren — a leading-comma continuation line is valid and
    # unreviewable, and 128 sites went in before anyone read one
    one('f.read_text(errors="replace"\n    )\n', 1,
        'f.read_text(errors="replace", encoding="utf-8"\n    )')
    one('p.write_text(\n    x,\n)\n', 1, 'x, encoding="utf-8"')
    one('p.read_text( )\n', 1, 'p.read_text(encoding="utf-8" )')
    # a `write_text(` inside a STRING is not a call — the false positive an
    # AST pass exists to avoid, measured three times in this repo
    one('s = "p.write_text(x)"\n', 0)
    # **kwargs is UNKNOWN, never rewritten
    one('open(p, **kw)\n', 0)
    # nested calls: the inner one is repaired at its own paren
    one('p.write_text(open(q).read())\n', 2,
        'p.write_text(open(q, encoding="utf-8").read(), encoding="utf-8")')
    # other methods named alike are untouched
    one('p.write_bytes(x)\n', 0)
    one('sock.read_text(x)\n', 1)   # duck-typed: the name IS the population
    return fails


def main(argv: list[str]) -> int:
    fails = selftest()
    if fails:
        for f in fails:
            print(f"  selftest: {f}")
        print("locale_io_fix SELFTEST FAILED - the rewriter is untrustworthy")
        return 2
    args = [a for a in argv if not a.startswith("--")]
    listing = "--list" in argv
    total = 0
    for a in args:
        p = Path(a)
        # ⛔ The NEWLINE STYLE is part of the file and this tool must not have
        # an opinion about it. Read with universal newlines (so `ast` sees the
        # LF text its offsets are computed against), then write the original
        # style back: the first run flipped `suite_membership_audit.py` from
        # CRLF to LF and turned an 11-site repair into a 515-line diff, which
        # is a repair nobody can review.
        raw = p.read_bytes()
        eol = "\r\n" if b"\r\n" in raw else "\n"
        src = raw.decode("utf-8").replace("\r\n", "\n")
        out, n = repair(src)
        total += n
        if n:
            print(f"{'would repair' if listing else 'repaired'} {n:4d}  {a}")
            if not listing:
                p.write_bytes(out.replace("\n", eol).encode("utf-8"))
    print(f"{total} site(s) over {len(args)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
