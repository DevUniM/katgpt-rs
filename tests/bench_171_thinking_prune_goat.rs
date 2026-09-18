//! GOAT Proof: Thinking Prune — FrozenBaseGuard for Token-Level DDTree (Plan 171).
//!
//! Validates three properties:
//! P1: FrozenBaseGuard intermediate hops produce STRICTLY MORE Uniform nodes
//!     (structural dominance — a tie is a failure, see Issue 831 T3)
//! P2: FrozenBaseGuard produces identical output to Uniform when screening is cheap
//!     (NoScreeningPruner — confirms correctness of the delegation)
//! P3: Wall-clock timing — FrozenBaseGuard with an expensive screener is >= 30%
//!     faster than Uniform at intermediate hops (the actual performance claim),
//!     measured as an INTERLEAVED median of ratios (Issue 831 T2)
//! P4: Single-hop edge case — FrozenBaseGuard applies full screening when hop is final

#[path = "common/ab_timing.rs"]
mod ab_timing;

use katgpt_rs::speculative::{
    build_dd_tree_screened, extract_best_path,
    types::{NoScreeningPruner, ScreeningPruner},
};
use katgpt_rs::types::Config;

#[cfg(feature = "thinking_prune")]
use katgpt_rs::pruners::PrunerSchedule;
#[cfg(feature = "thinking_prune")]
use katgpt_rs::speculative::build_dd_tree_screened_with_schedule;

// ── Helpers ────────────────────────────────────────────────────

/// Simulated expensive screener: injects artificial delay to model WASM/validator cost.
#[derive(Debug, Clone)]
struct ExpensiveScreener {
    /// Base relevance to return (0.0–1.0)
    base_relevance: f32,
    /// Artificial work per call (loop iterations)
    work_per_call: u32,
}

impl ScreeningPruner for ExpensiveScreener {
    fn relevance(&self, _depth: usize, _token_idx: usize, _parent_tokens: &[usize]) -> f32 {
        // Simulate expensive WASM validator call
        let mut acc: f32 = 0.0;
        for i in 0..self.work_per_call {
            acc += (i as f32).sin() * (i as f32).cos();
        }
        // ⛔ This MUST be `black_box`, and it used to be `let _ = acc;` under a
        // comment claiming it prevented the optimiser from removing the work.
        // It does not: the loop is pure and its result dropped, which is the
        // exact shape Issue 723 T5 measured being deleted by rustc 1.98.1 +
        // fat LTO. In release the "expensive" screener cost NOTHING, so P3 was
        // comparing two arms that both skipped the same free call — which is
        // why 50x the `work_per_call` moved the measured speedup only from
        // 0.4% to 3.1% (Issue 831, measured 2026-09-18).
        std::hint::black_box(acc);
        self.base_relevance
    }
}

/// A screener that returns different relevance per depth to ensure differentiation.
#[derive(Debug, Clone)]
struct VaryingScreener {
    relevances: Vec<f32>,
}

impl ScreeningPruner for VaryingScreener {
    fn relevance(&self, depth: usize, _token_idx: usize, _parent_tokens: &[usize]) -> f32 {
        self.relevances.get(depth).copied().unwrap_or(1.0)
    }
}

fn make_config() -> Config {
    let mut c = Config::draft();
    c.screening_threshold = 0.3;
    c.tree_budget = 512;
    c
}

fn random_marginals(depths: usize, vocab: usize, seed: u32) -> Vec<Vec<f32>> {
    let mut rng = katgpt_rs::types::Rng::new(seed as u64);
    (0..depths)
        .map(|_| {
            let mut m: Vec<f32> = (0..vocab).map(|_| rng.uniform()).collect();
            let sum: f32 = m.iter().sum();
            for v in m.iter_mut() {
                *v /= sum;
            }
            m
        })
        .collect()
}

fn marginals_refs(marginals: &[Vec<f32>]) -> Vec<&[f32]> {
    marginals.iter().map(|m| m.as_slice()).collect()
}

// ══════════════════════════════════════════════════════════════════════════
// P1: Structural Dominance — FrozenBaseGuard >= Uniform nodes
// ══════════════════════════════════════════════════════════════════════════

