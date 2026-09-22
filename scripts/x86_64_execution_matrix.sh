#!/usr/bin/env bash
# x86_64 execution matrix — Issue 806.
#
# ⛔ THE AXIS THIS CLOSES. AGENTS.md's table ends with `compile vs EXECUTE`,
# and one platform over that row reads: `full_gate` is macOS/aarch64 AND is
# compile+lint rather than execute; `wasm32_gate` builds a third triple;
# `test_gate` is the only executing lane, is scoped to four `--lib` suites,
# and its schedule is suspended. So every `#[cfg(target_arch = "x86_64")]` arm
# in this repo was, until 2026-09-16, executed by NOTHING — and the first two
# cells that were ever run caught **15** latent AVX2-transcription defects
# (Bench 800 addendum), the next seven caught **two** more plus a router
# defect red on every non-macOS platform (Bench 806). An uninvoked assertion
# is *unknown*, not passing.
#
# `scripts/suite_membership_audit.py` prints the same hole from the other
# side: katgpt-rs is `[NO broad run]` — 723 unpinned integration targets that
# no script and no workflow names. This is that broad run, on the one x86_64
# box, and it is a SCRIPT because "a census done by hand is a census that
# stops being done".
#
#   scripts/x86_64_execution_matrix.sh              # the matrix
#   scripts/x86_64_execution_matrix.sh --libs-only  # skip the root integration cell
#   scripts/x86_64_execution_matrix.sh --canary     # prove the floors fire
#   X86_MATRIX_DIR=/f/scratch scripts/…             # where to extract (default: mktemp)
#
# ⚠ NOT a CI lane and none is requested — the Actions spending call stands
# (AGENTS.md "Trigger health"). Workstation verdict, the standing of the
# drift sweeps.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$HERE")"
# ⛔ The pins are read from the SCRATCH tree, not from `$HERE` — set below,
# once the archive exists. The source comes from `git archive HEAD`, so a pin
# file read from the live worktree can describe a DIFFERENT commit: measured,
# on run 5 of this instrument, where a rebase landed between the extraction and
# the adjudication and two rows read UNPINNED that the archived tree still
# legitimately fails. Issue 797's rule, one level over — the display and the
# pins must read the same snapshot.
FLOORS=""

LIBS_ONLY=0
CANARY=0
for arg in "$@"; do
    case "$arg" in
        --libs-only) LIBS_ONLY=1 ;;
        --canary)    CANARY=1 ;;
        *) echo "unknown argument: $arg" >&2; exit 2 ;;
    esac
done

# ── Completion sentinel (Issue 734) ─────────────────────────────────────────
# On macOS /bin/bash 3.2.57 an abort on an unbound expansion or an `eval`
# syntax error enters the EXIT trap with `$?` ALREADY 0, so a trap whose last
# command succeeds turns the abort into exit 0. "Did the script reach its own
# last line?" is the only thing that catches that — and it catches every other
# premature death (SIGTERM, a `set -e` trip, an editing slip) on EVERY shell,
# which is why it stays on a box where 3.2 is out of the picture.
MATRIX_COMPLETED=0
SCRATCH=""
KEEP_SCRATCH="${X86_MATRIX_DIR:-}"
matrix_cleanup() {
    st=$?
    if [ -n "$SCRATCH" ] && [ -z "$KEEP_SCRATCH" ]; then
        rm -rf "$SCRATCH"
    fi
    if [ "$MATRIX_COMPLETED" != "1" ] && [ "$st" = "0" ]; then
        echo "✗ x86_64 matrix ABORTED mid-run while reporting success — it did not" >&2
        echo "  reach its own last line, so it verified NOTHING past the error above." >&2
        exit 1
    fi
    exit "$st"
}
trap matrix_cleanup EXIT

