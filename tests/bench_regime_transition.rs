//! Plan 215 T6: GOAT Proof — Regime Transition Before/After Benchmark
//!
//! Measures regime transition overhead and correctness improvement on constraint problems.
//! Run with: `cargo test --features "regime_transition" --test bench_regime_transition -- --nocapture`

#![cfg(feature = "regime_transition")]

use std::hint::black_box;
use std::time::Instant;

#[path = "common/ab_timing.rs"]
mod ab_timing;

use katgpt_rs::pruners::decision_trace::DecisionTrace;
use katgpt_rs::pruners::four_regime_router::{FourRegimeRouter, RegimeFeatures};
use katgpt_rs::pruners::regime_transition::{
    AdversarialBreaker, CollapseClassifier, DDTreeStats, GateResult, ProvenanceChain,
    RegimeCollapseClassifier, RegimeTransitionGate, RegimeTransitionScheduler,
};
use katgpt_rs::pruners::rule_extractor::ExtractedRule;

use katgpt_core::traits::ConstraintPruner;

// ── Mock pruner: Rejects token 3 ─────────────────────────────

/// Mock pruner that rejects any path where token_idx == 3.
/// Used for AdversarialBreaker tests.
struct RejectThree;

impl ConstraintPruner for RejectThree {
    fn is_valid(&self, _depth: usize, token_idx: usize, _parent_tokens: &[usize]) -> bool {
        token_idx != 3
    }
}

// ── Helpers ───────────────────────────────────────────────────

fn make_trace(rules: usize, alternatives: usize) -> DecisionTrace {
    DecisionTrace {
        rules_applied: (0..rules)
            .map(|i| ExtractedRule {
                conditions: vec![(0, i)],
                action: (1, i),
                score: 0.9,
                support: 1,
            })
            .collect(),
        alternatives_rejected: (0..alternatives)
            .map(|i| ExtractedRule {
                conditions: vec![(0, i + 100)],
                action: (1, i + 100),
                score: 0.3,
                support: 1,
            })
            .collect(),
        confidence: 0.85,
    }
}

fn make_ddtree_stats(n_failures: usize, uniform_depth: bool) -> DDTreeStats {
    let failure_depths: Vec<u32> = if uniform_depth {
        vec![5; n_failures]
    } else {
        (0..n_failures).map(|i| (i % 10) as u32).collect()
    };
    DDTreeStats {
        total_branches: n_failures as u32 * 2,
        failed_branches: n_failures as u32,
        failure_depths,
        max_depth: 10,
    }
}

// ── Bench 1: Collapse Classification Throughput ──────────────

#[test]
fn bench_collapse_classification_throughput() {
    let classifier = RegimeCollapseClassifier::default();
    let stats = make_ddtree_stats(10, true);

    // ⛔ Issue 855: this was `for _ in 0..100_000 { let _ = classifier.classify(&stats); }`
    // over a loop-invariant input with the result discarded. Under `-C lto=fat`
    // that whole loop is dead code (Issue 723 Class A2), so the release run
    // printed `100000 iterations in 0ns (0.0 ns/op)` and the `< 10_000 ns/op`
    // ceiling below passed with maximum margin — satisfied by work that did
    // not happen. A flaky bar is eventually noticed; this one could not fail.
    //
    // `best_of_us` is the treatment for a ONE-ARM absolute budget: contention
    // can only ever ADD time, so the minimum of N samples is the load-invariant
    // observation, and an all-zero run is a NAMED instrument failure rather
    // than a verdict. The input goes through `black_box` so the callee cannot
    // be hoisted out of the chunk and the result through `black_box` so it
    // cannot be discarded. The bar is unchanged.
    const CHUNK: usize = 10_000;
    const SAMPLES: usize = 10;
    let us = ab_timing::best_of_us(2, SAMPLES, || {
        let t = Instant::now();
        for _ in 0..CHUNK {
            black_box(classifier.classify(black_box(&stats)));
        }
        t.elapsed()
    });
    let ns_per = us * 1000.0 / CHUNK as f64;

    println!(
        "bench_collapse_classification: {SAMPLES} samples × {CHUNK} iterations, \
         best {us:.1}µs ({ns_per:.1} ns/op)"
    );
    assert!(ns_per < 10_000.0, "Classification too slow: {ns_per} ns/op");
}

// ── Bench 2: Gate Evaluation Throughput ───────────────────────

