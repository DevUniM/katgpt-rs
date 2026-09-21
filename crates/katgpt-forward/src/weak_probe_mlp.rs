//! Trained weak-side probe consumption (Issue 865 T2) — [`MlpWeakProbe`].
//!
//! Wraps a BLAKE3-committed
//! [`ProbeArtifact`](katgpt_speculative::probe_artifact::ProbeArtifact) (the
//! `LatentDynamicsMLP` connector + shared trunk `lm_head`, trained by the
//! riir-train `nextlat_*` lane pattern) and implements the
//! [`WeakLogitProbe`] seam from Issue 865 T1: for each denoised block
//! position, the tapped early-layer hidden state goes through the connector
//! (with a zero `next_emb` — the training convention; block positions are
//! mask tokens whose embeddings carry no per-position signal) and then the
//! shared head, producing the weak logits the affine combine extrapolates
//! against.
//!
//! Zero-alloc on the hot path: the connector's scratch buffers, the latent
//! row, and the zero embedding are allocated once at construction and reused
//! across every probe call, matching the seam's `&mut self` contract.

use std::path::Path;

use katgpt_core::types::matmul;
use katgpt_speculative::belief_drafter::MlpForwardScratch;
use katgpt_speculative::probe_artifact::{ProbeArtifact, ProbeArtifactError};

use crate::d2f_context::{ProbeCtx, WeakLogitProbe};

/// A trained weak-side probe loaded from a [`ProbeArtifact`] (Issue 865 T2).
///
/// The whole artifact is frozen data: the connector MLP and the shared head
/// are never mutated at runtime (the modelless consumption rule — the only
/// weight mutation is swapping the frozen snapshot, and installation replaces
/// the probe wholesale via `D2fContext::set_guidance`).
pub struct MlpWeakProbe {
    artifact: ProbeArtifact,
    /// Connector scratch (`[2n, 2n, n, n, n]` buffers), reused per position.
    scratch: MlpForwardScratch,
    /// Connector output row `[n_embd]`, reused per position.
    latent: Vec<f32>,
    /// The connector's constant `next_emb` input `[n_embd]` — zeros. The
    /// training lane trains against the same convention (see module docs).
    zeros: Vec<f32>,
}

impl MlpWeakProbe {
    /// Wrap a verified artifact.
    ///
    /// Fails loudly when the artifact declares a tap the D2F kernel does not
    /// provide: the current single-layer kernel taps ONLY layer 0 (the
    /// POST-ATTENTION residual — attention output + input residual, pre-MLP
    /// refinement; the earliest context-carrying point), so an artifact
    /// trained against a different tap would silently misread — that must be
    /// a construction error, never a decode-time surprise.
    pub fn new(artifact: ProbeArtifact) -> Result<Self, ProbeArtifactError> {
        if artifact.tap_layer != 0 {
            return Err(ProbeArtifactError::InvalidShape(format!(
                "artifact declares tap_layer {} but the D2F kernel provides only the layer-0 tap \
                 (post-attention residual); deeper taps need the multi-layer kernel extension",
                artifact.tap_layer
            )));
        }
        let n = artifact.mlp.n_embd;
        Ok(Self {
            scratch: MlpForwardScratch::new(n),
            latent: vec![0.0f32; n],
            zeros: vec![0.0f32; n],
            artifact,
        })
    }

    /// Load + verify from a wire file, then wrap.
    pub fn from_bin(path: &Path) -> Result<Self, ProbeArtifactError> {
        Self::new(ProbeArtifact::load_from_bin(path)?)
    }

    /// Borrow the sealed artifact (commitment, version, tap metadata).
    pub fn artifact(&self) -> &ProbeArtifact {
        &self.artifact
    }
}

impl WeakLogitProbe for MlpWeakProbe {
    fn probe(&mut self, input: ProbeCtx<'_>, out: &mut [f32]) {
        let n = self.artifact.mlp.n_embd;
        let vocab = self.artifact.vocab;
        debug_assert_eq!(
            input.n_embd,
            n,
            "probe artifact n_embd must match the decode context"
        );
        debug_assert_eq!(
            out.len(),
            (input.seq_len - input.block_start) * vocab,
            "probe out must hold exactly the block's logits"
        );
        for p in input.block_start..input.seq_len {
            let h = &input.tap[p * n..(p + 1) * n];
            self.artifact
                .mlp
                .forward_into(h, &self.zeros, &mut self.scratch, &mut self.latent);
            let row_off = (p - input.block_start) * vocab;
            matmul(
                &mut out[row_off..row_off + vocab],
                &self.artifact.lm_head,
                &self.latent,
                vocab,
                n,
            );
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use katgpt_speculative::belief_drafter::LatentDynamicsMLP;

    fn fixture(vocab: usize, n_embd: usize, tap_layer: usize) -> ProbeArtifact {
        let mlp = LatentDynamicsMLP::random_init(n_embd);
        let lm_head: Vec<f32> = (0..vocab * n_embd).map(|i| (i as f32) * 0.05 - 1.0).collect();
        ProbeArtifact::from_parts(mlp, lm_head, tap_layer, 1).expect("fixture artifact")
    }

    fn probe_ctx<'a>(tap: &'a [f32], block_start: usize, seq_len: usize, vocab: usize, n_embd: usize) -> ProbeCtx<'a> {
        ProbeCtx {
            xr: tap,
            x_norm: tap,
            tap,
            tokens: &[],
            committed_len: 0,
            block_start,
            seq_len,
            vocab,
            n_embd,
            step: 0,
        }
    }

