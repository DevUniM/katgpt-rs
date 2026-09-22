//! Seam 4 of 4 — the conformal calibrator at the freeze/thaw seam
//! (Issue 841 §B-3).
//!
//! The three seams before this one guard a READ: a per-head scale, a Platt
//! pair, a verifier threshold. Each is a pure function of its fitted
//! parameters, so a refusal costs exactly one call and nothing accumulates.
//!
//! ⛔ **This seam is different in kind, and the difference is the reason it
//! was kept for last.** A [`ConformalIntervalCalibrator`] does not only read
//! its calibration — it *grows* it, one residual at a time, through
//! [`update_residual`](ConformalIntervalCalibrator::update_residual). So there
//! are two failure modes here and only one of them is the class the first
//! three seams describe:
//!
//! - **READ after a swap** — an interval is emitted from residuals fitted
//!   against weights that no longer exist. Bad, visible in hindsight, and
//!   exactly the seam-1..3 shape.
//! - **WRITE across a swap** — post-swap residuals are pushed into a pre-swap
//!   pool. The pool becomes a **mixture of two models' error distributions**,
//!   and that is strictly worse than staleness, because it *heals*: after a
//!   ring-buffer's worth of new observations the pool looks freshly fitted and
//!   describes a distribution neither model has. No later check can see it —
//!   not `verify()`, not a commitment, not a coverage readout, because the
//!   empirical coverage of a mixture can sit at nominal while being wrong
//!   about both arms.
//!
//! A conformal interval's coverage guarantee rests on **exchangeability**
//! between the calibration residuals and the test residual. Swapping the
//! forecaster under a live pool breaks that premise silently, and the interval
//! keeps being emitted at full apparent confidence. Guarding only the read
//! would leave the pool being corrupted at full speed.
//!
//! ## What is bound to what
//!
//! ⚠ The identity that matters here is the one the **point forecaster** was
//! frozen under, not any hash of the residual pool. The pool is *derived* from
//! the forecaster's errors: hashing it would answer "were these residuals
//! corrupted", which is the question `StaticCalTable::verify` answers one seam
//! over, and not "do these residuals still describe the live model". Seam 2
//! records the same distinction for the same reason.
//!
//! ## Shape
//!
//! An **inherent** impl, not an extension trait — both types are this crate's,
//! so the orphan rule that forced a trait at seams 2 and 3 does not apply, and
//! a trait nobody can implement a second time is a trait that should not
//! exist. No shipped signature moved and no field was added:
//! [`ConformalIntervalCalibrator`] and every method on it are untouched, so a
//! default build is byte-identical. The guard is the opt-in
//! `calibration_staleness` flag; the calibrator stays default-on.
//!
//! ```ignore
//! let mut bound = calibrator.bound_to(store.snapshot_id());
//! // … per tick …
//! match bound.observe_and_update_checked(id, actual, &delay, ch, h) {
//!     Some(()) => {}
//!     None => refit_pool(),   // never "push anyway" — see above
//! }
//! ```

use crate::calibration_staleness::{SnapshotBound, SnapshotId};
use crate::conformal::{ConformalIntervalCalibrator, PointForecaster, PredictiveInterval};

impl<F: PointForecaster> ConformalIntervalCalibrator<F> {
    /// Bind this calibrator to the snapshot identity its residual pool was
    /// accumulated under.
    ///
    /// ⚠ This ASSERTS a fact the type cannot check: that the residuals in
    /// `self` came from *that* forecaster's errors. Calling it to silence a
    /// refusal re-attaches a contaminated pool under a fresh-looking identity
    /// — the same warning [`SnapshotBound::rebind`] carries, at the seam where
    /// it is easiest to reach for.
    #[inline]
    #[must_use]
    pub fn bound_to(self, fitted: SnapshotId) -> SnapshotBound<Self> {
        SnapshotBound::new(self, fitted)
    }
}

