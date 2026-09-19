//! GOAT gate — calibration staleness at the freeze/thaw seam (Issue 841 §B-3).
//!
//! ```bash
//! cargo bench -p katgpt-core --features calibration_staleness \
//!     --bench bench_841_calibration_staleness_goat
//! # G4 needs an allocator in the profile:
//! cargo bench -p katgpt-core --features calibration_staleness,alloc_tracking \
//!     --bench bench_841_calibration_staleness_goat
//! ```
//!
//! **G1 correctness** — a snapshot swap refuses, an unchanged snapshot admits,
//! and the admitted value is bit-identical to the unguarded one. Both sides,
//! because a guard that only ever refuses is as useless as one that only ever
//! admits.
//!
//! **G2 perf** — the guard's per-call cost against the calibrated `apply` it
//! sits in front of. Read as an ABSOLUTE budget (`best-of-N` minimum), not an
//! A/B ratio: the two arms here are not a paired comparison of the same work,
//! and AGENTS.md § *A ratio of two SEQUENTIALLY-timed arms measures the BOX*
//! is the reason this target states a budget instead.
//!
//! **G3 no-regression** — the fresh path returns exactly what an unguarded
//! calibration returns, over a swept input grid. The guard cannot change a
//! decision it admits.
//!
//! **G4 alloc-free** — zero allocations across both paths. Gated on
//! `any(debug_assertions, feature = "alloc_tracking")` per the Issue-741 rule;
//! it prints a LOUD skip rather than a silent pass when the profile carries no
//! allocator, because a green run with G4 compiled out is otherwise
//! indistinguishable from a green run with G4 satisfied.

use std::hint::black_box;
use std::time::Instant;

use katgpt_core::calibration_staleness::{SnapshotBound, SnapshotId, Staleness};

#[cfg(any(debug_assertions, feature = "alloc_tracking"))]
#[global_allocator]
static BENCH_ALLOC: katgpt_core::alloc::TrackingAllocator = katgpt_core::alloc::TrackingAllocator;

const C_A: [u8; 32] = [0xA5; 32];
const C_B: [u8; 32] = [0x5A; 32];

/// The thing that goes stale: a Platt (temperature, bias) pair.
type Platt = (f32, f32);

#[inline]
fn apply(p: f32, (t, b): Platt) -> f32 {
    1.0 / (1.0 + (-(p * t + b)).exp())
}

/// Best-of-`rounds` minimum nanoseconds per call.
///
/// The MINIMUM, not the mean: a loaded box can only ever make a round slower,
/// so the minimum is the load-robust statistic. AGENTS.md § *A latency number
/// without its BOX STATE is not a measurement* — the box state is printed
/// beside the figure rather than assumed.
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
        black_box(acc);
        best = best.min(ns);
    }
    best
}

fn main() {
    let mut failures: Vec<String> = Vec::new();
    println!("── Bench 841 — calibration staleness at the freeze/thaw seam ──\n");

    let fitted = SnapshotId::new(4, C_A);
    let cal: SnapshotBound<Platt> = SnapshotBound::new((2.0, -0.5), fitted);

    // ── G1: both sides of the predicate ────────────────────────────────────
    let g1_fresh = cal.get(fitted).is_some();
    let g1_swapped = cal.get(SnapshotId::new(5, C_B)).is_none();
    let g1_unbumped = cal.staleness(SnapshotId::new(4, C_B)) == Staleness::CommitmentMoved;
    let g1_unversioned = cal.staleness(SnapshotId::UNVERSIONED) == Staleness::Unversioned;
    let g1 = g1_fresh && g1_swapped && g1_unbumped && g1_unversioned;
    println!(
        "G1 correctness   fresh_admits={g1_fresh} swap_refuses={g1_swapped} \
         unbumped_swap_refuses={g1_unbumped} unversioned_refuses={g1_unversioned}  → {}",
        verdict(g1)
    );
    if !g1 {
        failures.push("G1: the predicate does not hold on all four arms".into());
    }

    // ── G3: the admitted path is bit-identical to the unguarded one ────────
    let raw: Platt = (2.0, -0.5);
    let mut g3 = true;
    let mut n_swept = 0_usize;
    for i in 0..=1000_u32 {
        let p = i as f32 / 1000.0;
        let guarded = cal.get(fitted).copied().map(|tb| apply(p, tb));
        let unguarded = apply(p, raw);
        n_swept += 1;
        match guarded {
            Some(v) if v.to_bits() == unguarded.to_bits() => {}
            _ => {
                g3 = false;
                break;
            }
        }
    }
    println!(
        "G3 no-regression bit-identical over {n_swept} swept inputs  → {}",
        verdict(g3)
    );
    if !g3 {
        failures.push("G3: the guard changed a value it admitted".into());
    }

    // ── G2: absolute budget ────────────────────────────────────────────────
    const ROUNDS: usize = 9;
    const ITERS: usize = 200_000;

    let guard_ns = best_of_ns(ROUNDS, ITERS, || match cal.get(black_box(fitted)) {
        Some(tb) => tb.0,
        None => 0.0,
    });
    let apply_ns = best_of_ns(ROUNDS, ITERS, || apply(black_box(0.6), black_box(raw)));
    let refuse_ns = best_of_ns(ROUNDS, ITERS, || {
        match cal.get(black_box(SnapshotId::new(5, C_B))) {
            Some(tb) => tb.0,
            None => 0.0,
        }
    });

    // The budget is the calibrated apply this guard protects. A guard costing
    // more than the work it guards is a guard nobody will wire.
    const BUDGET_RATIO: f64 = 1.0;
    let ratio = guard_ns / apply_ns.max(f64::MIN_POSITIVE);
    let g2 = ratio <= BUDGET_RATIO;
    println!(
        "G2 perf          guard={guard_ns:.3} ns/call  apply(sigmoid)={apply_ns:.3} ns/call  \
         refuse={refuse_ns:.3} ns/call  ratio={ratio:.3} (budget <= {BUDGET_RATIO:.2})  → {}",
        verdict(g2)
    );
    println!(
        "                 best-of-{ROUNDS} minimum over {ITERS} iters/round; \
         the minimum is the load-robust statistic — record the box state beside it."
    );
    if !g2 {
        failures.push(format!(
            "G2: guard {guard_ns:.3} ns/call is {ratio:.3}x the apply it protects"
        ));
    }

    // ── G4: allocation-free ────────────────────────────────────────────────
    #[cfg(any(debug_assertions, feature = "alloc_tracking"))]
    {
        katgpt_core::alloc::reset_alloc_stats();
        let mut acc = 0.0_f32;
        for i in 0..10_000 {
            let id = match i % 2 {
                0 => fitted,
                _ => SnapshotId::new(5, C_B),
            };
            acc += cal.get(black_box(id)).map_or(0.0, |tb| apply(0.6, *tb));
        }
        black_box(acc);
        let (n_allocs, bytes) = katgpt_core::alloc::get_alloc_stats();
        let g4 = n_allocs == 0;
        println!(
            "G4 alloc-free    {n_allocs} alloc(s), {bytes} byte(s) over 10000 mixed \
             fresh/stale calls  → {}",
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
        true => println!("✓ Bench 841 PASSED — every measured gate holds"),
        false => {
            for f in &failures {
                println!("✗ {f}");
            }
            println!("\n✗ Bench 841 FAILED — {} gate(s)", failures.len());
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
