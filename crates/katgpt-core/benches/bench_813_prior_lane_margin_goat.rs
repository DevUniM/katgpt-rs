//! Issue 819 (Research 566) — prior-lane + sink-margin-forecast GOAT gate.
//!
//! G3  latency: lane-on forward ratio vs lane-off ≤ 1.10× at n=128 d=64
//!     (the lane is one f32 add per key per query row over scratch scores);
//!     `forecast_stable_positions` ns/call (O(1) scalar exp).
//! G4  alloc-free: lane-on steady-state allocs == lane-off allocs (expect 0
//!     with caller scratch); forecast 0 allocs; flat sink scan with margins
//!     0 steady-state allocs with pre-reserved out.
//!
//! Harness = false, std::time::Instant (the bench_411 pattern). Exit 1 on
//! any gate failure. Run:
//!   cargo bench -p katgpt-core --bench bench_813_prior_lane_margin_goat
//!
//! Reference: Research 566 §5 (gate sketch); feature-gated per the
//! no-default-consumer rule — this bench RUNS the gates, promotion stays a
//! owner call gated on a runtime consumer (served GGUF models deliberately
//! do not consume lanes; Issue 819 non-goal).

use std::alloc::{GlobalAlloc, Layout, System};
use std::sync::Arc;
use std::sync::atomic::{AtomicUsize, Ordering};

use katgpt_core::data_probe::{
    SinkClassifierConfig, StableRankScratch, classify_all_sinks_flat, forecast_stable_positions,
};
use katgpt_core::parallax_attn::{
    ParallaxActivation, ParallaxConfig, ParallaxScratch, tiled_attention_parallax_forward,
};

// ── G4: counting allocator ────────────────────────────────────────────────

static ALLOCS: AtomicUsize = AtomicUsize::new(0);

struct Counting;

unsafe impl GlobalAlloc for Counting {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        ALLOCS.fetch_add(1, Ordering::Relaxed);
        unsafe { System.alloc(layout) }
    }
    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        unsafe { System.dealloc(ptr, layout) }
    }
    unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, new_size: usize) -> *mut u8 {
        ALLOCS.fetch_add(1, Ordering::Relaxed);
        unsafe { System.realloc(ptr, layout, new_size) }
    }
}

#[global_allocator]
static GLOBAL: Counting = Counting;

fn allocs() -> usize {
    ALLOCS.load(Ordering::Relaxed)
}

// ── fixtures ──────────────────────────────────────────────────────────────

const N: usize = 128;
const D: usize = 64;

fn rand_buf(len: usize, seed: u64) -> Vec<f32> {
    let mut s = seed;
    (0..len)
        .map(|_| {
            s = s
                .wrapping_mul(6364136223846793005)
                .wrapping_add(1442695040888963407);
            ((s >> 33) as f32 / (u32::MAX as f32)) - 0.5
        })
        .collect()
}

fn cfg_with(prior: Option<std::sync::Arc<[f32]>>) -> ParallaxConfig {
    ParallaxConfig {
        gate_scale: 0.0,
        activation: ParallaxActivation::Sigmoid,
        prior_logits: prior,
        ..Default::default()
    }
}

fn best_of_us<F: FnMut()>(mut f: F, iters: usize) -> f64 {
    // best-of (Issue 723 harness): the loaded-box-robust latency figure.
    let mut best = f64::INFINITY;
    for _ in 0..iters {
        let t = std::time::Instant::now();
        f();
        let us = t.elapsed().as_secs_f64() * 1e6;
        if us < best {
            best = us;
        }
    }
    best
}

