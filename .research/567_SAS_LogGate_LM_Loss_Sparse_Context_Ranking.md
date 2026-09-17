# Research 567: SAS — LM-Loss Log-Gate Training of Sparse Context Ranking

> **Source:** "SAS: Simple Attention Sparsification via End-to-End Optimization of Context Ranking" — Zhiwei Li, Lei Zhu, Hao Gu, Xiang Hu, Yan Wang, Haitao Mi, Sirui Han, Leo Liang, Zhijiang Guo (Tencent Hunyuan + HKUST-GZ/HKUST). [arXiv:2609.13141](https://arxiv.org/abs/2609.13141), 2026-09-11. Code: `github.com/Tencent-Hunyuan/Simple-Attention-Sparsification`
> **Date:** 2026-09-17
> **Status:** Gain — per-track outputs filed this session: (a) league/corridor: katgpt-rs Issue 826 (FlashMemory needle-axis quality gate — pooled-centroid weakness evidence); (b) training: riir-train Issue 560 (Plan 337 recipe deltas — LM-loss log-gate objective, ~0 GPU-h to amend)
> **Classification:** Public note (katgpt-rs)
> **Related Research:** 436 (FlashMemory — the SHIPPED sparse-decode corridor this paper's selector is the trained sibling of), 539 (SparDA — the family template; its distillation-trained Forecast is the SAS-vs-Seer-R contrast's cousin), 523 (H2O/policy-in-place — the eviction-class co-training requirement SAS's selection-class does NOT need), 201 (RAT-Plus train-dense-infer-sparse), 502 (behavior before perplexity), 435 (TTPO per-track precedent)
> **Related Plans:** riir-train Plan 337 (FlashMemory dual-encoder indexer training — the recipe deltas' home, Status Draft)
> **Related Issues:** katgpt-rs 584 (FlashMemory mechanism validation + Phase 3 promotion gate) · katgpt-rs 826 · riir-train 560
> **Panel:** not spawned — the abstract's training framing decomposed cleanly on Path 0 (the three design-choice findings ARE the training-recipe content; no hidden modelless layer found; see §3)

---

## TL;DR

Prior trainable sparse attention (SeerAttention-R, DeepSeek-V3.2 sparse adaptation) trains a block selector by **distilling layer-wise dense attention** because hard Top-K blocks gradients. SAS instead injects the selector's continuous scores into the attention softmax in log form during training — `o = softmax(qK_Sᵀ + log g_S)·V_S`, `g = softmax(s)`, current block anchored at unit gate — so the **plain LM loss trains the selector end-to-end, no teacher**. The gate is training-time only (inference = rank + Top-K + plain sparse attention). Gains are largest at tight budgets and hard tasks: at budget 1024, GPQA-Diamond +10.6/+13.7/+15.5 points over SeerAttention-R on Qwen3-4B/8B/14B; at 2048, AIME24 +13.0; training-free Quest scores **0** on AIME24/25 at 2048. Decode 2.4× at 64K → 5.6× at 512K (b=1), ~13× at b=8; prefill stays dense.

**The finding our shipped corridor needs:** their §8 limitation — pooling-based block summaries (AttnGate pools per-block key statistics) **destroy needle-like localized information** (RULER at 128K/budget-4096: 21.87–29.95 vs full attention 63.81–82.23). Our shipped FlashMemory sparse selector (`flashmemory_sparse.rs`, Issue 584, Bench 671) builds block centroids as the **mean of compressed KV latent** — the same pooling class. Before any Phase 3 promotion, the corridor's quality axis needs a needle/long-context gate; that evidence is filed as katgpt-rs Issue 826.

## 1. Paper Core Findings

### 1.1 The mechanism (Eq 9)

Block size b=64; the block containing the query is **B₀ — always retained, unit gate**; the C historical blocks are scored by a per-layer selector `s = R_θ(q, {K_Bm})` (SeerAttention-R's AttnGate architecture — query + pooled per-block key summaries, fully causal, decode-feasible):

```
g = softmax(s) ∈ R₊^C,  g₀ = 1
o_SAS = softmax(q K_Sᵀ + log g_S) V_S        # log g broadcast per block
```

`log g` inside the softmax ≡ multiplying each block's unnormalized attention weight by g_m. LM loss → o → log g → g → s → θ by standard backprop. At inference the gates are **removed** — scores rank, Top-K, plain sparse attention (softmax is monotonic; same ordering).

### 1.2 The four design choices + ablations (Qwen3-4B, GPQA-Diamond, budget 2048; dense 56.1)

| Choice | Variant | Score |
|---|---|---|
| Gate position | **inner** `softmax(qKᵀ+log g)` | **54.4** |
| | outer `softmax(qKᵀ)(g⊙V)` | 41.6 |
| Normalization | **softmax(s), B₀ unit-gated** | **54.4** |
| | sigmoid(s) | **17.0** — worse than baseline |
| | raw logits `softmax(qKᵀ+s)` | 18.8 |
| Continuity | **continuous soft gates** | **54.4** |
| | hard Top-K + STE | 46.0, exploding gradients |
| Training scope | full scope | 54.4 |
| | sparse scope (cheaper) | 54.8 @ 1 epoch — same final quality |

The gradient analysis (their Eq 5) explains inner-vs-outer: inner gating's gradient carries `(v_i − o)` — a **relative reallocation** signal among retained blocks; outer gating only rescales value contributions with fixed probabilities. The normalization analysis (Eq 6): `log g_m = s_m − LSE(s)` with the current block at zero bias — the shared `−LSE` term **does not cancel** (it is not applied to B₀), acting as a global discount calibrating aggregate historical attention mass against the always-retained anchor; it also makes gates shift-invariant. Without competitive normalization, sigmoid gates saturate to 1 and raw logits collapse to 0 variance over training — both converge to ungated attention, destroying the ranking signal (their Fig 3). STE's unbounded gradients: the forward normalizer sums only over the selected set, so a dropped block's `p̃ ≤ exp(z_i − max_{j∈S} z_j)` is unbounded, and a randomly-initialized selector early in training routinely excludes high-value blocks.

### 1.3 The objective-level claim

Same AttnGate architecture as SeerAttention-R; only the training signal changes (LM-loss log-gate vs dense-attention distillation). The paper's §6.1 analysis: SAS covers **less** per-layer dense-attention mass yet its **cross-layer union has higher recall** against the full-attention oracle — LM-loss training buys cross-layer complementarity that layer-wise distillation structurally cannot. Also shorter reasoning traces with fewer truncations.

### 1.4 Results shape

Tight-budget/hard-task gains (above); at budget 4096 SAS matches or exceeds full attention on some rows (AIME24 4B: 71.72 vs 71.25). LongBench transfers from math-only training data. Agentic BFCL +3.5 at 2048. Decode speedups vs dense: parity at 8K, 2.4× @ 64K, 4.6× @ 256K, 5.6× @ 512K (b=1); ~13× @ b=8/64K — batch-insensitive at long context. Continued-pretraining variant (joint backbone+selector, retrieval projections init'd from attention projections, GQA-group-shared selection) "encouraging but preliminary" (CRUX dropped 19.25 vs 24.62).

### 1.5 Kernel + cost structure

Training kernel: FlashAttention-style tiled fwd/bwd fusing (1) log-gate addition before the online-softmax update, (2) −∞ masking of unselected blocks, (3) whole-tile skipping; selection encoded as a per-query **threshold on the log gate** — Top-K without a sort. Backward recomputes from saved LSE and accumulates block-level gate gradients by summing dS over tokens per selected block. Inference: SGLang backend + FlashInfer sparse decode; **selection re-scored every step**. Cost breakdown: Top-K ranking grows from 21% of decode step at 8K to **90% at 512K** — selection, not attention, becomes the bottleneck at extreme context.

## 2. Signal-diff vs the shipped stack (§3.6)

| Cousin | Selection signal | Trained? | The delta |
|---|---|---|---|
| **FlashMemory sparse** (`flashmemory_sparse.rs`, shipped, Bench 671: 1.8× decode @64K/4090) | `dot(q, block_centroid)·scale`, sigmoid threshold σ ≥ 0.5, dynamic K, refresh τ=64 | **No** — modelless | Consumes relevance-proximity only; no gradient path into the selector. SAS's central claim is exactly that relevance ranking ≠ prediction-impact ranking under budget (Quest=0 on AIME @2048 is the training-free collapse datum). Inference-time MECHANISM is equivalent in class (per-query block scoring → subset → sparse softmax); the delta is the trained ranking + the always-retained-anchor calibration. |
| **SeerAttention-R** (not shipped) | same AttnGate | distillation | SAS = objective fix. Cited as the paper's controlled baseline, not a stack cousin. |
| **H2O / policy-in-place** (Research 523, Plan 367) | usage-rate eviction | co-training REQUIRED | **Class contrast:** eviction destroys information (dense-trained collapse R≈35–128×, fixed only by co-training); block *selection* keeps full KV and adapts per query — selector-only post-training works. Our Plan 367 (co-training) targets the eviction class; SAS says the selection class doesn't need it. |
| **SparDA Forecast** (Research 539, riir-train Plan 337 family) | one-layer-ahead predicted top-k | KL vs original selector | Distillation-family training — SAS's data argues the LM-loss log-gate is the better objective for that same selector slot. |
| **prior_logit_lane** (Issue 819, Bench 813) | closed-form prior logit π_j per key | No (closed form) | Structural cousin: a per-key score enters attention additively in log/sigmoid space. SAS trains that score; we supply it as a prior. SAS's sigmoid-gate collapse (17.0) is a TRAINING-dynamics finding — it does not condemn an inference-time constant prior (lane-off bit-identity is tested), but it IS the warning for any future trained gate in sigmoid space. |

## 3. Path 0 decomposition

| Component | Modelless analog? | Note |
|---|---|---|
| Log-gate inside softmax (`softmax(qKᵀ + log g)`) | **Ships** — `prior_logit_lane` adds per-key log-space scores; FlashMemory's sigmoid-threshold gate is the same multiplicative-gate shape, untrained | Structural coverage exists; the paper's contribution is the TRAINING signal, not the gate shape |
| No-sort threshold Top-K | **Ships** — FlashMemory's σ ≥ 0.5 threshold is exactly the no-sort selection trick (their kernel's log-gate threshold is its trained twin) | Independent discovery, shipped first |
| Selection-cost amortization | **Ships** — FlashMemory refresh τ=64 vs SAS re-scoring every step; their 90%-at-512K selection-cost datum is external validation that the refresh amortization is load-bearing | No action |
| End-to-end selector ranking | No modelless analog — needs the LM-loss gradient path | → riir-train Issue 560 (Plan 337 deltas) |
| Trained ranking ≠ relevance ranking | Modelless stack cannot train it, but the FAIL-URE datum (Quest 0 @ AIME 2048) bounds where the modelless selector is safe | → katgpt-rs Issue 826 (quality gate axis) |

## 4. Game-context reframe (step 4, honest)

The MMORPG serving path decodes over long agentic context (NPC dialogue histories, world-event transcripts) on the league's sparse-decode lane (FlashMemory corridor, Bench 671 on the 4090). SAS's tight-budget data says training-free selection collapses exactly where games would deploy it (hard multi-step tasks, tight KV budgets); and its pooled-summary failure mode is OUR shipped centroid choice. One sentence: the corridor is perf-validated but quality-unmeasured at the axis the game runtime would lean on.

## 5. Consumer reframe — healer (priority #2, honest)

No consumer: the healer has no attention softmax over context blocks; SAS's mechanism is Transformer-attention-specific. The conceptual rhyme — **relevance ranking ≠ utility ranking under a budget** — is the attention-stack twin of the LOPD signal-diff (riir-ai engram relevance-gate vs query-conditional utility, katgpt-rs Issue 656). Recorded as vocabulary, no file.

## 6. Verdict

**Gain.** Not Super-GOAT: the gate shape and no-sort selection already ship; the paper's novel content is the training objective, which is riir-train's currency (priority #5 lane), plus one league-corridor quality-gate obligation (priority #3 lane). Per-track outputs filed this session:

- **(a) League/corridor (primary):** katgpt-rs Issue 826 — FlashMemory Phase 3 promotion gate needs a needle/long-context quality axis; SAS's RULER data is the external evidence for the pooled-centroid weakness class our `rebuild_from_cache` mean-centroid shares.
- **(b) Training:** riir-train Issue 560 — Plan 337 recipe deltas: (i) LM-loss-through-log-gate objective (replaces/augments BCE-distillation indexer objective; Seer-R-controlled data says distillation misaligns ranking under budget), (ii) softmax-normalized gates + always-retained anchor (sigmoid 17.0 / raw-logit 18.8 collapse warnings for the dual-encoder's score head), (iii) continuous scores over STE (gradient-explosion mechanism), (iv) sparse-scope training viable (54.8 vs 54.4 — cheaper indexer training). ~0 GPU-h to amend the Draft plan; execution already 4090-gated.

## 7. References

- arXiv:2609.13141 (SAS) — Tencent Hunyuan; ablation tables + gradient derivations (App D) + kernel pseudocode (App E)
- Research 436 / Issue 584 / Bench 671 — the shipped FlashMemory corridor
- Research 539 / riir-train Issue 524 / Plan 337 — SparDA family template + the indexer-training recipe home
- Research 523 / riir-train Plan 367 — eviction-class co-training requirement (the class contrast)
- Issue 819 / Bench 813 — prior-logit lane (structural gate-in-log-space cousin)
