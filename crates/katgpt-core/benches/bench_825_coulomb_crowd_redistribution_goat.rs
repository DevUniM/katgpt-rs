//! Issue 825 T1+T2 — training-free Coulomb crowd redistribution via a DEC
//! Poisson solve: PoC + the 20x-bias analog gate.
//!
//! Research 468 §5 / arXiv:2608.01692 v3 Proposition 2: with the canonical
//! Coulomb field `b = grad(phi)`, `Laplace(phi) = mu0 - mu1`, the first-hitting
//! map of the autonomous flow `X' = b(X)` transports `mu0 -> mu1` EXACTLY, with
//! no training. Targets must be singular; a zone graph is the atomic case
//! (zones = vertices, `mu1` = weighted atoms on sink vertices).
//!
//! The issue's own caveat is what this bench exists to test:
//!
//! > **Continuum Coulomb field is NOT directly the discrete solve.** Prop 2
//! > lives in R^d with the fundamental solution; the DEC analog is the *graph
//! > Laplacian* Poisson solve — transport property transfer is unproven.
//!
//! # Sign convention — read this before the asserts
//!
//! The paper writes `Laplace(phi) = mu0 - mu1` for the continuum Laplacian,
//! which is negative semidefinite. This repo's `graph_laplacian` is
//! `delta.d = D - A`, the **positive** semidefinite negation of it. So the
//! solve here is `L(phi) = mu1 - mu0` and `phi` is the paper's potential
//! negated: mass flows toward INCREASING phi and sinks are potential maxima.
//! Getting this backwards yields a field that pushes every NPC away from its
//! target while every conservation assert still passes, which is why the
//! convention is written down next to the solve rather than inferred.
//!
//! # What the four gates measure
//!
//! - **G1 (conservation)** — `delta(j) = delta.d(phi) = L(phi) = mu1 - mu0`
//!   holds identically for `j = d(phi)`, so the numeric assert is on the CG
//!   residual, not on the algebra. Checked twice: `codifferential` against the
//!   target rank-0 field, and `belief_mass_divergence` on the mass-balanced
//!   residual flow — the Plan 314 steady-state check generalized to
//!   `mu0 != mu1`.
//! - **G2 (endpoint distribution)** — route N independent walkers by the flow
//!   and compare arrivals to `mu1` by MAE. This is a SAMPLING measurement: the
//!   expected endpoint distribution of the consistent construction is exactly
//!   `mu1`, so the residual is Monte-Carlo noise and must fall as `1/sqrt(N)`.
//!   The gate asserts that DECAY, because an assert at one N cannot tell
//!   "exact plus noise" from "biased by less than the tolerance" — and a
//!   fixture that cannot express the mechanism is the failure this repo keeps
//!   re-finding.
//! - **G3 (the 20x-bias analog)** — the naive rescaled attract field, the
//!   shipped `DecFlowField` consumption shape: `phi_naive(v) = -sum_j w_j *
//!   dist(v, sink_j)`, hand-set weights, same routing kernel. The paper
//!   measured 20x endpoint-weight bias for the EqM-style field against 0.005
//!   MAE for the consistent one. If the naive field is NOT badly biased on
//!   this graph the bench says so and reports FAIL-honest, per Issue 825 T2 —
//!   it does not move the bar.
//! - **G4 (alloc-free solve)** — after one warm-up, the CG solve and the
//!   `d(phi)` step allocate ZERO, measured through the repo's shared
//!   `counting_allocator!()` harness with its liveness canary.
//!
//! # Run
//!
//! ```bash
//! cargo bench -p katgpt-core --features dec_operators \
//!   --bench bench_825_coulomb_crowd_redistribution_goat
//! ```

#![cfg(feature = "dec_operators")]
// Parallel-array vertex/edge indexing reads better than iterator chains here.
#![allow(clippy::needless_range_loop)]

use std::time::Instant;

use katgpt_core::dec::{CellComplex, CochainField, belief_mass_divergence, codifferential};
// The `_into` (zero-alloc) variants are not re-exported at the crate root -
// only the allocating ones are - so they come from the module. G4 is about
// exactly this pair, so reaching for the root export would quietly make the
// gate measure the wrong thing.
use katgpt_core::dec::operators::{
    codifferential_into, exterior_derivative_into, graph_laplacian_into,
};

