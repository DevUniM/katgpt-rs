#!/usr/bin/env python3
"""A latency ceiling satisfied by a loop the optimiser DELETED (Issue 855).

    let start = Instant::now();
    for _ in 0..n { let _ = f(&loop_invariant_input); }
    let ns_per = start.elapsed().as_nanos() as f64 / n as f64;
    assert!(ns_per < 10_000.0, "too slow: {ns_per} ns/op");

rustc + fat LTO eliminates inlined-callee work whose outer result is dead, so
`ns_per` is **0.0** and the ceiling passes with MAXIMUM margin. A flaky bar
fails sometimes and is eventually noticed; this passes always, on every box, in
every profile that optimises — and reports a throughput figure for work that
did not happen.

**This is the `#![cfg]` green-zero rule one layer down.** There the binary is
empty and the count is 0; here the binary is not empty and the assertion
**runs, and is satisfied by absent work**, so the output is a plausible number
rather than a zero count and no count floor can see it.

    scripts/timed_region_guard_gate.py                 # the verdict AND the arms
    scripts/timed_region_guard_gate.py --prove-fires <sha>

## Why a gate and not a sweep-and-done

The treatment has existed for months. `tests/common/ab_timing.rs` defends
against exactly this **twice** — `ab_median_ratio` panics when every round
measured a 0 ns arm, `best_of_us` when every timed call did, and both messages
say *fix the harness, do not read a verdict out of it*. Neither reaches a
hand-rolled `Instant::now()` loop, and that is where every live specimen was.
Measured 2026-09-19 by EXECUTING all 34 in-scope regions: **7 were satisfied by
absent work**, 20.6% of the population, including two GOAT gates and one that
printed `Speedup: 8657.9x`. A known, un-enforced rule is this repo's own
most-repeated shape.

## The population, and why each half of it is load-bearing

In scope = a function that times a region (`Instant::now()` … `.elapsed()`)
**AND** loops >= 1000 times **AND** asserts something.

- **n >= 1000** is what makes a zero *exact*. The timer's own resolution cannot
  produce a 0 over that many iterations of work that happened, so there is no
  false-positive story on any box this workspace runs. Below it a 0 is a
  resolution artefact and the detector would be guessing.
- **asserts something** is what makes a zero *matter*. A region that only
  prints has no verdict a deleted loop can satisfy. (It can still print
  nonsense — Issue 855's `Speedup: 8657.9x` and `-169873680.5%` are both
  prints — so that residue is REPORTED on the verdict line rather than gated.)

GUARDED = the region calls the shared harness (`best_of_us` /
`ab_median_ratio`), or carries its own assertion that a timing quantity is
non-zero.

## What the static signal is worth — MEASURED, not assumed

Issue 855 T4 proposed grepping `let _ = f(…)` with no `black_box`. Executing
all 34 refuted it: the `let _ =` slice vanished 3 of 15 (20.0%) against 4 of 19
(21.1%) for the rest — **the base rate wearing a grep**. The column that does
separate is `black_box`: **7 of 23 without it vanished, 0 of 11 with it**. So
this gate does NOT try to predict which regions are broken. It gates the
strictly decidable thing — *is there a loud-zero defence at all* — and leaves
the reading to a human, which is the `percentile_index_audit` standing.

## The pins

`scripts/timed_region_survivors_expected.txt`, MEMBERSHIP with a reason per
row, both directions. A count is green on a swap, and a swap here is exactly
the bad case: one region repaired while a new unguarded gate lands. Every row
records the number somebody MEASURED, so the file is a measurement record and
not a backlog (Issue 785's rule).

The key is LINE-FREE — `<repo-relative path>::<enclosing fn>`. A line number
drifts on every edit above it, and a pin file that reds on noise is one people
delete.

⚠ STATED BLIND SPOTS, printed on the verdict line so a later census reads them
instead of re-deriving them:

- ⛔ The bound and the timer are matched at **FN scope, not REGION scope**, so
  a big SETUP loop before `Instant::now()` is credited to the timed region.
  Measured specimen (riir-neuron-db `local_kv/tests.rs::g2_compact_1000_
  entries_under_50ms`): `for i in 0..1000 { store.put(..) }` populates the
  store, and the timed region is a single `compact_wal()` call. The
  `n >= 1000` premise — *a zero over that many iterations is exact* — does NOT
  hold for such a row, because there is no loop in the timed region at all.
  Narrowing the predicate to the span between `Instant::now()` and `.elapsed()`
  would fix it and is NOT done here: base rate is 1 of 58 READ-tier rows
  workspace-wide, and the founding specimens all have the loop inside the
  region, so the change would be a real improvement with a real chance of
  dropping true rows. Pin such a row with this reason rather than repairing
  the sibling.
- The loop bound is resolved ONE hop (a literal `let`/`const`/`static` in the
  same body, else at file scope). A bound computed from anything else —
  arithmetic, a fn call, a CLI arg — is not seen. One hop is what reaches
  Issue 855's own founding specimens (`let n = 100_000; for _ in 0..n`); two
  start needing a value model.
- A timed region spread across two functions (helper times, caller asserts) is
  not seen — the unit here is the enclosing fn.
- A region that only PRINTS is out of scope by construction, and its count is
  reported rather than gated.
- It does NOT claim a guarded region is CORRECT, nor that an unguarded one is
  broken. 27 of the 34 were measured alive.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import console_safe  # noqa: E402

console_safe.apply()

REPO = Path(__file__).resolve().parent.parent
PINS = Path(__file__).resolve().parent / "timed_region_survivors_expected.txt"

# The bound below which a 0 ns reading is a timer-resolution artefact rather
# than evidence of elimination. Issue 855 T3's own words.
MIN_ITERS = 1000

# Blindness floors. They break SEPARATELY: a walk regression takes `files` to
# ~0 with the predicate intact, and a masker/regex regression takes `regions`
# to 0 over an unchanged walk. Measured 2026-09-19 at 753 / 608.
MIN_FILES = 400
MIN_REGIONS = 300

GLOBS = (
    "tests/*.rs",
    "tests/**/*.rs",
    "benches/*.rs",
    "benches/**/*.rs",
    "crates/*/tests/*.rs",
    "crates/*/tests/**/*.rs",
    "crates/*/benches/*.rs",
    "crates/*/benches/**/*.rs",
    "crates/*/src/tests/*.rs",
)

NOW = re.compile(r"\bInstant::now\s*\(")
ELAPSED = re.compile(r"\.elapsed\s*\(")
# The shared treatment. Both entry points panic loudly when every measured arm
# read 0, which is the runtime detector this class needs.
HARNESS = re.compile(r"\bab_median_ratio\s*\(|\bbest_of_us\s*\(")
# A hand-rolled equivalent: an assertion that a timing quantity is non-zero.
ZEROGUARD = re.compile(
    r"(assert[a-z_]*!|panic!)[^;]{0,400}?(>\s*0|!=\s*0|>\s*0\.0|is_zero|== 0|> 0u|nonzero)",
    re.S,
)
ASSERT = re.compile(r"\bassert[a-z_]*!\s*\(|\bpanic!\s*\(")
# ⛔ The bound is USUALLY a local, not a literal, and a literal-only predicate
# cannot see Issue 855's own founding specimens: `tests/bench_regime_transition.rs`
# writes `let n = 100_000; for _ in 0..n`, and BOTH of the two arms T1 filed
# sit in that shape. A gate blind to the cases that motivated it is a gate that
# would have shipped them. So the bound is RESOLVED, one hop, through a literal
# `let`/`const` binding in the same body or at file scope. One hop only: two
# hops start needing a value model, and the arms pin the boundary.
LOOPN = re.compile(r"for\s+\w+\s+in\s+0\.\.=?\s*([A-Za-z_][A-Za-z0-9_]*|[0-9_]+)")
LITERAL_BIND = re.compile(
    r"\b(?:let|const|static)\s+(?:mut\s+)?([A-Za-z_][A-Za-z0-9_]*)"
    r"(?:\s*:\s*[A-Za-z0-9_:<>, ]+)?\s*=\s*([0-9][0-9_]*)"
)


def loop_bounds(body: str, file_scope: dict[str, int]) -> list[int]:
    """Every `for _ in 0..N` bound in `body`, with one hop of resolution."""
    binds = dict(file_scope)
    binds.update({m.group(1): int(m.group(2).replace("_", "")) for m in LITERAL_BIND.finditer(body)})
    out: list[int] = []
    for m in LOOPN.finditer(body):
        tok = m.group(1)
        if tok[0].isdigit():
            out.append(int(tok.replace("_", "")))
        elif tok in binds:
            out.append(binds[tok])
    return out

# ⛔ Issue 855 T5's two statically-decidable buckets, found by RUNNING the 33
# sibling rows rather than by reasoning about them. Neither is gated — both are
# REPORTED, the `print_only` standing — because each is a state ORTHOGONAL to
# "is there a loud-zero defence", which is the only thing this gate decides.
#
# `#[ignore]`: `cargo test --exact <fn>` on an ignored test prints
# `ok. 0 passed; 1 ignored` and exits 0 — byte-for-byte this family's own
# green-zero shape. The region is then neither guarded NOR satisfied by absent
# work; it is UNEXECUTED, a third state no axis here could see. Measured: 4 of
# the 33 sibling rows, all riir-chain, and T5's own runner nearly recorded them
# as results.
IGNORED_ATTR = re.compile(r"#\s*\[\s*ignore")
# A region whose quantity reaches no stream: it lives only inside an `assert!`
# message, i.e. it is visible ONLY on failure. Measured as the highest-yield
# slice by a factor of four — 1 VANISHED of 4 (25%) against a population rate
# of 6.3% — and the mechanism is plain: nobody can have read a number nobody
# prints. Confirmed again the day it shipped: the first two of this repo's own
# silent arms to be made to print were BOTH dead (`three_mode_router_goat`,
# `0.00 ns/call` over 10 000 iterations against a `< 50_000` bar).
#
# ⚠ STATED FALSE POSITIVE, measured rather than predicted: the unit here is the
# enclosing fn, so a region whose value is printed by its CALLER reads as
# silent. Two of this repo's nine are exactly that (`bench_688`'s `time_primal`
# and `bench_815`'s `run_case` both RETURN a figure their caller prints), which
# is a ~22% false-positive rate on a 9-row sample. That is why the bucket is
# REPORTED and never gated — it orders a read, it does not decide one.
PRINTS = re.compile(r"\b(?:e?println!|print!|eprint!|write(?:ln)?!)\s*\(")

FN = re.compile(r"\bfn\s+(\w+)\s*(?:<[^>{]*>)?\s*\(")


def tracked(root: Path) -> list[str]:
    """Tracked test/bench sources. git's index, never a filesystem walk — a
    gitignored vendored drop is nobody's to repair (Issue 777)."""
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", *GLOBS],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return sorted(set(p for p in out.stdout.split() if p.endswith(".rs")))


