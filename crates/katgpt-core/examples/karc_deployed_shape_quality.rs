//! KARC deployed-shape forecast-quality audit (Issue 866 T1b).
//!
//! Bench 308's D3 split-config G1 contract (NRMSE ≤ 1e-3 AND threshold ≥ 8 LT)
//! was measured on `ChebyshevBasis` configs (K=8, R=2 / M=24) that **no
//! consumer constructs**. Every deployed monomorphization is `FourierBasis`
//! at R=1, period 4.0 (riir-engine `karc_bridge`):
//!
//! - **Lod0** (background): `KarcForecaster<FourierBasis<4>, 8, 4, 2>`  `d_h=64`
//! - **Lod1/HlaKarc** (default): `KarcForecaster<FourierBasis<8>, 8, 8, 4>` `d_h=256`
//! - **Lod2** (hero):          `KarcForecaster<FourierBasis<8>, 8, 8, 8>` `d_h=512`
//!
//! This example runs the Bench 308 Phase 5 protocol (one-step NRMSE over the
//! train fit, autonomous-rollout NRMSE over 1 Lyapunov time, ε=0.1 threshold
//! time in LT) on two fixtures:
//!
//! **A. Lorenz-driven leaky-belief fixture (the deployed consumer's regime).**
//! The runtime's own belief-update math — `katgpt_core::leaky_core::leaky_step`
//! with the shipped defaults (lr=0.1, `max_delta=0.3`, the `KIND_MAP` gather
//! [0,1,2,3,4,5,0,1], total = Σ[0..6]) — driven by deterministic Lorenz
//! forcing (σ=10, ρ=28, β=8/3; RK4 dt=0.025 per tick; 6 source "kind"
//! activations = fixed sigmoid mixtures of the Lorenz state). The fixture's
//! `λ_max` is measured by Benettin renormalization on the combined 11-dim
//! system. `N_TRAIN` = 2048 = riir-engine's `DEFAULT_MAX_SAMPLES` (the deployed
//! re-fit buffer). Headline λ = the deployed `HlaKarcConfig` default **1e-4**
//! (raised from 1e-6 by riir-ai Benchmark 398 §3.4), plus a context sweep.
//!
//! **B. The double-scroll attractor (the D3 contract's own fixture).** The
//! exact Bench 308 Phase 1 ODE (arXiv:2606.19984 §A.1, paper LT ≈ 7.81), but
//! fitted at the deployed basis FAMILY: Fourier R=1 at (M=4,K=2), (M=8,K=4)
//! and (M=8,K=8), D=3. This answers "do the deployed configs meet the D3
//! bars on the D3 fixture?" directly.
//!
//! Read-only measurement — prints, asserts nothing. The verdict record is
//! `.benchmarks/849_karc_deployed_shape_quality.md` (Issue 866 T1c).

use katgpt_core::{FourierBasis, KarcBasis, KarcForecaster};

// ── Shared metrics (mirrors examples/karc_double_scroll.rs) ───────────────

/// Normalised RMSE of `pred` vs `truth` (row-major n×dim), normalised by the
/// per-coordinate std of `truth` (mean over coordinates).
fn nrmse(pred: &[f32], truth: &[f32], dim: usize) -> f32 {
    debug_assert_eq!(pred.len(), truth.len());
    debug_assert_eq!(pred.len() % dim, 0);
    let n = pred.len() / dim;
    let mut stds = [0.0f32; 8];
    debug_assert!(dim <= stds.len());
    for d in 0..dim {
        let mut mean = 0.0f64;
        for i in 0..n {
            mean += truth[i * dim + d] as f64;
        }
        mean /= n as f64;
        let mut var = 0.0f64;
        for i in 0..n {
            let dx = truth[i * dim + d] as f64 - mean;
            var += dx * dx;
        }
        var /= n as f64;
        stds[d] = var.sqrt() as f32;
    }
    let mut sum = 0.0f32;
    for d in 0..dim {
        let mut err_sq = 0.0f32;
        for i in 0..n {
            let e = pred[i * dim + d] - truth[i * dim + d];
            err_sq += e * e;
        }
        let rmse = (err_sq / n as f32).sqrt();
        sum += rmse / stds[d].max(1e-12);
    }
    sum / dim as f32
}

