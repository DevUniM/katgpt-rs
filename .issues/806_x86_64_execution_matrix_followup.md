# Issue 806 — x86_64 execution matrix: the 4090 AVX2 run closed two cells; the rest of the katgpt-rs surface is still executed by nothing

**Status:** OPEN — the matrix RAN (2026-09-16), and what is left is one cell
that needs the M3. Workstation/4090-owned, no CI lane exists for this axis
(and none is requested; Actions spending call stands).

## Provenance

2026-09-16: the first x86_64 execution of the katgpt-core/katgpt-types SIMD suites
(`4994cbdc8`, 4090 box, i7-13700K) caught **15 latent AVX2-arm defects** in two modules
(`bf16_convert` narrow-RNE missing the `>> 16`; `simd_lut_dequant` single-stage kernels using
the SSE4.1 4-element `_mm_cvtepu8_epi32` under a 256-bit gather). All fixed same-day, 4090
rerun 2069/0, M3 NEON 2070/0. Record: `HISTORY.md` top row + `.benchmarks/800_bf16_simd_goat.md`
addendum. The run covered exactly two cells of the matrix; this issue was the rest of it.

## What the rest of the matrix found (same day, `8da93896` + fixes)

Full record: [Bench 806](../.benchmarks/806_x86_64_execution_matrix.md).
Nine cells, ~11,000 assertions executed on x86_64 for the first time.

| # | cell | result |
|---|---|---|
| 1 | `katgpt-types --lib --all-features` | 261 / 0 |
| 2 | `katgpt-types` `bench_578_avx2_goat` (release) | 2 / 0, min speedup 5.76× |
| 3 | `katgpt-core --lib --all-features` | 4957 / 0 |
| 4 | `katgpt-attn --lib --all-features` | 424 / 0 |
| 5 | `katgpt-dec --lib --all-features` | 282 / 0 |
| 6 | `katgpt-pruners --lib --all-features` | 3011 / 0 |
| 7 | `katgpt-tokenizer --lib --all-features` | 74 / 0 |
| 8 | `katgpt-rs --lib --all-features` | 565 / **4** → **569 / 0** after the fix |
| 9 | `katgpt-rs --tests --release --no-fail-fast` | 232 targets · 1509 passed · **7** failed |

**Five defects, all fixed:**

1. `argtopk`'s AVX2 insertion search discarded every **new maximum** (`lo == 0`
   used as a "no lane qualified" sentinel, where the NEON sibling has an
   explicit flag) — `086dd912`.
2. The same kernel's partial-chunk step read **4 floats past the end** of the
   slice on every execution — same commit.
3. `observe_tvp_decision` read `self.gpu.is_some()` instead of
   `self.gate.gpu_available()`, so 4 TVP GOAT tests were red on every
   non-macOS platform and `g1b`'s no-GPU assertion passed **vacuously** —
   `fa27be42`.
4. `bench_llmexec_guard_overhead`'s measured loop had no `black_box` on its
   inputs and was **constant-folded away in release**, publishing a fabricated
   `0 ns/call` — `703bb70b`.
5. `VocabChannelDecomposer` drew its Householder symmetry-breaker from
   `fastrand`'s **unseeded thread-local global**, so `decompose_neuron` was not
   a function of its arguments and `test_decompose_neuron_discovers_channels`
   was a coin flip — caught by running the matrix TWICE, not by the platform.
   Fixed at `2081138f`, filed as
   [Issue 809](809_unseeded_global_rng_in_shipped_primitives.md).

**The issue's own cell list was narrower than the surface.** It named three
packages; a grep for `target_arch = "x86_64"` over the tracked tree finds
**six**, and `katgpt-attn/src/dash_attn/channel_aware.rs:586` carries a
**compile-time** `cfg(all(target_arch = "x86_64", target_feature = "avx2"))` —
the shape a plain x86_64 build compiles to nothing. That is why the population
is DERIVED in the script below rather than hand-typed.

