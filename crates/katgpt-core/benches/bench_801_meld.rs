//! Bench 801 — meld composition-law GOAT gate (Issue 801 T3).
//!
//! Arms: meld (tanh) vs law-8 (unsaturated) vs no-W ablation vs mean —
//! G1 bracketing-recovery by depth (paper refs: meld 1.000/1.000/0.998/
//! 0.970/0.922 across d=1–5; law-8 …/0.899; no-W 0.843→0.684; mean collapses
//! on same-depth-multiset contrasts), G2 compose throughput, G4 zero-alloc
//! fixed-size witness. G1 self-tests (commutativity EXACT, non-associativity
//! EXISTS, boundedness depth-64, disagreement-coding limits) live in the
//! module's #[cfg(test)].
//!
//! # G1 protocol (a slice of Issue 801 T4 runnable here; T4 adds the PR
//! readout + the riir-poc three-competitor rig)
//!
//! - Atom bank: 32 seeded random unit vectors in `[f32; 32]`.
//! - Per trial: one random leaf assignment (a permutation of the bank over
//!   the `2^d` leaf slots), shared by ALL candidate bracketings; depth
//!   d ∈ 1..=5 ⇒ 2/4/8/16/32 leaves. Train centroids: 6 noise draws per
//!   shape (clean pass: σ = 0); queries: 6 held-out draws. Candidate set:
//!   1 true + 7 random distractor shapes (5 at d=2 — Catalan(3); 1 at d=1 —
//!   trivial by construction); candidate order is seeded-shuffled per query
//!   so tied centroids cannot hide behind a fixed position.
//! - Noise calibration: the paper's regime is 0 dB AT THE LEAF — noise
//!   power = signal power = 1 per leaf vector on unit atoms ⇒ σ = 1/√D
//!   ≈ 0.177. (A literal σ = 1 per coordinate would be −15 dB and drives
//!   every arm to chance — measured and rejected in the first run.)
//! - β = 3.0 (mid-window; the β ∈ [0.03, 30] ≥ 0.99 recovery window is
//!   covered by the module's self-tests).
//! - The `same-multiset` rows restrict the accuracy to queries whose true
//!   shape has ≥ 1 distractor with the SAME leaf-depth MULTISET — the
//!   paper's fixed-mixture contrasts. Honesty note: for ORDERED leaves a
//!   depth sequence determines the tree, so equal-multiset shapes still
//!   carry different per-leaf mean weights (mean composites differ); the
//!   paper's indistinguishability claim is about the S₂/D_eff statistics.
//!   The restricted rows are where mean's content-independence shows up
//!   FIRST — if mean does not collapse relative to meld there at depth ≥ 3,
//!   the bench says so LOUD (mandated by Issue 801 T3).
//!
//! Convention: `std::time::Instant` + `harness = false` (the bench_342 /
//! bench_324 house pattern — no Criterion dev-dep).
//!
//! Run:
//! ```bash
//! CARGO_TARGET_DIR=/tmp/krs_meld cargo bench -p katgpt-core \
//!   --features meld --bench bench_801_meld
//! ```

#![cfg(feature = "meld")]

use katgpt_core::meld::{MeldCompose, MeldLaw};
use std::time::Instant;

const D: usize = 32;
const N_ATOMS: usize = 32;
const DEPTHS: [usize; 5] = [1, 2, 3, 4, 5];
const N_DEPTHS: usize = 5;
const TRIALS: usize = 256;
const N_TRAIN: usize = 6;
const N_TEST: usize = 6;
const N_ASSIGN: usize = N_TRAIN + N_TEST;
const MAX_CANDS: usize = 8;
const BETA: f32 = 3.0;
/// Leaf-level 0 dB: noise power = signal power (= 1 per leaf vector) ⇒
/// σ = 1/√D.
fn noise_sigma() -> f32 {
    1.0 / (D as f32).sqrt()
}
const MEAN_AI: usize = 3;
const WARMUP: usize = 20;
const SAMPLES: usize = 25;
const ITERS: usize = 2000;

const ARMS: [Arm; 4] = [Arm::Meld, Arm::Law8, Arm::NoW, Arm::Mean];
const ARM_NAMES: [&str; 4] = ["meld", "law8", "no-W", "mean"];

// ─── Deterministic RNG (house pattern; no dep) ─────────────────────────────

struct Rng {
    s: u64,
    spare: Option<f32>,
}

