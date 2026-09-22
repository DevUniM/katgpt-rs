//! Opt-in reassociated (algebraic) dot product — the Issue 871 T4 lane.
//!
//! `f32::algebraic_add` / `f32::algebraic_mul` (Rust 1.98) carry per-op
//! `reassoc contract arcp nsz` and deliberately NO `nnan`/`ninf` — a NaN
//! input still behaves as a NaN output (no poison). The `reassoc`
//! permission lets LLVM use multiple independent vector accumulators and a
//! tree horizontal reduce; the strict kernel cannot (a strict IEEE ordered
//! reduction's add chain IS its bit-equality — see the `dot_8wide` doc and
//! the Bench 871 in-crate addendum).
//!
//! # Measured — claims scoped to the measurement (Bench 871)
//!
//! * **Perf:** 1.77×–8.8× faster than the strict `dot_8wide` shape at BOTH
//!   compile arms (SSE2 baseline — what every ordinary x86_64 consumer
//!   builds — and `+avx2,+fma`), d=16..4096. One box, one triple
//!   (`x86_64-pc-windows-msvc`), rustc 1.98.1, interleaved `ab_timing`
//!   A/B, box state recorded in Bench 871.
//! * **aarch64: UNMEASURED.** The strict side already emits packed
//!   multiplies there (T5 addendum), so the gap is expected smaller — no
//!   number is claimed for any aarch64 target.
//! * **Accuracy:** on the bench's cancellation-realistic fixture class
//!   (mixed exponents 2⁻⁷..2⁸), rel-err vs a strict f64 reference
//!   IMPROVED vs strict (4.6e-7 vs 5.1e-6 at d=4096) — the
//!   multi-accumulator reduction rounds better than the scalar serial
//!   chain. Measured on that data class only; not a general claim — the
//!   ill-conditioned arm (near-zero dots, rank-deficient structure) is
//!   recorded in Bench 871 and CONSUMER SELECTION reads it before wiring
//!   anywhere.
//! * **Divergence:** ulp(strict ↔ algebraic) grows with d (1 @ d=16 →
//!   52–56 @ d=4096). Cross-arch / cross-build / cross-opt-level
//!   bit-equality is gone BY CONSTRUCTION. Never use this kernel on a
//!   bit-pinned lane.
//!
//! # No-go zones (hard rules)
//!
//! Committed-byte paths (BLAKE3'd stats, freeze/thaw wire, quorum,
//! deterministic replay), GOAT calibration fixtures, Kahan/compensated
//! sums, the conformal/CRPS floor, and any lane pinning SIMD↔scalar
//! bit-identity or cross-arch bit-equality. `algebraic_div` /
//! `algebraic_rem` are BANNED repo-wide
//! (`scripts/algebraic_op_ban_gate.py`) — `arcp`/remainder semantics are a
//! far larger numerics change than reassociation.
//!
//! # Wiring an argmax-bearing consumer? (retention precondition)
//!
//! Any consumer whose output feeds an argmax / top-k decision (logits
//! lanes, key selection) must FIRST pass a real-data retention walk in the
//! Issue-750-T3 per-family shape. Bench 871's fixture-scale walk (0/1024
//! flips, 9 near-tie events) is LOW POWER and does not satisfy this
//! precondition. This feature ships with ZERO consumers wired; the
//! precondition gates the first wiring, not the primitive.
//!
//! Governance: the `fast-math-contraction-behind-feature-flag` shape
//! (riir-ai's GPU-side `gemv_fma_contract` precedent) — strict stays the
//! sole default path; promotion to default would require a separate GOAT
//! gate and is NOT claimed here.

