#!/usr/bin/env python3
"""A shipped primitive drew from the UNSEEDED thread-local global (Issue 809).

`fastrand`'s free functions (`fastrand::f32()`, `fastrand::usize(..)`, ...)
draw from a thread-local RNG seeded from system entropy on first use per
thread. Inside a shipped primitive that makes the primitive NOT a function of
its arguments: same input, different output per process. The measured instance
was `VocabChannelDecomposer::discover_channel` — a deterministic-looking test
assertion about which token ranks first flipped between two runs of identical
source, found only because the x86_64 execution matrix executed the same
commit twice (Issue 806's second run). The fix seeded from the input; this
gate is the class wall the issue's T2 asks for.

    scripts/global_rng_gate.py    # the verdict AND the arms

The arms run UNCONDITIONALLY, behind no flag: `docs_gate.sh` invokes each check
as `"$PY" "$script"` with no arguments, so an arm behind `'--canary' in
sys.argv` never fires on a push (Issue 789's finding).

The quantity to gate is NOT the count — *a set is gateable where its
cardinality is not* (`cfg_gated_floor_gate`'s rule). A count is green on a
swap and stale the moment the corpus grows. Membership, both directions: a
live site with no pin row reds (the commit that adds a global draw must
adjudicate it), a pin row whose site is gone or whose per-(file, call) count
moved reds STALE (the file must not only ever loosen).

The pin key is deliberately LINE-FREE: `path::call::count`, with the count
scoped to the (file, call) pair. A line number drifts on every edit above it;
an occurrence ordinal shifts when a sibling site is inserted. Counts move only
when the population the pin describes actually moves.

Population: every tracked `*.rs` free-function `fastrand::<primitive>()` call
(`bool|char|alphabetic|alphanumeric|lowercase|uppercase|digit|f32|f64|i8|i16|
i32|i64|u8|u16|u32|u64|usize|isize|rng|global_rng`). Deliberately OUT of
population:

- `fastrand::Rng::with_seed(..)` — the correct pattern (555 sites, Issue 809's
  measured baseline).
- `fastrand::Rng::new()` — an unseeded LOCAL instance, same entropy source,
  but a different and much larger population (~95 sites) dominated by
  sampling-by-design paths (drafters, players, tests). Adjudicating it is
  Issue 809's T3 census; pinning it unread would be a backlog wearing a pin
  (the issue's own T2 rule).
- Non-fastrand RNGs — fastrand is this repo's RNG crate; another crate would
  be a new dependency fact, not a new call site.

Comment and string literals are masked before matching (a doc comment naming
the function is prose, not a call). The masker is regex-grade, not lexer-grade
(see mask_line): its failure direction is OVER-detection, which lands as a
loud red adjudicated by a human — never as a silent green.
"""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
from pathlib import Path

import console_safe  # noqa: E402
from tracked_walk import tracked_files  # noqa: E402

console_safe.apply()

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
PINS = HERE / "global_rng_expected.txt"
GLOB = "*.rs"

# Two floors, failing differently (the console_encoding_gate pattern):
#   MIN_SITES  the PREDICATE. A regex regression that stops matching reports
#              every site pinned and prints a confident green over zero of
#              them — the silence direction.
#   MIN_FILES  the WALK. A tracked_files regression that returns few files
#              shrinks the population underneath the same green verdict.
MIN_SITES = 8
MIN_FILES = 4

# The free-function surface of the fastrand global. `Rng::` is excluded by
# construction (the alternation names only primitives, and `Rng` is not one).
GLOBAL_CALL = re.compile(
    r"fastrand::(bool|char|alphabetic|alphanumeric|lowercase|uppercase|digit"
    r"|f32|f64|i8|i16|i32|i64|u8|u16|u32|u64|usize|isize|rng|global_rng)\("
)

# ── the masker ──────────────────────────────────────────────────────────────
# Regex-grade, per line: cut at the first `//` outside a string literal, then
# blank out "..." and '...' bodies. Raw strings (r#"..."#) and multi-line
# strings are NOT modeled — a literal carrying a full `fastrand::f32(` shape
# may phantom-match. That direction is LOUD (an unpinned red a human
# resolves), never silent, which is the only property this cheap gate needs.


