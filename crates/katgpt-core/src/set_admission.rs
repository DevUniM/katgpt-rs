//! Counter-anchored set admission — the modelless fan-out gate (Plan 599,
//! Research 564, arXiv:2603.06397 "R4T" reward distillation).
//!
//! Greedy set admission over a candidate pool scoring
//!
//! ```text
//! score(x) = g(x) + α·cos(x, q₀) + κ·log(1 + x̂ᵀM⁻¹x̂)
//! ```
//!
//! where `g` is the caller's modular quality prior, `α·cos` anchors the set
//! to the query, and `κ·log(1 + x̂ᵀM⁻¹x̂)` is the exact marginal log-det gain
//! `log|I + G + xx̂ᵀ| − log|I + G|` of the admitted dual Gram `G = X̂ᵀX̂`
//! (`M ≡ I + G`, `M⁻¹` maintained by Sherman–Morrison rank-1 updates —
//! O(d²) per admission, never a matrix inverse). Candidates colinear with
//! an admitted member (`cos > θ_coll`, the `ColinearityBatchGate` 0.95
//! precedent) are rejected outright.
//!
//! Post-hoc, an **exact** cosine-kernel Vendi certificate runs on the dual
//! Gram's eigenvalues — the K×K and d×d Grams share nonzero spectra
//! (eigenduality), so the pinned
//! [`crate::spectral_pencil::jacobi_eigen`] kernel diagonalizes the
//! maintained d×d `G` and [`crate::certified_frontier::vendi_diversity`]
//! reads the score. The incremental participation ratio `(tr G)²/tr(G²)` is
//! the eigensolve-free fast path maintained during admission.
//!
//! # The three anchors and their failure families (the T0.2 spec)
//!
//! Each anchor holds one degenerate family shut; zeroing it re-opens that
//! family (the L2 property), and a modular-only objective over a
//! duplicate-tolerant pool admits an effective-rank-1 set (L1):
//!
//! | Weight zeroed | Family reachable | Mechanism |
//! |---|---|---|
//! | `kappa_div = 0` | **paraphrase-collapse** (selection) | no log-det gain → near-duplicates win on `g` alone |
//! | `alpha_align = 0` | **semantic-drift** (selection) | no query pull → the highest-`g` cluster wins wherever it lives |
//! | `rho_vendi = 0` | **coordinate-gaming** (detection) | the certificate floor drops to 0 → a spectrally rank-1 set that passes every pairwise colinearity check is never flagged `collapsed` |
//!
//! The first two families are SELECTION failures (who gets admitted); the
//! third is a DETECTION failure (the report misses a degenerate set) —
//! `rho_vendi` weights the certificate floor, never the greedy, so
//! admission is ρ-invariant by construction. The certificate is the honesty
//! instrument, not a per-candidate reward (R4T's RL-trained certificate
//! head, replaced by an exact closed form; the optional Phase-2 exp-tilt
//! arm is the RL-fixed-point replacement — measured there, not assumed
//! here). With all three weights at defaults the full triple excludes all
//! three interiors at the spec worlds (the `l1_*` / `l2_*` tests).
//!
//! # Boundaries
//!
//! - **Kernel fixed = cosine** (T0.1): eigenduality + exact Vendi require a
//!   linear/cosine kernel; an RBF kernel would need Nyström approximation
//!   and loses exactness — out of scope.
//! - **d = 8 ceiling** ([`DIM`]): Vendi ≤ min(K, d) — the depth ceiling is
//!   reported as [`CertificateReport::saturated`], never hidden.
//! - Zero-alloc on the hot path: all linear algebra runs in caller-owned
//!   fixed arrays; the two reusable lists inside [`AdmissionScratch`]
//!   reserve once (warmup) and are reused across cycles.
//! - Deterministic: pinned single-pass argmax, lowest-index tie-break;
//!   same pool + config → identical indices, bytes included.
//! - Opt-in: feature `set_admission = ["certified_frontier",
//!   "spectral_pencil"]` — consumes both substrates, forks neither.

use crate::certified_frontier::vendi_diversity;
use crate::spectral_pencil::dense::jacobi_eigen;

/// Latent dimension of the admission space (the plan's d = 8 working
/// ceiling; Vendi and PR saturate at `min(K, DIM)`).
pub const DIM: usize = 8;

/// Saturation bar for [`CertificateReport::saturated`] (the honesty field):
/// the certificate says "at the depth ceiling" this close to `min(K, DIM)`.
pub const SATURATION_FRACTION: f32 = 0.95;

