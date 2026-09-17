# Research 566: EOT Attention Priors (GOAT) + the Sigmoid Analog

> **Source:** "You Need Better Attention Priors" — Elon Litman (Stanford), arXiv:2601.15380, ICML 2026. https://arxiv.org/abs/2601.15380
> **Date:** 2026-09-17
> **Status:** Active
> **Related Research:** 258 (Attention Sink NOP/Broadcast, Plan 287), 261 (FuncAttn sink verdict — closed negative), 392 (SSMax + GoldShare, Plan 411), 487 (Massive Activations / sink-aware KV quant), 549 (ASEntmax)
> **Related Plans:** 411 (ssmax_temperature DEFAULT-ON, gold_share_probe opt-in), 287 (sink_aware_attn)
> **Classification:** Public

---

## TL;DR

Attention is the closed-form solution of an entropic-optimal-transport problem with an **implicit uniform prior**; replacing the Shannon regularizer with KL(p‖π) yields `p* = softmax(s/τ + log π)` — the log-prior is the missing additive term, and learned positional encodings are heuristics approximating it. The paper (GOAT) parameterizes the log-prior as learnable Fourier lanes over relative position + a rank-1 key-only sink lane, absorbed into one unmodified SDPA call via a pre-scaling trick, and proves sinks are optimal transport defaults with an exponential margin law (sensitivity ≤ (L−1)/(e^δ+L−1); δ ~ ln L suffices).

**The contribution this note adds:** our default attention is **sigmoid** (per AGENTS.md — sigmoid, never softmax). The paper's EOT line is confined to the simplex (normalized transport). We derive the **hypercube analog**: independent per-key gates under the same KL regularizer solve to `g*_j = σ(s_j/τ + logit π_j)` — the exact sigmoid counterpart, with `logit_bias` (Plan 364) as the constant-prior special case. Published prior art: **none found** (verified 2026-09-17; the OT-attention lineage — Litman 2508.08369, Sinkhorn attention — is entirely softmax-side; sigmoid attention work — SIGMA 2411.11674, Apple 2409.04431 — is empirical only). The margin law transfers to sigmoid gates with the **same δ ~ ln L scaling and is strictly more load-bearing**: sigmoid has no normalization to absorb noise, so the prior margin is the *only* protection in low-signal regimes.

**Distilled for katgpt-rs (modelless, inference-time):**
- The closed forms (softmax and sigmoid), the collapse-to-prior bound, the margin law, and the Appendix-F classification theorem all ship **without training** — they are properties of the objective, not of learned weights.
- What needs training: the spectral weights α_r/β_r and the sink MLP u(j) — an architecture change for a *future* from-scratch run only (see §6); not retrofittable onto served GGUF checkpoints.

---

## 1. Paper Core Findings

