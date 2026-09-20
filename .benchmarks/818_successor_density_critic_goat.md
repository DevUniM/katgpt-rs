# Bench 818 — `successor_density_critic` GOAT (Issue 860)

**Date:** 2026-09-20
**Primitive:** `crates/katgpt-core/src/successor_density_critic.rs` — the tabular, modelless CRL extraction (riir-ai Research 386; arXiv:2206.07568 Eysenbach et al.): count-based closed-form estimator of the CRL log-density-ratio goal critic `f*(s,a,g) = log p(s_{t+}=g|s,a)/p(g)` over dense `[S][A][S]` weighted-count tables, BLAKE3-committed freeze/thaw (the `contrastive_scope` pattern), deterministic zero-variance successor samplers, `argmax_a`/`argmax_g` (goal salience), sigmoid link (Bench 048; sigmoid never softmax). Opt-in feature `successor_density_critic`; **stays opt-in** — GOAT passed, but promotion to default additionally requires a live consumer (riir-ai Issue 991 goal salience / riir-train Plan 413 tabular arm, both pull-gated), and this is a NEW slot (goal-conditioned critic) with no incumbent to demote.

## Verdict

**GOAT PASS — G1a/G1b/G1c/G1d/G2/G3a/G3b/G3c/G4 all green** (release profile, `--features successor_density_critic,alloc_tracking`).

| Gate | Result | Bar |
|---|---|---|
| G1a exactness | max \|empirical − analytic\| = **0.00841** | ≤ 0.01 vs the behavior-continued Bellman measure (32-ring, 200k-step seeded walk) |
| G1b ranking | argmax_a == exact argmax on **128 decisive (s,g)** of 32×32 | decisive = exact gap ≥ 0.02 (≫ noise); near-ties counted, never folded |
| G1c Lemma 4.1 | goal-prior perturbation ×0.001/×3.7/×1e6 leaves argmax_a **bit-identical** | executable property, both sides on the same f64 formula path |
| G1d determinism | identically-seeded rebuild → **byte-identical** freeze | fixed accumulation order |
| G2 lookup | score **0.9 ns**, argmax_a **4.3 ns**, argmax_g **44.0 ns** | absolute budgets 50/500/500 ns (best-of-50 minimum) |
| G3a structure | uniform-prior argmax_g == raw conditional argmax (all 24) | the prior term is the score's ONLY extra correction |
| G3b prior bites | empirical prior moves **21** goal-salience argmax_g | ≥ 1 (the correction is load-bearing on the fixture) |
| G3c ranking | critic discordances **0**, raw-count discordances **95**, over 1854 enforced pairs | critic tracks the exact measure where raw joint counts invert |
| G4 alloc-free | **0 allocs / 0 bytes** over 10 000 mixed read calls | CountingAllocator, `--release --features alloc_tracking` |

Dev-profile run (same gates): score 15.7 ns / argmax_a 73.9 ns / argmax_g 340.5 ns, wall 809 ms — all green. Release wall **61 ms**.

**Box state** (AGENTS.md: a latency number without its box state is not a measurement): M3 Max, on battery (charging), one sibling agent session active (repo-sync greps — no compute load), no GPU work in flight. `CARGO_TARGET_DIR=/tmp/katgpt-860` (sibling-build isolation; removed after the run).

## The oracle that had to be right first (the finding of this bench)

The first G1 draft compared against a **closed-form "greedy-action-repeat" measure** (stay → point mass, step → geometric in distance). It was the wrong oracle and the gate caught it: the estimator conditions on the observed `(s, a)` and continues along the **behavior policy** — a stay transition whose trajectory later leaves the state DOES assign far mass to other goals (empirical `P(1|0,stay)` ≈ 0.5, not 0). The correct target is the Bellman fixed point

```
P(g|s,a) = (1−γ)·1[s'=g] + γ·Σ_a' π(a'|s')·P(g|s',a')
```