fn main() {
    println!("== Issue 819 GOAT gate: prior-logit lane + sink margin forecast ==");
    let mut failures = 0usize;

    // ── G3a: lane-on vs lane-off forward ratio ────────────────────────────
    let q = rand_buf(N * D, 0xABCDEF01);
    let k = rand_buf(N * D, 0x12345678);
    let v = rand_buf(N * D, 0x9ABCDEF0);
    let lane: std::sync::Arc<[f32]> = {
        let mut s = 0x51ED_270Bu64;
        let table: Vec<f32> = (0..N)
            .map(|_| {
                s = s.wrapping_mul(6364136223846793005).wrapping_add(1);
                ((s >> 33) as f32 / (u32::MAX as f32)) * 4.0 - 2.0 // logit in [−2, 2]
            })
            .collect();
        Arc::from(table.into_boxed_slice())
    };

    let mut scratch_off = ParallaxScratch::new(N, D);
    let mut scratch_on = ParallaxScratch::new(N, D);
    let mut out = vec![0.0f32; N * D];

    // Warmup.
    for _ in 0..5 {
        tiled_attention_parallax_forward(
            &q,
            &k,
            &v,
            &mut out,
            N,
            D,
            (D as f32).sqrt() / 8.0,
            &vec![0.0; D * D],
            &vec![0.0; D],
            &cfg_with(None),
            Some(&mut scratch_off),
        );
        tiled_attention_parallax_forward(
            &q,
            &k,
            &v,
            &mut out,
            N,
            D,
            (D as f32).sqrt() / 8.0,
            &vec![0.0; D * D],
            &vec![0.0; D],
            &cfg_with(Some(Arc::clone(&lane))),
            Some(&mut scratch_on),
        );
    }

    let iters = 200;
    let t_off = best_of_us(
        || {
            tiled_attention_parallax_forward(
                &q,
                &k,
                &v,
                &mut out,
                N,
                D,
                (D as f32).sqrt() / 8.0,
                &vec![0.0; D * D],
                &vec![0.0; D],
                &cfg_with(None),
                Some(&mut scratch_off),
            )
        },
        iters,
    );
    let t_on = best_of_us(
        || {
            tiled_attention_parallax_forward(
                &q,
                &k,
                &v,
                &mut out,
                N,
                D,
                (D as f32).sqrt() / 8.0,
                &vec![0.0; D * D],
                &vec![0.0; D],
                &cfg_with(Some(Arc::clone(&lane))),
                Some(&mut scratch_on),
            )
        },
        iters,
    );
    let ratio = t_on / t_off;
    println!("G3a lane-off {t_off:.2} µs | lane-on {t_on:.2} µs | ratio {ratio:.3}× (n={N} d={D})");
    if ratio > 1.10 {
        eprintln!("⛔ G3a FAIL: lane-on ratio {ratio:.3}× > 1.10×");
        failures += 1;
    }

    // ── G3b: forecast O(1) ────────────────────────────────────────────────
    let t_fc = best_of_us(
        || {
            let mut acc = 0.0f32;
            for i in 0..1000 {
                acc += forecast_stable_positions(i as f32 * 0.001);
            }
            std::hint::black_box(acc);
        },
        50,
    ) / 1000.0;
    println!("G3b forecast_stable_positions {t_fc:.4} µs/call (target < 0.05 µs)");
    if t_fc > 0.05 {
        eprintln!("⛔ G3b FAIL: forecast {t_fc:.4} µs/call > 0.05 µs");
        failures += 1;
    }

    // ── G3c: sink scan with margins (info: total cost of the O(n²) pass) ──
    let mut attn = rand_buf(N * N, 0xBEEF);
    let vals = rand_buf(N * D, 0xF00D);
    // Force column 0 into sink territory (strength ≈ 0.9 > τ_sink = 0.5) so
    // the margin estimator actually runs — random attention elects no
    // candidates and the per-candidate margin pass would never execute.
    for i in 0..N {
        attn[i * N] = 0.9;
    }
    let mut sink_scratch = StableRankScratch::new(D);
    let mut diags: Vec<katgpt_core::data_probe::SinkDiagnostic> = Vec::with_capacity(8);
    let cfg = SinkClassifierConfig::default();
    let t_scan = best_of_us(
        || {
            diags.clear();
            classify_all_sinks_flat(&attn, N, &vals, D, &cfg, &mut sink_scratch, &mut diags);
        },
        50,
    );
    println!(
        "G3c classify_all_sinks_flat (margins on) {t_scan:.2} µs total, {} candidate(s) with margins — margin pass is O(n²), same class as the col_sums pass",
        diags.len()
    );

    // ── G4: allocation counts (DELTAS over warm loops — the counter is
    // cumulative, so a snapshot comparison is meaningless) ────────────────
    // r/x are hoisted: the measured path is the kernel, not call-site temps.
    let r0 = vec![0.0f32; D * D];
    let x0 = vec![0.0f32; D];
    let warm = 10;
    let mut before = allocs();
    for _ in 0..warm {
        tiled_attention_parallax_forward(
            &q,
            &k,
            &v,
            &mut out,
            N,
            D,
            1.0,
            &r0,
            &x0,
            &cfg_with(None),
            Some(&mut scratch_off),
        );
    }
    let a0 = allocs() - before;
    before = allocs();
    for _ in 0..warm {
        tiled_attention_parallax_forward(
            &q,
            &k,
            &v,
            &mut out,
            N,
            D,
            1.0,
            &r0,
            &x0,
            &cfg_with(Some(Arc::clone(&lane))),
            Some(&mut scratch_on),
        );
    }
    let a1 = allocs() - before;
    println!("G4 forward allocs over {warm} warm calls: lane-off {a0}, lane-on {a1}");
    if a0 != a1 {
        eprintln!("⛔ G4 FAIL: lane-on allocs {a1} != lane-off allocs {a0}");
        failures += 1;
    }

    let before = allocs();
    for _ in 0..1000 {
        std::hint::black_box(forecast_stable_positions(1.5));
    }
    let f0 = allocs() - before;
    println!("G4 forecast allocs over 1000 calls: {f0}");
    if f0 > 0 {
        eprintln!("⛔ G4 FAIL: forecast allocates ({f0})");
        failures += 1;
    }

    // Sink scan steady state: warm once (grows out + scratch), then count.
    diags.clear();
    classify_all_sinks_flat(&attn, N, &vals, D, &cfg, &mut sink_scratch, &mut diags);
    let s0 = allocs();
    for _ in 0..10 {
        diags.clear();
        classify_all_sinks_flat(&attn, N, &vals, D, &cfg, &mut sink_scratch, &mut diags);
    }
    let s1 = allocs() - s0;
    println!("G4 sink scan allocs over 10 warm calls: {s1}");
    if s1 > 0 {
        eprintln!("⛔ G4 FAIL: sink scan steady-state allocs {s1} > 0");
        failures += 1;
    }

    // ── verdict ───────────────────────────────────────────────────────────
    if failures == 0 {
        println!(
            "✓ ALL GATES PASS (G3 lane ratio {ratio:.3}×; forecast {t_fc:.4} µs; G4 lane {a1} allocs, forecast 0, scan {s1})"
        );
    } else {
        eprintln!("⛔ {failures} gate(s) FAILED");
        std::process::exit(1);
    }
}
