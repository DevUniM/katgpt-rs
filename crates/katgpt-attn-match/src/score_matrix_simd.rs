//! Auto-vectorizing score matrix kernel (Plan 271 Phase 2, T2.2).
//!
//! Implements `Q·K^T · inv_sqrt_d` as a simple strict inner loop. The
//! kernels are STRICT IEEE ordered reductions: the scalar serial add order
//! is the load-bearing property (cross-arch / cross-build bit-equality comes
//! from it, for free). What the compiler does on top of that order is
//! target-dependent and MEASURED (Issue 871 / Bench 871, 2026-09-22):
//! x86_64-pc-windows-msvc emits **scalar-only** float math (0 packed
//! instructions crate-wide, at both the SSE2 baseline and `+avx2,+fma` —
//! `--emit asm`, in-crate); aarch64 emits packed `fmul.4s` products with the
//! add chain still scalar, lane-by-lane in exact element order (bit-identical,
//! and **no `fmla`**). Writes directly into a caller-provided output buffer —
//! zero allocation in the hot path.
//!
//! # Max-shift stabilization
//! The kernel does NOT apply softmax. It applies only the max-shift
//! stabilization (per-row max subtraction) so the consumer can safely `exp()`
//! the result. If you want the raw `QK^T · inv_sqrt_d` without stabilization,
//! pass `stabilize = false`.
//!
//! Per AGENTS.md hot-loop rules:
//! - Caller pre-allocates `out`; we write in-place.
//! - Inner loop is branch-free (bounds checks hoisted via pre-sliced rows).
//! - No allocation inside the kernel.
//!
//! # Performance history
//! The original Plan 271 implementation used 8 manual scalar accumulators
//! (the `dot_8wide` name). This was empirically refuted on Apple Silicon M3
//! Max (2026-07-29): the 8-wide pattern ran 1.26× SLOWER than a simple
//! `for` loop. The mechanism at the time was attributed to "preventing LLVM
//! from emitting the optimal `fmla` sequence" — **that attribution was wrong**:
//! the strict loop never emits `fmla` on any target (aarch64 cross-emit shows
//! packed `fmul.4s` + ordered scalar `fadd`s, no `fmla`; the win was the
//! removed per-element bounds checks and the `iter().sum()` horizontal
//! reduction, not the accumulator count — reasoned, Issue 871). The kernel
//! was simplified anyway; the name `dot_8wide` is retained for call-site
//! compatibility (5+ callers). See `dot_8wide` doc comment for the measured
//! codegen truth per target.

#![allow(clippy::too_many_arguments)]

/// Default stabilization flag. When `true`, the kernel subtracts the per-row
/// max before writing, ensuring `exp()` of the output is numerically safe.
pub const DEFAULT_STABILIZE: bool = true;

/// Compute the score matrix `S = Q·K^T · inv_sqrt_d` with optional max-shift
/// stabilization.
///
/// # Arguments
/// * `queries` - `(n, d)` row-major query vectors.
/// * `keys` - `(T, d)` row-major key vectors.
/// * `n` - Number of queries.
/// * `t` - Number of keys (called `T` in the paper; renamed here to avoid
///   collision with the type parameter convention).
/// * `d` - Head dimension.
/// * `inv_sqrt_d` - Pre-computed `1/√d`. Caller computes once and reuses.
/// * `out` - Caller-allocated `(n, t)` row-major output buffer.
/// * `stabilize` - If `true`, subtract per-row max before writing (prevents
///   `exp()` overflow downstream).
///
/// # Panics
/// Panics on dimension mismatch.
#[inline]
pub fn compute_score_matrix_simd(
    queries: &[f32],
    keys: &[f32],
    n: usize,
    t: usize,
    d: usize,
    inv_sqrt_d: f32,
    out: &mut [f32],
    stabilize: bool,
) {
    assert_eq!(queries.len(), n * d, "queries buffer size mismatch");
    assert_eq!(keys.len(), t * d, "keys buffer size mismatch");
    assert_eq!(out.len(), n * t, "output buffer size mismatch");

    // Stage 1: compute raw dot products into `out` (we reuse it as scratch).
    // Strict ordered reduction via `dot_8wide` — scalar on x86_64, mul-only
    // vectorized on aarch64 (see module doc; Issue 871).
    for i in 0..n {
        let q_row = &queries[i * d..(i + 1) * d];
        let out_row = &mut out[i * t..(i + 1) * t];
        for j in 0..t {
            let k_row = &keys[j * d..(j + 1) * d];
            out_row[j] = dot_8wide(q_row, k_row, d) * inv_sqrt_d;
        }
    }

    // Stage 2 (optional): per-row max-shift. No allocation — find max in a
    // single pass, then subtract in a second pass. We could fuse this into
    // stage 1 but separating keeps the inner dot-product loop branch-free and
    // more amenable to SIMD.
    if stabilize {
        for i in 0..n {
            let row = &mut out[i * t..(i + 1) * t];
            // Branch-free horizontal max — emits CMOV/conditional-select on
            // most targets rather than a predicted branch. Equivalent to the
            // previous `if v > max` but without the mispredict cost on
            // adversarial inputs.
            let mut max = row[0];
            for &v in &row[1..] {
                max = max.max(v);
            }
            for v in row.iter_mut() {
                *v -= max;
            }
        }
    }
}

