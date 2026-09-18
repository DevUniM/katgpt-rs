# Issue 843: the `plasma_path` ternary dense matvec is ~1.9× SLOWER than the f32 matvec it replaces (x86_64/AVX2, 1024×1024)

**Status:** OPEN — measured observation, owner-routed. Found incidentally while
benchmarking Issue 839 (Bench 839 arm G2c); it is not a `kron_tile` finding and
is deliberately not folded into that GOAT's verdicts.

## The claim on the flag

`plasma_path` is a **default-on** feature of `katgpt-core`,
`katgpt-transformer` and `katgpt-forward`, and its own manifest comment reads:

> Bit-plane ternary SIMD matvec — **multiplication-free CPU inference** (Plan
> 148, Research 110). […] this now gates the HOT-tier ternary CPU path.

The premise of a multiplication-free path is that it is *cheaper* than the
multiply it removes. At 1024×1024 on this box it is not.

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

- [ ] **T1 — Confirm or refute on a second arch.** `neon_ternary_matvec` vs
      `simd_dot_f32` on the M3. The SWAR/popcount balance is not the same on
      NEON, and this repo's own record (Issue 819) is that an arm nobody
      compiles is an arm nobody has measured. Do NOT generalise the x86_64
      figure before this.
- [ ] **T2 — Sweep the size axis before drawing any conclusion.** 1024×1024 is
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
- No change to `plasma_path`'s default until T1+T2 land. One arch and one size
  is not enough to move a shipped flag, and this file exists so that decision is
  taken on a measurement rather than on this paragraph.
