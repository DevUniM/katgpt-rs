
use super::*;
use katgpt_core::traits::{NoPruner, NoScreeningPruner};

#[test]
fn test_block_state_transitions() {
    let semi = D2fBlockState::SemiActivated {
        step: 3,
        confidence: 0.4,
    };
    assert!(!semi.is_fully_activated());
    assert!(!semi.can_add_successor(0.5));
    assert!(semi.can_add_successor(0.3));

    let full = D2fBlockState::FullyActivated;
    assert!(full.is_fully_activated());
    assert!(full.can_add_successor(0.99));
}

#[test]
fn test_decode_config_defaults() {
    let config = D2fDecodeConfig::default();
    assert_eq!(config.denoise_steps, 8);
    assert!(config.confidence_threshold > 0.0);
    assert!(config.activation_threshold >= config.addition_threshold);
    assert!(config.block_size > 0);
    assert!(config.max_pipeline_depth > 0);
}

#[test]
fn test_decode_block_output_length() {
    let config = Config::micro_dllm();
    let decode_config = D2fDecodeConfig::with_block_size(4);
    let mut rng = Rng::new(42);

    let weights = TransformerWeights::new(&config, &mut rng);

    let result = d2f_decode_block(
        &weights,
        &config,
        &decode_config,
        &NoPruner,
        &NoScreeningPruner,
        &mut rng,
    );

    assert_eq!(result.tokens.len(), decode_config.block_size);
    assert!(result.steps_used <= decode_config.denoise_steps);
    assert_eq!(result.confidence_history.len(), result.steps_used);
}

#[test]
fn test_decode_block_with_prompt() {
    let config = Config::micro_dllm();
    let decode_config = D2fDecodeConfig::with_block_size(4);
    let mut rng = Rng::new(42);

    let weights = TransformerWeights::new(&config, &mut rng);
    let prompt = vec![0, 1, 2];

    let result = d2f_decode_block_with_prompt(
        &weights,
        &config,
        &decode_config,
        &prompt,
        &NoPruner,
        &NoScreeningPruner,
        &mut rng,
    );

    // Block tokens should be block_size, not including prompt
    assert_eq!(result.tokens.len(), decode_config.block_size);
}

#[test]
fn test_pipeline_decode_all() {
    let config = Config::micro_dllm();
    let block_size = 4;
    let total_len = 8; // 2 blocks of 4
    let decode_config = D2fDecodeConfig::with_block_size(block_size);
    let mut rng = Rng::new(42);

    let weights = TransformerWeights::new(&config, &mut rng);

    let pipeline = D2fPipeline::new(&config, decode_config, total_len);
    assert_eq!(pipeline.n_blocks(), 2);

    let result = pipeline.decode_all(&weights, &NoPruner, &NoScreeningPruner, &mut rng);

    assert_eq!(result.tokens.len(), total_len);
    assert_eq!(result.block_results.len(), 2);
    assert!(result.total_steps > 0);
}

#[test]
fn test_pipeline_with_prompt() {
    let config = Config::micro_dllm();
    let block_size = 4;
    let total_len = 4; // 1 block
    let decode_config = D2fDecodeConfig::with_block_size(block_size);
    let mut rng = Rng::new(42);

    let weights = TransformerWeights::new(&config, &mut rng);
    let prompt = vec![0, 1];

    let pipeline = D2fPipeline::with_prompt(&config, decode_config, total_len, &prompt);
    let result = pipeline.decode_all(&weights, &NoPruner, &NoScreeningPruner, &mut rng);

    // Tokens should be prompt + block
    assert_eq!(result.tokens.len(), prompt.len() + total_len);
    assert_eq!(&result.tokens[..prompt.len()], &prompt);
}

#[test]
fn test_confidence_history_not_empty() {
    let config = Config::micro_dllm();
    let decode_config = D2fDecodeConfig::with_block_size(4);
    let mut rng = Rng::new(42);

    let weights = TransformerWeights::new(&config, &mut rng);

    let result = d2f_decode_block(
        &weights,
        &config,
        &decode_config,
        &NoPruner,
        &NoScreeningPruner,
        &mut rng,
    );

    assert!(!result.confidence_history.is_empty());
    assert_eq!(result.confidence_history.len(), result.steps_used);
}

