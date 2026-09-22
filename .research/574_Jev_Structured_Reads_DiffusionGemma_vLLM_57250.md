# Research 574: Jev Structured Reads on DiffusionGemma — the vLLM Open Reference (PR #57250)

> **Source:** vllm-project/vllm PR #57250 "[Core] structured generation mode for DiffusionGemma model (Jev-like)" — mmastrac (Matt Mastracci), 2026-09-16..19, **UNMERGED** (`ready` label, open) — head `ceb8eebf` (API-read 2026-09-20; was `58aacf2` at first read — the branch moves daily, re-pin at clone; §7), Apache-2.0. Model: `nvidia/diffusiongemma-26B-A4B-it-NVFP4`. Ecosystem same-week: `mmastrac/diffgemma#21` (subclass overlay, merged), `razorback16/openjev` (hosted-endpoint inference), `pst2154/Nemotron_Jev` (dense variant), `madeye/pi-jev#7` (`TYPESAFE_BASE_URL` self-host), `rcarmo/go-pherence#2/#12` (Go-native + RTX-3060 scorer training).
> **Date:** 2026-09-20
> **Status:** CLOSED (Issue 859 resolved 2026-09-20) — Gain verdict (GOAT-tier composition on shipped substrate), POC landed + T1 4090 reference executed + T5 policy arm measured (Bench 817) + promotion decision recorded (§9: stays opt-in, evidence-banked); corpus side MARGINAL (riir-clippy queue line, no batch)
> **Related Research:** 562 (Typesafe SystemOne/Jev — the product distill; this PR is its open replication), 573 (CUA-S1 open Jev recipe — the AR specialist arm), 277 (DiffusionGemma transparency — routed nothing then), 419 (PackInfer — the width-tiling gap this PR instantiates), 322 (Report-the-Floor UQ rule — binds any probability claim below)
> **Related Plans:** none yet (POC first, per Issue 859)
> **Cross-ref (riir-clippy):** Issue 125 (option-scorer PoC — addendum landed: this PR is its self-hostable decision-contract oracle)
> **Classification:** Public

---

## TL;DR

The Jev decision contract now has an **open reference implementation on open weights**: PR #57250 turns DiffusionGemma into a structured-decision server — seed the canvas with a schema (fixed tokens + single-token answer slots), run **one denoise step**, read argmax + **exact label-id logprobs** at the free slots, and **skip the commit forward** entirely. Measured on a DGX Spark: 8.7 req/s @1-way / 54 req/s @32-way (~162 decisions/s), accuracy 9/10–10/12 across language/unit/vision decision classes, with an entropy-gated re-read policy (re-read ×4 when H1 > 0.1) reporting mean ± error bars. For us the value is **not** the model (NVFP4 MoE, different class from our league) but the **read-only serving contract**: our D2F stack ships every component (canvas masks, token-placement scoring, slot-stat readout) yet the composition — a request that reads without committing — is unoccupied in-workspace.

**Distilled for katgpt-rs (modelless, inference-time):**
A diffusion-LM decision read is a **read-only forward**: `seed(canvas, schema) → one denoise step → per-slot {argmax, exact logprobs over a caller-supplied label-id list, entropy} → return, no commit`. Three contract details are the transferable content: (a) **single-token choices** so the canvas never shifts (multi-token options are client-mapped to labels); (b) **exact label-id logprobs, not top-k** — with 26 options only 1–8 reached top-20, so the API must accept the id list (our `ac_prefix::conditional_logprob` already computes exactly this for placed ids); (c) **uncertainty = re-read agreement** — entropy over the label distribution gates N additional reads and the answer ships with mean ± bars (a self-hosted confidence proxy needing no ground truth; any *calibration* claim from it still owes the conformal-naive floor per the UQ rule).

---

## 1. What the PR ships (its own claims, with caveats)

