# Bench 764: `slt` — singular learning theory selection primitive (Issue 781 / Research 558) GOAT

**Status:** PASS — G1–G4 + UQ floor gate ALL PASS; PROMOTED to default-on (the BMR/Plan 597 precedent: pure closed-form math, zero deps, no interaction surface).

**Date:** 2026-09-15 · **Lane:** `cargo test -p katgpt-core --features slt --lib slt` (12 tests) + the release/allocTracking + default-floor + `--all-features` check lanes.

## What shipped

Five closed-form functions + one derived helper in `katgpt-core::slt` (feature `slt = []`, zero deps, `f64` log-domain, `#[must_use]`):

| Primitive | Formula | GOAT evidence |
|---|---|---|
| `rlct_reduced_rank(a,b,r)` | `λ(r) = r(a+b−r)/2` (Aoyagi–Watanabe 2005) | full-rank limit `r=min(a,b) ⇒ ab/2` exact; monotone in r; `≤ ab/2` and `≤ r(a+b)/2` ceilings; oversized-rank clamp |
| `wbic(n,L,λ)` | `nL + λ·log n` (Watanabe 2013) | the G1 recovery cell below |
| `free_energy(n,L,λ,m)` | `nL + λ·log n − (m−1)·loglog n` | splits exactly into WBIC + multiplicity; `m=1 ⇒ ≡ WBIC` |
| `bayes_gap(λ,n)` | `λ/n` (the **Bayes-predictive** gap law) | the floor gate below |
| `sigmoid_wbic_weight(a,b,τ)` | `σ(−ΔWBIC/τ)` | antisymmetric pairwise sigmoid (w+w′=1), τ→∞ ⇒ 0.5, τ→0⁺ ⇒ step |
| `bic_overpenalty_nats(n,a,b,r)` | `r²/2·log n` (the gauge orbit) | exact at every rank incl. full (a factorized full-rank matrix still carries the GL(r) orbit) |

## G1 — planted-rank recovery (the headline)

