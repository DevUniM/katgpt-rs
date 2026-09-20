# Bench 844 — `exact_sigmoid` / `exact_sigmoid_f64` / `dot_f32_ordered` substrate promotion (riir-chain Issue 156 T1)

**Date:** 2026-09-20
**Verdict:** **PASS — G1a/G1b/G1c all green** (release profile). G2 timings REPORTED, not barred — the claim this bench exists for is exactness and determinism, not speed.

## What landed

Three ungated pure-math primitives (the `float_order` precedent: additive API, pure math, no existing call site rerouted, always compiled):

| Primitive | Home | Contract |
|---|---|---|
| `exact_sigmoid(f32)` | `katgpt-types/src/simd/activations.rs` → re-exported `katgpt_core::exact_sigmoid` | two-branch numerically stable form over libm `exp`; no Cephes polynomial, no ±40 saturation clamp |
| `exact_sigmoid_f64(f64)` | same | same form in f64 — for callers that compute in f64 and narrow to f32 only at the end |
| `dot_f32_ordered(&[f32], &[f32])` | `katgpt-types/src/simd/dot.rs` → `katgpt_core::simd::dot_f32_ordered` | sequential index-order fold, plain mul/add — no SIMD lane reassociation, no FMA contraction (Rust does not reassociate float adds without fast-math, so the fold is deterministic by construction) |

`katgpt_core::sigmoid`'s doc now names the exact variant (the name a new caller reaches for silently returns the approximation — that trap is closed).

## Why (the promotion trigger)

riir-chain Issue 156's substrate-first audit found the consensus/curator layer hand-rolls the exact two-branch sigmoid (twice in-repo) and a scalar ordered dot, because the substrate's only sigmoid (`fast_sigmoid`) is an approximation. Delegation was blocked on "no byte-identical target in the substrate" — this promotion creates the target.

Multi-copy evidence (R4 of the Issue-156 adjudication): the exact two-branch shape ships in **≥5 katgpt-rs src sites across 5 files** (`katgpt-core/src/salience/gate.rs:580` f32, `breakeven/mod.rs:256` f64, `refinement_marginal.rs:357`, `ugc_schedule.rs:103`, `successor_density_critic.rs:584+1055`) plus riir-chain's three sites. Refactoring those in-repo copies to consume the new primitive is a recorded follow-up, deliberately NOT in this unit (one of them landed hours ago in another session's lane).

## Gates

| Gate | Result | Detail |
|---|---|---|
| G1a f32 exactness | ✓ | exact max **2 ULP** / 5.96e-8 abs vs the f64-computed-and-narrowed reference over [-80, 80] step 0.0137 + edges (pin ≤ 4 ULP, measured 2; unit test pins ≤ 2 over [-90, 90] incl. the subnormal tail — held). Contrast: `fast_sigmoid` max **580,601,137 ULP** on the same grid — dominated by the ±40 clamp region, where `fast_sigmoid` returns exactly 0.0/1.0 and the true value is a representable tiny (σ(-50) = 1.9e-22). ⚠ the ABS-error column does NOT separate the variants (both read ~5.96e-8 max abs) — the ULP metric is the load-bearing one, because the clamp error lives in the far tail where absolute values are negligible |
| G1b f64 properties | ✓ | reflection `σ(x)+σ(-x)=1` within 1 ULP at 1.0 over [-50, 50]; monotone non-decreasing; exact bounds at 0 / ±∞ / NaN / ±800 / the ±40 boundary. No ULP gate for f64 — the implementation IS f64 libm, so a "≤1 ULP vs libm" oracle would be circular (verdict R2) |
| G1b f32 bounds | ✓ | 0.5 exactly at 0; ±∞; NaN propagates; the far tail is representable-and-nonzero (`exact_sigmoid(-50) ∈ (0, 1e-17)`) — the value difference vs `fast_sigmoid`'s clamp |
| G1c ordered-dot pins | ✓ | frozen sequential value 1.0 on the cancellation input `[1e8, 1.0, -1e8, 1.0]` (hand-computed: `1e8+1` loses the +1 to f32 spacing 8 at 1e8); `simd_dot_f32` on the same input reads 0 (reassociated lanes pair {1e8,−1e8} and {1,1}) — the anti-dedup pin. Every backend reassociates (NEON/AVX2/wasm-simd128 lanes, or the 4-accumulator + `mul_add` scalar fallback), so the inequality is target-independent |
| G2 perf | REPORTED | best-of-50 minimum, M3 Max (see box state): `fast_sigmoid` 3.1 ns · `exact_sigmoid` **1.7 ns** · `exact_sigmoid_f64` 2.8 ns · `simd_dot`@1024 52.9 ns · `dot_f32_ordered`@1024 **657.9 ns** (12.4× the SIMD kernel — the committed-value premium; inference kernels keep `simd_dot_f32`) |
| G3 no-regression | ✓ by construction | additive only; no existing call site rerouted; `fast_sigmoid`/`simd_dot_f32` untouched; the full katgpt-types + katgpt-core suites re-ran green at default features |
| G4 alloc-free | ✓ by inspection | pure stack math; no allocation path exists in any body, so no allocator arm is wired |