def attr_run(masked: str, fn_start: int) -> str:
    """The CONTIGUOUS attribute/comment run immediately above a fn.

    Not a fixed look-back window: an `#[ignore]` twenty lines up belongs to a
    different item, and crediting it would attribute one test's state to its
    neighbour. Walks back over attribute and comment lines only and stops at
    the first line that is neither — which is also why a blank line ends it,
    the shape `orphaned_attr_gate.py` exists to catch one axis over.
    """
    head = masked[:fn_start].rsplit("\n", 1)[0] if "\n" in masked[:fn_start] else ""
    out: list[str] = []
    for line in reversed(head.split("\n")):
        t = line.strip()
        if t.startswith("#[") or t.startswith("#![") or t.startswith("//"):
            out.append(t)
            continue
        break
    return "\n".join(out)


def fn_bodies(masked: str, raw: str | None = None):
    """(name, body, attrs) for every fn, by brace counting over MASKED text.

    ⛔ The BODY comes from the masked text and the ATTRIBUTES come from the
    RAW text, and the split is not a nicety — `mask_file` blanks `#[...]`
    lines, so an attribute run read off the masked source is always empty and
    the `#[ignore]` bucket would report a confident ZERO. Measured the first
    time this ran. It is the same rule `sequential_ab_timing_audit` records
    for `#[path = "…"]`, reached from the other direction.

    Safe because the masker is LENGTH-PRESERVING: it substitutes equal-length
    blanks, so one offset indexes both strings. `offsets_align()` asserts that
    premise rather than assuming it — if the masker ever stops preserving
    length, this silently reads the wrong lines.
    """
    src = masked if raw is None else raw
    for m in FN.finditer(masked):
        i = masked.find("{", m.end())
        if i < 0:
            continue
        depth = 0
        for j in range(i, len(masked)):
            if masked[j] == "{":
                depth += 1
            elif masked[j] == "}":
                depth -= 1
                if depth == 0:
                    yield m.group(1), masked[i:j], attr_run(src, m.start())
                    break