# ── The PLATFORM is part of the claim ───────────────────────────────────────
# Exactly as full_gate.sh refuses to report a pass off macOS: on aarch64 every
# arm this script exists for compiles to NOTHING, and a green run would be a
# green ZERO wearing a matrix.
ARCH="$(uname -m 2>/dev/null || echo unknown)"
case "$ARCH" in
    x86_64|amd64) ;;
    *)
        echo "⛔ host arch is '$ARCH', not x86_64 — every arm this matrix exists"
        echo "   for compiles to nothing here. REFUSING rather than reporting a"
        echo "   green zero. Run it on an x86_64 box."
        exit 1
        ;;
esac
command -v cargo >/dev/null 2>&1 || { echo "✗ cargo not installed"; exit 1; }

# ── BOX STATE — a latency bar without it is not a measurement ──────────────
# AGENTS.md §Feature Flag Discipline already rules that "a latency gate on a
# thrashing box measures the pagefile". EVERY PASSED-ALONE row this script
# prints is a latency-bar outcome, and until 2026-09-18 they were logged with
# no box state at all — so two runs were not comparable even in principle, and
# a series of them could not be pooled into a rate no matter how many were run.
# Measured occasion: runs 1 and 2 (2026-09-18) each fired a DIFFERENT member of
# the Issue-833 class and run 3 fired none, and nothing in the three logs can
# separate "quieter box" from "population minus its two most fragile members".
#
# DISCLOSURE ONLY — nothing here changes a verdict, a floor or a pin.
# Never fails the run. Every capture is `|| true`-guarded and emptiness-checked:
# under `set -euo pipefail` a `var="$(pipeline)"` that dies takes the script with
# it AFTER the measured work and BEFORE the verdict, which is the exact class
# AGENTS.md documents at length.
#
# ⛔ Selection is on whether a method ANSWERS, never on whether its source
# exists. MSYS ships a readable `/proc/meminfo` carrying no MemAvailable,
# CommitLimit or Committed_AS, so `[ -r /proc/meminfo ]` picks a branch that
# cannot answer on the one box this instrument exists for — and the result
# degrades to "unavailable", which reads as an honest degradation rather than a
# bug. Measured here, by the arm below, which previously asserted only the
# output SHAPE and so passed while the memory half was dead.
box_state() {
    state_mem=""
    state_src=""

    if [ -r /proc/meminfo ]; then
        state_mem="$(awk '
            /^MemAvailable:/ { a = $2 }
            /^CommitLimit:/  { c = $2 }
            /^Committed_AS:/ { u = $2 }
            END {
                if (a != "" && c != "")
                    printf "avail %.1f GiB · commit %.1f/%.1f GiB", \
                           a / 1048576, u / 1048576, c / 1048576
            }' /proc/meminfo 2>/dev/null || true)"
        [ -n "$state_mem" ] && state_src="/proc/meminfo"
    fi

    if [ -z "$state_mem" ] && command -v powershell.exe >/dev/null 2>&1; then
        state_mem="$(powershell.exe -NoProfile -NonInteractive -Command \
            '$m = Get-CimInstance Win32_PerfRawData_PerfOS_Memory; $o = Get-CimInstance Win32_OperatingSystem; "avail {0:N1} GiB, commit {1:N1}/{2:N1} GiB" -f ($o.FreePhysicalMemory/1MB), ($m.CommittedBytes/1GB), ($m.CommitLimit/1GB)' \
            2>/dev/null | tr -d '\r' || true)"
        [ -n "$state_mem" ] && state_src="Win32_PerfRawData"
    fi

    if [ -z "$state_mem" ]; then
        state_mem="UNAVAILABLE"
        state_src="no method answered"
    fi

    printf '%s [%s]' "$state_mem" "$state_src"
}

# ── The scratch tree ────────────────────────────────────────────────────────
# `git archive HEAD`, never the checkout: Issue 797's rule one axis over — an
# instrument that reads the WORKTREE measures lines no commit contains, and
# this box runs five-plus concurrent sessions against shared worktrees.
SHA="$(git -C "$REPO" rev-parse HEAD)"
if [ -n "$KEEP_SCRATCH" ]; then
    SCRATCH="$KEEP_SCRATCH"
    mkdir -p "$SCRATCH"
