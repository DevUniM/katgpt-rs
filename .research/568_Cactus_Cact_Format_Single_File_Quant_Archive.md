# Research 568: The .cact Format — Single-File mmap Weight Archive + Never-Unpack CQ2 Kernel

> **Source:** "The .cact Format" — Parkirat Sandhu, Cactus Compute blog, 2026-09-18. https://cactuscompute.com/blog/cact-format
> **Date:** 2026-09-18
> **Status:** Done — distillation + per-track verdicts (GOAT-plan on the kernel read path; format fusion = issue-first)
> **Related Research:** 020 (TurboQuant), 065 (RotorQuant/PlanarQuant/IsoQuant — rotation hierarchy), 159 (KVarN — Hadamard KV quant, dormant flag), 418 (StreamDQ — LUT dequant), 110 (Ciot ternary CPU — "Cold = Q4_K dequant-on-read"), 200 (quant outlier collapse), 265 (b-posit storage format), 109 (Shard-Drop KV compression)
> **Related Plans:** Plan 431 (`simd_lut_dequant`, default-on katgpt-core), Plan 486 (riir-engine fused Q4_K LUT GEMV, `simd_lut_q4k`), Plan 100 (Q4_K WGSL +52% decode)
> **Classification:** Public

---

## TL;DR

Needle ships as **one file the engine mmaps and reads in place**: a **196-byte header** (49 × u32 fields carrying the *entire* architecture geometry + the numerics), a **nameless positional tensor directory** (44 B/record, layer-major for contiguity), and **Cactus-Quantised (CQ) blobs** at **2.125 bits/weight (CQ2)** / 4.125 (CQ4). The quantization is the QuIP# class: rotate each 128-weight group with the normalized Walsh-Hadamard matrix so every group looks Gaussian, split into fp16 norm + Lloyd-Max-quantized direction, cost = `b + 16/128 = b + 1/8` bits/weight. The kernel **never unpacks weights**: it rotates the *activation* group with the same H (FWHT butterfly in registers), quantizes rotated activations to int8 per-group scale, and the dot product is a LUT lookup of int8 centroids by packed indices + `sdot` accumulate + one multiply per group — the weight-side rotation cancels the activation-side rotation because H is orthogonal. The 20-layer `needle3.cact` is **29 MB / 581 tensors**; one engine binary **under 1 MB** serves the whole 2–20 layer depth ladder because the geometry rides in the header.

**Distilled for katgpt-rs (modelless, inference-time):**
Three separable claims: (a) **the quant math** — QuIP#/QuaRot published class (Hadamard incoherence + codebook), NOT novel, and our Plasma ternary already runs at 1.58 bpw; (b) **the never-unpack kernel read path** — rotate-activation/int8-sdot/LUT-centroid GEMV, the sharper form of our Plan 431 LUT + Plan 486 fused GEMV (we dequant weights→f32 then dot; they never materialize a float); (c) **the format** — zero-parse single-file mmap archive with numerics-pinned-in-blob and header-driven depth ladder, the same design philosophy NeuronShard already validates (Pod, positional, zero-copy) but applied to a full model archive.

---

## 1. Source Core Findings (all numbers from the blog)

### 1.1 Layout
- **Header, 196 bytes**: 49 × u32 — format tag, tensor count, codebook length, then the whole geometry (vocab, width 768, 12 Q-heads / 2 KV-heads, layers, head_dim, ctx 8192, Hadamard size, residual lanes, sliding window 1024, global-attn bitmask, conv taps, engram params) + two **numerics** fields (`kv_window`, `kv_bits`) + `rope_theta` as f32.
- **Codebooks, 112 bytes**: 28 f32 = the 4/8/16-entry **Lloyd-Max** codebooks for 2/3/4-bit weights. Ternary + binary are analytic (closed-form centroids) → not stored.
- **Directory, 44 B/tensor**: `u8 dtype, u8 ndim, u16 pad, u32 shape[4], u64 offset, u64 nbytes, u32 group, u32 bits`. **No names** — positional, layer-major so one block's working set is one contiguous file span (cache + prefetcher friendly).
- **Blobs**: 64-byte aligned; matrices **pre-transposed `[out, in]`** so output rows are contiguous along the reduction axis and groups run along it.
- **Tokenizer**: RAW attachment = self-contained SentencePiece BPE dump (111 KB).