class FileScan(NamedTuple):
    """One file's verdict.

    A NamedTuple rather than a widening tuple: this grew from three fields to
    six and the callers unpack positionally, which is exactly how a sweep and
    its gate drift into disagreeing about which column is which.
    """

    regions: int
    unguarded: list[str]      # READ tier — literal bound, gated by MEMBERSHIP
    print_only: int           # asserts nothing — reported, never gated
    resolved_only: list[str]  # UNREAD tier — bound needed a hop, ratcheted
    ignored: list[str]        # `#[ignore]`d — UNEXECUTED, reported
    silent: list[str]         # prints nothing — unreadable on a pass, reported


def classify(text: str) -> FileScan:
    """One file, classified. See `FileScan` for the columns.

    ⚠ `ignored` and `silent` are computed over the WHOLE in-scope asserting
    population — both tiers — because that is the population Issue 855 T5
    measured, and scoping them to the gated tier would make the reported
    numbers answer a different question from the one that produced them.
    """
    # Issue 856's masker, IMPORTED and never re-written: three sibling
    # instruments have each reported a finding inside their own fixture
    # strings. Deferred, because that module imports from a sibling of ours.
    from platform_dead_code_audit import mask_file

    masked, _ = mask_file(text)
    if not NOW.search(masked):
        return FileScan(0, [], 0, [], [], [])
    # File-scope `const N: usize = 100_000;` — resolved once, shadowed by any
    # same-named binding inside the body.
    file_scope = {
        m.group(1): int(m.group(2).replace("_", ""))
        for m in LITERAL_BIND.finditer(masked)
    }
    regions = 0
    unguarded: list[str] = []
    resolved_only: list[str] = []
    ignored: list[str] = []
    silent: list[str] = []
    print_only = 0
    for name, body, attrs in fn_bodies(masked, text):
        if not (NOW.search(body) and ELAPSED.search(body)):
            continue
        regions += 1
        literal = [
            int(x.replace("_", ""))
            for x in re.findall(r"for\s+\w+\s+in\s+0\.\.=?\s*([0-9][0-9_]*)", body)
        ]
        big = loop_bounds(body, file_scope)
        if not [x for x in big if x >= MIN_ITERS]:
            continue
        if HARNESS.search(body) or ZEROGUARD.search(body):
            continue
        if not ASSERT.search(body):
            print_only += 1
            continue
        # TIER, and it is the difference between a wall and a ratchet: a
        # LITERAL bound is the population Issue 855 T3 executed end to end, so
        # every row in it is adjudicated and a membership wall is honest. A
        # bound that needed a hop is real and UNREAD, and pinning an unread
        # bucket by membership is a backlog wearing a pin (Issue 785).
        if [x for x in literal if x >= MIN_ITERS]:
            unguarded.append(name)
        else:
            resolved_only.append(name)
        # Both are ORTHOGONAL to the tier and to the guard: an ignored region
        # can be guarded, a silent one can be in either tier. Recorded on the
        # whole in-scope asserting population, never folded into a verdict.
        if IGNORED_ATTR.search(attrs):
            ignored.append(name)
        if not PRINTS.search(body):
            silent.append(name)
    return FileScan(regions, unguarded, print_only, resolved_only, ignored, silent)


