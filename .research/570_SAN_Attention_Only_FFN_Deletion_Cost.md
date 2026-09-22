# Research 570: SAN — What a Transformer Loses Without Feed-Forward Layers (0.006 nats at matched params)

> **Source:** "Simple Attention Networks: What a Transformer Loses Without Feed-Forward Layers" — Henry Ndubuaku, Cactus Compute blog, 2026-09-17. https://cactuscompute.com/blog/simple-attention-networks — companion to the paper **"A Controlled Study of Attention-Only Transformers"** (Cactus, Jul 2026, alphaxiv). Architecture behind Needle 3.
> **Date:** 2026-09-18
> **Status:** Done — distillation + per-track verdicts (league cell = GOAT-plan gated on an SAN artifact; query-token diagnostic = Gain→issue; training recipe → riir-train; SAN+engram fusion = novelty TBD)
> **Related Research:** 568 (Cact format — `needle3.cact` 29 MB/20L **IS an SAN serving artifact**; same paper family), 238 (LoRA Muon — paper trains all arms with Muon, 2× LR spread across arms), 116 (Ouro looped attention-only — recursion, not FFN removal), 006 (Raven routing slot memories — the engram analog; Raven found hybrid > pure for recall, the counterpoint), 444 (IMIR — operates on attention-only weights, different question)
> **Related Plans:** Plan 431 (`simd_lut_dequant`), Plan 486 (fused Q4_K LUT GEMV), Plan 100 (Q4_K WGSL) — the attention/GEMV kernel slots a SAN decode cell would consume
> **Cross-ref (riir-train / riir-neuron-db):** riir-train — SAN pretraining recipe (Muon, QK-norm mandatory, sandwich norm, per-arm LR sweep, SYNTH 105B); riir-neuron-db — the engram-buyback fusion (AnyRAG/ShardIndex = Needle 2's "engram bolted on")
> **Classification:** Public

---

## TL;DR

Cactus deleted the FFN (≈2/3 of a transformer's non-embedding params) from every block and measured the cost under three controls. **Iso-depth** (20L vs 20L, 87M vs 24M): FFN leads by **0.470 nats**. **Iso-FLOP** (9L FFN, 43M vs 24M SAN): **0.263 nats**. **Iso-param** (4L FFN, 24M vs 24M SAN with the freed budget reallocated into attention depth): **0.006 nats = 0.27% of loss** (0.0055/0.0054 on two clean seed pairs, 1-part-in-10⁴ reproducible; pipeline noise floor 0.0015 nats). The residual gap is not diffuse: it sits almost entirely on **query tokens** — positions with nothing in context to route from (weights-only knowledge) — where at 31B tokens the per-token gap is 5× the aggregate; by 105B the SAN is *ahead* on trace and answer regions. **The FFN's parameters matter; its functional form, on this distribution, largely does not** — a SAN layer, for a fixed attention pattern, is linear in its inputs and each head's update lies inside the convex hull of the value vectors it attends to: it selects and transports context, it cannot synthesise what context does not support. Needle 3 (8–29 MB, the same family as `needle3.cact` in Research 568) is this architecture with a 2–20-layer deployable ladder; Needle 2 bolted an engram memory on for exactly the lookup tokens the FFN used to serve.

**Distilled for katgpt-rs (modelless, inference-time):**
Three separable claims. (a) **The measurement protocol is the modelless primitive**: register predictions, control parameters/compute/depth independently, calibrate a noise floor (0.0015 nats via optimizer-equivalent parameterisation pairs), decompose loss by token region — a query/trace/answer-style decomposition localises *whether a workload is storage-bound or routing-bound* without any training. (b) **The architecture result re-prices our kernel slots**: at matched params an SAN pays ~2× FLOPs/token (0.40 vs 0.20 GFLOPs/tok @2048 ctx) but streams ~1/3 the weight bytes per token — in the bandwidth-bound on-device decode regime that is the right trade, and it deletes the FFN/GEMV slot from the hot path entirely. (c) **The regime is conditional, not universal**: every result is ≤87M params / 105B tokens; on natural web text (fineweb-edu) the iso-param gap is 0.040 nats, 7× the SYNTH number — storage-heavy distributions at larger scale are the paper's own untested next experiment. **This does not license FFN deletion on Bonsai-27B** (iso-depth 0.470 nats says in-place deletion is a catastrophe).

---

## 1. Paper Core Findings

### 1.1 The three controls (the whole design)

| Arm | Config | Total params | Non-emb | GFLOPs/tok | FFN lead (nats) |
|---|---|---|---|---|---|
| SAN | 20L, d=512, no FFN | 24.13M | 15.74M | ~0.40 | — |
| FFN iso-param | 4L, d=512, FFN 2048 | 24.12M | 15.73M | ~0.20 | **0.006** (0.27%) |
| FFN iso-FLOP | 9L, d=512, FFN 2048 | 43M | 35M | ~0.39 | **0.263** |
| FFN iso-depth | 20L, d=512, FFN 2048 | 87.06M | 78.67M | ~0.72 | **0.470** |

The three numbers order exactly by how much parameter budget the control lets attention reclaim. Method hygiene: every arm got its own learning-rate sweep (optimal Muon rate differs **2×** between arms — a shared rate silently biases the comparison); noise floor calibrated at **0.0015 nats** with a pair of optimizer-equivalent normalisation parameterisations; **8 predictions registered before measurement**; SYNTH (reasoning-dense, query/trace/answer regions) up to **105B tokens**.

### 1.2 Where the loss lives — the query-token deficit

SYNTH's three-region structure decomposes loss exactly (region-weighted sum reproduces the aggregate to 2%). SAN-loss minus FFN-loss (right of zero favours FFN):

| Region | Token share | @31B | @105B |
|---|---|---|---|
| query | 5.8% | +0.052 | **+0.038** |
| trace | 57.2% | +0.008 | **−0.0040** (SAN ahead) |
| answer | 35.9% | +0.011 | **−0.0070** (SAN ahead) |
| aggregate | — | +0.011 | −0.0025 |

At 31B the per-token query gap is **5×** the aggregate while those tokens carry 8% of the loss. Across the size ladder the query deficit is the *one invariant* — positive at every size and budget — while every other region changes sign. Benchmarks split the same way: Lambada (out-of-distribution recall on SYNTH models) favours FFN at every budget; Sciq (answer in the support passage) favours SAN, margin growing with training — **0.725→0.742 SAN vs FFN sliding 0.702→0.661**.

### 1.3 Distribution-dependence is load-bearing

Registered before launch: a matched-parameter pair trained on **fineweb-edu** (natural web text, mostly low-context prediction) would show 0.02–0.05 nats. Measured: **0.040**. The same pair *reverses* on Lambada — **0.203 vs 0.181 in the SAN's favour** — because distribution-matched text makes the passage sufficient and Lambada becomes a routing task. **"Whether a task is storage or routing is not a property of the task. It is a property of the match between the task and the training distribution."**

### 1.4 Two more axes

- **Training closes the gap**: iso-param gap 0.046 nats @5B → 0.019 @30B → 0.0055 @105B (each budget trained and tuned separately).
- **Size does not open it**: at fixed 31.5B tokens across five matched pairs, attention-only *wins* at the smallest size (−0.045 @2M non-emb), then the gap plateaus near 0.02 from 16M to 57M (0.012 @6M, 0.021 @16M, 0.019 @57M). Unique-document constraints (2M/8M/32M docs, ≤18 epochs) cost ≤0.010 nats, no architecture interaction.

### 1.5 The mechanism in the weights

In every model trained: **routing matrices (Q, K) crystallise within the first quarter of training and never move again**; the matrices that *write content* into the residual stream keep accumulating stable rank for the whole stable phase — the FFN down-projection in FFN models, and in SANs the **attention output projection W_o, which inherits the role as the only write path**. Muon holds routing matrices 2–3× flatter than AdamW. Representation rank stays high (min layer rank **173/512** at 20L) — the Dong et al. rank-collapse regime for pure attention is never approached once residuals + normalisation are present.

### 1.6 What keeps a deep attention-only stack trainable

Component ablations at 20L: **QK-normalisation is load-bearing** (removing it diverges outright at the tuned LR — the only divergence in the study and the one finding no registered prediction anticipated). **Scalar residual gates are performance-neutral** at every depth 20–48L in both architectures; their value was diagnostic — under learning-rate stress the FFN model's gate trajectories showed it **self-pruning toward attention-only form**. **Post-attention sandwich normalisation is the only variant beating baseline, by 0.009 nats.** Matched-parameter depth is U-shaped with a 20L optimum; 48-layer attention-only stacks train without incident. Every instability in the study happened in the FFN arm; none in the SAN arm.

### 1.7 The regime claim (their honesty)

At matched params a SAN pays roughly **2× the FLOPs/token** at 2048 context; at matched FLOPs the FFN model is ahead. The trade favours SAN where **parameters, not FLOPs, bind** — the on-device regime (memory limits set model size; a token costs bandwidth before arithmetic) — and on trace-rich distributions where answers are routable from context. **"We claim a regime, not superiority."** All results ≤87M params / 105B tokens; MMLU-class at chance at these scales; the storage account *predicts* a wider gap on storage-heavy mixtures at larger scale — the natural next experiment, untested.

---

## 2. Distillation

### 2.1 The modelless primitive: the storage-vs-routing diagnostic

The transferable, zero-training instrument is the **measurement protocol**:

1. **Region-decompose the loss** by token class (what must come from weights vs what is in context) — the paper's query/trace/answer split; the token-weighted region sum reproduced the aggregate to 2%, so localisation was real, not between-rows leakage.
2. **Calibrate a noise floor** before comparing architectures (their 0.0015-nat instrument: two optimizer-equivalent parameterisations). Any gap below the floor is not a finding.
3. **Sweep the confound axes independently** (params / compute / depth) and give every arm its own hyperparameter budget — the 2× Muon-rate spread means a shared sweep is silent bias.
4. **Register predictions before running** — the fineweb-edu band (0.02–0.05, measured 0.040) and the Sciq direction were pre-registered, which is what makes the localisation claim falsifiable.

Ported to our stack: a serving-workload classifier. Instrument per-token loss (or surprisal-vs-context-coverage proxy) on a candidate workload; if the gap concentrates on low-context tokens, the workload is storage-bound → FFN + retrieval; if it sits on context-anchored tokens, routing-bound → SAN-class / attention-heavy serving is quality-safe there.

### 2.2 Latent-space reframing

The SAN constraint is a statement about the convex hull of value vectors: for a fixed attention pattern, layer output is a transport of existing context content. That is exactly our **latent-to-latent preference** (Constraint 2): attention-only layers are latent mixture/transport operators; the FFN is the one learned per-position *nonlinear feature map* — closer to a raw→latent bridge with learned basis than to a mixer. The paper's rank dynamics read like our freeze/thaw vocabulary: **routing freezes early (selection structure = frozen snapshot), content rank accrues indefinitely in whatever write path exists** (capacity accrual = the Warm-tier accumulation shape). And the engram buy-back is our split: keep the *transport* layers in-model, externalise the *storage* deficit to retrieval (NeuronShard/AnyRAG) — model-internal latent transport + committed external memory.

### 2.3 Game-context reframe (workflow §1 step 4)

NPC dialogue/behaviour prompts are trace-rich: goal state, perception, recent events, quest state are all in context — routing-bound by the paper's account, i.e. the regime where attention-only is quality-safe. Knowledge queries ("what is this item's lore?") are query-shaped — storage-bound → route to retrieval or the FFN model. The diagnostic in §2.1 is the per-workload decider; a zone-served NPC population could run the SAN-class tier for the routing-bound majority at a fraction of the weight bytes.

### 2.4 Consumer-context reframe (priority #2 — the healer)

riir-clippy fix work is *mixed*: the fix shape usually mirrors in-file context (routing — the corpus/AST chunk supplies the pattern) but library/API knowledge is storage (an FFN model knows idioms weights-only). A span-level region decomposition of healer loss would say which. No consumer-surface adoption is claimed here — filed as the diagnostic's first candidate workload (issue, below).

### 2.5 Fusion subsection

1. **SAN decode cell in the perf league** (fusion priority #3): a parameter-matched attention-only arm turns the league into a bytes/token comparison. SAN at matched params streams ~1/3 the weight bytes (FFN ≈ 2/3 of non-emb params) — on the M3 (bandwidth-bound decode) that is the cell our fused attention kernels win outright, and `needle3.cact` (568: 29 MB / 20L / CQ2 never-unpack) is a ready-made SAN serving artifact. *Gated on a model artifact + engine support* (GGUF graph without FFN, or the cact path).
2. **SAN + NeuronShard engram** (priority #1/#5 boundary): Needle 2's design is architecturally our riir-neuron-db retrieval bolted onto an attention-only stack — the paper's own account says the deficit is *exactly* lookup tokens, and retrieval supplies exactly those. On-device tier (Needle 3 class, 8–29 MB) + shard retrieval = context-grounded model with committed external memory. **Novelty TBD — issue, not a claim** (Raven 006's counterpoint stands: pure slot-memory dropped to 0 on multi-needle N3-32K; hybrid shapes need care).
3. **Query-token diagnostic as tier router** (priority #1, modelless): §2.1 instrument drives per-workload model/tier selection across the fleet (game NPCs vs healer spans vs storage queries). Zero training; needs a validation rig.

---

## 3. Verdict — per track (workflow §1.5)

**Track (a) modelless inference — query-token diagnostic + measurement protocol: Gain.**
Actionable (a new instrument with a validation path; the noise-floor + region-decomposition protocol upgrades our own bench discipline), but no parity/perf claim is proven here. → `.issues/` entry (diagnostic rig + candidate workloads: healer spans, NPC prompts). No "already ships" claim to defend — the region-decomposition loss instrumentation does not ship anywhere in the workspace (closest cousin: retrieval-head calibration, Research 086/362, which scores *heads*, not *token regions*).

**Track (b) league/perf — SAN decode cell: GOAT-plan, conditional.**
The architecture result is published (the paper itself — not ours to claim), but the *cell* is real league surface: an SAN GGUF/cact served by our attention path vs llama.cpp at matched weight bytes. Gate: G1 correctness (reference logits), G2 tok/s + bytes/token at matched params, G3 no-regression on the Bonsai cells, G4 alloc-free. **Blocked on an artifact** (needle3.cact in-engine, or a trained SAN GGUF). Feature flag `san_decode`, opt-in until the cell exists.

**Track (c) model-based training — SAN pretraining recipe: riir-train recipe note, not a plan today.**
Applicable Path 0.5 items: Muon with per-arm LR sweeps (2× spread measured); QK-norm mandatory at depth; post-attention sandwich norm (+0.009 nats); residual gates optional/neutral (diagnostic only); tied embeddings, pre-norm, GQA 8q/4kv, RoPE; U-shaped depth, 20L optimum, 48L trains; SYNTH 105B for reasoning-dense; expect fineweb-class text to cost ~7× more (0.040 vs 0.0055). Worth an SAN training run **only if** the league cell (b) is wanted — the two are one decision.

**Not Super-GOAT:** the headline mechanism is published prior art (their paper); our candidate novelty is confined to fusion ideas #2/#3, both filed as novelty-TBD issues per the no-candidate-escape-hatch rule.

### MOAT gate (§1.6) — katgpt-rs

- **In scope:** Transformer stack — layers/attn slots (the MOAT table names this exact surface). The SAN result re-prices the FFN/GEMV slot (katgpt-transformer, Plans 431/486/100) vs the attention slot (katgpt-attn): a valid per-stack ledger entry is "attention-only depth ladder = parameter-bound decode cell; FFN slot stays default for storage-bound workloads".
- **Per-stack ledger:** nothing promotes or demotes today — no SAN artifact is served. The flag `san_decode` is the ledger row when the cell lands.
- **Scope discipline (the load-bearing caveat):** every paper number is ≤87M params / 105B tokens on SYNTH (+ one fineweb-edu control pair). **Bonsai-27B is ~300× larger and its mixture is storage-heavy by the paper's own account — 0.006 nats does NOT transfer, and iso-depth 0.470 nats is what in-place FFN deletion on Bonsai would cost.** The paper's larger-scale storage-heavy experiment is untested anywhere. Any FFN-lite decode claim on Bonsai must be re-measured, not inferred.

### Prior art (§4, searched 2026-09-18)

- **"A Controlled Study of Attention-Only Transformers"** (Cactus, Jul 2026) — the source paper itself; owns the architecture claim.
- **"Attention-Only Transformers via Unrolled Subspace Attention" (MSSA, Wang, OpenReview)** — attention-only via multi-subspace self-attention; different route (subspace machinery, not matched-param FFN deletion).
- **Dordevic et al. 2024 (AAAI)** — shallow FFNs *as* attention approximations (reverse direction).
- **"Attention Is Not All You Need: The Importance of FFNs" (2025)** — layerwise FFN importance in pretraining; supports FFN-as-memory, no matched-param deletion test.
- **Dong et al. 2021** (rank collapse for pure attention) — the classical negative result; addressed directly by the paper (min layer rank 173/512; residuals + QK-norm escape the regime).

### Exact quotes for citation

1. "At matched parameters the answer is 0.006 nats, and all of it lives on tokens with nothing to look up."
2. "Deleting feed-forward layers costs 0.47 nats at matched depth and 0.26 at matched compute; hand the freed parameters back to attention as depth and 0.006 nats remain, reproducible across seed pairs to one part in ten thousand."
3. "for a fixed attention pattern, a SAN layer is linear in its inputs, and each head's update at a position lies inside the convex hull of the value vectors of the positions it attends to."
4. "the optimal Muon rate differs by 2x between the arms, and a shared rate silently biases the whole comparison" (+ noise floor: "0.0015 nats")
5. "The matched-parameter gap shrinks with training: 0.046 nats at 5B tokens, 0.019 at 30B, 0.0055 at 105B"
6. "the per-token gap there is five times the sample aggregate while those tokens carry 8% of the loss" (query tokens, 31B)
7. "it favours the SAN, and the margin grows with training in the direction we registered in advance, 0.725 to 0.742 for the SAN while the FFN model slides from 0.702 to 0.661" (Sciq)
8. "we registered, before launching the run, that a matched-parameter pair trained on fineweb-edu would show a gap between 0.02 and 0.05 nats. It measured 0.040. The same pair reverses on lambada, 0.203 against 0.181 in the SAN's favour"
9. "The routing matrices, Q and K, crystallise within the first quarter of training and do not move again" … "a minimum layer rank of 173 of 512 at 20 layers, so the classical rank-collapse regime for pure attention is never approached once residuals and normalisation are in place."
10. "QK-normalisation is load-bearing: removing it diverges outright at the tuned learning rate" … "post-attention sandwich normalisation is the only variant that beats the baseline, by 0.009 nats."
11. "At matched parameters a SAN pays roughly twice the FLOPs per token at 2048 context, and at matched FLOPs the FFN model is ahead."
12. "Needle 2 was a Simple Attention Network with an engram memory bolted on for the facts that are not in context; Needle 3 keeps the attention-only stack and adds a ladder so that every depth from 2 to 20 layers is a deployable model."
13. "Whether a task is storage or routing is not a property of the task. It is a property of the match between the task and the training distribution."
14. "All results are at or below 87M parameters and 105B tokens, on one reasoning-dense corpus plus one knowledge-dense control pair, and MMLU-class benchmarks are at chance at these scales."