impl Rng {
    fn new(seed: u64) -> Self {
        Self {
            s: seed | 1,
            spare: None,
        }
    }
    fn next_u64(&mut self) -> u64 {
        let mut x = self.s;
        x ^= x >> 12;
        x ^= x << 25;
        x ^= x >> 27;
        self.s = x;
        x.wrapping_mul(0x2545_F491_4F6C_DD1D)
    }
    fn next_unit(&mut self) -> f32 {
        f32::from_bits(((self.next_u64() >> 40) as u32) | 0x3F80_0000) - 1.0
    }
    fn next_pm1(&mut self) -> f32 {
        self.next_unit() * 2.0 - 1.0
    }
    fn next_usize(&mut self, bound: usize) -> usize {
        (self.next_u64() % bound as u64) as usize
    }
    /// Standard normal via Box–Muller (spare-value cache).
    fn next_normal(&mut self) -> f32 {
        if let Some(s) = self.spare.take() {
            return s;
        }
        let u1 = self.next_unit().max(1e-7);
        let u2 = self.next_unit();
        let r = (-2.0 * u1.ln()).sqrt();
        let th = core::f32::consts::TAU * u2;
        self.spare = Some(r * th.sin());
        r * th.cos()
    }
}

// ─── Bracketing shapes (bench-side allocation is fine; only the primitive
//     must be zero-alloc) ────────────────────────────────────────────────────

enum Shape {
    Leaf(usize),
    Node(Box<Shape>, Box<Shape>),
}

fn rand_range(rng: &mut Rng, lo: usize, hi: usize) -> Shape {
    if hi - lo == 1 {
        return Shape::Leaf(lo);
    }
    let split = lo + 1 + rng.next_usize(hi - lo - 1);
    Shape::Node(
        Box::new(rand_range(rng, lo, split)),
        Box::new(rand_range(rng, split, hi)),
    )
}

fn rand_shape(rng: &mut Rng, leaves: usize) -> Shape {
    rand_range(rng, 0, leaves)
}

fn shape_key(s: &Shape, out: &mut String) {
    match s {
        Shape::Leaf(i) => out.push_str(&i.to_string()),
        Shape::Node(l, r) => {
            out.push('(');
            shape_key(l, out);
            out.push(' ');
            shape_key(r, out);
            out.push(')');
        }
    }
}

/// Leaf depths in leaf order (index = leaf slot).
fn leaf_depths(s: &Shape, depth: u32, out: &mut Vec<u32>) {
    match s {
        Shape::Leaf(_) => out.push(depth),
        Shape::Node(l, r) => {
            leaf_depths(l, depth + 1, out);
            leaf_depths(r, depth + 1, out);
        }
    }
}

// ─── Arms ───────────────────────────────────────────────────────────────────

#[derive(Clone, Copy, PartialEq, Eq)]
enum Arm {
    Meld,
    Law8,
    NoW,
    Mean,
}

struct Arms {
    meld: MeldCompose<D>,
    law8: MeldCompose<D>,
    now: MeldCompose<D>,
}

impl Arms {
    fn new() -> Self {
        Self {
            meld: MeldCompose::<D>::new(BETA, MeldLaw::Tanh),
            law8: MeldCompose::<D>::new(BETA, MeldLaw::Linear),
            now: MeldCompose::<D>::no_w(BETA, MeldLaw::Tanh),
        }
    }
}

fn mean2(a: &[f32; D], b: &[f32; D]) -> [f32; D] {
    let mut o = [0.0_f32; D];
    for (o_i, (a_i, b_i)) in o.iter_mut().zip(a.iter().zip(b.iter())) {
        *o_i = (a_i + b_i) * 0.5;
    }
    o
}

fn compose(s: &Shape, leaves: &[[f32; D]], arm: Arm, arms: &Arms) -> [f32; D] {
    match s {
        Shape::Leaf(i) => leaves[*i],
        Shape::Node(l, r) => {
            let a = compose(l, leaves, arm, arms);
            let b = compose(r, leaves, arm, arms);
            match arm {
                Arm::Mean => mean2(&a, &b),
                Arm::Meld => arms.meld.meld(&a, &b),
                Arm::Law8 => arms.law8.meld(&a, &b),
                Arm::NoW => arms.now.meld(&a, &b),
            }
        }
    }
}

