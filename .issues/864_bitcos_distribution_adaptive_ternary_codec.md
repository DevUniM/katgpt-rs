# Issue 864: BITCOS distribution-adaptive ternary codec (presence bitmap + compacted signs)

**Status:** OPEN — filed from Research 577 (arXiv:2609.16338); no code yet
**Date:** 2026-09-21
**Research:** [katgpt-rs/.research/577_BITCOS_Distribution_Adaptive_Ternary_Layout.md](../.research/577_BITCOS_Distribution_Adaptive_Ternary_Layout.md)
**Target:** `katgpt-types/src/bitcos.rs` (new module, beside `ternary_group.rs`/`ternary_trit.rs`) + Cargo feature `bitcos` (opt-in, implies `ternary_group_scale` — the Issue 582 `ternary_trit_pack` pattern)
**Priority context:** 4090 box; NOT a Bonsai-27B lever (0.96× vs the shipped trit tier at z=0.2966) — the win band is z ≳ 0.43 checkpoints + the z-meter/roofline dispatch primitive itself. League tg128 (GPU-busy-bound) and prefill (compute-bound) are out of scope by design.

---

## Problem

The ternary container ladder in katgpt-types is entirely fixed-rate: bit-planes (`TernaryGroupWeights`, Issue 578, 2.125 bits/w incl. scale) and 5-trits/byte (`TernaryTritWeights`, Issue 582, 1.75 bits/w incl. scale). Nothing measures zero density z; nothing adapts rate to it. arXiv:2609.16338 measures z = 0.297–0.515 across 29 real ternary checkpoints and shows a presence-bitmap + compacted-sign layout (2−z bits, bit-exact, training-free) cuts weight traffic 1.16–1.32× vs the bit-plane class — but ONLY in the bandwidth-bound regime (their Lunar Lake row: 0.47–0.70× when instruction-bound; our in-repo twin is Issue 582's G2b: cache-resident ⇒ storage PASS + latency FAIL, the `binary_plasma` precedent) and ONLY vs the bit-plane tier (vs the 1.75 trit tier it wins just z > 0.375 — a 0.96× regression at Bonsai-27B z=0.2966, ≈1.00× at 4B/8B, meaningful ≥1.05× only at z ≳ 0.43).

## Ship (all behind `bitcos` feature flag, opt-in)

- [ ] T1 Codec: `pack_from_group(&TernaryGroupWeights)` (the Issue 582 `from_group` repack precedent — bitmap = pos|neg; signs = compacted pos bits at set positions), `pack_from_planes(pos,neg)`, `pack_from_f32` (Research 110 error-compensated row quant, then pack), `unpack_row`, `to_group`, sizes/`bits_per_weight(z)`; **bit-exact roundtrip test** over exhaustive small cases + seeded random planes.
- [ ] T2 z-meter: popcount-based zero-density report for a `TernaryGroupWeights`-shaped blob; record OUR checkpoints' z (also corrects the inherited "1.58 bits/weight" doc figure — origin fixed in ternary.rs this commit, riir-ai Research 007 propagation rides this task's numbers).
- [ ] T3 GEMV consumers: portable scalar + **256-entry LUT variant** (presence-nibble × sign-window key — pdep-free, the GPU-portable mechanism per the Xe2 sequence and our `dequant_dot_via_lut`/StreamDQ lineage); optional AVX2-class arm ONLY via runtime `simd_level()` probe (the `shipped_target_feature_gate` law — never a compile-time `target_feature` cfg on a shipped path; pdep via `core::arch` under cfg).
- [ ] T4 Roofline harness + dispatch: measure γ (L1-resident loop), read β, bench a z-sweep 0.25–0.55; `should_use_bitcos(z, γ, β) = B(z)/γ > β` AND `z > 0.375` (the trit-tier crossover — dispatch must never select bitcos where the shipped trit tier is smaller); **negative controls**: (a) LNL-shaped — small working set must select a non-bitcos path; (b) G2b-shaped per Issue 582 — cache-resident latency loss expected and asserted.
- [ ] T5 GOAT gate, BOTH baselines: head-to-head vs the shipped **bit-plane** GEMV (2.125) AND the shipped **trit** GEMV (`ternary_trit_pack`, 1.75 — footprint gate modeled on Issue 582's G2 arithmetic) at z ∈ {0.30, 0.40, 0.51} on (a) a >L3 working set (bandwidth-bound: expect ≥1.05× vs BOTH tiers at z=0.51) and (b) an L1-resident set (expect ≤1.0× — must lose, proving the dispatch is load-bearing). **A pass vs bit-plane while losing to trit is a FAIL vs the best shipped tier** — both tables recorded in `.benchmarks/`. Promotion to default ONLY if (a) clears vs both with dispatch safe; otherwise stays opt-in.

## Non-goals

- No drafter wiring (riir-clippy L1 is cache-resident → instruction-bound → the losing regime, Research 577 §2.4).
- No league tg128/pp claims (compute-bound lanes).
- No riir-ai CUDA arm in this issue — pointer only, filed there after this gate is green.
