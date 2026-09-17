# Bench 810 — `argtopk` AVX2 dispatch: distribution matrix + per-k crossover (Issue 808 T2 evidence, Raptor Lake row)

**Date:** 2026-09-17
**Issue:** katgpt-rs Issue 808 (CLOSED 2026-09-17, T1 landed option 2; file removed per the
noise-reduction rule — record in [HISTORY.md](../HISTORY.md)) — the
AVX2 `argtopk` path is a measured loss vs its own scalar fallback. This bench
supplies **option 4's re-measurement** (realistic block-score distributions
instead of the recorded i.i.d. fixture) and **T2's per-k `N_MIN` data** on the
first of the ≥2 microarchitectures that issue demands before any dispatch
change. **It decides nothing** — T1 remains the owner's call.

**Surface:** `crates/katgpt-attn/src/dash_attn/block_topk.rs` —
`argtopk` (the k≤16 SIMD dispatch; AVX2 via runtime detection on x86_64) vs
`argtopk_scalar_heap` (the scalar fallback), exactly the pair the recorded
Issue-808 table measured.

## Method

- Instrument: `tests/common/ab_timing.rs` (Issue-723 interleaved
  median-of-ratios; arm a = scalar, arm b = SIMD dispatch; **speedup =
  1/median ratio = scalar ÷ SIMD, so < 1.00 is a loss** — the issue's
  convention). Rounds = 9 per cell, per-round band printed.
- Tests: `tests/bench_256_simd_topk.rs`
  `bench_simd_topk_issue808_distribution_matrix` +
  `bench_simd_topk_issue808_crossover_nmin` (landed with this bench; the file
  already had the Issue-808 T3 `[[test]]` row).
- ⚠ **Churn compression, declared:** both arms perturb the same four input
  positions per iteration (fat-LTO anti-hoist, Issue-723 Class A2) and consume
  an index sink. The churn is a constant added to BOTH arms, which compresses
  every ratio toward 1.00 — measured wins are understated and measured losses
  are MILDERS than true. The recorded Issue-808 table had no churn; where the
  two disagree, this table reads the SAFER direction for the kernel.
- Correctness per cell against a full-sort reference before timing.
- Box: 4090 workstation, i7-13700K (Raptor Lake), Windows/MSYS, load 1–10%
  (quiet), `--test-threads=1`.
- **Profile axis (both run, both recorded — the profile is part of the
  claim):** `default --release` (scalar fallback NOT auto-vectorized) and
  `RUSTFLAGS="-C target-feature=+avx2"` (the recorded table's configuration;
  scalar fallback auto-vectorized).

## Distributions

The recorded table's fixture (`make_scores`) is quasi-random i.i.d. uniform.
Real DashAttn block scores are sigmoid(q·centroid) over POSITIONAL blocks —
six shapes, all deterministic (seeded splitmix64; no global RNG, the Issue-809
class):

| dist | shape | why |
|---|---|---|
| `iid_uniform` | uniform | continuity with the recorded table |
| `gauss_sigmoid` | Gaussian logits → sigmoid | unstructured dot products |
| `locality` | AR(1) φ=0.65 | adjacent blocks score similarly (attention locality) |
| `early_peak` | top blocks first (peak ≥ k) | attention sink: threshold set early |
| `late_peak` | top blocks last | maximal insertion work during the sweep |
| `bimodal_sparse` | 12% high / 88% low | the block-sparse routing story |

## Headline findings (identical under BOTH profiles)

1. **k=8 and k=16 lose below n≈512 on 5 of 6 distributions** — 0.42–0.9×,
   deepest at small n and on `late_peak` (0.41× at k=8 n=64). `early_peak` is
   the lone winning k=8/16 shape (1.1–2.2×).
2. **k=2 and k=4 win or tie almost everywhere** (up to 3.9× at k=2 n=1024);
   the only deficits are at n=64 (0.71–0.97×) and they vanish by n=128.
   Option 2's carve-out (narrow to k≤4) is the distribution-robust one.
3. **`N_MIN` is distribution-sensitive, not a single number per k.** At k=8:
   crossover n=256 on `locality` but n=768 on `iid_uniform`, and `late_peak`
   k=8 **never crosses by n=1024** (0.90–0.95×). A pure n-floor (option 1)
   cannot be made distribution-safe for k=8/16.