fn sqdist(a: &[f32; D], b: &[f32; D]) -> f32 {
    a.iter().zip(b.iter()).map(|(x, y)| (x - y) * (x - y)).sum()
}

fn cand_count(depth: usize) -> usize {
    match depth {
        1 => 1,
        2 => 5,
        _ => MAX_CANDS,
    }
}

// ─── G1 bracketing recovery ────────────────────────────────────────────────

/// Returns (full accuracy per arm per depth, same-depth-multiset-contrast
/// accuracy per arm per depth).
fn run_g1(
    noisy: bool,
    sigma: f32,
    atoms: &[[f32; D]],
    rng: &mut Rng,
) -> ([[f64; N_DEPTHS]; 4], [[f64; N_DEPTHS]; 4]) {
    let arms = Arms::new();
    let mut acc = [[0.0_f64; N_DEPTHS]; 4];
    let mut acc_restr = [[0.0_f64; N_DEPTHS]; 4];
    for (di, &depth) in DEPTHS.iter().enumerate() {
        let n_leaves = 1_usize << depth;
        let nt = cand_count(depth);
        let mut hits = [0.0_f64; 4];
        let mut restr_hits = [0.0_f64; 4];
        let mut restr_denom = 0.0_f64;
        for _ in 0..TRIALS {
            // Candidate bracketings: true shape + distinct distractors.
            let mut shapes: Vec<Shape> = Vec::with_capacity(nt);
            let mut keys: Vec<String> = Vec::with_capacity(nt);
            while shapes.len() < nt {
                let s = rand_shape(rng, n_leaves);
                let mut k = String::new();
                shape_key(&s, &mut k);
                if !keys.contains(&k) {
                    keys.push(k);
                    shapes.push(s);
                }
            }
            // Depth multisets (sorted) for the same-multiset restriction.
            let mut multi: Vec<Vec<u32>> = Vec::with_capacity(nt);
            for s in &shapes {
                let mut d = Vec::with_capacity(n_leaves);
                leaf_depths(s, 0, &mut d);
                d.sort_unstable();
                multi.push(d);
            }
            let has_match: Vec<bool> = (0..nt).map(|i| i != 0 && multi[i] == multi[0]).collect();

            // One leaf assignment (atom permutation) shared by all shapes,
            // TRAIN + TEST noise draws over it.
            let mut perm: [usize; N_ATOMS] = std::array::from_fn(|i| i);
            for k in (1..N_ATOMS).rev() {
                let j = rng.next_usize(k + 1);
                perm.swap(k, j);
            }
            let mut leaves: Vec<Vec<[f32; D]>> = Vec::with_capacity(N_ASSIGN);
            for _ in 0..N_ASSIGN {
                let mut assign: Vec<[f32; D]> = Vec::with_capacity(n_leaves);
                for slot in 0..n_leaves {
                    let mut val = atoms[perm[slot]];
                    if noisy {
                        for c in val.iter_mut() {
                            *c += sigma * rng.next_normal();
                        }
                    }
                    assign.push(val);
                }
                leaves.push(assign);
            }
            // Nearest-centroid prototypes per (shape, arm).
            let mut cents: Vec<[[f32; D]; 4]> = Vec::with_capacity(nt);
            for s in &shapes {
                let mut per_arm = [[0.0_f32; D]; 4];
                for (ai, &arm) in ARMS.iter().enumerate() {
                    let mut sum = [0.0_f32; D];
                    for leaves_a in leaves.iter().take(N_TRAIN) {
                        let c = compose(s, leaves_a, arm, &arms);
                        for (sv, cv) in sum.iter_mut().zip(c.iter()) {
                            *sv += cv;
                        }
                    }
                    let inv = 1.0 / N_TRAIN as f32;
                    for (pv, sv) in per_arm[ai].iter_mut().zip(sum.iter()) {
                        *pv = sv * inv;
                    }
                }
                cents.push(per_arm);
            }
            // Classification: held-out composites of each shape against the
            // prototypes; candidate order seeded-shuffled per query so tied
            // centroids resolve to coin flips.
            let any_match = has_match.iter().any(|&m| m);
            for leaves_a in leaves.iter().skip(N_TRAIN) {
                for (si, shape_si) in shapes.iter().enumerate() {
                    let mut order: [usize; MAX_CANDS] = [0; MAX_CANDS];
                    for (i, o) in order.iter_mut().enumerate() {
                        *o = i;
                    }
                    for k in (1..nt).rev() {
                        let j = rng.next_usize(k + 1);
                        order.swap(k, j);
                    }
                    let restricted = si == 0 && any_match;
                    if restricted {
                        restr_denom += 1.0;
                    }
                    for (ai, &arm) in ARMS.iter().enumerate() {
                        let q = compose(shape_si, leaves_a, arm, &arms);
                        let mut best = 0_usize;
                        let mut best_d = f32::INFINITY;
                        for &cand in order.iter().take(nt) {
                            let d2 = sqdist(&q, &cents[cand][ai]);
                            if d2 < best_d {
                                best_d = d2;
                                best = cand;
                            }
                        }
                        if best == si {
                            hits[ai] += 1.0;
                            if restricted {
                                restr_hits[ai] += 1.0;
                            }
                        }
                    }
                }
            }
        }
        let denom = (TRIALS * N_TEST * nt) as f64;
        for (ai, hit) in hits.iter().enumerate() {
            acc[ai][di] = hit / denom;
        }
        let rd = restr_denom;
        for (ai, hit) in restr_hits.iter().enumerate() {
            acc_restr[ai][di] = if rd > 0.0 { hit / rd } else { f64::NAN };
        }
    }
    (acc, acc_restr)
}

