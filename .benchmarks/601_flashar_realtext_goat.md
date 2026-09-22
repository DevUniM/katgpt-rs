# Bench 601 — FlashAR confidence-commit GOAT gates ON REAL TEXT (Plan 601: the Plan 600 promotion precondition)

**Date:** 2026-09-17 · **Box:** Windows 4090 workstation (release profile,
`--test-threads=1`, isolated `CARGO_TARGET_DIR`) · **Total runtime:** ~22 s
· **Verdict:** ALL GATES GREEN → promotion executed (Plan 600 acceptance bar met).

## Corpus + model

| | |
|---|---|
| Fixture | Jane Austen, *Pride and Prejudice* tail, ~107k chars, novel body only, chapter-aligned (`CHAPTER LIII.` onward). Project Gutenberg eBook #1342 — public domain in the US. |
| Tokenizer | Char-level, 31-symbol compact alphabet (lowercase a–z, space, period, comma, apostrophe incl. U+2019; all else → space). |
| Model | `Config::micro_dllm_text()` — 2 layers, d=32, 4 heads, mlp 128, vocab 32 (mask 31), bidirectional; ~26k params. |
| Training | `train_mini_dllm` (the pattern lane's own trainer), 2048 disjoint 9-token blocks (seed + 8 slots), 40 epochs, lr 0.01, mask 0.3, seed 42. Deterministic. |
| Eval | 512 held-out 9-token blocks at fixture offset 80,000 (disjoint from train). |

T1 corpus honesty: held-out masked NLL **2.4357** nats/token vs empirical
unigram entropy **2.8860** (margin 0.45 > 0.15 bar); argmax acc **0.300**
vs chance 0.032.

## T2 — arm table (exact-match, paired seeds, production entries only)

```
arm                               kappa  NFE     acc      se    steps anchors   wall_us
all-mask D2F baseline              0.70    4   0.000   0.000     4.00    0.00      58.1
all-mask D2F baseline              0.70    8   0.000   0.000     8.00    0.00     115.4
stride1 tau0.70                    0.70    4   0.013   0.002     3.73    8.00     137.8
stride1 tau0.70                    0.70    8   0.013   0.002     7.35    8.00     234.5
stride2 tau0.70 (incumbent)        0.70    4   0.010   0.002     4.00    4.00     142.2
stride2 tau0.70 (incumbent)        0.70    8   0.010   0.002     7.98    4.00     251.7
stride4 tau0.70                    0.70    4   0.005   0.001     4.00    2.00     148.6
stride4 tau0.70                    0.70    8   0.005   0.001     7.98    2.00     254.8
stride2 tau=kappa (matched ref)    0.50    4   0.012   0.002     3.99    4.00     147.4
stride2 tau=kappa (matched ref)    0.50    8   0.013   0.002     7.94    4.00     249.9
stride2 tau=kappa (matched ref)    0.90    4   0.009   0.002     4.00    4.00     141.9
stride2 tau=kappa (matched ref)    0.90    8   0.009   0.002     8.00    4.00     252.9
stride2 tau=kappa (matched ref)    0.99    4   0.007   0.001     4.00    4.00     145.2
stride2 tau=kappa (matched ref)    0.99    8   0.007   0.001     8.00    4.00     252.1
conf kappa (no floor)              0.50    4   0.017   0.002     3.91    4.76     142.7
conf kappa (no floor)              0.50    8   0.021   0.003     7.67    4.76     239.6
conf kappa (no floor)              0.90    4   0.003   0.001     4.00    2.55     145.5
conf kappa (no floor)              0.90    8   0.003   0.001     8.00    2.55     250.4
conf kappa (no floor)              0.99    4   0.000   0.000     4.00    1.10     144.7
conf kappa (no floor)              0.99    8   0.000   0.000     8.00    1.10     250.6
conf kappa + floor (DBTM)          0.50    4   0.046   0.004     2.61    4.76     122.2
conf kappa + floor (DBTM)          0.50    8   0.047   0.004     2.87    4.76     181.1
conf kappa + floor (DBTM)          0.90    4   0.077   0.005     3.57    2.55     138.5
conf kappa + floor (DBTM)          0.90    8   0.078   0.004     5.18    2.55     219.7
conf kappa + floor (DBTM)          0.99    4   0.105   0.005     4.00    1.10     140.7
conf kappa + floor (DBTM)          0.99    8   0.117   0.005     6.79    1.10     230.0
```

### Gates (NFE=8)

| Gate | κ=0.5 | κ=0.9 | κ=0.99 | Bar | Verdict |
|---|---|---|---|---|---|
| G1 paired Δ(acc) | **+0.0344 ± 0.0038** | **+0.0686 ± 0.0047** | **+0.1106 ± 0.0052** | ≥ −2·SE, SE ≤ 0.05 | PASS |
| G2 fill steps | 2.87 vs 7.94 (2.8×) | 5.18 vs 8.00 (1.5×) | 6.79 vs 8.00 (1.2×) | beat (κ>0.5) / tie (κ=0.5) | PASS |
| G2 wall ratio | **0.72×** | **0.87×** | **0.91×** | ≤ 1.25× | PASS |
| Liveness (stride2@0.9 vs all-mask) | 0.009 vs 0.000, gap > 2·SE_gap | | | | PASS |
| DBTM termination | all cells | | | within budget | PASS |

## T3 — T9′ realized-KL cross-check vs the EMPIRICAL bigram law

The pattern lane's analytic `corpus_law()` has no real-text counterpart, so
P_Z = add-0.5-smoothed empirical bigram joint P(c1, c2) from a held-out
corpus stretch (16,384 tokens, offset 80,000) — the same smoothing the
pattern T9 uses, so the two estimates are method-identical. Seeds c1 drawn
from the smoothed unigram CDF; n_mc = 4096 per arm per seed; mean over 2
independent MC base seeds. Model-side UGC certificate (random-order
reference, printed not gated): Ĉ = 5.9261, bound 4Ĉ/8 = **2.963**.

| κ | stride-matched KL | conf+floor KL | ratio | leak (stride / conf) |
|---|---|---|---|---|
| 0.50 | 3.3917 | 2.9587 | **0.872** | 0.963 / 0.000 |
| 0.90 | 3.6742 | 2.4592 | **0.669** | 0.993 / 0.000 |
| 0.99 | 3.7969 | 1.8329 | **0.483** | 1.000 / 0.000 |

Gate (κ=0.9, the bench-600 T9 cell): ratio 0.669 ≤ 1.10 — **PASS**. The
greedy confidence reveal distorts the real-text block law LESS than the
incumbent at every cell; Caveat #1 empirically benign on text.

## The finding the pattern corpus could not show

**The strided incumbent collapses on real text.** At every matched τ ≥ 0.5
its fill round cannot commit text-confidence slots, so the decode leaves
slots MASKED at budget exhaustion: leak ≈ 1.0 (the first block slot is
masked on ~100% of blocks), exact-match accuracy 0.007–0.013 (masked slots
score zero), KL vs the corpus law 3.39–3.80. The DBTM floor exists precisely
to prevent this — it guarantees the block empties within budget — and on
real text it is the difference between a committed block and a masked one.
On the high-confidence pattern toy both rules terminated and the comparison
degenerated to steps-only; the toy was structurally blind to the incumbent's
failure mode.

Honest reading of G1: the +Δ win axis is termination-dominated (committed
slots score, masked slots do not). It is the same axis G2 measures and the
same axis the floor was designed around — it is NOT a claim that confidence
selection finds better tokens than the walk's own proposals.

## G3 + G4 (corpus-independent seam properties, cited not re-measured)

- G3 byte-identity with the config off: `test_issue811_harness_matches_production`
  + `test_issue600_entry_matches_poc_conf_arm` (`src/speculative/flashar_anchor.rs`)
  — green in the same lane this session.
- G4 alloc-free fill loop: `bench_600_flashar_fill_alloc_gate` — green in the
  same lane this session (5 allocs @ 4 rounds == 5 @ 8 rounds).

## Promotion

Plan 600's acceptance ("T8 all-green + T9 on real text") is met on both
corpora. Executed: `ConfidenceAnchorConfig::default()` = κ 0.9 + floor (the
balanced GOAT cell: best steps/wall at material quality gain) promoted as
the anchor-then-fill seam's decode default; `AnchorConfig::default()`
(stride 2) unchanged; `anchor_then_fill` signature unchanged (zero caller
churn). Demote-on-loss stands: a re-gate on a harder corpus that shows a G1
loss demotes the default back to stride.
