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

- **Algebraic is MORE accurate than strict** vs a strict f64 reference, at every dim, both arms —
  **on this mixed-magnitude LCG data class** (the qualifier is load-bearing: the f978a20b
  Cholesky precedent shows reassociation can REGRESS 10× on near-singular pivots; the
  ill-conditioned arm below measures that class for THIS kernel).
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
strict, retention walk before argmax-bearing lanes). ~~T5 may be the better spend: fixing the
strict side's missing x86_64 vectorization (runtime `simd_level()` dispatch or ordered-
reduction intrinsics) recovers part of the gap without surrendering the cross-arch bit-equality
that strict ordered reductions currently provide for free.~~ **Correction (2026-09-22, the
in-crate addendum below): that repair path does not exist.** The strict serial add order IS
the bit-equality; vectorizing the add chain changes summation order and therefore the bits.
The only bit-preserving partial vectorization — packed multiplies + ordered scalar adds — is
what LLVM already emits on aarch64 (and it leaves the add-latency chain intact, which is why
the AVX2 arm's strict time is flat vs baseline in G2 above). On x86_64 the perf lever is the
opt-in `algebraic_*` feature lane (T4) or nothing.

## Addendum — in-crate confirmation + aarch64 twin (T5, 2026-09-22)

**Method.** `cargo rustc -p katgpt-attn-match --features attn_match --release --
--emit asm -C lto=off` (isolated `CARGO_TARGET_DIR`), x86_64-pc-windows-msvc, rustc 1.98.1
(48a229cea, repo pin). Two arms: default target features (the SSE2 baseline every ordinary
consumer builds) and `-C target-feature=+avx2,+fma`. Instruction mix counted over the whole
crate's `.s` (float math ops only; `vmovaps`/`vxorps`/`vbroadcastss` moves excluded).

| arm | scalar float mul/add | packed float math | verdict |
|---|---|---|---|
| x86_64 baseline (SSE2), in-crate | 122 (`mulss`/`addss`) | **0** | every strict reduction is a scalar serial chain |
| x86_64 `+avx2,+fma`, in-crate | 122 (`vmulss`/`vaddss`) | **0** | unchanged — the wider ISA is unused by strict code |
| aarch64-apple-darwin, standalone twin | serial `fadd` chain | packed `fmul.4s` (mul half only) | partial vectorization, **no `fmla`**, bit-identical |

Per-function attribution (baseline arm): the scalar chains sit in `fit_beta_nnls` (25),
`value_fitter::*` (fit/cholesky/relative-error family), `compact_with_router` (8),
`select_highest_attn_keys` (7), `compute_score_matrix` (5), `compute_softmax_attention_and_output`
(5), `select_omp_keys` (5), `head_budget::*`, `compute_score_matrix_rayon` closures — i.e. every
loop the crate's comments described as "auto-vectorizing". The aarch64 evidence class is a
**standalone twin** (blake3's build script cannot cross-compile to aarch64-apple-darwin from
Windows; no Apple SDK) — the same evidence class as the original §Codegen evidence, and the
x86_64 twin-vs-in-crate relationship held exactly (122/0 both ways), which is the calibration
for trusting the aarch64 twin.

**aarch64 twin detail (the historical-claim kill):** the strict loop emits `ldp q1, q2, …` +
`fmul.4s v1, v1, v5` (packed products) then `mov sN, vM[k]` lane extracts feeding `fadd s0, s0, …`
in **exact element order** (lane 0,1,2,3 per group) — bit-identical to the serial order by
construction, and **zero `fmla`**. The 2026-07-29 M3 doc story ("the simple loop lets LLVM emit
the optimal `fmla` sequence with a single vector accumulator + one final horizontal reduce")
was never codegen-true: NEON gets multiply-throughput only; the add chain was always serial.
The 1.26× 8-accumulator refutation stands as a measurement, but its then-attributed mechanism is
corrected in-source: the confounders were per-element bounds checks (pre-`..d`-slice era) and
the `iter().sum()` horizontal reduce — not the accumulator count (reasoned; not re-measured,
M3 not reachable from this box).

**Consequence for T4:** there is no strict-side repair to spend on. The decision is purely
whether to ship the opt-in `algebraic_*` lane (owner act, feature-gated, retention walk before
any argmax-bearing consumer) or decline and keep strict-scalar.

### Ill-conditioned arm (2026-09-22, the (a′) landing condition — the f978a20b class, measured)

Run: baseline SSE2 arm, same box (sibling session active — medians on the plain A/B drifted
±0.05 vs the table above; the ill-conditioned metrics are f64-referenced and
load-insensitive). `d=512`, 512 trials/class, recorded either way, no bar:

| class | strict mean/max scale-rel err | algebraic mean/max | strict sign-flips vs truth | algebraic sign-flips |
|---|---|---|---|---|
| ortho (near-zero dot, f64-orthogonalized) | 8.247e-9 / 7.235e-8 | **4.584e-9 / 2.361e-8** | 256/512 | **191/512** |
| dup (rank-deficient, duplicate 8-blocks ± v) | 5.354e-9 / 7.093e-8 | **6.645e-18 / 1.052e-16** | 245/512 | **0/512** |

**Recorded verdict: algebraic ≥ strict on BOTH ill-conditioned classes** — the f978a20b
counterexample (Cholesky near-singular pivots, G5 0.7%→7.5% under a reassociation change)
does NOT reproduce for the plain dot kernel. The dup-class near-exactness is structural:
the multi-accumulator grouping cancels the duplicate-block ± pairs exactly, where the serial
chain accumulates rounding drift before subtracting (grouping-alignment luck for THIS
synthetic structure — a different grouping/structure pairing could fare differently; the
ortho row is the representative generic-cancellation result). Near-cancellation SIGN remains
a coin flip for both kernels (256 and 191 of 512) — truth-at-rounding-scale means sign is
noise; consumers deciding on small-magnitude dot signs need magnitude-aware logic either
way, not a summation-order choice.

**Doc repair landed with this addendum** (comment-only, clippy + 122 lib tests green):
`score_matrix_simd.rs` (module history, `dot_8wide` doc + inner comment, stage-1 comment, two
test docstrings), `score_matrix.rs` (module + call-site), `compact.rs` (3 sites), `router.rs`
(`CpuSimd` variant doc), `key_selection/omp.rs`, `key_selection/highest_attn.rs` (2 sites),
`value_fitter.rs` (3 sites). Every "auto-vectorizes on AVX2/NEON" claim in the crate now states
the measured per-target truth.
