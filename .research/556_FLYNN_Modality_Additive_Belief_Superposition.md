# Research 556: FLYNN — Modality-Additive Belief States & the Ablation-Superposition Diagnostic

> **Source:** [FLYNN: Robust Neural Network for Robot Navigation using Fly Brain Topology](https://arxiv.org/abs/2607.00025) — Benquan Wang & Jingdao Chen, Mississippi State Univ., arXiv:2607.00025v2 (2026-07-13). Code: github.com/ben-gitdev/fly-gym.
> **Date:** 2026-09-14
> **Status:** Done — Issue 777 executed same-day: T1–T4 COMPLETE, GOAT ALL PASS, `modality_additive` PROMOTED to katgpt-sense default (§7 addendum)
> **Related Research:** riir-ai 379 (fly-connectome wave survey → `lif_graph`), katgpt-rs 242 (recurrent-belief kernel taxonomy), 435 (temporal derivative kernel), 448 (latent error diffusion — negative), riir-neuron-db 304 (Hopfield super-GOAT + the AttractorKernel G2.1 blocker), 553 (flybody locomotion)
> **Related Plans:** none yet — Issue 777 gates any plan
> **Classification:** Public

---

## TL;DR

FLYNN wires an RNN directly from the full Drosophila connectome (139,255 neurons, 99.97% sparse, leaky-integrator cells with per-neuron-class rates) and trains it with plain DAgger imitation to parity with EfficientNet-B0/MobileNet-v3 on vision-based navigation. The headline is NOT the parity — it is that FLYNN survives **total vision loss with 44.3% success having NEVER seen dropout in training**, while baselines explicitly trained with camera-dropout collapse (3.9%–16.5%), and a Watts-Strogatz small-world control matched on degree/sparsity/path-lengths ALSO collapses (2.6%). The mechanism evidence: PCA of internal states shows **linear superposition per sensory modality** — the blind→full-vision transition vector equals blind→left + blind→right (cosine 0.9998; the small-world control: 0.9439). Each modality's information stream stays an independent, linearly-separable component of the recurrent state, so ablation subtracts cleanly instead of disrupting the navigation manifold.

**Distilled for katgpt-rs (modelless, inference-time):** two things, both zero-training — (1) an **ablation-superposition cosine diagnostic** for ANY recurrent belief kernel (measure whether state-transition deltas under modality subsets add linearly); (2) a **modality-additive kernel design constraint** (per-modality channels must enter the recurrence without cross-modality normalization). Our shipped `evolve_belief` fuses the 6 `SenseKind` channels via divisive normalization — `delta_i = (lr·t_min/total)·(k_{m[i]} − 0.5·total)`, `total = Σ all kinds` — so per-modality contributions are **provably not separable**: ablating one kind rescales every other modality's effective gain. The gap is real, measurable, and fixable behind a feature flag.

---

## 1. Paper Core Findings

- **Architecture.** Full FAFB v783 connectome as a sparse 139,255×139,255 weight matrix (5.34M edges, ≥5-synapse threshold). Leaky-integrator recurrence `h_{t+1} = α⊙h_t + (1−α)⊙tanh(W·h_t + x_t + b)` with **per-neuron-class leak rates** `α_c(i)`. Sensors map to biological entry points (vision → L1/L2/L3 with temporal filtering matched to L-cell roles; target angle → Johnston's Organ; collision → head bristles); motor read from descending neurons via a small MLP. Depth is emergent (temporal propagation through midbrain), not layered.
- **Training.** Standard DAgger imitation: VFH* planner teacher with privileged state → PID → wheel commands; 4 iterations, teacher-student mixing 1.0 → decreasing; Adam on MSE. Nothing novel in the loop.
- **Parity.** Checkerboard env, full vision: FLYNN 92.9% success / SPL 0.83 vs EfficientNet 90.3/0.80, MobileNet 91.6/0.81, SmallWorldNet 89.0/0.80 (~5M params each).
- **OOD (realistic textures, never trained on).** FLYNN **42.1%** vs EfficientNet 17.2%, MobileNet 0.0%, SmallWorldNet 3.2%. Baselines lose collision-recovery behavior and stall; FLYNN keeps it (higher collision counts = more recovery attempts, not worse navigation).
- **Vision loss (in-distribution env).** One eye: all models degrade similarly — but EfficientNet/MobileNet needed dropout training for this; FLYNN + SmallWorldNet got it spontaneously. **Total blindness: FLYNN 44.3%** vs EfficientNet 3.9% (dropout-trained!), MobileNet 16.5%, SmallWorldNet 2.6%. FLYNN falls back to wind + collision cues and keeps collision-recovery; every other model stalls after first collision.
- **The mechanism evidence.** PCA(10 PCs, 89.1% var) + KDE of internal states per vision condition: FLYNN forms distinct, tight clusters; `vec(B→F) ≈ vec(B→L) + vec(B→R)` with cosine **0.9998** and |B→F|=11.16 vs |B→L + B→R|=11.11. SmallWorldNet (matched substrate, RNN/leaky cells, small-world, degree, sensory→descending path-length statistics — differs ONLY in wiring): cosine 0.9439, magnitudes 22.88 vs 30.01, broad overlapping KDE clouds. **The specific connectome wiring, not small-worldness, produces modality-additive state.**
- **Honest caveats (paper's own).** PCA/KDE analysis is correlational-geometric, not causal; OOD test is visual-texture-shift only; L1/L2 temporal filtering is manually implemented (connectome-incomplete) and may carry part of the OOD result — but the total-blindness result removes the visual pathway entirely and the robustness persists, which is the cleaner attribution to architecture.

## 2. Distillation

### 2.1 The transferable primitive (modelless)

**P1 — Ablation-superposition cosine (the diagnostic).** For a recurrent belief kernel with per-modality input channels: fix an input stream; for every subset S of modalities, run to steady state and record the state-transition delta `Δ(S) = h(S) − h(∅)`. The kernel is *modality-additive* iff `Δ(full) ≈ Σ_m Δ({m})`, scored by cosine similarity + magnitude ratio. Zero training, closed-form, runs at runtime as a deployment health probe (a per-NPC "am I degrading linearly?" check), or as a G2-style gate on new kernel families. FLYNN's protocol is this over PCA projections; on our 8-dim beliefs we can run it directly, no PCA needed.

**P2 — Modality-additive kernel constraint (the design rule).** Per-modality channels must enter the recurrence without cross-modality terms: each modality m contributes `c_m(x_m)` and the state evolves on `Σ_m c_m(x_m)` — no divisive normalization by the modality sum, no subtractive centering on the sum. Then removing modality m subtracts exactly `c_m` from the drive — graceful degradation is structural, not trained-in.

**What is NOT claimable:** the phenomenon (features as linear directions — Elhage 2022 superposition; ActAdd/directional ablation — Turner 2023; mixed selectivity — Posani; shared input subspaces — Tafazoli 2024), no-retraining graceful degradation as an outcome (Thuruthel 2019, redundancy-based), connectome-as-sparse-mask (established genre), modularity→robustness as a finding (QA-index on ANNs exists). See the fence table in §3.

### 2.2 Signal-diff vs shipped cousins (§3.6 discipline — mechanism-level, not name-level)

| Shipped cousin | Core formula / signal consumed | Diff vs FLYNN property |
|---|---|---|
| `katgpt-sense` `ReconstructionState::evolve_belief` (reconstruction.rs:891) | `delta_i = (lr·t_min/total)·(k_{m[i]} − 0.5·total)`, `total = Σ all 6 kinds`; `KIND_MAP=[0..5,0,1]` wrap; ±max_delta and [−1,1] clamps | **Divisive normalization + subtractive centering over the modality SUM**: every dim's delta depends on all modalities. Ablating one kind rescales every remaining modality's effective gain (`1/total` grows) — compensation-by-recalibration, NOT linear subtraction. Clamps add piecewise non-linearity. Predicted superposition cosine: far from 1. **Not covered — this is the gap.** |
| `katgpt-micro-belief` `LeakyIntegrator` (leaky.rs:51) | `delta = scale·(x − ½·total)`, clamped; zero input = strict no-op (no α⊙h decay) | Same divisive shape; also lacks FLYNN's retention term α⊙h_t (belief never decays toward rest). Partial substrate for an additive variant. |
| `micro-belief` `AttractorKernel` (attractor.rs:54) | `s_t = 2σ(W_s·s + W_x·x + b) − 1` | RNN-shaped but σ non-linearity + dense W (no per-dim retention, no per-class rates). R304 records its G2.1 failure (569 belief-flips vs LeakyIntegrator's 1) — exactly the chaotic non-additive response P1 would have caught pre-deployment. |
| `GenericSpatialBelief::decay_confidence` (riir-games-shared spatial.rs:100) | `sigmoid(−λ·Δt + 4.6)` — single modality (vision), TIME-decay of confidence, belief never deleted | Complementary axis: handles *staleness over time*, not *modality-set ablation*. The two compose (see fusion). |
| `latent_functor::apply_functor` (riir-ai arithmetic/mod.rs:455) | `out = source + functor` latent vector add (subtraction = negate) | The arithmetic a "subtract modality m's contribution" op composes from — but nothing decomposes belief per modality today. |
| `katgpt-attn` `g2_ablation_parity_smoke` (salience_tri_gate_bench.rs:210) | delegate-disabled gate must be bit-identical on sub-decisions | The reusable bench PATTERN (ablation parity harness) — different assertion (bit-identity vs cosine additivity). |
| `katgpt-core` `lif_graph` (Issue 763, Bench 760) | LIF reservoir + **`maslov_sneppen` degree-preserving rewiring control** | Ships FLYNN's control condition! The WS-control dissociation method (matched-topology random wiring fails the property) is one rewiring away from measurable on our own reservoir. |

**Verdict: modality-additive decomposition + the superposition diagnostic ship NOWHERE in the workspace** (grep-clean across 16 repos, both vocabularies; mechanism-verified on the primary kernel above).

### 2.3 Fusion (paper × in-house substrate)

1. **P1 × R242 kernel taxonomy × R304 attractor blocker** → *additivity as a first-class G2-style gate for every new belief-kernel family.* R304's standing blocker (AttractorKernel random-init = 569 belief-flips, unusable) is precisely an unmeasured non-additivity/chaos failure; P1 run over the kernel families would have flagged it before the G2.1 bench burned a plan. The diagnostic hardens the existing kernel-selection pipeline.
2. **P2 × two-brain SpatialBelief × fog-of-war (riir-ai)** → *multi-modal think-brain.* Current think-brain handles ONE modality (vision→position belief, sigmoid time-decay). FLYNN generalizes: vision + sound + social channels as separable contributions; when darkness/fog kills vision, the sound/social components survive intact and VERIFIABLY (cosine check at runtime). NPC "senses" stop being all-or-nothing.
3. **FLYNN's control method × `lif_graph`'s `maslov_sneppen`** → the WS-dissociation experiment is runnable TODAY on shipped substrate: does connectome-shaped wiring (even synthetic shape-class, per R379's licensing constraint) beat its own degree-preserving rewire on the superposition cosine? Nobody has measured that in-house.
4. **(Secondary, healer lane)** `NonergodicFilter` (katgpt-micro-belief; consumed by riir-clippy `nonergodic_driver`) is itself a belief kernel — a P1-style ablation diagnostic over its generator arms, and channel-ablation on the retrieval fan-out (BM25 vs KNN lanes), are the healer-surface manifestations. Recorded as ideas only; no plan — the healer's belief states are not per-tick sensory and the fit is real but thin.

## 3. Verdict

**Tier: Gain** (GOAT-eligible pending the Issue-777 measurement — if the current kernel fails P1 as predicted AND the additive variant measurably improves blinded-belief quality at equal full-input behavior, re-gate as GOAT and promote per feature-flag discipline).

**One-line reasoning:** the paper's *phenomenon* is published prior art and its *controller result* is FLYNN's own — but the distilled instruments (P1 diagnostic + P2 constraint) fill a verified in-house gap (grep-clean, mechanism-diffed) on our highest-frequency substrate, the per-NPC belief kernel, at zero training cost.

**Novelty gate scoring (honest):**
- **Q1 no prior art?** Mechanism-level: NO — killed (superposition hypothesis, ActAdd, mixed selectivity, shared subspaces). Application-level (ablation-delta additivity as a runtime/gate diagnostic on recurrent belief kernels): no direct published match found; in-house: zero hits. Partial.
- **Q2 new behavior class?** In-stack YES (modality-ablation substrate is CLEAN — nothing today degrades per-modality except implicit zero-input freezing). World: no.
- **Q3 product selling point?** Plausible: "NPCs that keep their heads when blinded — measured graceful degradation, not dropout-training luck" (darkness zones, blindness effects, stealth, sensory-deprivation mechanics).
- **Q4 force multiplier?** YES: sense + micro-belief + lif_graph + two-brain SpatialBelief + latent_functor arithmetic.

Not all 4 → **not Super-GOAT**. No guide doc, no riir-ai plan yet — Issue 777 gates.

**Prior-art fence (do not cross these when wording claims):**

| Claim shape | Status | Killing art |
|---|---|---|
| "Modalities contribute linearly-separable components to latent state" | ❌ published | Elhage 2022; Turner 2023 (ActAdd); Posani (mixed selectivity); Tafazoli 2024 |
| "Graceful degradation without retraining" as outcome | ❌ published | Thuruthel 2019 (Science Robotics, redundancy-based); missing-modality literature (prompts/TTA) |
| Connectome/bio-graph as sparse training mask | ❌ genre | Zahn 2022; Lappalainen 2024; Balwani 2025; flyGNN |
| "Modularity causes robustness" | ❌ published | Hod et al. (QA-index on ANNs); bioRxiv 2025 |
| **Ablation-superposition cosine on belief-state transition vectors as a runtime/gate diagnostic** | ✅ survives (application-level) | none found |
| **Matched-topology rewiring control attributing additivity to wiring** | ✅ survives (method-level; FLYNN's own control) | FLYNN is the art — position as replication on our substrate |

**MOAT gate:** katgpt-rs = fundamental/base primitive via fusion — P1/P2 are generic math + kernel design rules on `katgpt-sense`/`katgpt-micro-belief`, no game semantics → **in scope**. Game wiring (multi-modal think-brain) is riir-ai's, noted as downstream consumer. Healer fusions stay ideas until a surface is read in depth.

## 4. Three-track decomposition (Path 0)

| Paper component | Extractable without GD? | In-house analog |
|---|---|---|
| Leaky-integrator recurrence | yes (shipped math) | `leaky_core::leaky_step`, `LeakyIntegrator`, HLA `LeakyIntegrator` default |
| Per-class leak rates α | yes (config constants) | partial: emotion differential decay (anger λ, fear 2λ); dual fast/slow EMA (R435) |
| Per-modality input channels | yes (shipped) | `SenseKind`×6 → `kind_activations` |
| Connectome wiring W | n/a — data, not math | **Out**: FlyWire/MaleCNS licensing (R379); shape-class synthetic ships (`lif_graph`, `mb_value`) |
| Linear-superposition property | yes — design constraint | **MISSING** (divisive normalization) |
| Superposition diagnostic | yes — closed-form | **MISSING** |
| DAgger training loop | — training track | ships: riir-train `dagger_lora` + `game_smt_teacher` (Plan 254) |

**Training-track verdict: DISCARD (auditable reason).** The DAgger loop is standard and already ships in riir-train; the connectome data itself is unlicensable (R379); everything of value for us — property, diagnostic, design constraint, control method — is modelless. No riir-train plan.

## 5. Reframes (both mandatory)

**Game-context:** a blindness spell / darkness zone / stealth state is a MODALITY ABLATION event. Today our NPC belief either freezes (zero-input no-op) or gets divisively rescaled (compensation lottery). With P2, losing vision subtracts vision's component cleanly — the NPC keeps navigating on sound/social cues with *measured* (cosine-verified) degradation instead of chaotic belief drift; per-modality sensory effects become a designer-reliable mechanic rather than a fragility.

**Consumer-context (healer, priority #2):** the healer's belief-shaped surfaces are `NonergodicFilter`'s strategy posterior and the retrieval fan-out's channels — P1 generalizes to "does the ranking/posterior degrade linearly when one channel is masked?", a plausible OOD-health probe for `--frontier-report`-style instrumentation. Thin fit; recorded, not planned.

## 6. Next

- ~~Issue 777~~ RESOLVED 2026-09-14 (see §7).
- riir-ai multi-modal think-brain guide: only on demonstrated consumer need; file there when picked up.

## 7. T1–T4 measurement addendum (2026-09-14, same-session PoC)

**Landed in commit `7e2a2638`** (+ the docs commit carrying this addendum);
HISTORY.md entry: “Issue 777 … resolved in `7e2a2638`”.

The defend-wrong PoC ran in the same session (bench `modality_superposition_bench` +
`katgpt-sense/tests/modality_additive_superposition.rs`). It **defended the core
claim and refuted two of this note's own predictions** — recorded here per the
§3.6 discipline (raw numbers, both axes):

| kernel | cos(Δ_full, ΣΔ_single) | ratio |Σ|/|full| | worst-pair | T3 predictability |
|---|---|---|---|---|
| sense `evolve_belief` (divisive) | 0.9737 | **5.17** | 0.9256 | **3.03** |
| `LeakyIntegrator` (divisive) | 1.0000 | **3.00** | 1.0000 | — |
| `AttractorKernel` ×3 seeds | 0.9999–1.0 | 1.004–1.018 | ≥0.9999 | — |
| **`evolve_belief_additive` (T2)** | **1.0000** | **1.0000** | **1.0000** | **0.000000** |

**Correction 1 — the failure is magnitude-flavored.** §2.2 predicted "cosine
far from 1" / the issue predicted "≈ −1": measured cos is 0.97–1.00 — the
`−0.5·total` centering keeps directions roughly aligned while stacking 6× in
Σ-singles, so the RATIO (5.17 ≈ N_KINDS·0.86) is the load-bearing failure
metric. **A cosine-only gate false-passes both divisive kernels.** P1's
instrument definition is amended: cosine AND magnitude ratio, both.

**Correction 2 — `AttractorKernel` PASSES P1** (ratio 1.004–1.018) in the
near-linear regime (σ≈linear at origin, `W_x·x` linear pre-activation).
The §2.3 fusion-1 claim "P1 would have caught R304's 569-flip failure" is
**REFUTED** — additivity and stability are different axes; R304's flip problem
would not show in this protocol. P1 is a necessary-but-not-sufficient kernel
gate; it pairs WITH the existing G2.1 flip-stability bench, never replaces it.

**T2 outcome** — `evolve_belief_additive` (per-kind drive `2σ(η·k)−1`, 6 sigmoid
calls + KIND_MAP gather; per-kind retention `belief_retention`, default 0.9;
`additive_drive_scale` η = 4.0): EXACT superposition (max|Δdim| = 0.0000),
silent kinds decay as α^t (gradual forget), argmax stable 0/31, predictability
err 0. **GOAT ALL PASS**: G1 exact additivity; G2 26.8 ns/tick @ D=8 ≤ 50 ns
budget (comparative number reported, not gated — the first draft's 2×
comparative gate was ill-posed for a COEXISTING method and re-scoped per the
Issue-777 record); G3 default path byte-identical (pinned test + suite green
at default / no-default / all-features / core re-export); G4 alloc-free by
construction. **PROMOTED to katgpt-sense `default`** (modelless gain; README /
examples feature counts synced 599→601 / 200→201; docs gate 17/17).

Measurement-hygiene notes that cost two bench iterations: (a) LLVM
 dead-code-eliminates an unsink'd timing loop (measured 0.0 ns/tick —
 `black_box` sink required); (b) single-run Instant on a ~20 ns kernel flips
 run-to-run under load (best-of-5 min stabilized it); (c) T must be
 pre-saturation for the divisive kernels or everything clamps to ±1 and the
 measurement goes degenerate.
