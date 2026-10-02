# Bench 906 — Plan 615 Phase 2: Two-Fidelity Certified BAI GOAT gate — **GOAT FAIL on G1** (certificate invalidity)

**Bench:** `benches/bench_615_two_fidelity_bai_goat.rs` (`harness = false`, `required-features = ["two_fidelity_bai"]`; run: `cargo bench -p katgpt-core --features two_fidelity_bai --bench bench_615_two_fidelity_bai_goat`)
**Plan:** [615_two_fidelity_bai.md](../.plans/615_two_fidelity_bai.md) · **Issue:** [915_two_fidelity_cert_interval_invalid.md](../.issues/915_two_fidelity_cert_interval_invalid.md) · **Research:** 601 · **Paper:** arXiv:2606.01708
**Date:** 2026-10-02 · **Box state:** M3 Max (16-core aarch64), macOS 26.6.2, AC power, release profile; run under light concurrent sibling load (editor build) — ALL REPORTED METRICS ARE SAMPLE/COST COUNTS, NOT WALL-CLOCK (the unified cost model `cost = n_fast + c·n_slow` is load-independent by construction; G4 alloc counts likewise).

## Verdict

**GOAT FAIL — on G1, not G2.** The G1 certificate arm found that `two_fidelity_search` returns **certified root intervals that systematically exclude the true minimax value** on the paper's own fixture family, and the empty-intersection guard fires at ~60% (δ budget: 5%). A certified-search primitive whose certificate body is invalid has no product; **G2 paired wins observed in the same runs are moot** (a certified wrong answer is not a result). Issue **915** carries the evidence, the fixture-honesty verification, and the deterministic reproduction (`B615_DEBUG=1 B615_TREES=8`, seed `0x615_0007` at (5,8)). The module stays opt-in (never left it); Phase 3/4 stay gated; **this bench is the re-arm gate.**

## What the gate arms measured (all landed and passing mechanically)

| arm | result |
|---|---|
| CANARY gate-machinery-fires / CP closed-form / alloc-counter-moves | ✓ ✓ ✓ (impossible floors proven to fire) |
| SANITY T2.2b (negamax-UCT adapter, zero-noise D3b3 convergence) | ✓ — \|V̂−V*\| = 0.0000 at 1k/10k/100k budgets, pick exact |
| G4 alloc linearity (3 searches == 3 × 1 search, 1 search ≤ 4) | ✓ — 2 allocs/search (node HashMap + result Vec), zero per-iteration |
| G2 paired win vs BAI-MCTS (LB95 > 0 per setting) | ✓ observed (see numbers) — **MOOT while G1 fails** |
| G2 paired win vs negamax-UCT at matched accuracy | ✓ observed — **MOOT while G1 fails** |
| **G1 empirical PAC (CP95 ≤ δ on picks)** | **✗ FAIL** (6/40 errors at (5,8), ε = 0.02 → CP95 upper ≫ δ) |
| **G1 certified-interval validity** | **✗ FAIL** — 42+ certified intervals exclude V* over the shakedown |
| **G1 guard-fires within the δ budget** | **✗ FAIL** — 24/40 uncertified at (5,8) vs δ = 0.05 |

## Protocol

Settings (D,b) ∈ {(5,8),(7,6),(10,3)} (paper §4 parity), ε = 0.02, δ = 0.05, c = 4, σ = 0.05 (slow noise uniform ±0.05 — declared σ ≥ 0.05/√3, loose-honest), fixture envelope **B(h) = 0.12·(1 − 2^−h)** — the trait contract shape (B(0) = 0, leaf fast oracle exact, nondecreasing in remaining depth), adversarial per-tree bias sign chosen to flip the depth-limited fast-only root pick (achieved on 31/40, 39/40, ~5/8 of trees per setting — the two-oracle race is forced). Ground truth: exact f64 minimax fold; fixture honesty verified node-by-node at every failing tree (`max |fast − V*| ≤ envelope` everywhere; interval misses are 1e5× above f32 noise). `B615_TREES` env shrinks the suite for shakedowns; the shipped default is the plan's 100 trees/setting. The 40-tree diagnostic run below is the evidence run — a full-protocol run is not owed while G1 fails (the gate stops at the first failing arm class).

## Measured numbers (40 trees/setting diagnostic run, current build)

