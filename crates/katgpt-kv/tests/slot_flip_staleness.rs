//! Issue 800 **Arm B3** — G1 staleness-is-the-spec test for the lock-free
//! slot-flip protocol (katgpt-kv; PoC companion of
//! `benches/slot_flip_poc.rs`).
//!
//! The contract under test: the consumer ALWAYS sees the exactly-one-epoch-old
//! frame — **never torn, never skipped, never duplicated** — under real
//! cross-thread contention (≥ 10⁴ flips per run here; 24 000 + 2 048 + probe).
//!
//! # Protocol (normative copy — the bench file is kept in deliberate sync)
//!
//! State: two flat slots + ONE `AtomicUsize turn` (seq-cst), a ticket counter
//! rather than a slot id. Mechanic source: PufferLib Cleanba 2-slot async
//! pipelining — riir-train [Research 454](../../riir-train/.research/454_pufferlib_pooled_env_rollout_architecture.md)
//! §2.1 ("warmup fills slot 0; then collect into write while training the
//! other slot — exactly one epoch old") → katgpt-rs Issue 800 Arm B.
//!
//! ```text
//! producer epoch p:  wait turn ≥ 2p−1  →  write slot[p & 1]  →  turn += 1
//! consumer frame c:  wait turn ≥ 2c+1  →  read  slot[c & 1]  →  turn += 1
//! ```
//!
//! Both sides bump the ONE monotone counter with one seq-cst RMW each
//! (publishes and releases interleave freely; gates are `≥` — the counter
//! never rewinds, so there is no ABA). Each gate is EXACT because the
//! waiter's own contribution to the counter is known to itself:
//!
//! - producer at epoch `p` has published exactly `p` frames, so
//!   `turn ≥ 2p−1` ⟺ releases ≥ `p−1` — every frame that ever occupied
//!   slot `p & 1` (most recently frame `p−2`) has been RELEASED. Off by
//!   one here (`2p−2`) is the classic bug: extra publishes compensate for
//!   a missing release, and the producer writes a slot the consumer is
//!   still reading.
//! - consumer at frame `c` has released exactly `c` frames, so
//!   `turn ≥ 2c+1` ⟺ publishes ≥ `c+1` — frame `c` itself (publishes are
//!   epoch-ordered by the single producer thread) is complete.
//!
//! The producer gate is NOT a wait on frame `p−1`'s release — that over-sync
//! (a plausible first draft) serializes the pipeline to P0→C0→P1→C1 with
//! zero overlap. Gating one release earlier lets producer epoch `c+1` fill
//! the other slot WHILE the consumer reads frame `c` — the Cleanba
//! produce-next-while-consume-current cadence; at balanced cost the steady
//! state is wait-free.
//!
//! Case study (recorded in the bench module docs too): the producer gate
//! must be `turn ≥ 2p−1`, not `2p−2` — the counter conflates publishes and
//! releases, and only the waiter's OWN contribution is known, so a gate one
//! release short lets extra publishes compensate for a missing release
//! (write-while-read). Caught here as an assert + hang (panic inside
//! `thread::scope` joins the still-spinning producer) on the very first
//! threaded run.
//!
//! # Why the reads are exactly `c` (monotonic — the B3 assertion)
//!
//! The producer is a SINGLE thread running epochs in order, so publishes are
//! epoch-ordered: reaching `turn ≥ 2c+1` proves frame `c` itself (not merely
//! some later frame) is complete. During the consumer's read of frame `c`,
//! the producer is in epoch `c` (slow-producer case: the consumer blocks at
//! the gate — it never reads un-published data) or epoch `c+1` (the pipeline
//! case). The consumer therefore always holds the newest published frame:
//! never fresher (the producer's in-flight frame lives in the OTHER slot),
//! never skipped or duplicated (the consumer's counter is private; each
//! frame is read exactly once). Indexing note: the issue phrases this as
//! "consumer reads i−1 while producer writes i"; with the consumer's private
//! counter `c` here, the read payload IS `c` and the producer's concurrent
//! epoch IS `c+1` — the same fact, counted from the consumer's side.
//!
//! Monotonic `payload == c` catches every violation class at once:
//! skipped frame (payload jumps), duplicated frame (payload repeats),
//! reordered frame (payload decreases), torn frame (mixed payloads within
//! one frame — see below).
//!
//! # Torn-read structural argument (point at the exact lines)
//!
//! The producer's ONLY write site is `produce_with`'s
//! `let slot: &[AtomicU32] = &self.slots[epoch & 1];` — reached exclusively
//! inside its fill-window `turn ∈ [2p−1, 2p)` (own publishes `= p`, releases
//! `R ∈ [p−1, p]` during the fill — frame `p−1` may legally be released
//! mid-fill; frame `p` is unpublished hence unread). The consumer's ONLY
//! read site is `consume_with`'s
//! `let slot: &[AtomicU32] = &self.slots[index & 1];` — reached exclusively
//! inside its read-window `turn ∈ [2c+1, 2c+2]` (own releases `= c`;
//! publishes may advance `c+1 → c+2` mid-read — epoch `c+2` needs release
//! `c+1`, which does not exist yet). Same-slot collision needs equal parity
//! (`p & 1 == c & 1`) AND overlapping windows:
//!
//! - `p == c`: fill-window `[2c−1, 2c)` vs read-window `[2c+1, 2c+2]` —
//!   disjoint; the producer's publish is the very event that can open the
//!   consumer's gate;
//! - `p == c+2`: fill-window starts at `turn ≥ 2c+3`, strictly above the
//!   read-window's ceiling — and the release RMW of frame `c` that enables
//!   it is itself sequenced-after every element read of frame `c`;
//! - `|p − c| ≥ 4`: cannot run concurrently (gates need later releases).
//!
//! So a producer write racing a consumer read of the SAME bytes cannot be
//! expressed. The fill/assert pair below still checks EVERY element with an
//! epoch-tagged payload (positive tag, negative tail sentinel) — a belt for
//! the suspenders, should the protocol ever be edited.
//!
//! Data visibility: element ops are `Relaxed` (they lower to plain
//! load/store on arm64/x86); ordering comes from the seq-cst `turn` chain —
//! the producer's stores are sequenced-before its publishing RMW, and the
//! consumer's load observing that RMW's value gives happens-before.
//!
//! # Wiring note
//!
//! Plain `cargo test` target, NO feature gate: unlike the crate's existing
//! test targets (which carry `required-features` because they exercise
//! gated modules), this test is self-contained — the protocol copy lives
//! here, nothing in `katgpt-kv` is imported, and the slot-flip upgrade of
//! `src/async_qdq.rs` is deliberately NOT landed (Arm B is decision-gated;
//! this file is the gate's correctness half, not the upgrade).

