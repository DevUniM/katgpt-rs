#![cfg(feature = "vortex_flow")]
//! Benchmark — SIMD Register TopK for k≤16 (Plan 256 Phase 1)
//!
//! Compares SIMD-optimized argtopk path vs scalar fallback across
//! k=4, 8, 16, 32 and n=64, 128, 256, 512, 1024 block counts.
//!
//! Run: `cargo test --features vortex_flow --test bench_256_simd_topk -- --nocapture`
//!
//! Issue-808 section (distribution matrix + per-k crossover) additionally
//! carries the profile axis: run it a second time under
//! `RUSTFLAGS="-C target-feature=+avx2"` — the scalar fallback auto-vectorizes
//! under that flag, so the comparison is profile-shaped, not just arch-shaped.

use katgpt_rs::dash_attn::block_topk::{argtopk, argtopk_scalar_heap};

// ── Helpers ───────────────────────────────────────────────────

/// Deterministic pseudo-random score generator (index-based seed).
fn make_scores(n: usize, seed: usize) -> Vec<f32> {
    (0..n)
        .map(|i| {
            let x = ((i.wrapping_mul(2654435761)).wrapping_add(seed.wrapping_mul(40503))) as f32;
            (x * 0.0001).sin() * 0.5 + 0.5
        })
        .collect()
}

/// Reference scalar argtopk — full sort + take top-k.
fn argtopk_reference(scores: &[f32], k: usize) -> Vec<usize> {
    let mut indexed: Vec<(usize, f32)> = scores.iter().copied().enumerate().collect();
    indexed.sort_by(|a, b| b.1.total_cmp(&a.1));
    indexed.into_iter().take(k).map(|(i, _)| i).collect()
}

// ── Correctness check ─────────────────────────────────────────

#[test]
fn bench_simd_topk_correctness_and_speed() {
    let k_values = [4, 8, 16];
    let n_values = [64, 128, 256, 512, 1024];
    let seed = 42;
    let iters = 1000;

    println!("╔══════════════════════════════════════════════════════════════════╗");
    println!("║  Plan 256 — SIMD Register TopK Benchmark (k≤16)               ║");
    println!("╠═════════╦════════╦════════════════╦════════════════╦═══════════╣");
    println!("║    k    ║   n    ║  SIMD (ns/call)║ Scalar(ns/call)║ Speedup   ║");
    println!("╠═════════╬════════╬════════════════╬════════════════╬═══════════╣");

    for &k in &k_values {
        for &n in &n_values {
            let scores = make_scores(n, seed);

            // Verify correctness first
            let mut simd_indices = Vec::with_capacity(k);
            argtopk(&scores, k, &mut simd_indices);
            let ref_indices = argtopk_reference(&scores, k);
            assert_eq!(
                simd_indices, ref_indices,
                "SIMD mismatch at k={k}, n={n}: simd={simd_indices:?} != ref={ref_indices:?}"
            );

            // Benchmark SIMD path
            let mut simd_indices = Vec::with_capacity(k);
            let start = std::time::Instant::now();
            for _ in 0..iters {
                simd_indices.clear();
                argtopk(&scores, k, &mut simd_indices);
            }
            let simd_ns = start.elapsed().as_nanos() as f64 / iters as f64;

            // Benchmark scalar path
            let mut scalar_indices = Vec::with_capacity(k);
            let start = std::time::Instant::now();
            for _ in 0..iters {
                scalar_indices.clear();
                argtopk_scalar_heap(&scores, k, &mut scalar_indices);
            }
            let scalar_ns = start.elapsed().as_nanos() as f64 / iters as f64;

            let speedup = scalar_ns / simd_ns;
            println!(
                "║ k={k:<5}║ n={n:<5}║ {simd_ns:>12.1}  ║ {scalar_ns:>12.1}  ║ {speedup:>7.2}x  ║"
            );
        }
    }

    println!("╚═════════╩════════╩════════════════╩════════════════╩═══════════╝");
}

// ── k=32 fallback benchmark (scalar path) ─────────────────────

