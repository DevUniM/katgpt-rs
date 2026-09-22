# Issue 874 — G8 (`bench_271_attn_match_goat::g8_simd_vs_scalar`) is inert: the "scalar" arm routes through the same `dot_8wide` kernel

Status: **OPEN — filed from the Issue 871 T5 verification (verdict round-2 finding, verified in-source); a standing GOAT-gate inertness on a DEFAULT-ON feature, live independent of the `algebraic_dot` lane. Repair not attempted in the filing session (gate owns count-pinned floors; the repair is its own unit).**

Branch: `develop` · Evidence: [Bench 871](../.benchmarks/871_algebraic_dot_ab.md) §Addendum (in-crate codegen) · Filed: 2026-09-22

## The defect

`g8_simd_vs_scalar` (Plan 271's GOAT gate 8, `tests/bench_271_attn_match_goat.rs:464+`)
measures the speedup of `compute_score_matrix_simd` over `compute_score_matrix` and asserts
≥ 1.5×. But `score_matrix.rs::compute_score_matrix` **routes its inner loop through
`dot_8wide`** — the SAME kernel `compute_score_matrix_simd` uses. The gate compares one
kernel against itself:

- **x86_64-pc-windows-msvc** (measured in-crate, Bench 871 addendum): both arms compile to
  the identical scalar serial chain (0 packed float math crate-wide at BOTH the SSE2
  baseline and `+avx2,+fma`) → speedup ≈ 1.0.
- **aarch64** (cross-emit twin evidence): both arms get the identical packed-`fmul.4s` +
  ordered-scalar-`fadd` shape → speedup ≈ 1.0 there too.

The `< 1.5` branch then prints `G8: SKIP …` and **returns Ok — exit 0**. So G8 can never
fail by construction: it either SKIPs (identical arms) or "passes" on timing noise between
two identical binaries (a false pass, which is worse). This is the Issue-855
latency-gate-green-zero class and the cfg-gated green-zero rule one layer down, sitting
inside a GOAT gate on a default-on feature.

## When it broke

The simplification that made `compute_score_matrix` reuse `dot_8wide` (the Plan-271-era
kernel consolidation, DRY-motivated — correct for bit-identity, fatal for the A/B gate).
Since then G8's two arms are the same code; any historical G8 "PASS" post-consolidation was
timing noise, and every SKIP was the gate going blind, not scalar being "unusually
well-optimized" (the SKIP message's own framing).

## Repair options (for the fixing session — decide, don't stack)

1. **Genuine scalar reference arm**: a `#[inline(never)]` naive triple-loop INSIDE the
   bench (never routed through `dot_8wide`) as the baseline, preserving the gate's original
   intent (SIMD-shaped vs naive-shaped).
2. **Re-point the gate** at a real architecture contrast that still exists (e.g. serial
   `compute_score_matrix` vs `compute_score_matrix_rayon` at a size where rayon wins) and
   rename accordingly.
3. **Retire the speedup claim**: convert G8 to an absolute throughput smoke (the
   `test_simd_throughput_smoke` shape already in `score_matrix_simd.rs` tests) and record
   that the relative-speedup claim is unmeasurable since the kernel consolidation.

⚠ Whatever the choice: check `scripts/test_gate.sh` PERF_ROWS and any count pins for
`bench_271_attn_match_goat` before/after, and note that option 1's naive arm is
deliberately NOT bit-different from the SIMD arm on x86_64 (both scalar) — the gate would
be measuring shape-vs-shape codegen, which after Issue 871's findings is known to be
target-dependent (state the target in any new bar).

## Tasks

- [ ] T1 — Decide the repair option (1/2/3 above) — owner-gated (GOAT gate semantics).
- [ ] T2 — Implement + re-run the full `bench_271_attn_match_goat` gate; record the new
  G8 posture in the Plan 271 record's addendum.
- [ ] T3 — Grep the workspace for OTHER `*_vs_scalar`-style A/B gates whose "scalar" arm
  routes through the same kernel as the "SIMD" arm (the same consolidation trap may exist
  elsewhere — this filing checked only the one the Issue 871 reviewer named).