class RepoScan(NamedTuple):
    """One repo's verdict — `scan`'s return. Named for `FileScan`'s reason."""

    files: int
    regions: int
    unguarded: list[str]
    print_only: int
    unread: list[str]
    ignored: list[str]
    silent: list[str]


def scan(root: Path) -> RepoScan:
    files = tracked(root)
    regions = 0
    found: list[str] = []
    unread: list[str] = []
    print_only = 0
    ignored: list[str] = []
    silent: list[str] = []
    for rel in files:
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        fs = classify(text)
        regions += fs.regions
        print_only += fs.print_only
        found.extend(f"{rel}::{n}" for n in fs.unguarded)
        unread.extend(f"{rel}::{n}" for n in fs.resolved_only)
        ignored.extend(f"{rel}::{n}" for n in fs.ignored)
        silent.extend(f"{rel}::{n}" for n in fs.silent)
    return RepoScan(len(files), regions, sorted(found), print_only,
                    sorted(unread), sorted(ignored), sorted(silent))


def read_pins(path: Path) -> dict[str, str]:
    """key -> reason. A reasonless row is REFUSED: a pin nobody can adjudicate
    from is a pin that outlives the thing it was written for."""
    pins: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "|" not in line:
            raise SystemExit(
                f"⛔ timed-region pin row without a reason: {line!r} — "
                "the format is `<path>::<fn>  |  <reason>`"
            )
        key, reason = line.split("|", 1)
        key, reason = key.strip(), reason.strip()
        if not reason:
            raise SystemExit(f"⛔ timed-region pin row with an EMPTY reason: {key!r}")
        pins[key] = reason
    return pins