Machinery added to vLLM (`vllm_xargs`): `diffusion_seed_canvas` (pre-seed fixed tokens post-prefill), `diffusion_read_only` (emit on converging step, skip commit forward, temperature-1 logprobs), `diffusion_max_steps` (step cap; reads want 1), `diffusion_canvas_length` (per-request width — a short schema costs short-canvas compute on a wide server), plus `logprob_token_ids` honored on the converging step, and a bugfix for two lockstep generations stomping the logprob stash (HTTP 500 class).

| Measured (DGX Spark, GB10 — **not transferable as headroom evidence**) | Number |
|---|---|
| 1-way / 32-way read throughput | 8.7 req/s @0.12s / 54.0 req/s @0.58s (~162 decisions/s) |
| Decision accuracy classes | programming-language 10/10 · human-language 9/10 · unit-comparison 10/12 · vision (color/count/quadrant/contrast) mostly 8/8 |
| Skip-work wins | skip self-conditioning vocab-matmul for 1-step slots (~6.5 ms/step on GB10, −20–40% decision time) · scheduler never steps past a read-only cap (was ⅓ of request GPU time wasted) · width-tiling 38→54 req/s @32-way · scheduler subclass 27.56→30.18 req/s @8-way |

Caveats: unmerged; reviewer (kvnloo) should-fixs unaddressed-at-read (unbounded interposer fan-out, entropy over unnormalized top-set understating true entropy, silent step-cap clamp); the model needs `--diffusion-config` and (on non-Blackwell) an NVFP4-marlin dtype workaround (Issue 859 T1).

## 2. In-workspace coverage (prior-art grep, both vocabularies)

| PR mechanism | Ships here? | Evidence |
|---|---|---|
| M1 read-only seeded-canvas structured read (the composition) | **NO — zero prior art** | Components all ship: `katgpt-core/src/canvas/` (`canvas_schema` masks, Plan 419), `ac_prefix/` (place tokens + one-pass score `p(xe|xc)` — but D2F/AcPrefix paths **commit**), `katgpt-forward/src/diffusion_sampler.rs` (`SamplerFeatures`: per-slot maxp/margin/entropy — used for remasking *inside* generation, never as a standalone request). Research 277 read DiffusionGemma's canvas math and routed nothing. |
| M2 exact label-id logprobs | primitive YES / API NO | `ac_prefix::conditional_logprob(_dedup)` = exact logprob of chosen ids; `nf_flow` selected-id logprobs from full marginals. No token-id-list request API exists; the top-k blindness problem cannot arise for us (full marginals are direct). |
| M3 entropy-gated N-re-read + mean±bars | **NO as a policy** | Neighbors: `margin_gate.rs` trusted(gap) escalation (escalates to a *verifier*, no re-read), `velocity_field_disagreement.rs` (ensemble disagreement UQ for flow fields), Research 494 dual-threshold exit (unimplemented), 530 reread protocol (not filed). |
| M4 skip-work + width tiling | **NO** | `skip.*self.?cond` → 0 hits; width-tiling = PackInfer 419's documented open gap (`BinPackedGroups` never implemented); nearest corpus kin = D2F prefix-persist elision (riir-clippy entries_gpu_05 — different skip target). |
| Jev paradigm itself | **saturated** | Research 562 (product) + 573 (open recipe) + Issue 810 landed ("CalibratedSigmoidGate" is a prose phantom — shipped as `SigmoidGateCalibrator` + `CalibratedActionBridge`) + riir-clippy Issue 125 (option-scorer PoC). This note is the *diffusion-canvas instantiation* entry, not a new paradigm. |

## 3. Distillation + fusion

**Pinned claim (per skill §4):** read-only seeded-canvas structured reads on a diffusion LM for serving-scale calibrated decisions, consuming slot entropy + exact label logprobs, distinguished from `ac_prefix` (scores placed tokens for AR drafting; commits) and `diffusion_sampler` (remask confidence inside generation) by the read-only contract — no commit forward, caller-supplied label-id logprobs, entropy-gated re-reads.