#[path = "../tests/common/mod.rs"]
mod common;
counting_allocator!();

// ---------------------------------------------------------------------------
// The toy zone graph
// ---------------------------------------------------------------------------

/// Grid width / height. 4x3 = 12 zones, the issue's "~6-12 vertices".
const W: usize = 4;
const H: usize = 3;
const N_V: usize = W * H;

/// Three sinks with DELIBERATELY unequal target weights. The bias gate exists
/// because a naive attract field cannot reproduce these; mirrors the paper's
/// 5-atom unequal-weight experiment.
const SINKS: [(usize, f32); 3] = [(0, 0.5), (3, 0.3), (11, 0.2)];

const CG_TOL: f32 = 1e-7;
const CG_MAX_ITER: usize = 4096;
/// Iterative-refinement rounds. Two is the measured plateau; a third changes
/// nothing because f32 has run out of bits, which is the point of the floor.
const REFINE_ROUNDS: usize = 3;
/// Stop refining once the TRUE residual is at the f32 floor for this problem.
const REFINE_FLOOR: f32 = 1e-7;

fn vid(x: usize, y: usize) -> usize {
    y * W + x
}

fn coord(v: usize) -> (usize, usize) {
    (v % W, v / W)
}

/// 4-neighbour grid graph as an explicit edge list.
///
/// `CellComplex::from_edges` orients edge `i` as `(tail, head)` with boundary
/// entries `(tail, i, -1)` and `(head, i, +1)`, so `d0(phi)[i] = phi[head] -
/// phi[tail]` and `delta1(j)[v]` is the net INFLOW at `v`.
fn grid_edges() -> Vec<(usize, usize)> {
    let mut e = Vec::new();
    for y in 0..H {
        for x in 0..W {
            if x + 1 < W {
                e.push((vid(x, y), vid(x + 1, y)));
            }
            if y + 1 < H {
                e.push((vid(x, y), vid(x, y + 1)));
            }
        }
    }
    e
}

/// `mu0`: the current crowd, uniform over every NON-sink zone.
/// `mu1`: the authored target, the unequal atoms above. Both sum to 1.
fn densities() -> (Vec<f32>, Vec<f32>) {
    let mut mu1 = vec![0.0f32; N_V];
    for (v, w) in SINKS {
        mu1[v] = w;
    }
    let sources: Vec<usize> = (0..N_V).filter(|v| mu1[*v] == 0.0).collect();
    let share = 1.0 / sources.len() as f32;
    let mut mu0 = vec![0.0f32; N_V];
    for &v in &sources {
        mu0[v] = share;
    }
    (mu0, mu1)
}

// ---------------------------------------------------------------------------
// Poisson solve — CG in the mean-zero subspace
// ---------------------------------------------------------------------------

/// Scratch for [`cg_poisson`], hoisted so the solve allocates nothing (G4).
///
/// `p_ch` is the reason this is a struct and not four locals: `graph_laplacian_into`
/// takes a `CochainField`, which owns its `Vec`, so the search direction must
/// live in a persistent cochain that the loop `copy_from_slice`s into. Building
/// one per iteration is the allocation G4 is there to catch.
struct CgScratch {
    r: Vec<f32>,
    p: Vec<f32>,
    ap: Vec<f32>,
    x: CochainField,
    p_ch: CochainField,
    ap_ch: CochainField,
    /// Rank-1 intermediate for the `delta . d` matvec — see [`lap_into`].
    d_ch: CochainField,
}

impl CgScratch {
    fn new(n: usize, n_edges: usize) -> Self {
        Self {
            r: vec![0.0; n],
            p: vec![0.0; n],
            ap: vec![0.0; n],
            x: CochainField::zeros(0, n, 1),
            p_ch: CochainField::zeros(0, n, 1),
            ap_ch: CochainField::zeros(0, n, 1),
            d_ch: CochainField::zeros(1, n_edges, 1),
        }
    }
}

