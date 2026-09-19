# Bench 841 — legal-token-set enumeration + the restricted vocabulary projection

**Status:** ✅ PASSED 5/5 — **PROMOTED to default-on 2026-09-19**
**Issue:** [841](../.issues/841_cactus_sweep_follow_ups.md) §grammar-forced vocab-projection skip (Research 571 §B-8)
**Feature:** `legal_token_set` (root default-on; `katgpt-core` / `katgpt-pruners` / `katgpt-speculative` own defaults stay `[]`)
**Target:** `benches/bench_841_legal_token_set_goat.rs`
**Box:** M3 Max, macOS 26.6.2, 16 cores, 64 GiB — loaded (5+ concurrent agent sessions), on battery/charging.
⚠ Per AGENTS.md § *A latency number without its BOX STATE is not a measurement*: these are
interleaved medians on a **shared, loaded** box. The ratios are what the harness protects;
the absolute ns figures carry that load class and are not quiet-box numbers.

```bash
cargo bench --features legal_token_set,alloc_tracking --bench bench_841_legal_token_set_goat
```

---

## The finding, before the numbers

**Both halves of this lead already shipped, privately, and nothing joined them.**

- `LodestarAutomaton` holds δ as a dense row-major `n_states × vocab_size` table that names
  every legal token of every state — and exposes only `transition(state, token) -> Option`,
  a per-token point query. The row scan existed in two private precompute helpers
  (`compute_singular_span`, `precompute_distances`) and **threw the token ids away**.
- `katgpt-forward::cluster_head::fill_cluster_exact` is a gathered-row LM-head pass —
  literally *score only these vocabulary rows* — and was `pub(crate)`, reachable only
  through the cluster-shaped API, which picks the row list itself and never accepts one.

So every consumer asked validity the only way the API allowed. In
`build_dd_tree_lodestar` that is `for (i, &prob) in marginal.iter().enumerate()` calling
`horizon.is_valid(depth, i, parent_tokens)` — and `is_valid` calls `follow_path(parent_tokens)`
**inside every one of those calls**, so one heap pop costs **O(vocab × prefix)**. The builder
already carried a comment noting the same problem for `ln()` and had cached that; the
validity scan was the identical shape, uncached, next to it.

The substrate-first verdict is therefore *consume, do not build*: no new kernel, no second
enumerator. `CsrLegalSet` is generalised from the one shipped state→successor enumerator in
this repo — `bisimulation::graph::TransitionGraph` (`adjacency_window` + `for_each_adjacent`,
CSR + callback, allocation-free) — over token ids instead of operator labels, and
`restricted_lm_head` is a public wrapper over `fill_cluster_exact`, not a re-transcription of
a SIMD dot over scattered rows.

---

## Results

```
vocab 32768, n_embd 256, seq_len 6, tree_budget 64

G1 tree bit-identity   12 (degree x config) cells, 0 mismatched, fixture builds a tree: true  → PASS
G1 projection rows     64 selected rows bit-identical: true; unselected are -inf: true        → PASS

G2 tree build deg=1     enumerated  315523 ns, scanned  840921 ns →  2.7x  PASS
G2 tree build deg=8     enumerated  326690 ns, scanned 7314542 ns → 22.5x  PASS
G2 tree build deg=64    enumerated  327342 ns, scanned 6737667 ns → 20.6x  PASS

G2b projection crossover (gathered rows vs the dense pass)
   active   0.1% (    33 rows)  restricted      2923 ns, dense    350637 ns → 120.68x win
   active   1.0% (   328 rows)  restricted     16026 ns, dense    384498 ns →  23.57x win
   active   5.0% (  1638 rows)  restricted     88851 ns, dense    368004 ns →   4.49x win
   active  10.0% (  3277 rows)  restricted    154375 ns, dense    383692 ns →   2.48x win
   active  20.0% (  6554 rows)  restricted    492022 ns, dense    360738 ns →   0.75x LOSS
   active  40.0% ( 13107 rows)  restricted    591411 ns, dense    381542 ns →   0.66x LOSS
   active 100.0% ( 32768 rows)  restricted    583425 ns, dense    383915 ns →   0.67x LOSS
   measured crossover: the gather stops winning at ~20.0% active
G2b default threshold  max_active_fraction = 10% measures 2.48x  → PASS

G3 worst case (all 32768 legal)  enumerated vs scanned → 1.33x .. 3.46x (two runs)  PASS
G3 plan refuses gather at degree 32768: true                                        PASS

G4 alloc-free          enumerated 17 alloc(s) vs scanned 17 — the seam adds 0       PASS

G5 index memory
   grammar (deg 8)  csr        188 B on top of dense  1572864 B → + 0.01%
   wide (deg 2048)  csr      40988 B on top of dense  1572864 B → + 2.61%
   fully dense      csr     655388 B on top of dense  1572864 B → +41.67%
G5 worst overhead      +41.67% against a density/2 bound (+50% at full density)     PASS
```

---

## Reading the gates

### G1 — bit-identical, not merely equivalent

Both arms live in **one binary**. A feature flag gives you one arm per build, so the scan is
reached through a `ScanOnly` wrapper whose `legal_degree` returns `None` — which is the state
of every pruner that has not opted in, so the control arm is the real pre-change path rather
than a reconstruction of it.

Bit-identity is a *designed* property, not a lucky one: the
`ConstraintPruner::for_each_legal` contract requires **strictly ascending** token ids, which
is exactly the order `marginal.iter().enumerate()` visits. The heap therefore receives the
same pushes in the same order and the `f32` score accumulates the same way. The arms assert
`a.score.to_bits() == b.score.to_bits()`; a tolerance there would have hidden the loss of the
property the contract exists for.

