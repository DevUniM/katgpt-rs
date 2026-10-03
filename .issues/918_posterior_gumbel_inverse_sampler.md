# Issue 918 — Posterior-Gumbel inverse sampler (max-first, exact) + residual-ordering property test

**Status:** Open — POC, small (≈200 LOC + tests); execution-class against a cited lineage, ZERO novelty claims.

**Source:** arXiv:2610.00497 "Gumbel Straight Flow" (DeepMind, 2026-09-30) — modelless extraction (riir-train Research 466 §3, No-GD advocate rows 3+5; revised per verdict round 1). The posterior construction is **Zhang et al. 2026** ("Gumbel distillation for parallel text generation", cited in-paper); the trick is Gumbel 1954; the OT identification is implicit in Galichon 2016 (all credited in-paper).

## What

Two additions to the existing `ac_prefix` Gumbel substrate (`keyed_gumbel_max_sample` etc., Plan-614 row):

1. **Posterior (truncated-Gumbel) inverse sampler — MAX-FIRST construction.** Given logits `ℓ` and a realized pick `y`, sample `ξ*` from the exact posterior `p(ξ | argmax(ℓ+ξ) = y)`:
   - `LSE = logsumexp(ℓ)`; `M ~ Gumbel(LSE)` (the max is Gumbel with that location; under the Gumbel-max representation `M` and the winner index are INDEPENDENT).
   - `ξ*_y = M − ℓ_y` (the winner's noise is pinned so `ℓ_y + ξ*_y = M`).
   - Each loser `k ≠ y`: `ξ*_k ~ Gumbel truncated ABOVE at M − ℓ_k` (so `ℓ_k + ξ*_k < M`), via the inverse CDF `ξ*_k = −log(−log(u · F(M − ℓ_k)))`, `F(t) = e^(−e^(−t))`, `u ~ U(0,1)` — coordinates conditionally independent given the max (Zhang 2026; arXiv:2610.00497 App E).
   - O(V), one exp/log pair per loser. **Do NOT draw losers freely and pin the winner above their max** — that reproduces the pick but is a BIASED coupling (loser marginals lack the truncation tilt), which would corrupt the straightness property if consumed by the GSF training coupling.
   **Consumer (honest):** the GSF training coupling in riir-train plan 437 Phase 1b/4b — teacher-forced picks whose sampling seed is unknown (the noise must be reconstructed FROM the outcome). NOT a replay/audit tool for our own keyed sampler: `keyed_gumbel_noise(seed, position, token)` is a pure function of its key, so a recorded seed already replays exactly, and a posterior sample is *a* consistent noise, never *the* noise used. katgpt-rs ships it as the upstream primitive riir-train consumes.
2. **Residual-ordering property test** (Theorem 1's actual mechanism, arXiv:2610.00497 App A.1): for two coupled pairs (same logits) with distinct winners `k1 ≠ k2`, `ξ¹_k1 − ξ²_k1 > ξ¹_k2 − ξ²_k2` holds DETERMINISTICALLY. Note: a literal path-intersection test CANNOT discriminate — in ℝ^V (V≥3) two interpolants cross only if `x0¹−x0² ∥ e_k2−e_k1`, a measure-zero event for continuous noise whether or not the pairs are coupled. The inequality is the falsifiable form: coupled draws → 0 violations over ~10⁴ pairs; decoupled control (independent noise) → violations at ~50% — a red arm that actually fires.

## Gates

- G1 (bit): `argmax(ℓ + ξ*) == y` on 100% of fixture picks; red-arm: wrong logits must break the identity.
- G1b (joint distribution — replaces any marginal-only check): draw `ξ ~` prior, REJECTION-FILTER to `argmax(ℓ+ξ) = y`, and require the sampler's winner AND loser coordinate marginals to match the filtered-prior marginals (KS + moment checks on both groups). Red arm: the free-loser-then-pin construction must FAIL the loser-marginal check — the gate must be able to catch the biased coupling.
- G2 (perf): O(V) single pass; bench vs `keyed_gumbel_max_sample` — same order, ns-class.
- G4 (alloc): zero-alloc on the hot path, fixed buffers, `ac_prefix` conventions.
- Residual-ordering discrimination gate: coupled → 0 violations; decoupled → violations present (assert the count is far from 0, not merely nonzero).

## Out of scope (recorded, no file)

- Gaussianized-prior transform `f(ξ) = Φ⁻¹(exp(−e^(−ξ)))` and the Pe(t) time-warp table — no live consumer outside GSF training (riir-train plan 437 owns that side).
- Flow-map anything — training-track, riir-train's.
- Any "audit forensics / bit-exact reconstruction of past picks" claim — retracted in verdict round 1: our keyed sampler needs no posterior for replay (seed is recorded), and a posterior draw is not the original noise.

**Cross-refs:** riir-train `.research/466_Gumbel_Straight_Flow_AR_Flow_Map_Distill.md` (the distill note) · riir-train `.plans/437` Phase 1b/4b (the training-side CONSUMER of the posterior sampler).
