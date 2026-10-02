//! GOAT gate — Issue 875 T3: time-annealed solver sampling ranges + the
//! zero-terminal-weight truncation predicate (Research 582 /
//! arXiv:2605.09071, the modelless arm's schedule layer).
//!
//! - **G1 (e2e, public surface)**: closed-form round-trip
//!   `ceiling(fraction(x)) ≈ x`; the paper alignment (`t_min = 0.02` →
//!   ceiling `0.70` at `ε = ((1−0.70)/(1−0.02))²`); the anneal law over a
//!   full schedule (fixed floor, non-increasing ceiling, exact endpoint
//!   postures); determinism (bit-equal repeated calls); the
//!   `dllm_solver` consumer seam (σ scaling, VE→VP bridge, skippable
//!   predicate boundary).
//! - **G2 (latency class)**: `range_at` vs a STRONG hand-rolled baseline
//!   (clamp-lerp + sqrt written inline in this test) through the shared
//!   `best_of_us` harness — a once-per-decode-iteration schedule must be
//!   ns-class (< 50 ns/op) and within 3× of the trivial baseline. NOT a
//!   per-token hot path: the seam is consulted once per decode iteration,
//!   never per token (by construction — `range_at` takes the iteration
//!   index, not a position). The bar asserts under `--release` only; a
//!   debug build measures an unoptimised binary (the standing rule).
//! - **G3**: no default-path surface — the struct + predicate + seam live
//!   behind `horizon_weights` (opt-in); the default lib suite is untouched
//!   (pinned in-module, not re-asserted here).
//! - **G4**: zero-alloc pinned in-module (`TrackingAllocator`).
//! - **Quality-at-fixed-budget** (the promotion-relevant axis) lives
//!   CROSS-REPO on the C9 toy harness (riir-train `.issues/569` — the
//!   fixture's owner; consumed in place, never duplicated or retrained).
//!   Bench 883 records the numbers + both SHAs; this gate pins the
//!   modelless substrate's own laws.
//!
//! The `[[test]]` row in Cargo.toml names `horizon_weights` AND
//! `critical_interval_gate` in `required-features` (the Issue-808
//! green-zero class; the consumer seam lives inside `dllm_solver`, which
//! the second feature gates — the `renoise_ce_score_horizon` combined-gate
//! precedent).

#[path = "common/ab_timing.rs"]
mod ab_timing;

use ab_timing::best_of_us;
use katgpt_core::dllm_solver::{annealed_renoise_range, renoise_level_skippable};
use katgpt_core::{TimeAnnealRange, terminal_truncation_ceiling, truncated_w_mass_fraction};
use std::hint::black_box;
use std::time::Instant;

const T: f32 = 1.0;
const T_MIN: f32 = 0.02;

#[test]
fn g1_truncation_closed_forms_e2e() {
    // Round-trip across a dense eps sweep.
    for i in 1..256 {
        let eps = i as f32 / 256.0;
        let cut = terminal_truncation_ceiling(eps, T_MIN, T);
        let back = truncated_w_mass_fraction(cut, T_MIN, T);
        let rel = ((back - eps) / eps).abs();
        assert!(rel < 1e-5, "eps={eps}: cut={cut} back={back} rel={rel}");
    }
    // The paper's own numbers, through the PUBLIC surface.
    let paper_eps = truncated_w_mass_fraction(0.70, T_MIN, T);
    let want = (0.30f32 / 0.98).powi(2);
    assert!((paper_eps - want).abs() < 1e-6);
    assert!((paper_eps - 0.0937).abs() < 5e-4, "{paper_eps}");
    let cut = terminal_truncation_ceiling(want, T_MIN, T);
    assert!((cut - 0.70).abs() < 1e-6, "{cut}");
    // w(T) = 0 anchor through the public surface.
    assert_eq!(
        truncated_w_mass_fraction(T, T_MIN, T).to_bits(),
        0.0f32.to_bits()
    );
}