use std::hint::spin_loop;
use std::sync::atomic::{AtomicU32, AtomicUsize, Ordering};
use std::thread;

/// Spin iterations before escalating to `yield_now` — must match the bench.
const SPIN_BUDGET: u32 = 2048;

/// A zeroed frame of `elems` f32 elements. (`AtomicU32` is not `Clone` on
/// current std, so the `vec![expr; n]` form is unavailable — map-collect.)
fn zero_frame(elems: usize) -> Box<[AtomicU32]> {
    (0..elems)
        .map(|_| AtomicU32::new(0))
        .collect::<Vec<_>>()
        .into_boxed_slice()
}

/// Lock-free 2-slot flip buffer — see the module docs for the protocol and
/// the staleness/torn-read proofs. This copy is NORMATIVE for Issue 800
/// Arm B; `benches/slot_flip_poc.rs` mirrors it for measurement.
struct SlotFlip {
    /// Two flat frame buffers, allocated once. Producer writes only
    /// `slots[epoch & 1]`; consumer reads only `slots[index & 1]`.
    slots: [Box<[AtomicU32]>; 2],
    /// The one coordination variable: even = consumer released a slot,
    /// odd = producer published a frame. Strict alternation.
    turn: AtomicUsize,
}

impl SlotFlip {
    fn new(elems: usize) -> Self {
        Self {
            slots: [zero_frame(elems), zero_frame(elems)],
            turn: AtomicUsize::new(0),
        }
    }