/// Mean per-coordinate std of `truth` (row-major n×dim).
fn mean_std(truth: &[f32], dim: usize) -> f32 {
    let n = truth.len() / dim;
    let mut sum_std = 0.0f32;
    for d in 0..dim {
        let mut mean = 0.0f64;
        for i in 0..n {
            mean += truth[i * dim + d] as f64;
        }
        mean /= n as f64;
        let mut var = 0.0f64;
        for i in 0..n {
            let dx = truth[i * dim + d] as f64 - mean;
            var += dx * dx;
        }
        var /= n as f64;
        sum_std += (var.sqrt()) as f32;
    }
    sum_std / dim as f32
}

/// First sample index where `‖û_t − u_t‖ > ε · σ̄`. Returns sample count if
/// never exceeded (mirrors the Phase 1 example).
fn threshold_time(pred: &[f32], truth: &[f32], dim: usize, eps: f32, sigma: f32) -> usize {
    let n = pred.len() / dim;
    let bound = eps * sigma;
    for i in 0..n {
        let mut err_sq = 0.0f32;
        for d in 0..dim {
            let e = pred[i * dim + d] - truth[i * dim + d];
            err_sq += e * e;
        }
        if err_sq.sqrt() > bound {
            return i;
        }
    }
    n
}

/// One-step NRMSE over the train fit: forecast every training delay state,
/// compare to the true next state (isolates model quality from rollout
/// divergence). Mirrors the Phase 1 example.
fn one_step_nrmse<B: KarcBasis<M>, const D: usize, const M: usize, const K: usize>(
    fc: &mut KarcForecaster<B, D, M, K>,
    traj: &[f32],
) -> f32 {
    let n_total = traj.len() / D;
    let mut err_sq = [0.0f32; 8];
    debug_assert!(D <= err_sq.len());
    let mut count = 0usize;
    for t in (K - 1)..(n_total - 1) {
        let mut delay = vec![0.0f32; K * D];
        for lag in 0..K {
            let idx = t - lag;
            for d in 0..D {
                delay[lag * D + d] = traj[idx * D + d];
            }
        }
        let mut pred = [0.0f32; 8];
        fc.forecast_into(&delay, &mut pred[..D]);
        for d in 0..D {
            let e = pred[d] - traj[(t + 1) * D + d];
            err_sq[d] += e * e;
        }
        count += 1;
    }
    let mut sum = 0.0f32;
    for d in 0..D {
        let mut mean = 0.0f64;
        for i in 0..count {
            mean += traj[(K - 1 + i) * D + d] as f64;
        }
        mean /= count as f64;
        let mut var = 0.0f64;
        for i in 0..count {
            let dx = traj[(K - 1 + i) * D + d] as f64 - mean;
            var += dx * dx;
        }
        let std = ((var / count as f64).sqrt() as f32).max(1e-12);
        sum += (err_sq[d] / count as f32).sqrt() / std;
    }
    sum / D as f32
}

// ── Fixture A: Lorenz-driven leaky-belief ─────────────────────────────────

const LORENZ_SIGMA: f64 = 10.0;
const LORENZ_RHO: f64 = 28.0;
const LORENZ_BETA: f64 = 8.0 / 3.0;
const DT_A: f64 = 0.025; // Lorenz time units per observation (tick)

fn lorenz_rhs(s: &[f64; 3], out: &mut [f64; 3]) {
    out[0] = LORENZ_SIGMA * (s[1] - s[0]);
    out[1] = s[0] * (LORENZ_RHO - s[2]) - s[1];
    out[2] = s[0] * s[1] - LORENZ_BETA * s[2];
}

fn lorenz_rk4(s: &mut [f64; 3], dt: f64) {
    let mut k1 = [0.0; 3];
    let mut k2 = [0.0; 3];
    let mut k3 = [0.0; 3];
    let mut k4 = [0.0; 3];
    let mut tmp = [0.0; 3];
    lorenz_rhs(s, &mut k1);
    for j in 0..3 {
        tmp[j] = s[j] + 0.5 * dt * k1[j];
    }
    lorenz_rhs(&tmp, &mut k2);
    for j in 0..3 {
        tmp[j] = s[j] + 0.5 * dt * k2[j];
    }
    lorenz_rhs(&tmp, &mut k3);
    for j in 0..3 {
        tmp[j] = s[j] + dt * k3[j];
    }
    lorenz_rhs(&tmp, &mut k4);
    for j in 0..3 {
        s[j] += dt / 6.0 * (k1[j] + 2.0 * k2[j] + 2.0 * k3[j] + k4[j]);
    }
}

