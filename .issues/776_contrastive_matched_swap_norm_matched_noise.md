# Issue 776: Contrastive matched-swap + norm-matched noise interventions (CVRR follow-on, Research 555)

**Status:** DONE (T1–T7) — implemented 2026-09-14 (katgpt-rs `be4ff672` + bench commit: `perturb_matched_swap`/`perturb_norm_matched_noise{_rows}` + probe `probe_matched_swap{_into}`/`probe_norm_noise{_into}` + battery sixth `norm_matched` arm + `LatentSpace::norm_matched_noise` + bench rows; 73 tests green, clippy -D warnings clean, default-off unaffected). Bench (release, audit cadence): matched_swap 0.37µs / norm_noise 46.2µs at n=4096 — both ≪1ms target.

**Source:** arXiv:2609.06746v3 (CVRR) §2.1 Figure 1a + §5.3 — the two interventions our shipped suites cannot express.

## Problem

The shipped intervention suites detect decorative latents but confound two channels:

1. `faithfulness::perturb::perturb_irrelevant` substitutes **random element picks** from an external pool — an incoherent mixture, not a coherent counterfactual state. `interpolation_geometry::intervention_battery`'s `shuffled` swaps in a **random donor** — changing query-content and evidence-content together. Neither can isolate *evidence-conditioned* content the way CVRR's contrastive matched-swap does (same question, different evidence → different answer; their §5.3: swapped state 26.7% vs text-only anchor 50.0% — *incompatible* image-content is more disruptive than *none*, a distinction random donors cannot show).
2. `LatentSpace::noise` is Gaussian around the origin — destroys magnitude AND structure together. CVRR's **row-norm-matched noise** (`n_j = g_j · ‖s_j‖/‖g_j‖`) preserves magnitude, destroying structure only — separating "consumer reads the norm" from "consumer reads the structure".

## Tasks

- [x] **T1** `faithfulness::perturb::perturb_matched_swap<T: Clone>(memory: &mut [T], donor: &[T])` — whole-buffer coherent swap (donor length must match; assert). Donor *selection* stays caller-side; document the contrastive protocol (donor shares the query/context, differs in the evidence → differs in the outcome) in the doc comment.
- [x] **T2** `faithfulness::perturb::perturb_norm_matched_noise(memory: &mut [f32], rng: &mut Rng)` — per-row (or per-element for flat slices, documented) `n = g · (‖s‖/‖g‖)`; zero-norm rows pass through as zero. (Shipped as whole-slice + `_rows` per-chunk variants.)
- [x] **T3** `interpolation_geometry::LatentSpace::norm_matched_noise(&self, anchor: &Self::Point, seed: u64) -> Self::Point` + wire into `intervention_battery` as a sixth report field (default: origin-noise retained for back-compat; norm-matched added alongside).
- [x] **T4** Two-sided canary tests (G1): (a) a consumer that ignores the memory → ALL deltas ≈ 0 → decorative verdict; (b) a consumer that reads structure-only → norm-matched noise diverges but a pure-norm reader does not; (c) contrastive donor flips a structure reader toward the donor's outcome (`flips_to_donor` analog). (Norm-only consumer `NormOnlyConsumer` = the separating canary; norm-matched arm added to `latent_is_causal` AND chain with its own failing-arm test.)
- [x] **T5** Golden vectors: seeded noise + swap outputs BLAKE3-pinnable (deterministic across runs). (Same-seed determinism tests; Box-Muller streams seed-reproducible.)
- [x] **T6** G4 zero-alloc: perturbations mutate caller buffers (existing pattern); battery additions reuse scratch buffers. G8-style zero-overhead-off: keep everything behind the existing `faithfulness_probe` / respective feature gates — no new default symbols. (Norm-matched arm reuses `noise_scratch` after the noise decode — zero new buffers; POD test updated 24→28 bytes.)
- [x] **T7** Bench extension: one audit-cadence cost row in `faithfulness_probe_bench` for the two new probe methods (target: same class as existing, < 1ms per segment). (Measured: swap 0.00–0.37µs, norm_noise 0.18–46.2µs across n=16..4096 — 21×–2700× headroom.)

## GOAT gate

G1 two-sided canary (the audit-instrument law: an audit that cannot fail certifies nothing); G4 alloc-free; G8 zero-overhead when off. Promotion: stays opt-in (`faithfulness_probe` is a diagnostic, Plan 278 ADR-2 unchanged).

## Non-goals

No enforcement/remediation here (strict-interface enforcement is riir-ai Issue 953); no layer/stage sweep (riir-train Plan 402 P1 consumer).