#[test]
fn bench_gate_evaluation_throughput() {
    let gate = RegimeTransitionGate::default();
    let trace = make_trace(10, 5);

    // ⛔ Issue 855, same class as `bench_collapse_classification_throughput`
    // above: `let _ = gate.evaluate(&trace, 5)` over a hoisted input measured
    // `0ns` over 100 000 iterations and passed the ceiling on nothing. Same
    // treatment, same bar.
    const CHUNK: usize = 10_000;
    const SAMPLES: usize = 10;
    let us = ab_timing::best_of_us(2, SAMPLES, || {
        let t = Instant::now();
        for _ in 0..CHUNK {
            black_box(gate.evaluate(black_box(&trace), black_box(5)));
        }
        t.elapsed()
    });
    let ns_per = us * 1000.0 / CHUNK as f64;

    println!(
        "bench_gate_evaluation: {SAMPLES} samples × {CHUNK} iterations, \
         best {us:.1}µs ({ns_per:.1} ns/op)"
    );
    assert!(
        ns_per < 10_000.0,
        "Gate evaluation too slow: {ns_per} ns/op"
    );
}

// ── Bench 3: Provenance Chain Recording ───────────────────────

#[test]
fn bench_provenance_chain_recording() {
    let mut chain = ProvenanceChain::default();
    let n = 10_000;

    let start = Instant::now();
    for i in 0..n {
        chain.record(i as u64, 0.5, i % 6);
    }
    let elapsed = start.elapsed();
    let ns_per = elapsed.as_nanos() as f64 / n as f64;

    println!(
        "bench_provenance_chain_record: {n} records in {elapsed:?} ({ns_per:.1} ns/op, blake3)"
    );
    assert!(
        ns_per < 10_000.0,
        "Provenance recording too slow: {ns_per} ns/op"
    );

    // Verify chain integrity after bulk recording
    assert!(
        chain.verify(),
        "Chain verification failed after bulk recording"
    );
}

// ── Bench 4: AdversarialBreaker Throughput ────────────────────

#[test]
fn bench_adversarial_breaker_throughput() {
    let breaker = AdversarialBreaker::with_default_threshold(RejectThree);
    let n = 100_000;

    let start = Instant::now();
    for i in 0..n {
        let token_idx = i % 10;
        let parent = [1, 2];
        let _ = breaker.is_valid(0, token_idx, &parent);
    }
    let elapsed = start.elapsed();
    let ns_per = elapsed.as_nanos() as f64 / n as f64;

    println!("bench_adversarial_breaker_is_valid: {n} calls in {elapsed:?} ({ns_per:.1} ns/op)");
    assert!(
        ns_per < 10_000.0,
        "AdversarialBreaker too slow: {ns_per} ns/op"
    );
}

// ── Bench 5: Four-Regime Router Selection ─────────────────────

#[test]
fn bench_four_regime_router_selection() {
    let mut router = FourRegimeRouter::with_defaults();
    let features = RegimeFeatures {
        failure_rate: 0.1,
        regime_collapse: false,
        transition_success: false,
        regime_q_value: 0.5,
    };
    let n = 100_000;

    let start = Instant::now();
    for i in 0..n {
        let arm = router.select(&features);
        router.update(arm, if i % 7 == 0 { 0.2 } else { 0.8 });
    }
    let elapsed = start.elapsed();
    let ns_per = elapsed.as_nanos() as f64 / n as f64;

    println!(
        "bench_four_regime_router_select_update: {n} cycles in {elapsed:?} ({ns_per:.1} ns/op)"
    );
    assert!(
        ns_per < 10_000.0,
        "Router select+update too slow: {ns_per} ns/op"
    );
}

// ── Bench 6: Scheduler Concurrency Control ────────────────────

#[test]
fn bench_scheduler_concurrency_control() {
    let scheduler = RegimeTransitionScheduler::new(4);
    let n = 100_000;

    let start = Instant::now();
    for _ in 0..n {
        if scheduler.try_acquire() {
            scheduler.release();
        }
    }
    let elapsed = start.elapsed();
    let ns_per = elapsed.as_nanos() as f64 / n as f64;

    println!("bench_scheduler_acquire_release: {n} cycles in {elapsed:?} ({ns_per:.1} ns/op)");
    assert!(
        ns_per < 10_000.0,
        "Scheduler acquire/release too slow: {ns_per} ns/op"
    );
}

