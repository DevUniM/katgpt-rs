# Research 574: Jev Structured Reads on DiffusionGemma — the vLLM Open Reference (PR #57250)

> **Source:** vllm-project/vllm PR #57250 "[Core] structured generation mode for DiffusionGemma model (Jev-like)" — mmastrac (Matt Mastracci), 2026-09-16..19, **UNMERGED** (`ready` label, open) — head `58aacf2` (page-derived; re-verify at consume time), Apache-2.0. Model: `nvidia/diffusiongemma-26B-A4B-it-NVFP4`. Ecosystem same-week: `mmastrac/diffgemma#21` (subclass overlay, merged), `razorback16/openjev` (hosted-endpoint inference), `pst2154/Nemotron_Jev` (dense variant), `madeye/pi-jev#7` (`TYPESAFE_BASE_URL` self-host), `rcarmo/go-pherence#2/#12` (Go-native + RTX-3060 scorer training).
> **Date:** 2026-09-20
> **Status:** Active — Gain verdict (GOAT-tier composition on shipped substrate), POC filed as Issue 859; corpus side MARGINAL (riir-clippy queue line, no batch)
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
| Jev paradigm itself | **saturated** | Research 562 (product) + 573 (open recipe) + Issue 810 CalibratedSigmoidGate **landed** + riir-clippy Issue 125 (option-scorer PoC). This note is the *diffusion-canvas instantiation* entry, not a new paradigm. |

## 3. Distillation + fusion

**Pinned claim (per skill §4):** read-only seeded-canvas structured reads on a diffusion LM for serving-scale calibrated decisions, consuming slot entropy + exact label logprobs, distinguished from `ac_prefix` (scores placed tokens for AR drafting; commits) and `diffusion_sampler` (remask confidence inside generation) by the read-only contract — no commit forward, caller-supplied label-id logprobs, entropy-gated re-reads.

**Fusion (paper × A × B):** read-only seeded read × `ac_prefix::conditional_logprob` × `margin_gate`/CalibratedSigmoidGate (Issue 810) ⇒ a `structured_read()` primitive on `katgpt-forward`'s D2F stack: seed = canvas placement (AcPrefix-shaped), one denoise step, read = `SamplerFeatures` slot stats + conditional-logprob over the label-id list, gate = re-read when label-entropy exceeds threshold (margin_gate's escalation shape, re-reading instead of verifying). Zero new substrate — composition only.

**Reframings (skill §1 step 4):**
- *Game:* too heavy for a 20 Hz per-NPC tick — but it is the authority-side Warm-tier cognition-oracle shape (quest adjudication, GM-scale decisions with confidence bars), and the entropy-gate-escalates pattern is the two-system architecture 562 validated, already shipped as margin_gate.
- *Consumer (healer, priority #2):* the interposer's question types (yes/no, scale, multiple-choice) are literally Noul/Choice/Score — Issue 125's option-scorer gains a self-hostable oracle, and its `samples=auto` policy is the `abstention_rate`/`selective_accuracy` axis implemented as agreement-across-reads.
- *Perf league:* no cell moves (our league is AR Bonsai/qwen; this is a different model class). vLLM remains the scored opponent; this is a capability watch, not a tok/s threat or opportunity.

## 4. Verdict

**GOAT-tier Gain** (not Super-GOAT — Q1 fails by construction: the PR is public prior art; Q2/Q3/Q4 pass for our stack: new capability class on our D2F surface, selling point "our engine serves Jev-style structured decisions natively — one forward, exact label logprobs, no parsing", multiplier across canvas/AcPrefix/SamplerFeatures/margin_gate/810).

MOAT gate: katgpt-rs in-scope (serving-stack primitive, no game semantics). Routing: primitive → `katgpt-forward` (feature flag); consumer intel → riir-clippy Issue 125; **POC → Issue 859 (4090)** with three competitors per §3.6 (read-only read vs full-loop-then-parse vs AR constrained decode) and the UQ floor rule binding any calibration claim. Corpus side (riir-clippy): MARGINAL C+ — Python serving code; the three M4 patterns are kernel_opt-adjacent leads only (dedup + applicability caveats in the queue line); no batch.

**4090 feasibility (Issue 859 T1):** NVFP4-marlin needs only SM ≥ 7.5, but a known SM89 bf16-garble bug (vLLM GH, 2026-02) forces `--dtype float16`; 26B-A4B NVFP4 ≈ 14 GB weights fits 24 GB. Box was unreachable this session (LAN timeout) — probe first. Fallback if the quant path fails: substrate POC only (CPU/small-fixture), reference validation deferred to when a fp8/fp16 DiffusionGemma quant or the Nemotron_Jev dense variant is runnable.
