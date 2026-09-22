# Bench 876 — state_option_scoring GOAT (Plan 607 T1 + T4 first reading)

**Status:** FIRST GOAT READING RECORDED — G2/G4/determinism PASS; **G1
(agreement vs the oracle) DOES NOT HOLD** — the honest reading that gates
{T2, T3}. Date: 2026-09-22 · Box: M3 Max (macOS 26.6.2, aarch64), AC
power, sibling agent sessions active (light) · Profile: release.

## What landed

- **T1** — `katgpt-core::state_option_scoring` behind the opt-in feature
  `state_option_scoring = ["distance_abstain"]` (root forward for the
  arena). `CentroidTable<D, K>`: unit-normalize-once option table (the
  determinism-committed state) + `exact_sigmoid(scale · cosine)` scoring +
  the pinned lowest-index argmax (`cmp_for_max` + reverse-index, the same
  comparator shape `pick_domain` uses and the tie-break the T0b oracle
  fixture pins). Generic by law (R4): vectors in, decisions out; nothing
  arena-specific in katgpt-core. The compression drafter stays OUT of the
  per-decision loop (R3).
- **T4** — `examples/tetris_02_option_arena.rs` + the arena-side
  deterministic trigram embedder `examples/common/hash_embed.rs`
  (substrate note: no in-tree generic TEXT embedder exists — engram hashes
  CanonicalId token ids; reflex/clippy span embedders are their repos' own
  code — so minimal arena glue, UNTUNED by plan). The arena drift-checks
  the T0b fixture (all 120 states / 2,660 options recompute
  byte-identically: placements, features, both sentence layers) before any
  scoring.

## Gates

| gate | result | evidence |
|---|---|---|
| G1a planted correctness (bench, synthetic) | **PASS 200/200** | planted perfect match wins at every rotating index across 200 sets |
| G1b discrimination floor | **PASS distinct=34** | ≥ 2 bar (reflex floor form); constant-pick fraction 14.5% (max single-pick freq) |
| G1 agreement vs the T0b oracle triples (arena) | **DOES NOT HOLD** | raw 13/120 (10.8%) == constant-pick baseline 13/120; chance 5.5%; detail below |
| G2 latency | **PASS** | p99 per decision SET **1,125 ns (K=9) / 2,250 ns (K=17) / 4,083 ns (K=34)** — ≤ 1 ms bar with 3 orders of magnitude headroom; option count printed beside every row (n=2000, tail@p99 = 22–119) |
| G4 alloc | **PASS** | `state_option_scoring_alloc_check`: 0 allocs / 0 deallocs across 100 steady-state decision sets at K=34, D=64 |
| determinism | **PASS** | double-build bit-identical; two full arena passes byte-identical; digests below |
| G3 no-regression | **PASS** | default `--lib` 2063 passed (floor 2060 — pre-existing agent drift upward, not this change); the module + its 8 tests compile out at default features |

## The G1 reading (the finding that gates {T2, T3})

Untuned T1 sentence-cosine scorer vs laya's recorded decisions over the
T0b fixture (120 states / 2,660 options):

- **raw argmax agreement: 13/120 (10.8%)** — exactly TIES the
  constant-pick baseline (always the oracle-majority index 16: 13/120).
  The bar is strict `>`, so G1 **does not hold**.
- chance baseline: 5.5% — raw clears chance but not constant-pick.
- class-level agreement (same-sentence equivalence): 13/120 — the oracle's
  33 same-sentence ties (count re-derived from the fixture's option-level
  p_clean, **matching the fixture README's pinned 33**) contribute only 2
  tied-twin hits; not the story.
- vs the Dellacherie argmax (context): 7/120 — the untuned sentence
  scorer is not secretly the classic heuristic either.
- discrimination: 21 distinct picks over 120 states — the scorer is NOT a
  constant picker (the reflex T7 failure mode is absent); it discriminates
  and is simply not yet ACCURATE.
- lines-cleared context (8 seeded games/policy, shared piece streams, cap
  500 placements): Dellacherie mean 195.6 lines vs T1-sentence mean 3.4
  (tops out at 382 placements total) — the untuned scorer plays far below
  the classic heuristic, consistent with the agreement numbers.

**Verdict per plan:** the first GOAT reading gates {T2, T3} — both levers
are now evidence-directed: T2's losslessness arm (decode the sentences,
score the structured arm, report the agreement DELTA) and T3's
corpus-fitted head (the plan's "80–90% corpus-viable" lever, determinism
constrained) are the mechanisms that can close a 10.8% vs ~31% (chance
is 5.5%; a good scorer must first clear constant-pick) gap. No embedder
or scale tuning happened in this unit (recorded anti-goal: the first
reading must measure the untuned scorer; the argmax is scale-invariant
anyway).

## Determinism anchors (two-box comparison — the standing claim)

- bench table blake3: `f2e231b2d7f6eca8859613f17f237f33e03c968adfdb6d459f339edc72b0b3dc`
- bench decisions blake3: `8f5d9f9176ada34d74cd5c3bd2ab5f9454e5cdc186c22b7a3c7d1c7a3233e5f2`
- arena two-pass digest: `1921b19ae3891e902373c50ad4b1c95c62d1e55cf876f423567f3694438815cf`

All three from THIS box (M3 Max aarch64, release). A second box re-running
`cargo bench -p katgpt-core --features state_option_scoring --bench
bench_876_state_option_scoring_goat` and
`cargo run --release --features state_option_scoring --example
tetris_02_option_arena` must print byte-identical digests. (The 4090 leg
was not run this session — the digests above are the anchors to compare.)

## Latency context (arena end-to-end, informal)

embed(state) + 34 embeds + table build + pick = p50 5,125 ns / p99 8,125 ns
per state (n=3000) — the formal bar is the bench's per-decision-SET p99
above; both are µs-scale against the 1 ms bar.

## Test-gate wiring (the executing lanes)

- `katgpt-core:2079:state_option_scoring` — the module's 8 lib tests +
  distance_abstain's 8 (feature implication) over the 2063-test default
  base, measured at landing.
- `katgpt-core:1:state_option_scoring_alloc_check:state_option_scoring` —
  the G4 binary (PERF_ROWS grammar, `--release --test-threads=1`).
- The arena's 3 example tests (drift check, decision determinism,
  discrimination floor) run via `cargo test --example
  tetris_02_option_arena --features state_option_scoring` — same
  example-test standing as tetris_01 (no test-gate lane; the fixture is
  provenance-digested, and the drift detector is what regeneration runs).

## Re-run commands

```bash
cargo bench -p katgpt-core --features state_option_scoring --bench bench_876_state_option_scoring_goat
cargo test  -p katgpt-core --features state_option_scoring --test state_option_scoring_alloc_check
cargo run   --release --features state_option_scoring --example tetris_02_option_arena
cargo test  --release --features state_option_scoring --example tetris_02_option_arena
```
