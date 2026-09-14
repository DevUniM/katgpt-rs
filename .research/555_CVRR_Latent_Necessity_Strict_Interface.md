# Research 555: CVRR — Latent Necessity & the Strict Interface (Informativeness ≠ Use)

**Status:** DISTILLED — Gain-tier, per-track verdicts (modelless Gain + training Gain); katgpt-rs Issue 776, riir-ai Issue 953, riir-train Plan 402 filed 2026-09-14. riir-clippy audit DEFERRED (repo mid-batch by sibling agent — §6).

> **Source:** "Reason Through the Latent! Making Latent Visual Reasoning Necessary" — [arXiv:2609.06746v3](https://arxiv.org/abs/2609.06746) — Suhyeong Park, Junha Jung, Jaewoo Kang (Korea University, dmis-lab / AIGEN Sciences), v1 2026-09-06, v3 2026-09-11. Code: [dmis-lab/CVRR](https://github.com/dmis-lab/CVRR) (README read at verdict time; no clone — paper §3 + App. C carry the complete method, nothing here needed byte-quotes from source).
> **Date:** 2026-09-14
> **Related Research:** [244](244_Self_Evolver_Faithfulness_Cognitive_Integrity.md) (the shipped audit half — Zhao et al. arXiv:2601.22436), 362 (HydraHead causal head-importance — shipped necessity scoring)
> **Related Plans:** [278](../.plans/278_faithfulness_probe_modelless.md) (FaithfulnessProbe), 298 (SmearClassifier), 358 (causal head-importance)
> **Cross-ref (riir-ai):** Issue 953 (frozen-evidence deliberation kernel + think-brain necessity audit) · (riir-train): Plan 402 (text-side strict-interface ladder) · (riir-clippy): deferred — §6
> **Classification:** Public

---

## TL;DR

CVRR's central distinction — **a latent state containing task-relevant information (informativeness) ≠ the computation actually using that state (path necessity)** — is verified by interventions (replace the latent with blank / matched-swap / norm-matched noise while bypass routes stay intact: predictions survive, the latent is decorative) and *fixed* architecturally (delete every bypass route before the consumer so the recurrent latent is the only path). **The audit half already ships in this stack** (FaithfulnessProbe Plan 278, 2026-06-16 — three months before CVRR v1 — plus `intervention_battery` and `causal_head_importance`), which kills Super-GOAT Q1 for the modelless track. The surviving deltas are real and cheap: **contrastive-pair coherent matched-swap** (isolate evidence-conditioned content), **norm-matched noise** (separate structure from magnitude), **necessity-by-construction enforcement** (nothing shipped enforces non-bypass — everything is diagnostic), a **frozen-evidence convex-mix deliberation kernel** (iterate state against FIXED evidence within one think cycle — nothing ships this shape), and the **step-drift metric** (decorative-recurrence detector). The training recipe (frozen backbone + rank-32 LoRA on ONE reused layer + answer-token-CE-only + delete-context-before-decode) gets a gated riir-train ladder.

**Distilled for katgpt-rs (modelless, inference-time):** intervention protocols and interface discipline, never the trained transition — (a) contrastive-pair donors + norm-matched noise as upgrades to the shipped intervention sets; (b) the strict-interface law: *a latent is presumptively decorative until an intervention moves its consumer's output, and provably necessary only when no parallel route exists*; (c) `h_t = (1−β)h_{t−1} + β·Σ_j σ(⟨h,v_j⟩/√d)·v_j` over frozen evidence rows — sigmoid-gated (never softmax), convexity-bounded (`‖h_t‖ ≤ max(‖h_{t−1}‖, ‖f‖)`), the modelless baseline any trained transition must beat.

---

## 1. Paper Core Findings

**Setup.** Latent visual reasoning (reasoning in hidden states instead of text CoT) has a hidden failure mode: the proposed latent state can be *informative* while the model's answer never *uses* it, because the original multimodal answer context (visual token rows, multimodal prefix KV) remains available as a **bypass**.

**Preliminary experiment (their Figure 1a).** For existing latent visual reasoners (UniVLR, LVR, Monet, ...), replace the proposed latent with (i) a blank-image latent, (ii) a matched latent from an example with a *different answer*, or (iii) row-norm-matched noise — leaving the multimodal answer context intact. UniVRL's accuracy moves ≤ 0.5pp under all three. The latents are behaviorally nonessential.

**CVRR (the fix).** Three components on Qwen2.5-VL-7B:

1. **Causal visual-read boundary (ℓ\*=20/28).** Layer-wise activation patching on contrastive pairs (same question, different images → different answers): patch visual-token activations at layer ℓ, measure the bidirectional drop in answer log-prob margin (Eq. 1). Pick the layer preceding the first sustained decline — where the question state has absorbed most visual competence (question-state sufficiency 75.4% vs 75.9% full-MM) *and* visual rows still exert downstream influence (App. H).
2. **Persistent visual recurrence.** Reuse layer L21 as a shared recurrent transition. `h₁ = P_Q·f₀(H*)` (native multimodal init — the load-bearing part), `v = P_V·H*` frozen forever; each step re-inserts the evolving question rows into the fixed multimodal scaffold and convex-mixes: `h_t = (1−β)h_{t−1} + β·P_Q·f_φ(H_t)`, β=0.5, T=4. Visual re-reading happens through the layer's *native* causal self-attention — no new cross-attention module. Cost: T=4 is only +9.9% latency / +13.4% FLOPs vs T=1 (single shared layer, not backbone re-invocation).
3. **Strict causal decoder interface.** Before answer decoding, DELETE visual rows + the entire multimodal KV cache. Lower layers get text-only prefix caches; the answer decoder sees the recurrent state as the *only* image-conditioned input. Path necessity "enforced by construction rather than discovered post hoc."

**Training.** Backbone 100% frozen; LoRA rank-32 (α=16, dropout 0.01) on ONLY the transition layer's attn+MLP projections = 2.88M / 8.295B params (0.0348%); answer-token cross-entropy ONLY — no latent targets, no teacher trajectories, no reconstruction. 3 epochs, eff. batch 128, lr 2e-5, 4×B200.

**Results.** 81.2% V\*, 52.7% MMVP pair, 55.2% BLINK under the strict interface — while the six retrained latent-reasoner baselines under the same interface collapse to ≤39.8% / ≤2.7% / ≤38.8%. Ablations: w/o visual re-read −12.0/−34.7 pts; text-only init instead of native multimodal init −44.0/−50.7 pts (= removing the entire visual path); w/o learned transition −4.7/−20.0 pts.

**Causal analyses (§5 — the modelless protocols).**
- Corrupt the final recurrent state: 81.2 → 14.0% (matched swap) / 35.6% (noise). *Restoring the multimodal prefix partially compensates* (→17.4/44.5%) — direct proof the bypass was carrying the baselines.
- Same-question swap (MMVP pairs share the question): 73.3 → 26.7%, vs text-only anchor 50.0% — *incompatible* image-conditioned content is more disruptive than *no* image content, isolating evidence-conditioning from question disruption.
- Crossed states: clean evidence `v` corrects an incorrect `h₁`; incorrect `v` degrades a clean `h₁` (DiD ±14.8 pts) — only while question→visual KV connections are enabled.
- Step-varying influence: consecutive per-step causal maps over the same frozen evidence have cosine 0.37/0.35 — *different evidence regions become causally relevant as the state evolves*; recurrence is not a fixed-weight re-read.
- Generalizes across 4 more VLM backbones (boundary re-localized per backbone: 21/25/32/35).

## 2. Distillation — coverage map + signal-diff

**The headline honest finding: the audit half of this paper already ships in this stack, from a different source paper, three months earlier.** Research 244 → Plan 278 FaithfulnessProbe (2026-06-16, from Zhao et al. arXiv:2601.22436) runs exactly CVRR's preliminary-experiment shape: perturb an injected memory segment, query the consumer, measure behavioral delta, verdict `is_faithfully_used(threshold)` — the decorative-latent detector. Around it: `intervention_battery` (interpolation_geometry, 5-way whole-latent: matched / shuffled-donor / zero / mean / noise, with `latent_is_causal()` + `flips_to_donor()`), `causal_head_importance` (Plan 358: activation/path patching necessity scoring — explicitly catches "correlated bystanders... overridden downstream", i.e. informative-but-unused heads), katgpt-claim L3 (`EvidenceItemId::Intervention` — ablate/zero/clamp/steer with pre-registered change), and `convergence_cadence` (settled→early-commit / churning→deliberate). This kills Super-GOAT Q1 for the modelless track and narrows the claim to the signal-diff survivors:

| CVRR component | Shipped cousin (signal it consumes) | Delta that survives |
|---|---|---|
| Blank-image latent intervention | `perturb_empty` / battery `zero` (content removed) | covered |
| Matched-swap, **contrastive pair** (same question, different evidence) | `perturb_irrelevant` (RANDOM picks from pool — incoherent mixture); battery `shuffled` (random donor — confounds query+evidence content) | **coherent whole-state swap from a contrastive donor** isolates evidence-conditioned content (§5.3: 26.7% vs 50.0% anchor — incoherent or confounded swaps cannot show this) |
| **Norm-matched noise** | battery `noise` (Gaussian around origin — magnitude AND structure both destroyed) | `n_j = g_j·(‖s_j‖/‖g_j‖)` preserves magnitude, destroys structure only — separates the two failure channels |
| Layer-wise boundary sweep (patch source at ℓ, margin response) | `causal_head_importance` (per-HEAD necessity; span logit-diff readout) | per-LAYER/stage sweep: where does source info enter the target representation + where does its direct influence die (sufficiency ↑ × residual influence ↓ crossover) |
| **Strict interface** (delete bypasses → necessity by construction) | *nothing* — every shipped instrument is DIAGNOSTIC (detect decorative use); the TriggeredInjectionGate mitigates (skip injection) but enforces nothing | enforcement half: per-consumer dataflow gate + replay-level necessity test. **Inverts cleanly onto our two-brain model** — see Issue 953 |
| Persistent recurrence, fixed evidence, convex mix | `evolve_belief` (leaky integrator, NEW evidence per tick); `reestimation` (coherence-triggered refit of direction vectors from a ring buffer of NEW observations — freeze/thaw on vectors, warm tier); motor-gated rehearsal (pre-action gating, not evidence re-reading) | **frozen-evidence iteration within one think cycle** — re-read the SAME evidence T times as the state evolves; free convexity norm bound; sigmoid-gated rows |
| Step-varying influence drift (cosine 0.37) | `convergence_cadence` (across-tick settle/churn health) | per-STEP gate-map drift inside one cycle: ≈1 ⇒ decorative recurrence (loop is a no-op burning ticks), ≈0 ⇒ no state carry |

**Raw/latent boundary note (critical for the enforcement half):** our two-brain model *deliberately* keeps the raw path load-bearing — anti-cheat and deterministic replay MUST read exact raw state; that bypass is correct by contract (AGENTS "Never gate raw sync correctness behind a feature flag"). CVRR's strict interface applies to the **think-brain consumer only** (strategic decisions consume belief-derived scalars, never fog-hidden raw data) — plus the **mirror gate**: zeroing raw coordinates MUST break anti-cheat (the raw path's necessity asserted in reverse). Never the physics path.