/// Multi-accumulator-permitted (reassociated) dot product — the opt-in
/// Issue 871 lane. Signature mirrors `score_matrix_simd::dot_8wide` for
/// call-site compatibility; the loop body is the Bench 871 measured twin
/// verbatim (prefix-`..d` bounds hoist + `algebraic_*` ops), so the bench's
/// twin-vs-kernel identity holds by construction.
///
/// NOT bit-equal to `dot_8wide` (see module docs). Same-build determinism
/// holds: one build produces one result for one input.
///
/// # Panics
/// Panics in debug builds if `a.len() != d` or `b.len() != d` (the same
/// `debug_assert` contract as `dot_8wide`: the caller guarantees equal
/// lengths; the `..d` prefix is a bounds-check hoist under that contract).
#[inline]
pub fn algebraic_dot(a: &[f32], b: &[f32], d: usize) -> f32 {
    debug_assert_eq!(a.len(), d);
    debug_assert_eq!(b.len(), d);
    let (a, b) = (&a[..d], &b[..d]);
    let mut dot = 0.0f32;
    for (&x, &y) in a.iter().zip(b.iter()) {
        dot = dot.algebraic_add(x.algebraic_mul(y));
    }
    dot
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Seeded local LCG (the global_rng_gate rule: no unseeded global draws).
    /// Same generator family as the Bench 871 fixture — mixed magnitudes,
    /// exponent 2⁻⁷..2⁸, random sign/mantissa — so the dots see real
    /// cancellation, not uniform-scale sums.
    struct Lcg(u32);

    impl Lcg {
        fn next_u32(&mut self) -> u32 {
            self.0 = self.0.wrapping_mul(1664525).wrapping_add(1013904223);
            self.0
        }

        fn next_f32(&mut self) -> f32 {
            let r = self.next_u32();
            let r2 = self.next_u32();
            let exp = 120 + (r % 16);
            f32::from_bits((exp << 23) | (r2 & 0x007F_FFFF) | (r2 & 0x8000_0000))
        }
    }

    /// Strict f64 reference, same order — ground truth for the accuracy test.
    fn dot_strict_f64(a: &[f32], b: &[f32]) -> f64 {
        let mut dot = 0.0f64;
        for (&x, &y) in a.iter().zip(b.iter()) {
            dot += f64::from(x) * f64::from(y);
        }
        dot
    }

    /// The strict f32 chain (the `dot_8wide` shape) — the comparison side.
    fn dot_strict_f32(a: &[f32], b: &[f32]) -> f32 {
        let mut dot = 0.0f32;
        for (&x, &y) in a.iter().zip(b.iter()) {
            dot += x * y;
        }
        dot
    }

    fn rel_err(x: f32, reference: f64) -> f64 {
        let scale = reference.abs().max(1e-30);
        (f64::from(x) - reference).abs() / scale
    }

    #[test]
    fn zero_len_and_zero_vectors() {
        assert_eq!(algebraic_dot(&[], &[], 0), 0.0);
        let z = vec![0.0f32; 64];
        assert_eq!(algebraic_dot(&z, &z, 64), 0.0);
    }

    #[test]
    fn known_answer_exact() {
        // All values exact in f32; 1·1 + 2·2 + 3·3 = 14 regardless of order.
        let a = [1.0f32, 2.0, 3.0];
        let b = [1.0f32, 2.0, 3.0];
        assert_eq!(algebraic_dot(&a, &b, 3), 14.0);
    }

    #[test]
    fn odd_tail_close_to_f64_reference() {
        let mut rng = Lcg(12345);
        let d = 13; // not a multiple of any vector width — the tail path
        let a: Vec<f32> = (0..d).map(|_| rng.next_f32()).collect();
        let b: Vec<f32> = (0..d).map(|_| rng.next_f32()).collect();
        let got = algebraic_dot(&a, &b, d);
        let want = dot_strict_f64(&a, &b);
        assert!(
            rel_err(got, want) < 1e-4,
            "odd-tail rel-err too large: got {got}, ref {want}"
        );
    }

    /// The measured Bench 871 property, pinned on the same fixture class:
    /// the reassociated reduction rounds at least as well as the strict
    /// serial chain against the f64 reference (measured margin ~11× at
    /// d=4096: 4.6e-7 vs 5.1e-6). Deterministic fixture — if this ever
    /// flips on a future toolchain, the module's accuracy claim is stale
    /// and must be re-scoped, not the assertion loosened.
    #[test]
    fn accuracy_not_worse_than_strict_on_fixture_class() {
        let mut rng = Lcg(98765);
        let d = 4096;
        let a: Vec<f32> = (0..d).map(|_| rng.next_f32()).collect();
        let b: Vec<f32> = (0..d).map(|_| rng.next_f32()).collect();
        let reference = dot_strict_f64(&a, &b);
        let alg = rel_err(algebraic_dot(&a, &b, d), reference);
        let strict = rel_err(dot_strict_f32(&a, &b), reference);
        assert!(
            alg <= strict,
            "algebraic rel-err {alg:.3e} exceeded strict {strict:.3e} — scope the claim"
        );
    }

    #[test]
    fn same_build_determinism() {
        let mut rng = Lcg(555);
        let d = 256;
        let a: Vec<f32> = (0..d).map(|_| rng.next_f32()).collect();
        let b: Vec<f32> = (0..d).map(|_| rng.next_f32()).collect();
        let x = algebraic_dot(&a, &b, d);
        let y = algebraic_dot(&a, &b, d);
        assert_eq!(x.to_bits(), y.to_bits());
    }

    /// The `no nnan` half of the flag set: NaN propagates as data — no
    /// poison, no unspecified results. Pins the safety property that makes
    /// `algebraic_*` a *safe* fast-math lane.
    #[test]
    fn nan_propagates_no_poison() {
        let a = [1.0f32, f32::NAN, 3.0];
        let b = [1.0f32, 1.0, 1.0];
        let got = algebraic_dot(&a, &b, 3);
        assert!(got.is_nan(), "NaN input must yield NaN output, got {got}");
    }
}