## T5 — the matrix is a script now

`scripts/x86_64_execution_matrix.sh` (`aaa575b4`), documented in AGENTS.md.
Refuses off x86_64, exports `+avx2` itself, derives its packages, carries the
Issue-734 sentinel, floors every cell in `scripts/x86_64_matrix_floors.txt`,
re-runs each failure ALONE and then adjudicates by MEMBERSHIP in
`scripts/x86_64_matrix_expected.txt`. `--canary` verified live.

- [x] T5 — landed.

## What is still OPEN

- [x] **T6 — `t698_t5_kv_mean_gates` needs ONE M3 run.** DONE same day: the
      M3 run reproduces the pin `23d0daab…` (test green) — T6's first branch,
      the fixture is genuinely arch-dependent. Arch-conditional dual pins with
      the recorded delta landed (band bits one ulp apart; behavior gates pass
      on both platforms); the stale pin row removed in the same commit. The
      addendum at the tail of Bench 806 has the full two-sided table.
- [ ] **T7 — TWO perf bars are pinned, not fixed.** Both are a bar
      calibrated on the M3 (one, `proof_g3b_swar_speedup`, is named
      `SWAR+FMLA` — an *aarch64* instruction) or an absolute-latency target
      that does not transfer between machines. Each needs an x86_64
      calibration on a QUIET box before it means anything. Rows and reasons:
      `scripts/x86_64_matrix_expected.txt`. ⚠ It was SIX. Four runs of the one
      commit produced four different failing sets — `bench_176`, `g7`,
      `g5_roaring`, `t08_throughput_rebalance_256x16` and
      `goat_6_context_scaling_flat_o1` all came and went with the box's load —
      so the script now RE-RUNS each failure alone and only rows that fail
      twice are adjudicated. That is the measurement to carry: on this box a
      latency bar's verdict is partly a property of who else is building, and
      the instrument has to say so rather than pin it.
- [ ] **T8 — `argtopk`'s AVX2 arm is a measured LOSS** post-fix (12 of 15
      (k, n) cells slower than the scalar fallback). Filed separately as
      [Issue 808](808_avx2_argtopk_is_a_measured_loss_vs_scalar.md); owner's
      call between four options.

## Method (pinned by the 2026-09-16 runs)

- Run on the 4090 (the only x86_64 box): `git archive HEAD` to a SCRATCH dir —
  never the sibling's checkout (it carries concurrent WIP), and not on `E:`,
  which is at 99%. The script does this for you.
- ⛔ `RUSTFLAGS="-C target-feature=+avx2"` is MANDATORY for any arm gated
  `cfg(all(target_arch = "x86_64", target_feature = "avx2"))` — a plain x86_64
  `cargo test` silently exercises the scalar fallback and proves nothing.
- ⛔ **The integration cell is `--release --no-fail-fast`, measured not
  preferred:** `goat_574_clustered_lm_head` ran >20 min in debug without
  finishing and 39.8s in release, and without `--no-fail-fast` the run stops
  at the first red target (the first attempt reported 56 of ~180).
- ⚠ `--all-features` is **not a supported TEST configuration** here. It is used
  as a WIDENING instrument, and every failure it produces is re-run under the
  single feature that gates it before being called a finding. That narrowing is
  what separated cell 8's four from an interaction artifact; nothing else in
  nine cells needed it.
- Failure triage heuristic, now three-for-three: **NEON-correct + AVX2-wrong =
  transcription slip** (lane crossing, saturating-pack-vs-truncate,
  SSE4.1-vs-AVX2 element counts, a sentinel replacing a flag), not algorithm
  error — the NEON arm is the algorithm witness, the tests are the oracle.
- ⚠ And a green parity test is not coverage: `argtopk`'s existing
  `test_argtopk_simd_matches_scalar` was green through both defects because its
  fixture's maximum sits inside the first `k`, so no post-init element is ever a
  new maximum. Check whether the fixture can EXPRESS the mechanism.
