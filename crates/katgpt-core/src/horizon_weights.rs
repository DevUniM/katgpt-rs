//! Remaining-horizon weighting — the (T−t) Fubini accumulation law and the
//! PFD closed-form `w(t)` schedule (Issue 875 T1 / Research 582).
//!
//! Source: *Probability-Flow Distillation: Exact Wasserstein Gradient Flow
//! for High-Fidelity 3D Generation* (arXiv:2605.09071), Theorem 1: under
//! linear drift `f(x,t) = a(t)·x` with stop-gradient, the expected
//! discrepancy of a uniformly-sampled-`t` partial integration equals the
//! Wasserstein gradient of a time-averaged functional weighted by
//!
//! ```text
//! w(t) = ½ (T−t) · g(t)² · c(t,0)²,    c(t,0) = exp(−∫₀ᵗ a(s) ds)
//! ```
//!
//! The `(T−t)` factor is a Fubini swap on the triangular integration
//! domain: averaging observations taken at uniformly sampled `t` over
//! `[0,T]` gives each partial integral effective weight `(T−s)` — MAXIMUM
//! at low noise (`t → 0`), decaying linearly to EXACTLY ZERO at `t = T`.
//! Corollary encoded here: skipping `t` near `T` is first-order lossless
//! (`w(T) = 0` — the zero-terminal-weight truncation).
//!
//! # Mechanism-distinct neighbors (the substrate-first vocabulary check)
//!
//! - [`crate::tether::horizon_decay`] (and the `hint_regret::memory`
//!   `r̂·σ(−λ·Δt)` family) is PAST-looking staleness fading — weight by
//!   time SINCE an observation. This module is FUTURE-looking — weight by
//!   the REMAINING horizon of an accumulation. Same word, opposite sign of
//!   information.
//! - `set_diffusion_schedule::PositionOffsetSchedule` decides WHERE (which
//!   position) to reveal next; this module decides HOW MUCH an observation
//!   at time `t` contributes to a time-averaged accumulation.
//! - `renoise_ce` averages its `k_draws` FLAT (`sum / k`); Issue 875 T2
//!   wires these weights into that average.
//!
//! # What ships
//!
//! - [`remaining_horizon_weight`] / [`remaining_horizon_weights`]: the
//!   normalized `(T−t)/T` generic law (pure arithmetic, any horizon).
//! - [`pfd_horizon_weight_at`] / [`pfd_horizon_weights`]: the exact closed
//!   form over a discrete uniform grid (cumulative trapezoid of `a`, one
//!   `exp` per grid point — the offline computation).
//! - [`HorizonWeightTable`]: the closed form frozen into a fixed
//!   `[f32; HORIZON_WEIGHT_GRID]` with a BLAKE3 commitment (the
//!   `katgpt-attn/static_cal.rs` `StaticCalTable` pattern — except this
//!   table is exact closed form, no calibration pass): O(1) nearest-grid
//!   lookup, cross-process reproducible, tamper-evident.
//!
//! # Gates (GOAT, per Issue 875 T5)
//!
//! - **G1** table vs closed-form recompute: bit-identical (`to_bits`) —
//!   pinned in-module (against both the grid fn and an independent f64
//!   oracle within tolerance) and e2e in the root gate
//!   `tests/bench_875_horizon_weights_goat.rs`.
//! - **G2** O(1) lookup vs per-call `exp` recompute (the STRONG baseline:
//!   caller-held cumulative integral) — the root gate via the shared
//!   `ab_timing` harness, median lookup/recompute ≤ 0.5 (≥ 2× faster).
//! - **G3** no-regression: opt-in, default-off — no default-path surface.
//! - **G4** fixed-size table, zero allocation on build and lookup (asserted
//!   under `debug_assertions`/`alloc_tracking` via `crate::alloc`).
//!
//! OPT-IN per the no-default-consumer rule: promotion to default waits for
//! the T2 consumer GOAT ((T−t)-weighted `renoise_ce` averaging).
//!
//! NaN policy: NaN inputs propagate through the pure functions (except
//! [`HorizonWeightTable::w_at_unit`], where the grid clamp sends NaN's
//! saturating cast to index 0 — documented there). This is a weight
//! schedule, not a sync-boundary value; callers on the sync path feed
//! clamped time fractions.

