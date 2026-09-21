//! `score_into` zero-alloc gate — the bench-811 counting-allocator
//! convention, for the corpus-drafter hot scorer.
//!
//! SEPARATE test binary because the counting allocator is binary-unique.
//! ONE test function: the checks share the thread-local counter and the
//! house convention keeps them serial by construction
//! (`analytic_lattice_alloc_check.rs` precedent).
//!
//! Landed for Plan 603 T1.3 (riir-reflex's G4): the engine's modelless hot
//! path composes `Lz4FlexDrafter::score_into`, so the SUBSTRATE must be
//! alloc-free after warmup — the allocating `score` path stays for cold
//! callers, and the canary here first proves the counter can SEE an
//! allocation (a green zero from a dead counter is the green-zero trap).

#![cfg(feature = "compression_drafter")]

use katgpt_core::compression_drafter::{CompressionDrafter, Lz4FlexDrafter};
use std::hint::black_box;
use std::sync::atomic::Ordering;

#[path = "common/mod.rs"]
mod common;
counting_allocator!();

fn drafter() -> Lz4FlexDrafter {
    let mut corpus = Vec::new();
    for i in 0..8 {
        corpus.extend_from_slice(
            format!(
                "deploy step {i}: verify the staging rollout and the health endpoints before \
                 promoting the release candidate to production\n"
            )
            .as_bytes(),
        );
    }
    Lz4FlexDrafter::new(corpus)
}

#[test]
fn score_into_alloc_gate() {
    // ── Canary: the counter is LIVE before any zero is trusted ──────────
    let before = ALLOC_COUNT.load(Ordering::Relaxed);
    let canary: Vec<u8> = vec![7u8; 256];
    black_box(&canary);
    assert!(
        ALLOC_COUNT.load(Ordering::Relaxed) - before > 0,
        "counting allocator must COUNT — a green zero from a dead counter is the green-zero trap"
    );
    drop(canary);

    // ── Cold: the FIRST score_into sizes table + buffers — it MUST
    //    allocate. This proves the gate can tell cold from warm. ─────────
    let mut d = drafter();
    let a0 = ALLOC_COUNT.load(Ordering::Relaxed);
    black_box(d.score_into(b"state bytes ", b"staging rollout"));
    let cold = ALLOC_COUNT.load(Ordering::Relaxed) - a0;
    assert!(
        cold > 0,
        "cold score_into must allocate (table + buffers); got 0 — is the gate blind?"
    );

    // ── Warm at the SAME shape: zero allocations. ────────────────────────
    for _ in 0..8 {
        black_box(d.score_into(b"state bytes ", b"staging rollout"));
    }
    let a1 = ALLOC_COUNT.load(Ordering::Relaxed);
    for _ in 0..100 {
        black_box(d.score_into(b"state bytes ", b"staging rollout"));
    }
    let warm = ALLOC_COUNT.load(Ordering::Relaxed) - a1;
    assert_eq!(warm, 0, "warm score_into must be alloc-free; got {warm}");

    // ── Warm at a LARGER candidate shape: one resize, then zero. ─────────
    let big = vec![b'x'; 4096];
    for _ in 0..8 {
        black_box(d.score_into(b"state bytes ", &big));
    }
    let a2 = ALLOC_COUNT.load(Ordering::Relaxed);
    for _ in 0..50 {
        black_box(d.score_into(b"state bytes ", &big));
    }
    let warm_big = ALLOC_COUNT.load(Ordering::Relaxed) - a2;
    assert_eq!(
        warm_big, 0,
        "warm large-shape score_into must be alloc-free; got {warm_big}"
    );

    // ── The allocating `score` path still allocates (the contrast arm —
    //    proves the counter distinguishes the two paths). ────────────────
    let a3 = ALLOC_COUNT.load(Ordering::Relaxed);
    black_box(d.score(b"state bytes ", b"staging rollout"));
    let alloc_path = ALLOC_COUNT.load(Ordering::Relaxed) - a3;
    assert!(
        alloc_path > 0,
        "the cold-path `score` allocates each call; counter saw none"
    );
}
