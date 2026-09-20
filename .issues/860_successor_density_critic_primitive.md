# Issue 860 — `successor_density_critic`: tabular discounted count-ratio goal-critic (modelless)

**Status:** LANDED 2026-09-20 (Bench 818 GOAT PASS — all gates green at dev AND release). T5 remains open as the consumer pull-gate (riir-ai Issue 991 / riir-train Plan 413 — the primitive is DONE; consumers file their own lanes and the promotion decision rides them).
**Filed:** 2026-09-20 · Research: [riir-ai Research 386](../../riir-ai/.research/386_Contrastive_RL_Goal_Conditioned_Value.md) · arXiv:2206.07568 (CRL, Eysenbach et al.) — No-GD-track extraction

## The primitive

In countable `(s, a, g)` domains the CRL critic's Bayes-optimum is a **log density ratio** (paper §4.2, Ma & Collins NCE consistency): `f*(s,a,g) = log( p(s_{t+}=g | s,a) / p(g) )`. That admits a **count-based closed-form estimator** — no gradient descent anywhere:

```
score(s,a,g) = ln[ (N(s,a,g)+α) · N / ((N(s,a)+α) · (N(g)+α)) ]      // Laplace-smoothed log-count ratio
N updated by hindsight positives:  t ~ Geom(1−γ), goal = visited s_t  // the paper's §3 sampler
C-learning blend per update:  w_next = (1−γ)/(2−γ), w_far = 1/(2−γ)   // paper App. D, γ-derived
```

`argmax_a` and `argmax_g` over the score are ranking-preserved against the true Q up to the goal-only constant (paper Lemma 4.1: the constant "can be ignored when selecting actions"). This is the same statistical family as BM25/IDF (log-count ratios) with trajectory discounting added — the substrate-first diff below shows no shipped primitive combines action-conditioning + discount + ranking-for-control.

Consumers: riir-ai Issue 991 (per-NPC goal salience `argmax_g`), riir-train Plan 413 Phase 1 tabular arm (map_walk gridworld), any zone/item/rule-keyed goal selection.

## Substrate-first diff (recorded per the skill)

| Shipped cousin | Why it does not cover this |
|---|---|
| `contrastive_scope` (default-on, Bench 669) | static two-corpus **word** log-odds gate; no action axis, no γ, no ranking-for-control |
| `occupancy::LogRatioClass` | KL-projection density ratio over sample distributions; no trajectory/discount structure |
| BM25 (katgpt-core / riir-neuron-db) | single-corpus TF-IDF ranking; no co-visitation, no discount |
| `conditional_dependence_infonce` (katgpt-band) | NCE as a CI **test**; critic is an input, not a value function |
| `best_belief` / rating | per-candidate Bernoulli selection — no (s,a) conditioning |

Build new, feature-gated: `successor_density_critic = []` (opt-in; promote only on GOAT).

## Tasks

- [x] `crates/katgpt-core/src/successor_density_critic.rs` — fixed-capacity count tables (`N(s,a,g)` via bounded key maps or dense `[G][A]` over discretized s), `observe_trajectory` (hindsight geometric sampler, C-learning blend), `score(s,a,g)`, `argmax_a(s,g)`, `argmax_g(s,a)`; zero-alloc lookups, `#[repr(u8)]` config enums; sigmoid link for pairwise scoring (Bench 048: sigmoid reaches positive margin at d≈log n — and the paper's primary variant is sigmoid-NCE, not softmax). **DONE** — dense `[S][A][S]` f64 weighted tables; observation is ONE O(L·G) reverse sweep (not the naive O(L²)); samplers: `Discounted` (default — deterministic expectation form of the paper's §3 sampler, exactly consistent, G1-gated) + `CLearning` (App. D blend, parity variant, requires γ > 0). DIVERGENCE RECORDED: the blend is deliberately NOT the default — it re-weights the horizon by design and breaks exact log-ratio consistency, so the G1 oracle cannot certify it; the unit `trajectory_clearning_blend` test + the bench fixture carry it instead.
- [x] Freeze/thaw: BLAKE3-committed table snapshot, atomic reload (lock-free reads via immutable `Arc` swap — the contrastive_scope pattern). **DONE** — counts are f64 (fractional sampler weights), so they are committed at full bit precision, not cast to u32 like contrastive_scope's integer counts; thaw refuses unknown sampler bytes / wrong lengths / S·A·S mismatch.
- [x] Ranking-preservation unit test: perturb `p(g)` by any positive factor → `argmax_a` output bit-identical (the Lemma-4.1 law as an executable property). **DONE** — in-module `lemma_ranking_invariance_under_goal_prior_perturbation` (biases 0.001…1e6, both sides on the same f64 `laplace_log_ratio` path so rounding ties break identically) + bench G1c at 32-state scale.
- [x] GOAT gate + bench: **G1** tabular enumeration on a synthetic MDP — score within Laplace-smoothing error of the exact log-ratio; ranking == exact-Q ranking. **G2** µs-scale lookup (criterion). **G3** no-regression vs uniform-prior and BM25-style baselines on a goal-reaching ranking task. **G4** alloc-free (CountingAllocator, release). **DONE — ALL GREEN** (`.benchmarks/818_successor_density_critic_goat.md`, `harness = false` + absolute-budget G2, best-of-50 minimum, NOT criterion — the house GOAT shape). ⛔ THE ORACLE LESSON: the first G1 compared against a greedy-action-repeat closed form (stay → point mass) and the gate CAUGHT it — the estimator's conditioning is the paper's behavior-continued measure (`s_{t+}` drawn by continuing the data policy after (s,a)); the shipped oracle is the Bellman fixed point by iteration. Also measured en route: the reverse-sweep fold decays EVERY histogram entry by γ (first draft folded only the next entry; single-far-state unit fixtures could not see it — the 4-ring iterated oracle caught it), and G3 needed a two-fixture split (γ = 0.9 for the prior-bite: at γ = 0.5 the 2×-per-step conditional ladder outruns the ~30× prior skew, measured 0 flips; γ = 0.5 for the visitation-inversion ranking where raw-count inverts on 95 enforced pairs while the critic holds 0 discordances).
- [ ] Consumers wired: riir-ai Issue 991 goal-salience (opt-in feature forward), Plan 413 tabular arm. **OPEN — the pull-gate half:** both consumers file their own lanes at adoption; the primitive ships complete behind `successor_density_critic = []` and stays opt-in until one lands (per the feature-flag discipline, GOAT alone does not promote a new slot without a consumer).
- [x] Bench file `.benchmarks/NNN_*` + feature-flag discipline note (promote to default only on GOAT pass; this is a NEW slot — goal-conditioned critic — no loser to demote). **DONE** — `.benchmarks/818_successor_density_critic_goat.md` (highwater 817→818), README/examples count sites 623→624 (count_features.py green), catalog §118.

## Honest scope

- Sparse-cell cold start needs the α floor stated in G1; consistency is asymptotic in visits.
- Continuous obs is OUT (that's Plan 413's trained φ-encoder) — this primitive is countable-domain only.
- Lemma-4.1 caveat: the identity is w.r.t. the goal-averaged policy; the doc must carry it (Research 386 honesty note).
