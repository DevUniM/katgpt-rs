//! Shared micro-arena fit/scoring helpers — katgpt-rs Plan 607 T5. The
//! tetris_03 recipe (corpus build → standardization → λ by state-level LOO
//! MSE → in-corpus + LOO readings), made reusable across the micro arenas,
//! plus the T1 sentence-cosine pick (the tetris_02 arm).
//!
//! Compiled ONLY by the T5 arena binaries (required-features =
//! `state_option_scoring`) — the 01 enumerators stay ungated and never see
//! this module. Both micro games freeze exactly 8 feature columns, so the
//! design width is a plain const (stable Rust rejects `{ F + 1 }` in type
//! position — the tetris_03 precedent of two named consts).

#[path = "hash_embed.rs"]
pub mod hash_embed;

use self::hash_embed::EMBED_DIM;
use crate::micro_dump::MicroOptionFixture;
use crate::micro_dump::MicroStateFixture;
use katgpt_core::state_option_scoring::CentroidTable;
use katgpt_core::state_option_scoring::head::{FittedHead, HeadFitter};

/// Frozen feature columns per micro-arena option (both games freeze 8).
pub const F: usize = 8;
/// Design width: F standardized features + intercept.
pub const D: usize = 9;
/// T1 option-table width (padded; the arenas' live widths are 2 and 3).
pub const T1_K: usize = 4;
/// Pinned λ grid (standardized scale). Selection criterion: state-level LOO
/// MSE — corpus-only, deterministic, never the agreement number.
pub const RIDGE_GRID: [f64; 4] = [1e-3, 1e-2, 1e-1, 1.0];

// ── T1 arm (untuned sentence cosine, the tetris_02 shape) ────────────────

pub fn t1_pick(state_sentence: &str, option_sentences: &[String]) -> usize {
    assert!(
        option_sentences.len() <= T1_K,
        "option width {} overflows the micro arena table",
        option_sentences.len()
    );
    let state_vec = hash_embed::embed(state_sentence);
    let mut mat = [[0.0f32; EMBED_DIM]; T1_K];
    for (dst, s) in mat.iter_mut().zip(option_sentences) {
        *dst = hash_embed::embed(s);
    }
    CentroidTable::<EMBED_DIM, T1_K>::new(&mat).pick(&state_vec)
}

// ── Corpus + standardization (the tetris_03 recipe) ──────────────────────

pub struct Standardizer {
    pub mean: [f64; F],
    pub inv_std: [f64; F],
}

impl Standardizer {
    /// Corpus-side stats in fixed column order (part of the committed
    /// recipe); std == 0 → the column carries no signal, map to 0.
    pub fn fit(rows: &[[f64; F]]) -> Self {
        let n = rows.len().max(1) as f64;
        let mut mean = [0.0f64; F];
        for r in rows {
            for (m, x) in mean.iter_mut().zip(r.iter()) {
                *m += x;
            }
        }
        for m in mean.iter_mut() {
            *m /= n;
        }
        let mut var = [0.0f64; F];
        for r in rows {
            for (v, (x, m)) in var.iter_mut().zip(r.iter().zip(mean.iter())) {
                let d = x - m;
                *v += d * d;
            }
        }
        let mut inv_std = [0.0f64; F];
        for i in 0..F {
            let s = (var[i] / n).sqrt();
            inv_std[i] = if s > 0.0 { 1.0 / s } else { 0.0 };
        }
        Self { mean, inv_std }
    }

    /// A live option's design row: standardized features + intercept.
    pub fn design(&self, raw: &[f64; F]) -> [f64; D] {
        let mut row = [0.0f64; D];
        for i in 0..F {
            row[i] = (raw[i] - self.mean[i]) * self.inv_std[i];
        }
        row[F] = 1.0;
        row
    }
}

pub struct HeadCorpus {
    /// Rows in corpus order: state 0's options, state 1's options, ...
    pub rows: Vec<[f64; D]>,
    /// y = the oracle's per-option p_clean.
    pub targets: Vec<f64>,
    /// `offsets[s]`..`offsets[s + 1]` is state s's row range.
    pub offsets: Vec<usize>,
}

