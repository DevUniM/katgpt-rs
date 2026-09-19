//! GOAT gate — seam 4 of 4, the conformal calibrator at the freeze/thaw seam
//! (Issue 841 §B-3).
//!
//! ```bash
//! cargo bench -p katgpt-core --features calibration_staleness \
//!     --bench bench_841_conformal_staleness_seam_goat
//! # G4 needs an allocator in the profile:
//! cargo bench -p katgpt-core --features calibration_staleness,alloc_tracking \
//!     --bench bench_841_conformal_staleness_seam_goat
//! ```
//!
//! ⛔ **Why this seam owes its OWN gate rather than riding Bench 841's.** The
//! first three seams guard a READ of a pure function — a per-head scale, a
//! Platt pair, a verifier threshold — so `Bench 841` measures a guard against
//! the `apply` it fronts and that is the whole cost model. This one also
//! guards a **WRITE**: a [`ConformalIntervalCalibrator`] *grows* its
//! calibration one residual at a time, so a swap that nobody guards does not
//! merely make the next read stale, it **contaminates the pool** — and the
//! contamination HEALS into something that looks freshly fitted and describes
//! neither model. No count, no commitment and no coverage readout can see
//! that afterwards. G5 measures it.
//!
//! **G1 correctness** — both sides of the predicate at THIS seam, read AND
//! write. A guard that only ever refuses is as useless as one that only ever
//! admits, and the write half adds a claim the read half cannot make: a
//! refused push must leave the pool's length unchanged.
//!
//! **G2 perf** — the guard's per-call cost against the
//! `interval_from_point_into` it sits in front of. An ABSOLUTE budget
//! (best-of-N minimum), not an A/B ratio: AGENTS.md § *A ratio of two
//! SEQUENTIALLY-timed arms measures the BOX*.
//!
//! **G3 no-regression** — the admitted path is bit-identical to the unguarded
//! one over a swept input grid, on all three interval fields.
//!
//! **G4 alloc-free** — zero allocations over mixed fresh/stale read AND write
//! calls. Gated per the Issue-741 rule; prints a LOUD skip rather than a
//! silent pass when the profile carries no allocator.
//!
//! **G5 the claim** — the modelless quality gate, and the one that makes the
//! seam worth wiring. Three arms over the SAME swap: unguarded (emits
//! well-formed intervals that **under-cover**), guarded (emits none), and
//! guarded-then-refit (emits, and covers at nominal). The guard's own
//! contribution is the middle column's **zero**; the outer two are what give
//! that zero a size.

use std::hint::black_box;
use std::time::Instant;

use katgpt_core::calibration_staleness::{SnapshotId, Staleness};
use katgpt_core::conformal::{
    ConformalIntervalCalibrator, DecayUnit, PointForecaster, PredictiveInterval, ResidualMode,
    ResidualRingBuffer,
};

#[cfg(any(debug_assertions, feature = "alloc_tracking"))]
#[global_allocator]
static BENCH_ALLOC: katgpt_core::alloc::TrackingAllocator = katgpt_core::alloc::TrackingAllocator;

const C_A: [u8; 32] = [0xA5; 32];
const C_B: [u8; 32] = [0x5A; 32];

/// 90% two-tailed interval.
const ALPHA: f32 = 0.10;
/// Pool capacity. Deliberately 2x the per-phase push count, so an unguarded
/// second phase produces a genuine 50/50 MIXTURE rather than simply
/// overwriting the first model out of the ring.
const CAPACITY: usize = 512;
const PER_PHASE: usize = 256;
/// Model A's errors are narrow; model B's are 10x wider. The direction is
/// chosen deliberately: the mixture then sits BELOW the live model's true
/// quantile, i.e. it UNDER-covers, which is the dangerous direction. A
/// wide-then-narrow swap over-covers and merely wastes width.
const SPREAD_A: f32 = 0.1;
const SPREAD_B: f32 = 1.0;

/// A zero point forecast — the residual pool is the whole subject here.
struct ZeroForecaster;

impl PointForecaster for ZeroForecaster {
    fn forecast_into(&mut self, _delay_state: &[f32], _h: usize, out: &mut f32) {
        *out = 0.0;
    }
}