/// The matvec: `L(phi) = delta(d(phi))`, composed EXPLICITLY rather than via
/// the fused `graph_laplacian_into`.
///
/// **Solve with the operator you transport with.** The transport field is
/// `j = d(phi)` and the conservation law is read through `delta(j)`, so the
/// operator the solve inverts should be the one the gate then measures; a
/// fused form is a second implementation of the same map and needs no reason
/// to agree with the first at the last bit.
///
/// ⚠ An earlier version of this comment claimed it DID disagree, and named
/// that as the cause of a residual stuck at 1.372e-5 through three refinement
/// rounds. **The diagnostic printed beside G1 refutes that**: on this complex
/// `max|graph_laplacian(phi) - delta(d(phi))|` is exactly **0**. The real cause
/// was the CG breakdown guard — see the comment at `pap` — and the residual is
/// 5.96e-8 once it is fixed. The composed form is kept on the principle above,
/// which is sound independently of the measurement that was wrong, and the
/// diagnostic stays because a claim of this shape should be re-measured on
/// every run rather than remembered from one.
#[inline]
fn lap_into(
    cx: &CellComplex,
    phi: &CochainField,
    d_ch: &mut CochainField,
    out: &mut CochainField,
) {
    exterior_derivative_into(cx, phi, d_ch);
    codifferential_into(cx, d_ch, out);
}

/// Scratch for the refinement loop, hoisted for the same reason `CgScratch` is.
struct RefineScratch {
    phi: Vec<f32>,
    resid: Vec<f32>,
    phi_ch: CochainField,
    lx_ch: CochainField,
    d_ch: CochainField,
}

impl RefineScratch {
    fn new(n: usize, n_edges: usize) -> Self {
        Self {
            phi: vec![0.0; n],
            resid: vec![0.0; n],
            phi_ch: CochainField::zeros(0, n, 1),
            lx_ch: CochainField::zeros(0, n, 1),
            d_ch: CochainField::zeros(1, n_edges, 1),
        }
    }
}

/// Remove the constant mode. `L` is singular on it, so both the RHS and the
/// iterate must stay mean-zero or CG wanders along the null direction and the
/// residual stops being a convergence signal.
fn project_mean_zero(v: &mut [f32]) {
    let mean = v.iter().sum::<f32>() / v.len() as f32;
    for e in v.iter_mut() {
        *e -= mean;
    }
}

fn dot(a: &[f32], b: &[f32]) -> f32 {
    a.iter().zip(b).map(|(x, y)| x * y).sum()
}

/// Solve `L(phi) = rhs` to the f32 floor: CG, then ITERATIVE REFINEMENT.
///
/// CG tracks its residual RECURSIVELY (`r -= alpha*ap`), and in f32 that
/// recursion drifts away from the true `rhs - L(x)` — measured here at 1.4e-5
/// against a `1e-7` recursive residual, a factor of ~100. Refinement recomputes
/// the TRUE residual and re-solves for a correction, which is the repair for a
/// number that is wrong; loosening the gate would have been the repair for a
/// number that is right, and this one is not.
///
/// Returns (total CG iterations, refinement rounds taken).
fn solve_refined(
    cx: &CellComplex,
    rhs: &[f32],
    scratch: &mut CgScratch,
    refine: &mut RefineScratch,
) -> (usize, usize) {
    let n = rhs.len();
    let mut iters = cg_poisson(cx, rhs, scratch);
    refine.phi[..n].copy_from_slice(&scratch.x.data[..n]);
    let mut rounds = 0usize;
    for _ in 0..REFINE_ROUNDS {
        // true residual: rhs - L(phi)
        refine.phi_ch.data[..n].copy_from_slice(&refine.phi[..n]);
        lap_into(cx, &refine.phi_ch, &mut refine.d_ch, &mut refine.lx_ch);
        for i in 0..n {
            refine.resid[i] = rhs[i] - refine.lx_ch.data[i];
        }
        project_mean_zero(&mut refine.resid[..n]);
        let rn = refine.resid[..n].iter().fold(0.0f32, |m, v| m.max(v.abs()));
        if rn <= REFINE_FLOOR {
            break;
        }
        iters += cg_poisson(cx, &refine.resid[..n], scratch);
        for i in 0..n {
            refine.phi[i] += scratch.x.data[i];
        }
        rounds += 1;
    }
    project_mean_zero(&mut refine.phi[..n]);
    scratch.x.data[..n].copy_from_slice(&refine.phi[..n]);
    (iters, rounds)
}

