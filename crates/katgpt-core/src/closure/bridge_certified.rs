//! `BridgeCertified` — the determinism contract for raw↔latent bridges at the
//! sync boundary (Proposal 005, katgpt-rs Phase 1+2; Plan 604).
//!
//! Plan 385 closed the per-module cognition determinism gap for WASM `cog_*`
//! modules (G3 cross-arch gate + `CogSlashEvidence`). The bridges those
//! modules depend on — the raw→latent projections in [`super::bridge`] — had
//! no such contract. A client running the platform-SIMD path on aarch64 and a
//! pillar replaying on `x86_64` can disagree in the last ULP: [`super::bridge`]'s
//! dot goes through [`crate::simd::simd_dot_f32`], which reassociates the sum
//! (SIMD lanes + fused mul-add), and reassociated float addition is not
//! cross-arch stable. This module ships the certification surface:
//!
//! - [`BridgeCertified`] — marker trait: freeze-version pinning + pillar-side
//!   byte-level replay.
//! - [`certified_ptg_to_motif_embedding`] / [`certified_ptg_to_motif_embedding_into`]
//!   — the certified raw→latent kernel. Identical math to
//!   [`super::bridge::ptg_to_motif_embedding`] except the dot:
//!   [`crate::simd::dot_f32_ordered`] (sequential fold, deterministic by
//!   construction) instead of the platform-SIMD dot, and [`crate::simd::fast_sigmoid`]
//!   pinned by name (Cephes polynomial — a fixed software op sequence; the
//!   libm-based [`crate::simd::exact_sigmoid`] is the per-platform reference
//!   and is deliberately NOT used: libm `expf` diverges across platforms).
//! - [`g1_corpus`] — the deterministic G1 corpus (v1), shared by the harness
//!   example and the audit tests so there is exactly one definition.
//!
//! ## Why the certified kernel deliberately does not reuse the shipped one
//!
//! [`super::bridge::ptg_to_motif_embedding`] is a cold/warm diagnostic path
//! whose platform-SIMD dot is measurably faster (it vectorizes). Bit-identity
//! across architectures requires the accumulation order to be part of the
//! contract, so the certified kernel pays the sequential fold. The shipped
//! path is untouched — the default build is byte-identical, and callers opt
//! into certification per call site.
//!
//! ## Wire layouts (canonical, little-endian everywhere)
//!
//! - Freeze snapshot: `[u32 LE k][u32 LE n][f32 LE × k·n]`.
//! - Replay output: `[f32 LE × K]`.
//! - [`BridgeCertified::freeze_version_hash`] = BLAKE3 over
//!   `b"katgpt-bridge-certified-v1" || freeze snapshot bytes`.
//!
//! All arithmetic here is IEEE f32 `+`, `*`, `/` in fixed order over finite
//! values — no `libm` transcendentals, no reassociation, no denormals in the
//! reachable range (`fast_sigmoid` clamps at |x| > 40, so `exp` arguments stay
//! within ±40 and every intermediate is a normal f32).

use super::PrimitiveTransitionGraph;
use super::bridge::{MotifDirections, feature_index};
use crate::simd::{dot_f32_ordered, fast_sigmoid};

/// Domain-separation prefix for [`BridgeCertified::freeze_version_hash`].
const FREEZE_HASH_DOMAIN: &[u8] = b"katgpt-bridge-certified-v1";

