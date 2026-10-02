# Plan 617: Recurrent-Depth Contrast Guidance (LoopCD) for Looped Inference

**Date:** 2026-10-02
**Research:** [katgpt-rs/.research/602_LoopCD_Recurrent_Depth_Contrast_Guidance.md](../.research/602_LoopCD_Recurrent_Depth_Contrast_Guidance.md)
**Source paper:** [arXiv:2610.02185](https://arxiv.org/abs/2610.02185) — "Decoding Looped Transformers Better for (Almost) Free" (Apple); twin class prior art [arXiv:2609.24196](https://arxiv.org/abs/2609.24196) (EMNLP 2026)
**Target:** `katgpt-rs/src/transformer/loop_guidance.rs` (new module) + wiring in `src/transformer/variants.rs` + Cargo feature `loop_guidance`
**Status:** Active — Phase 0
**Classification:** Public

---

## Goal

Ship the completed-loop-iteration variant of the shipped `probe_guidance` combine (Issue 865): `z′ = z_R + ω(z_R − z_k)` (logit mode, one extra scratch head pass) and `h′ = h_R + ω(h_R − h_k)` (hidden mode, single head pass), with adaptive margin gating `ω = ω_max·[1 − (p_(1) − p_(2))]`, plus a decision-level guided settle-exit fused with the existing `AdvantageMarginGate`/`GainCostLoopHalter` exit family — on the looped forward (`WeightShared`/`TrainingFree`), where no contrast has ever been measured. GOAT gate: guided decode at full loop depth ≥ unguided accuracy, guided at **half** depth ≥ unguided full depth, on a **non-saturated** toy looped fixture; flag-off bit-identity; zero-alloc hot path.

**Lineage the gate must beat:** the combine arithmetic itself ships (`probe_guidance`) and its GOAT gate ran **NEGATIVE twice** on the mini dLLM lane (Bench 847: gain temperature-reachable, dominated by unguided T=1.0 at matched diversity; Bench 850: no modelless weak side wins on a saturated lane; negative pinned as `tests/probe_guidance_goat.rs`). This plan is therefore an adjudication, not a formality: the claim under test is that the weak side's **alignment source** (same block, same head, same prefix — only compute differs) and a lane with structured depth-computation gaps change the verdict. If T3.3(c) fails, the negative extends to a third lane and the class stays closed here.

Honest scope note: no real looped checkpoint exists on this stack (Bonsai/qwen3.8 lanes are not looped); evidence is toy-domain, same posture as Plan 136's loop modes. Promotion to default waits on a production looped consumer (the `event_log_query` Bench-564 precedent) — this plan ships opt-in.

## Phase 0 — Skeleton (CORE)

### Tasks

- [x] **T0.1** `LoopGuidanceConfig { mode: Logits | Hidden, omega: f32, omega_max: f32, adaptive: bool, ref_loop: usize }` — defaults `omega=0.0` (bit-identical off), `ref_loop=1`; validation `omega ≥ 0`, `omega_max ≥ omega` (negative ω universally degrades per paper §G.1 — refuse it) **LANDED 2026-10-03 — `src/transformer/loop_guidance.rs`; `validate()` refuses negative ω / ω_max < ω / ref_loop 0; `is_armed()` marks the ω=0 posture a structural no-op (no capture, no combine)**
- [x] **T0.2** `Cargo` feature `loop_guidance` (opt-in, no default membership); module compiles empty without it (the `#![cfg]` + `required-features` row discipline — same commit) **LANDED — root feature forwards `katgpt-core/loop_guidance`; module `#![cfg]`-gated (mod.rs decl + file gate); `[[test]]` rows for both gate targets**
- [x] **T0.3** README feature-table row + `.docs/` pointer (docs gate: count_features consistency) **LANDED — README table row + catalog row + the 5 count bumps 668→669; docs gate 35/35**

## Phase 1 — Primitive

### Tasks

- [x] **T1.1** Reference capture at loop `ref_loop`: logit mode = one extra head pass on the loop-`k` hidden state into a scratch buffer (reuse the `LoopDeepRun::capture_logits` / `AdvantageMarginGate` scratch readout pattern — no new allocation); hidden mode = stash `h_k` (clone-free: keep the loop-`k` hidden in a second scratch slot inside the existing loop buffer) **LANDED — `capture_reference` at the completed `ref_loop` iteration, placed BEFORE every exit family so an exit AT the capture iteration still gets its reference; pre-sized scratch (the object's one allocation)**
- [x] **T1.2** Contrast apply — **DRY: one home for the arithmetic.** Extract the affine strong−weak combine from `katgpt-forward::d2f_context::apply_probe_guidance` (Issue 865) into a shared katgpt-core helper consumed by BOTH the 865 combine (pure refactor — `tests/probe_guidance_goat.rs` and the d2f combine-kernel tests must stay green; they pin the formula) and the new loop path: logit mode `z′ = z_R + ω·(z_R − z_k)` fused with the adaptive gate `ω_t = ω_max·[1 − (p_(1) − p_(2))]` computed from `softmax(z_R)`'s top-two (partial-argmax scratch, no full-softmax alloc); hidden mode: `h′ = h_R + ω·(h_R − h_k)` applied **before** coda/head so the head pass count stays 1. **Landing shape (verdict-review note):** the helper is gated `any(feature = "probe_guidance", feature = "loop_guidance")` (or the ungated choice is argued in the commit message — it slightly changes the default build surface); the extraction lands as **its own commit ahead of Phase 1** so the formula-preserving refactor is reviewable separately from the new consumer **LANDED — extraction landed FIRST as its own commit (`b329aefec`, gated `any(probe_guidance, loop_guidance)` at the core-crate level, goat gate 5/5 + d2f 41/41 green after); the margin kernel `top_two_margin` is two-pass zero-alloc (the concentration pin CAUGHT the first draft computing `1−p₂` instead of `p₁−p₂` — fixed to the exact shared-denominator form); hidden-mode adaptive ω consumes the PREVIOUS step's output margin (the one-head-pass law means h_R is never read out — deviation pinned in the module doc + a test)**
- [x] **T1.3** Wire into `forward_looped` `WeightShared` + `TrainingFree` paths (`src/transformer/variants.rs`) behind `loop_guidance`; precedence vs `AdvantageMarginGate` documented in code: guidance applies to whichever prediction is finally decoded (exit-iteration or loop-`R`) **LANDED — cfg'd `Option` parameter (the cadence_gate precedent: slot exists only feature-on); both paths wired (tf_loop via the `lg_capture!` macro at both IterationMode arms); precedence documented at the signature + module doc**
- [x] **T1.4** Unit tests: (a) `omega=0` byte-identical to unguided (both modes); (b) adaptive gate maps max-margin → ω 0 and zero-margin → ω_max (concentration pin); (c) determinism (same inputs → same logits); (d) hidden mode performs exactly one head pass; logit mode exactly two; (e) negative-omega config refused **LANDED — `tests/loop_guidance_gates.rs` 14/14; (d) pinned via the observable proxy (logit capture writes the z_k scratch / hidden capture writes only the hidden slot) + the ref_loop-beyond-loop_count no-op pin — the pass COUNT itself is a code-structure property, documented**
- [x] **T1.5** Zero-alloc pin: steady-state decode step allocates 0 bytes with guidance armed (counting-allocator test, the G4 house pattern) **LANDED — `tests/loop_guidance_alloc_gate.rs` (own target/own process — a multi-test target cannot hold this pin: sibling tests share the process-wide counter), contract = guided adds ZERO over unguided; green**

## Phase 2 — Guided settle-exit (the F1 fusion)

### Tasks

- [ ] **T2.1** Decision-level exit criterion alongside the shipped representation-residual halter: **argmax stability across consecutive iterations** — exit when `argmax(z_τ)` has been unchanged for `settle_patience` consecutive loop iterations after `d_min` (the runtime form of offline `agreement_exit`, `katgpt-core/src/loop_depth_probe.rs`); `GainCostLoopHalter` stays as backstop — precedence: whichever fires first, logged. **Cost honesty:** stability checking needs a readout per loop iteration — see T3.4's per-loop readout cost leg; a bounded candidate-set readout (top-m refreshed every j loops) is the large-vocab mitigation and must be chosen before any half-depth claim
- [ ] **T2.2** Loop-budget accounting: report `loops_used / loop_count`, guided vs unguided, in the forward result (consumable by `InferenceOverrides`-style budget knobs later; no router wiring this plan)
- [ ] **T2.3** Tests: exit-iteration answer ≡ full-depth guided answer on the Phase-3 fixture (quality-parity pin); flag-off exit behavior unchanged (existing `AdvantageMarginGate` tests stay green)

## Phase 3 — GOAT bench + gates

### Tasks

- [ ] **T3.1** Toy looped fixture — **provenance pinned: hand-constructed modelless weights** with known iterative semantics (closed-form iterative-refinement task; NO in-repo training — a BLAKE3-committed riir-train artifact is the documented fallback only if hand-construction cannot produce the required slope, per the 865-T2 pattern). The fixture is asserted **non-degenerate BEFORE any guidance leg** (the Bench-847 lesson): (a) a real depth→accuracy slope exists (without it the gate is vacuous); (b) the **close-decision stratum is non-empty with a minimum count** (a saturated toy has no close decisions and T3.3(c) would pass over zero rows — 850's exact failure mode); (c) **disagreement floor**: a minimum count where `argmax(z_k) ≠ argmax(z_R)` — the paper's own disagreement-rate metric (51% at k=1 for Huginn). Without (c), a fixture whose iteration is a monotone contraction along one direction makes `z_R − z_k` parallel to `z_R`, greedy argmax is unchanged **by construction**, and G1 is null for a structural reason rather than an empirical one. **Ordering (verdict-review note): the fixture is frozen and its non-degeneracy assertions are committed before the first guided arm runs; the bench record states that ordering** so a hand-constructed fixture cannot quietly bake in the win
- [ ] **T3.2** `cargo test --release -p katgpt-rs --features loop_guidance --test loop_guidance_goat` (named target + `required-features` row; NOT a benches/ file — the numbers are assertions, and `--release` per gate discipline)
- [ ] **T3.3** G1 quality ladder — **metric pinned: greedy argmax** (the paper's parallel component is an order-preserving rescale and cannot move argmax; any gain must come from the orthogonal re-ranking component — if ANY sampled or pass@k metric is used, the **unguided temperature front at matched diversity** is a mandatory baseline, the exact instrument that killed 865 in Bench 847): (a) guided-full ≥ unguided-full; (b) **guided-half ≥ unguided-full** (the headline claim); (c) on the close-decision stratum: guided > **all three incumbents** — `probe_guidance`-style combine with an **early-tap** dropout weak side (the shipped 865 lane), `product_policy_log` positive blend, `AdvantageMarginGate` exit-only — demote-the-loser discipline; (d) **cheap-weak control**: a dropout weak side applied to **`z_R` itself** under the same combine — separates "any contrast helps" from "depth contrast helps" (the paper's disagreement-tracking claim; if the cheap-weak arm matches the loop-index arm, the alignment-source story is refuted on this fixture). **The two dropout arms are named distinctly in the bench output** (early-tap incumbent vs z_R control) — they differ only in dropout placement and must never read as one leg
- [ ] **T3.4** G2 overhead **with the per-loop readout cost leg** (the settle-exit's stability check needs a readout per loop; at a real vocabulary that head matmul rivals the loop block itself — the paper's 1.01–1.31× is for ONE extra pass, not R): report ns/step and **net-FLOP accounting including all per-loop readouts** — the half-depth claim is void without it; large-vocab mitigation (bounded candidate-set readout, larger snapshot stride) chosen and measured. Logit mode ≤ 2 head passes/step (guidance proper); hidden mode ≤ +5% step time; loop-reduction fraction printed. G3: default-feature build clean + flag-off bit-identity + incumbent exit tests green + `tests/probe_guidance_goat.rs` still green after the T1.2 refactor. G4: from T1.5
- [ ] **T3.5** `.benchmarks/617_loop_guidance_goat.md` with box state (the §Feature-Flag G2 rule: load class beside every number) + verdict + README/docs closure

## Phase 4 — Promotion decision (owner-gated posture)

### Tasks

- [ ] **T4.1** Record the adjudication verdict vs all three incumbents + the cheap-weak control; if guidance loses any G1 leg, record the negative in the research note §2.35 lineage ("the negative extends to a third lane") and keep the feature opt-in dead-or-narrow — never promote a tie; **tier upgrade to GOAT happens only at this record, only on a non-saturated fixture, only with all three incumbents beaten**
- [ ] **T4.2** Promotion to `default` **blocked** pending a production looped consumer (Plan 136 surface adoption); reopen trigger recorded in the research note
- [ ] **T4.3** riir-ai Issue 1025 cross-ref updated with the measured results if the deliberation analog (F2) is picked up by a game-side session

---

## Risks / honest caveats

- **The class is 0-for-2 on this stack** (Bench 847 + Bench 850, both NEGATIVE on the mini dLLM lane; the negative is pinned as the `tests/probe_guidance_goat.rs` inverted-bar gate). This plan's claim — alignment source + non-saturated lane change the verdict — is a falsifiable prediction from the paper's mechanism account (gain tracks disagreement; gains land on close decisions; a saturated trunk has neither), not a measured gain. Expect an 847 repeat if the fixture is degenerate; that is why T3.1's non-degeneracy assertions run first.
- **Toy-only evidence** until a looped checkpoint joins the stack; the class is concurrently published (2609.24196) so external validation exists but not on our substrate.
- The paper's generation-strength window (ω ∈ [0.2, 0.3]) and hidden-reference burn-in subtleties (Huginn h6/h7) are checkpoint-specific; the toy fixture pins the mechanism, not the hyperparameters — hyperparameter transfer is explicitly out of scope.
- `AdvantageMarginGate` exit (Plan 283) already achieves skip-settled-compute at 100% argmax parity on its fixtures; the settle-exit must show value in the *unsettled* stratum or it is redundant — T3.3(c) is the load-bearing leg. The settle-exit's per-loop readout cost (T3.4) can erase the FLOP win at real vocabularies — net accounting precedes any depth-reduction claim.