/// Solve `L(phi) = rhs` for a mean-zero `phi` by conjugate gradient.
///
/// Returns the iteration count; the solution is `scratch.x`.
fn cg_poisson(cx: &CellComplex, rhs: &[f32], scratch: &mut CgScratch) -> usize {
    let n = rhs.len();
    scratch.x.data.fill(0.0);
    scratch.r[..n].copy_from_slice(rhs);
    project_mean_zero(&mut scratch.r[..n]);
    scratch.p[..n].copy_from_slice(&scratch.r[..n]);
    let mut rs = dot(&scratch.r[..n], &scratch.r[..n]);
    if rs.sqrt() <= CG_TOL {
        return 0;
    }
    for it in 1..=CG_MAX_ITER {
        scratch.p_ch.data[..n].copy_from_slice(&scratch.p[..n]);
        lap_into(cx, &scratch.p_ch, &mut scratch.d_ch, &mut scratch.ap_ch);
        scratch.ap[..n].copy_from_slice(&scratch.ap_ch.data[..n]);
        project_mean_zero(&mut scratch.ap[..n]);
        let pap = dot(&scratch.p[..n], &scratch.ap[..n]);
        // NOT `pap.abs() < f32::EPSILON`. `L` is SPD on the mean-zero subspace,
        // so `p'Lp > 0` for every non-zero `p` and the only real breakdown is
        // `pap <= 0`. An ABSOLUTE floor is scale-dependent, and that is not a
        // style point: iterative refinement solves for a CORRECTION whose
        // residual is ~1e-5, making `pap ~ 1e-10` — legitimately tiny and far
        // under `f32::EPSILON` (1.19e-7). The first version returned at that
        // guard before taking a single step, so three refinement rounds ran and
        // the residual did not move one bit. A solver that silently does
        // nothing looks exactly like a solver that has converged.
        // NaN is spelled out rather than ridden in on a negated comparison:
        // clippy rejects `!(pap > 0.0)` on a partially ordered type, and it is
        // right that the two cases should be readable apart.
        if pap.is_nan() || pap <= 0.0 {
            project_mean_zero(&mut scratch.x.data[..n]);
            return it;
        }
        let alpha = rs / pap;
        for i in 0..n {
            scratch.x.data[i] += alpha * scratch.p[i];
            scratch.r[i] -= alpha * scratch.ap[i];
        }
        let rs_new = dot(&scratch.r[..n], &scratch.r[..n]);
        if rs_new.sqrt() <= CG_TOL {
            project_mean_zero(&mut scratch.x.data[..n]);
            return it;
        }
        let beta = rs_new / rs;
        for i in 0..n {
            scratch.p[i] = scratch.r[i] + beta * scratch.p[i];
        }
        rs = rs_new;
    }
    project_mean_zero(&mut scratch.x.data[..n]);
    CG_MAX_ITER
}

// ---------------------------------------------------------------------------
// Routing — the discrete first-arrival map
// ---------------------------------------------------------------------------

/// Per-vertex outgoing choices derived from an edge flow `j`.
///
/// Mass leaves `v` along edge `e` when `j[e] > 0` and `v` is `e`'s tail, or
/// `j[e] < 0` and `v` is `e`'s head. A gradient flow `j = d(phi)` is ACYCLIC —
/// `phi` strictly increases along every positive-flow edge, so a positive-flow
/// cycle would need `phi(v) > phi(v)`. That is the discrete replacement for the
/// paper's finite-hitting-time argument, and it is a property of the
/// construction rather than something the walk measures.
struct Routes {
    out: Vec<Vec<(usize, f32)>>,
    out_total: Vec<f32>,
    in_total: Vec<f32>,
}

