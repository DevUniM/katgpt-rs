//! SIMD argmax — single-pass `(usize, f32)` reducer used by token sampling.

#[allow(unused_imports)]
use crate::simd::simd_max_f32;

/// Single-pass argmax: returns `(index, value)` of the maximum element.
///
/// Fuses max-finding and index-recovery into one traversal. The naive idiom —
/// `simd_max_f32(x)` followed by `x.iter().position(|&v| v == max)` — scans the
/// buffer twice (one SIMD max pass + one scalar equality scan that can run the
/// full length). On `aarch64` this uses a NEON kernel that tracks per-lane max
/// values *and* indices in one pass, measured at ~5× faster than the two-pass
/// idiom across vocab sizes 27 → 256k.
///
/// Tie-break matches `position(|&v| v == max)`: the **first** index attaining
/// the maximum is returned (strict `>` never replaces an earlier equal value).
///
/// Returns `(0, f32::NEG_INFINITY)` for an empty slice.
#[inline]
pub fn simd_argmax_f32(x: &[f32]) -> (usize, f32) {
    if x.is_empty() {
        return (0, f32::NEG_INFINITY);
    }
    #[cfg(target_arch = "aarch64")]
    {
        unsafe { neon_argmax_f32(x) }
    }
    #[cfg(all(target_arch = "wasm32", target_feature = "simd128"))]
    {
        unsafe { wasm32_simd128_argmax_f32(x) }
    }
    #[cfg(not(any(
        target_arch = "aarch64",
        all(target_arch = "wasm32", target_feature = "simd128")
    )))]
    {
        two_pass_argmax_f32(x)
    }
}

/// The x86_64 (and generic non-SIMD) path: `simd_max_f32` reduce +
/// `position(== max)`. Provenance: a scalar index-tracking loop does not
/// auto-vectorize and measured SLOWER than this two-pass idiom at large
/// vocab, so the two-pass is the incumbent — and it survived a second
/// challenger on measured evidence. Issue 817 ported the NEON single-pass
/// (8 lanes tracking (max, index), blend-on-strict-gt) and the dispatch A/B
/// measured it a net LOSS on this box: the two-pass wins `iid` 2.8–3.5× and
/// `early` 3–4.7× at n ≥ 256 (ILP'd `max_ps` reduce + a vectorized
/// early-exiting `position` beat a latency-bound cmp/blend chain), while the
/// kernel only wins when the maximum sits in the last few percent of the
/// scan (1.5–1.9×) and at n=64 (fixed-overhead, ~20 ns). Both profile arms,
/// tight round bands:
/// [Bench 811](../../.benchmarks/812_argmax_avx2_single_pass_goat.md).
/// Demote-on-loss applied; the dispatch was reverted the same day. Reopen
/// trigger: re-run `tests/bench_817_argmax_dispatch_ab.rs` after a major
/// toolchain/CPU change — if the two-pass absolute columns regress or the
/// position-scan advantage disappears, re-try the port.
///
/// Cost note (measured, Bench 810): this path's cost depends on WHERE the
/// maximum sits — the second pass rescans until it finds `max`, so a late
/// maximum pays two full scans (`late_peak` k=1 lost ~0.9× in the argtopk
/// k=1 rows). That loss is ACCEPTED: fixing it costs more everywhere else
/// (Bench 811).
///
/// Gated to exactly the platforms the dispatch arm above serves (x86_64 and
/// the generic non-SIMD triples) — on aarch64 / wasm32+simd128 the NEON and
/// wasm kernels own the dispatch, and an ungated copy here is dead code there.
#[cfg(not(any(
    target_arch = "aarch64",
    all(target_arch = "wasm32", target_feature = "simd128")
)))]
#[inline]
fn two_pass_argmax_f32(x: &[f32]) -> (usize, f32) {
    let max_val = simd_max_f32(x);
    let idx = x.iter().position(|&v| v == max_val).unwrap_or(0);
    (idx, max_val)
}

