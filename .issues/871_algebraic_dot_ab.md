# Issue 871 — Rust 1.98 `algebraic_*` float operators: measured A/B against the strict ordered-reduction dot

Status: **MEASURED — GOAT-shaped G2 win at both ISA arms on this box (1.77×–8.8× faster, 5/5 dims ≥1.77×), G1 accuracy IMPROVED vs strict (multi-accumulator beats the serial chain), argmax retention clean at fixture scale (0/1024 flips, low near-tie power — 9 events); promotion NOT claimed (owner act, per the `fast-math-contraction-behind-feature-flag` governance shape) — the scalar-strict finding below is the bigger repo consequence.**

Branch: `develop` · Record: [Bench 871](../.benchmarks/871_algebraic_dot_ab.md) · Bench target: `benches/bench_871_algebraic_dot_ab.rs` (no feature gate, no perf bar — this issue carries the verdict)

## Context

Rust 1.98.0 (2026-08-20; our pinned toolchain is 1.98.1) stabilized `f32::algebraic_add/sub/mul/div/rem` — safe per-op fast-math (`reassoc contract arcp nsz`, deliberately no `nnan`/`ninf`, so no poison; rust-lang/rust#136469). For a reduction loop this licenses multiple independent vector accumulators + a tree horizontal reduce, at the cost of cross-arch / cross-build / cross-opt-level **bit-equality** — a property our strict ordered reductions currently give us for free and that several lanes pin.

## Findings (all measured on this box; numbers + box state in Bench 871)

1. **G2 — algebraic is 1.77×–8.8× faster than the strict `dot_8wide` shape, at BOTH compile arms** (baseline SSE2 = what every ordinary x86_64 consumer builds, and `+avx2,+fma`). Worst case d=16 (1.77–1.83×, tail-dominated); best d=256–4096 (5.5× at SSE2, 7.1–8.8× at AVX2+FMA).
2. **⛔ The strict side is SCALAR on x86_64-pc-windows-msvc** — the bigger finding. `dot_strict` emits only `vmulss`/`vaddss` (a serial dependency chain) even with `target-cpu=x86-64-v3`; the strict IEEE ordered reduction does **not** vectorize here. The `dot_8wide` doc comment ("auto-vectorizes to optimal SIMD FMA on every target we ship (NEON, AVX2)") holds on aarch64/NEON where it was measured (M3, the 8-accumulator refutation) but **not on x86_64-windows** — meaning every strict dot in this repo runs scalar today for any consumer building on that target at default target-cpu. This is the Issue-847 class one layer down: a platform the doc claims covered, measured uncovered.
3. **G1 accuracy — algebraic is MORE accurate than strict** against a strict f64 reference on cancellation-realistic data (rel-err 4.6e-7 vs 5.1e-6 at d=4096, SSE2 arm; 1.5e-7 vs 5.1e-6 at AVX2+FMA). The multi-accumulator reduction has less rounding error than the scalar serial chain. The classic fast-math accuracy tax does not appear for add/mul reassociation on this data class — measured, not assumed.
4. **G1 divergence — ulp(strict↔algebraic) grows with d** (1 @ d=16 → 52–56 @ d=4096). Cross-build/cross-arch bit-equality is gone by construction; the no-go zones below are load-bearing.
5. **Retention — 0 argmax flips in 1024 near-tie-forced 64-key trials** (9 near-tie events: top-2 gap ≤ 8 ulp). Clean, but **low power** — the forced pair only reaches the top-2 in 9 trials; a production retention walk (Issue-750-T3 shape) must run on real logits before any logits-lane adoption.

## No-go zones (unchanged by the good numbers)

Committed-byte paths (BLAKE3'd stats, freeze/thaw wire, quorum, deterministic replay), GOAT calibration fixtures, Kahan/compensated sums and the conformal/CRPS floor, and any lane pinning SIMD↔scalar bit-identity or cross-arch bit-equality. `algebraic_div` (`arcp`) is banned outright — a far larger numerics change than reassociation.

## Verdict

The win is real and large, and the accuracy story is favorable — but adoption is an **owner act** in the `fast-math-contraction-behind-feature-flag` shape (riir-clippy `kernel_opt` corpus, the same governance riir-ai's `gemv_fma_contract` already ships on the GPU side): strict default, dedicated feature, correctness gates strict, per-family retention before any argmax-bearing lane. Finding 2 may matter more than finding 1: fixing the STRICT side's missing vectorization on x86_64 (runtime `simd_level()` dispatch or explicit ordered-reduction intrinsics) recovers part of the gap without surrendering bit-equality.

## Tasks

- [x] T1 — Bench landed: `benches/bench_871_algebraic_dot_ab.rs` + `[[bench]]` row (harness=false, no features). Interleaved `ab_timing` A/B + ulp/f64-reference numerics + argmax retention; deterministic LCG (global_rng_gate-safe); prints compile-time target features. Clippy `-D warnings` clean.
- [x] T2 — Codegen evidence captured (Bench 871 §codegen): strict = scalar `vmulss`/`vaddss` chain at baseline AND v3; algebraic = `addps`/`mulps` packed at SSE2, `vfmadd231ps` ×5 + `vaddps` ×6 at AVX2+FMA (multi-accumulator mainloop).
- [x] T3 — A/B measured both arms on the 4090 box (Windows, x86_64-pc-windows-msvc, rustc 1.98.1): see Findings 1/3/5. Box state recorded in Bench 871.
- [ ] T4 — **Owner decision: adoption lane.** Either (a) feature-gated `algebraic_dot` (strict default, opt-in perf builds — the `gemv_fma_contract` shape) for hot non-bit-pinned reductions and scalar fallback arms, or (b) decline and record the negative. Needs the real-logits retention walk first if any logits lane is in scope.
- [ ] T5 — **Verify `dot_8wide` in-crate codegen on x86_64** (Finding 2 was measured on a standalone probe of the identical loop shape; the in-crate compile context should be confirmed) and correct the `score_matrix_simd.rs` doc comment — it currently claims AVX2 auto-vectorization that does not happen on x86_64-windows. If confirmed, decide: runtime `simd_level()` dispatch (the Issue-847 repair class) or explicit ordered-reduction intrinsics for the strict side.
- [-] T6 — NEON/aarch64 arm: DEFERRED — the M3 is not reachable from this box (the SSH path documented in the global rules is M3→4090, not the reverse). The `dot_8wide` M3 measurements stand as the aarch64 baseline; re-run Bench 871 there when a lane exists.
- [-] T7 — riir-clippy `rust_perf` rule candidate ("reduction loop may permit reassociation" — suggest-only, never auto-apply): DEFERRED until T4 decides adoption; the healer must not emit numerics-changing rewrites ahead of an owner call.
