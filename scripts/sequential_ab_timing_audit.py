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

# ── provenance, because `_T` above is a NAME and the class is a VALUE ───────
# `RATIO` decides a side is timing-derived from what it is CALLED. A two-arm
# ratio whose locals are `a`/`b`, `t_3d`/`t_2d` or `overhead_ns`/`baseline`
# matches neither side's token list and lands in UNRESOLVED. Measured on this
# repo (Issue 833 T3): **8 such targets, 8 of 8 true positives on a per-site
# read**, every one feeding a bar or an assert. So provenance is a second
# resolver, not a replacement — `RATIO` still decides the easy majority.
LET_BIND = re.compile(r"\blet\s+(?:mut\s+)?([A-Za-z_]\w*)\s*(?::[^=;]+)?=\s*([^;]*);")
ELAPSED = re.compile(r"\.elapsed\s*\(\s*\)")
IDENT = re.compile(r"\b[A-Za-z_]\w*\b")
# A bare `A / B` between two identifiers — names deliberately unconstrained,
# because the whole point is that the names are what `RATIO` could not read.
ANY_RATIO = re.compile(r"\b([A-Za-z_]\w*)\s*/\s*([A-Za-z_]\w*)\b")
# `(A - B) / C` — a RELATIVE DIFFERENCE, which is algebraically `A/C - B/C` and
# is the same two-arm comparison wearing a percentage. AGENTS.md lists "written
# as a subtraction or a percentage" as a STATED blind spot; this closes the half
# that is then divided. Measured (Issue 833 T3): 10 targets in the 2+-timer
# residue, and two of them are GOAT bars — `pipeline_pruner_goat` asserts
# `latency_improvement >= 0.20` and `static_cal_goat` `>= 0.05`, the second a
# bar TIGHTER than the ±21.7% drift Issue 723 T5 measured for this very class.
REL_DIFF = re.compile(
    r"\(\s*([A-Za-z_]\w*)\s*-\s*([A-Za-z_]\w*)\s*\)\s*/\s*([A-Za-z_]\w*)"
)

# ── the treatment is a SHAPE, and `ADOPTED_RE` matches a NAME ───────────────
# `tests/common/ab_timing.rs` is one spelling of interleaved paired arms +
# a per-pair ratio + a median across pairs. A target that hand-rolls the
# identical thing matches neither literal and is then reported as needing the
# migration it already has — the cries-wolf direction, and it is POPULATED:
# `bench_657_clustered_lm_head_bound.rs` read SEQUENTIAL ("the class") while
# its own doc block describes alternating A→B / B→A ordering and a median of
# per-pair ratios, i.e. a STRICTER treatment than the shared harness.
PUSH_RATIO = re.compile(r"\.push\s*\(\s*[A-Za-z_]\w*\s*/\s*[A-Za-z_]\w*\s*\)")
REDUCE = re.compile(r"\bmedian\w*\b|\bpercentile\b|\bsort_by\b|\bsort_unstable\b")


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


def timing_locals(masked: str) -> set:
    """Identifiers bound, directly or transitively, from an `.elapsed()` value.

    The transitive hop is what reaches the ordinary shape — `let d = t.elapsed();
    let a_ns = d.as_nanos() as f64 / ITERS as f64;` — where only the FIRST
    binding mentions `elapsed` and the one that gets compared is two hops away.
    Bounded at three rounds: it is a fixpoint over straight-line `let`s, not a
    dataflow analysis, and an unbounded loop here would be a hang in a report.
    """
    names, pending = set(), []
    for m in LET_BIND.finditer(masked):
        lhs, rhs = m.group(1), m.group(2)
        if ELAPSED.search(rhs):
            names.add(lhs)
        else:
            pending.append((lhs, set(IDENT.findall(rhs))))
    for _ in range(3):
        grew = False
        for lhs, rhs_idents in pending:
            if lhs not in names and rhs_idents & names:
                names.add(lhs)
                grew = True
        if not grew:
            break
    return names