## Honest notes

- **The Cephes speed claim inverts on this arch.** `fast_sigmoid`'s doc says "~1.7× faster than libm on aarch64"; measured here, the libm two-branch exact form is ~1.8× FASTER than the Cephes polynomial (1.7 vs 3.1 ns) on this grid. Neither number is a promotion bar — the variant split is about exactness, not speed — but the doc's perf claim should not be quoted on aarch64 without re-measuring. (Probable cause of the original claim's box is x86_64; not re-measured there here.)
- The G1a pin is `≤ 4 ULP` with the unit-test gate at `≤ 2 ULP` (measured 2 on both grids, including the subnormal tail) — both are measured-with-headroom pins, not invented constants.
- The dot pin (`ordered != simd`) reds the day a backend converges with the sequential fold — that is its job (verdict R3: without it, a future "dedup" collapses the kernels silently).

## Box state (the rule: a latency number without its box state is not a measurement)

M3 Max (aarch64, macOS), AC power, **loaded box** — sibling agent sessions running release cargo builds concurrently (CPU ~99% at session start); no GPU consumer in this lane (CPU-only math). `CARGO_TARGET_DIR=/tmp/katgpt-156-t1` (sibling-build isolation). Timings are best-of-50 minima, so the load can only have inflated them; treat every G2 number as an upper bound.

## Consumers

- riir-chain (Issue 156 T2): `curator_bridge::{sigmoid, dot_product}` and `forensic/recover::sigmoid` delegate to these fns behind a bit-identity pin that carries copies of the legacy bodies (verdict R5). `consensus/congestion::inclusion_probability` is deliberately NOT delegated — its `x < 0` domain is reachable three ways through `pub` inputs (negative stake, negative trust, negative `lambda`), and the two-branch form differs from the shipped inline form on that domain; a consensus-path numerics change is its own decision, not a side effect of dedup (verdict R1, refused-and-recorded).

## Follow-up executed (2026-09-21, Issue 861)

The ≥5 in-repo copies were delegated in the recorded follow-up:
`salience/gate.rs::sigmoid`, `breakeven/mod.rs::sigmoid` (f64),
`refinement_marginal::escalation_sigmoid`, `ugc_schedule::inv_log_reveal_odds`,
and `successor_density_critic::p_successor` (the f64-compute-then-narrow shape)
now all consume `crate::exact_sigmoid`/`exact_sigmoid_f64`. Bit-identical by
construction (expression-identical bodies); validated per the
feature-aware law — clippy + module tests at default AND at
`breakeven_routing,refinement_marginal,successor_density_critic` — full
default-feature lib suite 2063/2063. The link-identity TEST copy at
`successor_density_critic.rs:1055` deliberately STAYS inline: it is the
independent oracle for its assert, and delegating it would make the test
circular. `salience/gate.rs`'s stale TODO ("hoist to `fast_sigmoid` when the
SIMD dispatcher lands") is gone — it named the approximation as the target.

## Re-run

```bash
cargo bench -p katgpt-core --bench bench_844_exact_sigmoid_ordered_dot
cargo test -p katgpt-types --lib exact_sigmoid
cargo test -p katgpt-types --lib ordered_dot
```