/// Marker trait: the implementing bridge is certified for quorum replay.
///
/// Certified bridges MUST satisfy, by construction:
///
/// 1. **Deterministic** — same inputs → bit-identical outputs on every target
///    architecture. For the motif bridge this is delivered by the sequential
///    fold (`dot_f32_ordered`) + the Cephes polynomial sigmoid
///    (`fast_sigmoid`): fixed IEEE op sequences, no libm, no reassociation.
/// 2. **Freeze-version-pinned** — the output is a pure function of
///    (raw inputs, freeze snapshot); the snapshot is content-addressed by
///    [`freeze_version_hash`](BridgeCertified::freeze_version_hash) and that
///    hash travels with any synced scalar the bridge produced, so a pillar can
///    reject version-skewed scalars at commitment check before replaying.
/// 3. **Replayable from bytes** — [`replay`](BridgeCertified::replay)
///    re-derives the output from the wire forms (postcard PTG + canonical
///    snapshot), which is what the Piece-3 drift sampler / pillar-side
///    forensic replay consumes.
///
/// Bridges that violate any property MUST NOT impl this trait. The audit
/// tests (`tests/bridge_certified_invariants.rs`) and the G1 harness
/// (`examples/bridge_determinism_check.rs`) are the empirical gates; f32
/// determinism is not provable in Lean (`ℝ` has no ULP).
pub trait BridgeCertified {
    /// BLAKE3 over the domain-separated freeze snapshot this bridge projects
    /// onto. Content-addressed: flipping one coefficient bit changes the hash.
    fn freeze_version_hash(&self) -> [u8; 32];

    /// Pillar-side forensic replay from wire bytes.
    ///
    /// `raw_inputs` is a postcard-encoded
    /// [`PrimitiveTransitionGraph`]; `freeze_snapshot` is the client's claimed
    /// canonical snapshot (see the module docs for the layout).
    ///
    /// Returns the output as `[f32 LE × K]`, or:
    /// - [`BridgeCertifyError::FreezeSkew`] when the claimed snapshot's hash
    ///   differs from this table's — the Piece-3 *valid divergence* (the
    ///   bridge is deterministic, but against a different freeze version):
    ///   NOT slashable; reject the synced scalar and re-request against the
    ///   canonical snapshot.
    /// - [`BridgeCertifyError::BadInputs`] when `raw_inputs` does not decode.
    /// - [`BridgeCertifyError::NonFreezeable`] when this table's own state is
    ///   not certifiable (non-finite coefficients).
    fn replay(
        &self,
        raw_inputs: &[u8],
        freeze_snapshot: &[u8],
    ) -> Result<Vec<u8>, BridgeCertifyError>;
}

/// Error taxonomy for [`BridgeCertified::replay`].
///
/// The variants separate the two Piece-3 outcomes a pillar must distinguish:
/// [`FreezeSkew`](BridgeCertifyError::FreezeSkew) is a *valid* divergence
/// (version skew — reject + re-request, never slash), while everything else
/// is malformed evidence.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum BridgeCertifyError {
    /// The client's claimed freeze snapshot is not the pillar's snapshot.
    /// Carries both hashes: `client` = BLAKE3 of the submitted bytes,
    /// `pillar` = this table's [`freeze_version_hash`](BridgeCertified::freeze_version_hash).
    FreezeSkew {
        client_freeze_hash: [u8; 32],
        pillar_freeze_hash: [u8; 32],
    },
    /// `raw_inputs` is not a decodable PTG.
    BadInputs(String),
    /// The certified table itself carries non-finite coefficients — it can
    /// never be certified. (Signaling-NaN quieting is architecture-defined,
    /// so non-finite tables are refused at the door rather than hashed.)
    NonFreezeable,
}

impl std::fmt::Display for BridgeCertifyError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::FreezeSkew {
                client_freeze_hash,
                pillar_freeze_hash,
            } => write!(
                f,
                "freeze skew: client {client_freeze_hash:02x?} != pillar {pillar_freeze_hash:02x?}"
            ),
            Self::BadInputs(e) => write!(f, "bad PTG inputs: {e}"),
            Self::NonFreezeable => write!(f, "directions carry non-finite coefficients"),
        }
    }
}

impl std::error::Error for BridgeCertifyError {}

impl MotifDirections {
    /// Canonical little-endian freeze snapshot:
    /// `[u32 LE k][u32 LE n][f32 LE × k·n]`.
    ///
    /// Explicit `to_le_bytes` (not `bytemuck::cast_slice`, which is
    /// native-endian) so the bytes — and therefore the freeze hash — are
    /// identical on every target.
    #[must_use]
    pub fn to_freeze_snapshot(&self) -> Vec<u8> {
        let mut out = Vec::with_capacity(8 + self.directions.len() * 4);
        out.extend_from_slice(&(self.k as u32).to_le_bytes());
        out.extend_from_slice(&(self.n as u32).to_le_bytes());
        for v in &self.directions {
            out.extend_from_slice(&v.to_le_bytes());
        }
        out
    }

