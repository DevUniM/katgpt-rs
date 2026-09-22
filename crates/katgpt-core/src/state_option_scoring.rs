//! Per-option centroid-cosine scoring over a fixed option table —
//! katgpt-rs Plan 607 T1, the modelless game-decision lane's scoring
//! primitive (opt-in `state_option_scoring`).
//!
//! # The shape being upstreamed
//!
//! riir-reflex `engine.rs` `route_terms` (Issue 004 T7): each decision
//! option carries a corpus centroid; the state is embedded; per-option
//! `sigmoid(dot(state, centroid) · ROUTE_SCALE)` ranks the options and the
//! argmax decides. Reflex measured WHY the byte-level drafter cannot do
//! this job (a short option encoding never moves a long shared context's
//! compressed length → every option ties → constant pick), and this module
//! carries the fix upstream as a generic primitive: **centroid-cosine
//! scoring only** — the compression drafter stays out of the per-decision
//! loop (Plan 607 R3, decided at the plan, never a number relaxed later).
//!
//! # Generic by law (R4)
//!
//! The surface takes `(state vector, option matrix)` — nothing
//! arena-specific in katgpt-core (a public upstream surface is not shaped
//! by one consumer). The first consumer embeds its domain's sentences into
//! vectors elsewhere and hands the vectors here; embedding is deliberately
//! NOT this module's job.
//!
//! # Contracts
//!
//! - **Sigmoid, never softmax** — per-option scores are independent
//!   [`exact_sigmoid`] projections (the Issue-870 exact form), never a
//!   normalized group distribution.
//! - **Pinned tie-break** — argmax ties go to the LOWEST index
//!   ([`cmp_for_max`] + reverse-index comparator, the same shape
//!   `pick_domain` uses). This is the exact tie-break the Plan 607 oracle
//!   fixture pins (lowest-index on equal p_clean); a scorer that broke ties
//!   differently would disagree with the oracle on honest equivalences.
//! - **Zero-alloc** — table build, scoring and the argmax are all
//!   stack-local folds. The G4 gate is the separate
//!   `state_option_scoring_alloc_check` binary (the `*_alloc_check`
//!   convention: a counting allocator would pick up sibling tests in a
//!   shared binary).
//! - **Determinism** — the unit-normalized table IS the scoring state:
//!   same input rows → bit-identical table (sequential folds, no SIMD
//!   reduction reordering, no RNG). The GOAT prints a BLAKE3 over the
//!   table bytes; two runs / two boxes must agree.
//!
//! # Unit normalization
//!
//! Both the state and every row are unit-normalized (the
//! `distance_abstain` idiom — this module CONSUMES that implementation via
//! the feature implication rather than forking a bit-parity-critical
//! numeric helper), so the dot product is a true cosine in [−1, 1] and the
//! score is `exact_sigmoid(scale · cos)` in (0, 1). A zero vector passes
//! through normalization: "no direction" reads as cosine 0 against
//! everything, never NaN.

use crate::float_order::cmp_for_max;

/// The option table: `K` unit-normalized rows built once per decision
/// corpus. This is the determinism-committed artifact — the GOAT digest is
/// taken over [`Self::rows`] bytes.
///
/// `K` is const-generic (the `pick_domain` shape): the option count is
/// part of the type, the whole hot path stays stack-local, and the
/// monomorphized folds stay branch-free. The first consumer's decision
/// sets are 9/17/34 options wide.
pub struct CentroidTable<const D: usize, const K: usize> {
    rows: [[f32; D]; K],
}

impl<const D: usize, const K: usize> CentroidTable<D, K> {
    /// Build from raw option vectors; every row is unit-normalized once at
    /// build. Bit-identical for identical inputs.
    pub fn new(options: &[[f32; D]; K]) -> Self {
        assert!(K > 0, "option table needs at least one option");
        Self {
            rows: core::array::from_fn(|i| crate::distance_abstain::unit(options[i])),
        }
    }

    /// Option count (the const `K`).
    pub const fn len(&self) -> usize {
        K
    }