/// Fixed grid density for [`HorizonWeightTable`]. 64 points covers the
/// schedule shapes the PFD paper anneals over (`[0.02T, 0.98T] → [0.02T,
/// 0.70T]`) with nearest-grid lookup error well under the trapezoid
/// discretization error at those smoothness classes; consumers needing
/// other densities use the slice-based pure functions.
pub const HORIZON_WEIGHT_GRID: usize = 64;

/// Normalized remaining-horizon weight `(T−t)/T`, clamped to `[0, 1]`.
///
/// The pure Fubini law: how much an observation at time `t` contributes to
/// a time-averaged accumulation over `[0, T]` when `t` is sampled
/// uniformly. `t = 0` → 1.0 (max weight, low noise), `t = T` → exactly 0.
#[inline]
pub fn remaining_horizon_weight(t: f32, horizon: f32) -> f32 {
    debug_assert!(horizon > 0.0, "horizon must be positive");
    ((horizon - t) / horizon).clamp(0.0, 1.0)
}

/// Fill `out` with the normalized `(T−t)/T` weights over a UNIFORM grid
/// `t_i = T·i/(n−1)`, `i = 0..n` (the horizon itself cancels — the output
/// is dimensionless).
///
/// `out[n−1]` is EXACTLY `0.0` (the zero-terminal-weight corollary).
/// Requires `n ≥ 2`: a single-point grid has no interval to weight over.
pub fn remaining_horizon_weights(out: &mut [f32]) {
    let n = out.len();
    assert!(n >= 2, "remaining_horizon_weights needs n >= 2, got {n}");
    let last = (n - 1) as f32;
    for (i, slot) in out.iter_mut().enumerate() {
        *slot = 1.0 - i as f32 / last;
    }
    // Exact-zero terminal weight (+0.0, never −0.0): the truncation
    // corollary's anchor.
    out[n - 1] = 0.0;
}

/// The PFD closed form at a single point, given the caller-held cumulative
/// drift integral `A(t) = ∫₀ᵗ a(s) ds`:
///
/// ```text
/// w(t) = ½ (T−t) · g(t)² · exp(−2·A(t))      (c(t,0)² = exp(−2A))
/// ```
///
/// This is the STRONG per-call baseline the table's G2 gate races against:
/// one `exp` plus a handful of multiplies, with the integral already in
/// hand. Hot-path callers should hold the [`HorizonWeightTable`] instead.
///
/// The evaluation order here is pinned — [`pfd_horizon_weights`] calls this
/// function so the grid fill and the point form agree bit-for-bit.
#[inline]
pub fn pfd_horizon_weight_at(t: f32, horizon: f32, g_t: f32, a_integral_t: f32) -> f32 {
    0.5 * (horizon - t) * g_t * g_t * (-2.0 * a_integral_t).exp()
}

/// Fill `out` with the PFD closed form over a UNIFORM grid
/// `t_i = T·i/(n−1)`, from drift-diffusion schedules sampled at the same
/// grid points (`g[i] = g(t_i)`, `a[i] = a(t_i)`).
///
/// The cumulative drift integral is the left-to-right trapezoid (exact for
/// constant `a`; the deterministic accumulation order is pinned by the G1
/// bit-match test). `out[n−1]` is EXACTLY `0.0` — the `(T−t)` factor, not
/// a clamp. Requires `g.len() == a.len() == out.len()` and `n ≥ 2`.
pub fn pfd_horizon_weights(g: &[f32], a: &[f32], horizon: f32, out: &mut [f32]) {
    let n = out.len();
    assert!(n >= 2, "pfd_horizon_weights needs n >= 2, got {n}");
    assert_eq!(g.len(), n, "g schedule must match the output grid");
    assert_eq!(a.len(), n, "a schedule must match the output grid");
    let dt = horizon / (n - 1) as f32;
    let mut a_int = 0.0f32;
    for i in 0..n {
        if i > 0 {
            a_int += 0.5 * (a[i - 1] + a[i]) * dt;
        }
        let t = horizon * i as f32 / (n - 1) as f32;
        out[i] = pfd_horizon_weight_at(t, horizon, g[i], a_int);
    }
    out[n - 1] = 0.0;
}

