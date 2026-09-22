# Bench 871 — Rust 1.98 `algebraic_*` dot vs strict ordered-reduction dot: the A/B that decides the lane (Issue 871)

**Status:** RECORD — MEASURED 2026-09-22, 4090 box, both compile arms. **Verdict: algebraic wins
1.77×–8.8× (5/5 dims), accuracy IMPROVES vs strict, retention clean at fixture scale — promotion
NOT claimed (owner act).** The secondary finding is the load-bearing one: **the strict side is
scalar on x86_64-pc-windows-msvc** — the `dot_8wide` "auto-vectorizes on every target we ship"
claim does not hold on this target (Issue 871 Finding 2).

**Issue:** katgpt-rs Issue 871 · **Target:** `benches/bench_871_algebraic_dot_ab.rs`
(`cargo build --release --bench bench_871_algebraic_dot_ab`, then run the `deps/` binary; no
feature gate, no perf bar — the issue carries the verdict).

## Box state

4090 Windows workstation (katop box), **CPU-only** (f32 dot loops; GPU not involved).
rustc 1.98.1 (48a229cea, repo pin), x86_64-pc-windows-msvc. Baseline run: **6.7 GB free of
31.8 GB, ~36% CPU load (GUI background; Unity/Zed exempt per owner call — recorded, not
corrected), 0 concurrent cargo procs.** AVX2+FMA run: 6.4 GB free, ~30% CPU load. Both runs
post-build (no compiler concurrent). The ab_timing treatment (13 interleaved rounds,
median-of-ratios, per-round range printed) is the load-invariance defense; per-round ranges were
tight at every dim except d=64 baseline (0.29..0.60) and d=4096 baseline (0.13..0.65) — medians
quoted with that caveat.

## G2 — interleaved A/B (a = strict `dot_8wide` shape, b = algebraic twin; median b/a, < 1.0 ⇒ algebraic faster)

| d | SSE2 baseline ratio | ⇒ speedup | AVX2+FMA ratio | ⇒ speedup | strict ns/iter (base→avx2) | algebraic ns/iter (base→avx2) |
|---|---|---|---|---|---|---|
| 16 | 0.547 | 1.83× | 0.565 | 1.77× | 3.6 → 3.7 | 1.9 → 2.1 |
| 64 | 0.351 | 2.85× | 0.204 | 4.90× | 13.9 → 15.0 | 5.0 → 3.0 |
| 256 | 0.184 | 5.45× | 0.114 | 8.80× | 76.9 → 80.8 | 13.6 → 9.2 |
| 1024 | 0.218 | 4.59× | 0.141 | 7.09× | 450.6 → 375.6 | 96.3 → 52.9 |
| 4096 | 0.183 | 5.47× | 0.127 | 7.89× | 1587 → 1570 | 342 → 199.5 |

**The strict arm's time is flat across ISA arms** (1587 → 1570 ns at d=4096, within noise) — the
strict ordered reduction did not use the wider ISA at all. All of the AVX2+FMA gain accrues to
the algebraic arm.

## G1 — numerics (deterministic LCG data, mixed magnitudes, real cancellation)

- **Algebraic is MORE accurate than strict** vs a strict f64 reference, at every dim, both arms.
  Worst-vs-best at d=4096: strict rel-err 5.086e-6; algebraic 4.559e-7 (SSE2) / 1.453e-7
  (AVX2+FMA). The multi-accumulator reduction carries less rounding error than the scalar serial
  chain — the fast-math accuracy tax does not appear for add/mul reassociation on this data class.
- **ulp(strict↔algebraic)**: 1 @ d=16 → 4 @ d=64 → 5 @ d=256 → 18–20 @ d=1024 → 52–56 @ d=4096.
  Cross-build/cross-arch bit-equality is gone by construction (the ISA arms already disagree with
  each other: 52 vs 56 ulp at d=4096).
- **Argmax retention**: 1024 trials × 64 keys (d=64), forced near-tie pair on alternating trials —
  **0 flips**, 9 near-tie events (top-2 gap ≤ 8 ulp). Clean but LOW POWER: the forced pair only
  reaches the top-2 in 9 of 512 forced trials; a production retention walk must run on real
  logits before any logits-lane adoption (the Issue-750-T3 shape).

## Codegen evidence (rustc 1.98.1, `-C opt-level=3`, standalone twin of the exact loop shapes)

| arm | strict | algebraic |
|---|---|---|
| baseline SSE2 | 5 `mulss` + 5 `addss` — scalar serial chain | 2 `mulps` + 4 `addps` — 128-bit packed |
| `target-cpu=x86-64-v3` | 9 `vmulss` + 9 `vaddss` — **still scalar** | **5 `vfmadd231ps` + 6 `vaddps`** — packed YMM, multi-accumulator mainloop |

The scalar-strict result is the Issue-847 class one layer down: a platform the substrate doc
claims covered (`dot_8wide`: "auto-vectorizes to optimal SIMD FMA on every target we ship (NEON,
AVX2)") measured uncovered — the claim was established on aarch64/NEON (M3) and does not
transfer to x86_64-windows. In-crate confirmation + doc repair is Issue 871 T5.

## Verdict

Measured, GOAT-shaped on G1/G2 at this scale — but adoption is an owner act in the
`fast-math-contraction-behind-feature-flag` shape (strict default, dedicated feature, gates run
strict, retention walk before argmax-bearing lanes), and **T5 may be the better spend**: fixing
the strict side's missing x86_64 vectorization (runtime `simd_level()` dispatch or ordered-
reduction intrinsics) recovers part of the gap without surrendering the cross-arch bit-equality
that strict ordered reductions currently provide for free.
