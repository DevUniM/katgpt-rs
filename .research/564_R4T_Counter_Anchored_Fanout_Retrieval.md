# Research 564: R4T — Counter-Anchored Fan-Out Retrieval & Set Admission

> **Source:** "Efficient, Property-Aligned Fan-Out Retrieval via RL-Compiled Diffusion" (Retrieve-for-Train / R4T), [arXiv:2603.06397](https://arxiv.org/abs/2603.06397), Jiang, Li, Ryu, Hu, Su, Wan, Hebert, Peng, Han, Kuzmin, Boutilier (Google Research + UIUC), ICML 2026 — read via the [research blog](https://research.google/blog/bypassing-inference-bottlenecks-accelerating-complex-ai-search-with-retrieve-for-train/) (2026-09-15)
> **Date:** 2026-09-16
> **Status:** Active — distillation complete; Plan 599 (modelless, PRIMARY) + riir-train Plan 412 (recipe, SECONDARY) filed
> **Related Research:** 496 (SPADE — corpus grounding as THE diversity mechanism), 510 (ActFlow — sphere-exclusion/Vendi scoreboards), 235 (Thicket variance-probe fan-out spaces)
> **Related Plans:** 599 (counter-anchored set admission — this note's primary extraction); riir-train 412 (training recipe, Path 0.5); riir-clippy issue 121 (healer consumer)
> **Classification:** Public

---

## TL;DR

R4T trains a fan-out LM with RL (Soft-GRPO) against a **set-level composite reward** whose three terms are **mutual counter-anchors** — groundedness (distance to the corpus manifold), diversity (Vendi Score over the generated set), alignment (anchor to the original query) — then distills the learned behavior into a 53.9M diffusion model that maps a query embedding to a complete *set* of target embeddings in one non-autoregressive pass (12–20× faster than autoregressive fan-out). The transferable core for this stack is **not** the RL or the diffusion student: it is (a) the counter-anchor objective as a **modelless selection-time admission gate**, (b) exact Vendi certification via **d×d eigenduality** (our d=8 regime makes this ~512 FLOPs, K-independent), and (c) **latent query fan-out** (direction bank + manifold snap) which makes the paper's reward-hack failure mode *structurally impossible* — latent candidates are corpus points by construction, so groundedness is an identity, not a penalty term.

**Distilled for katgpt-rs (modelless, inference-time):** a counter-anchored set-admission operator — greedy admission scoring `g(x) + α·a(x,q₀) + κ·log(1 + x̂ᵀM⁻¹x̂)` under a colinearity cap, with Sherman–Morrison rank-1 maintenance (O(d²)=64 FLOPs/admission at d=8), an incremental participation-ratio tripwire, an exact cosine-kernel Vendi certificate from one 8×8 eigensolve, and a collapse→re-fan-out recovery ladder. The greedy modular+logdet surrogate carries the classical (1−1/e) bound; exact Vendi certifies post-hoc.

---

## 1. Paper Core Findings

1. **Set-valued retrieval** (a coherent slate: "camping gear" → tent+bag+stove+lamp, not 4 tents) requires optimizing **non-decomposable set-level properties** — diversity/coverage/complementarity only exist as functions of the whole set.
2. **Zero-shot LLM fan-out fails two ways:** *paraphrastic collapse* (near-synonymous sub-queries) and *autoregressive latency* (hundreds of CoT tokens; ~50 s at large context batches).
3. **Three-step pipeline:** (i) RL-train a fan-out LM (Gemma3-4B/Qwen3-4B, exactly 10 sub-queries/rollout) via Soft-GRPO against the composite reward; (ii) the frozen FOLM synthesizes (query → target-set) supervision offline, zero human labels; (iii) distill into a 53.9M DiT (hidden 1024) that emits all 10 target embeddings in one pass (VE/EDM, x0-prediction, 256-step PF-SDE sampler at inference; 0.07 s vs 1.46 s AR at batch 8).
4. **The counter-anchor law (the ablation):** groundedness-only → degenerate strings that mathematically exploit vector coordinates ("line ending line ending"); +alignment → paraphrase collapse; +Vendi → the policy is forced into a balanced region of embedding space. Each pair of anchors leaves one degenerate family feasible; the triple excludes all three. Default reward weights λ = 0.6 groundedness / 0.2 diversity / 0.2 alignment.
5. **Soft-GRPO** = GRPO advantage `(r−μ_G)/(σ_G+ε)` + bidirectional per-token KL to the sampling policy (β₁ forward-KL in ratio form + β₂ reverse-KL as −log πθ), unclipped — not temperature softening.
6. **RL as a one-time "objective transducer"** — decouple expensive reward-driven exploration from the deployed model; deploy the cheap compiled artifact.

## 2. Distillation

### 2.1 Path 0 component table (coverage × extraction, post signal-diff)

| # | R4T component | Math | Coverage in stack (signal-diffed) | Extraction (modelless) |
|---|---|---|---|---|
| 1 | Vendi Score `exp(−Σλ̂lnλ̂)` | kernel-spectrum entropy | **SHIPS** — `certified_frontier::vendi_diversity(eigs)` (Plan 580) consumes identical formula as a scoreboard | Covered; new: exact cosine-kernel eigs via **d×d eigenduality** (K-independent) + incremental participation-ratio fast path |
| 2 | Diverse set selection | greedy over marginal diversity | **PARTIAL** — `ShardIndex::retrieve_diverse` seed(cosine-nearest)+marginal wedge-span greedy. Signal diff: admission consumes *pure diversity* (`wedge(q,c)+Σwedge(s,c)` — maximizes distance from the query too); **no alignment anchor in admission, no certificate, no tripwire, no recovery** | Extend to the counter-anchored triad in one admission score |
| 3 | Collapse detection | set degenerates to one family/direction | **PARTIAL (categorical)** — riir-clippy `instantiation_rerank::detect_collapse` (top-k pool on one rule family, `oracle_outside` evidence) + `collapse_monitor` pool-entropy axis. Signal diff: categorical family entropy, not geometric kernel spectrum; post-hoc, not selection-time | Geometric tripwire (PR/eigenduality Vendi) at admission time + re-fan-out ladder |
| 4 | Alignment counter-anchor | cos(x, q₀) | NOT in any admission score (only as the cosine seed) | Modular term in the gate |
| 5 | Groundedness penalty | kNN manifold distance | Implicit (retrieval returns corpus points) | Free post-snap identity; one-probe audit for generated candidates |
| 6 | **Latent query fan-out** (generate K diverse query facets, then ground) | — | **NOT SHIPPED** — retrieve_diverse selects existing shards; nothing *expands* a query | Tangent-cap direction bank (`sphere_exclusion_coverage`) + θ-ladder + manifold snap; local-PCA variant (kNN covariance 8×8 eigensolve) |
| 7 | Offline compile → one-pass deploy | RL→supervision→student | **PARTIAL** — freeze/thaw + ruliology L3 sweep pattern | Offline sweep → 1 KB frozen direction bank (BLAKE3-committed, `MerkleFrozenEnvelope`) vs the paper's 53.9M params |
| 8 | Soft-GRPO (bidirectional KL) | loss form | NOT SHIPPED — `loss_grpo` has DAPO/GEPO/duplication stabilizers, no soft-KL terms | riir-train Plan 412 (~50-line loss addition) |
| 9 | Diffusion set-sampler (query emb → K embs) | trained artifact | NOT SHIPPED (not needed at d=8 — see §2.4 L6) | riir-train Plan 412 (trained track, gated) |
| 10 | RL fixed point on finite populations | advantage-weighted → exp-tilt `w∝e^{λΨ}` | **SHIPS as machinery** — `distributional_steering` FkStepper + `systematic_resample_into` | Optional deterministic reweight replacing the RL entirely at our scale |

### 2.2 Fusion (the novel combination)

- **Healer (fusion priority #2):** `LatentMatcher` fans a span across seven per-domain `RuleIndex`es and merges — an unanchored set decision. Counter-anchored set rerank (grounding=identity, alignment=span similarity, diversity=provenance/kernel spread) with `detect_collapse` as the eval axis → riir-clippy issue 121. Fastest GOAT on the table.
- **Game runtime (priority #1):** AnyRAG/NPC evidence slates — diverse grounded evidence feeding KG-triple emission kills echo-chamber triples (one source repeatedly "confirming"); zone attention gets the same triad (personality alignment × zone-manifold grounding × vendi spread). Per-NPC, latent-local, never synced — inside the sync-boundary rules. Follow-up consumer after Plan 599 lands.
- **Cross-cutting:** the tripwire is a second, *geometric* collapse detector beside CGSP's `EntropyCollapse` (policy entropy over arms vs kernel spectrum over latents — orthogonal signals).

### 2.3 Prior art (§4 search — pins the claim before scoping novelty)

Claim pinned: *"counter-anchored set-level admission (align+ground+diversity) with exact-Vendi certificate and collapse-recovery, operating modellessly on latent sets"* — distinguished from classical DPP/MMR greedy by the certificate loop and counter-anchor structure, and from R4T itself by selection-time (not training-time) use.

- RL query fan-out: ParallelSearch (2025), ExpandSearch (arXiv:2510.10009), Learning-to-Expand (arXiv:2509.05570), Nogueira & Cho (2017) — **preceded**.
- Vendi as RL reward: VendiRL (arXiv:2509.02930, Sep 2025, skill diversity) — **preceded** (in-domain instantiation new).
- Diffusion slate/embedding generation: arXiv:2408.06883 (slate diffusion 2024), DreamRec (NeurIPS 2023), DiffGRM (Oct 2025) — partial.
- One-pass diverse slates in production: YouTube DPP (KDD 2018), Fast Greedy MAP (NeurIPS 2018) — the capability is classical; greedy modular+logdet admission IS DPP MAP territory (Kulesza & Taskar 2012).
- AR→diffusion distillation: Distilled Diffusion LMs, Beyond Autoregression (8×, ICLR 2025), dLLM, A2D — established pattern.
- **Genuinely new in the paper:** the counter-anchor triad + anti-hacking analysis; the end-to-end RL→diffusion compilation. **Genuinely new in OUR filing:** selection-time counter-anchored admission + eigenduality certificate + latent fan-out with structural reward-hack immunity.

### 2.4 Extractable limit laws (property-testable)

- **L1 (collapse inevitability):** any *modular* objective `J(S)=Σf(s)` without a set-coupling term degenerates to effective rank 1 under duplicate-tolerant generation — the paper's ablation is a corollary of modularity, not an RL pathology. One-line proof; property test.
- **L2 (counter-anchor exclusion):** three degenerate families (paraphrase-collapse / semantic-drift / coordinate-gaming); each *pair* of anchors leaves one feasible; the triple excludes all interiors. Testable prediction: zero any one weight → the corresponding family becomes reachable.
- **L5 (eigenduality cost law):** for linear/cosine kernels `K = X̂X̂ᵀ`, nonzero spectrum = spectrum of the d×d Gram — **exact** Vendi from one 8×8 eigensolve, O(K·d²+d³), corpus-size-independent. (Fails for RBF → Nyström approximation; we pin cosine.)
- **L6 (the honest d=8 ceiling — cuts against us):** Vendi ≤ min(K, d); at d=8 a slate cannot carry >8 genuinely distinct directions. The tripwire must report *saturation*, not just collapse; consumers needing K>8 distinct directions must raise d (e.g. BonsaiEmbedder space) or accept the ceiling. The categorical family-entropy detector (instantiation_rerank) is **complementary, not replaced** — family space exceeds latent dims.

### 2.5 Latent ↔ raw boundary

The gate operates purely on latent directions (`[f32;8]`, dot products, kernel spectra). Outputs are corpus-shard references (raw). Nothing crosses a sync boundary; no chain angle; per-NPC consumers stay latent-local. Bridge functions remain zero-alloc, feature-gated, sync-invariant.

## 3. Verdict

**One verdict per track:**

- **Track (a) modelless inference: GOAT.** Provable selection-quality gain + a new tripwire signal family; not a new capability class. Plan 599 files it (feature `set_admission`, GOAT gate, promote/demote vs the pure-diversity incumbent).
- **Track (c) model-based: Gain.** Recipe applicable (Soft-GRPO soft-KL terms + Vendi composite reward + diffusion set-router); riir-train Plan 412 (Path 0.5: ~20–30 4090 GPU-h pilot; GOAT gate = set-recall/MRR vs the shipped modelless baseline, OOD fresh-family rig as the justification axis, mandatory no-Vendi collapse negative control). **SECONDARY by the serving-envelope rule (TTPO):** the modelless gate runs inside the healer's per-span hot path; the trained router is per-file batched and must beat the modelless arm to exist.
- **Track (b) self-adaptive: recorded.** Re-freezing improved direction banks from runtime evidence (C5 pattern) is a Plan 599 Phase-4 follow-up; no separate filing.

**Novelty gate (§1.5) on the modelless primitive:** Q1 prior art = PARTIAL (core greedy = classical DPP MAP; triad published in this paper as a *reward*; selection-time use + certificate loop is ours). Q2 new behavior class = NO. Q3 selling point = WEAK-MODERATE ("our healer/NPC retrieval admits provably-balanced slates" — quality, not capability). Q4 force multiplier = YES (vendi × retrieve_diverse × LatentMatcher × CGSP collapse lineage × freeze/thaw). **Not all 4 YES → GOAT, not Super-GOAT.**

**MOAT gate:** katgpt-rs — base selection-math primitive via fusion of shipped pieces, in scope. riir-clippy — consumer-first (retrieval floors/OOD), issue 121 in scope. riir-train — active recipe moat, Plan 412 in scope.

**Panel discard audit (§3.5):** (1) model-based advocate's full 3-stage FOLM pipeline as PRIMARY — discarded as primary on serving-envelope fit; retained as Plan 412 Phase 2. (2) riir-rag AnyRAG trained retriever (advocate pick b) — deferred behind the clippy pilot (the OOD eval rig exists only there); recorded in Plan 412. (3) exp-tilt-as-RL-replacement — kept as an optional Plan 599 arm, not mandated (the fixed-point argument holds on finite populations; unmeasured on our corpora).

**Honest caveats:** kernel assumed cosine (eigenduality exactness); paper Table 3 values (G, β₁/β₂, σ_data) unpinned from the blog — Plan 412 T0 pins them from the PDF; the 12–20× latency headline does NOT transfer (our baselines are µs–ms, not 50 s) — every gate is quality-at-iso-latency; d=8 ceiling per L6.