else
    SCRATCH="$(mktemp -d)"
fi

BOX_START="$(box_state)"
echo "▸ extracting $SHA → $SCRATCH"
git -C "$REPO" archive HEAD | tar -x -C "$SCRATCH"
FLOORS="$SCRATCH/scripts/x86_64_matrix_floors.txt"
EXPECTED="$SCRATCH/scripts/x86_64_matrix_expected.txt"

# ⛔ MANDATORY, not a tuning knob: an arm gated
# `cfg(all(target_arch = "x86_64", target_feature = "avx2"))` compiles to
# NOTHING under a plain x86_64 `cargo test`, which then exercises the scalar
# fallback and proves nothing about the kernel. katgpt-attn's channel_aware.rs
# carries exactly that shape.
export RUSTFLAGS="-C target-feature=+avx2"

# -j 6, not -j $(nproc): this box has a measured STATUS_ACCESS_VIOLATION
# history for rustc at the default parallelism. A scheduling bound, not a
# verdict about any crate.
JOBS="${X86_MATRIX_JOBS:-6}"

# ⚠ A load-robustness cap, and the FIRST version of this comment named the
# wrong cause — the refutation is the part worth keeping.
#
# `highs-sys` builds HiGHS through cmake + MSVC. Twice, cell 6
# (katgpt-tokenizer) died with `C1001 Internal compiler error` in <vector> plus
# `cl D8040 "error creating or communicating with child process"`. D8040 is
# cl.exe failing to SPAWN its own child — resource exhaustion — and the C1001
# is collateral; nothing in katgpt-tokenizer is involved. The matrix reports it
# as `died without a failures block — nothing asserted`, the correct refusal,
# and also a RED CELL over a toolchain flake in the only lane on this box that
# EXECUTES anything.
#
# The obvious hypothesis was cmake`s own `--parallel`, derived from the CPU
# count. MEASURED, and it is WRONG (2026-09-18, highs-sys build dir deleted
# between runs so each rebuilds):
#
#   cmake 6 x cargo 6, quiet box   -> 74 passed, 13.8s
#   cmake 2 x cargo 2, quiet box   -> 74 passed, 13.9s
#   cmake 1 x cargo 2, quiet box   -> 74 passed, 15.6s
#
# Both failures happened while ANOTHER heavy cargo build ran concurrently in a
# different target dir; every quiet-box run passes at every parallelism, and
# the three timings are indistinguishable. So the trigger is WHOLE-BOX
# concurrent compiler load, and the cap does not address it — it only shrinks
# this lane`s own contribution to the peak.
#
# Kept anyway, on the measurement: it costs nothing detectable here, and a
# smaller peak is the one part of the load this lane controls. ⛔ It is NOT a
# fix — the remedy is to run the matrix ALONE. That is also the causal claim
# this comment can actually support: two failures under concurrent load, three
# passes without it, and no experiment isolating load itself.
#
# Capped rather than retried: a retry loop would hide a genuine build break.
# Overridable, because a Linux box has no reason to pay for it.
#
# ⚠ Two MORE failures, 2026-09-18, and they do NOT fit the load story above:
# runs 5 and 6 (`--libs-only`, fresh scratch each) both died in the highs-sys
# build WITH this cap already at 1 and with no concurrent cargo — after four
# consecutive passes the same evening. Different symptoms and different cells:
#   run 5, cell 6: `cl : command line error D8040` (child-process spawn)
#   run 6, cell 5: `fatal error C1001: Internal compiler error`
# Cell-instability is what rules out a code cause; what it does NOT do is
# confirm "concurrent load", because there was none to speak of. So the honest
# standing is 4 passes / 2 failures on one box in one evening with the cap
# fixed, mechanism UNKNOWN, and the comment above should be read as one
# hypothesis rather than the finding. Do not tune this number on that evidence.
if [ -z "${CMAKE_BUILD_PARALLEL_LEVEL:-}" ]; then
    case "$(uname -s)" in
        MINGW* | MSYS* | CYGWIN*) export CMAKE_BUILD_PARALLEL_LEVEL=1 ;;
    esac
