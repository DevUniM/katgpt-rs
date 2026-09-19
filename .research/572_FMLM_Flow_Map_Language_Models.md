# Research 572: Flow Map Language Models (FMLM)

> **Source:** "Flow Map Language Models: One-step Language Modeling via Continuous Denoising" — Lee, Yoo, Agarwal, Shah, Huang, Raghunathan, Hong, Boffi, Kim (KAIST/CMU/MIT). [arXiv:2602.16813](https://arxiv.org/abs/2602.16813) v3, Feb–May 2026. Code: github.com/david3684/flm.
> **Date:** 2026-09-19
> **Status:** DONE — Gain (two modelless POCs filed: Issues 852, 853; training recipes routed: riir-train Issue 563). Heavy family saturation: no Super-GOAT (Q1 fails — flow maps for one-step generation are 2022–2025 prior art; one-step *text* predates this paper by 8 months).
> **Related Research:** 044 (ELF — the competing continuous DLM, already distilled + landed), 366 (Self-Cond FMLM fixed-point flows — the *follow-up* paper; its "~95% of inference surface already ships" verdict governs this family), 341-family (D2F discrete diffusion), 271 (MIT 6.S184 vocab crosswalk), 382 (Spherical Steering — covers FMRG's ∇r=d case), 445 (iMAUVE interpolation geometry).
> **Related Plans (riir-train):** 395 (Looped Flows recipe arm — its self-distillation pseudotargets are FMLM's measured-losing arm), 411 (DBTM — its JVP transport loss is the Eulerian/149.13 arm), 068 (D2F `GpuD2fDistill` — soft-target TODO is the landing slot for ELF+PD), 411 Phase 3 Sudoku arm.
> **Classification:** Public (generic math) / riir-train (recipes).

---

## TL;DR

FMLM builds a continuous flow over **raw one-hot token embeddings** (unconstrained Euclidean, no simplex projection), trains the denoiser with **cross-entropy on a softmax output** (the Bayes-posterior minimizer, Lemma 3.1), and proves the resulting flow admits a **unique learnable flow map** that discrete state spaces cannot have (Prop 3.5: finite-set pushforwards cannot hit arbitrary target distributions — elementary measure argument). Distilled one-step generation: LM1B 119.34 Gen PPL (baselines 293–5743 at 1 step), OWT 168.30. Autoguidance halves Gen PPL (96.91→51.62) with stability to η=100 where discrete baselines collapse at η≥10.

**For this stack the paper is ~90% covered by prior family distills (044/366/riir-train 452+395+411).** The residual deltas that survive coverage:

1. **Semigroup distillation beats both arms our open plans chose** — FMLM's own ablation: semigroup-KL 119.34 vs Eulerian-JVP 149.13 (unstable, needs L×|V| Jacobian) vs Lagrangian 193.08; teacher-composed 119 vs self-distilled 159. Plan 395 uses self-distillation pseudotargets; Plan 411 uses finite-difference JVP transport. → riir-train Issue 563.
2. **τ(t) decoding-error-linearized schedule** — measured-P_e LUT time warp, the single highest-leverage ablation in the paper (149.18→106.98 at |V|≈50k, no retraining). Our `ScheduleKind` family (Uniform/LogitNormal/EquiProb) has no data-adaptive member. → Issue 852.
3. **Autoguidance** (weak-variant extrapolation, inference-only) — unshipped; our ternary-draft/full pair and RecFM's dual-dropout training are ready-made weak/strong pairs. → Issue 853 (+ riir-train Issue 563 free-rider arm).
4. **CE-vs-MSE on simplex targets** — `masked_softmax_mse` incumbents in riir-bench-algo are exactly FMLM's measured-losing arm (129.04 vs 96.91). → riir-train Issue 563.

**Verdict: Gain** (four filed actionables). Not Super-GOAT: one-step-by-learned-flow-map = prior art (Rectified Flow 2209.03003 → Consistency Models 2303.01469 → CTM 2310.06742 → Flow Map Matching 2406.07507 → MeanFlow 2505.13447 → Shortcut 2410.12557); one-step text = DLM-One 2506.00290 (continuous) and DCD 2506.10892 (discrete), both May–Jun 2025; flow maps for language = a **concurrent trio** (Categorical Flow Maps 2602.12233, FMLM 2602.16813, Discrete Flow Maps 2604.09784). The note exists to (a) record the family coverage map, (b) route the four deltas, (c) prevent re-evaluation.

---

## 1. Paper core (what matters for us)

### 1.1 The formulation in five lines

- Interpolant `I_t = (1−t)x₀ + t·x₁`, x₀ ~ N(0,I), x₁ one-hot. Unconstrained Euclidean R^{L×|V|}; **no simplex projection** (beats SSD-LM/TESS/Riemannian RDLM on all metrics).
- **Denoiser = posterior** (Lemma 3.1): optimal `D_t(x)_l = p(token_l | I_t = x)` — parameterize with tokenwise **softmax + cross-entropy**, recover velocity by exact affine map `b_t(x) = (D_t(x) − x)/(1−t)`.
- **Two-time denoiser** `δ_{s,t}(x) = x + (1−s)·v_{s,t}(x)`: always simplex-valued (weighted average of denoisers along the trajectory), diagonal `δ_{t,t} = D_t`, and satisfies the **semigroup condition as a convex combination on the simplex**: `δ_{s,t} = γ·δ_{s,u} + (1−γ)·δ_{u,t}(X_{s,u}(x))`, `γ = (1−t)(u−s)/((1−u)(t−s))`.
- **Flow map** `X_{s,t}(x) = ((1−t)/(1−s))x + ((t−s)/(1−s))δ_{s,t}(x)` — one evaluation transports between arbitrary time pairs.
- **Prop 3.5 (impossibility):** on a finite set S, no deterministic `f: S→S` pushes μ onto arbitrary ν (attained probabilities live in `{0} ∪ [μ_min, 1]`). Discrete diffusion's few-step factorized transitions are therefore structurally incapable of one-step transport; continuous flows are not. **Design law for our D2F line: discrete few-step quality walls are mathematical, not tuning gaps — the SDE noise in `elf_sde` and verify-then-resample in spec-decode are load-bearing closures, not hacks.**

### 1.2 Why CE, not MSE (the ablation our training tree should read)

LM1B 1024-step Gen PPL: velocity+MSE **3801** (rank-broken, |V|≫d full-rank Gaussian target), denoiser+MSE **129.04**, denoiser+softmax+MSE 120.16, denoiser+softmax+CE **96.91**. Same ordering on the flow-map side (156.83/181.72/**119.34**). CE decomposes as irreducible entropy + KL-to-posterior (Prop 3.2), giving the unique minimizer + a Wasserstein guarantee `W₂ ≤ C(ξ)√Δ_D + r_ξ`.

### 1.3 The three distillation choices (semigroup won)

| Objective | Mechanism | 1-step LM1B |
|---|---|---|
| **Semigroup** | teacher `δ̄ = sg(γ·δ̂_{s,u}(I_s) + (1−γ)·δ̂_{u,t}(X̂_{s,u}(I_s)))`; pure KL, **no derivatives** | **119.34** |
| Eulerian (MeanFlow-family) | needs spatial Jacobian through full L×|V| state; "highly unstable" | 149.13 |
| Lagrangian (TVM-family) | time-derivative + off-simplex evaluation | 193.08 |

Plus: distillation-from-teacher **119** vs direct/self-distillation **159** — a ~25% class gap, directly relevant to Plan 395's self-distillation pseudotargets.

### 1.4 Closed-form inventory (training-free math, for the record)

- All inter-object conversions b↔D↔δ↔X (affine, zero-alloc); general interpolant form in Lemma C.8.
- **τ(t) reparameterization**: `τ(t) = 1 − (|V|/(|V|−1))·P_e(t)`, P_e = per-token decoding error rate; 1000-point LUT (Gauss-Hermite + cubic spline); critical at |V|≈50k (149.18→106.98).
- Semigroup γ weights (midpoint form `γ = (1−t)/(2−s−t)`).
- Autoguidance: `b_guided = b_weak + η(b − b_weak)`, weak = dropout-0.1 same net; continuous stable to η=50–100, **discrete baselines collapse at η≥10** (logit-space extrapolation amplifies factorization artifacts).
- FMRG: `x_{t+1} = X_{t,1}(x_t) + λ∇r(X_{t,1}(x_t))` — differentiable one-evaluation look-ahead; reward trains on clean data only.
- Pinsker/Gronwall error bounds (given measured excess risk).

### 1.5 Headline numbers

179M DiT (RoPE, AdaLN, softcapping). Many-step: FLM 96.91/62.23 (LM1B/OWT) beats Duo 98.14/77.69, MDLM 109.21/105.15. 1-step: 119.34/168.30 vs baselines 293–5743. 2-step 110.19/133.29, 4-step 98.76/111.31. Autoguidance 96.91→**51.62** (η=50). Sudoku: 1-step validity 9.38% (all baselines 0.00%), conditional 39.84%, rejection sampling **≈7.6× faster than 81-step AR**. Clean monotone scaling 179M→870M (75.57→65.94→61.59). Cost: ~30% time/memory over embedding-diffusion (full |V|×d forward each step). No claims at 27B scale.

---

## 2. Family coverage map (why this is 90% pre-distilled)

| FMLM content | Covered by | Evidence |
|---|---|---|
| Iterated refinement / fixed-point inference surface | R366 §2.1: `LoopMode::WeightShared` (Plan 108, GOAT 8/8), `LoopMode::TrainingFree` (Plan 136, GOAT 4/4), `is_converged` halt (Plan 085), `self_cond_draft` (Plan 222) | "~95% of the inference surface is already shipped" — R366 TL;DR |
| Two-time denoiser + semigroup **as training recipe** | R366 §1.4 (routed to riir-train); consumed by R452/Plan 395, Plan 411 | recipes live there — but the **semigroup-beats-Eulerian/self-distill ablation postdates those choices** (the delta this note files) |
| Continuous-DLM modelless extras (SDE injection, logit-normal) | R044 (ELF) — landed, default-on: `elf_sde`, `ScheduleKind::LogitNormal` | GOAT checklist all `[x]` |
| One-step draft + verify + resample | DDTree/speculative decode architecture | verify-then-resample IS our spec-decode |
| FMRG with dot-product reward | Bridge pattern (x + λ·d), zone-attention preference vectors, R382 slerp steering | ∇r = d collapses to the shipped pattern |
| Self-conditioning | Plan 222 `self_cond_draft` + R366 | fixed-point view fully covered |

**PASS-Redirects (synthesis):** Lee, Yoo et al. [arXiv:2602.16813 "Flow Map Language Models: One-step Language Modeling via Continuous Denoising"] — family pre-covered by R044/R366; residual semigroup/τ/autoguidance/CE deltas filed (Issues 852, 853; riir-train 563); Prop 3.5 recorded as D2F design law.

---

## 3. Path 0 inventory — panel verdicts (three-track adversarial panel, 2026-09-19)

| # | Mechanism | Track | Verdict | Destination |
|---|---|---|---|---|
| 1 | τ(t) P_e-LUT schedule | modelless | **FILED** — measurement→frozen-LUT, conformal standing; `ScheduleKind` has no data-adaptive member | Issue 852 |
| 2 | Autoguidance extrapolation | modelless (+train free-rider) | **FILED** — arithmetic on two existing forwards; ternary-draft pair + RecFM dual-dropout are ready-made weak/strong pairs | Issue 853 + riir-train 563 arm |
| 3 | b↔D↔δ↔X algebra module | modelless | **DISCARD (conditional)** — becomes load-bearing only when two of {b,D,δ,X} coexist as separate objects; every shipped path has a single denoiser output and inlines the one conversion it uses. Reopen condition: Plan 395/411 landing a two-time object in the stack | — |
| 4 | Semigroup γ weights alone | modelless | **DISCARD (conditional)** — consumes δ objects absent from the stack; same reopen condition as #3 | — |
| 5 | FMRG look-ahead reward gradient | modelless | **COVERED** — ∇r=d case is the shipped bridge pattern (x + λ·d, zone attention, R382); learned-reward case drags autodiff out of envelope | — |
| 6 | W₂/Pinsker certification metric | modelless | **DISCARD** — certification slot owned by the conformal floor machinery (Plan 340); our G1 gates are exact-match/count-based, no live gate demands distributional distance | — |
| 7 | Prop 3.5 impossibility | theorem | **ADOPT as documentation** — zero FLOPs; cite in D2F/`elf_sde` module docs on next touch (discrete few-step walls are structural; SDE noise + verify-resample are the closures) | doc touch, no issue |
| 8 | Rejection-sampling with 1-step proposals | modelless | **COVERED** — IS speculative decode; quest_grammar drafter+pruner is the same shape | — |
| 9 | Semigroup-KL recipe (vs self-distill/JVP) | model-based | **FILED** — beats Plan 395's pseudotarget arm (119 vs 159 class) and Plan 411's JVP arm (119.34 vs 149.13) with NO Jacobian | riir-train 563 |
| 10 | ELF+PD progressive distillation (v2 App B) | model-based | **FILED** — lands in Plan 068's checked-in soft-target TODO; x̃ = z_t + (1−t)/(r−t)(z_r−z_t); 2×-token-budget schedule beats one-shot 12× | riir-train 563 |
| 11 | CE-vs-MSE on simplex targets | model-based | **FILED** — `masked_softmax_mse` incumbents are the measured-losing arm (129 vs 97); NCA retrofit row | riir-train 563 |
| 12 | Muon LR 2e-3 ablation (ELF v2) | model-based | **NOTED, no new issue** — published backing for the parked riir-train Issue 525 T2 A/B (`lora_muon` implemented, unwired); referenced from 563 | riir-train 563 refs |

Discard audit trail: #3/#4 mechanism-level — the algebra only pays when two distinct flow objects coexist; #5 — the closed-form-reward special case is literally the shipped pattern, the general case violates the envelope; #6 — the Report-the-Floor rule's slot is taken and no gate asks for W₂.

---

## 4. Fusion (paper × our substrate)

**Autoguidance × RecFM dual-dropout consistency (novel combination, novelty TBD→Issue 853):** RecFM trains the student to be consistent across two dropout scales (`p` vs `p·α`). A net trained that way has a *meaningful* dropout-on forward — exactly the dropout-0.1 weak variant autoguidance needs. Nobody has connected dual-dropout consistency training to a free inference-time guidance dial: `ŷ = ŷ_dropout + w·(ŷ_clean − ŝ_dropout)`, w>1, zero extra training, w swept by the existing `bench_elf_omega_sweep` harness. The katgpt-rs twin: DDTree's verify step already holds (full-model, ternary-draft) pairs in memory — the (b − b_weak) residual is free.

**Semigroup-KL as the JVP-free transport loss (Plan 411 fusion):** DBTM's `L_transport` regresses T onto `sg(T + İ·∇T)` via finite-difference JVP — the Eulerian family FMLM measured at 149.13 vs 119.34, flagged unstable through the L×|V| state. The semigroup form deletes the JVP cost center while improving the target number, and Plan 411 already schedules `L_semi` late — this supplies its exact winning form.

**τ(t) as the measured member of the `ScheduleKind` family:** logit-normal (ELF) and EquiProb (DiffusionBlocks) are guessed parametric shapes; τ(t) is the first whose shape comes from the model's own measured decoding-error curve — a calibration artifact in conformal standing, BLAKE3-committable as a Pod.

---

## 5. Prior-art verdict (Q1: NO — heavy published landscape)

- General one-step/few-step flow maps: Rectified Flow (2209.03003, Sep 2022), Progressive Distillation (2211.01015), Consistency Models (2303.01469), CTM (2310.06742), DMD (2311.18828), Flow Map Matching (2406.07507, Boffi — FMLM co-author), MeanFlow (2505.13447, Geng/…/He — ELF senior author), Shortcut (2410.12557), Boffi self-distillation taxonomy (2505.18825).
- One-step **text**: DLM-One (2506.00290, May 30 2025, continuous, ~2000× step speedup); DCD (2506.10892, discrete). Both predate FMLM v1 by 8 months.
- Flow maps for language: **concurrent trio** — Categorical Flow Maps (2602.12233), FMLM (2602.16813), Discrete Flow Maps (2604.09784). Follow-ups: Self-Cond FMLM (2607.00714 = our R366), Posterior Refinement (any-order flow maps).
- FMLM's defensible novelty (per the panel read): CE-on-simplex training of the flow map directly + the continuous-formulation-enables-flow-map argument (Prop 3.5) + the semigroup/Eulerian/Lagrangian comparison. All mechanism-level established; combination-level novel at publication time.

Autoguidance lineage (for Issue 853 honesty): image-diffusion autoguidance (2024–25); AR contrastive decoding (Li et al. 2022, logits = (1+α)expert − α·amateur) is the logit-space twin — our katgpt-rs arm on logits is an **adoption** of established technique, not a novelty claim; the dual-dropout-recfm latent arm is the fusion candidate.

CFG-for-text prior art: Schiff et al. 2412.10173 (discrete CFG, NeurIPS 2024), A-CFG 2505.20199, MeanFlow's integrated CFG — ELF's contribution is the continuous-embedding adaptation, mechanism not new.

---

## 6. Routing

- **Issue 852** (katgpt-rs): `ScheduleKind::DecodingErrorLut` POC — τ(t) measured schedule, GOAT vs Uniform/LogitNormal/EquiProb at matched step budget.
- **Issue 853** (katgpt-rs): autoguidance/residual-extrapolation POC — (a) logit-space adoption via ternary-draft pair on DDTree (contrastive-decoding prior art, unshipped here), (b) latent-space dual-dropout RecFM arm (fusion, routes with riir-train 563).
- **riir-train Issue 563**: semigroup-KL delta for Plans 395/411; ELF+PD target for Plan 068 soft-target TODO; CE-vs-MSE swaps; Muon backing note.
- Prop 3.5: cite from D2F/`elf_sde` module docs on next touch (no standalone task).
