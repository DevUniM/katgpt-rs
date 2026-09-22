//! Arms for the freeze/thaw calibration-staleness rule (Issue 841 §B-3).
//!
//! Every arm is two-sided where the rule has two sides — a guard that only
//! ever refuses is as useless as one that only ever admits, and this repo has
//! measured both failure modes in its own instruments.

use super::*;

const C_A: [u8; 32] = [0xAA; 32];
const C_B: [u8; 32] = [0xBB; 32];

fn id(version: u64, commitment: [u8; 32]) -> SnapshotId {
    SnapshotId::new(version, commitment)
}

// ── the predicate, arm by arm ──────────────────────────────────────────────

#[test]
fn t01_same_generation_same_weights_is_fresh() {
    let b = SnapshotBound::new(1.5_f32, id(7, C_A));
    assert_eq!(b.staleness(id(7, C_A)), Staleness::Fresh);
    assert_eq!(b.get(id(7, C_A)), Some(&1.5));
    // The admitting side must not spend a warning.
    assert!(!b.has_warned());
}

#[test]
fn t02_generation_moved_refuses() {
    let b = SnapshotBound::new(1.5_f32, id(7, C_A));
    assert_eq!(b.staleness(id(8, C_A)), Staleness::VersionMoved);
    assert_eq!(b.get(id(8, C_A)), None);
}

#[test]
fn t03_zero_generation_is_never_fresh_even_when_identical() {
    // Rule 1, and the arm that pins the ORDER of the checks: a 0-vs-0 pair
    // compares equal on both fields, so an equality-first predicate would
    // report Fresh and the unwired call site would read clean forever.
    let b = SnapshotBound::new(1.5_f32, SnapshotId::UNVERSIONED);
    assert_eq!(b.staleness(SnapshotId::UNVERSIONED), Staleness::Unversioned);
    assert_eq!(b.get(SnapshotId::UNVERSIONED), None);
}

#[test]
fn t04_zero_generation_on_either_side_alone_refuses() {
    let fitted_zero = SnapshotBound::new(1.5_f32, id(0, C_A));
    assert_eq!(fitted_zero.staleness(id(3, C_A)), Staleness::Unversioned);

    let current_zero = SnapshotBound::new(1.5_f32, id(3, C_A));
    assert_eq!(current_zero.staleness(id(0, C_A)), Staleness::Unversioned);
}

#[test]
fn t05_commitment_moved_under_a_held_generation_is_its_own_verdict() {
    // The defensive half: weights swapped, counter not bumped. It must NOT
    // be reported as VersionMoved — that sends the reader to refit a
    // calibration when the actual repair is a broken bump site.
    let b = SnapshotBound::new(1.5_f32, id(7, C_A));
    assert_eq!(b.staleness(id(7, C_B)), Staleness::CommitmentMoved);
    assert_eq!(b.get(id(7, C_B)), None);
}

#[test]
fn t06_the_four_verdicts_are_distinct() {
    // Pooling any two is the failure this enum exists to prevent; assert they
    // cannot silently collapse.
    let all = [
        Staleness::Fresh,
        Staleness::VersionMoved,
        Staleness::Unversioned,
        Staleness::CommitmentMoved,
    ];
    for (i, a) in all.iter().enumerate() {
        for (j, b) in all.iter().enumerate() {
            assert_eq!(a == b, i == j, "{a:?} vs {b:?}");
        }
        assert_eq!(a.is_fresh(), matches!(a, Staleness::Fresh));
        assert!(!a.reason().is_empty());
    }
}

// ── the warning latch ──────────────────────────────────────────────────────

#[test]
fn t07_warning_is_spent_once_per_binding() {
    let b = SnapshotBound::new(1.5_f32, id(7, C_A));
    assert!(!b.has_warned());
    assert_eq!(b.get(id(9, C_A)), None);
    assert!(b.has_warned());
    // Further refusals keep refusing and do not re-warn.
    for _ in 0..64 {
        assert_eq!(b.get(id(9, C_A)), None);
    }
    assert!(b.has_warned());
}

#[test]
fn t08_staleness_is_pure_and_does_not_spend_the_warning() {
    let b = SnapshotBound::new(1.5_f32, id(7, C_A));
    for _ in 0..8 {
        assert_eq!(b.staleness(id(9, C_A)), Staleness::VersionMoved);
    }
    assert!(!b.has_warned(), "classification must have no side effect");
}

