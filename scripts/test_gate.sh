#!/bin/sh
# scripts/test_gate.sh — the first CI-executed tests in this repo
# (katgpt-rs Issue 718 T3(b), the riir-train 507 shape; Issue 718 closed +
# removed 2026-09-04 — durable record in
# `.docs/10_audits/ci_compile_vs_execute_axis.md`).
#
# Before this gate, every automatic trigger here (full_gate.yml,
# feature_isolation*.yml, docs_gate.yml, lean_proofs.yml) reached only
# `cargo check` / `cargo clippy` / the Python auditors — CI compiled all
# 477 integration-test targets, 31 lib targets and 176 bench targets over
# 32 packages and EXECUTED none, so by this repo's own rule that an
# uninvoked assertion is unknown, not passing, every Rust assertion here
# was unknown. This gate makes the machine-invariant core EXECUTED and
# FLOORED. It is the AUTHORIZED scoped tier (owner decision recorded in
# `.docs/10_audits/ci_compile_vs_execute_axis.md`, 2026-09-04);
# the full-workspace `--all-features --release` execution stays
# dispatch-only. It has now been PRICED on a quiet box
# (`.benchmarks/701_full_workspace_execution_pricing.md`) and the verdict
# was still dispatch-only, on that measurement. No scheduled full job.
#
# Scope (and what it deliberately does NOT cover):
#   COVERED     — the default-feature `--lib` suites of katgpt-rs (root)
#                 and katgpt-core: 203 + 1974 passed at landing, pure
#                 modelless CPU, zero sibling checkouts (katgpt-core's
#                 deps are crates.io-only; the root builds its own member
#                 crates), no model files, no GPU.
#                 Platform invariance, grep-verified at landing: katgpt-core
#                 has ZERO `#[cfg(target_os)]` attributes (its two
#                 `target_os` sites are runtime `cfg!()` bools — both
#                 branches compile everywhere), and the root lib's
#                 `target_os` gates are all behind the opt-in
#                 `ane`/`gpu_inference` features, dead at default features
#                 on every platform — so the floored counts are expected
#                 to be platform-invariant. The first scheduled run is the
#                 measurement: if Linux deltas surface, that is the rot
#                 check finding real debt, not a reason to widen silently.
#   NOT COVERED — the 477 integration-test targets (each carries
#                 required-features or multi-minute single tests — priced
#                 out of a weekly gate; the floors here make expanding
#                 this gate a one-line ROWS addition), the 176 bench
#                 targets, and everything needing Metal/ANE/4090 — those
#                 stay workstation-owned.
#
# T3 shape: per-target FLOORS, not exact pins. A floor fires DOWNWARD
# only — adding tests never reds the gate; deleting tests, a feature
# change that compiles a lib to nothing, or a broken build reds it. A
# target that produces NO `test result:` line also fails (the
# `#![cfg]`-gated-file green-zero trap: `ok. 0 passed` with exit 0 is
# byte-for-byte a real pass, and a skipped target produces no line at all).
#
# --canary: runs the first row with a floor of 100000 and asserts the gate
# FAILS — the proof the floors are live (same comparison path as a
# blind/zero target, without mutating the tree). Dev-time; too costly to
# run in CI every week.
#
# Parse discipline: exactly ONE `test result:` line is expected per `--lib`
# invocation. More or fewer means the parse has gone blind — fail loudly
# rather than sum or guess.
#
# Floors measured 2026-09-04 on committed-HEAD-equivalent working tree
# (debug, M3): katgpt-rs 203 passed / 0 failed (30.9 s), katgpt-core
# 1974 passed / 0 failed / 7 ignored (11.0 s). katgpt-dec at
# `--features pca_global` measured 2026-09-11 (Plan 591 Phase 2; 249 =
# 225 base + 24 pca, DEFAULT-ON since Bench 708 — the row also equals the
# default-feature count now, kept explicit so the pin survives a future
# default-list change). katgpt-core raised 1974→2041 2026-09-13 (4090 box,
# Windows, HEAD 662783dc — the +67 are committed test additions since
# 09-04; platform-invariant per the landing analysis, zero target_os cfg
# at default features). katgpt-core raised 2041→2053 2026-09-15 (Issue 781
# / Bench 764 — the slt module promoted default-on, +12 tests; same box,
# measured). katgpt-core raised 2053→2060 2026-09-15 (Issue 782 / Bench 765
# — slt_sweep promoted default-on, +7 gate tests +1 ignored diagnostics;
# same box, measured 2060/8). Raising a floor is a
# measured act; lowering one needs a note in the commit that does it.
#
# --test-threads=2 is deliberate (the riir-train 507 precedent): a weekly
# red on runner-load noise from a timing-sensitive test would be alarm
# fatigue; 2 threads costs ~2x wall on a ~40 s suite.
#
# Row format: `pkg:floor` for a default-feature lib suite, or
# `pkg:floor:features` for a feature-armed one (the riir-chain convention:
# a feature-gated surface's tests compile to NOTHING at default features —
# the green-zero trap — so the row that executes them must NAME the
# feature). First row must stay featureless (the --canary arm runs it).