/// The PFD closed-form schedule frozen into a fixed-size committed table
/// (the `StaticCalTable` pattern: exact closed form instead of a
/// calibration pass). Build once offline, [`verify`](Self::verify) on
/// load, O(1) nearest-grid lookups on the hot path.
///
/// G4: `[f32; HORIZON_WEIGHT_GRID]` — zero allocation on build and lookup.
///
/// ⛔ The commitment is the identity of the TABLE, not of the schedules:
/// `verify` proves the frozen weights were not tampered with, not that
/// they were built from the right `g`/`a` (mirrors
/// `StaticCalTable::commitment` being the table's identity, not the
/// weights'). Bind build provenance at the caller if that matters.
#[derive(Clone, Debug)]
pub struct HorizonWeightTable {
    w: [f32; HORIZON_WEIGHT_GRID],
    /// `1/horizon`, stored so lookup is multiply-round-index (no divide).
    inv_horizon: f32,
    commitment: [u8; 32],
}

impl HorizonWeightTable {
    /// Build from schedules sampled at the grid points and commit.
    ///
    /// Bit-identical to [`pfd_horizon_weights`] on the same inputs (G1:
    /// the build delegates to the pure function; the test pins it).
    pub fn build(
        g: &[f32; HORIZON_WEIGHT_GRID],
        a: &[f32; HORIZON_WEIGHT_GRID],
        horizon: f32,
    ) -> Self {
        assert!(
            horizon > 0.0 && horizon.is_finite(),
            "horizon must be positive and finite, got {horizon}"
        );
        let mut w = [0.0f32; HORIZON_WEIGHT_GRID];
        pfd_horizon_weights(g, a, horizon, &mut w);
        let mut table = Self {
            w,
            inv_horizon: 1.0 / horizon,
            commitment: [0u8; 32],
        };
        table.commit();
        table
    }

    /// Recompute the BLAKE3 commitment over the stored weights + grid
    /// scale. Deterministic, zero-alloc.
    pub fn commit(&mut self) {
        let mut hasher = blake3::Hasher::new();
        hasher.update(&self.inv_horizon.to_bits().to_le_bytes());
        hasher.update(bytemuck::cast_slice(&self.w));
        self.commitment.copy_from_slice(hasher.finalize().as_bytes());
    }

    /// Verify the stored commitment against the stored weights.
    pub fn verify(&self) -> bool {
        let mut probe = Self {
            w: self.w,
            inv_horizon: self.inv_horizon,
            commitment: [0u8; 32],
        };
        probe.commit();
        probe.commitment == self.commitment
    }

    /// O(1) nearest-grid lookup at absolute time `t` (same units the table
    /// was built with).
    #[inline]
    pub fn w_at(&self, t: f32) -> f32 {
        self.w_at_unit(t * self.inv_horizon)
    }

    /// O(1) nearest-grid lookup at normalized time `x = t/T ∈ [0, 1]`
    /// (the form zone-graph / per-tick consumers want: pass
    /// `tick / total_ticks`).
    ///
    /// NaN input saturates to index 0 (NaN fails the clamp's ordering and
    /// the saturating `as usize` cast lands at 0) — the max-weight end.
    /// Callers feeding unclamped external time should sanitize first.
    #[inline]
    pub fn w_at_unit(&self, x: f32) -> f32 {
        let x = x.clamp(0.0, 1.0);
        let idx = (x * (HORIZON_WEIGHT_GRID - 1) as f32 + 0.5) as usize;
        self.w[idx.min(HORIZON_WEIGHT_GRID - 1)]
    }

    /// The frozen weights; grid point `i` ↔ `t_i = T·i/(N−1)`.
    pub fn weights(&self) -> &[f32; HORIZON_WEIGHT_GRID] {
        &self.w
    }

