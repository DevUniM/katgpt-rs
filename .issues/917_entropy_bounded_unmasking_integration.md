# Issue 917: EB-Sampler-Class Entropy-Bounded Commitment for D2F/DDTree/Drafter Commit Paths

**Status:** Open — T1 primitive LANDED 2026-10-03 (feature `entropy_bounded_commit`, opt-in) + T4 prior-art check DONE (HF transformers ships the entropy-proxy form; exact-parity test pinned); modelless oracle A/B MEASURED (Bench 917: no-stall everywhere; at equal validity EB needs 5–19% fewer NFE than the floored τ=0.9 incumbent, while shipped D2F τ stalls; the bound costs 16× on independent positions); T2/T3 lane wiring + the lane G2/G3 remain, blocked on a trained D2F checkpoint (riir-infer `gemma2_d2f` gates quality on `D2F_GOAT_TRAINED=1`); the checkpoint producer is riir-train Plan 437 (AR→diffusion conversion, Phase 4), staged with ALL phases owner-gated (4090 windows) — so T2/T3 inherit that gate. When Plan 437 Phase 4 yields a checkpoint, its decode is the natural T2 lane (the DiffusionGemma recipe already uses an entropy budget; A/B EB vs τ there). Gain-tier integration PoC (execution against a named published lineage; zero novelty claims)