## 3. Verdict — one per track (TTPO discipline)

| Track | Tier | One-line reasoning |
|---|---|---|
| Modelless (audit + interface + kernel) | **Gain** | Q1 fails — FaithfulnessProbe family ships the decorative-latent audit (independently, earlier); the surviving signal-diff deltas (contrastive donors, norm-matched noise, enforcement gate, frozen-evidence kernel, drift metric) are real, cheap, and extend existing pillars → Issues 776 + 953. |
| Training (strict-interface recurrence, text-side) | **Gain** | New-to-stack (not world-novel — Coconut/looped/recurrent-depth are the published text-latent class, per §5 below), cheap falsifier ladder with honest stop conditions → riir-train Plan 402. |

Not Super-GOAT: modelless Q1 = NO (shipped substrate); training track Q2/Q3 unproven until the boundary sweep survives. No "candidate" hedging — the filings are the Gain-tier deliverables.

**MOAT gate:** katgpt-rs — extends the shipped faithfulness/intervention pillar family via fusion (fits: base audit primitives, public). riir-ai — frozen-evidence deliberation is a cognition-substrate candidate connecting ≥2 pillars (belief kernels + think-brain + FaithfulnessProbe consumer); riir-ai Issue 953. riir-train — active-moat recipe plan with GOAT-vs-modelless baseline (the Issue 953 kernel IS the modelless comparator Plan 402 P3 must beat).

