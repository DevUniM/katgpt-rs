# Issue 771 — Radix-tree prefix KV cache (the RadixAttention primitive)

**Status:** OPEN

## Problem

SGLang's RadixAttention stores cached token sequences in a **radix tree**
whose nodes own KV blocks: the shared system-prompt trunk is stored **once**,
branching contexts (auth code vs db code, multi-turn forks, agent
trajectories) extend it as child nodes, and a new request walks the tree to
find the **longest prefix whose KV already exists** — only the divergent
suffix is prefilled. Leaf-LRU evicts under memory pressure, with ref-counted
shared trunk pages never freed while a branch lives.

We do not have this primitive. What ships today:

| Piece | Where | Shape | Gap |
|---|---|---|---|
| PagedAttention half | `katgpt-transformer::PagedKVCache` | Paged KV + free list + **ref-counted pages**, `fork()` (share) + `rollback()` (CoW page-table) | Refcounts serve spec-decode tree verify; no prefix index, no cross-request reuse, no LRU |
| Prefix cache (single-stream) | riir-ai `riir-gpu::qwen38_prefix_cache` (private consumer) | Flat ≤4-entry whole-prefix checkpoints, longest-prefix match (blake3 key + exact token verify), LRU, KV-lineage rule | Explicitly documented divergence: *"theirs is SGLang's radix tree deduplicating shared prefixes across branches; ours is exact-match longest-prefix — equivalent for single-stream reuse"* (Bench 750) |
| Segment matcher | `katgpt-kv::cache_prune::{RollingHash, KvSegmentPool}` | Rolling-hash + blake3 two-phase verified windowed-segment matching | A query structure, not a serving-integrated prefix cache; unwired |

The gap is the **composition**: a mutable prefix tree over token chunks whose
nodes hold ref-counted page ranges of a `PagedKVCache`, with leaf-LRU
eviction — i.e. RadixAttention, as a public modelless primitive.

## Why now (and why not blocking)

Every inference lane in the stack is **single-stream** (perf-rematch league
vs llama.cpp); the branching workload that makes a tree beat a flat cache —
concurrent requests sharing trunks — has no host yet (0 grep hits for
continuous batching / request scheduler). Recorded N/A in riir-ai
`.research/034` ("Radix tree prefix cache → multi-request prefix sharing.
Single-stream."). **The divergence was correct for the current lanes.**

This issue tracks the *primitive*, which is crate-local, modelless, and
benchable **without** a serving engine: a synthetic branching request trace
(agent trajectory / multi-turn conversation shape) drives hit-rate × TTFT
against the flat prefix-cache control. The consumer integration lands in
riir-ai whenever a serving lane materializes — that is the reopen/trigger
condition for escalation, not a blocker for the substrate.

## Design shape

- Tree keyed by tokens at **page granularity** (node boundaries at
  `PAGE_SIZE` token chunks — reuses `PagedKVCache` pages as the unit of
  sharing; ref-count = share count across branches).
- Match: walk by tokens (hash-accelerated compare per node span), longest
  prefix wins; on divergence, CoW from the branch point (the existing
  `fork`/refcount discipline).
- Insert: on request completion (or semantic anchor), extend the walked path.
- Eviction: leaf-preferential LRU; a node frees its pages only when its
  refcount hits zero (interior trunks with live branches never free).
- **Address-stability constraint (load-bearing):** shared pages must never
  be moved/repaged under reuse — captured CUDA graphs bake live buffer
  addresses (the vLLM capture×prefix-cache corruption class, cited in the
  qwen38 T4 design note; that design avoided allocator changes for exactly
  this reason). The tree owns *indices*, not buffers.
- Consume the `KvSegmentPool` match pattern (hash fast-filter + exact
  compare as authority) for per-node span verification.

### Prior-art caution

katgpt-rs Research 137 / riir-neuron-db Bench 485 measured the ART class
(`blart`/`congee`) **NEGATIVE for the LocalKvStore index domain** — a
different problem (byte-string key store). Do not reuse those crates by
analogy; token-chunk nodes with small fanout (HashMap or smallvec children)
are sufficient and stay in-tree.

## GOAT gate (per feature-flag discipline)

Ship behind `radix_prefix_cache` (opt-in) in `katgpt-kv`:

- **G1 correctness:** bit-identical outputs vs no-cache on branching traces
  (shared-trunk reuse must not leak state across branches).
- **G2 perf:** match latency O(tree-depth) vs flat O(entries × len) rehash;
  TTFT reuse ≥ flat cache on a branching trace (flat cache misses cross-
  branch partial trunks at its entry bound).
- **G3 no-regression:** single-stream path untouched (flag off = zero code).
- **G4 alloc:** match path zero-alloc; insert/evict bounded (no per-token
  allocation in the walk).

## Tasks

- [ ] T1 — `RadixPrefixTree` skeleton in `katgpt-kv` (nodes = token-chunk
      spans + ref-counted page ranges; insert/match/evict; property tests:
      match(prefix(A)) == A, branch CoW isolation, LRU eviction respects
      live-branch refcounts)
- [ ] T2 — `PagedKVCache` integration seam (share/adopt pages by refcount;
      address-stability test: page indices stable across eviction churn)
- [ ] T3 — Synthetic branching-trace bench (flat prefix-cache control;
      hit-rate × TTFT × match-latency; the G2 evidence)
- [ ] T4 — GOAT gate run + promotion decision (`radix_prefix_cache`
      default-off until G1–G4 pass)
- [ ] T5 — Consumer note in riir-ai (serving-lane trigger: when continuous
      batching lands, consume this primitive — do NOT re-derive a private
      tree there)

## Boundary

Public modelless inference primitive, zero riir deps (katgpt-kv +
katgpt-transformer only) — katgpt-rs owns it. Consumer-side serving
integration belongs to riir-ai's future serving lane.