def provenance_hits(masked: str, already: list) -> list:
    """Two-arm comparisons `ratio_hits` could not see, found by VALUE not name.

    Two expression shapes, ONE `timing_locals` pass — they are the same
    resolver, and computing provenance twice is the expensive half:

      * `A / B`        — a ratio whose locals spell none of `_T`'s tokens.
      * `(A - B) / C`  — a RELATIVE DIFFERENCE, the same comparison wearing a
        percentage, which `ANY_RATIO` misses only because the numerator is
        parenthesised rather than an identifier.

    `already` is the name-matched set, so a site is reported once and the two
    resolvers stay separable — the counts must not double-count a comparison
    both can see. `COUNTY` still applies to every operand: a timing local over
    a count is a rate whichever resolver found it and whichever shape it wore.
    """
    names = timing_locals(masked)
    if len(names) < 2:
        return []
    seen, hits = set(already), []

    def admit(text: str, operands: tuple) -> None:
        if text in seen:
            return
        if any(o not in names for o in operands):
            return
        if any(COUNTY.search(o) for o in operands):
            return
        seen.add(text)
        hits.append(text)

    for m in REL_DIFF.finditer(masked):
        a, b, c = m.group(1), m.group(2), m.group(3)
        if a == b:
            continue  # (x - x) is zero, not a comparison
        admit(m.group(0), (a, b, c))
    for m in ANY_RATIO.finditer(masked):
        a, b = m.group(1), m.group(2)
        if a == b:
            continue  # x/x is a normalisation, not a comparison
        admit(m.group(0), (a, b))
    return hits


def hand_rolled(masked: str) -> bool:
    """Does this target already implement the treatment under another name?

    Interleaved pairs (a per-pair ratio pushed into a sample) plus a reduction
    across those pairs. Both halves are required: a `.push(a / b)` with no
    reduction is a log, and a median with no per-pair ratio is the
    median-of-A-over-median-of-B shape that IS the defect.
    """
    return bool(PUSH_RATIO.search(masked)) and bool(REDUCE.search(masked))


HARNESS = "common/ab_timing.rs"


def classify(text: str, rel: str = "") -> tuple:
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
    # The harness is not an adopter of itself. `ADOPTED_RE` matches the module
    # by NAME, and the module's own path contains that name, so `ab_timing.rs`
    # certified itself and inflated the one figure this section is quoted for.
    # Its own verdict rather than an exclusion: dropping it from the walk would
    # make a `tests/common/` helper carrying a real ratio invisible, and that
    # is the silent direction. Measured: without the short-circuit the harness
    # is UNRESOLVED, so nothing was being masked — the defect is the COUNT.
    if rel.endswith(HARNESS):
        return ("HARNESS", n, [])
    # ADOPTED is read off the UNMASKED text on purpose: `#[path = "..."]` puts
    # the module path inside a string literal, which masking blanks.
    if ADOPTED_RE.search(text):
        return ("ADOPTED", n, [])
    if n < 2:
        # One timer cannot bracket two arms separately in the ordinary shape.
        # Not proven — see the STATED blind spot about differencing one timer
        # twice — so it is UNRESOLVED, never "clean".
        return ("UNRESOLVED", n, [])
    # HAND-ROLLED is tested BEFORE the ratio, for arm 2's reason one step over:
    # a target that already carries the treatment must not be reported as
    # needing it, or the report reds work somebody already did. It is its own
    # verdict and is never folded into ADOPTED — that one means "uses the
    # shared harness", this one means "duplicates it", and the responses
    # differ (migrate vs leave alone / DRY onto the shared module).
    if hand_rolled(masked):
        return ("HAND-ROLLED", n, [])
    hits = ratio_hits(masked)
    hits = hits + provenance_hits(masked, hits)
    return (("SEQUENTIAL" if hits else "UNRESOLVED"), n, hits)


