# Issue 841 — Cactus/Needle sweep follow-ups (katgpt-rs-owned leads)

> ⚠ **Renumbered 840 → 841** (2026-09-18): dual allocation — a concurrent session holds `.issues/840` upstream, itself a record of this same session's 569 research dual-allocation (`cf6eb54f0`…`a2ff2a6f5`); the upstream holder keeps 840, this note lands as 841.

**Status:** OPEN — leads consolidated from Research 568/569/570/571 (22-source Cactus Compute sweep, 2026-09-18). One checkbox per lead; `- [-]` = deliberately deferred with reason. Cross-repo training leads live in `../riir-train/.issues/561_cactus_training_leads.md`.

## Primitive / league lane (katgpt-rs + riir-gpu consumers)

- [ ] **CQ-W2A8 never-unpack GEMV** (Research 568 fusion 1): rotate each 128-lane activation group via existing `hadamard_transform_inplace()`, int8 per-group scale, dot through Plan 431 LUT with int8 accumulate + one per-group scale multiply. Flag `cq_w2a8`; head-to-head vs Plan 486 `gemv_q4_k_row_lut`; measure the per-group FWHT amortization claim, don't assume it.
- [ ] **CLAWS activation-sparse decode cell** (Research 571 §C-15): per-neuron Fisher-style `cᵢ` LUT (offline calibration) × GeGLU gate scores → `argtopk_with_scratch` mask → Q4_K GEMV skips masked K-superblocks. ⚠ re-run x86_64 execution matrix (Bench 806 argtopk class). Bar: dense-level quality at 50% density, ≥1.2× MLP block.
- [ ] **HiDRA-v2 on the Bench 688 permanent negative** (Research 571 §C-16): LDA median-split tree init (closed-form, modelless arm FIRST) → beam routing + truncated scoring; reuse Issue-666 `ClusterLayout` packed rows; gate on the existing 123-probe real-checkpoint harness. riir-train BCE per-node training only if the modelless arm stalls. Verify router-storage cost (≈V·d, same size as head) before claiming a win.
- [ ] **TurboQuant-H riir-rag index lane** (Research 571 §B-11): 2.125-bpw Hadamard + per-group Lloyd-Max over the embedding index via `group_lut_at` 4-entry LUTs. **Gate = recall@k vs f32, not PPL.** Open question: quantize-then-wedge vs wedge-then-quantize vs Clifford-wedge KNN.
- [ ] **KV permanent sinks + bounded window** (Research 571 §B-8): pin system/tool tokens as non-evicting attention sinks + 256-token sliding window ⇒ deterministic RAM ceiling. Grep-clean today (nothing ships). Fuse with KVarN; league + riir-esp32 relevant.
- [ ] **Grammar-forced vocab-projection skip** (Research 571 §B-8): lodestar knows the legal token set per state — extend so forced/structural steps skip vocabulary-projection rows entirely (their ≤98% claim) instead of score-then-filter in `find_valid_token`. Exact-path, token-for-token validated.
- [ ] **functional_embed (PETE-distill)** (Research 571 §C-13): Fourier-of-token-ID features `T(p)` + closed-form ridge/ALS distillation of shipped `wte` via KARC — zero GD. Gates: ≥0.98 mean cosine on Bonsai table + riir-rag recall + decode. Free first step: permute-tokens ablation on our BPE tokenizer.
- [ ] **SAN league cell** (Research 570): gated on an artifact — convert a shipped SAN checkpoint (paper ships checkpoints) or serve `needle3.cact`; flag `san_decode`; bytes/token-at-matched-params comparison vs llama.cpp.

## Fusion ideas, novelty-TBD (issue-first per the gate — do NOT promote without §4 searches)

- [ ] **`.kpt` archive** (Research 568 fusion 2): .cact-style nameless positional layer-major single-file mmap × NeuronShard Pod × **BLAKE3/Merkle integrity .cact lacks**; atomic weight hot-swap = file replacement. Format+engine lift; owner call before any plan.
- [ ] **Engram-delta as the modelless fine-tune** (Research 571 §B-8 fusion 1): write product tool-vocabulary into `StagingEngramTable` → commit → `EngramHotSwap` → freeze envelope → chain-commit. GOAT gate vs LoRA fine-tune (accuracy/latency/training-cost=0). Prior-art class: kNN-LM/RETRO/product-key memories — pin the claim to *zero-training specialization + committed deltas* before any tier claim.
- [ ] **SAN npc_brain v2** (Research 571 §C-12 fusion 1): trained tiny attention-only brain (SAN recipe: QK-norm + sandwich norm + Muon) on trace-dense corpora; knowledge stays context-side per the query-deficit finding. Blocked on a multi-layer brain consumer.

## Boundary / hygiene (cheap, boundary-shaped)

- [ ] **Calibration-staleness rule at the freeze/thaw seam** (Research 571 §B-3): a snapshot swap must invalidate attached calibration/confidence heads — expose `None` + one-time loud warning, never a stale plausible score. Extends the freeze-envelope schema; pairs with the UQ "Report the Floor" rule (discrete-decision corollary: beat a base-rate/Platt floor on ECE + selective-risk@coverage).
- [ ] **fix_verify refusal-vs-truncation audit** (Research 571 §B-9): verify a killed mid-verify re-check cannot read as a verified keep; if indistinguishable, port the completion-sentinel pattern (flagged unverified — audit the kill path first).
- [ ] **riir-rag embedder-identity fingerprint** (Research 571 §B-4): `index_code_triples_if_changed` stores per-file content hashes — verify the stored fingerprint includes embedder identity; an embedder swap would keep hashes matching while embeddings go stale. One-file read of `retriever.rs` first.

## Deferred

- [-] Ships-manifest per-platform gate (Research 571 §B-5 F1): real, but this repo's lane is primitives; `wasm32_surface_audit` covers the load-bearing half. Park until a deploy surface asks for it.
- [-] WASI Preview 2 component target (Research 571 §B-5 F3): zero host consumers; revisit if riir-esp32 or an edge host materializes.
- [-] KV-cache QAT (Research 571 §B-8): riir-train seed — lives in riir-train issue 561.
