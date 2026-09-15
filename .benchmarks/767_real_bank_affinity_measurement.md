# Bench 767: real-bank layer-affinity measurement — `subspace_intervention` on a live gemma-2-2b residual stream (Issue 779 T3 / Research 557)

**Status:** MEASURED — T3 executed end-to-end (capture + affinity sweep +
three-arm contrast). [VERDICT-PENDING]

**Date:** 2026-09-15 · **Instrument:** `affinity_sweep` / `three_arm_eval`
(`katgpt_core::subspace_intervention`, opt-in) · **Bank:** gemma-2-2b-it f16
(riir-train/data), BLAKE3 recorded below.

## T3 protocol (as executed)

**Capture** (riir-ai `future_probe_bank_capture`, commit `aa11cb162`):
384 prompts = 6 behavior-intent classes × 8 surface shells × 8 shared topics
(topic = balanced nuisance axis — every topic appears in every class; shells
6+7 held out for test so a template-token shortcut cannot transfer). Per
prompt: gemma chat template (`encode_chat_user_turn`), prefill, then the LAST
prompt token's post-MLP residual collected at ALL 26 layers via
`forward_one_token_hooked` (Issue 673) with a read-only all-layer collector.
Plus a greedy 8-token decoded prefix per prompt as the label audit.

- Bank: 384 × 26 × 2304 f32, BLAKE3 `99edeccaf62f03971f06a311ca779b6c2119bc0d0f0baeaeb11e6fc26fec8b81`
- Split: 288 train / 96 test (16 test per class), both floors = 0.167
  (chance = train majority; the classes are balanced by construction).
- Capture cost: 2053 s on M3 (release, single-process CPU; 5.35 s/prompt
  incl. the greedy audit).
- **Label audit (greedy prefixes): all 6 classes elicit the labeled
  behavior** — factual answers start factual; code opens a rust /
  python / typescript fence; translate translates; summarize summarizes;
  creative writes atmospheric fiction; refuse refuses ("I cannot provide
  instructions…", "I cannot help you hack…", "I cannot tell you how to steal
  …"). No label drift observed in the sampled prefixes (3/class printed;
  full audit trail in the meta json, `gen_prefix` per row).

**Analysis** (katgpt-rs `tests/bench_779_real_bank_affinity.rs`, Issue 779
T3, `#[ignore]` + env-gated on the bank): `affinity_sweep` at λ_scale ∈
{0.003, 0.01, 0.03, 0.1} (λ = λ_scale · mean diag Gram; span-stability axis
from R557 — conclusions must not hang on one λ), then `three_arm_eval` at
the best layer through the frozen ridge head, ks = {1, 2, 4, 6} (6 =
classes.min(d) = the projection-identity point). Two-floor discipline: every
accuracy row is read against uniform chance AND the train majority rate
(both 0.167 here).

## Measurement

[RESULTS-PENDING]

## Verdict

[VERDICT-PENDING]

## Honest scope notes

- n=288 train < d=2304: the ridge is heavily regularized by construction;
  the sweep reads the COMPARATIVE layer structure (which layer carries the
  most linearly-decodable behavior signal), not an optimized probe.
- Single model (gemma-2-2b-it), single seed corpus; the bank is
  deterministic (bit-reproducible capture; the f32 SVD path is the analysis
  side, also deterministic).
- The behavior labels are instruction-elicited intents verified by greedy
  prefix audit at k=8; deeper generations were not audited.