fi

# ── The POPULATION is DERIVED ───────────────────────────────────────────────
# Every package owning a tracked *.rs that mentions `target_arch = "x86_64"`.
# A new x86_64-bearing crate joins by EXISTING, which is the whole reason not
# to hand-type the list — Issue 806's own cell list named three packages and
# the tracked tree has six.
#
# ⚠ Deliberately a plain grep, NOT the literal-masking Rust lexer that
# wasm32_surface_audit.py imports. That instrument's verdict is UNCOVERED — a
# FINDING — so a `#[cfg(...)]` inside a test fixture's `r#"…"#` invents one.
# This one's output is "which crates to test", where over-inclusion costs a few
# seconds of cargo and under-inclusion is the only real failure mode. A plain
# grep over-reports. The asymmetry is the argument, and it is why importing the
# lexer here would be cargo-culting a rule past the case it was measured on.
pkgs_from_sources() {
    git -C "$REPO" grep -l -E 'target_arch[[:space:]]*=[[:space:]]*"x86_64"' \
        -- '*.rs' 2>/dev/null \
    | while read -r rel; do
        d="$(dirname "$REPO/$rel")"
        while [ "$d" != "/" ] && [ "$d" != "$(dirname "$REPO")" ]; do
            if [ -f "$d/Cargo.toml" ] && grep -q '^\[package\]' "$d/Cargo.toml"; then
                sed -n '/^\[package\]/,/^\[/p' "$d/Cargo.toml" \
                    | sed -n 's/^name[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' \
                    | head -1
                break
            fi
            d="$(dirname "$d")"
        done
    done | sort -u
}

# The ROOT package is in the matrix whether or not it greps: its `--lib` is
# where the inference router lives, and that is where Issue 806's cell 3 found
# a defect that had nothing to do with SIMD.
ROOT_PKG="$(sed -n '/^\[package\]/,/^\[/p' "$REPO/Cargo.toml" \
            | sed -n 's/^name[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)"

# ── …UNION the pinned rows ──────────────────────────────────────────────────
# A package can reach these kernels through a DEPENDENCY and own no x86_64
# source of its own — katgpt-dec is the measured case, and Issue 806 named it
# as a cell while the source grep does not. The wasm32 audit calls that bucket
# BY-DEP and refuses to fold it into the derived one; the same distinction
# applies here, so it is ADDED by a pinned row with its reason in the floors
# file rather than by widening the grep until it happens to catch it.
pkgs_from_floors() {
    [ -f "$FLOORS" ] || return 0
    sed 's/#.*//' "$FLOORS" | awk '$1 != "" && $1 !~ /^__/ { print $1 }'
}

PKGS="$(printf '%s\n%s\n%s\n' "$(pkgs_from_sources)" "$(pkgs_from_floors)" \
        "$ROOT_PKG" | sed '/^$/d' | sort -u)"

N_PKGS="$(printf '%s\n' "$PKGS" | sed '/^$/d' | wc -l | tr -d ' ')"
# A FLOOR: a grep regression that derives 0 packages must RED, not print a
# confident green over an empty matrix. Same shape as every sweep's
# min_scripts — the ceiling is green over whatever the instrument can SEE.
POP_FLOOR=5
if [ "$N_PKGS" -lt "$POP_FLOOR" ]; then
    echo "✗ derived only $N_PKGS package(s), floor is $POP_FLOOR — the population"
    echo "  derivation is blind; a matrix over nothing is not a pass."
    exit 1
fi
echo "▸ population: $N_PKGS package(s) derived from the tracked tree"

