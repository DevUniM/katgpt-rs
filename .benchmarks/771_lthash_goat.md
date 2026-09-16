# Bench 771 — `lthash` GOAT gate (Issue 807): incremental homomorphic multiset hash

Status: **G1 + G2 + G4 PASS — primitive lands OPT-IN** (promotion waits on the first consumer, per the no-default-consumer rule; consumers are proposal-gated: riir-chain Proposal 010 D1, riir-dapps Proposal 005 D1).
Crate: `katgpt-core`, feature `lthash` (opt-in) · bench `bench_lthash` (criterion, required-features `lthash`)
Machine: SHIKUWA (i7-13700K, Windows 11), 2026-09-16, default `target/` (no concurrent cargo in this repo observed).

## The primitive

LtHash — the Bellare–Micciancio MSet-Add-Hash construction as instantiated by
eprint 2019/227 and Agave's account-state commitment (mined read-only from
`riir-clippy/.raw/agave @ c95d8706`; `lattice-hash/src/lt_hash.rs` read
directly: `[u16; 1024]`, wrapping add/sub, BLAKE3 checksum). State
`[u16; N]` limbs (default 1024); `insert` = add, `remove` = subtract,
`merge` = sum (the deterministic-parallel-fold combiner), `checksum` =
BLAKE3 over limb bytes. Element derivation: domain-separated BLAKE3 XOF
over a LENGTH-PREFIXED part list — `(ab, c)` ≠ `(a, bc)` by construction.

## G1 — correctness (10/10 unit gates, `cargo test -p katgpt-core --features lthash --lib lthash`)

| gate | asserts |
|---|---|
| `order_invariance` | 3 seeded permutations of a 64-member multiset → identical checksums |
| `remove_and_replace_roundtrip` | insert→remove returns exactly to identity; `replace` ≡ remove+insert |
| `multiset_semantics` | {A,A,B} ≠ {A,B,B}; {A,A}−A ≡ {A} |
| `merge_equals_incremental` | chunked folds (sizes 1/7/10, both fold orders) ≡ sequential insertion — the parallel-fold determinism property |
| `encoding_is_unambiguous` | length-prefix kills part-boundary collisions |
| `domain_separation` | same parts, different domains → different elements |
| `drift_gate_incremental_equals_rebuild` | 500 random insert/remove/replace ops, incremental state bit-identical to the from-scratch rebuild of the final multiset — the property BOTH consumers' drift gates pin |
| `narrow_lane_width_holds` | the full algebra at N=128 (the consumer width-trade arm) |
| `limbs_roundtrip` | persist/restore via `from_limbs` (the durable-row shape) |
| `known_answer_vector` | hex-pinned checksum `dc6a9214…75c4963` — construction drift alarm |

## G2 — performance (criterion medians)

| op | N=1024 (default) | N=128 |
|---|---|---|
| `element_derive` (BLAKE3 XOF + limb conversion) | **1.37 µs** | 245 ns |
| `insert` | **19.2 ns** | — |
| `replace` | **31.6 ns** | 3.3 ns |
| `merge` | **19.3 ns** | — |
| `checksum` (BLAKE3 over 2 KB) | **5.76 µs** | — |

**The headline (the riir-chain commitment_root shape):**

| path | time |
|---|---|
| incremental `replace` (one member update) | **31.6 ns** |
| from-scratch fold of 1000 pre-derived members (+checksum) | **33.8 µs** |

≈ **1069×** at 1000 members — and the ratio grows linearly with member
count (Bench 028's sorted-fold version of the same rebuild measured
**31.6 ms at N=10⁵**, paid per replica per CPI; the incremental path stays
at one `replace` regardless of N).

Honest scope note: the rebuild arm uses PRE-DERIVED elements (isolates the
accumulation cost). Derive-inclusive end-to-end: an incremental update costs
`derive(new) + replace` ≈ **1.4 µs**; a derive-inclusive rebuild at N=1000
costs ≈ **1.39 ms** (1000 × 1.37 µs + fold) — the same ~1000× class. The
drift-gate recompute (periodic from-scratch audit both consumers mandate)
inherits the rebuild cost by design — that is its job.

## G4 — allocation discipline

Zero-alloc by construction: every op path is fixed-array arithmetic
(`[u16; N]` limbs, `[u8; 1024]` XOF scratch); ns-scale op timings above are
the runtime witness (a 19 ns insert cannot contain an allocation).

## G3 — no-regression

The feature is additive and opt-in (not in `default`); the default-feature
lib suite was untouched (2068 other lib tests filtered out of the G1 run;
`count_features.py` green after the total-count claim bumps 610→611 across
README.md ×3 + examples/README.md ×1).

## Verdict

**PASS — ships opt-in** (`lthash = []` in katgpt-core). Promotion to default
waits on the first consumer wiring (riir-chain 010 D1 / riir-dapps 005 D1)
passing its own consumer gate — the no-default-consumer rule.

Anti-copy held: no Agave AVX2/AVX512 batch kernel, no async hasher threads,
no freelists — the portable core is wrapping-u16 arithmetic + blake3
(~150 LOC + tests).