/// Configuration for the counter-anchored admission gate.
///
/// Defaults are R4T's reward proportions (0.6 / 0.2 / 0.2) as the starting
/// sweep point for α/κ — a prior, not a claim (the plan's wording); the
/// colinearity cap takes the `ColinearityBatchGate` 0.95 precedent.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct SetAdmissionConfig {
    /// Query-alignment anchor weight (α). Zero re-opens semantic-drift (L2).
    pub alpha_align: f32,
    /// Diversity (log-det) anchor weight (κ). Zero re-opens
    /// paraphrase-collapse (L2).
    pub kappa_div: f32,
    /// Colinearity cap (θ_coll): candidates with `cos(x̂, admitted) > θ` are
    /// rejected outright.
    pub theta_coll: f32,
    /// Certificate floor fraction (ρ): the report flags
    /// `collapsed = vendi < ρ·min(K, DIM)`. Zero disables the flag entirely —
    /// coordinate-gaming becomes undetectable (L2). Admission is ρ-invariant.
    pub rho_vendi: f32,
}

impl Default for SetAdmissionConfig {
    fn default() -> Self {
        Self {
            alpha_align: 0.6,
            kappa_div: 0.2,
            theta_coll: 0.95,
            rho_vendi: 0.2,
        }
    }
}

/// Post-admission certificate report (the honesty instrument).
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct CertificateReport {
    /// Exact cosine-kernel Vendi score of the admitted set:
    /// `exp(−Σ pᵢ ln pᵢ)` over the dual Gram's positive normalized
    /// eigenvalues. Upper bound `min(K, DIM)`.
    pub vendi: f32,
    /// Incremental participation ratio `(tr G)²/tr(G²)` maintained during
    /// admission (the between-certifications fast path — no eigensolve).
    pub participation_ratio: f32,
    /// `vendi ≥ SATURATION_FRACTION·min(K, DIM)` — the depth ceiling
    /// reached; the d = 8 saturation is a first-class output, never silent.
    pub saturated: bool,
    /// `vendi < ρ·min(K, DIM)` — the set is rank-collapsed against the
    /// certificate floor. Always `false` when ρ = 0 (the L2-ρ hole).
    pub collapsed: bool,
}

/// Caller-owned scratch for [`admit_into`] / [`certify_scratch`]: fixed
/// linear algebra, reusable lists that keep their allocations across
/// cycles.
#[derive(Clone)]
pub struct AdmissionScratch {
    /// Dual Gram `G = X̂ᵀX̂` of the admitted set (row-major).
    pub gram: [[f32; DIM]; DIM],
    /// `M⁻¹ = (I + G)⁻¹`, maintained by Sherman–Morrison rank-1 updates
    /// (the admitted Gram alone can be singular; `I + G` never is).
    pub minv: [[f32; DIM]; DIM],
    /// Normalized admitted latents (the colinearity cap's members).
    pub admitted: Vec<[f32; DIM]>,
    /// Normalized pool (cleared and refilled per cycle — the allocation
    /// persists).
    pub pool_hats: Vec<Option<[f32; DIM]>>,
    /// Running trace of `G`.
    pub tr_g: f32,
    /// Running trace of `G²`.
    pub tr_g2: f32,
}

impl Default for AdmissionScratch {
    fn default() -> Self {
        Self::new()
    }
}

impl AdmissionScratch {
    /// Fresh scratch: `G = 0`, `M⁻¹ = I`.
    #[must_use]
    pub fn new() -> Self {
        Self {
            gram: [[0.0; DIM]; DIM],
            minv: identity(),
            admitted: Vec::new(),
            pool_hats: Vec::new(),
            tr_g: 0.0,
            tr_g2: 0.0,
        }
    }

    /// Reset for a fresh cycle (keeps every allocation).
    pub fn clear(&mut self) {
        self.gram = [[0.0; DIM]; DIM];
        self.minv = identity();
        self.admitted.clear();
        self.pool_hats.clear();
        self.tr_g = 0.0;
        self.tr_g2 = 0.0;
    }
}

#[inline]
fn identity() -> [[f32; DIM]; DIM] {
    let mut m = [[0.0_f32; DIM]; DIM];
    for (i, row) in m.iter_mut().enumerate() {
        row[i] = 1.0;
    }
    m
}

/// Normalize a latent onto the cosine kernel's unit shell.
/// `None` for zero/non-finite vectors (rejected, never NaN).
#[inline]
fn normalize(x: &[f32; DIM]) -> Option<[f32; DIM]> {
    if x.iter().any(|v| !v.is_finite()) {
        return None;
    }
    let n = x.iter().map(|v| v * v).sum::<f32>().sqrt();
    if !n.is_finite() || n < 1e-12 {
        return None;
    }
    let mut out = [0.0_f32; DIM];
    for (o, v) in out.iter_mut().zip(x) {
        *o = v / n;
    }
    Some(out)
}