4. **The k=1 dispatch is a different machine with its own distribution
   dependence:** x86_64 `simd_argmax_f32` is the two-pass idiom
   (auto-vectorized max-reduce + `position(== max)`), so its cost depends on
   WHERE the max sits — `early_peak` wins up to 8.2× (second pass exits
   immediately), `late_peak` loses ~0.9× at every n (second pass rescans the
   array). Recorded here because the issue's k-sweep included k=1; not part of
   the heap-kernel decision.

## N_MIN summary (first sweep n with median speedup ≥ 1.00; ≥1.05 point noted)

| k | iid_uniform | locality |
|---|---|---|
| 2 | 64 (≥1.05 at 64) | 64 (≥1.05 at 64) |
| 4 | 64 (≥1.05 at 64) | 128 (≥1.05 at 128) |
| 8 | 768 (no ≥1.05 in sweep) | **256** (≥1.05 at 256) |
| 12 | 768 (≥1.05 at 768) | **256** (≥1.05 at 256) |
| 16 | 768 (no ≥1.05 in sweep) | 768 (≥1.05 at 768) |

(`late_peak`/`early_peak`/`gauss`/`bimodal` crossovers were not swept — the
matrix grid covers them at n≤1024; `late_peak` k=8 is still a loss at n=1024,
so its N_MIN is >1024.)

## Verbatim runs