    /// Decode a canonical freeze snapshot. Inverse of
    /// [`to_freeze_snapshot`](MotifDirections::to_freeze_snapshot); rejects
    /// trailing bytes, shape overflow, and non-finite coefficients.
    pub fn from_freeze_snapshot(bytes: &[u8]) -> Option<Self> {
        if bytes.len() < 8 {
            return None;
        }
        let k = u32::from_le_bytes([bytes[0], bytes[1], bytes[2], bytes[3]]) as usize;
        let n = u32::from_le_bytes([bytes[4], bytes[5], bytes[6], bytes[7]]) as usize;
        let body = &bytes[8..];
        if body.len() != k.checked_mul(n)? * 4 {
            return None;
        }
        let mut directions = Vec::with_capacity(k * n);
        for chunk in body.as_chunks::<4>().0 {
            directions.push(f32::from_le_bytes([chunk[0], chunk[1], chunk[2], chunk[3]]));
        }
        if directions.iter().any(|v| !v.is_finite()) {
            return None;
        }
        Self::from_flat(directions, k, n)
    }

    /// Content-addressed freeze hash over the canonical snapshot,
    /// domain-separated (see [`FREEZE_HASH_DOMAIN`]).
    ///
    /// Returns `None` for non-finite tables: a certified hash must not exist
    /// for a table whose replay is architecture-ambiguous (sNaN quieting).
    #[must_use]
    pub fn freeze_snapshot_hash(&self) -> Option<[u8; 32]> {
        if self.directions.iter().any(|v| !v.is_finite()) {
            return None;
        }
        let mut hasher = blake3::Hasher::new();
        hasher.update(FREEZE_HASH_DOMAIN);
        hasher.update(&self.to_freeze_snapshot());
        Some(hasher.finalize().into())
    }
}

impl BridgeCertified for MotifDirections {
    fn freeze_version_hash(&self) -> [u8; 32] {
        self.freeze_snapshot_hash()
            .expect("BridgeCertified table must be finite; audit refuses non-finite tables")
    }

    fn replay(
        &self,
        raw_inputs: &[u8],
        freeze_snapshot: &[u8],
    ) -> Result<Vec<u8>, BridgeCertifyError> {
        // Non-finite tables never hash; refuse them as evidence of nothing
        // rather than panicking inside the pillar-side forensic path.
        let pillar_freeze_hash = self
            .freeze_snapshot_hash()
            .ok_or(BridgeCertifyError::NonFreezeable)?;
        let client_freeze_hash = {
            let mut hasher = blake3::Hasher::new();
            hasher.update(FREEZE_HASH_DOMAIN);
            hasher.update(freeze_snapshot);
            hasher.finalize().into()
        };
        if client_freeze_hash != pillar_freeze_hash {
            return Err(BridgeCertifyError::FreezeSkew {
                client_freeze_hash,
                pillar_freeze_hash,
            });
        }
        let ptg = super::deserialize_postcard(raw_inputs)
            .map_err(|e| BridgeCertifyError::BadInputs(e.to_string()))?;
        let emb = certified_ptg_to_motif_embedding(&ptg, self);
        Ok(embedding_to_bytes(&emb))
    }
}

/// **Certified raw → latent**: project a PTG into a `K`-dim motif embedding
/// with the cross-arch-deterministic kernel.
///
/// Same math as [`super::bridge::ptg_to_motif_embedding`], but the per-row
/// dot is the sequential fold ([`crate::simd::dot_f32_ordered`]) and the
/// sigmoid is pinned to the Cephes [`crate::simd::fast_sigmoid`] — both fixed
/// software op sequences, so outputs are bit-identical on `x86_64`, aarch64 and
/// wasm32 for the same input bytes. Cold-path convenience; the hot path is
/// [`certified_ptg_to_motif_embedding_into`].
#[must_use]
pub fn certified_ptg_to_motif_embedding(
    ptg: &PrimitiveTransitionGraph,
    dirs: &MotifDirections,
) -> Vec<f32> {
    let mut feature = vec![0.0f32; dirs.n];
    for node in &ptg.nodes {
        let idx = feature_index(node.primitive, dirs.n);
        if let Some(slot) = feature.get_mut(idx) {
            *slot += 1.0;
        }
    }
    let mut out = Vec::with_capacity(dirs.k);
    for k in 0..dirs.k {
        let row = dirs.row(k);
        let dot = dot_f32_ordered(row, &feature[..dirs.n]);
        out.push(fast_sigmoid(dot));
    }
    out
}

