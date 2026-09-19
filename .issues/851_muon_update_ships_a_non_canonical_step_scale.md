# Issue 851: `muon_update` ships a NON-canonical step scale while its own doc claims "standard Muon scaling"

**Status:** OPEN — filed from the arXiv:2502.16982 distill session
(2026-09-19). The paper itself is otherwise fully distilled in-workspace
(see §Provenance); this file is the one actionable delta it surfaced.

## The defect

`crates/katgpt-core/src/newton_schulz.rs` — the public, default-on
(`newton_schulz` feature, Plan 152, GOAT 25/25 Bench 050) Muon convenience
wrapper applies a step scale that matches **neither** reference convention,
while claiming to:

```rust
// L256-257 (muon_update) and L284-285 (muon_update_into):
// Scale by 1/max(rows, cols) — standard Muon scaling
let scale = 1.0 / (rows.max(cols) as f32);
```

The doc comment one screen up disagrees with the code it documents — L232
says `scaling = 1.0 / (rows as f32)` (bare `rows`, not `max(rows, cols)`),
so the file carries **three** mutually inconsistent stories (doc, comment,
canonical reality).

## What canonical actually is

By Lemma 1 of Moonlight (arXiv:2502.16982, Liu et al., Moonshot AI, Feb
2025), the Newton-Schulz-orthogonalized update of a full-rank `[A, B]`
matrix has RMS `√(1/max(A,B))`. The three reference scalings in the family:

| Convention | Scale | Resulting update RMS | Resulting ‖ΔW‖_F at square D×D (×lr) |
|---|---|---|---|
| Keller Jordan original Muon | `√max(1, A/B)` | `√(1/D)` at square | `lr·√D` |
| Moonlight "Adjusted LR" (their Eq 7, the chosen method) | `0.2·√max(A,B)` | `0.2` (matches AdamW's 0.2–0.4) | `0.2·lr·D` |
| riir-train production `muon_step_dense` (`optimizer_lora_muon.rs` L1162, "rescale to approximately preserve ‖g‖") | `√max(rows,cols)` | `1.0` | `lr·√D` |
| **shipped `muon_update`** | `1/max(A,B)` | `max(A,B)^{-3/2}` | `lr/√D` |

At square D×D the shipped update is **D× smaller than Keller's** and
`0.2·D^{1.5}`× smaller than Moonlight's — and the error **grows with D**,
which is precisely the property that makes it un-absorbable by an LR grid.

## Why it matters (the measured lesson)

riir-train Bench 492 (Issue 472 T7, the `{Adam, AdamW, Muon} × LR grid × d`
optimizer canary) recorded this exact class as its load-bearing
methodological finding: a first-draft RMS-match scale that was 4.1× the
canonical family at D=32 produced a Muon-vs-Adam gap that *grew with d* —
"the LR grid does not absorb a d-dependent scale error; the step-scale
convention must match the reference implementation family, not a
re-derived 'fair' match."

Blast radius today: **zero production consumers** — riir-ai has no
`muon_update`/`newton_schulz5` call sites (verified by grep 2026-09-19);
riir-train's optimizer uses its own canonical-scale `muon_step_dense` +
`ns_inv_sqrt_psd_into`; only `tests/bench_152_newton_schulz_goat.rs` and
the module's unit tests exercise it. So the defect is latent, not live —
but it is a public default-on API wearing a "standard" label, and the next
consumer who transplants it with an LR tuned for canonical Muon inherits a
silently D×-too-small, d-dependent step.

## The fix (proposed)

1. Scale `muon_update` / `muon_update_into` by `√max(rows, cols)` —
   aligning with the in-house reference family (riir-train's shipped
   convention; Keller and Moonlight agree with it within a constant the LR
   absorbs — Bench 492 measured 13% at D=32 between the two named forms).
   This yields the clean invariant **update RMS ≈ 1.0 (pre-LR)**.
2. Repair the doc/comment self-disagreement (L232 `1.0/(rows as f32)` vs
   L257 `1/max`); name all three conventions in the doc so the next reader
   does not re-derive a "fair" match.
3. Regression test: assert RMS(out) ≈ 1.0 within NS5's singular-value band
   (singulars converge to [0.68, 1.12] per Bench 050, so ±20% tolerance),
   at square and non-square shapes.
4. Re-run `cargo test --features newton_schulz --test bench_152_newton_schulz_goat`
   + the module unit tests — the GOAT assertions are scale-invariant
   (orthogonality ratio, finiteness, variant-match, pre-scale momentum
   norms), so they should hold; re-verify rather than assume.

## Provenance + what already ships (why this is a small issue, not a plan)

Filed while distilling [arXiv:2502.16982 "Muon is Scalable for LLM
Training"](https://arxiv.org/abs/2502.16982) (Moonlight). The paper's
contributions are otherwise fully absorbed, most of them generations deep:

- NS5 iteration + Muon momentum + zero-alloc scratch — Plan 152 / Research
  114 (AMUSE), GOAT 25/25 (Bench 050), default-on. The paper's N=5-is-
  sufficient finding confirms the shipped iteration count.
- Weight decay for Muon (their #1 technique) — ships in riir-train
  `optimizer_lora_muon.rs` including the *split* gauge-invariant form
  `s = √(1−λη)` (the LoRA-Muon refinement), presets 0.005–0.02.
- Update-RMS scaling (their #2 technique) — ships as `O·√max(rows,cols)`
  in `muon_step_dense`, and has been superseded twice: Bench 473 measured
  that the RMS-matching identity itself breaks under finite-iteration NS
  (−0.37% to −10.54%, moves 30.71% with the momentum spectrum), and
  `muon_sample_calibration.rs` (Plan 339 T4.1c) replaces static scaling
  with per-parameter runtime calibration on the real momentum.
- "Muon is the optimizer of record" stance + the 2024–2026 industrial
  landscape (Moonlight → Kimi K2 MuonClip → …) — riir-train Research 439
  §2 and Research 441 (which cites this arXiv ID in its references).
- SVD-entropy diagnostics (their §3.4) — the effective-rank / spectral
  machinery ships as `river_valley` (Plan 152, default-on) and
  riir-neuron-db `spectral_flatness.rs`.
- Distributed Muon (ZeRO-1, DP gather) — out of scope at our single-GPU
  (4090/M3) training scale; no action.

**Secondary note for riir-train routing (recorded here, no sibling file):**
the paper's SFT ablation (Tables 6–7) is a negative result worth keeping —
Muon-SFT shows **no advantage** over AdamW-SFT on AdamW-*pretrained* bases
(Qwen2.5-7B: MMLU 71.4 vs 70.8, Adam slightly ahead; HumanEval 79.3 vs
77.4); the Muon advantage appears only when pretrain AND SFT both use
Muon. Our base models (Gemma-2-2B, MiniCPM5, Bonsai/Ternary) are
externally AdamW-pretrained — Muon-SFT plans on them should not budget for
the ~2× pretraining gain.
