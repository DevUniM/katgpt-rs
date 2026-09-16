# Bench 809 — Set-Causal Reveal-Order Sweep: t\*-gated probability-ordered reveal vs uniform/ar/mdlm (Issue 813)

**Date:** 2026-09-17
**Issue:** Issue 813 — the Plan 600 T3 deferred arm (RESOLVED same day — the seam commit; the issue file removed per the noise-reduction rule, recoverable from git history)
**Harness:** `tests/bench_809_set_causal_order_sweep.rs` (`required-features = ["set_diffusion", "ignition_schedule"]`; run `cargo test --release -p katgpt-rs --test bench_809_set_causal_order_sweep --features set_diffusion,ignition_schedule -- --nocapture`)
**Verdict:** seam + arms LANDED and verified (G1 byte-identity, G2 t\*-gate mechanism, G3/G4 tables green) — the clean-token cells are self-copy trivial (no separation possible there), and **Addendum I resolves it: the denoiser objective measures REAL SEPARATION — prob-t\* is the best arm on both eval seeds** (2.59/2.61 nats vs uniform 2.89/2.88; Research 563 §4.3 measured green). Full story: Issue 816 (resolved same day, file removed per the noise rule — git history + Addendum I below).

## What landed

1. **The seam** (`src/dllm/set_causal.rs`, the module that now hosts the moved set-causal trainer): `train_mini_set_causal_with_gen_steps` / `evaluate_set_causal_nelbo_with_gen_steps` take a per-sequence gen-step source `(seq_len, tokens, rng) -> Vec<u32>` — the Issue-813 ask, generalized to what the arms actually need (per-sequence lengths, the MDLM endpoint, tokens-aware confidence ordering). `SetCausalGenStepsFn` is the type alias. The incumbent signatures are unchanged delegating wrappers (byte-identical — G1).
2. **The arms**: uniform w=1 (`PositionOffsetSchedule::diffusion`), sw-default w=0.5 (incumbent), ar (`ar_order`), mdlm all-at-once (`mdlm_gen_steps`, degenerate calibration floor), and **prob-t\*** — the new arm: teacher-forced confidence (train-derived Laplace-smoothed empirical bigram law via `dllm::text_corpus`) → `probability_order` → t\*-gate (`commit_time_star(V, σ=1, a=1)`): the top-`⌈t*·L⌉` most-confident positions reveal first in confidence order; the tail keeps the schedule's uniform shape. Both `probability_order` and `commit_time_star` are CONSUMED from katgpt-core (substrate-first acceptance) — which also landed the root `ignition_schedule` forward feature.
3. **Root feature**: `ignition_schedule = ["katgpt-core/ignition_schedule"]` (pure dependency forward, opt-in; unique-flag count unchanged at 614 — count_features green).

## G1 — seam byte-identity (PASS)

Markov V=8 L=8, 300 epochs, seed 42: incumbent `train_mini_set_causal` vs the gen-steps core with an equivalent schedule closure — **loss histories bitwise equal**; eval NELBO bitwise equal across all three entry-point pairings (legacy weights vs seam weights; schedule entry vs closure entry). The wrapper draws the same `seq_len` uniforms in the same order — the pre-seam rng stream is preserved exactly.

## G2 — t\*-gate mechanism (PASS)

Deterministic synthetic law, fixed sequence: the front set is exactly the top-`⌈t*·8⌉ = 6` confidence positions (`t*(8) = 0.671`), and the argmax-confidence position gets gen-step 0.

## G3 — Cell A, the Research-376 Markov lane (PASS, saturated)

300 epochs, seed 42, release, i7-13700K:

| arm | train[0] | train[-1] | eval NELBO | wall_ms |
|---|---|---|---|---|
| uniform w=1 (mdlm order) | 0.8119 | 0.0000 | 0.0000 | 580 |
| sw-default w=0.5 (incumbent) | 0.8848 | 0.0000 | 0.0001 | 560 |
| ar (exact) | 0.6015 | 0.0000 | 0.0001 | 532 |
| mdlm all-at-once (degenerate) | 0.6745 | 0.0000 | 0.0002 | 580 |
| prob-t\* (new) | 0.7467 | 0.0000 | 0.0002 | 587 |

chance = ln 8 = 2.0794 · t\* = 0.6710. **Every arm masters the deterministic chain** — confidence ordering carries no signal when every position is perfectly predictable from its predecessor (the Plan-600-T8 saturation class).

## G4 — Cell B, the Plan-601 real-text lane (PASS, and the mechanism finding)

Austen char-level, `micro_dllm_text`, 2048 train / 512 held-out eval blocks, 40 epochs, seed 42, release:

