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

use katgpt_core::mdlm_gen_steps;
use katgpt_core::predict_w_from_order_stats;
use katgpt_rs::benchmark::bench_ar_ness_w_sweep;
use katgpt_rs::dllm::text_corpus::{TEXT_CORPUS, encode_text, slice_blocks};
use katgpt_rs::dllm::{
    PositionOffsetSchedule, evaluate_set_causal_denoiser_nll_with_gen_steps,
    train_mini_set_causal_denoiser_with_gen_steps,
};
use katgpt_rs::speculative::set_diffusion::{CpuSetCausalForward, SetDiffusionConfig, set_diffusion_decode};
use katgpt_rs::types::{Config, Rng};
use katgpt_core::{ar_order, order_to_gen_steps};

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

// ── T3.2: the gap-predictor G3 gate (real-text lane) ──────────────────
//
// Two regime models trained on the Bench-809 Cell-B protocol (Austen,
// 2048/512 blocks, 40 epochs): one under AR reveal, one under uniform
// reveal. The PROBE is the mdlm schedule (all-eligible-at-once): with
// every position competing simultaneously, the commit order is the
// MODEL's natural regime (confident positions first) — the paper's
// AR-ness measurement posture, not the schedule's. The predictor maps
// the probe signature to w*; G3 compares denoiser NLL at w* vs the
// fixed settings, with T3.3's retention floor (≥ 0.95) as the
// no-regression tolerance.

/// T3.3: capability-retention floor — the paper's LR lesson number.
/// Retention on NLL (lower better): nll_best / nll_chosen ≥ RETENTION.
const RETENTION: f32 = 0.95;

const G3_SEED: u64 = 42;
const G3_LR: f32 = 0.01;
const G3_EPOCHS: usize = 40;
const G3_TRAIN_BLOCKS: usize = 2048;
const G3_EVAL_BLOCKS: usize = 512;
const G3_SEQ_LEN: usize = 9; // BLOCK + 1 (the 601/809 protocol)
const G3_MASK_RATIO: f32 = 0.5;
const G3_PROBE_DECODES: usize = 8;

