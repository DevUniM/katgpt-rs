# Research 558: Singular Learning Theory — RLCT λ + WBIC as a Selection Currency [L1-183]

**Status:** RECORD + LANDED — the Track-A half shipped as `katgpt_core::slt`, promoted default-on (`580bda30`, Bench 764 GOAT, 2026-09-15). The T0 novelty verdict on the §2.3 noise-sweep estimator: KEEP at application level (form = classical Hill estimator — caveat recorded in HISTORY §Issue 781); T4 estimator deferred. Track-C half = riir-train Plan 404 (unclaimed).

> **Source:** [Deep Learning is Singular, and That's Good](https://arxiv.org/abs/2010.11560) — Murfet, Wei, Gong, Li, Gell-Redman, Quella (U. Melbourne), arXiv:2010.11560, Oct 2020; IEEE TNNLS 34(12):10473–10486, Dec 2023
> **Date:** 2026-09-14
> **Status:** Done — GOAT-tier Gain (two-track: modelless selection primitive + riir-train diagnostic plan). NOT Super-GOAT (novelty gate §6: the math is published; the fusion applications are the open lanes).
> **Related Research:** 551 (BMR + EFE-over-models — the exact-evidence cousin over count models), 315 (scaling exponents — the paper's own future-work names unrealisable-DSL power laws), 238 (LoRA low-rank manifold — rank-selection consumer), 125 (weight norm ↔ Kolmogorov complexity — complexity-generalization cousin), 488 (effective-degree polynomial simplicity), 284 (simplicity bias sampler)
> **Related Plans:** 597 (BMR — shipped closed-form evidence), [riir-train Plan 404](../../../riir-train/.plans/404_llc_lambda_guided_selection.md) (LLC λ̂ diagnostic + λ-guided LoRA rank selection — the training-track half)
> **Related Issues:** 781 (this repo — `slt` selection primitive, feature-gated)
> **Classification:** Public (katgpt-rs — generic modelless selection math; consumer wiring stays private)

---

## TL;DR

Neural networks are **singular** statistical models: the set of true parameters `W₀ = {w : p(y|x,w) = q(y|x)}` is an analytic variety with singularities, the Fisher/Hessian is degenerate everywhere on it, and the Laplace approximation / BIC machinery built on "divide by the Hessian determinant" is invalid. Watanabe's singular learning theory replaces it with three laws, none of which contain a gradient:

1. **Free energy:** `E_n F(n) = n·S_n + λ·log n + o(log n)` — the complexity penalty is the **RLCT λ** (real log canonical threshold), not `d/2`.
2. **WBIC:** the correct singular-model selection criterion is `nL_n(w₀) + λ·log n` (Watanabe 2013) — BIC's `d/2` over-penalizes by exactly `(d/2 − λ)·log n`.
3. **Generalization:** `E_n G(n) = λ/n + o(1/n)` for the Bayes predictive distribution vs `C/n` (`C ≥ λ`, sup of a Gaussian process) for MAP/MLE — posterior averaging beats point estimates by `(C−λ)/n`.

λ has a **volume-codimension** interpretation: `V(t) = Vol{w near w₀ : K(w) < t} ∝ t^λ`, so `2λ` is the only geometrically meaningful count of effective parameters. The paper's headline measurement: a 21-parameter ReLU toy has λ ≈ 0.53 where regular theory says 10.5 — **an order of magnitude less effective complexity than parameter count**, which is *why* over-parameterized singular models can generalize.

**Distilled for this stack (the selection-currency frame):** every artifact-selection decision we currently make by raw loss (LoRA rank 16–32 hand-picked, checkpoint-by-val-loss, shard merge/keep in Raven/δ-Mem consolidation, freeze/thaw snapshot tie-breaks) is a singular-model selection problem being answered with the wrong criterion. Raw loss is monotone in capacity → always picks max capacity; BIC (`d/2`) over-penalizes by a measured amount; `WBIC = nL + λ·log n` has an interior optimum. The closed form for low-rank families (Aoyagi–Watanabe 2005) prices LoRA/dendritic ranks for free: **`λ(r) = r·(a+b−r)/2`** for rank-r factorization of an a×b matrix — full-rank limit recovers `ab/2 = d/2` exactly, monotone in r, so a WBIC interior optimum always exists.

Prior-art verdict (§4): the λ-estimation instrument class is **heavily published** (LLC/SGLD line, developmental interpretability) — no novelty there. Two gaps confirmed empty across targeted searches: **LoRA/adapter rank selection via λ** (unpublished) and **artifact/consolidation selection via WBIC** (unpublished). Those are our lanes.

---

## 1. Paper Core Findings

### 1.1 The three laws (operator form)

| Law | Formula | What it prices |
|---|---|---|
| Free energy | `F_n ≈ nL_n(w₀) + λ·log n − (m−1)·loglog n` | which model/artifact is cheapest given the data |
| Temperature scaling | `E_βw[nL_n] = nL_n(w₀) + λ/β + U_n·√(λ/2β) + O_p(1)` | λ is a **slope** in 1/β — measurable by tempered sampling (this is the estimator, Watanabe 2013 Thm 4 / paper's Algorithm 1) |
| Generalization | `E_n G(n) = λ/n` (Bayes) vs `C/n, C ≥ λ` (MAP/MLE) | the value of averaging over point snapshots |

### 1.2 Why singular ≠ regular (the failure of classical counting)

- **Fisher degenerate everywhere on W₀** (paper Lemma 2): every ReLU-network true parameter is a degenerate critical point of K — the Hessian determinant is zero *at every point of the true set*, not just at measure-zero points. Laplace/saddle-point approximation is invalid **by construction**, not marginally. Paper's experiment: last-two-layers Laplace → `inf/NaN`; last-layer Laplace → learning coefficient ~1000–2000 (vs 0.8–9.7 for MCMC) — catastrophically wrong, three orders of magnitude.
- **λ depends on the (model, truth, prior) triplet**, not just (model, prior): simpler true distribution relative to the model → more singular W₀ → **lower λ**. Verified experimentally (paper Table 2: λ rises 0.526 → 0.556 as the truth gets more complex at fixed model). Consequence: **λ is a property of the trained artifact + its data, not of the architecture alone** — exactly what an artifact-selection currency needs.
- **λ ≤ d/2 always** (realisable case) — a free sanity ceiling for any estimator.

### 1.3 Reduced-rank regression — the closed-form anchor (paper A.2, Aoyagi–Watanabe 2005)

For `X ≈ BA` with `A ∈ R^{H×M}`, `B ∈ R^{N×H}`: `K(w) = ‖BA − B₀A₀‖²`, `W₀` is a smooth `H²`-dimensional graph over `GL(H)`, and the model is **minimally singular** — locally quadratic in `d′ = H·M` normal directions. The RLCT (Aoyagi–Watanabe 2005) for rank-r factorization of an a×b matrix:

```
λ(r) = r·(a + b − r) / 2
```

- `r = min(a,b)` ⇒ `λ = ab/2 = d/2` (regular limit, exact).
- `dλ/dr = (a+b−2r)/2 > 0` for `r < (a+b)/2` ⇒ WBIC always has an interior optimum in r (raw loss never does — it is monotone).
- This is **LoRA structure exactly** (`ΔW = AB^T`): the complexity of a rank-r adapter is priced by a one-line closed form.

### 1.4 Volume codimension `V(t) ∝ t^λ`

`d′ = 2·lim_{t→0} log(V(at)/V(t))/log(a)` — the effective-parameter count as a *volume exponent of the almost-true set*. This is the correct version of what `effective_rank`-style second-moment counters approximate (see signal-diff §2.2): the paper explicitly cites the eigenspectrum/effective-dimensionality line (Thomas et al. 2019, Maddox et al. 2020) as **inappropriate for singular models**.

### 1.5 Experiments (paper §5–6, small nets, NUTS/HMC)

- Last-layer(s) MCMC (being "Bayesian a little bit") beats MAP consistently; last-layer-only often beats last-two-layers (MCMC struggles with the singular setting).
- λ̂ estimation via 5-point 1/β regression around `β₀ = 1/log n`, R² ≥ 0.92 everywhere.
- ReLU non-analyticity is not fundamental (SiLU twin gives identical λ̂ within noise).

### 1.6 Future work the paper names (all now published — see §4)

SGD-as-posterior-sampling; RLCT estimation at scale; unrealisable truths ↔ neural scaling power laws.

---

## 2. Distillation

### 2.1 Vocabulary translation (paper → codebase)

| Paper term | Codebase equivalent | Ships? |
|---|---|---|
| learning coefficient / RLCT λ | — (no analog; closest: `effective_rank`, see 2.2) | No |
| WBIC `nL + λ log n` | selection scores: `best_belief_score` (Beta-LCB), BMR log-evidence (Plan 597) | No (cousins differ, 2.2) |
| effective number of parameters `2λ` | `effective_rank` (entropy of covariance eigenvalues, `data_probe/geometry.rs`) | Partial — wrong measure class (2.2) |
| tempered posterior / inverse temperature β | — | No |
| Bayes predictive vs MAP | freeze/thaw snapshot swap (point artifact) vs weighted mixture | Point-swap ships; WBIC-weighted mixture does not |
| phase transition (λ shift) | changepoint: `first_pit` kernel (`prover_selection.rs`) | Kernel ships; λ-series input does not |
| free energy `F = nL + λ log n` | cross-n shard comparability in Raven/δ-Mem consolidation | No (raw-loss/entropy heuristics today) |
| flat minima / Hessian eigenspectrum | (the critique, not the primitive) | — |

### 2.2 Signal-diff vs closest shipped cousins (§3.6 discipline)

| Cousin | Signal it consumes | Signal λ/WBIC consumes | Diff |
|---|---|---|---|
| `effective_rank` (`data_probe/geometry.rs`; neuron-db `spectral_flatness`) | second-moment **spectrum** of a weight/activation population | **volume exponent** of the KL-loss sublevel set around a trained point | at a singular point the covariance spectrum reads ≈ full rank (→ BIC's d/2) while λ ≪ d/2 (paper: 0.53 vs 10.5) — erank **over-counts exactly where selection matters**. The paper itself condemns this measure class (Thomas/Maddox citations). |
| BMR (Plan 597, Bench 715) | integer counts of a **conjugate table model**; exact log-evidence via lgamma/Beta ratios | real-valued losses + λ of a **parametric singular family**; asymptotic evidence | complementary families: BMR prices tables, WBIC prices manifolds. A freeze envelope could carry both (BMR for discrete parts, WBIC for continuous low-rank overlays). |
| `best_belief_score` (Beta-LCB) | r/f outcome evidence — penalizes **scarcity of evidence** (n) | λ — penalizes **capacity at fixed evidence** | orthogonal axes; composable (`LCB(win-rate) + λ·log n·scale` style combined scores are well-defined) |

### 2.3 The modelless λ̂ estimator (novelty TBD — flagged, not claimed)

The No-GD panel extraction: λ estimation does not require MCMC *in principle* — `E_β[nΔL] = λ/β` and `V(t) ∝ t^λ` are statements about **loss evaluations**, and a Gaussian-noise sweep on frozen weights with a near-zero CDF power-law fit (`λ̂ = m / Σⱼ ln(u_max/uⱼ)`, exponential-MLE under exact power law) is a forward-pass-only estimator. On LoRA/dendritic overlays the perturbation space is the low-dimensional overlay itself (`r·(a+b)` params, not the host model) — prod-viable at freeze time. **However: no dedicated prior-art check has been run on this estimator form** (known published routes: SGLD slope 2308.12108, exact algebraic 2608.20183 — 2-D models only, linear-response 2605.07970). Issue 781 T0 gates on that check before any GOAT claim; until then this is a **fusion idea, novelty TBD** per §1.5 discipline.

---

## 3. Path 0 decomposition — three-track panel merge

| # | Component | Analog ships? | Extractable without GD? | Route |
|---|---|---|---|---|
| 1 | WBIC score `nL + λ·log n` | No (2.2) | Yes — arithmetic given λ | katgpt-core `slt` (Issue 781 T1) |
| 2 | Closed-form `λ(r) = r(a+b−r)/2` | No | Yes — one line | katgpt-core `slt` (Issue 781 T1) |
| 3 | λ̂ via tempered sampling (SGLD) | No | **No** — sampling is GD-adjacent | riir-train Plan 404 Phase 0 |
| 4 | λ̂ via noise-sweep V(t) fit on frozen weights | No | Yes (claimed) | Issue 781 T0 — novelty-gated |
| 5 | `λ/n` gap predictor | No | Yes — arithmetic; **UQ-bearing → floor gate** | Issue 781 T3 |
| 6 | Bayes-vs-MAP `(C−λ)/n` → sigmoid WBIC-Elo mixture weights | Partial (`rating`/Elo ships; WBIC-diff input does not) | Yes | Issue 781 T1 + riir-ai consumer |
| 7 | λ-series phase detection | Partial (`first_pit` ships; λ-series does not) | Offline per-checkpoint | Plan 404 Phase 2 |
| 8 | Free-energy cross-n ledger for consolidation | No | Yes — arithmetic | riir-neuron-db consumer (post-GOAT) |

**Paths 1–3 checked (modelless unblock):** (1) freeze/thaw snapshot *correction* — N/A: WBIC selects among candidates, corrects no bias; (2) deterministically-constructed LoRA overlay — N/A: same, it is not a repair mechanism; (3) latent-space correction — N/A. All three fail *because this paper is a selection theory, not a correction theory* — its content decomposes into arithmetic (rows 1,2,5,6,8 — modelless-validable) and measurement (rows 3,4). Row 3 defers to Path 0.5 (Plan 404); row 4 is the potential modelless rescue of row 3, gated on its own prior-art check.

**Panel discards (auditable reasons, §3.5):**
- *riir-clippy regime detection on per-rule r/f series* — DISCARDED from filing: RLCT is defined on `K(w)` sublevel sets; heal-rate count trajectories carry no parametric `w`, so λ semantics do not transfer (mechanism-level kill, not a cost note). The `first_pit` kernel already serves that lane's changepoint needs.
- *SGLD-tempered final training stage* + *last-layer cached-feature Bayesian pass* + *λ-matched TernaryDraftModel capacity* — NOT discarded, sequenced: Plan 404 Phase 3 `- [-]` (each consumes Phase 0's λ̂ or Issue 781's closed form first).
- *BIC over-penalty report `(d/2−λ)·log n`* — folded into Issue 781 test expectations (not a standalone artifact).

---

## 4. Prior-art ledger (searches run 2026-09-14; IDs verified against arXiv)

**λ estimation (instrument class — NO novelty available):**
- LLC + SGLD estimator: Lau, Furman, Wang, Murfet, Wei, arXiv:2308.12108 (AISTATS 2025) — the canonical scalable λ̂; "Estimating the LLC at Scale" arXiv:2402.03698 was **withdrawn and merged into 2308.12108 v2** (cite the latter).
- Sampler benchmark: arXiv:2507.21449 (RMSProp-preconditioned SGLD best for local sampling).
- Exact algebraic λ (2-D models): arXiv:2608.20183. Linear-response estimators: arXiv:2605.07970. Modes/resolution: arXiv:2504.18048.

**Model selection via λ:** WBIC (Watanabe, JMLR 2013); sBIC (Drton & Plummer, arXiv:1309.0911, JRSS-B 2017); Liu 2025 refinement (Springer 10.1007/s42081-024-00262-1); Patterning (arXiv:2601.13548 — selects among *solutions* via data reweighting, not architectures). **No published architecture/rank-search-by-λ paper found.**

**Low-rank λ:** Aoyagi–Watanabe 2005 (Neural Networks 18(7):924–933, journal — the `λ(r)` closed form); Hayashi et al. arXiv:2303.09154 (layered linear nets RLCT); arXiv:2512.00686 (empirical λ scaling in low-rank linear nets/autoencoders). **No published LoRA-rank-selection-via-RLCT paper found — two targeted searches empty. Open lane.**

**Phases of learning:** arXiv:2402.02364 (stagewise development, TMLR 2025); arXiv:2410.02984 (rLLC, ICLR 2025 Spotlight); arXiv:2310.06301 (TMS k-gons — λ *determines* Bayesian phase transitions); arXiv:2501.17745 (transient ridge).

**SLT × LLM compression/intervention:** arXiv:2510.12077 (MDL meets SLT — LLC tracks Pythia compressibility under quantization/factorization); arXiv:2609.00699 (susceptibility data-reweighting debias on Gemma-2-9B reward models); arXiv:2509.26544 (BIF — SGLD stats at billions of params). **Gaps: no SLT pruning, distillation, or adapter-selection papers.**

---

## 5. Fusion

1. **λ(r) × LoRA-Muon (R238):** the gauge-invariant low-rank manifold work gives `ΔW = AB^T` arithmetic; `λ(r)` prices it. Rank selection by WBIC on top of gauge-rebalanced merges — the unpublished lane (§4). Consumer: riir-train Plan 404 Phase 1 (LoRA r ∈ {8,16,32,64} sweep), quest_grammar rank 16–32 hand-picked lane.
2. **WBIC × BMR (R551/Plan 597):** two evidence currencies — exact over count-tables, asymptotic over singular manifolds. Freeze envelope carries both; selection composes `BMR_evidence + λ·log n`.
3. **λ/n × best_belief_score:** capacity axis × evidence axis — a two-axis artifact scoreboard; consumers: freeze/thaw tie-break (riir-ai), Raven/δ-Mem merge/keep ranking across heterogeneous-n shards (riir-neuron-db — the free-energy ledger makes losses at different n commensurable, which raw loss never is).
4. **λ̂(t) × `first_pit`:** the changepoint kernel already ships; a per-checkpoint λ series turns Plan 404's diagnostic into a phase detector (freeze-candidate tagging: post-λ-drop checkpoints).
5. **Sigmoid WBIC-Elo (Bayes-vs-MAP law):** `(C−λ)/n` says averaging beats points — mixture weights `σ(−ΔWBIC/τ)` over frozen adapters via the shipped `rating` machinery (sigmoid-not-softmax compliant); a freeze/thaw upgrade from hard swap to weighted mixture.

**Game-context reframe (step 4a):** λ is a **freeze/consolidation-seam scalar, not a per-tick signal** — it must NOT be forced into the 20 Hz path or the sync boundary (nothing here crosses raw↔latent; it ranks artifacts offline). Player-visible consequences are second-order: personality-snapshot selection stability (fewer post-refreeze behavior regressions), crowd diversity via consolidation ranking, smaller/faster adapters at equal quality.

**Consumer reframe (step 4b, riir-clippy):** no principled mapping of λ onto rule corpora / fix-trajectory stores (see §3 discard — RLCT has no `w` there). The honest takeaway for the healer is the *anti-Laplace rule*: any plan reaching for Hessian/curvature machinery to predict generalization or select models is using the instrument this paper measured as catastrophically wrong (λ_est ~10³ vs true ~1) — route through WBIC/λ̂ instead.

---

## 6. Novelty gate (per track — TTPO discipline)

**Track A (modelless, katgpt-rs Issue 781):** Q1 prior art — **NO** at math level (λ(r) = Aoyagi–Watanabe 2005; WBIC = Watanabe 2013); YES at fusion level (rank/artifact selection via WBIC — unpublished). Q2 new behavior class — NO (selection quality, no new capability class). Q3 product selling point — marginal (internal quality lever). Q4 force multiplier — YES (freeze/thaw, consolidation, rank selection, distillation capacity). **1.5/4 → GOAT-tier Gain.** No Super-GOAT guide; issue + this note.

**Track C (model-based, riir-train Plan 404):** Q1 — the *application* (λ-guided LoRA rank selection) is unpublished, but the instrument (SGLD λ̂) is 2308.12108's published method — so this is a **consumer plan, not a primitive claim**. Q4 — YES (quest_grammar, Stage-3 rank, checkpoints, distillation capacity). GOAT-tier Gain → Plan 404. Serving-envelope note (TTPO): selection decisions run at training/freeze time (cold path); the modelless noise-sweep (Issue 781 T0), if it survives its prior-art check, is the runtime-track twin — Plan 404 is PRIMARY for λ̂ measurement until then.

---

## 7. GOAT gates

**Issue 781 (`slt` module):**
- G1: property tests — `r=min(a,b) ⇒ λ=ab/2`; λ(r) monotone in r; interior WBIC optimum exists. **Planted-rank recovery:** synthetic reduced-rank regression with known true rank r* — WBIC picks r*, raw loss picks r_max, BIC over-penalizes to r_min.
- G1 calibration targets (estimator half): quadratic bowl ⇒ λ̂ = d/2; planted RRR ⇒ λ̂ = r(a+b−r)/2; paper's ReLU toy (d=21) ⇒ λ̂ ≈ 0.53 (reproducing the paper's headline number is the strongest evidence the estimator sees singularity, not parameter count).
- G2: selection O(k); noise-sweep batched into fused forward passes.
- G3: no-regression — existing `best_belief_score` lanes untouched.
- G4: alloc-free, zero-alloc hot paths, scratch-buffer reuse.
- **UQ floor rule (λ/n predictor):** must beat `d/2n` (BIC's own gap prediction — the floor *is* the incumbent theory) and constant-gap baselines on CRPS / coverage / Winkler across synthetic families + real checkpoints. Cannot beat the floor ⇒ gate FAILS.

**Plan 404 (riir-train):** G1 λ̂ recovers closed-form λ on oracle cells (full-rank k/2; RRR r(d+D−r)/2) within CI; G2 WBIC-selected rank ≥ val-loss-selected rank on held-out at strictly smaller rank; G3 deterministic replay (seeded noise, bit-identical); G4 probe tax ≤ 5–20% depending on phase. GPU-hours: Phase 0 6–10 h, Phase 1 10–14 h, Phase 2 3–6 h on the 4090 (≈ one Bench-335 optimizer arm each).

---

## 8. Sources

- Primary: arXiv:2010.11560 (full text via r.jina.ai, 2026-09-14).
- Aoyagi & Watanabe 2005, Neural Networks 18(7):924–933 (reduced-rank λ closed form).
- Watanabe 2013, JMLR 14:867–897 (WBIC); Watanabe 2009 (SLT textbook).
- Prior-art IDs as in §4 (verified by search agent against arXiv listings, 2026-09-14).