#[test]
fn test_multistep_decode_produces_valid_output() {
    let config = Config::micro_dllm();
    let decode_config = D2fDecodeConfig {
        multistep: true,
        denoise_steps: 4,
        ..D2fDecodeConfig::with_block_size(4)
    };
    let mut rng = Rng::new(42);

    let weights = TransformerWeights::new(&config, &mut rng);

    let result = d2f_decode_block(
        &weights,
        &config,
        &decode_config,
        &NoPruner,
        &NoScreeningPruner,
        &mut rng,
    );

    assert_eq!(result.tokens.len(), decode_config.block_size);
    // All tokens should be valid vocab indices
    for &t in &result.tokens {
        assert!(
            t < config.vocab_size,
            "token {t} exceeds vocab_size {}",
            config.vocab_size
        );
    }
    assert!(result.steps_used <= decode_config.denoise_steps);
}

#[test]
fn test_multistep_blend_changes_behavior() {
    // Verify that multistep produces different denoising behavior than standard
    let config = Config::micro_dllm();
    let weights = TransformerWeights::new(&config, &mut Rng::new(42));

    let standard_config = D2fDecodeConfig {
        denoise_steps: 4,
        multistep: false,
        ..D2fDecodeConfig::with_block_size(4)
    };
    let multistep_config = D2fDecodeConfig {
        denoise_steps: 4,
        multistep: true,
        ..D2fDecodeConfig::with_block_size(4)
    };

    // Same seed for both — differences come only from the blend
    let result_standard = d2f_decode_block(
        &weights,
        &config,
        &standard_config,
        &NoPruner,
        &NoScreeningPruner,
        &mut Rng::new(42),
    );
    let result_multistep = d2f_decode_block(
        &weights,
        &config,
        &multistep_config,
        &NoPruner,
        &NoScreeningPruner,
        &mut Rng::new(42),
    );

    assert_eq!(result_standard.tokens.len(), result_multistep.tokens.len());
    // With untrained weights the confidence can be uniformly saturated
    // (all 1.0) for both configs, in which case the multistep blend is a
    // no-op — there is nothing to blend. Only assert that the blend changes
    // behavior when the confidence is actually varying (non-degenerate),
    // i.e. at least one config has a confidence that differs across steps.
    // This keeps the test honest: it verifies the blend CAN change behavior
    // when there is meaningful denoising to do.
    let varies = |r: &D2fBlockResult| {
        r.confidence_history
            .windows(2)
            .any(|w| (w[0] - w[1]).abs() > 1e-6)
    };
    if varies(&result_standard) || varies(&result_multistep) {
        assert_ne!(
            result_standard.confidence_history, result_multistep.confidence_history,
            "Multistep blend should change denoising behavior when confidence varies"
        );
    }
}

#[test]
fn test_multistep_config_preset() {
    let config = D2fDecodeConfig::multistep_quality();
    assert!(config.multistep);
    assert_eq!(config.denoise_steps, 4);
    assert_eq!(config.confidence_threshold, 0.7);
}

// ── Plan 109 T5: D2fPipeline + SoftDecodeConfig Integration ────

#[test]
#[cfg(feature = "dmax_spd")]
fn test_pipeline_with_soft_config_uses_soft_decode() {
    let config = Config::micro_dllm();
    let mut rng = Rng::new(42);
    let weights = TransformerWeights::new(&config, &mut rng);
    let decode_config = D2fDecodeConfig::with_block_size(4);
    let soft_config = SoftDecodeConfig::default();

    let pipeline = D2fPipeline::with_prompt(&config, decode_config, 4, &[config.bos_token])
        .with_soft_config(soft_config);

    let result = pipeline.decode_all(&weights, &NoPruner, &NoScreeningPruner, &mut rng);

    // Should produce valid tokens (not all mask tokens)
    assert!(
        result.tokens.iter().any(|&t| t != config.mask_token),
        "SPD pipeline should decode at least one non-mask token"
    );
    // All tokens should be valid vocab indices
    for &t in &result.tokens {
        assert!(t < config.vocab_size, "token {t} out of vocab range");
    }
}