/// Sigmoid (the house bridge primitive: dot-product projection + sigmoid).
#[inline]
fn sigmoid(x: f64) -> f32 {
    (1.0 / (1.0 + (-x).exp())) as f32
}

/// The 6 source kind activations: fixed sigmoid mixtures of the Lorenz state,
/// sharpened (^4) and normalized into COMPETITIVE shares summing to 0.9.
/// Sharpening is what makes the regime evidence-like: the dominant kind's
/// share exceeds `half_total = 0.45` often enough to push its coordinates up
/// while the rest drain — a competitive accumulator, not a uniform sink (the
/// fixture bug this construction guards against: unsharpened shares keep every
/// input below `half_total`, so all coordinates sink to the −1 clamp and freeze).
/// Raw normalization, no softmax. Deterministic; no RNG anywhere.
#[inline]
fn kinds_from_lorenz(s: &[f64; 3]) -> [f32; 6] {
    let (x, y, z) = (s[0], s[1], s[2]);
    let raw = [
        sigmoid(0.25 * x + 0.5),
        sigmoid(0.25 * y - 0.5),
        sigmoid(0.15 * z - 3.0),
        sigmoid(0.141_421_36 * (x + y) + 1.0),
        sigmoid(0.141_421_36 * (x - y) - 1.0),
        sigmoid(0.1 * z - 0.15 * x - 1.0),
    ];
    let mut pow = [0.0f32; 6];
    let mut sum = 0.0f32;
    for i in 0..6 {
        pow[i] = raw[i] * raw[i] * raw[i] * raw[i];
        sum += pow[i];
    }
    let mut out = [0.0f32; 6];
    for i in 0..6 {
        out[i] = pow[i] / sum * 0.9;
    }
    out
}

/// One belief tick: the runtime's own math — `leaky_step` with the shipped
/// defaults and the `KIND_MAP` gather (the sum-over-6 quirk preserved).
#[inline]
fn belief_tick(belief: &mut [f32; 8], kinds: &[f32; 6]) {
    let total: f32 = kinds.iter().copied().sum();
    // KIND_MAP = [0,1,2,3,4,5,0,1] (crate::sense::reconstruction).
    let input: [f32; 8] = [
        kinds[0], kinds[1], kinds[2], kinds[3], kinds[4], kinds[5], kinds[0], kinds[1],
    ];
    katgpt_core::leaky_core::leaky_step(belief, &input, total, 0.1, 0.3);
}

/// Combined-system one-tick step: Lorenz RK4 + kinds + belief tick.
#[inline]
fn fixture_a_step(lorenz: &mut [f64; 3], belief: &mut [f32; 8]) -> [f32; 8] {
    lorenz_rk4(lorenz, DT_A);
    let kinds = kinds_from_lorenz(lorenz);
    belief_tick(belief, &kinds);
    *belief
}

/// Simulate the fixture, recording beliefs. Returns the belief trajectory
/// (row-major n×8) and the final combined state (for truth continuation).
fn simulate_belief_fixture(
    n_samples: usize,
    lorenz: [f64; 3],
    belief: [f32; 8],
) -> (Vec<f32>, [f64; 3], [f32; 8]) {
    let mut lorenz = lorenz;
    let mut belief = belief;
    let mut out = Vec::with_capacity(n_samples * 8);
    for _ in 0..n_samples {
        let b = fixture_a_step(&mut lorenz, &mut belief);
        out.extend_from_slice(&b);
    }
    (out, lorenz, belief)
}