    /// The BLAKE3 commitment over the frozen weights + grid scale.
    pub fn commitment(&self) -> &[u8; 32] {
        &self.commitment
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const T: f32 = 10.0;

    /// VE-flavored deterministic schedules: g increasing in t, positive
    /// drift a with a mild slope — the regime where all three factors of
    /// w(t) move.
    fn schedules(n: usize) -> (Vec<f32>, Vec<f32>) {
        let mut g = Vec::with_capacity(n);
        let mut a = Vec::with_capacity(n);
        for i in 0..n {
            let t = T * i as f32 / (n - 1) as f32;
            g.push(0.5 + 0.08 * t);
            a.push(0.25 + 0.01 * t);
        }
        (g, a)
    }

    #[test]
    fn generic_law_endpoints_monotone_mean_half() {
        let mut w = [0.0f32; 16];
        remaining_horizon_weights(&mut w);
        assert_eq!(w[0], 1.0);
        assert_eq!(w[15].to_bits(), 0.0f32.to_bits(), "terminal weight is exact +0.0");
        for i in 1..16 {
            assert!(
                w[i] <= w[i - 1],
                "generic law must be non-increasing, w[{i}]={}",
                w[i]
            );
        }
        // Uniform-grid mean of (1 − x) is exactly 1/2 up to f32 rounding.
        let mean = w.iter().sum::<f32>() / w.len() as f32;
        assert!((mean - 0.5).abs() < 1e-3, "Fubini mean {mean}");
        // Point form agrees with the grid form.
        for (i, &wi) in w.iter().enumerate() {
            let t = T * i as f32 / 15.0;
            let point = remaining_horizon_weight(t, T);
            assert!((point - wi).abs() <= 1e-6);
        }
    }

    #[test]
    fn zero_drift_reduces_to_half_remaining_horizon_g_squared() {
        let (g, _) = schedules(32);
        let a_zero = vec![0.0f32; 32];
        let mut w = [0.0f32; 32];
        pfd_horizon_weights(&g, &a_zero, T, &mut w);
        for i in 0..32 {
            let t = T * i as f32 / 31.0;
            // c(t,0) = exp(0) = 1 exactly; exp(-2*0.0) == 1.0 exactly, and
            // x*1.0 == x bit-exactly, so this is bit-equality.
            let expect = 0.5 * (T - t) * g[i] * g[i];
            assert_eq!(w[i].to_bits(), expect.to_bits(), "i={i}");
        }
    }

    #[test]
    fn terminal_weight_is_exactly_zero() {
        let (g, a) = schedules(64);
        let mut w = [0.0f32; 64];
        pfd_horizon_weights(&g, &a, T, &mut w);
        assert_eq!(w[63].to_bits(), 0.0f32.to_bits());
        // Not near-zero: EXACTLY zero, even with g/a nonzero at t=T.
        assert!(g[63] > 0.0 && a[63] > 0.0);
    }

    #[test]
    fn f64_oracle_agreement() {
        // Independent recomputation in f64 (different precision, different
        // accumulation shape) — the correctness check that is NOT
        // satisfied by construction.
        let n = 64usize;
        let (g, a) = schedules(n);
        let mut w = [0.0f32; 64];
        pfd_horizon_weights(&g, &a, T, &mut w);
        let dt = f64::from(T) / (n - 1) as f64;
        let mut a_int = 0.0f64;
        for (i, &wi) in w.iter().enumerate() {
            if i > 0 {
                a_int += 0.5 * (f64::from(a[i - 1]) + f64::from(a[i])) * dt;
            }
            let t = f64::from(T) * i as f64 / (n - 1) as f64;
            let oracle = 0.5 * (f64::from(T) - t) * f64::from(g[i]).powi(2) * (-2.0 * a_int).exp();
            if i == n - 1 {
                assert_eq!(oracle, 0.0);
            } else {
                let rel = (f64::from(wi) - oracle).abs() / oracle.abs().max(1e-12);
                assert!(rel < 1e-5, "i={i} f32 {wi} vs oracle {oracle} (rel {rel})");
            }
        }
    }

    #[test]
    fn trapezoid_is_exact_for_constant_drift() {
        // For constant a the trapezoid integral is a·t up to the dt
        // rounding; check against the closed form fed the analytic
        // integral A(t) = a·t.
        let n = 64usize;
        let g = vec![1.0f32; n];
        let a_const = 0.7f32;
        let a = vec![a_const; n];
        let mut w = [0.0f32; 64];
        pfd_horizon_weights(&g, &a, T, &mut w);
        for (i, &wi) in w.iter().enumerate() {
            let t = T * i as f32 / (n - 1) as f32;
            let analytic = pfd_horizon_weight_at(t, T, 1.0, a_const * t);
            let rel = (wi - analytic).abs() / analytic.abs().max(1e-12);
            assert!(rel < 1e-5, "i={i} rel {rel}");
        }
    }

    #[test]
    fn table_matches_pure_fn_bit_for_bit() {
        let (g, a) = schedules(HORIZON_WEIGHT_GRID);
        let gt: &[f32; HORIZON_WEIGHT_GRID] = g.as_slice().try_into().unwrap();
        let at: &[f32; HORIZON_WEIGHT_GRID] = a.as_slice().try_into().unwrap();
        let table = HorizonWeightTable::build(gt, at, T);
        let mut direct = [0.0f32; HORIZON_WEIGHT_GRID];
        pfd_horizon_weights(&g, &a, T, &mut direct);
        for (i, (&tw, &dw)) in table.weights().iter().zip(direct.iter()).enumerate() {
            assert_eq!(
                tw.to_bits(),
                dw.to_bits(),
                "G1 bit-match failed at grid point {i}"
            );
        }
    }

    #[test]
    fn commitment_roundtrip_and_tamper_detection() {
        let (g, a) = schedules(HORIZON_WEIGHT_GRID);
        let gt: &[f32; HORIZON_WEIGHT_GRID] = g.as_slice().try_into().unwrap();
        let at: &[f32; HORIZON_WEIGHT_GRID] = a.as_slice().try_into().unwrap();
        let mut table = HorizonWeightTable::build(gt, at, T);
        assert!(table.verify());
        assert_ne!(
            table.commitment(),
            &[0u8; 32],
            "commitment must be set at build"
        );
        // Tamper with one weight → verify fails.
        table.w_mut_for_test()[7] += 0.001;
        assert!(!table.verify());
        // Re-commit → verifies again (the table's own identity).
        table.commit();
        assert!(table.verify());
    }

    /// Test-only tamper seam (keeps `w` private).
    impl HorizonWeightTable {
        fn w_mut_for_test(&mut self) -> &mut [f32; HORIZON_WEIGHT_GRID] {
            &mut self.w
        }
    }

    #[test]
    fn w_at_rounds_to_nearest_grid_point() {
        let (g, a) = schedules(HORIZON_WEIGHT_GRID);
        let gt: &[f32; HORIZON_WEIGHT_GRID] = g.as_slice().try_into().unwrap();
        let at: &[f32; HORIZON_WEIGHT_GRID] = a.as_slice().try_into().unwrap();
        let table = HorizonWeightTable::build(gt, at, T);
        assert_eq!(table.w_at_unit(0.0).to_bits(), table.weights()[0].to_bits());
        assert_eq!(
            table.w_at_unit(1.0).to_bits(),
            table.weights()[HORIZON_WEIGHT_GRID - 1].to_bits()
        );
        // x = 32.5/63 rounds up to 33; x = 31.6/63 rounds down to 32.
        let inv = (HORIZON_WEIGHT_GRID - 1) as f32;
        let x_up = 32.5 / inv;
        assert_eq!(
            table.w_at_unit(x_up).to_bits(),
            table.weights()[33].to_bits(),
            "midpoint rounds up"
        );
        let x_down = 31.6 / inv;
        assert_eq!(
            table.w_at_unit(x_down).to_bits(),
            table.weights()[32].to_bits(),
            "below midpoint rounds down"
        );
        // Absolute-time form scales through the stored inv_horizon.
        let t_mid = T * 32.0 / inv;
        assert_eq!(table.w_at(t_mid).to_bits(), table.weights()[32].to_bits());
        // Out-of-range clamps.
        assert_eq!(table.w_at(-1.0).to_bits(), table.weights()[0].to_bits());
        assert_eq!(
            table.w_at(2.0 * T).to_bits(),
            table.weights()[HORIZON_WEIGHT_GRID - 1].to_bits()
        );
    }

    #[cfg(all(test, any(debug_assertions, feature = "alloc_tracking")))]
    #[test]
    fn build_and_lookup_are_alloc_free() {
        use std::hint::black_box;
        let (g, a) = schedules(HORIZON_WEIGHT_GRID);
        let gt: &[f32; HORIZON_WEIGHT_GRID] = g.as_slice().try_into().unwrap();
        let at: &[f32; HORIZON_WEIGHT_GRID] = a.as_slice().try_into().unwrap();
        crate::alloc::reset_alloc_stats();
        let table = HorizonWeightTable::build(gt, at, T);
        let mut sink = 0.0f32;
        for i in 0..1024usize {
            sink += black_box(table.w_at(black_box(i as f32) * 0.01));
        }
        let (count, _bytes) = crate::alloc::get_alloc_stats();
        assert_eq!(count, 0, "G4: build + 1024 lookups allocated {count} times");
        assert!(sink.is_finite(), "sink must be consumed: {sink}");
    }
}