**Source lineage (the controlling prior art):**
- Ben-Hamu, Gat, Severo, Nolte, Karrer (FAIR/Meta), ["Accelerated Sampling from Masked Diffusion Models via Entropy Bounded Unmasking"](https://arxiv.org/abs/2505.24857) (NeurIPS 2025) — the EB-Sampler: sort masked positions by an error proxy (entropy/confidence/margin), unmask the largest prefix whose `Σ H − max H ≤ γ` — a bound on the joint-dependence error (their Eq. 8). Measured 2–3× NFE reduction on LLaDa 8B / Dream 7B at quality parity.
- Same family: PC-Sampler (cumulative-entropy error tolerance), APD (adaptive per-step count), and the DiffusionGemma Technical Report's own algorithm (`Require: Entropy budget b = 0.1`).
- Composition into drafters is AUTHOR-SUGGESTED: EB-Sampler §7 — "Our EB-Sampler approach is complementary, and could be simply applied to speed up the draft model" (their spec-decode related work cites Christopher et al. arXiv:2408.05636, the DFlash precursor).
- Trigger source: the Srivastava essay ["Diffusion will be everywhere"](https://varunneal.github.io/essays/diffusion) (2026-09-27), whose appendix `entropy_bound` presents a prefix-sum variant (`Σ_{j<i} H_j ≤ τ`); full distill in `riir-train/.research/465_AR_to_Diffusion_Conversion_Essay.md`.

**Why this is an issue and not a novelty claim:** the verdict round-1 claim ("cumulative-entropy commitment is novel") was FALSIFIED by the reviewer's independent search under the correct vocabulary — recorded as the wrong-vocabulary lesson in Research 465 §4. What remains is execution: our shipped commit paths use fixed-k / per-position-threshold policies; the EB-class adaptive policy is absent workspace-wide.

## What we would build (modelless, zero training)

- [x] **T1** `entropy_bounded_commit` in katgpt-core (suggested home: `canvas/` or `speculative/`): given per-position entropies `H`, an error-proxy order, and threshold γ, return the commit set via the EB residual bound `Σ H − max H ≤ γ` (implement the EB form, not the essay's prefix form — the EB form carries the Eq-8 joint-dependence bound; the prefix form is the simpler, weaker heuristic). Zero-alloc, fixed-size, sigmoid-free (this is argmax/cumsum territory).
  - **LANDED 2026-10-03** — `katgpt-core/src/entropy_bounded_commit.rs` (feature `entropy_bounded_commit`, root mirror). `entropy_bounded_commit(candidates, entropy, key, γ, max_commit)` sorts the caller's candidate buffer under a strict `(NaN-last, key, index)` order and scans once with the exact incremental residual (`+= min(h, running max)` — the residual is monotone, so the largest admissible prefix ends at the first violation); `select_nth_unstable` + head sort under a cap; `position_stats{,_into}` gives entropy/top-1/margin per logits row via the shared `simd::logsumexp_parts` kernel; `ErrorProxy::{Entropy, Confidence, Margin}`. G1 (11 unit tests): no-stall on all-equal / one-dominant / degenerate-zero, brute-force `Σ−max` agreement over 500 random cases, cap ≡ full-sort prefix, NaN entropy and NaN/negative γ never commit, determinism across input permutations, exact HF parity. G4: `entropy_bounded_commit_alloc_check` — 0 bytes steady state; 64-candidate commit 0.76–0.96 µs full sort / ~250 ns capped at 8; stats 1.05–1.25 ms per 64×4096 block (M3 Max on AC, two runs — mean-of-1000 then `best_of_us` best-of-2000 — box shared with sibling sessions, `--release`; a range, not a figure). Catalog §141.
- [ ] **T2** Wire into the D2F decode commit (riir-ai `gemma2_d2f` lane's τ_conf site) behind a feature flag — A/B vs the incumbent per-position threshold.
- [ ] **T3** Wire into DDTree expansion order (best-first search already sorts by a proxy; EB's adaptive count replaces the fixed width-k) and the DFlash block commit (`dflash_predict`) — the drafter-composition the EB paper itself suggests.
- [x] **T4** Code-level prior-art check at PoC time: the ComfyUI-DiffusionGemma GitHub project surfaced during review — verify whether it implements the entropy-budget sampler before claiming any in-repo first (verdict reviewer's note; unverified as of filing).
  - **DONE 2026-10-03:** the sampler is upstream in **HF transformers** — `src/transformers/models/diffusion_gemma/generation_diffusion_gemma.py`, `EntropyBoundSamplerConfig(entropy_bound=0.1)` + `EntropyBoundSampler.accept_canvas`: entropy proxy only, sort ascending, accept where `cumsum(H) − H ≤ bound` (the EB form, docstring cites 2505.24857). `shanevcantwell/ComfyUI-DiffusionGemma` exposes it as widgets via its `EntropyBoundScheduler` compat wrapper; `exportAnything/ComfyUI-DiffusionGemmaPromptBuilder` and a Java port (`edwardcapriolo/deliverance`) consume the same config. So no in-repo first exists to claim, as filed. The T1 test `hf_entropy_bound_sampler_parity` pins exact agreement with HF's formula (500/500 random cases).

## Oracle-lane evidence (2026-10-03, Bench 917)

`.benchmarks/917_entropy_bounded_commit_goat.md` — exact oracle denoiser (uniform over a finite valid set; validity = joint-dependence error made decidable), deterministic. EB γ=0.1: validity 1.000 at 3.9 / 5.8 NFE on the dependent families vs fixed-k's k=1 at 16; vs τ=0.9 WITH a singleton floor 5–19% fewer NFE at equal validity over 3 seeds × 2 families; shipped D2F τ (no floor) stalls 2000/2000. Cost side, reported not hidden: on independent peaked positions EB γ≤0.3 needs 16 NFE where τ needs 1. The γ dial is flat over [0, 0.3] on these families — not calibrated by this bench. Not a promotion basis; the lane A/B must also report per-pass commit-count distributions.

## GOAT gate plan (for any future promotion)

- **G1 (guarantee correctness):** the no-stall property holds under adversarial entropy distributions (all-equal, one-dominant, degenerate-zero) — note this property is EB-Sampler's BY CONSTRUCTION (singleton U: `sum − max = 0 ≤ γ`, their Algorithm 1), so G1 asserts our implementation preserves it, it does not claim it as ours.
- **G2 (perf):** NFE / forward-pass count at equal task quality vs the incumbent fixed-k / per-position-threshold commit, at DDTree and D2F scales — the EB paper's own 2–3× is the external reference, our bar is a measured win on OUR lanes, not a reproduction of theirs.
- **G3 (no regression):** task quality at the matched-compute point ≥ incumbent (their Pareto claim, re-measured here).
- **G4 (alloc):** zero-alloc hot path preserved.

## Cousins (signal-diffs, kept separate by axis)

| Cousin | Axis | Diff |
|---|---|---|
| EB-Sampler (2505.24857) | MDM commit policy — the class source | We compose into drafter/DDTree paths; EB form adopted over the essay's prefix form |
| D2F τ_conf (Research 034, shipped) | Per-position remask threshold | Fixed per-position threshold vs adaptive cumulative budget |
| Research 243 Bebop | Step-level spec-decode acceptance forecast (γ adaptation) | Different mechanism axis: forecasts acceptance to size the verify budget; not a canvas commit policy |
| EntropyBifurcatedPruner (Research 164) | Entropy-routed screening strictness | Routes pruner strictness; not a commit-count policy |

**Filed:** 2026-10-03 · verdict path: spawn_agent fallback (primary reviewer rate-limited), 2 rounds REVISE→AGREE · related: riir-train Research 465, Plan 437