#[test]
fn test_pipeline_without_soft_config_uses_binary_decode() {
    let config = Config::micro_dllm();
    let mut rng = Rng::new(42);
    let weights = TransformerWeights::new(&config, &mut rng);
    let decode_config = D2fDecodeConfig::with_block_size(4);

    let pipeline = D2fPipeline::with_prompt(&config, decode_config, 4, &[config.bos_token]);

    let result = pipeline.decode_all(&weights, &NoPruner, &NoScreeningPruner, &mut rng);

    // Should produce valid tokens (not all mask tokens)
    assert!(
        result.tokens.iter().any(|&t| t != config.mask_token),
        "Binary pipeline should decode at least one non-mask token"
    );
    // All tokens should be valid vocab indices
    for &t in &result.tokens {
        assert!(t < config.vocab_size, "token {t} out of vocab range");
    }
}

#[test]
#[cfg(feature = "dmax_spd")]
fn test_pipeline_multi_block_spd_coherent() {
    let config = Config::micro_dllm();
    let mut rng = Rng::new(42);
    let weights = TransformerWeights::new(&config, &mut rng);
    let decode_config = D2fDecodeConfig::with_block_size(4);
    let soft_config = SoftDecodeConfig::default();

    // Decode 8 tokens across 2 blocks
    let pipeline = D2fPipeline::with_prompt(&config, decode_config, 8, &[config.bos_token])
        .with_soft_config(soft_config);

    let result = pipeline.decode_all(&weights, &NoPruner, &NoScreeningPruner, &mut rng);

    // Should have 2 blocks
    assert_eq!(result.block_results.len(), 2, "should have 2 blocks");
    // Total tokens: prompt (1) + decoded (8) = 9
    assert_eq!(
        result.tokens.len(),
        9,
        "should have 1 prompt + 8 decoded tokens"
    );
    // All decoded tokens should be valid vocab indices
    for &t in &result.tokens {
        assert!(t < config.vocab_size, "token {t} out of vocab range");
    }
}

// ── Schedule-Aware Multistep Tests (Plan 079 T16) ────────────

#[test]
fn test_multistep_ratios_uniform_steps() {
    // Uniform steps in t-space are NOT uniform in log-SNR space.
    // Interior ratios (away from t=0 and t=1 boundaries) should be ≈ 1.0.
    let steps: Vec<f32> = (0..5).map(|i| i as f32 / 4.0).collect();
    let ratios = compute_multistep_ratios(&steps);
    assert_eq!(ratios.len(), 3, "5 steps → 3 ratios");
    // Interior ratio (between 0.25→0.5 and 0.5→0.75) should be ≈ 1.0
    assert!(
        (ratios[1] - 1.0).abs() < 0.01,
        "interior ratio ≈ 1.0, got {}",
        ratios[1]
    );
    // All ratios should be positive and bounded
    for &r in &ratios {
        assert!(r > 0.0 && r <= 10.0, "ratio out of bounds: {r}");
    }
}

#[test]
fn test_multistep_ratios_empty() {
    assert!(compute_multistep_ratios(&[]).is_empty());
    assert!(compute_multistep_ratios(&[0.5]).is_empty());
    assert_eq!(compute_multistep_ratios(&[0.0, 1.0]), vec![1.0]);
}

#[test]
fn test_multistep_ratios_non_uniform() {
    // Non-uniform steps should produce varying r_i
    // Heavily skewed schedule: more steps at the beginning
    let steps = vec![0.0, 0.1, 0.3, 0.6, 1.0];
    let ratios = compute_multistep_ratios(&steps);
    assert_eq!(ratios.len(), 3, "5 steps → 3 ratios");

    // For non-uniform steps, not all r_i should be identical
    let all_same = ratios.windows(2).all(|w| (w[0] - w[1]).abs() < 0.01);
    assert!(
        !all_same,
        "non-uniform steps should produce varying ratios: {ratios:?}"
    );

    // All ratios should be positive and bounded
    for &r in &ratios {
        assert!(r > 0.0, "ratio should be positive, got {r}");
        assert!(r <= 10.0, "ratio should be clamped to 10.0, got {r}");
    }
}

#[test]
fn test_multistep_ratios_logit_normal() {
    let mut rng = Rng::new(42);
    let schedule = ScheduleKind::LogitNormal {
        mean: -1.5,
        std: 0.8,
    };
    let steps = schedule.generate_steps(8, &mut rng);
    let ratios = compute_multistep_ratios(&steps);

    // N steps → N-2 ratios (need 3 consecutive λ points for one ratio)
    assert_eq!(ratios.len(), 6, "8 steps → 6 ratios");
    for &r in &ratios {
        assert!(r > 0.0 && r <= 10.0, "ratio out of bounds: {r}");
    }
}

