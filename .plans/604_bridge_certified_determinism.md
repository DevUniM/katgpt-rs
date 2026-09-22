# Plan 604 — BridgeCertified determinism contract (Proposal 005, Phase 1+2, katgpt-rs scope)

Status: COMPLETE — G1 PASS (aarch64 ≡ x86_64/Rosetta digest `bae6e6228bcf1b12…`), G3+G4 PASS; stays opt-in (T4.1)
Owner: session katgpt-rs-604
Proposal: `.proposals/005_bridge_certified_determinism.md` (Phase 1 + Phase 2 — the
"Ships now — open primitive, leaf-clean (katgpt-rs)" half only; Phase 3 runtime/slashing
wiring stays deferred to riir-ai/riir-chain by the proposal's own scoping)

## Substrate-first verdict (mandatory gate, 2026-09-21)

CONSUME, DO NOT REBUILD — the certified path needs exactly two primitives and both ship:

- `katgpt_types::simd::dot_f32_ordered` — order-stable sequential fold, docstring names
  "replay determinism" as its use case, `ordered_dot_is_the_sequential_fold` pins the fold.
  The platform `simd_dot_f32` the shipped bridge uses REASSOCIATES (lanes + mul_add) — that
  is the actual cross-arch divergence vector, NOT the sigmoid.
- `katgpt_types::simd::fast_sigmoid` (Cephes polynomial, scalar) — a software op sequence:
  cross-arch bit-identical BY CONSTRUCTION. `exact_sigmoid` (libm) is the per-platform
  reference and is explicitly NOT cross-platform — do not use it here.
- ⇒ **T1.4 (`bridge_soft_sigmoid`) is OBSOLETE-BY-SUBSTRATE**: fast_sigmoid already IS the
  "software-emulated sigmoid with fixed coefficients" the proposal's Caveat 1 asked for.
  No new sigmoid ships. The certified kernel pins fast_sigmoid by name.

Vocabulary-translation greps done: `BridgeCertified` (0 hits pre-work), `dot_f32_ordered`
(1 hit, in katgpt-types), `bridge_soft_sigmoid` (0), `certified_dot` (0). No parallel
substrate exists; no parallel system built.

## Tasks

- [x] T1.1 `BridgeCertified` trait + `BridgeCertifyError` + `MotifDirections` impl in
      `katgpt-core/src/closure/bridge_certified.rs`, feature `bridge_certified = ["closure_instrument"]`.
      Deviations from the proposal sketch (documented, prod-grade):
      `replay` returns `Result<Vec<u8>, BridgeCertifyError>` (the sketch's bare `Vec<u8>`
      cannot distinguish the Piece-3 freeze-skew "valid divergence" from a decode failure);
      snapshot + output bytes are EXPLICIT little-endian (`to_le_bytes`, not bytemuck —
      cast_slice is native-endian and not cross-arch canonical).
- [x] T1.2 Certified kernels: `certified_ptg_to_motif_embedding` (cold, allocates) +
      `certified_ptg_to_motif_embedding_into` (hot, zero-alloc: caller feature + out scratch).
      Certified kernel = `dot_f32_ordered` + `fast_sigmoid`; the SHIPPED `ptg_to_motif_embedding`
      (platform simd dot) is untouched — default build byte-identical.
- [x] T1.3 G1 harness `examples/bridge_determinism_check.rs`: deterministic xorshift corpus
      (g1_corpus v1, ≥10⁴ PTGs), BLAKE3 digest over output bytes, `--expect <hex>` verify
      mode, prints arch + box state. Corpus generator lives IN the library
      (`bridge_certified::g1_corpus`) so example + tests share one definition (the
      fixture-copying-is-drift lesson).
- [x] T1.4 G1 measurement: aarch64-apple-darwin native + x86_64-apple-darwin (Rosetta)
      digests — **IDENTICAL** `bae6e6228bcf1b12cd8b374eee8c6320a58fd788ae1af8e4539f5bd831d4be68`
      (also profile-independent on aarch64: debug ≡ release). platform_gap ~92.6% on both
      arches — the reassociation gap is the common case, certification is load-bearing.
- [x] T1.5 Audit tests `tests/bridge_certified_invariants.rs` (hash content-addressing,
      replay round-trip bit-identity, FreezeSkew both-hash error, BadInputs, non-finite
      direction rejection, certified≠simd load-bearing pin, `_into`≡allocating bit-identity,
      aarch64 digest pin with cross-arch protocol message).
- [x] T1.6 G4 `tests/bridge_certified_alloc_check.rs` — separate single-fn binary (repo
      convention: a counting allocator would pick up parallel sibling tests), zero-alloc
      steady state for `certified_ptg_to_motif_embedding_into`, live-counter canary.
- [x] T1.7 Perf microbench record (ordered vs simd dot at the certified shapes) in
      `.benchmarks/604_bridge_certified_g1.md` with box state (the AGENTS.md latency rule).
- [x] T1.8 cargo clippy/heal on touched files; test at `--features bridge_certified` AND
      default (gated-off compiles to nothing); proposal 005 status update + commit/push.

## GOAT gate (this plan's scope)

| Gate | Target | Status |
|---|---|---|
| G1 | certified corpus digest bit-identical aarch64 ↔ x86_64 (Rosetta), ≥10⁴ inputs | T1.4 |
| G2 | n/a in this repo — drift-sampler overhead bench is riir-wasm's (Phase 3, deferred) | — |
| G3 | default build byte-identical (opt-in feature; untouched shipped bridge) | T1.8 |
| G4 | `certified_..._into` zero-alloc steady state | T1.6 |

Promotion: stays OPT-IN. Phase 4 promotion requires G2+G3(G3 here)+G4 AND the Phase-3
wiring; record the decision, do not promote.

- [x] T4.1 record promotion decision in `.benchmarks/604_bridge_certified_g1.md`
      (decision: stays OPT-IN — Phase-3 wiring absent, no sync-boundary consumer in this repo)
