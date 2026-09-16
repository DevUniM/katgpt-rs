//! Calibrated ActionBridge — decision-level confidence calibration
//! (riir-ai Issue 964 C2; substrate: Issue 810, GOAT Bench 808).
//!
//! [`ActionBridge`](super::ActionBridge)'s `sigmoid_confidence` gates the
//! ABSTAIN threshold (`confidence < threshold` → suppress / hand off to the
//! CLARIFY fallback in riir-engine's `arg_runtime` Step 8), but a threshold
//! on an UNCALIBRATED confidence is a threshold on a number whose meaning is
//! proven nowhere: "0.8" is not known to mean "the chosen action succeeds
//! ~80% of the time". This module wraps the bridge with the Platt
//! calibrator so the ABSTAIN threshold becomes a statement about outcomes:
//!
//! 1. **observe** — record `(raw sigmoid confidence, action_succeeded)`
//!    whenever the outcome of a selected action is known (riir-engine's
//!    Step 9 `InfoOutcomeStatus` is the production signal).
//! 2. **refit** — off-hot-path deterministic 2-param Platt refit.
//! 3. **select_action_calibrated** — the winner is chosen on raw scores
//!    exactly as [`ActionBridge::select_action`] does; the reported
//!    confidence is the calibrated probability. Because one strictly
//!    monotone transform is applied to a shared score scale, the argmax is
//!    preserved EXACTLY — calibration never changes WHICH action wins, only
//!    what its confidence MEANS (and therefore whether it clears the
//!    threshold).
//!
//! # Contract
//!
//! - **Cold start is bit-identical**: identity params return the raw
//!   confidence unchanged (exact-value fast path), so a fresh wrapper makes
//!   the same selections AND the same ABSTAIN decisions as the bare bridge.
//! - **Argmax invariant**: selection is computed on raw scores; the fitted
//!   transform is strictly monotone (`w = 1/T > 0`), so the winner is
//!   identical before and after any refit — pinned by test, not just argued.
//! - **Latent-domain rules**: calibration is a local monotone transform on
//!   a confidence scalar; it never crosses a sync boundary and never feeds
//!   anti-cheat/replay paths.

use super::ActionBridge;
use crate::sigmoid_calibration::SigmoidGateCalibrator;

/// An [`ActionBridge`] whose `sigmoid_confidence` is calibrated against
/// recorded decision outcomes.
///
/// Generic over the same `A` (action-space size) and `D` (latent dim) as the
/// inner bridge. The calibrator is owned (single consumer); snapshot it via
/// [`Self::params`] + [`Self::commitment`] for freeze/thaw.
///
/// # Example
///
/// ```
/// use katgpt_core::ActionBridge;
/// use katgpt_core::bridge::calibrated::CalibratedActionBridge;
///
/// let inner = ActionBridge::<3, 2>::new([[1, 0], [0, 1], [-1, -1]], 0.6);
/// let mut bridge = CalibratedActionBridge::new(inner, 1024, 128);
///
/// let q = [5.0, 1.0];
/// let (action, raw_conf) = bridge.inner().select_action(&q);
/// // When the outcome is known: record (raw confidence, succeeded).
/// bridge.observe(raw_conf, true);
/// bridge.refit();
///
/// // Same winner; calibrated confidence (cold start: bit-identical bits).
/// let (a2, conf2) = bridge.select_action_calibrated(&q);
/// assert_eq!(a2, action);
/// assert!((0.0..1.0).contains(&conf2));
/// ```
pub struct CalibratedActionBridge<const A: usize, const D: usize> {
    inner: ActionBridge<A, D>,
    calibrator: SigmoidGateCalibrator,
}

impl<const A: usize, const D: usize> CalibratedActionBridge<A, D> {
    /// Wrap `inner` with an identity-calibrated gate.
    ///
    /// `capacity` / `min_obs` are the [`SigmoidGateCalibrator`] evidence
    /// window size and occupancy floor. Until `min_obs` pairs are observed
    /// and [`Self::refit`] moves the parameters, selections AND confidences
    /// are **bit-identical** to the bare bridge.
    pub fn new(inner: ActionBridge<A, D>, capacity: usize, min_obs: usize) -> Self {
        Self {
            inner,
            calibrator: SigmoidGateCalibrator::new(capacity, min_obs),
        }
    }

    /// Record one `(raw sigmoid confidence, action_succeeded)` pair.
    ///
    /// `raw_confidence` is the value the INNER bridge reported at selection
    /// time — not a previously calibrated output (the Platt map is fitted
    /// from raw sigmoid outputs). Zero-alloc, O(1).
    #[inline]
    pub fn observe(&mut self, raw_confidence: f32, action_succeeded: bool) {
        self.calibrator.observe(raw_confidence, action_succeeded);
    }

    /// Off-hot-path refit of the calibration parameters over the evidence
    /// window. Returns `true` when the parameters moved. Below `min_obs`
    /// occupancy this is a no-op and the gate stays bit-identical.
    pub fn refit(&mut self) -> bool {
        self.calibrator.refit()
    }

