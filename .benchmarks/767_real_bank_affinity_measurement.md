# Bench 767: real-bank layer-affinity measurement — `subspace_intervention` on a live gemma-2-2b residual stream (Issue 779 T3 / Research 557)

**Status:** MEASURED — T3 executed end-to-end (capture + affinity sweep +
three-arm contrast). VERDICT: affinity axis NEGATIVE close (saturated
plateau — no re-pin); three-arm POSITIVE (low-rank task core confirmed on
real tensors). Issue 779 CLOSED 2026-09-16.

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

**Bank provenance (G0, re-measured 2026-09-16):** the original capture's
/tmp artifact was wiped between sessions; the bank was REGENERATED from the
same pinned GGUF + tokenizer + committed example (`aa11cb162`) — BLAKE3
**identical** `99edecca…8b81`. The bit-reproducibility claim is now a
measurement, not an assertion. Capture cost re-measured **1581 s** (4.12
s/prompt) against the recorded 2053 s — same bank bytes, different box load
(two sibling cargo sessions active on 09-15 vs one on 09-16); cite both,
read neither as the capture's intrinsic cost.

**Layer-affinity sweep** (`affinity_sweep`, 4 λ_scale values, 26 layers;
chance = train-majority = 0.167): the curve is a **ceiling plateau, not a
peak** —

| layer | acc @λ=0.003 | @0.01 | @0.03 | @0.1 |
|---|---|---|---|---|
| L00 | 1.000 | 1.000 | 1.000 | 0.990 |
| L01 | 0.927 | 0.938 | 0.969 | 0.969 |
| L02–L25 | 1.000 | 1.000 | 1.000 | 1.000 |

Every layer from L02 up decodes all 6 behavior classes at 1.000 test
accuracy — 6× above both floors — at every regularization strength. The
reported "best layer 25" and "per-class peak L00" are argmax tie-break
artifacts (Rust `max_by` returns the LAST max, the sweep's per-class tracker
keeps the FIRST 1.000), not structure. **No layer carries more task signal
than any other: the hand-picked `layer` param needs no re-pin.**

**Three-arm contrast at L25** (frozen ridge head, ks = {1, 2, 4, 6}, rank
cap 6):

| k | aligned | random | residual |
|---|---|---|---|
| 1 | 0.333 | 0.219 | 0.833 |
| 2 | 0.500 | 0.260 | 0.896 |
| 4 | **1.000** | 0.146 | 0.344 |
| 6 (rank) | 1.000 | 0.062 | 0.000 |

Aligned beats random **6.8× at k=4** (1.000 vs 0.146) and **16× at k=6**;
the top-4 SVD dims of the probe weights alone recover the FULL head
accuracy, and projecting out them collapses the readout (residual 0.344 →
0.000). The task signal on real activations is **low-rank and
subspace-carried** — R557's core finding transfers from the synthetic tiered
bank to a real residual stream. (k=6 residual = 0.000 is the degenerate
0-dim complement: bias-only readout classifies every test row wrong; the
projection identity aligned@rank == full == 1.000 holds to 1e-6.)

## Verdict

1. **Affinity axis: NEGATIVE close for the re-pin question — legitimate per
the issue's outcome criteria.** Not "flat because the instrument is blind"
(the synthetic POC proved it detects planted peaks) but "saturated because
the corpus is too separable": 6 greedy-verified, strongly-differentiated
instruction intents are linearly decodable at ceiling from every layer ≥ L02
of a real gemma-2-2b residual stream. **FutureBehaviorProbe consumers need
no measured layer re-pin — any readout layer works; the terminal layer (the
collectors' existing default) is as good as any.**
2. **Three-arm axis: POSITIVE.** The aligned-vs-random contrast on real
tensors (6.8×–16× at matched k) + residual collapse closes R557 M2's
real-tensor half: the subspace, not the norm, carries the task; a
freeze/thaw artifact that commits the top-4 probe-SVD dims commits the task.
3. **Instrument verdict: the protocol discriminates in BOTH directions** —
planted structure recovered on the synthetic bank (Issue 778), real
saturation measured AS saturation on the real bank (this bench). Nothing to
revive at this scale: a future affinity revival needs a corpus where layers
plausibly differ — fine-grained labels (near-synonym behaviors,
confidence-graded outcomes), not coarse instruction intents.

Issue 779 CLOSED (T3 resolved; issue file removed per the noise-reduction
rule — this bench + the HISTORY row are the trail).

## Honest scope notes

- n=288 train < d=2304: the ridge is heavily regularized by construction;
  the sweep reads the COMPARATIVE layer structure (which layer carries the
  most linearly-decodable behavior signal), not an optimized probe.
- Single model (gemma-2-2b-it), single seed corpus; the bank is
  deterministic (bit-reproducible capture; the f32 SVD path is the analysis
  side, also deterministic).
- The behavior labels are instruction-elicited intents verified by greedy
  prefix audit at k=8; deeper generations were not audited.
