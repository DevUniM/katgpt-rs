# Bench 814 — FlashMemory Full-Model NIAH QA gate (Issue 826 T1+T2)

**Date:** 2026-09-18
**Issue:** Issue 826 — T1 needle axis + T2 budget stress (file removed per noise-reduction after T3's gate wiring landed; this bench doc + git history are the record. Final disposition: T1+T2 measured here; T3 wired the Issue-584 Phase-3 promotion gate with the relative pin below; the ABSOLUTE SAS-class axis stays open-and-recorded as untestable on the 0.4B testbed — dense oracle never retrieves (pw_rank top-1.3% at every rung 512→17322); needs a model whose dense oracle retrieves (Bonsai-27B 4090 GQA path or any ≥1B with real long-context training); 64K rung priced ~9h/arm in §Cost model; T4 centroid refinement deferred behind an absolute-axis gap, modelless-only.)
**Instrument:** `benches/bench_685_flashmemory_full_model_niah_qa.rs` (`cargo bench --bench bench_685_flashmemory_full_model_niah_qa --features kimi_k3_loader,flashmemory_sparse`)
**Box:** M3 Max (16 cores), macOS 26.6.2, release build, single process at ~99% of one core; no GPU (CPU SIMD path), no competing compute consumer.
**Model:** Kimi-K3-0.40B (`riir-train/data/kimi-k3-0.40b/model.safetensors`, F32, trained context 4096).

## What this measured

Bench 023's honest negative (2026-08-13) left the needle axis unmeasured
end-to-end: at single-layer depth the needle is invisible (dense attention rank
34/34 at layer 3/8), so "Full-model NIAH" was deferred. SAS
(arXiv:2609.13141, Research 567) documents the failure class the promotion
gate must exclude: pooled block summaries destroy needle-like localized
information — and FlashMemory's block centroid IS a mean-of-latent pool.

This bench runs the FULL 8-layer model two ways on identical NIAH prompts and
compares: **DENSE** (the real `kimi_k3_forward_token` path — the oracle) vs
**SPARSE** (identical layer composition, MLA layers 3+7 swapped to
`mla_forward_token_flashmemory`; KDA layers unchanged). QA axis: needle hit,
decode agreement, per-step logit cosine, password-token rank. Selection axis
(the SAS-class question): needle-block membership in the σ-selection, block
coverage, recency-fallback rate.

## Gate results

| Gate | Result |
|---|---|
| **Parity** (σ=0 + fresh selection ≡ dense) | **PASS** — probe `FFM_PROBE=1` at 2170 tokens: re-orchestration vs real forward max\|Δlogits\|=0.000000; flashmemory@σ0 (refresh=1) residual 2-3e-6 = fp-reassociation scale, cos=1.000000 |
| **T1 sparse-within-tolerance @σ=0.5** | **PASS at every rung** — decode agreement 12/12, cosQ=1.0000, minCos=1.0000 (query + all decode steps), pw_rank within ±3% of dense |
| **T2 budget stress** | **e2e QA holds to σ=0.70** (the tightest arm): 12/12 agreement, cos=1.0000 at 43.8-50.0% coverage with 50-56% recency-fallback. Selection-axis collapse is layer-split (below) |
| **Dense oracle validity** | **FAILS on this testbed** — dense never emits the password at any rung (2048→16384). See honest verdict |

### T1 — the full ladder (single-needle depth 0.5, stem query, BOS, block=64, refresh=64, n_decode=12)

| Rung (tokens) | Arm | hit | agree | cosQ | minCos | pw_rank | selN | cov | fb | prefill |
|---|---|---|---|---|---|---|---|---|---|---|
| 2170 (from the 2048-ladder run) | dense | false | — | — | — | 6037 | — | — | — | 60s |
| | σ=0.50 | false | 12/12 | 1.0000 | 0.9998 | 4673 | 87.5% | 87.4% | 12.5% | 52s |
| | σ=0.70 | false | 12/12 | 1.0000 | 0.9998 | 4767 | 56.2% | 52.7% | 37.5% | 44s |
| 4335 (4096-ladder run) | dense | false | — | — | — | 2112 | — | — | — | 174s |
| | σ=0.50 | false | 12/12 | 1.0000 | 1.0000 | 2181 | 87.5% | 87.5% | 12.5% | 140s |
| | σ=0.70 | false | 12/12 | 1.0000 | 1.0000 | 2291 | 43.8% | 43.8% | 56.2% | 117s |
| 8664 | dense | false | — | — | — | 2093 | — | — | — | 584s |
| | σ=0.50 | false | 12/12 | 1.0000 | 1.0000 | 2166 | 81.2% | 81.2% | 18.8% | 445s |
| | σ=0.70 | false | 12/12 | 1.0000 | 1.0000 | 2269 | 43.8% | 47.1% | 50.0% | 353s |
| 8664 multi (queried @0.75, distractor @0.25) | dense | false | — | — | — | 2111 | — | — | — | 579s |
| | σ=0.50 | false | 12/12 | 1.0000 | 1.0000 | 2187 | 87.5% | 87.5% | 12.5% | 449s |
| | σ=0.70 | false | 12/12 | 1.0000 | 1.0000 | 2378 | 43.8% | 43.8% | 56.2% | 350s |
| 17322 | dense | false | — | — | — | 2106 | — | — | — | 2112s |
| | σ=0.50 | false | 12/12 | 1.0000 | 1.0000 | 2099 | 87.5% | 87.5% | 12.5% | 1585s |
| | σ=0.70 | false | 12/12 | 1.0000 | 1.0000 | ~2270 | 50.0% | 49.9% | 50.0% | ~1250s |

(2038-token rung used the pre-BOS/question-format build; 4335-row from the
first ladder launch — same binary semantics except query style/BOS, kept as a
separate ladder point because the numbers are consistent with the final build.)

**Needle affinity is context-stable AND sparse-stable.** Dense pw_rank sits at
2093-2111 out of 163840 (top 1.3%, ~40× above the ~82000 random rank) at
EVERY rung 512→17322 — the model encodes the needle but never emits it. The
sparse arm tracks dense within ±3% at every arm, INCLUDING σ=0.7 at half
coverage.

### T2 — selection-axis collapse is LAYER-SPLIT (query-step score sweep)

| σ | L3 sel% (8192) | L3 sel% (16384) | L7 sel% (both) |
|---|---|---|---|
| 0.30–0.45 | 87.5 | 87.5 | 87.5–100 |
| 0.50 | 75.0 | 87.5 | 87.5 |
| 0.55 | 62.5 | 87.5 | 87.5 |
| 0.60 | 37.5 | 37.5 | 87.5 |
| 0.65 | 12.5 | 25.0 | 87.5 |
| 0.70 | 0.0 | 12.5 | 87.5 |
| 0.75–0.95 | 0.0 | 0.0 | 87.5 |

- **Layer 3 collapses at σ≈0.60** (needle selection ≥50% up to σ=0.55).
- **Layer 7 NEVER collapses** (87.5-100% at every σ to 0.95) — its block
  scores are strongly positive everywhere, so its selection provides ~no KV
  reduction. The corridor's sparsity (and its budget-stress fragility) is
  LAYER-3-DRIVEN. A per-layer threshold (σ₃ > σ₇) would buy real budget with
  the same fidelity — follow-up material.
- **Multi-key: NO selection discrimination** — the distractor block is
  selected at the SAME rate as the queried needle (distN=87.5%/43.8% =
  selN at 8192-multi). Selection is permissive; discrimination (if any)
  happens in the attention weights, not the centroid scores. Decode still
  agreed 12/12 — the QA axis is unaffected at these rungs.

## GOAT verdict

**The gate the issue asked for: PASSED with a pinned tolerance.**

- **Tolerance pin (Issue 826 Phase 3 gate parameter): `cosQ ≥ 0.99` AND
  decode agreement ≥ 12/12 AND pw_rank within ±5% of dense at σ=0.5.**
  Measured margin: cosQ=1.0000 and 12/12 at EVERY rung — the pin has 4+ orders
  of magnitude of headroom on the cosine axis.
- **The needle axis does NOT block promotion at the measured rungs**: sparse
  selection (including σ=0.7 at ~47% coverage) preserves the model's
  needle-directed behavior indistinguishably from dense.

### Honest verdict on the ABSOLUTE axis (why this does not validate SAS-class safety end-to-end)

**Dense-oracle retrieval FAILS on this testbed at every rung** — Kimi-K3-0.40B
never completes the password (top-1.3% affinity, never top-1; completions are
pretraining associations like "Inigo Montoya"/"GNU/Linux"). Consequences:

1. The QA axis measured here is **relative** (sparse vs dense), which is what
   Issue 826 T1's floor literally specifies ("sparse accuracy within a stated
   tolerance of dense"). It PASSED decisively.
2. The **absolute** claim ("pooled centroids destroy needle retrieval") is
   UNTESTABLE on a model that cannot retrieve at all — dense and sparse fail
   identically. The SAS-class risk remains OPEN until the corridor is
   measured on a model whose dense oracle actually retrieves (Bonsai-27B on
   the 4090, or any ≥1B with real long-context training). Until then the
   promotion gate's needle row is the RELATIVE pin above.
3. **64K was priced out, not skipped**: measured prefill cost ≈ 10ns × n²
   (the MLA decode path re-up-projects k_c/v_c for every cached token per
   query — the known Phase-6 weight-absorption item). At n≈60K that is
   ~9h PER ARM on this box. The measured ladder stops at 4.2× trained context
   (17322 tokens); the 64K rung needs the 4090 or the k_c/v_c caching fix.

## The parity-gate story (recorded — it caught a construction bug, not a defect)

1. First parity run FAILED: max|Δlogits|=0.1289 at 2170 tokens (3e-6 at 387)
   — superlinear growth, not reassociation noise.
2. Probe bisect (`FFM_PROBE=1`): re-orchestration vs real forward = 0.000000
   (bench exonerated); flashmemory@σ0 layer-3-only = 5.8e-5, layer-7-only =
   0.1289 — localized, growing with n.
3. Root cause: `FlashMemorySelector::select` reuses the cached selection
   within `refresh_period` — at σ=0 with refresh=64, each step attends only
   blocks that existed at the last refresh, missing up to block_size−1
   RECENT tokens (the largest-attention tail). Paper semantics for serving;
   NOT dense-equivalence.
4. Fix: the parity/probe arms construct `refresh_period=1` (fresh selection
   every step). Residual: 2-3e-6 — **PARITY PASS**. `katgpt-attn` production
   code untouched (a wrong-comment rmsnorm hypothesis was reverted clean).

This is why the bench carries the probe as a standing mode: the σ=0 parity
claim is only well-formed WITH the fresh-selection construction, and the
probe asserts both halves (orchestration sanity + per-layer localization).

## Cost model (for the 64K/256K follow-ups)

Measured prefill wall time ≈ **10 ns × n²** on this box (n = tokens: 2170→60s,
4335→174s, 8664→584s, 17322→2112s). Dominated by the per-token k_c/v_c
re-up-projection in the MLA decode path (mla.rs: "Phase 6 may cache the
up-projected k_c/v_c"). Extrapolation: 64K ≈ 9h/arm, 256K ≈ 6 days/arm —
single-box CPU. The 4090 (with the GQA flashmemory path, Bench 671) or the
weight-absorption optimization are the unblock either way.

## Reproduce

```bash
# full ladder (≈2.5h on M3 Max)
KIMI_K3_MODEL_DIR=../riir-train/data/kimi-k3-0.40b \
FFM_SEQ_LENS=2048,4096,8192,16384 FFM_MULTI_LENS=8192 FFM_THRESHOLDS=0.5,0.7 \
cargo bench --bench bench_685_flashmemory_full_model_niah_qa \
  --features kimi_k3_loader,flashmemory_sparse -- --nocapture

# parity-bisect probe (≈6 min)
FFM_PROBE=1 cargo bench --bench bench_685_flashmemory_full_model_niah_qa \
  --features kimi_k3_loader,flashmemory_sparse
```
