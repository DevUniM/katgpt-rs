# Bench 848 — Engram-Fused PUCT Arena G5 (Issue 868 / Plan 605 / Proposal 013)

**Verdict: NEGATIVE — G5 FAIL. The feature stays opt-in; no promotion is claimed.** Every
strength arm failed or showed no gain, and the T1.3 sanity gates make the failure
interpretable: the mechanism fired everywhere but the count-based evidence gate — working
exactly as designed — damped it to near-zero influence, because 9×9 self-play transpositions
are too rare to accumulate evidence.

Issue: `.issues/868_engram_fused_puct_arena_poc.md` (record lives in git history after the
noise-reduction removal) · Plan: `.plans/605_engram_fused_puct_poc.md` · Proposal:
`.proposals/013_engram_fused_puct_memory_augmented_moka_search.md`

## Box state

M3 Max (aarch64, macOS 26.6.2), release profile, isolated `CARGO_TARGET_DIR=/tmp/e868/target`.
Concurrent sibling agent sessions were active during the runs (mild load; the measured
1.12 s/game arena rate matches the miner's 1.14 s/game, so contention was not material).
Not a GPU measurement — CPU-only int8 path.

## Phase 1 — mining + T1.3 sanity gates (240 self-play games, b50/c1.5/k8)

272.7 s total; **16,930 distinct positions** from 17,066 plies — only 136 repeat visits.

| Gate | Measured | Reading |
|---|---|---|
| Count distribution | p10=p25=p50=p75=p90=p99=**1**, max **35** | transpositions are nearly absent at this scale |
| Rumor fraction (n<4) | **100.0%** | every mined row is a rumor by the issue's own standard |
| Hit-rate curve (2¹⁶/2¹⁸/2²⁰) | fires **100%** at every size | table size is not the bottleneck |
| Evidence gate ≥ 0.5 | **4 / 16,930 = 0.02%** | the gate suppresses essentially ALL memory influence |
| Collision audit (2²⁰) | 2,088 multi-owner slots across 16 heads; **22.0%** of entries share ≥1 slot | modest contamination, mostly mooted by the gate |

Frozen table: 16,930 entries, n_slots 2²⁰, BLAKE3 root `8453c1479d8dddfa…` (deterministic
build, G6 pinned by tests).

## Phase 3 — arena arms

### G5 head-to-head (PRIMARY) — fused vs plain, paired, n=616

**296/616 = 48.1%** (draws 0) — **FAIL**. Wilson one-sided 95% lower **44.8%** < 50%;
two-sided 95% [44.1%, 52.0%]; Clopper–Pearson exact lower 44.7%. The CI includes 50%, so
this is "no gain detected" (and, if anything, the point estimate leans slightly negative) —
recorded as FAIL per the strict lower-bound gate. Runtime 692 s (1.12 s/game).

Fusion telemetry: **1,055,917 lookups, 1,039,205 fires = 98.4%** — the memory was READ at
essentially every expansion. Combined with T1.3: fires were universal, influence was ~0.
The issue's two failure modes are now SEPARATED by measurement: it is not "memory never
fired"; it is "memory fired and the evidence gate correctly refused to trust rumors".

### T3.2b independent-opponent control — vs GREEDY, same seeds/colors, n=100 each

- fused vs GREEDY: **93/100 = 93.0%**
- plain vs GREEDY: **97/100 = 97.0%**
- delta (fused − plain): **−4.0 pp** (1.3σ at n=100 — not significant)

⛔ **First run of this arm was corrupted by a reward-inversion bug** (White-game rewards
counted for the PUCT arm, forcing both arms to ~50% — the observed 51/51 tie was the
artifact, not a measurement). Caught reviewing the output against the harness reference
(85–94% vs GREEDY); fixed (`1.0 − reward` when the PUCT arm holds White) and re-measured.
The numbers above are the corrected run. The primary h2h and the budget arm were NOT
affected (both invert explicitly).

### T3.3 budget alternative — fused b25 vs plain b50, paired, n=308

**110/308 = 35.7%** — FAIL decisively. Halving the budget costs far more strength than the
damped memory returns; the "equal win-rate at ≤ 50% budget" alternative does not hold.

### G2 — fusion read overhead

**293 ns/expansion** (best of 7 rounds × 12,800 reads) vs the **< 100 ns** bar — **FAIL**
as specified. Context: ~1% of one int8 forward pass (~25 µs), so performance-irrelevant in
practice, but the gate is absolute. The cost is 16 runtime-modulus u64 divisions in the
multi-head hash + 16 slot copies; no optimization was attempted for a mechanism with no
measured gain.

### Gates that PASSED

- **G1**: empty table ⇒ bit-identical moves vs the feature-off player (40 fixed positions +
  2 full games, move sequences equal).
- **G4**: fusion read is zero-allocation (256 calls, counting allocator, delta 0; tests
  serialized by a mutex because the counter is process-wide).
- **G6**: deterministic miner (entry order irrelevant → same root) + file round-trip +
  tamper refusal (byte flip → `CommitmentMismatch`).
- **Q-init direction**: a mined `v̄ = +1` row for the position after the plain player's best
  opening move strictly suppresses that move's root visit share (the one-shot damped
  pseudo-visit does what it claims).
- **T2.1 artifact identity**: default-features wasm32 release artifact is **size-identical**
  (381,353 B raw `.wasm` pre/post on the same box; sha differs — the added optional dep
  changes cargo's `-C metadata`, permuting symbol order without changing emitted code; the
  issue's sanctioned form is "byte-identical OR size-identical"). `cargo tree
  --target wasm32-unknown-unknown` at default features: **no katgpt-core**. wasm32
  `--all-features` compiles clean (engram is wasm32-safe; the fusion code cfg's out).
- **G3**: clippy `-D warnings` clean at default / `--features engram_puct` /
  `--all-features` / `--no-default-features`; tests green at the engram posture
  (24 lib + 5 gates); the gate target carries `required-features` + `#![cfg]` so default
  invocations skip it loudly.

## Synthesis (why it failed, and what would have to change)

1. **The evidence drought is the measured cause.** The count-based sigmoid gate
   (n_min=8, τ_n=4) is the issue's own anti-rumor rule, and it worked: after 240 games,
   100% of mined positions have n < 4, so 99.98% of rows sit at gate ≤ 0.18. The mechanism
   could not legally fire. Mining longer does not fix this quickly — distinct positions
   grow ~linearly (≈70 plies/game) while repeat visits stay confined to openings.
2. **The prior-art mechanism is absent by construction** (proposal caveat, inventor's
   regret #2): M-MCTS's gain came from kernel regression over NEIGHBOURING states; a
   hard-hash table has no neighbourhood, so generalization beyond exact transpositions —
   exactly the thing this domain lacks — cannot happen.
3. A re-open would need at least one of: a transposition-dense domain (smaller boards),
   neighbourhood generalization (kernel regression over nearby keys), or a dramatically
   larger mining corpus with a re-mining cadence (`EngramHotSwap` substrate exists). None
   is this POC's scope.

**Promotion: NOT claimed (owner call on a full PASS; this is a FAIL).** `engram_puct`
stays opt-in, default-off, native-gated; the wasm browser build is untouched (T2.1).
