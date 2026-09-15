# Issue 801: NAP-Admissibility Audit of Shipped Composers + `meld` Primitive PoC

**Status:** OPEN — T1/T2/T3 DONE 2026-09-16 (T1 PDF-verified below; T2 `ee6993a77` Research 560 addendum — 4 INADMISSIBLE / 1 PARTIAL / 1 N.A., census SURVIVES; T3 `43f15f7c8`+`f314d5006` [Bench 801](../.benchmarks/801_meld_goat.md) — algebra all PASS, quality-ladder RED FLAG → T4 is the sole adjudicator, see the sharpened T4 spec). Filed 2026-09-15 from Research 560 (arXiv:2609.14384, Murphy — NAP + Meld)

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
- [x] T2 — NAP-admissibility audit (report table, no code changes): score each shipped
  composer against the 5 invariants — `CommittedFieldBlend::apply_blended`
  (katgpt-core), Raven `sleep()`/`consolidate()` (riir-neuron-db `consolidation/`),
  `tpr_bind`/`unbind` (katgpt-core `tpr/`), `frozen_attractor` heal lerp,
  `GaugeInvariantComposer::compose_pair` (riir-ai), Clifford-wedge `retrieve_diverse`
  (selection, not fusion — include for completeness). **DONE 2026-09-16 `ee6993a77`** —
  Research 560 addendum, all 6 found (two location corrections: `frozen_attractor` +
  `retrieve_diverse` ship in riir-neuron-db, not where the census hinted; the gauge LAW
  is upstream here in `katgpt-sparse/src/sparse_task_vector.rs:318-396`). Verdicts:
  blend INADMISSIBLE (extensivity + fixed-λ: gates per-archetype-frozen,
  content-independent ACROSS constituents) · tpr PARTIAL (associative-by-law, structure
  via role bookkeeping — F3 as predicted) · frozen heal INADMISSIBLE-as-composer
  (restore op; DSOM mode is disagreement-magnitude-aware but magnitude-only,
  daughter-asymmetric) · Raven sleep/EMA INADMISSIBLE (exactly the paper's mean-pooling
  class; `density_aware_wake`'s own doc states the fixed-mixture property) · gauge
  compose INADMISSIBLE (free-Λ linear mixture + untied daughter weights = planar fold;
  the cancellation prune is a real nonlinearity but grouping-invariant) · wedge
  `retrieve_diverse` N.A.-not-a-composer (inverted: EXPOSES constituents). Closing
  verdict: the census finding SURVIVES code-level scrutiny, sharpened by the theorems —
  the two nearest neighbors (gauge compose, DSOM heal) each hold exactly one Meld
  ingredient while lacking the other three. Surprise: Issue 618's drift ledger is a
  natural F6 (KG provenance) hook beside the grouping-blind composite.
- [x] T3 — `meld` primitive prototype behind opt-in feature `meld` (katgpt-core, near
  `committed_field_blend.rs`): **DONE 2026-09-16 `43f15f7c8` (module+bench) +
  `f314d5006` (feature/lib.rs wiring)** — [Bench 801](../.benchmarks/801_meld_goat.md).
  `MeldCompose<const D>`/`MeldLaw {Tanh, DivisiveNorm, Linear=law-8}` + `no_w`
  ablation + `lambda_star_into` (the T4(c) disagreement trace); closed-form quadratic
  λ⋆ (disc = 4(4−t²), stable root, candidate enumeration, bit-exact commutativity via
  canonical (hi,lo) ordering); normalized-Hadamard W (in-place FWHT, 1/√D); zero-alloc
  fixed-size. DN deviation (documented): `y/√(ε+Σy²)` not `y/√(ε+Σy²/D)` — the spec's
  form is bounded by √D and cannot meet the depth-64 |coord|≤1 gate; shipped form is
  the Carandini–Heeger standard, hard |out|≤1. Self-tests ALL PASS: commutativity EXACT
  bitwise (4800 cases), non-associativity 512/512, λ⋆ vs brute force ≤3.24e-7 (f64
  referee), boundedness depth-64, disagreement-coding limits, W orthogonality, β
  limits. 2067/0 with the feature; combo+bf16 2077/0; wasm32 clean; clippy clean.
  **RED FLAG carried honestly (Bench 801)**: the paper's quality ladder did NOT
  reproduce on our D=32 fixture — tanh-meld 0.380 at d=5 vs law-8 0.870 (paper:
  meld ≥ law-8); mean does NOT collapse on full-vector nearest-centroid for ordered
  leaves (per-leaf depth weights are tree-dependent; the blindness theorem is about
  the S₂/D_eff readout); no-W collapses HARDER than paper. T4 sharpened accordingly.
- [ ] T4 — PoC in `riir-ai/crates/riir-poc` (§3.6 discipline, three competitors):
  meld vs frozen/no-adaptation baseline (mean) vs role-explicit composer (tpr with
  tree-position roles) on a controlled toy domain (synthetic hierarchical experience
  stream, depth 2–8 bracketings, nearest-centroid decode, 60 seeds — mirror the paper's
  regime). Measure: (a) bracketing-recovery accuracy at each depth; (b) **PR readout
  discipline (§9.2)**: participation_ratio of the SQUARED-AMPLITUDE
  distribution p̂_ℓ = a_ℓ²/Σa_ℓ² over atom-direction projections (deterministic vectors
  give PR = exp(3S₄−2S₂), NOT exp(S₂) — the paper's own honesty; measure the right
  quantity, don't assume the clean identification); (c) disagreement-trace utility
  (contradiction detection vs mean-smoothing). Print the verdict table. **PoC defends
  OR refutes** — if meld loses to mean on (a) at all depths, record the refutation in
  Research 560 §"PoC Addendum" and close this issue NEGATIVE; the audit (T2) survives
  regardless (framework-level finding).
  **SHARPENED by Bench 801 (2026-09-16) — T4 is now the SOLE adjudicator and MUST:**
  (1) **scan the tanh operating point first** — at unit-RMS atoms + κ=2 the mixture
  sits in tanh's amplification region; the paper's population regime may normalize
  differently (candidate lever: atom scale sweep, or DN law which is scale-normalizing
  — Bench 801's DN arm is the natural first comparator); (2) the bracketing-separation
  claim MUST be adjudicated on the **S₂/D_eff (PR over squared amplitudes) readout**,
  NOT full-vector nearest-centroid alone — Bench 801 showed ordered leaves separate
  same-multiset bracketings at the full-vector level via per-leaf depth weights, so
  that axis falsely exonerates mean-pooling; (3) include same-multiset restricted
  contrasts on the statistics readout; (4) keep law-8 in the comparison — it BEAT
  tanh-meld at depth on our fixture, and the paper itself calls saturation
  boundedness-only; if law-8 + the PR readout is the configuration that separates,
  the extraction is still real (boundedness is a Pod-safety wrapper, not the quality
  axis).
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
