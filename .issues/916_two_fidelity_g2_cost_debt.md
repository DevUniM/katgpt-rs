# Issue 916 — two_fidelity_bai G2 cost debt: δ/node_cap dilution + a non-δ-correct BAI baseline

**Status:** OPEN — cause (a) LANDED 2026-10-03 (commit `3aa27c149`, rebased over the 617 lane); cause (b) OPEN (cost attribution measurement + fix). G1 certificate arms PASS (the 915 defect is gone); G2(a) reads a massive PASS against the corrected baseline (shakedown: the δ-correct LUCB-MCTS caps all 8 trees at every setting — 30M samples = 120M unified — LB95 ≈ +120M/setting vs 2FFS ≤ 1M).

**Parent:** Issue 915 (closed: the certificate invalidity was a BENCH fixture bug — internal slow samples centered at 0.0 — not a module defect; mechanism + fix in git history and `.benchmarks/615_two_fidelity_bai_goat.md`).

## Evidence (re-arm shakedown, `B615_TREES=8`, post-915 fixture fix, 2026-10-03)

| setting | 2FFS errs / cert | 2FFS cost (fast / slow) | BAI errs / capped | BAI cost | UCT B* |
|---|---|---|---|---|---|
| (5,8)  | 0/8, **8/8 certified** | 225 386 (616 / 56 192) | **4/8 errs**, 0 capped | 10 817 | 33.5M (no match) |
| (7,6)  | 0/8, **8/8 certified** | 987 702 (1 647 / 246 514) | **4/8 errs**, 0 capped | 5 342 | 33.5M (no match) |
| (10,3) | 0/8, **8/8 certified** | 574 838 (520 / 143 579) | **3/8 errs**, 0 capped | 3 840 | 33.5M (no match) |

G1: certificate-validity 0 invalid (was 42+), guard-fires 0/24 (was 24/40), picks 0/24 errors (CP arm needs n ≥ 59 to certify δ at zero errors — the full n = 300 run passes by construction; the 8-tree shakedown cannot, so the record's "shakedown: G1 all arms ✓" expectation was arithmetically wrong for that one arm).

## Cause (a) — RESOLVED: the BAI-MCTS baseline was not δ-correct as implemented

The in-bench BAI arm = LUCB stop at the root over the SHARED UCT engine's sample-max/min point backups. It stopped (0 capped) while erring 4/8, 4/8, 3/8 — three orders above δ = 0.05. The root-arm radii only cover arm-level sampling noise; the extreme-backup bias (`E[max of noisy means]` optimistic at Max nodes, disclosed in the bench header) is NOT covered, so the stop fires on miscalibrated intervals. **Fixed** (commit `3aa27c149`): the arm is now the LUCB-MCTS/UGapE-MCTS bound-propagation class — per-leaf time-uniform slow CIs through the module's own `NodeInterval` machinery (same β/δ_v rule as `two_fidelity_search`, fairness: the baseline shares 2FFS's confidence machinery, isolating the two-fidelity mechanism), Eq. 6 bound propagation (internal (L, U) = max|min child L/U, unrevealed children at the neutral sentinel), optimistic binding-child descent, root LUCB ε-stop, deterministic leader-L/challenger-U alternation. Module support: `NodeInterval::slow_only()` (the oracle-less carrier). Divergences from KKC documented at the site.

Shakedown verdict vs the corrected baseline (`B615_TREES=8`): **the δ-correct LUCB-MCTS CAPS all 8 trees at every setting** — 30M samples = 120M unified cost — because the leader's L at a Min arm needs the full b-ary fan-out (8·8 Max@1 nodes at (5,8), each with a CI-converged leaf chain) before it rises off −∞, and the U-side fans out at Min nodes symmetrically; ε = 0.02 tightness then needs ~2 000 diluted-δ samples per binding leaf. G2(a) reads **LB95 ≈ +120M per setting** (cap = the conservative understatement, the same convention as the UCT no-checkpoint-matched row); 2FFS rows bit-identical to the pre-fix run (determinism across builds confirmed). Disclosure for any claim built on this: the paper's own BAI instance stops at 8.8e5–1.91e7 samples where ours caps at 3e7 — our instance is the conservative member of the class (diluted uniform per-leaf δ + deterministic alternation), so a G2(a) win measured against it is an UPPER bound on the ratio vs a better-tuned instance; the paper's own numbers stay the cross-implementation context rows.

## Cause (b) — the primitive's own cost: ~10× the paper's sample count, attribution UNMEASURED

The (5,8) tree spends 56 192 slow samples; the paper's 2FFS uses 5.39e3 on this setting — ~10×. **Do not build on the first attribution written here**: the initial draft blamed the uniform `δ / node_cap` dilution; the closed-form arithmetic refutes that as the DOMINANT term. At an ε-driven width target w = 0.02 (σ = 0.05), n ≈ 8σ²·ln(2n_k/δ_k)/w² ≈ 50·L: the diluted δ_v = δ/65536 (δ_k ≈ 1e-12 at n ≈ 2000) gives L ≈ 35 ⇒ n ≈ 1800, while an undiluted δ_v ≈ 0.01 gives L ≈ 25 ⇒ n ≈ 1300 — a **~1.4× factor**, real but secondary. The remaining ~7× must live in the RESOLUTION PATTERN — which nodes the recursion certifies and to which widths (the ρ_k ladder + blocking-path descent) versus the paper's — and that is a measurement question, not an arithmetic one.

First step for any attack: per-node sample accounting in a diagnostic run (`B615_DEBUG`-style dump of (node, slow_n, width target, scale k) at search end), compared against the paper's Figure/Table cost decomposition (Research 601 §allocation). Then the candidate levers, in order of safety:

1. **Depth-budgeted a-priori δ allocation** — δ split over depth levels (each level's mass uniform over that level's full a-priori node count b^l — union-bound-safe for ANY adaptive sampling on balanced trees, Σ_l δ_l = δ). Sound, but the arithmetic above prices it at ~1.4× — take it only if the measurement shows the ln term matters at the actual width targets.
2. **The paper's own allocation** (Eq. set around Thm 3.6) — re-read Research 601 §allocation for the exact scheme; if it allocates over the RESOLVED set, port it verbatim with its own union proof, never ad hoc.
3. **Race-budget / width-target shape** — if the measurement shows the recursion is driving some nodes to far finer widths than their side needs (e.g., m_samples(rho/2) targets much finer than the stop rule consumes), that is a v1-divergence cost bug, the cheapest class to fix.
4. NOT sound: allocating over the runtime-revealed node count (post-hoc δ division breaks the union bound — the sampled set is outcome-dependent).

## What this issue owns

- [x] (a) Rebuild the in-bench BAI baseline as the δ-correct bound-propagation class — LANDED `3aa27c149`; G2(a) re-judged against it (shakedown PASS; the full-protocol run is the recording run).
- [ ] (b) Tighten/attribute the 2FFS cost — measurement first (per-node sample accounting at `B615_DEBUG`-style granularity), then the lever the measurement names. Behind a **new opt-in config knob** if it changes the confidence allocation (never a silent change), with the union proof in the doc comment and the coverage pre-arm extended.
- [ ] Re-arm: `bench_615_two_fidelity_bai_goat` full protocol (100 trees/setting) under the corrected baseline — in flight at the time of this edit; its ALL-GATES-PASS is the GOAT verdict for plan 615 Phase 2 and un-gates Phase 3/4.

## What this is NOT

- NOT a correctness finding: every certified interval in the shakedown contained V* (the 915 defect is gone); 0/24 pick errors.
- NOT a promotion candidate either way: the module is opt-in by design (certified-search slot).
