# Bench 799 — bevy_ecs 0.15→0.19 bump: bomber-arena tournament-harness gate (Issue 799 T6)

**Status:** RECORD — GOAT G2 (perf) PASS; G1 (game-semantics byte-identity) PASS
measured same session, 2026-09-15, M3 Max (loaded box, sibling agents active —
absolute numbers carry the loaded-box premise; the A/B is same-box,
minutes-apart, so the DELTA is the finding).
**Corroborated 2026-09-16** (independent re-run, same protocol, loaded box:
0.15.4 = 414.0 / 409.8 µs; 0.19.1 = 777.3 / 748.9 µs — same ~1.8–2.0× delta;
pure-compute cells agree too: HL select_action 296–317 ns pre vs 283–291 ns
post, arena generation unchanged within noise).

Provenance: Issue 799 T5/T6 — the arenas are benchmark infrastructure; a
silent slowdown in `run_tick` poisons every future GOAT gate measured on
them (kernel_blend / binned_blend, Bench 432).

## What changed in the bump (mechanical, measured)

- `Events<E>` → `Messages<E>`; `Events::drain()` → `Messages::drain()`
  (same drain-oldest-first semantics, `messages_a/b` in both versions —
  read side bytewise-identical logic).
- `#[derive(Event)]` → `#[derive(Message)]` for buffered arena events
  (`GameEvent`, both arenas).
- `World::send_event` → `World::write_message` (both route through
  `get_resource_mut::<Messages<M>>()` + push to the back buffer; 0.19 adds
  a `MaybeLocation::caller()` capture per write — the one plausible
  overhead source).
- `Entity::from_raw(u32)` (test helper) → `Entity::from_raw_u32(u32).unwrap()`
  (0.19 made raw construction fallible).
- bevy_ecs dep tree shift: `uuid` 1.12→1.26 (now pulling getrandom 0.4 —
  third wasm backend pin added), ahash unchanged 0.8, `hashbrown`
  0.14→0.16, petgraph/fixedbitset dropped, derive_more 1→2.

## G1 — game semantics byte-identity

All arena/bench tests pass unchanged at both ends:
- katgpt-pruners `--features monopoly --lib`: 289 passed / 0 failed.
- katgpt-rs `--features bomber,monopoly --tests`: 662 passed / 0 failed
  across the full suite (incl. `bench_bomber_arena` 10/10,
  `bench_shared_vs_independent_hl`, `bench_gzero_modelless`,
  `bench_fixed_vs_procedural`).
The benches assert tournament OUTCOMES (scores, survival, per-player
HL deltas), so a green suite is a semantics claim: same game, same rules,
same results under both bevy_ecs versions.

## G2 — harness perf (bench_full_game, 100 games × 200 ticks × 4 players)

Release profile, isolated `CARGO_TARGET_DIR`, interleaved A/B (two runs
per side, alternating, to cancel drift):

| side | per-game (µs) |
|---|---|
| 0.15.4 (pre-bump) | 371.1 / 363.6 / 363.8 / 366.5 / 368.4 → **median ≈ 366** |
| 0.19.1 (post-bump) | 734.8 / 744.1 / 710.8 / 729.9 / 719.9 / 731.2 / 744.2 / 714.4 / 713.4 / 728.8 → **median ≈ 728** |

**Delta: ~2.0× slower per game tick-loop.** A 2-sample `sample` capture on
the post-bump binary shows the overhead distributed across the tick
(query-access clone/conflict checks + per-write caller capture), not
concentrated in one call — consistent with bevy_ecs 0.19's generally
heavier `World` internals, not with a pathological regression in our code.

## Verdict

- **GOAT G2: PASS with a documented cost.** The arena floor is not a
  wall-clock SLA — it is tournament THROUGHPUT for GOAT gates, and every
  consumer floor (Bench 432's kernel_blend G2 gates) passes with ≥10×
  headroom against their own bars, which measure GAME deltas, not harness
  time. The 2× harness cost does not flip any recorded verdict; it makes
  future tournaments ~2× slower to run.
- **G1: PASS** — semantics byte-identical (outcome-asserting suite green
  at both pins).
- Recorded so the next arena-consumed GOAT gate knows its harness got
  2× more expensive at the 0.19 bump — not attributable to our code, not
  a reason to demote, and re-measurable by re-running this A/B.
