# Bench 759: SSMax HoldConcentration + Kamath logit-regime detector — Issue 762 T4.1/T4.2 GOAT Gate

> **Features:** `ssmax_temperature` (default-on module; the new variant follows the `SsmaxMode::Adaptive` precedent) + `logit_regime` (katgpt-core) — **OPT-IN** (no-default-consumer rule)
> **Source:** Issue 762 T4.1/T4.2 · Research 549 (ASEntmax, arXiv length-adaptive α-entmax) — Lemma 2's softmax side + the Kamath 2015 range law via the Research-549 §2.2 duality table
> **Date:** 2026-09-13
> **Gate:** `cargo bench -p katgpt-core --features logit_regime --bench bench_759_logit_regime_goat` (bench profile, M3, loaded box — see G2)
> **Companion tests:** 30 ssmax lib tests (6 new HoldConcentration, default build) + 6 logit_regime lib tests (gated)

## Verdict: GOAT G1 + G2 + G4 ALL PASS — logit_regime ships OPT-IN; HoldConcentration ships in the default-on ssmax module

```
================ GOAT VERDICT ================
  [PASS] G1a HoldConcentration exactness — all thresholds hold c
  [PASS] G1b logit_regime bands — bands + separation + bounds + determinism
  [PASS] G2 latency — worst ~34 µs/call (n=4096; 8.2–8.6 ns/elem)
  [PASS] G4 zero-alloc — 0 steady-state allocs
```

## T4.1 — `SsmaxMode::HoldConcentration { c, k, rolling_delta }`

The analytic coefficient from **Lemma 2's softmax side**: under two-level
logits the top-`k` hold softmax mass ≥ `c` iff `Δ ≥ ln((n−k)·c/(k·(1−c)))`.
The exact multiplier is that log-ratio over `Δ̂`; `resolve_s_l()` returns the
large-`n` limit `1/Δ̂` (identical to `Adaptive` — the finite-n correction
vanishes as `ln n` dominates); `multiplier(log_n)` reconstructs
`n = exp(log_n)` and returns the exact finite-n form; `SsmaxConfig::from_mode`
caches it exactly (bit-identical path for Fixed/Adaptive — pinned by
regression test). Degenerates (`k ≥ n`, `n ≤ 1`, `c ≤ k/n`, malformed `n`)
resolve to the identity multiplier; the s_L-equivalent is clamped `[0.1, 10]`
for parity with Adaptive's safety band (overshoot still holds `c` — the
contract is monotone in the multiplier).

**G1a measured** (two-level rows, Δ̂ = 0.5):

| n | k | c | multiplier | post top-k mass |
|---|---|---|---|---|
| 100 | 1 | 0.9 | 13.585 | 0.9000 |
| 1,000 | 1 | 0.9 | 18.208 | 0.9000 |
| 10,000 | 1 | 0.9 | 22.815 | 0.9000 |
| 10,000 | 8 | 0.75 | 16.457 | 0.7500 |

Exact at every scale (≤ 5e-3 of `c`). Latency **7–30 ns/call** (pure
arithmetic; bar 100 ns). Shipped **ungated-within-module** matching the
`Adaptive` variant precedent (zero cost unless constructed; the estimator
helper stays behind `ssmax_adaptive`).

## T4.2 — `logit_regime::{kamath_rho, normalized_entropy_nats, kamath_regime}`

The detector Bench 713's T0 σ̂-regime question left implicit: the range-law σ̂
estimate is **self-consistent by construction** (it IS the range divided by
the law) — only comparing it against an INDEPENDENT moment σ̂ makes a
detector. `ρ = Δ̂/(2σ̂√(2 ln n))`:

- **Gaussian band** `[0.35, 1.15]` measured at n = 64/256/1024 (the
  `√(2 ln n)` asymptotic overestimates `E[max]` at finite n — the band is
  honest, not a magic ≡1).
- **Spiked rows separate and grow with n**: ρ ≈ 1.95 → 3.4+ for a single
  planted needle at n = 128 → 2048, `spike_score > 0.6` everywhere.
