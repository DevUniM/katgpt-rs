# Bench 765: `slt_sweep` — the noise-sweep λ̂ estimator (Issue 782 / 781 T4) GOAT

**Status:** PASS — G1–G4 ALL PASS; PROMOTED to default-on (the BMR/Bench-764
precedent: pure modelless math, zero deps, no interaction surface; the gain
is the instrument itself, anchored).

**Date:** 2026-09-15 · **Lane:** `cargo test -p katgpt-core --features
slt_sweep --lib sweep` (7 gate tests + 1 ignored diagnostics) + the release/
allocTracking lane + the default-floor + `--all-features` check lanes.

## What shipped

`katgpt_core::slt::sweep` (feature `slt_sweep = ["slt"]`, zero deps,
zero-alloc estimate path, bit-reproducible from a seed):

| Item | Role |
|---|---|
| `fill_gaussian_dirs(dirs, seed)` | the canonical deterministic direction stream (xorshift64\* + Box–Muller; same stream as the module's test RNG, promoted to shipped surface) |
| `NoiseSweepSpec { draws, scale0, scale_decay, scales }` | probe budget (default m=1024, K=6, geometric ladder 0.5·0.45^k); scales independently streamed (seed mixed per scale) |
| `NoiseSweepScratch` | pre-allocated dirs/w/deficits/ladder buffers — the estimate path allocates nothing |
| `noise_sweep_lambda(spec, w0, loss, scratch, seed) -> f64` | median over the ladder of per-scale log-log CDF-slope fits; NaN when no scale is valid — never a silent zero |

Cost contract: `1 + K·m` loss evals (6145 at default) — a freeze/
consolidation-seam instrument (R558 §5), never a per-tick signal. The loss
closure is caller-owned: the intended prod surface is a LoRA/dendritic
overlay (`r·(a+b)` params), not the host model.

## The estimator form — and the v1 → v2 design record

**v1 (windowed mirrored-Hill, killed at landing):** fit
`λ̂ = k / Σⱼ ln(u₍ₖ₊₁₎/u₍ⱼ₎` on the smallest-k deficits. Exactly unbiased
for exact power laws — but NO polynomial-loss family has an exact power-law
CDF under the GAUSSIAN probe measure (only the Lebesgue sublevel volume is
exact; the Gaussian radial tail is the cutoff). Measured **−28%…−37%**
systematic on bowl/quartic/RRR anchors (the χ-shaped bulk sits inside any
upper-half window). The failure is kept as the design record in the module
doc.

**v2 (shipped):** for fixed scale t, fit `ln P̂(u < s)` vs `ln s` over an
order-statistic ladder (counts ~ m/512 … m/16, 8 geometric points, weights
∝ count) — the **shell-cancelling volume-codimension form** (Murfet et al.
2020 eq. 4.3): the Gaussian shell factor multiplies both thresholds and
divides out of the SLOPE. On χ²₄ the two-quantile slope over p ∈
[0.001, 0.06] is within ~2% of λ (closed-form check) where v1 sat at −17%.

## G1 — the calibration ladder (measured, seed 0x5EED_0782, default spec)

| anchor | geometry class | λ̂ | target | rel |
|---|---|---|---|---|
| bowl d=2 | star body | 1.0317 | 1.0 | **+3.2%** |
| bowl d=4 | star body | 1.6575 | 2.0 | −17.1% |
| quartic Σw⁴ d=2 | star body | 0.5048 | 0.5 | **+1.0%** |
| quartic Σw⁴ d=4 | star body | 0.8156 | 1.0 | −18.4% |
| quartic Σw⁴ d=8 | star body | 1.6140 | 2.0 | −19.3% |
| planted RRR a=b=3 r=1 | **tube** (flat fiber) | 2.4725 | 2.5 | **−1.1%** |
| ReLU toy d=21 (Murfet §6) | **cone** (dead units) | 2.7715 | d/2=10.5 | singularity gate [2.0, 3.6] |

Gates: bowl/quartic ±15% (d=2) / ±25% (d≥4); RRR ±15%; ReLU [2.0, 3.6]
with the d/2=10.5 contrast asserted in the message.

**The geometry-class finding (load-bearing):** TUBE/CONE sublevel sets —
singular points with flat directions (fibers, dead units) — are
near-unbiased (−1.1%) because the along-tube Gaussian factor is
s-independent and cancels in the slope. ISOLATED regular minima (star
bodies) carry a documented −18…−19% radial-tail bias at d ≥ 4 (+1…+3% at
d ≤ 2). The bias is monotone in d within a family — ranking within a
family (the module's selection use) is preserved.

## The ReLU toy — the local vs tempered-global boundary

The paper's cell (H=5, m=3, b=−1/3, q=1, x uniform [−1,1]²; K = fixed
32×32 midpoint sum — the paper's own empirical-L_n construction at n=1000):
measured **λ̂ = 2.7715**, stable at **2.7710** under 9× denser quadrature
(96²) and **2.9143** at 16× draws (m=16384, wall probe) — i.e. the LOCAL
tangent-cone exponent at the s_m apex is ≈2.8, NOT the paper's tempered-
global SGLD value 0.526. The instrument sees the singular geometry
decisively (2.8 ≪ 10.5 — a 3.6× reduction vs parameter count; also ≪ the
minimally-singular bound 5) but a local isotropic Gaussian probe resolves
the cone-mixture's dominant slope, not the posterior-weighted global RLCT
that SGLD reports. **Recorded as the instrument boundary; the paper's 0.526
is not a local-probe target.** riir-train Plan 404 (SGLD) stays PRIMARY for
tempered-global λ̂.

## G2 — cost

A full default estimate = 6145 loss evals, µs-class overhead per eval
(bowl cell finishes in ~1-2 ms debug); the 250 ms debug ceiling test guards
O(m²) rot. Cold-path contract (freeze time), never per-tick.

## G3 — no regression + determinism

Default-feature lib suite **2053 → 2060** (floor bumped in
`scripts/test_gate.sh`, measured same box) — +7 gate tests, +1 ignored
diagnostics. Same seed ⇒ **bit-identical** λ̂ (`to_bits` eq); different
seed ⇒ different estimate. `--all-features` check clean; clippy
`-D warnings` clean.

## G4 — alloc-free, release-verified

Estimate path (scratch pre-built): **0 allocations** under the counting
allocator, `--release --features slt_sweep,alloc_tracking` (the Issue-741
profile-free predicate). PASS.

## UQ floor rule — not triggered (routing recorded)

λ̂ is a point parameter estimate feeding the already-floor-gated `bayes_gap`
(Bench 764 §T3); it emits no interval/coverage/confidence surface. The
calibration ladder above IS its gate.

## Verdict

- **PROMOTED to default-on** (202 default → 203; 603 total → 604). Feasible
  domain λ ≲ 3 — the SINGULAR regime the module prices; the sample wall
  above that is Γ(d/2)-starvation of the near-zero window and is physics,
  not implementation.
- The estimator is the runtime/freeze-time twin of riir-train Plan 404's
  SGLD instrument; consumer wiring (freeze/thaw λ̂-informed WBIC scoring,
  dendritic-overlay rank pricing) follows in consumer repos when a
  selection consumer materializes — the closed-form `rlct_reduced_rank`
  already covers the known-rank families.

## Reproduce

```sh
cargo test -p katgpt-core --lib slt::sweep            # post-promotion: 7 gates
cargo test -p katgpt-core --release --features slt_sweep,alloc_tracking --lib slt   # G4 lane
cargo test -p katgpt-core --lib sweep_diagnostics -- --ignored --nocapture          # the measured table
cargo test -p katgpt-core --lib                      # 2060 (floor bumped)
```
