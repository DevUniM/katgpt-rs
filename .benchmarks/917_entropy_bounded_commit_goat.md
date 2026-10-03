# Bench 917 — EB-Sampler-class entropy-bounded commit: modelless oracle A/B

**Status:** MEASURED 2026-10-03 — oracle-lane PASS (G1 no-stall, G2 vs fixed-k and vs the floored τ incumbent, G3 validity); the LANE verdict (D2F / DDTree / DFlash, Issue 917 T2/T3) is still OPEN and blocked on a trained diffusion checkpoint. Not a promotion basis on its own.

**Owner:** Issue 917 (T1 primitive `katgpt-core/src/entropy_bounded_commit.rs`, feature `entropy_bounded_commit`).
**Target:** `crates/katgpt-core/tests/bench_917_entropy_bounded_commit_goat.rs` (deterministic, seeded, no timing — every number below is a reproducible count).

```sh
cargo test -p katgpt-core --features entropy_bounded_commit \
  --test bench_917_entropy_bounded_commit_goat --release -- --nocapture
```

## Why an oracle, and what it can and cannot say

The lane gate wants NFE at matched quality on a real diffusion decode. The only in-workspace D2F lane (riir-infer `gemma2_d2f`) has no trained checkpoint — its own quality assertion is gated on `D2F_GOAT_TRAINED=1` — so an A/B there on random weights measures nothing. The oracle makes quality DECIDABLE instead: the target is uniform over a finite valid set `S`, the denoiser returns the exact conditional marginals `p(x_i | revealed)`, every pass samples masked positions independently (the factorized proposal every MDM/D2F commit uses), and a policy picks which samples to commit. A final string outside `S` is exactly the joint-dependence error the EB bound is about. Fixed `k = 1` is exact sequential sampling (validity 1.0 at NFE = L) — the reference.

It cannot say how the γ dial behaves on a real LM's entropy profile, nor what a real denoiser's miscalibration does to the bound. That is T2/T3's job.

## Families (L = 16, V = 8, 2000 runs per row)

- **RANDOM** — `|S| = 32` random strings: every position depends on every other.
- **HALVES** — `S = A × B`, two independent halves of 8 strings each (`|S| = 64`).
- **PEAKED-INDEP** — independent positions, each 0.9 / 0.1 over two tokens (closed form, `|S| = 2^16`): the case where `Σ H − max H` is loosest, because it charges for dependence that does not exist.

## Result (support seeds 917 / 9170 / 91700)

| policy | RANDOM validity | NFE | HALVES validity | NFE | PEAKED validity | NFE |
|---|---|---|---|---|---|---|
| EB γ=0 | 1.0000 | 3.88 | 1.0000 | 5.76 | 1.0000 | 16.00 |
| EB γ=0.1 | 1.0000 | 3.88 | 1.0000 | 5.76 | 1.0000 | 16.00 |
| EB γ=0.3 | 1.0000 | 3.88 | 1.0000 | 5.76 | 1.0000 | 16.00 |
| EB γ=1 | 0.6385 | 3.54 | 0.5815 | 3.99 | 1.0000 | 4.00 |
| fixed k=1 | 1.0000 | 16.00 | 1.0000 | 16.00 | 1.0000 | 16.00 |
| fixed k=2 | 0.5415 | 5.27 | 0.6070 | 7.11 | 1.0000 | 8.00 |
| fixed k=4 | 0.0240 | 2.05 | 0.1075 | 2.57 | 1.0000 | 4.00 |
| fixed k=8 | 0.0000 | 2.00 | 0.0010 | 2.00 | 1.0000 | 2.00 |
| τ=0.5 (D2F, no floor) | 0.0000 | 64 (2000 stalls) | 0.1020 | 20.52 (592 stalls) | 1.0000 | 1.00 |
| τ=0.5 + floor | 0.2250 | 2.99 | 0.2040 | 2.76 | 1.0000 | 1.00 |
| τ=0.9 (D2F, no floor) | 0.0000 | 64 (2000 stalls) | 0.0000 | 64 (2000 stalls) | 1.0000 | 1.00 |
| τ=0.9 + floor | 1.0000 | 4.34 | 1.0000 | 7.18 | 1.0000 | 1.00 |

EB vs the FAIR incumbent (τ = 0.9 with the singleton floor) across three independent support draws per family — all at validity 1.000:

| family | seed | EB γ=0.1 NFE | τ=0.9+floor NFE | EB saving | shipped-D2F τ stalls |
|---|---|---|---|---|---|
| RANDOM | 917 | 3.84 | 4.27 | 10% | 2000/2000 |
| HALVES | 917 | 5.74 | 7.07 | 19% | 2000/2000 |
| RANDOM | 918 | 4.27 | 4.51 | 5% | 2000/2000 |
| HALVES | 918 | 5.25 | 6.46 | 19% | 2000/2000 |
| RANDOM | 919 | 4.02 | 4.56 | 12% | 2000/2000 |
| HALVES | 919 | 5.49 | 6.32 | 13% | 2000/2000 |

## Reading

- **vs fixed-k the gain is large and not the interesting number.** No fixed k > 1 keeps validity ≥ 0.99 on the dependent families, so the best fixed-k at matched quality is k = 1 (16 NFE) against EB's 3.9 / 5.8. Fixed-k is not what D2F ships.
- **vs the incumbent it is modest: 5–19% fewer NFE at equal validity**, and only once the incumbent is given a floor it does not have. The shipped D2F τ rule (no floor) stalls on every run at τ = 0.9 and on 592/2000 HALVES runs at τ = 0.5 — the no-stall property, not the NFE ratio, is the larger practical difference on a flat canvas.
- **The γ dial is flat on these families over [0, 0.3]**: entropy falls from ~ln 8 to 0 within a few reveals, so no prefix ever sits near the budget. γ = 1 crosses into the regime where two uncertain positions are committed together and validity collapses (0.64 / 0.58). A family with graded dependence would exercise the dial; these do not, and the record does not claim it is calibrated.
- **The bound's cost is real (PEAKED-INDEP)**: with genuinely independent positions EB at γ ≤ 0.3 commits one position per pass (16 NFE — two positions at 0.325 nats each already exceed γ) while τ commits everything in 1. `Σ H − max H` upper-bounds the mutual information and is loose exactly when positions are independent. A real LM canvas mixes both regimes; which one dominates is a lane question.

## Gates in the target

- `bench_917_eb_commit_oracle_ab`: k = 1 exact on every family; EB never stalls at any γ on any family; on RANDOM and HALVES, EB γ = 0.1 validity ≥ 0.99 and NFE < every fixed-k row reaching ≥ 0.99; PEAKED reported, validity asserted.
- `bench_917_eb_vs_floored_tau_across_seeds`: on 3 seeds × {RANDOM, HALVES}, EB validity ≥ τ+floor validity − 0.005 and EB NFE strictly below τ+floor NFE.

## Next

Issue 917 T2/T3 (lane wiring) and the lane G2/G3 need a trained D2F checkpoint (riir-train) or a drafter lane with a real model; the PEAKED-INDEP cost says the lane A/B must report the per-pass commit count distribution, not just mean NFE.