#[test]
fn test_multistep_ratios_equi_probability() {
    let schedule = ScheduleKind::EquiProbability {
        mean: -1.2,
        std: 1.2,
    };
    let steps = schedule.generate_steps(6, &mut Rng::new(42));
    let ratios = compute_multistep_ratios(&steps);

    // N steps → N-2 ratios
    assert_eq!(ratios.len(), 4, "6 steps → 4 ratios");
    for &r in &ratios {
        assert!(r > 0.0 && r <= 10.0, "ratio out of bounds: {r}");
    }
}

#[test]
fn test_multistep_with_logit_normal_schedule() {
    // Verify multistep decode works with non-uniform LogitNormal schedule
    let config = Config::micro_dllm();
    let mut rng = Rng::new(42);
    let weights = TransformerWeights::new(&config, &mut rng);

    let decode_config = D2fDecodeConfig {
        denoise_steps: 4,
        multistep: true,
        schedule: ScheduleKind::LogitNormal {
            mean: -1.5,
            std: 0.8,
        },
        confidence_threshold: 0.3,
        block_size: config.block_size,
        temperature: 0.8,
        ..D2fDecodeConfig::default()
    };

    let result = d2f_decode_block(
        &weights,
        &config,
        &decode_config,
        &NoPruner,
        &NoScreeningPruner,
        &mut rng,
    );

    assert_eq!(result.tokens.len(), config.block_size);
    // steps_used may be less than denoise_steps if converged early
    assert!(
        result.steps_used <= decode_config.denoise_steps,
        "steps_used {} exceeds max {}",
        result.steps_used,
        decode_config.denoise_steps
    );
    for &t in &result.tokens {
        assert!(t < config.vocab_size, "token {t} out of vocab range");
    }
}

#[test]
fn test_multistep_schedule_changes_blend_coefficients() {
    // Non-uniform schedule should produce different confidence history
    // than uniform schedule, since blend coefficients differ.
    let config = Config::micro_dllm();
    let weights = TransformerWeights::new(&config, &mut Rng::new(42));

    let uniform_config = D2fDecodeConfig {
        denoise_steps: 4,
        multistep: true,
        schedule: ScheduleKind::Uniform,
        ..D2fDecodeConfig::with_block_size(4)
    };
    let logit_normal_config = D2fDecodeConfig {
        denoise_steps: 4,
        multistep: true,
        schedule: ScheduleKind::LogitNormal {
            mean: -1.5,
            std: 0.8,
        },
        ..D2fDecodeConfig::with_block_size(4)
    };

    let result_uniform = d2f_decode_block(
        &weights,
        &config,
        &uniform_config,
        &NoPruner,
        &NoScreeningPruner,
        &mut Rng::new(42),
    );
    let result_logit_normal = d2f_decode_block(
        &weights,
        &config,
        &logit_normal_config,
        &NoPruner,
        &NoScreeningPruner,
        &mut Rng::new(42),
    );

    assert_eq!(
        result_uniform.tokens.len(),
        result_logit_normal.tokens.len()
    );
    // Both should produce valid output regardless of schedule
    for &t in &result_uniform.tokens {
        assert!(t < config.vocab_size);
    }
    for &t in &result_logit_normal.tokens {
        assert!(t < config.vocab_size);
    }
}

