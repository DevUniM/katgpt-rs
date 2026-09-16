# Research 562: TypeSafe "System One Models" & Jev — Calibrated Structured Decisions

> **Source:** "Introducing System One Models & Jev" — TypeSafe AI blog, Diogo Almeida, 2026-09-15 — https://typesafe.ai/blog/introducing-system-one-models-and-jev (secondary: HN thread 49717558, The Register 2026-09-16, docs.typesafe.ai)
> **Date:** 2026-09-16
> **Status:** Done — Gain verdict, filed katgpt-rs Issue 810
> **Related Research:** 322 (Report-the-Floor UQ rule), 311 (conformal line)
> **Related Plans:** Plan 340 (ConformalIntervalCalibrator, default-on)
> **Cross-ref (riir-ai / riir-chain / riir-neuron-db):** riir-ai `arg_runtime/pipeline.rs` (ActionBridge ABSTAIN), `integrity/injection.rs` (5 affect scalars), `.proofs/RiirAiProof/Hla/Bounded.lean`
> **Classification:** Public

---

## TL;DR

TypeSafe AI (ex-OpenAI RLHF founder) announced **Jev**: a model class that gives up string generation entirely and emits **type-safe structured decisions (Bernoulli/Choice/Score) with calibrated probabilities, all in one parallel pass** (70–500 ms, output tokens free), trained with a "RLCD — Reinforcement Learning for Calibrated Decisions" method. Every component has published prior art (non-autoregressive generation, schema-conditioned encoders, calibration literature, constrained decoding); the integration + positioning ("a frontier-intelligence function call") is the product. For our stack this **validates the two-system serving architecture we already ship** (fast sigmoid-gated decision heads + slow deliberation) and exposes one real gap: **our sigmoid decision scalars are boundedness-proven but never calibration-gated**. Filed as katgpt-rs Issue 810 (Platt-style calibrator primitive + gates).