def selftest() -> None:
    """The arms. UNCONDITIONAL — `docs_gate.sh` invokes each check with NO
    arguments, so an arm behind a flag never fires on a push (Issue 789)."""
    guarded_harness = (
        "fn g() { let t = Instant::now();\n"
        "  for _ in 0..10000 { work(); }\n"
        "  let d = t.elapsed();\n"
        "  let r = best_of_us(3, 10000, || work());\n"
        "  assert!(r < 10.0, \"{d:?}\"); }\n"
    )
    u = classify(guarded_harness).unguarded
    assert u == [], f"the shared harness did not count as a defence: {u}"

    own_guard = (
        "fn g() { let t = Instant::now();\n"
        "  for _ in 0..10000 { work(); }\n"
        "  let ns = t.elapsed().as_nanos();\n"
        "  assert!(ns > 0, \"instrument failure\");\n"
        "  assert!(ns < 10_000_000); }\n"
    )
    u = classify(own_guard).unguarded
    assert u == [], f"a hand-rolled non-zero assertion did not count: {u}"

    bare = (
        "fn g() { let t = Instant::now();\n"
        "  for _ in 0..100000 { let _ = f(&x); }\n"
        "  let ns = t.elapsed().as_nanos() as f64 / 100000.0;\n"
        "  assert!(ns < 10_000.0); }\n"
    )
    u = classify(bare).unguarded
    assert u == ["g"], f"Issue 855's own shape was not flagged: {u}"

    # ⛔ The n >= 1000 bound is the thing that makes a zero EXACT. Below it a 0
    # is a timer-resolution artefact, and flagging one is the cries-wolf
    # outcome this report exists to avoid. Pinned from BOTH sides so the
    # boundary cannot drift silently.
    small = bare.replace("0..100000", "0..100").replace("100000.0", "100.0")
    u = classify(small).unguarded
    assert u == [], f"a small-n region was flagged — a 0 there proves nothing: {u}"
    edge = bare.replace("0..100000", "0..1000").replace("100000.0", "1000.0")
    u = classify(edge).unguarded
    assert u == ["g"], f"the n == {MIN_ITERS} boundary is exclusive: {u}"

    # A region with no assertion has no verdict a deleted loop can satisfy. It
    # is REPORTED (it can still print nonsense) and never gated.
    printer = (
        "fn g() { let t = Instant::now();\n"
        "  for _ in 0..100000 { let _ = f(&x); }\n"
        '  println!("{:?}", t.elapsed()); }\n'
    )
    _fs = classify(printer)
    u, p = _fs.unguarded, _fs.print_only
    assert u == [] and p == 1, f"print-only should report, not gate: {u} {p}"

    # ⛔ THE TIER SPLIT, and it is what separates a wall from a ratchet.
    # Issue 855 T1's OWN two founding specimens are `let n = 100_000; for _ in
    # 0..n` — a literal-only predicate cannot see them, so the gate would have
    # shipped the class it was written for. One hop reaches them, and those
    # rows are UNREAD, so they are counted rather than pinned by name.
    hop = (
        "fn g() { let n = 100_000;\n"
        "  let t = Instant::now();\n"
        "  for _ in 0..n { let _ = f(&x); }\n"
        "  let ns = t.elapsed().as_nanos() as f64 / n as f64;\n"
        "  assert!(ns < 10_000.0); }\n"
    )
    _fs = classify(hop)
    u, ro = _fs.unguarded, _fs.resolved_only
    assert u == [] and ro == ["g"], f"one-hop bound mis-tiered: {u} {ro}"
    # File scope resolves too, and a body binding SHADOWS it.
    _fs = classify("const N: usize = 50_000;\n" + hop.replace("let n = 100_000;\n", "").replace("0..n", "0..N").replace("/ n as", "/ N as"))
    u, ro = _fs.unguarded, _fs.resolved_only
    assert ro == ["g"], f"file-scope const not resolved: {ro}"
    # Two hops is deliberately OUT — resolving it needs a value model.
    two = hop.replace("let n = 100_000;", "let base = 100_000; let n = base;")
    _fs = classify(two)
    u, ro = _fs.unguarded, _fs.resolved_only
    assert u == [] and ro == [], f"a two-hop bound was resolved: {u} {ro}"
    # A literal bound stays in the READ tier even beside a resolved one.
    both = hop.replace("for _ in 0..n {", "for _ in 0..2000 { g(); }\n  for _ in 0..n {")
    _fs = classify(both)
    u, ro = _fs.unguarded, _fs.resolved_only
    assert u == ["g"] and ro == [], f"a literal bound was demoted to the unread tier: {u} {ro}"

    # A fn that never times anything is not a region, however many loops it has.
    u = classify("fn g() { for _ in 0..100000 { work(); } assert!(true); }\n").unguarded
    assert u == [], f"an untimed fn entered the population: {u}"

    # The MASKER is why a fixture string is not source — this file is itself
    # full of Rust in string literals, and three sibling instruments have each
    # reported a finding inside their own test data.
    fixture = 'fn h() -> &\'static str { r#"\n' + bare + '"# }\n'
    u = classify(fixture).unguarded
    assert u == [], f"a timed region inside a raw string read as source: {u}"

    # The pin READER, both refusals. A reasonless row must not be silently
    # accepted — that is how a pin outlives the thing it was written for.
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "pins.txt"
        p.write_text("# c\na.rs::f  |  measured 3 ns\n", encoding="utf-8")
        assert read_pins(p) == {"a.rs::f": "measured 3 ns"}
        for bad in ("a.rs::f\n", "a.rs::f  |  \n"):
            p.write_text(bad, encoding="utf-8")
            try:
                read_pins(p)
            except SystemExit:
                pass
            else:  # pragma: no cover
                raise AssertionError(f"a reasonless pin row was accepted: {bad!r}")

    # The floors are FLOORS. A classifier that goes blind must RED, not report
    # a clean zero — the failure mode this whole class is about, one level up.
    assert MIN_FILES > 0 and MIN_REGIONS > 0, "a floor of 0 cannot detect blindness"

    # ⛔ A region needs BOTH halves of the timing pair. `Instant::now()` with no
    # `.elapsed()` is a start time somebody captured and never read — not a
    # timed region, and counting it would inflate every figure this gate
    # reports. Arms the `and` in `classify`'s region test, which no other
    # fixture distinguishes because they all carry both halves.
    half_pair = (
        "fn g() { let t = Instant::now();\n"
        "  for _ in 0..100000 { let _ = f(&x); }\n"
        "  assert!(true); }\n"
    )
    fs = classify(half_pair)
    assert fs.regions == 0, (
        "`Instant::now()` with no `.elapsed()` counted as a timed region — the "
        f"pair test must require BOTH halves: {fs.regions}")
    assert fs.unguarded == [], f"…and it must not be flagged either: {fs.unguarded}"
    # The mirror: `.elapsed()` with no `Instant::now()` is equally not a region.
    assert classify(
        "fn g() { let d = t.elapsed();\n"
        "  for _ in 0..100000 { let _ = f(&x); }\n"
        "  assert!(d.as_nanos() < 10); }\n"
    ).regions == 0, "`.elapsed()` with no `Instant::now()` counted as a region"

    # ⛔ The PREMISE that lets attributes be read off the raw text at a masked
    # offset: `mask_file` is LENGTH-PRESERVING. Asserted, not assumed — if it
    # ever stops being true, `attr_run` reads the wrong lines and the
    # `#[ignore]` bucket reports a confident number that is simply wrong,
    # which is the silent direction.
    from platform_dead_code_audit import mask_file as _mf

    for probe in (bare, printer, fixture):
        _masked, _ = _mf(probe)
        assert len(_masked) == len(probe), (
            "mask_file is no longer length-preserving — `fn_bodies` indexes the "
            "raw text at a MASKED offset and now reads the wrong lines")

    # ── Issue 855 T5's two reported buckets ────────────────────────────────
    # Each is asserted in BOTH directions. An arm that only shows the bucket
    # filling is satisfied by a predicate that fires on everything.
    ign = (
        "#[test]\n"
        "#[ignore = \"timing test\"]\n"
        "fn g() { let t = Instant::now();\n"
        "  for _ in 0..100000 { let _ = f(&x); }\n"
        "  let ns = t.elapsed().as_nanos() as f64 / 100000.0;\n"
        "  assert!(ns < 10_000.0); }\n"
    )
    fs = classify(ign)
    assert fs.ignored == ["g"], f"an #[ignore]d in-scope region was not seen: {fs.ignored}"
    assert fs.unguarded == ["g"], (
        "#[ignore] must not change the GUARD verdict — the two axes are "
        f"orthogonal: {fs.unguarded}")
    fs = classify(ign.replace("#[ignore = \"timing test\"]\n", ""))
    assert fs.ignored == [], f"a non-ignored region was reported ignored: {fs.ignored}"

    # ⛔ The attribute must belong to THIS fn. An `#[ignore]` on the PREVIOUS
    # item is the false positive a fixed look-back window would produce, and it
    # would attribute one test's state to its neighbour.
    neighbour = (
        "#[test]\n#[ignore]\nfn other() { let _ = 1; }\n\n"
        "#[test]\n"
        "fn g() { let t = Instant::now();\n"
        "  for _ in 0..100000 { let _ = f(&x); }\n"
        "  let ns = t.elapsed().as_nanos() as f64 / 100000.0;\n"
        "  assert!(ns < 10_000.0); }\n"
    )
    fs = classify(neighbour)
    assert fs.ignored == [], (
        f"an #[ignore] on the PREVIOUS item was credited to this one: {fs.ignored}")

    # SILENT: the quantity reaches no stream, so it is visible only on failure.
    fs = classify(bare)
    assert fs.silent == ["g"], f"a region printing nothing was not seen: {fs.silent}"
    loud = bare.replace("assert!(ns < 10_000.0);",
                        'println!("{ns} ns"); assert!(ns < 10_000.0);')
    fs = classify(loud)
    assert fs.silent == [], f"a region that DOES print was reported silent: {fs.silent}"
    assert fs.unguarded == ["g"], (
        "printing is not a loud-zero defence and must not change the guard "
        f"verdict: {fs.unguarded}")


