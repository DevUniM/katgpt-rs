# Bench 802 — commitment-gap calibration rig: RESIDUE DEAD-BY-DOMINATION at micro scale (Issue 802 item 1)

**Status:** RECORD — defend-wrong verdict executed per the issue's own rule.
G1 (gap signal) REGIME-DEPENDENT · G2 (calibrated beats tuned-global) PASS at
both p* · G3 FAIL — the no-gate one-forward baseline dominates the entire
joint-gate family. **The calibration residue is dead at micro scale**; the
scale-up condition is stated precisely below. Measured 2026-09-16, M3 Max,
release.

Rig: `../riir-ai/crates/riir-poc/benches/commitment_gap_calibration.rs`
(deterministic, ~3 min end-to-end incl. training; run command in the file
header). Provenance: Issue 802 item 1 from Research 561 (arXiv:2609.15177,
TSD). Consumes the shipped item-2 kernel (`jsd_topk`) and item-3 counters
(`SamplerFeatures::from_logits_into` + `StabilityTracker::observe`) as the
rig's measurement source — the issue's design, exercised end to end.

## Setup

- Micro D2F: `Config::micro_dllm` + 2 layers / n_embd 32 / mlp 128, trained
  per-sample SGD (lr 1e-3, 1500 epochs, **mask ratio 0.85** — matched to the
  decode regime of 14/16 masked; the stock 0.3 trains a 70%-visible model
  that is far off-distribution at decode time, the first run's confound).
- 5 task classes: Alt `[a,b,a,b,…]`, PairSwap `[a,b,b,a,…]`, Fib
  (tᵢ₊₁ = tᵢ + tᵢ₋₁ mod 26 — second-order recurrence, forces stepwise
  refinement), Cycle4 `[a,b,c,d,…]` (two free parameters per period —
  structural hostages), Noise (control). Learned honestly: Alt ≈ 0.94,
  Cycle4 ≈ 0.40; PairSwap/Fib stayed at chance at this scale (recorded, not
  hidden — they behave as extra noise-like classes).
- Decode mirrors production `d2f_decode_block_prompt_q_core`: 2-token prompt,
  greedy threshold commits, forced batch at the end. NFE = real forwards;
  stalls skip provably identical forwards (virtual aging only advances
  trackers — the honest accounting; without it stall-y policies inflate to
  the cap).
- λ_ref is NOT hand-set: p75 of the model's own forward-1 confidence
  (0.394 here). A fixed 0.9 either saturates or stalls depending on training
  regime — the probe-derived threshold is the transferable design.

## Measured verdict

| gate | claim | measured | verdict |
|---|---|---|---|
| G1 | gap JSD₂(p_t, p_commit) separates would-miss states (ratio ≥ 5, n_miss ≥ 100) | **regime-dependent**: 31–82× when the decode is cascade-dominated (revisions rare, 1.7–5% would-miss); **2.4×** when commits collapse into 1–2 waves (38% would-miss) | FAIL (pre-registered bar) |
| G2 | (c-ft) beats (b) at both p* | 0.2587 acc @ 1.76 fwd vs 0.2538 @ 2.47 — both axes, both p* | PASS |
| G3 | best calibrated not dominated by best fixed-λ | λ=0.9: **1.00 fwd @ 0.2937** vs (c-ft) 1.76 @ 0.2587 | FAIL (dominated) |

Overall: **RESIDUE DEAD-BY-DOMINATION** — (c) beats (b) exactly where the
precision constraint binds, but that regime is dominated by the trivial
one-forward no-gate baseline. The issue's verdict rule ("(c) must beat (b) or
the residue is dead") is satisfied only vacuously: the whole joint-gate
family sits strictly inside the λ frontier's efficient corner.

## Why (the mechanism, measured not argued)

1. **Self-consistency is the wrong label in contamination regimes.** The
   calibration label `[z_t == z_commit]` measures "will I change my mind",
   not "am I right". When commits are cascade-driven, the reference makes
   the same mistakes the deployed policy would — early commits match late
   ones at ~99% and precision never binds, so inversion collapses (b) ≡ (c).
2. **Where the constraint binds, the label decouples.** In the wave regime
   (38% would-miss) precision finally binds — and G2 confirms bucketing
   dominates a tuned global rule there (the one honest pro-calibration
   datum). But wave-regime revisions are context-driven: gap separation
   collapses (2.4×), and the Noise control shows the label's blindness
   outright (calibration precision 0.99+, eval accuracy 0.04).
3. **Single-pass calibration misses its own target off-policy.** Rules
   calibrated to p* = 0.90 on λ_ref trajectories realize only **0.609**
   early-commit precision under the deployed policy — committing changes the
   trajectory distribution. A DAgger-style refinement round is the recorded
   follow-up if anyone revives this at scale.
4. **Micro decode needs no iteration at all.** With matched-mask training,
   the model's forward-1 (prompt-only) predictions are its best: every
   iterative commit wave contaminates the context with its own errors
   (λ=0.3: 12 fwd @ 0.254 pre-skip accounting; the no-gate 1-forward policy:
   0.294). The item-4 horizon axis is undefined here for the same reason —
   the reference cascade completes in ≤ 2 waves, so there is no per-position
   horizon structure to reallocate verify budget against.

## What survives (and the revival condition)

- The **LESS joint gate itself** (published class, not claimed) showed one
  clean dominance over tuned λ in the cascade regime: 8.3 fwd @ 0.2567 vs
  λ=0.3's 12.1 @ 0.2538 — fewer forwards AND higher accuracy. Consistent
  with LESS's published 72% step reduction; no novelty claim.
- The **gap signal is real** in every regime (misses always carry larger
  gap) — the item-2 kernel + item-3 counters work as a measurement
  substrate for exactly the quantity TSD trains on.
- **Revival condition** (all three required): (i) large would-miss mass
  (real 8B dLLMs on multi-step reasoning — TSD's regime), (ii) revisions
  that improve rather than corrupt the context, (iii) a baseline that
  genuinely iterates (≥ 3+ forwards), and — per (3) — an on-policy
  (DAgger-style) calibration round. Micro cannot falsify the class at that
  scale; what micro kills is deployment of the calibration HERE and the
  novelty claim as filed.

Honest caveats: micro model learned 2 of 4 structured families; single
training seed per config (deterministic per config, but one draw); grid and
bucket counts are small-corpus choices (MIN_FIRES = 30). None of these
soften the G3 domination — the baseline wins by 3.5 accuracy points at half
the NFE, far outside any tuning noise.

Also landed with this record: the root `katgpt_rs::speculative`
re-export surface now carries `StabilityTracker`/`TOPK_DRIFT_K`/
`N_STABILITY_FEATURES` (item 3 shipped them in `katgpt-forward` but the root
shim missed them — the rig consumed them through the root path).