def mask_line(line: str) -> str:
    out: list[str] = []
    in_str: str | None = None
    i = 0
    while i < len(line):
        c = line[i]
        if in_str:
            if c == "\\" and i + 1 < len(line):
                out.append("  ")  # the escape and the char it escapes
                i += 2
                continue
            out.append(" ")
            if c == in_str:
                in_str = None
            i += 1
            continue
        if c in "\"'":
            in_str = c
            out.append(" ")
            i += 1
            continue
        if c == "/" and line[i + 1 : i + 2] == "/":
            break  # line comment — everything after is prose
        out.append(c)
        i += 1
    return "".join(out)


def mask(src: str) -> str:
    return "\n".join(mask_line(line) for line in src.splitlines())


# ── the classifier ──────────────────────────────────────────────────────────


def sites(src: str) -> dict[str, int]:
    """Per-call-name counts of global free-function draws in one source."""
    counts: dict[str, int] = {}
    for m in GLOBAL_CALL.finditer(mask(src)):
        counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    return counts


def scan(root: Path) -> dict[str, dict[str, int]]:
    """{relpath: {call: count}} over the tracked tree."""
    found: dict[str, dict[str, int]] = {}
    files, _excluded = tracked_files(root, GLOB)
    for path in files:
        counts = sites(path.read_text(encoding="utf-8", errors="replace"))
        if counts:
            found[path.relative_to(root).as_posix()] = counts
    return found


# ── the pins ────────────────────────────────────────────────────────────────


def parse_pins(path: Path) -> dict[str, str]:
    """`relpath::call::count # reason` — a reasonless row is REFUSED (a row
    nobody had to justify is a backlog wearing a pin, Issue 785)."""
    pins: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "#" not in line:
            raise SystemExit(f"⛔ {path.name}: reasonless pin row refused: {line!r}")
        key, reason = line.split("#", 1)
        parts = key.strip().split("::")
        if len(parts) != 3 or not parts[2].strip().isdigit():
            raise SystemExit(f"⛔ {path.name}: malformed pin row: {line!r}")
        pins[f"{parts[0].strip()}::{parts[1].strip()}"] = (
            f"{int(parts[2])}#{reason.strip()}"
        )
    return pins


def verdict(root: Path, pins: dict[str, str], floors: bool = True) -> tuple[list[str], int, int]:
    fails: list[str] = []
    live = scan(root)
    n_sites = sum(sum(c.values()) for c in live.values())
    n_files = len(live)

    # The floors assert the REAL tree's walk + predicate. Fixture arms pass
    # floors=False: a one-file fixture would otherwise trip them and turn
    # every pin assertion into a floor failure.
    if floors:
        if n_sites < MIN_SITES:
            fails.append(
                f"⛔ walk/predicate floor: {n_sites} global sites < MIN_SITES={MIN_SITES}"
            )
        if n_files < MIN_FILES:
            fails.append(
                f"⛔ walk floor: {n_files} files carrying global sites < MIN_FILES={MIN_FILES}"
            )

    # live site with no pin row, or a count that moved
    for rel, counts in sorted(live.items()):
        for call, count in sorted(counts.items()):
            key = f"{rel}::{call}"
            if key not in pins:
                fails.append(f"✗ UNPINNED global draw: {key} x{count}")
            else:
                want, _reason = pins[key].split("#", 1)
                if int(want) != count:
                    fails.append(f"✗ STALE pin {key}: pinned x{want}, live x{count}")

    # pin row whose site left the population
    for key in sorted(pins):
        rel, call = key.rsplit("::", 1)
        if live.get(rel, {}).get(call) is None:
            fails.append(f"✗ STALE pin {key}: site no longer in the population")
    return fails, n_sites, n_files


# ── the arms (unconditional) ────────────────────────────────────────────────
# EQUIVALENT survivors (arm_reach, measured 2026-09-16): the in-string escape
# guard's `< -> <=` and `+ -> -` flips differ ONLY when a line's LAST
# character is a backslash inside a string — the Rust line-continuation form,
# i.e. a multi-line string, which mask_line documents out of scope (its
# failure direction is loud, never silent). Pinned here rather than armed.


