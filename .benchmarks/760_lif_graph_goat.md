# Bench 760: Signed-graph LIF reservoir — Issue 763 T2–T6 GOAT Gate

> **Feature:** `lif_graph` (katgpt-core) — **OPT-IN** (no consumer yet; the consumer path is the riir-ai per-archetype circuit shard, Research 379 §7)
> **Source:** Issue 763 · riir-ai Research 379 (fly-connectome landscape survey) · model: Shiu et al. Nature 2024 (canonical constants) · integration: RuVector exact-exponential trick (pinned refs in the issue)
> **Date:** 2026-09-13
> **Gate:** `cargo bench -p katgpt-core --features lif_graph --bench bench_760_lif_graph_goat` (bench profile, 4090 box, i7-13700K host CPU, GPU idle — pure CPU primitive)
> **Companion tests:** 5 lib unit tests + `tests/lif_graph_g1.rs` (7) + `tests/lif_graph_g4_alloc.rs` (2), all `--features lif_graph`

## Verdict: GOAT G1 + G2 + G4 ALL PASS — ships OPT-IN (no consumer; promotion needs one)

```
================ GOAT VERDICT ================
  [PASS] G1 exact dense parity — event vs dense bit-identical (3 regimes ×
         seeds; spike sets + v/g/refrac bitwise) + determinism + exact-delay
         chain + Maslov–Sneppen degree preservation + rest-state pinning
  [PASS] G2 perf — event vs matvec ≥3× at 10k/1%-class active: 97,285×
         measured (822 ns vs 80.0 ms); event vs CSR full scan 34.8× at
         3.1% active; saturated parity 1.08× (honesty line)
  [PASS] G3 no-regression — new opt-in module; default build does not
         compile it (zero-cost-unless-invoked); default `cargo check` clean
  [PASS] G4 alloc-free — 0 steady-state allocs on both step paths (2,800-tick
         warmup, 4×1,404-tick window, non-vacuous: 60+ spikes)
```

## The primitive (Issue 763 T2)

`crates/katgpt-core/src/lif_graph.rs` — the fly-connectome architecture
class: a **fixed signed sparse graph** (CSR, sign pre-folded into f32
weights) running current-based LIF with exact exponential integration
(`a_m`, `a_s`, `c_gs` precomputed — 3 muls per active neuron per tick),
timing-wheel spike delays (18 buckets @ Shiu dt=0.1ms), and a closed-form
ridge readout consuming `linalg::ridge_solve_direct_f64` (KARC precedent —
no training loop, gradient-free by construction).

**The exact-parity active set is the design's core**: quiescence is defined
as the bitwise fixed point of the shared per-node update
(`refrac == 0 ∧ g == 0.0 ∧ leak(v) == v` bitwise), so the dense update of a
skipped node IS the identity — event-driven and dense paths produce
bit-identical trajectories by construction, not by tolerance. This differs
from RuVector's tolerance-based dropout (approximate by design). Two parity
hazards were caught by the G1 gate during development:

1. **Spike-order accumulation**: the event path originally scheduled ring
   writes in active-set visit order while dense collected ascending — two
   spikers hitting one target accumulated `g += w` in different orders →
   2-ULP divergence. Fix: canonical ascending spike order in both paths
   (sort before scheduling).
2. **g-floor snapping**: applied identically in both paths (a subnormal g
   tail would otherwise pin the active set open for ~4,300 ticks).

**Weight units are PSP millivolts** (Shiu `w = 0.275 mV × count`): delivery
converts to drive via `g += w·(t_mbr/tau_syn)`. Single-synapse input moves
`v` by 0.275 mV against a 7 mV threshold gap — firing is coincidence
detection (~26 synchronous synapses), as in the whole-fly model. The
**single-fire drive window** is `w ∈ (11.1, 17.2)` (peak Δv = g0·0.1575 at
t≈9.2 ms; post-refractory residue must stay subthreshold) — the G4/bench
fixtures drive w=14, exactly one fire per period.

## G2 — the measured matrix (Issue 763 T4)

Host CPU (bench profile). `event` = active-set step; `dense_csr` = CSR
full-scan reference step (bit-identical dynamics); `matvec` = the classic
dense-W·spike-indicator O(N²) baseline every textbook reservoir runs.