    fn produce_with(&self, epoch: usize, fill: impl FnOnce(&[AtomicU32])) {
        // `turn + 1 ≥ 2*epoch` ⟺ `turn ≥ 2p−1` without the p=0 underflow.
        // p=0 is the Cleanba warmup (vacuous gate); p=1's gate is met by the
        // producer's own frame-0 publish (first overlap starts immediately).
        let mut spins: u32 = 0;
        while self.turn.load(Ordering::SeqCst) + 1 < 2 * epoch {
            if spins < SPIN_BUDGET {
                spin_loop();
                spins += 1;
            } else {
                std::thread::yield_now();
            }
        }
        // THE torn-read structural line: write target is `slots[epoch & 1]`,
        // inside the fill-window `turn ∈ [2p−1, 2p)` only.
        let slot: &[AtomicU32] = &self.slots[epoch & 1];
        fill(slot);
        self.turn.fetch_add(1, Ordering::SeqCst);
    }

    fn consume_with<R>(&self, index: usize, read: impl FnOnce(&[AtomicU32]) -> R) -> R {
        let mut spins: u32 = 0;
        while self.turn.load(Ordering::SeqCst) < 2 * index + 1 {
            if spins < SPIN_BUDGET {
                spin_loop();
                spins += 1;
            } else {
                std::thread::yield_now();
            }
        }
        // THE other structural line: read target is `slots[index & 1]`,
        // inside the read-window `turn ∈ [2c+1, 2c+2]` only.
        let slot: &[AtomicU32] = &self.slots[index & 1];
        let out = read(slot);
        self.turn.fetch_add(1, Ordering::SeqCst);
        out
    }
}

/// Fill every element with the epoch tag; the tail element carries the
/// NEGATIVE tag as a sentinel (catches an off-by-one region swap that a
/// uniform fill would hide). Exact integer-valued f32 payloads: any mix of
/// two epochs inside one frame is a detectable torn read.
fn fill_exact(frame: &[AtomicU32], epoch: usize) {
    let v = epoch as f32;
    for cell in frame.iter() {
        cell.store(v.to_bits(), Ordering::Relaxed);
    }
    if let Some(tail) = frame.last() {
        tail.store((-v).to_bits(), Ordering::Relaxed);
    }
}

/// Assert EVERY element: payload == epoch (tail == −epoch). `assert_eq!` on
/// exact integer-valued f32 — no tolerance, tears cannot pass.
fn assert_frame(frame: &[AtomicU32], epoch: usize) {
    let v = epoch as f32;
    for (i, cell) in frame.iter().enumerate() {
        let got = f32::from_bits(cell.load(Ordering::Relaxed));
        let want = if i + 1 == frame.len() { -v } else { v };
        assert_eq!(
            got, want,
            "B3 FAIL: frame {epoch} element {i}: expected {want}, got {got} \
             (torn/skipped/duplicated read — see module docs)"
        );
    }
}

/// Deterministic busy work to deschedule the sides at pseudo-random points,
/// forcing every interleaving class (producer ahead, consumer ahead, both
/// racing into the flip). Pure spin — no allocation, no locking.
fn jitter(units: usize) {
    for _ in 0..units {
        spin_loop();
    }
}

