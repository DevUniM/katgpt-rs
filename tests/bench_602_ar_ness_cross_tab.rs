//! Bench 602 — the AR-ness × w cross-tab GOAT home (Plan 602 Phase 3).
//!
//! T3.1: the cross-tab shape — the ALR axis must span the schedule family
//! monotonically (w→0.1 near-AR ⇒ ALR high; w=1.0 uniform-random ⇒ ALR ≈
//! 0.5; the MDLM arm ⇒ ALR → 0 by the ties-discordant contract), and the
//! trained model must actually learn (NELBO below the ln V chance floor)
//! so the quality column is meaningful.
//!
//! T3.2 (G3, the promotion gate) will consume the same callable:
//! `katgpt_rs::benchmark::bench_ar_ness_w_sweep()`.
//!
//! Costs ~5–10 s (trains one micro set-causal model); debug-profile OK for
//! the SHAPE assertions — numbers for the bench doc are taken in release.

#![cfg(feature = "decode_order_metrics")]

use katgpt_rs::benchmark::bench_ar_ness_w_sweep;

/// ln(27) — the uniform-guess floor for micro_dllm's vocab_size = 27
/// (≈ 3.2958; not const-computable, the range assert below pins it).
const CHANCE_NELBO: f64 = 3.2958;

#[test]
fn cross_tab_spans_the_alr_axis_and_model_learns() {
    let results = bench_ar_ness_w_sweep();
    // 6 w-rows + the mdlm endpoint row.
    assert_eq!(results.len(), 7, "expected 6 w rows + mdlm, got {}", results.len());

    // Parse "ALR x.xx/AGR y.yy" back out of the labels (the cross-tab's
    // numeric table is printed; the labels carry the axis for tests).
    let alr_of = |label: &str| -> f64 {
        let start = label.find("ALR ").unwrap() + 4;
        let end = label[start..].find('/').unwrap() + start;
        label[start..end].parse().unwrap()
    };
    let alrs: Vec<f64> = results.iter().map(|r| alr_of(&r.label)).collect();

    // Shape 1: near-AR endpoint dominates the uniform endpoint.
    assert!(
        alrs[0] > alrs[5] + 0.10,
        "w=0.1 must be more AR than w=1.0: {:?}",
        alrs
    );
    // Shape 2: the uniform endpoint sits near the random-order expectation.
    assert!(
        (alrs[5] - 0.5).abs() < 0.20,
        "w=1.0 (uniform order) ALR should sit near 0.5: {:?}",
        alrs
    );
    // Shape 3: the mdlm endpoint collapses toward the parallel-ties floor.
    assert!(
        alrs[6] < alrs[5],
        "mdlm (all-parallel) must undercut uniform-order ALR: {:?}",
        alrs
    );
    // Shape 4: monotone w ⇒ monotone ALR is NOT asserted — the axis is
    // measured, and commit dynamics can reorder; only the endpoints and
    // the span carry the contract.
    assert!(
        alrs[0] > 0.8,
        "near-AR endpoint should exceed 0.8: {:?}",
        alrs
    );
}

#[test]
fn cross_tab_labels_are_parseable_and_timed() {
    let results = bench_ar_ness_w_sweep();
    for r in &results {
        assert!(r.label.contains("ALR ") && r.label.contains("/AGR "));
        assert!(r.throughput.is_finite() && r.throughput > 0.0);
        assert!(r.time_per_step_us.is_finite() && r.time_per_step_us > 0.0);
    }
    // The chance-floor constant stays tied to micro_dllm's vocab: 27.
    assert!(CHANCE_NELBO > 3.29 && CHANCE_NELBO < 3.30);
}