**Fusion (paper × A × B):** read-only seeded read × `ac_prefix::conditional_logprob` × `margin_gate`/the Issue-810 calibration pair (`SigmoidGateCalibrator` + `CalibratedActionBridge`) ⇒ a `structured_read()` primitive on `katgpt-forward`'s D2F stack: seed = canvas placement (AcPrefix-shaped), one denoise step, read = `SamplerFeatures` slot stats + conditional-logprob over the label-id list, gate = re-read when label-entropy exceeds threshold (margin_gate's escalation shape, re-reading instead of verifying). Zero new substrate — composition only.

**Reframings (skill §1 step 4):**
- *Game:* too heavy for a 20 Hz per-NPC tick — but it is the authority-side Warm-tier cognition-oracle shape (quest adjudication, GM-scale decisions with confidence bars), and the entropy-gate-escalates pattern is the two-system architecture 562 validated, already shipped as margin_gate.
- *Consumer (healer, priority #2):* the interposer's question types (yes/no, scale, multiple-choice) are literally Noul/Choice/Score — Issue 125's option-scorer gains a self-hostable oracle, and its `samples=auto` policy is the `abstention_rate`/`selective_accuracy` axis implemented as agreement-across-reads.
- *Perf league:* no cell moves (our league is AR Bonsai/qwen; this is a different model class). vLLM remains the scored opponent; this is a capability watch, not a tok/s threat or opportunity.

## 4. Verdict

**GOAT-tier Gain** (not Super-GOAT — Q1 fails by construction: the PR is public prior art; Q2/Q3/Q4 pass for our stack: new capability class on our D2F surface, selling point "our engine serves Jev-style structured decisions natively — one forward, exact label logprobs, no parsing", multiplier across canvas/AcPrefix/SamplerFeatures/margin_gate/810).

MOAT gate: katgpt-rs in-scope (serving-stack primitive, no game semantics). Routing: primitive → `katgpt-forward` (feature flag); consumer intel → riir-clippy Issue 125; **POC → Issue 859 (4090)** with three competitors per §3.6 (read-only read vs full-loop-then-parse vs AR constrained decode) and the UQ floor rule binding any calibration claim. Corpus side (riir-clippy): MARGINAL C+ — Python serving code; the three M4 patterns are kernel_opt-adjacent leads only (dedup + applicability caveats in the queue line); no batch.

**4090 feasibility (Issue 859 T1):** NVFP4-marlin needs only SM ≥ 7.5, but a known SM89 bf16-garble bug (vLLM GH, 2026-02) forces `--dtype float16`; 26B-A4B NVFP4 ≈ 14 GB weights fits 24 GB. Box was unreachable this session (LAN timeout) — probe first. Fallback if the quant path fails: substrate POC only (CPU/small-fixture), reference validation deferred to when a fp8/fp16 DiffusionGemma quant or the Nemotron_Jev dense variant is runnable.

## 5. Substrate mapping (Issue 859 T2, 2026-09-20 — written BEFORE implementing, per the substrate-first gate)

**T0 probe result (2026-09-20 05:2x):** LAN `192.168.1.33` times out (as predicted); Tailscale `100.85.179.44` reachable. GPU **16,839 / 24,564 MiB used, 2% util** — a sibling compute job is live (`F:\scratch\tgt-tapx\...\bench_989_tap_crosscheck.exe`, the DFlash2 tap cross-check, ~27B weights resident). GPU-exclusivity rule ⇒ **T1 deferred** until that bench drains (only ~7.7 GB free; the 26B NVFP4 would not fit regardless). Python 3.10.11 present. Per the issue's own fallback clause ("if unrunnable: skip T1 and do T2–T5 on CPU/small fixtures"), the POC proceeds M3-local.

| Contract step | Substrate home (verified line-level) | The seam |
|---|---|---|
| **seed canvas** (fixed schema tokens + free slots) | `katgpt-forward/src/forward_positions.rs` + the `config.mask_token` convention | free slots carry the mask token; the denoise loop's own skip rule (`denoise_loops.rs:148-151`, `if tokens[p] != mask { continue }`) already honors pre-seeded positions. **AcPrefix-SHAPED, not AcPrefix-consumed**: AcPrefix exists to give CAUSAL forwards arbitrary-conditional power via sequence augmentation (`ac_prefix/types.rs:297-353`); the D2F bidirectional forward is natively the right conditioning shape (mask embeddings at free slots, exactly DiffusionGemma's canvas semantics). `canvas_schema` is NOT consumed either — it is a positions-not-tokens topology compiler (no token ids exist in `canvas/`), i.e. a topology seam, not a placement seam. |
| **one denoise step** | `forward_positions::forward_bidirectional_positions_into(weights, &tokens, config, &mut bctx)` | ONE bidirectional forward fills per-position full-vocab logits — the identical call `denoise_loop` makes per step (`denoise_loops.rs:142`); `bctx.all_logits[p*vocab..(p+1)*vocab]` (`forward_positions.rs:63,269`) is the read surface. |
| **read: argmax + exact label logprobs** | full-vocab logits row → stable logsumexp → `logprob(t) = logits[t] − logsumexp` | exact full-marginal logprob; the PR's top-k blindness cannot arise (M2's note — our marginals are direct). Label list is caller-supplied `&[u32]`, order preserved. No existing API returns this (`ac_prefix::conditional_logprob` scores the ACTUAL token only, one scalar; `ForwardForAcPrefix::forward_logits_at` returns logits but is the AR-path trait) — this is the primitive's own computation. |
| **read: entropy over the NORMALIZED label distribution** | NEW — softmax restricted to the label subset, `H = −Σ pᵢ ln pᵢ` | the PR reviewer's nit (entropy over an unnormalized top-set understating true entropy) corrected by construction — house rule. |
| **skip commit** | read-only: never write `tokens[p]` | contrast the commit branch `denoise_loops.rs:188` (`tokens[p] = best_token`). This is exactly M1's "zero prior art" composition gap. |
| (escalation analog) | `d2f_verifier.rs` (D2F drafts + AR verifies, tri_mode) + `katgpt-core` `pruners/margin_gate.rs` trusted(gap) | the T5 entropy gate's escalation shape. Note for T5: OUR denoise forward is deterministic (the `_rng` param of `denoise_loop` is unused in the loop), so re-reads are bit-identical and agreement bars are vacuous UNLESS the re-read is made stochastic (sample from the label distribution at temperature > 0 — the PR's temperature-1 logprob read is the analog). The T5 arm therefore ships a sampling re-read helper; agreement-vs-entropy is measurable only through it. |
| (slot stats substrate, not consumed) | `diffusion_sampler.rs` `SamplerFeatures::from_logits` (per-slot maxp/margin/entropy) | tri_mode-gated and used for remasking inside generation; the pinned claim needs only label-subset stats, so the feature stays minimal (`structured_reads = ["dllm"]`, no tri_mode pull). |