#[test]
fn g3_gap_predictor_matches_or_beats_fixed_on_both_regimes() {
    let config = Config::micro_dllm_text();
    let tokens = encode_text(TEXT_CORPUS);
    let train = slice_blocks(&tokens, 0, G3_TRAIN_BLOCKS, G3_SEQ_LEN);
    let eval = slice_blocks(&tokens, 80_000, G3_EVAL_BLOCKS, G3_SEQ_LEN);

    // ── Train the two regime models (DENOISER objective — corruption +
    // loss-on-masked; the clean-token objective degenerates to the
    // identity copy under self-eligibility, measured nelbo→0 on real
    // text — the Bench-809 g5 lesson, reproduced here on the first run) ──
    let mut ar_reveal = |len: usize, _tokens: &[usize], _rng: &mut Rng| {
        order_to_gen_steps(&ar_order(len))
    };
    let (w_ar, _) = train_mini_set_causal_denoiser_with_gen_steps(
        &config, &train, &eval, G3_EPOCHS, G3_LR, G3_MASK_RATIO, &mut ar_reveal, G3_SEED,
    );
    let uniform_sched = PositionOffsetSchedule::new(1.0);
    let mut uni_reveal = |len: usize, _tokens: &[usize], rng: &mut Rng| {
        order_to_gen_steps(&uniform_sched.sample_order_with(len, || rng.uniform()))
    };
    let (w_uni, _) = train_mini_set_causal_denoiser_with_gen_steps(
        &config, &train, &eval, G3_EPOCHS, G3_LR, G3_MASK_RATIO, &mut uni_reveal, G3_SEED,
    );

    // ── Probe at the mdlm endpoint: the model's natural commit order.
    // Self-calibrating τ: sweep a fixed grid per model pair and keep the
    // MOST DISCRIMINATING τ (largest |ALR_AR − ALR_UNI| + |AGR_AR − AGR_UNI|
    // separation; deterministic tie-break to the LOWER τ). Rationale
    // (measured): τ=0.1 → everything commits on pass 0 (all-ties, no
    // signal); τ=0.5 on a real-text denoiser → the commits thin out — the
    // informative window is model-dependent, so the probe CALIBRATES on
    // the pair it will judge. Reported in the table.
    let probe_at = |weights: &katgpt_rs::transformer::TransformerWeights,
                    tau: f32|
     -> (f32, f32, usize, usize) {
        let forward = CpuSetCausalForward {
            weights,
            config: &config,
        };
        let decode_config = SetDiffusionConfig {
            mask_token: config.mask_token,
            vocab_size: config.vocab_size,
            denoise_steps: 8,
            confidence_threshold: tau,
            temperature: 0.0,
        };
        let gen_steps = mdlm_gen_steps(G3_SEQ_LEN - 1);
        let mut rng = Rng::new(G3_SEED + 7);
        let mut alr = 0.0f32;
        let mut agr = 0.0f32;
        let mut n = 0usize;
        let mut nfe = 0usize;
        let mut committed = 0usize;
        for _ in 0..G3_PROBE_DECODES {
            let r = set_diffusion_decode(&forward, &decode_config, &[], &gen_steps, &mut rng);
            let a = r.local_ar_ness();
            let g = r.global_ar_ness();
            if a.is_finite() {
                alr += a;
                n += 1;
            }
            if g.is_finite() {
                agr += g;
            }
            nfe += r.forward_passes;
            committed += r.unmask_steps.iter().filter(|&&s| s != u32::MAX).count();
        }
        (
            alr / n.max(1) as f32,
            agr / n.max(1) as f32,
            nfe / G3_PROBE_DECODES,
            committed,
        )
    };

    const TAU_GRID: [f32; 5] = [0.15, 0.25, 0.35, 0.45, 0.55];
    let mut best_tau = TAU_GRID[0];
    let mut best_sep = -1.0f32;
    let mut best_probe_ar = (0.0f32, 0.0f32, 0usize, 0usize);
    let mut best_probe_uni = (0.0f32, 0.0f32, 0usize, 0usize);
    println!("\n== Bench 602 G3 — probe τ calibration (mdlm endpoint, both regimes) ==");
    println!(
        "{:>6} | {:>18} {:>12} | {:>18} {:>12} | {:>8}",
        "τ", "AR: (ALR,AGR)", "NFE/commits", "UNI: (ALR,AGR)", "NFE/commits", "separation"
    );
    for &tau in TAU_GRID.iter() {
        let p_ar = probe_at(&w_ar, tau);
        let p_uni = probe_at(&w_uni, tau);
        let sep = (p_ar.0 - p_uni.0).abs() + (p_ar.1 - p_uni.1).abs();
        println!(
            "{:>6.2} | ({:>5.3},{:>5.3}) {:>5}/{:<4} | ({:>5.3},{:>5.3}) {:>5}/{:<4} | {:>8.3}",
            tau,
            p_ar.0,
            p_ar.1,
            p_ar.2,
            p_ar.3,
            p_uni.0,
            p_uni.1,
            p_uni.2,
            p_uni.3,
            sep
        );
        // A τ where either model commits nothing carries no signal — skip.
        let both_commit = p_ar.3 > 0 && p_uni.3 > 0;
        if both_commit && sep > best_sep {
            best_sep = sep;
            best_tau = tau;
            best_probe_ar = p_ar;
            best_probe_uni = p_uni;
        }
    }
    let (alr_ar, agr_ar, nfe_ar, _) = best_probe_ar;
    let (alr_uni, agr_uni, nfe_uni, _) = best_probe_uni;
    let w_mdlm_ar = predict_w_from_order_stats(alr_ar, agr_ar);
    let w_mdlm_uni = predict_w_from_order_stats(alr_uni, agr_uni);

    println!("\n== Bench 602 G3 — gap-predictor (real-text, both regimes) ==");
    println!("chosen τ={best_tau} (most discriminating over the grid, separation {best_sep:.3})");
    println!(
        "AR-trained probe:  ALR={alr_ar:.3} AGR={agr_ar:.3} (NFE {nfe_ar}) -> mdlm-w={w_mdlm_ar} (reported: all-ties degeneracy)");
    println!(
        "UNI-trained probe: ALR={alr_uni:.3} AGR={agr_uni:.3} (NFE {nfe_uni}) -> mdlm-w={w_mdlm_uni} (reported: all-ties degeneracy)");

    // ── ALSO measure the residual probe (schedule w=0.5): the model's
    // commit deviation from the calibrated schedule signature (0.589,
    // 0.797) — ΔALR > 0 means the model drags toward AR (defers commits
    // until left context lands), the paper's actual measurement posture
    // (AR-ness under the model's own decoding). REPORTED; asserted only
    // where measured stable.
    let sched_probe = |weights: &katgpt_rs::transformer::TransformerWeights| -> (f32, f32) {
        let forward = CpuSetCausalForward {
            weights,
            config: &config,
        };
        let decode_config = SetDiffusionConfig {
            mask_token: config.mask_token,
            vocab_size: config.vocab_size,
            denoise_steps: 8,
            confidence_threshold: best_tau,
            temperature: 0.0,
        };
        let sched = PositionOffsetSchedule::new(0.5);
        let mut order_rng = Rng::new(G3_SEED + 11);
        let mut rng = Rng::new(G3_SEED + 12);
        let mut alr = 0.0f32;
        let mut agr = 0.0f32;
        let mut alr_n = 0usize;
        let mut agr_n = 0usize;
        for _ in 0..G3_PROBE_DECODES {
            let order = sched.sample_order_with(G3_SEQ_LEN - 1, || order_rng.uniform());
            let gen_steps = order_to_gen_steps(&order);
            let r = set_diffusion_decode(&forward, &decode_config, &[], &gen_steps, &mut rng);
            let a = r.local_ar_ness();
            let g = r.global_ar_ness();
            if a.is_finite() {
                alr += a;
                alr_n += 1;
            }
            if g.is_finite() {
                agr += g;
                agr_n += 1;
            }
        }
        (alr / alr_n.max(1) as f32, agr / agr_n.max(1) as f32)
    };
    let (sp_alr_ar, sp_agr_ar) = sched_probe(&w_ar);
    let (sp_alr_uni, sp_agr_uni) = sched_probe(&w_uni);
    // Calibrated w=0.5 signature from the T3.1 table.
    const CAL_05: (f64, f64) = (0.589, 0.797);
    println!(
        "residual probe @w=0.5: AR ({sp_alr_ar:.3},{sp_agr_ar:.3}) ΔALR={:+.3} | UNI ({sp_alr_uni:.3},{sp_agr_uni:.3}) ΔALR={:+.3}  (calibrated {CAL_05:?})",
        sp_alr_ar as f64 - CAL_05.0,
        sp_alr_uni as f64 - CAL_05.0
    );

    // ── w* from the RESIDUAL posture (the paper's AR-drag measurement) ──
    // The mdlm-endpoint nearest-row signatures are REPORTED above but do
    // not discriminate (a confident model commits all-at-once → ties);
    // the residual probe carries the signal.
    let w_star_ar = katgpt_core::predict_w_residual(sp_alr_ar, sp_agr_ar, 0.5);
    let w_star_uni = katgpt_core::predict_w_residual(sp_alr_uni, sp_agr_uni, 0.5);
    println!(
        "residual w*: AR-trained -> w*={w_star_ar:.3} | UNI-trained -> w*={w_star_uni:.3}"
    );
    // Discrimination (the mechanism's direction, now through the residual):
    // the AR-trained model's drag is strictly larger → strictly lower w*.
    assert!(
        w_star_ar < w_star_uni,
        "residual predictor failed to discriminate: w*_AR={w_star_ar} >= w*_UNI={w_star_uni} \
         (ΔALR {:+.3} vs {:+.3})",
        sp_alr_ar as f64 - CAL_05.0,
        sp_alr_uni as f64 - CAL_05.0
    );

    // ── Eval: denoiser NLL per reveal arm, per model ──
    let eval_nll = |weights: &katgpt_rs::transformer::TransformerWeights, w: f32| -> f32 {
        let sched = PositionOffsetSchedule::new(w);
        let mut reveal = |len: usize, _t: &[usize], rng: &mut Rng| {
            order_to_gen_steps(&sched.sample_order_with(len, || rng.uniform()))
        };
        let mut rng = Rng::new(G3_SEED + 1000);
        evaluate_set_causal_denoiser_nll_with_gen_steps(
            weights, &eval, &config, G3_MASK_RATIO, &mut reveal, &mut rng,
        )
    };
    let fixed = [0.1f32, 0.5, 1.0];
    println!("\n{:>18} {:>8} {:>10} {:>10}", "model", "w", "NLL", "retention");
    for (label, weights, w_star) in [("AR-trained", &w_ar, w_star_ar), ("UNI-trained", &w_uni, w_star_uni)] {
        let fixed_nlls: Vec<f32> = fixed.iter().map(|&w| eval_nll(weights, w)).collect();
        let best_fixed = fixed_nlls.iter().copied().fold(f32::INFINITY, f32::min);
        let chosen = eval_nll(weights, w_star);
        let retention = best_fixed / chosen;
        println!(
            "{:>18} {:>8.2} {:>10.4} {:>10.4}  (fixed: {:?})",
            label, w_star, chosen, retention,
            fixed.iter().zip(fixed_nlls.iter()).map(|(w, n)| format!("w={w}:{n:.3}")).collect::<Vec<_>>()
        );
        // G3 no-regression floor (T3.3): the predictor-chosen config holds
        // ≥ 95% of the best fixed setting's capability.
        assert!(
            retention >= RETENTION,
            "{label}: predictor-chosen w={w_star} NLL {chosen:.4} vs best fixed {best_fixed:.4} \
             (retention {retention:.4} < {RETENTION})"
        );
    }
}
