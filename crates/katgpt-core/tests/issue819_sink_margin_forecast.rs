#![cfg(all(feature = "sink_aware_attn", feature = "sink_margin_forecast"))]
//! Issue 819 T1 (Research 566) — sink margin estimator + stability forecast.
//!
//! G1  forecast closed-form basics (`e^0 = 1`, `e^{ln 10} = 10`, monotone);
//!     planted-margin recovery on the classifier: constant and query-varying
//!     sink logits — the estimator returns exactly
//!     `mean sink-column logit − mean context logit` (the closed form of
//!     "sink-key logit minus context logit centroid", Research 566 §2).
//! G1s brute-force sensitivity sim vs the margin law: a sink-protected head
//!     (context priors pushed down by δ) has context-noise sensitivity
//!     ≈ ε·(L−1)·sigmoid(ω−δ) ≤ ε·(L−1)·e^{ω−δ}; the unity-gain crossing length
//!     scales ≈ e^δ — the forecast's claim, checked against simulation.
//! G2  Figure-2c signature: at a fixed prior margin, sink posterior share
//!     sheds strictly as content range ω grows (the protection the margin
//!     buys is spent by content rivals), while the measured margin itself
//!     stays ≈ δ. Flat/Vec scan paths agree; single-column and n<2 report
//!     `None`; uniform maps read margin ≈ 0.
//!
//! Reference: Research 566 §2 (sigmoid margin law ‖Δo‖ ≲ ε·(L−1)·e^{ω−δ},
//! δ ≳ ω + ln L), arXiv:2601.15380 Thm 5.4 / Def 5.2 / Fig 2c.

use katgpt_core::data_probe::{
    SinkClassifierConfig, SinkDiagnostic, StableRankScratch, classify_all_sinks,
    classify_all_sinks_flat, classify_sink_at, forecast_stable_positions,
};

fn sigmoid(x: f32) -> f32 {
    1.0 / (1.0 + (-x).exp())
}

/// Attention map `n × n` with sink column `s` at logit `sink_logit` and all
/// other entries at logit `ctx_logit`.
fn constant_map(n: usize, s: usize, sink_logit: f32, ctx_logit: f32) -> Vec<Vec<f32>> {
    (0..n)
        .map(|_| {
            (0..n)
                .map(|j| {
                    if j == s {
                        sigmoid(sink_logit)
                    } else {
                        sigmoid(ctx_logit)
                    }
                })
                .collect()
        })
        .collect()
}

fn classify(map: &[Vec<f32>], cfg: &SinkClassifierConfig) -> Vec<SinkDiagnostic> {
    let mut scratch = StableRankScratch::new(4);
    let mut out = Vec::new();
    let values = vec![vec![1.0f32; 4]; map.len()];
    classify_all_sinks(map, &values, cfg, &mut scratch, &mut out);
    out
}

fn flat(map: &[Vec<f32>], cfg: &SinkClassifierConfig) -> Vec<SinkDiagnostic> {
    let n = map.len();
    let flat: Vec<f32> = map.iter().flatten().copied().collect();
    let mut scratch = StableRankScratch::new(4);
    let mut out = Vec::new();
    let values = vec![1.0f32; n * 4];
    classify_all_sinks_flat(&flat, n, &values, 4, cfg, &mut scratch, &mut out);
    out
}

// ── G1: forecast closed form ─────────────────────────────────────────────

#[test]
fn forecast_closed_form_basics() {
    assert_eq!(forecast_stable_positions(0.0), 1.0);
    assert!((forecast_stable_positions(10.0_f32.ln()) - 10.0).abs() < 1e-4);
    assert!((forecast_stable_positions(100.0_f32.ln()) - 100.0).abs() < 1e-2);
    // Monotone; negative margin honestly forecasts < 1 position.
    assert!(forecast_stable_positions(3.0) > forecast_stable_positions(2.0));
    assert!(forecast_stable_positions(-1.0) < 1.0);
}

// ── G1: planted-margin recovery ──────────────────────────────────────────

#[test]
fn estimator_recovers_constant_planted_margin() {
    let n = 16;
    let s = 0;
    let cfg = SinkClassifierConfig::default();
    for &delta in &[0.5f32, 2.0, 4.0] {
        // Sink column at logit δ, context at 0 (σ = 0.5 exactly, which sits
        // AT τ_sink and is excluded — only the sink column is a candidate).
        let map = constant_map(n, s, delta, 0.0);
        let diags = classify(&map, &cfg);
        assert_eq!(diags.len(), 1, "exactly the sink column clears τ_sink");
        let d = &diags[0];
        assert_eq!(d.position, s);
        let margin = d
            .margin
            .expect("full-map scan must populate margin under the feature");
        assert!(
            (margin - delta).abs() < 1e-3,
            "δ={delta}: estimator returned {margin}, want ~{delta}"
        );
        // Forecast coherence: N ≈ e^δ.
        let forecast = forecast_stable_positions(margin);
        assert!((forecast - delta.exp()).abs() < 1e-2);
    }
}

