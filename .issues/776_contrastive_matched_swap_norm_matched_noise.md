# Issue 776: Contrastive matched-swap + norm-matched noise interventions (CVRR follow-on, Research 555)

**Status:** Open — filed 2026-09-14 from [Research 555](../.research/555_CVRR_Latent_Necessity_Strict_Interface.md); not started.

**Source:** arXiv:2609.06746v3 (CVRR) §2.1 Figure 1a + §5.3 — the two interventions our shipped suites cannot express.

## Problem

The shipped intervention suites detect decorative latents but confound two channels:

1. `faithfulness::perturb::perturb_irrelevant` substitutes **random element picks** from an external pool — an incoherent mixture, not a coherent counterfactual state. `interpolation_geometry::intervention_battery`'s `shuffled` swaps in a **random donor** — changing query-content and evidence-content together. Neither can isolate *evidence-conditioned* content the way CVRR's contrastive matched-swap does (same question, different evidence → different answer; their §5.3: swapped state 26.7% vs text-only anchor 50.0% — *incompatible* image-content is more disruptive than *none*, a distinction random donors cannot show).
2. `LatentSpace::noise` is Gaussian around the origin — destroys magnitude AND structure together. CVRR's **row-norm-matched noise** (`n_j = g_j · ‖s_j‖/‖g_j‖`) preserves magnitude, destroying structure only — separating "consumer reads the norm" from "consumer reads the structure".

## Tasks

- [ ] **T1** `faithfulness::perturb::perturb_matched_swap<T: Clone>(memory: &mut [T], donor: &[T])` — whole-buffer coherent swap (donor length must match; assert). Donor *selection* stays caller-side; document the contrastive protocol (donor shares the query/context, differs in the evidence → differs in the outcome) in the doc comment.
- [ ] **T2** `faithfulness::perturb::perturb_norm_matched_noise(memory: &mut [f32], rng: &mut Rng)` — per-row (or per-element for flat slices, documented) `n = g · (‖s‖/‖g‖)`; zero-norm rows pass through as zero.
- [ ] **T3** `interpolation_geometry::LatentSpace::norm_matched_noise(&self, anchor: &Self::Point, seed: u64) -> Self::Point` + wire into `intervention_battery` as a sixth report field (default: origin-noise retained for back-compat; norm-matched added alongside).
- [ ] **T4** Two-sided canary tests (G1): (a) a consumer that ignores the memory → ALL deltas ≈ 0 → decorative verdict; (b) a consumer that reads structure-only → norm-matched noise diverges but a pure-norm reader does not; (c) contrastive donor flips a structure reader toward the donor's outcome (`flips_to_donor` analog).
- [ ] **T5** Golden vectors: seeded noise + swap outputs BLAKE3-pinned (deterministic across runs).
- [ ] **T6** G4 zero-alloc: perturbations mutate caller buffers (existing pattern); battery additions reuse scratch buffers. G8-style zero-overhead-off: keep everything behind the existing `faithfulness_probe` / respective feature gates — no new default symbols.
- [ ] **T7** Bench extension: one audit-cadence cost row in `faithfulness_probe_bench` for the two new interventions (target: same class as existing, < 1ms per segment).

## GOAT gate

G1 two-sided canary (the audit-instrument law: an audit that cannot fail certifies nothing); G4 alloc-free; G8 zero-overhead when off. Promotion: stays opt-in (`faithfulness_probe` is a diagnostic, Plan 278 ADR-2 unchanged).

## Non-goals

No enforcement/remediation here (strict-interface enforcement is riir-ai Issue 953); no layer/stage sweep (riir-train Plan 402 P1 consumer).
