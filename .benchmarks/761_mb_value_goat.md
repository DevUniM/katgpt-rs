# Bench 761: mb_value — bounded three-factor (dopamine) plasticity value circuit — Issue 767 T1–T9 GOAT Gate

> **Feature:** `mb_value` (katgpt-core) — **OPT-IN** (no consumer yet; the consumer path is the riir-ai per-NPC value overlay, Research 380 §8)
> **Source:** Issue 767 · riir-ai Research 380 (TMNF-C distill) · adonis-singh/TMNF-C @ `eb6be045` MIT · mechanism after Bennett/Nowotny et al., Nat. Commun. 12:2569 (2021)
> **Date:** 2026-09-13
> **Gate:** `cargo bench -p katgpt-core --features mb_value --bench bench_767_mb_value_goat` (bench profile, M3 Max, AC power, no other compute)
> **Companion tests:** 8 in `tests/mb_value_g1.rs` + `tests/mb_value_g4_alloc.rs` (1), all `--features mb_value`

## The primitive (Issue 767 T1–T4)

`crates/katgpt-core/src/mb_value.rs` — the mushroom-body architecture class: fixed
random sparse PN rows (seeded, fanin-clamped) → quantile-calibrated ReLU →
top-k KC code (`select_nth_unstable_by` under the total order (drive, idx) —
the SET is exactly the full-sort reference's, G1-pinned) → approach-minus-avoid
linear readout over per-KC distinct MBON synapse lists. The ENTIRE learning
machinery is one bounded local rule:

```text
w ← clamp(w − η · code_active · RPE · compartment_sign, 0, w0)
```

Calibration (`calibrate`) is measurement, not learning: feature z-scores,
PN quantile thresholds/gains, a 17-step bisection on the action-code gain to a
target code-overlap (measured landing: target 0.5 → 0.4999), per-MBON `w0`
normalization (mean drive over calibration codes = 1), and the derived step
`η = α/(eff_app + eff_avd)` — scale-free ΔV-per-RPE across circuit sizes.
`eta = 0` until calibration → updates are inert by construction pre-calibrate.
No softmax anywhere; `w()`/`set_w()` are the BLAKE3 freeze/thaw seam; NO
connectome data ships (seeded random wiring; `fly()`/`toy()` are shape classes).

## G1 — correctness + the ridge floor (8/8 PASS, 234 s debug)

| Gate | Result |
|---|---|
| Construction seed-determinism (incl. cross-seed wiring difference) | PASS |
| Canonical top-k == full-sort reference (200 random cases + forced all-ties degenerate circuit; ties break by index) | PASS |
| Bounds `[0, w0]` under adversarial RPE streams (±1e30, ±inf, NaN, alternating; NaN/±inf are no-ops) | PASS |
| Depression → recovery dynamics (avoid-side mean 2.67 → ~0 under +RPE, recovers under −RPE; saturation floor/ceiling) | PASS |
| Calibration sanity (both compartments connected, overlap bisection lands 0.4999, mean V ≈ 0 at start over the calibration distribution) | PASS |
| Bit-identical repeat training streams | PASS |
| **Toy corridor vs the ridge-batch floor** (the issue's mandatory baseline: ridge on the SAME codes, fit to realized MC returns via `linalg::ridge_solve_direct_f64`) | **PASS — dopamine r = 0.9705 (Spearman 0.9695) vs ridge 0.9998; margin 0.029 < 0.05 gate** |
| **Distribution-shift arm** (reward polarity flips at phase boundary) | **PASS — online dopamine re-adapts to r = 0.9444 while the FROZEN batch fit inverts to r = −0.9945** |

Corridor setup (recorded for reproduction): state-only toy circuit (the (s,a)
shared-code interference is the source's own measured negative — "the value
differs little between actions" — deliberately NOT this gate's axis), 1-D
corridor, progress-shaped reward `sign·scale·Δs` (scale 4), γ=0.98, α=0.01,
follow-the-paying-direction policy, 60k episodes (learning curve: 0.60@2k →
0.86@8k → 0.94@30k → 0.97@60k — still climbing; the runtime is the gate's
cost). Honest residual: ONE mid-range code region (s≈0.43) sits at 1.36 vs
target 2.05 — interpolation drag from shared synapses; every other eval state
within ±0.25 of target, top end and wall EXACT. The reward-sign double-count
bug found during tuning (dir × Δs double-counting — every step paid the same
sign) is recorded in the test's comment as the trap it was.

## G2 — perf (bench profile, M3 Max)

| Cell (n_kc / kc_active) | code top-k | code full-sort | value | dopamine update |
|---|---|---|---|---|
| fly_sparse (4,064 / 200 = 4.9%) | **28.9 µs** | 65.9 µs | **1.86 µs** | **4.14 µs** |
| fly_saturated (4,064 / 4,064) | 74.2 µs | 66.8 µs | 53.2 µs | 107.4 µs |
| toy (256 / 32) | **1.82 µs** | 3.36 µs | **0.14 µs** | **0.25 µs** |

- **Sparse regime (the fly class): top-k beats full sort 2.28×** (gate ≥1.2×);
  value/update are µs-class (gate met).
- **Saturated honesty line: top-k LOSES 0.90×** — `select_nth` degenerates at
  k=n (expected; the sparse-regime win is the claim, the R379 §9 G2-bar
  import). Value/update at saturation touch all 61k synapses: 53/107 µs —
  the O(active × fanin) cost as designed.
- **The NPC-scale line:** toy-class full learning cycle (code+value+update)
  ≈ 2.2 µs → **1,000 NPCs learning online every tick ≈ 2.2 ms of the 50 ms
  20 Hz budget (4.4%)** — the selling-point shape for the riir-ai consumer.

## G3 — no-regression

New opt-in feature + new test/bench targets only; no existing target touched
(`lib.rs` gained one cfg-gated module + one entry in the `linalg` cfg
any-list per the Bench-696 rule — the G1 floor test consumes
`ridge_solve_direct_f64`). Default build unchanged.

## G4 — allocation-free steady state (1/1 PASS)

64 cycles × 32 stationary (features, action, rpe) triples through
code+value+update: **0 allocations** after warmup (per-thread counting
allocator, the house pattern).

## UQ posture + negatives carried (T8)

Not UQ-bearing: point value for ranking (any future distribution claim owes
the conformal-naive floor first). Module docs carry TMNF-C's measured
negatives verbatim: action selection from shared codes is near-random (50%
KC overlap); frozen weights degrade. This primitive is for VALUE FORMATION
feeding external selection.

## Verdict

**GOAT G1–G4 ALL PASS. Stays OPT-IN** (consumer-first promotion rule — the
named consumer is the riir-ai per-archetype frozen circuit + per-NPC dopamine
readout overlay, Research 380 §8, gated on Issue 763's landed `lif_graph`
substrate story). Promotion to default-on requires a production consumer
GOAT, per the house rule (cf. `lif_graph`, Issue 763).