### (D=5, b=8) — complete

| arm | errors | cost mean (unified) | notes |
|---|---|---|---|
| **2FFS** | 6/40 | **689** (fast 666, slow 6) | cert 16/40 — 24 guard-fires; certified intervals invalid on 24 trees (42 interval misses incl. D=7) |
| BAI-MCTS (LUCB) | 24/40 | 10 401 | 0 capped; the baseline shares the failure regime (see below) |
| negamax-UCT | 21/40 at every checkpoint 4k→8.4M | n/a (budget-exact) | errs plateau = the same stale-estimate class, not noise |
| fast-only (depth-2 truncation) | 31/40 | 37 449 | the adversarial arm did its job |
| slow-only (level-2 frontier) | 28/40 | 307 712 | cheap + badly truncated |

Paired LB95 (2FFS cost advantage): vs BAI ≈ 9 700 > 0 ✓ — moot per the verdict.

### (D=7, b=6) — run in progress at record time; diagnostics already decisive

Same failure signature from the first trees: `t0` nodes 1–5 certified-invalid
(misses 0.06–0.09), `t1`, `t2` (TIGHT intervals, width 0.024, still missing by
0.006 — deep resolution does not repair containment), `t5`, `t7`, `t9` — 26+
certified-invalid intervals at this setting alone.

### Paper-parity context rows (their numbers, their protocol — context only)

| setting | paper 2FFS samples | paper BAI-MCTS samples | paper ratio | paper ops ratio |
|---|---|---|---|---|
| (5,8) | 5.39e3 | 8.80e5 | 163× | 2.84× |
| (7,6) | 1.77e4 | 1.75e7 | 988× | 4.58× |
| (10,3) | 1.31e4 | 1.91e7 | 1458× | 1.86× |

(Paper accuracy 1.00 everywhere — which our measured G1 refutes for the
v1 implementation on honest contract-shaped envelopes. The parity claim
cannot be adjudicated until the certificate defect is fixed; re-run the
bench for the claim rows.)

## The finding in one paragraph

On contract-honest fixtures (verified per-node), the search returns
`certified = true` with root intervals whose upper endpoints sit BELOW the
true minimax values (always `true > hi`; misses 0.013–0.078), and ~60% of
searches hit the empty-intersection guard instead (B.3 default action) —
both classes far outside the δ = 0.05 budget, at every setting, with
deterministic per-seed reproduction. Every component interval provably
contains its node's V* under an honest envelope, so the fold is losing
containment somewhere in the ρ_k-ladder / blocking-child / lazy-discharge
machinery — the T1.5 "all-live-children recursion" v1 divergence, recorded
at landing as "cost-character only, PAC never weakened", is the natural
suspect and is now **refuted by measurement**: the divergence is
correctness-character on gapless fixtures. Full evidence + the working
hypothesis: **Issue 915**.

## En-route findings (filed, not fixed here)

- The module's own `VecTree` test fixture contradicts the trait contract it
  documents: its envelope `bias_scale·2^−h` is DECREASING in remaining depth
  with B(0) = bias_scale ≠ 0, while the trait doc pins B nondecreasing with
  B(0) = 0 (leaf-exact). The 32-tree PAC smoke passes under a 0.3 root gap —
  a regime where the defect cannot fire. Both belong to the Issue-915 fix.
- The baselines' backup scheme needed the sample-max/min extreme form: raw
  path-averaging collapses to the subtree mean on uniform alternating trees
  (measured: frozen exactly at the subtree-mean offset at 1k/10k/100k
  budgets), and explore-first must win in each node's OWN direction
  (−INF at Min nodes) or Min subtrees lock onto their first-visited child.
  Both lessons are pinned by the SANITY arm + recorded in the bench header.

## Re-arm procedure

1. Fix the containment defect (Issue 915 owner/fix session).
2. `cargo clippy -p katgpt-core --features two_fidelity_bai --all-targets -- -D warnings`
3. `B615_TREES=8` shakedown: SANITY ✓, G1 all arms ✓.
4. Full protocol run (default 100 trees/setting): ALL GATES PASS is the GOAT
   verdict; G2 rows become claimable then (vs the paper's 163–1458× class).
5. Only after a GOAT PASS: Phase 3 consumer seams (T3.1–T3.3) + Phase 4 docs.
