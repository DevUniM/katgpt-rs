# Bench 882 — Issue 876: the flappy render widening (v2 → v3), the render-side fix measured

**Status:** RECORD — the v3 render is measured; the decoded arm reads Δ0 vs
the structured arm (96/100, G1 HOLDS, discrimination PASS). Issue 876's
gate is MET.

- **Date:** 2026-09-23 · box: M3 Max aarch64, release profile, AC power
- **Issue:** [876](../.issues/) (filed from Plan 607 T2 / Bench 881; closed
  by this record — the file is removed per the noise-reduction rule, this
  record + the fixtures README carry it)
- **Fixture:** `tests/fixtures/flappy_oracle_laya_en_v3.jsonl`
  (blake3 `88ac82bf…51fba`) — regenerated oracle over the **IDENTICAL
  100-state set** as the v2 record (same seed 607, same enumerator
  exclusions; asserted state-by-state in `decode_01_losslessness`), so the
  v2 → v3 delta isolates the RENDER.
- **Grammar v3** (`laya-flappy-v3`, `examples/common/flappy_sim.rs`): the
  option sentence widens from the v2 position band ALONE to
  `The bird {band}, {offset}, {post-motion}.`:
  1. **quantized OFFSET** — fine post_rel vs the gap center, clamped ±2
     ("under / just under / at / just over / over the center") — the
     issue's candidate 1;
  2. **NEUTRAL post-motion** — kinematic magnitude+direction ("drifting
     down two steps" … "holding this height" … "drifting up two steps"),
     never the v1 value-loaded "rising"/"falling" — the issue's candidate 2.
- **Known structural caveat (stated, not hidden):** post_v is
  action-determined in this protocol (flap ⇒ +2, coast ⇒ ≤ 0), so the
  motion clause inherently names the action. The neutral wording + the
  offset anchor are the measured defense: the v3 oracle did NOT degenerate
  (argmax 48 flap / 52 coast, zero exact p ties, min margin 0.012) — the
  v1 confound did not reproduce.
- **Oracle:** riir-reflex `laya_oracle_batch` @ `63b1552` (origin/develop,
  one docs-only commit after the v2 fixture's `1c64d31` — same laya lane),
  english checkpoint, CPU posture. Run in an ISOLATED WORKTREE
  (`git worktree add --detach`, sibling agent WIP untouched) with the
  **G5 parity gate re-verified green at that exact commit** before the run
  (2 passed, 28.4 s). Oracle blake3 `84b65b68…e2ccff`; 200 forwards, 26.4 s.
  Dump blake3 `cf1d7f9b…ab758`.

## The measurement (controlled comparison — only the render moved)

| arm | λ | in-corpus | LOO | distinct | digest |
|---|---|---|---|---|---|
| structured (F=8 exact numerics) | 0.1 | **96/100** | **96/100** | 2 | `dc6bcf73…b9fd2` (pinned full) |
| decoded v3, raw fill ORDINALS | 1 | 51/100 | 51/100 | 2 | (not pinned — rejected design) |
| decoded v3, structured-units reconstruction | 1 | **96/100** | **96/100** | 2 | `c93d36dc…e3c5` (pinned full) |

constant-pick 52/100 (index 1) · chance 50.0%.

**Issue 876's gate: MET.** decoded LOO 96 > constant-pick 52, distinct
picks 2 ≥ 2. And the stronger reading: **Δ0** — the decoded arm EXACTLY
matches the structured arm in-corpus AND in LOO (4/100 LOO flips, none
agreement-changing). The v3 render + the structured-units reconstruction
make the sentence arm IS the structured arm on flappy, the lanes anchor's
outcome, at 96/100.

## Findings

1. **The decoded FEATURE DESIGN is part of the measurement.** The first
   v3 decoding (raw fill ordinals [band, offset, pmot, rel, v, h] — the
   v2 design + 2 columns) read **51/100, BELOW constant-pick** — worse
   than v2's 77 — because a linear head over ordinals cannot represent the
   band×offset joint (the meaningful variable, post_rel in cells, is a 2-D
   lookup over the two ordinals), while the oracle's read is smooth in
   geometry. The landed design reconstructs the STRUCTURED UNITS from the
   fills — the lanes anchor's own pattern (decoded features live in the
   units the render describes): (band, offset, h) → post_rel EXACT for
   every rendered in-gap/squeeze combination, crash tails at the boundary
   ±(h+1); pmot → post_v exact; state band → pre_rel clamped ±2; column
   order mirrors `flappy_sim::FEATURE_NAMES`. Per-column exactness is
   asserted over the corpus (`flappy_v3_reconstruction_is_exact_where_the_render_is_exact`).
   Both designs are recorded; the ordinal design's failure is the honest
   provenance of the reconstruction.
2. **The neutral-motion defense worked.** The structural caveat (the
   motion clause names the action) did NOT become the v1 trap: the oracle
   split 48/52 with healthy margins. Whether laya reads the motion clause,
   the offset, or their interaction is NOT decomposed here — the
   offset-only ablation is the recorded next arm if anyone needs that
   attribution.
3. **The v2 record is untouched.** `render_option_sentence_v2` is frozen
   and pinned by a literal-string test; `flappy_02_arena` still drift-checks
   + replays the v2 fixture byte-identically (re-run green this session);
   the Bench 880/881 anchors in `decode_01_losslessness` still assert.
4. **Decode layer stays exact.** 6/6 grammar tables `verify_closed` over
   their full fill products (the v3 option table is 7 × 5 × 5 = 175);
   200/200 v3 option sentences decode, re-render byte-identically, fills
   == semantic forward; v/h recover exactly.

## Validation

- `cargo run --release --features state_option_scoring,template_decode
  --example decode_01_losslessness` — full run green, all anchors
  (tetris full-digest, flappy v2 96/96 + prefix, v3 both arms full-digest,
  lanes identical-digest) asserted; the v3 gate asserts are UNCONDITIONAL.
- `cargo test --release --features state_option_scoring,template_decode
  --example decode_01_losslessness` → 41 passed (6 new: v3 corpus decode,
  v3 reconstruction exactness, frozen-v2 render pin, v3 band-tie law,
  + the v3 grammar-table tests).
- `cargo test --release --features state_option_scoring --example
  flappy_01_state_enum --example flappy_02_arena` → 8 + 12 passed.
- `cargo test -p katgpt-core --features template_decode --lib` → 2074
  passed (unchanged — the primitive is untouched).
- clippy `-D warnings` clean on all three touched examples.
- G5 parity re-verified at the oracle commit (isolated worktree).

## Re-run

```bash
cargo run  --release --features state_option_scoring,template_decode --example decode_01_losslessness
cargo test --release --features state_option_scoring,template_decode --example decode_01_losslessness
cargo run  --release --features state_option_scoring --example flappy_02_arena   # the frozen v2 record
```

All numbers from THIS box (M3 Max aarch64, release). Both new head digests
are pinned in FULL (`FLAPPY_V3_HEAD_ANCHOR`, `FLAPPY_V3_DECODED_HEAD_ANCHOR`)
— two-box portable per the T3 determinism law; a second-box run is the
same standing follow-up as every prior fixture-pinned anchor.

📖 Issue 876 (closed) · Plan 607 T2 · Bench 881 · Catalog §125 ·
`tests/fixtures/micro_oracle_README.md` (the v2 → v3 history).