floor_for() {  # $1 = row key; prints its floor, or nothing
    [ -f "$FLOORS" ] || return 0
    sed 's/#.*//' "$FLOORS" | awk -v p="$1" '$1 == p { print $2 }' | head -1
}

FAILED=0
CELL=0
TOTAL_PASSED=0
SEEN_FAILS="$SCRATCH/.failing_tests.txt"
: > "$SEEN_FAILS"

# ── Failing tests are CONFIRMED, then adjudicated by MEMBERSHIP ─────────────
# The first full run of the integration cell was 0 correctness failures and
# SIX perf-bar failures — a ≥5× gate whose own name says `SWAR+FMLA` (an
# aarch64 instruction) scoring 4.37× here, two speedup ratios computed from
# two timings that both read 0.00 µs, and a router-overhead bar measured on a
# box running four other agents' cargo. None is this matrix's to fix, and a
# gate that always reds is a gate nobody runs (AGENTS.md's cries-wolf rule).
# So they are pinned by NAME with a reason each, the wall is 0 UNPINNED, and a
# pin whose test has since started passing reds too — the file must not only
# ever loosen. A count would be green on a swap; a set is not.
#
# ⛔ AND THE SET CHURNS, which is why a membership pin alone is the wrong
# instrument here. Three runs of the same commit on this box produced three
# DIFFERENT failing sets: run 1 six, run 2 dropped two (`bench_176`, `g7`) and
# gained an unseeded-RNG flake, run 3 dropped `g5_roaring` and gained
# `t08_throughput_rebalance_256x16`. A pin file re-typed after every run is a
# diary, not a wall.
#
# So every failure is RE-RUN ALONE before it is adjudicated — this session's
# own finding, mechanised. The re-run is cheap: everything is already built and
# `--exact` makes every other binary run zero tests.
#
# ⛔ **But "passed alone" is EVIDENCE, not a CAUSE, and calling it TRANSIENT
# has now been wrong three times.** The word asserts "load-sensitive bar", and
# at least three distinct classes produce the identical observation:
#
#   1. a load-sensitive perf BAR       — Issue 831. TRANSIENT is correct here.
#   2. a shared-fixed-path CONCURRENCY — Issue 832. Passes alone BY
#      CONSTRUCTION; alone there is no second process. One was filed TRANSIENT
#      and the defect shipped.
#   3. an unseeded-RNG COIN FLIP       — `player_type_creates_instances`,
#      2026-09-18: asserted `Place` against a documented
#      `PASS_PROBABILITY = 0.02` twelve lines away. 9 failures in 400 seeds, so
#      a single clean re-run is what you EXPECT 98% of the time.
#
# Re-running N times narrows (2) not at all and (3) only weakly — a 2% flake
# survives five re-runs 90% of the time — so the repair is not more re-runs
# alone. It is to stop naming a cause the instrument cannot observe: rows print
# as PASSED-ALONE with the three classes and their disambiguating checks
# attached, so the reader adjudicates instead of inheriting a guess. The extra
# runs still buy real evidence for (3) and cost nothing, so they are kept.
#
# PASSED-ALONE rows are still never counted and never pinned: what they are NOT
# is explained.
CONFIRM_RUNS="${CONFIRM_RUNS:-3}"
PASSED_ALONE_FILE="$SCRATCH/.passed_alone"
: > "$PASSED_ALONE_FILE"

collect_fails() {  # $1 = log, $2 = the cargo args of the cell it came from
    sed -n 's/^test \(.*\) \.\.\. FAILED$/\1\t'"$2"'/p' "$1" >> "$SEEN_FAILS" || true
}

