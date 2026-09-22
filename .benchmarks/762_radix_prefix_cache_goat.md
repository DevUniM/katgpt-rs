# Bench 762 — Issue 771 T1–T4: the radix-tree prefix KV cache GOAT (RadixAttention primitive) — G1–G4 ALL PASS

**Status:** RECORD (Issue 771 T1–T4 complete; T5 consumer note landed in riir-ai)

- Date: 2026-09-14
- Feature: `radix_prefix_cache` (opt-in, katgpt-kv) — **default-OFF**
- Surface: `katgpt_kv::radix_prefix::RadixPrefixTree` + the `PagedKVCache`
  chunk-page seam (`chunk_page_tables` / `retain_chunk_pages` /
  `release_chunk_pages` / `adopt_chunk_pages`, ungated)
- Gate: `cargo test --release --test bench_762_radix_prefix_cache_goat --features radix_prefix_cache`

## What shipped

The **index half** of SGLang's RadixAttention as a public modelless
primitive: a mutable radix tree over token sequences at page granularity
(chunk = `PagedKVCache::PAGE_SIZE` = 16 tokens), each chunk carrying one
page index per KV layer. Longest-prefix match truncates to whole chunks
(the trailing partial chunk is re-prefilled — this is what makes CoW
unnecessary: a request never writes into a page another branch reads).
Leaf-preferential LRU eviction with lock-awareness; the tree owns page
**indices**, never buffers (CUDA-graph address stability by construction).
The pool half is 4 seam methods on `PagedKVCache` (pure ref-count
mechanics — the refcount discipline: pool refcount = live-seq holds +
1-while-tree-indexed; locks are a hit-rate optimization, never safety).

## G1 — correctness (both Config::micro and Config::small_target)

- **Bit-identity**: adopt-then-fill KV == fresh-fill KV over a 4-turn
  branching conversation (compared via `f32::to_bits()` — the deterministic
  filler produces NaN payloads where float `!=` lies). PASS ×2 configs.
- **Branch isolation**: two branches over a shared 4-chunk trunk — trunk
  page indices identical across branches (dedup), suffix pages exclusive,
  trunk page refcount exactly 3 (2 live seqs + 1 tree hold), writes into
  branch B's suffix never alter branch A's reads. PASS ×2.
- **Address/pool stability**: after eviction churn under a tight budget,
  no tree-held page is in the pool free list (pool never moves pages —
  captured-graph safety). PASS ×2.

## G2 — perf (16 conversations × 8 turns × 2 chunks, round-robin, 50% budget)

- **Hit-rate at equal page budget (128 chunk-pages): radix 0.184 vs flat
  0.075 — 2.45×.** The flat control (the qwen38_prefix_cache shape:
  bounded whole-prefix entries, longest-prefix scan) duplicates the trunk
  per entry — 2.5× footprint for the same coverage — and an evicted
  conversation loses everything (its trunk lived inside its entries). The
  radix tree holds trunks once and peels leaf tails.
- **Match-only latency (release, 2,560 lookups): radix 0.21 ms vs flat
  2.06 ms — 9.8×.** The radix walk is O(matched tokens) memcmp; the flat
  scan is O(entries × len) with a per-lookup length sort. Debug build:
  44.7× (1.11 vs 49.63 ms).
- (info, not gated) full serve loop incl. insert+evict: 0.11 vs 0.16 ms.

## G3 — no-regression

The module is `#[cfg(feature = "radix_prefix_cache")]`; default-features
`cargo check -p katgpt-kv` compiles it away (verified). The seam methods
are additive, never called by existing paths. The gate target carries a
`required-features` row (Issue 713 discipline — naming it without the
feature errors instead of a green zero).

## G4 — alloc

Counting global allocator over 64 match iterations (match_prefix +
path_pages_into + unlock, scratch pre-warmed): **0 allocations**. Insert
allocates (cold path — per request); eviction allocates nothing (release
callback).

## Divergences from SGLang (documented in-module)

1. Chunk-floor matching (no partial-page sharing → no CoW hazard).
2. No per-chunk hash filter — direct memcmp is the authority and the
   filter costs more than it saves at 64 B/chunk (the hash+verify pattern
   stays in `KvSegmentPool` where segments are unanchored).
3. Node-per-request instead of edge-extension (finer LRU granularity, no
   extend-vs-split special case).
4. Locks stay on the split head slot (node ids stay valid; every locker
   of a split node matched at most the head's span).

## Promotion verdict (T4): stays OPT-IN

G1–G4 all pass and the gain is modelless — but there is **no production
consumer yet**: every inference lane in the stack is single-stream
(riir-ai `.research/034` recorded the radix tree as N/A for single-stream;
the 4090 lane's flat `Qwen38PrefixCache` is the correct shape there, per
its Bench 750 divergence note). Promotion follows the `drift_segment`
precedent (GOAT PASS + consumers landed → promotion candidate): promote
when riir-ai's serving lane consumes it. The workload-conditional gain
(branching + budget pressure) has no production lane to fire on today.

## Files

- `crates/katgpt-kv/src/radix_prefix/mod.rs` — the tree
- `crates/katgpt-kv/tests/radix_prefix_cache_tests.rs` — 13 behavior tests (required-features row)
- `crates/katgpt-transformer/src/kv_cache.rs` — the 4-method seam
- `tests/bench_762_radix_prefix_cache_goat.rs` — this gate
- Root `Cargo.toml` — `radix_prefix_cache = ["katgpt-kv/radix_prefix_cache"]` + `[[test]]` row