#[test]
fn bench_simd_topk_k32_scalar_fallback() {
    let n_values = [64, 128, 256, 512, 1024];
    let seed = 99;
    let iters = 1000;
    let k = 32;

    println!();
    println!("╔══════════════════════════════════════════════════════════════════╗");
    println!("║  k=32 scalar fallback (selection sort) — n sweep              ║");
    println!("╠════════════════╦════════════════════════════════════════════════╣");
    println!("║       n        ║     ns/call                                    ║");
    println!("╠════════════════╬════════════════════════════════════════════════╣");

    for &n in &n_values {
        let scores = make_scores(n, seed);

        // Verify correctness
        let mut indices = Vec::with_capacity(k);
        argtopk(&scores, k, &mut indices);
        let ref_indices = argtopk_reference(&scores, k);
        assert_eq!(
            indices, ref_indices,
            "Scalar fallback mismatch at k={k}, n={n}"
        );

        // Benchmark
        let mut indices = Vec::with_capacity(k);
        let mut pairs = Vec::new();
        let start = std::time::Instant::now();
        for _ in 0..iters {
            indices.clear();
            pairs.clear();
            katgpt_rs::dash_attn::block_topk::argtopk_with_scratch(
                &scores,
                k,
                &mut indices,
                &mut pairs,
            );
        }
        let ns = start.elapsed().as_nanos() as f64 / iters as f64;

        println!("║ n={n:<12}║ {ns:>12.1} ns                                ║",);
    }

    println!("╚════════════════╩════════════════════════════════════════════════╝");
}

// ── Detailed sweep: fixed n=256, k sweep ──────────────────────

#[test]
fn bench_simd_topk_k_sweep_n256() {
    let k_values = [1, 2, 4, 8, 12, 16];
    let n = 256;
    let seed = 77;
    let iters = 2000;

    println!();
    println!("╔══════════════════════════════════════════════════════════════════╗");
    println!("║  n=256 — k sweep (SIMD path k≤16 vs scalar)                   ║");
    println!("╠═════════╦════════════════╦════════════════╦═════════════════════╣");
    println!("║    k    ║  SIMD (ns/call)║ Scalar(ns/call)║ Speedup             ║");
    println!("╠═════════╬════════════════╬════════════════╬═════════════════════╣");

    for &k in &k_values {
        let scores = make_scores(n, seed);

        // Correctness check
        let mut simd_indices = Vec::with_capacity(k);
        argtopk(&scores, k, &mut simd_indices);
        let ref_indices = argtopk_reference(&scores, k);
        assert_eq!(simd_indices, ref_indices, "Mismatch at k={k}");

        // SIMD benchmark
        let mut simd_indices = Vec::with_capacity(k);
        let start = std::time::Instant::now();
        for _ in 0..iters {
            simd_indices.clear();
            argtopk(&scores, k, &mut simd_indices);
        }
        let simd_ns = start.elapsed().as_nanos() as f64 / iters as f64;

        // Scalar benchmark
        let mut scalar_indices = Vec::with_capacity(k);
        let start = std::time::Instant::now();
        for _ in 0..iters {
            scalar_indices.clear();
            argtopk_scalar_heap(&scores, k, &mut scalar_indices);
        }
        let scalar_ns = start.elapsed().as_nanos() as f64 / iters as f64;

        let speedup = scalar_ns / simd_ns;
        println!(
            "║ k={k:<5}║ {simd_ns:>12.1}  ║ {scalar_ns:>12.1}  ║ {speedup:>7.2}x              ║"
        );
    }

    println!("╚═════════╩════════════════╩════════════════╩═════════════════════╝");
}

