//! Causal perturbation strategies for injected memory segments.
//!
//! Each function applies one [`Intervention`](super::types::Intervention)
//! variant in-place on a `&mut [T]` slice. Zero allocation — all perturbations
//! mutate the caller-owned buffer.

use fastrand::Rng;

/// `Empty` intervention — zero-fill (replace all elements with `Default`).
///
/// Content is removed but length/format preserved. A faithful consumer
/// should fall back to baseline behavior (small delta vs no-memory baseline)
/// because zeroed memory carries no signal.
#[inline]
pub fn perturb_empty<T: Clone + Default>(memory: &mut [T]) {
    for elem in memory.iter_mut() {
        *elem = T::default();
    }
}

/// `Shuffle` intervention — Fisher-Yates on the slice.
///
/// Destroys temporal/causal structure while preserving the multiset of
/// values. A faithful consumer that depends on ordering (e.g. positional
/// weights, sequence-aware readout) produces a large behavioral delta.
#[inline]
pub fn perturb_shuffle<T>(memory: &mut [T], rng: &mut Rng) {
    // Fisher-Yates: for i from last down to 1, swap[i] <-> swap[random j in 0..=i].
    if memory.len() < 2 {
        return;
    }
    let mut i = memory.len() - 1;
    while i > 0 {
        let j = rng.usize(..=i);
        memory.swap(i, j);
        i -= 1;
    }
}

/// `Corrupt` intervention — random element displacement.
///
/// Each element is, with probability 0.5, replaced by a clone of a randomly
/// chosen *different* element from the same slice. Breaks internal coherence
/// (duplicates, lost ordering) without introducing external content.
#[inline]
pub fn perturb_corrupt<T: Clone>(memory: &mut [T], rng: &mut Rng) {
    let n = memory.len();
    if n < 2 {
        return;
    }
    for i in 0..n {
        if rng.usize(..2) == 0 {
            // Pick an index != i (guaranteed by offsetting then wrapping).
            let j = (i + 1 + rng.usize(..n - 1)) % n;
            let replacement = memory[j].clone();
            memory[i] = replacement;
        }
    }
}

/// `Irrelevant` intervention — replace elements with picks from an external pool.
///
/// Substitutes same-format unrelated content. The pool is caller-provided
/// (e.g. tokens from a different context, latent vectors from another shard).
/// No-op if the pool is empty.
#[inline]
pub fn perturb_irrelevant<T: Clone>(memory: &mut [T], rng: &mut Rng, pool: &[T]) {
    if pool.is_empty() {
        return;
    }
    let pool_len = pool.len();
    for elem in memory.iter_mut() {
        let pick = rng.usize(..pool_len);
        *elem = pool[pick].clone();
    }
}

/// `Filler` intervention — replace all elements with a constant placeholder.
///
/// Semantically-empty content (e.g. padding token, placeholder scalar).
/// Unlike [`perturb_empty`] which uses `Default::default()`, the caller
/// chooses the placeholder here, allowing a non-zero filler (e.g. `<pad>`
/// token id) that tests whether the consumer distinguishes "no content"
/// from "garbage content".
#[inline]
pub fn perturb_filler<T: Clone>(memory: &mut [T], filler: &T) {
    for elem in memory.iter_mut() {
        *elem = filler.clone();
    }
}

/// `MatchedSwap` intervention (Issue 776, Research 555 — CVRR §2.1/§5.3) —
/// **coherent whole-buffer replacement** with a contrastive donor's state.
///
/// Unlike [`perturb_irrelevant`] (random element picks from a pool — an
/// incoherent mixture) this substitutes one intact, semantically valid
/// counterfactual state. The donor *selection protocol* is caller-side and
/// is what makes the intervention sharp: pick a donor that shares the
/// query/context and differs in the evidence (so differs in the outcome) —
/// a contrastive pair. Swapping then isolates **evidence-conditioned
/// content** specifically: a consumer that tracks the evidence must change
/// behavior toward the donor's outcome, while question/context
/// representation stays fixed (CVRR §5.3: swapped-state 26.7% vs text-only
/// anchor 50.0% — incompatible evidence-content is MORE disruptive than
/// none, a distinction random-pool substitution cannot show).
///
/// Length-mismatch is a no-op (guarded by `debug_assert_eq!`) — a partial
/// swap would be neither state.
#[inline]
pub fn perturb_matched_swap<T: Clone>(memory: &mut [T], donor: &[T]) {
    debug_assert_eq!(
        memory.len(),
        donor.len(),
        "matched_swap donor must be same-length (a coherent whole-state swap)"
    );
    if memory.len() != donor.len() {
        return;
    }
    for (dst, src) in memory.iter_mut().zip(donor.iter()) {
        *dst = src.clone();
    }
}