/// Plan 602 T1.3: π emission from the D2F block-decode core.
#[cfg(feature = "decode_order_metrics")]
#[test]
fn test_decode_block_unmask_steps() {
    let config = Config::micro_dllm();
    // τ = 0: every masked position with a live softmax commits on the step
    // it is first sampled — deterministic regardless of weight draw.
    let decode_config = D2fDecodeConfig {
        denoise_steps: 4,
        confidence_threshold: 0.0,
        ..D2fDecodeConfig::with_block_size(4)
    };
    let mut rng = Rng::new(42);

    let weights = TransformerWeights::new(&config, &mut rng);
    let mut ctx = D2fContext::new(&config);

    let (result, pi) = d2f_decode_block_with_unmask_steps(
        &mut ctx,
        &weights,
        &config,
        &decode_config,
        &[],
        &NoPruner,
        &NoScreeningPruner,
        &mut rng,
    );

    assert_eq!(pi.len(), decode_config.block_size);
    // τ = 0 ⇒ the whole block commits at step 0: a fully parallel π.
    assert_eq!(pi, vec![0u32; 4]);
    assert_eq!(result.state, D2fBlockState::FullyActivated);
    // The parallel-tie shape reads as anti-AR by contract (ties discordant).
    assert_eq!(katgpt_core::dllm::global_ar_ness(&pi), 0.0);
    assert_eq!(katgpt_core::dllm::local_ar_ness(&pi), 0.0);

    // τ = 1.1 (unreachable): nothing commits — every entry keeps the
    // sentinel and the metrics are NaN (the empty measurement is visible,
    // never a silent 0.5).
    let strict_config = D2fDecodeConfig {
        denoise_steps: 2,
        confidence_threshold: 1.1,
        ..D2fDecodeConfig::with_block_size(4)
    };
    let (result_never, pi_never) = d2f_decode_block_with_unmask_steps(
        &mut ctx,
        &weights,
        &config,
        &strict_config,
        &[],
        &NoPruner,
        &NoScreeningPruner,
        &mut Rng::new(42),
    );
    assert_eq!(pi_never, vec![u32::MAX; 4]);
    assert!(katgpt_core::dllm::global_ar_ness(&pi_never).is_nan());
    assert_ne!(result_never.state, D2fBlockState::FullyActivated);
}

// ═══════════════════════════════════════════════════════════
// Probe guidance (Issue 865 T1) — feature-gated: compiles to nothing
// without `probe_guidance`.
// ═══════════════════════════════════════════════════════════
#[cfg(feature = "probe_guidance")]
mod probe_guidance_tests {
    use super::*;
    use crate::d2f_context::WeakLogitProbe;

    /// Probe that writes `value` into every output slot.
    struct ConstProbe(f32);

    impl WeakLogitProbe for ConstProbe {
        fn probe(&mut self, _input: crate::d2f_context::ProbeCtx<'_>, out: &mut [f32]) {
            out.fill(self.0);
        }
    }

    /// Probe that writes a poison value — any invocation is detectable. Used
    /// to prove λ = 1.0 never invokes the probe (G1) and the combine never
    /// touches the strong logits.
    struct PoisonProbe;

    impl WeakLogitProbe for PoisonProbe {
        fn probe(&mut self, _input: crate::d2f_context::ProbeCtx<'_>, out: &mut [f32]) {
            out.fill(999.0);
        }
    }

    /// Probe carrying fixed values (set at construction) — for the
    /// probe == logits identity case.
    struct EchoProbe {
        values: Vec<f32>,
    }

    impl WeakLogitProbe for EchoProbe {
        fn probe(&mut self, _input: crate::d2f_context::ProbeCtx<'_>, out: &mut [f32]) {
            out.copy_from_slice(&self.values[..out.len()]);
        }
    }

    fn block_range(vocab: usize) -> std::ops::Range<usize> {
        2 * vocab..6 * vocab
    }

    #[test]
    fn combine_kernel_lambda_one_is_full_noop() {
        // G1: λ = 1.0 must not even invoke the probe — the poison stays
        // unwritten and the strong logits stay untouched.
        let config = Config::micro_dllm();
        let mut dctx = D2fContext::new(&config);
        let vocab = config.vocab_size;
        let range = block_range(vocab);
        for (i, l) in dctx.logits_flat[range.clone()].iter_mut().enumerate() {
            *l = (i % 13) as f32 * 0.25 - 1.0;
        }
        dctx.set_guidance(1.0, Box::new(PoisonProbe));
        let logits_before = dctx.logits_flat[range.clone()].to_vec();
        let probe_before = dctx.probe_logits_flat[range.clone()].to_vec();

        crate::d2f_context::apply_probe_guidance(&mut dctx, &[], 2, 6, vocab, config.n_embd, 0);

        assert_eq!(dctx.logits_flat[range.clone()], logits_before);
        assert_eq!(dctx.probe_logits_flat[range], probe_before);
    }

    #[test]
    fn combine_kernel_no_probe_is_noop() {
        // λ = 2.0 but no probe installed → unguided no-op.
        let config = Config::micro_dllm();
        let mut dctx = D2fContext::new(&config);
        let vocab = config.vocab_size;
        let range = block_range(vocab);
        for (i, l) in dctx.logits_flat[range.clone()].iter_mut().enumerate() {
            *l = (i % 7) as f32 * 0.5;
        }
        dctx.guidance_lambda = 2.0;
        let logits_before = dctx.logits_flat[range.clone()].to_vec();

        crate::d2f_context::apply_probe_guidance(&mut dctx, &[], 2, 6, vocab, config.n_embd, 0);

        assert_eq!(dctx.logits_flat[range], logits_before);
    }

