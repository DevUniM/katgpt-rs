# Bench 801 — meld composition-law gate: G1 self-tests PASS, bracketing-ladder NOT reproduced on our fixture (Issue 801 T3)

**Status:** RECORD — G1 self-tests PASS (commutativity EXACT bitwise, non-
associativity 512/512, λ⋆ within 3.24e-7 of brute-force optimum, boundedness
depth-64, disagreement-coding limits); **G1 quality ladder: RED FLAG — the
paper's depth-ladder shape did NOT reproduce on our synthetic fixture**;
Super-GOAT Q3 stays BLOCKED on T4. Measured 2026-09-16, M3 Max, D=32.
**RESOLVED 2026-09-16 (same day): T4 ran and REFUTED the quality axis** —
riir-ai Bench 932 (`286687cd0`): mean matches/beats every meld arm on the
adjudicating same-multiset D_eff readout (all margins ≤ +0.008); this bench's
σ-regime hypothesis confirmed for absolute quality but the ordering never
crosses law-8. The λ̃ disagreement-trace utility CONFIRMED (AUC 0.976).
Close-out: katgpt-rs HISTORY.md "Issue 801 CLOSED" row + Research 560
§"PoC Verdict" addendum. This record stands as the T3 algebra evidence.

Provenance: Issue 801 T3 — the §3.6 PoC discipline says the quality axis is
claimed only from a measured PoC, never from architecture. This bench is the
first measurement, and it is honest both ways: the algebra properties all
hold; the headline quality claim does not (yet) transfer to our fixture.

## What held (the algebra, all self-tested)

- **Commutativity EXACT**: 4800 (composer, pair) cases bitwise identical
  under daughter swap — the canonical-(hi,lo) ordering trick makes the
  soft-min argmin path swap-symmetric bit-for-bit (3 laws × 4 β × D∈{4,16} ×
  ±no-W).
- **Non-associativity EXISTS**: 512/512 seeded triples differ under
  re-bracketing — grouping information demonstrably survives composition
  (the property mean/EMA provably lack; cf. Research 560 addendum audit).
- **λ⋆ correctness**: quadratic closed form vs 10_001-point grid brute
  force, 512 cases, worst margin g_min − g(λ⋆) = 3.236e-7 (≤ 1e-6 bar;
  f64 referee — f32 ulp at |g|≈23 exceeds the bar).
- **Boundedness**: depth-64 recursion, max|coord| ≤ 1 at every step (Tanh +
  DivisiveNorm; law-8 excluded — unbounded by design).
- **Disagreement-coding**: λ̃ → min-taking limit for large β·|u−v|; → 0.5
  (mean) for agreement / small β. The paper's two testable predictions both
  observable in the primitive.

## What did NOT hold (the red flag, printed LOUD by the bench)

Bracketing-recovery by depth (D=32, 256 trials, leaf-level 0 dB noise,
nearest-centroid decode), vs the paper's ladder:

| arm | d=1 | d=2 | d=3 | d=4 | d=5 | paper (meld) |
|---|---|---|---|---|---|---|
| meld (tanh) | 1.000 | 0.831 | 0.532 | 0.434 | 0.380 | 1.000/1.000/0.998/0.970/0.922 |
| law-8 (unsaturated) | 1.000 | 0.908 | 0.801 | 0.844 | 0.870 | …/0.964/0.899 |
| no-W | 1.000 | 0.294 | 0.178 | 0.167 | 0.474 | 0.843/0.754/0.705/0.677/0.684 |
| mean | 1.000 | 0.706 | 0.710 | 0.844 | 0.910 | collapses (same-multiset) |

Three divergences from the paper, all recorded:

1. **tanh-meld < law-8 at depth** (paper: meld ≥ law-8 everywhere).
   Working hypothesis: with unit-RMS atoms, κ·W·mixture sits in tanh's
   high-slope/amplification region, compounding noise through depth; the
   paper's population-dynamics regime may normalize differently. T4 must
   scan the input scale (the tanh operating point) as a first variable.
2. **Mean-pooling does NOT collapse on full-vector nearest-centroid** for
   ORDERED leaves: per-leaf depth weights (a_ℓ = 2^−depth(ℓ)) make the
   per-leaf mean sequence itself tree-dependent, so same-depth-multiset
   bracketings separate at the full-vector level. The paper's blindness
   theorem is about the **S₂/D_eff statistics readout** — exactly the
   §9.2/PR discipline Issue 801 T4(b) already mandates
   (`p̂_ℓ = a_ℓ²/Σa², PR = exp(3S₄−2S₂)` for deterministic vectors). T4
   MUST carry that readout; the full-vector decode axis alone would
   falsely exonerate mean-pooling.
3. **no-W collapses hard at d=2–4** (0.294/0.178/0.167 — paper's no-W degrades
   gently 0.843→0.684). Direction matches (W is load-bearing); magnitude
   does not. Same regime suspicion as (1).

## Throughput (G2 axis — context, not the claim)

| D | meld ns | mean ns | × |
|---|---|---|---|
| 32 | 236 | 12.3 | 19 |
| 64 | 541 | 19.0 | 28 |
| 128 | 1102 | 13.5 | 82 |

meld is 19–82× a mean composer — expected (quadratic solve per coordinate +
FWHT). The claim is structure, not speed; recorded so consumers price it.
G4: fixed-size stack arrays, zero heap in the hot path.

## Verdict routing (per Issue 801 T5, pre-T4 state)

- T2 audit (landed `ee6993a77`): the census finding SURVIVES code-level
  scrutiny — 4 INADMISSIBLE / 1 PARTIAL (tpr bookkeeping) / 1 N.A.; the gap
  meld targets is real at the code level.
- T3 (landed `43f15f7c8` + wiring `f314d5006`): the primitive exists,
  opt-in `meld`, algebra-validated; NOT quality-validated.
- **T4 (open) is now the sole adjudicator** and MUST: (a) scan the tanh
  operating point / atom scale; (b) use the S₂/D_eff (PR over squared
  amplitudes) readout for the bracketing-separation claim; (c) include the
  same-multiset restricted contrasts on the statistics readout; (d) if meld
  still loses to mean on the paper's own readout at paper-like regime,
  record the refutation in Research 560 §"PoC Addendum" and close the
  quality axis NEGATIVE — the audit (T2) survives regardless.

Validation: `cargo test -p katgpt-core --features meld --lib` → 2067 passed
(7 new meld tests); combo with bf16_simd → 2077/0; default 2060/0; wasm32
combo clean; clippy `-D warnings` clean; bench wall 3.1 s release.
