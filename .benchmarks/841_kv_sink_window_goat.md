# Bench 841 — KV permanent sinks + bounded window

**Status:** ✅ PASSED 5/5 — **NOT promoted** (opt-in `kv_sink_window`), and the reason is a
*missing measurement*, not a failing gate: see [Promotion](#promotion-is-blocked-by-a-corpus-not-by-a-gate).
**Issue:** [841](../.issues/841_cactus_sweep_follow_ups.md) §KV permanent sinks (Research 571 §B-8)
**Feature:** `kv_sink_window` (opt-in; requires `usage_rate_eviction`)
**Target:** `crates/katgpt-core/benches/bench_841_kv_sink_window_goat.rs`
**Box:** M3 Max, macOS 26.6.2, 16 cores, 64 GiB — loaded (concurrent agent sessions), battery/charging.
⚠ Per AGENTS.md § *A latency number without its BOX STATE is not a measurement*: the ns
figures are best-of-N minima on a shared box. G2's claim is a **shape** (flatness), which the
load cannot invent; the absolute ns carry the load class.

```bash
cargo bench -p katgpt-core --features kv_sink_window,alloc_tracking \
    --bench bench_841_kv_sink_window_goat
```

---

## The substrate correction, first

⛔ **The lead recorded this row as "Grep-clean today (nothing ships)" and that is wrong in the
direction that invites a parallel system.** `katgpt-core::kv_eviction` ships the entire
eviction apparatus (Plan 585, Research 523): usage-rate `mass/age` scoring, `UsageScoreTable`,
`select_evict_into(scores, k, pinned, out)` — **which already takes a pin mask** — and
`runaway_gate`, the promotion canary every lossy KV policy must pass.
`katgpt-attn::dash_attn::eviction_window` ships too.

What is genuinely absent is narrower and it is what this module is:

1. nothing **constructs** that pin mask — `select_evict_into` answers *"given k, which k
   rows?"* and nothing answered *"which rows must never be candidates?"*;
2. nothing supplies a **ceiling** — nothing answered *"what is k?"*, so live rows grew with
   the sequence.

`sink` as a concept had zero literal hits in either module. So this composes with the shipped
selector instead of replacing it, and `SinkWindowPolicy::UNBOUNDED` reduces to it index for
index (G3).

---

## Results

```
policy: n_sink 4, window 256, ceiling 260

G1 ceiling             20000 steps, peak live 260 vs ceiling 260
                       (0 breach, 0 sink loss, steady state AT ceiling: true)  → PASS
G1 memory              after 20000 tokens: 260 live rows vs 20000 unbounded
                       — 77x fewer, and CONSTANT in the sequence length

G2 per-step planning cost as the sequence grows
   seq   1000  unbounded    7042 ns/step   bounded  166 ns/step →  42x
   seq   4000  unbounded   23541 ns/step   bounded  166 ns/step → 142x
   seq  16000  unbounded   99833 ns/step   bounded  166 ns/step → 601x
G2 bounded flatness    16x sequence growth moves the bounded arm 1.00x (budget 2.0x)  → PASS

G3 reduction           UNBOUNDED vs select_evict_into: 0 mismatch over 13 k;
                       sink-only vs the same under its pin mask: 0                     → PASS

G4 alloc-free          0 alloc(s), 0 byte(s) over 2000 steady-state eviction steps      → PASS

G5 fidelity honesty    unknown d_max → Lossy; window < d_max → Lossy;
                       window >= d_max → Lossless; a scrolled-away sink is still a sink → PASS
```

---

## Reading the gates

### G1 — the claim is the ceiling, and it is asserted as a loop

20 000 steps of one-token-at-a-time admission against a **hostile scorer** that ranks the
sinks worst (−1.0) and the oldest rows best (`1e6 − pos`), so any policy ordering by score
alone evicts exactly the wrong rows. Peak live is **260 against a ceiling of 260**: not under
it by luck, exactly at it.

⚑ The second half of that gate is the one worth keeping: **the steady state must sit AT the
ceiling.** A policy that evicted everything satisfies `live <= capacity` perfectly, so a bound
alone is not evidence the policy is doing anything.

### G2 — flatness is the gate, not the speedup

The bounded arm measures **166 ns/step at every sequence length** — 1.00× drift across a 16×
growth — while the unbounded arm goes 7 µs → 100 µs. The 601× at seq 16 000 is a *corollary*
and is reported without being gated on, because the two arms do different amounts of work by
construction: that difference **is** the finding, so gating on its magnitude would be gating
on the fixture. The flatness cannot be manufactured by a loaded box.

### G3 — the off switch must not be a second code path

`UNBOUNDED` reproduces `kv_eviction::select_evict_into` **index for index** over 13 budgets,
on a score vector carrying ties, zeros, a NaN, an infinity and a negative zero. The sink-only
composition (`window = usize::MAX`, `n_sink = 3`) likewise matches the shipped selector run
under this module's own pin mask.

### G5 — the verdict this module must get wrong in only one direction

`fidelity(None)` is `Lossy`. Not knowing `d_max` is **not** evidence that the window clears
it, and the permissive reading here would exempt a real lossy surface from the runaway gate —
i.e. it would silently authorise the promotion that G5 exists to block.

---

## Two fidelity regimes, and only one is promotable

A bounded window is **not** automatically lossy. `katgpt-attn`'s `alibi_entmax_window_1p5`
(Issue 747, Research 549) derives a distance `d_max` beyond which entmax-1.5 attention mass is
**exactly** zero for an ALiBi head — evicting past it is bit-identical, not approximate.

| condition | verdict | consequence |
|---|---|---|
| `window >= d_max` | `Lossless { d_max }` | every evicted row carried exactly 0.0 mass; **not** a lossy surface, the runaway gate does not apply |
| `window < d_max`, or `d_max` unknown | `Lossy` | rows with real mass are dropped; the Plan-585 runaway gate on a sealed long-context eval is **mandatory** before promotion |

`d_max` is **caller-supplied, not imported**: `katgpt-attn` is downstream of `katgpt-core`, so
importing it is a dependency cycle. Same house pattern `kv_eviction` already uses for
attention mass.

⚑ This is the part that makes the primitive more than a re-implementation: it identifies a
**provably-lossless operating regime** for a mechanism everyone treats as inherently
approximate.

---

## Promotion is blocked by a CORPUS, not by a gate

All five gates pass and the gain is modelless. Promotion is still refused, and the reason is
a rule this repo already wrote down: `kv_eviction`'s own module docs state that **any lossy
KV policy promoted to default MUST pass the runaway gate on a sealed long-context eval**,
because aggregate perplexity stays flat while output length runs to the cap (the paper
measured 35–128× output/target blowups while SubEM read fine).

With an unknown `d_max` this is a lossy surface. **This repo has no sealed long-context
eval**, so the promotion is blocked by a *missing measurement* rather than by a failing one.
`kv_eviction::runaway_gate` is the instrument and it already ships; the corpus is the open
task. Recorded here rather than left as an inference from a green bench.

⚑ The `Lossless` arm is a separate, later promotion question with a *different* gate: a
consumer that supplies a `d_max` its window clears is not a lossy surface at all, and the
argument there is bit-identity, not a corpus.

---

## Traps pinned as arms

- ⛔ **A sink that has scrolled far outside the window is still a sink** (`w05`). The
  classification tests `Sink` FIRST and unconditionally; a window-first predicate classifies
  it `Stale` and evicts the system prompt at exactly the sequence length this policy exists
  for. The order is the guarantee.
- ⛔ **Stale rows go before window rows in a separate PHASE, not through a blended key**
  (`w12`). A row outside the window is *out of policy*, not merely low-scoring. One
  comparable number lets a high-scoring stale row survive, which makes the ceiling a
  numerical property instead of a structural one — and `w12` gives the oldest row a score of
  `1e9` to prove it still goes first.
- ⚑ **`w07` found a real defect at this module's own sentinel.** `UNBOUNDED` is
  `window: usize::MAX`, and the literal `distance < window` comparison classified exactly one
  representable distance (position 0 at `current_pos = u64::MAX`) as `Stale` — under the
  policy whose entire purpose is to classify nothing stale, because on a 64-bit target
  `usize::MAX == u64::MAX` and a window of `w` covers `0..w`. `usize::MAX` is now read as a
  sentinel. Found by an arm, not by reasoning.
- ⛔ **`current_pos - window` underflows** for every early position under a large window; the
  implementation compares a saturating **distance** instead (`w07`), and both sides are
  widened to `u128` so `usize::MAX as u64` cannot wrap on a 32-bit target.
- ⛔ **The two phases append to one buffer, so an overlap in the predicates would evict the
  same slot twice** and silently under-deliver the ceiling (`w19` asserts the output is a
  set).
- ⛔ **A corrupt score is never evicted first** (`w16`) — NaN orders last under
  `float_order::cmp_for_min`, the conservative direction, inherited from the shipped selector
  rather than re-decided.
- ⚠ **Two wrong test expectations were corrected, not the code.** `w10` demanded all four
  sinks be live at step 0, when only one token had been admitted; `w19`'s arithmetic said 15
  where 18 is right. Both were the test asserting its own arithmetic rather than the policy's.

---

## What this does not measure

- **No quality number at all.** Nothing here says a 256-token window preserves task
  performance — that is precisely what the missing long-context eval would answer, and its
  absence is why this is not promoted.
- **No real KV cache.** The arms operate on slot positions and caller-supplied scores; wiring
  to an actual cache (and to a mass producer) is consumer-side, which is `kv_eviction`'s own
  documented boundary.
- **The default `n_sink = 4`, `window = 256` are the LEAD's numbers**, not a measurement of
  this repo. A consumer should size `window` against its own recall and against `d_max` if it
  has one.