/// Benettin largest Lyapunov exponent of the combined system: two copies,
/// δ-perturbed, renormalized every observation. λ = Σln(d/d0) / `total_time`.
fn benettin_lambda(steps: usize, delta: f64) -> f64 {
    let mut l_ref = [-8.0f64, 8.0, 27.0];
    let mut b_ref = [0.5f32; 8];
    // Transient onto the attractor.
    for _ in 0..2000 {
        fixture_a_step(&mut l_ref, &mut b_ref);
    }
    let mut l_pert = l_ref;
    let mut b_pert = b_ref;
    // Perturb the full combined state.
    l_pert[0] += delta;
    b_pert[0] += delta as f32;
    let mut acc_ln = 0.0f64;
    for _ in 0..steps {
        fixture_a_step(&mut l_ref, &mut b_ref);
        fixture_a_step(&mut l_pert, &mut b_pert);
        // Euclidean distance over the combined state.
        let mut d2 = 0.0f64;
        for j in 0..3 {
            let dx = l_pert[j] - l_ref[j];
            d2 += dx * dx;
        }
        for j in 0..8 {
            let dx = (b_pert[j] - b_ref[j]) as f64;
            d2 += dx * dx;
        }
        let d = d2.sqrt().max(1e-300);
        acc_ln += (d / delta).ln();
        // Renormalize the perturbed copy back onto the reference's shell.
        let scale = delta / d;
        for j in 0..3 {
            l_pert[j] = l_ref[j] + (l_pert[j] - l_ref[j]) * scale;
        }
        for j in 0..8 {
            b_pert[j] = b_ref[j] + (b_pert[j] - b_ref[j]) * (scale as f32);
        }
    }
    acc_ln / (steps as f64 * DT_A)
}

/// The per-fixture geometry both measurement fns share (bundled so the
/// measurement signature stays under clippy's argument ceiling).
struct FixtureSpec<'a> {
    traj: &'a [f32],
    truth: &'a [f32],
    n_region: usize,
    seed_t: usize,
    samples_per_lt: f64,
}

/// Fit one deployed shape on the belief fixture and roll it out autonomously.
fn run_fixture_a<B: KarcBasis<M>, const D: usize, const M: usize, const K: usize>(
    basis: B,
    label: &str,
    fx: &FixtureSpec<'_>,
    lambda: f32,
) {
    let traj = fx.traj;
    let truth = fx.truth;
    let n_total = fx.n_region;
    let seed_t = fx.seed_t;
    let samples_per_lt = fx.samples_per_lt;
    let mut fc: KarcForecaster<B, D, M, K> = KarcForecaster::with_capacity(basis, 2048);
    for t in (K - 1)..(n_total - 1) {
        let mut delay = vec![0.0f32; K * D];
        for lag in 0..K {
            let idx = t - lag;
            for d in 0..D {
                delay[lag * D + d] = traj[idx * D + d];
            }
        }
        let mut target = [0.0f32; D];
        for d in 0..D {
            target[d] = traj[(t + 1) * D + d];
        }
        fc.accumulate_pair(&delay, &target);
    }
    let fit = fc.fit_ridge(lambda);
    let fit_note = match &fit {
        Ok(()) => format!("ok ({} entries)", fc.wout.len()),
        Err(e) => format!("ERR {e:?}"),
    };
    let os = one_step_nrmse(&mut fc, &traj[..n_total * D]);

    // Autonomous rollout: seed = delay window ending at seed_t; truth = the
    // pre-generated continuation.
    let mut cur_delay = vec![0.0f32; K * D];
    for lag in 0..K {
        let idx = seed_t - lag;
        for d in 0..D {
            cur_delay[lag * D + d] = traj[idx * D + d];
        }
    }
    let horizon = truth.len() / D;
    let mut pred = Vec::with_capacity(horizon * D);
    for _ in 0..horizon {
        let mut out = [0.0f32; D];
        let ok = fc.forecast_into(&cur_delay, &mut out);
        if !ok {
            break;
        }
        pred.extend_from_slice(&out);
        let mut next = vec![0.0f32; K * D];
        next[..D].copy_from_slice(&out[..D]);
        next[D..].copy_from_slice(&cur_delay[..(K - 1) * D]);
        cur_delay = next;
    }
    let n_pred = pred.len() / D;
    let n_one_lt = (samples_per_lt.ceil() as usize).max(1).min(n_pred);
    let nrmse_1lt = nrmse(&pred[..n_one_lt * D], &truth[..n_one_lt * D], D);
    // Persistence baseline: û_t = u_{t-1} (the seed's last true belief).
    let mut persist = Vec::with_capacity(n_one_lt * D);
    let last: &[f32] = &traj[seed_t * D..seed_t * D + D];
    for _ in 0..n_one_lt {
        persist.extend_from_slice(last);
    }
    let persist_nrmse = nrmse(&persist, &truth[..n_one_lt * D], D);
    let sigma = mean_std(&truth[..n_one_lt * D], D);
    let thr = threshold_time(&pred, truth, D, 0.1, sigma);
    let thr_lt = thr as f64 / samples_per_lt;

    println!(
        "  {label:<26} λ={lambda:<7} 1-step {os:.3e} | 1-LT {nrmse_1lt:.3e} (persist {persist_nrmse:.3e}) | thr {thr} samp = {thr_lt:.2} LT | fit {fit_note}"
    );
    println!(
        "      D3 bars: NRMSE ≤1e-3 {} · thr ≥8 LT {}",
        if nrmse_1lt <= 1.0e-3 { "PASS" } else { "FAIL" },
        if thr_lt >= 8.0 { "PASS" } else { "FAIL" },
    );
}