#[cfg(feature = "thinking_prune")]
fn proof_p1_structural_dominance() {
    println!("\n── P1: FrozenBaseGuard intermediate produces >= Uniform nodes ──\n");

    let mut config = make_config();
    // ⛔ P1's own budget, and it is the whole of Issue 831 T3. At the shared
    // `tree_budget = 512` this proof was VACUOUS: both schedules hit the cap
    // and reported 1536 nodes (512 x 3 hops) on all 10 seeds — `Frozen wins=0,
    // Uniform wins=0, Ties=10` — so `>=` passed on exact equality every time
    // and "the two schedules build the same tree" was indistinguishable from
    // structural dominance. The budget was masking the mechanism, not the
    // screener: uncapped, the same fixture measures Uniform 2268 against
    // FrozenBaseGuard 200756. 4096 is large enough for Uniform to reach its
    // natural 2268 and for the gap to be real (8948), and small enough not to
    // build a 200k-node tree ten times to say so.
    config.tree_budget = 4096;
    let depths = 5;
    let vocab = config.vocab_size;
    let n_trials = 10;

    let mut frozen_wins = 0;
    let mut uniform_wins = 0;
    let mut ties = 0;

    // Screener that rejects some tokens (simulates real pruning)
    let screener = VaryingScreener {
        relevances: vec![0.8, 0.4, 0.2, 0.6, 0.9],
    };

    for seed in 0..n_trials {
        let marginals = random_marginals(depths, vocab, seed);
        let refs = marginals_refs(&marginals);

        // Simulate 3-hop SpecHop pipeline
        let total_hops = 3;

        // Uniform: every hop applies full screening
        let mut uniform_total_nodes = 0;
        for hop in 0..total_hops {
            let tree = build_dd_tree_screened_with_schedule(
                &refs,
                &config,
                &screener,
                true,
                PrunerSchedule::Uniform,
                hop,
                total_hops,
            );
            uniform_total_nodes += tree.len();
        }

        // FrozenBaseGuard: only final hop applies screening
        let mut frozen_total_nodes = 0;
        for hop in 0..total_hops {
            let tree = build_dd_tree_screened_with_schedule(
                &refs,
                &config,
                &screener,
                true,
                PrunerSchedule::FrozenBaseGuard,
                hop,
                total_hops,
            );
            frozen_total_nodes += tree.len();
        }

        println!(
            "  Seed {seed}: Uniform={uniform_total_nodes} nodes, FrozenBaseGuard={frozen_total_nodes} nodes",
        );

        match frozen_total_nodes.cmp(&uniform_total_nodes) {
            std::cmp::Ordering::Greater => frozen_wins += 1,
            std::cmp::Ordering::Less => uniform_wins += 1,
            std::cmp::Ordering::Equal => ties += 1,
        }
    }

    println!("\n  Summary: Frozen wins={frozen_wins}, Uniform wins={uniform_wins}, Ties={ties}");

    // Assert: FrozenBaseGuard should NEVER produce fewer total nodes...
    assert_eq!(
        uniform_wins, 0,
        "FrozenBaseGuard should produce >= Uniform nodes (Uniform won {uniform_wins} times)",
    );
    // ...and STRICTLY more, which is the claim this proof is named for
    // (Issue 831 T3). The `>=` above cannot fail on a build where both
    // schedules produce the identical tree, and for as long as the budget
    // capped both that is exactly what it was passing on. A TIE is now a
    // failure, and it fails with the diagnosis attached rather than leaving
    // the next reader to rediscover the cap.
    assert_eq!(
        ties, 0,
        "P1 is VACUOUS: {ties} of {n_trials} trials produced IDENTICAL node counts for \
         both schedules, so `>=` is passing on equality and proves nothing about \
         structural dominance. The usual cause is `tree_budget` capping both \
         schedules at the same size — raise it until Uniform reaches its natural \
         size (Issue 831 T3).",
    );
    assert_eq!(
        frozen_wins, n_trials,
        "FrozenBaseGuard should produce strictly MORE nodes on every trial \
         (won {frozen_wins} of {n_trials})",
    );
    // ⚠ The 10 seeds do NOT diversify this measurement: `VaryingScreener`
    // keys only on `depth`, ignoring `token_idx` and `parent_tokens`, so
    // pruning is deterministic per depth and every seed reports the same two
    // counts. The trials are a loop over one case. Left as-is deliberately —
    // making them independent is a fixture question (Issue 831 T4), and
    // recording it beats a reader inferring breadth this proof does not have.
    println!("  ✅ P1 PASS: FrozenBaseGuard produces strictly more nodes on all {n_trials} trials");
}