#[test]
fn g1_anneal_law_e2e() {
    let sch = TimeAnnealRange::DEFAULT;
    let total = 500usize;
    // Pre-anneal exact flat posture.
    let (lo, hi) = sch.range_at(0, total);
    assert_eq!((lo, hi), (0.02, 0.98));
    let (lo, hi) = sch.range_at(349, total);
    assert_eq!((lo, hi), (0.02, 0.98), "last pre-anneal iter");
    // Terminal exact annealed posture + monotone extension.
    let (lo, hi) = sch.range_at(total - 1, total);
    assert_eq!((lo, hi), (0.02, 0.70));
    let (lo, hi) = sch.range_at(total + 77, total);
    assert_eq!((lo, hi), (0.02, 0.70));
    // Full-schedule invariants: fixed floor, ordered, non-increasing.
    let mut prev_hi = f32::INFINITY;
    for iter in 0..total {
        let (lo, hi) = sch.range_at(iter, total);
        assert_eq!(lo, 0.02, "floor moves at {iter}");
        assert!(hi <= prev_hi && hi >= lo, "iter={iter} hi={hi}");
        prev_hi = hi;
    }
    // Determinism.
    for &iter in &[0usize, 400, total - 1] {
        let a = sch.range_at(iter, total);
        let b = sch.range_at(iter, total);
        assert_eq!(a.0.to_bits(), b.0.to_bits());
        assert_eq!(a.1.to_bits(), b.1.to_bits());
    }
    // Custom schedule honors caller fields.
    let custom = TimeAnnealRange {
        floor_frac: 0.05,
        ceil_start_frac: 0.9,
        ceil_end_frac: 0.4,
        anneal_frac: 0.5,
    };
    let (lo, hi) = custom.range_at(0, 20);
    assert_eq!((lo, hi), (0.05, 0.9));
    let (lo, hi) = custom.range_at(19, 20);
    assert_eq!((lo, hi), (0.05, 0.4));
}

#[test]
fn g1_dllm_consumer_seam_e2e() {
    let sch = TimeAnnealRange::DEFAULT;
    let sigma_max = 4.0f32;
    // σ scaling through the seam.
    let (lo, hi) = annealed_renoise_range(&sch, 0, 64, sigma_max);
    assert!((lo - 0.08).abs() < 1e-6);
    assert!((hi - 3.92).abs() < 1e-6);
    let (_, hi) = annealed_renoise_range(&sch, 63, 64, sigma_max);
    assert!((hi - 2.8).abs() < 1e-6);
    // VE→VP bridge: alpha(sigma) = 1/(1+sigma^2) documented on the seam —
    // the annealed ceiling maps to a VALID alpha in (0, 1).
    for &(iter, total) in &[(0usize, 64usize), (32, 64), (63, 64)] {
        let (_, hi) = annealed_renoise_range(&sch, iter, total, sigma_max);
        let alpha = 1.0 / (1.0 + hi * hi);
        assert!((0.0..1.0).contains(&alpha), "alpha({hi}) = {alpha}");
    }
    // Skippable predicate boundary.
    let eps = (0.30f32 / 0.98).powi(2);
    assert!(renoise_level_skippable(0.70, eps, T_MIN, T));
    assert!(!renoise_level_skippable(0.69, eps, T_MIN, T));
    // Skipping the whole annealed-away segment costs <= eps of the law's
    // mass — the corollary, measured through the seam's own predicate.
    let mass = truncated_w_mass_fraction(0.70, T_MIN, T);
    assert!(mass <= eps + 1e-6 && mass > 0.09, "{mass}");
}

#[test]
fn g2_latency_class_release_only() {
    let sch = TimeAnnealRange::DEFAULT;
    const BATCH: usize = 4096;

    // Arm A: the shipped schedule + truncation ceiling.
    let a_us = best_of_us(3, 12, || {
        let mut sink = 0.0f32;
        let t = Instant::now();
        for i in 0..BATCH {
            let (lo, hi) = sch.range_at(black_box(i), black_box(BATCH));
            sink += lo + hi;
            sink += terminal_truncation_ceiling(black_box(i as f32) * 0.0002, 0.02, 1.0);
        }
        black_box(sink);
        t.elapsed()
    });

    // Arm B: the STRONG baseline — hand-rolled clamp-lerp + sqrt, the
    // trivial arithmetic the schedule compiles down to.
    let b_us = best_of_us(3, 12, || {
        let mut sink = 0.0f32;
        let t = Instant::now();
        for i in 0..BATCH {
            let a = BATCH as f32 * 0.7;
            let denom = (BATCH as f32 - 1.0) - a;
            let p = ((i as f32 - a) / denom).clamp(0.0, 1.0);
            let hi = 0.98 + p * (0.70 - 0.98);
            let eps = i as f32 * 0.0002;
            let cut = 1.0 - 0.98 * eps.sqrt();
            sink += 0.02 + hi + cut;
        }
        black_box(sink);
        t.elapsed()
    });

    let a_ns = a_us * 1000.0 / BATCH as f64;
    let b_ns = b_us * 1000.0 / BATCH as f64;
    println!(
        "range_at+ceiling: {a_ns:.2} ns/op vs baseline {b_ns:.2} ns/op (x{:.2})",
        a_ns / b_ns
    );
    if cfg!(not(debug_assertions)) {
        assert!(a_ns < 50.0, "schedule must be ns-class: {a_ns:.2} ns/op");
        assert!(
            a_ns < 3.0 * b_ns,
            "schedule must be within 3x of trivial arithmetic: {a_ns:.2} vs {b_ns:.2}"
        );
    } else {
        println!("debug build — latency bars deferred to --release (standing rule)");
    }
}