#[test]
fn turn_arithmetic_single_threaded() {
    // Pin the ticket arithmetic before the threaded tests: produce(0) lands
    // turn on 1 (publish); consume(0) lands it on 2 (release). Epochs 0 and
    // 1 both have gate 0 — the Cleanba warmup (slot 0 filled solo) plus the
    // first overlap (epoch 1 may fill slot 1 while frame 0 is being read).
    let sf = SlotFlip::new(4);
    assert_eq!(sf.turn.load(Ordering::SeqCst), 0);
    sf.produce_with(0, |f| fill_exact(f, 0));
    assert_eq!(sf.turn.load(Ordering::SeqCst), 1);
    sf.consume_with(0, |f| {
        assert_frame(f, 0);
        0
    });
    assert_eq!(sf.turn.load(Ordering::SeqCst), 2);
}

#[test]
fn g1_exactly_one_epoch_staleness_under_contention() {
    // 24 000 flips (≥ 10⁴ required), 8-element frames: near-zero per-frame
    // work → maximum contention on `turn`, both threads live in the flip
    // windows almost the whole run. Jitter at coprime periods (499/503)
    // desynchronizes the sides so producer-ahead, consumer-ahead, and
    // simultaneous-flip orderings all occur.
    const FRAMES: usize = 24_000;
    let sf = SlotFlip::new(8);
    thread::scope(|s| {
        s.spawn(|| {
            for p in 0..FRAMES {
                if p % 499 == 0 {
                    jitter(100_000); // producer stalls → consumer waits on publish
                }
                sf.produce_with(p, |f| fill_exact(f, p));
            }
        });
        for c in 0..FRAMES {
            if c % 503 == 0 {
                jitter(100_000); // consumer stalls → producer waits on release
            }
            sf.consume_with(c, |f| assert_frame(f, c));
        }
    });
    // Clean termination: every half-step accounted for — no lost flips.
    assert_eq!(
        sf.turn.load(Ordering::SeqCst),
        2 * FRAMES,
        "turn must land on 2N after N produce+consume pairs"
    );
}

#[test]
fn g1_realistic_frame_size_under_compute_load() {
    // The KV-chunk scale (16 KiB = 4096 f32) with real per-frame work on both
    // sides — the async_qdq-shaped regime, where the producer is often
    // AHEAD (deep into the next fill) while the consumer still reads. 2048
    // flips with whole-frame compute between flips.
    const FRAMES: usize = 2_048;
    const ELEMS: usize = 4_096;
    let sf = SlotFlip::new(ELEMS);
    thread::scope(|s| {
        s.spawn(|| {
            for p in 0..FRAMES {
                if p % 97 == 0 {
                    jitter(200_000); // producer runs extra long in some epochs
                }
                sf.produce_with(p, |f| fill_exact(f, p));
            }
        });
        for c in 0..FRAMES {
            if c % 101 == 0 {
                jitter(300_000); // consumer sometimes slower than producer
            }
            sf.consume_with(c, |f| assert_frame(f, c));
        }
    });
    assert_eq!(sf.turn.load(Ordering::SeqCst), 2 * FRAMES);
}

#[test]
fn g1_warmup_first_read_is_frame_zero_not_one() {
    // The warmup contract: the consumer's FIRST read must be frame 0
    // (the warmup-filled slot), never frame 1 — catches an off-by-one in
    // the ticket arithmetic that would silently shift the staleness to zero
    // or two epochs.
    const FRAMES: usize = 256;
    let sf = SlotFlip::new(8);
    thread::scope(|s| {
        s.spawn(|| {
            for p in 0..FRAMES {
                sf.produce_with(p, |f| fill_exact(f, p));
            }
        });
        let mut first_payload = f32::NAN;
        for c in 0..FRAMES {
            sf.consume_with(c, |f| {
                if c == 0 {
                    first_payload = f32::from_bits(f[0].load(Ordering::Relaxed));
                }
                assert_frame(f, c);
            });
        }
        assert_eq!(
            first_payload, 0.0,
            "warmup violated: first consumer read must be frame 0"
        );
    });
    assert_eq!(sf.turn.load(Ordering::SeqCst), 2 * FRAMES);
}