// ══════════════════════════════════════════════════════════════════════════
// P2: Identical Output with NoScreeningPruner (correctness)
// ══════════════════════════════════════════════════════════════════════════

#[cfg(feature = "thinking_prune")]
fn proof_p2_identical_with_noop_screener() {
    println!("\n── P2: Identical output with NoScreeningPruner ──────────────\n");

    let config = make_config();
    let marginals = random_marginals(4, config.vocab_size, 42);
    let refs = marginals_refs(&marginals);
    let screener = NoScreeningPruner;

    let total_hops = 3;

    for hop in 0..total_hops {
        let uniform_tree = build_dd_tree_screened_with_schedule(
            &refs,
            &config,
            &screener,
            true,
            PrunerSchedule::Uniform,
            hop,
            total_hops,
        );
        let frozen_tree = build_dd_tree_screened_with_schedule(
            &refs,
            &config,
            &screener,
            true,
            PrunerSchedule::FrozenBaseGuard,
            hop,
            total_hops,
        );

        assert_eq!(
            uniform_tree.len(),
            frozen_tree.len(),
            "Hop {hop}: NoScreeningPruner should produce identical trees",
        );

        // Verify scores match
        for (i, (u, f)) in uniform_tree.iter().zip(frozen_tree.iter()).enumerate() {
            assert!(
                (u.score - f.score).abs() < 1e-6,
                "Hop {hop}, node {i}: score mismatch (Uniform={}, Frozen={})",
                u.score,
                f.score,
            );
        }
        println!(
            "  Hop {hop}: {} nodes, all scores match ✅",
            uniform_tree.len()
        );
    }

    println!("  ✅ P2 PASS: NoScreeningPruner produces identical results");
}

// ══════════════════════════════════════════════════════════════════════════
// P3: Wall-Clock Timing — FrozenBaseGuard is faster at intermediate hops
// ══════════════════════════════════════════════════════════════════════════