    /// True only for the impossible `K = 0` instantiation (rejected at
    /// [`Self::new`]); present so `K` reads as a length, not a magic bound.
    pub const fn is_empty(&self) -> bool {
        K == 0
    }

    /// Unit-normalized row `i`.
    pub fn row(&self, i: usize) -> &[f32; D] {
        &self.rows[i]
    }

    /// All rows (the determinism digest is taken over these bytes).
    pub fn rows(&self) -> &[[f32; D]; K] {
        &self.rows
    }

    /// Score every option: `out[i] = exact_sigmoid(scale · cos(state,
    /// row_i))`. Returns the argmax index (`cmp_for_max`, ties → lowest
    /// index). Zero-alloc; deterministic fold order throughout.
    ///
    /// `scale` shapes the score SPREAD for callers that blend scores with
    /// other terms; for every `scale > 0` the returned argmax equals
    /// [`Self::pick`] (the exact sigmoid is strictly monotone) — the scale
    /// never moves the decision on its own.
    pub fn score_into(&self, state: &[f32; D], scale: f32, out: &mut [f32; K]) -> usize {
        let q = crate::distance_abstain::unit(*state);
        for (o, row) in out.iter_mut().zip(self.rows.iter()) {
            let mut dot = 0.0f32;
            for (a, b) in q.iter().zip(row.iter()) {
                dot += a * b;
            }
            *o = crate::exact_sigmoid(scale * dot);
        }
        argmax_lowest_index_tie(out)
    }

    /// Argmax cosine only — no scores materialized, no sigmoid. Ties → the
    /// lowest index. Equals [`Self::score_into`]'s return for `scale > 0`.
    pub fn pick(&self, state: &[f32; D]) -> usize {
        let q = crate::distance_abstain::unit(*state);
        let mut dots = [0.0f32; K];
        for (s, row) in dots.iter_mut().zip(self.rows.iter()) {
            let mut dot = 0.0f32;
            for (a, b) in q.iter().zip(row.iter()) {
                dot += a * b;
            }
            *s = dot;
        }
        argmax_lowest_index_tie(&dots)
    }
}

/// Argmax over `scores` with the deterministic tie-break: [`cmp_for_max`]
/// (NaN-safe total order) composed with reverse-index so the LOWEST index
/// wins a tie — `pick_domain`'s comparator shape and the Plan 607 oracle's
/// pinned tie-break. (std `max_by` folds left-to-right and keeps the
/// accumulator unless the next element compares Greater, so
/// `then(i2.cmp(i1))` makes an equal later element lose to the earlier
/// one.)
fn argmax_lowest_index_tie<const K: usize>(scores: &[f32; K]) -> usize {
    let (best, _) = (0..K)
        .map(|i| (i, scores[i]))
        .max_by(|(i1, s1), (i2, s2)| cmp_for_max(*s1, *s2).then(i2.cmp(i1)))
        .unwrap_or((0, scores[0]));
    best
}

#[cfg(test)]
mod tests {
    use super::*;

    const S: f32 = 8.0; // the substrate's route scale (reflex ROUTE_SCALE)

    #[test]
    fn unit_idiom_zero_vector_passes_through() {
        let v = crate::distance_abstain::unit([0.0f32; 4]);
        assert_eq!(v, [0.0; 4], "zero vector must not NaN — cosine 0 pass-through");
        let u = crate::distance_abstain::unit([3.0, 4.0, 0.0, 0.0]);
        assert_eq!(u, [0.6, 0.8, 0.0, 0.0]);
    }

    #[test]
    fn pick_is_cosine_argmax_with_lowest_index_ties() {
        // state along +x; options 0 and 2 identical (cos 1), option 1 off-axis.
        let options: [[f32; 2]; 3] = [[4.0, 0.0], [0.6, 1.0], [9.0, 0.0]];
        let table = CentroidTable::<2, 3>::new(&options);
        assert_eq!(table.pick(&[2.0, 0.0]), 0, "tie between 0 and 2 → lowest index");
        assert_eq!(table.pick(&[0.0, 5.0]), 1, "aligned with option 1's direction");
    }