/// NEON single-pass argmax: tracks 4 lanes of (max value, index) simultaneously.
///
/// Each lane `l` accumulates the strided elements `x[l], x[l+4], x[l+8], …`;
/// `vcgtq_f32` (strict greater-than) only updates a lane on a *new* maximum, so
/// within a lane the earliest index wins. The 4 lane candidates are then reduced
/// by (value desc, index asc), and a scalar tail handles the final `len % 4`.
#[cfg(target_arch = "aarch64")]
#[inline]
unsafe fn neon_argmax_f32(x: &[f32]) -> (usize, f32) {
    use core::arch::aarch64::{
        vaddq_u32, vbslq_u32, vcgtq_f32, vdupq_n_u32, vld1q_f32, vld1q_u32, vmaxq_f32, vst1q_f32,
        vst1q_u32,
    };
    unsafe {
        let n = x.len();
        // Below one full vector, scalar is cheaper than NEON setup.
        if n < 4 {
            let mut bi = 0usize;
            let mut bv = *x.get_unchecked(0);
            for i in 1..n {
                let v = *x.get_unchecked(i);
                if v > bv {
                    bv = v;
                    bi = i;
                }
            }
            return (bi, bv);
        }

        let base: [u32; 4] = [0, 1, 2, 3];
        let four = vdupq_n_u32(4);
        let mut vmax = vld1q_f32(x.as_ptr());
        let mut vidx = vld1q_u32(base.as_ptr());
        let mut cur = vaddq_u32(vidx, four); // indices for the next chunk
        let chunks = n / 4;
        let mut i = 4;
        for _ in 1..chunks {
            let v = vld1q_f32(x.as_ptr().add(i));
            let mask = vcgtq_f32(v, vmax); // lanes where v strictly greater
            vmax = vmaxq_f32(vmax, v);
            vidx = vbslq_u32(mask, cur, vidx); // adopt new index only where greater
            cur = vaddq_u32(cur, four);
            i += 4;
        }

        // Reduce the 4 lanes: highest value, smallest index on ties.
        let mut vals = [0f32; 4];
        let mut idxs = [0u32; 4];
        vst1q_f32(vals.as_mut_ptr(), vmax);
        vst1q_u32(idxs.as_mut_ptr(), vidx);
        let mut bv = vals[0];
        let mut bi = idxs[0] as usize;
        for l in 1..4 {
            let vi = idxs[l] as usize;
            if vals[l] > bv || (vals[l] == bv && vi < bi) {
                bv = vals[l];
                bi = vi;
            }
        }

        // Scalar tail (0..3 remaining elements).
        while i < n {
            let v = *x.get_unchecked(i);
            if v > bv {
                bv = v;
                bi = i;
            }
            i += 1;
        }
        (bi, bv)
    }
}

/// WASM SIMD128 single-pass argmax — 4-wide, tracks (max value, index) per lane.
///
/// Issue 007: ports the NEON kernel structure to `core::arch::wasm32`. Uses
/// `f32x4_max` for lane-wise max and `v128_bitselect` to pick the candidate
/// index only where it strictly exceeds the running lane max (mirrors NEON's
/// `vbslq_u32` semantics: `bitselect(cand_idx, best_idx, gt_mask)` =
/// `mask ? cand_idx : best_idx`). Tie-break is first-index-wins via strict `>`
/// (`f32x4_gt`), matching `position(|&v| v == max)` on the scalar path.
///
/// Compile-time gated by `target_feature = "simd128"`.
#[cfg(all(target_arch = "wasm32", target_feature = "simd128"))]
#[inline]
unsafe fn wasm32_simd128_argmax_f32(x: &[f32]) -> (usize, f32) {
    use core::arch::wasm32::{
        f32x4_extract_lane, f32x4_gt, f32x4_max, i32x4_add, i32x4_extract_lane, i32x4_splat,
        v128_bitselect, v128_load,
    };
    unsafe {
        let n = x.len();
        // Below one full vector, scalar is cheaper than SIMD128 setup.
        if n < 4 {
            let mut bi = 0usize;
            let mut bv = *x.get_unchecked(0);
            for i in 1..n {
                let v = *x.get_unchecked(i);
                if v > bv {
                    bv = v;
                    bi = i;
                }
            }
            return (bi, bv);
        }

        // Seed: vmax = x[0..4], vidx = [0,1,2,3], cur = [4,5,6,7] (next chunk's indices).
        let base: [i32; 4] = [0, 1, 2, 3];
        let four = i32x4_splat(4);
        let mut vmax = v128_load(x.as_ptr().cast());
        let mut vidx = v128_load(base.as_ptr().cast());
        let mut cur = i32x4_add(vidx, four);
        let chunks = n / 4;
        let mut i = 4;
        for _ in 1..chunks {
            let v = v128_load(x.as_ptr().add(i).cast());
            let mask = f32x4_gt(v, vmax); // lanes where v strictly greater
            vmax = f32x4_max(vmax, v);
            // Adopt new index only where strictly greater; else keep old.
            vidx = v128_bitselect(cur, vidx, mask);
            cur = i32x4_add(cur, four);
            i += 4;
        }

        // Reduce the 4 lanes: highest value, smallest index on ties.
        let v0 = f32x4_extract_lane::<0>(vmax);
        let v1 = f32x4_extract_lane::<1>(vmax);
        let v2 = f32x4_extract_lane::<2>(vmax);
        let v3 = f32x4_extract_lane::<3>(vmax);
        let i0 = i32x4_extract_lane::<0>(vidx) as usize;
        let i1 = i32x4_extract_lane::<1>(vidx) as usize;
        let i2 = i32x4_extract_lane::<2>(vidx) as usize;
        let i3 = i32x4_extract_lane::<3>(vidx) as usize;
        let mut bv = v0;
        let mut bi = i0;
        for (v, idx) in [(v1, i1), (v2, i2), (v3, i3)] {
            if v > bv || (v == bv && idx < bi) {
                bv = v;
                bi = idx;
            }
        }

        // Scalar tail (0..3 remaining elements).
        while i < n {
            let v = *x.get_unchecked(i);
            if v > bv {
                bv = v;
                bi = i;
            }
            i += 1;
        }
        (bi, bv)
    }
}