18 further unit arms cover the axes the bench samples: `t21`/`t22` assert enumeration equals
the vocabulary scan over the **full product** of states × tokens (unbudgeted and budgeted),
`t28`–`t32` assert bit-identical trees under jump-ahead, A\*, five pruner budgets, and a
marginal shorter than the automaton's alphabet.

### G2b — the crossover was measured because the naive rule is wrong

"Smaller than the vocabulary, therefore gather" is the obvious rule and it loses above ~20%
active. `RestrictionPolicy::max_active_fraction` carries the threshold as **data** and the
gate is on the **shipped default**, not on the best cell: a default that admits a losing
gather is a default that has to move.

⚑ The measured ~20% independently reproduces the **21–34%** band Issue 661 measured for the
clustered head — a different kernel, a different caller, the same answer. That agreement is
worth more than either measurement alone, and it is why the default is set at 10% rather than
at the edge of the band.

### G3 — the worst case is faster, which is the mechanism showing through

Every token legal: enumeration names nothing the scan would not have found, and still walks a
32 768-entry CSR row. It is nonetheless **1.3–3.5× faster**, because the scan pays
`follow_path(parent_tokens)` inside all 32 768 `is_valid` calls while the enumeration pays it
once. So the seam has no measured regression regime, and the second half of G3 pins that the
*plan* still refuses to gather there — a degenerate legal set is precisely what the naive rule
gets wrong.

⚠ The two G3 figures (1.33× and 3.46×) are consecutive runs on a loaded box. Read the
**direction**, which is stable; the magnitude is not a quiet-box number.

### G5 — the cost of promotion, measured rather than argued

Promotion makes every `LodestarAutomaton` carry the index. Overhead is
`4·n_edges + 4·(n_states+1)` against `8·n_states·vocab`, i.e. **density/2**, bounded at +50%.
For the shape this exists for it is +0.01%.

---

## Promotion

`lodestar` is itself **default-on**, so the seam improves a path that already ships. With G1
bit-identical, G4 allocation-neutral, G3 showing no regression regime and G5 bounding the
cost, the GOAT rule's step 4 is satisfied and the gain is modelless (pure structure — no
training, no weights, no calibration). Promoted to the root crate's `default` set.

⚠ **What promotion does NOT do.** The two `ConstraintPruner` hooks default to `None` / no-op,
so a pruner that has not implemented them keeps the scan. `LodestarPruner` is the only
implementor today; `VocabChannelPruner` (whose `VocabChannelMap::layer_union` is already a
sorted token set) and any future grammar/JSON-schema pruner are the obvious next ones. The
`restricted_lm_head` half is **exported and tested but has no in-repo caller** — a real
forward pass with a grammar attached is a riir-ai-side wiring job, since that is where the
decode loop lives. Recorded here rather than implied by the green.

---

## Traps pinned as arms rather than prose

- ⛔ **The default `for_each_legal` yields nothing, and nothing is not the empty legal set.**
  A caller that reads the default as "no token is legal" prunes the whole tree and reports it
  as a clean result. `t09` pins that the distinguishing read is the *plan*
  (`Full { unenumerable: true }`), never the yield count, and `ProjectionPlan` keeps
  `Dead` and `Full{unenumerable}` unpooled for exactly this reason.
- ⛔ **A degree read off the raw transition row is a SUPERSET of what `is_valid` admits.**
  Under a pruner budget `is_valid` also rejects tokens whose successor cannot complete in the
  remaining steps, and the contract says the caller does not re-filter. Enumeration applies
  the budget through **one shared predicate** (`fits_budget`) — two transcriptions of a
  predicate are two chances to disagree. `t22` sweeps five budgets over the full product.
- ⛔ **The legal set is a property of the GRAMMAR, not of this position's marginal.** An
  automaton's alphabet can be wider than the model's vocabulary, so the `prob > 0.0` guard and
  the `marginal.get(i)` bound stay on both paths. `t32` builds against a marginal 8 wide with
  a 64-token alphabet; an unguarded index would panic on the fast path only.
- ⛔ **An out-of-range token is skipped, not clamped** (`r04`) — a clamp silently scores the
  wrong row.
- ⛔ **A restricted projection must fully overwrite its buffer** (`r06`). A reused buffer that
  leaked a finite logit from the previous position's legal set is a token the sampler can
  reach and the grammar forbids.
- ⚠ **The vacuity guard caught its own fixture.** The budget sweep's first cell (budget 2)
  admits nothing from the start state, and an earlier `assert!(!tree.is_empty())` failed
  there. The cell is **kept** — empty-vs-empty is where a wrong enumeration is easiest to
  miss — and the guard moved to the sweep TOTAL. Tuning a vacuity guard away is how a vacuous
  sweep gets to look green.

---

## One deliberate behavioural deviation, measured rather than hidden

`find_forced_token` used to `return None` the instant it saw a second valid token. The
callback form cannot `return` out of its caller, so it latches `branched` and the walk
continues doing nothing for the rest of the row. The **result** is identical (`t29`/`t30`
assert bit-identical trees under jump-ahead), and the **work** is bounded by O(deg) where the
original scanned the whole vocabulary — so the deviation is a strictly smaller loop in every
case except the degenerate all-legal one, which is exactly what G3 measures and finds
1.3–3.5× faster anyway. Recorded because "the loop no longer breaks early" is the kind of
thing that reads as a regression to the next person to open the file.

## What this does not measure

- **No real grammar.** The fixtures are synthetic DFAs with a chosen degree. The claim is
  about the *seam*; the speedup a given grammar sees is its own degree's business, and the
  bench sweeps degree rather than picking one.
- **No end-to-end decode.** `restricted_lm_head` is gated against `standard_lm_head` row by
  row, not inside a forward pass.
- **Quiet-box figures.** See the box-state note at the top.