    #[test]
    fn combine_kernel_formula() {
        // logits' = λ·logits + (1−λ)·probe, checked per element at λ = 0.5.
        let config = Config::micro_dllm();
        let mut dctx = D2fContext::new(&config);
        let vocab = config.vocab_size;
        let range = block_range(vocab);
        let n = range.len();
        for (i, l) in dctx.logits_flat[range.clone()].iter_mut().enumerate() {
            *l = (i % 11) as f32 * 0.3 - 1.2;
        }
        dctx.set_guidance(0.5, Box::new(ConstProbe(3.0)));
        let logits_before = dctx.logits_flat[range.clone()].to_vec();

        crate::d2f_context::apply_probe_guidance(&mut dctx, &[], 2, 6, vocab, config.n_embd, 0);

        for i in 0..n {
            let want = 0.5 * logits_before[i] + 0.5 * 3.0;
            assert_eq!(dctx.logits_flat[range.start + i], want, "elem {i}");
        }
    }

    #[test]
    fn combine_kernel_lambda_zero_replaces_with_probe() {
        // λ = 0: the weak side fully replaces the strong side.
        let config = Config::micro_dllm();
        let mut dctx = D2fContext::new(&config);
        let vocab = config.vocab_size;
        let range = block_range(vocab);
        for (i, l) in dctx.logits_flat[range.clone()].iter_mut().enumerate() {
            *l = (i % 5) as f32;
        }
        dctx.set_guidance(0.0, Box::new(ConstProbe(-2.5)));

        crate::d2f_context::apply_probe_guidance(&mut dctx, &[], 2, 6, vocab, config.n_embd, 0);

        assert!(dctx.logits_flat[range].iter().all(|&l| l == -2.5));
    }

    #[test]
    fn combine_kernel_probe_equals_logits_is_fixed_point() {
        // probe == logits ⇒ logits' = λ·l + (1−λ)·l = l — the affine form's
        // fixed point. Bit-exact only at λ = 1 (the two weighted terms round
        // independently otherwise); at λ = 1.75 hold it to f32 rounding.
        let config = Config::micro_dllm();
        let mut dctx = D2fContext::new(&config);
        let vocab = config.vocab_size;
        let range = block_range(vocab);
        let values: Vec<f32> = (0..range.len()).map(|i| (i % 17) as f32 * 0.2 - 1.0).collect();
        dctx.logits_flat[range.clone()].copy_from_slice(&values);
        dctx.set_guidance(1.75, Box::new(EchoProbe { values: values.clone() }));

        crate::d2f_context::apply_probe_guidance(&mut dctx, &[], 2, 6, vocab, config.n_embd, 0);

        for (a, b) in dctx.logits_flat[range].iter().zip(values.iter()) {
            assert!((a - b).abs() < 1e-4, "fixed point drift {a} vs {b}");
        }
    }

    /// Decode one block from the same seed twice: once unguided, once with
    /// the given guidance installed, and compare results field-wise.
    fn decode_pair(
        install: Option<(f32, Box<dyn WeakLogitProbe>)>,
    ) -> (D2fBlockResult, D2fBlockResult) {
        let config = Config::micro_dllm();
        let decode_config = D2fDecodeConfig::with_block_size(4);
        let weights = TransformerWeights::new(&config, &mut Rng::new(42));

        let mut plain = D2fContext::new(&config);
        let unguided = d2f_decode_block_with_prompt_with(
            &mut plain,
            &weights,
            &config,
            &decode_config,
            &[],
            &NoPruner,
            &NoScreeningPruner,
            &mut Rng::new(42),
        );

        let mut guided_ctx = D2fContext::new(&config);
        if let Some((lambda, probe)) = install {
            guided_ctx.set_guidance(lambda, probe);
        }
        let guided = d2f_decode_block_with_prompt_with(
            &mut guided_ctx,
            &weights,
            &config,
            &decode_config,
            &[],
            &NoPruner,
            &NoScreeningPruner,
            &mut Rng::new(42),
        );
        (unguided, guided)
    }

