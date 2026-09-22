//! Bench 873 — `pool_admission` GOAT G2 (Issue 873 primitive A): steady-state
//! latency of the admission policy's per-cycle paths.
//!
//! Measured (best-of-chunks absolute budgets — plain `Instant` loops, the
//! `bench_319_g8e` house style; interleaving is for A/B arms, an absolute
//! budget takes the best of repeated chunks, the correct treatment for a
//! deterministic scan with no comparison arm):
//!
//! 1. **`consider` + 2× `update_want` at K=32** (mini-AGI's resident scale)
//!    and **K=256** (a large working set) — a deterministic want pattern
//!    that mostly REJECTS (hysteresis: the steady state of a flat
//!    distribution) with periodic admit bursts. The scan is O(live); the
//!    bar is the regression fence.
//! 2. **`update_want` alone at K=256** — the every-cycle touch, O(live)
//!    identity scan.
//! 3. **`fair_turn_next` on a terminated sweep at U=4096** — the O(1)
//!    rejection via the `pending` counter; must not rescan the universe.
//!
//! Every timed body sinks its outcomes through `black_box` AND accumulates
//! them into a checksum consumed after the loop — the work is live, so the
//! optimiser cannot delete it (the `timed_region_guard` law: `black_box` on
//! both arguments and result). Deterministic end to end: arithmetic want
//! patterns, no RNG of any kind.
//!
//! ```sh
//! cargo bench -p katgpt-core --features pool_admission --bench bench_873_pool_admission_goat
//! ```

use std::hint::black_box;
use std::time::Instant;

use katgpt_core::pool_admission::{AdmissionOutcome, AdmissionSet, PoolAdmissionConfig};

/// Chunks per measurement (best-of; discards preemption spikes).
const CHUNKS: usize = 240;
/// Steady-state cycles per chunk. Large enough that each chunk sits far
/// above timer resolution (a cycle is tens–hundreds of ns).
const CYCLES: usize = 4_096;

/// Best-of-`chunks` wall time per cycle (ns) for `body`, after 4 warmup
/// chunks. `body` returns a sink value that MUST be consumed by the caller
/// (the loud-zero defence lives at the call sites, where the sink lands in a
/// checksum).
fn best_ns_per_cycle<F: FnMut() -> u64>(mut body: F) -> f64 {
    for _ in 0..4 {
        let _ = black_box(body()); // warmup, discarded
    }
    let mut best = f64::INFINITY;
    for _ in 0..CHUNKS {
        let t = Instant::now();
        let sink = body();
        let elapsed = t.elapsed().as_secs_f64() / CYCLES as f64;
        best = best.min(black_box(elapsed));
        let _ = black_box(sink);
    }
    best * 1.0e9
}

/// Fill a set to capacity with staggered admission ticks, so a mixed
/// evictable/newborn population persists across the bench (ages only grow —
/// residents admitted `dwell..2·dwell` before the probe tick are evictable
/// forever after).
fn filled(k: usize, dwell: u64) -> AdmissionSet {
    let mut s = AdmissionSet::new(k, PoolAdmissionConfig::with_dwell(dwell));
    let base = 10_000u64;
    for i in 0..k as u64 {
        // wants in 1..=4: a flat band the candidate pattern plays against.
        let _ = s.consider(i, 1.0 + (i % 4) as f32, base + (i % dwell));
    }
    s
}

fn main() {
    println!("bench_873_pool_admission_goat (Issue 873 A / G2)\n");

    // ── consider (+ 2 resident touches) @ K=32 and K=256 ─────────────────
    let mut cycle_ns: Vec<(usize, f64)> = Vec::new();
    for k in [32usize, 256] {
        let mut s = filled(k, 8);
        let probe_tick = 50_000u64;
        let mut checksum = 0u64;
        let per_cycle = best_ns_per_cycle(|| {
            let mut sink = 0u64;
            for c in 0..CYCLES {
                // Want pattern: (c % 97) × 0.07 spans 0.00..6.72 — mostly
                // REJECT against victims ~1..4 at margin 1.10, periodically
                // clearing it (admit bursts): exactly the hysteresis mix.
                let want = 1.0 + ((c % 97) as f32) * 0.07;
                let out = s.consider(
                    black_box(1_000_000 + (c % 977) as u64),
                    black_box(want),
                    black_box(probe_tick + c as u64),
                );
                if matches!(out, AdmissionOutcome::Admitted { .. }) {
                    sink += 1;
                }
                // Re-touch two residents per cycle at band values so the set
                // does not drift to all-high wants (rejects must persist).
                let r = (c as u64) % k as u64;
                s.update_want(black_box(r), black_box(1.0 + ((r + c as u64) % 4) as f32));
                let r2 = (r + 7) % k as u64;
                s.update_want(black_box(r2), black_box(1.0 + ((r2 + c as u64) % 4) as f32));
            }
            sink
        });
        println!(
            "  consider + 2×update_want  K={k:<4} : {per_cycle:8.1} ns/cycle  ({CYCLES} cycles/chunk, best of {CHUNKS})"
        );
        cycle_ns.push((k, per_cycle));
        checksum = checksum.wrapping_add(1);
        let _ = black_box(checksum);
    }

    // ── update_want alone @ K=256 ─────────────────────────────────────────
    {
        let mut s = filled(256, 8);
        let per_touch = best_ns_per_cycle(|| {
            let mut sink = 0u64;
            for c in 0..CYCLES {
                let id = (c % 256) as u64;
                s.update_want(black_box(id), black_box(2.0 + (c % 5) as f32 * 0.1));
                sink += s.row_for(id).map(|r| r.want.to_bits() as u64).unwrap_or(0);
            }
            sink
        });
        println!("  update_want               K=256  : {per_touch:8.1} ns/touch");
    }

    // ── fair_turn_next on a TERMINATED sweep @ U=4096 ─────────────────────
    {
        let mut s = filled(32, 8);
        s.note_universe(4_096);
        while s.fair_turn_next().is_some() {} // terminate the sweep
        let per_call = best_ns_per_cycle(|| {
            let mut sink = 0u64;
            for c in 0..CYCLES {
                if s.fair_turn_next().is_some() {
                    sink += 1; // must NEVER fire: the sweep is terminated
                }
                sink += (c & 1) as u64;
            }
            sink
        });
        println!(
            "  fair_turn_next (done)     U=4096 : {per_call:8.1} ns/call   (O(1) rejection — no universe rescan)"
        );
    }

    // ── the GOAT bars (asserted AFTER the measurements print) ─────────────
    // Fences with ~an order of magnitude of headroom over the measured
    // quiet-box values (recorded in .benchmarks/873): O(live) is the
    // contract; a breach means the scan accidentally went quadratic or an
    // allocation crept onto the per-cycle path.
    println!("\n  G2 bars:");
    let mut all_pass = true;
    for (k, measured) in &cycle_ns {
        let bar = if *k <= 32 { 250.0 } else { 1_500.0 };
        let pass = *measured <= bar;
        all_pass &= pass;
        println!(
            "    K={k:<4} ns/cycle {measured:8.1} ≤ {bar:6.0} : {}",
            if pass { "PASS" } else { "FAIL" }
        );
    }
    assert!(
        all_pass,
        "pool_admission G2 regression fence breached — see measurements above"
    );
    println!("\n  G2 PASS (fence, not a claim of optimality — O(live) is the contract)");
}
