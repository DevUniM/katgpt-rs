# Bench 843 — per-shape plasma dispatch GOAT (Issue 843 T4, owner call gate D1)

**Status:** LANDED 2026-09-19, GOAT G1+G2 GREEN (M3 Max / aarch64-NEON,
release, interleaved `ab_median_ratio` harness). `plasma_path` stays
DEFAULT-ON — the owner call resolves T4 as a per-shape dispatch primitive,
not a demotion: the footprint argument stands, and the flag's manifest
comments now state the measured trade instead of implying a latency win.

## The owner call (gate D1, 2026-09-19)

**Per-shape dispatch: f32 below the L3 boundary, ternary above. Option (b)
NOT taken** (pre-expanded i8 sign rows, ~1.7–2× back at 5.3× footprint —
the bitplane footprint is not the product at served shapes).

## What landed

`katgpt-types/src/simd/plasma_dispatch.rs` (feature-gated with the
`TernaryWeights` container it dispatches over; re-exported through
`katgpt_core::simd` + the top-level `plasma_path` re-export):

- `l3_cache_bytes()` — cached probe: `KATGPT_PLASMA_L3_BYTES` env override →
  macOS `sysctl hw.l3cachesize` → Linux sysfs `index3/size` → 32 MiB
  default (biased toward f32: over-estimating costs the bounded
  above-boundary gap, under-estimating re-introduces the 1.9–3.0× losing
  regime).
- `plasma_prefers_ternary{,_with_l3}(rows, cols[, l3])` — the pure policy:
  ternary only when the f32 operand `rows·cols·4` exceeds the boundary.
- `simd_matvec_plasma_dispatch{,_with_l3}(dense, ternary, x, y[, l3])` —
  for callers holding BOTH representations (the quantize-from-dense seam);
  bit-identical to whichever kernel the policy picks; zero-alloc.

## GOAT (tests/bench_843_plasma_dispatch_goat.rs, required-features plasma_path)

| gate | claim | measured (M3, release) |
|---|---|---|
| G1 | dispatch == selected kernel, bit-identical, both sides of a FORCED boundary (`_with_l3`) | PASS |
| G1 | policy boundary == the f32 operand bytes (512²@1 MiB edge-exact; served 768×3072 = 9 MiB → f32 side) | PASS |
| G2 | dispatch ≥1.5× faster than pure `simd_ternary_matvec` @1024², f32 arm forced | **2.11×** (Issue 843's own sweep: 2.16× NEON / 2.26× AVX2) |
| G2 | dispatch ≤10% slower than pure `simd_matvec` @1024² | **−1.6%** (median 0.984, rounds 0.920..1.108) |
| G3 | no-regression: nothing existing routes through the dispatch (kernels untouched; katgpt-types suite unchanged; the 3 new unit tests are feature-gated) | structural PASS |
| G4 | alloc-free: slices in/out, one OnceLock policy read | structural PASS |

## Posture

The dispatch is a POLICY primitive for dual-representation callers; the
flag's kernels are untouched and every existing consumer keeps its behavior
byte-identical. Downstream wiring (e.g. riir-ai's npc_brain quantize seam)
is a consumer-side decision, deliberately not done here — katgpt-rs ships
the policy, consumers opt in per surface.