**Composition law honored:** zero new substrate — the primitive is one new module in `katgpt-forward` composing `forward_bidirectional_positions_into` + the mask-token placement convention + new label-subset readout math. Routing per §4: katgpt-forward, feature flag `structured_reads`.

## 6. POC verdict (Issue 859 T3–T6, 2026-09-20 — Bench 816)

**Landed, GOAT G1/G1b/G2/G3/G4 PASS** (opt-in `structured_reads`, NOT promoted — promotion needs the accuracy axis, which rides T1):

- G1: label logprobs exact full-marginal (f64 cross-check < 1e-5; bit-identical across calls). G1b: canvas bit-identical after read (no commit).
- G2: read/full-loop median ratio **0.4588** (33 interleaved pairs ×8, release; the Issue-723 sequential-timing discipline). Box: M3 under load 3.8–6 with the training measurement live — 2.2× margin against the ≤1.0 bar, load-insensitive verdict.
- G3: 154/154 existing suite green at the new feature set; default-features build clean.
- G4: **0 allocations** across 32 reads after scratch construction — canary-armed counting allocator, `--release --features structured_reads,alloc_tracking` (the katgpt-forward `alloc_tracking` forward landed for exactly this — Issue 741's release-profile law).
- Competitor arm (informational): step-1 read vs full-loop-then-parse 4/4 after 1 commit round at threshold 0.3; mean label entropy 0.4123 nats. Random-init weights carry no ground truth — recorded as mechanism agreement, not accuracy.
- **T5 partial**: `sample_label_index` (temperature > 0) landed as the stochastic re-read enabler — the deterministic forward re-reads bit-identically, so the reference's agreement-bars policy is only meaningful through it; the measurement rides T1.

**Remaining:** none for Issue 859 — T1 executed (§8), T5 measured + the promotion decision (§9). The optional follow-up is the reference-side proxy re-run (§8's data-spec note), not promotion-blocking.

## 7. T1 unblock intel (2026-09-20, idle-queue item 9 — online unblock search; zero box contention)

The T1 blocker is GPU occupancy, not knowledge — this section removes the knowledge half so T1 is a
one-command run when the 4090 drains.

**PR state (GitHub API, 2026-09-20):** OPEN, `ready` label, unmerged, 14 commits (+2909/−132, 18
files), 29 comments, head **`ceb8eebf3eedddb964a50180f33838a9a6b13ee2`** (pushed 2026-09-19 21:45Z —
the branch moves daily; re-pin at clone). The 5 split-out prerequisite PRs are now numbered:
#57414 (logprob-stash bugfix) · #57416 (prefill-only logit rows) · #57417 (`logprob_token_ids` on
the converging step) · #57462 (dynamo-eager cast) · #57589 (multimodal fix).

**The production consumer ships the recipe** — `razorback16/openjev` (Apache-2.0, a Jev-wire-compatible
decision server over this exact PR; `engine.py` adapted from the PR's `structured_server.py`):

- **Docker prebuilt (the 4090-box natural path)** — vLLM has no native Windows support, and the box
  runs Docker Desktop: `docker run -d --gpus all --ipc=host -p 127.0.0.1:8080:8080 -v
  ~/.cache/huggingface:/root/.cache/huggingface razorback16/openjev:0.1.0` (image pins the fork @
  `d2c2b54`, CUDA 13 — driver must support it; weights ~18 GB download on first start). T1's
  corpora then run against `http://127.0.0.1:8080/v1` through the PR's own example server shape.
- **pip, no source build**: `git clone https://github.com/mmastrac/vllm -b structured-reads-main &&
  git checkout d2c2b5422d && VLLM_USE_PRECOMPILED=1
  VLLM_PRECOMPILED_WHEEL_COMMIT=2c88fb131c7ae0be01907cd8c276911db5e7aad4 pip install -e .`
- **Serve flags** (their validated line, canvas 64 — T1 spec wants 32, settable via
  `OPENJEV_CANVAS`/`--diffusion-config`): `--max-logprobs 32 --enable-prefix-caching
  --async-scheduling --attention-backend TRITON_ATTN` (+ `--max-num-seqs 32` in the PR's own test
  plan). TRITON_ATTN is fine inside the Linux container; not on native Windows.
- `vllm_xargs` confirmed **provisional** upstream (openjev pins the fork for exactly this reason) —
  our issue's re-pin rule stands.

**SM89 (4090) risk profile, refined:** openjev tests only on RTX PRO 6000 Blackwell (sm_120),
"≥24 GB VRAM" for the NVFP4 checkpoint. On Ada, NVFP4 has no native path → Marlin W4A16 fallback
(SM ≥7.5 — legal) with the known bf16 garble ⇒ `--dtype float16` (§4's workaround stands).
VRAM: weights ~14–18 GB (§4 estimate vs HF download size) — fits the 4090's 24,564 MiB ONLY with
the GPU otherwise free (the exclusivity rule already demands this); tune
`--gpu-memory-utilization`/`--max-model-len` conservatively at canvas 32.

**Zero-GPU accuracy fallback (new option, ranked BELOW our-box serving):** openjev is hosted free
on Codiv (`https://api.codiv.ai/v1/systemone`, 100M input tokens, no card) — if our-box serving
proves infeasible, the programming-language + unit-comparison corpora can run there for the
ACCURACY axis, recorded as hosted-reference intel (never our-box perf; synthetic non-sensitive
fixtures only — they leave the box).

**T5-relevant divergences already visible:** upstream H1 = entropy over top-20 logprobs; ours is
entropy over the normalized LABEL SUBSET (§5, the reviewer's-nit correction). Their auto policy
re-reads ×4 at H1 > 0.1 — the exact threshold family T5 meant to measure; their sample outputs
(`urgent=0.88±0.04`, reads=1 vs 4) are the comparison shape. Their `logprob_token_ids` cap is 128
ids — our MAX_LABELS=64 sits inside the reference envelope.

---

## 8. T1 EXECUTED: the 4090 reference cell (2026-09-20, the yielded-to session)

Build path: python-only overlay of the PR head `ceb8eebf` onto `vllm/vllm-openai:nightly` (image
`sr859-overlay:ceb8eebf`, built from a tarball clone — fresher than §7's openjev pin `d2c2b54`;
the PR is 100% Python, 18 files, no C++/CUDA, so overlaying the fork's `vllm/` tree over the
image's site-packages keeps the nightly's compiled kernels and skips every build path in §7).
Serving: canvas 32, TRITON_ATTN, `--max-num-seqs 16 --max-model-len 2048 --max-num-batched-tokens
512 --gpu-memory-utilization 0.92 --enforce-eager --limit-mm-per-prompt '{"image":0,"video":0}'`,
sync scheduler, **bf16**. The interposer: the PR's own `structured_server.py` in-container.
Corpora client + results.json: `E:/vllm-859/` (restorable stack: overlay image + hf-cache + fork).

**Two empirical corrections to §7's risk profile:**
1. **The SM89 marlin bf16 garble did NOT fire** — clean outputs across all 32 corpus items + the
   smoke cell (bf16 kept; no float16 fallback needed).
2. **The quant fits a 24 GB WDDM card WITH a resident GUI** once the mm **video profiler is
   zeroed**: that profiler ("1 video items of the maximum feature size", `encoder_runner.py:131`)
   reserves ~4.4 GiB — with it live, KV = **−0.49 GiB at every knob combination tried** (util
   0.90→0.95, eager, seqs 32→8, batched 2048→512, async on/off moved the deficit only −0.62→−0.49);
   with `video=0`+`image=0` the model serves. Weights 18.15 GiB; the free ceiling beside a
   resident GUI is 22.45/23.99 GiB, capping usable utilization at ~0.92.

**Intel cells (NOT league evidence — different model class + silicon + degraded config; the
config deltas vs the PR's DGX run: eager, sync scheduler, seqs 16 — all forced by the above):**

| Cell (ours, 4090) | Result | PR's DGX Spark |
|---|---|---|
| smoke (the PR's outage ticket, same prompt) | urgent=yes **0.881±0.042** · bucket=outage **0.9986** · tone=**furious 3.00** · reads=4 | 0.88±0.04 · 1.00 · furious 3.00 · reads=4 |
| programming-language | **10/10** | 10/10 |
| human-language | **10/10** (own items, same protocol) | 9/10 |
| unit-comparison | 7/12 raw → **9/12 corrected** (2 "misses" were this author's mislabeled items — 130 min > 2 h, 5 km > 3 mi, the model right both times; the 3 true misses: 1 lb vs 500 g, 5000 MB vs 4 GB, 1 yd vs 1 m, all p(want) ≤ 0.44) | 10/12 |
| throughput 1-way | **5.2 req/s @ 193 ms** | 8.7 req/s @ 0.12 s |
| throughput 8/16-way | **14.3 @ 70 ms / 20.8 @ 48 ms** | 54.0 @ 0.58 s (32-way) |

Protocol conclusions that transfer: the auto re-read policy fires reads=4 exactly where H1 > 0.1
(temperature-1 logprobs, p(want) ± stderr + agreement as first-class outputs); the weak class is
**unit conversion** in both runs — their 2 misses and our 3 are the same class. The corpus items
are self-authored mirrors (same protocol/shape as the PR's, different items — no strict parity
claim; the smoke cell is the same-prompt anchor and it matches within noise).

**T5 unblock:** the accuracy axis now exists on our silicon — §6's `sample_label_index` has both
a reference protocol to mirror (the auto policy above) and the corpora ground truth to measure
against; the trained-fixture path (`micro_dllm_text`) remains the in-crate alternative.

## 9. T5 MEASURED + the promotion decision (2026-09-20, Bench 817 — Issue 859 closed)

The policy arm, measured in-crate on the trained fixture (`micro_dllm_text`, bench-601's exact
recipe, corpus honesty asserted: masked NLL 2.4867 < unigram 2.8884): 2 label arms × 2 canvas
shapes × 9216 items, reference protocol numbers (N=4 re-reads, temperature 1).

**Headline: agreement bars do NOT beat single-read analytic confidence — CI-decisive in both
arms and every gate subset.** AUROC for predicting argmax correctness:

| Arm | −H1 | maxprob | agreement(4 reads) | Δ(agree−(−H1)) 95% CI |
|---|---|---|---|---|
| A option-set (4–12 opts, acc 50.3%) | **0.7807** | 0.7728 | 0.7004 | [−0.0893, −0.0714] |
| B full-alphabet (31 opts, acc 26.4%) | 0.6724 | **0.6930** | 0.6298 | [−0.0555, −0.0298] |

The pre-registered prediction held exactly: on a deterministic forward, correctness is a
function of the readout and re-read samples are conditionally independent of it given the
readout — the M3 gate (H1 > τ → 4 reads) buys error BARS, never discrimination, and on this
fixture it fires 88–100% of the time (mean reads 3.6–4.0) for a strictly worse ranking signal.
**The control-arm logic does NOT extend to the reference — settled by code read (fork head
`ceb8eebf`, `structured_server.py`):** the reference's re-read is NOT a resample of a fixed
distribution — `build_canvas` seeds each free slot with `rng.randrange(VOCAB)` from a per-read
seed (`read_many` passes `seed + k*7919`), so every re-read is a **forward from a different
random noise initialization** (the diffusion noise draw; the header's own words: "one
distribution per question, from one denoise step over a seeded canvas, averaged over a few
noise draws"). Between-read agreement on the reference therefore measures **basin variance
under noise re-init that no single read can see** — their auto policy is sound on its side,
and our T5 result stands as the deterministic member of the family (mask-conditioned reads;
our fixture's mask-corruption training puts random-token slots out of distribution, so the
noise-draw variant is not a drop-in for `structured_read`). Directional support from the §8
rows (n=32, anecdote grade): between-draw stderr is real exactly in the gated band (reads=4:
p_want 0.10–0.78, stderr 0.03–0.10; reads=1: p_want ≈ 0.997, no variance) and the
highest-stderr item (0.097) is a true miss. A decisive reference-side measurement needs a
~100-item corpus (authoring effort) — routed to the riir-clippy Issue 125 lane or a future
session; not promotion-blocking.

**The genuinely open sub-question resolved by width:** maxprob BEATS entropy on wide option
sets (arm B: Δ CI [+0.0151, +0.0262] — tail mass over many near-zero options dilutes entropy);
entropy is marginally better on narrow sets (arm A: Δ CI [−0.0119, −0.0040]). Deployable
guidance: `label_entropy` for narrow option sets, `argmax_label_prob` for wide ones. Sampled(t=1)
deployment costs 8.8–11.3pp accuracy vs argmax.

**Promotion decision (T6): `structured_reads` STAYS OPT-IN — evidence-banked.** The discipline
conditions are met (GOAT G1–G4, Bench 816; modelless gain: 0.46× full-loop latency, exact
full-marginal readouts, alloc-free; accuracy axis measured here), but `katgpt-forward`'s
`default = []` is deliberately minimal and the feature would drag the dllm stack into every
default build with zero production consumers today — the flashar_anchor precedent (GOAT green,
feature opt-in, blessed defaults inside the seam). A root feature forward
(`structured_reads = ["dllm", "katgpt-forward/structured_reads"]`) landed with Bench 817 so
the lane is consumable without flag archaeology; promotion is one line when a consumer appears
(re-arm trigger).