type Cal = ConformalIntervalCalibrator<ZeroForecaster>;

fn calibrator() -> Cal {
    ConformalIntervalCalibrator::new(
        ZeroForecaster,
        1,
        1,
        1,
        CAPACITY,
        0.0,
        DecayUnit::Step,
        ResidualMode::Paper,
        false,
    )
}

/// Deterministic draws. A seeded `Rng`, never the unseeded thread-local
/// global — AGENTS.md § `global_rng_gate`.
fn rng(seed: u64) -> fastrand::Rng {
    fastrand::Rng::with_seed(seed)
}

fn draw(r: &mut fastrand::Rng, spread: f32) -> f32 {
    (r.f32() * 2.0 - 1.0) * spread
}

/// Best-of-`rounds` minimum nanoseconds per call. The MINIMUM, because a
/// loaded box can only make a round slower.
fn best_of_ns(rounds: usize, iters: usize, mut f: impl FnMut() -> f32) -> f64 {
    let mut best = f64::INFINITY;
    for _ in 0..rounds {
        let t = Instant::now();
        let mut acc = 0.0_f32;
        for _ in 0..iters {
            acc += f();
        }
        let ns = t.elapsed().as_nanos() as f64 / iters as f64;
        // Issue 855: a loop whose result is discarded is a loop LLVM may
        // delete, and the ceiling is then satisfied by nothing running.
        assert!(acc.is_finite(), "the measured loop was optimised away");
        assert!(ns > 0.0, "0 ns over {iters} iterations — the loop vanished");
        black_box(acc);
        best = best.min(ns);
    }
    best
}

/// Empirical coverage of `interval` over `n` fresh draws from model B.
fn coverage(interval: &PredictiveInterval, n: usize, seed: u64) -> f64 {
    let mut r = rng(seed);
    let hits = (0..n)
        .filter(|_| interval.contains(draw(&mut r, SPREAD_B)))
        .count();
    hits as f64 / n as f64
}