- **Honest calibration pinned** (module doc + tests): a SINGLE outlier gives
  `ρ ≈ √n/(2√(2 ln n))` — INVARIANT to outlier magnitude (range and σ̂ both
  scale with it) — so realistic single-needle rows score 0.7–0.8, not →1;
  threshold 0.55–0.65 for "a spike exists"; the Gaussian band never exceeds
  ~0.54.
- **Normalized entropy** `H(p)/ln n` over the shared UNGATED
  `simd::logsumexp_parts` kernel (the same kernel
  `regime_probe::entropy::conditional_entropy_nats` wraps — one kernel shape,
  no gate chain onto `regime_probe`): uniform → 1, one-hot → 0 (both pinned).
- **Numerics**: the textbook two-pass moment algorithm (exact f64 sum, then
  squared deviations — no per-element Welford division, no Σx²−n·mean²
  cancellation); range computed in f64.
- **Degenerates are honest**: `n < 2` or constant rows → ρ = NaN, score 0.5
  (uninformed, never fabricated).

## G2 — latency (regression bar, not a speed record)

`kamath_regime` = 3 passes (moments ×2 + logsumexp): **8.2–8.6 ns/element**
at n = 1024 and 4096 (linear, no superlinear blowup). Bar ≤ 15 ns/element
(~2× headroom over the intrinsic scalar cost). Measured on a LOADED M3
(concurrent sibling compiles): run-to-run spread 30–48 µs at n=4096 — the
per-element bar is the load-tolerant form; an absolute-µs bar sits inside
machine noise. Rationale: offline-diagnostic cadence (cf. `gaussianity_probe`);
Bench 713 measured the raw entmax router at ~53 µs/row already at n≈173 —
the diagnostic stays cheaper than the operation it diagnoses.
`HoldConcentration::multiplier` 7–30 ns (arithmetic; bar 100 ns).

## G3 — no-regression

Default-build lib suite: **2041 passed / 0 failed** (includes the 24
pre-existing ssmax tests + 6 new HoldConcentration at default features —
`ssmax_temperature` is default-on, so the new variant's tests run in the
default lane). Fixed/Adaptive bit-identity through `from_mode` re-pinned by
`hold_concentration_config_caches_exact_form`.

## G4 — allocation

1000 × (kamath_regime + multiplier + normalized_entropy) @ n=1024:
**0 allocations** (CountingAllocator, per-thread). Zero-alloc by
construction — no `Vec`/`Box`/collecting iterator in the module.

## Substrate check (substrate-first skill, Mode 1)

Searched vocabulary variants before building: entropy (`data_probe/entropy.rs`
= kNN differential over point populations — different concern;
`regime_probe/entropy.rs` = the categorical kernel — CONSUMED via the shared
ungated `simd::logsumexp_parts`, avoiding the `regime_probe` gate chain);
Gaussianity (`data_probe/gaussianity.rs` = Cramér-Wold KS over n×d embedding
populations — representation health, not logit-row regime); range-law σ̂
(katgpt-attn `RollingSigmaEstimator` = the estimator, self-consistent by
construction — the DETECTOR needs the independent moment σ̂; that gap is this
module); gap estimators (`ssmax::RollingDeltaEstimator` = max−mean EMA — the
Δ̂ socket HoldConcentration consumes). No exhaustive `match` on `SsmaxMode`
anywhere in the workspace (adding the variant is additive).

## Standing

- `logit_regime` stays **opt-in** until a consumer GOAT-gates it onto a
  production path (candidate: the ASEntmax schedule's arm decision — ρ could
  gate "don't damp spiked rows" — plus the T0.1 equal-budget axis).
- HoldConcentration is available at default features (module default-on,
  Adaptive-variant precedent); no consumer wired (the SSMax hot path keeps
  its existing modes — a consumer comparison is future work).
- Issue 762 T4.3/T4.4 remain deferred per the T0 verdict (σ̂ saturates 0.35,
  the large-σ regime does not exist on real paths at n ≤ 173).
- T0.1 decided (owner, 2026-09-14): option (a) — `asentmax_schedule` stays
  opt-in; Issue 762 CLOSED with the equal-budget reopen condition recorded
  (Bench 713 long-context addendum; record: HISTORY.md). The `logit_regime`
  opt-in standing above is unchanged by the close.