def scan(repo: str) -> dict:
    """Classify every timed target in `repo`. Returns a result dict."""
    files, excluded = tracked_files(repo, "*.rs")
    root = Path(repo).resolve()
    rows = {"HARNESS": [], "ADOPTED": [], "HAND-ROLLED": [], "SEQUENTIAL": [], "UNRESOLVED": []}
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
        verdict, n, hits = classify(text, rel)
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

    # 6b. PROVENANCE (Issue 833 T3). `_T` reads a NAME; these locals are
    #     timing-derived by VALUE and spell none of its tokens. Without this
    #     the shape below — the reduced form of 8 measured true positives —
    #     reads UNRESOLVED.
    prov = """
    fn g() {
        let t0 = Instant::now(); work(); let d0 = t0.elapsed();
        let a = d0.as_nanos() as f64;
        let t1 = Instant::now(); other(); let d1 = t1.elapsed();
        let b = d1.as_nanos() as f64;
        assert!(a / b <= 1.15);
    }"""
    if v(prov) != "SEQUENTIAL":
        fails.append(f"a provenance-bound two-arm ratio read {v(prov)}, not SEQUENTIAL")
    #     ...and it must NOT invent one. A count denominator stays a RATE even
    #     when the numerator's provenance is impeccable — otherwise provenance
    #     converts every single-arm bar in the repo into the class.
    prov_rate = """
    fn g() {
        let t0 = Instant::now(); work(); let d0 = t0.elapsed();
        let a = d0.as_nanos() as f64;
        let t1 = Instant::now(); let _d1 = t1.elapsed();
        let n_tokens = a;
        let per = a / n_tokens;
    }"""
    if v(prov_rate) != "UNRESOLVED":
        fails.append(f"a provenance-bound time/COUNT rate read {v(prov_rate)}, not UNRESOLVED")
    #     The transitive hop is the part that reaches the ordinary shape, so it
    #     is asserted directly rather than only through a verdict.
    hop = timing_locals("let d = t.elapsed(); let a_ns = d.as_nanos(); let z = a_ns * 2;")
    for want in ("d", "a_ns", "z"):
        if want not in hop:
            fails.append(f"timing_locals missed the transitive binding {want!r}")
    if "q" in timing_locals("let d = t.elapsed(); let q = unrelated * 2;"):
        fails.append("timing_locals bound an identifier with no timing provenance")
    #     Ratios both resolvers can see must be reported ONCE — two resolvers
    #     over one site is a double count, and the hits feed the display.
    dbl = ("fn g() { let t = Instant::now(); let a_ns = t.elapsed().as_nanos();\n"
           "  let t = Instant::now(); let b_ns = t.elapsed().as_nanos();\n"
           "  let r = a_ns / b_ns; }")
    masked_dbl, _ = mask_file(dbl)
    h = ratio_hits(masked_dbl)
    if len(h + provenance_hits(masked_dbl, h)) != 1:
        fails.append("a ratio both resolvers can see must be counted once")

    # 6b-ii. RELATIVE DIFFERENCE (Issue 833 T3). `(a - b) / b` is `a/b - 1` —
    #     the same two-arm comparison wearing a percentage, and AGENTS.md lists
    #     it as a STATED blind spot. Two measured GOAT bars were behind it.
    reldiff = """
    fn g() {
        let t0 = Instant::now(); base(); let d0 = t0.elapsed();
        let base_total = d0.as_nanos() as f64;
        let t1 = Instant::now(); feat(); let d1 = t1.elapsed();
        let feat_total = d1.as_nanos() as f64;
        let improvement = (base_total - feat_total) / base_total;
        assert!(improvement >= 0.20);
    }"""
    if v(reldiff) != "SEQUENTIAL":
        fails.append(f"a relative-difference bar read {v(reldiff)}, not SEQUENTIAL")
    #     `(x - x) / x` is zero, not a comparison — the sibling of the x/x rule,
    #     and without it any self-difference reads as the class.
    if v(reldiff.replace("(base_total - feat_total)", "(base_total - base_total)")) != "UNRESOLVED":
        fails.append("(x - x) / x must not read SEQUENTIAL")
    #     ...and COUNTY must reach the DENOMINATOR of the difference form too,
    #     or `(a - b) / n_tokens` — a per-token delta, which is a rate — becomes
    #     the class. This is the arm that keeps the widening honest.
    if v(reldiff.replace("/ base_total;", "/ n_tokens;")) != "UNRESOLVED":
        fails.append("a relative difference over a COUNT must stay UNRESOLVED")

    # 6c. HAND-ROLLED (Issue 833 T3). The treatment is a SHAPE and `ADOPTED_RE`
    #     matches a NAME, so a target that hand-rolls interleaved pairs reads
    #     SEQUENTIAL — "needs migrating" — while already carrying it. Measured
    #     specimen: bench_657_clustered_lm_head_bound.rs.
    rolled = """
    fn g() {
        let mut ratios = vec![];
        for _ in 0..REPS {
            let t0 = Instant::now(); a(); let a_us = t0.elapsed().as_micros() as f64;
            let t1 = Instant::now(); b(); let b_us = t1.elapsed().as_micros() as f64;
            ratios.push(a_us / b_us);
        }
        ratios.sort_by(|x, y| x.total_cmp(y));
        assert!(median(&mut ratios) <= 1.15);
    }"""
    if v(rolled) != "HAND-ROLLED":
        fails.append(f"hand-rolled interleaved pairs read {v(rolled)}, not HAND-ROLLED")
    #     BOTH halves are required, and each negative is a real shape: a push
    #     with no reduction is a log, and a reduction with no per-pair ratio is
    #     median-of-A-over-median-of-B, which IS the defect this class is about.
    if v(rolled.replace("ratios.sort_by(|x, y| x.total_cmp(y));", "")
             .replace("median(&mut ratios)", "ratios[0]")) == "HAND-ROLLED":
        fails.append("a per-pair ratio with no reduction must not read HAND-ROLLED")
    if v(seq + "\nfn h() { let m = median(&mut xs); }") == "HAND-ROLLED":
        fails.append("a reduction with no per-pair ratio must not read HAND-ROLLED")
    #     ...and ADOPTED must still outrank it, so a migrated target that kept
    #     its old loop is not demoted to 'duplicates the harness'.
    if v('#[path = "common/ab_timing.rs"]\nmod ab_timing;\n' + rolled) != "ADOPTED":
        fails.append("ADOPTED must outrank HAND-ROLLED")

    # 6d. HARNESS. `ADOPTED_RE` matches the module by NAME and the module's own
    #     path contains that name, so the harness certified itself and inflated
    #     the one figure this instrument is quoted for. Its own verdict rather
    #     than an exclusion — dropping `tests/common/` from the walk would make
    #     a helper module carrying a real ratio invisible, the silent direction.
    if classify(seq, "tests/common/ab_timing.rs")[0] != "HARNESS":
        fails.append("the harness module must not be counted as its own adopter")
    #     ...and it must not swallow the adopters, which live one directory up
    #     and reference the same string.
    adopter = '#[path = "common/ab_timing.rs"]\nmod ab_timing;\n' + seq
    if classify(adopter, "tests/bench_x.rs")[0] != "ADOPTED":
        fails.append("a target referencing the harness must still read ADOPTED")
    #     The default argument keeps every other arm honest: with `rel` unset
    #     nothing may be reclassified, or the arms above would be asserting a
    #     different function from the one `scan` calls.
    if classify(seq)[0] != "SEQUENTIAL":
        fails.append("classify() without a path must be unchanged")

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

    grand = {"HARNESS": 0, "ADOPTED": 0, "HAND-ROLLED": 0, "SEQUENTIAL": 0, "UNRESOLVED": 0}
    tot_files = tot_targets = 0
    # The UNRESOLVED bucket has two sub-populations with opposite priors, and
    # pooling them is the bucket note's own hazard one level down. A TRIAGE
    # AID, never a verdict — the percentile audit's `tail support` standing:
    # it ORDERS the rows so the read starts where it can change an answer.
    single = multi = 0
    verbose = "-v" in argv or "--verbose" in argv

    for repo in repos:
        r = scan(repo)
        tot_files += r["rs_files"]
        tot_targets += r["targets"]
        for k in grand:
            grand[k] += len(r["rows"][k])
        single += sum(1 for _, n, _ in r["rows"]["UNRESOLVED"] if n < 2)
        multi += sum(1 for _, n, _ in r["rows"]["UNRESOLVED"] if n >= 2)
        print(f"\n── {r['repo']} ── {r['targets']} target file(s) of "
              f"{r['rs_files']} tracked *.rs, {r['timed']} of them TIMED")
        print(f"     ADOPTED {len(r['rows']['ADOPTED']):>4}   "
              f"HAND-ROLLED {len(r['rows']['HAND-ROLLED']):>4}   "
              f"SEQUENTIAL {len(r['rows']['SEQUENTIAL']):>4}   "
              f"UNRESOLVED {len(r['rows']['UNRESOLVED']):>4}")
        for rel, n, hits in sorted(r["rows"]["SEQUENTIAL"]):
            ex = ", ".join(sorted(set(hits))[:2])
            print(f"       SEQUENTIAL  {rel}  (Instant::now x{n})  {ex}")
        for rel, n, _ in sorted(r["rows"]["HAND-ROLLED"]):
            print(f"       HAND-ROLLED {rel}  (Instant::now x{n})")
        if verbose:
            for rel, n, _ in sorted(r["rows"]["UNRESOLVED"]):
                tag = "1-timer " if n < 2 else "2+-timer"
                print(f"       UNRESOLVED  [{tag}] {rel}  (Instant::now x{n})")
            for rel, n, _ in sorted(r["rows"]["ADOPTED"]):
                print(f"       ADOPTED     {rel}  (Instant::now x{n})")

    print("\n" + "─" * 72)
    print(f"  HARNESS     {grand['HARNESS']:>5}   IS tests/common/ab_timing.rs — not an adopter of itself")
    print(f"  ADOPTED     {grand['ADOPTED']:>5}   uses tests/common/ab_timing.rs")
    print(f"  HAND-ROLLED {grand['HAND-ROLLED']:>5}   carries the treatment under another name")
    print(f"  SEQUENTIAL  {grand['SEQUENTIAL']:>5}   <- the class (Issue 833)")
    print(f"  UNRESOLVED  {grand['UNRESOLVED']:>5}   <- NOT clean; needs a per-target read")
    print(f"                    {single:>5} carry ONE timer  — mostly ordinary single-arm bars")
    print(f"                    {multi:>5} carry TWO+       — where the STATED blind spots live")
    print(f"  population  {tot_targets:>5} target file(s) / {tot_files} tracked *.rs")

    # Floors AFTER the report, so a blind run still prints what it did see.
    code, msg = floor_verdict(tot_files, sum(grand.values()))
    if code:
        print("\n" + msg)
        return code

    print("\n  ⚠ UNRESOLVED is not 'clean' — a two-arm comparison the regex cannot\n"
          "    see lands there, and so does an ordinary single-arm latency bar\n"
          "    that is not this class at all. Never fold it into either neighbour.\n"
          "  ⚠ HAND-ROLLED is never folded into ADOPTED: that one means 'uses the\n"
          "    shared harness', this one means 'duplicates it'. Both are TREATED —\n"
          "    neither is a migration candidate — but only the second is a DRY\n"
          "    finding, and pooling them would report the treatment as universal.\n"
          "  ⚠ STATED blind spots, NARROWED by Issue 833 T3: a ratio built through\n"
          "    a helper; a comparison written as a subtraction or a percentage and\n"
          "    never divided; two arms differenced off ONE Instant::now(); and arm\n"
          "    ORIENTATION, which is not statically decidable and is the part that\n"
          "    actually costs time to migrate. What T3 CLOSED is the fifth: a ratio\n"
          "    whose locals are timing-derived by VALUE but not by NAME, which\n"
          "    `provenance_hits` now resolves (8 found here, 8 of 8 true on a read).\n"
          "  Report only; exit 0. Migration is a per-target read — Issue 833 T4.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
