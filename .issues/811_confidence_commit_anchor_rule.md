# Issue 811: Confidence-Commit Anchor Rule (DBTM κ ∪ floor) + t\* Schedule for the D2F Reveal Lane

**Status:** PoC COMPLETE 2026-09-16 — T4 verdict **PASS** on the steps/termination axis at quality parity (production upgrade planned as [Plan 600](../.plans/600_flashar_confidence_commit_upgrade.md); the strided incumbent stays default — demote-on-loss rule). T3 sweep-bench arm + T5 UGC cross-check deferred with reasons below.
**Date:** 2026-09-16
**Research:** [`.research/563_DBTM_Discrete_Beckmann_One_Step_Language.md`](../.research/563_DBTM_Discrete_Beckmann_One_Step_Language.md)
**Source:** Tang & Wang, arXiv:2609.15903 §5.1 (Eq 26 commit rule), §4.3 (Thm 4.1 t\*), Table 9/11/12
**Consumers:** `crates/katgpt-forward/src/flashar_anchor.rs` (`anchor_then_fill`), `katgpt_core::set_diffusion_schedule` (`PositionOffsetSchedule`), the Plan-381 schedule-sweep bench lane

## Context

DBTM's inference scheme commits tokens by **confidence/quality with a floor** — per round r of budget k:
`Δ𝒞_r = {ℓ : q_ℓ ≥ κ} ∪ top_{n_r}(q)`, `n_r = ⌈|R_r|/(k−r+1)⌉` — guaranteeing termination in exactly k forward calls, then renoises the rest and reapplies the same map (refinement, not ODE integration; their Table 9: one map application beats 64-step Euler integration of the learned field).

Two documented gaps make this actionable here:

1. **UGC's own Caveat #1** (`katgpt-core/src/ugc_schedule.rs`): its KL certificate covers *random-order* Bernoulli/fixed-cardinality reveal, "**NOT confidence-threshold (greedy per-token) reveal**". The confidence-greedy cell is uncovered — DBTM's rule + floor is exactly that cell, with the paper's Table 11 evidence that κ-adaptive commit beats fixed-cardinality at NFE ≥ 4.
2. **FlashAR `anchor_then_fill` selects anchors by STRIDE** (positional, fixed) — content-blind. The confidence signal already ships: DiffusionSampler (Plan 116) computes per-position confidence from the denoiser's own output (AUC 0.76–0.78 on micro-D2F).

Secondary arm — the **t\* commitment law** `t* = 1 − (1 + σ·√(2 ln V))^(−1/a)` (REM-derived; mode-collapse boundary for early supervision, safe-anchor boundary after): a 3-parameter closed form in the `IgnitionSchedule` timing-law family (Bench 666), consumable as a `PositionOffsetSchedule` variant (probability-ordered / t\*-gated reveal) where UGC must *estimate* its grid from data. Their Table 12: anchoring before t\* collapses modes, after t\* slows convergence — a principled constant where the lane currently sweeps by hand.

## PoC scope (T1–T3 before any feature lands)