## 4. Adversarial panel record (mandatory — abstract carries LoRA/SFT)

Two advocates spawned in parallel with the prior-art search; coordinator merge into the Path 0 inventory:

**No-GD advocate (12 items)** — strongest 3: (1) intervention-sensitivity audit suite → **killed as novel by Plan 278 coverage**, narrowed to the two intervention upgrades (Issue 776); (2) convex-mix fixed-evidence recurrence kernel → **Issue 953** (the only *runtime behavior* primitive; new emergent class: NPC attention shifting across frozen zone memories within a think cycle at fixed tick cost); (3) per-consumer bypass enumeration / strict-interface gate → **Issue 953** task 3, with the two-brain carve-out + mirror gate.
**Auditable discards:** standalone contrastive-pair *mining* primitive (folded into 776/953 protocols — no consumer without an audit first); generic stage-patch harness in katgpt-core (deferred to Plan 402 P1 — a harness with zero consumers is dead substrate, substrate-first rule); frozen-evidence read discipline / shared constructors / counterfactual-exchange / ε-calibration (subsumed into 776+953 tasks).

**Model-based advocate (8 items)** — strongest 2: (1) answer-token-only CE as a loss-mask diff on the live `bonsai_lora_accuracy_parity` harness (minutes–1h, sufficiency proof at 7B-scale) → **Plan 402 P2**; (2) activation-patching boundary localization as a pre-training tool (1–6h, decides the big bet before it costs 30–45 GPU-h) → **Plan 402 P1**.
**Auditable discards:** patching-scored data curation (optional P2.5, gated on P1's curve existing); one-layer-LoRA targeting + hyperparameter package (folded into P3 config); strict-interface *eval harness* (folded into P3's GOAT precondition). Honest flags recorded in Plan 402: vision→text transfer unproven (text context shares the LM prior → flatter patching curve), span-copy degeneration risk (text evidence can be copied; vision can't), Q2_0-ternary training dynamics ≠ paper's bf16 7B.

**Path 0 decomposition (documentation requirement):** audit protocols — modelless, SHIPPED (278/358/battery); interface discipline — modelless, files as Issue 953; convex-mix kernel — modelless, Issue 953; boundary sweep — modelless protocol, consumer is the training lane (Plan 402 P1); trained transition + answer-CE — genuinely GD, Plan 402. Paths 1–3 checked: freeze/thaw snapshot correction N/A (new capability, not bias correction); deterministic-LoRA construction cannot substitute (paper's own w/o-learned-transition ablation −4.7/−20.0: native-only insufficient); latent-space correction — the Issue 953 kernel IS path 3's analog and ships as the modelless baseline P3 must beat.

## 5. Prior-art search record (§4 — pinned claims before search)

- **Pinned modelless claim:** "intervention-sensitivity + bypass audit distinguishing decorative from load-bearing latents, for runtime consumers, consuming swap/blank/noise divergence" → **killed** as novel by in-stack coverage (Plan 278 family); narrowed claim "contrastive-donor coherent swap + norm-matched noise" survives (no shipped intervention consumes a coherent counterfactual state or magnitude-preserving noise).
- **Pinned training claim:** "delete-all-context-routes, decode-from-recurrent-state-only latent reasoning for text LLMs" → search (activation patching / causal intervention latent reasoning 2026) confirms the technique family is established (Vig 2020, Geiger 2021 causal abstractions, Meng 2022 ROME, best-practices arXiv:2404.15255, attribution patching at scale). Text-latent-reasoning landscape per the paper's own §A.1: Coconut (Hao 2025), looped transformers (Fan 2026 arXiv:2606.31779), recurrent-depth (Kohli 2026), Latent Sketchpad (Zhang 2025) — **none remove the context/KV routes pre-decode**; CVRR is the VLM-side prior art. Our claim is therefore *new-to-stack transfer with measured stop conditions*, not world novelty — stated as such in Plan 402.

## 6. Fusion + deferred items

- **riir-clippy — component-necessity audit (DEFERRED, not filed):** swap a pipeline component (learned ordering / RerankMode / Elo table) with static/null, measure fix-outcome **flip rate**: flip ≤ ε ⇒ component decorative/bypassed vs flip > ε but static wins ⇒ on-path-but-beaten — *different remedies*. Retroactively classifies the honest-negative ordering benches (Bench 085/088/089: "menu width 1 in 105/126" is the bypass signature — ordering cannot matter at width 1). Natural home: a `--domain X --necessity-audit` mode beside `--score-bench`/`--frontier-report`, extending the nonergodic A/B harness. **Not filed: the repo is mid-batch by a sibling agent (dirty score-history files block a clean pull); file as riir-clippy `.issues/106_*` when quiet.**
- **riir-neuron-db — consolidation drift:** does Raven/δ-Mem re-read different shard regions across sleep cycles, or is it stuck at drift≈1 on the same rows (degeneracy detector for the consolidation pipeline). Same drift metric, second consumer.
- **katgpt-claim:** CVRR's Figure 1a is now a second published instance of the L3-intervention evidence class the rubric already encodes — cite both papers at the rubric's next doc pass.

## Filed follow-ups

- katgpt-rs [Issue 776](../.issues/776_contrastive_matched_swap_norm_matched_noise.md) — intervention-set upgrade (probe + battery).
- riir-ai Issue 953 — frozen-evidence deliberation kernel + step-drift metric + think-brain necessity audit (feature-gated, GOAT-gated).
- riir-train Plan 402 — text-side strict-interface ladder (P1 boundary sweep → P2 answer-CE pilot → P3 gated lane).

**Provenance:** paper fetched from arXiv HTML v3 (2026-09-11) on 2026-09-14; repo README via github.com/dmis-lab/CVRR (no `.raw/` clone — method fully specified in paper; no byte-quotes taken from source). License CC BY 4.0 (paper).