// ── Issue 808 addendum: distribution matrix + per-k crossover ────────────────
//
// The table recorded in Issue 808 was measured on ONE input distribution —
// `make_scores` above, quasi-random i.i.d. uniform via a hashed sinusoid.
// Option 4 in the issue flags exactly that: a real DashAttn block-score
// distribution may not look like it. This section measures the same
// SIMD-vs-scalar question across six score distributions and produces the
// per-k N_MIN crossover data option 1 needs (T2's measurement half).
//
// ⛍ It does NOT gate anything: the issue's own bar is that a dispatch change
// is decided by the owner on ≥ 2 microarchitectures, and this file provides
// one. The numbers land in `.benchmarks/810_argtopk_distribution_crossover.md`
// as the Raptor-Lake row of that decision table.
//
// Instrument: `tests/common/ab_timing.rs` (Issue-723 interleaved
// median-of-ratios). Arm a = `argtopk_scalar_heap` (baseline), arm b =
// `argtopk` (the SIMD dispatch — AVX2 via runtime detection on x86_64, NEON
// on aarch64), so `speedup = 1/median_ratio` and **< 1.00 is a loss** — the
// issue's convention. `[profile.release]` is `lto = "fat"` +
// `codegen-units = 1` (the Issue-723 Class-A2 folding regime): both arms
// churn the same four input positions per iteration and consume an index
// sink, and `ab_median_ratio` asserts loudly on a vanished arm.

#[path = "common/ab_timing.rs"]
mod ab_timing;

use std::hint::black_box;

/// Seeded splitmix64 — deterministic, no global RNG state (the Issue-809 class).
struct SplitMix64(u64);

impl SplitMix64 {
    fn next_f32(&mut self) -> f32 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        let v = z ^ (z >> 31);
        ((v >> 40) as f32) / (1u32 << 24) as f32
    }
}

/// Block-score distributions the routing layer actually plausibly sees.
///
/// i.i.d. shapes are distribution-free in insertion count (the streaming
/// top-k work is a function of the rank sequence), so the interesting arms
/// are the STRUCTURED ones: positional locality, early/late peak placement,
/// and cluster separation.
#[derive(Clone, Copy)]
enum Dist {
    /// i.i.d. uniform — the recorded table's family, for continuity.
    IidUniform,
    /// Gaussian-ish logits through sigmoid — clustered near 0.5 with tails.
    GaussSigmoid,
    /// AR(1) positional correlation — adjacent blocks score similarly
    /// (attention locality over contiguous token blocks).
    Locality,
    /// The top-scoring blocks sit at the START of the scan (attention sink):
    /// the heap threshold is set high immediately, later insertions rare.
    EarlyPeak,
    /// The top-scoring blocks sit at the END: maximal insertion work during
    /// the sweep.
    LatePeak,
    /// Block-sparse routing story: a small high cluster, a large low cluster.
    BimodalSparse,
}

const ALL_DISTS: [Dist; 6] = [
    Dist::IidUniform,
    Dist::GaussSigmoid,
    Dist::Locality,
    Dist::EarlyPeak,
    Dist::LatePeak,
    Dist::BimodalSparse,
];

impl Dist {
    fn name(self) -> &'static str {
        match self {
            Dist::IidUniform => "iid_uniform",
            Dist::GaussSigmoid => "gauss_sigmoid",
            Dist::Locality => "locality",
            Dist::EarlyPeak => "early_peak",
            Dist::LatePeak => "late_peak",
            Dist::BimodalSparse => "bimodal_sparse",
        }
    }

    /// `k` is needed so the peak arms always carry at least `k` top blocks —
    /// a peak smaller than k cannot set the threshold early and proves nothing.
    fn make(self, n: usize, k: usize, seed: u64) -> Vec<f32> {
        let mut rng = SplitMix64(seed ^ 0xD1B5_4A32_D192_ED03);
        let peak = (n / 20).max(k);
        match self {
            Dist::IidUniform => (0..n).map(|_| rng.next_f32()).collect(),
            Dist::GaussSigmoid => (0..n)
                .map(|_| {
                    // Irwin–Hall(3) ≈ Gaussian logit, scaled to σ≈1
                    let s = rng.next_f32() + rng.next_f32() + rng.next_f32();
                    let logit = (s - 1.5) * 4.0;
                    1.0 / (1.0 + (-logit).exp())
                })
                .collect(),
            Dist::Locality => {
                let mut s = rng.next_f32();
                (0..n)
                    .map(|_| {
                        s = 0.65 * s + 0.35 * rng.next_f32();
                        s
                    })
                    .collect()
            }
            Dist::EarlyPeak => (0..n)
                .map(|i| {
                    if i < peak {
                        0.85 + 0.15 * rng.next_f32()
                    } else {
                        0.35 * rng.next_f32()
                    }
                })
                .collect(),
            Dist::LatePeak => (0..n)
                .map(|i| {
                    if i >= n - peak {
                        0.85 + 0.15 * rng.next_f32()
                    } else {
                        0.35 * rng.next_f32()
                    }
                })
                .collect(),
            Dist::BimodalSparse => (0..n)
                .map(|_| {
                    if rng.next_f32() < 0.12 {
                        0.75 + 0.25 * rng.next_f32()
                    } else {
                        0.35 * rng.next_f32()
                    }
                })
                .collect(),
        }
    }
}

