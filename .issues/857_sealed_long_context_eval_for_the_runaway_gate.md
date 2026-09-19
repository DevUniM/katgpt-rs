# Issue 857 — the sealed long-context eval the runaway gate has no corpus for

**Status:** OPEN — filed 2026-09-19; the BOUNDARY question (which the filing named as
*"the question to answer first"*) ANSWERED 2026-09-19 by substrate-first grep, and the
issue is consequently **PULL-GATED, not blocked** — see §Where it lives. Blocks the
promotion of `kv_sink_window`
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
- [x] **Decide where it lives.** ANSWERED 2026-09-19 — and the answer is **both, split by
      role**, which is why the filing's "riir-train *or* riir-ai" was one question short.
      See §Where it lives below. Verified by grep, not remembered.
- [ ] **Pin `r_max` and `p_cap_max` against a NO-POLICY baseline**, not against the paper's
      numbers. A threshold inherited from another model's runaway distribution is a threshold
      nobody has measured here.
- [ ] **Run the gate at lr=0-equivalent: the identity policy.** `SinkWindowPolicy::UNBOUNDED`
      evicts nothing, so it MUST pass with margin. A canary that reds on the policy that
      changes nothing is measuring the harness, not the policy (the lr=0
      control-arm discipline, applied to eviction).
- [ ] **Then**: re-gate `kv_sink_window` and promote or refuse on the result.

## Where it lives — the substrate-first verdict (2026-09-19)

`BOUNDARY.md` settles the katgpt-rs half in one line: this repo owns modelless
inference primitives and nothing downstream, with *training* routed to `../riir-train` and
*game runtime / cognition wiring* to `../riir-ai`. A corpus is DATA and a generation harness
needs a model; neither is ownable here. Only `RunawayStats` / `runaway_gate` — already
shipped — crosses back.

The sibling halves both already exist, and finding that is what changes this issue's
standing:

| piece | home | what already ships there |
|---|---|---|
| the long-context CORPUS + generation harness | `riir-train` | `crates/riir-train-engine/src/kimi_k3_long_context.rs` — Plan 318 Phase E2's long-context dataset builder, which packs real `.rs` sources into 1024–4096-token windows with a SEP-separated greedy pack; plus `examples/plan318_teacher_data_gen.rs` and the GPU lane |
| the canary WIRING at a real KV cap | `riir-ai` | `.issues/882` (KV-eviction consumer surface, GATED-DEFERRED) — whose **T2 already reads "wire `RunawayStats` canary"** |
| the scoring instrument + the promotion bar | **here** | `kv_eviction::RunawayStats` / `runaway_gate`; 882 records the composite bar as `runaway_gate ∧ beats_random_prompt_pin ∧ protection factorial` |

⛔ **So this is PULL-GATED on riir-ai `.issues/882`'s own T-Pull-1, and building the corpus
before that trigger fires would be building a measurement with no consumer.** 882's
consumer verification (2026-09-06) is explicit: **zero attention-KV eviction surfaces exist
in riir-ai today** — the riir-gpu evictions are auxiliary weight/prefix caches, riir-router
`truncation` is prompt-side, and riir-engine runs fixed-size recurrent state. No cap, no
eviction, nothing to run a runaway canary against.

⚑ **And the corpus is therefore NOT the binding blocker on `kv_sink_window`'s promotion,
which is the correction this issue owes its own header.** AGENTS.md's no-default-consumer
rule keeps that primitive opt-in regardless of any corpus: there is no in-repo consumer of
`select_evict_windowed` at all. The honest ordering is

1. a consumer appears (882's T-Pull-1: a bounded decode KV budget on the serving path),
2. the corpus is built in riir-train against THAT consumer's window, not against
   `kv_sink_window`'s default 260 — which the filing already warned is sizing the test to
   the current policy,
3. the canary is wired in riir-ai (882 T2) and `r_max` / `p_cap_max` pinned against a
   no-policy baseline,
4. **then** `kv_sink_window` is re-gated and promoted or refused.

Steps 2–4 stay exactly as the task list below has them. What changed is that step 1 is
somebody else's trigger, already filed, already owned — so this issue waits on an event
rather than on an unassigned decision, and nobody should read it as work that is merely
undone.

⚠ No sibling issue is filed for the corpus **on purpose**: riir-ai 882 is the pull-gate and
duplicating its trigger in riir-train would create a second, drifting copy of the same
condition. File the riir-train corpus issue at pull time, citing 882's fired trigger.

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