**Distilled for katgpt-rs (modelless, inference-time):**
A decision head is just a readout: state latent → per-schema-slot dot-product → sigmoid → calibrated probability, computed in ONE pass (one matvec — our ternary SIMD lane does this natively). The transferable primitives are (a) **calibration as a first-class output contract** (the probability means what it says, fit from outcomes — a tiny 2-param convex refit, no base-weight mutation: track-b self-adaptive), and (b) the **negative lessons**: a closed schema that cannot abstain forces confident wrong answers (HN's sharpest critique — our `ActionBridge` already abstains below threshold), and per-answer calibration does not compose into per-decision calibration (workflow-level ECE is the metric that matters).

---

## 1. Source Core Claims (with their own caveats)

| Claim | Jev | Blog's own "Nuance" / community audit |
|---|---|---|
| Outputs | Typed `Noul`(Bernoulli)/`Choice`(≤10 native, 255 via 2-stage)/`Score` + calibrated p + confidence | "Can't hallucinate" = schema-guarantee only; still confidently wrong; **cannot abstain** (forced answer) |
| Sampling | All outputs parallel, one pass, non-autoregressive | Architecture undisclosed; HN consensus guess: small encoder + calibrated readout heads (GLiNER2-shaped); a Qwen-2.5-1B "RLCD" clone appeared on HF within hours of launch |
| Training | "RLCD" — RL for calibrated decisions | No paper, no math; **acronym collision** with RLCD = Reinforcement Learning from Contrastive Distillation (Yang et al., ICLR 2024, arXiv:2307.12950) |
| Speed/cost | 70–500 ms; $0.042/MTok in, output free | Baselines include reasoning-mode LLMs; workflow evals authored in-house; reference = mean of GPT-6-Astra + Fable 5.1 (inherits their errors) |
| Eval | "Workflow evals": fixed compute graph, score = probability agreement with big-model ensemble | Nearest published: GKD/on-policy distillation (agreement as *training* loss), lm-eval-harness (fixed harness vs ground truth). The composition appears unpublished — and weaker than a real-tool oracle |

Use cases they name: "smart if-statements" (classify/route/score/branch), map-reduce over big data, real-time control (Doom demo on structured game state, 10 qps), LLM-output verification/guardrails, agent-overseer rubrics.

## 2. Prior-Art Landscape (all components covered)

- Non-autoregressive single-pass outputs: NAT (Gu et al. 2017, arXiv:1711.02281), LLaDA (arXiv:2502.09992), Mercury (Inception Labs), parallel-generation survey arXiv:2508.08712.
- Schema-conditioned single-pass decisions: **GLiNER2** (arXiv:2507.18546) — closest shipping analog; BERT-encoder classifiers; SPENs (arXiv:1511.06350).
- Calibration: Guo et al. 2017 (temperature scaling/ECE, arXiv:1706.04599); Kadavath 2022 (arXiv:2207.05221); verbalized-confidence overconfidence (arXiv:2306.13063).
- RL-for-calibration (the real "RLCD" content): **RLCR** (Damani 2025, arXiv:2507.16806 — proper-scoring-rule RL reward), Rewarding Doubt (arXiv:2503.02623 — log-score reward), reward-calibration RLHF (ICLR 2025, arXiv:2410.09724), CAPO (ACL 2026).
- Guaranteed-valid outputs: Outlines (arXiv:2307.09702), Geng EMNLP 2023 (arXiv:2305.13971), PICARD (arXiv:2109.05093).
- Two-stage high-cardinality score-then-choose: XMC family (AttentionXML, NeurIPS 2019; survey arXiv:2302.05971); retrieve-then-rerank (arXiv:1901.04085).

Verdict: the *class* is mature; TypeSafe's defensible novelty is integration + API + (claimed) training-data flywheel, none of which is extractable math.

## 3. Path-0 Inventory + Three-Track Verdicts

| Paper component | Track | Modelless analog / extraction | Verdict |
|---|---|---|---|
| Parallel structured readout (one pass) | a | **Ships**: `pick_domain`/`VariableRankRouter` argmax-over-dot-projections; one SIMD matvec = the whole "parallel sampler" for our schemas | Covered (§4) |
| Calibrated probabilities per output | a+b | **Gap → Issue 810**: Platt/temperature refit from recorded outcomes; CLR's ECE gate is the one existing calibrator, scoped to its own verifier | **Gain — file** |
| Abstain on low confidence | a | **Ships, and Jev lacks it**: `arg_runtime/pipeline.rs` ABSTAIN + SalienceTriGate CLARIFY | Covered (selling point) |
| 2-stage score-then-choose (≤255) | a | **Ships**: `rerank()`+`RerankMode`, `argtopk_with_scratch`, `pick_domains_top_k` | Covered |
| Workflow evals (reference-agreement) | eval | We are **ahead**: riir-clippy's clippy/rustc/git/lake oracles are real-tool ground truth; Bench-706-style Brier-vs-floor precedent exists | Covered (note the idea for NPC decision-graph evals) |
| RLCD training (RL for calibration) | c | Published recipes exist as separate papers (RLCR, Rewarding Doubt, ICRL); this source carries **zero method math** to distill | Recorded, no plan — audited discard below |

**Audited discard (riir-train plan not filed):** (1) the blog publishes no RLCD objective/recipe — there is nothing to transcribe; the actionable methods are the cited published papers, which are their own distill tasks; (2) serving-envelope: a trained decision head sits outside our 20 Hz hot path, while the modelless 2-param calibrator refit sits inside it (TTPO envelope rule); (3) existing GRPO reward-shaping (`riir-train-engine` bench_251) can absorb a calibration-reward row later **if** a trained head ever enters serving. Reopen trigger: Jev paper release, or any plan that trains a decision head.
*Adversarial-panel note:* the two mandatory briefs were covered by the parallel sub-agents already run (component-agent surfaced the model-based recipes incl. RLCR; substrate-sweep surfaced the modelless gaps + closed-form/convex feasibility). Merged above; no additional agents spawned to avoid duplicating completed work.

## 4. Workspace Substrate Mapping (vocabulary-translation grep, both layers)

- **Decision heads**: katgpt-core `variable_rank_domain_expert.rs` (`pick_domain<N,A>`, `RoutingVerdict`), `cgsp/dual_pool.rs` (`route_select`), riir-ai `arg_runtime/pipeline.rs` (`select_action → (action_idx, sigmoid_confidence)` + ABSTAIN), riir-games-shared `quant_expert_route`, riir-clippy `KernelExpertRouter::build_activity`. No `DecisionSchema` type exists — selection is modelless tables + argmax + sigmoid.
- **Sigmoid confidence**: 5 affect scalars via `project_belief_to_raw_signature` (`sigmoid(dot8(belief_delta, DIR))` — valence/arousal/desperation/calm/fear); belief-decay `sigmoid(-λ·Δtick)`; curiosity/verify-budget gates. **Bounded, not calibrated**: `.proofs/RiirAiProof/Hla/Bounded.lean` proves range (0,1) — a range proof, not distributional calibration.
- **Calibration substrate**: `ConformalIntervalCalibrator` (Plan 340, default-on; CRPS/coverage/Winkler + the Report-the-Floor rule); CLR verifier **ECE gate ≤ 0.10** (measured 0.0087, Bench 284); ECE/Brier/log-loss metrics in Bench 706 (nonergodic belief; Bayesian ω beat the sigmoid floor 119×) and Bench 579. **No generic Platt/temperature-scaling calibrator primitive anywhere** — the gap Issue 810 fills.
- **Two-stage/rerank**: `katgpt-attn-match/rerank.rs` (+`ndcg_at`), `argtopk_with_scratch` (NEON+AVX2), riir-clippy `RerankMode::Structural` (default).
- **Parallel-vs-AR**: speculative decode dominant; D2F masked diffusion (the one parallel all-at-once lane); BoM parallel hypothesis sampling (deliberately not calibrated UQ).
- **Oracles/ensembles**: real-tool oracles (clippy/rustc/git/lake) + known-answer tables; **no reference-model ensemble harness** (we consider that a feature — ground truth beats reference-agreement).

## 5. Game-Context Reframe (riir-ai)

Jev's Doom demo is *structured game state in → typed decisions + confidence out at 10 qps* — literally our NPC tick: state JSON → `pick_domain`-style head → action + sigmoid confidence. The frame transfers cleanly:

1. **"Smart if-statements" = our sigmoid gates.** Zone attention, curiosity triggers, VerifyBudgetGate tiers — all fuzzy decision rules composed into the tick graph. The System One framing is a *selling-point vocabulary* for the `riir-ai/.docs/` moat book (fast system = 20 Hz latent ops; slow system = CLR/KARC/MCTS deliberation — we have both, named).
2. **The can't-abstain critique is a competitive edge for us.** `ActionBridge` abstains below confidence threshold and escalates (CLARIFY); Jev structurally cannot. An NPC decision head that must always answer produces pathological behavior on out-of-distribution state; ours degrades to deliberation instead. Worth one line in the docs book.
3. **Per-scalar calibration ≠ per-decision calibration.** Even if fear=0.8 is calibrated as a *scalar*, "NPC fled" correctness is a composite. Issue 810's gate must therefore measure **decision-level ECE/Brier** (did the chosen action match outcome), not only per-direction scalar ECE — the same composite-calibration critique HN aimed at TypeSafe's workflows.
4. **Calibrated affect scalars unlock downstream consumers**: sleep-cycle consolidation thresholds, KG-triple emission thresholds (latent-similarity gates), and the two-brain confidence decay could all consume calibrated probabilities instead of raw sigmoid outputs — with the sync boundary untouched (raw scalars stay raw; calibration is a local monotone transform, still (0,1)-bounded, still sigmoid-not-softmax).

## 6. Consumer Reframe (riir-clippy, priority #2)

- The healer's selection math (`select_best_candidate` = `W_EVO·evolution + W_RATE·reliability`, ρ hand-pinned — vocab.md §6/Le Critique lineage) has an **already-firing outcome stream** (`EvolveRecorder::record_outcome`). The Issue-810 calibrator is exactly the primitive that would data-fit those hand-pinned constants from outcomes — a follow-on consumer after the base primitive proves G1.
- "Overseer rubric layer" (HN's strongest use-case): maps to our existing `llmexec_guard`/`VerifyBudgetGate` — no new substrate needed.
- Workflow-eval idea: score-bench already beats it (real clippy oracle vs reference-agreement). Record only.

## 7. Fusion

**Paper × Plan 340 conformal floor × Bench-706 Brier-vs-floor × ActionBridge ABSTAIN → `CalibratedSigmoidGate`.**
A generic katgpt-core primitive: record `(sigmoid_output, outcome)` pairs per direction; refit temperature+bias (2-param convex fit — track-b, no base-weight mutation, BLAKE3-frozen + freeze/thaw-versioned like any snapshot); emit calibrated p + keep ABSTAIN. Consumers: ActionBridge confidence, affect scalars, CLR verifier (already ECE-gated — becomes the first calibrated consumer), later riir-clippy blend weights. Ranking preserved iff temperature > 0 — gate it. GOAT gate must beat (a) uncalibrated baseline on decision-level ECE/Brier and (b) the Bench-706-style sigmoid floor, per the Report-the-Floor rule (Research 322).

## 8. Verdict

**Tiers:**

| Tier | Criteria | This paper |
|---|---|---|
| Super-GOAT | — | **No**: calibration of classifier outputs is a mature field (Platt 1999, Guo 2017); in-workspace the fusion is novel, class-level it is not. Q1 fails. |
| GOAT | — | Not directly: the source ships no measurable technique we can port (closed model, no math). |
| **Gain** | ✓ | **Actionable calibration gap + validated architecture + negative lessons (abstain, composite calibration) → files.** |
| Pass | — | — |

**One-line reasoning:** a product announcement with every component pre-published and no extractable math, but it prices a real gap in our stack (sigmoid confidence everywhere, calibrated nowhere except CLR) and hands us the eval vocabulary to gate it.

**MOAT gate:** `katgpt-rs` — base-primitive fit (sigmoid mechanics + calibration), force-multiplier ≥ 2 pillars (ActionBridge/NPC decisions, CLR, HLA scalars, later riir-clippy selection) → **open primitive, Issue 810, feature-flag + bench before any promotion**. `riir-ai` — consumer only (affect scalars + ABSTAIN already ship). `riir-train` — recorded row, no plan (audited discard above). `riir-clippy` — follow-on consumer (outcome-fitted blend weights).

**Files:** katgpt-rs `.issues/810_calibrated_sigmoid_gate_poc.md` (poc/proof task). No plan until the PoC proves the gain.

**Reopen triggers:** Jev architecture paper or independent replication with numbers (the hours-later Qwen-2.5-1B-RLCD clone is the one to watch); any plan that trains a decision head (→ RLCR arXiv:2507.16806 as the recipe source); if decision-level calibration proves GOAT, promote primitive and wire riir-clippy's `W_EVO/W_RATE` fit as consumer #2.