def prove_fires(sha: str) -> int:
    """Known-answer validation against a frozen commit. At the parent of the
    Issue-855 repairs the seven VANISHED regions were unguarded, so the gate
    must report MORE findings there than the pin file admits."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        tar = subprocess.run(
            ["git", "-C", str(REPO), "archive", sha],
            capture_output=True,
        )
        if tar.returncode != 0:
            print(f"⛔ could not archive {sha}")
            return 2
        subprocess.run(["tar", "-x", "-C", str(root)], input=tar.stdout, check=True)
        # `git archive` produces no .git, so tracked() falls back to nothing —
        # walk instead, which is sound here: an archive contains only tracked files.
        files = [
            str(p.relative_to(root))
            for p in root.rglob("*.rs")
            if any(part in ("tests", "benches") for part in p.parts)
        ]
        found = []
        regions = 0
        for rel in files:
            try:
                text = (root / rel).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            _fs = classify(text)
            r, u = _fs.regions, _fs.unguarded
            regions += r
            found.extend(f"{rel}::{n}" for n in u)
        pins = read_pins(PINS)
        pins.pop("__max_unread_resolved", None)
        extra = sorted(set(found) - set(pins))
        print(f"  {sha}: {len(files)} file(s), {regions} region(s), {len(found)} unguarded")
        print(f"  UNPINNED at that commit: {len(extra)}")
        for k in extra:
            print(f"    + {k}")
        if not extra:
            print("⛔ --prove-fires found nothing — the gate cannot fire")
            return 1
        print(f"✓ the gate fires at {sha}: {len(extra)} region(s) the pins do not admit")
        return 0


def main(argv: list[str]) -> int:
    selftest()
    if "--prove-fires" in argv:
        i = argv.index("--prove-fires")
        return prove_fires(argv[i + 1] if i + 1 < len(argv) else "HEAD~1")

    sc = scan(REPO)
    n_files, n_regions, found = sc.files, sc.regions, sc.unguarded
    print_only, unread = sc.print_only, sc.unread
    pins = read_pins(PINS)
    ratchet_key = "__max_unread_resolved"
    if ratchet_key not in pins:
        print(f"⛔ the pin file has no `{ratchet_key}` row — the unread tier is ungated")
        return 1
    try:
        ratchet = int(pins.pop(ratchet_key).split()[0])
    except ValueError:
        print(f"⛔ `{ratchet_key}` is not a number")
        return 1

    if n_files < MIN_FILES:
        print(f"✗ timed-region guard gate: walk floor — {n_files} file(s) < {MIN_FILES}")
        return 1
    if n_regions < MIN_REGIONS:
        print(
            f"✗ timed-region guard gate: predicate floor — {n_regions} region(s) "
            f"< {MIN_REGIONS}; the classifier went blind over an unchanged walk"
        )
        return 1

    unpinned = sorted(set(found) - set(pins))
    stale = sorted(set(pins) - set(found))

    print(
        f"timed-region guard gate — {n_files} tracked test/bench file(s), "
        f"{n_regions} timed region(s); READ tier (literal bound >= {MIN_ITERS}, "
        f"asserting, unguarded): {len(found)} against {len(pins)} pinned; "
        f"UNREAD tier (bound needed a hop): {len(unread)} against a ratchet of "
        f"{ratchet}; {print_only} print-only in-scope (reported, never gated); "
        f"{len(sc.ignored)} #[ignore]d, {len(sc.silent)} print NO number "
        "(both REPORTED — orthogonal to the guard, Issue 855 T5)"
    )
    if len(unread) > ratchet:
        print(
            f"  ✗ UNREAD tier {len(unread)} > ratchet {ratchet} — a NEW unguarded "
            "timed region landed. Give it `best_of_us` / `ab_median_ratio`, or RUN "
            "it, read the printed number, and raise the ratchet with that number "
            "as the reason."
        )
        for k in sorted(set(unread))[:20]:
            print(f"      · {k}")
        return 1
    if len(unread) < ratchet:
        print(
            f"  ⚠ UNREAD tier is {len(unread)}, BELOW the ratchet of {ratchet} — "
            "tighten it in the same commit that lowered it, or the slack is a "
            "free pass for the next one. Not a failure: a ratchet that reds on "
            "an improvement is a ratchet people delete."
        )
    for k in unpinned:
        print(f"  ✗ UNPINNED {k} — no loud-zero defence: use `best_of_us` (one-arm")
        print("      ceilings) or `ab_median_ratio` (A/B ratios), which panic when an")
        print("      arm measures 0; or RUN it, read the printed number, and add a row")
    for k in stale:
        print(f"  ✗ STALE {k} — pinned but no longer an unguarded in-scope region")
        print(f"      (reason on file: {pins[k]}); remove the row")
    if unpinned or stale:
        print(
            f"✗ timed-region guard gate FAILED — {len(unpinned)} unpinned, "
            f"{len(stale)} stale"
        )
        return 1
    print(
        "✓ timed-region guard gate PASSED — every unguarded in-scope timed region "
        "carries a row recording the number somebody MEASURED. ⚠ It does NOT claim "
        "a pinned region is safe: `black_box` is the weakest of the three defences "
        "(result, ARGUMENTS, RECEIVER) and two arms vanished carrying one. STATED "
        "blind spots: a loop bound needing more than ONE hop of resolution, a "
        "region split across two fns, and the print-only residue counted above "
        "(Issue 855 T4). ⛔ Two MORE states it reports and cannot gate, each "
        "found by EXECUTING the population rather than reasoning about it: an "
        "`#[ignore]`d region is UNEXECUTED — `ok. 0 passed; 1 ignored`, exit 0, "
        "this family's own green-zero shape one axis over — and a region that "
        "prints NO number is unreadable in the configuration that passes, which "
        "measured 4x the population's VANISHED rate. A third, UNBUILDABLE, is "
        "not statically decidable at all and is out of scope by construction: "
        "it is a manifest-RESOLUTION property (riir-chain Issue 157)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
