# Bench 604 — BridgeCertified G1 cross-arch determinism gate (Proposal 005 Phase 1+2)

Status: COMPLETE — G1 PASS; feature `bridge_certified` stays OPT-IN (see Promotion)

## What this gate proves

The certified motif bridge (`certified_ptg_to_motif_embedding*`, Plan 604) produces
bit-identical output across x86_64 and aarch64 over the G1 corpus (v1): 10 000
deterministically generated PTGs (seed `G1_SEED = 0x0604_B21D_6E55`), K=32 × N=64
directions table, BLAKE3 digest over the 1 280 000 output bytes.

| Run | arch | profile | digest (first 16) | full |
|---|---|---|---|---|
| 1 | aarch64-apple-darwin (native) | release | `bae6e6228bcf1b12` | `bae6e6228bcf1b12cd8b374eee8c6320a58fd788ae1af8e4539f5bd831d4be68` |
| 2 | x86_64-apple-darwin (Rosetta 2) | release | `bae6e6228bcf1b12` | **identical** |
| 3 | aarch64-apple-darwin (native) | debug (test harness) | same | **identical to release** |

**G1 PASS.** The digest is arch-independent AND profile-independent on aarch64 —
consistent with the design claim (fixed IEEE op sequence: `dot_f32_ordered`
sequential fold + Cephes `fast_sigmoid`; no libm, no reassociation, no denormals
in the reachable range since fast_sigmoid clamps at |x| > 40).

Pin: `G1_PINNED_DIGEST` in `tests/bridge_certified_invariants.rs` asserts the
digest; the harness (`examples/bridge_determinism_check.rs --expect <hex>`) is
the cross-arch re-verification tool.

## Why the certified kernel is a separate path (the load-bearing measurement)

`platform_gap` = fraction of corpus inputs where the certified (ordered) path
disagrees with the shipped platform-SIMD path on the SAME arch:

- aarch64 native: **9263 / 10000**
- x86_64 (Rosetta): **9266 / 10000**

The reassociation gap is not an edge case — ~93% of realistic inputs produce a
different last ULP between the two kernels. Mixing the platform path at a sync
boundary with a pillar replaying the ordered path (or the same path on another
arch) would diverge on virtually every scalar. Certification must be per-call-site
and exclusive.

## Microbench (record-only; the GOAT G2 latency gate is riir-wasm's, Phase 3)

K=32, N=64, corpus PTGs (1–64 nodes, mean ~32), ns per PTG:

| Box state | certified (`*_into`, zero-alloc) | platform (`ptg_to_motif_embedding`) | ratio |
|---|---|---|---|
| M3 Max, aarch64 native, release, 16 cores, load ~4 (sibling agent sessions active), AC power | **877 ns** | **314 ns** | 2.8× slower |
| Same box, x86_64 via Rosetta 2, release | **1216 ns** | **8552 ns** | **0.14× (7× FASTER)** |

Read with the AGENTS.md box-state rule: single-run Instant timings, loaded box,
not a criterion distribution — magnitudes, not gates. Two honest observations:

1. On native aarch64 the certified path pays ~563 ns/PTG for the sequential
   fold + loss of SIMD. Both paths are sub-µs; the bridge is a cold/warm
   diagnostic path (closure module docs), and the certified path is opt-in.
2. Under Rosetta the ordering INVERTS: the certified path is ~7× faster,
   because `certified_*_into` performs zero allocations per call while the
   platform path allocates twice (feature vec + output vec) and allocation is
   disproportionately expensive under Rosetta. The zero-alloc design is not
   just G4 hygiene — it is a real win on the x86_64 emulation path.

## GOAT gate (Plan 604 scope)

| Gate | Result |
|---|---|
| G1 correctness (cross-arch digest) | **PASS** (rows 1–2 above) |
| G2 perf (drift sampler ≤0.5% CPU @10K NPC×20Hz) | n/a here — riir-wasm Phase 3, deferred by proposal |
| G3 no-regression (default build) | PASS — feature off compiles the module to nothing; `cargo check -p katgpt-core` + 58 existing closure lib tests green |
| G4 alloc-free | **PASS** — `bridge_certified_alloc_check`: 0 bytes across 1000 steady-state calls (with live-counter canary) |

## Promotion decision (Plan 604 T4.1)

**Stays OPT-IN.** The proposal's Phase-4 promotion condition requires G2 + the
Phase-3 runtime wiring (BridgeDriftSampler in riir-ai, BridgeDriftEvidence +
architecture_root freeze pin in riir-chain) — none of which exists yet. There is
additionally no consumer in this repo that would benefit from default-on (the
shipped platform path is correct for its cold/warm diagnostic use). Revisit when
a sync-boundary consumer adopts the certified path.

## Reproduction

```sh
# G1 both arches (digests must match):
cargo run --release -p katgpt-core --features bridge_certified --example bridge_determinism_check
cargo run --release -p katgpt-core --features bridge_certified --target x86_64-apple-darwin --example bridge_determinism_check

# Audit + alloc gates:
cargo test -p katgpt-core --features bridge_certified --test bridge_certified_invariants
cargo test -p katgpt-core --features bridge_certified --test bridge_certified_alloc_check

# Microbench arm:
cargo run --release -p katgpt-core --features bridge_certified --example bridge_determinism_check -- --bench
```