    /// Select the best action; report the CALIBRATED confidence.
    ///
    /// The winner is `inner.select_action`'s winner exactly (selection on
    /// raw scores; the monotone transform cannot reorder them — see the
    /// module doc). The confidence is `calibrator.apply(raw)` — identity
    /// (bit-identical) until a refit moves the parameters.
    #[inline]
    pub fn select_action_calibrated(&self, q_values: &[f32; D]) -> (usize, f32) {
        let (idx, raw) = self.inner.select_action(q_values);
        (idx, self.calibrator.apply(raw))
    }

    /// The ABSTAIN predicate on the CALIBRATED confidence:
    /// `p_cal < threshold` → suppress (hand off to the CLARIFY fallback).
    /// With calibrated p this is a statement about outcome probability, not
    /// about an uncalibrated score.
    #[inline]
    pub fn should_abstain(&self, calibrated_confidence: f32) -> bool {
        calibrated_confidence < self.inner.threshold()
    }

    /// Current parameters as `(T, b)` in `p_cal = sigmoid((logit(p) − b)/T)`.
    /// `T > 0` always (the monotonicity guard).
    pub fn params(&self) -> (f32, f32) {
        self.calibrator.params()
    }

    /// BLAKE3 commitment over the calibrator's versioned canonical bytes —
    /// freeze/thaw evidence for "which calibration produced these
    /// confidences".
    pub fn commitment(&self) -> [u8; 32] {
        self.calibrator.commitment()
    }

    /// Borrow the inner (uncalibrated) bridge — the source of the raw
    /// confidences [`Self::observe`] expects, and of the raw threshold.
    pub fn inner(&self) -> &ActionBridge<A, D> {
        &self.inner
    }

    /// Mutably borrow the inner bridge.
    pub fn inner_mut(&mut self) -> &mut ActionBridge<A, D> {
        &mut self.inner
    }

    /// Unwrap into the inner bridge (drops the evidence window).
    pub fn into_inner(self) -> ActionBridge<A, D> {
        self.inner
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn bridge() -> ActionBridge<3, 2> {
        ActionBridge::new([[1, 0], [0, 1], [-1, -1]], 0.6)
    }

    /// Cold start: selections AND confidences bit-identical to the bare
    /// bridge — the exact value, not a float twin.
    #[test]
    fn cold_start_is_bit_identical() {
        let calibrated = CalibratedActionBridge::new(bridge(), 64, 8);
        for i in 0..64u32 {
            let x = (i as f32 / 16.0) - 2.0;
            let q = [x, 0.5 - x];
            let (raw_idx, raw_conf) = calibrated.inner().select_action(&q);
            let (cal_idx, cal_conf) = calibrated.select_action_calibrated(&q);
            assert_eq!(raw_idx, cal_idx, "winner moved at q = {q:?}");
            assert_eq!(raw_conf.to_bits(), cal_conf.to_bits(), "q = {q:?}");
        }
    }

    /// Argmax invariant after a REAL refit: the winner never changes (the
    /// monotone transform cannot reorder one shared score scale).
    #[test]
    fn refit_never_changes_the_winner() {
        let mut calibrated = CalibratedActionBridge::new(bridge(), 256, 32);
        // Overconfident evidence: high confidences systematically fail.
        for i in 0..256 {
            let p = 0.02 + 0.96 * i as f32 / 255.0;
            calibrated.observe(p, p < 0.5);
        }
        assert!(calibrated.refit());
        let (t, _b) = calibrated.params();
        assert!(t > 0.0, "T must stay positive");

        for i in 0..512u32 {
            let x = (i as f32 / 128.0) - 2.0;
            let q = [x, 1.0 - x];
            let (raw_idx, _) = calibrated.inner().select_action(&q);
            let (cal_idx, cal_conf) = calibrated.select_action_calibrated(&q);
            assert_eq!(raw_idx, cal_idx, "winner moved at q = {q:?}");
            assert!((0.0..1.0).contains(&cal_conf));
        }
    }

    /// `should_abstain` compares against the inner bridge's threshold; at
    /// cold start it reproduces the bare bridge's ABSTAIN decisions exactly.
    #[test]
    fn abstain_predicate_matches_raw_at_cold_start() {
        let calibrated = CalibratedActionBridge::new(bridge(), 64, 8);
        for i in 0..64u32 {
            let x = (i as f32 / 16.0) - 2.0;
            let q = [x, 0.3];
            let (_, raw) = calibrated.inner().select_action(&q);
            let (_, cal) = calibrated.select_action_calibrated(&q);
            assert_eq!(
                calibrated.should_abstain(cal),
                raw < calibrated.inner().threshold(),
                "q = {q:?}"
            );
        }
    }

    /// Deterministic refit + commitment (the freeze/thaw evidence contract).
    #[test]
    fn refit_and_commitment_are_deterministic() {
        let fit = || {
            let mut c = CalibratedActionBridge::new(bridge(), 512, 64);
            for i in 0..512 {
                let p = 0.02 + 0.96 * i as f32 / 511.0;
                c.observe(p, p < 0.4);
            }
            assert!(c.refit());
            (c.params(), c.commitment())
        };
        assert_eq!(fit(), fit());
    }
}