impl<F: PointForecaster> SnapshotBound<ConformalIntervalCalibrator<F>> {
    /// Guarded [`interval_from_point_into`](ConformalIntervalCalibrator::interval_from_point_into).
    ///
    /// `None` leaves `out` **untouched**. That is deliberate and is the one
    /// behaviour a caller must not paper over: a zero-width interval at the
    /// point forecast is not a degraded answer, it is a *maximally confident*
    /// one, and it is what `out` would hold if a refusal wrote a neutral
    /// value. Abstain, or refit.
    #[inline]
    pub fn interval_from_point_into_checked(
        &self,
        current: SnapshotId,
        point: f32,
        channel: usize,
        h: usize,
        alpha: f32,
        out: &mut PredictiveInterval,
    ) -> Option<()> {
        let cal = self.get(current)?;
        cal.interval_from_point_into(point, channel, h, alpha, out);
        Some(())
    }

    /// Guarded [`interval_into`](ConformalIntervalCalibrator::interval_into).
    /// `None` leaves `out` untouched — see
    /// [`interval_from_point_into_checked`](Self::interval_from_point_into_checked).
    #[inline]
    pub fn interval_into_checked(
        &mut self,
        current: SnapshotId,
        channel: usize,
        h: usize,
        alpha: f32,
        out: &mut PredictiveInterval,
    ) -> Option<()> {
        let cal = self.get_mut(current)?;
        cal.interval_into(channel, h, alpha, out);
        Some(())
    }

    /// Guarded [`coverage_violation`](ConformalIntervalCalibrator::coverage_violation).
    ///
    /// ⛔ `None` must not collapse to `false`. The 1-bit signal's two values
    /// are *covered* and *violated*; "we cannot say" is a third state, and
    /// folding it into `false` reports a stale pool as a calibrated
    /// non-surprise — the quietest possible way to lose the signal this
    /// function exists to produce.
    #[inline]
    pub fn coverage_violation_checked(
        &mut self,
        current: SnapshotId,
        actual: f32,
        channel: usize,
        h: usize,
        alpha: f32,
    ) -> Option<bool> {
        let cal = self.get_mut(current)?;
        Some(cal.coverage_violation(actual, channel, h, alpha))
    }

    /// Guarded [`update_residual`](ConformalIntervalCalibrator::update_residual)
    /// — the **write** half, and the one this seam exists for.
    ///
    /// A refusal here is not a lost datapoint, it is a *prevented* one: the
    /// residual being offered was produced by a model the pool has never seen,
    /// and mixing it in is the failure mode the module docs describe. Refit,
    /// or start a fresh pool.
    #[inline]
    pub fn update_residual_checked(
        &mut self,
        current: SnapshotId,
        actual: f32,
        forecast: f32,
        channel: usize,
        h: usize,
    ) -> Option<()> {
        let cal = self.get_mut(current)?;
        cal.update_residual(actual, forecast, channel, h);
        Some(())
    }

    /// Guarded [`observe_and_update`](ConformalIntervalCalibrator::observe_and_update).
    ///
    /// ⚠ The forecast half is refused too, not just the push. Forecasting
    /// through a bound calibrator whose identity has moved reads the *wrapped
    /// forecaster* — which is the thing that changed — so letting it run and
    /// only skipping the push would report a number from the new model under
    /// the old model's binding.
    #[inline]
    pub fn observe_and_update_checked(
        &mut self,
        current: SnapshotId,
        actual: f32,
        delay_state: &[f32],
        channel: usize,
        h: usize,
    ) -> Option<()> {
        let cal = self.get_mut(current)?;
        cal.observe_and_update(actual, delay_state, channel, h);
        Some(())
    }

    /// Guarded [`step`](ConformalIntervalCalibrator::step).
    ///
    /// ⚠ Present so a FRESH binding can still advance its recency clock — the
    /// guarded API must be usable on its own, or a caller keeps an unguarded
    /// handle beside it and the seam is decorative. A refusal skips the tick,
    /// which is correct: ages are only meaningful relative to pushes that
    /// were allowed.
    #[inline]
    pub fn step_checked(&mut self, current: SnapshotId) -> Option<()> {
        let cal = self.get_mut(current)?;
        cal.step();
        Some(())
    }
}

#[cfg(test)]
mod tests;
