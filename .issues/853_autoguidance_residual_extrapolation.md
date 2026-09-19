# Issue 853: Autoguidance residual extrapolation — weak/strong pair steering at inference

**Status:** OPEN — POC, modelless (off [Research 572](../.research/572_FMLM_Flow_Map_Language_Models.md) row 2; source: FMLM [arXiv:2602.16813](https://arxiv.org/abs/2602.16813) Eq 26 autoguidance)

## Why

FMLM's autoguidance is an **inference-only** affine extrapolation away from a weakened read of the same model:

```
b_guided = b_weak + η · (b − b_weak),   η > 1
```

with the weak variant = the SAME net at dropout 0.1 (no second model trained). Result: Gen PPL 96.91 → **51.62** at η=50, stable to η=100 — while every DISCRETE baseline collapses at η≥10 (logit-space extrapolation amplifies factorization artifacts). The mechanism is arithmetic over two forward passes we already hold:

- **DDTree verify step** holds (full-model, ternary-draft) pairs in memory — the residual (b − b_weak) is free.
- **RecFM** (riir-ai/riir-train) trains dual-dropout consistency (`p` vs `p·α`) — a net trained that way has a *meaningful* dropout-on forward, exactly the weak variant autoguidance needs. Zero training change; `ŷ = ŷ_dropout + w·(ŷ_clean − ŷ_dropout)` at inference.

## Prior-art honesty (two arms, two different claims)

- **Arm A — logit space (katgpt-rs, adoption NOT novelty):** extrapolating token logits with a weak draft is contrastive decoding (Li et al. 2022: `(1+α)·expert − α·amateur`). Established; unshipped in our stack. The delta we test: the ternary Q2 draft as the amateur, on DDTree expansion logits, η small (the draft gap is much wider than dropout-0.1 — sweep conservatively).
- **Arm B — latent space (fusion, novelty TBD):** dual-dropout-trained RecFM readouts (hidden states, not logits) extrapolated at w>1. Nobody has connected consistency-across-dropout training to a free inference guidance dial. Continuous space is where FMLM measured η stability — the collapse mode is discrete-specific. Routes with riir-train Issue 563 (free-rider arm: pure inference A/B on an existing RecFM LoRA, ~0 training GPU-hours).

## Tasks

- [ ] `autoguidance_extrapolate(strong: &[f32], weak: &[f32], eta: f32)` — zero-alloc kernel, `flow_autoguid` feature flag (opt-in), identity at η=1 (bit-identical fallback, safe default)
- [ ] Arm A bench: DDTree acceptance rate + task quality at η ∈ {1, 1.5, 2, 3} vs baseline; record the collapse boundary honestly (discrete-space prediction from FMLM: instability beyond small η)
- [ ] Arm B (with riir-train 563): dropout-on/off RecFM forward pair on an existing LoRA, w ∈ {1.5, 2, 3}, acceptance/KL metrics; reuse `bench_elf_omega_sweep.rs` sweep pattern
- [ ] η per-context auto-tune probe: bandit pruner with acceptance rate as reward (modelless adaptivity we already ship) — only if Arms A/B show any usable range
- [ ] GOAT: G1 determinism (fixed-seed dropout mask for the weak variant — deterministic transform, never RNG-at-inference); G2 ≥2% quality or ≥5% acceptance gain at η>1; G3 no regression at η=1; G4 zero-alloc
- [ ] Negative-result clause: if Arm A collapses at all η>1 (plausible — ternary gap too wide, discrete space) and Arm B shows no range, record curves + close

## Refs

- Research 572 §1.4 (autoguidance), §3 row 2, §4 (fusion section — the dual-dropout connection)
- riir-train Issue 563 (Arm B free-rider); R366 (self-cond draft — the 2-pass weak/strong shape); R382 (spherical steering — different mechanism: interpolation, not extrapolation)
- Latent-vs-raw rule: latent arm operates on hidden/belief state; NEVER on raw sync scalars (position/HP) — extrapolation there breaks deterministic replay