#[inline]
fn dot(a: &[f32; DIM], b: &[f32; DIM]) -> f32 {
    a.iter().zip(b).map(|(u, v)| u * v).sum()
}

/// One Sherman–Morrison rank-1 update of `M⁻¹` in place:
/// `M⁻¹ ← M⁻¹ − (M⁻¹x)(M⁻¹x)ᵀ / (1 + xᵀM⁻¹x)`.
fn sherman_morrison_rank1(minv: &mut [[f32; DIM]; DIM], x: &[f32; DIM]) {
    let mut mx = [0.0_f32; DIM];
    for (row, mrow) in mx.iter_mut().zip(minv.iter()) {
        *row = dot(mrow, x);
    }
    let denom = 1.0 + dot(x, &mx);
    if !denom.is_finite() || denom.abs() < 1e-12 {
        return; // numerically degenerate update — keep the prior inverse
    }
    for (mrow, &mxi) in minv.iter_mut().zip(&mx) {
        for (mij, &mxj) in mrow.iter_mut().zip(&mx) {
            *mij -= mxi * mxj / denom;
        }
    }
}

/// Admit one unit latent into the scratch: rank-1 Gram update, PR traces,
/// Sherman–Morrison, member list.
fn admit_latent(scratch: &mut AdmissionScratch, x: &[f32; DIM]) {
    // xᵀGx on the PRIOR Gram — the tr(G²) update needs the old product.
    let mut gx = [0.0_f32; DIM];
    for (gxi, row) in gx.iter_mut().zip(scratch.gram.iter()) {
        *gxi = dot(row, x);
    }
    let xgx = dot(&gx, x);

    // G ← G + xxᵀ.
    for i in 0..DIM {
        for j in 0..DIM {
            scratch.gram[i][j] += x[i] * x[j];
        }
    }
    // tr(G) += ‖x̂‖² = 1 on the unit shell;
    // tr(G²) += 2·xᵀGx + (xᵀx)² = 2·xᵀGx + 1.
    scratch.tr_g += 1.0;
    scratch.tr_g2 += 2.0 * xgx + 1.0;

    sherman_morrison_rank1(&mut scratch.minv, x);
    scratch.admitted.push(*x);
}

/// Greedy counter-anchored admission over one pool.
///
/// Writes admitted pool indices into `out_indices` (the caller sizes it =
/// the target set size K; slots beyond the returned count carry the
/// `u16::MAX` sentinel) and returns the admitted count. `quality[g]` is the
/// modular prior for `pool[g]`; `query` is the anchor `q₀` (a non-normalizable
/// query zeroes the alignment term for every candidate). `scratch` is
/// cleared internally — one call = one fresh cycle.
///
/// # Panics
/// Panics if `pool.len() != quality.len()` or `pool.len() > u16::MAX`
/// (the index encoding).
pub fn admit_into(
    cfg: &SetAdmissionConfig,
    pool: &[[f32; DIM]],
    quality: &[f32],
    query: &[f32; DIM],
    out_indices: &mut [u16],
    scratch: &mut AdmissionScratch,
) -> usize {
    assert_eq!(pool.len(), quality.len(), "pool/quality length mismatch");
    assert!(
        pool.len() <= u16::MAX as usize,
        "pool exceeds the u16 index encoding"
    );
    scratch.clear();
    let k_target = out_indices.len();
    for slot in out_indices.iter_mut() {
        *slot = u16::MAX;
    }
    scratch.admitted.reserve(k_target);
    scratch.pool_hats.reserve(pool.len());
    if k_target == 0 || pool.is_empty() {
        return 0;
    }
    let q_hat = normalize(query);
    for x in pool {
        scratch.pool_hats.push(normalize(x));
    }

    for _ in 0..k_target {
        let mut best: Option<(f32, usize)> = None;
        for (idx, hat) in scratch.pool_hats.iter().enumerate() {
            let Some(x) = hat else { continue };
            // Colinearity cap against every admitted member.
            let mut colinear = false;
            for a in &scratch.admitted {
                if dot(x, a) > cfg.theta_coll {
                    colinear = true;
                    break;
                }
            }
            if colinear {
                continue;
            }
            // Exact marginal log-det gain: log(1 + x̂ᵀM⁻¹x̂).
            let mut mx = [0.0_f32; DIM];
            for (row, mrow) in mx.iter_mut().zip(scratch.minv.iter()) {
                *row = dot(mrow, x);
            }
            let logdet_gain = (1.0 + dot(x, &mx)).ln();
            let align = q_hat.map_or(0.0, |q| dot(x, &q));
            let score = quality[idx] + cfg.alpha_align * align + cfg.kappa_div * logdet_gain;
            if score.is_finite() && best.is_none_or(|(bs, _)| score > bs) {
                best = Some((score, idx));
            }
        }
        let Some((_, idx)) = best else { break };
        let x = scratch.pool_hats[idx].expect("best index came from a normalized row");
        admit_latent(scratch, &x);
        out_indices[scratch.admitted.len() - 1] = idx as u16;
    }
    scratch.admitted.len()
}

