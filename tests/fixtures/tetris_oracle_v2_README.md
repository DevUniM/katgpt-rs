# Tetris laya oracle fixture v2 (katgpt-rs Plan 607 T0b)

The G1 oracle fixture for the modelless game-decision lane: laya's
per-option P(clean) and per-state decision over the T4a Tetris state dump.
The T4 arena replays this fixture — agreement with `argmax` is the G1 gate.

## Provenance

| field | value |
|---|---|
| dump generator | `cargo run --release --example tetris_01_state_enum` (katgpt-rs, seed 607, grammar `laya-tetris-v2`) |
| dump blake3 (pre-join) | `aa07b3b4ea75afca60fe5c6c7b75c0c4eca27383f44b32e5985dfe6cd64f4e72` |
| oracle generator | `riir-reflex examples/laya_oracle_batch` @ git `e4bf657` (origin/develop 2026-09-22; run re-verified byte-identical from the committed generator) |
| checkpoint | `english` (ModernBERT-large, max_len 512) |
| oracle blake3 (raw decisions) | `2261dbf349c1b3787b5c378875e4df3e2ad9d67dfd669405ae813088ed4e6537` |
| forwards | 2,660 (one `noul` forward per option sentence, ~124 ms each, 396 s wall) |
| question | `Does the stack look clean?` (world-anchored, never "what to do") |

## Shape

Line 1 is a `_meta` record (the table above, machine-readable). Each
following line is one state:

- `state_id` — `arch:<board>:<piece>` (authored archetype) or
  `playNN:MMM` (seeded Dellacherie-greedy ladder).
- `options[]` — the pinned order (rotation asc, then column asc); each
  option carries its grammar `sentence`, the structured outcome
  `features`, and laya's `p_clean` for it.
- `argmax` — laya's decision over the options, **lowest-index tie-break**.

## The tie record (honest equivalences)

33/120 states carry an exact `p_clean` tie for the best option — every one
a **same-sentence** tie (two options whose grammar descriptions are
byte-identical; concentrated on symmetric boards — `empty`, `well_left`,
`floor_low/high`, `right_stack`). These are honest grammar equivalences,
not oracle noise: the v1 two-clause grammar tied 66/120 (heavily
cross-sentence), and the v2 widening (side + resulting-height clauses)
took cross-sentence ties to zero. The arena must apply the same
lowest-index tie-break the oracle pinned.

## Measured oracle sanity (not a gate — recorded context)

- `p_clean` spans 0.027–0.850 across the corpus (the checkpoint reads the
  sentences; it is not constant-picking).
- Spearman(p_clean, Dellacherie score) per state: mean **+0.365**,
  positive in 94/120 states — laya prefers clean placements, loosely
  aligned with the classic heuristic.

## Regeneration

The dump side is fully deterministic (`tetris_01_state_enum`, seed 607 →
byte-identical blake3). Regenerating the ORACLE side needs the laya
weights (`~/.cache/riir-reflex/laya`, or `LAYA_WEIGHTS_DIR`/`LAYA_HOME`)
and the generator example above; the fixture's provenance pins the exact
generator commit. Copying the laya forward INTO katgpt-rs is forbidden by
the lane split (Plan 607) — the committed fixture is the drift detector
(the katgpt-device-verify rule).