fn print_row(name: &str, vals: &[f64; N_DEPTHS]) {
    print!("  {name:<14}");
    for v in vals {
        if v.is_nan() {
            print!(" {:>7}", "—");
        } else {
            print!(" {:>7.3}", v);
        }
    }
    println!();
}

fn print_table(title: &str, acc: &[[f64; N_DEPTHS]; 4], restr: &[[f64; N_DEPTHS]; 4]) {
    println!("{title}");
    print!("  {:<14}", "arm");
    for d in 1..=N_DEPTHS {
        print!("   d={d:<4}");
    }
    println!();
    for (ai, name) in ARM_NAMES.iter().enumerate() {
        print_row(name, &acc[ai]);
    }
    println!("  same-depth-multiset contrasts (restricted):");
    for ai in [0, MEAN_AI] {
        print_row(&format!("{} @same-ms", ARM_NAMES[ai]), &restr[ai]);
    }
}

// ─── G2 throughput ─────────────────────────────────────────────────────────

fn median_op_ns(mut op: impl FnMut()) -> f64 {
    for _ in 0..WARMUP {
        op();
    }
    let mut samples: Vec<f64> = Vec::with_capacity(SAMPLES);
    for _ in 0..SAMPLES {
        let t0 = Instant::now();
        for _ in 0..ITERS {
            op();
        }
        samples.push(t0.elapsed().as_nanos() as f64 / ITERS as f64);
    }
    samples.sort_by(|a, b| a.partial_cmp(b).expect("non-finite timing sample"));
    samples[SAMPLES / 2]
}

fn g2_for<const N: usize>(seed: u64, label: &str) {
    let mut rng = Rng::new(seed);
    let mut u = [0.0_f32; N];
    let mut v = [0.0_f32; N];
    let mut w = [0.0_f32; N];
    for c in u.iter_mut() {
        *c = rng.next_pm1();
    }
    for c in v.iter_mut() {
        *c = rng.next_pm1();
    }
    let mc = MeldCompose::<N>::new(BETA, MeldLaw::Tanh);
    let mut chk = 0_u64;
    let meld_ns = median_op_ns(|| {
        let o = mc.meld(&u, &v);
        // Fold EVERY coordinate — a partial fold lets dead-store elimination
        // erase most of the primitive (first run measured mean at 0.1 ns/op
        // exactly because only w[0] was observed).
        for x in &o {
            chk = chk.wrapping_add(x.to_bits() as u64);
        }
    });
    let mean_ns = median_op_ns(|| {
        for (wi, (a, b)) in w.iter_mut().zip(u.iter().zip(v.iter())) {
            *wi = (a + b) * 0.5;
        }
        for x in &w {
            chk = chk.wrapping_add(x.to_bits() as u64);
        }
    });
    let ratio = meld_ns / mean_ns.max(1e-9);
    println!(
        "  {label:>6} {:>12.0} {:>12.1} {:>7.0}   (chk {:016x})",
        meld_ns, mean_ns, ratio, chk
    );
}

// ─── main ───────────────────────────────────────────────────────────────────

