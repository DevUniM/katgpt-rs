//! Issue 777 T2 — modality-additive belief kernel unit gates (Research 556 /
//! FLYNN arXiv:2607.00025).
//!
//! The `#![cfg]` below protects the TEST COUNT (feature off → empty binary,
//! cargo prints `ok. 0 passed`); the `[[test]] required-features` row in
//! Cargo.toml protects the READER (the target is skipped loudly, not silently
//! green). Both are needed — see katgpt-rs AGENTS.md §"cfg-gated targets".
//!
//! Run: `cargo test -p katgpt-sense --features modality_additive --test modality_additive_superposition`

#![cfg(feature = "modality_additive")]

use katgpt_sense::reconstruction::{ReconstructionConfig, ReconstructionState};

/// Test-precedent stimulus (non-trivial: all kinds positive and distinct).
const STIMULUS: [f32; 6] = [0.5, 0.2, 0.8, 0.1, 0.3, 0.4];

fn run_additive(subset: u8, ticks: usize) -> [f32; 8] {
    let mut st = ReconstructionState::new([0.0; 8]);
    for _ in 0..ticks {
        let mut act = [0.0f32; 6];
        for m in 0..6 {
            if subset & (1 << m) != 0 {
                act[m] = STIMULUS[m];
            }
        }
        st.evolve_belief_additive(&act);
    }
    *st.belief()
}

/// G1 core: superposition by construction — each belief dim's trajectory
/// depends ONLY on its own SenseKind channel, so the full-condition value of
/// dim i equals its single-kind value for `m[i]`, exactly (pre-clamp interior;
/// retention-blend of two bounded values cannot reach the clamp).
#[test]
fn additive_superposition_exact_per_dim() {
    let full = run_additive(0b11_1111, 16);
    for m in 0..6 {
        let single = run_additive(1 << m, 16);
        for i in 0..8 {
            if katgpt_sense::reconstruction::TripleEvidence::KIND_MAP[i] == m {
                assert_eq!(
                    full[i], single[i],
                    "dim {i} (kind {m}) must be identical under full vs single-kind drive"
                );
            }
        }
    }
}

/// Graceful ablation: a silenced kind's dims decay toward 0 as α^t — gradual
/// forget, never a hard delete (0.9^30 ≈ 0.042).
#[test]
fn additive_ablation_decays_gradually() {
    let mut st = ReconstructionState::new([0.0; 8]);
    for _ in 0..64 {
        st.evolve_belief_additive(&STIMULUS);
    }
    let steady = *st.belief();
    assert!(
        steady.iter().any(|&v| v > 0.5),
        "fixture must reach a non-trivial steady state"
    );
    for _ in 0..30 {
        st.evolve_belief_additive(&[0.0; 6]);
    }
    for &v in st.belief().iter() {
        assert!(
            v.abs() < 0.1,
            "silent input must decay belief toward 0 (gradual forget), got {v}"
        );
    }
}

/// Determinism: same inputs → bit-identical belief.
#[test]
fn additive_is_deterministic() {
    let a = run_additive(0b10_1101, 16);
    let b = run_additive(0b10_1101, 16);
    assert_eq!(a, b);
}

/// Stability: belief never leaves [-1, 1] under extreme activations.
#[test]
fn additive_stays_bounded() {
    let mut st = ReconstructionState::new([0.0; 8]);
    let big = [1e3f32; 6];
    for _ in 0..256 {
        st.evolve_belief_additive(&big);
    }
    for &v in st.belief().iter() {
        assert!(v.abs() <= 1.0, "belief must stay in [-1, 1], got {v}");
    }
}

/// Config plumbing: custom retention/drive fields are honored (a sharper
/// drive scale produces a higher steady state).
#[test]
fn additive_config_fields_are_live() {
    let cfg = ReconstructionConfig {
        additive_drive_scale: 8.0, // much sharper sigmoid → higher steady state
        ..Default::default()
    };
    let mut st = ReconstructionState::with_config([0.0; 8], cfg);
    for _ in 0..64 {
        st.evolve_belief_additive(&STIMULUS);
    }
    let sharp = *st.belief();
    let base = run_additive(0b11_1111, 64);
    assert!(
        sharp[2] > base[2],
        "η=8 must drive kind-2's dim harder than the default η=4"
    );
}
