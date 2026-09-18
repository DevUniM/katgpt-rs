#!/usr/bin/env python3
"""A wall-clock gate that times arm A to completion, then arm B, measures the
BOX — `scripts/sequential_ab_timing_audit.py` (Issue 834, from Issue 833).

    let t = Instant::now();  for _ in 0..N { a(); }  let a_ns = t.elapsed();
    let t = Instant::now();  for _ in 0..N { b(); }  let b_ns = t.elapsed();
    assert!(a_ns as f64 / b_ns as f64 >= 0.90);

Two sequential arms of the **same** work measured +5.2% and +21.7% thirty
seconds apart on a loaded box (Issue 723 T5). A 10% bar cannot survive that,
so the verdict belongs to whatever else the scheduler was doing rather than to
the code — and a gate whose verdict the box decides is a gate that cannot run
in CI, which is the finding either way.

`tests/common/ab_timing.rs` is the treatment this repo already ships:
interleaved `(a-chunk, b-chunk)` pairs so a drift moves BOTH arms and cancels
in the ratio, the MEDIAN across pairs so one preemption spike is discarded,
and a loud zero when the optimiser deletes an arm.

## Why this exists as a census

Issue 723 converted the 8 targets its census could see. Issue 831 converted a
9th by walking into it. Issue 833's `bench_105_gdn2_goat.rs` GOAT 2 was found
by `scripts/x86_64_execution_matrix.sh` reporting it PASSED-ALONE — it read
0.844 against a 0.90 bar in cell 8 and passed 3/3 alone. **None of the three
was found by a census**, which is the whole argument for one: the treatment
has existed for months and the members are found by tripping over them.

## What this is NOT

⛔ **A report, exit 0** — except a blindness floor or a failing self-test,
which exit **2**. It is deliberately NOT a gate and NOT a drift sweep, and
Issue 833 T4 refuses both by name. The migration is **not mechanical** and a
count cannot express it:

  * The `a`/`b` ORIENTATION is a per-target read. `AbRatio::median` is a TIME
    ratio; roughly half these gates state a THROUGHPUT claim, whose ratio is
    its reciprocal. Getting it backwards inverts the bar SILENTLY.
  * The chunk size comes off the target's own printed per-round range, which
    does not exist until the target has been migrated once.
  * Arms must be `black_box`ed at both ends. The `let _ = f()` elimination
    shape (Issue 723 Class A2) is orthogonal to interleaving and survives it.

So a slice chosen from this report is a slice chosen from a classifier with a
large UNRESOLVED bucket. Read it to find candidates, never to bulk-convert.

## The buckets, and why UNRESOLVED is printed first-class

**ADOPTED** — names `common/ab_timing.rs` or calls `ab_median_ratio`.
**SEQUENTIAL** — >= 2 `Instant::now()` AND a ratio whose BOTH sides are
timing-derived identifiers, minus count-like denominators (`iters`,
`n_tokens`, `len`, `steps`). The decidable class.
**UNRESOLVED** — timed, but no decidable two-arm ratio. This is **not
"clean"**: a two-arm comparison written in a shape the regex cannot see lands
here, and so does an ordinary single-arm latency bar that is not the class at
all. It is reported as its own number and is never folded into either
neighbour — the rule this repo states for percentile UNRESOLVED, for wasm32
UNRESOLVED, and for `len_derived`'s 118 bind sites.

⚠ Two predicates that disagree about the population corroborate a magnitude
better than either alone: an independent looser pass over `tests/*.rs` +
`crates/*/tests/*.rs` returned 55 where this one returns 57 (Issue 833).
**Take the figure from a run, never from a sentence.**

⚠ **STATED blind spots**, so a later census reads them instead of re-deriving
them: a ratio built through a helper function; a comparison expressed as a
subtraction or a percentage rather than a division; two arms timed from ONE
`Instant::now()` by differencing `elapsed()` twice; and arm ORIENTATION,
which is not statically decidable and is the part that actually costs time.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import re  # noqa: E402

import console_safe  # noqa: E402
from platform_dead_code_audit import mask_file  # noqa: E402
from tracked_walk import tracked_files  # noqa: E402

console_safe.apply()

# ── blindness floors ────────────────────────────────────────────────────────
# Two, because they break differently: a walk regression takes RS_FILES to ~0
# with the classifier intact, and a masker/regex regression takes TIMED to 0
# over an unchanged walk. Either one reports a confident, perfect-looking
# "0 SEQUENTIAL" — the same output as the class being eradicated.
MIN_RS_FILES = 1400
MIN_TIMED = 120

INSTANT = re.compile(r"\bInstant::now\s*\(\s*\)")
ADOPTED_RE = re.compile(r"common/ab_timing\.rs|\bab_median_ratio\b")

_T = r"(?:ns|us|ms|secs|elapsed|time|tps|throughput|per_call|latency)"
# Both sides must be timing-derived IDENTIFIERS. A bare numeral or a literal
# on either side is a unit conversion, not a comparison of two measured arms.
RATIO = re.compile(rf"\b([A-Za-z_]\w*{_T}\w*|{_T}\w*)\s*/\s*([A-Za-z_]\w*{_T}\w*|{_T}\w*)\b")
# A denominator that counts things makes the expression a RATE (ns per token),
# which every single-arm latency bar computes and which is not this class.
COUNTY = re.compile(r"\b(iter|iters|iterations|n_\w+|\w+_count|count|steps|len|insert|tokens)\b", re.I)


def is_target(rel: str) -> bool:
    """Is this path a test or bench target — i.e. somewhere a GATE lives?

    `src/` is excluded deliberately: a timing ratio in library code is a
    runtime decision (a scheduler, an adaptive threshold), not an assertion
    whose verdict a loaded box can flip.
    """
    return (
        rel.startswith("tests/")
        or rel.startswith("benches/")
        or "/tests/" in rel
        or "/benches/" in rel
    )


def ratio_hits(masked: str) -> list:
    """Two-timing-arm ratios in already-masked source, in source order."""
    hits = []
    for m in RATIO.finditer(masked):
        a, b = m.group(1), m.group(2)
        if a == b:
            continue  # x/x is a normalisation, not a comparison
        if COUNTY.search(a) or COUNTY.search(b):
            continue
        hits.append(m.group(0))
    return hits


def classify(text: str) -> tuple:
    """`(verdict, n_instant, hits)` for one target's source.

    Masking is not optional and is imported rather than re-written: a text
    scan cannot tell a real `Instant::now()` from one inside a doc-comment or
    a raw-string fixture, and this workspace has met that class three times
    (wasm32_surface, platform_dead_code, subprocess_encoding).
    """
    masked, _attrs = mask_file(text)
    n = len(INSTANT.findall(masked))
    if n == 0:
        return ("UNTIMED", 0, [])
    # ADOPTED is read off the UNMASKED text on purpose: `#[path = "..."]` puts
    # the module path inside a string literal, which masking blanks.
    if ADOPTED_RE.search(text):
        return ("ADOPTED", n, [])
    if n < 2:
        # One timer cannot bracket two arms separately in the ordinary shape.
        # Not proven — see the STATED blind spot about differencing one timer
        # twice — so it is UNRESOLVED, never "clean".
        return ("UNRESOLVED", n, [])
    hits = ratio_hits(masked)
    return (("SEQUENTIAL" if hits else "UNRESOLVED"), n, hits)


def scan(repo: str) -> dict:
    """Classify every timed target in `repo`. Returns a result dict."""
    files, excluded = tracked_files(repo, "*.rs")
    root = Path(repo).resolve()
    rows = {"ADOPTED": [], "SEQUENTIAL": [], "UNRESOLVED": []}
    n_targets = 0
    for f in files:
        rel = str(Path(f).resolve().relative_to(root)).replace("\\", "/")
        if not is_target(rel):
            continue
        n_targets += 1
        try:
            text = Path(f).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        verdict, n, hits = classify(text)
        if verdict == "UNTIMED":
            continue
        rows[verdict].append((rel, n, hits))
    return {
        "repo": Path(repo).name,
        "rs_files": len(files),
        "vendored": excluded,
        "targets": n_targets,
        "rows": rows,
        "timed": sum(len(v) for v in rows.values()),
    }


# ── arms ────────────────────────────────────────────────────────────────────
def floor_verdict(tot_files: int, timed: int) -> tuple:
    """`(exit_code, message|None)` for the two blindness floors.

    EXTRACTED out of `main()` deliberately. This repo has recorded the same
    finding in four instruments: a gate's own floor arithmetic sits inline
    beside its error strings, so no arm can reach it, and the classifier's
    self-test — which is the only thing anybody runs — cannot see the numbers
    that decide whether the classifier was even looking. Perturbing
    `MIN_TIMED` to 0 was SURVIVED by the arms until this function existed.
    """
    if tot_files < MIN_RS_FILES:
        return (2, f"⛔ WALK REGRESSION — {tot_files} tracked *.rs below floor "
                   f"{MIN_RS_FILES}. The verdict above is a green ZERO, not a pass.")
    if timed < MIN_TIMED:
        return (2, f"⛔ PREDICATE REGRESSION — {timed} timed target(s) below floor "
                   f"{MIN_TIMED}. The masker or the Instant::now() pattern is blind.")
    return (0, None)


def selftest() -> list:
    """Arms over the classifier's own bucket boundaries.

    The bucket boundaries ARE the finding here, and this repo's own history
    says they are only testable against cases whose answer is known
    independently: `wasm32_surface_audit` produced three confident wrong
    answers before a right one, all in the classifier.
    """
    fails = []

    def v(src):
        return classify(src)[0]

    # 1. The motivating specimen, reduced: two timed arms, a throughput ratio.
    seq = """
    fn g() {
        let t = Instant::now();
        for _ in 0..N { a(); }
        let a_ns = t.elapsed().as_nanos();
        let t = Instant::now();
        for _ in 0..N { b(); }
        let b_ns = t.elapsed().as_nanos();
        assert!(a_ns / b_ns >= 1.0);
    }"""
    if v(seq) != "SEQUENTIAL":
        fails.append(f"the canonical two-arm shape read {v(seq)}, not SEQUENTIAL")

    # 2. ADOPTED wins over SEQUENTIAL even when the old arithmetic is still in
    #    the file — a partially-migrated target must not be reported as
    #    unmigrated, or the report reds work somebody already did.
    if v('#[path = "common/ab_timing.rs"]\nmod ab_timing;\n' + seq) != "ADOPTED":
        fails.append("a file naming ab_timing.rs must read ADOPTED")
    if v("fn g() { let t = Instant::now(); let u = Instant::now();\n"
         "  let r = ab_median_ratio(1, 1, 1, a, b); }") != "ADOPTED":
        fails.append("a call to ab_median_ratio must read ADOPTED")

    # 3. A RATE is not the class. This is the single most common false
    #    positive: every one-arm latency bar divides elapsed time by a count.
    rate = """
    fn g() {
        let t = Instant::now(); work(); let total_us = t.elapsed().as_micros();
        let t2 = Instant::now(); more(); let _x = t2.elapsed();
        let per = total_us / n_tokens;
    }"""
    if v(rate) != "UNRESOLVED":
        fails.append(f"a time/count RATE read {v(rate)}, not UNRESOLVED")

    # 4. MASKING, both seams. A fixture string and a doc-comment are the two
    #    shapes that made three sibling instruments report findings inside
    #    their own test data.
    if v('fn g() { let s = "let t = Instant::now(); a_ns / b_ns"; let u = 1; }') != "UNTIMED":
        fails.append("Instant::now() inside a string literal must not count")
    if v("/// let t = Instant::now(); a_ns / b_ns\n"
         "/// let t = Instant::now();\nfn g() {}") != "UNTIMED":
        fails.append("Instant::now() inside a doc comment must not count")
    # ...and the mask must not swallow a REAL site on the next line.
    mixed = ('fn g() {\n  let s = "Instant::now()";\n'
             '  let t = Instant::now(); let a_ns = t.elapsed();\n'
             '  let t = Instant::now(); let b_ns = t.elapsed();\n'
             '  let r = a_ns / b_ns; }')
    if v(mixed) != "SEQUENTIAL":
        fails.append(f"a real site beside a masked one read {v(mixed)}, not SEQUENTIAL")

    # 5. One timer is UNRESOLVED and explicitly NOT clean — the bucket note
    #    above promises this and a reader will rely on it.
    if v("fn g() { let t = Instant::now(); let a_ns = t.elapsed(); }") != "UNRESOLVED":
        fails.append("a single-timer target must read UNRESOLVED")

    # 6. x/x is a normalisation. Without this the ratio rule fires on every
    #    file that divides a quantity by itself to get 1.0.
    same = ("fn g() { let t = Instant::now(); let a_ns = t.elapsed();\n"
            "  let t = Instant::now(); let _ = t.elapsed();\n"
            "  let r = a_ns / a_ns; }")
    if v(same) != "UNRESOLVED":
        fails.append(f"x/x normalisation read {v(same)}, not UNRESOLVED")

    # 7. is_target: src/ is out of scope and the exclusion is deliberate, so
    #    it is asserted rather than left to the caller to rediscover.
    for rel, want in (("tests/a.rs", True), ("benches/b.rs", True),
                      ("crates/k/tests/c.rs", True), ("crates/k/benches/d.rs", True),
                      ("src/lib.rs", False), ("crates/k/src/m.rs", False),
                      ("scripts/x.rs", False)):
        if is_target(rel) is not want:
            fails.append(f"is_target({rel!r}) should be {want}")

    # 8. The FLOORS — the arithmetic the classifier's own arms cannot reach.
    #    Both directions on both floors, because a floor that only ever passes
    #    is indistinguishable from no floor, and the failure mode this guards
    #    is an instrument printing a confident PERFECT score over nothing.
    if floor_verdict(MIN_RS_FILES, MIN_TIMED)[0] != 0:
        fails.append("floors must PASS exactly at their boundary")
    if floor_verdict(MIN_RS_FILES - 1, MIN_TIMED)[0] != 2:
        fails.append("a walk one file below floor must exit 2")
    if floor_verdict(MIN_RS_FILES, MIN_TIMED - 1)[0] != 2:
        fails.append("a predicate one target below floor must exit 2")
    if floor_verdict(0, 0)[0] != 2:
        fails.append("a wholly blind run must exit 2")
    #    ...and they must be DISTINGUISHABLE. Pooling them into one message is
    #    how a walk regression gets diagnosed as a broken regex.
    walk_msg = floor_verdict(0, MIN_TIMED)[1] or ""
    pred_msg = floor_verdict(MIN_RS_FILES, 0)[1] or ""
    if "WALK" not in walk_msg or "PREDICATE" not in pred_msg:
        fails.append("the two floors must report distinguishable causes")
    #    The floors must be non-trivial: a floor of 0 can never fire.
    if MIN_RS_FILES <= 0 or MIN_TIMED <= 0:
        fails.append("a floor of 0 is not a floor")

    return fails


def main(argv) -> int:
    fails = selftest()
    if fails:
        print("⛔ sequential-ab-timing audit SELFTEST FAILED — classifier cannot be read:")
        for f in fails:
            print(f"    {f}")
        return 2

    args = [a for a in argv[1:] if not a.startswith("-")]
    repos = args or ["."]

    grand = {"ADOPTED": 0, "SEQUENTIAL": 0, "UNRESOLVED": 0}
    tot_files = tot_targets = 0
    verbose = "-v" in argv or "--verbose" in argv

    for repo in repos:
        r = scan(repo)
        tot_files += r["rs_files"]
        tot_targets += r["targets"]
        for k in grand:
            grand[k] += len(r["rows"][k])
        print(f"\n── {r['repo']} ── {r['targets']} target file(s) of "
              f"{r['rs_files']} tracked *.rs, {r['timed']} of them TIMED")
        print(f"     ADOPTED {len(r['rows']['ADOPTED']):>4}   "
              f"SEQUENTIAL {len(r['rows']['SEQUENTIAL']):>4}   "
              f"UNRESOLVED {len(r['rows']['UNRESOLVED']):>4}")
        for rel, n, hits in sorted(r["rows"]["SEQUENTIAL"]):
            ex = ", ".join(sorted(set(hits))[:2])
            print(f"       SEQUENTIAL  {rel}  (Instant::now x{n})  {ex}")
        if verbose:
            for rel, n, _ in sorted(r["rows"]["UNRESOLVED"]):
                print(f"       UNRESOLVED  {rel}  (Instant::now x{n})")
            for rel, n, _ in sorted(r["rows"]["ADOPTED"]):
                print(f"       ADOPTED     {rel}  (Instant::now x{n})")

    print("\n" + "─" * 72)
    print(f"  ADOPTED    {grand['ADOPTED']:>5}   uses tests/common/ab_timing.rs")
    print(f"  SEQUENTIAL {grand['SEQUENTIAL']:>5}   <- the class (Issue 833)")
    print(f"  UNRESOLVED {grand['UNRESOLVED']:>5}   <- NOT clean; needs a per-target read")
    print(f"  population {tot_targets:>5} target file(s) / {tot_files} tracked *.rs")

    # Floors AFTER the report, so a blind run still prints what it did see.
    code, msg = floor_verdict(tot_files, sum(grand.values()))
    if code:
        print("\n" + msg)
        return code

    print("\n  ⚠ UNRESOLVED is not 'clean' — a two-arm comparison the regex cannot\n"
          "    see lands there, and so does an ordinary single-arm latency bar\n"
          "    that is not this class at all. Never fold it into either neighbour.\n"
          "  ⚠ STATED blind spots: a ratio built through a helper; a comparison\n"
          "    written as a subtraction or a percentage; two arms differenced off\n"
          "    ONE Instant::now(); and arm ORIENTATION, which is not statically\n"
          "    decidable and is the part that actually costs time to migrate.\n"
          "  Report only; exit 0. Migration is a per-target read — Issue 833 T4.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