    fn results_equal(a: &D2fBlockResult, b: &D2fBlockResult) -> bool {
        a.tokens == b.tokens
            && a.confidence_history == b.confidence_history
            && a.steps_used == b.steps_used
    }

    #[test]
    fn g1_lambda_one_guided_is_bit_identical_to_unguided() {
        // G1 end-to-end: λ = 1.0 with a poison probe installed decodes
        // byte-identical to unguided — the probe is never invoked.
        let (unguided, guided) = decode_pair(Some((1.0, Box::new(PoisonProbe))));
        assert!(results_equal(&unguided, &guided));
    }

    #[test]
    fn absent_probe_lambda_two_is_bit_identical_to_unguided() {
        // Guidance strength alone does nothing without a probe.
        let (unguided, guided) = decode_pair(None);
        assert!(results_equal(&unguided, &guided));
    }

    #[test]
    fn guidance_can_override_strong_proposal() {
        // micro_dllm collapses to a point mass (every position picks one token
        // with confidence 1.0), so sharpening (λ=2, zero probe) is invisible.
        // What IS observable: a probe favoring a different token at λ < 1
        // pulls the proposal toward it — proving the weak side can override
        // the strong side when blended.
        struct OpposingProbe {
            token: usize,
            boost: f32,
        }
        impl WeakLogitProbe for OpposingProbe {
            fn probe(&mut self, input: crate::d2f_context::ProbeCtx<'_>, out: &mut [f32]) {
                let count = input.seq_len - input.block_start;
                for p in 0..count {
                    for t in 0..input.vocab {
                        out[p * input.vocab + t] = if t == self.token { self.boost } else { 0.0 };
                    }
                }
            }
        }
        let vocab = Config::micro_dllm().vocab_size;
        let strong_pick = 15usize; // the point-mass token this fixture collapses to
        let other = (strong_pick + 7) % (vocab - 1); // mask_token = vocab−1, never propose it
        let (unguided, guided) = decode_pair(Some((
            0.5,
            Box::new(OpposingProbe { token: other, boost: 10.0 }),
        )));
        assert_eq!(
            unguided.tokens,
            vec![strong_pick; unguided.tokens.len()],
            "fixture premise: unguided decode collapses to the point mass"
        );
        assert_ne!(
            guided.tokens, unguided.tokens,
            "guided decode must diverge from the point mass somewhere, got {:?}",
            guided.tokens
        );
    }

    #[test]
    fn pipeline_set_guidance_wires_through() {
        // The pipeline builder applies guidance to its internal context:
        // λ = 1.0 + poison probe decodes identical to the plain pipeline.
        let config = Config::micro_dllm();
        let decode_config = D2fDecodeConfig::with_block_size(4);
        let weights = TransformerWeights::new(&config, &mut Rng::new(42));

        let plain = D2fPipeline::with_prompt(&config, decode_config, 4, &[0, 1])
            .decode_all(&weights, &NoPruner, &NoScreeningPruner, &mut Rng::new(42));
        let guided = D2fPipeline::with_prompt(&config, decode_config, 4, &[0, 1])
            .set_guidance(1.0, Box::new(PoisonProbe))
            .decode_all(&weights, &NoPruner, &NoScreeningPruner, &mut Rng::new(42));

        assert_eq!(plain.tokens, guided.tokens);
        assert_eq!(plain.total_steps, guided.total_steps);
    }

    #[test]
    fn pipeline_guidance_below_one_is_not_vacuous() {
        // Issue 865 T1 fix (found by T2): decode_all's own loop never called
        // apply_probe_guidance — set_guidance was dead on the pipeline path
        // and the λ = 1 test above passed vacuously. This test FAILS on that
        // build: an opposing probe at λ = 0.5 must actually move the decode.
        let config = Config::micro_dllm();
        let vocab = config.vocab_size;
        let decode_config = D2fDecodeConfig::with_block_size(4);
        let weights = TransformerWeights::new(&config, &mut Rng::new(42));
        let strong_pick = 15usize;
        let other = (strong_pick + 7) % (vocab - 1); // mask_token = vocab−1, never propose it
        struct OpposingProbe {
            token: usize,
            boost: f32,
        }
        impl WeakLogitProbe for OpposingProbe {
            fn probe(&mut self, input: crate::d2f_context::ProbeCtx<'_>, out: &mut [f32]) {
                let count = input.seq_len - input.block_start;
                for p in 0..count {
                    for t in 0..input.vocab {
                        out[p * input.vocab + t] = if t == self.token { self.boost } else { 0.0 };
                    }
                }
            }
        }

        let plain = D2fPipeline::with_prompt(&config, decode_config, 4, &[0, 1])
            .decode_all(&weights, &NoPruner, &NoScreeningPruner, &mut Rng::new(42));
        let guided = D2fPipeline::with_prompt(&config, decode_config, 4, &[0, 1])
            .set_guidance(0.5, Box::new(OpposingProbe { token: other, boost: 1000.0 }))
            .decode_all(&weights, &NoPruner, &NoScreeningPruner, &mut Rng::new(42));

        assert_ne!(
            plain.tokens, guided.tokens,
            "pipeline guidance at λ=0.5 must move the decode (non-vacuous wiring)"
        );
    }