### 1.2 CQ quantization (the 2.125 math)
- Groups of **128 weights along the input dim**; group is first rotated by normalized **Walsh-Hadamard** H → every group looks Gaussian → **one codebook fits all groups**.
- Rotated group split into: **length (fp16 norm, 16 bits)** + **direction (b-bit Lloyd-Max indices, 128·b bits)** → cost/weight = `b + 1/8` → **2.125 (CQ2), 3.125 (CQ3), 4.125 (CQ4)**.
- Reconstruction: `w = (codebook[idx] · norm) · H`; H symmetric + orthogonal → **its own inverse, nothing to invert**.
- Ternary: separate 2-bit "crumb" encoding, sign-extends to −1/0/+1 in-kernel; binary packs 8/byte.
- Bit packing: one continuous LSB-first stream per row.

### 1.3 Never-unpack kernel (CQ-W2A8)
- Take activation → **rotate each 128-lane group with the same H** (fast Walsh-Hadamard butterfly in registers) → quantize rotated activation to **int8 with one scale per group**.
- Dot product = **LUT lookup of int8 centroids by packed weight indices** → int8 `sdot` accumulate → **one multiply per group** by (weight norm × activation scale × codebook scale).
- Weight-side H cancels activation-side H (orthogonal) → **exact up to quantization itself; no weight ever materialized as a float**.
- Mixed precision per directory records: block matrices CQ2; embedding (tied output head), lane maps, confidence head CQ4; norms/Hadamard diagonals/gates/conv taps/biases FP16.
- Same path serves the KV cache at whatever `kv_bits` the header declares.

### 1.4 File economics (needle3.cact, 20 layers)
- **29 MB**, 581 tensors: 115 CQ2 tensors = **85% of bytes** (five engram n-gram tables — 110,592 rows × 128 — are **2/3 of weight bytes** on their own); 7 CQ4; 456 FP16 < **4%** of file.
- Depth ladder: `needle build --layers 8` keeps the blocks depth selects, writes `num_layers = 8` + matching engram sites into the header → **one engine < 1 MB serves 2..20 layers**; a 2-layer fine-tune export = a few MB.

### 1.5 The tag is the contract
- `0x05E12A83` = Needle 2, `0x05E12A84` = Needle 3; wrong generation → **refuse with a message, never guess**. Within a generation, rebuild rather than patch. Numerics live in the blob because "leaving either to a runtime flag would silently serve the wrong numerics."
- 20-line stdlib Python parser exists (`read_export` in the package is the dequant reference).

---

## 2. Distillation

### 2.1 Prior-art pin (before any novelty claim)
**Claim pin:** "Hadamard-rotated grouped codebook quantization with never-unpack int8-sdot kernel read, delivered as a single-file zero-parse mmap archive" — for our serving/edge lane, consuming the file's bytes directly, distinguished from GGUF (generic, name-resolved, loader-converts) and from QuIP# (method, no format) by the fusion of method+format+kernel into one contract.
- **QuIP# (Tseng et al., ICML 2024)** + QuIP (Chee et al., NeurIPS 2023): randomized Hadamard incoherence processing + lattice codebooks, SOTA ≤4-bit/2-bit weight-only PTQ. → The rotation-makes-Gaussian idea is **published prior art**; .cact's CQ is a Lloyd-Max (product/spherical) variant, not E8 lattices.
- **GGUF/safetensors**: both name-resolve tensors and require loader-side conversion; .cact's contribution is bytes-are-already-the-shape-the-kernel-wants (pre-transposed, aligned, never-unpacked).
- **Our own stack already carries the rotation class for KV**: KVarN (Research 159, `katgpt-kv/src/kvarn/hadamard.rs`, flag currently `false` in benches), `hadamard_transform_inplace()` in `shard_kv`, OCTOPUS WHT (Research 063), PlanarQuant/IsoQuant (Research 065). Q4_K cold path + Plan 431 LUT + Plan 486 fused GEMV carry the read path at 4 bits.

### 2.2 The three separable primitives

| # | Primitive | Modelless? | Our status |
|---|---|---|---|
| P1 | Rotation+codebook 2.125-bpw weight encoding | Yes — Lloyd-Max is closed-form/deterministic; reconstruction needs no training | Ternary Plasma already at **1.58 bpw** (lower); Q4_K at 4 bpw sits between CQ2 and CQ4. No weight-side rotated-codebook format ships |
| P2 | **Never-unpack W2A8 kernel** (rotate activation, int8 sdot, LUT centroids) | Yes — pure inference mechanics | **Gap**: Plan 431/486 dequant weights→f32 then f32-dot; nothing rotates activations or dots in int8 |
| P3 | **Single-file zero-parse mmap archive** (fixed header + nameless positional directory + numerics-in-blob + depth ladder) | Yes — static artifact format | **Half**: NeuronShard validates the philosophy (Pod, positional, zero-copy mmap, BLAKE3/Merkle); no full-model archive in this shape — we load GGUF (league) / safetensors (Plan 087) |