    #[test]
    fn score_into_argmax_equals_pick_for_positive_scale() {
        let mut options = [[0.0f32; 8]; 7];
        for (i, o) in options.iter_mut().enumerate() {
            for (d, x) in o.iter_mut().enumerate() {
                *x = ((d * 7 + i * 3) % 13) as f32 - 6.0;
            }
        }
        let table = CentroidTable::<8, 7>::new(&options);
        let state = [1.0, -2.0, 3.0, -1.0, 0.5, 2.0, -0.5, 1.5];
        let mut scores = [0.0f32; 7];
        let best_scored = table.score_into(&state, S, &mut scores);
        assert_eq!(best_scored, table.pick(&state));
        for s in scores {
            assert!(s > 0.0 && s < 1.0, "exact sigmoid is bounded (0, 1), got {s}");
        }
    }

    #[test]
    fn scores_are_monotone_in_cosine() {
        let options: [[f32; 2]; 2] = [[1.0, 0.0], [2.0, 0.0]]; // same direction
        let table = CentroidTable::<2, 2>::new(&options);
        let state = [3.0, 4.0]; // cos 0.6 to both
        let mut scores = [0.0f32; 2];
        table.score_into(&state, S, &mut scores);
        assert_eq!(scores[0], scores[1], "equal cosine → equal score");
    }

    #[test]
    fn table_build_is_bit_deterministic() {
        let mut options = [[0.0f32; 16]; 5];
        for (i, o) in options.iter_mut().enumerate() {
            for (d, x) in o.iter_mut().enumerate() {
                *x = ((i * 31 + d * 7) % 11) as f32 - 5.0;
            }
        }
        let a = CentroidTable::<16, 5>::new(&options);
        let b = CentroidTable::<16, 5>::new(&options);
        for (ra, rb) in a.rows().iter().zip(b.rows().iter()) {
            let ba: Vec<u8> = ra.iter().flat_map(|f| f.to_le_bytes()).collect();
            let bb: Vec<u8> = rb.iter().flat_map(|f| f.to_le_bytes()).collect();
            assert_eq!(ba, bb, "same input rows → bit-identical table");
        }
    }

    #[test]
    fn single_option_picks_itself() {
        let options: [[f32; 4]; 1] = [[1.0, 2.0, 3.0, 4.0]];
        let table = CentroidTable::<4, 1>::new(&options);
        assert_eq!(table.pick(&[1.0, 1.0, 1.0, 1.0]), 0);
        let mut scores = [0.0f32; 1];
        table.score_into(&[1.0, 2.0, 3.0, 4.0], S, &mut scores);
        assert!(scores[0] > 0.999, "state == option → cos 1 → sigmoid ≈ 1");
    }

    #[test]
    fn planted_discrimination_refuses_constant_pick() {
        // Eight states, each aligned with a DIFFERENT basis option — the
        // reflex discrimination floor: distinct picks ≥ 2 over distinct
        // state vectors (a constant picker scores 1 distinct pick here).
        const K: usize = 8;
        let mut options = [[0.0f32; K]; K];
        for (i, row) in options.iter_mut().enumerate() {
            row[i] = 1.0;
        }
        let table = CentroidTable::<K, K>::new(&options);
        let mut picks = std::collections::HashSet::new();
        for i in 0..K {
            let mut state = [0.05f32; K];
            state[i] = 1.0;
            picks.insert(table.pick(&state));
        }
        assert_eq!(picks.len(), K, "rotated planted index → every pick distinct");
    }

    #[test]
    fn zero_state_reads_as_no_direction_not_nan() {
        let options: [[f32; 4]; 3] = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]];
        let table = CentroidTable::<4, 3>::new(&options);
        assert_eq!(table.pick(&[0.0, 0.0, 0.0, 0.0]), 0, "all cosines 0 → tie → lowest index");
    }
}