Three competitors on the SAME trained mini-D2F (the `train_mini_dllm` pattern harness FlashAR's own tests use):

1. **strided anchor** ( incumbent — `AnchorConfig` stride)
2. **confidence-commit** (q = max-softmax per position, threshold κ, NO floor)
3. **confidence-commit + floor** (κ ∪ ⌈|R|/(k−r+1)⌉ — the DBTM rule)

Metrics: exact-pattern accuracy / generative quality at NFE ∈ {1, 2, 4, 8}; wall-clock; termination-within-k proof (property test for arm 3); renoise-vs-hold ablation for committed-context treatment.

## Tasks

- [x] T1 PoC harness: extend the flashar training-coupled test rig to run all three arms on one trained mini-D2F checkpoint (seeded, `CARGO_TARGET_DIR=/tmp/...`, clean up)
- [x] T2 Run the arm table at NFE {1,2,4,8} × κ {0.5, 0.9, 0.99}; record verdict table in this issue
- [x] T3 t\* schedule arm — pure-math half: `commit_time_star` (katgpt-core `ignition_schedule`) + `probability_order` (katgpt-core `set_diffusion_schedule`), both unit-tested; t\* constants recorded below
- [-] T3 Plan-381 sweep-bench arm (probability-ordered reveal vs uniform/ar/mdlm on the sweep bench) — DEFERRED: the set-causal train/eval seams (`train_mini_set_causal`, `evaluate_set_causal_nelbo`) accept `&PositionOffsetSchedule` only; a probability-ordered arm needs a custom-order seam. Seam issue FILED: [Issue 813](813_set_causal_custom_order_seam.md).
- [x] T4 Verdict: recorded below — PASS (conditional, honest scope) → upgrade planned as [Plan 600](../.plans/600_flashar_confidence_commit_upgrade.md)
- [-] T5 UGC cross-check (confidence-greedy reveal KL vs the UGC certificate) — DEFERRED: the T4 pass is on steps/termination at quality PARITY (no quality gain claimed), so the Caveat #1 certificate question is not load-bearing yet. Folded into Plan 600 T9 — required before any default-promotion claim on real text.

## Acceptance

- Measured table committed here (or a bench file ref) before any promotion; property test for the k-round termination guarantee; honest negative recorded if arm 3 ≤ arm 1.

---

## PoC results (2026-09-16, T1–T4)

**Harness** (`src/speculative/flashar_anchor.rs` tests, `--features flashar_anchor`): one trained mini-D2F (the `train_mini_dllm` recipe, 200 epochs, final test_acc 72%); 24 eval sequences, block=8, PAIRED seeds — every row draws the identical rng stream per sequence, so the Round-1 walk and its selection input are byte-identical across arms and only the rule differs. Parity guard `test_issue811_harness_matches_production`: the harness stride arm reproduces the production `anchor_then_fill` decode byte-identically. Round-1 walk records both the sampled token (production parity) and the (argmax, max-softmax q) proposal (the confidence signal the DBTM rule consumes); arms select over the SAME walk; the fill runs through the SHARED production path via the new `anchor_fill_with_prefilled` seam (`commit_budget: Option<usize>` arms the floor; `None` = incumbent semantics, zero extra work on the default path).

**Arm table** (acc = exact-match vs the alternating ground truth, ±1σ ≈ 0.026 on 192 samples; steps = fill rounds to convergence; wall µs includes the walk; k = fill budget):

| arm | κ | k | acc | steps | anchors | wall µs |
|---|---|---|---|---|---|---|
| all-mask D2F baseline | .70 | 8 | 0.062 | 2.00 | 0 | 266 |
| stride1 (pure AR anchors) | .70 | 8 | 0.167 | 1.00 | 8 | 128 |
| stride2 (incumbent, τ=.70) | .70 | 8 | 0.167 | 1.67 | 4 | 217 |
| stride2 τ=κ (matched ref) | .50 | 8 | 0.167 | 1.46 | 4 | 190 |
| stride2 τ=κ (matched ref) | .90 | 8 | 0.167 | 3.25 | 4 | 424 |
| stride2 τ=κ (matched ref) | .99 | 8 | 0.167 | 7.00 | 4 | 915 |
| conf κ (no floor) | .50 | 8 | 0.177 | 1.00 | 8 | 128 |
| conf κ (no floor) | .90 | 8 | 0.146 | 1.71 | 7.0 | 221 |
| conf κ (no floor) | .99 | 8 | 0.146 | 4.00 | 6.2 | 520 |
| conf κ + floor (DBTM) | .50 | 8 | 0.177 | 1.00 | 8 | 128 |
| conf κ + floor (DBTM) | .90 | 8 | 0.146 | **1.04** | 7.0 | **134** |
| conf κ + floor (DBTM) | .99 | 8 | 0.146 | **1.50** | 6.2 | **194** |

(Full 52-row grid at k ∈ {1,2,4,8} in the test output; k=1 and k=2 preserve the same ordering, all rows converged or budget-capped.)

**Findings:**

1. **The anchor round carries ALL the signal on this corpus** — all-mask D2F decodes at 0.031–0.062 accuracy vs 0.146–0.177 with any anchors. Anchor SELECTION is about how much of the walk's signal survives, and the confidence rule keeps MORE of it from the SAME walk: κ=0.5 commits 8/8 anchors vs stride's 4/8 (content-adaptive density vs fixed positional discard).
2. **Quality: parity, no regression.** All anchored arms sit at 0.146–0.177 — differences ≤1.2σ. The best cell (0.177) IS a confidence arm; the DBTM floor arm matches the matched-threshold stride arm everywhere within noise.
3. **Steps/wall: the DBTM floor wins decisively at high κ.** At κ=0.99/k=8: 1.50 steps / 194 µs vs 7.00 / 915 µs matched-stride (4.7×); at κ=0.90: 1.04 / 134 µs vs 3.25 / 424 µs (3.1×). The floor commits the stragglers the threshold keeps rejecting — the no-floor confidence arm crawls at 4.00 steps there. The floor also converts DBTM's termination bound into measured behavior: `test_issue811_termination_property` proves full unmask within budget at every (κ, k) cell INCLUDING κ=0.999, on the real model.
4. **Honest scope:** quality does not separate arms on this toy (anchor-dominated; ~1σ spread) — the pass is on the steps/termination axis at quality parity, NOT a quality win. Real-text quality gates are Plan 600 T8/T9 before any promotion.

**T4 verdict: PASS (conditional).** commit+floor beats the matched strided arm at 3 of 4 NFE points (k ∈ {2,4,8}) on steps-to-converge and wall at quality parity, and guarantees termination. → production upgrade planned as [Plan 600](../.plans/600_flashar_confidence_commit_upgrade.md) behind the existing `flashar_anchor` feature; strided incumbent stays default (demote-on-loss rule).

**Renoise-vs-hold ablation: not run** — the mapping has no clean analog here: in this port uncommitted positions are ALWAYS mask in the fill input (hold-by-mask is the incumbent semantics), so "renoise" would be a no-op; the informative ablation (argmax-draft context for uncommitted positions) needs a context/commitment split in the fill loop — noted as a Plan 600 option, not proceeding without a quality claim to test.

**T3 t\* constants (pure math landed in katgpt-core):** `commit_time_star(V, σ, a) = 1 − (1 + σ·√(2 ln V))^(−1/a)` — unit-tested against the paper's shape (near-flat in V: t\*(V=30522) − t\*(V=12) < 0.2 at σ=a=1; monotone in σ and V; σ→0 or a→∞ → t\*→0). Derived anchor constants for our lanes: micro_dllm (V=27, σ=0.3 mask ratio, a=1) → **t\* ≈ 0.435**; same vocab at σ=1 → t\* ≈ 0.720. `probability_order(confidence)` (confidence-descending, stable ties, NaN-last) is the matching reveal-order primitive — the pair is consumable as a t\*-gated probability-ordered schedule once the set-causal custom-order seam exists (the deferred T3 half).

**Validation:** 5/5 root harness tests + 2/2 new katgpt-forward dbtm tests + 20/20 ignition tests + probability_order tests green; clippy `-D warnings` clean on katgpt-core (all-features), katgpt-forward (dllm,flashar_anchor), katgpt-rs (flashar_anchor); root default-features check green (gated code compiles away).