/// Zero-allocation variant of [`certified_ptg_to_motif_embedding`].
///
/// * `feature_scratch` — caller-owned scratch, `len >= dirs.n`, zeroed by
///   this call (contents may be garbage on entry).
/// * `out` — caller-owned output, `len >= dirs.k`; the first `k` slots are
///   overwritten with the embedding.
///
/// Returns `k`. Panics if either scratch is too short (documented contract —
/// a too-short scratch is a caller bug, not a runtime condition). Performs no
/// allocation (G4: `tests/bridge_certified_alloc_check.rs`).
///
/// # Panics
/// If `feature_scratch.len() < dirs.n` or `out.len() < dirs.k`.
pub fn certified_ptg_to_motif_embedding_into(
    ptg: &PrimitiveTransitionGraph,
    dirs: &MotifDirections,
    feature_scratch: &mut [f32],
    out: &mut [f32],
) -> usize {
    let n = dirs.n;
    let k = dirs.k;
    assert!(
        feature_scratch.len() >= n,
        "certified bridge: feature_scratch.len() {} < n {n}",
        feature_scratch.len()
    );
    assert!(
        out.len() >= k,
        "certified bridge: out.len() {} < k {k}",
        out.len()
    );
    let feature = &mut feature_scratch[..n];
    feature.fill(0.0);
    for node in &ptg.nodes {
        let idx = feature_index(node.primitive, n);
        if let Some(slot) = feature.get_mut(idx) {
            *slot += 1.0;
        }
    }
    for (dst, row) in out.iter_mut().zip((0..k).map(|k| dirs.row(k))) {
        *dst = fast_sigmoid(dot_f32_ordered(row, feature));
    }
    k
}

/// Canonical replay output encoding: `[f32 LE × K]`.
#[must_use]
pub fn embedding_to_bytes(emb: &[f32]) -> Vec<u8> {
    let mut out = Vec::with_capacity(emb.len() * 4);
    for v in emb {
        out.extend_from_slice(&v.to_le_bytes());
    }
    out
}

/// Decode a replay output produced by [`embedding_to_bytes`] /
/// [`BridgeCertified::replay`]. Rejects non-multiple-of-4 lengths.
pub fn embedding_from_bytes(bytes: &[u8]) -> Option<Vec<f32>> {
    if !bytes.len().is_multiple_of(4) {
        return None;
    }
    Some(
        bytes
            .as_chunks::<4>()
            .0
            .iter()
            .map(|c| f32::from_le_bytes([c[0], c[1], c[2], c[3]]))
            .collect(),
    )
}

// ── G1 corpus (v1) ────────────────────────────────────────────────────────

/// The deterministic G1 corpus, version 1.
///
/// One definition, consumed by both `examples/bridge_determinism_check.rs`
/// and `tests/bridge_certified_invariants.rs` — the digest pins are only
/// meaningful while every party generates the identical corpus (the
/// fixture-copying-is-drift lesson: copying the fixture is what detects
/// drift, copying the generator is what creates it).
///
/// **Changing ANY constant or generator step below invalidates every pinned
/// digest and requires re-running G1 on both architectures.**
#[derive(Clone, Debug)]
pub struct G1Corpus {
    /// 10 000 PTGs, deterministic from the seed.
    pub ptgs: Vec<PrimitiveTransitionGraph>,
    /// The certified directions table (K = 32, N = 64).
    pub dirs: MotifDirections,
    /// Canonical snapshot bytes for `dirs` (the corpus's freeze snapshot).
    pub freeze_snapshot: Vec<u8>,
}

