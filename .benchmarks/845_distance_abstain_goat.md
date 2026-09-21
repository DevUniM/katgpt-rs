# Bench 845 — Corpus-Distance Abstain T1.6 Gate (Proposal 014 T1.6 / Issue 863)

**Status:** GO (opt-in) — G1–G5 all PASS; T1.6 validated, promotion-to-default still requires the live consumer.
**Date:** 2026-09-21 · **Crate:** `katgpt-core` · **Feature:** `distance_abstain` · **Box:** M3 Max, LOADED (sibling cargo builds active throughout — the G5 spread below is that, disclosed per the AGENTS.md box-state rule)

## The T1.6 question

Proposal 014 T1.6 (marked UNVALIDATED) required the Research 576 §2.1 extraction — confidence via similarity-to-training-data (SalesRLAgent, arXiv:2503.23303; single-author, synthetic-corpus, no-code caveats on record in the research note) — to beat the score-threshold ABSTAIN baseline (`CalibratedActionBridge::should_abstain`) on **selective accuracy at matched abstain rates** before joining the engine's arm.

## What shipped

- `crates/katgpt-core/src/distance_abstain.rs` — `CorpusDistanceGate<const D>`: K registered exemplars (unit-normalized at construction), `max_similarity` = max cosine (zero-alloc query: one stack scratch row, one fold), `abstain_confidence` = `sigmoid(scale·(max_sim − mid))` (sigmoid, never softmax), `should_abstain` (`<`, mirroring the score bridge), `fused_should_abstain` (the OR).
- 7 lib tests: monotone in corpus distance (K=1 so max-sim IS the cosine — no row-crossover jitter), scale-invariance (bit-identical), empty-corpus-abstains-always, zero-vector NaN-free, threshold semantics one-ulp, fused-is-exact-OR, non-positive-scale refusal.
- `crates/katgpt-core/benches/bench_845_distance_abstain_goat.rs` — the T1.6 gate.

## Experimental design (the honest form)

**Two error worlds on ONE geometry** (K=128 exemplars = 4 clusters × 32, D=64, n=4096/rep, OOD share 30%, 8 replicates):

- **W1 (OOD-blind errors — the arena's world):** reported confidence p ~ U(0.5, 0.99) for EVERY query; in-corpus accuracy follows `sigmoid(1.2·logit p − 0.2)`; OOD accuracy collapses to ~coin-flip regardless of p. Distance carries error information the score lacks.
- **W2 (score-only errors — negative control):** identical everything, but accuracy follows the p-calibration everywhere. Distance carries nothing. A distance arm that won here would prove the fixture rigged.

**Arms:** `score` (abstain low p — the T1.6 baseline) · `dist` (abstain low corpus-confidence) · `fused` (the deployable OR, swept as min of the two **batch quantiles**) · `oracle` (ranks by true p — labeled ceiling, printed never gated).

**⛔ Rank fusion is load-bearing (the run's first finding):** `min(p, d_conf)` on raw scales degenerates to distance-only — d_conf < p at EVERY query (the sigmoid's range sits under U(0.5, 0.99)), so the first fused sweep was byte-identical to the dist arm and G2 failed for instrumentation reasons, not mechanism reasons. Fusing the batch quantiles puts both signals on one scale (production reads the same composition from running quantiles / `SigmoidGateCalibrator`; the batch CDF uses no outcome information, so it is not an oracle). Recorded in the feature comment and here so the next consumer does not re-derive it.

**Statistics:** gates read replicate MEANS + sign counts. Measured en route: a single-world Δ at these operating points is ~1σ (one-off +0.63 pp at ρ=30% proved nothing; the 8-replicate mean is the verdict).

## Results (8-replicate means, byte-identical across two full reruns)

| W1 arm | AURC | ρ=5% | ρ=10% | ρ=20% | ρ=30% |
|---|---|---|---|---|---|
| score | 0.2289 | 0.6827 | 0.6935 | 0.7140 | 0.7347 |
| dist | 0.2704 | 0.6808 | 0.6918 | 0.7124 | 0.7376 |
| **fused** | **0.1894** | 0.6819 | 0.6920 | **0.7174** | **0.7443** |
| oracle* | 0.1751 | 0.6838 | 0.6933 | 0.7169 | 0.7455 |

| W2 arm | AURC | ρ=5% | ρ=10% | ρ=20% | ρ=30% |
|---|---|---|---|---|---|
| score | 0.1222 | 0.7566 | 0.7710 | 0.7993 | 0.8279 |
| dist | 0.2640 | 0.7413 | 0.7410 | 0.7407 | 0.7406 |
| fused | 0.1662 | 0.7494 | 0.7564 | 0.7712 | 0.7875 |

**G2 — W1 fused win (PASS):** AURC −17% (0.1894 vs 0.2289); mean Δ(fused−score) −0.08 pp @ 5%, −0.15 pp @ 10% (non-inferiority ±0.2 pp), **+0.34 pp @ 20%** (≥+0.2), **+0.97 pp @ 30%** (≥+0.3), Δ(30%) > 0 in **8/8 replicates**. At ρ=30% fused captures **~89%** of the labeled oracle's gain over the score gate ((0.7443−0.7347)/(0.7455−0.7347)).

**G3 — W2 control (PASS):** dist AURC 0.2640 > score 0.1222 and **fused-W2 AURC 0.1662 > score 0.1222** — the fused advantage VANISHES when distance carries no error information; dist Δ vs score −1.5 to −8.7 pp at every ρ. The fixture discriminates: the W1 win is attributable to the OOD mechanism, not fixture bias.

**G1 (PASS):** 7 lib tests + confidence in (0,1)/NaN-free over 2×4096×8 queries.

**G4 (PASS):** 0 allocations over 4096 `abstain_confidence` + `fused_should_abstain` calls (Issue-741 predicate; counting_allocator liveness asserted first).

**G5 (PASS, ceiling):** best-of-9 per-query `max_similarity` (K=128, D=64 = 8192 MACs): **2.2 µs → 14.9 µs across four runs on a LOADED M3** (sibling cargo builds active; first reading 2191 ns, then 14851/5307/12308 ns). The 20 µs budget is a regression CEILING on a shared box, not the measurement — a quiet-box figure is still unrecorded (same standing as the docs-gate CPU paragraph). The spread itself is the AGENTS.md box-state rule reproduced: identical binary, 6.8× swing.

## Verdict

**GO for the opt-in lane.** The T1.6 claim holds in the world the arena targets (OOD-blind confident errors): rank-fused distance+score dominates the score-only baseline on AURC, is non-inferior at shallow abstention, wins the deep-abstention regime in 8/8 replicates, and captures most of the labeled oracle's headroom — at zero query allocations and a ~µs-scale gate. The W2 control proves the signal, not the fixture. **Not promoted to default** — margin_gate precedent: toy-evidence only, no live consumer; promotion is the Proposal 014 Phase-1 engine's owner-gated call.

Caveats on record: the fixture's OOD collapse is total by construction (real hallucination regimes are graded); the quantile fusion is batch-transductive in the bench (running-quantile production form unmeasured); MID=0.45 is a hand-set operating point on this geometry (probe-recorded, production calibrates).

## Run

```bash
CARGO_TARGET_DIR=/tmp/bench845 cargo bench -p katgpt-core \
  --features distance_abstain --no-default-features \
  --bench bench_845_distance_abstain_goat -- --nocapture
```

Resolution of `.issues/863_distance_abstain_t16_validation.md` (removed per the noise-reduction rule; full life in `git log --follow -- .issues/863*`).
