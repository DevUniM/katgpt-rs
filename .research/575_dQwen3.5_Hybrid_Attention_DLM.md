# Research 575: dQwen3.5 — Hybrid-Attention Diffusion Language Models

> **Source:** dQwen3.5: Hybrid-Attention Diffusion Language Models — Xue, Rout, Akella, Klivans, Sanghavi, Shakkottai (UT Austin), [arXiv:2609.20751](https://arxiv.org/abs/2609.20751), Sep 2026
> **Date:** 2026-09-20
> **Status:** Active
> **Classification:** Public
> **Related Research:** 034 (D2F Discrete Diffusion Forcing), 055 (Nemotron TriMode), 070 (Gated DeltaNet 2), 028 (HLA)
> **Related Plans:** katgpt-rs 066 (D2F), 105 (GDN2 recurrent attention), **602 (decode-order AR-ness instrument — this session)**; **riir-train 414 (Bonsai GDN block-diffusion DLM — this session)**

---

## TL;DR

Adapting a hybrid GDN+attention AR model (Qwen3.5) into a masked diffusion LM requires bidirectionalizing ONLY the attention layers — the causal GDN majority (75% of the stack) stays causal — and adapts ~2.2× faster (median 2.21× tokens to matched training loss) than a trunk-matched full-attention control, while exhibiting full DLM decode behavior (local AR-ness 0.64, inside the full-attention DLM range; global AR-ness 0.97).

**Why it matters here:** our league models ARE scalar-decay GDN hybrids (Ternary-Bonsai-27B carries 48 GDN layers; qwen3.8-27B is the exact paper twin architecture), our D2F/SetDLM stack is already shipped (`dllm_solver.rs`, `ugc_schedule.rs`, `set_diffusion_schedule.rs`, D2F block decode, GPU SetDLM trainer Plans 379–384), and the workspace grep confirms **nobody has joined the two halves**. The paper supplies the join: the adaptation recipe (training track) and two measurement instruments — decode-order AR-ness metrics and capability-retention-gated adaptation — that run modellessly over signals we already emit.

**Distilled for katgpt-rs (modelless, inference-time):**
1. **ALR/AGR decode-order metrics** — `ALR = |{k : π(k) < π(k+1)}| / |{k : π(k) ≠ π(k+1)}|` (adjacent), `AGR = |{i<j : π(i) < π(j)}| / |{i<j : π(i) ≠ π(j)}|` (all pairs), over the per-position unmask step π that d2f/UGC/SetDLM decode paths already produce. Pure post-hoc statistics.
2. **The ALR/AGR gap as a block-safety predictor** — low local + high global ⇒ any-order *within* a block is cheap, block *boundaries* carry the order cost. Choose d2f block size and SetDLM `w` from the measured gap (gives Plans 379–384's w=0.5 NLL win a measured mechanism).
3. **Anchors = UGC certified spine** — the paper's sparse anchor set A (positions carrying future context) maps onto `ugc_schedule.rs`'s certified high-confidence masks: the certified set is the spine, the rest decodes as the conditional chain. A view, not new math.
4. **Offline anchor scorer from logs** — first-unmask-in-block frequency + masked-position entropy rank which positions carry future context, on ANY model, weights untouched.
5. **Capability-retention floor as GOAT G0** — the paper's LR lesson: training loss is a liar (1e-4 destroyed small models' MMLU while loss curves looked smooth). Any promoted adaptation/config change must hold `score_after / score_before ≥ 0.95` on a pinned eval suite. Cheapest and most transferable item in the paper.

---

## 1. Paper Core Findings

- **Hybrid adapts faster:** dQwen3.5-2B (GDN trunk 1.37B) reaches each stable-phase loss level with a median **2.21× fewer** content tokens than dQwen3-1.7B (full-attention trunk 1.41B) under the same recipe. Only 6/24 sequence layers bidirectionalized vs 28/28 in the control.
- **Causal RNNs don't block any-order decoding:** local AR-ness 0.636 for dQwen3.5-9B vs 0.631–0.652 for full-attention DLMs (LLaDA-8B, Dream-7B, Dream-Coder-7B); global AR-ness 0.884–0.967 for all. DLMs — including from-scratch LLaDA — decode globally left-to-right, locally out-of-order. Block decoding pushes AGR → 0.99 by construction while ARL stays ~0.7.
- **Parallel decoding holds:** dQwen3.5-9B leads all 6.5–7B-trunk comparators on HumanEval at every NFE speedup beyond 1× (fixed budgets) and stays on the quality–speed frontier under confidence-threshold τ unmasking to ~8×.
- **Over-adaptation hurts:** 50B tokens suffice; 100B improves 5/7 benchmarks at 0.8B but only **1/7 at 9B** (regressions concentrate in knowledge/math). LR was selected by **capability retention**, not loss — 1e-4 catastrophically destroyed the small models' MMLU.
- **§5 anchor theory:** factorize `q(x) = q(x_A) · Π_{i∉A} q(x_i | x_<i, x_A)` with A a sparse set of anchor positions carrying future context. If |A| ≪ L, causal recurrence models the prefix chain and bidirectional attention only needs to reach a few anchors — why a 25% bidirectional minority suffices.
- **Recipe:** prepend BOS + shift readout by one (hidden k predicts token k+1 — preserves AR readout alignment); repurpose unused token ids for mask/pad/BOS (**no embedding resize**); time-reweighted objective w_t = 1/λ_t (equal weight per masked target, linear schedule α_t = 1−t); AdamW (0.9, 0.95), warmup 1k / stable 44k / cosine 5k; mixture 50% code / 35% general / 15% math; weight-average of last 5 checkpoints.

---

## 2. Distillation

### Published prior art (§4 searches, agent-verified)

| Claim | Prior art | Delta that survives |
|---|---|---|
| Hybrid→DLM adaptation exists | **FLARE** (arXiv:2606.01774) adapts hybrid Qwen3.5 backbones | FLARE has **no hybrid-vs-full-attention control** — the 2.21× efficiency comparison survives |
| Recurrent layers + diffusion | **DiffuMamba** (2511.15927): bidirectional Mamba; **BDLM** (2607.02805): "partial bidirectionality", from-scratch | Opposite design point — they bidirectionalize the recurrence; this paper keeps GDN causal and bidirectionalizes attention only |
| "Anchor" vocabulary | **ADLM** (Rout et al., 2505.18456): anchors = masking-schedule/data-level notion | Same word, different concept — here anchors are an architecture-level information-structure claim |
| Decode-order metrics | **DiffuCoder** (2506.20639, ICLR 2026) ships decode-order metrics incl. the literal term "AR-ness" | Metric CONCEPT is preempted; the ALR/AGR local/global split, the gap-predictor use, and in-workspace instrumentation remain deltas |
| Capability loss in adaptation | Ye et al. (2308.12219); Gong et al. (2410.17891) | Published; the over-adaptation quantification + retention-selected LR is a refinement |
| Future-dependence probing | "Do LMs plan ahead?" (breadcrumbs), multi-token future knowledge, Jacobi/lookahead decoding | A studied class — the offline anchor scorer is in-workspace-novel, not literature-novel |

### Fusion (paper × 034 D2F × 055 TriMode × 070 GDN2 × UGC/SetDLM)

Ternary-Bonsai-27B is structurally the paper's hybrid minus the bidirectional attention. The join none of the cousins has:

- **Training half → riir-train Plan 414:** adapt the served GDN hybrid under the paper recipe on the shipped SetDLM trainer (riir-gpu Plans 379–384 lane). Stage 1 validates the core premise (causal GDN trunk trains under masked diffusion) on the 0.4B arch-test model.
- **Measurement half → katgpt-rs Plan 602:** ALR/AGR + anchor scoring over the existing dllm benchmark, then close the loop — block size and `w` chosen from the measured order statistics.
- **Game-runtime fusion (recorded, not planned):** two-brain fog-of-war budgets are anchor-shaped — sparse info-brain re-observation mirrors |A| ≪ L; anchor scores could weight the visible_radius re-observation schedule. No consumer surface asked for this yet; revisit when spatial cognition touches decode-order signals.
- **Healer check (ladder #2, asked and answered):** the healer's drafter is AR ternary; π-logging would make draft-acceptance order measurable, but the workspace grep found zero documented healer gaps naming decode order (`AR-ness|decode_order|anchor_token` = 0 hits anywhere) → non-actionable today.

### Path 0 / track decomposition (§3.5)

| Component | Training? | Modelless analog | Verdict |
|---|---|---|---|
| Bidirectionalized attention masks | config change | mask config only | modelless |
| Token shifting + unused-id reuse | serving-side | serving-side | modelless |
| Masked-diffusion objective w=1/λ_t | GD to train | schedule shape transfers (slot-allocation variant, Plan 602 T2.3) | both tracks |
| 2.21× adaptation efficiency | GD (adaptation run) | methodology transfers: T\*(θ) = min tokens/NFE to reach loss θ, matched-trunk ratio | both tracks |
| ALR/AGR, retention floor, anchor scorer | none | pure post-hoc statistics | modelless |
| DLM weights themselves | **GD genuinely required** | no freeze/thaw or deterministic-LoRA construction synthesizes the diffusion objective's weight updates | Track B (Path 0.5 default — training-efficiency, actively pursued) |

Panel record: No-GD advocate returned 10 feasible extractions (all folded into Plan 602 except where noted); model-based advocate returned GO with a 3-stage plan, ternary-specific risks, and honest 4090 GPU-hour ranges (0.4B full-FT ≈ 7–14 h; 27B LoRA ≈ 100–280 h; 27B full-FT infeasible).

---

## 3. Verdict

**GAIN (both tracks actionable; no Super-GOAT).**

Why not Super-GOAT: FLARE preempts the headline adaptation claim; DiffuCoder (ICLR 2026) preempts the decode-order metric concept; bidirectional-recurrent diffusion exists (DiffuMamba/BDLM, opposite design point); future-dependence probing is a studied class. The in-workspace novelty is the **bridge** — served GDN hybrid × shipped DLM stack × measurement instruments — filed as two plans:

- **Track A (modelless — primary by serving-envelope fit; runs inside the decode/bench hot path):** [katgpt-rs Plan 602](../.plans/602_decode_order_arness_instrument.md) — feature `decode_order_metrics`; GOAT gate: G1 known-answer orderings (identity→1.0, reversed→0.0, random→≈0.5), G2 O(L)/O(L·W) zero-alloc, G3 predictor-chosen (w, block size) ≥ fixed at matched NFE, G0 retention floor ≥ 0.95 for any promotion.
- **Track B (training):** [riir-train Plan 414](../../riir-train/.plans/414_bonsai_gdn_block_diffusion_dlm.md) — Stage 1 arch validation on the 0.4B GDN model (full FT, 1–5B tokens, ~7–14 GPU·h via 4090 issue), Stage 2 Bonsai-27B LoRA with the three named ternary risks (mask-row quant calibration, GDN state-norm drift under masked context, unseen mask-token value). GOAT: G1 retention ≥ 0.95 of AR baseline, G2 ≥ 2× decode tok/s at NFE 4, G3 AR path byte-identical with flag off, G4 seed-deterministic eval.

Deferred with auditable reasons:
- **Refinement stop-rule** (NLL-vs-step argmin exit in `dllm_solver.rs`): no consumer loop runs refinement steps today — reopen when a refinement loop ships.
- **Confidence-threshold τ unmasking + 1/λ_t slot-allocation schedule variants:** folded into Plan 602 T2.3 as optional, promote-only-on-G3 — not separately tracked.
- **DLM league lane** (serve a DLM as a new decode-throughput axis): gated on Plan 414 Stage 1 results; the league doc's opponents table is untouched this session.

### MOAT gate per domain

| Domain | Fit | Action |
|---|---|---|
| katgpt-rs | sampling/decoding axis + dllm primitives in-scope | note + Plan 602 here |
| riir-train | active training moat; Path 0.5 default applies | Plan 414 |
| riir-ai / league | Plan 414 G2 is league-adjacent (decode tok/s axis) | no doc change this session |
| riir-clippy (#2) | asked; zero documented gaps map | non-actionable, recorded above |
| game runtime (#1) | fusion idea recorded (fog-of-war anchor weighting) | no plan — no consumer asked |
