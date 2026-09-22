//! Deterministic hashed character-trigram text embedder — katgpt-rs Plan
//! 607 T4, ARENA-SIDE glue (not a katgpt-core surface: T1's law is vectors
//! in, decisions out; R4 keeps the consumer's representation choices out of
//! the primitive).
//!
//! Substrate-first note (recorded in Plan 607): no generic TEXT embedding
//! primitive exists in-tree to consume — katgpt-core's engram trigram
//! hashing operates on `CanonicalId` token ids, not text, and the
//! span-embedding hashbags in riir-reflex / riir-clippy are those repos'
//! own code (the lane split keeps them there). This is the minimal
//! deterministic glue the arena needs; it is NOT promoted, NOT shared, and
//! NOT tuned against the oracle (Plan 607: no embedder tuning in this
//! unit — the first reading must measure the untuned scorer).
//!
//! Form: byte trigrams of the (ASCII, closed-grammar) sentences →
//! splitmix64-finaled FNV-mix slot → +1.0 count. Integer ops only, so the
//! vector is bit-identical on every box; normalization happens inside the
//! scorer (`CentroidTable` unit-normalizes both sides — true cosine).

/// Embedding width. 64 keeps the hot path in L1 at the arena's option
/// counts (34 × 64 f32 = 8.7 KB per table).
pub const EMBED_DIM: usize = 64;

/// Embed `text` into `out` (reset first). Counts are raw — the scorer
/// normalizes.
pub fn embed_into(text: &str, out: &mut [f32; EMBED_DIM]) {
    *out = [0.0; EMBED_DIM];
    let b = text.as_bytes();
    if b.len() < 3 {
        // Degenerate short input: one whole-text token so it still lands
        // somewhere. Empty text stays all-zero — cosine 0 to everything,
        // the scorer's "no direction" pass-through.
        if !b.is_empty() {
            out[slot_of(b)] += 1.0;
        }
        return;
    }
    for w in b.windows(3) {
        out[slot_of(w)] += 1.0;
    }
}

fn slot_of(w: &[u8]) -> usize {
    let mut x: u64 = 0x9E37_79B9_7F4A_7C15;
    for &byte in w {
        x = (x ^ byte as u64).wrapping_mul(0x100_0000_01B3);
        x = x.rotate_left(7);
    }
    x ^= x >> 30;
    x = x.wrapping_mul(0xBF58_476D_1CE4_E5B9);
    x ^= x >> 27;
    x = x.wrapping_mul(0x94D0_49BB_1331_11EB);
    x ^= x >> 31;
    (x % EMBED_DIM as u64) as usize
}

#[cfg(test)]
fn embed(text: &str) -> [f32; EMBED_DIM] {
    let mut out = [0.0f32; EMBED_DIM];
    embed_into(text, &mut out);
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn deterministic_same_text_same_vector() {
        let a = embed("The piece leaves no holes under it on the left edge.");
        let b = embed("The piece leaves no holes under it on the left edge.");
        assert_eq!(a, b);
    }

    #[test]
    fn distinct_texts_distinct_vectors() {
        let a = embed("The piece leaves no holes under it and the stack stays low.");
        let b = embed("The piece leaves one hole under it and makes a tall bump on top.");
        let dot: f32 = a.iter().zip(b.iter()).map(|(x, y)| x * y).sum();
        let na: f32 = a.iter().map(|x| x * x).sum::<f32>().sqrt();
        let nb: f32 = b.iter().map(|x| x * x).sum::<f32>().sqrt();
        let cos = dot / (na * nb);
        assert!(
            cos < 0.999,
            "distinct sentences must not embed identically (cos {cos})"
        );
    }

    #[test]
    fn empty_text_is_the_zero_vector() {
        let v = embed("");
        assert!(v.iter().all(|&x| x == 0.0));
    }

    #[test]
    fn short_text_lands_somewhere() {
        let v = embed("ab");
        assert_eq!(v.iter().map(|x| *x as usize).sum::<usize>(), 1);
    }
}
