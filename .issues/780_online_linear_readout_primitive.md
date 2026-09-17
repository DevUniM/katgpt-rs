# OnlineLinearReadout — katgpt-core primitive for online-fit calibrated linear probes

**Status:** OPEN — BLOCKED, and the block is now **harder than "time-gated"**: the consumer is CLOSED, not waiting.

⛔ **Correction 2026-09-17.** The status below said *"re-check when riir-clippy 107 T3+ opens on organic multi-attempt rings carrying the column"*. There is no such T3 to wait for. **riir-clippy Issue 107 CLOSED NEGATIVE on evidence 2026-09-15** (riir-clippy `5dfa1daff`, HISTORY.md record; file removed per the noise-reduction rule) — T3–T6 (probe harness, gate wiring, GOAT, transfer row) were closed **UNBUILT**, on the owner call that no probe harness, gate or bench is warranted while every available corpus says the oracle decision carries no decodable signal beyond the strategy prior. The two statements were written the same day and the sequencing note is the stale one.

This does not change what to DO here — do not build the primitive — but it changes what to WATCH. The trigger is no longer "a task opens in a live issue"; it is one of riir-clippy 107's three recorded **reopen triggers**, any one of which reopens that issue and with it this one:

1. an **ORGANIC** fixseq ring with ≥2-revert runs AND the span-embed column populated (it accumulates from 107 T2's write-time capture, riir-clippy `1d3cec0b`, and that capture ships — this is the lane's only revival path);
2. **riir-train** densifying the store per its R135 / Bench 047;
3. any post-keep-fix corpus where the resolved rate moves between orderings at all (the riir-clippy Bench 085 corollary).

⚠ Kept OPEN rather than closed alongside its consumer: the shape here is a katgpt-core **primitive gap** (the missing third half of the linear-probe lineage, argued below on this repo's own type inventory), and that argument does not depend on riir-clippy having a use for it. What 107's closure removes is the **live consumer** T5's promotion bar requires — so this cannot reach promotion, and building it now would be a synthetic-fixture GOAT pass that does not speak to the measured-absent live signal.

**Prior sequencing record** (accurate, superseded only in what it says to watch): riir-clippy 107 T1 measured the probe lane NOT viable on ring-native features (horizon 1 < 2 on every corpus; the strategy prior is a sufficient statistic there). T2 landed the span-shape embedding column and measured the synthetic corpora NOT revived either — auc(embed) 1.000 under the same 1.000 strategy floor; the diverged synthetic arms share templates, so span content carries no extra signal there.

Filed from riir-clippy Research 168 — arXiv:2607.05188 distillation.

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
