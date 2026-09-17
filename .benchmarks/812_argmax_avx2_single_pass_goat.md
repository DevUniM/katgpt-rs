# Bench 812 — AVX2 single-pass `argmax` port: measured NEGATIVE, dispatch reverted (Issue 817)

**Date:** 2026-09-17
**Issue:** Issue 817 (filed and closed same day — removed under the noise
reduction rule; this doc is the durable record; the number 812 not 811: the
sibling plan-599 GOAT landed `.benchmarks/811_set_admission_goat.md` on
origin mid-session — the one dual-allocation the gate exists for, renumbered
per the collision rule)
**Origin:** [Bench 810](810_argtopk_distribution_crossover.md) measured that
the x86_64 `simd_argmax_f32` two-pass idiom (`simd_max_f32` reduce +
`position(== max)`) costs two full scans when the maximum sits late
(`late_peak` k=1 lost ~0.9× at every n) — and `argmax.rs` carried a standing
offer to port the NEON single-pass kernel to AVX2 "once it can be verified on
x86."
**Verdict: NEGATIVE — demote-on-loss applied; the port was reverted the same
day.** The two-pass stays. Reopen instrument:
`crates/katgpt-types/tests/bench_817_argmax_dispatch_ab.rs`.

## What was measured

The NEON single-pass structure ported to AVX2 (8 lanes tracking (max value,
index) via `cmp_ps` + `blendv` on strict-`>`, 8-lane reduce (value desc, index
asc), scalar tail `n % 8`, runtime-gated by the shared
`is_avx2_fma_available()` CPUID dispatcher) versus the incumbent two-pass —
arm b = live `simd_argmax_f32` dispatch, arm a = the two-pass idiom verbatim.
Correctness held everywhere (the existing known-answer + randomized-tie sweep,
a new tail-boundary sweep at the AVX2 `len % 8` boundaries including
max-in-last-tail, 4096-element buffers, and a NaN no-panic/in-range pin).

Shapes: `iid` (uniform — max position uniform), `early` (planted max at n/20),
`mid` (n/2), `late` (n−1−n/20). `speedup = two_pass ÷ dispatch`, so **> 1.00
favors the kernel**.

## Results (i7-13700K Raptor Lake, quiet box, interleaved median-of-ratios, rounds=9)

### Run A — default release

```
== Issue 817 argmax dispatch A/B (speedup = two_pass/dispatch, >1.00 dispatch wins) ==
shape         n   twopass ns  dispatch ns   speedup         round band
iid          64         43.6         23.3     1.87x    1.79..1.98
iid         256         43.1         60.9     0.67x    0.65..0.82
iid        1024         60.1        238.8     0.24x    0.22..0.32
iid        4096        469.5        982.8     0.41x    0.34..0.94
early        64         19.0         25.7     0.71x    0.66..0.86
early       256         19.9         58.8     0.34x    0.34..0.35
early      1024         54.3        232.6     0.22x    0.21..0.30
early      4096        189.2        924.1     0.20x    0.20..0.22
mid          64         24.9         24.3     1.04x    0.97..1.05
mid         256         64.9         59.4     1.09x    1.07..1.12
mid        1024        226.1        236.8     0.95x    0.92..1.01
mid        4096        780.1        906.1     0.90x    0.69..0.92
late         64         41.5         23.8     1.78x    1.48..1.87
late        256         98.5         61.5     1.65x    1.30..1.73
late       1024        380.1        231.4     1.64x    1.60..1.68
late       4096       1419.1        869.8     1.62x    1.53..1.74
```

### Run B — `RUSTFLAGS="-C target-feature=+avx2"` (auto-vectorizes the two-pass arm)

```
shape         n   twopass ns  dispatch ns   speedup         round band
iid          64         44.2         23.9     1.85x    1.43..2.43
iid         256         39.5         59.2     0.67x    0.63..0.68
iid        1024         66.1        239.5     0.28x    0.25..0.30
iid        4096        408.2        940.5     0.35x    0.30..0.77
early        64         14.2         22.0     0.64x    0.61..0.71
early       256         19.3         60.8     0.33x    0.27..0.33
early      1024         56.8        233.9     0.23x    0.22..0.30
early      4096        207.9        936.6     0.21x    0.20..0.31
mid          64         33.0         23.9     1.39x    1.10..1.64
mid         256         64.8         58.9     1.08x    1.07..1.20
mid        1024        230.4        238.1     0.98x    0.86..1.02
mid        4096        761.5        856.6     0.88x    0.84..0.95
late         64         40.5         22.5     1.82x    1.64..1.86
late        256        100.2         58.0     1.69x    1.66..2.06
late       1024        544.8        254.2     1.92x    1.29..3.64
late       4096       1417.4        878.3     1.54x    1.48..2.12
```

## Why the two-pass wins (mechanism, consistent with both profiles)

- The kernel is **latency-bound**: each 8-vector's `cmp→blend` chain depends
  on the previous vector's `vmax`, ≈1.1–1.2 cycles/element, shape-independent.
- The two-pass is **throughput-bound**: `avx2_max_f32` runs four independent
  `max_ps` accumulators (≈0.125 cycles/element), and `position(== max)`
  auto-vectorizes to an 8-floats-per-cycle equality scan that EXITS EARLY
  whenever the maximum sits in the first half — the common case (`iid` max
  position is uniform, `early` by construction). Total ≈0.15–0.3
  cycles/element on those shapes.
- The kernel only wins when `position` must scan most of the array (`late`,
  1.5–1.9×) or at n=64 where two call boundaries dominate (~20 ns).

No size or shape predicate can route around this: an argmax caller cannot
know where its maximum is without scanning — the thing the dispatch would
have to predict. The NEON single-pass premise does not transfer to x86_64,
where LLVM's auto-vectorization of the reduce+search pair is the stronger
instrument.

## Disposition

- Dispatch reverted; `two_pass_argmax_f32` remains the x86_64/generic path,
  its doc comment now carries the measured numbers and the reopen trigger.
- The kernel itself was deleted (no consumer, dead code otherwise); it lives
  in this repo's git history at the Issue-817 commit if ever needed.
- Tests KEPT: `argmax_matches_two_pass_at_simd8_tail_boundaries` (valid
  cross-platform equivalence at the AVX2 tail lengths, incl. max-in-last-tail)
  and `argmax_nan_input_stays_defined_and_in_range` (no-panic/in-range pin;
  NaN input is out of contract and was ALREADY platform-inconsistent in the
  incumbent — scalar fold sticky-poisons, `avx2_max_f32` heals via
  `maxps`-SRC2, NEON heals; documenting any of these as THE semantics would
  pin an accident).
- The Bench-810 `late_peak` k=1 loss (~0.9×) is ACCEPTED: the only measured
  fix costs 3–4.7× on the common shapes.
- Load note: Run A at 1% CPU; Run B finished just as a sibling workload began
  (32% at check) — every verdict cell's round band stayed tight, and the two
  runs agree within noise.
