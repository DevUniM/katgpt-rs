# Bench 873 — `pool_admission` GOAT gate (Issue 873 primitive A)

**Status:** G1 + G2 + G4 PASS — 2026-09-22, M3 Max (aarch64), macOS 26.6.2.
Opt-in feature `pool_admission` (katgpt-core); promotion stays opt-in until
the first consumer GOAT (riir-ai working sets / PagedKVCache, or
riir-neuron-db `zone_cache` — consumers file their own wiring per the issue's
standing note).

## What landed

`katgpt-core/src/pool_admission.rs` — hysteresis admission policy for a
fixed-capacity resident set (Research 581 mechanism rows #6/#7/#8, distilled
from volotat/mini-AGI `paged.py:569-714` @ `96784b7`, MIT):

- **margin** ×1.10 (source-pinned, [`DEFAULT_MARGIN`]) — a candidate
  displaces the weakest evictable resident only when beating it by 10%:
  no movement on noise, cascading turnover on a real shift.
- **dwell-from-ADMISSION-tick** newborn immunity — [`ResidentRow`] carries
  no last-use field at all, so the "permanently young under a last-use
  clock" bug (measured the hard way at mini-AGI `paged.py:242-247`) is
  unrepresentable by construction.
- **terminating fair-turn sweep** — one never-admitted item designated per
  cycle, index order, terminates for good, re-arms only on universe growth
  (O(1) rejection when terminated via the `pending` counter).
- **apply-by-identity** — `resident_ids_into(&mut Vec<u64>)` is the readout;
  the caller's load count is the true set delta.
- Free-fn core (`admission_decision` over caller-owned rows) +
  stateful `AdmissionSet` convenience layer — the [`kv_eviction`] shape:
  want-scores are caller-supplied (the `suspect_indices` house pattern;
  `kv_eviction::score` is the natural producer), slot allocation stays
  `graph_stable_pool`'s concern.

## G1 — known-answer vectors (16 lib tests, all green)

`no_movement_on_noise` · `admits_exactly_at_margin_boundary_plus_epsilon` ·
`burst_on_real_shift_turns_the_set_over` · `newborn_immunity_blocks_displacement`
· `weakest_among_evictable_not_weakest_overall` (age gates the victim pool
before want ranks it) · `since_admission_not_last_use_is_the_dwell_clock`
(THE clock law: a resident touched every cycle becomes evictable at exactly
admission+dwell — reds under any last-use-clock regression) ·
`fair_turn_sweep_terminates_and_rearms_only_on_growth` ·
`fair_turn_resumes_from_cursor_in_index_order` ·
`fair_admission_waives_margin_but_honors_dwell` · `identity_apply_no_double_load`
· `free_slots_fill_without_displacement` · `zero_want_is_a_valid_signal` ·
`non_finite_never_poisons` (kv_eviction::observe posture) ·
`weakest_evictable_tie_breaks_lowest_index` · `pure_core_matches_stateful`.

## G2 — steady-state latency (the fence, not an optimality claim)

`cargo bench -p katgpt-core --features pool_admission --bench
bench_873_pool_admission_goat` — best-of-240-chunks × 4096 cycles,
deterministic want patterns (mostly-reject hysteresis mix + periodic admit
bursts), `black_box` on arguments and results, checksum sinks (the
`timed_region_guard` law):

| path | measured | bar | headroom |
|---|---|---|---|
| consider + 2×update_want, K=32 | **75.6 ns/cycle** | ≤ 250 | 3.3× |
| consider + 2×update_want, K=256 | **422.9 ns/cycle** | ≤ 1500 | 3.5× |
| update_want alone, K=256 | **83.5 ns/touch** | (recorded, no bar) | — |
| fair_turn_next, terminated, U=4096 | **0.3 ns/call** | (recorded, no bar) | the O(1) rejection |

Box state: M3 Max, load 4–10 (two sibling agent sessions active — one
riir-reflex metal lane, one riir-neuron-db substrate plan; best-of-chunks
absorbs preemption spikes). O(live) is the contract; a breach means the scan
went quadratic or an allocation crept onto the per-cycle path.

## G4 — zero steady-state alloc

`g4_alloc_free_steady_state` (crate `TrackingAllocator`, the
`convergence_cadence` pattern, debug-gated per the counter design): 1000
cycles of update_want × K + one fair designation/admission + one ordinary
consider + the identity readout into a caller-owned buffer = **0 allocs**.
Allocation happens at construction and on universe growth only.

## Substrate check (substrate-first skill, Mode 1 — recorded per the gate)

- Searched: admission / evict / resident / want_score / hysteresis / dwell
  (`kv_eviction`, `UsageRow`, `set_admission`, `graph_stable_pool`);
  ewma / rate controller (`saddle_escape::FlipDetector`,
  `gain_cost_halt::GainCostLoopHalter`, `BreakevenTracker`); staleness /
  death (`calibration_staleness`, `decay_confidence`, `twist_cache`).
- Found: `kv_eviction` = the keep-side usage-rate scorer (composes — its
  `score` is the natural want-score producer); `set_admission` = retrieval
  fan-out gate (vocabulary false positive); `graph_stable_pool` = slot
  allocation (composes; policy ≠ allocator); no EWLS controller (B's gap);
  `calibration_staleness`/`decay_confidence` = different concepts.
- Decision: BUILD-NEW as the admission complement of `kv_eviction`
  (Research 581 row #6/#7/#8 "gap"), consuming the caller-supplied-signal
  house pattern.
- Architectural rules: raw-scalar deterministic policy over caller-owned
  state; no sync surfaces (the kv_eviction posture); modelless by
  construction; no new deps (BOUNDARY unchanged).

## Prior art (A4)

TinyLFU / W-TinyLFU (Caffeine) is the nearest published cousin
(frequency-sketch candidate-vs-victim admission). Deltas: the dwell immunity
window, the admission-tick clock, the TERMINATING fair-turn sweep (vs
W-TinyLFU's permanent admission window), and a multiplicative margin over
arbitrary caller-supplied want-scores (no sketch, no frequency assumption).
Full novelty table: Research 581 §4/§5.

[`DEFAULT_MARGIN`]: ../crates/katgpt-core/src/pool_admission.rs
[`ResidentRow`]: ../crates/katgpt-core/src/pool_admission.rs
[`kv_eviction`]: ../crates/katgpt-core/src/kv_eviction/mod.rs
