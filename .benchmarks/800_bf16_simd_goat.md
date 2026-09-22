# Bench 800 — bf16⇄f32 SIMD conversion kernels GOAT gate (Issue 800 Arm A)

**Status:** RECORD — **G2 FAIL (honest), G1 + G4 PASS → `bf16_simd` stays
opt-in, NO consumer wiring (A4 deferred), NO promotion.** Measured 2026-09-16,
M3 Max (loaded box, sibling agents active — relative numbers same-box
minutes-apart; the DELTA is the finding).

Provenance: Issue 800 Arm A — the pufferlib distill's lead candidate. The
premise under test: `riir-engine weight_tensor::dequantize_row` runs a scalar
per-element BF16 loop on the weight-streaming hot path, so a NEON/AVX2 batch
kernel should win ≥4× (the pufferlib kernel-shape argument).

## The result

| kernel | scalar ns | SIMD ns | × | GB/s (scalar→SIMD) |
|---|---|---|---|---|
| widen u16→f32 (N=65536) | 13083 | 13083 | **1.00×** | 30.1 → 30.1 |
| narrow RNE | 33708 | 28292 | **1.19×** (2nd run 1.23×) | 11.7 → 13.9 |
| narrow trunc | 13166 | 13125 | **1.00×** | 29.9 → 30.0 |

Median of 7, release, two independent runs, stable.

## Root cause (the finding worth keeping)

**LLVM auto-vectorizes the scalar reference loops into the same NEON code.**
The identical 13083 ns medians for widen (0.92–1.00× across runs) are the
tell: rustc on aarch64 turns the trivially-vectorizable elementwise loops
(`from_bits(bits << 16)`, the add-form RNE, the `>>16` trunc) into the same
NEON sequences the intrinsics produce. Hand-written SIMD buys ~nothing for
this kernel class on M3 + current rustc; the RNE arm's 1.19–1.23× is the
auto-vectorizer handling the NaN-select slightly worse than the hand blend.

Consequences, per the feature-flag discipline (promotion requires the GOAT
gate to pass):

- `bf16_simd` ships **opt-in** (`bf16_simd = []`), never promoted.
- **A4 consumer wiring NOT executed**: `dequantize_row`'s consumer path
  already receives auto-vectorized codegen for its elementwise loop; swapping
  in the explicit kernels has no measured win to buy. Revisit only if (a) a
  consumer measures a real dequantize-bound profile where the auto-vectorizer
  demonstrably bails (debug builds, future rustc regressions, non-autovec
  targets), or (b) the ISA-guarantee argument (explicit intrinsics are not
  subject to optimizer heuristics) is independently worth it to the owner.

## What DID pass (the code is correct and stays)

- **G1**: bit-exact vs `half::bf16::from_f32` over hand boundary vectors +
  2²⁰ seeded random bit patterns + NaN class (the sNaN-payload-1→Inf trap is
  special-cased; half's qNaN-forcing convention `|0x0040` matched); widen is
  exhaustive over all 65536 u16 values; NEON-vs-scalar parity test EXECUTES
  on this machine.
- **G4**: `into_buf` slice→slice APIs, zero alloc, stack-buffer test.
- **AVX2 arm — the caveat resolved NEGATIVE, then FIXED (2026-09-16, same
  day).** The optional follow-up ran on the 4090 (i7-13700K, x86_64 native,
  `RUSTFLAGS="-C target-feature=+avx2"`, repo @ `d1f9be27a`): **execution
  parity FAILED — 15 tests red** (3 bf16 narrow-RNE + 12 simd_lut_dequant).
  The shared-algorithm argument the NEON arm proves is REFUTED by execution;
  both bugs are AVX2-transcription slips in arms that no automatic lane
  compiles (NEON runs on the M3, nothing runs x86_64-native):
  1. `f32_to_bf16_rne_avx2` dropped the NEON identity's final `t >> 16` —
     `_mm_packus_epi32` SATURATES i32→u16 instead of taking the high half,
     so every narrow packed 0x0000/0x7FFF/0xFFFF mask garbage
     (`rne(+0.0)` → 32767). Fix: shift `sel` before the split+pack.
  2. `dequant_via_lut_avx2` + `dequant_dot_via_lut_avx2` used the SSE4.1
     **4-element** `_mm_cvtepu8_epi32` where the 256-bit gather needs the
     **8-element** `_mm256_cvtepu8_epi32` — lanes 4–7 of every chunk kept
     index 0 and gathered `lut[0]`. The multi-stage kernel's own comment
     already documented this exact trap; the single-stage kernels missed it.
     All 12 lut failures cascade from these two sites (the multi-vs-single
     mismatch had the SINGLE side wrong). Also removed the dead stage-0
     preload in the multi-stage kernel that carried the same wrong intrinsic.
  Post-fix rerun on the same box: **`cargo test -p katgpt-core --lib
  --features bf16_simd` → 2069 passed / 0 failed** (was 2054/15). The same
  session also executed the katgpt-types suite on x86_64 for the first time
  (139/139, default build, runtime AVX2 dispatch) — the
  `simd_exp_sum_extreme_inputs_underflow_not_wrap` regression (riir-train
  Issue 549) has now actually RUN and passed on AVX2 hardware.
- Tests (original M3 run): `cargo test -p katgpt-core --features bf16_simd
  --lib` → 2070 passed (10 new bf16 tests); combo `--features
  bf16_simd,meld` → 2077/0; default features → 2060/0; wasm32 combo check
  clean; clippy `-D warnings` clean.

Landing: `f314d5006` (kernels + wiring; meld half of the wiring completes
`43f15f7c8`). Issue 800 Arm A closed A1/A2/A3 with the honest FAIL; A4 `- [-]`.