/// `NormNoise` intervention, whole-slice L2 form (Issue 776, Research 555 —
/// CVRR §2.1 Figure 1a "row-norm-matched noise") — replace the memory with
/// Gaussian noise scaled to the memory's own L2 norm: `n = g · (‖s‖/‖g‖)`.
///
/// Preserves total magnitude while destroying structure — separating the
/// "consumer reads the norm/energy" channel from the "consumer reads the
/// structure" channel. Origin-Gaussian noise (e.g.
/// `LatentSpace::noise`) destroys both at once and cannot separate them.
/// For a `[k×d]` row-major layout use [`perturb_norm_matched_noise_rows`]
/// (CVRR matches per-token-row norms).
///
/// Zero-norm memory stays zero (magnitude trivially preserved). Gaussian
/// draws use Box-Muller from the caller's `rng` — deterministic given the
/// rng state, zero allocation.
pub fn perturb_norm_matched_noise(memory: &mut [f32], rng: &mut Rng) {
    norm_matched_noise_into(memory, memory.len(), 0, rng);
}

/// `NormNoise` intervention, per-row form — CVRR's row-norm matching for a
/// flat `[k×d]` row-major buffer: each `row_len`-sized chunk gets noise
/// scaled to that chunk's own L2 norm.
///
/// `row_len` MUST divide the buffer length (`debug_assert`); a `row_len` of
/// `0` degenerates to the whole-slice form.
pub fn perturb_norm_matched_noise_rows(memory: &mut [f32], row_len: usize, rng: &mut Rng) {
    debug_assert!(
        memory.len().is_multiple_of(row_len.max(1)),
        "row_len must divide the buffer length"
    );
    if row_len == 0 || row_len > memory.len() {
        norm_matched_noise_into(memory, memory.len(), 0, rng);
        return;
    }
    let mut offset = 0;
    while offset < memory.len() {
        let end = (offset + row_len).min(memory.len());
        norm_matched_noise_into(memory, end, offset, rng);
        offset = end;
    }
}

/// Shared engine: overwrite `memory[offset..end]` with Box-Muller Gaussian
/// noise scaled to that span's L2 norm. Zero allocation, in-place.
fn norm_matched_noise_into(memory: &mut [f32], end: usize, offset: usize, rng: &mut Rng) {
    let span = &mut memory[offset..end];
    if span.is_empty() {
        return;
    }

    // Target magnitude: the span's own L2 norm.
    let target_norm: f32 = span.iter().map(|x| x * x).sum::<f32>().sqrt();
    if target_norm < 1e-12 {
        // Zero (or numerically zero) memory: magnitude is trivially
        // preserved by staying zero.
        span.fill(0.0);
        return;
    }

    // Gaussian draws via Box-Muller, written in place, accumulating g's
    // squared norm in the same pass.
    let mut g_sq: f32 = 0.0;
    for x in span.iter_mut() {
        // u1 in (0, 1] — log(0) guarded by the next_up-style retry-free clamp.
        let mut u1 = rng.f32();
        while u1 <= f32::EPSILON {
            u1 = rng.f32();
        }
        let u2 = rng.f32();
        let g = (-2.0 * u1.ln()).sqrt() * (std::f32::consts::TAU * u2).cos();
        *x = g;
        g_sq += g * g;
    }
    let g_norm = g_sq.sqrt();
    if g_norm < 1e-12 {
        // Astronomically unlikely (all draws ≈ 0); deterministic fallback —
        // spread the target norm uniformly with alternating signs.
        let m = target_norm / (span.len() as f32).sqrt();
        for (i, x) in span.iter_mut().enumerate() {
            *x = if i & 1 == 0 { m } else { -m };
        }
        return;
    }

    let scale = target_norm / g_norm;
    for x in span.iter_mut() {
        *x *= scale;
    }
}

