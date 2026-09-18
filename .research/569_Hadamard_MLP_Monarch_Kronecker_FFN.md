# Research 569: Hadamard MLP — Kronecker-Factored FFN at WHT Initialization (Cactus Needle 3)

> **Source:** ["The Hadamard MLP: Channel Mixing for Almost No Parameters"](https://cactuscompute.com/blog/hadamard-mlp) — Henry Ndubuaku, Cactus (cactuscompute.com), 2026-09-17. Engineering blog distilling the Needle 3 architecture (same org as the `.cact` format, Research 568).
> **Date:** 2026-09-18
> **Status:** GAIN — distill filed; class-level prior art (Monarch, Dao et al. 2022) kills Super-GOAT at Q1; actionable halves filed as katgpt-rs Issue 839 (modelless Kronecker-tile primitive) + riir-train recipe plan suggested (training track, not filed this session)
> **Related Research:** 159 (KVarN — ships the tile row/col Hadamard + `hadamard` flag), 65 (RotorQuant — WHT-butterfly vs rotor/iso/planar rotation table for quant), 418 + Plan 452 (StreamDQ SIMD LUT dequant — the near-memory DQ analog; NOTE the LUT-dequant plan is 452, not 431 — 431 is cross-stage relocation), 568 (Cactus `.cact` single-file 2-bit archive — same org as Needle), 511 + 387 + 455 (memory-layers / PKM / Hebbian MLP — the "engram" lane), 452 (RoVE — matrix-mixer lens, Kronecker `A ⊗ W_V` vocabulary), 008 (TwELL sparse MLP), 390 (Expand Neurons Not Parameters PASS)
> **Classification:** Public

## TL;DR

Needle 3 replaces the transformer FFN `W₂ σ(W₁x)` (4.7M params @ d=768, 4× width) with a **Monarch-structured channel mixer**: three Kronecker stages `Mₛ = Aₛ ⊗ Bₛ` (A,B ∈ ℝ³²ˣ³², tile n=1024 = 32×32) with fixed random permutations between stages, four learned diagonals, one bias, and a rank-8 input-conditioned channel gain `c(x) = 1 + softmax(xV)U`. **"Starts as WHT and learns from there" is initialization, not constraint**: the Walsh matrix is itself a Kronecker product, so `A = B = H₃₂` at step 0 is an exact Hadamard transform, and every gradient step can move the factors — the only retained constraint is the Kronecker/Monarch block structure, never the WHT values. Per layer: **25.6K params vs 4.7M (180×), ~0.21M MACs/token vs 4.7M (22×)**; model-level (20 blocks): 94M fewer params (121M not 215M) and 100 vs 296 MFLOPs/token, attention + engram unchanged. Quality is argued indirectly (a 121M model beating 10× models on mobile tool calls; 400–4,000 tok/s decode on a Raspberry Pi 5) — **no perplexity deltas are published**, and the post itself flags knowledge-heavy general text as the open question. The knowledge role moves to the **engram**: 70.8M of 121M params are hashed n-gram tables read by gather, "costing no arithmetic at all."

## 1. Core mechanisms

- **Kronecker apply as tile GEMMs.** `(A ⊗ B) vec(Z) = vec(Aᵀ Z B)` — two 32×32×32 products = 65,536 MACs vs 1024² ≈ 1.05M dense, 2,048 params vs ~1M. Applied "in registers" on a tile that fits vector registers; a layer's whole mixer is a few hundred FMAs per lane with no weight matrix to stream — the bytes argument, not the FLOPs argument, is what the engine cashes in.
- **One Kronecker stage is not enough** — it mixes only within rows and within columns; channels in different rows AND different columns never meet. The fix is the butterfly fix: **fixed random permutations Π₁, Π₂ between stages**. Three stages ⇒ every channel has a path to every other = the Monarch construction (Dao et al. 2022).
- **Initialization vs constraint (the headline phrase).** H₂ₙ = [[Hₙ, Hₙ],[Hₙ, −Hₙ]] is recursive, so H₁₀₂₄ = H₃₂ ⊗ H₃₂ (up to scaling): setting A = B = H₃₂ makes stage 1 of training an exact WHT. Needle 2 kept the rotation FIXED with learned diagonals either side; Needle 3 makes the rotation learnable. Gradients flow into Aₛ, Bₛ through the two tile GEMMs (standard product rule on `Aᵀ Z B`); diagonals D₁–D₄ and the rank-8 V,U train normally; D₄ inits at 0.02 (small residual-write, same convention as attention out); U inits at zero so c(x) ≡ 1 at step 0.
- **Why it loses so little.** (a) Monarch is expressive enough to represent the dense mixers transformers actually learn (Dao's claim); (b) on tool-shaped routing data "the block's job is to route and transform what is already in context, that expressivity was not where the loss lived"; (c) the storage role moves to the engram gather-memory; (d) the rank-8 gain buys a little of the input-dependence a wide FFN gets from width ("bought with a vector rather than a matrix"). Explicit caveat in-post: 3 Kronecker mixes + permutations cannot represent all linear maps, and c(x) is "a narrow substitute."

## 2. Track classification (Path 0 decomposition)

| Component | Training-loop or math? | Modelless analog in our stack |
|---|---|---|
| Kronecker tile apply (65,536 MACs/stage) | inference math | **partial ships** — `katgpt-kv/kvarn/hadamard.rs` `hadamard_rows`/`hadamard_cols` = the exact tile-row/tile-col apply with A=B=H₃₂; arbitrary learned 32×32 factors = new primitive (Issue 839) |
| WHT init → learn away | training recipe (needs from-scratch training or long fine-tune) | NOT retrofittable to served upstream checkpoints (Research 452 Q3 logic: our engine serves fixed upstream weights). Valid only for models WE train → **riir-train** (TernaryDraftModel / Bonsai-scale drafters) |
| Fixed WHT + learned diagonals (Needle 2 form) | training recipe | WHT-only + fixed diagonals IS modelless-computable, but the quality claim is a trained-model result — no modelless FFN-swap claim is licensed |
| Rank-8 input-conditioned gain c(x) | training recipe (V,U learned) | latent-analog: sigmoid-gated (never softmax) input-conditioned diagonal scaling → `latent_functor/zone_gating` fusion idea |
| Engram (hashed n-gram gather memory, 70.8M params, zero arithmetic) | trained tables, inference = gather | **covered lane** — Research 511 Memory Layers at Scale / 387 PKM / 455 Hebbian memory MLP |

**Verdict:** primarily a **training recipe** (structured init + training); the modelless inference angle is the **tile-apply primitive** (arbitrary-factor Kronecker stage) and the WHT butterfly we already ship — not a modelless FFN replacement.

## 3. Stack mapping — what ships, what's new

**Already ships:**
- `walsh_hadamard_in_place_normalized<const D>` — `katgpt-core/src/meld.rs` (Meld W, G4 zero-alloc witnessed)
- `hadamard_transform_inplace` + `hadamard_rows(tile, cols)` + `hadamard_cols[_into](tile, rows, cols)` — `katgpt-kv/src/kvarn/hadamard.rs` (unsafe non-aliasing butterfly for LLVM auto-vectorization; KVarN `hadamard` flag, Research 159). **This is the A=B=H₃₂ Monarch stage apply, already written.**
- `hadamard_factorize<const D>` — `katgpt-core/src/orthogonal_factorization.rs` (explicit ±1/√n matrix; Parseval/dyadic-exactness anchors, Bench 687)
- TurboQuant WHT-butterfly quant-rotation baseline + rotor/iso/planar comparison — Research 65 (the learnable-rotation direction this blog validates is our RotorQuant lane one step further)
- Ternary SIMD matvec (Plasma hot path) — the fusion target for quantized factors
- LUT dequant — Research 418 / Plan 452 (SIMD LUT DeQuant)
- 2-bit single-file archive — Research 568 (`.cact`, same org); the blog's "shipped 2-bit archive" (~100KB/layer full precision → far less shipped)

**New (not shipped):**
1. Arbitrary-factor Kronecker tile apply `kron_apply(A,B,tile)` (generalize kvarn rows/cols from WHT to learned 32×32 GEMM) — Issue 839
2. 3-stage Monarch composition + fixed random permutations
3. WHT-init → train-away recipe (riir-train, our trained draft models)
4. Rank-8 input-conditioned gain (sigmoid variant)
5. Ternary-quantized Kronecker factors (fusion — see §5)

## 4. GOAT vs Super-GOAT per mechanism

| Mechanism | Tier | Why |
|---|---|---|
| Kronecker-tile apply primitive (modelless) | **GOAT-plan** (Issue 839) | New structured-sparse-matvec slot; class prior art exists (Monarch/Butterfly), so novelty is the composition — GOAT, not Super-GOAT. Super-GOAT upside only if the ternary-factor fusion (§5.1) clears a quality GOAT on a trained model |
| WHT-init structured-FFN training recipe | **GOAT-plan** (riir-train; suggested, not filed) | Applicable training recipe for models we train (drafters); serving-envelope fit is secondary — the hot-path payoff lands only through our own trained checkpoints |
| Engram gather-memory | **PASS/covered** | Research 511/387/455 lane already owns memory-layers-at-scale; no new filing |
| c(x) rank-8 gain | **Gain-level fusion idea** | sigmoid-gated input-conditioned diagonal scaling maps onto `latent_functor` zone-gating; no independent primitive |

**Novelty gate Q1 = NO** (Monarch: Dao et al. 2022, PMLR, 179+ cites; Butterfly 2020; MoST Monarch sparse tuning 2025; learned-permutation Monarch factorization 2025; even "Hadamard and Monarch: Compressing GPT-2 Small", 2026). All four YES fails ⇒ no Super-GOAT.

## 5. Fusion ideas

1. **Ternary-Kronecker FFN (the strongest).** Quantize Aₛ,Bₛ ∈ {−1,0,+1}³²ˣ³² → each stage is two ternary tile matmuls (add/sub accumulate, no multiplies — composes with the ternary SIMD matvec kernels), 6,144 factor weights ≈ 1.5 KB/layer at 2 bits, cache-resident for a session. GOAT gate: trained small-LM quality ternary-factors vs f32-factors vs dense FFN (riir-train lane); G2 perf from the 22× MAC ratio.
2. **WHT-rotation quant adapter.** The post's "fixed rotation + learned per-channel gains is already a surprisingly capable mixer" is the RotorQuant lane's learnable-rotation step (Research 65's TurboQuant row + diagonals) validated from the architecture side — cheap follow-on for our Q4_K/ternary quant pre-rotation.
3. **Cheap-drafter spec decode.** Structured-FFN + engram-gather drafter = more drafter depth per byte — pairs with TernaryDraftModel and the decode-GEMV league cell (Bonsai tg128 hold).

## 6. Verdict

**Gain** — published Monarch-class prior art kills Super-GOAT at Q1, but the recipe is directly actionable: the modelless half (Kronecker-tile apply) is a small primitive sitting on top of machinery we already ship (Issue 839), and the training half is a concrete recipe for our own small trained models in riir-train.

## 7. Exact quotes for citation (math notation normalized from the KaTeX doubling)

1. "Needle replaces the transformer's feed-forward layer with three Kronecker-factored mixes that start as the Walsh-Hadamard transform and learn from there. 25.6K parameters per layer instead of 4.7M, and a fifth of the compute per token."
2. "Needle 2 used the transform as is, with learned diagonal scalings on either side, on the observation that a fixed rotation plus learned per-channel gains is already a surprisingly capable mixer. Needle 3 keeps the idea and makes the rotation itself learnable, without giving back the cost."
3. "…which is two small matrix products, 2·32³ = 65,536 multiply-adds, against the 1024² ≈ 10⁶ of a dense matrix of the same size, and 2·32² = 2,048 parameters against a million."
4. "The Walsh matrix is itself a Kronecker product of smaller Walsh matrices, so initialising A and B to H₃₂ makes the stage an exact Hadamard transform on the first step of training, and every step after that can move it."
5. "Needle applies three Kronecker mixes with a fixed random shuffle of the channels after the first and the second, so that by the third stage every channel has had a path to every other. This is the Monarch construction…"
6. "…with U zero at initialisation so the gain starts at exactly one. It costs 14K multiply-adds and lets a token scale its own channels before the nonlinearity… bought with a vector rather than a matrix."
7. "Counting everything, a layer holds 3×2×32² factor weights, five vectors of length 1,024 and the two rank-8 matrices: 25.6K parameters, and about 0.21M multiply-adds per token."
8. "Per layer the Hadamard MLP is 180 times smaller than the dense layer it replaces and 22 times cheaper to run." / "Across the 20 blocks of Needle 3 the difference is 94M parameters, which would have taken the model from 121M to 215M, and 196 MFLOPs per token, which would have taken it from 100 to 296."
9. "70.8M of its 121M parameters live in hashed n-gram tables that are read by gather, a few rows per token, costing no arithmetic at all." / "Decode on a Raspberry Pi 5 runs at 400 to 4,000 tokens per second across the depth ladder."
10. "A dense feed-forward layer can represent any linear map on its hidden width; three Kronecker mixes with permutations cannot represent all of them, and the rank-8 gain is a narrow substitute for the input-dependence of a wide hidden layer. … Whether the same trade holds for knowledge-heavy general text at larger scale is the open question."

## References

- Dao, T. et al. 2022. "Monarch: Expressive Structured Matrices for Efficient and Accurate Modeling" (PMLR) — the Monarch class (prior art, Q1).
- Dao, T. et al. 2020. "Learning Fast Optimizers / Butterfly factorizations" — Butterfly grandparent class.
- MoST 2025 (Monarch sparse tuning); Mohamed 2025 (learned permutations in Monarch factorization).
- "Hadamard and Monarch: Compressing GPT-2 Small" (Ethan Liu, 2026-06) — closest external combination.
- QuaRot-class WHT rotation for quant — our Research 65 RotorQuant lane covers the rotation-comparison table.
- Internal: Research 159/65/418/568/511/387/455/452, Plan 452, Issue 839.