/// The exact certificate over the scratch's current admitted set:
/// dual-Gram eigenvalues through the pinned Jacobi, Vendi over them, the
/// maintained participation ratio, and the collapse / saturation flags
/// against `min(K, DIM)` (K = the admitted count).
pub fn certify_scratch(cfg: &SetAdmissionConfig, scratch: &AdmissionScratch) -> CertificateReport {
    let k = scratch.admitted.len();
    if k == 0 {
        return CertificateReport {
            vendi: 0.0,
            participation_ratio: 0.0,
            saturated: false,
            collapsed: false,
        };
    }
    let cap = k.min(DIM) as f32;
    let participation_ratio = if scratch.tr_g2 > 0.0 {
        scratch.tr_g * scratch.tr_g / scratch.tr_g2
    } else {
        0.0
    };
    let mut dense = crate::spectral_pencil::dense::DenseScratch::<DIM>::new();
    let _ = jacobi_eigen(&scratch.gram, false, &mut dense);
    let vendi = vendi_diversity(&dense.values);
    CertificateReport {
        vendi,
        participation_ratio,
        saturated: vendi >= SATURATION_FRACTION * cap,
        collapsed: vendi < cfg.rho_vendi * cap,
    }
}

/// Certificate for a caller-held set (no greedy pass) — the detection
/// surface consumers and audits use on already-delivered sets.
pub fn certify_set(cfg: &SetAdmissionConfig, set: &[[f32; DIM]]) -> CertificateReport {
    let mut scratch = AdmissionScratch::new();
    scratch.admitted.reserve(set.len());
    for x in set {
        if let Some(hat) = normalize(x) {
            admit_latent(&mut scratch, &hat);
        }
    }
    certify_scratch(cfg, &scratch)
}

#[cfg(test)]
mod tests {
    use super::*;
    use fastrand::Rng;

    fn unit(x: [f32; DIM]) -> [f32; DIM] {
        normalize(&x).expect("test vector is normalizable")
    }

    fn cfg_with(alpha: f32, kappa: f32, rho: f32) -> SetAdmissionConfig {
        SetAdmissionConfig {
            alpha_align: alpha,
            kappa_div: kappa,
            theta_coll: 0.95,
            rho_vendi: rho,
        }
    }

    /// The paraphrase/gaming family: `normalize(e0 + wobble·s_j·e_j)` —
    /// pairwise cosines strictly under the 0.95 cap (0.9412 at wobble 0.25,
    /// 0.8796 at 0.37) but spectrally one dominant direction. Yields exactly
    /// `k` distinct members, alternating coordinate and sign
    /// (k ≤ DIM is the caller's contract — indices stay in-bounds).
    fn wobble_set(wobble: f32, k: usize) -> Vec<[f32; DIM]> {
        assert!(k <= DIM, "the family has one member per (coord, sign) slot");
        let mut set = Vec::with_capacity(k);
        let mut j = 1_usize;
        while set.len() < k {
            let sign = if set.len() % 2 == 0 { 1.0 } else { -1.0 };
            let mut x = [0.0_f32; DIM];
            x[0] = 1.0;
            x[j] = wobble * sign;
            set.push(unit(x));
            j += 1;
            if j == DIM {
                j = 1;
            }
        }
        set
    }

    // ── T1.5 known answers ──────────────────────────────────────────

    #[test]
    fn identical_set_has_vendi_and_pr_one() {
        // K = 6 identical members: spectrum = one nonzero eigenvalue →
        // vendi = 1 exactly; PR = K²/K² = 1. Floor 0.2·6 = 1.2 > 1 → the
        // certificate flags the collapse.
        let set: Vec<[f32; DIM]> = vec![unit([1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]); 6];
        let r = certify_set(&SetAdmissionConfig::default(), &set);
        assert!((r.vendi - 1.0).abs() < 1e-4, "vendi {}", r.vendi);
        assert!((r.participation_ratio - 1.0).abs() < 1e-4, "pr {}", r.participation_ratio);
        assert!(r.collapsed, "identical set must flag collapsed");
        assert!(!r.saturated);
    }

