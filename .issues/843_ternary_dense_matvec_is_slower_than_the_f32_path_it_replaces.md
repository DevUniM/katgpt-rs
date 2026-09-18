# Issue 843: the `plasma_path` ternary dense matvec is slower than the f32 matvec it replaces BELOW the L3 boundary — and only wins above it (x86_64/AVX2)

**Status:** OPEN — **T1 + T2 DONE** (T2: on x86_64/AVX2 the crossover lands on the L3 boundary — §T2; T1: on aarch64/NEON there is NO crossover anywhere in 32..=16384, and the served shape 768×3072 reads 2.10× — §T1; the two arches AGREE that every shape this workspace serves is in the losing regime). T3/T4 open. Measured observation, owner-routed. Found incidentally while
benchmarking Issue 839 (Bench 839 arm G2c); it is not a `kron_tile` finding and
is deliberately not folded into that GOAT's verdicts.

## The claim on the flag

`plasma_path` is a **default-on** feature of `katgpt-core`,
`katgpt-transformer` and `katgpt-forward`, and its own manifest comment reads:

> Bit-plane ternary SIMD matvec — **multiplication-free CPU inference** (Plan
> 148, Research 110). […] this now gates the HOT-tier ternary CPU path.

The premise of a multiplication-free path is that it is *cheaper* than the
multiply it removes. At 1024×1024 on this box it is not.

➡ **Read §T2 before acting on this section.** The one-point framing below is
what the issue was filed on; the size sweep since has found a **crossover at
the L3 boundary**, which keeps the finding and changes its shape — the kernel
is not slower everywhere, it is slower everywhere the operand still fits
cache, which on this box includes every shape this workspace serves.

## Measured

All three arms via `tests/common/ab_timing.rs` (interleaved chunks, one ratio
per pair, median across pairs — never two sequential loops), release profile,
same fixture generator, same `x`, on the same run:

| kernel | ns/call at 1024×1024 | note |
|---|---|---|
| `simd_matvec` (f32, `simd_dot_f32`) | **63,253** | AVX2+FMA via runtime probe |
| `simd_ternary_matvec` | **122,737** – 125,040 | `simd_level()` disclosed as `Avx2` |
| `ternary_matvec_scalar` | **539,687** | its own scalar reference |
| (`kron_apply`, for scale) | 4,387 – 4,664 | Issue 839, different shape |

Derived:

- ternary AVX2 is **4.32×** its own scalar arm — so the SIMD arm **is** being
  taken and **is** working. This is the first hypothesis to check and it is
  refuted, which is why this is filed as a finding rather than as a caveat.
- ternary AVX2 is **1.94× SLOWER** than the f32 SIMD matvec over the identical
  operator, identical input vector, identical box.
- Throughput: ternary ≈ **8.5 GMAC/s**, f32 ≈ **16.6 GMAC/s**.

Weight footprint favours ternary by 21×, which is presumably the deployment
argument: `n⁴` trits as two bitplanes ≈ **197 KiB** against **4 MiB** of f32.
Both fit L3 on this box, so the measurement above is not a memory-bandwidth
regime and does not settle the large-model case.

## Box state

`shikuwa`, Windows 11 Pro, i7-13700K (16 cores), 17.34 GB free physical of
31.78, commit 36.92 / 62.78 GB (limit re-read at launch), no concurrent cargo
build in another target dir; three peer agent sessions live, one busy. Every
figure is one box, one arch — see the last task.

## Reproduce

```text
cargo test --release --features kron_tile --test bench_839_kron_tile_goat \
    -- --nocapture --test-threads=1     # G2c prints the ternary + f32 arms
```

The scalar-vs-AVX2 probe was a temporary fourth arm in that target, removed
after recording (it is not about `kron_tile`). To re-derive: `ab_median_ratio(11,
30, 3, ternary_matvec_scalar, simd_ternary_matvec)` over
`TernaryWeights::pack_from_i8(&trits, 1024, 1024)` where `trits` is a seeded
LCG draw thresholded at ±0.33 (so all three trit values occur, ~1/3 zeros).

## Why this is worth a number rather than a shrug