#[test]
fn estimator_recovers_query_varying_sink_logits() {
    // Sink logit per row ℓ_i = δ + u_i with mean(u) = m̄: the estimator must
    // return δ + m̄ − ctx (mean sink logit minus mean context logit, exactly).
    let n = 12;
    let s = 3;
    let delta = 2.0f32;
    let ctx = -0.5f32;
    let u: Vec<f32> = (0..n).map(|i| ((i as f32) * 0.7).sin() * 0.4).collect();
    let mean_u: f32 = u.iter().sum::<f32>() / n as f32;

    let map: Vec<Vec<f32>> = (0..n)
        .map(|i| {
            (0..n)
                .map(|j| {
                    if j == s {
                        sigmoid(delta + u[i])
                    } else {
                        sigmoid(ctx)
                    }
                })
                .collect()
        })
        .collect();

    let cfg = SinkClassifierConfig::default();
    let diags = classify(&map, &cfg);
    assert_eq!(diags.len(), 1);
    let margin = diags[0].margin.expect("margin must be populated");
    let want = delta + mean_u - ctx;
    assert!(
        (margin - want).abs() < 1e-3,
        "varying-u: got {margin}, want {want} (mean sink logit − mean context logit)"
    );
}

// ── G1s: brute-force sensitivity sim vs the margin law ───────────────────

/// A sink-protected head in the paper's parameterization: sink prior logit 0,
/// context prior logits pushed DOWN by δ (that is what a sink lane buys), each
/// carrying content in (−ω/2, +ω/2). Unnormalized sigmoid gates — the
/// hypercube setting the margin law bounds:
/// `o = sigmoid(c_sink)·v_s + Σ_k sigmoid(c_k − δ)·v_k`.
///
/// Returns ‖Δo‖ for a coherent +ε perturbation of every context logit
/// (worst-case direction: each context gate rises).
fn sensitivity(delta: f32, l: usize, omega: f32, eps: f32) -> f32 {
    let ctx: Vec<f32> = (1..l)
        .map(|k| {
            let t = (k as f32 * 0.618_034) % 1.0; // golden-ratio scramble
            (t - 0.5) * omega
        })
        .collect();
    // Value vectors: a COMMON unit direction plus a small per-key jitter —
    // with a zero-sum direction mix the perturbation responses cancel and
    // the linear-in-L growth the law predicts never materializes.
    let v: Vec<[f32; 4]> = (0..l)
        .map(|j| {
            let jit = ((j % 3) as f32) * 0.05;
            [1.0, jit, -jit, jit * 0.5]
        })
        .collect();

    let out_for = |ctx_shift: f32| {
        let mut o = [0.0f32; 4];
        // Sink gate: content-free (content range lives in the context).
        let g_s = sigmoid(0.0);
        for d in 0..4 {
            o[d] += g_s * v[0][d];
        }
        for (k, &c) in ctx.iter().enumerate() {
            let g = sigmoid(c + ctx_shift - delta);
            for d in 0..4 {
                o[d] += g * v[k + 1][d];
            }
        }
        o
    };

    let base = out_for(0.0);
    let pert = out_for(eps);
    let diff: f32 = (0..4)
        .map(|d| (pert[d] - base[d]) * (pert[d] - base[d]))
        .sum::<f32>()
        .sqrt();
    diff
}

#[test]
fn sensitivity_agrees_with_margin_bound_on_toy_margins() {
    let eps = 0.05f32;
    let omega = 1.0f32;
    for &delta in &[2.0f32, 4.0, 6.0] {
        for &l in &[8usize, 64, 256] {
            let meas = sensitivity(delta, l, omega, eps);
            // Bound: ε·(L−1)·sigmoid(ω−δ) ≤ ε·(L−1)·e^{ω−δ} (Research 566 §2 —
            // each context gate ≤ sigmoid(ω−δ) under the −δ prior shift).
            let bound = eps * (l as f32 - 1.0) * sigmoid(omega - delta);
            assert!(
                meas <= bound * 1.05 + 1e-6,
                "δ={delta} L={l}: measured sensitivity {meas} exceeds bound {bound}"
            );
        }
    }
    // The forecast's claim, brute-forced: the context length at which noise
    // passes through at ~unity gain (measured = ε) grows with the margin δ.
    // Grow L geometrically until measured ≥ ε; the crossing for δ+2 must sit
    // well past the crossing for δ (the law predicts ≈ e² ≈ 7.4×; assert
    // > 4× for slack against the value-vector direction mix).
    let crossing = |delta: f32| {
        let mut l = 4usize;
        while l < 1 << 22 && sensitivity(delta, l, omega, eps) < eps {
            l = (l as f32 * 1.25) as usize;
        }
        l
    };
    let lo = crossing(2.0);
    let hi = crossing(4.0);
    assert!(
        (hi as f32) > 4.0 * (lo as f32),
        "unity-gain length must grow ≈ e^δ: δ=2 crossed at {lo}, δ=4 at {hi}"
    );
}

