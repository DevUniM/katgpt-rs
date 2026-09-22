# Bench 880 — Plan 607 T5: the Flappy + three-lanes micro-arenas (GOAT reading)

**Date:** 2026-09-23 · **Repo:** katgpt-rs · **Plan:** katgpt-rs Plan 607 T5
**Machine:** M3 Max (16-core), macOS 26.6.2, release profile; oracle on the
same box, CPU posture, sibling builds active throughout (load class: loaded
— the oracle timings are wall-clock context, never gate quantities).

## What this is

T5 is the default-on PRECONDITION for the `state_option_scoring` flag
(Plan 607 R4 — one arena cannot promote a flag): the same decision shape
Tetris exercised, re-proven on two structurally different micro-arenas —
Flappy (K=2 resulting-state decisions, laya's own recorded protocol:
"The bird is a little below the gap" → code derives the action) and
three-lanes (K=3 per-lane safety reads, laya's lanes demo with ONE pinned
noun per obstacle class). Both arenas replay committed laya-oracle fixtures
through the SAME two arms (T1 untuned sentence-cosine; T3 corpus-fitted
head) and read the SAME G1 gate shape (raw > constant-pick AND > chance,
never vs laya alone) + discrimination floor + determinism anchors.

## Headline

**G1 HOLDS on both arenas with the T3 fitted head.** The primitive surface
transferred with ZERO widening (`CentroidTable<D, K>` at K=4 padded; `HeadFitter<D>`
at D=9 — both already generic): T5 consumed the T1/T3 surface as-is.

| arena | T1 cosine | T3 head (in-corpus) | T3 head (LOO) | constant-pick | chance |
|---|---|---|---|---|---|
| Flappy v2 (K=2) | 39/100 | **96/100 (96.0%)** | 96/100 | 77/100 | 50.0% |
| Lanes v1 (K=3) | 9/100 | **84/100 (84.0%)** | 84/100 | 41/100 | 33.3% |

- **Generalization:** the in-corpus/LOO gap is 0.0 pp on BOTH arenas (Tetris
  T3 was 0.8 pp) — ridge + 8 standardized features keep the fit honest at
  n=100 states.
- **T1 fails on both** (39% / 9%, both under constant-pick): the untuned
  trigram-cosine arm is now 0-for-3 across game shapes (Tetris 10.8%). The
  corpus-fitted head is the lane's scorer — recorded, not relaxed.
- **The head beats the code-arithmetic policy at imitating laya on lanes**
  (84% vs clearest-lane 74%): laya's lane-safety read carries
  noun-dependent weights (rock/train/barrier), and the head absorbs them
  from the corpus — pure clearance ranking cannot. On flappy: head 96% vs
  gap-center policy 69% — same shape, laya prefers differently than pure
  center-seeking at the edges.
- **λ chosen by LOO MSE:** flappy 0.1 (MSE 0.010740), lanes 0.01 (MSE
  0.000118); the agreement number never entered selection.

## The flappy v1 negative — our own wording trap, measured

The first flappy grammar (v1) carried a motion clause in the option
sentence (", rising." / ", falling fast.") to guarantee the options never
tie. The v1 oracle **never preferred a coast sentence: argmax went to flap
in 85/100 states**, pinning BOTH arms at the constant-pick ceiling (85%)
— G1 unpassable by construction. Laya's read keyed on the value-loaded
motion clause and ignored the position clause carrying the actual
decision. This is laya's own measured "wording sensitivity" trap
("barrier" 0.75 vs "train" 0.45) reproduced in OUR grammar — and the fix
was structural, not tuning: grammar v2 renders the position band ALONE and
the enumerator excludes both degenerate classes (v = +2: both actions land
on one cell; same-band results: identical sentences). The v2 oracle tracks
geometry, and the same scorer that tied constant-pick under v1 reads 96%
under v2. Full story: `tests/fixtures/micro_oracle_README.md`.

## Gates

| gate | flappy v2 | lanes v1 | bar |
|---|---|---|---|
| G1 raw > constant-pick AND > chance | 96 > 77 ∧ 96 > 50 **HOLDS** | 84 > 41 ∧ 84 > 33.3 **HOLDS** | both |
| G1a discrimination floor | 2 distinct picks PASS | 3 distinct picks PASS | ≥ 2 |
| G2 latency per decision SET | p99 42 ns (K=2) | p99 42 ns (K=3) | ≤ 1 ms, option count printed |
| G3 no-regression | katgpt-core untouched by T5 | same | counts pinned |
| G4 alloc-free | formal rows = bench_878 + state_option_head_alloc_check (unchanged primitive) | | 0 allocs |
| determinism | double-fit bit-identical ✓; two decision passes byte-identical ✓ | same | bit-identical |

Anchors — flappy: head `4ac0a13c…1aae3`, decisions `cc89ff49…00cd94`,
λ=0.1; lanes: head `7d3f1d8e…09d34`, decisions `8d2f9c75…43345`, λ=0.01.
Fixture provenance: flappy `6a89e095…a71a` (dump `76d0f5d4…`, oracle
`0eab399f…`), lanes `6a6d02af…4f600` (dump `3a5c7eb7…`, oracle
`23007714…`).

## Play-loop context (NOT a gate)

- Flappy (16 seeded flights, cap 100 pipes): gap_center 3.00 mean ·
  t3_head 1.50 · always_flap 1.31 · t1_cosine 0.44 pipes. The head beats
  constant-flap but trails the code policy — the head imitates LAYA, and
  laya agrees with gap-center only 69%: agreement-with-laya ≠
  flight-optimality. That is the lane's claim exactly: match the model's
  state read at ~10⁵× lower cost (p99 42 ns vs ~124 ms/forward, zero
  weights), never out-fly arithmetic — laya's own protocol says code does
  the arithmetic.
- Lanes (16 seeded runs, cap 60 steps): clearest 8.38 mean · t3_head 1.44 ·
  always_middle 0.94 · t1 0.69 steps survived. Same pattern.

## Latency honesty (the matched-units precondition, T6's law)

Both figures are per DECISION SET on this box: our p99 42 ns/set (K=2 or
K=3, D=9); laya ~124 ms per FORWARD on the same CPU posture — and a laya
decision here costs one forward PER OPTION (2–3 forwards, 250–370 ms per
decision set). Ratio ≈ 10⁶–10⁷×, zero model weights vs 650 MB. T6 restates
the consolidated number at matched units before any citation.

## Oracle economics

200 + 300 forwards at ~120 ms (flappy 24.0 s, lanes 36.5 s wall) — the
fixture pipeline stays cheap because the oracle is a LOCAL G5-parity lane,
not a published API. Re-run commands in
`tests/fixtures/micro_oracle_README.md`.

## Re-run

```bash
cargo run --release --features state_option_scoring --example flappy_02_arena
cargo run --release --features state_option_scoring --example lanes_02_arena
```

## Verdict

**GO for the plan's purpose** — T5's precondition is satisfied: G1 holds on
a second and third game shape with zero primitive widening, and the
constant-pick/chance baselines are beaten by wide margins on both. The
flag stays opt-in pending T6/T7 close-out (bench-doc consolidation +
AGENTS.md feature-table rows); any default-on promotion remains gated on
the plan's own bar plus a production consumer, which no arena provides.