    #[test]
    fn new_rejects_deeper_tap_loudly() {
        let artifact = fixture(9, 8, 1);
        let err = match MlpWeakProbe::new(artifact) {
            Err(e) => e,
            Ok(_) => panic!("deeper tap must be rejected"),
        };
        assert!(
            err.to_string().contains("tap_layer"),
            "rejection must name the tap mismatch: {err}"
        );
    }

    #[test]
    fn probe_recomputes_direct_connector_head_math() {
        let artifact = fixture(7, 8, 0);
        let vocab = artifact.vocab;
        let n = artifact.mlp.n_embd;
        let mut probe = MlpWeakProbe::new(artifact).expect("valid artifact");

        // Two block positions (block_start = 2, seq_len = 4) over a 6-row tap.
        let tap: Vec<f32> = (0..6 * n).map(|i| ((i % 19) as f32) * 0.2 - 1.5).collect();
        let mut out = vec![0.0f32; 2 * vocab];
        probe.probe(probe_ctx(&tap, 2, 4, vocab, n), &mut out);

        for (row, p) in (2..4).enumerate() {
            let h = &tap[p * n..(p + 1) * n];
            let latent = probe.artifact.mlp.forward(h, &[0.0; 8]);
            let mut expected = vec![0.0f32; vocab];
            matmul(&mut expected, &probe.artifact.lm_head, &latent, vocab, n);
            assert_eq!(
                out[row * vocab..(row + 1) * vocab],
                expected,
                "row {row} (position {p}) must equal the direct forward+matmul"
            );
        }
    }

    #[test]
    fn probe_honors_block_start_offset() {
        let artifact = fixture(5, 8, 0);
        let vocab = artifact.vocab;
        let n = artifact.mlp.n_embd;
        let mut probe = MlpWeakProbe::new(artifact).expect("valid artifact");

        let tap: Vec<f32> = (0..6 * n).map(|i| ((i % 7) as f32) * 0.3).collect();
        let mut out = vec![0.0f32; (6 - 2) * vocab];
        probe.probe(probe_ctx(&tap, 2, 6, vocab, n), &mut out);

        // Row 0 must be position 2's logits, NOT position 0's.
        let h2 = &tap[2 * n..3 * n];
        let latent2 = probe.artifact.mlp.forward(h2, &[0.0; 8]);
        let mut expected2 = vec![0.0f32; vocab];
        matmul(&mut expected2, &probe.artifact.lm_head, &latent2, vocab, n);
        assert_eq!(out[..vocab], expected2, "first output row must be block_start's position");
    }

    #[test]
    fn from_bin_roundtrip_produces_identical_probe_output() {
        let artifact = fixture(6, 8, 0);
        let vocab = artifact.vocab;
        let n = artifact.mlp.n_embd;
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("weak_probe_test.bin");
        artifact.save_to_bin(&path).expect("save");

        let mut direct = MlpWeakProbe::new(artifact).expect("wrap");
        let mut loaded = MlpWeakProbe::from_bin(&path).expect("load");

        let tap: Vec<f32> = (0..4 * n).map(|i| ((i % 11) as f32) * 0.25).collect();
        let mut a = vec![0.0f32; 4 * vocab];
        let mut b = vec![0.0f32; 4 * vocab];
        direct.probe(probe_ctx(&tap, 0, 4, vocab, n), &mut a);
        loaded.probe(probe_ctx(&tap, 0, 4, vocab, n), &mut b);
        assert_eq!(a, b, "file roundtrip must not move a single logit");
    }

    #[test]
    fn probe_is_stable_across_calls_zero_alloc_contract() {
        // The same tap must produce the same logits on every call — the
        // reused scratch must be fully overwritten per position, never carry
        // state between calls.
        let artifact = fixture(5, 8, 0);
        let vocab = artifact.vocab;
        let n = artifact.mlp.n_embd;
        let mut probe = MlpWeakProbe::new(artifact).expect("valid artifact");

        let tap: Vec<f32> = (0..3 * n).map(|i| ((i % 13) as f32) * 0.4 - 1.0).collect();
        let mut a = vec![0.0f32; 3 * vocab];
        let mut b = vec![9.5f32; 3 * vocab]; // pre-poisoned: every slot must be overwritten
        probe.probe(probe_ctx(&tap, 0, 3, vocab, n), &mut a);
        probe.probe(probe_ctx(&tap, 0, 3, vocab, n), &mut b);
        assert_eq!(a, b, "probe must be a pure function of the tap");
        assert!(
            b.iter().all(|&v| v != 9.5),
            "every output slot must be written (no poison survives)"
        );
    }
}