1. **EOT derivation (Prop 3.1):** `p* = argmin{−⟨p,s⟩ + τ·KL(p‖π)}` solves to `p* = softmax(s/τ + log π)`. Standard attention = uniform prior. Effective-cost view: the log-prior additively contours transport costs — inductive bias enters the *objective*, not the content representations.
2. **GOAT parameterization:** log-prior `K_ij = K^rel_ij + u(j)` where `K^rel_ij = Σ_r [α_r cos(ω_r(i−j)) + β_r sin(ω_r(i−j))]` (truncated Fourier, learnable α/β, fixed geometric ω) and `u(j)` is a key-only bias (linear decay + MLP over sinusoidal encodings). Both are linearized into query/key subspaces (2 dims per frequency + 1 sink lane, `d_p = 2R+2`) and absorbed into a **single unmodified SDPA call** by pre-scaling: content × √(d_h/d_c), prior lanes × √(d_h), so the kernel's 1/√d_h leaves content at 1/√d_c and the prior unscaled. FlashAttention-compatible, no L×L bias matrix. Peak-memory drop measured (−36% on their DNA task vs RoPE).
3. **Negative spectral weights (App C):** operating on the log-prior escapes Bochner positivity — α_r/β_r may be negative, giving **repulsion** (active suppression at specific relative distances), mathematically inaccessible to positive-definite kernel approximations (Performer-class linear attention). **⇒ documented negative transfer to HLA** (linear attention family): the learned-prior trick does not reach `riir-engine/src/hla` or `katgpt-hla`.
4. **Sink theory (Thm 5.1):** with content-score dynamic range ω_i, the posterior is pointwise bounded `π_ij·e^(−ω) ≤ p_ij ≤ π_ij·e^(+ω)` — low-signal queries **collapse to the prior**. Sinks are not artifacts; they are the optimal KL-regularized default.
5. **Margin law (Thm 5.4, Def 5.2):** a sink with prior-logit margin δ bounds context-noise sensitivity `Ψ ≤ (L−1)/(e^δ + L−1)`; standard (uniform) attention's Ψ → 1 as L → ∞. Logarithmic margin growth δ ~ ln L suffices — and only needs the key-only lane, which is **exactly rank-1 / minimal** (Thm 4: key-only priors are the unique minimal-rank mechanism for query-independent defaults).
6. **Classification theorem (App F, Thm 2):** SDPA-compatible (finite dot-product factorization) + translation-equivariant + bounded ⇒ the relative log-prior is **exactly a finite trigonometric polynomial**. ALiBi's linear bias = the unique maximum-entropy recency prior under a mean-lag constraint (Thm 3 + Prop F.6). The Fourier parameterization is not a choice — it is the admissible class.
7. **Experiments (trained, 125M-scale):** −1.55 ppl vs ALiBi on C4 with robust 16× length extrapolation (RoPE degrades catastrophically); near-perfect passkey/NIAH far beyond training length; learned u(j) spontaneously recovers a sharp j=0 sink spike + recency rise; ViT learns a 2D shift-invariant prior with zero-shot resolution extrapolation.

---

## 2. Distillation — the sigmoid analog (novel, this note)

The paper's optimality is over the **simplex** (transport plans, mass = 1). Our default gates live on the **hypercube** — each key independently gated, `g_j ∈ [0,1]`, output `o = Σ_j g_j v_j` unnormalized. Reformulate the same objective over independent gates:

```
g* = argmin_{g ∈ [0,1]^L} { −⟨g, s⟩ + τ·KL(g ‖ π) },
KL(g‖π) = Σ_j [ g_j log(g_j/π_j) + (1−g_j) log((1−g_j)/(1−π_j)) ]   (Bernoulli, factorizes)
```

Per-coordinate stationarity `−s_j + τ·[logit(g_j) − logit(π_j)] = 0` gives:

> **g\*_j = σ( s_j/τ + logit π_j )** — the exact sigmoid counterpart of softmax(s/τ + log π).

- `logit π_j` is the **prior logit**; the paper's sink lane u(j) is a learned `logit π_j`; **`SigmoidFusionConfig.logit_bias` (Plan 364) is the constant-π special case already shipped** — the xHC "boot CLOSED at −4" init is the prior π = σ(−4) ≈ 0.018. The GRT recipe ("bias toward identity, specialize gradually") gets a first-principles footing: it is a maximum-entropy-style default prior, and every gate reverts to it as content signal flattens.
- **Collapse-to-prior (sigmoid Thm-5.1 analog):** as content range ω → 0, `g_j → σ(logit π_j) = π_j` pointwise — cleaner than softmax (no partition function, independent coordinates).
- **Margin law (sigmoid Thm-5.4 analog):** with prior-logit margin δ = ℓ_{j*} − min_{k∈C} ℓ_k > 0 (ℓ ≡ logit π) and content range ω, every context gate obeys `g_k ≤ σ(ω − δ) ≤ e^{ω−δ}`, so

  > ‖Δo‖ ≤ ε·Σ_{k∈C} g_k ≤ ε·(L−1)·e^{ω−δ},  bounded ⇒ δ ≳ ω + ln L.

  Same δ ~ ln L scaling as the paper. **Strictly more load-bearing:** with a uniform zero prior, sigmoid context mass grows ≈ L·σ(ω) — **linear, unbounded** — vs softmax's Ψ → 1 (saturated). Softmax redistributes noise; sigmoid accumulates it. The prior margin is the *only* structural protection a sigmoid gate stack has. This is the theoretical explanation for why the negative `logit_bias` default is not merely a training convenience but a stability requirement.