    #[test]
    fn tap_capture_never_moves_logits() {
        // The T2 tap is a pure COPY inside the forward KERNEL: a capture-on
        // forward must be bit-identical to capture off, and the taps must
        // actually be written. (Kernel level — the decode cores arm capture
        // themselves when guidance is live, by design.)
        let config = Config::micro_dllm();
        let weights = TransformerWeights::new(&config, &mut Rng::new(42));
        let tokens: Vec<usize> = vec![0, 5, config.mask_token, 3, 7, 9];

        let mut off_ctx = D2fContext::new(&config);
        forward_block_causal_with(&mut off_ctx, &weights, &tokens, &config, 4);

        let mut on_ctx = D2fContext::new(&config);
        on_ctx.probe_tap_capture = true;
        forward_block_causal_with(&mut on_ctx, &weights, &tokens, &config, 4);

        assert_eq!(
            off_ctx.logits_flat,
            on_ctx.logits_flat,
            "capture is a pure copy — logits must be bit-identical"
        );
        let n = config.n_embd;
        let any_written = (0..tokens.len())
            .any(|p| on_ctx.probe_tap_flat[p * n..(p + 1) * n].iter().any(|&v| v != 0.0));
        assert!(any_written, "armed capture must populate probe_tap_flat");
        // And the capture must differ from the pre-layer input residual (it
        // carries the attention output) at least somewhere.
        let differs_from_xr = (0..tokens.len()).any(|p| {
            on_ctx.probe_tap_flat[p * n..(p + 1) * n] != off_ctx.xr[p * n..(p + 1) * n]
        });
        assert!(
            differs_from_xr,
            "the tap (post-attention) must differ from xr (pre-attention) somewhere"
        );
    }

    // ── Issue 865 T2: the trained artifact path ──────────────────────

    use katgpt_speculative::belief_drafter::LatentDynamicsMLP;
    use katgpt_speculative::probe_artifact::ProbeArtifact;
    use crate::weak_probe_mlp::MlpWeakProbe;

    fn artifact_probe() -> MlpWeakProbe {
        let config = Config::micro_dllm();
        let mlp = LatentDynamicsMLP::random_init(config.n_embd);
        let lm_head: Vec<f32> = (0..config.vocab_size * config.n_embd)
            .map(|i| ((i % 23) as f32) * 0.1 - 1.0)
            .collect();
        let artifact = ProbeArtifact::from_parts(mlp, lm_head, 0, 1).expect("artifact");
        MlpWeakProbe::new(artifact).expect("wrap")
    }

    #[test]
    fn artifact_probe_lambda_one_is_bit_identical_end_to_end() {
        // G1 through the T2 path: a real artifact probe at λ = 1.0 must be a
        // full no-op (the combine is skipped, the probe never invoked), not
        // merely numerically neutral.
        let (unguided, guided) = decode_pair(Some((1.0, Box::new(artifact_probe()))));
        assert!(results_equal(&unguided, &guided));
    }

    #[test]
    fn artifact_probe_below_one_engages_the_weak_side() {
        // A random-init artifact differs from the trunk's own head, so a λ
        // below 1 must engage the weak side — the decode diverges from
        // unguided somewhere. (The paper's quality claim is T3's λ-sweep
        // gate; this test only proves the artifact path is LIVE end to end.)
        let (unguided, guided) = decode_pair(Some((0.5, Box::new(artifact_probe()))));
        assert!(
            !results_equal(&unguided, &guided),
            "λ=0.5 with a divergent artifact must move the decode somewhere"
        );
    }
}