// ── G2: Figure-2c signature — sink share sheds as ω grows ────────────────

const SINK_LOGIT: f32 = 2.0; // sigmoid(2) ≈ 0.88 mass — clears τ_sink comfortably

#[test]
fn sink_share_sheds_as_content_range_grows() {
    let n = 16;
    let s = 0;
    let delta = 3.0f32; // context priors sit at SINK_LOGIT − delta
    let cfg = SinkClassifierConfig::default();
    let mut prev_share = f32::INFINITY;
    for &omega in &[0.5f32, 1.0, 2.0, 4.0] {
        // Sink-protected map: context logits = content(−ω/2..ω/2) − delta,
        // relative to the sink's prior logit.
        let map: Vec<Vec<f32>> = (0..n)
            .map(|i| {
                (0..n)
                    .map(|j| {
                        if j == s {
                            sigmoid(SINK_LOGIT)
                        } else {
                            let t = ((i * n + j) as f32 * 0.618_034) % 1.0;
                            sigmoid((t - 0.5) * omega - delta + SINK_LOGIT)
                        }
                    })
                    .collect()
            })
            .collect();

        // Sink posterior share (per-row reading, row 0's gates).
        let sink_gate = sigmoid(SINK_LOGIT);
        let ctx_sum: f32 = map[0]
            .iter()
            .enumerate()
            .filter(|&(j, _)| j != s)
            .map(|(_, &p)| p)
            .sum();
        let share = sink_gate / (sink_gate + ctx_sum);
        assert!(
            share < prev_share,
            "sink share must strictly decrease as ω grows: ω={omega} share={share} prev={prev_share}"
        );
        prev_share = share;

        // The measured margin stays ≈ delta (the prior margin is stable; it
        // is the protection that erodes as ω spends it — the forecast reads
        // the erosion through the ω-term of the law, not through δ̂).
        let diags = classify(&map, &cfg);
        let d = diags
            .iter()
            .find(|d| d.position == s)
            .expect("sink column must clear τ_sink");
        let margin = d.margin.expect("margin populated");
        assert!(
            (margin - delta).abs() < 0.35,
            "measured margin should stay near the planted δ across ω: got {margin}"
        );
        // And the margin law's own term grows with ω: e^{ω−δ} → the forecast
        // horizon e^{δ−ω} shrinks, matching the observed share shedding.
        let horizon = forecast_stable_positions(delta - omega);
        assert!(
            horizon < forecast_stable_positions(delta),
            "effective horizon must shrink as ω grows"
        );
    }
}

// ── Path agreement + edges ───────────────────────────────────────────────

#[test]
fn flat_and_vec_paths_agree() {
    let n = 16;
    let map = constant_map(n, 2, 2.5, 0.0);
    let cfg = SinkClassifierConfig::default();
    let vec_diags = classify(&map, &cfg);
    let flat_diags = flat(&map, &cfg);
    assert_eq!(vec_diags.len(), flat_diags.len());
    for (a, b) in vec_diags.iter().zip(flat_diags.iter()) {
        assert_eq!(a.position, b.position);
        let (ma, mb) = (
            a.margin.expect("vec margin"),
            b.margin.expect("flat margin"),
        );
        assert!(
            (ma - mb).abs() < 1e-4,
            "flat/Vec margin disagreement: {ma} vs {mb}"
        );
    }
}

#[test]
fn none_edges_single_column_and_tiny_maps() {
    let cfg = SinkClassifierConfig::default();
    // n = 1 map: no context to centroid against.
    let map = vec![vec![0.9f32]];
    let diags = classify(&map, &cfg);
    assert_eq!(diags.len(), 1);
    assert!(diags[0].margin.is_none(), "n=1 margin must be None");

    // Single-column classifier: no other columns available → None.
    let values = vec![vec![1.0f32; 4]; 4];
    let col = [0.9f32, 0.1, 0.1, 0.1];
    let mut scratch = StableRankScratch::new(4);
    let d = classify_sink_at(0, &col, &values, None, &cfg, &mut scratch);
    assert!(d.margin.is_none(), "single-column margin must be None");
}

#[test]
fn uniform_map_has_zero_margin() {
    let n = 16;
    let cfg = SinkClassifierConfig::default();
    // Uniform map: every column is identical, so sink-minus-centroid is
    // exactly 0 — no protection, no advantage (all n columns clear τ_sink
    // at uniform 0.8 and every margin must read ~0).
    let flat_map = vec![0.8f32; n * n];
    let mut scratch = StableRankScratch::new(4);
    let mut out = Vec::new();
    let values = vec![1.0f32; n * 4];
    classify_all_sinks_flat(&flat_map, n, &values, 4, &cfg, &mut scratch, &mut out);
    assert_eq!(out.len(), n, "every column clears τ_sink at uniform 0.8");
    for d in &out {
        let m = d.margin.expect("margin populated");
        assert!(
            m.abs() < 1e-4,
            "uniform map margin must be ~0: position {} margin {m}",
            d.position
        );
    }
}
