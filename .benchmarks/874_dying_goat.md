# Bench 874 — `kv_eviction::dying` GOAT gate (Issue 873 primitive C)

**Status:** G1 + G2 + G4 PASS — 2026-09-22, M3 Max (aarch64), macOS 26.6.2.
Opt-in feature `dying` (implies `usage_rate_eviction` — the parent module's
own gate); promotion stays opt-in until the first consumer GOAT
(riir-neuron-db `shard_compactor`, riir-clippy corpus rule retirement, or
belief GC — consumers file their own wiring per the issue's standing note).

## What landed

`katgpt-core/src/kv_eviction/dying.rs` — the delete-side complement of the
keep-side usage-rate scorer (Research 581 mechanism row #5, distilled from
volotat/mini-AGI `paged.py:284-325` @ `96784b7`, MIT):

- **ONE definition, TWO thresholds**: `d = min(now − last_addressed,
  own_age)/window`, pinned 0 while on survival trial; `d ≥ 0.75` ([`BRAKE_THRESHOLD`],
  source-pinned) → `Verdict::Braking` (stop growth/feeding), `d ≥ 1.0` →
  `Verdict::Dead` (delete). Brakes and prunes read the same number — the
  "should we prune" drift this shape refuses.
- **Two newborn protections**: the own-age clamp (a never-addressed item
  dies by AGE, never `(now − epoch)` — no dead-from-birth) + trial pinning
  (a newborn cannot die before `admission + trial_len`).
- **Anti-magnitude by design** (`paged.py:292-299` — the busiest items carry
  the smallest gates): [`DeathRow`] carries NO magnitude field; usage mass
  lives in the keep-side `UsageRow` beside it, and the two rankings are
  separate on purpose.
- `calibrate_window` — the mini-AGI `segments/step` self-calibration,
  generalized: cumulative-event ratios → a tick-unit window; refuses
  (`None`) on zero events and on non-representable extremes.

## G1 — known-answer vectors (11 lib tests, all green)

`fresh_item_is_alive` · `thresholds_read_one_definition` (74/75/99/100/10000
at window 100 — exact threshold edges) · `addressing_resets_staleness_monotonically`
(backwards touch never un-stales) · `never_addressed_dies_by_age_not_epoch`
(the own-age clamp arm) · `trial_pinning_a_newborn_cannot_die_on_trial`
(pinned through trial end, then immediate at once — no second ramp) ·
`trial_end_with_recent_touch_is_alive` (no cliff for an item used through
its trial) · **`magnitude_is_anti_predictive_and_ignored` (THE C2 falsifier:
the historically-hottest item reads Dead while the low-magnitude
recently-touched item reads Alive — the death ranking orders by recency
where a magnitude ranking orders oppositely)** · `batch_scan_counts_dead_into_caller_buffer`
· `zero_window_is_guarded_not_panicking` · `calibration_converts_events_to_ticks`.

## G2 — steady-state latency (fences, not optimality claims)

`cargo bench -p katgpt-core --features dying --bench bench_874_dying_goat`
— best-of-240 chunks × 4096 rows, mixed stale/fresh population (every
verdict class in every scan), `now` varied per chunk (no constant-folding),
`black_box` + checksum sinks:

| path | measured | bar | headroom |
|---|---|---|---|
| `verdicts_into` batch (4096 rows) | **1.30 ns/row** | ≤ 20 | ~15× |
| `death_score` scalar | **1.03 ns/row** | ≤ 10 | ~10× |

Box state: M3 Max, load 4–10 (two sibling agent sessions active;
best-of-chunks absorbs preemption spikes). O(1)/row is the contract.

## G4 — zero steady-state alloc

`g4_alloc_free_steady_state` (crate `TrackingAllocator`, debug-gated per
the counter design): 1000 cycles of touch + batch scan into a caller-owned
buffer = **0 allocs**.

## Substrate check (recorded per the substrate-first gate)

Extends `kv_eviction` BY DESIGN (the issue's own C1: "the delete-side
complement of `UsageRow`'s keep-side `cum_mass/age`"). Searched
staleness/death/decay vocabulary: `calibration_staleness` (snapshot-bound
calibration invalidation — different concept), `decay_confidence`
(riir-games-shared perceptual fade, no deletion semantics — Research 581
row #5's own signal-diff), `twist_cache`/`bfcp_region_cache` (cache-local
TTLs, no dual-threshold contract). No delete-side staleness metric exists →
BUILD-NEW as the kv_eviction sibling. No new deps; sync boundary: none
(pure scoring over caller-owned state).

[`BRAKE_THRESHOLD`]: ../crates/katgpt-core/src/kv_eviction/dying.rs
[`DeathRow`]: ../crates/katgpt-core/src/kv_eviction/dying.rs
