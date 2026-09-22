//! Issue 867 T2 G4 — `SourceFeatureAdapter` zero-alloc apply hot path.
//!
//! Separate test binary so the counting allocator is binary-unique (the
//! bench_811 convention; a unit test shares its binary with every other
//! test's allocations). The canary first proves the instrument is live — a
//! green zero from a dead counter is the green-zero trap (Issue 741's
//! lesson), so we require the canary to COUNT before trusting the zero.
//!
//! Profile axis: `katgpt_core::alloc` exists under
//! `any(debug_assertions, feature = "alloc_tracking")`, so this file carries
//! that gate IN ADDITION to the feature gate — in a release build without
//! the tracking feature the binary compiles to nothing by design, which is
//! exactly why the Cargo.toml [[test]] row carries required-features (the
//! reader protection) and why this is run at DEV profile.

#![cfg(all(
    feature = "canon_source_features",
    any(debug_assertions, feature = "alloc_tracking")
))]

use katgpt_canon::source_adapter::SourceFeatureAdapter;
use katgpt_canon::source_features::{AstHistogram, N_AST_BINS};
use katgpt_core::alloc::{TrackingAllocator, get_alloc_stats, reset_alloc_stats};

#[global_allocator]
static A: TrackingAllocator = TrackingAllocator;

#[test]
fn source_adapter_apply_is_zero_alloc() {
    // Canary: the counter must be live before the zero means anything.
    reset_alloc_stats();
    let _probe: Vec<u8> = vec![0u8; 1024];
    let (canary_allocs, _bytes) = get_alloc_stats();
    assert!(
        canary_allocs >= 1,
        "canary: TrackingAllocator counted nothing — dead counter is the green-zero trap"
    );
    reset_alloc_stats();

    const D_OUT: usize = 256;
    let w_t: Vec<f32> = (0..N_AST_BINS * D_OUT)
        .map(|i| (((i % 17) as f32) - 8.0) * 0.01)
        .collect();
    let adapter = SourceFeatureAdapter::from_weights(w_t, N_AST_BINS, D_OUT);
    let hist = AstHistogram {
        counts: core::array::from_fn(|i| (i % 7) as u32 + 1),
    };
    let mut out = vec![0.0f32; D_OUT];

    // Warmup + capture the expected output (also proves determinism below).
    adapter.apply_into(&hist, &mut out);
    let expected = out.clone();

    reset_alloc_stats();
    for _ in 0..1000 {
        adapter.apply_into(&hist, &mut out);
    }
    let (allocs, _bytes) = get_alloc_stats();
    assert_eq!(
        allocs, 0,
        "apply_into allocated {allocs} times over 1000 calls — G4 violation"
    );
    assert_eq!(out, expected, "apply drifted across 1000 calls");

    // The raw-slice seam (back-map path) carries the same contract.
    let features = hist.normalized();
    adapter.apply_slice_into(&features, &mut out);
    reset_alloc_stats();
    for _ in 0..1000 {
        adapter.apply_slice_into(&features, &mut out);
    }
    let (allocs, _bytes) = get_alloc_stats();
    assert_eq!(
        allocs, 0,
        "apply_slice_into allocated {allocs} times over 1000 calls — G4 violation"
    );
}