computed by iteration (γ = 0.5 → contraction 0.5; 300 sweeps converge far below f64 resolution). The module doc carries the conditioning caveat (Lemma 4.1's identity is w.r.t. the goal-averaged policy — the Research 386 honesty note). Lesson: an exactness gate is only as good as its analytic target; the closed form must answer the SAME conditioning question as the estimator.

## The two-fixture G3 split (why γ appears twice)

The raw-count baseline (joint counts) inverts where (s,a) visitation skews the joint away from the conditional — but WHERE the ratio's two corrections bite depends on the fixture:

- **G3c (visitation inversion) at γ = 0.5:** the conditional ladder is 2× per step, so exact values sit far apart (rarely excluded as near-ties) and the visitation-vs-conditional inversions land on ENFORCED pairs (95 of 1854). Critic: 0 discordances.
- **G3b (prior bite) at γ = 0.9:** goal-salience `argmax_g` flips only when the goal-prior skew outruns the top-vs-runner-up conditional gap. At γ = 0.5 the 2×-per-step ladder (top-vs-runner 3.5–140×) always outruns the ~30× prior skew (prior(0) = 0.816 vs 0.027 elsewhere under the 0.98-stay sink) — measured: **0 flips**. At γ = 0.9 the ladder flattens to ≈1.11× per step and **21 of 24** queries flip. The prior-corrected salience is the riir-ai 991 readout, so the gate proves the correction is live, not decorative.

## Design notes (recorded per the issue's honesty clauses)

- **Sampler default is `Discounted`, not `CLearning`.** The deterministic expectation form of the paper's §3 geometric hindsight sampler is exactly consistent with the discounted measure the G1 oracle checks; the App. D C-learning blend re-weights the horizon by design (w_next = (1−γ)/(2−γ), far arm (1−γ)γ^(j−1)/(2−γ), per-update mass → 1 as the horizon grows), which trades away that consistency. The blend ships as a parity variant (`SamplerKind::CLearning`, requires γ > 0 — no far future exists at γ = 0) with its own unit test; the exactness gates pin the default.
- **Reverse sweep, not the naive walk:** successor mass for all T transitions lays down in ONE backwards pass — O(L·G) total, deterministic accumulation order. The fold is `f ← γ·f; f[states[i+1]] += 1` — EVERY entry decays by γ (the first draft folded only the single next entry and overcounted far mass on stale goals; the hand-computed unit tests missed it because their fixtures had only ONE distinct far state — the 4-ring G1 against the iterated oracle caught it).
- **Fractional (f64) counts**, committed at full bit precision — the sampler weights are fractional, so `contrastive_scope`'s u32 count cast would round them away. Freeze layout documented at [`SuccessorDensityTable::freeze`]; thaw refuses unknown sampler bytes, wrong lengths, and S·A·S mismatches.
- **`laplace_log_ratio` is a pure pub fn** — the Lemma-4.1 invariance test perturbs marginals through the SAME arithmetic the builder uses, and consumers/benches reuse one formula instead of re-deriving it.
- **Substrate-first diff** (recorded in the issue, verified by grep): `contrastive_scope` (word log-odds, no action axis), `occupancy::LogRatioClass` (no trajectory/discount structure), BM25 (no co-visitation/discount), `conditional_dependence_infonce` (NCE as a CI test, not a value function), `best_belief` (no (s,a) conditioning) — none combines action-conditioning + discount + ranking-for-control. New slot; feature-gated per discipline.

## Commands

```bash
cargo bench -p katgpt-core --features successor_density_critic \
    --bench bench_818_successor_density_critic_goat
cargo bench -p katgpt-core --features successor_density_critic,alloc_tracking \
    --bench bench_818_successor_density_critic_goat
cargo test -p katgpt-core --features successor_density_critic --lib -- successor_density
```

## Validation at landing

- `cargo clippy --lib --features successor_density_critic -- -D warnings` — clean
- `cargo clippy --lib --all-features -- -D warnings` — clean
- `cargo test -p katgpt-core --lib` — 2063 passed (floor 2030 held; +12 new tests)
- `cargo test -p katgpt-core --lib --features successor_density_critic` — 2075 passed
- GOAT bench at dev AND release (`alloc_tracking`) — all 9 gates green
- ⚠ Per AGENTS.md this is a per-crate claim, not a whole-repo green: the root package's targets and the wasm32 lane are not re-asserted by this change (the new module is std-only, no cfg-gated arch arms, no wasm-incompatible deps — the feature compiles to nothing when off).