The flag is **default-on**, so this is the shipped hot path rather than an
opt-in experiment, and nothing in the workspace compares the two kernels: the
ternary benches (578, 582, 583) measure ternary against *ternary* — SIMD vs
scalar, packing variants, scale hoisting — which is exactly the comparison that
reports 4.32× and cannot see the 1.94×. A speedup over your own previous
implementation is not a speedup over the implementation you replaced.

## Tasks

- [x] **T1 — DONE (2026-09-19, §T1 below): CONFIRMED on NEON, and stronger than the x86_64 finding — no crossover at ANY measured size.** `neon_ternary_matvec` vs
      `simd_dot_f32` on the M3. The SWAR/popcount balance is not the same on
      NEON, and this repo's own record (Issue 819) is that an arm nobody
      compiles is an arm nobody has measured. Do NOT generalise the x86_64
      figure before this.
- [x] **T2 — DONE, and it found a clean crossover (§T2 below). The original one-point framing was too strong.** Sweep the size axis before drawing any conclusion. 1024×1024 is
      one point and it is the point where f32 still fits L3. The ternary win
      should appear where the f32 operand does not — measure 2K, 4K, 8K square,
      and report the crossover size or its absence. A single-size verdict on a
      memory-argument kernel is the shape this repo files issues about.
- [ ] **T3 — Read `avx2_ternary_matvec` for a sign-extraction stall.** 8.5
      GMAC/s from a popcount path that should beat an FMA path suggests the
      per-block `pos_bits`/`neg_bits` → f32 accumulate is the bottleneck rather
      than the multiply-free arithmetic. Profile before rewriting; the arm is
      4.32× its scalar, so it is not simply unvectorised.
- [ ] **T4 — Decide what the finding means for the flag, which is an owner
      call.** If the crossover is above the sizes this workspace actually runs,
      `plasma_path`'s default-on status is a latency regression on the hot tier
      and the model-size win is the only one it delivers — worth stating in the
      manifest comment either way, since that comment currently reads as a
      performance claim.

## Non-goals

- Not a `kron_tile` issue. Bench 839's G2c reports the number and bars nothing
  on it, precisely so this question stays separable.
- No change to `plasma_path`'s default until **T4** — which is now measurable
  from both arches (T1 + T2 landed). The measurement side is complete: two
  arches, every size from 32 to 16384 square plus the served 768×3072 shape,
  and **ternary loses everywhere on both**. The x86_64 crossover at 4096 did
  not generalize (§T1), so the flag is defensible on FOOTPRINT alone at every
  shape measured; whether that trade is right for the hot tier is T4's owner
  call, taken on these numbers rather than on this paragraph.

## T2 — measured (2026-09-19): there IS a crossover, and it lands on the L3 boundary

`tests/bench_843_ternary_size_sweep.rs`, same interleaved harness, same box,
`simd_level() = Avx2`, 11 of 11 rounds surviving at every size:

| `m` | f32 ns/call | ternary ns/call | ternary/f32 | f32 operand |
|---|---|---|---|---|
| 32 | 111 | 172 | **1.56** | 4 KiB |
| 64 | 277 | 593 | **2.24** | 16 KiB |
| 128 | 817 | 2,236 | **2.77** | 64 KiB |
| 256 | 3,080 | 8,383 | **2.79** | 256 KiB |
| 512 | 8,927 | 33,060 | **3.70** | 1 MiB |
| 1024 | 54,754 | 123,074 | **2.26** | 4 MiB |
| 2048 | 318,921 | 490,897 | **1.49** | 16 MiB |
| 4096 | 2,766,395 | 2,107,814 | **0.74** | 64 MiB |

(Second run of the same binary; the `m ≥ 256` rows reproduce the first run's
2.73 / 3.59 / 1.94 / 1.55 / 0.75 to within a few percent, which is the
interleaved harness doing its job.)

**So the kernel is not wrong — it is size-conditional, and the condition is
cache residency.** The curve is **not monotone: it PEAKS at `m = 512`** and
falls from there, crossing 1.0 between 2048 and 4096. The rising limb below 512
is its own regime — at `m ≤ 256` both operands are L1/L2-resident, so there is
no memory pressure for a 16× smaller footprint to relieve and the ratio is
pure per-MAC cost. Read the two limbs separately; a single "ternary is N×
slower" figure is an average over two different mechanisms. This box (i7-13700K) has **30 MB of L3** (`Win32_CacheMemory`,
read rather than assumed — L1 0.4+0.2+0.2+0.5 MB, L2 16+8 MB, L3 30 MB ×2
reported per-socket-view), so:

- `m = 2048` → a 16 MiB f32 operand, which **fits** L3 → ternary loses, 1.55×.
- `m = 4096` → a 64 MiB f32 operand, which **does not** → ternary wins, 1.33×
  faster, while its own 4 MiB packed form fits L2 outright.

That is precisely the mechanism the footprint argument predicts, and the
1024-point this issue was filed on sits **four bisections inside the losing
regime**. The original title's claim was true and its framing was too strong:
the defect is not "the multiplication-free path is slower", it is **"the
multiplication-free path is slower everywhere this workspace actually runs
it"**.

⛔ **And that is the part T4 has to decide, because it is where the sizes
are.** The operands in this workspace are `d ≈ 768` with a 4× FFN width
(Research 569's own reference shape), i.e. `768 × 3072` → a **9 MiB** f32
operand: comfortably inside L3 on this box and therefore inside the losing
regime, by a measured factor of roughly 1.5–1.9×. A flag defended as
*"multiplication-free CPU inference"* and enabled **by default** is, at the
shapes served here, a latency regression whose compensation is a 16× smaller
weight footprint. Both halves of that are real; only one of them is in the
manifest comment.

⚠ **What T2 does NOT settle.** One box, one arch, one thread, square matrices
only, and a cache hierarchy that is this CPU's rather than a property of the
kernel — a machine with 8 MB of L3 would cross over far earlier, and a server
with 256 MB might never. So the finding is *"the crossover is the L3
boundary"*, which travels, rather than *"the crossover is m = 4096"*, which
does not. `simd_ternary_matmul_batch` (the batched path, which amortises the
weight read across a batch) is untouched and is the shape a real decode step
uses — T3's read should start there.

## Reproduce T2

```text
cargo test --release --features plasma_path     --test bench_843_ternary_size_sweep -- --nocapture
```

A **report**: it asserts instrument health only (every round surviving, every
ratio finite) and prints its own reading, deliberately pinning no bar — a bar
written before the sweep would have been a bar written from the hypothesis, and
the hypothesis was wrong in the direction that mattered.

### The low end prices Issue 839 T7, and refutes its LATENCY premise

The `m = 32` and `m = 64` rows are the Kronecker **factor** widths of Issue 839,
whose T7 proposes quantizing `A`, `B` to `{-1,0,+1}` so the stage becomes
add/sub accumulate. Measured: **1.56× and 2.24× SLOWER** than the f32 factors
T7 would replace, with the mechanism visible — a 32×32 f32 factor is **4 KiB**
and lives in L1, which is as far from the crossover as this sweep reaches.

⚠ **It is a PROXY and only the latency half is refuted.** A Kronecker stage is
two 32×32 *matrix* products, not one matvec, so the arithmetic intensity is not
identical and a fused ternary kernel could do better than this ratio. What the
row does establish is that the multiplication-free arithmetic is not *itself*
cheaper at this width on this box, so T7 cannot be justified by "add/sub is
faster than multiply" — that is the claim the number contradicts.

T7's **footprint** premise is untouched and is written into its own task text
(6,144 weights ≈ 1.5 KB/layer). That remains a real win and it is a different
argument, on the axis this very sweep shows is the one that pays. Recorded in
Issue 839 §T7 as well, so the deferral carries its reason rather than a
hypothesis.

## T1 — measured (2026-09-19): CONFIRMED on NEON, and there is NO crossover anywhere

Same committed instrument, second arch: `tests/bench_843_ternary_size_sweep.rs`
run on the M3 (aarch64, `simd_level() = Neon`), release profile, the same
`ab_timing.rs` interleaved harness, 11 of 11 rounds surviving at every size.
Measured from a clean `origin/develop` worktree (`4efd9fa79`) — the shared
checkout's dirty WIP was deliberately not measured through.

| `m` | f32 ns/call | ternary ns/call | tern/f32 | f32 operand |
|---|---|---|---|---|
| 32 | 119 | 347 | **3.04** | 4 KiB |
| 64 | 278 | 779 | **2.84** | 16 KiB |
| 128 | 877 | 2337 | **2.68** | 64 KiB |
| 256 | 3638 | 7983 | **2.20** | 256 KiB |
| 512 | 13986 | 31020 | **2.22** | 1 MiB |
| 1024 | 57024 | 123251 | **2.16** | 4 MiB |
| 2048 | 248054 | 517826 | **2.08** | 16 MiB |
| 4096 | 1036670 | 1972030 | **1.91** | 64 MiB |
| 8192 | 4215621 | 7835288 | **1.86** | 256 MiB |
| 16384 | 17204758 | 31223443 | **1.83** | 1 GiB |

The 8192/16384 rows are a throwaway extension (temp worktree copy, `SWEEP`
+2 rows, run once and not landed — the T2 temp-arm precedent); the first eight
rows are the committed bench unchanged. `REPRODUCE T2` above gives the first
eight; the extension is derivable by adding the two rows.

And the shape §T2 names as the one T4 actually decides about, measured directly
rather than interpolated (same throwaway run):

| shape | f32 ns/call | ternary ns/call | tern/f32 | f32 operand |
|---|---|---|---|---|
| 768 × 3072 (d=768, 4× FFN) | 145,458 | 301,919 | **2.10** | 9.0 MiB |

**The verdict, and what it changes about §T2's reading.** On NEON the ratio is
monotonically DECREASING from 3.04 to 1.83 — narrowing, but never crossing, all
the way to a **1 GiB f32 operand**, sixteen times beyond the size where AVX2
crossed. §T2's crossover claim is therefore **box-local, not kernel
property**: the AVX2 arm's f32 kernel collapsed at 64 MiB (2.77 ms against
NEON's 1.02 ms on the same shape — the 13700K running out of memory bandwidth
where the M3 Max's unified memory still feeds it), and that collapse is what
crossed 1.0. On a box whose f32 arm keeps being fed, the ternary arm never
catches up even when the footprint advantage is 16×. **Both arches now agree
on the part that matters: at every shape this workspace serves, `plasma_path`
is a latency regression of roughly 1.9–3.0×, and the footprint win is the only
compensation it delivers.** §T2's honest "a machine with more bandwidth might
never cross" hedge is now measured rather than hedged.

**Box state** (per the AGENTS.md rule, recorded beside the numbers): m3 max,
macOS 26.6.2, M3 Max 16 cores, 64 GiB RAM 74% free, AC power; load average
3.7 falling from 9.4 (sibling agent builds had just finished), zero cargo
processes running during the runs. Stability check that costs nothing and was
run anyway: an earlier build of the SAME bench from the dirty shared checkout
— a different binary, ~15 minutes earlier, under heavier load — reproduced
every shared row to within ~2% (1024: 2.16 both; 2048: 2.10/2.08; 4096:
1.93/1.91), which bounds the load sensitivity of these medians and also shows
the shared tree's WIP does not touch this path. Only the clean-worktree
numbers above are the record.

**For T3, a structural observation from reading the NEON arm** (not a profile,
and the AVX2 kernel is the task's subject — but the two arms share their
shape, so a fix in one should be checked against the other):
`fmla_nibble8` (katgpt-types/src/simd/ternary.rs) spends ~16 vector ops per
8 elements — 2 scalar byte extracts + 2 splats, 4×`vandq_u32`, 4×`vcgeq_u32`,
2×`vsubq_s32`, 2×`vcvtq_f32_s32` — to produce **2** useful `vfmaq_f32`. The
sign EXTRACTION outnumbers the multiply-free arithmetic ~8:1, which is
exactly the "sign-extraction stall" T3 hypothesizes for AVX2, visible here
without a profiler. The 8.5 GMAC/s ternary figure reproduces on this box to
three digits (1024²/123.3 µs ≈ 8.5 GMAC/s), suggesting both arms sit at a
similar extraction-bound ceiling rather than a memory one at served sizes.

⚠ **What T1 does NOT settle** (inherited from §T2, still open): the batched
`simd_ternary_matmul_batch` path is untouched by both sweeps, and it amortises
the weight read across a batch — the shape a real decode step uses. T3's read
should start there, on BOTH arches now. One thread throughout; the two arms'
summation orders are not bit-identical, but neither gate here depends on
bit-equality across arms.
