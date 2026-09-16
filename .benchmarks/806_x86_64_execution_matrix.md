# Bench 806 — the x86_64 execution matrix: nine cells executed, one product defect found

**Owner:** [Issue 806](../.issues/806_x86_64_execution_matrix_followup.md).
**Box:** shikuwa (the 4090 — i7-13700K, 16 cores, Windows 11, x86_64 native).
**Repo:** `8da93896` (`git archive HEAD` into a SCRATCH tree on `F:`, per the
method Issue 806 pins — never a sibling's checkout, and off `E:` because that
volume is at 99%).
**Toolchain:** the workspace pin (`rust-toolchain.toml`, 1.98.1).
**Flags:** `RUSTFLAGS="-C target-feature=+avx2"`, `-j 6`
(`-j 6` per the box's `STATUS_ACCESS_VIOLATION` history, not for speed).

## Why this exists

AGENTS.md's **compile vs EXECUTE** axis, one platform over. `full_gate` is
macOS/aarch64 and is compile+lint rather than execute; `wasm32_gate` builds a
third triple; `test_gate` is the only executing lane and it is scoped and
schedule-suspended. So every `#[cfg(target_arch = "x86_64")]` arm in this
workspace was, until 2026-09-16, executed by nothing. The first two cells of
that matrix (Bench 800's addendum) caught **15 latent AVX2-transcription
defects**. This run is the rest of the matrix.

## The matrix

| # | cell | features | profile | result |
|---|---|---|---|---|
| 1 | `katgpt-types --lib` | `--all-features` | debug | **261 / 0** |
| 2 | `katgpt-types --tests` (`bench_578_avx2_goat`) | `--all-features` | **release** | **2 / 0** |
| 3 | `katgpt-core --lib` | `--all-features` | debug | **4957 / 0** (26 ignored) |
| 4 | `katgpt-attn --lib` | `--all-features` | debug | **422 / 0** |
| 5 | `katgpt-dec --lib` | `--all-features` | debug | **282 / 0** |
| 6 | `katgpt-pruners --lib` | `--all-features` | debug | **3011 / 0** |
| 7 | `katgpt-tokenizer --lib` | `--all-features` | debug | **74 / 0** |
| 8 | `katgpt-rs --lib` (root) | `--all-features` | debug | **565 / 4 → 569 / 0** after the fix below |
| 9 | `katgpt-rs --tests` (integration) | default | **release** | **232 targets · 1509 passed · 7 failed · 28 ignored** — see below |

Cells 4, 6 and 7 are **not in Issue 806's cell list** — the issue scoped the
follow-up to katgpt-core, katgpt-dec and the root package. A grep for
`target_arch = "x86_64"` over the tracked tree finds x86_64 arms in
**katgpt-attn, katgpt-pruners and katgpt-tokenizer** as well, and
`katgpt-attn/src/dash_attn/channel_aware.rs:586` carries a
**compile-time** `cfg(all(target_arch = "x86_64", target_feature = "avx2"))`
— the highest-risk shape there is, because a plain x86_64 build without
`+avx2` compiles it to nothing and the aarch64 gate never sees it at all.
The issue's cell list was narrower than the surface; this record is the
corrected one.

## The finding — `router_tvp.rs` asked the wrong question about the GPU

Cell 8 came back **4 red** with `--all-features`, and the four survived
narrowing to the single feature that gates them
(`--features thicket_variance_probe`) and to a build **without** `+avx2`. So:
not an `--all-features` interaction, not AVX2, not this box. A standing
defect in an opt-in feature that no lane executes.

```
inference_router::router_tests::g1_high_disagreement_promotes_cpu_to_gpu
inference_router::router_tests::g4_reasoning_disagreement_promotes
inference_router::router_tests::g5b_clear_signal_returns_to_defer
inference_router::router_tests::tvp_signal_persists
      left: Hold      right: PromoteGpu
```

`InferenceRouter::observe_tvp_decision` read

```rust
let gpu_available = self.gpu.is_some();
```

while the path its own doc comment says it **mirrors** —
`observe_critical_entropy`, `src/inference_router.rs:546` — reads
`self.gate.gpu_available()`. Those two disagree on every platform but one:
`try_create_gpu_backend()` returns `None` unless
`all(target_os = "macos", feature = "gpu_inference")`, so on x86_64
`self.gpu` is **always** `None` however the caller constructed the router.

The pair of tests is what makes the verdict decisive rather than a judgement
call. `g1` builds `fast_router(true, …)` and demands `PromoteGpu`; `g1b`
builds `fast_router(false, …)` and demands `Hold`. Under the backend-handle
reading **both arms see `false`**, so `g1` is red and **`g1b` passes
vacuously** — a two-sided pair that only the gate-derived value can satisfy.
`TriggerGate` is also the component that actually promotes the tier
(`trigger_gate.rs:242`, `:303`, `:384` all branch on its own
`self.gpu_available`), so a TVP recommendation derived from a different
notion of availability could contradict the gate it advises.

Fixed at one line plus the comment explaining it; cell 8 goes **569 / 0**.
Opt-in feature, so no default-path behaviour changes. On macOS with
`gpu_inference` the value moves only in the case where the caller said
"GPU available" and backend creation then FAILED — where the gate already
believes it is available and promotes anyway, and `forward()` falls back to
CPU through `signal_recompile_for_tier`'s `if let Some(...)`. Agreeing with
the gate is strictly the more consistent of the two.

## The second finding — two AVX2 defects in `argtopk`, one of them UB

Cell 9 red at `tests/bench_256_simd_topk.rs` (`#![cfg(feature =
"vortex_flow")]`), the **only** thing in the workspace that executes the AVX2
`argtopk` kernel in `katgpt-attn/src/dash_attn/block_topk.rs`:

```
bench_simd_topk_k_sweep_n256        Mismatch at k=8
  left (SIMD): [  4, 91, 222, 129,  97, 255, 184, 167]
  right (ref): [227, 86,  45,   4,  91, 222, 129,  97]
bench_simd_topk_correctness_and_speed
```

Read the two rows against each other: the SIMD answer is the reference with
its **top three dropped** and three lower-ranked indices appended. Not
garbage — a systematically missing head.

**Defect 1 — a new MAXIMUM was silently discarded.**
`insert_sorted_simd_avx2` searches for the insertion point with
`_mm256_movemask_ps` + `trailing_zeros()`, then:

```rust
if lo == 0 && chunks8 > 0 { lo = chunks8 * 8; }   // "nothing qualified"
```

`lo == 0` cannot distinguish *no lane qualified* from *lane 0 qualified* —
and lane 0 qualifying means `val` is a **new top-1**. Every such candidate had
`lo` reset to `k`, hit `if lo >= k { return; }`, and was thrown away. The NEON
sibling (`insert_sorted_simd_neon`, same file) carries an explicit
`found_in_simd` flag and never had this; the AVX2 port replaced the flag with
the sentinel. Bench 800's triage heuristic again, third instance:
**NEON-correct + AVX2-wrong = transcription slip, not algorithm error.**

It fires only for `k ≥ 8` (`chunks8 = k / 8` is 0 below that, so the search is
pure scalar) — which is exactly what the failing table shows: k=1, 2 and 4
printed clean and k=8 was the first assert.

**Defect 2 — an out-of-bounds read on every execution.** The AVX2 arm had a
"handle the remaining 4" step that ran when `n - pos` was 4..7 and loaded a
**full 8-wide** `_mm256_loadu_ps` from `pos`, then masked lanes 4..7 away with
`& 0x0F`. So it over-read up to 4 floats past the end of the slice — UB, for a
result it discarded — and the scalar tail immediately below already handled
those elements. The NEON sibling has no such step. Removed, which is both the
minimal fix and the DRY one.

**Why the crate's own parity test did not catch it.**
`block_topk.rs::test_argtopk_simd_matches_scalar` compares SIMD against a full
sort for k ∈ {1,2,4,8,16} and is **green** — `cargo test -p katgpt-attn --lib
--all-features` was 422/0 in cell 4 of this very matrix. Its fixture is a
20-element array whose maximum, `4.2`, sits at index **7** — inside the first
`k` for every k it tests. No element after the initial fill is ever a new
maximum, so defect 1's branch is unreachable, and n=20 with k=8 leaves a
4-element tail the removed loop mishandled only into a masked-off lane. **A
fixture that cannot express the mechanism it guards.** Two regression tests now
live in the crate that owns the kernel, so any x86_64 `cargo test -p
katgpt-attn` catches a recurrence without the root package or `vortex_flow`:
`test_argtopk_new_maximum_after_init_is_kept` (a strictly ascending ramp, so
EVERY post-init element is a new maximum, over n ∈ {24,32,40,64,100} × k ∈
{1,4,8,12,16}) and `test_argtopk_partial_tail_lengths_match_reference`
(lengths leaving 1..7 elements past the last full chunk).

Both were validated by **re-introducing defect 1 and re-running**: the two new
tests RED and the nine pre-existing `argtopk` tests stay GREEN — which is the
measurement, not a claim. ⚠ Read defect 2's coverage honestly: its over-read
was into lanes the kernel then masked away, so it corrupted no RESULT and **no
assertion over outputs can detect it**. The tail test pins the lengths at which
that step used to run; the defect itself is one only a sanitizer or a page
boundary would have caught, which is why it survived alongside a green
parity test.

⚠ The kernel is also a measured **performance loss** post-fix — 12 of 15
(k, n) cells slower than the scalar fallback it replaces. That is a separate
decision with its own options and is filed as
[Issue 808](../.issues/808_avx2_argtopk_is_a_measured_loss_vs_scalar.md), not
resolved here.

## A profile note that is not a defect

Cell 2 **fails in debug** — `bench_578_avx2_goat`'s G2 gate measures an
unoptimised binary and reports below its 2× floor. That is AGENTS.md's
"run the armed gates with `--release`" rule, and the target's own docstring
already prints the `--release` command. In release, on this box:

```
  shape           avx2         scalar        speedup
 512x512         39375         318555          8.09x
1024x1024       175170        1009360          5.76x
 512x5120       394725        2755090          6.98x
min speedup across shapes: 5.76x   (floor: 2x)
```

⚠ Worth writing down anyway: the target is
`#![cfg(all(feature = "ternary_group_scale", feature = "plasma_path",
target_arch = "x86_64"))]`, so it is a **green zero** on the M3 and red in
any x86_64 debug run. It passes in exactly one configuration — x86_64 ×
release × those two features — and nothing automatic is in it. This run is.

## Cell 9 — the integration targets, and why the PROFILE had to change

232 targets, 1509 assertions, **28 green-zero targets** (a `#![cfg]` whose
feature is off — this repo's own documented shape, not a finding here).

**Debug is not a viable profile for this cell, measured twice.**
`goat_574_clustered_lm_head` ran for over **20 minutes in debug without
finishing** and takes **39.8s** in release. `bench_164_gepa_reflective_goat`
fails its own 10%-overhead bar at **15.5%** in debug purely because both sides
are unoptimised. And `--no-fail-fast` is not optional either: the first
attempt stopped at the first red target and reported **56** of ~180 as if that
were the run.

### 7 failing tests, 0 of them correctness

| test | what it says | class |
|---|---|---|
| `proof_g3b_swar_speedup` | ≥5.0× gate, **4.37×** | bar named `SWAR+FMLA` — an **aarch64** instruction; the x86_64 arm was never calibrated |
| `g5_roaring_batch_speedup` | "≥2×, got **0.0×** (roaring=0.00µs, linear=0.00µs)" | the ratio is **0/0** — both arms below clock granularity in release |
| `g7_throughput_gain_over_plan_218_baseline` | −69.9% (6.22ms vs 3.66ms) | same target, same first-execution |
| `t09_throughput_inv_sqrt_16x16` | 88.7 µs vs a **10 µs absolute** target | absolute latency does not transfer between machines at all |
| `bench_176_router_forward_cpu` | 27.7% overhead (1.35 µs vs 1.06 µs) | 0.29 µs of absolute overhead, on a loaded box |
| `benchmark::llmexec_guard::tests::test_bench_llmexec_guard_runs` | "guard timing should be positive" | **FIXED — a real defect, below** |
| `t698_t5_kv_mean_gates` | fixture hash `4d0b592740db9358` ≠ pinned `23d0daab3f087159` | **UNADJUDICATED, below** |

⛔ Read every perf row with the box conditions: four other agent sessions had
cargo and clippy resident throughout. AGENTS.md's rule is that a gate whose
verdict the box can invalidate should REFUSE; a cell that is 99% correctness
assertions and 1% latency bars cannot refuse wholesale, so the six are pinned
by name in `scripts/x86_64_matrix_expected.txt` with a reason each, and the
latency bars are the part to distrust.

### The third defect — a benchmark LLVM deleted

`bench_llmexec_guard_overhead`'s **measured** loop called `verify_tier` on a
`const BENCH_INPUTS` with a default config and **no `black_box` on the
inputs**. In release, LLVM folds every call, precomputes `tier_counts`,
deletes the loop, and `elapsed_guard` reads **0 ns** — so the function
publishes a fabricated `0 ns/call` and `print_llmexec_guard_bench` prints it.
The warmup and the no-op baseline immediately above it already black_box their
inputs; the one loop whose number is REPORTED did not.

Note which assertion caught it: `assert!(ns_guard > 0.0)` is the **only** one a
deleted loop fails — `ns_guard < 1000.0` passes happily on `0.0`. And note the
axis: full_gate's Layer 6b asserts (release × default-features), but it is
`cargo check --tests` — COMPILE only. This had never been EXECUTED there.

### The one left open — `t698_t5_kv_mean_gates`

The test pins a BLAKE3[16] of its seeded `TransformerWeights`, and its own
message says *"never re-base silently"*. So it is **pinned, not re-based**.
What is measured:

- the hash is **`4d0b592740db9358`** here and **stable across debug, release,
  and with/without `+avx2`** — so it is not a codegen or profile artifact;
- the pin `23d0daab3f087159` was **measured at landing** (`892657c1`,
  2026-08-30; the commit message records it), i.e. on the M3;
- `issue_698` **t1/t2/t6/t7** hash the SAME `TransformerWeights::new` stream at
  `n_layer = 1` and **their pins DO reproduce here** — so this is not a blanket
  cross-platform weight-init divergence;
- `gated_mlp`, the only RNG-**drawing** cfg-gated field in that constructor, is
  opt-in and off in this build, and `config.rs` has not changed since the test
  landed;
- `Rng::normal` is Box–Muller over `f32::ln` and `f32::cos`, and measured on
  this box those differ from an f64-then-round reference on **0.26%** and
  **0.20%** of inputs — so a per-platform libm difference is possible *in
  principle*. ⚠ But t1 agrees over ~4k draws, which a ~0.5%-per-draw
  divergence could not survive, so that mechanism is **not** established.
  (The first version of this probe measured 12.8%/62.4% and was WRONG — it
  folded the f32 multiply and `sqrt` rounding into the comparison and measured
  double-rounding, not libm. The corrected probe isolates the call.)

Resolving it needs **one M3 run of this target**, which this box cannot do.
Until then the correct state is a named pin with the measurement written down,
not a re-based constant.

## What the SECOND run found, which is the argument for the script

The matrix was run again against the same commit on the same box an hour
later, as validation of the script itself. Three things moved, and none of them
was a code change:

1. **Two of the six pinned perf bars PASSED** — `bench_176_router_forward_cpu`
   and `g7_throughput_gain_over_plan_218_baseline`. Fewer sibling agent
   sessions had cargo resident. They are **LOAD-SENSITIVE**, not
   x86_64-uncalibrated, and pinning them would have written a box condition
   into a tracked file as if it were a property of the code. **The stale-pin
   wall caught it** — a pin file that only ever loosens would have kept both
   forever. Both rows removed; read any future red on them as a
   box-conditions question first.

2. **`katgpt-pruners` went 3011 → 3010 passed, 1 failed**, on a
   deterministic-looking assertion:
   `test_decompose_neuron_discovers_channels`, *"Token 2 should be the top
   token, got [3, 2, 1, 0]"*. `VocabChannelDecomposer` drew its Householder
   symmetry-breaker from `fastrand`'s **unseeded thread-local global**, so
   `decompose_neuron` was not a function of its arguments — and two tokens tie
   in that fixture, so the perturbation decided the order. Measured across the
   repo: **555 `Rng::with_seed` sites against 11 global-`fastrand` ones**, two
   of them in a shipped pruner's hot path. Fixed (seed derived from the input)
   and filed as
   [Issue 809](../.issues/809_unseeded_global_rng_in_shipped_primitives.md),
   which keeps the other nine as an unread census rather than batch-converting
   them.

⛔ **Read what actually caught (2): not the platform — a SECOND EXECUTION of
the same commit.** This class is invisible to any gate that runs once per
commit, and it could have flipped on the M3's weekly `--lib` lane at any time.
The two runs happened here only because the first was validating a script.

### The latency bars do not reproduce, and the pin file had to stop pretending

Four runs of one commit produced **four different failing sets**:

| run | failing set |
|---|---|
| 1 | six perf bars |
| 2 | `bench_176` and `g7` gone; the katgpt-pruners RNG flake arrives |
| 3 | `g5_roaring` gone; `t08_throughput_rebalance_256x16` arrives |
| 4 | `g7` back and gone again; `goat_6_context_scaling_flat_o1` arrives, never seen before |

A membership pin is the right shape for a stable set and the wrong one for a
churning one — **a pin file re-typed after every run is a diary, not a wall**,
and re-typing it is how a real regression eventually gets absorbed as
*"probably the box again"*.

So the script **re-runs every failure ALONE before adjudicating it**: this
record's own finding, mechanised. A load-sensitive bar passes the second time
and a real failure does not. TRANSIENT rows print — they are what the box did —
and are never counted and never pinned. It cost nothing (everything is built,
and `--exact` makes every other binary run zero tests) and it absorbed two rows
on the first run that had it.

What survives is **three** reproducible rows, and each one says something:
`proof_g3b_swar_speedup` (a bar whose own name is an aarch64 instruction),
`t09_throughput_inv_sqrt_16x16` (an absolute 10 µs target — absolute latency
does not transfer between machines at all) and `t698_t5_kv_mean_gates` (the
fixture hash, above). `g5_roaring_batch_speedup` left on run 4 and its own
message said why all along: `0.0× (roaring=0.00μs, linear=0.00μs)` is **0/0** —
under load both arms fall below the clock granularity, and alone they do not.

## Reproduce

The matrix is a **script** now — `scripts/x86_64_execution_matrix.sh`, landed
with this record. Nine cells run by hand is a session; a census done by hand is
a census that stops being done.

```bash
scripts/x86_64_execution_matrix.sh                       # the matrix
scripts/x86_64_execution_matrix.sh --libs-only           # skip cell 9
scripts/x86_64_execution_matrix.sh --canary              # prove the floors fire
X86_MATRIX_DIR=/f/avx2scratch scripts/x86_64_execution_matrix.sh
```

It refuses off x86_64, exports `+avx2` itself, derives its package list from
the tracked tree (7 measured, against the 3 this issue hand-typed), floors
every cell, and adjudicates failing tests by membership. The raw commands the
2026-09-16 run used, for the record:

```bash
mkdir -p /f/avx2scratch && git archive HEAD | tar -x -C /f/avx2scratch
cd /f/avx2scratch
export RUSTFLAGS="-C target-feature=+avx2"
cargo test -p katgpt-types --lib --all-features -j 6
cargo test -p katgpt-types --test bench_578_avx2_goat --all-features -j 6 --release -- --nocapture
cargo test -p katgpt-core --lib --all-features -j 6
cargo test -p katgpt-attn -p katgpt-dec -p katgpt-pruners -p katgpt-tokenizer --lib --all-features -j 6
cargo test -p katgpt-rs --lib --all-features -j 6
cargo test -p katgpt-rs --tests --no-fail-fast --release -j 6
```

⚠ `--all-features` is **not a supported TEST configuration** in this
workspace (fixture RNG streams and GOAT calibrations are per-feature), so it
is used here as a WIDENING instrument and every failure it produced was
re-run under the single feature that gates it before being called a finding.
That narrowing is what separated cell 8's four from an interaction artifact —
and nothing else in nine cells needed it.

## Addendum (same day, the M3 side) — T6 resolved: the fixture IS arch-dependent

The one M3 run T6 asked for happened hours later (M3 Max, aarch64, same commit
line). Both halves of the measurement now exist:

| quantity | M3 (aarch64) | 4090 (x86_64) |
|---|---|---|
| `issue_698_t5_kv_mean` full test | **PASSES** — pin reproduces | fixture hash `4d0b592740db9358` ≠ pin |
| band bits (Mean vs First max_abs) | `0x3e5f_d968` (2.186028e-1) | `0x3e5f_d970` (2.186029e-1) — one ulp |
| argmax flips (the behavior gate) | 0/12 | 0/12 |
| G1 same-run bit-identity, k=1 Mean≡First bit-exact | pass | pass |

So T6's first branch holds: the pin `23d0daab3f087159` is the aarch64 value and
`4d0b592740db9358` is the x86_64 value of the SAME deterministic-per-platform
fixture — arch-conditional dual pins with the recorded delta, not a re-base.
The n_layer=1 t1 counterargument stands as measured but doesn't reach this
fixture: whether the mechanism is Box–Muller libm ulps at specific draws in the
larger stream (the 0.26%/0.20% per-call divergence the probe above measured is
compatible with ~260k draws producing a different hash while ~4k draws agree) or
something else, the arch-conditional pin is correct under either reading. The
test passes on both platforms post-fix; the `t698_t5_kv_mean_gates` pin row in
`x86_64_matrix_expected.txt` went STALE and was removed in the same commit.

Also from the M3 side (not in any upstream cell): `kda_backward_grad_check`'s
magnitude floor × tolerance (5e-4 × 2.5e-2 = 1.25e-5) was below the test's own
measured FD noise (2.8e-5 absolute on `f_b_proj[127]`, matching the
`f32::EPSILON·|loss|/ε ≈ 2.9e-5` bound) — M3-tuned constants, not a derivation
defect: the L=1 grad check AND the exact token-vs-sequence identity both pass on
x86_64. Floor raised to 2e-3 (budget 5e-5, a 1.8× margin over measured noise);
7/7 on both platforms.

Landing: the fix commit (dual pins + floor + stale-row removal) + this
addendum; issue T6 ticked.
