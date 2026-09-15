# Issue 801: NAP-Admissibility Audit of Shipped Composers + `meld` Primitive PoC

**Status:** OPEN — filed 2026-09-15 from Research 560 (arXiv:2609.14384, Murphy — NAP + Meld)

Research 560 distilled arXiv:2609.14384 ("Formal Properties of Language as Constraints on
Neural Dynamics") to two modelless extractions: (1) the **NAP 5-invariant admissibility
battery** for composition mechanisms (non-associative grouping, commutativity, recursive
closure, substructure access, structured workspace transitions), and (2) **Meld** — a
bounded, commutative, non-associative, disagreement-coding composition law
(shared-component → sublinear integration → saturation). The census finding: **no shipped
composer in the workspace combines saturation + sublinearity + substructure access +
disagreement-coding**, and the common ones (mass-weighted mean, EMA lerp, gated linear
sums) are associative/commutative ⇒ *provably bracketing-blind* — grouping and order
information is destroyed at consolidation time.

Super-GOAT Q3 (product selling point: structure-aware NPC memory, decomposable shard
consolidation, disagreement-coding healer composition) is **quality-contingent** — this
issue is the §3.6 PoC that either confirms or refutes it.

## Tasks

- [x] T1 — Fetch the PDF. **DONE 2026-09-15**: `curl -sL https://arxiv.org/pdf/2609.14384 -o /tmp/nap_2609.14384.pdf` + `pdftotext` (jina + arxiv-html both failed; curl+pdftotext worked, 5501 lines). Equations transcribed into Research 560 §1 (PDF-verified): `Meld(u,v) = tanh(κW[λ⋆u+(1−λ⋆)v])`, κ=2; `λ⋆ = argmin_λ[λu+(1−λ)v+(1/β)log(λ²+(1−λ)²)]` (pointwise, second-Rényi S₂(λ)=−log[λ²+(1−λ)²]); tied orthogonal W; saturation = boundedness only (law-8 ablation matches on every axis). Ablation hierarchy + depth-ladder numbers + extensivity correspondence in Research 560 §1.3–1.7. Initial reconstruction corrected in the same session.
- [ ] T2 — NAP-admissibility audit (report table, no code changes): score each shipped
  composer against the 5 invariants — `CommittedFieldBlend::apply_blended`
  (katgpt-core), Raven `sleep()`/`consolidate()` (riir-neuron-db `consolidation/`),
  `tpr_bind`/`unbind` (katgpt-core `tpr/`), `frozen_attractor` heal lerp,
  `GaugeInvariantComposer::compose_pair` (riir-ai), Clifford-wedge `retrieve_diverse`
  (selection, not fusion — include for completeness). The audit now runs on
  paper-supplied theorems, not just our algebra: (a) the extensivity correspondence
  (Research 560 §1.3) — mean/EMA/lerp/sum are Shannon-extensive ⇒ associative ⇒
  inadmissible as structure-preserving composers, whatever their decoding accuracy;
  (b) the pointwise-class + fixed-mixture theorem (§1.5) — fixed-λ composers
  (mass-weighted mean, content-independent gates) are provably identical on
  same-leaf-depth-multiset bracketings; (c) the three-fold linear-mixture failure
  (§1.2) — check each composer for free mixture parameters, type-closure violations,
  and planar/order smuggling (untied weights). Deliverable: table in the issue
  close-out note + Research 560 addendum.
- [ ] T3 — `meld` primitive prototype behind opt-in feature `meld` (katgpt-core, near
  `committed_field_blend.rs`): `meld(u,v) = sat(κ·W·[λ⋆u + (1−λ⋆)v])` — (a) pointwise
  soft-min mixture: λ⋆ per coordinate as the argmin closed form (quadratic in λ;
  β→0 degrades to mean, β→∞ to hard min — verify both limits in tests); (b) tied
  orthogonal non-permutation W shared by both daughters (a fixed rotation or
  Hadamard-structured orthogonal map — the load-bearing second-order separator;
  ablation arm: remove W, expect the paper's 0.84→0.68 decay pattern); (c) sat = tanh
  (κ=2) with a divisive-normalization variant (paper: DN slightly better at depth);
  plus the unsaturated law-8 arm `W[λ⋆u+(1−λ⋆)v]`. Zero-alloc, fixed-size `[f32; D]` →
  `[f32; D]`, const-generic D. Invariant self-tests: commutativity EXACT (swap-symmetric
  argmin), non-associativity at nesting (samples where `meld(meld(a,b),c) ≠
  meld(a,meld(b,c))` must EXIST), boundedness through depth-64 recursion (‖·‖ ≤ 1 under
  tanh), disagreement-coding (λ⋆ → min-like as β·|u−v| grows; agreement → mean).
  GOAT gate G1–G4 per discipline; benchmark vs mean/EMA composer (criterion).
- [ ] T4 — PoC in `riir-ai/crates/riir-poc` (§3.6 discipline, three competitors):
  meld vs frozen/no-adaptation baseline (mean) vs role-explicit composer (tpr with
  tree-position roles) on a controlled toy domain (synthetic hierarchical experience
  stream, depth 2–8 bracketings, nearest-centroid decode, 60 seeds — mirror the paper's
  regime). Measure: (a) bracketing-recovery accuracy at each depth (paper refs: meld
  1.000→0.922 d=1–5; law8 →0.899; mean-pooling collapses on same-depth-multiset pairs);
  (b) **PR readout discipline (§9.2)**: participation_ratio of the SQUARED-AMPLITUDE
  distribution p̂_ℓ = a_ℓ²/Σa_ℓ² over atom-direction projections (deterministic vectors
  give PR = exp(3S₄−2S₂), NOT exp(S₂) — the paper's own honesty; measure the right
  quantity, don't assume the clean identification); (c) disagreement-trace utility
  (contradiction detection vs mean-smoothing). Print the verdict table. **PoC defends
  OR refutes** — if meld loses to mean on (a) at all depths, record the refutation in
  Research 560 §"PoC Addendum" and close this issue NEGATIVE; the audit (T2) survives
  regardless (framework-level finding).
- [ ] T5 — Verdict routing: if T4 confirms (meld ≥ mean on hierarchy recovery AND PR
  separation is real): re-run the Research-560 §1.5 gate with Q3 evidence → if 4/4,
  file the private consolidation guide (`riir-neuron-db/.research/`) + consumer plan
  (Raven sleep-cycle meld composition, freeze/thaw lineage); consider `meld` for the
  healer multi-span pool (riir-clippy consumer issue). If refuted: keep the primitive
  opt-in or remove, record the negative, keep T2's audit as the standing finding.

## References

- Research 560: `.research/560_NAP_Meld_Bounded_NonAssociative_Composition.md`
- Closest shipped cousin: Research 527 (tpr — roles-vs-law framing, F3) + Issue 707
  precedent (GOAT-ALL-PASS lifecycle)
- Census evidence: subagent report 2026-09-15 (saturation/sublinear/substructure/
  disagreement table over 8 shipped composers) — reproduced in Research 560 §2
- Prior-art: Marcolli–Berwick arXiv:2305.18278 + 2507.13501 (the corrected target);
  VSA survey arXiv:2001.11797; VTB (Gosmann & Eliasmith 2019); bioRxiv
  2026.02.18.706604 (binding-geometry comparison — read at PoC time)
