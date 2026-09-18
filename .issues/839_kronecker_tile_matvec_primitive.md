# Issue 839: Kronecker-tile matvec primitive (`kron_apply`) — Hadamard-MLP fusion (Research 569)

**Status:** OPEN — GOAT-plan; modelless half of the Hadamard-MLP distill (Research 569). Training half (WHT-init structured FFN for our own drafters) routes to riir-train, not this issue.

## Motivation

Cactus Needle 3 (blog 2026-09-17) replaces the dense FFN with three Kronecker stages `Mₛ = Aₛ ⊗ Bₛ` (A,B ∈ ℝ³²ˣ³², 1024 channels as a 32×32 tile) applied as `vec(Aᵀ Z B)` — 65,536 MACs and 2,048 params per stage vs ~1M and ~1M dense (180× smaller, 22× cheaper per layer at the full 3-stage construction, 25.6K vs 4.7M params). The tile row/col apply machinery **already ships** in `katgpt-kv/src/kvarn/hadamard.rs` (`hadamard_rows`/`hadamard_cols`) — but only at A=B=H₃₂ (fixed WHT). The new primitive is the **arbitrary-factor** version: general 32×32 (or 64×64) A,B, batched over tiles — the structured-sparse-matvec slot.

Prior art (kills Super-GOAT, not GOAT): Monarch (Dao et al. 2022), Butterfly (2020), MoST (2025).

## Tasks

- [ ] T1 `kron_apply(A, B, tiles, scratch)` in katgpt-core (linalg): per-tile `Z ← Aᵀ Z B` as two small GEMMs, const-generic or runtime 32/64, zero-alloc (caller scratch), `#[inline]`, SIMD-chunked inner loops (optimization-guidelines: chunked, branch-free).
- [ ] T2 WHT fast path: when A=B=H₃₂, delegate to the existing butterfly (`walsh_hadamard_in_place_normalized`-class) and pin bit-parity with the generic path in a test.
- [ ] T3 G1 correctness: `(A⊗B)·x` tile apply == dense reference on random A,B,x (1e-5 f32), + exact Hadamard round-trip anchor.
- [ ] T4 G2 perf bench: batched 3-stage Monarch apply vs (a) dense n=1024 matvec, (b) ternary dense matvec at matched params — expect ~16× FLOP ratio floor vs (a); record in `.benchmarks/`.
- [ ] T5 G3 no-regression: feature-gated (`kron_tile`), default-off; existing KVarN/meld WHT paths byte-identical.
- [ ] T6 G4 zero-alloc witness (fixed-size scratch, no heap on the hot path).
- [ ] T7 Ternary-factor fusion spike (deferred behind T4 PASS): A,B quantized to {−1,0,+1} — stage becomes add/sub accumulate via the ternary SIMD matvec kernels; 6,144 weights ≈ 1.5 KB/layer. GOAT gate for the fused form runs in riir-train on a trained small LM (quality axis is not modelless-decidable).
- [ ] T8 Document the Needle-3 recipe pointer (WHT init → learnable factors, fixed permutations, rank-8 gain as sigmoid-gated variant) in the module doc; cross-link Research 569.

## Non-goals

- No FFN retrofit of served upstream checkpoints (weights are fixed upstream — Research 452 Q3 logic).
- No training loop in katgpt-rs (riir-train owns the recipe).