### 2.3 Signal-diff vs closest cousins (§3.6 discipline)
- vs **Plan 431 LUT dequant**: 431 replaces the int→fp *cast* with a LUT, still dequantizes to f32 and dots in f32. .cact keeps centroids in **int8** and dots in int8 — the never-materialize step is the uncovered delta, and it composes with 431 (the centroid LUT IS a LUT).
- vs **Plan 486 fused GEMV**: same slot (decode GEMV), different arithmetic core (f32 accumulate). The .cact form's per-group FWHT on the *activation* amortizes across all output rows of a block (activations reused per group-column; weights pre-transposed so groups align) — the reason the design is affordable.
- vs **KVarN hadamard (KV)**: same transform, other operand — KVarN absorbs H into W_K/W_V for KV tiles at rest; .cact rotates *activations per matmul* against *stored rotated weights*. The blog's `kv_bits`-in-header discipline is directly applicable to KVarN's config surface (numerics pinned in the artifact, not a runtime flag).
- vs **NeuronShard**: NeuronShard is a fixed-layout single-purpose Pod (positional, mmap, BLAKE3/Merkle-committed, freeze/thaw envelope). .cact generalizes the shape to a *model archive* — but ships **no integrity** (no checksum at all); our Merkle/BLAKE3 envelope is strictly stronger and would be a differentiator, not a copy.

---

## 3. Verdict — per track (TTPO rule: one verdict per track)