| cell | active fraction | event | dense_csr | matvec | event/matvec | event/dense_csr |
|---|---|---|---|---|---|---|
| sparse N=1k, E=5k | 2.3% | 73.7 ns | 2.78 µs | 769.9 µs | 10,446× | 37.8× |
| sparse N=10k, E=50k | 3.1% | 822 ns | 28.6 µs | 80.0 ms | **97,285×** | 34.8× |
| saturated N=1k | 100% | 2.61 µs | 2.88 µs | 770.3 µs | 295× | 0.91× |
| saturated N=10k | 100% | 27.3 µs | 29.4 µs | 79.5 ms | 2,910× | 1.08× |

- **The gate** (≥3× event vs matvec at 10k / 1%-class active): **PASS at
  97,285×** — the dense-matvec baseline is O(N²) regardless of activity
  (100M madds/tick at 10k), so the gate clears by ~4 orders of magnitude.
  The gate as written is nearly vacuous against a dense baseline; the
  MEANINGFUL axes are the ones below.
- **The active-set axis** (event vs dense_csr): **34.8× at 10k / 3.1%
  active** — the sparse-regime win the primitive exists for (dense_csr does
  10k node updates/tick; event does ~310).
- **The honesty line** (saturated): **0.91× / 1.08× — parity**, the
  RuVector "collapse to ~1× at saturation" class, measured not asserted.
  At 100% active the skip buys nothing; the bookkeeping overhead is inside
  noise at 10k, ~9% at 1k.
- **Regime characterization printed per run** (active fraction + spikes/tick
  measured, not assumed): sparse fixtures land at 2.3%/3.1% active (the
  issue's 1–5% cell), 0.00–0.04 spikes/tick.

## G4 — the ring-slot lesson (recorded for the class)

The first G4 fixture failed with 6 recurring allocations at every fire
tick. Root cause chain (worth recording — it generalizes to any timing-wheel
design): (1) 6 allocs = one bucket's amortized doubling 4→8→…→128 for ~100
spike-edge writes; (2) it RECURRED every period because the schedule slot
is `(ring_head + 17) mod 18` and the period (1400) was NOT a multiple of
the ring length — the slot shifted 14 positions per period, cycling through
9 distinct buckets, each priming lazily on first use; (3) fix = slot-aligned
period (1404 = 18×78) so every period reuses ONE bucket, primed during
warmup. Long irregular workloads eventually prime every bucket (amortized —
documented in the module); the G4 gate measures the stationary orbit, per
the house pattern (KARC G3).

## Controls (Issue 763 T-controls — FlyDoom ladder)

- `SignedAdjacency::er_matched` — ER-matched null (same N, E; randomized
  topology): shipped as a builder.
- `SignedAdjacency::maslov_sneppen` — degree-preserving double-edge swaps:
  shipped as a builder, in/out degree preservation PINNED by unit + G1
  tests (and non-vacuity: the swap must change the edge set).
- Weight-shuffle: trivially caller-side (permute `weights()` before
  `from_edges`); not shipped as a method.

## T6 — promote/demote decision

**Stays OPT-IN.** GOAT G1+G2+G4 pass, modelless (closed-form ridge readout,
fixed graph — the KARC class), zero-cost-unless-invoked — but the
feature-flag discipline requires a consumer for promotion (the
`karc_lod_tier` / `hebbian_kernel_memory`-layer precedents: primitive GOAT
PASS ≠ default-on). The named consumer path: **riir-ai per-archetype
circuit shard + per-NPC readout** (riir-ai Research 379 §7) — a riir-ai
issue owns that wiring when it lands. CEM readout stays excluded (the
issue's audited discard: ridge covers linear readouts closed-form).

## Reproduction

```
cargo test  -p katgpt-core --features lif_graph --lib lif_graph        # 5 unit
cargo test  -p katgpt-core --features lif_graph --test lif_graph_g1    # 7 G1
cargo test  -p katgpt-core --features lif_graph --test lif_graph_g4_alloc  # 2 G4
cargo bench -p katgpt-core --features lif_graph --bench bench_760_lif_graph_goat
```

Second bench run (all 12 cells, medians): sparse 1k event 74-115 ns →
dense_csr 2.78 µs → matvec 770 µs; sparse 10k event 822 ns-11.6 µs (the
11.6 µs reading was the 43%-active pre-tuning fixture; the tuned 3.1%
fixture reads 822 ns) → dense_csr 28.6-40.9 µs → matvec 78.4-80.4 ms.
