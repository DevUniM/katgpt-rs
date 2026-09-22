//! Seam-4 arms (Issue 841 §B-3).
//!
//! Every arm asserts a DISTINCTION rather than a value. The primitive refuses
//! by default — [`SnapshotId::UNVERSIONED`] is never fresh — so an arm that
//! only checks "this returned `None`" is satisfied by a guard that is not
//! wired at all, which is the shape seam 1's arms were built to avoid.

use std::cell::Cell;
use std::rc::Rc;

use super::*;
use crate::calibration_staleness::Staleness;
use crate::conformal::{
    ConformalIntervalCalibrator, DecayUnit, PointForecaster, PredictiveInterval, ResidualMode,
    ResidualRingBuffer,
};

/// A forecaster that COUNTS its calls, so "the forecast half was refused too"
/// is observable rather than asserted by reading the source.
struct CountingForecaster {
    value: f32,
    calls: Rc<Cell<usize>>,
}

impl PointForecaster for CountingForecaster {
    fn forecast_into(&mut self, _delay_state: &[f32], _h: usize, out: &mut f32) {
        self.calls.set(self.calls.get() + 1);
        *out = self.value;
    }
}

type Cal = ConformalIntervalCalibrator<CountingForecaster>;

fn counter() -> Rc<Cell<usize>> {
    Rc::new(Cell::new(0))
}

fn id(version: u64, byte: u8) -> SnapshotId {
    SnapshotId::new(version, [byte; 32])
}

fn calibrator(value: f32, calls: Rc<Cell<usize>>) -> Cal {
    ConformalIntervalCalibrator::new(
        CountingForecaster { value, calls },
        1,
        1,
        1,
        64,
        0.0,
        DecayUnit::Step,
        ResidualMode::Paper,
        false,
    )
}

/// Push a spread of residuals so the pool has a non-degenerate quantile.
fn fill(cal: &mut Cal, centre: f32) {
    for k in 0..32 {
        let spread = (k as f32 - 16.0) * 0.1;
        cal.update_residual(centre + spread, 0.0, 0, 1);
        cal.step();
    }
}

fn pool_len(bound: &SnapshotBound<Cal>) -> usize {
    bound
        .peek_unchecked()
        .residual_pool
        .channel_bucket(0, 0)
        .len()
}

/// A FRESH binding is bit-identical to the unbound calibrator. Without this
/// arm every other one is satisfied by a guard that refuses unconditionally.
#[test]
fn t1_a_fresh_binding_is_bit_identical_to_the_raw_read() {
    let a = id(7, 0xAA);

    let mut raw = calibrator(1.0, counter());
    fill(&mut raw, 0.5);
    let mut want = PredictiveInterval::new(0.0, 0.0, 0.0, 0.1);
    raw.interval_from_point_into(2.0, 0, 1, 0.1, &mut want);

    let mut cal = calibrator(1.0, counter());
    fill(&mut cal, 0.5);
    let bound = cal.bound_to(a);
    let mut got = PredictiveInterval::new(0.0, 0.0, 0.0, 0.1);
    assert_eq!(
        bound.interval_from_point_into_checked(a, 2.0, 0, 1, 0.1, &mut got),
        Some(())
    );

    assert_eq!(got.lower.to_bits(), want.lower.to_bits());
    assert_eq!(got.point.to_bits(), want.point.to_bits());
    assert_eq!(got.upper.to_bits(), want.upper.to_bits());
}

/// A refusal leaves `out` UNTOUCHED. A neutral write would be a zero-width
/// interval at the point forecast — the most confident answer available, in
/// the one situation where no answer is warranted.
#[test]
fn t2_a_refused_read_does_not_write_a_maximally_confident_interval() {
    let fitted = id(7, 0xAA);
    let mut cal = calibrator(1.0, counter());
    fill(&mut cal, 0.5);
    let bound = cal.bound_to(fitted);

    let sentinel = PredictiveInterval::new(-99.0, -98.0, -97.0, 0.42);
    let mut out = sentinel;
    assert_eq!(
        bound.interval_from_point_into_checked(id(8, 0xAA), 2.0, 0, 1, 0.1, &mut out),
        None,
        "a moved generation must refuse"
    );
    assert_eq!(out, sentinel, "the refusal wrote into `out`");

    let mut live = sentinel;
    assert_eq!(
        bound.interval_from_point_into_checked(fitted, 2.0, 0, 1, 0.1, &mut live),
        Some(())
    );
    assert_ne!(live, sentinel);
}