fn routes_from_flow(edges: &[(usize, usize)], j: &[f32]) -> Routes {
    let mut out = vec![Vec::new(); N_V];
    let mut out_total = vec![0.0f32; N_V];
    let mut in_total = vec![0.0f32; N_V];
    for (e, &(tail, head)) in edges.iter().enumerate() {
        let f = j[e];
        if f > 0.0 {
            out[tail].push((head, f));
            out_total[tail] += f;
            in_total[head] += f;
        } else if f < 0.0 {
            out[head].push((tail, -f));
            out_total[head] += -f;
            in_total[tail] += -f;
        }
    }
    Routes {
        out,
        out_total,
        in_total,
    }
}

/// How a walker decides to stop.
enum Stop<'a> {
    /// The CONSISTENT rule, derived from the field itself. Mass balance at `v`
    /// is `inflow + mu0 = outflow + mu1` — exactly what `delta(j) = mu1 - mu0`
    /// guarantees — so the fraction `mu1[v] / (inflow + mu0[v])` of the mass
    /// passing through `v` stops there. A transit vertex has `mu1 = 0` and
    /// never absorbs; a pure sink has no outflow and absorbs everything.
    Absorb(&'a [f32]),
    /// The only rule a hand-built attract field can offer: stop on first
    /// arrival at a sink. It carries no target weights to derive one from, and
    /// THAT is the asymmetry G3 measures.
    FirstSink(&'a [bool]),
}

fn absorb_probs(r: &Routes, mu0: &[f32], mu1: &[f32]) -> Vec<f32> {
    (0..N_V)
        .map(|v| {
            let avail = r.in_total[v] + mu0[v];
            if avail <= 0.0 {
                0.0
            } else {
                (mu1[v] / avail).clamp(0.0, 1.0)
            }
        })
        .collect()
}

/// Route every walker in `start` and return the normalized arrival histogram,
/// plus the number of walkers that hit the step cap.
fn route(
    r: &Routes,
    start: &[usize],
    stop: &Stop<'_>,
    rng: &mut fastrand::Rng,
) -> (Vec<f32>, usize) {
    let mut hist = vec![0.0f32; N_V];
    // A gradient flow is acyclic, so this cap can only bind for a NON-gradient
    // field. It is reported rather than silently absorbed: a capped walk is a
    // finding about the field, not a timeout.
    let max_steps = N_V * 4;
    let mut capped = 0usize;
    for &s in start {
        let mut v = s;
        let mut stepped = 0usize;
        loop {
            let stopping = match stop {
                Stop::Absorb(p) => rng.f32() < p[v],
                Stop::FirstSink(is_sink) => is_sink[v],
            };
            if stopping || r.out_total[v] <= 0.0 {
                hist[v] += 1.0;
                break;
            }
            if stepped >= max_steps {
                capped += 1;
                hist[v] += 1.0;
                break;
            }
            let pick = rng.f32() * r.out_total[v];
            let mut acc = 0.0;
            let mut next = r.out[v][r.out[v].len() - 1].0;
            for &(dst, w) in &r.out[v] {
                acc += w;
                if pick <= acc {
                    next = dst;
                    break;
                }
            }
            v = next;
            stepped += 1;
        }
    }
    let n = start.len() as f32;
    for h in hist.iter_mut() {
        *h /= n;
    }
    (hist, capped)
}

fn mae(a: &[f32], b: &[f32]) -> f32 {
    a.iter().zip(b).map(|(x, y)| (x - y).abs()).sum::<f32>() / a.len() as f32
}

/// Walker start vertices drawn from `mu0` by largest-remainder apportionment,
/// so the START distribution contributes no sampling error of its own — the
/// only noise in G2 is the routing, which is what the decay bar is about.
fn walkers_from(mu0: &[f32], n: usize) -> Vec<usize> {
    let scaled: Vec<f32> = mu0.iter().map(|&m| m * n as f32).collect();
    let mut counts: Vec<usize> = scaled.iter().map(|s| s.floor() as usize).collect();
    let mut rem: Vec<(f32, usize)> = scaled
        .iter()
        .enumerate()
        .map(|(v, s)| (s - s.floor(), v))
        .collect();
    rem.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal));
    let mut assigned: usize = counts.iter().sum();
    let mut k = 0usize;
    while assigned < n {
        counts[rem[k % N_V].1] += 1;
        assigned += 1;
        k += 1;
    }
    let mut out = Vec::with_capacity(n);
    for (v, c) in counts.iter().enumerate() {
        out.extend(std::iter::repeat_n(v, *c));
    }
    out
}