// ── Fixture B: double-scroll at the deployed basis family ─────────────────

const R1: f64 = 1.2;
const R2: f64 = 3.44;
const R4: f64 = 0.193;
const BETA: f64 = 11.6;
const I_R: f64 = 2.25e-5;
const DT_B: f64 = 0.25;
const SUBSTEPS: usize = 10;
const LT_B_UNITS: f64 = 7.81; // paper-reported Lyapunov time

fn ds_rhs(state: &[f64; 3], out: &mut [f64; 3]) {
    let (v1, v2, i) = (state[0], state[1], state[2]);
    let dv = v1 - v2;
    let sh = 2.0 * I_R * (BETA * dv).sinh();
    out[0] = v1 / R1 - dv / R2 - sh;
    out[1] = dv / R2 + sh - i;
    out[2] = v2 - R4 * i;
}

fn ds_rk4_once(s: &mut [f64; 3], dt: f64) {
    let mut k1 = [0.0; 3];
    let mut k2 = [0.0; 3];
    let mut k3 = [0.0; 3];
    let mut k4 = [0.0; 3];
    let mut tmp = [0.0; 3];
    ds_rhs(s, &mut k1);
    for j in 0..3 {
        tmp[j] = s[j] + 0.5 * dt * k1[j];
    }
    ds_rhs(&tmp, &mut k2);
    for j in 0..3 {
        tmp[j] = s[j] + 0.5 * dt * k2[j];
    }
    ds_rhs(&tmp, &mut k3);
    for j in 0..3 {
        tmp[j] = s[j] + dt * k3[j];
    }
    ds_rhs(&tmp, &mut k4);
    for j in 0..3 {
        s[j] += dt / 6.0 * (k1[j] + 2.0 * k2[j] + 2.0 * k3[j] + k4[j]);
    }
}

fn ds_step(s: &mut [f64; 3]) {
    let dt_sub = DT_B / SUBSTEPS as f64;
    for _ in 0..SUBSTEPS {
        ds_rk4_once(s, dt_sub);
    }
}

fn generate_double_scroll(n: usize) -> (Vec<f32>, [f64; 3]) {
    let mut s: [f64; 3] = [0.1, 0.0, 0.0];
    for _ in 0..1000 {
        ds_step(&mut s);
    }
    let mut out = Vec::with_capacity(n * 3);
    for _ in 0..n {
        ds_step(&mut s);
        out.push(s[0] as f32);
        out.push(s[1] as f32);
        out.push(s[2] as f32);
    }
    (out, s)
}