- **Signal-diff vs SSMax (Research 392 / Plan 411), run per §3.6:** SSMax's Δ is a **content** margin (gold-vs-distractor score gap) and its bound `α_gold ≈ 1/(1+(N−1)N^{−sΔ})` preserves *gold mass* under dilution via a **multiplicative** temperature. GOAT's δ is a **prior** margin and the bound bounds *context-noise bleed* via an **additive** structural lane. Different signals, different axes; both are exponential-in-margin laws and compose (SSMax on the content channel, prior lane on the structural channel).
- **Signal-diff vs 2607.01538 Prop 1 (App H, recorded in Research 392 §1.4):** that result is an **algebraic identity** — softmax with a learned scalar `b_L` added to the denominator (`α̃_t = exp(s_t)/(Σexp(s_{t'}) + exp(b_L))`) ≡ standard softmax weight × gate `σ(lse(s) − b_L)`. It shows a sigmoid gate *appears* when you decompose a softmax sink; it derives nothing about how gate weights should be chosen. The §2 derivation is a different theorem: the sigmoid gate is the **closed-form optimal solution** of the KL(g‖π)-regularized objective over the hypercube, with logit-additivity (`σ(s/τ + logit π)`), per-key priors, and the collapse/margin laws. Complementary: Prop 1 justifies sigmoid as a *form*; the KL derivation tells you the *optimal content of the gate bias* (the prior logit) and its stability scaling.
- **Game reframe (two-brain):** the think-brain confidence decay `σ(−λ·Δt)` is a **time-axis** prior-logit drift; the collapse law is the **signal-axis** version. Unified form: `ℓ_j(t) = logit(base_rate_j) − λ·Δt_j` — fog-of-war staleness decay *is* a prior-logit drift toward the uninformative prior; per-NPC fusion gates reverting to base rates under weak observation are the KL-prior gate at work, with the same exponential bounds.
- **Healer reframe (priority #2, honest read):** no direct consumer — riir-rag retrieval is KNN/BM25 over spans, not position-structured attention, and the margin law has no analogue there. Nearest surface would be base-rate anchoring in retrieval scoring; speculative, not filed.

---

## 3. Verdict

**Gain.** (Ships + actionable improvements.) Not Super-GOAT: Q3 fails — "our gates are KL-regularized transport solutions" is a robustness story, not a product selling point no competitor can claim; the core learned-prior mechanism has dense published prior art (gpt-oss learnable sink biases, StreamingLLM, learnable-ALiBi family). The two genuinely novel pieces (sigmoid-EOT derivation; margin-based sink-stability *forecasting* — verified no prior art) are diagnostic/parameterization upgrades, i.e. GOAT-tier at best, and they extend shipped substrate rather than open a new capability class.

Prior-art audit (2026-09-17, web): sink-margin stability law — original to this paper; sink-failure forecasting from measured margins — none found; EOT/KL derivation for sigmoid attention — none found (open). The paper itself sits downstream of Litman 2508.08369 with the sink lane anticipated in spirit by OpenAI's gpt-oss attention-sink biases (empirical, no EOT derivation, no margin law).

**MOAT gate (katgpt-rs):** in scope — attention-stack primitives (attention slot). The sigmoid analog belongs in `katgpt-core` (sigmoid fusion / parallax / sink diagnostics). Training-track residue (learned α/β, u(j) MLP) → future-arch note only; riir-train has no active from-scratch attention retrain (Bonsai is a distill of external checkpoints; not retrofittable).

**Three-track check (Path 0):** value = the math (closed forms, theorems), not a training loop → modelless-validable for everything in §2. Learned-weight instantiation is ordinary supervised parameter fitting, deferred with the architecture change (§6). Model-based advocate's extraction (train a small arch with prior lanes) recorded as the optional arm in Issue 819 T4 — 0.4B Kimi-K3 test-arch is the cheap vehicle, exactly the paper's 125M-class scale.

---

## 4. Fusion map

| Fusion | Consumes | Produces | Where |
|---|---|---|---|
| **A — Sink stability forecast** | `sink_classify.rs` (NOP/Broadcast classifier) + measured logit rows | `SinkDiagnostic.margin` + `forecast_stable_positions(δ) = e^δ` — predictive "this head's sink protects up to N ≈ e^δ positions" | `katgpt-core/src/data_probe/` (Issue 819 T1) |
| **S — Prior-logit lane** | `SigmoidFusionConfig.logit_bias` (constant π, shipped) | optional per-key `prior_logits: &[f32]` (the u(j) lane; `None` = bit-identical constant path), documented δ ~ ln L law | `katgpt-core/src/engram/kernel.rs` + parallax (Issue 819 T2/T3) |
| **B — Belief prior drift** | think-brain `σ(−λ·Δt)` staleness decay | unified `ℓ_j = logit(base_rate_j) − λ·Δt_j` reading; no code change required — a design-law note for game-side fusion gates | `riir-ai` (recorded here; no plan unless a consumer asks) |
| **C — Future-arch lanes** | MLA's existing content+rope two-lane structure (`katgpt-kv::shard_kv::rope`, `katgpt-attn::mla`) — structurally GOAT's content+prior split | replace/augment the rope lane with learnable spectral lanes + sink lane in a *from-scratch* run | riir-train, gated behind A/S results; 0.4B test-arch vehicle |
| **D — Negative result (record)** | `riir-engine/src/hla`, `katgpt-hla` | linear-attention family **cannot** take learned negative-weight priors (Bochner positivity); do not attempt the transfer | this note only |

---

## 5. GOAT gate sketch (for Issue 819)

- **G1 correctness:** per-key prior lane at uniform π ≡ constant-bias path bit-identical (extend the existing `logit_bias_zero_is_bit_identical` pattern); forecast helper agrees with brute-force sensitivity sims on toy margins.
- **G2 quality:** margin-forecast detects the paper's Figure-2c signature (sink mass sheds as ω grows) on synthetic rows; per-key lane improves low-signal selectivity vs constant bias on a planted-distractor toy.
- **G3 latency:** per-key lane = one f32 add per key (SIMD stride-1) ≈ the existing `logit_bias` cost; forecast = O(1) after the margin scan the classifier already does.
- **G4 alloc-free:** scratch extends `StableRankScratch` convention; no heap after warmup.
- **G5 no-regression:** default paths (logit_bias constant, classifier without margin field read) bit-identical.

---

## 6. What we are NOT doing (audited discards)

- **Not retrofitting served checkpoints** (Bonsai-27B / qwen3.8-27B GGUF): the prior lanes are architecture; inference-time injection into models trained without them is an unvalidated behavior change. Sink handling for served models stays with the shipped classifier + SSMax.
- **Not redirecting to riir-train as a plan today:** no from-scratch attention retrain is on the roadmap; the 0.4B test-arch arm is filed as the optional Issue-819 T4 with recipe sketch (RoPE baseline vs +spectral lanes vs +sink lane; ppl + NIAH/passkey extrapolation axes; ~hours-class GPU on the 4090 at 0.4B) — graduates to a riir-train plan only if T1–T3 land and the owner pulls.
- **Not porting to HLA** (Fusion D negative transfer, paper's own App C).
