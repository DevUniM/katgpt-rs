# Bench 813 — Prior-Logit Lane + Sink Margin Forecast GOAT (Issue 819, Research 566)

**Status:** COMPLETE — G1–G4 ALL PASS; both primitives stay OPT-IN (no-default-consumer rule)
**Date:** 2026-09-17
**Source:** Research 566 (arXiv:2601.15380 "You Need Better Attention Priors", ICML 2026) + the note's sigmoid-EOT derivation (§2, no published prior art)
**Issue:** `.issues/819_sigmoid_prior_logit_lane_sink_margin_forecast.md` (T1–T3 landed; T4 owner-gated; T5 landed same commit)
**Bench:** `crates/katgpt-core/benches/bench_813_prior_lane_margin_goat.rs` (harness=false, Instant, best-of)
**Features:** `prior_logit_lane` (T2) · `sink_margin_forecast` (T1) — both opt-in, zero deps, wasm-clean (pure f32 + std)

## What landed

| Task | Surface | Mechanism |
|---|---|---|
| T1 sink margin + forecast | `data_probe::sink_classify` | `SinkDiagnostic.margin: Option<f32>` (gated `sink_margin_forecast`) — mean per-query sink-minus-context-centroid logit margin, closed form `δ̂ = (n·c̄_s − R̄)/(n−1)` (algebraically identical to the naive per-query mean; one O(n²) pass + O(n) per candidate — the same asymptotic class as the classifier's col_sums pass). Logits invert through a `[1e-6, 1−1e-6]` clamp. `forecast_stable_positions(δ) = e^δ` — the context length a measured margin protects at the ε = ½ noise budget (Ψ ≤ (L−1)/(e^δ+L−1)). Computed by the full-map paths only; single-column classifiers have no context and return `None`. |
| T2 per-key prior-logit lane | `parallax_attn` | `ParallaxConfig::prior_logits: Option<Arc<[f32]>>` (gated `prior_logit_lane`): `ℓ_j` added to each key's pre-normalization score — AFTER SSMax's length rescale (the prior enters unscaled, GOAT's pre-scaling reading) and BEFORE normalization. `None` = bit-identical (lane-off branch is the literal pre-lane loop); all-zero table also output-identical (the ±0.0 perturbation dies at exp(±0)=1 — tested). |
| T3 length-aware law | module docs | `parallax_attn` mod docs carry the sigmoid margin law `‖Δo‖ ≲ ε·(L−1)·e^{ω−δ}` ⇒ δ ≳ ω + ln L, the uniform-prior linear-growth instability (softmax saturates; sigmoid accumulates), and the constant-bias = maximum-entropy-style default-prior reading. `SigmoidFusionConfig::logit_bias` doc records the constant-prior special case + the per-call expression (`config.logit_bias = lane[j]`; the xHC forward already composes per-step bias this way). |
| T5 cross-refs | docs | Research 566 §4 table updated (filed → landed); Research 258/392 pointers; issue checkboxes updated. |

## GOAT verdict

**G1 correctness — PASS (14 tests, 2 new integration targets).**
- `tests/issue819_prior_logit_lane` (6): zeros-lane ≡ None bit-identity on BOTH score sites and both activations; lane-off ≡ uniform-weight reference; closed-form recovery `p_j = σ(ℓ_j)/Σσ(ℓ_k)` (sigmoid, the Research 566 §2 form) and `p_j = e^{ℓ_j}/Σe^{ℓ_k}` (softmax, the paper's `softmax(s/τ + log π)`); per-key monotonicity; lane+SSMax composition.
- `tests/issue819_sink_margin_forecast` (8): forecast closed form (`e^0=1`, `e^{ln10}=10`, monotone, negative-δ honest `<1`); planted-margin recovery — constant and query-varying sink logits, exact to the closed form (mean sink logit − mean context logit); **brute-force sensitivity sim vs the law**: sink-protected head (context priors at −δ), measured ‖Δo‖ under +ε coherent context perturbation stays under `ε·(L−1)·σ(ω−δ)` ≤ `ε·(L−1)·e^{ω−δ}` for L ∈ {8, 64, 256}, δ ∈ {2, 4, 6} — and the unity-gain crossing length grows ≈ e^δ (the forecast's claim, checked against simulation); Figure-2c signature (sink share sheds strictly as ω grows at fixed δ while δ̂ holds ≈ δ); flat/Vec path agreement; n=1 / single-column `None` edges; uniform-map margin ≈ 0.

**G2 quality — PASS.** Planted-distractor: with all content scores exactly equal, ANY constant bias provably cancels to uniform weights (σ(s+b)/Σσ(s+b) = 1/L — verified for b ∈ {−4,−1,0,2}); the per-key lane at +4 lifts gold to the KL-prior closed form (≈1.75× uniform at L=8) — low-signal selectivity a constant prior cannot express, which is the issue's G2 statement.

**G3 latency — PASS.** Release, n=128 d=64, best-of 200: lane-off 122.04 µs vs lane-on 122.58 µs — **ratio 1.004×** (target ≤1.10×; the lane is one f32 add per key over already-hot scratch scores). `forecast_stable_positions` 1.3 ns/call (O(1)). Sink scan with margins 30.5 µs total at n=128 (O(n²) pass, same class as the col_sums pass the classifier already pays; 1 forced candidate exercised the margin loop).

**G4 alloc-free — PASS.** Counting global allocator, warm loops: lane-on forward == lane-off == **0 allocs**; forecast **0 allocs** / 1000 calls; flat sink scan with margins **0 steady-state allocs** (scratch + pre-reserved out). (First bench run FAILED G4 with a harness bug — cumulative-vs-delta snapshot comparison — fixed in the bench, not the kernel.)

**G5 no-regression — PASS.** Default-feature lib: 2063 passed / 0 failed (lane+margin code compiles to nothing; the config field is cfg'd out); `data_probe_sink_classify` (feature-off margin) 18/18; four-feature lib 2113/2113; clippy `-D warnings` clean at default, 4-feature, and `--all-features --lib`.

**MOAT:** in scope (attention slot). **Modelless:** closed forms + measured logits; zero training; zero new deps. **Promotion:** both features stay opt-in per the no-default-consumer rule — served GGUF checkpoints deliberately do not consume lanes (architecture change; Issue 819 non-goal). Promotion becomes an owner call when a runtime consumer (a future from-scratch arch) exists; T4 (0.4B test-arch training arm) stays gated behind owner pull.

## G5 addendum — the full 8-combo matrix (follow-up)

The G5 lane list above (default / 4-feature / all-features-lib) was an INCOMPLETE feature matrix, and two combos were red: `parallax_attn` alone (`build_sink_case` dead code — consumers all live behind `sink_aware_attn`) and `parallax_attn,sink_aware_attn` without `sink_margin_forecast` (2× `unused_mut` — the T1 `mut diag` became conditionally-used when the margin write moved behind the cfg; fallout of THIS bench's own T1 commit, not pre-existing). Both are the same latent class the AGENTS.md gate table warns about — a feature-conditional use site only compiles wrong in the combo nobody named. Fixed with a precise `#[cfg(feature = "sink_aware_attn")]` on the helper and `#[cfg_attr(not(feature = "sink_margin_forecast"), allow(unused_mut))]` on both `let`s; the full 8-combo sweep over {parallax_attn, sink_aware_attn, sink_margin_forecast, prior_logit_lane} is green at `--all-targets -D warnings`, 24 `parallax_attn` module tests pass under the 4-feature combo.

## Honest deviations from the issue text

1. **Lane home is `ParallaxConfig`, not `SigmoidFusionConfig`.** The issue sketched the field on `SigmoidFusionConfig`, but the engram kernel is a SINGLE-key gate — a per-key lane there degenerates to `logit_bias` assignment per call (which the xHC forward already does per-step). The only place key-indexing exists is the multi-key path, so the lane landed on `ParallaxConfig` (which already carried the ssmax cfg-field precedent). The engram side gets the T3 law docs instead of a parallel mechanism (substrate-first: no duplicate lane under a second name). An `Option<&'a [f32]>` field was tried first and REVERTED — with the field cfg'd off, `'a` is unused (E0392) in `parallax_attn`-without-`prior_logit_lane` builds; the owned `Arc<[f32]>` keeps the config lifetime-free across every feature combination at one cold-path allocation per table build.
2. **The margin estimator is the total-logit margin** (sink-column logit centroid minus context centroid — measurable from the attention map alone), which under a uniform prior IS the content margin and under a lane is prior+sink-content (conservative proxy for the paper's prior-only δ). Documented in `sink_classify.rs`; the G1s sim validates the law it feeds.
3. **Scratch extension not needed** — the estimator needs two scalar accumulators, not a buffer; `StableRankScratch` is unchanged (a strictly better G4 story than the issue's "scratch extends" sketch).

## Measurement conditions

M3 Max (16-core, aarch64), release profile (`bench` inherits opt-level 3), quiet box, exclusive cargo (no sibling GPU/compute load — CPU-only bench). G3 figures are best-of-200 (Issue 723 harness) after 5 warmup calls; wall vs CPU not separately logged — the ratio (1.004×) is the gate, not the absolute µs.