confirm_fails() {  # stdin: name<TAB>args ; stdout: names that failed AGAIN
    while IFS="$(printf '\t')" read -r name args; do
        [ -n "$name" ] || continue
        passes=0
        failed=0
        i=0
        while [ "$i" -lt "$CONFIRM_RUNS" ]; do
            i=$((i + 1))
            # shellcheck disable=SC2086 -- $args is a deliberate word list
            if (cd "$SCRATCH" && cargo test $args -j "$JOBS" -- --exact "$name") \
                    > "$SCRATCH/.confirm.log" 2>&1; then
                passes=$((passes + 1))
            else
                failed=1
                break
            fi
        done
        if [ "$failed" -eq 0 ]; then
            echo "    · PASSED-ALONE $name — failed in the cell, passed $passes/$CONFIRM_RUNS alone" >&2
            # ⛔ A FILE, not a variable: this function runs on the right-hand
            # side of a pipeline, i.e. in a subshell, so `PASSED_ALONE=$((…))`
            # here is invisible to the caller and the note below would never
            # print. Exactly the shape AGENTS.md's pipefail-discard audit is
            # about, one hazard over.
            echo x >> "$PASSED_ALONE_FILE"
        else
            echo "$name"
        fi
    done
}

# Printed once, after the confirm pass, whenever anything landed in that
# bucket — at the place a reader decides what to do about it, not in a
# docstring they will not open.
passed_alone_note() {
    [ -s "$PASSED_ALONE_FILE" ] || return 0
    cat >&2 <<'NOTE'

  ⚠ PASSED-ALONE is an OBSERVATION, not a diagnosis. Three classes produce it
    and they need opposite responses — adjudicate before dismissing:
      · load-sensitive perf BAR   → check whether the bar is ISA-calibrated for
        another arch, and what else was running. The only class the old
        "TRANSIENT" label was right about.
      · CONCURRENCY on a shared path → grep the test for a FIXED
        env::temp_dir()/"/tmp" path; it passes alone BY CONSTRUCTION, because
        alone there is no second process (scripts/shared_temp_path_gate.py).
      · unseeded-RNG COIN FLIP    → grep for fastrand::Rng::new()/default() or
        a free-function draw; re-run it across a few hundred SEEDS, not a few
        processes. A 2% flake survives three re-runs 94% of the time.
NOTE
}

run_lib_cell() {
    pkg="$1"
    floor="$2"
    CELL=$((CELL + 1))
    echo ""
    echo "=== cell $CELL: $pkg --lib --all-features (debug, +avx2, floor ${floor:-unpinned}) ==="
    log="$SCRATCH/.cell_$pkg.log"
    # debug, deliberately: `debug_assertions` is ON, which is half the reason
    # to execute at all. The GOAT/perf targets go in release below, because a
    # latency bar measured on an unoptimised binary is not a measurement —
    # both halves of AGENTS.md's profile row, in one run.
    rc=0
    (cd "$SCRATCH" && cargo test -p "$pkg" --lib --all-features -j "$JOBS") \
        > "$log" 2>&1 || rc=$?
    before="$(wc -l < "$SEEN_FAILS" | tr -d ' ')"
    collect_fails "$log" "-p $pkg --lib --all-features"
    after="$(wc -l < "$SEEN_FAILS" | tr -d ' ')"
    if [ "$rc" -ne 0 ] && [ "$before" = "$after" ]; then
        # Non-zero with no `test … FAILED` line is the harness DYING, not a
        # test asserting — AGENTS.md's shared-target-dir shape. Nothing
        # asserted anything, so this can never be pinned away.
        echo "✗ $pkg: cargo test died without a failures block — nothing asserted"
        grep -E '^error' "$log" | head -10 || true
        echo "  full log: $log"
        FAILED=$((FAILED + 1))
        return 0
    fi
    n="$(awk '/^test result:/ { s += $4 } END { print s + 0 }' "$log")"
    TOTAL_PASSED=$((TOTAL_PASSED + n))
    if [ -n "$floor" ] && [ "$n" -lt "$floor" ]; then
        echo "✗ $pkg: passed $n < floor $floor — a suite reporting fewer assertions"
        echo "  than its floor is blind, skipped, or compiled to an empty binary."
        FAILED=$((FAILED + 1))
        return 0
    fi
    if [ "$rc" -ne 0 ]; then
        echo "· $pkg: $n passed, $((after - before)) failing test(s) — adjudicated below"
    else
        echo "✓ $pkg: $n passed (floor ${floor:-unpinned})"
    fi
}