| arm | train[0] | train[-1] | eval NELBO | wall_ms |
|---|---|---|---|---|
| uniform w=1 (mdlm order) | 0.0343 | 0.0000 | 0.0000 | 3379 |
| sw-default w=0.5 (incumbent) | 0.0341 | 0.0000 | 0.0000 | 3330 |
| ar (exact) | 0.0334 | 0.0000 | 0.0002 | 3201 |
| mdlm all-at-once (degenerate) | 0.0315 | 0.0000 | 0.0000 | 3355 |
| prob-t\* (new) | 0.0328 | 0.0000 | 0.0000 | 3329 |

chance = ln 32 = 3.4657 · t\* = 0.7247. **train[0] ≈ 0.034 nats at epoch 0 — already ~100× better than chance**, and every arm converges to ~0 by epoch 40. The ordering axis cannot separate because the objective is self-copy trivial. Two-layer mechanism, both measured: (1) self is always attention-eligible (`gen_step[t] <= gen_step[q]`); (2) — the deeper layer — the residual stream carries `wte[token_q]` back to the logits in Phase C, so even a strict-self attention variant leaves the leak intact (a strict-self implementation was built, measured insufficient at ~0.00001 across all arms, and REVERTED rather than shipped speculative). The fix is the masked-target objective → Issue 816 (resolved same day), Addendum I below.

## Addendum I — the denoiser cell (Issue 816 resolved): the ordering axis SEPARATES

The masked-target fix: corrupt at `mask_ratio = 0.5` (`corrupt_block_into`), run the INCUMBENT set-causal forward over the corrupted input, take the loss over MASKED positions only — a masked position's residual carries `wte[mask_token]`, not the answer, so the copy path is closed by construction. New API under `set_diffusion`: `train_mini_set_causal_denoiser_with_gen_steps` / `evaluate_set_causal_denoiser_nll_with_gen_steps` (no kernel/ctx/backward change).

Cell B-denoiser — real-text (2048 train / 512 eval blocks, 40 epochs, seed 42, release):

| arm | train[0] | train[-1] | eval@seed+1k | eval@seed+2k | wall_ms |
|---|---|---|---|---|---|
| uniform w=1 (mdlm order) | 3.0272 | 2.8863 | 2.8913 | 2.8779 | 2745 |
| sw-default w=0.5 (incumbent) | 3.0269 | 2.8784 | 2.8932 | 2.8724 | 2662 |
| ar (exact) | 3.0025 | 2.7096 | 2.7128 | 2.7436 | 2671 |
| mdlm all-at-once | 3.0066 | 2.7988 | 2.8135 | 2.8554 | 2700 |
| **prob-t\*** | 2.8455 | 2.5966 | **2.5946** | **2.6079** | 2751 |

chance = ln 32 = 3.4657 · unigram floor (no context) = 2.8884 nats · t\* = 0.7247.

**Measured verdicts (all pinned by `g5_denoiser_realtext_table`):**

1. **The DBTM separation holds: prob-t\* wins the table on BOTH eval seeds** — −0.30 nats vs uniform (≈10%), −0.12 vs the second-best arm (ar). Confidence-ordered reveal front-loads predictable positions and hands the hard positions the most context — the Research 563 §4.3 Thm 4.1 direction, measured green on the leak-free objective.
2. **uniform ≈ sw-default ≈ the no-context floor** (2.87–2.89 vs floor 2.8884): random orderings give masked positions nearly useless context at L=9 / mask 0.5. Sitting AT the floor is the honest result for these arms, not a failure.
3. **mdlm is NOT a ceiling** — 2.81/2.86, beaten by ar: half its attended context is mask noise. The "full context = best" assumption was wrong, as was the clean-token cell's "degenerate floor" reading; both of the test file's own earlier comments were corrected to the measured truth.
4. **Leakage guard**: any arm reading near-zero NLL means the loss set leaked back into copy; any arm meaningfully WORSE than the floor means the ordering is actively harmful. Both fire the gate.

**Honest scope**: one corpus (Austen char), one block length (9), one mask ratio (0.5), one training seed — a measured direction on the lane's protocol, not a law. No promotion: nothing in this lane is a decode default; the anchor-then-fill seam's `ConfidenceAnchorConfig::default()` is untouched. A harder-corpus / longer-context re-gate follows the Plan-601 demote-on-loss pattern if promotion is ever on the table.

## Honest-scope notes

- The MDLM all-at-once row is recorded as the degenerate identity-copy calibration floor, never a quality claim (its "win" in Cell B epoch-0 is the copy leak at maximum, not quality).
- Eval rng: same starting seed per arm, different consumption by construction (deterministic arms draw none; sampled arms draw per reveal) — the mean over 512 blocks is the comparable quantity, not per-draw streams.
- No promotion claim, no default-path change: the seam is additive API under the existing `set_diffusion` feature; the `ignition_schedule` root forward is a pure dependency forward with no src/ consumer yet (documented in the feature comment).
- Environment: Windows 11, i7-13700K (16 cores), release profile, exclusive of GPU work (CPU-only lane); no other cargo build held the target dir.