/// Per-iteration input churn: perturb four base positions by a golden-ratio
/// delta in [-1e-3, +1e-3]. Small enough to leave the distribution's shape
/// (and top-k membership, except at true near-ties) intact; large enough that
/// every iteration's input differs — the anti-hoist requirement under fat LTO.
/// Identical work in both arms, so it cancels in the ratio.
#[inline]
fn churn(buf: &mut [f32], i: usize, base: &[f32]) {
    let n = buf.len();
    let quarter = (n / 4).max(1);
    for p in 0..4usize {
        let pos = (i + p * quarter) % n;
        let t = (i as u64).wrapping_add(p as u64);
        let delta = ((t as f64 * 0.618_033_988_749_894_9).fract() - 0.5) as f32 * 2.0e-3;
        buf[pos] = base[pos] + delta;
    }
}

struct CellResult {
    scalar_ns: f64,
    simd_ns: f64,
    /// 1 / median per-round ratio (scalar ÷ SIMD) — the issue's speedup.
    speedup: f64,
    /// Smallest and largest per-round speedup — the box-agreement band.
    speedup_lo: f64,
    speedup_hi: f64,
}

/// One interleaved A/B measurement of `argtopk` (SIMD dispatch) vs
/// `argtopk_scalar_heap`, with per-cell correctness verification against a
/// full-sort reference first.
fn measure_cell(base: &[f32], k: usize, rounds: usize) -> CellResult {
    let n = base.len();
    let iters = ((4_000_000.0 / (n.max(1) as f64 * 1.5)) as usize).clamp(256, 50_000);

    // Correctness on the base scores before any timing.
    let mut idx_simd = Vec::with_capacity(k);
    let mut idx_scalar = Vec::with_capacity(k);
    argtopk(base, k, &mut idx_simd);
    argtopk_scalar_heap(base, k, &mut idx_scalar);
    let ref_idx = argtopk_reference(base, k);
    assert_eq!(idx_simd, ref_idx, "SIMD mismatch at k={k}, n={n}");
    assert_eq!(idx_scalar, ref_idx, "scalar-heap mismatch at k={k}, n={n}");

    let mut scratch_a = base.to_vec();
    let mut idx_a = Vec::with_capacity(k);
    let mut sink_a = 0u64;
    let mut scratch_b = base.to_vec();
    let mut idx_b = Vec::with_capacity(k);
    let mut sink_b = 0u64;

    let ab = ab_timing::ab_median_ratio(
        rounds,
        iters,
        iters,
        |i| {
            churn(&mut scratch_a, i, base);
            idx_a.clear();
            argtopk_scalar_heap(&scratch_a, k, &mut idx_a);
            sink_a = sink_a.wrapping_add(idx_a[0] as u64).rotate_left(1);
        },
        |i| {
            churn(&mut scratch_b, i, base);
            idx_b.clear();
            argtopk(&scratch_b, k, &mut idx_b);
            sink_b = sink_b.wrapping_add(idx_b[0] as u64).rotate_left(1);
        },
    );
    black_box((sink_a, sink_b));

    CellResult {
        scalar_ns: ab.a_ns_per_iter(),
        simd_ns: ab.b_ns_per_iter(),
        speedup: 1.0 / ab.median,
        speedup_lo: 1.0 / ab.max(),
        speedup_hi: 1.0 / ab.min(),
    }
}