FIRST=1
for pkg in $PKGS; do
    floor="$(floor_for "$pkg")"
    if [ "$CANARY" -eq 1 ] && [ "$FIRST" -eq 1 ]; then
        # Same comparison path as a real row — test_gate.sh's convention, so
        # the canary proves the live code rather than a parallel copy of it.
        floor=1000000
    fi
    FIRST=0
    run_lib_cell "$pkg" "$floor"
done

if [ "$CANARY" -eq 1 ]; then
    if [ "$FAILED" -eq 0 ]; then
        echo "✗ canary UNEXPECTEDLY PASSED — the floors did not fire, this gate is vacuous"
        exit 1
    fi
    echo ""
    echo "✓ canary: the impossible floor fired ($FAILED red cell(s)) — the floors are live"
    MATRIX_COMPLETED=1
    exit 0
fi

if [ "$LIBS_ONLY" -eq 0 ]; then
    CELL=$((CELL + 1))
    echo ""
    echo "=== cell $CELL: $ROOT_PKG --tests --release (default features, +avx2) ==="
    # RELEASE, and --no-fail-fast. Both were measured, not preferred:
    #   • in debug, `goat_574_clustered_lm_head` ran for over 20 minutes
    #     without finishing and release runs it in 39.8s; and
    #     `bench_164_gepa_reflective` fails its own 10%-overhead bar at 15.5%
    #     purely because both sides are unoptimised. A perf GOAT in debug
    #     measures the wrong binary.
    #   • without --no-fail-fast the run STOPS at the first red target — the
    #     first attempt reported 56 of ~180 and exited 101.
    log="$SCRATCH/.cell_root_tests.log"
    (cd "$SCRATCH" && cargo test -p "$ROOT_PKG" --tests --no-fail-fast --release \
        -j "$JOBS") > "$log" 2>&1 || true
    n_targets="$(grep -c '^test result:' "$log" || true)"
    n_passed="$(awk '/^test result:/ { s += $4 } END { print s + 0 }' "$log")"
    n_failed="$(awk '/^test result:/ { s += $6 } END { print s + 0 }' "$log")"
    t_floor="$(floor_for "__root_tests_targets")"
    p_floor="$(floor_for "__root_tests_passed")"
    echo "  targets=$n_targets passed=$n_passed failed=$n_failed"
    if [ -n "$t_floor" ] && [ "$n_targets" -lt "$t_floor" ]; then
        echo "✗ only $n_targets target(s) ran, floor $t_floor — a target that compiles"
        echo "  to an empty binary prints 'ok. 0 passed' and exits 0, so a SHRINKING"
        echo "  target count is the shape that hides."
        FAILED=$((FAILED + 1))
    fi
    if [ -n "$p_floor" ] && [ "$n_passed" -lt "$p_floor" ]; then
        echo "✗ only $n_passed assertion(s) ran, floor $p_floor — the target count can"
        echo "  hold while every binary inside it empties out."
        FAILED=$((FAILED + 1))
    fi
    collect_fails "$log" "-p $ROOT_PKG --tests --release"
    if [ "$n_failed" -gt 0 ]; then
        echo "· $n_failed failing test(s) — adjudicated below (log: $log)"
    else
        echo "✓ integration targets clean"
    fi
    TOTAL_PASSED=$((TOTAL_PASSED + n_passed))
fi

