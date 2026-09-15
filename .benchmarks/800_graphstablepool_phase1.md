# Bench 800-C — GraphStablePool<T> extraction, phase 1 (Issue 800 Arm C)

**Status:** RECORD — phase 1 LANDED (`877e06eb2`): the common contract VERIFIED to
exist across **4** sites (the issue's 3 + a 4th found in-repo), type extracted
opt-in (`graph_stable_pool`), 6 contract tests green (2066/0 with feature,
2092/0 four-feature combo, default 2060/0, wasm32 clean, clippy clean).
Re-points are incremental follow-ups (one repo per commit) — none executed in
phase 1 by design.

Provenance: Issue 800 Arm C — the never-move pool contract ships three times
under three names (an independently-rediscovered substrate; DRY extraction per
substrate-first, not new machinery).

## The four-site contract comparison (the phase-1 finding)

| Site | Slot store | Free list | Stability actually guaranteed |
|---|---|---|---|
| `RadixPrefixTree` (katgpt-kv `radix_prefix/mod.rs`) | `Vec<RadixNode>` by value | `free_nodes` LIFO | **INDEX** only (node ids are the stable handles) |
| `PagedKVCache` (katgpt-transformer `kv_cache.rs`) | `Vec<Vec<f32>>` heap handles | `free_pages` LIFO | **INDEX + payload-address** (via T-indirection — pages never move, the 24-byte handles do) |
| `Qwen38LaneSet` (riir-gpu `qwen38_dense_cudarc.rs`) | one flat `CudaSlice<f32>` per layer, fixed slots | none | **TRUE ADDRESS** — captured graphs bake device pointers; achieved by allocate-once pre-allocation + lifetime scoping, NOT chunking |
| `BranchBank<E>` (katgpt-core `branching/bank.rs` — in-repo 4th instance) | `Vec<CognitiveBranch>` by value | `free_slots` LIFO | **INDEX** (`BranchId`) |

**The load-bearing verdict (documented loudly in the module doc):** the common
contract is INDEX stability — alloc pops the LIFO free list else appends; live
indices never invalidated; backing store grows by append only. Payload-address
stability is a property of the STORED TYPE (heap indirection, site 2's recipe)
or of pre-allocation discipline (site 3), not of the pool itself. `&T` borrows
do not survive `alloc` — hold the index. Chunked/pinned storage was rejected:
site 3's guarantee doesn't come from chunking, and the two index-stable sites
don't need it.

## The type

`GraphStablePool<T>` (`Vec<Option<T>>` storage — zero-cost for the niche-bearing
shapes all four sites store): `new`/`with_capacity`/`alloc(T)->usize`/`free(usize)->
Option<T>`/`get`/`get_mut`/`len`(live)/`is_empty`/`capacity`(total slots ever).
`free` returns the value (site-2 buffer-recycling delta + the status signal);
double-free = silent no-op (majority discipline, documented).

## Site-deltas table (the re-point adapters, for the follow-up commits)

- **radix_prefix**: eviction clears payloads instead of taking values → salvage
  payload Vecs from `free`'s return.
- **PagedKVCache**: refcount layer gates the free; `alloc_page` refills in place →
  caller re-`alloc`s the returned buffer (zero realloc churn preserved).
- **Qwen38LaneSet**: no free list, fixed n, replacement invalidates baked pointers →
  `with_capacity` pre-allocate, never churn; scope graph caches to the pool lifetime.
- **BranchBank**: caller-side cap check before `alloc`; anchor side-cache stays
  bank-local keyed by returned index.

## Boundary note (C3)

Generic slot allocator, no game/chain/shard vocabulary, zero riir deps — passes
the katgpt-rs domain test for the public crate. Re-point follow-ups: katgpt-kv →
katgpt-transformer (in-repo), then riir-gpu (riir-ai commit), + optional BranchBank.

## Phase 2 — re-point verdicts (2026-09-16, `bdb1091a4` + riir-ai `35108b6a7`)

| Site | Verdict | Evidence |
|---|---|---|
| 1 radix_prefix | **RE-POINTED** | bench_762 GOAT release PASS post-re-point: G1 bit-identity + isolation + address/pool stability, G2 hit-rate 0.184 vs flat 0.075 + match 0.22 ms vs 2.17 ms flat (pool's one-Option-layer walk invisible at 10× margin), G4 0 allocs; radix tests 14/14; pool lib 7/7 incl. new `iter()` contract test; clippy clean; default + wasm32 clean. LIFO parity verified for evict-push AND `clear()`'s `(1..len)` build |
| 2 PagedKVCache | **DECLINED** | refill-at-stable-index (the DDTree fork/rollback zero-realloc contract, riir-engine forward_paged G4-gated) forces recycled buffers out-of-pool between free/reuse → 1 bookkeeping structure becomes 2; pub fields are bench_414's legacy-replica instrument; None-on-freed safety is dead defense (rollback truncates tables before freeing) |
| 3 Qwen38LaneSet | **N.A.** | no free list / no churn — the set IS the lifetime-scoped flat-arena pattern (allocate-once, graphs inside the set, whole-set replacement drops baked pointers); a wrapper adds alloc/free nothing calls |
| 4 BranchBank | **DECLINED** | wire pins slots-by-value + in-band Removed slots + explicit ordered `free_slots` stack; from_bytes byte-identity unreproducible without exposing pool internals; wire feeds neuron-db freeze (versioned migration, not refactor) |

Phase 1's site-deltas table above was the pre-adoption prediction; row 1 is the
only one whose adaptation fired as written. Rows 2-4 are the measured refutation
class: contract-SHAPED matches are not re-point obligations when a bigger
load-bearing shape (refcount policy, wire pin, graph-pointer scoping) owns the
site.
