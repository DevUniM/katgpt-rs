# Bench 881 — Plan 607 T2: bounded template decode, the losslessness arm

**Status:** RECORD — T2 measured; all three decode layers exact; the agreement
delta splits the arenas three ways (super-lossless / lossless / lossy-to-constant).

- **Date:** 2026-09-23 · box: M3 Max aarch64, release profile, AC power
- **Plan:** [607](../.plans/607_modelless_game_lane.md) T2 (Gate A standing
  approval — the T4 first reading showed the sentence arm at the constant-pick
  tie, which is decode-relevant evidence, so the lapse condition did not fire)
- **Primitive:** katgpt-core `template_decode` (new, opt-in, independent —
  `template_decode = []`): closed-grammar template tables, `decode` →
  (template, fill indices), loud `Unknown`/`Ambiguous` refusals,
  `verify_closed` full-fill-product proof, zero-alloc decode, `u8` fills /
  ≤ 8 slots / ≤ 256 vocabs asserted at build.
- **Tables:** `examples/common/grammar_tables.rs` — the three protocols
  (`laya-tetris-v2` spot + state, `laya-flappy-v2` option + state,
  `laya-lanes-v1` option), vocabulary order = feature ordinal (contract);
  forward mappers mirror the renderers' matches, corpus round-trip is the
  drift detector.

## The decode layer (asserted before any scoring)

- closed-space proof: **5/5 tables `verify_closed` PASS** over their full fill
  products (cap 100_000) — ambiguity-free by construction, not by sampling.
- tetris: **2660/2660** option sentences decode, re-render byte-identical,
  fills == the semantic forward; **120/120** state sentences (spread + flat
  shapes).
- flappy: **200/200** option sentences + 100/100 state sentences; pre-v and
  gap-half recover EXACTLY (the motion/width vocabularies are bijective on
  the pinned domain).
- lanes: **300/300** lane sentences; decode == semantic forward per lane.

## The structured-arm anchors (the recipe-equivalence proof)

The T2 width-genericized fit recipe (`micro_fit`: `Standardizer<F>` +
`HeadCorpus<D>` + method-level `design<const D>`) reproduces every published
structured arm bit-identically — asserted in the example:

| arena | in-corpus | LOO | head blake3 (published anchor) |
|---|---|---|---|
| tetris (F=11, D=12) | 36/120 | 35/120 | `65409c14fd7573c6ea821d2d32ab9aa44cbda2f59c707759db2df39870fa2e66` (full match) |
| flappy (F=8, D=9) | 96/100 | 96/100 | `4ac0a13c…1aae3` (prefix match; re-run of `flappy_02_arena` byte-identical) |
| lanes (F=8, D=9) | 84/100 | 84/100 | `7d3f1d8e…9d34` (prefix match; re-run of `lanes_02_arena` byte-identical) |

Also re-run byte-identical: `tetris_03_head_fit` (head `65409c14…2e66`,
decisions `04644b0c…8fb0c`). The genericization is arithmetic-identical —
G3 no-regression held by digest, not by argument.

## The reading — the agreement delta (decoded − structured)

| arena | structured in/LOO | decoded in/LOO | Δin | Δloo | LOO flips | distinct s/d | verdict |
|---|---|---|---|---|---|---|---|
| tetris | 36/120 · 35/120 | **44/120 · 44/120** | **+8** | **+9** | 77/120 | 22/23 | **decoded BEATS structured — G1 HOLDS** |
| flappy | 96/100 · 96/100 | 77/100 · 77/100 | −19 | −19 | 19/100 | 2/**1** | **decoded arm degenerates to constant-pick — G1 DOES NOT HOLD** |
| lanes | 84/100 · 84/100 | 84/100 · 84/100 | +0 | +0 | **0/100** | 3/3 | **exactly lossless — identical head, 0 flips** |

Baselines (published): constant-pick 13/120 (tetris) · 77/100 (flappy) ·
41/100 (lanes); chance 5.5% / 50% / 33.3%.

### Findings

1. **Tetris — the render carries MORE laya-relevant decision information
   than the structured numerics (Δ +8/+9).** The oracle reads the SENTENCE
   (it never saw the structured state), so laya's read is a function of the
   grammar's bands — including the position/side band the 11 Dellacherie-class
   features never had. The decoded head (5 band ordinals, λ=1) tracks that
   function better than the numeric head (λ=0.1): 44/120 vs 36/120, and LOO ==
   in-corpus at 44 — the 5-column fit generalizes as well as it fits. The 77/120
   LOO flips say the two arms are genuinely different function classes, and on
   the laya-imitation metric the sentence-aligned one wins. The columns the
   render "drops" (bumpiness, wells, transitions, eroded) were never
   decision-relevant TO LAYA.
2. **Flappy — the render is the bottleneck (Δ −19, discrimination FAIL).**
   The v2 grammar renders the post-placement position band ALONE (the v1
   motion clause was the measured confound); the structured head reads exact
   post_rel + post_v and reaches 96. The decoded arm (band ordinal + banded
   pre-rel + exact pre-v/h) collapses to 77/100 with ONE distinct pick — the
   constant-flap ceiling. The band is too coarse for the ridge head to beat
   constant-pick at imitating laya. This is the plan's "(a) non-zero delta is
   a finding about the RENDER" branch, at maximum severity: the flappy v2
   render would need re-widening (e.g. a quantized offset clause) before any
   decode-based consumer could act on it. NOT fixed here by tuning — recorded
   as the render-side work item.
3. **Lanes — exactly lossless (Δ 0, 0 flips).** All 300 decoded rows are
   bit-identical to the structured rows; the decoded corpus fits the
   IDENTICAL head (digest equality asserted). The lanes grammar encodes every
   feature the structured read uses; decode recovers it perfectly. This is
   the lossless anchor of the whole arm: when the render carries the
   features, the sentence arm IS the structured arm.

### The R6 verdict

The head-to-head belongs at the feature boundary, and the measurement now
says the boundary CUTS BOTH WAYS per arena: decoding a third party's
laya-format traffic is exactly lossless for lanes, strictly BETTER than the
available numerics for tetris, and render-limited for flappy (the grammar,
not the decoder, is what would need to change). Decode-only, corpus-limited:
the primitive claims nothing beyond the pinned tables.

## Validation

- `cargo test -p katgpt-core --features template_decode --lib` → 2074 passed
  (11 new `template_decode` module tests: round-trip, loud refusals, prefix
  backtracking, empty fills, multi-template dispatch, full-space verify,
  cross-template collision, three build-refusal arms) — test-gate row
  `katgpt-core:2074:template_decode`.
- `cargo test --release --features state_option_scoring,template_decode
  --example decode_01_losslessness` → 35 passed (corpus decode exactness
  ×3, lanes losslessness, decoded-head bit-determinism).
- clippy `-D warnings` posture clean on the module + all touched examples.
- `count_features` green (README/examples flag counts re-pinned 640→641).
- Anchors byte-identical on `flappy_02_arena` / `lanes_02_arena` /
  `tetris_03_head_fit` post-genericization (the G3 row above).

## Re-run

```bash
cargo run  --release --features state_option_scoring,template_decode --example decode_01_losslessness
cargo test --release --features state_option_scoring,template_decode --example decode_01_losslessness
cargo test -p katgpt-core --features template_decode --lib
```

All numbers from THIS box (M3 Max aarch64, release). The decode layer and the
deltas are fixture-pinned and re-derive byte-identically; the fits are
f64-deterministic (two-box portable per the T3 determinism law).