    #[test]
    fn orthonormal_set_saturates_at_min_k_d() {
        // K = 5 orthonormal members in d = 8: vendi = PR = min(K, d) = 5.
        let mut set = Vec::new();
        for j in 0..5 {
            let mut x = [0.0_f32; DIM];
            x[j] = 1.0;
            set.push(x);
        }
        let r = certify_set(&SetAdmissionConfig::default(), &set);
        assert!((r.vendi - 5.0).abs() < 0.01, "vendi {}", r.vendi);
        assert!((r.participation_ratio - 5.0).abs() < 0.01, "pr {}", r.participation_ratio);
        assert!(r.saturated, "5 orthogonal members at the d=8... min(5,8)=5: vendi ≥ 0.95·5");
        assert!(!r.collapsed);

        // K = 8 = DIM: full depth ceiling reached.
        let mut set = Vec::new();
        for j in 0..DIM {
            let mut x = [0.0_f32; DIM];
            x[j] = 1.0;
            set.push(x);
        }
        let r = certify_set(&SetAdmissionConfig::default(), &set);
        assert!((r.vendi - 8.0).abs() < 0.01, "vendi {}", r.vendi);
        assert!(r.saturated, "K = DIM orthonormal must saturate");
    }

    #[test]
    fn pr_and_vendi_rank_correlate_over_random_sets() {
        // T1.5's empirical pin: two different functionals that agree on the
        // ORDERING of diversity (Spearman ≥ 0.95 over 10⁴ seeded sets).
        let mut rng = Rng::with_seed(0x5E7_AD_001);
        let trials = 10_000_usize;
        let mut prs = Vec::with_capacity(trials);
        let mut vendis = Vec::with_capacity(trials);
        for _ in 0..trials {
            let k = 2 + rng.usize(..7); // 2..=8 members
            let mut set = Vec::with_capacity(k);
            for _ in 0..k {
                let mut x = [0.0_f32; DIM];
                for v in x.iter_mut() {
                    *v = rng.f32() * 2.0 - 1.0;
                }
                set.push(x); // certify_set normalizes internally
            }
            let r = certify_set(&SetAdmissionConfig::default(), &set);
            prs.push(r.participation_ratio);
            vendis.push(r.vendi);
        }
        let rho = spearman(&prs, &vendis);
        println!("[t15] spearman(pr, vendi) over {trials} random sets: {rho:.4}");
        assert!(rho >= 0.95, "rank correlation {rho} < 0.95");
    }

    /// Spearman rank correlation (distinct ranks — ties are measure-zero
    /// on the continuous random sets above).
    fn spearman(a: &[f32], b: &[f32]) -> f64 {
        let ra = ranks(a);
        let rb = ranks(b);
        let n = a.len() as f64;
        let (ma, mb) = (
            ra.iter().sum::<f64>() / n,
            rb.iter().sum::<f64>() / n,
        );
        let (mut cov, mut va, mut vb) = (0.0, 0.0, 0.0);
        for i in 0..a.len() {
            let da = ra[i] - ma;
            let db = rb[i] - mb;
            cov += da * db;
            va += da * da;
            vb += db * db;
        }
        cov / (va.sqrt() * vb.sqrt())
    }

    fn ranks(v: &[f32]) -> Vec<f64> {
        let mut idx: Vec<usize> = (0..v.len()).collect();
        idx.sort_by(|&i, &j| v[i].partial_cmp(&v[j]).expect("no NaN in test data"));
        let mut out = vec![0.0_f64; v.len()];
        for (rank, &i) in idx.iter().enumerate() {
            out[i] = rank as f64;
        }
        out
    }

    // ── L1: the modular-only disease ────────────────────────────────

    /// 14 duplicate-tolerant members (pairwise cos 0.8796 < 0.95) — the
    /// L1/L2-κ paraphrase family: `normalize(e0 ± 0.37·e_j)`, j = 1..8.
    fn dup_pool() -> Vec<[f32; DIM]> {
        let mut pool = Vec::new();
        for j in 1..DIM {
            for sign in [1.0_f32, -1.0] {
                let mut x = [0.0_f32; DIM];
                x[0] = 1.0;
                x[j] = 0.37 * sign;
                pool.push(unit(x));
            }
        }
        pool
    }

    /// 10 diverse fillers over the e1..e7 complement: `normalize(e_j + 0.5·e_k)`
    /// on distinct pairs — pairwise cosines ≤ 0.45, nothing colinear.
    fn filler_pool() -> Vec<[f32; DIM]> {
        let pairs = [(1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7), (1, 3), (2, 4), (3, 5), (4, 6)];
        pairs
            .iter()
            .map(|&(a, b)| {
                let mut x = [0.0_f32; DIM];
                x[a] = 1.0;
                x[b] = 0.5;
                unit(x)
            })
            .collect()
    }

