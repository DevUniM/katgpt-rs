# Issue 852: `ScheduleKind::DecodingErrorLut` — FMLM's τ(t) measured time warp for D2F

**Status:** OPEN — POC, modelless (off [Research 572](../.research/572_FMLM_Flow_Map_Language_Models.md) row 1; source: FMLM [arXiv:2602.16813](https://arxiv.org/abs/2602.16813) Eq 25)

## Why

FMLM's single highest-leverage ablation is a **measured, data-adaptive time reparameterization** — no retraining, just a timeline warp:

```
τ(t) = 1 − (|V|/(|V|−1)) · P_e(t)     P_e(t) = per-token decoding error rate at time t
```

built as a 1000-point LUT (Gauss-Hermite quadrature + cubic spline, O(1) eval). At |V|≈50k it moved 149.18 → 106.98 Gen PPL — the difference between converging and not. Token identity concentrates in a narrow window near t=1 for large vocabs; τ redistributes step budget so each step contributes equally to decoding.

Our `ScheduleKind` family (`katgpt-forward/src/d2f/mod.rs`: Uniform, LogitNormal{mean,std} from R044, EquiProb from DiffusionBlocks) contains only **parametric guessed shapes**. This adds the first **measured** member: the shape comes from the model's own decoding-error curve. Standing: a calibration pass → frozen artifact (conformal machinery precedent, Plan 340) — never a gradient. The LUT is a fixed-size Pod: BLAKE3-committable, freeze/thaw-able per model family.

## Honest scope

- FMLM's gain was measured at |V|≈50k text LMs. If our D2F lanes run at toy vocab (games, |V|≤256), the concentration effect may not transfer — the GOAT gate must accept a honest negative and close the issue as recorded.
- P_e measurement = decode tokens at grid t-values with the frozen model on a held batch and count disagreements. One probe pass, deterministic.

## Tasks

- [ ] Measure P_e(t) on a held batch per D2F model: 128+ t-bins, deterministic seed, record curve
- [ ] `ScheduleKind::DecodingErrorLut { lut: [f32; N] }` (fixed N=1000 or smaller; const-generic or const N) + builder from a measured P_e curve (monotone regression + spline), behind `d2f_tau_lut` feature flag (opt-in)
- [ ] τ↔t inversion helper (the paper ships t(τ) as a second LUT — both directions needed for step-grid mapping)
- [ ] GOAT gate G1: LUT monotonicity + round-trip τ(t(τ))=τ identity tests; G2: matched-step-budget bench vs Uniform (default) / LogitNormal / EquiProb on the existing D2F bench harness (`tests/bench_elf_modelless.rs` pattern); promote to default only on measured win; G3: no regression in existing ScheduleKind tests; G4: zero-alloc LUT eval (no spline allocation in hot path)
- [ ] Negative-result clause: if no win at our vocab scale, record the measured curves + verdict in Research 572 and close

## Refs

- Research 572 §1.4, §3 row 1, §4 (fusion: measured member of the ScheduleKind family)
- riir-train sibling: Issue 563 notes the training-side twin (invert-CDF t-sampling for RecFM at |V|≥32k, where the effect is in-regime)