Synthetic reduced-rank regression, a=b=8, n=2000, σ=0.5, seeded xorshift64\* + Box-Muller; rank-k fits = SVD truncation of the cross-covariance estimator `C = (1/n)Σ y xᵀ` (test-only symmetric Jacobi eigensolver on `CᵀC` — the shipped `thin_svd_into` is feature-gated elsewhere; the module is zero-dep by contract). **Loss convention (load-bearing): per-SAMPLE nats `0.5·Σ_dims(r²)/σ²` — λ prices the full a×b manifold; a per-dim average shrinks every gain by 1/a and collapses the selection margins (the first draft's failure mode, kept as this note).**

- **Cell A (strong ladder 1.5..1.0, r\*=6):** raw loss picks 8 (=r_max, monotone — the failure mode); **WBIC picks 6** ✓; naive-parameter BIC also picks 6 (over-count too small to bite at full strength).
- **Cell B (marginal 6th direction, s₆=0.075):** raw loss 8; **WBIC picks 6** ✓ (realized gain ≈ 24 nats > Δλ·ln n ≈ 19); **naive BIC picks 5** ✓ (its `r²/2·ln n` gauge over-count raises the bar to ≈ 30 nats — the over-penalization the issue specified, measured).

## G2 — selection is O(k), µs-class

1_000 full k=1..=8 selections (WBIC + argmin over the ladder): well under the 1 ms/iter ceiling (measured ~sub-µs; the per-candidate cost is a handful of float ops). PASS.

## G3 — no regression

Default-feature lib suite **2041 passed / 7 ignored** — count-identical to the pinned `test_gate.sh` floor (katgpt-core:2041, raised 2026-09-13). Post-promotion the floor moves to 2053 (+12 slt tests) in the same commit. `cargo check -p katgpt-core --all-features` clean.

## G4 — alloc-free, release-verified

`rlct_reduced_rank` + `wbic` + `free_energy` + `bayes_gap` + `sigmoid_wbic_weight` + `bic_overpenalty_nats` + a selection loop: **0 allocations** under the counting allocator, `--release --features slt,alloc_tracking` (the Issue-741 profile-free predicate). PASS.

## UQ floor gate (T3 / R558 §7) — PASS, thin margin recorded honestly

The `bayes_gap` λ/n predictor vs the incumbent floor `d/2n` (BIC's own gap prediction on the naive parameter count of the SELECTED rank) and constant-gap baselines, on the **WBIC-mixture predictor's** realized train→test gap (the λ/n law prices the Bayes-predictive gap — a point fit realizes C/n, C=2λ for this family; scoring a point fit would be the category error the module doc warns about). 3 families × n ∈ {250,500,1000,2000} × 12 reps; identical scoring machinery across arms (per-cell realized-gap spread s, central 95% intervals) so the comparison isolates the CENTER; Bradley-Terry mixture weights composed from PAIRWISE `sigmoid_wbic_weight` (σ(−ΔWBIC/τ), τ=10 nats — sigmoid, never softmax):

| arm | CRPS/s ↓ | Winkler/s ↓ | coverage |
|---|---|---|---|
| **bayes_gap (λ/n)** | **0.598** | **4.529** | **0.972** |
| bic_floor (d/2n) | 0.604 | 4.670 | 0.972 |
| const 1e-3 | 0.644 | 4.664 | 0.917 |
| const 1e-2 | 0.632 | 4.630 | 0.931 |
| const 1e-1 | 0.825 | 7.905 | 0.861 |

**bayes_gap beats the floor and every constant on CRPS + Winkler at equal coverage.** Margin over the floor is THIN (~1%) at these family scales (a=b=8, λ ≈ 14–30 — the gauge over-count r²/2 is small against λ); the margin widens with the r/k\* ratio. Recorded so a future re-gate at larger ranks has a baseline.

## T0 — novelty gate on the noise-sweep λ̂ estimator: **KEEP** (with a caveat)

Two targeted searches (2026-09-15) + the LLC-estimation survey (Emergent Mind, updated 2025-10-15): every published λ̂ route is SGLD/tempered-posterior (arXiv:2308.12108, 2402.03698→merged, 2507.21449), exact-algebraic 2-D (2608.20183), or linear-response (2605.07970) — **no Gaussian-perturbation V(t) power-law route published**. Caveat on record: the estimator FORM `λ̂ = m/Σ ln(u_max/uⱼ)` is the classical Hill estimator (1975) — the novelty is the APPLICATION (loss-deficit ratios under frozen-weight noise → λ), not the statistics. T4 (the estimator + its calibration ladder: quadratic bowl ⇒ d/2, planted RRR ⇒ r(a+b−r)/2, ReLU toy ⇒ ≈0.53) stays `- [-]` deferred as its own unit, unblocked by this verdict.

## Verdict

- **PROMOTED to default-on** (`slt` joins the default list; 201 → 202 default-on, 602 → 603 total flags). The demotion clause found no loser: raw-loss selection picked r_max in both cells (WBIC strictly dominates — no tying lane).
- λ is a freeze/consolidation-seam scalar (R558 §5) — never a per-tick signal; nothing joins a hot path.
- Consumer wiring (T6) filed in the consumer repos: riir-ai (freeze/thaw WBIC tie-break + sigmoid mixture weights) + riir-neuron-db (free-energy cross-n ledger in Raven/δ-Mem merge/keep ranking).

## Reproduce

```sh
cargo test -p katgpt-core --features slt --lib slt -- --nocapture   # 12 tests incl. both G1 cells + the floor gate table
cargo test -p katgpt-core --release --features slt,alloc_tracking --lib slt   # G4 in the shipping profile
cargo test -p katgpt-core --lib                                  # post-promotion: 2053 (floor bumped in test_gate.sh)
```
