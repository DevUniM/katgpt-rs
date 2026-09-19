# Issue 857 — the sealed long-context eval the runaway gate has no corpus for

**Status:** OPEN — filed 2026-09-19. Blocks the promotion of `kv_sink_window`
([Bench 841](../.benchmarks/841_kv_sink_window_goat.md), 5/5 PASSED, opt-in) and of every
future lossy KV policy. Not a defect: a **missing measurement**.

## The gap

`katgpt-core::kv_eviction` ships `RunawayStats` + `runaway_gate` (Plan 585 T2.1, Research 523,
arXiv:2608.19920) and its own module docs state the rule:

> **any lossy KV policy (eviction / quantization / compaction) promoted to default MUST pass
> this gate on a sealed long-context eval.**

⛔ **The instrument ships and the corpus does not.** So the rule is currently unfalsifiable in
both directions: nothing can pass it, and nothing that skips it can be caught skipping it.
`runaway_gate(stats, r_max, p_cap_max)` takes `RunawayStats::from_generations(output_lens,
target_lens, cap)` — three vectors nobody produces.

That is not hypothetical bookkeeping. It is the live blocker on a primitive that measured
5/5 the day it landed: `kv_sink_window` holds a hard ceiling (peak live 260 of 260 over
20 000 steps) with a flat 166 ns/step planning cost against 100 µs unbounded at seq 16 000,
and stays opt-in solely because no corpus exists to run the canary on.

## Why this canary and not perplexity

The failure mode is **length runaway**, and it is invisible to the metrics anyone would reach
for first. Under a train/inference attention mismatch, generation degrades into output
lengths the paper measured at **35–128× the target**, saturating the token cap — while
perplexity-style and tolerant substring metrics (SubEM) read FINE. `r_median` exposes the
length axis; `p_cap` exposes the saturation axis. A lossy KV policy promoted on a flat
perplexity is promoted on a metric that cannot see its failure.

This is the same shape as the Issue-750 lossy-surface rule already recorded in AGENTS.md
(*aggregate perplexity can be flat while family-conditional behavior flips*), one axis over:
there the hidden axis is the family, here it is the generation length.

## Tasks

- [ ] **Decide the corpus.** It must be SEALED (fixed, versioned, committed or content-hashed
      — a corpus that drifts turns the gate into a diary) and genuinely long-context: the
      failure only appears past the window the policy imposes, so prompts shorter than
      `n_sink + window` measure nothing. ⚠ Sizing it against `kv_sink_window`'s default 260
      would be sizing the test to the current policy; size it to the longest window a
      consumer might ship.
- [ ] **Decide where it lives.** The corpus is DATA and this repo is a modelless-primitive
      repo — read `BOUNDARY.md` before adding one. A generation harness needs a model, which
      this repo does not own, so the eval may belong in `riir-train` or `riir-ai` with only
      the `RunawayStats` verdict crossing back. **This is the question to answer first**; the
      rest of the tasks depend on it.
- [ ] **Pin `r_max` and `p_cap_max` against a NO-POLICY baseline**, not against the paper's
      numbers. A threshold inherited from another model's runaway distribution is a threshold
      nobody has measured here.
- [ ] **Run the gate at lr=0-equivalent: the identity policy.** `SinkWindowPolicy::UNBOUNDED`
      evicts nothing, so it MUST pass with margin. A canary that reds on the policy that
      changes nothing is measuring the harness, not the policy (the lr=0
      control-arm discipline, applied to eviction).
- [ ] **Then**: re-gate `kv_sink_window` and promote or refuse on the result.

## The regime that does NOT need this corpus

⚑ A bounded window is not automatically lossy. `katgpt-attn::alibi_entmax_window_1p5`
(Issue 747, Research 549) derives a distance `d_max` beyond which entmax-1.5 attention mass is
**exactly** zero for an ALiBi head, and `SinkWindowPolicy::fidelity(Some(d_max))` reports
`WindowFidelity::Lossless` when `window >= d_max`. In that regime every evicted row carried
0.0 mass, the output is bit-identical, and this rule does not apply at all.

So there are **two** promotion paths and they must not be conflated:

| regime | argument | blocked on |
|---|---|---|
| `window >= d_max` | bit-identity | a consumer that supplies `d_max` (scope assumptions in `eviction_window`'s module docs must hold — ALiBi, causal, bounded raw logits) |
| otherwise | the runaway gate | **this issue** |

## Scope note

This issue is about the CORPUS. The scoring instrument, the policy, and the composition are
all landed and gated. Nothing here asks for new primitives.