    fn n_slots(out: &[u16]) -> usize {
        out.iter().take_while(|&&i| i != u16::MAX).count()
    }

    /// Mean pairwise cosine of the admitted members (the duplication
    /// metric — the paraphrase family's own instrument).
    fn mean_pairwise_cos(pool: &[[f32; DIM]], out: &[u16]) -> f32 {
        let slots = n_slots(out);
        let members: Vec<[f32; DIM]> = out[..slots]
            .iter()
            .map(|&i| normalize(&pool[i as usize]).expect("pool row"))
            .collect();
        let mut total = 0.0_f32;
        let mut pairs = 0_usize;
        for (i, a) in members.iter().enumerate() {
            for b in &members[i + 1..] {
                total += dot(a, b);
                pairs += 1;
            }
        }
        if pairs == 0 { 0.0 } else { total / pairs as f32 }
    }

    #[test]
    fn l1_modular_only_admits_effective_rank_one_set() {
        let mut pool = dup_pool();
        pool.extend(filler_pool());
        let quality: Vec<f32> = pool
            .iter()
            .enumerate()
            .map(|(i, _)| if i < 14 { 1.0 } else { 0.97 })
            .collect();
        let query = unit([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]);

        // Modular-only (α = κ = 0): the 0.03 g-gap admits duplicates in
        // every slot — an effective-rank-1 set.
        let mut scratch = AdmissionScratch::new();
        let mut out = [0_u16; 8];
        let n = admit_into(
            &cfg_with(0.0, 0.0, 0.2),
            &pool,
            &quality,
            &query,
            &mut out,
            &mut scratch,
        );
        assert_eq!(n, 8, "the cap never fires on pairwise-0.88 dups");
        let r = certify_scratch(&cfg_with(0.0, 0.0, 0.2), &scratch);
        let mp = mean_pairwise_cos(&pool, &out);
        println!(
            "[L1] modular-only: vendi={:.3} pr={:.3} mean-pairwise-cos={:.3}",
            r.vendi, r.participation_ratio, mp
        );
        // The L1 claim is EFFECTIVE RANK: the participation ratio (the
        // set's own rank functional) must read ≈ 1, and the admitted
        // members must be near-duplicates. The vendi floor flag belongs to
        // the ρ family (L2-ρ) and is deliberately not asserted here.
        assert!(
            r.participation_ratio < 1.5,
            "pr {} — the set must be effectively rank-1",
            r.participation_ratio
        );
        assert!(mp >= 0.85, "mean pairwise cos {mp:.3} — admitted members must be near-duplicates");
    }

    // ── L2-κ: paraphrase-collapse is a selection failure ─────────────

    #[test]
    fn l2_paraphrase_collapse_reachable_only_when_kappa_zero() {
        // The world: the paraphrase family wobbles around e0 (g = 1.0);
        // the filler family spreads over the three OTHER even axes (e2,
        // e4, e6 — mutually orthogonal bases, g = 0.99). The query sits at
        // normalize(e0+e2+e4+e6) so EVERY member reads the exact same
        // cos-to-query (0.5/1.0668 = 0.4688) — the α anchor cancels out of
        // the comparison and κ alone decides. Fillers stay genuinely fresh
        // (orthogonal bases ⇒ near-zero mutual overlap), so κ's log-det
        // correction keeps winning for as long as fresh fillers exist.
        let q0 = unit([1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0]);
        let mut pool = Vec::new();
        // Paraphrase dups: base e0, wobble on the odd axes, g = 1.0.
        for j in [1_usize, 3, 5, 7] {
            for sign in [1.0_f32, -1.0] {
                let mut x = [0.0_f32; DIM];
                x[0] = 1.0;
                x[j] = 0.37 * sign;
                pool.push(unit(x));
            }
        }
        let dup_len = pool.len(); // 8
        // Diverse fillers: orthogonal even bases, same wobble shape, g = 0.99.
        for base in [2_usize, 4, 6] {
            for j in [1_usize, 3, 5, 7] {
                for sign in [1.0_f32, -1.0] {
                    let mut x = [0.0_f32; DIM];
                    x[base] = 1.0;
                    x[j] = 0.37 * sign;
                    pool.push(unit(x));
                }
            }
        }
        let quality: Vec<f32> = pool
            .iter()
            .enumerate()
            .map(|(i, _)| if i < dup_len { 1.0 } else { 0.99 })
            .collect();
        let k = 6_usize;
        let dup_count = |out: &[u16]| -> usize {
            out[..n_slots(out)]
                .iter()
                .filter(|&&i| (i as usize) < dup_len)
                .count()
        };

        // κ = 0: collapse reachable — the 0.01 g-gap admits the whole
        // duplicate family.
        let mut scratch = AdmissionScratch::new();
        let mut out = [0_u16; 6];
        admit_into(&cfg_with(0.6, 0.0, 0.2), &pool, &quality, &q0, &mut out, &mut scratch);
        let d0 = dup_count(&out);
        let mp0 = mean_pairwise_cos(&pool, &out);
        println!("[L2k] kappa=0: dups={d0}/{k} mean-pairwise-cos={mp0:.3}");
        assert!(d0 >= k - 1, "kappa=0 must fill the set with near-duplicates");
        assert!(mp0 >= 0.8, "kappa=0 admitted set must be duplicated (mean pairwise cos {mp0:.3})");

        // Defaults: κ = 0.2's fresh-direction log-det gain (≈ 0.2·0.22 ≈
        // 0.045) dominates the 0.01 g-gap, and the orthogonal filler bases
        // keep the gain fresh — fillers win nearly every slot; the full
        // triple excludes the family.
        let mut scratch = AdmissionScratch::new();
        let mut out = [0_u16; 6];
        admit_into(&SetAdmissionConfig::default(), &pool, &quality, &q0, &mut out, &mut scratch);
        let r = certify_scratch(&SetAdmissionConfig::default(), &scratch);
        let d = dup_count(&out);
        println!("[L2k] defaults: dups={d}/{k} vendi={:.3}", r.vendi);
        assert!(d <= 2, "defaults must not paraphrase-collapse (dup_count {d})");
        assert!(r.vendi >= 2.5, "default set must be spectrally diverse (vendi {:.3})", r.vendi);
    }