| Track | Content | Verdict | Reason |
|---|---|---|---|
| **(a) Modelless inference** | P2 never-unpack W2A8 kernel | **GOAT-plan** | Better numbers on an existing slot (decode GEMV — Plan 486's `gemv_q4_k_row_lut`), league-relevant (M3/4090 decode), concrete G1–G4 gate: exactness of H-cancellation, ns/call vs 486, 0-alloc. The only `[/]` risk: per-group FWHT cost — amortization argument above must be measured, not assumed |
| **(a) Modelless inference** | P3 single-file mmap archive | **Gain → issue-first** | Real capability (one fetch, zero loader, depth ladder, `<1 MB` engine), but a format+engine integration, not a kernel win; novelty of "BLAKE3/Merkle-committed single-file model archive" unverified → `.issues/` fusion entry before any plan |
| **(a) Modelless inference** | P1 2.125-bpw weight encoding | **Pass** (for weights) | QuIP#-class published method (cite above); our ternary already ships 1.58 bpw on the lane we serve. P1 becomes relevant only as the encoding *inside* P3/P2 |
| **(b) Self-adaptive runtime** | Nothing direct | **Pass** | .cact is a static artifact — no runtime latent updates. Tangential: numerics-in-blob = freeze/thaw versioning philosophy match |
| **(c) Model-based training** | 2-bit archive produced by platform post-training; fine-tune "trains through these numerics at 4 bits" (QAT) | **→ riir-train (recorded, no plan now)** | QAT-at-4-bits + PTQ codebook fitting = riir-train territory; we already hold the class (Research 202 QAT Infusion, 538 GDN W4A4, 534 FP4 FA4). No new recipe beyond "train at the deploy numerics" — which 202 already covers |

**Tier verdict: GOAT-plan** (P2), with P3 filed as an issue. Not Super-GOAT: the headline mechanism's math is published prior art (QuIP#), and the format win, while genuinely new *for us*, is an engineering capability rather than a new inference-behavior class.

**MOAT gate (katgpt-rs):** P2 is squarely in-scope — "quant-aware inference" + SIMD kernels + the decode hot path; engine stays MIT-open (matches Research 159's license split: rotation/LUT/dequant = Engine layer). P3's integrity half (Merkle-committed archive) is **riir-neuron-db** moat territory — cross-repo fusion, file the issue there if pursued.

---

## 4. Stack mapping

| .cact mechanism | Closest shipped | New? | Rating |
|---|---|---|---|
| Never-unpack W2A8 (rotate act, int8 sdot, LUT centroid) | Plan 431 `simd_lut_dequant` (default-on), Plan 486 fused Q4_K GEMV (2.0–2.3× on real blocks) | int8-sdot + activation rotation + zero float materialization | **GOAT** (existing slot, league-relevant) |
| Single-file mmap, fixed header, nameless positional dir | `NeuronShard` Pod (positional, zero-copy mmap); GGUF (league serving); safetensors loader (Plan 087) | Full-model archive in NeuronShard's philosophy; depth ladder via header | **Super-GOAT-fusion-shaped** (issue first) |
| Numerics in blob (`kv_bits`, `kv_window`) | KVarN config surface (`bits`, `hadamard` flags, currently runtime-selected); feature-gate/profile-is-part-of-claim discipline | Pinning KV numerics into the artifact/config contract | **Gain** |
| H² = I self-inverse | RotorQuant lesson 7 (WHT self-cancels; Givens inverse bug = PPL 15,369) | Nothing — validates shipped lesson | — |
| Depth ladder (2..20, one `<1 MB` engine) | Fixed Bonsai/qwen3.8 arch; ELT anytime-inference research (273) | Header-driven layer subsetting | **Gain** (future) |
| Embedded tokenizer RAW attachment | `SentencePieceGgufTokenizer` (GGUF embeds tokenizer) | Nothing | — |
| Tier placement | `bench_148` tier table: Hot FP16 → Warm SpectralQuant 3–4 bpw → **Cold Q4_K 4 bpw** → Freeze Turso | A CQ2-style row **below** Cold at 2.125 bpw ("Deep-Cold") | **Gain** (tier-table row) |

## 5. Fusion ideas (sharpest 3)

1. **FWHT-activation + LUT-centroid + int8-sdot GEMV** × Plan 431/486 (the GOAT): rotate each 128-lane activation group once per forward (our `hadamard_transform_inplace()` already exists), quantize to int8 per-group scale, dot against stored rotated-codebook weights via the 431 LUT with int8 accumulate + one per-group scale multiply. Feature flag `cq_w2a8`; gate vs Plan 486 GEMV; target the Bonsai-27B decode league cell.
2. **`.kpt` archive = .cact layout × NeuronShard × MerkleFrozenEnvelope**: nameless positional layer-major directory, 64-B aligned pre-transposed blobs, fixed header + **BLAKE3 root commitment + Merkle over the directory** (integrity .cact lacks), the whole file versioned as a freeze envelope → atomic weight hot-swap = file replacement; single-fetch edge/browser distribution (seal-remake wasm32 lane); deploy artifact = one file (riir-deployer).
3. **Deep-Cold tier row + numerics-in-artifact**: CQ2-style 2.125-bpw encoding as the tier *below* Q4_K Cold for archive/cold-boot (read path = fusion 1), with `kv_bits`-style numerics pinned in `NeuronShard`/config headers so a snapshot declares the numerics it was built for.

## 6. Citation quotes (exact, with numbers)

1. "A model that runs on a router or a watch cannot afford a loader. It cannot parse JSON, resolve tensor names, convert dtypes, or hold two copies of the weights while it rearranges one into the other."
2. "__Header, 196 bytes.__ Forty-nine 32-bit fields: a format tag, the number of tensors, the codebook length, then the entire architecture geometry"
3. "They are in the blob because a model quantised for one must be run at it; leaving either to a runtime flag would silently serve the wrong numerics."
4. "Multiplying a group by the normalised Walsh-Hadamard matrix H spreads every weight's energy across all 128 coordinates, so whatever the group looked like before, after rotation it looks like a sample from a Gaussian."
5. "What is written per group is 128·b bits of indices and 16 bits of norm, so the cost per weight is b + 1/8: 2.125 bits at CQ2, 4.125 at CQ4."
6. "The rotation on the weight side cancels against the rotation on the activation side because H is orthogonal, so the answer is exact up to the quantisation itself, and no weight is ever materialised as a float."
7. "For a matmul it takes the activation, rotates each 128-lane group of it with the same Hadamard transform (a fast Walsh-Hadamard butterfly in registers), and quantises the rotated group to int8 with one scale per group."
8. "The 20-layer needle3.cact is 29 MB of 2-bit weights in 581 tensors. 115 of them are CQ2 and carry 85% of the bytes"
9. "That is how one engine under 1 MB serves the whole ladder, and how a fine-tune exported at 2 layers ends up a few megabytes."
10. "0x05E12A83 is the Needle 2 format and 0x05E12A84 is Needle 3; the Python package reads the first four bytes and picks the matching engine, and an engine handed the other generation's tag refuses with a message rather than guessing."

## 7. Follow-ups

- [ ] If pursued: `.issues/` entry for fusion 1 (CQ-W2A8 GEMV vs Plan 486 GEMV gate) — GOAT-plan path.
- [ ] If pursued: `.issues/` entry (riir-neuron-db side) for fusion 2 (.kpt archive × Merkle envelope) — novelty TBD before any plan.
- [ ] `[-]` QAT-at-deploy-numerics note → riir-train backlog (covered by Research 202's class; no new plan).