#[cfg(feature = "thinking_prune")]
fn proof_p3_wall_clock_timing() {
    println!("\n── P3: Wall-clock timing with expensive screener ───────────\n");

    let config = make_config();
    let depths = 4;
    let vocab = config.vocab_size;
    let iters = 200;
    let total_hops = 3;

    // Expensive screener with synthetic work
    let expensive = ExpensiveScreener {
        base_relevance: 0.7,
        work_per_call: 100, // enough to be measurable
    };

    let marginals = random_marginals(depths, vocab, 12345);
    let refs = marginals_refs(&marginals);

    // ── The instrument (Issue 831 T2) ───────────────────────────────────
    //
    // This bar used to time Uniform to completion, then FrozenBaseGuard to
    // completion, and assert on that single ratio. Measured on an idle box:
    // **4 of 20 captured-mode runs FAILED** (-1.9% .. -5.0%) while 12 of 12
    // `--nocapture` runs passed (+0.9% .. +11.7%) — the verdict moved with how
    // the harness was invoked, which is a measurement of the scheduler and not
    // of the primitive. That is Issue 723 Class A exactly, and
    // `common/ab_timing.rs` is the treatment AGENTS.md already prescribes:
    // interleaved `(a-chunk, b-chunk)` pairs so a drift moves both arms, and
    // the MEDIAN across pairs so one preemption spike is discarded.
    //
    // ⚠ `ab_median_ratio`, not `best_of_us`. Issue 831 T2 names the
    // `best_of_us` shape, but that module's own docs reserve it for an
    // ABSOLUTE budget with no second arm to ratio against ("contention can
    // only ever add time, so the smallest of N samples is the closest
    // observation"). P3 has two arms and its claim is comparative, so the
    // median-of-ratios form is the one that cancels load; taking a minimum per
    // arm independently would compare two different load windows.
    //
    // ⛔ And the arms are `black_box`ed now. Both of them were
    // `let _ = build_dd_tree_screened_with_schedule(...)`, which is the exact
    // shape Issue 723 T5 measured being deleted by rustc 1.98.1 + fat LTO —
    // "a direct call with a used result measured 16.6 µs; `let _ = f()` over
    // the same fn in the same binary read ~0", *even through a `black_box`
    // inside the callee*. An eliminated arm makes this comparison noise
    // against noise, which is a second and sufficient explanation for a bar
    // that flips sign between invocations. The input is `black_box`ed too so
    // the build cannot be hoisted out of the round.
    // 7 rounds x 8 iters/arm. Sized on the MEASURED signal rather than
    // guessed: with the screener's work no longer deleted the effect is ~64%
    // in a per-round band 2.6% wide, so a median over 7 rounds is decisive and
    // the old 200-iteration sweep was buying precision the claim does not
    // need. It matters because the fixture is now genuinely expensive — the
    // debug-profile run went from ~0.6s of deleted work to 24s of real work at
    // the previous sampling, and this brings it back under 8s without
    // weakening the verdict.
    let rounds = 7;
    let iters_per_round = iters / 25;

    let ab = ab_timing::ab_median_ratio(
        rounds,
        iters_per_round,
        20,
        // a = BASELINE: Uniform screens every hop.
        |_i| {
            for hop in 0..total_hops {
                let tree = build_dd_tree_screened_with_schedule(
                    std::hint::black_box(&refs),
                    &config,
                    std::hint::black_box(&expensive),
                    true,
                    PrunerSchedule::Uniform,
                    hop,
                    total_hops,
                );
                std::hint::black_box(tree);
            }
        },
        // b = CANDIDATE: FrozenBaseGuard skips the intermediate hops.
        |_i| {
            for hop in 0..total_hops {
                let tree = build_dd_tree_screened_with_schedule(
                    std::hint::black_box(&refs),
                    &config,
                    std::hint::black_box(&expensive),
                    true,
                    PrunerSchedule::FrozenBaseGuard,
                    hop,
                    total_hops,
                );
                std::hint::black_box(tree);
            }
        },
    );

    // `ratio = b / a`, so FrozenBaseGuard being faster means a ratio BELOW 1.
    let speedup_pct = (1.0 - ab.median) * 100.0;

    // Printed on the PASS path as well as the FAIL path (Issue 831 T2), and
    // `report` prints the per-round RANGE beside the median on purpose: a
    // median inside a 0.9..1.1 band and one inside a 0.3..3.0 band are not the
    // same claim even when they are the same number. ⚠ `cargo test` still
    // swallows this without `--nocapture` — that is cargo's capture, not the
    // test's, which is why the assertion message below carries the numbers too.
    ab.report("P3 uniform-vs-frozen");
    println!("  Speedup (median of {rounds} interleaved rounds): {speedup_pct:.1}%");

    // Assert: FrozenBaseGuard skips the expensive screener on the intermediate
    // hops (2 of 3), so the expected saving is ~2/3.
    //
    // ⛔ The bar is 30%, not `faster at all`, and that is a REPAIR rather than
    // a tightening-for-its-own-sake. `ns_frozen < ns_uniform` was the widest
    // bar expressible, and it still failed 4 runs in 20 — because with the
    // screener's work deleted (see `ExpensiveScreener::relevance`) both arms
    // did the same near-nothing and the sign of the difference was noise. With
    // the work restored the measurement is 64.2% release / 63.1% debug, in a
    // per-round band 2.6% wide, which is the 30-60% this fixture's own comment
    // has predicted since it landed and which no run had ever produced.
    //
    // 30% is chosen as HALF the measured effect, the house slack convention
    // (`x86_64_matrix_floors.txt` uses ~60% of measured for the same reason):
    // it holds in both profiles with a wide margin, so an unrelated commit on
    // a loaded box does not red it, while a regression that stops skipping the
    // intermediate hops takes the speedup to ~0 and cannot pass.
    let min_speedup_pct = 30.0;
    assert!(
        speedup_pct >= min_speedup_pct,
        "FrozenBaseGuard should be >= {min_speedup_pct:.0}% faster than Uniform with an \
         expensive screener, got {speedup_pct:.1}% \
         (median ratio b/a {:.4} over {rounds} rounds, range {:.4}..{:.4}; \
          a {:.0} ns/iter, b {:.0} ns/iter). \
         A result near 0% usually means the screener's work was optimised away \
         — check that ExpensiveScreener::relevance still black_boxes its accumulator.",
        ab.median,
        ab.min(),
        ab.max(),
        ab.a_ns_per_iter(),
        ab.b_ns_per_iter(),
    );
    println!("  ✅ P3 PASS: FrozenBaseGuard is {speedup_pct:.1}% faster with expensive screener");
}

