# Issue 764 — `LoraPair` KV-cache weight-epoch contract unspecified (the public-side twin of riir-ai Issue 938)

**Status:** OPEN → **LANDSCAPE CHANGED 2026-09-13 (same day, minutes after filing)** — items 1+2 below were LANDED by `49f5d245` (WeightEpoch + `LoraAdapter::weight_epoch()` + the LoraPair by-design acceptance docs + the core_04 example fix) while this issue was being filed; item 1's remaining half — the GENERAL constructor `WeightEpoch::from_parts(tag, parts)` for non-adapter weight walks (the frozen-model axis riir-ai's Gemma2/KVCA v2 lane consumes) — added same day on top. What stays open: nothing actionable here — the riir-ai-side consumption is tracked in riir-ai Issue 938. Resolve on the next issue sweep.
**Origin:** riir-ai Issue 938 (filed 2026-09-13 from riir-train `.research/453` — Yifan Zhang's "Recurrent Looped Transformer" §5.4/App-C cache-staleness law). The private-side contract LANDED same day (riir-ai: `weight_epoch` module + KVCA v2 + `Gemma2PatchedForward::weight_epoch`).
**Date:** 2026-09-13

## The gap

`LoraPair { reader, writer }` (Plan 025, `katgpt-types/src/lora.rs:498`) swaps the
effective weight set between prefill and decode — and `examples/core_04_prefill.rs`
(Proof 3/4) demonstrates sharing ONE `MultiLayerKVCache` across that switch as a
feature ("Reader→Writer LoRA switch works end-to-end" + "Shared KV Cache —
prefill + decode seamless").

Per the staleness law: a cache entry is exact only when computed under the SAME
weight epoch. KV rows written under the reader adapter and read under the writer
adapter are a mixed-epoch computation — well-defined as a path, but NOT equal to
the computation under either single policy, and invalid for any exactness claim
built on top. As an emergent-behavior demo this may be acceptable — but the
acceptance must be DOCUMENTED at the swap site, and exactness-claiming consumers
need a way to refuse stale reads.

## What to build (mirrors the riir-ai contract)

1. A public `WeightEpoch` primitive (u64 identity; BLAKE3-of-effective-weights
   constructor + a monotone-version constructor for the swap axis) — the
   modelless, zero-hot-path-cost shape riir-ai landed (`riir-engine/src/weight_epoch.rs`
   is the reference implementation; a public port belongs here per the
   upstream-first rule, then riir-ai can consume it).
2. Document the mixed-epoch contract at the `LoraPair` swap site (module docs)
   and in `core_04_prefill.rs` — the example should SAY the shared cache is a
   mixed-epoch read accepted for demo purposes, not a correctness pattern.
3. Optional property gate: epoch-tagged cache + swap → refusal arm.

## Validation

- Same bars as riir-ai Issue 938: match-epoch bit-identity + a planted stale
  read refused; no hot-path cost (u64 compare).
- Full repo gates apply (public crate — `full_gate.sh` / docs gate on main).

## Related

- riir-ai Issue 938 (the private-side twin; landed 2026-09-13).
- riir-train `.research/453` (the distillation) + riir-train Issue 543 (training side).
- Plan 025 (`LoraPair { reader, writer }` — the deterministic overlay design).