pub fn build_corpus<R>(
    states: &[(MicroStateFixture, R)],
    feature_row: impl Fn(&MicroOptionFixture) -> [f64; F],
) -> (HeadCorpus, Standardizer) {
    let mut raws: Vec<[f64; F]> = Vec::new();
    let mut targets: Vec<f64> = Vec::new();
    let mut offsets = vec![0usize];
    for (st, _) in states {
        for o in &st.options {
            let p = o.p_clean.unwrap_or_else(|| {
                panic!(
                    "{}: p_clean missing — the corpus needs the oracle's per-option read",
                    st.state_id
                )
            });
            raws.push(feature_row(o));
            targets.push(p);
        }
        offsets.push(raws.len());
    }
    let stdizer = Standardizer::fit(&raws);
    let rows: Vec<[f64; D]> = raws.iter().map(|r| stdizer.design(r)).collect();
    (
        HeadCorpus {
            rows,
            targets,
            offsets,
        },
        stdizer,
    )
}

// ── λ selection + the LOO reading ────────────────────────────────────────

pub struct LamRow {
    pub lam: f64,
    pub mse: f64,
    pub agree: usize,
}

/// Leave ONE STATE out: fit on the other states' options, predict the
/// held-out state's options, argmax = that state's LOO decision. Sibling
/// options never leak. MSE selects λ; agreement is REPORTED at the chosen
/// λ (selection never sees the agreement number). Returns
/// (chosen λ, LOO picks at the chosen λ, per-λ rows for printing).
pub fn loo_select(
    fitter: &mut HeadFitter<D>,
    corpus: &HeadCorpus,
    argmaxes: &[usize],
) -> (f64, Vec<usize>, Vec<LamRow>) {
    let n_states = argmaxes.len();
    let mut chosen = RIDGE_GRID[0];
    let mut chosen_mse = f64::INFINITY;
    let mut chosen_picks = vec![0usize; n_states];
    let mut rows = Vec::with_capacity(RIDGE_GRID.len());
    for &lam in &RIDGE_GRID {
        let mut sq = 0.0f64;
        let mut agree = 0usize;
        let mut picks = vec![0usize; n_states];
        for s in 0..n_states {
            let (a, b) = (corpus.offsets[s], corpus.offsets[s + 1]);
            let mut train: Vec<[f64; D]> = Vec::with_capacity(corpus.rows.len() - (b - a));
            train.extend_from_slice(&corpus.rows[..a]);
            train.extend_from_slice(&corpus.rows[b..]);
            let mut ty: Vec<f64> = Vec::with_capacity(corpus.targets.len() - (b - a));
            ty.extend_from_slice(&corpus.targets[..a]);
            ty.extend_from_slice(&corpus.targets[b..]);
            let head = fitter.fit_into(&train, &ty, lam);
            let mut best_pred = f64::NEG_INFINITY;
            let mut bi = 0usize;
            for (j, row) in corpus.rows[a..b].iter().enumerate() {
                let p = head.score(row);
                let e = p - corpus.targets[a + j];
                sq += e * e;
                if p > best_pred {
                    best_pred = p;
                    bi = j;
                }
            }
            picks[s] = bi;
            if bi == argmaxes[s] {
                agree += 1;
            }
        }
        let mse = sq / corpus.targets.len() as f64;
        rows.push(LamRow { lam, mse, agree });
        if mse < chosen_mse {
            chosen_mse = mse;
            chosen = lam;
            chosen_picks = picks;
        }
    }
    (chosen, chosen_picks, rows)
}

/// BLAKE3 over the head weights (f64 LE) — the determinism anchor.
pub fn head_digest(h: &FittedHead<D>) -> blake3::Hash {
    let mut bytes = Vec::with_capacity(D * 8);
    for w in h.weights() {
        bytes.extend_from_slice(&w.to_le_bytes());
    }
    blake3::hash(&bytes)
}
