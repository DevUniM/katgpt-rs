# Bench 846 — Issue 864 BITCOS GOAT gates (codec + z-meter + kernels + roofline)

**Status:** COMPLETE — G1/G2/G4 PASS, T4 roofline + negative controls PASS, G2b(a) latency FAILS the promotion clause → **stays opt-in** (the designed honest outcome for an instruction-bound host)
**Date:** 2026-09-21
**Box:** 4090 host (i7-13700K, 8P+8E, DDR5) — Windows 11, AC power, ~19% GPU idle ambient, no compute competitors (league-verified window)
**Feature:** `bitcos` (implies `ternary_group_scale`), gated with `ternary_trit_pack` for the both-tier comparison
**Source:** [Research 577](../.research/577_BITCOS_Distribution_Adaptive_Ternary_Layout.md) / arXiv:2609.16338 (Georganas et al., "Breaking the 1.58-bit Barrier for Ternary LLMs")

## What shipped

- `katgpt-types/src/bitcos.rs` — `BitcosWeights` (presence bitmap + compacted neg-sign stream + per-row offsets + f16 group scales), `pack_from_planes/group/f32`, `to_group`, `unpack_row_into`, `get`, `is_canonical`, checksum; the **z-meter** (`zero_density_report` over any `TernaryGroupWeights` blob, per-row min/max spread); paper-rate helpers (`bitcos_bits_per_weight`, `bitcos_payload_bytes_per_weight`); the roofline dispatch `should_use_bitcos(z, γ, β) = B(z)/γ > β ∧ z > 0.375`.
- `katgpt-types/src/simd/bitcos.rs` — three GEMV consumers: scalar reference (bit-identical to `ternary_group_matvec_scalar`), **256-entry LUT** variant (presence-nibble × sign-window key — the paper's Xe2 pdep-free table, the CUDA/WGSL-portable mechanism; bit-identical to scalar), and the **pdep+SWAR AVX2 arm** (one `_pdep_u64` + `andnot` reconstructs the planes per word, then the shipped `fma_scaled_nibble8_avx2` SWAR dot; runtime-probed AVX2+FMA ∧ BMI2 per the `shipped_target_feature` law).
- `tests/bench_864_bitcos_goat.rs` — the gates below (`required-features = ["bitcos", "ternary_trit_pack"]`).
- 12 lib tests + 4 kernel tests in-module; 4 GOAT tests.

**Polarity note (pinned in-code):** Research 577 §2.2 words the stream as "compacted `pos` bits" against its own `0=+1 / 1=−1` convention — the self-consistent form is **neg-compaction** (sign 1 = −1), which is what ships. Two bugs were caught by the gates themselves before any timing ran: the pack side must `pext` (compact to low bits), not `pdep` (scatter to positions) — the strayed high bits tripped `is_canonical`; and the scalar kernel's `pos` is the reconstructed plane `p & !neg`, not presence (a negative weight has both bits set).

## G1 — correctness: PASS

- Pack→`to_group` roundtrip bit-exact in pos/neg planes AND f16 scales: exhaustive 3⁴=81 single-nibble rows + seeded multi-word/multi-row shapes (incl. ragged 3×200, 7×129) + the all-zero tensor (empty sign stream, sentinel only).
- `bitcos_matvec_scalar` **bit-identical** to the shipped `ternary_group_matvec_scalar` at (256×4096) — same per-group column-order accumulation including `0.0·x` zero terms.
- `bitcos_matvec_lut` **bit-identical** to scalar.
- pdep/AVX2 arm: max_rel 2.5e-3 at 16384 cols vs scalar — the folded-scale association class the shipped AVX2 kernel itself carries (~1e-6 at small shapes, growing with group count); asserted < 5e-3 at the streaming shape.

## G2 — footprint vs BOTH shipped tiers: PASS (deterministic)

512×4096 fixtures at controlled z (`k/m` zero-draw), `encoded_bytes()` vs both tiers' own `encoded_bytes()`:

| z | bitcos | trit (1.75) | bit-plane (2.125) | bitcos/trit | bitcos/plane |
|---|---|---|---|---|---|
| 0.500 | 430,040 B | 452,608 B | 557,056 B | **0.950** | **0.772** |
| 0.600 | 403,832 B | 452,608 B | 557,056 B | **0.892** | **0.725** |
| 0.666 | 386,488 B | 452,608 B | 557,056 B | **0.854** | **0.694** |

Below the crossover (dense fixture, z < 0.375): bitcos is **larger than trit — asserted** (the honest Bonsai-27B regression; the dispatch's `z > 0.375` arm exists because of it). The paper-rate arithmetic (`2−z+0.125` vs 1.75/2.125 incl. scales) is unit-pinned at the exact crossover: 1.75 == 1.75.

## G2b(a) — the >L3 streaming regime: **FAIL → stays opt-in**

16384×16384 (payloads 54.7/57.9/71.3 MB vs 30 MB L3), single-thread, release, median of 5, plane re-run drift 0.0% (the assert's own bound):

| kernel | ms | ratio vs bitcos |
|---|---|---|
| bit-plane AVX2 SWAR (shipped) | 36.35 | **0.767×** (bitcos loses 23%) |
| trit AVX2 (shipped) | 39.69 | **0.846×** (bitcos loses 15%) |
| bitcos pdep+SWAR | 47.03 | — |

**Verdict: the ≥1.05×-vs-BOTH promotion gate FAILS on this host.** The mechanism is the paper's own Lunar Lake class, measured on ours: γ (bitcos L1-resident decode rate) = **1.23 B/ns** < β (the shipped kernel's achieved streaming rate) = **1.95 B/ns** — the kernel is instruction-bound, so the 25% payload cut has nothing to pay the pdep+window decode with. This extends Bench 586's finding (trit 15–31% slower than bit-plane SWAR on x86_64) to the bitcos layout: on wide-ALU desktop silicon the SWAR-from-planes dot is already the better trade; the paper's win band (EMR 64-core bandwidth-starved servers, 1.14–1.28×) is a different β/γ knee.

## G2b(b) + T4 — L1-resident negative control + roofline: PASS

- L1-resident (128×1024, ~29 KB payload): bitcos 0.832× of the bit-plane kernel (final post-heal run; 0.770 in the first) — the expected cache-resident loss (Issue 582 G2b / `binary_plasma` precedent), inside the 2× reject bound.
- The roofline dispatch **measured on this shape refuses** (`should_use_bitcos` with the measured γ/β → false) — the load-bearing assert that the predicate is not decoration.
- Synthetic negative controls: instruction-bound at CAT-Q z (γ halved) → refuses; z = 0.297 bandwidth-bound → refuses (trit smaller); z = 0.375 exactly → refuses (strict >).
- **Dispatch/gate agreement**: the streaming shape's measured dispatch verdict equals the G2b(a) gate outcome (both false here) — the predicate demonstrably tracks the knee it was derived from.

## G4 — alloc-free: PASS

0 allocations per call for scalar/LUT/dispatcher kernels under the thread-local CountingAllocator (stack scratch only; the container's pack-time allocations are offline).

## What this tier is FOR (the honest close)

1. **Footprint** at z > 0.375 checkpoints (CAT-Q/BitNet/Maple class): 0.85–0.95× the best shipped tier, bit-exact, training-free — the storage lane.
2. **The z-meter + four-tier roofline dispatch** — the durable general primitive: every future checkpoint gets measured z and a measured γ/β verdict before anyone wires a container. This host's verdict is honestly NO for latency; a many-core bandwidth-starved host (or a CUDA arm where β is the SM-side share) re-measures with the same instrument.
3. **The LUT kernel** is the GPU-portable consume mechanism (no scatter instruction) — the riir-gpu `gemv_ternary_cuda_raw` BITCOS arm pointer stays recorded, now with a reference implementation in-tree.

**Promotion: DENIED by measurement (stays opt-in)** — the issue's own clause. Re-open triggers: a host whose measured β exceeds the bitcos decode rate (server-class silicon), a served checkpoint with measured z ≥ 0.43, or a CUDA/WGSL LUT arm whose decode rate clears its SM-side bandwidth share.