/// `xoshiro256**`-free deterministic PRNG: `xorshift64*` (Marsaglia). 10
/// lines, no deps, identical on every architecture — the corpus must not
/// depend on platform RNG or floating-point generation.
struct Xorshift64Star(u64);

impl Xorshift64Star {
    fn next_u64(&mut self) -> u64 {
        let mut x = self.0;
        x ^= x >> 12;
        x ^= x << 25;
        x ^= x >> 27;
        self.0 = x;
        x.wrapping_mul(0x2545_F491_4F6C_DD1D)
    }

    /// Uniform `f32` in `[-2.0, 2.0)` from 24 random bits (exponent fixed,
    /// mantissa random → no float parsing, no libm).
    fn next_f32_bipolar(&mut self) -> f32 {
        const TWO_POW_24: f32 = 16_777_216.0;
        let mantissa = (self.next_u64() >> 40) as f32; // 24 bits, [0, 2^24)
        (mantissa / TWO_POW_24 - 0.5) * 4.0
    }
}

/// Build the G1 corpus (v1): 10 000 PTGs + the K=32/N=64 directions table.
///
/// Seed is fixed at the call sites (`G1_SEED`, below) so every run and every
/// architecture walks the identical corpus.
#[must_use]
pub fn g1_corpus(seed: u64) -> G1Corpus {
    let mut rng = Xorshift64Star(seed);
    const CORPUS_LEN: usize = 10_000;
    let mut ptgs = Vec::with_capacity(CORPUS_LEN);
    for i in 0..CORPUS_LEN {
        let node_count = 1 + (rng.next_u64() as usize) % 64;
        let mut rec = super::PtgRecorder::new(i as u32);
        let mut prev: Option<super::NodeId> = None;
        for j in 0..node_count {
            let prim = (rng.next_u64() as u32) % 256;
            let mut blake_in = [0u8; 32];
            for b in blake_in.iter_mut() {
                *b = (rng.next_u64() >> 56) as u8;
            }
            let node = rec.enter(
                super::PrimitiveKind::UserDefined(prim),
                j as u32,
                Some(blake_in),
            );
            if let Some(p) = prev {
                rec.exit(p, node, super::OperatorKind::Sequence);
            }
            prev = Some(node);
        }
        ptgs.push(rec.finish());
    }
    // Directions: K = 32 rows × N = 64 dims, values in [-2, 2).
    const K: usize = 32;
    const N: usize = 64;
    let mut directions = Vec::with_capacity(K * N);
    for _ in 0..K * N {
        directions.push(rng.next_f32_bipolar());
    }
    let dirs = MotifDirections::from_flat(directions, K, N).expect("shape K*N checked");
    let freeze_snapshot = dirs.to_freeze_snapshot();
    G1Corpus {
        ptgs,
        dirs,
        freeze_snapshot,
    }
}

/// The G1 seed. Part of the corpus contract (v1) — the digests pinned by the
/// harness and the audit tests are digests of THIS corpus.
pub const G1_SEED: u64 = 0x0604_B21D_6E55;