    // ── L2-α: semantic-drift is a selection failure ──────────────────

    /// Far cluster (cos-to-query ≈ 0.18, high g) vs near cluster
    /// (cos-to-query ≈ 0.94, lower g), both internally cap-safe.
    fn drift_world() -> (Vec<[f32; DIM]>, Vec<f32>, [f32; DIM]) {
        let mut pool = Vec::new();
        let q0 = [1.0_f32, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];
        // Near cluster: normalize(e0 ± 0.375·e_j), j = 1..8 — cos to q0 ≈ 0.936.
        for j in 1..DIM {
            for sign in [1.0_f32, -1.0] {
                let mut x = [0.0_f32; DIM];
                x[0] = 1.0;
                x[j] = 0.375 * sign;
                pool.push(unit(x));
            }
        }
        let near_len = pool.len(); // 14
        // Far cluster: normalize(0.2·e0 + 1.0·e3 ± 0.5·e_j), j ∈ {4,5,6} —
        // cos to q0 ≈ 0.18.
        for j in [4_usize, 5, 6] {
            for sign in [1.0_f32, -1.0] {
                let mut x = [0.0_f32; DIM];
                x[0] = 0.2;
                x[3] = 1.0;
                x[j] = 0.5 * sign;
                pool.push(unit(x));
            }
        }
        // Near g = 0.9 (indices < 14), far g = 1.0.
        let quality: Vec<f32> = pool
            .iter()
            .enumerate()
            .map(|(i, _)| if i < near_len { 0.9 } else { 1.0 })
            .collect();
        (pool, quality, q0)
    }

    #[test]
    fn l2_semantic_drift_reachable_only_when_alpha_zero() {
        let (pool, quality, query) = drift_world();
        let near_len = 14_usize;
        let k = 6_usize;
        let q = normalize(&query).expect("q0");
        let mean_cos = |out: &[u16]| -> f32 {
            let slots = n_slots(out);
            out[..slots]
                .iter()
                .map(|&i| dot(&normalize(&pool[i as usize]).expect("pool"), &q))
                .sum::<f32>()
                / slots as f32
        };

        // α = 0: the far cluster wins on g — the set drifts off-query.
        let mut scratch = AdmissionScratch::new();
        let mut out = [0_u16; 6];
        admit_into(&cfg_with(0.0, 0.2, 0.2), &pool, &quality, &query, &mut out, &mut scratch);
        let mc0 = mean_cos(&out);
        let far0 = out[..n_slots(&out)].iter().filter(|&&i| (i as usize) >= near_len).count();
        println!("[L2a] alpha=0: mean-cos={mc0:.3} far-members={far0}/{k}");
        assert!(far0 >= k - 1 && mc0 < 0.5, "alpha=0 set must drift off-query");

        // Defaults: the alignment anchor holds the set on-query.
        let mut scratch = AdmissionScratch::new();
        let mut out = [0_u16; 6];
        admit_into(&SetAdmissionConfig::default(), &pool, &quality, &query, &mut out, &mut scratch);
        let mc = mean_cos(&out);
        println!("[L2a] defaults: mean-cos={mc:.3}");
        assert!(mc >= 0.8, "defaults must hold the set on-query (mean cos {mc:.3})");
    }