// ---------------------------------------------------------------------------
// main
// ---------------------------------------------------------------------------

fn main() {
    println!("=== Issue 825 — Coulomb crowd redistribution GOAT (DEC Poisson solve) ===\n");

    let edges = grid_edges();
    let cx = CellComplex::from_edges(N_V, &edges);
    let (mu0, mu1) = densities();
    let is_sink: Vec<bool> = mu1.iter().map(|&m| m > 0.0).collect();

    println!(
        "zone graph: {N_V} vertices ({W}x{H}), {} edges, {} sinks",
        edges.len(),
        SINKS.len()
    );
    println!(
        "mu0: uniform over {} source zones   mu1: {SINKS:?}\n",
        mu0.iter().filter(|&&m| m > 0.0).count()
    );

    // ── the solve: L(phi) = mu1 - mu0 (see the sign-convention note) ──────
    let rhs: Vec<f32> = (0..N_V).map(|v| mu1[v] - mu0[v]).collect();
    let mut scratch = CgScratch::new(N_V, edges.len());
    let mut refine = RefineScratch::new(N_V, edges.len());
    let t0 = Instant::now();
    let (iters, rounds) = solve_refined(&cx, &rhs, &mut scratch, &mut refine);
    let solve_us = t0.elapsed().as_secs_f64() * 1e6;
    println!("CG: {iters} iteration(s) over {rounds} refinement round(s), {solve_us:.1} us");

    let phi_ch = CochainField::from_vec(0, 1, scratch.x.data.clone());
    let mut j_ch = CochainField::zeros(1, edges.len(), 1);
    exterior_derivative_into(&cx, &phi_ch, &mut j_ch);

    // ── G1: conservation ──────────────────────────────────────────────────
    let div = codifferential(&cx, &j_ch);
    let g1_resid = (0..N_V)
        .map(|v| (div.data[v] - rhs[v]).abs())
        .fold(0.0f32, f32::max);
    // GLOBAL balance: `delta` of ANY edge field sums to zero over vertices,
    // because every edge contributes +1 at its head and -1 at its tail. It is
    // structurally exact and independent of the solve, so it catches an
    // orientation or indexing error that the residual above cannot.
    let g1_global: f32 = div.data.iter().sum::<f32>().abs();
    // The Plan 314 reducer, generalized to `mu0 != mu1`: `belief_mass_divergence`
    // is `sum_v |delta(j)[v]|`, which for a correct field is the TOTAL MASS
    // MOVED — `sum_v |mu1 - mu0|`, i.e. everything that leaves plus everything
    // that arrives. Reading it as "should be ~0" would be the steady-state
    // special case and would assert the transport away.
    let moved_expect: f32 = (0..N_V).map(|v| (mu1[v] - mu0[v]).abs()).sum();
    let g1_bmd = belief_mass_divergence(&cx, &j_ch);
    // The bar is the f32 FLOOR for this problem, not a preference: the RHS has
    // entries of order 1e-1 and f32 carries ~1.2e-7 relative, so 1e-6 absolute
    // is already single-digit ULPs of the largest term. Measured: 5.96e-8, a
    // factor of 17 under the bar. The first run sat at 1.4e-5 and the bar was
    // NOT moved to meet it — the solver was wrong (the `pap` guard) and got
    // fixed.
    // Diagnostic: how far apart the crate's TWO forms of the same rank-0
    // operator are in f32 on this complex — the fused `graph_laplacian` against
    // the composed `delta(d(.))`. Reported, never gated: it is a property of the
    // crate's code paths, not of this PoC. The solve uses the COMPOSED form, so
    // the operator it inverts is the operator it transports with.
    let mut fused = CochainField::zeros(0, N_V, 1);
    graph_laplacian_into(&cx, &phi_ch, &mut fused);
    let mut composed_d = CochainField::zeros(1, edges.len(), 1);
    let mut composed = CochainField::zeros(0, N_V, 1);
    lap_into(&cx, &phi_ch, &mut composed_d, &mut composed);
    let op_gap = (0..N_V)
        .map(|v| (fused.data[v] - composed.data[v]).abs())
        .fold(0.0f32, f32::max);

    let g1_tol = 1e-6f32;
    let g1 = g1_resid <= g1_tol && g1_global <= 1e-6 && (g1_bmd - moved_expect).abs() <= 1e-4;
    println!("\nG1 conservation:");
    println!("   max|delta(j) - (mu1-mu0)|  = {g1_resid:.3e}  (tol {g1_tol:.0e})");
    println!("   |sum_v delta(j)[v]|        = {g1_global:.3e}  (tol 1e-6, structurally exact)");
    println!("   belief_mass_divergence(j)  = {g1_bmd:.6}  vs mass moved {moved_expect:.6} (tol 1e-4)");
    println!("   [diagnostic] max|graph_laplacian(phi) - delta(d(phi))| = {op_gap:.3e}  (one operator, two forms; report only)");
    println!("   -> {}", pf(g1));

    // ── G2: endpoint distribution and its 1/sqrt(N) decay ─────────────────
    let r = routes_from_flow(&edges, &j_ch.data);
    let absorb = absorb_probs(&r, &mu0, &mu1);
    let mut rng = fastrand::Rng::with_seed(0x0825_C0F1);
    println!("\nG2 endpoint distribution (Coulomb solve), MAE vs mu1:");
    let mut maes: Vec<(usize, f32)> = Vec::new();
    let mut total_capped = 0usize;
    for &n in &[1_000usize, 10_000, 100_000, 1_000_000] {
        let start = walkers_from(&mu0, n);
        let (hist, capped) = route(&r, &start, &Stop::Absorb(&absorb), &mut rng);
        total_capped += capped;
        let m = mae(&hist, &mu1);
        println!(
            "   N = {n:>9}   MAE = {m:.6}   MAE*sqrt(N) = {:.4}   capped = {capped}",
            m * (n as f32).sqrt()
        );
        maes.push((n, m));
    }
    let decay = maes[0].1 / maes[3].1.max(f32::EPSILON);
    let g2_tol = 0.01f32;
    // The signal is the DECAY, not one number: exact-plus-noise falls like
    // 1/sqrt(N), a biased field flattens. 1000x more walkers should buy near
    // 31x; the bar is a loose 4x so sampling noise alone cannot red it.
    let g2 = maes[3].1 <= g2_tol && decay >= 4.0 && total_capped == 0;
    println!(
        "   MAE at N=1e6 {:.6} (tol {g2_tol}), decay 1e3->1e6 {decay:.1}x (bar 4x), \
         capped {total_capped} (bar 0 — a gradient flow is acyclic) -> {}",
        maes[3].1,
        pf(g2)
    );

    // ── G3: the 20x-bias analog ───────────────────────────────────────────
    // phi_naive(v) = -sum_j w_j * dist(v, sink_j) — the shipped DecFlowField
    // consumption shape: a hand-built goal potential, no density input. Negated
    // once more for this file's sign convention, exactly as the solve is, so
    // both fields push mass toward increasing potential.
    let phi_naive: Vec<f32> = (0..N_V)
        .map(|v| {
            let (vx, vy) = coord(v);
            SINKS
                .iter()
                .map(|&(s, w)| {
                    let (sx, sy) = coord(s);
                    let d = vx.abs_diff(sx) as f32 + vy.abs_diff(sy) as f32;
                    w * d
                })
                .sum::<f32>()
        })
        .collect();
    let naive_ch = CochainField::from_vec(0, 1, phi_naive);
    let mut j_naive = CochainField::zeros(1, edges.len(), 1);
    exterior_derivative_into(&cx, &naive_ch, &mut j_naive);
    // `d` of a distance-sum increases AWAY from the sinks, so the transport
    // field is its negation.
    for f in j_naive.data.iter_mut() {
        *f = -*f;
    }
    let r_naive = routes_from_flow(&edges, &j_naive.data);
    let n_big = 1_000_000usize;
    let start = walkers_from(&mu0, n_big);
    let (hist_naive, capped_naive) =
        route(&r_naive, &start, &Stop::FirstSink(&is_sink), &mut rng);
    let mae_naive = mae(&hist_naive, &mu1);
    let ratio = mae_naive / maes[3].1.max(f32::EPSILON);
    let g3 = ratio >= 10.0;
    // Two DIFFERENT failures hide inside one MAE, and pooling them lets a reader
    // credit the whole ratio to weight bias. Named apart: how much of the crowd
    // reached a sink AT ALL (a hand-built attract field has local minima, and a
    // walker that finds one stops in open country), and how the arrivals SPLIT
    // once you condition on having arrived.
    let arrived_naive: f32 = SINKS.iter().map(|&(v, _)| hist_naive[v]).sum();
    println!("\nG3 naive rescaled attract field (the DecFlowField shape):");
    println!("   reached a sink at all: {:.1}%  (the rest stop at local minima of the hand-built potential, in open country)", arrived_naive * 100.0);
    for (v, w) in SINKS {
        let cond = if arrived_naive > 0.0 {
            hist_naive[v] / arrived_naive
        } else {
            0.0
        };
        println!(
            "   sink {v:>2}: target {w:.3}   naive {:.4}   conditional-on-arrival {cond:.4}",
            hist_naive[v]
        );
    }
    println!(
        "   MAE naive {mae_naive:.6} vs Coulomb {:.6} -> {ratio:.1}x \
         (bar 10x, paper measured 20x), capped {capped_naive} -> {}",
        maes[3].1,
        if g3 { "PASS" } else { "FAIL-honest" }
    );
    if !g3 {
        println!(
            "   ^ FAIL-honest: the naive field is NOT badly biased on this graph. Issue 825 T2\n   \
               says to report that and re-adjudicate whether the primitive earns a flag — it\n   \
               does NOT say to move the bar."
        );
    }

    // ── G4: alloc-free solve ──────────────────────────────────────────────
    let g4 = gate_g4(&cx, &rhs, &edges);

    let all = g1 && g2 && g3 && g4;
    println!(
        "\n=== VERDICT: G1 {} · G2 {} · G3 {} · G4 {} -> {} ===",
        pf(g1),
        pf(g2),
        pf(g3),
        pf(g4),
        if all { "GOAT PASS" } else { "GOAT FAIL" }
    );
    if !all {
        std::process::exit(1);
    }
}