// ── Tests ─────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::super::{OperatorKind, PrimitiveKind, PtgRecorder, serialize_postcard};
    use super::*;

    #[test]
    fn snapshot_round_trip_is_identity() {
        let dirs = MotifDirections::from_flat((0..12).map(|i| i as f32 - 6.0).collect(), 3, 4)
            .expect("shape");
        let snap = dirs.to_freeze_snapshot();
        let back = MotifDirections::from_freeze_snapshot(&snap).expect("canonical");
        assert_eq!(back.k, dirs.k);
        assert_eq!(back.n, dirs.n);
        assert_eq!(back.directions, dirs.directions);
        // Bit-identity, not just f32 equality: re-encoding must reproduce the bytes.
        assert_eq!(back.to_freeze_snapshot(), snap);
    }

    #[test]
    fn snapshot_rejects_trailing_and_short() {
        let dirs = MotifDirections::zeros(2, 3);
        let snap = dirs.to_freeze_snapshot();
        assert!(MotifDirections::from_freeze_snapshot(&snap[..snap.len() - 1]).is_none());
        let mut trailing = snap.clone();
        trailing.push(0);
        assert!(MotifDirections::from_freeze_snapshot(&trailing).is_none());
        assert!(MotifDirections::from_freeze_snapshot(&snap[..4]).is_none());
    }

    #[test]
    fn snapshot_rejects_non_finite() {
        let mut bad = MotifDirections::zeros(1, 2);
        bad.directions[1] = f32::NAN;
        assert!(bad.freeze_snapshot_hash().is_none());
        let snap = {
            let mut s = Vec::new();
            s.extend_from_slice(&1u32.to_le_bytes());
            s.extend_from_slice(&2u32.to_le_bytes());
            s.extend_from_slice(&1.0f32.to_le_bytes());
            s.extend_from_slice(&f32::INFINITY.to_le_bytes());
            s
        };
        assert!(MotifDirections::from_freeze_snapshot(&snap).is_none());
    }

    #[test]
    fn freeze_hash_is_content_addressed() {
        let a = MotifDirections::from_flat(vec![0.5; 8], 2, 4).expect("shape");
        let mut b = a.clone();
        assert_eq!(a.freeze_snapshot_hash(), b.freeze_snapshot_hash());
        // One-ULP flip changes the hash.
        b.directions[3] = f32::from_bits(b.directions[3].to_bits() ^ 1);
        assert_ne!(a.freeze_snapshot_hash(), b.freeze_snapshot_hash());
    }

    #[test]
    fn certified_into_matches_allocating_bit_identically() {
        let mut rng = Xorshift64Star(7);
        let dirs_vec: Vec<f32> = (0..(8 * 16)).map(|_| rng.next_f32_bipolar()).collect();
        let dirs = MotifDirections::from_flat(dirs_vec, 8, 16).expect("shape");
        let mut rec = PtgRecorder::new(1);
        let mut prev = None;
        for j in 0..40 {
            let node = rec.enter(
                PrimitiveKind::UserDefined((rng.next_u64() as u32) % 256),
                j as u32,
                None,
            );
            if let Some(p) = prev {
                rec.exit(p, node, OperatorKind::Sequence);
            }
            prev = Some(node);
        }
        let ptg = rec.finish();
        let alloc = certified_ptg_to_motif_embedding(&ptg, &dirs);
        let mut feature = vec![0.0f32; dirs.n];
        let mut out = vec![0.0f32; dirs.k + 7]; // slack: only the first k are written
        let k = certified_ptg_to_motif_embedding_into(&ptg, &dirs, &mut feature, &mut out);
        assert_eq!(k, dirs.k);
        assert_eq!(&out[..k], alloc.as_slice());
    }

    #[test]
    #[should_panic(expected = "feature_scratch.len()")]
    fn into_panics_on_short_feature_scratch() {
        let dirs = MotifDirections::zeros(2, 8);
        let ptg = PrimitiveTransitionGraph::empty(0);
        let mut feature = vec![0.0f32; 7];
        let mut out = vec![0.0f32; 2];
        let _ = certified_ptg_to_motif_embedding_into(&ptg, &dirs, &mut feature, &mut out);
    }

    #[test]
    fn replay_round_trip_matches_direct_compute() {
        let mut rng = Xorshift64Star(11);
        let dirs_vec: Vec<f32> = (0..(4 * 8)).map(|_| rng.next_f32_bipolar()).collect();
        let dirs = MotifDirections::from_flat(dirs_vec, 4, 8).expect("shape");
        let mut rec = PtgRecorder::new(2);
        let node = rec.enter(PrimitiveKind::UserDefined(3), 0, None);
        let _ = node;
        let ptg = rec.finish();
        let raw = serialize_postcard(&ptg).expect("postcard");
        let snap = dirs.to_freeze_snapshot();
        let bytes = dirs.replay(&raw, &snap).expect("replay");
        let emb = embedding_from_bytes(&bytes).expect("decode");
        assert_eq!(emb, certified_ptg_to_motif_embedding(&ptg, &dirs));
    }
}