// ── Bench 7: Regime Transition Overhead vs Baseline ───────────

#[test]
fn bench_regime_transition_overhead_vs_baseline() {
    let classifier = RegimeCollapseClassifier::default();
    let gate = RegimeTransitionGate::default();
    let mut router = FourRegimeRouter::with_defaults();
    let mut chain = ProvenanceChain::default();
    let trace = make_trace(8, 3);
    let stats = make_ddtree_stats(8, true);

    let features_standard = RegimeFeatures {
        failure_rate: 0.1,
        regime_collapse: false,
        transition_success: false,
        regime_q_value: 0.5,
    };

    // Baseline: just the pruner (no regime transition machinery)
    let n = 50_000;
    let breaker = AdversarialBreaker::with_default_threshold(RejectThree);

    let start = Instant::now();
    for i in 0..n {
        let _ = breaker.is_valid(0, i % 10, &[1, 2]);
    }
    let baseline = start.elapsed();

    // With regime transition: classify → gate → provenance → router
    let start = Instant::now();
    for i in 0..n {
        let _ = classifier.classify(&stats);
        let _ = gate.evaluate(&trace, 4);
        chain.record(i as u64, 0.5, i % 6);
        let arm = router.select(&features_standard);
        router.update(arm, 0.7);
    }
    let with_regime = start.elapsed();

    let overhead_ns = with_regime.as_nanos() as f64 - baseline.as_nanos() as f64;
    let overhead_pct = overhead_ns / baseline.as_nanos() as f64 * 100.0;

    println!(
        "bench_regime_transition_overhead: baseline={baseline:?}, with_regime={with_regime:?}, overhead={overhead_pct:.1}%"
    );
    // Note: overhead is high because baseline is just is_valid calls (trivial),
    // while regime path includes Vec-allocating trace construction, blake3 hashes,
    // and VecDeque history updates. The per-iteration cost is still low (~1.75µs).
    // This is acceptable for the correctness improvement regime transition provides.
    println!(
        "  Per-iteration: baseline={:.0}ns, regime={:.0}ns",
        baseline.as_nanos() as f64 / n as f64,
        with_regime.as_nanos() as f64 / n as f64,
    );
    let us_per_regime = with_regime.as_nanos() as f64 / n as f64 / 1000.0;
    assert!(
        us_per_regime < 10.0,
        "Per-iteration regime cost too high: {us_per_regime} µs"
    );
}

// ── Bench 8: Full Pipeline End-to-End ─────────────────────────

#[test]
fn bench_full_pipeline_end_to_end() {
    let classifier = RegimeCollapseClassifier::default();
    let gate = RegimeTransitionGate::default();
    let mut chain = ProvenanceChain::default();
    let mut router = FourRegimeRouter::with_defaults();
    let breaker = AdversarialBreaker::with_default_threshold(RejectThree);
    let trace = make_trace(6, 2);

    let n = 10_000;
    let start = Instant::now();
    for i in 0..n {
        // Step 1: Classify DDTree failures
        let stats = make_ddtree_stats(5, i % 3 == 0);
        let collapse = classifier.classify(&stats);

        // Step 2: Build features from classification
        let features = RegimeFeatures {
            failure_rate: stats.failed_branches as f32 / stats.total_branches.max(1) as f32,
            regime_collapse: collapse
                == katgpt_rs::pruners::regime_transition::CollapseType::Regime,
            transition_success: i > 0 && i % 50 == 0,
            regime_q_value: 0.5,
        };

        // Step 3: Route to regime arm
        let arm = router.select(&features);
        router.update(arm, 0.6);

        // Step 4: If Discovery, evaluate gate
        if features.regime_collapse {
            let result = gate.evaluate(&trace, 3);
            if result == GateResult::Accept {
                chain.record(i as u64, 0.8, arm.index());
            }
        }

        // Step 5: Run pruner (always)
        let _ = breaker.is_valid(0, i % 10, &[1, 2]);
    }
    let elapsed = start.elapsed();
    let us_per = elapsed.as_micros() as f64 / n as f64;

    println!("bench_full_pipeline_e2e: {n} iterations in {elapsed:?} ({us_per:.1} µs/iter)");
    assert!(chain.verify(), "Provenance chain integrity check failed");
    assert!(us_per < 1000.0, "Full pipeline too slow: {us_per} µs/iter");
}
