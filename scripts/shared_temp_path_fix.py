#!/usr/bin/env python3
"""Repair half of `shared_temp_path_gate.py` — Issue 832 T5.

Rewrites a FIXED `env::temp_dir().join("literal")` into the process-unique form
this workspace already uses:

    env::temp_dir().join(format!("stem_{}.ext", std::process::id()))

The pid goes BEFORE the extension, which is the established convention here
(`katgpt-types/src/tests_types.rs` writes `katgpt_core_test_gpart_{}.bin`);
appending it after would produce `cache.bin_1234`, which reads as a different
file type to anything that sniffs a suffix.

⛔ It repairs only what the GATE finds, by importing the gate's own `mask` and
`FIXED_JOIN` rather than re-deriving them. A second copy of a hand-rolled Rust
lexer is a second thing to get wrong — the rule `wasm32_surface_audit` records
about importing `platform_dead_code_audit`'s masker — and here it is stronger
than a convention: a repair pass whose idea of a site differs from the gate's
either misses rows the gate will red on, or edits code the gate never asked
about.

By default `examples/` and `src/bin/` are SKIPPED. That is not squeamishness:
it is the adjudication the two pinned rows in
`shared_temp_path_expected.txt` record — a demo's scratch path is meant to stay
findable by the human who ran it, and no gate runs two examples concurrently.
`--include-demos` overrides it for a repo whose owner decides otherwise.

Idempotent (a repaired site no longer matches), LF-preserving (a scripted
rewrite that flips line endings turns a 40-line repair into a 2000-line diff),
and it REFUSES to leave a line over `--max-width`, wrapping instead — an
unformatted line is a `cargo fmt` invitation, and `cargo fmt -p <crate>`
reformats ~1300 unrelated lines in this workspace.

    scripts/shared_temp_path_fix.py ../riir-ai --dry-run
    scripts/shared_temp_path_fix.py ../riir-ai
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import console_safe  # noqa: E402

console_safe.apply()

import shared_temp_path_gate as stp  # noqa: E402
from tracked_walk import tracked_files  # noqa: E402

DEMO = re.compile(r"(^|/)(examples|bin)/")


def unique_literal(lit: str) -> str:
    """`"a.bin"` -> `format!("a_{}.bin", std::process::id())` source text."""
    stem, dot, ext = lit.rpartition(".")
    # `rpartition` yields ("", "", lit) when there is no dot — and a leading
    # dot (".cache") is a hidden-file name, not an extension, so an empty stem
    # is treated as no extension too.
    if dot and stem:
        body = f"{stem}_{{}}.{ext}"
    else:
        body = f"{lit}_{{}}"
    return f'format!("{body}", std::process::id())'


def repair_line(line: str, max_width: int) -> tuple[str, int]:
    """(new_line, n_sites). Wraps rather than leave an over-wide line."""
    n = 0
    # Match on the MASKED copy so a site inside a comment or a raw string is
    # not rewritten, but splice into the REAL text: offsets are identical
    # because `mask` preserves length, which is the invariant its arms pin.
    masked = stp.mask(line)
    out = line
    for m in reversed(list(stp.FIXED_JOIN.finditer(masked))):
        n += 1
        lit = m.group(1)
        out = out[:m.start()] + out[m.start():m.end()].replace(
            f'"{lit}"', unique_literal(lit), 1) + out[m.end():]

    if n and len(out.rstrip("\n")) > max_width:
        indent = len(out) - len(out.lstrip())
        pad = " " * (indent + 4)
        # Break after `.join(` — the one split point that is always legal here
        # and that rustfmt itself chooses for this shape.
        out = re.sub(r"\.join\(format!\(",
                     f".join(format!(\n{pad}", out, count=1)
        out = re.sub(r", std::process::id\(\)\)\)",
                     f",\n{pad}std::process::id()\n{' ' * (indent + 0)}))",
                     out, count=1)
    return out, n


def repair_file(path: Path, max_width: int, dry: bool) -> int:
    raw = path.read_bytes()
    src = raw.decode("utf-8", errors="replace")
    # ⛔ Ask whether the file has a SITE before announcing anything about it.
    # The first version tested CRLF first and printed a loud per-file refusal
    # for every CRLF file in the repo — 18 of them in riir-ai, none carrying a
    # site — which reads as a repair backlog that does not exist. A message
    # that invites work nobody needs to do is this workspace's own
    # cries-wolf failure mode, one instrument down.
    if not stp.sites(src):
        return 0
    if b"\r\n" in raw:
        # Refuse rather than silently normalise: a scripted rewrite that flips
        # line endings turns a small repair into an unreviewable diff, and a
        # CRLF file needs a deliberate decision rather than a side effect.
        print(f"  ⛔ SKIPPED (CRLF, and it HAS {sum(stp.sites(src).values())} "
              f"site(s)) {path.name} — normalise the file deliberately, then "
              f"re-run")
        return 0
    lines = src.split("\n")
    total = 0
    for i, line in enumerate(lines):
        new, n = repair_line(line, max_width)
        if n:
            lines[i] = new
            total += n
    if total and not dry:
        path.write_bytes("\n".join(lines).encode("utf-8"))
    return total


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--include-demos", action="store_true")
    ap.add_argument("--max-width", type=int, default=100)
    a = ap.parse_args(argv)

    repo = a.repo.resolve()
    files, _ = tracked_files(repo, "*.rs")
    n_sites = n_files = n_skipped = 0
    for path in sorted(files):
        rel = path.relative_to(repo).as_posix()
        if not a.include_demos and DEMO.search(rel):
            if stp.sites(path.read_text(encoding="utf-8", errors="replace")):
                n_skipped += 1
            continue
        n = repair_file(path, a.max_width, a.dry_run)
        if n:
            n_files += 1
            n_sites += n
            print(f"  {'would fix' if a.dry_run else 'fixed'} {n}  {rel}")

    print(f"\n{'DRY RUN — ' if a.dry_run else ''}{n_sites} site(s) in "
          f"{n_files} file(s) in {repo.name}; {n_skipped} demo file(s) left "
          f"alone (examples/ and src/bin/ — the adjudicated class; "
          f"--include-demos overrides)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
