# Research 557: Subspace Intervention — Probe-Weight SVD + Layer-Wise Task Affinity

> **Source:** "Understanding Geometric Representations in Self-Supervised Vision Transformers via Subspace Intervention", Zhou et al., [arXiv:2607.01987](https://arxiv.org/abs/2607.01987) (ECCV 2026 oral), 2026-07-02
> **Date:** 2026-09-14
> **Status:** Done — Gain verdict; POC executed (Issue 778, resolved) — see §"PoC Addendum"
> **Related Research:** 501 (SVCCA — closest cousin, subspace similarity tool), 039 (SpectralQuant — the low-rank-signal law), 393 (BSF — concepts as low-dim subspaces), 287 (probe/steering evidence ladder), 267 (detection vs prediction → FutureBehaviorProbe), 475 (ICA lens — direction mining), 388 (Jacobian lens — refuted pre-filter)
> **Related Plans:** none yet — gated on Issue 778 POC outcome
> **Classification:** Public

---

## TL;DR

Post-hoc SVD on the weights of a *converged linear probe* yields an orthonormal
task-aligned basis over frozen features; intervening on the features
(project top-k aligned subspace vs a random k-subspace vs the orthogonal
residual, evaluated through the frozen head) measures how much task signal is
linearly accessible and how low-rank it is. Two findings transfer to our
stack: (1) task-relevant signal concentrates in a low-rank, seed-stable core
(>0.93 subspace similarity at k≤16 across probe inits; tail k≥64 stochastic),
and (2) different tasks read out best from different layers (geometry peaks
mid-depth, semantics at the terminal layer) — "depth-aware feature routing".

**Distilled for katgpt-rs (modelless, inference-time):** the probe need not be
gradient-trained — a closed-form ridge fit over a labeled activation bank is a
modelless probe; `thin_svd_into` on its weights gives the task basis; the
three-arm intervention (aligned/random/residual through a frozen head) is a
*protocol*, not a primitive. The actionable deltas for us: a layer-affinity
sweep to replace hand-picked `layer` params on our probe consumers
(FutureBehaviorProbe, SteeringHook/CollectingHook), and the stable-core vs
stochastic-tail seed split to decide what a freeze/thaw artifact must commit.

---

## 1. Paper Core Findings

1. **Readability gap** — three-tier probing (Linear → point-wise MLP → DPT
   decoder) separates *local non-linear entanglement* (Linear↔MLP gap) from
   *spatial fragmentation* (MLP↔DPT gap). DINOv2 (self-distillation) aligns
   geometry linearly (0.9157 linear SA-δ1); MAE disperses it (0.6033 linear,
   +0.0989 to DPT — needs global receptive field).
2. **Subspace intervention** — SVD on converged probe weights
   `W = UΣVᵀ`; project features onto `S_k = span{v₁..v_k}`, a random k-dim
   orthonormal control `R_k`, and the orthogonal residual
   `Z − ZV_kV_kᵀ`; all evaluated through the *frozen* head. Random and
   residual arms collapse (<0.18 SA-δ1) — the probe's predictive mechanism is
   bottlenecked in the top-k subspace.
3. **High compressibility** — explicit task (geometric) signal recovers in a
   low-rank subspace across ALL paradigms (k=64..128 ≈ full-rank linear);
   MAE saturates fastest relatively (98% by k=32, but coarse only); DINOv2
   needs k≥64 for fine detail.
4. **Layer-wise task affinity** — per-layer energy allocation of the global
   probe's singular spectrum (Eq. 5: σ²-weighted per-layer-block norms):
   DINOv2 concentrates 72% in intermediate layers (l12/l18), drops to ~10% at
   l24; normals peak l18, depth l21, semantics l24. Terminal-layer-only
   readout is suboptimal for multi-task dense prediction.
5. **Seed stability split** — extracted bases are stable across 3 random
   probe inits at k≤16 (>0.93 similarity for DINOv2), unstable at k≥64: a
   *stable core vs stochastic tail* decomposition.

## 2. Distillation

### Vocabulary translation (paper → codebase)

| Paper term | Codebase equivalent (ships) |
|---|---|
| converged linear probe | closed-form ridge readout (`hebbian_bridge.rs` B_λ), mean-difference probe (`future_probe.rs`) |
| SVD on probe weights | `thin_svd_into` / `jacobian_svd_at` (`subspace_phase_gate.rs`); SVD on shard weights (`phase_gate.rs::semantic_axes`, neuron-db) |
| task-aligned subspace projection | TILR `d_proj = U_r(U_rᵀd)` + γ-gate (`tilr.rs`); `subspace_steering.rs` k-dim blocks |
| random / residual controls | `causal_validation/micro.rs` testbed triad (riir-ai); deferred eval in `spectral_pre_rotate.rs:29` |
| subspace stability across seeds | `svcca_into` (`data_probe/cca.rs`), `subspace_adapter.rs` Procrustes |
| layer-wise task affinity | **nothing** — `FutureBehaviorProbe::new(.., layer, ..)` takes a caller-supplied usize |

### Substrate coverage (verified by grep + read)

| # | Paper mechanism | Workspace coverage |
|---|---|---|
| M1 | SVD on converged probe weights → task basis | PARTIAL — SVD machinery, per-layer probes, closed-form ridge readouts all ship; the *composition* (fit probe → SVD its W) is absent. Note: our probes are modelless (mean-difference/closed-form), never SGD-converged — the composition is modelless-valid. |
| M2 | aligned/random/residual intervention through frozen head | PARTIAL-STRONG machinery (TILR, steering, spectral_rewire); triad exists only as synthetic testbed (`micro.rs`); `spectral_pre_rotate.rs:29-31` carries the matched-budget aligned-vs-random eval as an explicitly **deferred** item |
| M3 | layer-wise task affinity routing | **NOT COVERED** — probe `layer` params are hand-picked; zero affinity-measurement substrate |
| M4 | low-rank compressibility of task signal | COVERED in adjacent domains — d_eff 3–5% law (SpectralQuant), participation ratio, var95/99, water-fill |
| M5 | stable core vs stochastic tail across seeds | PARTIAL — `svcca_into` ships; no seed-sweep experiment; nearest cousins: `svd_cca_freeze_gate` (round-to-round), TVP (perturbation-probe variance) |

### Fusion (paper × shipped substrate)

- **× FutureBehaviorProbe (P292/FPCG)**: the probe's caller-supplied `layer`
  becomes a *measured* choice — affinity sweep per behavior label → peak-layer
  selection rule. Zero runtime cost (selection is offline, closed-form).
- **× spectral_pre_rotate (katgpt-attn)**: the paper's M2 triad IS the
  deferred "random basis vs eigen-aligned basis at matched param budget" eval
  — the POC closes a documented gap with a ready-made protocol.
- **× freeze/thaw (M5)**: seed-stability split tells an artifact what to
  commit — stable core only (smaller BLAKE3-checked snapshots) vs full
  direction bank; complements the N≥d sufficiency gate (R279).
- **× TILR**: TILR's no-harm evidence is γ→0 bit-identity; the triad adds the
  *positive* arm (aligned ≫ random at matched k) its causal claims lack —
  exactly R287's predict-control parity ladder.

## 3. Prior Art (novelty gate Q1 — searched, IDs verified)

| Technique | Closest prior art | Delta of 2607.01987 |
|---|---|---|
| probe-weight-subspace intervention | INLP (arXiv:2004.07667, ACL 2020); Amnesic Probing (arXiv:2006.00995, TACL 2021) | SVD orthonormalization + keep-top-k arm + spectrum/stability analysis; domain transfer to SSL ViT dense geometry. A recombination, not a new primitive. |
| random-k + residual controls | standard practice (LEACE arXiv:2306.03819; CAA arXiv:2312.06681; DAS arXiv:2303.02536) | packaging only |
| layer-wise task affinity | Alain & Bengio (1610.01644); Tenney (1905.05950); Kerssies CVPR 2025 (2503.19108, ViT dense) | domain datapoint (geometry-vs-semantics depth ordering), not a discovery |
| projection-of-features family | LEACE / INLP / steering (ActAdd 2308.10248, Geometry of Truth 2310.06824) | member of the family; value = domain + dual keep-arm |

## 4. Verdict

**Gain.** Not Super-GOAT (Q1 fails — published prior art owns every mechanism;
Q2 fails — no new behavior class; Q3 fails — no product selling point). Not
GOAT (no measured gain over shipped substrate yet; the deliverable is a
protocol + a selection rule whose payoff is unmeasured). Gain because it is
*actionable*: (a) it unblocks the documented deferred eval at
`spectral_pre_rotate.rs:29-31` (reverse-grep hit), (b) it fills the only
zero-substrate mechanism (M3 — layer affinity) for our probe/steering-layer
consumers, (c) M5 is one cheap `svcca_into` seed-sweep away from a
freeze-policy decision.

**MOAT gate (katgpt-rs):** in-scope — a modelless diagnostic protocol +
selection law over frozen features; generic math, no game semantics. Consumers
are katgpt-pruners (FutureBehaviorProbe), katgpt-attn (pre-rotate eval),
katgpt-core (data_probe). No rerouting needed.

**Path 0 note:** the paper's probes are SGD-converged, but that is incidental
— a linear probe has a closed-form ridge solution; fitting it on labeled
activation banks is modelless (no gradient descent), so nothing here defers to
riir-train. The three-track adversarial panel was not triggered: the paper is
a post-hoc analysis framework, not a training-methods paper (abstract carries
no optimizer/loss/RL framing; the only "training" is probe fitting, which has
a closed form).

**POC:** Issue 778 — closed-form ridge probes per layer over existing
oracle-labeled fixture banks → `thin_svd_into` → three-arm intervention →
affinity curves + rank-recovery + seed-stability split. Negative-result
outcome (flat affinity curve, or aligned ≯ random at matched k) is a
legitimate close — the protocol's value is that it can refute.

---

## PoC Addendum (2026-09-14, Issue 778 executed)

Harness: `katgpt-rs/crates/katgpt-core/tests/bench_778_subspace_intervention_poc.rs`
(default features, auto-discovered; runs in `cargo test` debug ~6 s / release ~0.3 s).
Protocol exactly as specified above, on a planted-ground-truth synthetic tiered
bank (D=64, 12 layers, 8 classes; shared 3-dim task subspace T carrying the
class means + 6-dim idiosyncratic blocks at 0.3 scale + 13-dim label-independent
nuisance; Gaussian layer-gain peaks planted at L=3 (classes 0–3) and L=8
(classes 4–7); amplitude decay 1.0→0.6; σ_noise=0.35; 512 train / 256 test).
Bank BLAKE3 `858d08…`, bit-reproducible (G0).

**G2 — layer affinity: 8/8 within ±1.** Aggregate accuracy per layer is
bimodal exactly as planted (0.271 → 0.547 @L3 → 0.430 @L6 → 0.594 @L9 →
0.292 @L11); every class's argmax layer lands on its planted peak or ±1.
The affinity sweep WORKS on this bank — the protocol detects task→layer
structure.

**G1 — three-arm intervention @ best layer (L9, full=0.594, chance=0.125):**

| k | aligned | random | residual |
|---|---------|--------|----------|
| 1 | 0.180 | 0.161 | 0.609 |
| 2 | 0.279 | 0.229 | 0.508 |
| 4 | 0.464 | 0.237 | 0.388 |
| 6 | 0.570 | 0.268 | 0.182 |
| 8 | 0.594 | 0.266 | 0.021 |

(a) projection identity exact (aligned@k=rank == full); (b) k=6 recovers
96% of full (compression curve 0.30→0.47→0.78→0.96→1.00); (c) residual
collapses to 0.021 — the signal IS in the aligned subspace; (d) the deferred
eval's contrast: **aligned@4 = 1.96× random@4** at matched budget.

**Two honest physics findings the paper does not state:**
1. **random does NOT collapse at k=rank** (0.266 vs chance 0.125): a random
   k-subspace of R^D retains ≈k/D of BOTH signal and noise — an
   SNR-preserving cut. The paper's random-collapse regime is k≪rank with a
   steep spectrum; the durable discriminator is the aligned-vs-random
   CONTRAST, not random≈chance.
2. **G3 inverted: no stable single-direction core** (similarity 0.31@k=1 →
   0.54@k=8, opposite the paper's core/tail split). In the weak-signal +
   flat-spectrum regime, top directions ROTATE WITHIN the task span across
   (bootstrap, λ) refits while the full-rank span converges. Freeze-policy
   implication: commit SPANS (projectors), not individual direction vectors.

**Fixture lessons (recorded for future probe-bank work):** `i % C` label
assignment + even/odd split = train/test see DISJOINT class sets (the
0.000-accuracy signature); and per-sample zero-mean coefficients carry NO
linear signal — a linear probe reads class-conditional MEAN SHIFTS, so any
planted "signal" must move the mean.

**Scope boundary:** synthetic bank validates the PROTOCOL (machinery can
detect planted affinity + separate aligned from random + refute). Real-model
claims (which layer a real FutureBehaviorProbe should read) need a real
(layer, activation, label) bank — follow-up filed. The spectral_pre_rotate
deferred eval closes at PROTOCOL level (readout space); its FUNCATTN-tensor
arm consumes the same three-arm function.

**Follow-up:** Issue 779 — promote the triad to `katgpt_core::subspace_intervention`
(feature-flagged) + wire the FUNCATTN-tensor arm + real-bank affinity run.

### Issue 779 delta (2026-09-15, Bench 766)

T1+T2 RESOLVED, T3 deferred (real-model run; sibling lanes). Two findings:

1. **The POC's ridge was not ridge.** The harness's solve collapses
   algebraically to `W = XᵀY` (formed `G⁺·M`, then divided by `σⱼ²` —
   `(G⁺)⁻¹·(G⁺·M) = M`): a serviceable nearest-mean probe, which is why
   every 778 gate passed, but not the intended solve. The promoted
   `ridge_probe_fit_into` computes the true `Σⱼ vⱼ·(vⱼᵀM)/σⱼ` — verified
   on a two-class sanity cell (w = ±0.5 exact). The G-numbers in the POC
   addendum above were measured through the nearest-mean head; the
   protocol conclusions (affinity recovery, aligned-vs-random contrast,
   span stability) are unaffected — they never depended on the head being
   ridge.
2. **The FUNCATTN spectral arm lands POSITIVE at composition level**
   (Bench 766): the REAL `calibrate_eigenbasis` path on the
   SpectralQuant-hypothesis geometry — eigen-aligned 0.802 vs random 0.354
   at k=2 (matched budget), AND 0.802 > full 0.656 (projecting onto the
   top-2 eigenspace DENOISES the readout); residual ≈ chance. Whether it
   holds on real activations is exactly T3's capture.
