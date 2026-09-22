#!/usr/bin/env python3
"""`algebraic_div` / `algebraic_rem` are BANNED in Rust sources (Issue 871 T4).

Rust 1.98's `f32::algebraic_*` operators carry per-op `reassoc contract arcp
nsz` — deliberately NO `nnan`/`ninf`, so no poison. Issue 871 ADOPTED the
add/mul reassociation lane (feature-gated `katgpt-attn-match/algebraic_dot`,
Bench 871, owner verdict 2026-09-22) but BANNED div/rem outright: `arcp`
reciprocal semantics and remainder reassociation are a far larger numerics
change than summation-order reassociation, and no measured case wants them.

The verdict condition: "a prose no-go list is this file's most-repeated
failure shape — a tracked check, not a doc line." This gate is the mechanical
form: ANY code occurrence of `algebraic_div` or `algebraic_rem` in a tracked
`*.rs` file reds. There is no pin file and no exemption vocabulary by design
— lifting the ban is an owner act that edits this gate's BANNED set in the
same commit that argues it.

    scripts/algebraic_op_ban_gate.py    # the verdict AND the arms

The arms run UNCONDITIONALLY, behind no flag (Issue 789: `docs_gate.sh`
invokes each check as `"$PY" "$script"` with no arguments):

- arm 1 (predicate liveness): a planted synthetic source carrying one
  `algebraic_div` + one `algebraic_rem` CODE occurrence each, plus prose
  mentions in `//` comments, `///` docs and string literals — the classifier
  must report exactly the two code sites and mask every prose mention. This
  is the predicate floor a ban gate cannot express as a count (0 is the
  target; a regex regression would report 0 over everything and read green).
- arm 2 (clean pass): a clean synthetic source reports zero findings.
- arm 3 (walk floor): the live tracked-`*.rs` count must clear MIN_FILES —
  a tracked_files regression shrinks the population underneath the same
  green verdict (the silence direction).

Population: every tracked `*.rs` in the repo (tracked_files — the one-copy
walk, Issue 777). The masker is IMPORTED from platform_dead_code_audit (the
lexer-grade one with the measured defect history — a second hand-rolled
masker is a second thing to get wrong, the wasm32_surface precedent).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import console_safe  # noqa: E402
from tracked_walk import tracked_files  # noqa: E402

console_safe.apply()

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
GLOB = "*.rs"

# The banned set — lifting this is an owner act argued in the same commit.
BANNED = ("algebraic_div", "algebraic_rem")

# Walk floor: measured landing population is thousands of tracked .rs; this
# floor only needs to catch a walk collapse, not to track growth.
MIN_FILES = 1000

BANNED_RX = re.compile(r"\balgebraic_(?:div|rem)\b")


def scan_files(root: Path, files: list[Path]) -> dict[str, list[str]]:
    """{relpath: [banned names found in CODE]} over the given files.

    Prose (comments, doc comments, string literals) is masked before
    matching — a doc line NAMING the ban is not a violation.
    """
    from platform_dead_code_audit import mask_file

    found: dict[str, list[str]] = {}
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise SystemExit(
                f"⛔ {path}: unreadable after the walk listed it — {exc}"
            ) from exc
        masked, _attrs = mask_file(text)
        names = sorted({m.group(0) for m in BANNED_RX.finditer(masked)})
        if names:
            found[path.relative_to(root).as_posix()] = names
    return found


PLANTED = '''\
// prose mention: algebraic_div and algebraic_rem are banned (comment).
/// Doc mention: algebraic_div banned (doc comment).
fn clean(a: f32, b: f32) -> f32 {
    let note = "string mention: algebraic_rem banned";
    let _ = note;
    a + b
}

fn offender_div(a: f32, b: f32) -> f32 {
    a.algebraic_div(b)
}

fn offender_rem(a: f32, b: f32) -> f32 {
    a.algebraic_rem(b)
}
'''


def selftest(live_files: int) -> list[str]:
    """Three arms, run unconditionally (exit 2 on any failure)."""
    from platform_dead_code_audit import mask_file

    failures: list[str] = []
    masked, _ = mask_file(PLANTED)
    counts: dict[str, int] = {}
    for m in BANNED_RX.finditer(masked):
        counts[m.group(0)] = counts.get(m.group(0), 0) + 1
    if counts != {"algebraic_div": 1, "algebraic_rem": 1}:
        failures.append(
            f"arm1 predicate: expected exactly {{'algebraic_div': 1, "
            f"'algebraic_rem': 1}} (code occurrences, prose masked), got "
            f"{counts} — the regex or the masker broke"
        )

    clean_masked, _ = mask_file("fn f(x: f32) -> f32 { x * 2.0 }\n")
    if list(BANNED_RX.finditer(clean_masked)):
        failures.append("arm2 clean: findings on a clean source")

    if live_files < MIN_FILES:
        failures.append(
            f"arm3 floor: walk returned {live_files} files, below "
            f"MIN_FILES={MIN_FILES} — the population collapsed or the "
            f"floor is stale"
        )
    return failures


def main() -> int:
    files, _excluded = tracked_files(REPO_ROOT, GLOB)
    n_files = len(files)

    failures = selftest(n_files)
    if failures:
        for f in failures:
            print(f"⛔ selftest: {f}")
        return 2

    found = scan_files(REPO_ROOT, files)
    if found:
        print(
            f"⛔ {len(found)} file(s) carry banned algebraic_div/"
            f"algebraic_rem CODE occurrences (Issue 871 T4 ban — lifting it "
            f"is an owner act that edits this gate in the same commit that "
            f"argues it):"
        )
        for rel in sorted(found):
            print(f"  ✗ {rel}: {', '.join(found[rel])}")
        return 1

    print(
        f"✓ algebraic_op_ban: 0 banned occurrences over {n_files} tracked "
        f".rs files (div/rem ban enforced; the add/mul lane is the opt-in "
        f"katgpt-attn-match/algebraic_dot feature)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