fn pf(b: bool) -> &'static str {
    if b { "PASS" } else { "FAIL" }
}

/// G4 — the steady-state solve path allocates nothing.
///
/// `assert_counter_is_live()` first: a counter that has silently become a
/// no-op passes every alloc gate in the repo at once, which is strictly worse
/// than the defect the gate is looking for.
fn gate_g4(cx: &CellComplex, rhs: &[f32], edges: &[(usize, usize)]) -> bool {
    assert_counter_is_live();
    let mut scratch = CgScratch::new(N_V, edges.len());
    let mut refine = RefineScratch::new(N_V, edges.len());
    let mut j_ch = CochainField::zeros(1, edges.len(), 1);
    let mut phi_ch = CochainField::zeros(0, N_V, 1);

    // The REFINED solve, because that is the path the other three gates read.
    // Measuring `cg_poisson` alone would certify a function nothing calls.
    // Warm-up first: the first pass sizes every buffer the measured pass reuses.
    solve_refined(cx, rhs, &mut scratch, &mut refine);
    phi_ch.data.copy_from_slice(&scratch.x.data);
    exterior_derivative_into(cx, &phi_ch, &mut j_ch);

    let (_, allocs) = alloc_delta(|| {
        for _ in 0..100 {
            solve_refined(cx, rhs, &mut scratch, &mut refine);
            phi_ch.data.copy_from_slice(&scratch.x.data);
            exterior_derivative_into(cx, &phi_ch, &mut j_ch);
        }
    });
    let ok = allocs == 0;
    println!(
        "
G4 alloc: {allocs} allocation(s) over 100 refined solve + d(phi) passes -> {}",
        pf(ok)
    );
    ok
}
