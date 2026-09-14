# Issue 782: `slt` noise-sweep λ̂ estimator — the 781-T4 unit (Bench-764 follow-up)

**Status:** RESOLVED — all gates PASS, promoted default-on (Bench 765);
close-out commits ref'd in HISTORY §Issue 782.

Ship the modelless λ̂ estimator behind `slt_sweep = ["slt"]` (opt-in until
its own GOAT):

- `slt::sweep::fill_gaussian_dirs(dirs, seed)` — the canonical deterministic
  direction stream (xorshift64\* + Box–Muller; same stream as the module's
  test RNG, promoted to shipped surface so λ̂ is bit-reproducible).
- `slt::sweep::NoiseSweepSpec { draws, scale0, scale_decay, scales }` —
  probe budget; default m=1024, K=6, geometric ladder downward from 0.5,
  per-scale independent streams.
- `slt::sweep::NoiseSweepScratch` — pre-allocated dirs/w/deficits/ladder
  buffers (zero-alloc estimate path).
- `slt::sweep::noise_sweep_lambda(spec, w0, loss, scratch, seed) -> f64` —
  per-scale **shell-cancelling log-log CDF-slope** fit over an
  order-statistic ladder (the Murfet 2020 eq. 4.3 volume-codimension form;
  the in-flight v1 mirrored-Hill window measured −28…−37% systematic — the
  Gaussian probe measure breaks the exact-power-law premise; the v1→v2
  record lives in the module doc + Bench 765), median across the ladder;
  scales whose deficits hit non-positive/non-finite values are skipped; NaN
  when no scale is usable.

## Calibration ladder (G1) — measured, with the instrument boundary

| anchor | class | λ̂ | target | rel |
|---|---|---|---|---|
| bowl d=2 / d=4 | star body | 1.0317 / 1.6575 | 1 / 2 | +3.2% / −17.1% |
| quartic d=2/4/8 | star body | 0.5048 / 0.8156 / 1.6140 | 0.5 / 1 / 2 | +1.0% / −18.4% / −19.3% |
| planted RRR a=b=3 r=1 | tube | 2.4725 | 2.5 | **−1.1%** |
| ReLU toy d=21 | cone | 2.7715 | d/2=10.5 | singularity gate [2.0, 3.6] |

Tubes/cones (the singular regime — flat fibers, dead units) near-unbiased;
star bodies carry the documented Gaussian-radial-tail bias (monotone in d,
within-family ranking preserved). Sample wall: λ ≳ 3 infeasible at
m ≤ 2048 (Γ(d/2)-starved near-zero window) — the feasible domain is the
singular regime, exactly what the module prices.

## Tasks

- [x] T1 — `slt_sweep` feature + the four shipped items (zero-alloc,
  `#[must_use]`, derivation doc incl. the v1→v2 form record).
- [x] T2 — G1 calibration ladder (locked deterministic tolerances).
- [x] T3 — G3 determinism: bit-identical under seed; different seed moves.
- [x] T4 — G4 alloc-free (counting allocator, release, Issue-741 predicate).
- [x] T5 — G2 cost: 1 + K·m loss evals; 250 ms debug ceiling test.
- [x] T6 — GOAT verdict: PASS ⇒ promoted to default (floor 2053 → 2060,
  README 603/202 → 604/203, module-doc row, HISTORY).
- [x] T7 — Bench 765 with the measured wall + per-anchor deltas + the
  local-vs-tempered-global boundary (ReLU toy local ≈2.77 stable under 9×
  quadrature + 16× draws vs SGLD-global 0.526 — 0.526 is not a local-probe
  target).

## Notes

- UQ floor rule: NOT triggered — λ̂ is a point parameter estimate feeding
  the already-floor-gated `bayes_gap`; routing recorded (Bench 765).
- The estimator is a freeze/consolidation-seam instrument (R558 §5); the
  loss closure is caller-owned (LoRA/dendritic overlay space).
- riir-train Plan 404 (SGLD) remains PRIMARY for tempered-global λ̂ at any
  λ; this is the runtime/freeze-time twin for the singular regime.
