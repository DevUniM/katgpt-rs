# Issue 800 — pufferlib-derived modelless primitive candidates (bf16 SIMD lead, slot-flip buffer, GraphStablePool)

**Status:** OPEN (2026-09-15) — the modelless-track findings from the PufferLib distill (riir-train [Research 454](../../riir-train/.research/454_pufferlib_pooled_env_rollout_architecture.md) @ `6ffa5b10`, MIT; adversarial-panel No-GD brief, coverage reads done). Three arms; one candidate was honestly killed at the panel (the 3-state spin handshake — channels/papaya are house style, no port).

## Arm A (lead) — SIMD bf16⇄f32 batch conversion kernels → `katgpt-core`

The only clearly-absent piece. Today `riir-ai/crates/riir-engine/src/weight_tensor.rs` `dequantize_row` runs a **scalar** per-element BF16 loop on the weight-streaming hot path; no SIMD bf16 lane exists anywhere (`packus`/`srli` hits are only `simd_lut_dequant.rs`, a different class). PufferLib ships the kernel shape (`pufferenv.h:59-80`): the widening direction (`u16 → u32<<16 → f32`) is lossless and trivially vectorizable; the narrowing is their AVX2 8-lane `srli_epi32 + packus_epi32` single-store pack.

- [ ] A1 AVX2 arm (`_mm256_packus_epi32` shape) + NEON arm for M3 (`uzp`/`shrn` u16x8 pack); `into_buf` API writing into caller-owned buffers (the CrowdAttention scratch discipline)
- [ ] A2 Semantics: **RNE default** (the `half` crate's), truncation as the explicit fast opt-in arm — pufferlib's scalar `bits>>16` is biased; we take the shape, not the rounding
- [ ] A3 GOAT: G1 known-answer vectors (NaN/Inf survival, subnormal loss, bit-exactness vs `half` on the RNE arm) · G2 ≥4× the scalar loop at 8-lane · G4 zero-alloc · feature-flag opt-in, promotion to default only on pass
- [ ] A4 Consumers wired after gate: `weight_tensor.rs::dequantize_row` BF16 arm; bf16 KV lane study (bf16 doubles usable exponent range over the f16 KV cache)

## Arm B — lock-free slot-flip `DoubleBuffer` upgrade → `katgpt-kv` (`async_qdq.rs`)

`async_qdq.rs` `DoubleBuffer` ships the slots but the overlap is *simulated* (single-threaded); real cross-thread overlap exists only as ANE channel split-jobs. PufferLib's Cleanba mechanic worth having is the **lock-free slot-ownership flip**: producer touches only `write_slot`, consumer only `ready_slot`, flip = one seq-cst store, warmup-boot fills slot 0.

- [ ] B1 PoC: cross-thread slot-flip vs serial vs **mpsc-channel baseline** (the honest bar — channels are the Rust default and may tie at 20 Hz cadence)
- [ ] B2 Decision gate: promote only if it beats BOTH baselines; if channels tie → record the decline in the arm's closing note (pufferlib needs the spin machine because C pthreads has no channels; we might not)
- [ ] B3 G1: one-slot-staleness is the *spec* (consumer sees exactly epoch-old data; torn read structurally impossible — producer never writes the ready slot)

## Arm C — `GraphStablePool<T>` extraction → `katgpt-core`

The contract ships **three times under three names**: `katgpt-kv` `radix_prefix` ("captured CUDA graphs that bake buffer addresses stay valid"), `katgpt-transformer` `PagedKVCache` ("the pool never moves pages; alloc reuses free-list slots and only ever appends"), riir-gpu persistent activation arenas. Per substrate-first this is a DRY extraction of an existing, independently-rediscovered substrate — a shared vocabulary type (append-only + free-list + never-move + fixed-address borrow), not new machinery.

- [ ] C1 Extract the type to `katgpt-core`; re-point the three sites incrementally (one repo per commit)
- [ ] C2 G1: generalize the existing `bench_762 g1_address_stability` test as the type's contract test; G4 zero-alloc by construction
- [ ] C3 Boundary note: public crate — the type carries no game/chain semantics (passes the katgpt-rs domain test)

## Cross-refs

- riir-train [Research 454](../../riir-train/.research/454_pufferlib_pooled_env_rollout_architecture.md) §3 coverage table (the reads behind these arms)
- riir-train [Plan 408](../../riir-train/.plans/408_pooled_env_rollout_substrate.md) (the training-track plan — Arm A/B consumers there too)
- riir-clippy mining queue 2026-09-15 lane-intel line (the source verdict: corpus NO / training-lane intel HIGH)