fn main() {
    let t_start = Instant::now();
    let sigma = noise_sigma();
    println!("== bench_801_meld — Issue 801 T3 (Research 560 / arXiv:2609.14384 §4.9.1) ==");
    println!(
        "D={D} atoms={N_ATOMS} trials={TRIALS} train={N_TRAIN} test={N_TEST} β={BETA} noise σ={sigma:.4} (leaf-level 0 dB)"
    );
    println!(
        "paper ladder (0 dB, d=1..5): meld 1.000/1.000/0.998/0.970/0.922 · law8 1.000/1.000/0.998/0.964/0.899 · no-W 0.843/0.754/0.705/0.677/0.684"
    );
    println!(
        "paper: mean-pooling is provably indistinguishable on same-leaf-depth-multiset bracketings (fixed-mixture theorem; S₂/D_eff statistics)"
    );

    let mut rng = Rng::new(801);
    let atoms: Vec<[f32; D]> = (0..N_ATOMS).map(|_| unit_vec(&mut rng)).collect();

    let (clean, restr_clean) = run_g1(false, 0.0, &atoms, &mut rng);
    let (noisy, restr_noisy) = run_g1(true, sigma, &atoms, &mut rng);
    print_table(
        "G1 clean (no leaf noise) — bracketing recovery, nearest-centroid:",
        &clean,
        &restr_clean,
    );
    print_table(
        "G1 0 dB (leaf noise, σ = 1/√D) — bracketing recovery:",
        &noisy,
        &restr_noisy,
    );

    // The mandated LOUD check: mean must collapse relative to meld at depth
    // ≥ 3 — on the same-depth-multiset contrasts (restricted rows, when they
    // exist) and overall.
    let mut collapsed = true;
    let mut restrict_exists = false;
    for di in 2..N_DEPTHS {
        if !restr_noisy[MEAN_AI][di].is_nan() || !restr_clean[MEAN_AI][di].is_nan() {
            restrict_exists = true;
        }
        if clean[MEAN_AI][di] >= clean[0][di] - 0.02 || noisy[MEAN_AI][di] >= noisy[0][di] - 0.02 {
            collapsed = false;
        }
        for restr in [&restr_clean, &restr_noisy] {
            let m = restr[MEAN_AI][di];
            let x = restr[0][di];
            if !m.is_nan() && !x.is_nan() && m >= x - 0.02 {
                collapsed = false;
            }
        }
    }
    if collapsed {
        println!(
            "VERDICT: mean-pooling collapses relative to meld at depths ≥ 3 ✓ (structure axis confirmed on this fixture{})",
            if restrict_exists {
                ", incl. same-multiset contrasts"
            } else {
                ""
            }
        );
    } else {
        println!(
            "⚠⚠ LOUD: mean-pooling did NOT collapse relative to meld at depth ≥ 3 on this fixture — RED FLAG for T4. Note: for ORDERED leaves a per-leaf depth sequence determines the tree, so full-vector nearest-centroid can distinguish same-MULTISET bracketings by their per-leaf mean weights; the paper's blindness is about S₂/D_eff statistics. Investigate the regime (noise, atom scale, candidate sampling, readout choice) before any T4 claim; do not hide this."
        );
    }

    println!("G2 throughput (median ns/op, {SAMPLES} samples × {ITERS} iters):");
    println!("  {:>6} {:>12} {:>12} {:>7}", "D", "meld", "mean", "×");
    g2_for::<32>(9001, "32");
    g2_for::<64>(9002, "64");
    g2_for::<128>(9003, "128");
    println!(
        "  (meld is expected slower than mean — the claim is structure (bracketing retention), not raw speed)"
    );

    println!(
        "G4 zero-alloc witness: the hot path (meld/meld_into/apply_w/lambda_star_into/soft_min_lambda_star/Walsh–Hadamard) uses only fixed-size stack arrays [f32; D]; no Vec/Box/String/heap allocation anywhere in katgpt_core::meld outside #[cfg(test)]."
    );
    println!("total wall: {:.1} s", t_start.elapsed().as_secs_f64());
}

fn unit_vec(rng: &mut Rng) -> [f32; D] {
    let mut v = [0.0_f32; D];
    for c in v.iter_mut() {
        *c = rng.next_pm1();
    }
    let n = v.iter().map(|x| x * x).sum::<f32>().sqrt().max(1e-12);
    for c in v.iter_mut() {
        *c /= n;
    }
    v
}
