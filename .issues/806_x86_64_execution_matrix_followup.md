# Issue 806 — x86_64 execution matrix: the 4090 AVX2 run closed two cells; the rest of the katgpt-rs surface is still executed by nothing

**Status:** OPEN — follow-up task, workstation/4090-owned, no CI lane exists for this axis (and none is requested; Actions spending call stands).

## Provenance

2026-09-16: the first x86_64 execution of the katgpt-core/katgpt-types SIMD suites
(`4994cbdc8`, 4090 box, i7-13700K) caught **15 latent AVX2-arm defects** in two modules
(`bf16_convert` narrow-RNE missing the `>> 16`; `simd_lut_dequant` single-stage kernels using
the SSE4.1 4-element `_mm_cvtepu8_epi32` under a 256-bit gather). All fixed same-day, 4090
rerun 2069/0, M3 NEON 2070/0. Record: `HISTORY.md` top row + `.benchmarks/800_bf16_simd_goat.md`
addendum. The run covered exactly two cells of the matrix; this issue is the rest of it.

## Cells covered (2026-09-16, green)

| cell | result |
|---|---|
| `katgpt-types --lib`, default features, runtime AVX2 dispatch | 139/139 |
| `katgpt-core --lib --features bf16_simd`, `RUSTFLAGS="-C target-feature=+avx2"` | was 2054/15 → **2069/0** post-fix |

## Cells still x86_64-UNEXECUTED (this issue's scope)

1. `katgpt-core --lib --all-features` at `+avx2` — every other feature-gated SIMD arm
   (elementwise variants, ternary SWAR, dot accumulators, `simd_lut_dequant`'s remaining
   public entry points beyond the bf16_simd cell's coverage) compiles to nothing on aarch64
   and has never run on x86_64. **Highest-value cell: today's finding says the prior
   probability of more transcription bugs in never-executed arms is NOT low.**
2. `katgpt-dec` lib tests at `+avx2` (the DEC operators ship SIMD paths too).
3. Root package `--lib` + the always-on integration targets at `+avx2`.
4. `wasm32`-adjacent: none — out of scope here (wasm32_gate owns that triple).

## Method (pinned by the 2026-09-16 run)

- Run on the 4090 (the only x86_64 box): `git archive HEAD | ` extract to a SCRATCH dir —
  never the sibling's checkout (it carries concurrent WIP).
- ⛔ Compile-time `target_feature` gates: `RUSTFLAGS="-C target-feature=+avx2"` is MANDATORY
  for any arm gated `cfg(all(target_arch = "x86_64", target_feature = "avx2"))` — a plain
  x86_64 `cargo test` silently exercises the scalar fallback and proves nothing. Record the
  flags with every run.
- Cross-check compile errors from the M3 first:
  `RUSTFLAGS="-C target-feature=+avx2" cargo check -p <crate> --target x86_64-unknown-linux-musl --lib`
  (check never links; the M3 loop is seconds, the 4090 loop is minutes).
- Failure triage heuristic that worked: NEON-correct + AVX2-wrong = transcription slip
  (lane crossing, saturating-pack-vs-truncate, SSE4.1-vs-AVX2 element counts), not
  algorithm error — the NEON arm is the algorithm witness, the tests are the oracle.

## Exit criteria

Every cell above green on the 4090 (or a defect found → fixed → green), counts recorded in a
`.benchmarks/` addendum + a `HISTORY.md` row. If a cell finds more latent defects, fix them in
the same session — the oracle tests already exist for every arm these suites cover.