    // ── L2-ρ: coordinate-gaming is a detection failure ───────────────

    #[test]
    fn l2_coordinate_gaming_reachable_only_when_rho_zero() {
        // The gaming set: 8 members at pairwise cos 0.9412 — it passes
        // EVERY pairwise colinearity screen (< 0.95) but its spectrum is
        // one dominant direction (vendi ≈ 1.36 < the default floor 1.6).
        let gaming = wobble_set(0.25, DIM); // K = 8 members
        let cfg = SetAdmissionConfig::default();

        // Detection distinctness: the set really does pass the cap.
        let mut max_pair = 0.0_f32;
        for (i, a) in gaming.iter().enumerate() {
            for b in &gaming[i + 1..] {
                max_pair = max_pair.max(dot(a, b));
            }
        }
        println!("[L2r] gaming set: max pairwise cos={max_pair:.4} (< 0.95 cap)");
        assert!(max_pair < cfg.theta_coll, "the world must pass pairwise screens");

        let flagged = certify_set(&cfg, &gaming);
        println!("[L2r] defaults: vendi={:.3} collapsed={}", flagged.vendi, flagged.collapsed);
        assert!(flagged.collapsed, "defaults must flag the spectrally-degenerate set");

        // ρ = 0: the hole — same set, same spectrum, never flagged.
        let blind = certify_set(&cfg_with(0.6, 0.2, 0.0), &gaming);
        assert!(!blind.collapsed, "rho=0 must leave the gaming set unflagged");
        assert!(
            (blind.vendi - flagged.vendi).abs() < 1e-6,
            "the certificate is rho-invariant"
        );
    }

    // ── Cap, determinism, robustness ────────────────────────────────

    #[test]
    fn colinearity_cap_rejects_exact_duplicates() {
        let mut pool = vec![unit([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]); 6];
        pool.push(unit([0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]));
        let quality = vec![1.0_f32; pool.len()];
        let query = unit([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]);
        let mut scratch = AdmissionScratch::new();
        let mut out = [0_u16; 4];
        let n = admit_into(
            &SetAdmissionConfig::default(),
            &pool,
            &quality,
            &query,
            &mut out,
            &mut scratch,
        );
        assert_eq!(n, 2, "cap admits one duplicate + the orthogonal axis, got {n}");
    }

    #[test]
    fn admission_is_deterministic_and_rho_invariant() {
        let mut rng = Rng::with_seed(0xA0_AD_00_01_u64);
        let mut pool = Vec::new();
        for _ in 0..64 {
            let mut x = [0.0_f32; DIM];
            for v in x.iter_mut() {
                *v = rng.f32() * 2.0 - 1.0;
            }
            pool.push(x);
        }
        let quality: Vec<f32> = (0..pool.len()).map(|i| 1.0 - 0.3 * (i % 5) as f32 / 4.0).collect();
        let query = unit([1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]);

        let run = |rho: f32| {
            let mut scratch = AdmissionScratch::new();
            let mut out = [0_u16; 8];
            admit_into(&cfg_with(0.6, 0.2, rho), &pool, &quality, &query, &mut out, &mut scratch);
            out
        };
        let a = run(0.2);
        let b = run(0.2);
        let c = run(0.0); // rho only weights the report — the greedy is invariant
        assert_eq!(a, b, "same pool + config must admit identically");
        assert_eq!(a, c, "rho must not change the admission (rho-invariance)");
    }

    #[test]
    fn non_normalizable_rows_are_skipped() {
        let pool = vec![
            [0.0_f32; DIM],                                // zero vector
            unit([1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]), // good
        ];
        let quality = vec![1.0_f32, 0.5];
        let query = unit([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]);
        let mut scratch = AdmissionScratch::new();
        let mut out = [0_u16; 2];
        let n = admit_into(
            &SetAdmissionConfig::default(),
            &pool,
            &quality,
            &query,
            &mut out,
            &mut scratch,
        );
        assert_eq!(n, 1, "only the normalizable row admits");
        assert_eq!(out[0], 1, "the admitted index is the good row");

        // A non-finite query zeroes alignment without panicking.
        let bad_query = [f32::NAN; DIM];
        let good = [pool[1]; 1];
        let q2 = vec![1.0_f32];
        let mut out2 = [0_u16; 1];
        let n2 = admit_into(
            &SetAdmissionConfig::default(),
            &good,
            &q2,
            &bad_query,
            &mut out2,
            &mut scratch,
        );
        assert_eq!(n2, 1, "a NaN query must not panic the admission");
    }
}