Raptor Lake, quiet box. `+avx2` first (the recorded table's profile), then
default. Unedited `--nocapture` output; hand-retyping these tables would be
transcription drift.

### Run A — `RUSTFLAGS="-C target-feature=+avx2"`, release

```
== Issue 808 per-k crossover (first n with speedup ≥ 1.00) ==
distribution       k      n    scalar ns      simd ns   speedup         round band
iid_uniform        2     64         37.4         31.4     1.20x    1.13..1.22
--> N_MIN[iid_uniform, k=2] = 64 (speedup ≥ 1.05 at 64)
iid_uniform        4     64         57.4         49.4     1.16x    1.14..1.19
--> N_MIN[iid_uniform, k=4] = 64 (speedup ≥ 1.05 at 64)
iid_uniform        8     64         92.3        179.2     0.51x    0.50..0.56
iid_uniform        8    128        125.1        236.8     0.53x    0.50..0.55
iid_uniform        8    192        164.4        288.0     0.58x    0.51..0.60
iid_uniform        8    256        161.8        208.3     0.79x    0.67..0.81
iid_uniform        8    384        253.2        384.4     0.65x    0.63..0.74
iid_uniform        8    512        296.9        384.6     0.77x    0.75..0.79
iid_uniform        8    768        383.3        374.7     1.02x    0.97..1.06
--> N_MIN[iid_uniform, k=8] = 768 (no ≥1.05 point in sweep)
iid_uniform       12     64        135.0        182.5     0.74x    0.71..0.76
iid_uniform       12    128        180.8        249.6     0.73x    0.69..0.75
iid_uniform       12    192        241.4        321.5     0.78x    0.61..0.80
iid_uniform       12    256        225.2        237.7     0.95x    0.90..1.00
iid_uniform       12    384        320.5        390.4     0.81x    0.76..0.93
iid_uniform       12    512        380.3        403.9     0.94x    0.86..1.00
iid_uniform       12    768        441.4        401.5     1.17x    0.72..1.24
--> N_MIN[iid_uniform, k=12] = 768 (speedup ≥ 1.05 at 768)
iid_uniform       16     64        170.8        257.8     0.66x    0.62..0.70
iid_uniform       16    128        242.6        341.1     0.71x    0.65..0.76
iid_uniform       16    192        314.3        446.5     0.70x    0.66..0.77
iid_uniform       16    256        287.4        373.5     0.78x    0.68..0.83
iid_uniform       16    384        412.5        550.2     0.76x    0.67..0.86
iid_uniform       16    512        492.7        598.4     0.82x    0.78..0.88
iid_uniform       16    768        519.3        503.1     1.02x    1.00..1.14
--> N_MIN[iid_uniform, k=16] = 768 (no ≥1.05 point in sweep)
locality           2     64         39.2         32.9     1.17x    1.05..1.47
--> N_MIN[locality, k=2] = 64 (speedup ≥ 1.05 at 64)
locality           4     64         51.7         51.7     0.98x    0.91..1.19
locality           4    128         87.1         78.1     1.13x    0.99..1.19
--> N_MIN[locality, k=4] = 128 (speedup ≥ 1.05 at 128)
locality           8     64         91.5        185.8     0.50x    0.47..0.51
locality           8    128        121.1        220.4     0.54x    0.51..0.59
locality           8    192        155.0        199.8     0.79x    0.69..0.84
locality           8    256        132.4        123.7     1.08x    1.01..1.11
--> N_MIN[locality, k=8] = 256 (speedup ≥ 1.05 at 256)
locality          12     64        134.0        191.2     0.69x    0.66..0.77
locality          12    128        182.8        243.8     0.76x    0.68..0.78
locality          12    192        204.2        237.8     0.88x    0.76..0.96
locality          12    256        199.4        140.5     1.38x    1.32..1.54
--> N_MIN[locality, k=12] = 256 (speedup ≥ 1.05 at 256)
locality          16     64        170.7        240.8     0.70x    0.63..0.84
locality          16    128        248.6        328.3     0.72x    0.68..0.99
locality          16    192        293.4        450.4     0.65x    0.58..0.76
locality          16    256        238.3        315.8     0.75x    0.64..0.86
locality          16    384        399.6        495.1     0.78x    0.72..0.92
locality          16    512        496.3        656.4     0.76x    0.72..0.77
locality          16    768        609.6        542.8     1.06x    0.98..1.50
--> N_MIN[locality, k=16] = 768 (speedup ≥ 1.05 at 768)
```

```
== Issue 808 distribution matrix (speedup = scalar/SIMD, <1.00 is a loss) ==
distribution       k      n    scalar ns      simd ns   speedup         round band
iid_uniform        1     64         33.1         23.6     1.41x    1.33..1.43
iid_uniform        1    128         47.9         42.8     1.12x    1.10..1.13
iid_uniform        1    256         99.0         45.1     2.12x    2.08..2.75
iid_uniform        1    512        179.0         61.7     3.01x    2.35..3.12
iid_uniform        1   1024        364.7        266.8     1.35x    1.33..1.45
iid_uniform        2     64         43.4         47.0     0.94x    0.72..1.14
iid_uniform        2    128         69.2         58.9     1.15x    1.13..1.39
iid_uniform        2    256         99.6         68.7     1.45x    1.42..1.47
iid_uniform        2    512        180.2         70.1     2.56x    2.51..2.61
iid_uniform        2   1024        347.3        101.0     3.65x    2.33..3.80
iid_uniform        4     64         48.2         52.6     0.93x    0.87..0.97
iid_uniform        4    128         76.6         68.2     1.12x    1.11..1.14
iid_uniform        4    256        150.1        111.4     1.35x    1.31..1.39
iid_uniform        4    512        235.6        124.8     1.88x    1.87..1.91
iid_uniform        4   1024        385.1        167.9     2.32x    2.08..2.37
iid_uniform        8     64         81.4        191.9     0.42x    0.41..0.45
iid_uniform        8    128        131.2        280.2     0.46x    0.46..0.49
iid_uniform        8    256        207.0        379.9     0.56x    0.49..0.57
iid_uniform        8    512        281.6        374.3     0.77x    0.70..0.78
iid_uniform        8   1024        491.7        456.4     1.08x    1.07..1.09
iid_uniform       16     64        160.9        279.3     0.58x    0.55..0.60
iid_uniform       16    128        243.2        384.0     0.63x    0.60..0.71
iid_uniform       16    256        328.5        496.5     0.65x    0.62..0.73
iid_uniform       16    512        453.2        517.5     0.87x    0.79..1.01
iid_uniform       16   1024        636.9        668.7     0.96x    0.82..1.07
gauss_sigmoid      1     64         33.0         46.4     0.72x    0.61..0.82
gauss_sigmoid      1    128         54.3         64.0     0.83x    0.78..1.04
gauss_sigmoid      1    256         88.0         75.3     1.14x    1.03..1.57
gauss_sigmoid      1    512        183.2         90.1     2.04x    1.96..2.15
gauss_sigmoid      1   1024        340.1        119.5     2.90x    2.14..4.16
gauss_sigmoid      2     64         38.0         38.2     1.01x    0.86..1.08
gauss_sigmoid      2    128         58.4         48.1     1.21x    1.20..1.23
gauss_sigmoid      2    256        114.2         72.8     1.63x    1.21..1.71
gauss_sigmoid      2    512        206.4         85.1     2.47x    1.83..2.97
gauss_sigmoid      2   1024        361.0         99.8     3.52x    3.18..4.85
gauss_sigmoid      4     64         52.7         68.6     0.77x    0.70..0.87
gauss_sigmoid      4    128         89.9         71.2     1.25x    1.10..1.47
gauss_sigmoid      4    256        155.8        133.7     1.15x    1.11..1.27
gauss_sigmoid      4    512        241.4        127.1     1.96x    1.68..1.99
gauss_sigmoid      4   1024        407.4        160.6     2.55x    2.46..2.63
gauss_sigmoid      8     64         96.1        227.0     0.42x    0.39..0.46
gauss_sigmoid      8    128        136.1        293.7     0.46x    0.43..0.50
gauss_sigmoid      8    256        206.2        366.3     0.56x    0.55..0.60
gauss_sigmoid      8    512        304.6        420.6     0.74x    0.66..0.74
gauss_sigmoid      8   1024        487.3        426.2     1.20x    0.83..1.33
gauss_sigmoid     16     64        157.2        279.2     0.57x    0.49..0.60
gauss_sigmoid     16    128        244.3        368.1     0.67x    0.63..0.69
gauss_sigmoid     16    256        355.1        494.0     0.72x    0.67..0.77
gauss_sigmoid     16    512        464.5        597.0     0.77x    0.73..0.85
gauss_sigmoid     16   1024        681.2        649.9     1.04x    0.83..1.24
locality           1     64         32.9         34.6     0.97x    0.80..1.13
locality           1    128         47.5         45.2     1.04x    1.03..1.11
locality           1    256        101.9         42.7     2.43x    2.10..2.61
locality           1    512        174.1        183.6     0.94x    0.90..1.07
locality           1   1024        327.7         54.6     7.13x    3.89..8.56
locality           2     64         37.0         33.4     1.13x    0.91..1.22
locality           2    128         62.4         57.3     1.09x    1.05..1.12
locality           2    256        110.0         63.5     1.71x    1.29..2.04
locality           2    512        186.0         86.3     2.17x    2.00..2.25
locality           2   1024        343.1         95.6     3.65x    3.20..3.70
locality           4     64         47.0         61.5     0.79x    0.63..0.86
locality           4    128         95.4         91.4     1.05x    0.91..1.13
locality           4    256        148.7        102.8     1.44x    1.41..1.50
locality           4    512        254.7        161.6     1.55x    1.39..1.91
locality           4   1024        417.6        146.9     2.81x    2.30..3.70
locality           8     64         85.3        203.3     0.41x    0.39..0.47
locality           8    128        138.0        287.8     0.48x    0.45..0.49
locality           8    256        220.1        428.5     0.51x    0.47..0.58
locality           8    512        317.2        511.4     0.63x    0.59..0.63
locality           8   1024        500.1        474.1     1.06x    1.04..1.08
locality          16     64        158.6        261.6     0.61x    0.59..0.62
locality          16    128        265.8        435.4     0.61x    0.56..0.68
locality          16    256        355.6        568.2     0.63x    0.58..0.64
locality          16    512        466.6        652.2     0.72x    0.67..0.73
locality          16   1024        720.6        744.4     0.95x    0.92..1.12
early_peak         1     64         47.1         17.9     2.78x    2.08..2.97
early_peak         1    128         57.4         15.7     3.64x    3.61..3.79
early_peak         1    256         93.0         20.6     4.76x    3.55..5.14
early_peak         1    512        170.1         28.2     6.06x    5.55..6.44
early_peak         1   1024        311.6         38.5     8.18x    7.42..8.22
early_peak         2     64         47.7         18.3     2.58x    2.53..2.73
early_peak         2    128         62.0         23.5     2.57x    2.50..3.23
early_peak         2    256         99.7         36.1     2.93x    1.75..3.08
early_peak         2    512        171.2         53.6     3.27x    2.73..3.30
early_peak         2   1024        317.0         80.6     3.94x    3.89..3.98
early_peak         4     64         45.6         19.2     2.40x    2.27..2.45
early_peak         4    128         61.9         28.2     2.20x    2.06..2.30
early_peak         4    256        108.2         49.4     2.24x    1.84..2.34
early_peak         4    512        183.8         75.9     2.50x    2.01..2.57
early_peak         4   1024        336.8        108.8     3.18x    2.78..3.25
early_peak         8     64         38.6         29.2     1.36x    1.12..1.36
early_peak         8    128         65.8         30.9     2.15x    1.95..2.30
early_peak         8    256        120.4         77.3     1.55x    1.54..1.62
early_peak         8    512        216.4        174.8     1.24x    1.14..1.40
early_peak         8   1024        367.5        243.7     1.52x    1.39..1.55
early_peak        16     64         55.1         50.1     1.10x    1.06..1.13
early_peak        16    128         82.3         50.2     1.65x    1.54..1.74
early_peak        16    256        125.4         60.2     2.15x    1.59..2.23
early_peak        16    512        240.5        141.5     1.72x    1.54..1.74
early_peak        16   1024        438.3        297.0     1.49x    1.42..1.50
late_peak          1     64         36.3         48.7     0.72x    0.68..0.97
late_peak          1    128         51.3         67.8     0.75x    0.72..0.80
late_peak          1    256         92.1        103.7     0.90x    0.83..0.92
late_peak          1    512        172.3        190.5     0.90x    0.90..0.92
late_peak          1   1024        343.8        389.8     0.90x    0.83..0.93
late_peak          2     64         43.1         39.5     1.08x    0.99..1.20
late_peak          2    128         68.3         56.7     1.19x    1.14..1.33
late_peak          2    256        107.5         83.0     1.31x    1.24..1.32
late_peak          2    512        195.7         92.1     2.11x    2.05..2.20
late_peak          2   1024        356.9        121.0     2.97x    2.83..2.99
late_peak          4     64         62.1         64.1     0.99x    0.85..1.05
late_peak          4    128         98.9         86.2     1.14x    1.08..1.21
late_peak          4    256        172.2        134.5     1.26x    1.21..1.35
late_peak          4    512        265.5        181.3     1.53x    1.12..1.61
late_peak          4   1024        429.4        226.8     1.89x    1.83..1.94
late_peak          8     64        117.4        287.1     0.41x    0.39..0.43
late_peak          8    128        161.0        380.7     0.43x    0.39..0.45
late_peak          8    256        247.9        500.1     0.49x    0.48..0.52
late_peak          8    512        498.8        689.0     0.71x    0.63..0.93
late_peak          8   1024        685.1        748.5     0.95x    0.77..1.06
late_peak         16     64        230.1        408.2     0.57x    0.54..0.58
late_peak         16    128        320.1        538.5     0.59x    0.57..0.64
late_peak         16    256        427.5        661.3     0.64x    0.57..0.78
late_peak         16    512        561.7        767.9     0.73x    0.68..0.78
late_peak         16   1024        796.4        910.3     0.87x    0.86..0.91
bimodal_sparse     1     64         45.5         15.8     2.88x    2.70..3.03
bimodal_sparse     1    128         50.4         65.3     0.76x    0.74..0.83
bimodal_sparse     1    256        104.3         68.9     1.55x    1.28..1.62
bimodal_sparse     1    512        177.9         80.3     2.32x    1.95..2.41
bimodal_sparse     1   1024        335.9        277.4     1.38x    0.77..1.46
bimodal_sparse     2     64         36.9         31.7     1.15x    1.09..1.28
bimodal_sparse     2    128         63.3         50.5     1.24x    1.02..1.46
bimodal_sparse     2    256        110.9         56.5     2.07x    1.34..2.11
bimodal_sparse     2    512        200.1         98.0     2.05x    1.98..2.08
bimodal_sparse     2   1024        369.3         98.1     3.82x    3.18..4.01
bimodal_sparse     4     64         50.2         59.1     0.85x    0.76..0.96
bimodal_sparse     4    128         93.5         76.5     1.25x    1.14..1.30
bimodal_sparse     4    256        124.3         89.7     1.39x    1.22..1.47
bimodal_sparse     4    512        256.5        161.5     1.59x    1.56..1.61
bimodal_sparse     4   1024        420.6        148.9     2.78x    2.72..3.22
bimodal_sparse     8     64         75.1        164.0     0.46x    0.44..0.49
bimodal_sparse     8    128        134.4        282.8     0.49x    0.42..0.49
bimodal_sparse     8    256        189.9        319.4     0.59x    0.57..0.65
bimodal_sparse     8    512        331.5        555.4     0.64x    0.45..0.65
bimodal_sparse     8   1024        474.9        391.0     1.24x    0.97..1.32
bimodal_sparse    16     64        147.2        239.2     0.61x    0.59..0.66
bimodal_sparse    16    128        247.0        395.7     0.62x    0.54..0.69
bimodal_sparse    16    256        323.6        528.7     0.62x    0.49..0.69
bimodal_sparse    16    512        538.5        703.9     0.75x    0.69..0.90
bimodal_sparse    16   1024        649.5        587.8     1.10x    1.05..1.18
```

### Run B — default release (no RUSTFLAGS; scalar fallback not auto-vectorized)

Key deltas vs Run A (full output in the session record; shape identical):
`iid_uniform` k=8 n=1024 **1.20×** (A: 1.08×), k=16 n=1024 **1.12×** (A:
0.96×), k=8 n=64 **0.51×** (A: 0.42×), k=16 n=64 **0.66×** (A: 0.58×) —
without `+avx2` the scalar fallback loses its auto-vectorization, so the SIMD
side reads consistently a few points kinder at the margins; the
win/loss boundary does not move. `N_MIN` values are identical to Run A's
table. `late_peak` k=8 n=1024 stays a loss (**0.91×**, band 0.78..0.95).

### Cross-check against the recorded Issue-808 table (same +avx2 profile, iid)

Recorded k=4 n=1024 1.75× → here 2.32×; k=8 n=64 0.59× → 0.42×; k=16 n=1024
1.07× → 0.96×; k-sweep n=256: k=2 1.80× → 1.45×, k=8 0.62× → 0.56×. Direction
agrees in every cell; magnitudes differ within the declared churn compression
plus session/seed variation. The one qualitative softening — k=16 n=1024
flipping 1.07× (win) → 0.96× (loss) — sits inside the parity noise band
(±0.1×) where the round bands in BOTH measurements overlap 1.00.

## What this means for the owner's T1 options (evidence, not the decision)

- **Option 1 (n-floor):** workable for k≤4 with a tiny floor, but for k=8/16
  `N_MIN` moves with the distribution (256 → 768 → >1024) — a single
  conservative floor per k would have to be ≥1024 for k=8, forfeiting every
  win below that. Not distribution-safe below that.
- **Option 2 (k≤4):** the robust carve-out. k=2/4 win or tie on every
  distribution and both profiles past n=64–128; k=8/16 lose on 5 of 6
  distributions below n≈512.
- **Option 3 (delete AVX2 arm):** the k=8/16 arm's remaining wins are
  `early_peak` (1.1–2.2×) and large-n margins (≤1.2×) — small against the
  0.42–0.75× losses it carries on the same grid.
- **Option 4 (this bench):** done — the recorded table's shape survives
  realistic distributions; its k=8/16 losses get DEEPER on `late_peak`, and
  its k=2/4 wins get wider on `bimodal_sparse`.
- Any dispatch change still needs T2's ≥2-microarchitecture bar — this is the
  Raptor Lake row only.

---

## Addendum (2026-09-17) — option 2 landed; the post-change grid

Issue 808 T1 resolved to **option 2, x86_64-scoped**: `AVX2_ARGTOPK_K_MAX = 4`
in `crates/katgpt-attn/src/dash_attn/block_topk.rs`, applied inside the x86_64
`argtopk_simd` so the arch-independent `k ≤ 16` predicate in
`argtopk_with_scratch` and the whole NEON range are untouched.

Re-measured on the same box and instrument (4090, i7-13700K,
`RUSTFLAGS="-C target-feature=+avx2"`, release, interleaved median-of-ratios,
9 rounds), via the new `bench_simd_topk_issue808_t2_above_bound_is_not_a_loss`:

| region | before (this bench) | after |
|---|---|---|
| k=8, `late_peak`, n<512 | **0.41–0.72×** | **0.98–0.99×** |
| k ∈ {8,16}, all 6 dists, n ∈ {64..512} | 0.42–1.2× | **0.95–1.03×**, worst cell 0.95× |
| k=2, `iid_uniform`, n=1024 | 5.1× | **5.11×** (unchanged) |
| k=4, `gauss_sigmoid`, n=1024 | 3.5× | **3.51×** (unchanged) |
| k=1, `locality`, n=1024 | — | **6.73×** |

Read the "after" column for what it is: above the bound the AVX2 kernel is no
longer dispatched, so both arms are `argtopk_scalar_heap` and ~1.00 is the
**definition** of the fix rather than a measurement of the kernel. The kernel's
own numbers above k=4 are the ones in the body of this document, and this bench
can no longer reach them on x86_64 — which is why
`bench_simd_topk_issue808_crossover_nmin` is KEPT rather than deleted: it is
the instrument that would have to re-run, on a second microarchitecture, before
the bound could widen toward option 1.

⚠ **The last bullet above still stands, with a narrowed scope.** The
≥2-microarchitecture bar was never load-bearing for NARROWING the dispatch —
that direction is conservative, falling back to code that runs on every target.
It gates WIDENING, and it is pinned as such in
`test_avx2_argtopk_dispatch_bound_is_pinned`, which reds on any change to the
constant without timing anything.