# ── Adjudicate the failing set against the pins ─────────────────────────────
PINNED="$SCRATCH/.pinned.txt"
if [ -f "$EXPECTED" ]; then
    # A reasonless row is REFUSED, not accepted: a row nobody had to justify
    # is a backlog wearing a pin (Issue 785's rule, and the shape every other
    # membership pin file in this repo uses).
    if grep -qE '^[^#[:space:]][^#]*$' "$EXPECTED"; then
        echo "✗ $EXPECTED has a row with no '# reason' — refusing"
        grep -nE '^[^#[:space:]][^#]*$' "$EXPECTED" | head -5 || true
        FAILED=$((FAILED + 1))
    fi
    sed 's/#.*//' "$EXPECTED" | awk 'NF { print $1 }' | sort -u > "$PINNED"
else
    : > "$PINNED"
fi
echo ""
echo "▸ confirming each failure ALONE, $CONFIRM_RUNS run(s) each (passing alone is EVIDENCE, not a cause — see the note below)"
sort -u "$SEEN_FAILS" | confirm_fails | sort -u > "$SEEN_FAILS.sorted"
passed_alone_note
UNPINNED="$(comm -23 "$SEEN_FAILS.sorted" "$PINNED")"
STALE="$(comm -13 "$SEEN_FAILS.sorted" "$PINNED")"
n_fail_tests="$(wc -l < "$SEEN_FAILS.sorted" | tr -d ' ')"
n_pinned="$(wc -l < "$PINNED" | tr -d ' ')"
echo ""
echo "▸ CONFIRMED failing tests: $n_fail_tests, pinned rows: $n_pinned"
if [ -n "$UNPINNED" ]; then
    echo "✗ UNPINNED failing test(s) — this is the wall:"
    printf '    %s\n' $UNPINNED
    FAILED=$((FAILED + 1))
fi
if [ -n "$STALE" ] && [ "$LIBS_ONLY" -eq 1 ]; then
    # --libs-only skips the cell that PRODUCES most of these rows, so every one
    # of them would read STALE for the trivial reason that it never ran. A
    # deferral, on the DEFERRED precedent, not a silent skip.
    echo "· STALE check DEFERRED — --libs-only did not run the cell these pins"
    echo "  describe, so \"passes now\" is unmeasured rather than true:"
    printf '    %s
' $STALE
    STALE=""
fi
if [ -n "$STALE" ]; then
    echo "✗ STALE pin(s) — these tests PASS now, so the row describes nothing."
    echo "  Remove them in this commit; a pin file that only ever loosens is not a wall:"
    printf '    %s\n' $STALE
    FAILED=$((FAILED + 1))
fi

BOX_END="$(box_state)"
echo ""
echo "▸ box state — every PASSED-ALONE row above is a latency-bar outcome:"
echo "    at start: $BOX_START"
echo "    at end:   $BOX_END"
echo "  ⚠ NOT observed: in-run load. These are ENDPOINT samples, and the"
echo "     endpoints are the two instants our own cargo is NOT running."
echo "     Measured 2026-09-18 (run 5): a cell died at \`cl : error D8040\`"
echo "     — an MSVC child-spawn failure, i.e. a box under enough load to"
echo "     break a build — while both endpoints read quiet. A per-cell"
echo "     sampler was tried and could not be armed against a known answer,"
echo "     so it is NOT shipped rather than shipped unverified."
echo "  ⚠ Two runs of this matrix are comparable only through these lines. A"
echo "     quiet run is NOT evidence the Issue-833 population is shrinking."
if [ "$FAILED" -gt 0 ]; then
    echo "✗ x86_64 execution matrix FAILED — $FAILED red cell(s) over $CELL cell(s)"
    exit 1
fi
echo "✓ x86_64 execution matrix PASSED — $CELL cell(s), $TOTAL_PASSED assertion(s)"
echo "  EXECUTED on $ARCH at $SHA with RUSTFLAGS='$RUSTFLAGS'."
echo "  ⚠ It does NOT cover: the macOS device backends, wasm32, or"
echo "     --all-features for the integration targets (fixture RNG streams and"
echo "     GOAT calibrations are per-feature — AGENTS.md)."
MATRIX_COMPLETED=1  # the last line — see matrix_cleanup above