/// The full distribution × (k, n) grid — does the AVX2/NEON dispatch still
/// lose where the recorded table says it does, once the input looks like
/// block scores instead of i.i.d. uniform?
#[test]
fn bench_simd_topk_issue808_distribution_matrix() {
    let k_values = [1usize, 2, 4, 8, 16];
    let n_values = [64usize, 128, 256, 512, 1024];
    let rounds = 9;

    println!(
        "\n== Issue 808 distribution matrix (speedup = scalar/SIMD, <1.00 is a loss) =="
    );
    println!(
        "{:<15} {:>4} {:>6} {:>12} {:>12} {:>9}  {:>17}",
        "distribution", "k", "n", "scalar ns", "simd ns", "speedup", "round band"
    );

    for &dist in &ALL_DISTS {
        for &k in &k_values {
            for &n in &n_values {
                let base = dist.make(n, k, 0x5EED_600D + (n as u64) * 7919);
                let r = measure_cell(&base, k, rounds);
                println!(
                    "{:<15} {:>4} {:>6} {:>12.1} {:>12.1} {:>8.2}x  {:>6.2}..{:<6.2}",
                    dist.name(),
                    k,
                    n,
                    r.scalar_ns,
                    r.simd_ns,
                    r.speedup,
                    r.speedup_lo,
                    r.speedup_hi,
                );
            }
        }
    }
}

/// The per-k N_MIN crossover sweep — option 1's data half. Sweeps n upward at
/// each k until the SIMD dispatch reaches parity (speedup ≥ 1.00), on two
/// distribution bookends (i.i.d. and the locality shape a real block-score
/// stream plausibly has). One box, one microarchitecture — the Raptor-Lake
/// row of the table the owner's T2 needs before any dispatch change.
#[test]
fn bench_simd_topk_issue808_crossover_nmin() {
    let k_values = [2usize, 4, 8, 12, 16];
    let n_sweep = [
        64usize, 128, 192, 256, 384, 512, 768, 1024, 1536, 2048, 3072, 4096, 6144, 8192,
    ];
    let rounds = 9;

    println!("\n== Issue 808 per-k crossover (first n with speedup ≥ 1.00) ==");
    println!(
        "{:<15} {:>4} {:>6} {:>12} {:>12} {:>9}  {:>17}",
        "distribution", "k", "n", "scalar ns", "simd ns", "speedup", "round band"
    );

    for &dist in &[Dist::IidUniform, Dist::Locality] {
        for &k in &k_values {
            let mut n_min = None;
            let mut n_min_05 = None;
            for &n in &n_sweep {
                let base = dist.make(n, k, 0xC0FF_EE01 + (n as u64) * 104729);
                let r = measure_cell(&base, k, rounds);
                println!(
                    "{:<15} {:>4} {:>6} {:>12.1} {:>12.1} {:>8.2}x  {:>6.2}..{:<6.2}",
                    dist.name(),
                    k,
                    n,
                    r.scalar_ns,
                    r.simd_ns,
                    r.speedup,
                    r.speedup_lo,
                    r.speedup_hi,
                );
                if n_min_05.is_none() && r.speedup >= 1.05 {
                    n_min_05 = Some(n);
                }
                if n_min.is_none() && r.speedup >= 1.00 {
                    n_min = Some(n);
                    break;
                }
            }
            match (n_min, n_min_05) {
                (Some(n1), Some(n2)) => println!(
                    "--> N_MIN[{}, k={k}] = {n1} (speedup ≥ 1.05 at {n2})",
                    dist.name()
                ),
                (Some(n1), None) => {
                    println!("--> N_MIN[{}, k={k}] = {n1} (no ≥1.05 point in sweep)", dist.name())
                }
                (None, _) => println!(
                    "--> N_MIN[{}, k={k}] = >{} (no crossing in sweep)",
                    dist.name(),
                    n_sweep[n_sweep.len() - 1]
                ),
            }
        }
    }
}
