# Bench 800-B — lock-free slot-flip DoubleBuffer PoC vs mpsc (Issue 800 Arm B)

**Status:** RECORD — **B2 DECLINE** (slot-flip beats serial +21–46% everywhere but
ties mpsc: the promote gate requires beating BOTH >10%). Measured 2026-09-16,
M3 Max, release, median-of-7 ×2 independent runs (verdict reproduced; slot-vs-mpsc
sign flips inside ±5% across runs — a true tie).

Provenance: Issue 800 Arm B — the pufferlib/Cleanba slot-ownership mechanic as an
upgrade candidate for `katgpt-kv::async_qdq::DoubleBuffer` (whose shipped overlap is
simulated single-threaded). The arm's own decision gate named mpsc as the honest
bar: pufferlib needs the spin machine because C pthreads has no channels; Rust has
them.

## Results (N=2000 frames/rep, 2-thread measurement, no pinning)

| frame | compute cell | serial ns/f | slot-flip ns/f (overlap×) | mpsc ns/f (overlap×) | slot vs mpsc |
|---|---|---|---|---|---|
| 16 KiB | short (~4 µs) | 8,020 | 4,360 (1.84×) | 4,796 (1.67×) | **+9.1%** |
| 16 KiB | long (~200 µs) | 483,883 | 291,436 (1.66×) | 292,854 (1.65×) | +0.5% |
| 64 KiB | short (~4 µs) | 22,752 | 17,383 (1.31×) | 17,677 (1.29×) | +1.7% |
| 64 KiB | long (~200 µs) | 511,284 | 294,900 (1.73×) | 295,047 (1.73×) | +0.0% |

All variants share the identical `[AtomicU32]` frame representation + kernels
(checksums bit-identical in every cell) — the measured delta is pure handoff.

## Decision + regime map

- **DECLINE**: `async_qdq.rs` stays single-threaded; the upgrade is not filed.
- The only slot-flip-favorable cell (16 KiB short-compute, +9.1% vs mpsc) still
  misses the >10% bar — and the consumer grep is decisive: every `DoubleBuffer`
  consumer (async_qdq itself + the `async_qdq_overlap` GOAT test) models 64 KiB
  chunks with 50 µs+ attention — squarely the long-compute cell where channels are
  free (<0.01% of the 50 ms tick at 20 Hz). No consumer operates in the 1–10 µs
  regime where the mechanism could matter.
- Both concurrent designs hit the same overlap ceiling (~1.7×, below the 2.0 ideal:
  calibrated P≠C compute + 2 threads sharing the machine).

## What the PoC leaves behind (worth keeping)

- `crates/katgpt-kv/tests/slot_flip_staleness.rs` — a normative, tested
  specification of the lock-free two-slot protocol (seq-cst monotone ticket RMW;
  producer gate `turn ≥ 2p−1`, consumer gate `turn ≥ 2c+1`; interval-disjoint
  windows ⇒ torn read structurally impossible), 4/4 ×5 runs incl. 24,000-flip
  max-contention. If any future consumer ever needs real cross-thread overlap, the
  protocol + its proof-shape already exist here.
- Two design-bug case studies recorded in the bench header (zero-overlap strict
  alternation; off-by-one producer gate that let extra publishes compensate a
  missing release → write-while-read → hang).

Commit: lands with the batch commit (Arm B files; orchestrator-owned).
Issue 800 Arm B: B1/B2/B3 all [x], decline recorded in the issue.
