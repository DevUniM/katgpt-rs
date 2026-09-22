# Bench 841 — `.kpt` single-file weight-archive POC (Issue 841 / Research 568 fusion 2)

**Status:** POC LANDED 2026-09-19 (owner gate D3 override: POC + perf + sec
evidence instead of a deferral). Opt-in feature `kpt_archive` — NOT a
promotion candidate; the format+engine lift stays parked until a
NeuronShard-Merkle consumer actually wants single-file mmap hot-swap.

## What landed

`katgpt-core/src/kpt_archive.rs` (feature `kpt_archive`, zero new deps —
blake3 + bytemuck already non-optional) + `examples/kpt_archive_poc.rs`
(poc + perf) + `tests/kpt_archive_sec_injection.rs` (17 bad-injection arms).

- **Format v1**: .cact-style nameless positional layer-major single file —
  32 B header · 64 B/layer directory · 16-aligned padded payloads
  (pos_bits ‖ neg_bits ‖ row_scale, canonical LE) · 64 B trailer
  (pairwise-BLAKE3 Merkle root + archive id). Sequential layout is VERIFIED,
  not assumed (splice/reorder/overlap rejected structurally).
- **Atomic hot-swap** = temp write + fsync + rename; `swap_in_place`
  verifies the built bytes BEFORE any disk write (verify-before-rename) and
  returns the new `archive_id` — the replay detector.

## Measured (M3 Max, release, 2026-09-19)

8 layers at the served shape 768×3072 (Research 569's reference geometry)
→ **4.52 MiB** archive (21.3× smaller than the f32 equivalent — the
footprint argument this format exists for):

| operation | measured |
|---|---|
| build (serialize + hash) | 5.3 ms |
| full verify (structure + 8 layer hashes + Merkle + id) | **4,495 µs ≈ 1006 MiB/s** |
| atomic hot-swap (write + fsync + rename + reload + re-verify) | **21.0 ms** |
| first write | 8.4 ms |

Round-trip: all 8 layers bit-identical (`pos_bits`/`neg_bits`/`row_scale`);
build byte-deterministic across calls; zero-copy `layer_view` == copying path.

## Security (the 17 arms, all green)

Fail-closed ladder — structure (magic/version/length/overflow-checked
offsets/strict sequencing) → per-layer BLAKE3 → Merkle root → archive id:
magic corruption · version bump · empty/tiny/truncated files · payload
single-bit flip (LayerHashMismatch) · directory hash swap between layers ·
merkle-root tamper · archive-id tamper · offset-beyond-EOF · offset+len u64
wrap attack · layer-count inflation · non-sequential/overlapping layout ·
blocks64 dimension mismatch · valid-but-stale replay (id differs — the
documented division: integrity ≠ freshness, the id is the consumer's
replay signal) · refused swap leaves the live file untouched · whole-file
atomic replacement with no temp litter · empty archive as the documented
degenerate case.

## Known POC limits (deliberate)

- **No mmap** (no memmap2 dep): load is `read` + borrowed views; the format
  is mmap-ready (fixed offsets, 16-aligned) and the zero-copy path is
  alignment-checked via bytemuck. A production lift adds the dep.
- **POC, not promoted**: no production consumer; rides the no-default-consumer
  rule like every fusion row in Issue 841.