/// Fit one deployed-family shape on the double-scroll and roll out. Mirrors
/// the Phase 1 protocol (no normalization — Fourier is bounded for any input).
fn run_fixture_b<B: KarcBasis<M>, const M: usize, const K: usize>(
    basis: B,
    label: &str,
    fx: &FixtureSpec<'_>,
    lambda: f32,
) {
    let traj = fx.traj;
    let truth = fx.truth;
    let n_total = fx.n_region;
    let seed_t = fx.seed_t;
    let samples_per_lt = fx.samples_per_lt;
    const D: usize = 3;
    let mut fc: KarcForecaster<B, D, M, K> = KarcForecaster::with_capacity(basis, 4000);
    for t in (K - 1)..(n_total - 1) {
        let mut delay = vec![0.0f32; K * D];
        for lag in 0..K {
            let idx = t - lag;
            for d in 0..D {
                delay[lag * D + d] = traj[idx * D + d];
            }
        }
        let mut target = [0.0f32; D];
        for d in 0..D {
            target[d] = traj[(t + 1) * D + d];
        }
        fc.accumulate_pair(&delay, &target);
    }
    let fit = fc.fit_ridge(lambda);
    let fit_note = match &fit {
        Ok(()) => format!("ok ({} entries)", fc.wout.len()),
        Err(e) => format!("ERR {e:?}"),
    };
    let os = one_step_nrmse(&mut fc, &traj[..n_total * D]);

    let mut cur_delay = vec![0.0f32; K * D];
    for lag in 0..K {
        let idx = seed_t - lag;
        for d in 0..D {
            cur_delay[lag * D + d] = traj[idx * D + d];
        }
    }
    let horizon = truth.len() / D;
    let mut pred = Vec::with_capacity(horizon * D);
    for _ in 0..horizon {
        let mut out = [0.0f32; D];
        let ok = fc.forecast_into(&cur_delay, &mut out);
        if !ok {
            break;
        }
        pred.extend_from_slice(&out);
        let mut next = vec![0.0f32; K * D];
        next[..D].copy_from_slice(&out);
        next[D..].copy_from_slice(&cur_delay[..(K - 1) * D]);
        cur_delay = next;
    }
    let n_pred = pred.len() / D;
    let n_one_lt = (samples_per_lt.ceil() as usize).max(1).min(n_pred);
    let nrmse_1lt = nrmse(&pred[..n_one_lt * D], &truth[..n_one_lt * D], D);
    let mut persist = Vec::with_capacity(n_one_lt * D);
    let last: &[f32] = &traj[seed_t * D..seed_t * D + D];
    for _ in 0..n_one_lt {
        persist.extend_from_slice(last);
    }
    let persist_nrmse = nrmse(&persist, &truth[..n_one_lt * D], D);
    let sigma = mean_std(&truth[..n_one_lt * D], D);
    let thr = threshold_time(&pred, truth, D, 0.1, sigma);
    let thr_lt = thr as f64 / samples_per_lt;

    println!(
        "  {label:<26} λ={lambda:<7} 1-step {os:.3e} | 1-LT {nrmse_1lt:.3e} (persist {persist_nrmse:.3e}) | thr {thr} samp = {thr_lt:.2} LT | fit {fit_note}"
    );
    println!(
        "      D3 bars: NRMSE ≤1e-3 {} · thr ≥8 LT {}",
        if nrmse_1lt <= 1.0e-3 { "PASS" } else { "FAIL" },
        if thr_lt >= 8.0 { "PASS" } else { "FAIL" },
    );
}

