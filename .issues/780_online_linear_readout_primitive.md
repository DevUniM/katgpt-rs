# OnlineLinearReadout — katgpt-core primitive for online-fit calibrated linear probes

**Status:** OPEN (filed from riir-clippy Research 168 — arXiv:2607.05188 distillation; consumer: riir-clippy Issue 107)

## Summary

katgpt-core ships the frozen half of the linear-probe lineage (`FutureBehaviorProbe` — offline logistic fit, BLAKE3-committed, hot-swap; `IndicatorProbeBank` — frozen thresholds) and the scalar-posterior half (`best_belief_score` Beta-LCB, `rating` Elo). The missing third half: **an online, gradient-free fit** — moment accumulators + closed-form solve + Beta-LCB calibration — so a probe can be fit at runtime from an agent's own logged outcome labels without any training lane. riir-clippy's `evolve.rs` EMA direction is a local, uncalibrated twin of exactly this; the primitive belongs here (DRY), the healer consumes it.

## Why this shape

- **Mutation class #3, verbatim**: a direction vector + sigmoid gate updated from labeled outcomes — latent state, never base weights (the modelless mandate's allowed runtime mutation).
- **GD-free fits, all deterministic**: ridge/RLS (`G += x·xᵀ`, `h += y·x`, `w = (G+λI)⁻¹h`, rank-1 additive — the same complexity class as a Beta increment); closed-form LDA `Sw⁻¹(μ₊−μ₋)`; perceptron/Elo-class mistake updates; Beta counting on projection signs. Decay-able moments for distribution drift. Full Gram inverse is an offline/staging step; the hot path stays `simd_dot_f32` + sigmoid (O(D), alloc-free, `FutureBehaviorProbe` cost class).
- **Calibration is first-class**: Beta-LCB over sign-agreement counts on the fitted direction — the `best_belief_score` discipline extended from scalar keys to a vector readout. UQ "Report the Floor" rule: a probe must beat the base-rate and history-aggregate floors to gate anything.

## Proposal

- Feature `linear_probe` (opt-in), module beside the pruner/probe lineage in katgpt-core.
- Type sketch: `OnlineLinearReadout<const D: usize>` — `observe(x: &[f32; D], y: bool)` (moment update, no alloc), `fit_into(&mut [f32; D])` (closed-form solve on staging), `score(x) -> ProbeVerdict { p, lcb, n }` (inline dot + sigmoid + Beta-LCB, zero-alloc), decay config, BLAKE3 commitment of `(w, b, counts)` reusing the `FutureBehaviorProbe` freeze/thaw convention (probe ≈ D+1 floats + counts — a ~260 B artifact through the existing envelope discipline).

## Tasks

- [ ] T1 — feature `linear_probe` + `OnlineLinearReadout` core (moments, closed-form fit, calibrated score, decay).
- [ ] T2 — freeze/thaw + hot-swap: BLAKE3-committed artifact, readers never see torn state (the `FutureBehaviorProbe` contract).
- [ ] T3 — GOAT gate: (G1) AUC within ε of a GD-fit logistic reference on fixed fixture corpora AND beats base-rate floor; (G2) score path O(D), no alloc (criterion, `future_probe` bench class); (G3) no regression on existing probe benches; (G4) alloc-free scoring, fixed buffers.
- [ ] T4 — docs: the three-half map (frozen offline / indicator bank / online fit) + the mutation-class justification in the module doc.
- [ ] T5 — promotion decision: GOAT pass + a live consumer (riir-clippy Issue 107 gate) ⇒ propose default-on; else stay opt-in with the consumer noted.

## Non-goals

MLP heads, backprop of any kind, softmax link (sigmoid only per AGENTS.md), engine-residual capture (that is riir-ai/riir-train lane — Plan 403).