/// The seam's reason to exist: the WRITE half refuses, and the pool is
/// provably not grown. Seams 1-3 have no arm of this shape because they guard
/// pure reads — nothing there can accumulate.
#[test]
fn t3_the_write_half_refuses_and_the_pool_does_not_grow() {
    let fitted = id(7, 0xAA);
    let mut cal = calibrator(1.0, counter());
    fill(&mut cal, 0.5);
    let mut bound = cal.bound_to(fitted);
    let before = pool_len(&bound);

    assert_eq!(
        bound.update_residual_checked(id(8, 0xAA), 9.0, 0.0, 0, 1),
        None
    );
    assert_eq!(pool_len(&bound), before, "a refused write still pushed");

    assert_eq!(
        bound.update_residual_checked(fitted, 9.0, 0.0, 0, 1),
        Some(())
    );
    assert_eq!(pool_len(&bound), before + 1);
}

/// The worked case the module docs describe: an UNGUARDED pool that keeps
/// accumulating across a swap converges on a distribution describing NEITHER
/// model, and nothing about the pool afterwards reveals it.
#[test]
fn t4_an_unguarded_pool_mixes_two_models_and_the_guard_refuses_instead() {
    let alpha = 0.1_f32;

    let mut mixed = calibrator(0.0, counter());
    fill(&mut mixed, 1.0);
    fill(&mut mixed, -1.0); // the swap nobody told the pool about
    let mut got = PredictiveInterval::new(0.0, 0.0, 0.0, alpha);
    mixed.interval_from_point_into(0.0, 0, 1, alpha, &mut got);

    let mut pure_b = calibrator(0.0, counter());
    fill(&mut pure_b, -1.0);
    let mut want_b = PredictiveInterval::new(0.0, 0.0, 0.0, alpha);
    pure_b.interval_from_point_into(0.0, 0, 1, alpha, &mut want_b);

    assert!(
        got.half_width() > want_b.half_width() * 1.5,
        "the mixture was expected to be visibly inflated: mixed {} vs live {}",
        got.half_width(),
        want_b.half_width()
    );
    assert!(got.lower.is_finite() && got.upper.is_finite());

    let a = id(1, 0xAA);
    let b = id(2, 0xBB);
    let mut cal = calibrator(0.0, counter());
    fill(&mut cal, 1.0);
    let mut bound = cal.bound_to(a);
    for _ in 0..32 {
        assert_eq!(bound.update_residual_checked(b, -1.0, 0.0, 0, 1), None);
    }
    let mut guarded = PredictiveInterval::new(0.0, 0.0, 0.0, alpha);
    assert_eq!(
        bound.interval_from_point_into_checked(a, 0.0, 0, 1, alpha, &mut guarded),
        Some(()),
        "the pre-swap binding is still readable at its OWN identity"
    );
    assert!(
        guarded.half_width() < got.half_width(),
        "the guarded pool must not have absorbed the second model"
    );
}

/// `None` is a third state and must not collapse to `false`. Two-sided: the
/// same observation is `Some(true)` on a fresh binding.
#[test]
fn t5_coverage_violation_none_is_not_a_calibrated_non_surprise() {
    let fitted = id(3, 0x11);
    let mut cal = calibrator(0.0, counter());
    fill(&mut cal, 0.0);
    let mut bound = cal.bound_to(fitted);

    assert_eq!(
        bound.coverage_violation_checked(fitted, 1000.0, 0, 1, 0.1),
        Some(true),
        "a wild observation is a violation while the binding is fresh"
    );
    assert_eq!(
        bound.coverage_violation_checked(fitted, 0.0, 0, 1, 0.1),
        Some(false),
        "an ordinary observation is not"
    );
    assert_eq!(
        bound.coverage_violation_checked(id(4, 0x11), 1000.0, 0, 1, 0.1),
        None,
        "a stale binding says `cannot tell`, which is neither of the above"
    );
}

/// The cold start refuses, and the verdict names the repair (wire a counter),
/// not a refit.
#[test]
fn t6_an_unwired_call_site_is_unversioned_not_stale() {
    let mut cal = calibrator(0.0, counter());
    fill(&mut cal, 0.0);
    let bound = cal.bound_to(SnapshotId::UNVERSIONED);
    let mut out = PredictiveInterval::new(0.0, 0.0, 0.0, 0.1);
    assert_eq!(
        bound.interval_from_point_into_checked(id(9, 0x22), 0.0, 0, 1, 0.1, &mut out),
        None
    );
    assert_eq!(bound.staleness(id(9, 0x22)), Staleness::Unversioned);
    assert_eq!(
        bound.staleness(SnapshotId::UNVERSIONED),
        Staleness::Unversioned,
        "0-vs-0 must not read as Fresh"
    );
}