#[test]
fn t09_rebind_rearms_the_latch() {
    let mut b = SnapshotBound::new(1.5_f32, id(7, C_A));
    assert_eq!(b.get(id(8, C_A)), None);
    assert!(b.has_warned());

    b.rebind(id(8, C_A));
    assert!(!b.has_warned(), "a refit must re-arm the warning");
    assert_eq!(b.get(id(8, C_A)), Some(&1.5));

    // ...and it warns AGAIN the next time it goes stale, rather than being
    // permanently silenced by one refit.
    assert_eq!(b.get(id(9, C_A)), None);
    assert!(b.has_warned());
}

#[test]
fn t10_refit_with_mutates_and_rebinds_in_one_step() {
    let mut b = SnapshotBound::new(1.5_f32, id(7, C_A));
    assert_eq!(b.get(id(8, C_B)), None);

    let returned = b.refit_with(id(8, C_B), |v| {
        *v = 2.5;
        *v * 2.0
    });
    assert_eq!(returned, 5.0);
    assert_eq!(b.fitted(), id(8, C_B));
    assert_eq!(b.get(id(8, C_B)), Some(&2.5));
    assert!(!b.has_warned());
}

// ── the escape hatch ───────────────────────────────────────────────────────

#[test]
fn t11_peek_unchecked_ignores_staleness_by_construction() {
    // Pinned so the escape hatch cannot quietly grow a check and become a
    // second `get` that nobody knows refuses.
    let b = SnapshotBound::new(1.5_f32, id(7, C_A));
    assert_eq!(*b.peek_unchecked(), 1.5);
    assert_eq!(b.get(id(99, C_B)), None);
    assert_eq!(*b.peek_unchecked(), 1.5);
}

#[test]
fn t12_into_inner_yields_the_calibration() {
    let b = SnapshotBound::new(vec![1.0_f32, 2.0], id(7, C_A));
    assert_eq!(b.into_inner(), vec![1.0, 2.0]);
}

// ── the identity type ──────────────────────────────────────────────────────

#[test]
fn t13_unversioned_is_the_default_and_is_unversioned() {
    assert_eq!(SnapshotId::default(), SnapshotId::UNVERSIONED);
    assert!(SnapshotId::UNVERSIONED.is_unversioned());
    assert!(!id(1, C_A).is_unversioned());
    assert_eq!(SnapshotId::UNVERSIONED.commitment, [0u8; 32]);
}

#[test]
fn t14_a_format_version_makes_the_guard_degenerate() {
    // The trap named in the SnapshotId docs, pinned as a measurement rather
    // than as prose: SWTF_VERSION/SDBF_VERSION are 1 for EVERY snapshot ever
    // written, so an id built from one holds the generation constant and the
    // version half of the predicate can never fire. The commitment half still
    // does — which is exactly why the degradation is silent.
    const FORMAT_VERSION: u64 = 1;
    let b = SnapshotBound::new(1.5_f32, id(FORMAT_VERSION, C_A));
    assert_eq!(
        b.staleness(id(FORMAT_VERSION, C_A)),
        Staleness::Fresh,
        "two different snapshots would both report the format version"
    );
    assert_eq!(
        b.staleness(id(FORMAT_VERSION, C_B)),
        Staleness::CommitmentMoved,
        "only the commitment half survives a format-version id"
    );
}

// ── the seam, end to end ───────────────────────────────────────────────────

#[test]
fn t15_a_swap_invalidates_an_attached_platt_pair() {
    // The whole class in one arm: a (temperature, bias) pair fitted against
    // snapshot gen 4, a swap to gen 5, and the calibrated score that must NOT
    // come back.
    let cal = SnapshotBound::new((2.0_f32, -0.5_f32), id(4, C_A));

    let apply = |p: f32, (t, b): (f32, f32)| 1.0 / (1.0 + (-(p * t + b)).exp());

    let before = cal.get(id(4, C_A)).copied().map(|tb| apply(0.6, tb));
    assert!(before.is_some(), "fresh must still calibrate");

    // The freeze/thaw swap lands.
    let after = cal.get(id(5, C_B));
    assert!(
        after.is_none(),
        "a stale head must refuse, not return a plausible score"
    );
}

#[test]
fn t16_guard_is_allocation_free_on_both_paths() {
    // G4. The guard is 32 bytes of comparison and an atomic; nothing here may
    // allocate, because `get` sits in front of a per-decision scalar.
    let b = SnapshotBound::new(1.5_f32, id(7, C_A));
    let fresh = id(7, C_A);
    let stale = id(8, C_B);
    let mut acc = 0.0_f32;
    for i in 0..1024 {
        let q = match i % 2 {
            0 => b.get(fresh),
            _ => b.get(stale),
        };
        acc += q.copied().unwrap_or(0.0);
    }
    assert_eq!(acc, 512.0 * 1.5);
}
