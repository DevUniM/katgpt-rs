# Micro-arena oracle fixtures — Plan 607 T5 (flappy v2 + lanes v1) · Issue 876 (flappy v3)

The laya-oracle fixtures for the two T5 micro-arenas, generated with the
same pipeline as the Tetris fixture (`tetris_oracle_laya_en_v2.jsonl`):
enumerate decision states in `katgpt-rs`, forward every option sentence
through riir-reflex's LOCAL laya lane (the G5-parity `RiirAgent`, english
checkpoint, CPU posture), self-join the per-option `p_clean` + argmax back,
and commit the provenance-digested result. Both arenas drift-check every
state byte-identically before any scoring.

| fixture | grammar | states × options | fixture blake3 |
|---|---|---|---|
| `flappy_oracle_laya_en_v2.jsonl` | `laya-flappy-v2` | 100 × 2 | `6a89e095…a71a` |
| `flappy_oracle_laya_en_v3.jsonl` | `laya-flappy-v3` | 100 × 2 | `88ac82bf…1fba` |
| `lanes_oracle_laya_en_v1.jsonl` | `laya-lanes-v1` | 100 × 3 | `6a6d02af…4f600` |

## Provenance

- Generator: `riir-reflex examples/laya_oracle_batch @ git 1c64d31`
  (riir-reflex origin/develop, 2026-09-23), english checkpoint, CPU
  posture, oracle blake3 as recorded per fixture in the `_meta` line
  (flappy v2 `0eab399f…7360d54`, flappy v3 `84b65b68…e2ccff`, lanes
  `23007714…803125f`). The v3 oracle ran at `63b1552` (one docs-only
  commit later — same laya lane), in an isolated worktree with the G5
  parity gate re-verified green at that commit before the run.
- Dumps (pre-oracle, byte-identical re-runs verified): flappy
  `76d0f5d4…e2aa1a`, lanes `3a5c7eb7…e5399b`; seed 607, 100 states each.
  The v3 dump is `cf1d7f9b…ab758` — the v3 corpus carries the IDENTICAL
  state set as v2 (same seed, same enumerator exclusions); only the
  render moved.

## Re-run

```bash
# dumps
cargo run --release --example flappy_01_state_enum -- --out-dir /tmp/607 --seed 607
cargo run --release --example lanes_01_state_enum   -- --out-dir /tmp/607 --seed 607
# oracle (in riir-reflex; weights under ~/.cache/riir-reflex/laya)
cargo run --release --features laya-riir --example laya_oracle_batch -- \
    --dump /tmp/607/flappy_oracle_manifest.jsonl --out /tmp/607/flappy_oracle.jsonl
# join (v2)
cargo run --release --example flappy_01_state_enum -- --out-dir /tmp/607 --seed 607 \
    --join /tmp/607/flappy_oracle.jsonl \
    --fixture-out tests/fixtures/flappy_oracle_laya_en_v2.jsonl \
    --oracle-blake3 <hex>
# arenas
cargo run --release --features state_option_scoring --example flappy_02_arena
cargo run --release --features state_option_scoring --example lanes_02_arena
# losslessness arms (incl. the v3 section)
cargo run --release --features state_option_scoring,template_decode --example decode_01_losslessness
```

## The flappy v1 → v2 grammar history (the measured trap)

v1 option sentences were `The bird {position clause}, {motion clause}.` —
the motion clause existed to guarantee the two options never tie. The v1
oracle NEVER preferred a coast sentence: argmax went to flap (index 0) in
**85/100 states**, pinning every scorer at the constant-pick ceiling
(85%) — laya's read keyed on the value-loaded motion clause ("rising"
reads safe) and ignored the gap-relative position clause that carries the
actual decision. This is laya's own "wording sensitivity" trap reproduced
in our own grammar, and the reason the grammar law changed: v2 renders the
position band ALONE, and the enumerator excludes both degenerate classes
(v = +2 lands both actions on one cell; same-band results render identical
sentences — the unbounded Below/Above bands tie most often), so every
committed decision has two distinct descriptions. The v2 oracle tracks
geometry (Bench 880: the fitted head reads 96/100 vs constant-pick 77).

## The flappy v2 → v3 widening (Issue 876, Bench 882)

v2's band alone was too coarse for decode-based consumption: the decoded
arm collapsed to constant-flap (77/100, ONE distinct pick — Bench 881).
v3 adds two clauses to the option sentence: a quantized OFFSET (fine
post_rel vs the gap center, clamped ±2 — "just under the center" …) and
a NEUTRAL post-motion clause ("holding this height" / "drifting down one
step" — kinematic, never "rising"). The structural caveat (stated in the
fixture `_meta` and the sim module): post_v is action-determined here
(flap ⇒ +2), so the motion clause inherently names the action — the
neutral wording + the offset anchor are the measured defense, and the v3
oracle did NOT degenerate (48 flap / 52 coast argmaxes, zero p ties).
Over the identical state set, the decoded arm (fills reconstructed into
the structured units) reads 96/100 = the structured arm (Δ0, 4/100 flips,
G1 HOLDS) — see `decode_01_losslessness`. The v2 fixture + its frozen
render (`flappy_sim::render_option_sentence_v2`) stay UNCHANGED — they
are the Bench 880/881 provenance and `flappy_02_arena`'s input.

## Schemas

Fixture line 0 is the `_meta` provenance record; each following line is one
state: `{state_id, grammar, question, state_sentence, state, options:
[{label, features, sentence, p_clean}], argmax}`. Option order is the
game's PINNED order (flappy `[flap, coast]` — index 0 = flap, the
lowest-index tie-break's referent; lanes `[left, middle, right]`); the
feature column order per game is pinned in the sim modules
(`flappy_sim::FEATURE_NAMES`, `lanes_sim::FEATURE_NAMES`) and carried in
the `_meta`'s notes. Oracle argmax is asserted (at join time) to equal the
p_clean argmax under the lowest-index tie-break.

Reading: `.benchmarks/880_micro_arena_goat.md`.
