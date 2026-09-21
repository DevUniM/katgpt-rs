# Issue 863 — T1.6 validation: corpus-distance abstain vs score-threshold ABSTAIN

**Status:** IN-PROGRESS — implements Proposal 014 T1.6 (marked UNVALIDATED there); Research 576 §2.1 extraction.

## The claim under test

Research 576 §2.1 (SalesRLAgent, arXiv:2503.23303 — single-author, synthetic-corpus, no-code; thin-paper caveats on record): confidence via **similarity-to-training-data** is computable modellessly — retrieval distance → sigmoid gate → abstain when the decision state is far from every registered corpus region. Proposal 014 T1.6 requires it to beat the score-threshold ABSTAIN baseline (`CalibratedActionBridge::should_abstain`) on **selective accuracy at matched abstain rates** before it can join the engine's default arm.

## Deliverable

- `katgpt-core` opt-in feature `distance_abstain` — `CorpusDistanceGate<const D>`: registered unit-norm exemplars; `max_similarity` (max cosine, zero-alloc query path); `abstain_confidence` = `sigmoid(scale·(max_sim − mid))` (sigmoid, never softmax); `should_abstain`.
- `bench_845_distance_abstain_goat` — the T1.6 gate: two error worlds on one geometry. **W1** (OOD-blind errors — the arena's world): the model's score carries no OOD information, errors concentrate far from the corpus. **W2** (score-only errors — negative control): identical geometry, errors driven by score alone. Arms: score-only / distance-only / fused `min(p, d_conf)`, risk–coverage + matched-rate selective accuracy at ρ ∈ {5, 10, 20, 30}%.
- Gates: G1 mechanism sanity (monotone in corpus distance, scale-invariant, empty-corpus abstains). G2 win (W1): fused AURC < score AURC, non-inferior at every ρ, ≥2 pp at ρ=20%, ≥3 pp at ρ=30%. G3 control (W2): distance-only must NOT beat score (the fixture discriminates — the W1 win is attributable to the OOD-error mechanism, not fixture bias). G4 zero-alloc query path. G5 per-query latency budget (K=128, D=64).

## Standing rule honored

OPT-IN regardless of verdict — `margin_gate` precedent: no default promotion on toy-only evidence; promotion requires the live consumer (the Proposal 014 Phase-1 engine, owner-gated).

## Resolution

See `.benchmarks/845_distance_abstain_goat.md` (lands with the measured verdict); this file removed per the noise-reduction rule, commit hash referenced there and in Proposal 014 T1.6.
