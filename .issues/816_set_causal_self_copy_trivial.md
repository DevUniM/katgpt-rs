# Issue 816: Set-causal clean-token objective is self-copy trivial — masked-target variant needed for any order-separation measurement

**Status:** FILED 2026-09-17 — measured in [Bench 809](../.benchmarks/809_set_causal_order_sweep.md) (the Issue 813 sweep arm — 813 RESOLVED same day, file removed per the noise rule, recoverable from git history). The seam + arm + tables LANDED; the separation instrument is blocked by the lane's objective, not by the ordering.
**Date:** 2026-09-17
**Blocking:** every reveal-ORDER comparison in the set-causal lane (the Plan-381 sweep's separation purpose; any future `probability_order` vs schedule claim)

## The measured finding

Bench 809 Cell B (real-text Austen, the Plan-601 corpus): **train[0] ≈ 0.034 nats at epoch 0** against chance 3.466 — the untrained model is already ~100× better than chance, and every arm (uniform / sw-default / ar / mdlm / prob-t\*) converges to ~0.0000 within 40 epochs. Cell A (the Markov fixture) is saturated the same way at 300 epochs. **No reveal order can separate at convergence.**

## The mechanism (read from the kernel, not inferred)

The set-causal eligibility predicate is `gen_step[t] <= gen_step[q]` — **self is always eligible** (`crates/katgpt-forward/src/forward_set_causal.rs`: "Position q itself is always eligible since position_order[q] <= q_gen_step"). Set-causal training feeds CLEAN tokens at every position (no corruption — `src/dllm/set_causal.rs`, the SW-SetDLM trainer), so every position's input includes its own token and the identity copy through self-attention + residual solves the all-L-conditionals objective for ANY ordering. The paper's variance-reduction semantics (predict x_σ(i) from x_σ(<i)) require the target NOT to be visible; this lane's trainer never hides it.

The MDLM all-at-once row (all gen-steps 0) is the same leak at its maximum: full context including self = pure copy floor (recorded in Bench 809 as the calibration row).

## The ask

A masked-target (or target-excluded) set-causal trainer variant — e.g. mask the query position's input token for the loss positions (the corruption machinery of `train_mini_dllm` / `corrupt_block_into` composed with the set-causal forward), or exclude self from the attention eligibility for the queried position — whichever keeps the existing clean-token trainer and its GOAT gate untouched (opt-in sibling, the Plan-600/813 discipline). Then re-run the Bench 809 arm table: only a non-copy-trivial objective can measure whether confidence-ordered reveal (Research 563 §4.3 Thm 4.1) actually separates.

## Notes

- The seam itself (Issue 813) is DONE and verified: G1 byte-identity + G2 t\*-gate mechanism green; the arms run and the tables are recorded.
- The existing GOAT gate (`test_goat_gate_set_causal_beats_bidirectional_at_sw_schedule`) compares TRAINING DISTRIBUTIONS on this same fixture — its tiny absolute margins are read through the same copy-trivial objective, which this issue documents as context, not as a challenge to its verdict.
- Modelless-first: the masked-target variant is a deterministic trainer change; no training-method dependency. The consumer is the Plan-381 lane (root crate).