fn main() {
    println!("KARC deployed-shape forecast-quality audit (Issue 866 T1b)");
    println!("D3 contract bars: NRMSE ≤ 1e-3 (1 LT autonomous) AND threshold ≥ 8 LT (ε=0.1)");
    println!();

    // ── Fixture A ──
    println!("── Fixture A: Lorenz-driven leaky-belief (the deployed regime) ──");
    let lam_max = benettin_lambda(8000, 1e-7);
    println!(
        "  Benettin λ_max (combined system) = {lam_max:.4} /unit → 1 LT = {:.1} ticks (dt={DT_A})",
        1.0 / (lam_max * DT_A)
    );
    let samples_per_lt_a = 1.0 / (lam_max * DT_A);

    const N_TRAIN_A: usize = 2048; // riir-engine DEFAULT_MAX_SAMPLES
    const N_REGION_A: usize = N_TRAIN_A + 4 + 50;
    const HORIZON_A: usize = 900; // ~20 LT at ~44 samp/LT
    let n_a = N_REGION_A + HORIZON_A;
    let (traj_a, lorenz_end, belief_end) =
        simulate_belief_fixture(n_a, [-8.0, 8.0, 27.0], [0.5; 8]);
    let seed_t_a = N_REGION_A - 1;
    let truth_a: Vec<f32> = traj_a[N_REGION_A * 8..].to_vec();
    // Kind stats (fixture non-degeneracy witness).
    let mut l = [-8.0, 8.0, 27.0];
    let mut b = [0.5f32; 8];
    let mut ksum = [0.0f64; 6];
    let mut ksum2 = [0.0f64; 6];
    for _ in 0..n_a {
        lorenz_rk4(&mut l, DT_A);
        let k = kinds_from_lorenz(&l);
        belief_tick(&mut b, &k);
        for i in 0..6 {
            ksum[i] += k[i] as f64;
            ksum2[i] += (k[i] as f64) * (k[i] as f64);
        }
    }
    print!("  kind means/stds:");
    for i in 0..6 {
        let m = ksum[i] / n_a as f64;
        let sd = (ksum2[i] / n_a as f64 - m * m).sqrt();
        print!("  k{i}={m:.2}±{sd:.2}");
    }
    println!();
    // Belief non-degeneracy witness: a pinned trajectory (the fixture bug this
    // guards against) shows ~zero std per coordinate.
    print!("  belief stds:");
    for d in 0..8 {
        let mut m = 0.0f64;
        for i in 0..n_a {
            m += traj_a[i * 8 + d] as f64;
        }
        m /= n_a as f64;
        let mut v = 0.0f64;
        for i in 0..n_a {
            let dx = traj_a[i * 8 + d] as f64 - m;
            v += dx * dx;
        }
        print!("  b{d}={:.3}", (v / n_a as f64).sqrt());
    }
    println!();

    println!("  deployed monomorphizations, deployed default λ=1e-4 headline:");
    let fx_a = FixtureSpec {
        traj: &traj_a,
        truth: &truth_a,
        n_region: N_REGION_A,
        seed_t: seed_t_a,
        samples_per_lt: samples_per_lt_a,
    };
    run_fixture_a::<FourierBasis<4>, 8, 4, 2>(
        FourierBasis::<4>::new(4.0),
        "Lod0  F<4>  K=2 d_h=64",
        &fx_a,
        1e-4,
    );
    run_fixture_a::<FourierBasis<8>, 8, 8, 4>(
        FourierBasis::<8>::new(4.0),
        "Lod1  F<8>  K=4 d_h=256",
        &fx_a,
        1e-4,
    );
    run_fixture_a::<FourierBasis<8>, 8, 8, 8>(
        FourierBasis::<8>::new(4.0),
        "Lod2  F<8>  K=8 d_h=512",
        &fx_a,
        1e-4,
    );
    println!("  λ context sweep (Lod1 shape):");
    for lam in [1e-6f32, 1e-3, 5e-2] {
        run_fixture_a::<FourierBasis<8>, 8, 8, 4>(
            FourierBasis::<8>::new(4.0),
            "Lod1  F<8>  K=4 d_h=256",
            &fx_a,
            lam,
        );
    }
    let _ = (lorenz_end, belief_end); // continuation state held for reference

    // ── Fixture B ──
    println!();
    println!("── Fixture B: double-scroll at the deployed basis family (Fourier R=1, D=3) ──");
    let samples_per_lt_b = LT_B_UNITS / DT_B;
    println!("  paper LT ≈ {LT_B_UNITS} units ≈ {samples_per_lt_b} samples (dt={DT_B})");
    const N_TRAIN_B: usize = 4000;
    const HORIZON_B: usize = 700; // ~22 LT at ~31 samp/LT
    let (traj_b, ds_end) = generate_double_scroll(N_TRAIN_B + 4 + 50 + HORIZON_B);
    let n_region_b = N_TRAIN_B + 4 + 50;
    let seed_t_b = n_region_b - 1;
    let truth_b: Vec<f32> = traj_b[n_region_b * 3..].to_vec();
    let _ = ds_end;

    println!("  deployed (M,K) family, Phase-1-tuned λ=5e-3 first, deployed λ=1e-4 second:");
    let fx_b = FixtureSpec {
        traj: &traj_b,
        truth: &truth_b,
        n_region: n_region_b,
        seed_t: seed_t_b,
        samples_per_lt: samples_per_lt_b,
    };
    for lam in [5e-3f32, 1e-4] {
        run_fixture_b::<FourierBasis<4>, 4, 2>(
            FourierBasis::<4>::new(4.0),
            "Lod0-family  F<4> K=2",
            &fx_b,
            lam,
        );
        run_fixture_b::<FourierBasis<8>, 8, 4>(
            FourierBasis::<8>::new(4.0),
            "Lod1-family  F<8> K=4",
            &fx_b,
            lam,
        );
        run_fixture_b::<FourierBasis<8>, 8, 8>(
            FourierBasis::<8>::new(4.0),
            "Lod2-family  F<8> K=8",
            &fx_b,
            lam,
        );
        println!();
    }
}