/// A swap that forgot to bump is a CALLER BUG and keeps its own verdict —
/// pooling it with an ordinary stale pool sends the reader to refit something
/// that is not the problem.
#[test]
fn t7_weights_moved_while_the_generation_held_is_its_own_verdict() {
    let mut cal = calibrator(0.0, counter());
    fill(&mut cal, 0.0);
    let mut bound = cal.bound_to(id(5, 0xAA));

    assert_eq!(bound.staleness(id(5, 0xBB)), Staleness::CommitmentMoved);
    assert_eq!(bound.staleness(id(6, 0xAA)), Staleness::VersionMoved);
    assert_eq!(
        bound.update_residual_checked(id(5, 0xBB), 1.0, 0.0, 0, 1),
        None
    );
}

/// The forecast half is refused too — asserted by COUNTING the forecaster's
/// calls, so "we skipped the push" cannot pass for "we skipped the call".
#[test]
fn t8_a_refused_observe_never_consults_the_wrapped_forecaster() {
    let calls = counter();
    let fitted = id(2, 0x33);
    let mut cal = calibrator(0.25, Rc::clone(&calls));
    fill(&mut cal, 0.0);
    let mut bound = cal.bound_to(fitted);
    let at_entry = calls.get();

    assert_eq!(
        bound.observe_and_update_checked(id(3, 0x33), 1.0, &[], 0, 1),
        None
    );
    assert_eq!(
        calls.get(),
        at_entry,
        "the wrapped forecaster ran under a binding that had already moved"
    );

    assert_eq!(
        bound.observe_and_update_checked(fitted, 1.0, &[], 0, 1),
        Some(())
    );
    assert_eq!(
        calls.get(),
        at_entry + 1,
        "the fresh path must still forecast"
    );
}

/// The recency clock advances only while fresh — ages are meaningful only
/// relative to pushes that were allowed.
#[test]
fn t9_the_recency_clock_advances_only_on_a_fresh_binding() {
    let fitted = id(4, 0x44);
    let mut bound = calibrator(0.0, counter()).bound_to(fitted);
    let t0 = bound.peek_unchecked().tick();

    assert_eq!(bound.step_checked(id(5, 0x44)), None);
    assert_eq!(bound.peek_unchecked().tick(), t0, "a refused step ticked");

    assert_eq!(bound.step_checked(fitted), Some(()));
    assert_eq!(bound.peek_unchecked().tick(), t0 + 1);
}

/// A refit restores service AND re-arms the one-time warning, so a head that
/// goes stale twice warns twice.
#[test]
fn t10_a_real_refit_restores_service_and_rearms_the_warning() {
    let a = id(1, 0xA1);
    let b = id(2, 0xB2);
    let mut cal = calibrator(0.0, counter());
    fill(&mut cal, 0.0);
    let mut bound = cal.bound_to(a);

    assert_eq!(bound.update_residual_checked(b, 1.0, 0.0, 0, 1), None);
    assert!(bound.has_warned());

    // The refit is what licenses the rebind: drop the old model's errors,
    // then re-accumulate under the new identity.
    bound.refit_with(b, |c| {
        c.residual_pool = ResidualRingBuffer::new(1, 1, 64);
        fill(c, -1.0);
    });
    assert!(!bound.has_warned(), "rebind must re-arm the latch");
    assert_eq!(bound.update_residual_checked(b, 1.0, 0.0, 0, 1), Some(()));
    assert_eq!(bound.staleness(a), Staleness::VersionMoved);
}

/// `peek_unchecked` is the escape hatch and is NOT the guarded path — pinned
/// so a later reader cannot confuse the two.
#[test]
fn t11_peek_unchecked_bypasses_the_guard_by_design() {
    let mut cal = calibrator(0.0, counter());
    fill(&mut cal, 0.0);
    let bound = cal.bound_to(id(1, 0x55));
    let mut out = PredictiveInterval::new(0.0, 0.0, 0.0, 0.1);
    assert_eq!(
        bound.interval_from_point_into_checked(id(2, 0x55), 0.0, 0, 1, 0.1, &mut out),
        None
    );
    bound
        .peek_unchecked()
        .interval_from_point_into(0.0, 0, 1, 0.1, &mut out);
    assert!(out.upper > out.lower);
}