// ---------------------------------------------------------------------------
// Unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn rng() -> Rng {
        Rng::with_seed(0xCAFE)
    }

    #[test]
    fn test_perturb_empty_zeros_all() {
        let mut m = vec![1.0_f32, 2.0, 3.0, 4.0];
        perturb_empty(&mut m);
        assert!(m.iter().all(|&v| v == 0.0));
        // Length preserved.
        assert_eq!(m.len(), 4);
    }

    #[test]
    fn test_perturb_shuffle_preserves_multiset() {
        let mut m = vec![1_u32, 2, 3, 4, 5, 6, 7, 8];
        let original = m.clone();
        perturb_shuffle(&mut m, &mut rng());
        // Multiset unchanged.
        let mut sorted_orig = original.clone();
        sorted_orig.sort_unstable();
        let mut sorted_now = m.clone();
        sorted_now.sort_unstable();
        assert_eq!(sorted_orig, sorted_now);
        // But order changed (extremely unlikely to be identity for 8 elems).
        assert_ne!(original, m);
    }

    #[test]
    fn test_perturb_shuffle_short_slice_noop() {
        let mut m = vec![42_u32];
        let original = m.clone();
        perturb_shuffle(&mut m, &mut rng());
        assert_eq!(m, original);
    }

    #[test]
    fn test_perturb_corrupt_changes_some_elements() {
        let mut m = vec![1_u32, 2, 3, 4, 5, 6, 7, 8];
        let original = m.clone();
        perturb_corrupt(&mut m, &mut rng());
        // At least one element should differ.
        assert!(m.iter().zip(&original).any(|(&a, &b)| a != b));
    }

    #[test]
    fn test_perturb_irrelevant_substitutes_from_pool() {
        let mut m = vec![0_u32; 8];
        let pool = vec![100_u32, 200, 300];
        perturb_irrelevant(&mut m, &mut rng(), &pool);
        // Every element is now from the pool.
        assert!(m.iter().all(|&v| pool.contains(&v)));
        // And none is the original 0.
        assert!(m.iter().all(|&v| v != 0));
    }

    #[test]
    fn test_perturb_irrelevant_empty_pool_noop() {
        let mut m = vec![1_u32, 2, 3];
        let original = m.clone();
        perturb_irrelevant(&mut m, &mut rng(), &[]);
        assert_eq!(m, original);
    }

    #[test]
    fn test_perturb_filler_constant_fill() {
        let mut m = vec![1.0_f32, 2.0, 3.0];
        perturb_filler(&mut m, &7.5);
        assert!(m.iter().all(|&v| v == 7.5));
    }

    // ── Issue 776 (Research 555 / CVRR) interventions ─────────────────────

    #[test]
    fn test_perturb_matched_swap_copies_donor_verbatim() {
        let mut m = vec![1_u32, 2, 3, 4];
        let donor = vec![9_u32, 8, 7, 6];
        perturb_matched_swap(&mut m, &donor);
        assert_eq!(m, donor, "whole-state coherent swap must be verbatim");
    }

    #[test]
    #[should_panic(expected = "matched_swap donor must be same-length")]
    fn test_perturb_matched_swap_length_mismatch_panics_in_debug() {
        // A partial swap would be neither state — guarded by debug_assert
        // (a programming error at the call site, not a runtime condition).
        let mut m = vec![1_u32, 2, 3];
        let donor = vec![9_u32, 8];
        perturb_matched_swap(&mut m, &donor);
    }

    #[test]
    fn test_perturb_norm_matched_noise_preserves_l2() {
        let mut m = vec![3.0_f32, -4.0, 0.5, 12.0, -0.25, 1.0];
        let expected_norm: f32 = m.iter().map(|x| x * x).sum::<f32>().sqrt();
        let mut rng = rng();
        perturb_norm_matched_noise(&mut m, &mut rng);
        let got: f32 = m.iter().map(|x| x * x).sum::<f32>().sqrt();
        let rel_err = ((got - expected_norm) / expected_norm).abs();
        assert!(
            rel_err < 1e-4,
            "L2 norm preserved: got {got}, want {expected_norm}"
        );
        // Structure destroyed: not equal to any plausible original layout.
        assert_ne!(m, vec![3.0, -4.0, 0.5, 12.0, -0.25, 1.0]);
    }

    #[test]
    fn test_perturb_norm_matched_noise_zero_stays_zero() {
        let mut m = vec![0.0_f32; 8];
        let mut rng = rng();
        perturb_norm_matched_noise(&mut m, &mut rng);
        assert!(m.iter().all(|&v| v == 0.0));
    }

    #[test]
    fn test_perturb_norm_matched_noise_deterministic() {
        // Golden-style: same rng seed → identical output (T5).
        let base = vec![1.5_f32, -2.0, 3.0, -0.5, 4.0, 0.25];
        let mut a = base.clone();
        let mut b = base.clone();
        perturb_norm_matched_noise(&mut a, &mut Rng::with_seed(0xC0FFEE));
        perturb_norm_matched_noise(&mut b, &mut Rng::with_seed(0xC0FFEE));
        assert_eq!(a, b);
        // Different seed → different structure (same norm).
        let mut c = base.clone();
        perturb_norm_matched_noise(&mut c, &mut Rng::with_seed(0x5EED));
        assert_ne!(a, c);
        let na: f32 = a.iter().map(|x| x * x).sum::<f32>().sqrt();
        let nc: f32 = c.iter().map(|x| x * x).sum::<f32>().sqrt();
        assert!((na - nc).abs() < 1e-3, "both seeds preserve the norm");
    }

    #[test]
    fn test_perturb_norm_matched_noise_rows_per_row_norms() {
        // [2x3] layout: rows [3,4,0] (norm 5) and [0,0,0] (norm 0).
        let mut m = vec![3.0_f32, 4.0, 0.0, 0.0, 0.0, 0.0];
        let mut rng = rng();
        perturb_norm_matched_noise_rows(&mut m, 3, &mut rng);
        let row0: f32 = m[0..3].iter().map(|x| x * x).sum::<f32>().sqrt();
        assert!((row0 - 5.0).abs() < 1e-4, "row 0 keeps its own norm");
        assert!(m[3..6].iter().all(|&v| v == 0.0), "zero row stays zero");
    }
}
