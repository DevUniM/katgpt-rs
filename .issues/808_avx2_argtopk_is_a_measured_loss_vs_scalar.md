# Issue 808 — the AVX2 `argtopk` path is a measured LOSS vs its own scalar fallback on x86_64

**Status:** OPEN — decision, workstation-measured. Found while executing
[Issue 806](806_x86_64_execution_matrix_followup.md)'s matrix; the correctness
half of the same finding is already fixed. **2026-09-17:** option 4's
re-measurement (six realistic block-score distributions) + T2's per-k `N_MIN`
crossover landed as [Bench 810](../.benchmarks/810_argtopk_distribution_crossover.md)
— the recorded loss shape SURVIVES realistic distributions and deepens on
`late_peak`; k≤4 is the distribution-robust carve-out. T1 remains the owner's
call; T2's ≥2-microarchitecture bar is still 1 of 2 met.

## Provenance

`crates/katgpt-attn/src/dash_attn/block_topk.rs` dispatches `argtopk` to an
AVX2 kernel for `k ≤ 16` (Plan 256 Phase 1). That kernel had **never been
executed** — `full_gate` is macOS/aarch64 and compiles it to nothing,
`wasm32_gate` builds a third triple, and the only target that exercises it,
`tests/bench_256_simd_topk.rs`, opens `#![cfg(feature = "vortex_flow")]` and is
therefore a green zero on a default `cargo test`.

Its first x86_64 execution (2026-09-16, 4090 box, `RUSTFLAGS=-C
target-feature=+avx2`, repo @ `8da93896`) found **two correctness defects**,
both fixed in the same session and both recorded in
[Bench 806](../.benchmarks/806_x86_64_execution_matrix.md). This issue is the
**performance** half, which the tests do not assert and so did not fail on.

## The measurement

`cargo test -p katgpt-rs --test bench_256_simd_topk --release --
--nocapture --test-threads=1`, `+avx2`, i7-13700K. Speedup = scalar ÷ AVX2, so
**below 1.00× is a loss**:

| k \ n | 64 | 128 | 256 | 512 | 1024 |
|---|---|---|---|---|---|
| 4  | 0.83× | 0.94× | 1.24× | 1.43× | 1.75× |
| 8  | 0.59× | 0.61× | 0.65× | 0.81× | 1.14× |
| 16 | 0.75× | 0.78× | 0.84× | 0.92× | 1.07× |

**12 of 15 cells are a loss**, and the loss deepens as `k` grows — the opposite
of what a wider register is supposed to buy. The three wins are all at the
large-`n` end. The k-sweep at n=256 agrees independently: k=1 0.98×, k=2 1.80×,
k=4 1.61×, k=8 0.62×, k=12 0.84×, k=16 0.79×.

⚠ These numbers are **post-fix**. They are not the cost of the defects; the
defects made the kernel do LESS work (a discarded insertion is a skipped
shift), so the pre-fix figures would have flattered it.

## Why this is plausible rather than surprising

The AVX2 arm is not a vectorised top-k. It is a scalar sorted-insert whose
*insertion-point search* is vectorised — `_mm256_cmp_ps` +
`_mm256_movemask_ps` over `k ≤ 16` heap slots, i.e. one or two vector
compares to replace a branchy walk over at most 16 floats that the
auto-vectoriser already sees. The shift that follows is scalar either way.
For `k = 8` the search is a **single** 8-wide compare, and the setup
(`_mm256_set1_ps`, the movemask, the `trailing_zeros`) costs more than the
walk it replaces. `argtopk_scalar_heap` is meanwhile compiled with the same
`+avx2` the kernel demands, so "scalar" here is already auto-vectorised —
Bench 800's `simd_lut_dequant` reached the same conclusion for the same
reason.

## Options (owner's call — the modelless-first rule does not decide this one)

1. **Raise the dispatch floor on `n`.** The crossover is ~n = 256 at k = 4 and
   ~n = 1024 at k = 8/16. A `k ≤ 16 && n >= N_MIN` predicate keeps the wins
   and drops every loss. Needs `N_MIN` measured per k, not guessed.
2. **Narrow the dispatch to `k ≤ 4`.** Simplest; keeps the 1.24–1.75× band and
   the k=2 1.80×, drops the k=8/16 arm entirely.
3. **Delete the AVX2 arm.** Two correctness defects and a net loss is a poor
   trade for an arm nothing executed. The NEON arm is unaffected and is the
   algorithm witness the AVX2 port was transcribed from.
4. **Keep and re-measure on the deployed profile.** These are `.rev()`-free
   synthetic ramps at `iters = 1000`; a real DashAttn block-score distribution
   may not look like them.

⛔ Do not decide this from THIS box alone. n = 1 machine, one microarchitecture
(Raptor Lake), one input distribution. A dispatch change is a **behaviour**
change on every x86_64 deployment; the measurement above is strong enough to
say "the arm does not currently earn its keep here" and not strong enough to
pick between 1 and 2.

## Tasks

- [ ] T1 — owner picks an option above.
- [ ] T2 — if 1 or 2: measure `N_MIN` per `k` on ≥ 2 microarchitectures, then
      gate the dispatch and add the crossover to the bench as an assertion, so
      the next regression is a test failure rather than a table nobody reads.
      ⚠ 2026-09-17: the Raptor-Lake row exists (Bench 810) — and `N_MIN` is
      DISTRIBUTION-sensitive there (k=8: 256 on `locality`, 768 on
      `iid_uniform`, >1024 on `late_peak`), so the eventual gate needs the
      distribution axis, not one n per k.
- [x] T3 — **DONE** (landed with this issue). `bench_256_simd_topk` had no
      `[[test]]` row at all, so `cargo test --test bench_256_simd_topk` at
      default features compiled an empty binary and printed `ok. 0 passed`,
      exit 0 — this repo's own green-zero rule, on the one target that
      executes the kernel two defects were hiding in. Row added; independent
      of options 1–4.
- [x] T4 — **DONE 2026-09-17** (Bench 810 + `tests/bench_256_simd_topk.rs`
      `bench_simd_topk_issue808_{distribution_matrix,crossover_nmin}`). Option
      4's evidence half, ungated: six deterministic distributions (iid /
      gauss-sigmoid / locality / early-peak / late-peak / bimodal-sparse) ×
      k ∈ {1,2,4,8,16} × n ∈ {64..1024} × BOTH profile arms (default release;
      `+avx2`), interleaved median-of-ratios (`tests/common/ab_timing.rs`),
      per-cell correctness vs full-sort reference. Headlines: (1) the k=8/16
      loss survives every distribution except `early_peak` and DEEPENS on
      `late_peak` (0.41–0.72× below n=512; still 0.90–0.95× at n=1024 — no
      n-floor rescues k=8 there); (2) k=2/4 win or tie on every distribution
      past n=64–128 (up to 3.9×) — option 2 is the distribution-robust
      carve-out; (3) `N_MIN` is distribution-sensitive (see T2 note); (4)
      k=1's dispatch is a separate two-pass argmax whose cost depends on where
      the max sits (`late_peak` loses ~0.9× at every n). Instrument caveat:
      the harness's anti-hoist churn adds a constant to both arms, compressing
      ratios toward 1.00 — measured losses are MILDer than true. T1 is
      untouched: this box is 1 of the ≥2 microarchitectures T2's bar demands.
