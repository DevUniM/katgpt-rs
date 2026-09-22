# Issue 874 — G8 (`bench_271_attn_match_goat::g8_simd_vs_scalar`) is inert: the "scalar" arm routes through the same `dot_8wide` kernel

Status: **OPEN — T3 (the workspace census) LANDED 2026-09-22 (see the T3 section below): the consolidation trap exists in exactly ONE gate workspace-wide — this issue's own founding specimen; the adjacent by-catch class (a vacuous correctness assert + a wasm32 test target broken since the Plan 008 Step 7 wrapper removal — both riir-ai) is REPAIRED at `f04df9241` and compile-verified 2026-09-22 (worktree-verified while a sibling's manifest edit blocks live riir-ai loads); T1 remains owner-gated (GOAT gate semantics), and the T3 population gives the owner the full scope for that call: repairing ONE gate, not a family.**

Branch: `develop` · Evidence: [Bench 871](../.benchmarks/871_algebraic_dot_ab.md) §Addendum (in-crate codegen) · Filed: 2026-09-22

## The defect

`g8_simd_vs_scalar` (Plan 271's GOAT gate 8, `tests/bench_271_attn_match_goat.rs:464+`)
measures the speedup of `compute_score_matrix_simd` over `compute_score_matrix` and asserts
≥ 1.5×. But `score_matrix.rs::compute_score_matrix` **routes its inner loop through
`dot_8wide`** — the SAME kernel `compute_score_matrix_simd` uses. The gate compares one
kernel against itself:

- **x86_64-pc-windows-msvc** (measured in-crate, Bench 871 addendum): both arms compile to
  the identical scalar serial chain (0 packed float math crate-wide at BOTH the SSE2
  baseline and `+avx2,+fma`) → speedup ≈ 1.0.
- **aarch64** (cross-emit twin evidence): both arms get the identical packed-`fmul.4s` +
  ordered-scalar-`fadd` shape → speedup ≈ 1.0 there too.

The `< 1.5` branch then prints `G8: SKIP …` and **returns Ok — exit 0**. So G8 can never
fail by construction: it either SKIPs (identical arms) or "passes" on timing noise between
two identical binaries (a false pass, which is worse). This is the Issue-855
latency-gate-green-zero class and the cfg-gated green-zero rule one layer down, sitting
inside a GOAT gate on a default-on feature.

## When it broke

The simplification that made `compute_score_matrix` reuse `dot_8wide` (the Plan-271-era
kernel consolidation, DRY-motivated — correct for bit-identity, fatal for the A/B gate).
Since then G8's two arms are the same code; any historical G8 "PASS" post-consolidation was
timing noise, and every SKIP was the gate going blind, not scalar being "unusually
well-optimized" (the SKIP message's own framing).

## Repair options (for the fixing session — decide, don't stack)

1. **Genuine scalar reference arm**: a `#[inline(never)]` naive triple-loop INSIDE the
   bench (never routed through `dot_8wide`) as the baseline, preserving the gate's original
   intent (SIMD-shaped vs naive-shaped).
2. **Re-point the gate** at a real architecture contrast that still exists (e.g. serial
   `compute_score_matrix` vs `compute_score_matrix_rayon` at a size where rayon wins) and
   rename accordingly.
3. **Retire the speedup claim**: convert G8 to an absolute throughput smoke (the
   `test_simd_throughput_smoke` shape already in `score_matrix_simd.rs` tests) and record
   that the relative-speedup claim is unmeasurable since the kernel consolidation.

⚠ Whatever the choice: check `scripts/test_gate.sh` PERF_ROWS and any count pins for
`bench_271_attn_match_goat` before/after, and note that option 1's naive arm is
deliberately NOT bit-different from the SIMD arm on x86_64 (both scalar) — the gate would
be measuring shape-vs-shape codegen, which after Issue 871's findings is known to be
target-dependent (state the target in any new bar).

## Tasks

- [ ] T1 — Decide the repair option (1/2/3 above) — owner-gated (GOAT gate semantics).
- [ ] T2 — Implement + re-run the full `bench_271_attn_match_goat` gate; record the new
  G8 posture in the Plan 271 record's addendum.
- [x] T3 — Grep the workspace for OTHER `*_vs_scalar`-style A/B gates whose "scalar" arm
  routes through the same kernel as the "SIMD" arm (the same consolidation trap may exist
  elsewhere — this filing checked only the one the Issue 871 reviewer named). LANDED
  2026-09-22 — see the "T3 census" section.

## T3 census (2026-09-22)

Vocabulary: `vs_scalar|simd_vs|scalar_speedup|vs scalar` over tracked `*.rs` across the
18 workspace roots — **88 matches → 16 gate/bench sites read one by one**. Verdicts:

**INERT (this issue's class — a gate whose two arms route through the same kernel):**

1. `katgpt-rs/tests/bench_271_attn_match_goat.rs::g8_simd_vs_scalar` — the founding
   specimen, and the ONLY one. No other gate workspace-wide shares the trap.

**BY-CATCH (different defect classes, found by the census reads — repair LANDED
riir-ai-side at `f04df9241`; compile-verification COMPLETE 2026-09-22, worktree-
verified at the `f04df9241` tree while a sibling's in-flight riir-train manifest edit
still blocks live riir-ai workspace loads: `cargo check -p riir-engine --target
wasm32-unknown-unknown --test wasm_simd_bench` Finishes clean, and the bench's own
`verify_correctness()` (T6 scalar-vs-dispatcher + T7 matvec) passes under criterion
`--test` — both green on the exact landed bytes):**

2. `riir-ai/crates/riir-engine/benches/bench_286_simd.rs::verify_correctness` T6 arm —
   `expected` and `reference` BOTH computed by `scalar_project_ternary` on the same
   inputs: a **vacuous correctness assert** (the comment says "scalar reference must
   equal naive reference" — the naive twin never existed in the file). The wasm twin
   (`tests/wasm_simd_bench.rs`) has the real scalar-vs-SIMD arm, so the native bench's
   T6 verify certified nothing.
3. `riir-ai/crates/riir-engine/tests/wasm_simd_bench.rs` — **un-compilable on its own
   target since Plan 008 Step 7 dropped the `matmul_f32_simd`/`dot_f32_simd` wrappers**:
   the file still imports `matmul_f32_simd` (zero definitions anywhere in katgpt-types /
   katgpt-core / riir-infer-core — verified by grep) for an API-surface regression test
   whose guarded contract was deliberately removed. Whole-file `#![cfg(wasm32)]` hid
   the break from every native lane — its T6/T7 ≥2.0 SIMD-vs-scalar GOAT gates execute
   NOWHERE (the green-zero class one level up). Fix: drop the dead import + the dead
   wrapper test (the replacement API `simd_matvec` is already covered by the file's own
   T7 tests).

**OK — genuine contrast, asserted speedup gates (the healthy population):**

4. `katgpt-tokenizer/src/fast_bpe/simd_split.rs::g2_scan_ab_simd_vs_scalar` — distinct
   `SplitLevel::Scalar` code path; interleaved rounds + median; its 1.25 floor's STATED
   purpose is catching silent fallback-to-scalar (this issue's class, caught by design).
5. `katgpt-types/tests/bench_578_avx2_goat.rs::g2_avx2_vs_scalar_speedup` — dispatcher
   AVX2 vs the named `ternary_group_matvec_scalar`; loud non-AVX2 skip whose comment
   shows same-code awareness; interleaved medians; ≥2.0 gate.
6. `katgpt-rs/tests/bench_148_plasma_path_goat.rs::proof_g3_throughput_1024` — inline
   raw-loop FP32 scalar baseline PLUS an explicit anti-inertness assert ("scalar
   baseline suspiciously fast … compiler may have vectorized it") — the model citizen.
7. `riir-ai/crates/riir-engine/tests/wasm_simd_bench.rs` t6/t7 bench bodies — local
   naive scalar helpers vs imported SIMD fns; ≥2.0 GOAT gates asserted (WHEN the file
   compiles — see by-catch 3).
8. `riir-ai/crates/riir-gpu/benches/matmul_swap_ab_bench.rs` — three distinct shader
   sources (standard tiled / scalar-swap_ab / CMMA-swap_ab).
9. `riir-ai/crates/riir-gpu/tests/bench_606_t3c_dot4i8_probe.rs::t3c_alu_microbench` —
   distinct packed/scalar shaders; loud-zero assert (both shaders must execute);
   print-only verdict.

**OK — print-only ratios / absolute bars (no relative gate to false-pass):**

10. `katgpt-core/src/cubical_nerve/nerve.rs::bench_optimized_vs_scalar_nerve` — print-only,
    no ratio assert (and cross-size, not same-size A/B).
11. `katgpt-pruners/src/interval_pruner/simd.rs` — two print-only ratio benches; the
    module's asserts are value-equality only.
12. `katgpt-rs/tests/bench_256_simd_topk.rs` — value asserts; timing print-only; uses the
    shared `ab_median_ratio` harness (asserts loudly on a vanished arm).
13. `katgpt-rs/tests/goat_234_manifold_pruner.rs::g9` — value-match assert; ratio print-only.
14. `katgpt-rs/tests/latent_steering_t3_simd_vs_scalar.rs` — ratio print-only; the asserted
    gate is an ABSOLUTE budget (G4 carry-over p50).
15. `katgpt-core/examples/simd_wasm32_goat.rs` — reference is an INDEPENDENT scalar loop
    by design ("not the crate's own `scalar_*` fallback"); G2 speedup printed with honest
    INCONCLUSIVE labeling, not asserted.
16. `riir-ai/crates/riir-engine/benches/bench_286_simd.rs` (perf half) — Criterion report;
    inline naive scalar refs. (Its verify half is by-catch 2.)

Non-gates excluded: value/bit-identity tests (bf16_convert, simd_lut_dequant, bitcos,
ternary_trit, regime_probe, riir-gpu devpos family, matmul_swap_ab_cubecl agreement),
semantic comparisons (morality, feeling_brain NCA-vs-decay), doc comments, riir-clippy
corpus text, `.scratch/` POCs, and the nested `riir-ai/riir-train/` checkout's duplicate
hits.

**Reading for T1's owner decision:** the trap is ONE gate, not a family — options 1/2/3
bound exactly `bench_271_attn_match_goat::g8`. The workspace's OTHER SIMD A/B gates
already defend this class three independent ways worth copying whichever option wins:
bench_148's anti-vectorization assert on the scalar baseline, fast_bpe's fallback-catch
floor, and bench_578's same-code-aware loud skip. The two riir-ai by-catches are filed
for repair there (the wasm32 break restores two live ≥2.0 GOAT gates once compile-fixed).
