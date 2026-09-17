# Research 563: Discrete Beckmann Transport Models — One-Step Language, the t\* Commitment Law, and Confidence-Commit Refinement

> **Source:** Tang & Wang, "Discrete Beckmann Transport Models for One-Step Language Modeling and Reasoning" [arXiv:2609.15903](https://arxiv.org/abs/2609.15903) (v2, 15 Sep 2026; UPenn/Harvard/Kempner/IAIFI). Code: github.com/sophtang/DBTM.
> **Date:** 2026-09-16
> **Status:** Active — **Gain, dual-track** (TTPO rule: one verdict per track). Modelless track → [Issue 811](../HISTORY.md) — **PoC COMPLETE 2026-09-16: T4 PASS** on steps/termination at quality parity → upgrade planned as [Plan 600](../.plans/600_flashar_confidence_commit_upgrade.md). **Ordering-axis verdict 2026-09-17 ([Bench 809](../.benchmarks/809_set_causal_order_sweep.md)): the §4.3 confidence-ordered reveal hypothesis MEASURED GREEN on real text** — under the masked-target set-causal objective, prob-t\* wins the reveal-order table on both eval seeds (2.59/2.61 nats vs uniform 2.89/2.88); the clean-token cells are self-copy trivial (residual-stream leak, Issue 816 resolved same day by the denoiser trainer). Training track → [riir-train Plan 411](../../riir-train/.plans/411_dbtm_autonomous_map_arm.md) (the no-distill arm on the Plan-395 successor lane, owner-gated). NOT Super-GOAT (Q1–Q3 NO — see §3).
> **Related Research:** 468 (BTM continuous predecessor — the divergence constraint, PoC'd FAIL on CCE / superseded by transition-kernel), 366 (Self-Conditioned FMLM fixed-point flows — ~95% of the inference surface shipped), 485 (UGC certified reveal schedules — **its Caveat #1 is this note's modelless gap**), 316 (DSpark confidence-scheduled spec decode), 445 (MeanFlow / latent thought flows), 271 (MIT crosswalk — flow-map class rows)
> **Related Plans:** 569 (TransitionKernelCce — the measured winner over Beckmann for CCE), 166 (FlashAR anchor-then-fill — the strided-anchor consumer), 381 (schedule sweep GOAT bench), 116 (DiffusionSampler adaptive confidence), 108/222/258/291 (fixed-point/self-cond/warm-start shipped surface)
> **Cross-ref (riir-train):** Research 452 (Looped Flows — the direct sibling recipe, same Sudoku bench family, same Plan-387 diagnosis), Plan 395 (OPEN owner-gated sibling arm), Plan 387 (the negative both papers diagnose)
> **Classification:** Public (katgpt-rs)

---

## TL;DR

DBTM is the **discrete/simplex instantiation of Beckmann Transport Models** (Research 468's paper, same group — Tang is on both) applied to language: a time-independent (autonomous) velocity field on the token simplex whose one-step transport map lands on one-hot vertices, trained **without teacher distillation** by minimizing a conservation-equation residual, with generation = **iterate one idempotent map + confidence-commit refinement** instead of ODE integration. Beats distilled discrete-diffusion/flow-map baselines at 1–4 NFE on OWT/LM1B; Sudoku-hard 97.5% at 16 NFE.

**For the stack, the headline mechanisms are ~all covered**: the divergence constraint was already PoC'd and **lost** to the transition-kernel form for our CCE consumer (Issue 573 FAIL → Issue 574 PASS → Plan 569); the fixed-point/autonomous-map inference surface ships (Research 366: `LoopMode::WeightShared`, `is_converged`, RCD/3SR warm-start); the refinement class is published (FMLM+ posterior refinement) and ships in parts (DSpark, DiffusionSampler, FlashAR anchor-then-fill). **Two deltas survive with documented gap evidence**: (1) the **confidence-commit rule (threshold κ ∪ floor ⌈|R|/(k−r+1)⌉)** — UGC's own Caveat #1 excludes confidence-threshold reveal from its KL certificate, and FlashAR's anchor selection is *strided* (positional), not confidence-adaptive; (2) the **closed-form commitment-time law t\* = 1−(1+σ√(2 log V))^(−1/a)** (REM-derived) — a new formula in the `IgnitionSchedule` timing-law family, consumable as an anchor/schedule constant where UGC must *estimate* its schedule from data. Training track: DBTM is a **cheaper, no-time-conditioning competitor to Looped Flows (452/395)** for the same slot.

---

## 1. Paper Core Findings

### 1.1 Autonomous flow on the simplex (§3, §9.2)

Velocity `b(x) = E_{t,x0,x1}[İ_t | I_t = x]` — the flow-matching velocity **time-averaged over the interpolant** (Prop 3.1). Satisfies the **divergence condition** `∇·(νb) = μ0 − μ1` where `ν(x) = ∫ μ_t(x) dt` is the occupation measure and `j = νb` the current — the Beckmann OT flux constraint (identical to Research 468's core equation; DEC `codifferential` is our operator).

### 1.2 One-step map + conservation equation (§3.2, §10.6)

`T(x) := lim_{s→τ(x)} X_s(x) ∈ M1` (simplex vertices). **Idempotent** (semigroup `T∘k = T∘k′`); solves `b·∇T = 0` off the manifold, `T = id` on it. A **partially trained** `T_θ` ≈ the flow truncated at finite time → generation = iterate `T_θ` until fixed point. Convergence theorem (Thm 3.1): absorption + finite hitting time `τ ≤ t_entry + 2r₁/κ₋` on the simplex; autonomous attractors = vertices ONLY (Prop 10.1), stationary across time (vs time-dependent flow's moving interior attractors).

### 1.3 Distillation-free training (§4)

Transport loss: regress `T_θ(I_t)` onto `sg(T_θ(I_t) + İ_t·∇T_θ(I_t))` (Euler step; needs a JVP — they fuse it in Triton). Boundary loss `T(x1)=x1`. **Anchor loss**: CE to `x1` only for `t > t_anchor`. Semigroup loss (late training). Total = L_transport + λ L_semi + λ L_bnd + λ L_anchor (+ refinement-in-loop terms §5.2).

### 1.4 Phase transition / commitment time (§4.3, Thm 4.1 — the REM law)

```
t* = 1 − (1 + σ·√(2 log V))^(−1/a)
```
from Random-Energy-Model analysis: the posterior over vertices is Gibbs at inverse temperature β(t); the argmax is correct iff the target's energy ρ² beats the max of V−1 competing Gaussians ≈ ρ√(2 log V). Anchoring **before** t\* → mode collapse; **after** → slower convergence (Table 12). Steering/transport effort is best concentrated on `[0, t*]`. Task constants: LM1B (V=30 522) t\*=0.82; Sudoku (V=12) t\*=0.69.

### 1.5 Attractor formation order (§10.1.2, Props 10.2–10.4)

Time-dependent attractors form **in order of target probability**: the dominant (argmax p) at t=0; attractor j at Lambert-W time `t_j/(1−t_j)² = −σ²W(−p_j/(p_l(1+m)e))`; **no non-dominant attractor forms before t=1/2** (σ=1). Verified in simulation to V=5000.

### 1.6 Refinement as test-time scaling (§5)

Partial-context interpolant (clean context set 𝒞, noised rest). **Commit rule** (Eq 26): per round r of budget k, commit `Δ𝒞_r = {ℓ: qℓ ≥ κ} ∪ top_{n_r}(q)` with floor `n_r = ⌈|R_r|/(k−r+1)⌉` — guarantees termination in exactly k NFEs (self-stopping). Renoise uncommitted positions, reapply the SAME map. Each NFE = **refinement of a full clean proposal**, not an ODE step. Quality head `q_φ` (BCE on argmax-correctness, zero extra NFE). Table 9: the one-step map **beats integrating the learned autonomous field with 64 Euler steps** — refine, don't integrate.

### 1.7 Results (§6)

OWT (linear-attention backbone, matched params): DBTM+ril lowest non-collapsed PPL at every NFE (65.2 @1 NFE vs FMLM 168.3); ril cuts 1-NFE PPL 58–65%. Sudoku hard: 99.9/99.4/97.5 @16 NFE vs FMLM+ 97.8/92.6/81.4 (+16.1 hard). GSM8K 16.8% @32 (AR still dominates 63.3%). Linear-attention backbone: gates conditioned on **state, not time**.

---

## 2. Distillation

### 2.1 Vocabulary translation (paper → codebase)

| Paper term | Codebase equivalent (shipped) | Where |
|---|---|---|
| autonomous flow / occupation measure | fixed-point flows (b⋆ autonomous) | Research 366 (FMLM★), `LoopMode::WeightShared` |
| conservation equation residual | `codifferential` / `belief_mass_divergence` | katgpt-dec (Plan 251/314); CCE consumer adjudicated |
| one-step map / flow map | depth-step shortcuts, `dflash_predict_*` | Plan 343, 490; `katgpt-speculative/dflash.rs` |
| commitment time t\* | `ignition_time(ζ, ε)` patience law | `katgpt-core/ignition_schedule` (Bench 666) |
| phase transition gate | `phase_transition_gate(N, d)` | `subspace_phase_gate` (Bench 301) |
| REM / √(2 log V) max-statistic | √(2 log n) growth damping | ASEntmax (Bench 713) |
| commit rule (κ ∪ floor) | confidence-scheduled decode; anchor-then-fill (STRIDED) | DSpark (R316), FlashAR (Plan 166), DiffusionSampler (Plan 116) |
| reveal/unmask schedule | `PositionOffsetSchedule` (ar/uniform/block-causal/mdlm) | `katgpt-core::set_diffusion_schedule` |
| refinement loop (renoise+remap) | RCD/3SR warm-start carry; `is_converged` halt | Plans 258/291/085 |

### 2.2 Signal-diff per mechanism (the §3.6 defense)

| Mechanism | Closest cousin | Signal the cousin consumes | Diff vs paper | Verdict |
|---|---|---|---|---|
| Divergence constraint `∇·(νb)=μ0−μ1` | `codifferential` + Issue 573 PoC | LP feasibility on state marginals | **Measured**: vacuous on connected graphs (all marginals transport-reachable); transition-kernel (Plan 569) won | **Covered + adjudicated** |
| Autonomous fixed-point map | Research 366 surface | iterate-until-converged, warm-start | DBTM adds simplex-vertex convergence proof; no new consumer | **Covered** |
| t\* commitment law | `IgnitionSchedule.ignition_time` = ln(1/ε)/ζ | capacity-free patience (ζ) | DBTM consumes **(V, σ, a)** — vocab-size/noise scaling, REM-derived; different signal, closed form, same family | **Family ships, formula new** |
| Commit rule κ ∪ floor | FlashAR `anchor_then_fill` | **stride** (positional), fixed | DBTM commits by **confidence/quality** (content) + floor → adaptive, termination-guaranteed; UGC Caveat #1 excludes confidence-greedy reveal from its certificate | **Delta — Issue 811** |
| Reveal schedule timing | UGC `equal_sqrt_mass_grid` | Monte-Carlo-estimated unmasking-gain curvature h′(t) | DBTM t\* is a 3-param closed form (free); UGC estimates from data; complementary (t\* as prior/init) | **Delta (secondary arm of 811)** |
| Refinement class (draft-all → self-correct) | FMLM+ (Agarwal 2606.24773, published) + DiffusionSampler | consistency-vs-context scoring | DBTM's floor + self-stopping + idempotent map are details on the published class | **Class covered** |
| REM attractor order | none (Lambert-W t_j unpublished in-stack) | — | per-token basin-availability prior (low-p tokens unsafe before t≥1/2) | Recorded, no consumer today |

### 2.3 Fusion (paper × shipped substrate)

1. **Confidence-commit × FlashAR × UGC (Issue 811)**: replace FlashAR's strided anchor selection with DBTM's `κ ∪ floor` rule over the denoiser's own max-softmax confidence (DiffusionSampler's signal, AUC 0.78); GOAT on the Plan-381 schedule-sweep bench + flashar's `reduces_steps` harness. UGC's certificate gap (confidence-greedy reveal) is exactly the cell this lights up — and UGC's estimated grid gives the *timing*, DBTM's rule the *selection*.
2. **t\* as a `PositionOffsetSchedule` constant**: a t\*-gated/probability-ordered reveal variant vs `uniform/ar/mdlm` in the existing sweep — the cheap closed-form sibling of UGC's estimated schedule, and the principled default for anchor timing.
3. **DBTM arm × Looped Flows arm (Plan 411)**: both recipes diagnose Plan 387's Bernoulli-blank corruption failure; DBTM needs NO time conditioning and NO recurrence (single map + conservation residual), Looped Flows needs the t-MLP but brings ARC results. Same slot, same bench family, owner-gated ordering.

### 2.4 Game-context reframe (step 4 — honest)

t\* as a per-NPC deliberation deadline (choice-set V, uncertainty σ): "commitment safety scales √(log V) — nearly flat in choice count" is an attractive per-entity law, but **Bench 712 / Issue 746 Row 1 CLOSED the anytime-commitment-schedule class for lack of consumer** (`CommittedFieldBlend` is sigmoid-weighted, no time grid; tf_loop is fixed-β). Recorded as **not actionable today**; reopens only if a time-grid consumer materializes.

### 2.5 Consumer reframe (healer, priority #2 — honest)

DBTM's refinement-in-loop ("train on the commit sets the sampler actually visits") maps to mining fix trajectories on on-policy multi-error states — **already shipped** as `corpus_gen::compose_multi_strided`, and the ordering question was **measured NEGATIVE** (Issue 093/099: every learned ordering regressed vs static min-delta; the Issue-100 signal fix won). No new healer plan.

### 2.6 Path 0 decomposition (§3.5 — two questions per component)

| Component | Ships? | Extractable without GD? | Note |
|---|---|---|---|
| Divergence condition | yes (`codifferential`) | yes (Issue 573 did) | measured vacuous for CCE |
| Autonomous map iteration | yes (366 surface) | yes | no new consumer |
| t\* law | family ships (`IgnitionSchedule`) | **yes — closed form** | Issue 811 arm 2 |
| Commit rule κ∪floor | partial (strided anchor) | **yes — consumes own softmax** | Issue 811 arm 1 |
| Conservation-residual training | no | no — requires GD through JVP | riir-train Plan 411 |
| Anchor/semigroup/ril losses | no | no | Plan 411 |
| Quality head q_φ | DiffusionSampler class | no (BCE-trained head) | class covered |

Paths 1–3 (freeze/thaw, deterministic LoRA, latent correction) do not apply to the training rows: the residual is a property of a *learned map's* Jacobian — no deterministic construction supplies it. Path 0.5 → Plan 411.

**Panel disclosure:** the adversarial panel (the skill's two advocate roles — No-GD extraction + model-based recipe) was consolidated coordinator-side in this session rather than spawned as independent subagents (the parallel `spawn_agent` batch was canceled by the user); the §2.2 table + discard reasons above are the consolidated output, and the independence a spawned panel would have provided is only partially mitigated by the measured-evidence citations per discard. Every discard cites the mechanism-level diff (measured Issue-573/574 for the divergence row; published FMLM+ + shipped DSpark/DiffusionSampler for the refinement row).

---

## 3. Verdict

**Dual-track (TTPO rule).**

- **Modelless track: Gain** (small). Ships + actionable improvement with a documented gap (UGC Caveat #1; FlashAR's fixed striding) → [Issue 811](../HISTORY.md), PoC-first per §3.6 (a quality claim needs a head-to-head on a trained mini-D2F, not architectural reasoning).
- **Training track: Gain** → [riir-train Plan 411](../../riir-train/.plans/411_dbtm_autonomous_map_arm.md) (Path 0.5; recipe + GPU-hours + GOAT gate vs NELBO/distilled/387 baselines; owner-gated like its sibling Plan 395).

**Not Super-GOAT** — Q1 NO (in-note prior art: 468/366/485/316 + published FMLM+/MeanFlow class); Q2 NO (better schedules/commit rules, not a new capability class); Q3 NO (no finishable product sentence); Q4 partial (connects dllm+UGC+FlashAR+spec lanes). Not GOAT (no measured gain yet — that is Issue 811's PoC).

**MOAT gate:** katgpt-rs in-scope (generic math on confidence/ordering — no game/chain/shard semantics); riir-train in-scope (active training moat, dLLM lane). No reroute needed.

---

## 4. Prior art (§4 searches, 2026-09-16)

- Commitment/speciation phase transitions in diffusion: published class — Raya & Lampinen (arXiv:2402.16991, hierarchical timescales), "Dynamical regimes of diffusion models" (Nature Comms 2024, speciation time tS), Ambrogioni 2025 / Yu & Huang 2025 (cited by the paper as the theory it builds on). **No prior closed-form t\*(V,σ,a) for the simplex found** — the formula is DBTM's contribution; the class is not ours to claim.
- Draft-all-then-self-correct: FMLM+ "Posterior Refinement" (Agarwal et al., arXiv:2606.24773) — the paper's own strongest baseline, one step earlier. DCD "Deferred Commitment Decoding" (arXiv:2601.02076) — training-free uncertainty-mitigating decode. Class covered.
- Distillation-free one-step discrete maps: the paper's own Table 3 (DFM needs distill/bootstrap; FMLM distilled; MeanFlow continuous). DBTM is the novelty here — we implement, not claim.

---

## 5. References

- Tang & Wang, arXiv:2609.15903v2 (this paper)
- Lee (Cheuk-Kit), Coeurdoux, Chen, Tang, Potaptchik, Du, Albergo, Vanden-Eijnden, arXiv:2608.01692 — Research 468 (author overlap verified against the arXiv v3 listing: Sophia Tang is 4th author here and first author of 2609.15903)
- Yoo et al., arXiv:2607.00714 — Research 366
- Wainwright, arXiv:2608.13520 — Research 485 (UGC)
- Agarwal et al., arXiv:2606.24773 — FMLM+ posterior refinement
- Suleymanzade et al., arXiv:2609.11801 — Research 452 (Looped Flows, riir-train)