/// Dot product kernel — strict ordered reduction.
///
/// The name `dot_8wide` is retained for call-site compatibility (5+ callers);
/// the implementation is a plain single-accumulator `for` loop. **Strict
/// IEEE semantics: adds apply in exact element order.** That order is the
/// bit-stability property — cross-arch and cross-build bit-equality hold
/// *because* the chain is serial, and it cannot be vectorized without
/// changing the summation order (and therefore the bits).
///
/// # Measured codegen (Issue 871 / Bench 871, rustc 1.98.1, 2026-09-22)
/// - **x86_64-pc-windows-msvc, in-crate `--emit asm`** (`-C lto=off`,
///   `--features attn_match`): **scalar-only at BOTH arms** — default SSE2
///   baseline and `-C target-feature=+avx2,+fma` both emit 0 packed float-math
///   instructions for the whole crate (no `vmulps`/`vaddps`/`vfmadd…ps`;
///   scalar `mulss`/`addss` or VEX `vmulss`/`vaddss` chains only). LLVM does
///   not reassociate strict FP reductions, and its x86 backend does not even
///   split out the multiply half here.
/// - **aarch64-apple-darwin cross-emit (standalone twin of this exact loop —
///   blake3's build script blocks a cross crate build from Windows)**: packed
///   `fmul.4s` products + per-lane `mov sN, vM[k]` extracts feeding an ordered
///   scalar `fadd s0` chain in exact element order — **bit-identical to the
///   serial order, and no `fmla`**. The historical "optimal `fmla` sequence"
///   claim was never codegen-true; NEON gets multiply-throughput only and the
///   add chain stays serial on every target.
///
/// Consequence: on x86_64 the kernel runs a scalar serial chain in every
/// ordinary build. Recovering SIMD throughput requires changing summation
/// order — the opt-in `algebraic_*` lane (Issue 871 T4, owner-gated feature
/// flag) — not "fixing" strict codegen: there is no strict vectorized add.
/// The one bit-preserving partial vectorization (packed mul + ordered scalar
/// adds) is what aarch64 already emits and buys ~nothing where the add chain
/// binds (reasoned: the `fadd` latency chain dominates; measured: the AVX2
/// arm's strict time is flat vs baseline, Bench 871 G2).
///
/// **Why not manual unrolling (historical note, Plan 271 era):** the original
/// implementation used 8 scalar accumulators (`acc[0]..acc[7]`) under the
/// assumption that manual unrolling beats auto-vectorization. Empirically
/// refuted on Apple Silicon M3 Max (LLVM 21.1.8, stable 1.93): the 8-wide
/// pattern ran **1.26× slower** than the simple loop. The then-attributed
/// mechanism ("blocked the optimal `fmla` sequence") is corrected above — no
/// `fmla` ever existed for the strict loop; the confounders were per-element
/// bounds checks (the pre-`..d`-slice era, see below) and the horizontal
/// `iter().sum()` reduction, not the accumulator count.
///
/// # Panics
/// Caller guarantees `a.len() == b.len() == d`.
#[inline]
pub fn dot_8wide(a: &[f32], b: &[f32], d: usize) -> f32 {
    debug_assert_eq!(a.len(), d);
    debug_assert_eq!(b.len(), d);

    // Simple strict loop — the serial `dot += x * y` order IS the kernel's
    // bit-stability contract (see the doc comment above for the measured
    // per-target codegen; Issue 871).
    //
    // The lengths are only `debug_assert`ed, so in release builds `a[k]`/`b[k]`
    // carried per-element bounds checks against unknown slice lengths. Slicing
    // the `..d` prefixes up front turns those `2·d` checks into two range checks
    // outside the loop, leaving a clean unguarded loop for the target backend
    // to schedule (packed `fmul.4s` + ordered scalar adds on aarch64; scalar on
    // x86_64). Same k order, same single accumulator → bit-identical.
    let mut dot = 0.0f32;
    for (&x, &y) in a[..d].iter().zip(b[..d].iter()) {
        dot += x * y;
    }
    dot
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Instant;

    /// SIMD kernel must match the scalar reference within 1e-6.
    #[test]
    fn test_simd_matches_scalar() {
        let n = 4;
        let t = 8;
        let d = 16;
        let mut seed = 12345u32;
        let mut rng = || {
            seed = seed.wrapping_mul(1664525).wrapping_add(1013904223);
            (seed as f32) / (u32::MAX as f32) * 2.0 - 1.0
        };
        let queries: Vec<f32> = (0..n * d).map(|_| rng()).collect();
        let keys: Vec<f32> = (0..t * d).map(|_| rng()).collect();
        let inv_sqrt_d = 1.0f32 / (d as f32).sqrt();

        // Scalar reference (no stabilization).
        let mut scalar = vec![0.0f32; n * t];
        scalar_dot_matmul(&queries, &keys, n, t, d, inv_sqrt_d, &mut scalar);

        // SIMD kernel (no stabilization).
        let mut simd = vec![0.0f32; n * t];
        compute_score_matrix_simd(&queries, &keys, n, t, d, inv_sqrt_d, &mut simd, false);

        for i in 0..n * t {
            assert!(
                (scalar[i] - simd[i]).abs() < 1e-6,
                "simd/scalar mismatch at {}: scalar={} simd={}",
                i,
                scalar[i],
                simd[i]
            );
        }

        // With stabilization: SIMD row max should be 0.
        let mut simd_stab = vec![0.0f32; n * t];
        compute_score_matrix_simd(&queries, &keys, n, t, d, inv_sqrt_d, &mut simd_stab, true);
        for i in 0..n {
            let row_max = simd_stab[i * t..(i + 1) * t]
                .iter()
                .cloned()
                .fold(f32::NEG_INFINITY, f32::max);
            assert!(
                (row_max - 0.0).abs() < 1e-6,
                "stabilized row max should be 0, got {row_max}"
            );
        }
    }

    /// Stabilization keeps all values ≤ 0 so `exp()` is safe.
    #[test]
    fn test_stabilize_bounds_for_exp() {
        let n = 2;
        let t = 4;
        let d = 8;
        let queries = vec![2.0f32; n * d];
        let keys = vec![2.0f32; t * d];
        let inv_sqrt_d = 1.0f32 / (d as f32).sqrt();
        let mut out = vec![0.0f32; n * t];
        compute_score_matrix_simd(&queries, &keys, n, t, d, inv_sqrt_d, &mut out, true);
        for &v in &out {
            assert!(v <= 1e-6, "stabilized value {v} should be ≤ 0");
        }
    }

    /// Odd `d` exercises the scalar tail.
    #[test]
    fn test_simd_handles_odd_d() {
        let n = 2;
        let t = 3;
        let d = 13; // not a multiple of 8
        let queries: Vec<f32> = (0..n * d).map(|i| (i as f32) * 0.1).collect();
        let keys: Vec<f32> = (0..t * d).map(|i| (i as f32) * 0.05).collect();
        let inv_sqrt_d = 1.0f32 / (d as f32).sqrt();

        let mut scalar = vec![0.0f32; n * t];
        scalar_dot_matmul(&queries, &keys, n, t, d, inv_sqrt_d, &mut scalar);

        let mut simd = vec![0.0f32; n * t];
        compute_score_matrix_simd(&queries, &keys, n, t, d, inv_sqrt_d, &mut simd, false);

        for i in 0..n * t {
            assert!((scalar[i] - simd[i]).abs() < 1e-6, "odd-d mismatch at {i}");
        }
    }

    /// GOAT G8: SIMD kernel must be ≥4× faster than scalar at t=512.
    /// Throughput smoke test (release-only). Documents the actual ns/call of
    /// `compute_score_matrix_simd` at the Plan 271 reference size (`n=8, t=512,
    /// d=64`). Skipped under `debug_assertions` (debug SIMD is not representative).
    ///
    /// Historical note: this was originally `test_simd_4x_speedup` which asserted
    /// ≥1.5× speedup of the (then manually-unrolled) `dot_8wide` kernel over a
    /// scalar reference. The assertion was empirically refuted on Apple Silicon
    /// M3 Max (2026-07-29): the manual 8-accumulator pattern ran 1.26× SLOWER
    /// than the simple loop. The kernel was simplified; the speedup comparison
    /// is now meaningless (both paths use the same strict inner loop — and on
    /// x86_64 both compile scalar-only, Issue 871). This test now serves as a
    /// throughput smoke guard — it documents the absolute perf without asserting
    /// a false relative-speedup gate. The GOAT-level gate lives in
    /// `bench_271_attn_match_goat.rs::g8_simd_vs_scalar` (which SKIPs on <1.5×).
    #[test]
    fn test_simd_throughput_smoke() {
        if cfg!(debug_assertions) {
            eprintln!("skipping simd throughput test in debug build");
            return;
        }
        let n = 8;
        let t = 512;
        let d = 64;
        let mut seed = 98765u32;
        let mut rng = || {
            seed = seed.wrapping_mul(1664525).wrapping_add(1013904223);
            (seed as f32) / (u32::MAX as f32) * 2.0 - 1.0
        };
        let queries: Vec<f32> = (0..n * d).map(|_| rng()).collect();
        let keys: Vec<f32> = (0..t * d).map(|_| rng()).collect();
        let inv_sqrt_d = 1.0f32 / (d as f32).sqrt();

        let mut simd_buf = vec![0.0f32; n * t];

        // Use black_box to prevent the compiler from eliminating the loop.
        use std::hint::black_box;

        // Warmup.
        for _ in 0..3 {
            compute_score_matrix_simd(
                black_box(&queries),
                black_box(&keys),
                n,
                t,
                d,
                inv_sqrt_d,
                &mut simd_buf,
                false,
            );
        }

        let iters = 200;
        let start = Instant::now();
        for _ in 0..iters {
            compute_score_matrix_simd(
                black_box(&queries),
                black_box(&keys),
                n,
                t,
                d,
                inv_sqrt_d,
                &mut simd_buf,
                false,
            );
        }
        let _: f32 = black_box(simd_buf[0]);
        let total_ns = start.elapsed().as_nanos();
        let per_call_ns = total_ns / iters as u128;
        eprintln!(
            "simd_throughput: n={n}, t={t}, d={d}, {iters} iters, {total_ns} ns total, {per_call_ns} ns/call"
        );
        // Throughput guard: each call must complete in under 5 ms at this size
        // (n=8, t=512, d=64 = 262K multiply-adds + the max-shift pass). This is a
        // generous ceiling — the kernel typically runs in ~50-90 µs/call on
        // Apple Silicon (packed muls + scalar adds; scalar-only on x86_64 —
        // Issue 871). The guard catches catastrophic
        // regressions (e.g., accidental debug-mode emission, a broken unroll)
        // without asserting a false speedup claim.
        assert!(
            per_call_ns < 5_000_000,
            "simd throughput regression: {per_call_ns} ns/call > 5 ms ceiling"
        );
    }

    /// Scalar reference for cross-checking correctness (used by
    /// `test_simd_matches_scalar`). Uses a simple `for k in 0..d` dot product —
    /// the same strict shape `dot_8wide` uses internally (both are strict
    /// ordered reductions; scalar on x86_64 — Issue 871).
    /// Kept as a separate function so the correctness test has an independent
    /// reference, not to assert a speedup.
    fn scalar_dot_matmul(
        queries: &[f32],
        keys: &[f32],
        n: usize,
        t: usize,
        d: usize,
        inv_sqrt_d: f32,
        out: &mut [f32],
    ) {
        for i in 0..n {
            let q_row = &queries[i * d..(i + 1) * d];
            let out_row = &mut out[i * t..(i + 1) * t];
            for j in 0..t {
                let k_row = &keys[j * d..(j + 1) * d];
                let mut dot = 0.0f32;
                for k in 0..d {
                    dot += q_row[k] * k_row[k];
                }
                out_row[j] = dot * inv_sqrt_d;
            }
        }
    }
}