set -u

# ⛔ katgpt-types is here because of riir-train Issue 549, and the reason is the
# COMPILE-vs-EXECUTE axis this script exists for, one platform over.
# `avx2_exp_sum_inplace` — the fused exp+sum behind every softmax — was the one
# exp kernel missing the n-clamp before the `(n + 127) << 23` bit-trick, so for
# x < -87.3 the shift wrapped the exponent field and returned ~1e23-1e33 garbage
# instead of ~0. It cost two sessions and presented as "seed-1000 training
# collapses on the 4090, healthy on the M3".
#
# The regression test landed in `490b662e` and was EXECUTED BY NOTHING:
# full_gate is macOS/aarch64 (the NEON sibling always clamped, so that lane
# cannot see this class) and is compile+lint, not execute; wasm32_gate builds a
# different kernel; and this — the only executing lane, ubuntu-latest, x86_64,
# where `is_avx2_fma_available()` dispatches to the kernel that had the bug —
# did not select the crate. A guard nobody runs is the "uninvoked assertion is
# UNKNOWN, not passing" rule in AGENTS.md, applied to the one test written to
# stop this exact defect recurring.
#
# The floor is arch-INVARIANT and that was checked, not assumed: the crate's
# three `cfg(target_arch)` sites are assertions inside ONE test body, not gates
# on whole test functions, so the count is the same on aarch64 and x86_64 —
# which matters because AGENTS.md tells you to run this script locally, and a
# floor derived from one arch would red on the other.
ROWS="
katgpt-rs:203
katgpt-core:2060
katgpt-dec:249:pca_global
katgpt-types:139
"

canary=0
if [ "${1:-}" = "--canary" ]; then
    canary=1
    echo "canary: running the first row with floor=100000 — the gate MUST fail"
fi

fail=0
first=1
for row in $ROWS; do
    pkg=${row%%:*}
    tail=${row#*:}
    floor=${tail%%:*}
    feats=""
    case "$tail" in
        *:*) feats=${tail#*:} ;;
    esac
    if [ "$canary" = 1 ] && [ "$first" = 1 ]; then
        floor=100000
    fi
    first=0

    feat_args=""
    [ -n "$feats" ] && feat_args="--features $feats"

    echo "=== $pkg --lib (floor $floor, ${feats:-default features}, --test-threads=2) ==="
    if ! out=$(cargo test -p "$pkg" --lib $feat_args -- --test-threads=2 2>&1); then
        echo "FAIL $pkg: cargo test exited non-zero"
        printf '%s\n' "$out" | tail -20
        fail=1
        continue
    fi

    n=$(printf '%s\n' "$out" | awk '$1 == "test" && $2 == "result:" { for (i = 3; i <= NF; i++) if ($i == "passed;") print $(i-1) }')
    nlines=$(printf '%s\n' "$n" | grep -c .)
    if [ "$nlines" != "1" ]; then
        echo "FAIL $pkg: expected exactly 1 'test result:' line for --lib, got $nlines — the parse is blind or the target shape changed"
        fail=1
        continue
    fi

    echo "passed=$n floor=$floor"
    if [ "$n" -lt "$floor" ]; then
        echo "FAIL $pkg: passed $n < floor $floor — a target reporting fewer assertions than its floor is blind, skipped, or broken"
        fail=1
    fi
done

if [ "$fail" = 1 ]; then
    echo "test_gate: FAIL"
    exit 1
fi
if [ "$canary" = 1 ]; then
    echo "test_gate: canary UNEXPECTEDLY PASSED — the floors did not fire, the gate is vacuous"
    exit 1
fi
echo "test_gate: PASS"