def classifier_arms() -> list[str]:
    fails: list[str] = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            fails.append(msg)

    check(sites("let x = fastrand::f32();") == {"f32": 1}, "free f32 must classify")
    check(sites("let x = fastrand::u8(..0x10);") == {"u8": 1}, "ranged u8 must classify")
    check(
        sites("let x = fastrand::usize(..n);") == {"usize": 1},
        "usize(..) must classify",
    )
    check(sites("fastrand::rng()") == {"rng": 1}, "rng() handle must classify")
    check(
        sites("fastrand::global_rng()") == {"global_rng": 1},
        "global_rng() must classify",
    )
    # the correct patterns must NOT classify
    check(
        sites("let mut r = fastrand::Rng::with_seed(42);\nlet x = r.f32();") == {},
        "with_seed + method must NOT classify",
    )
    check(
        sites("let mut r = fastrand::Rng::new();") == {},
        "Rng::new is out of population",
    )
    check(sites("let x = rng.f32();") == {}, "seeded method call must NOT classify")
    check(sites("use fastrand::Rng;") == {}, "an import must NOT classify")
    # masking
    check(
        sites("// fastrand::f32() in a doc comment") == {},
        "commented call must NOT classify",
    )
    check(sites('let s = "fastrand::f32()";') == {}, "string literal must NOT classify")
    check(
        sites("let x = fastrand::f32(); // draw vs fastrand::usize() prose")
        == {"f32": 1},
        "call before a comment keeps exactly the live site",
    )
    check(
        sites(r'let s = "escaped \" quote then fastrand::f32()";') == {},
        "escaped quote must not leak the mask",
    )
    check(sites("") == {}, "empty source has no sites")
    # A lone `/` is division, not a comment: code AFTER it must stay live.
    # Kills the mask_line `and -> or` on the comment test and its `== -> !=`
    # flip (with != the comment never terminates and the prose would
    # classify; with or a bare division breaks the line early and a real
    # call after it would go unseen — both directions are silent-green
    # hazards, which is why this fixture is two-sided).
    check(
        sites("let a = b / c; // prose fastrand::f32()\nlet y = fastrand::f32();")
        == {"f32": 1},
        "division must not mask the rest of the line or the next one",
    )
    check(
        sites('let s = "ends with escaped backslash\\\\";\nlet y = fastrand::f32();')
        == {"f32": 1},
        "string-close-backslash must not leak the mask past the literal",
    )
    # Kills the in-string escape guard's `and -> or` and `== -> !=` flips:
    # under either, the escape-skip fires on ordinary chars, "a" never
    # closes, and the call after it is wrongly masked.
    check(
        sites('let s = "a"; let y = fastrand::f32();') == {"f32": 1},
        "a short string must close and the code after it stay live",
    )
    # Kills the comment-guard's `and -> or` and second-`== -> !=` flips:
    # under either, the guard fires at ANY slash (a lone division `/`
    # included), masking the live call that follows it on the same line.
    check(
        sites("let r = a / b; let y = fastrand::f32();") == {"f32": 1},
        "a lone division slash must not mask the rest of the line",
    )
    return fails


def pin_arms(tmp: Path) -> list[str]:
    """Fixture-tree arms over parse + verdict, both directions."""
    fails: list[str] = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            fails.append(msg)

    src = "crate; fn f() { let x = fastrand::f32(); }"
    (tmp / "a.rs").write_text(src, encoding="utf-8")
    good = tmp / "pins.txt"
    good.write_text("# header\n\na.rs::f32::1 # stochastic by design\n", encoding="utf-8")
    fails0, _, _ = verdict(tmp, parse_pins(good), floors=False)
    check(fails0 == [], f"pinned live site must be clean, got {fails0}")

    # reasonless row refused
    bad = tmp / "bad.txt"
    bad.write_text("a.rs::f32::1\n", encoding="utf-8")
    try:
        parse_pins(bad)
        check(False, "reasonless pin row must be refused")
    except SystemExit:
        pass

    # malformed row refused
    bad2 = tmp / "bad2.txt"
    bad2.write_text("a.rs::f32 # no count\n", encoding="utf-8")
    try:
        parse_pins(bad2)
        check(False, "malformed pin row must be refused")
    except SystemExit:
        pass

    # unpinned live site reds
    (tmp / "b.rs").write_text(
        "crate; fn g() { let y = fastrand::bool(); }", encoding="utf-8"
    )
    fails1, _, _ = verdict(tmp, parse_pins(good), floors=False)
    check(
        any("UNPINNED" in f and "b.rs::bool" in f for f in fails1),
        "a new global draw must red UNPINNED",
    )
    (tmp / "b.rs").unlink()

    # count moved reds
    (tmp / "a.rs").write_text(
        src + "\nfn h() { let z = fastrand::f32(); }", encoding="utf-8"
    )
    fails2, _, _ = verdict(tmp, parse_pins(good), floors=False)
    check(
        any("STALE" in f and "a.rs::f32" in f and "x2" in f for f in fails2),
        "count growth must red STALE",
    )

    # site gone reds
    (tmp / "a.rs").write_text("crate; fn f() {}", encoding="utf-8")
    fails3, _, _ = verdict(tmp, parse_pins(good), floors=False)
    check(
        any("STALE" in f and "a.rs::f32" in f for f in fails3),
        "site removal must red STALE",
    )
    (tmp / "a.rs").write_text(src, encoding="utf-8")
    return fails