// ══════════════════════════════════════════════════════════════════════════
// P4: Single-Hop Edge Case — Full Screening Applied
// ══════════════════════════════════════════════════════════════════════════

#[cfg(feature = "thinking_prune")]
fn proof_p4_single_hop_is_final() {
    println!("\n── P4: Single-hop edge case applies full screening ────────\n");

    let config = make_config();
    let marginals = random_marginals(3, config.vocab_size, 99);
    let refs = marginals_refs(&marginals);

    let screener = VaryingScreener {
        relevances: vec![0.5, 0.2, 0.8], // 0.2 < threshold 0.3 → should trim at depth 1
    };

    // Single hop (hop 0 of 1) → is final → should apply full screening
    let frozen_tree = build_dd_tree_screened_with_schedule(
        &refs,
        &config,
        &screener,
        true,
        PrunerSchedule::FrozenBaseGuard,
        0,
        1,
    );

    // Compare with explicit full screening
    let full_tree = build_dd_tree_screened(&refs, &config, &screener, true);

    assert_eq!(
        frozen_tree.len(),
        full_tree.len(),
        "Single-hop FrozenBaseGuard should produce identical tree to full screening",
    );
    println!(
        "  Single-hop tree: {} nodes (matches full screening)",
        frozen_tree.len()
    );
    println!("  ✅ P4 PASS: Single-hop applies full screening correctly");
}

// ══════════════════════════════════════════════════════════════════════════
// P5: Path Quality — Best path identical at final hop
// ══════════════════════════════════════════════════════════════════════════

#[cfg(feature = "thinking_prune")]
fn proof_p5_final_hop_quality_identical() {
    println!("\n── P5: Final hop path quality identical to Uniform ────────\n");

    let config = make_config();
    let marginals = random_marginals(4, config.vocab_size, 77);
    let refs = marginals_refs(&marginals);

    let screener = VaryingScreener {
        relevances: vec![0.9, 0.6, 0.4, 0.7],
    };

    let total_hops = 3;

    // Both schedules should produce identical results at the FINAL hop
    let uniform_tree = build_dd_tree_screened_with_schedule(
        &refs,
        &config,
        &screener,
        true,
        PrunerSchedule::Uniform,
        total_hops - 1,
        total_hops,
    );
    let frozen_tree = build_dd_tree_screened_with_schedule(
        &refs,
        &config,
        &screener,
        true,
        PrunerSchedule::FrozenBaseGuard,
        total_hops - 1,
        total_hops,
    );

    let uniform_path = extract_best_path(&uniform_tree);
    let frozen_path = extract_best_path(&frozen_tree);

    assert_eq!(
        uniform_path, frozen_path,
        "Final hop paths should be identical between Uniform and FrozenBaseGuard",
    );
    println!("  Uniform path: {uniform_path:?}");
    println!("  Frozen path:  {frozen_path:?}");
    println!("  ✅ P5 PASS: Final hop produces identical paths");
}

// ══════════════════════════════════════════════════════════════════════════
// Main — Run all proofs
// ══════════════════════════════════════════════════════════════════════════

#[test]
fn test_bench_171_thinking_prune_goat() {
    println!("═══════════════════════════════════════════════════════════");
    println!("  GOAT Proof: Thinking Prune — FrozenBaseGuard DDTree (171)");
    println!("═══════════════════════════════════════════════════════════");

    #[cfg(feature = "thinking_prune")]
    {
        proof_p1_structural_dominance();
        proof_p2_identical_with_noop_screener();
        proof_p3_wall_clock_timing();
        proof_p4_single_hop_is_final();
        proof_p5_final_hop_quality_identical();

        println!("\n═══════════════════════════════════════════════════════════");
        println!("  ALL 5 PROOFS PASSED ✅");
        println!("═══════════════════════════════════════════════════════════");
    }

    #[cfg(not(feature = "thinking_prune"))]
    {
        println!("  ⚠️  thinking_prune feature not enabled — skipping");
        println!(
            "  Run with: cargo test --features thinking_prune --test bench_171_thinking_prune_goat -- --nocapture"
        );
    }
}