fn main() {
    let mut failures: Vec<String> = Vec::new();
    println!("── Bench 841 — seam 4: the conformal calibrator at the freeze/thaw seam ──\n");

    let a = SnapshotId::new(4, C_A);
    let b = SnapshotId::new(5, C_B);

    // ── G1: both sides of the predicate, read AND write ────────────────────
    let mut cal = calibrator();
    let mut r = rng(0xC0FFEE);
    for _ in 0..PER_PHASE {
        cal.update_residual(draw(&mut r, SPREAD_A), 0.0, 0, 1);
        cal.step();
    }
    let mut bound = cal.bound_to(a);
    let len0 = bound
        .peek_unchecked()
        .residual_pool
        .channel_bucket(0, 0)
        .len();

    let mut out = PredictiveInterval::new(0.0, 0.0, 0.0, ALPHA);
    let g1_fresh_read = bound
        .interval_from_point_into_checked(a, 0.0, 0, 1, ALPHA, &mut out)
        .is_some();
    let sentinel = PredictiveInterval::new(-99.0, -98.0, -97.0, 0.42);
    let mut untouched = sentinel;
    let g1_stale_read = bound
        .interval_from_point_into_checked(b, 0.0, 0, 1, ALPHA, &mut untouched)
        .is_none()
        && untouched == sentinel;
    let g1_stale_write = bound.update_residual_checked(b, 9.0, 0.0, 0, 1).is_none()
        && bound
            .peek_unchecked()
            .residual_pool
            .channel_bucket(0, 0)
            .len()
            == len0;
    let g1_fresh_write = bound.update_residual_checked(a, 0.0, 0.0, 0, 1).is_some()
        && bound
            .peek_unchecked()
            .residual_pool
            .channel_bucket(0, 0)
            .len()
            == len0 + 1;
    let g1_unbumped = bound.staleness(SnapshotId::new(4, C_B)) == Staleness::CommitmentMoved;
    let g1_unversioned = bound.staleness(SnapshotId::UNVERSIONED) == Staleness::Unversioned;
    let g1 = g1_fresh_read
        && g1_stale_read
        && g1_stale_write
        && g1_fresh_write
        && g1_unbumped
        && g1_unversioned;
    println!(
        "G1 correctness   fresh_read={g1_fresh_read} stale_read_refuses_and_leaves_out={g1_stale_read} \
         stale_write_refuses_and_pool_unchanged={g1_stale_write} fresh_write_lands={g1_fresh_write} \
         unbumped={g1_unbumped} unversioned={g1_unversioned}  → {}",
        verdict(g1)
    );
    if !g1 {
        failures.push("G1: the predicate does not hold on all six arms".into());
    }

    // ── G3: the admitted path is bit-identical to the unguarded one ────────
    let mut raw = calibrator();
    let mut r = rng(0xC0FFEE);
    for _ in 0..PER_PHASE {
        raw.update_residual(draw(&mut r, SPREAD_A), 0.0, 0, 1);
        raw.step();
    }
    raw.update_residual(0.0, 0.0, 0, 1); // mirror G1's admitted write
    let mut g3 = true;
    let mut n_swept = 0_usize;
    for i in 0..=1000_u32 {
        let point = i as f32 / 100.0 - 5.0;
        let mut want = PredictiveInterval::new(0.0, 0.0, 0.0, ALPHA);
        raw.interval_from_point_into(point, 0, 1, ALPHA, &mut want);
        let mut got = PredictiveInterval::new(0.0, 0.0, 0.0, ALPHA);
        let admitted = bound
            .interval_from_point_into_checked(a, point, 0, 1, ALPHA, &mut got)
            .is_some();
        n_swept += 1;
        let same = got.lower.to_bits() == want.lower.to_bits()
            && got.point.to_bits() == want.point.to_bits()
            && got.upper.to_bits() == want.upper.to_bits();
        if !(admitted && same) {
            g3 = false;
            break;
        }
    }
    println!(
        "G3 no-regression bit-identical on all three fields over {n_swept} swept points  → {}",
        verdict(g3)
    );
    if !g3 {
        failures.push("G3: the guard changed an interval it admitted".into());
    }

    // ── G5: the claim — three arms over the SAME swap ──────────────────────
    let nominal = 1.0 - ALPHA as f64;
    const N_EVAL: usize = 100_000;

    // (i) UNGUARDED — keep pushing model B's residuals into model A's pool.
    let mut mixed = calibrator();
    let mut r = rng(0xC0FFEE);
    for _ in 0..PER_PHASE {
        mixed.update_residual(draw(&mut r, SPREAD_A), 0.0, 0, 1);
        mixed.step();
    }
    let mut rb = rng(0xBEEF);
    for _ in 0..PER_PHASE {
        mixed.update_residual(draw(&mut rb, SPREAD_B), 0.0, 0, 1);
        mixed.step();
    }
    let mut mixed_iv = PredictiveInterval::new(0.0, 0.0, 0.0, ALPHA);
    mixed.interval_from_point_into(0.0, 0, 1, ALPHA, &mut mixed_iv);
    let mixed_cov = coverage(&mixed_iv, N_EVAL, 0x5EED);

    // (ii) GUARDED — the same pushes, refused; count what got emitted.
    let mut cal2 = calibrator();
    let mut r = rng(0xC0FFEE);
    for _ in 0..PER_PHASE {
        cal2.update_residual(draw(&mut r, SPREAD_A), 0.0, 0, 1);
        cal2.step();
    }
    let mut guarded = cal2.bound_to(a);
    let mut rb = rng(0xBEEF);
    let mut refused_writes = 0_usize;
    for _ in 0..PER_PHASE {
        if guarded
            .update_residual_checked(b, draw(&mut rb, SPREAD_B), 0.0, 0, 1)
            .is_none()
        {
            refused_writes += 1;
        }
    }
    let mut emitted = 0_usize;
    let mut sink = PredictiveInterval::new(0.0, 0.0, 0.0, ALPHA);
    for _ in 0..PER_PHASE {
        if guarded
            .interval_from_point_into_checked(b, 0.0, 0, 1, ALPHA, &mut sink)
            .is_some()
        {
            emitted += 1;
        }
    }

    // (iii) REFIT — the repair the refusal asks for.
    let mut rb = rng(0xBEEF);
    guarded.refit_with(b, |c| {
        c.residual_pool = ResidualRingBuffer::new(1, 1, CAPACITY);
        for _ in 0..PER_PHASE {
            c.update_residual(draw(&mut rb, SPREAD_B), 0.0, 0, 1);
            c.step();
        }
    });
    let mut refit_iv = PredictiveInterval::new(0.0, 0.0, 0.0, ALPHA);
    let refit_ok = guarded
        .interval_from_point_into_checked(b, 0.0, 0, 1, ALPHA, &mut refit_iv)
        .is_some();
    let refit_cov = coverage(&refit_iv, N_EVAL, 0x5EED);

    // The bars. The middle column is the guard's own contribution; the outer
    // two are what give its zero a size, and each is asserted separately so a
    // reader can see WHICH claim moved.
    const MIN_DEFICIT: f64 = 0.05; // the hazard must be real, not a rounding edge
    const REFIT_TOL: f64 = 0.03;
    let deficit = nominal - mixed_cov;
    let g5_hazard = deficit >= MIN_DEFICIT;
    let g5_silent = mixed_iv.lower.is_finite() && mixed_iv.upper.is_finite();
    let g5_guard = emitted == 0 && refused_writes == PER_PHASE;
    let g5_refit = refit_ok && (refit_cov - nominal).abs() <= REFIT_TOL;
    let g5 = g5_hazard && g5_silent && g5_guard && g5_refit;
    println!(
        "G5 the claim     unguarded: [{:.3}, {:.3}] emitted, coverage {:.1}% vs {:.0}% nominal \
         (deficit {:.1} pts, bar >= {:.1})",
        mixed_iv.lower,
        mixed_iv.upper,
        mixed_cov * 100.0,
        nominal * 100.0,
        deficit * 100.0,
        MIN_DEFICIT * 100.0,
    );
    println!(
        "                 guarded:   {emitted} interval(s) emitted, {refused_writes} of {PER_PHASE} \
         post-swap writes refused"
    );
    println!(
        "                 refit:     [{:.3}, {:.3}], coverage {:.1}% (|Δ| <= {:.1} pts)  → {}",
        refit_iv.lower,
        refit_iv.upper,
        refit_cov * 100.0,
        REFIT_TOL * 100.0,
        verdict(g5)
    );
    println!(
        "                 ⛔ the unguarded interval is WELL-FORMED and finite — that is the point: \
         nothing about it reads as broken."
    );
    if !g5 {
        failures.push(format!(
            "G5: hazard={g5_hazard} well_formed={g5_silent} guard_emitted_none={g5_guard} \
             refit_restores={g5_refit}"
        ));
    }

    // ── G2: absolute budget ────────────────────────────────────────────────
    const ROUNDS: usize = 9;
    const ITERS_GUARD: usize = 200_000;
    // The quantile read is O(pool), i.e. ~257 elements per call here, so it
    // needs far fewer iterations than the 32-byte compare beside it.
    const ITERS_WORK: usize = 20_000;

    // ⛔ The two interval arms are shaped IDENTICALLY — same `out`
    // construction, same `black_box`ed point, same return — and only the
    // guard differs. The first version of this gate wrote the unguarded arm
    // into an `out` hoisted ABOVE the loop and the guarded one into a local,
    // and measured 5800 vs 15657 ns/call: a 2.70x "guard cost" for a 2.3 ns
    // compare. That figure was a measurement of the two loop bodies' shapes,
    // not of the guard, and it is exactly the confound AGENTS.md § *A ratio
    // of two SEQUENTIALLY-timed arms measures the BOX* asks to be removed
    // before a ratio is read as a cost.
    let work_ns = best_of_ns(ROUNDS, ITERS_WORK, || {
        let mut o = PredictiveInterval::new(0.0, 0.0, 0.0, ALPHA);
        bound
            .peek_unchecked()
            .interval_from_point_into(black_box(0.6), 0, 1, ALPHA, &mut o);
        o.upper
    });
    let checked_ns = best_of_ns(ROUNDS, ITERS_WORK, || {
        let mut o = PredictiveInterval::new(0.0, 0.0, 0.0, ALPHA);
        match bound.interval_from_point_into_checked(black_box(a), 0.6, 0, 1, ALPHA, &mut o) {
            Some(()) => o.upper,
            None => 0.0,
        }
    });
    let guard_ns = best_of_ns(ROUNDS, ITERS_GUARD, || {
        match bound.staleness(black_box(a)) {
            Staleness::Fresh => 1.0,
            _ => 0.0,
        }
    });

    // TWO budgets, because they answer different questions and the second is
    // the one a caller pays. The isolated guard against the work it fronts is
    // the seam-1..3 figure; the END-TO-END guarded call against the same call
    // unguarded is what wiring this seam actually costs.
    const BUDGET_RATIO: f64 = 1.0;
    const END_TO_END_BUDGET: f64 = 1.25;
    let ratio = guard_ns / work_ns.max(f64::MIN_POSITIVE);
    let e2e = checked_ns / work_ns.max(f64::MIN_POSITIVE);
    let g2_guard = ratio <= BUDGET_RATIO;
    let g2_e2e = e2e <= END_TO_END_BUDGET;
    let g2 = g2_guard && g2_e2e;
    println!(
        "\nG2 perf          guard={guard_ns:.3} ns/call  interval_from_point={work_ns:.1} ns/call  \
         checked_end_to_end={checked_ns:.1} ns/call"
    );
    println!(
        "                 guard/work={ratio:.5} (budget <= {BUDGET_RATIO:.2})  \
         checked/work={e2e:.4} (budget <= {END_TO_END_BUDGET:.2})  → {}",
        verdict(g2)
    );
    println!(
        "                 best-of-{ROUNDS} minimum over {ITERS_GUARD}/{ITERS_WORK} iters/round; \
         the minimum is the load-robust statistic — record the box state beside it."
    );
    if !g2_guard {
        failures.push(format!(
            "G2: guard {guard_ns:.3} ns/call is {ratio:.5}x the quantile read it protects"
        ));
    }
    if !g2_e2e {
        failures.push(format!(
            "G2: the guarded call is {e2e:.4}x the unguarded one end to end"
        ));
    }

    // ── G4: allocation-free ────────────────────────────────────────────────
    #[cfg(any(debug_assertions, feature = "alloc_tracking"))]
    {
        katgpt_core::alloc::reset_alloc_stats();
        let mut acc = 0.0_f32;
        let mut o = PredictiveInterval::new(0.0, 0.0, 0.0, ALPHA);
        for i in 0..10_000 {
            let id = match i % 2 {
                0 => a,
                _ => b,
            };
            if bound
                .interval_from_point_into_checked(black_box(id), 0.6, 0, 1, ALPHA, &mut o)
                .is_some()
            {
                acc += o.upper;
            }
            let _ = bound.update_residual_checked(black_box(id), 0.01, 0.0, 0, 1);
        }
        black_box(acc);
        let (n_allocs, bytes) = katgpt_core::alloc::get_alloc_stats();
        let g4 = n_allocs == 0;
        println!(
            "G4 alloc-free    {n_allocs} alloc(s), {bytes} byte(s) over 10000 mixed fresh/stale \
             read+write calls  → {}",
            verdict(g4)
        );
        if !g4 {
            failures.push(format!("G4: {n_allocs} allocation(s) on the guard path"));
        }
    }
    #[cfg(not(any(debug_assertions, feature = "alloc_tracking")))]
    {
        println!(
            "G4 alloc-free    ⛔ NOT MEASURED — this profile compiles no allocator. \
             Re-run with `--features alloc_tracking`; a green run without it is not a G4 pass."
        );
    }

    println!();
    match failures.is_empty() {
        true => println!("✓ Bench 841 seam 4 PASSED — every measured gate holds"),
        false => {
            for f in &failures {
                println!("✗ {f}");
            }
            println!("\n✗ Bench 841 seam 4 FAILED — {} gate(s)", failures.len());
            std::process::exit(1);
        }
    }
}

fn verdict(ok: bool) -> &'static str {
    match ok {
        true => "PASS",
        false => "FAIL",
    }
}