def walk_arms(tmp: Path) -> list[str]:
    fails: list[str] = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            fails.append(msg)

    # A fixture tree with no .git falls back to the filesystem walk
    # (tracked_walk's rule) — and vendored drops are excluded there too.
    # Fresh dir: pin_arms' files must not leak into this population.
    fresh = Path(tempfile.mkdtemp(prefix="global_rng_walk_"))
    try:
        (fresh / "vendor").mkdir()
        (fresh / "vendor" / "v.rs").write_text(
            "fn f() { let x = fastrand::f32(); }", encoding="utf-8"
        )
        live = scan(fresh)
        check(live == {}, "vendored drop must be excluded from the population")
    finally:
        shutil.rmtree(fresh, ignore_errors=True)
    return fails


def floor_arms(tmp: Path) -> list[str]:
    """The floors are the blindness detector — an arm must watch them fire.
    Kills the default-True flip and the two `< -> <=` boundary mutants."""
    fails: list[str] = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            fails.append(msg)

    # A sub-floor fixture called POSITIONALLY (default floors=True) must
    # produce both floor lines — proves the default is ON and the floors fire.
    small = tmp / "floor_small"
    small.mkdir()
    (small / "one.rs").write_text(
        "fn f() { let x = fastrand::f32(); }", encoding="utf-8"
    )
    pins = {"one.rs::f32": "1# tiny fixture"}
    fails1, _, _ = verdict(small, pins)
    check(
        any("MIN_SITES" in f for f in fails1)
        and any("MIN_FILES" in f for f in fails1),
        "sub-floor fixture must fire both floors",
    )

    # A fixture sized EXACTLY at both floors must be clean — the boundary
    # cell `n < MIN` and `n == MIN` must disagree about.
    edge = tmp / "floor_edge"
    edge.mkdir()
    per_file = MIN_SITES // MIN_FILES
    extra = MIN_SITES - per_file * MIN_FILES
    for fi in range(MIN_FILES):
        n = per_file + (1 if fi < extra else 0)
        lines = [f"fn f{fi}_{j}() {{ let x = fastrand::f32(); }}" for j in range(n)]
        (edge / f"m{fi}.rs").write_text("\n".join(lines), encoding="utf-8")
    epins = {
        f"m{fi}.rs::f32": f"{per_file + (1 if fi < extra else 0)}# boundary"
        for fi in range(MIN_FILES)
    }
    fails2, _, _ = verdict(edge, epins)
    check(
        not any("floor" in f for f in fails2),
        f"fixture at exactly the floors ({MIN_SITES} sites / {MIN_FILES} files) must be clean, got {fails2}",
    )
    return fails


def selftest() -> list[str]:
    """The arm `arm_reach_audit` runs (argumentless, by its arm vocabulary):
    it creates its own fixture tree."""
    tmp = Path(tempfile.mkdtemp(prefix="global_rng_gate_"))
    try:
        return classifier_arms() + pin_arms(tmp) + walk_arms(tmp) + floor_arms(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    fails: list[str] = []
    fails += selftest()
    vfails, n_sites, n_files = verdict(REPO_ROOT, parse_pins(PINS))
    fails += vfails
    if fails:
        for f in fails:
            print(f)
        print(f"✗ global_rng_gate: {len(fails)} failure(s)")
        return 1
    print(
        f"✓ global_rng_gate: {n_sites} global sites across {n_files} files, every row pinned"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
