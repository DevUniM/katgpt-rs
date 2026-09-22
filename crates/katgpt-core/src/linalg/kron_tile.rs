//! Kronecker-factored tile apply — `(A ⊗ B) · x` as two small GEMMs.
//!
//! Issue 839, distilled from Research 569 (Cactus Needle 3, 2026-09-17), whose
//! FFN replaces each dense `ℝ^{1024×1024}` stage with `Mₛ = Aₛ ⊗ Bₛ` for
//! `A, B ∈ ℝ^{32×32}`: **2,048 parameters and 65,536 MACs per stage** against
//! ~1M and ~1M dense. The tile machinery already ships in
//! `katgpt-kv::kvarn::hadamard` — but only at the *fixed* `A = B = H₃₂` (Walsh–
//! Hadamard). This module is the **arbitrary-factor** version: general `n × n`
//! `A`, `B`, batched over tiles, zero-alloc, with the WHT case kept as a
//! delegating fast path rather than a second transcription of the butterfly.
//!
//! Modelless by construction: `A` and `B` are *inputs*. Nothing here trains
//! them — the WHT-initialised learnable-factor recipe is riir-train's half of
//! Research 569 and is explicitly out of scope (Issue 839 non-goals).
//!
//! # The convention, derived rather than asserted
//!
//! Let `x ∈ ℝ^{n²}` be reshaped **row-major** into `Z ∈ ℝ^{n×n}`, i.e.
//! `Z[i][j] = x[i·n + j]`, and let the Kronecker product be the standard one,
//! `(A ⊗ B)[i·n + j][k·n + l] = A[i][k] · B[j][l]`. Then
//!
//! ```text
//! y[i·n+j] = Σ_{k,l} A[i][k] · B[j][l] · x[k·n+l]
//!          = Σ_k A[i][k] · Σ_l Z[k][l] · B[j][l]
//!          = Σ_k A[i][k] · (Z Bᵀ)[k][j]
//!          = (A · Z · Bᵀ)[i][j]
//! ```
//!
//! so **`(A ⊗ B) · x  ≡  Y = A Z Bᵀ`** with no further transposes. That is the
//! form implemented here, and it is what [`kron_dense_into`] builds a reference
//! for. Research 569 and the Monarch literature write the stage as `vec(Aᵀ Z B)`
//! — the same operation under a *column-major* `vec`; a caller wanting that
//! reading passes the transposed factors. The identity above is pinned by
//! `kron_apply_matches_dense_reference`, not left to the reader.
//!
//! This convention is also the cache-friendly one for row-major storage, which
//! is why it is the one implemented rather than merely the one documented:
//!
//! - **Step 1** `T = A · Z` — accumulated as `n` axpy passes over contiguous
//!   rows (`T[i][·] += A[i][k] · Z[k][·]`). A pure elementwise FMA loop with no
//!   reduction, so LLVM vectorises it on every target.
//! - **Step 2** `Y = T · Bᵀ` — `Y[i][j] = ⟨T[i][·], B[j][·]⟩`, a dot product of
//!   **two contiguous rows**. `Bᵀ` costs nothing: it is what makes step 2 read
//!   `B` row-wise.
//!
//! # Why this transcribes no kernel of its own
//!
//! Step 2's reduction is `katgpt_types::simd::simd_dot_f32`, the crate's
//! shipped ISA-dispatched dot (NEON / AVX2+FMA behind a runtime probe /
//! wasm32-simd128 / scalar), and the WHT arm is
//! `meld::walsh_hadamard_in_place_normalized`. Neither is reimplemented here,
//! and that is a choice rather than an omission: `AGENTS.md` records the
//! measured cost of carrying one hand-written kernel per ISA — 30
//! `unsafe_op_in_unsafe_fn` findings in `dash_attn/channel_aware.rs`, every one
//! in the x86_64 arm, because *"that file carries two transcriptions of one
//! kernel and only `simd_dot_neon` had the `unsafe { }` block"*. The defect
//! class IS the duplication. Delegating leaves this module one reduction path,
//! already covered by `katgpt-types`' own four-arm tests and executed by the
//! x86_64 execution matrix.
//!
//! Step 1 needs no kernel at all: it is `n` axpy passes over contiguous rows
//! (`T[i][·] += A[i][k] · Z[k][·]`), elementwise FMA with no reduction, which
//! LLVM vectorises on every target without help. There is no shipped axpy to
//! delegate to, and writing one would be the transcription this section
//! declines.
//!
//! ⚠ **The delegation is measured right at the widths this exists for, and
//! WRONG at two it supports** (Issue 844, Bench 844). `simd_dot_f32` carries a
//! ~3.3 ns fixed per-call cost, so against a plain single-accumulator loop it
//! measures **1.54× faster at length 32** and **3.13× at 64** — and **0.51×
//! at 8**, i.e. 2× slower, and 0.86× at 16. `n = 32` is Research 569's stage
//! and `n = 64` the other width the recipe names, so step 2 is on the right
//! side of the crossover where it matters; a caller at `n ∈ {8, 16}` is paying
//! for the dispatch instead of amortising it.
//!
//! Deliberately NOT repaired with a length-conditional branch. That would add a
//! second summation order and a second code path for widths nothing in
//! Research 569 uses, against AGENTS.md's own threshold that *"2× is the
//! threshold below which the fast path would not be worth the second code path
//! at all"* — which the 8-wide case only just reaches and the 16-wide case
//! misses. Stated here so a caller choosing a small width chooses it knowing.
//!
//! # Determinism, and what is NOT claimed
//!
//! Fixed inputs give bit-identical outputs run to run on one box. Across
//! **architectures** they do not: `simd_dot_f32` reduces in NEON, AVX2 and
//! scalar orders, which are three different floating-point programs over the
//! same reals, and the WHT butterfly's pairwise tree is a fourth. So the
//! parity and G1 gates assert a measured tolerance rather than bit-equality —
//! the arch-conditional-pin shape `AGENTS.md` records for
//! `t698_t5_kv_mean_gates`. Measured on x86_64 (2026-09-18): fast path vs
//! generic max |Δ| = 4.8e-7 over `n ∈ {8,16,32,64}`, against a 1e-5 pin.
//!
//! # The Needle-3 recipe, and which half of it lives here (Issue 839 T8)
//!
//! Research 569's construction is three stages `Mₛ = Aₛ ⊗ Bₛ`, **fixed random
//! permutations** Π₁/Π₂ between them, four learned diagonals, a bias, and a
//! rank-8 input-conditioned channel gain `c(x) = 1 + softmax(xV)U`. Per layer
//! that is 25.6K parameters against a dense FFN's 4.7M (180×) and ~0.21M
//! MACs/token against 4.7M (22×).
//!
//! What lives here is the **modelless** half and only that:
//!
//! | Needle-3 piece | here |
//! |---|---|
//! | one Kronecker stage `A ⊗ B` | [`kron_apply`] |
//! | the WHT starting point `A = B = H₃₂` | [`wht_apply_tiles`] / [`wht_factor_into`] |
//! | fixed inter-stage permutations Π₁, Π₂ | [`permute_into`] + [`is_permutation`] |
//! | learned diagonals D₁–D₄, bias, rank-8 gain V/U | **not here** — trained parameters |
//! | *"starts as WHT and learns from there"* | **not here** — riir-train |
//!
//! The headline phrase is about **initialisation, not constraint**: `H₁₀₂₄ =
//! H₃₂ ⊗ H₃₂` up to scaling, so `A = B = H₃₂` makes stage 1 an exact WHT at step
//! 0 and every gradient step may move the factors; the only retained constraint
//! is the Kronecker block structure. Gradients reach `Aₛ`, `Bₛ` by the ordinary
//! product rule on the two tile GEMMs — which is *why* this primitive is the
//! useful half to ship modellessly, and equally why the recipe itself cannot
//! be: it needs from-scratch training or a long fine-tune, so it is not
//! retrofittable onto the fixed upstream checkpoints this workspace serves
//! (Research 452 Q3). The rank-8 gain's sigmoid-gated analog is a
//! latent-space idea filed elsewhere, not a gap here.
//!
//! # The tile count is an ARGUMENT, never derived from `x.len()`
//!
//! `katgpt-rs` has an audit for exactly the shortcut this module would
//! otherwise take (`scripts/len_derived_binding_audit.py`): a kernel that
//! computes its shape from a buffer's declared size silently derives the
//! *wrong* shape when the buffer is a capacity-sized or reused scratch slice,
//! and the failure mode is a measured identically-zero result with no panic.
//! So `tiles` is passed in and the contract is `assert!`ed — not
//! `debug_assert!`ed, because a release build is where an over-long buffer
//! actually arrives, and the check is `O(1)` against `O(tiles · n³)` of work.

use katgpt_types::simd::{simd_dot_f32, simd_matvec};

/// Tile widths with a [`wht_apply_tiles`] const-dispatch arm.
///
/// Public because the fast path's applicability is part of its contract: a
/// caller choosing a tile width should be able to see, at compile time, whether
/// the WHT arm exists for it rather than discovering a `false` return at
/// runtime.
pub const WHT_TILE_WIDTHS: [usize; 5] = [8, 16, 32, 64, 128];

/// Caller-owned scratch for the intermediate `T = A · Z`.
///
/// One `n × n` buffer, reused across every tile and every call. Grown only by
/// [`KronScratch::ensure`], which is idempotent — so a steady-state hot path
/// performs zero allocations (G4).
#[derive(Debug, Clone, Default)]
pub struct KronScratch {
    t: Vec<f32>,
}

impl KronScratch {
    /// Scratch sized for `n × n` tiles. Allocates once.
    #[must_use]
    pub fn with_capacity(n: usize) -> Self {
        Self {
            t: vec![0.0; n * n],
        }
    }

    /// Grow to hold an `n × n` tile if needed. Idempotent: a second call at the
    /// same or a smaller `n` allocates nothing, which is what makes the steady
    /// state alloc-free even when the caller cannot hoist the sizing.
    pub fn ensure(&mut self, n: usize) {
        if self.t.len() < n * n {
            self.t.resize(n * n, 0.0);
        }
    }

    /// Current capacity in elements — the width `w` such that `w · w` tiles fit.
    #[must_use]
    pub fn capacity_elems(&self) -> usize {
        self.t.len()
    }
}

/// One tile: `y ← A · z · Bᵀ  ≡  (A ⊗ B) · z`, out of place.
///
/// `a`, `b`, `z`, `y` are all `n × n` row-major with exactly `n · n` elements.
/// `y` may not alias `z` (the borrow checker enforces it); for the in-place
/// form use [`kron_apply`], which is in-place *safely* because step 2 reads
/// only from scratch.
///
/// # Panics
/// If any slice length is not `n · n`, or `scratch` was not [`KronScratch::ensure`]d
/// to `n`. These are contract violations, checked in every profile — see the
/// module doc on why a wrong shape must not be allowed to proceed.
#[inline]
pub fn kron_apply_tile_into(
    a: &[f32],
    b: &[f32],
    n: usize,
    z: &[f32],
    y: &mut [f32],
    scratch: &mut KronScratch,
) {
    assert!(n > 0, "tile width must be non-zero");
    let nn = n * n;
    assert_eq!(a.len(), nn, "A must be n×n");
    assert_eq!(b.len(), nn, "B must be n×n");
    assert_eq!(z.len(), nn, "z must be one n×n tile");
    assert_eq!(y.len(), nn, "y must be one n×n tile");
    assert!(
        scratch.capacity_elems() >= nn,
        "scratch holds {} elems, need {nn} — call KronScratch::ensure({n})",
        scratch.capacity_elems()
    );
    let t = &mut scratch.t[..nn];
    gemm_a_z(a, z, n, t);
    gemm_t_bt(t, b, n, y);
}

/// `tiles` tiles in place: each `n × n` block of `x` becomes `A · Z · Bᵀ`.
///
/// The batched entry point, and the one a hot path should call: `A`, `B` and the
/// scratch stay resident while `x` streams past.
///
/// # Panics
/// If `a`/`b` are not `n · n` long, or `x.len() != tiles · n · n`, or `scratch`
/// is too small. The length contract is asserted rather than derived — see the
/// module doc.
pub fn kron_apply(
    a: &[f32],
    b: &[f32],
    n: usize,
    tiles: usize,
    x: &mut [f32],
    scratch: &mut KronScratch,
) {
    assert!(n > 0, "tile width must be non-zero");
    let nn = n * n;
    assert_eq!(a.len(), nn, "A must be n×n");
    assert_eq!(b.len(), nn, "B must be n×n");
    assert_eq!(
        x.len(),
        tiles * nn,
        "x must be exactly {tiles} tile(s) of {n}×{n}; a buffer longer than its \
         live range is the len-derived shape defect this signature exists to refuse"
    );
    assert!(
        scratch.capacity_elems() >= nn,
        "scratch holds {} elems, need {nn} — call KronScratch::ensure({n})",
        scratch.capacity_elems()
    );
    let t = &mut scratch.t[..nn];
    for tile in x.chunks_exact_mut(nn) {
        // Step 1 reads the tile into scratch; step 2 writes the tile back
        // reading only scratch and `b`, so in-place is sound with one buffer.
        gemm_a_z(a, tile, n, t);
        gemm_t_bt(t, b, n, tile);
    }
}

/// `T ← A · Z`, all `n × n` row-major.
///
/// `n` axpy passes over contiguous rows: elementwise FMA, no reduction, so this
/// is the loop LLVM vectorises without help. The `k = 0` pass *writes* instead
/// of accumulating, which removes the zeroing pass over `T`.
#[inline]
fn gemm_a_z(a: &[f32], z: &[f32], n: usize, t: &mut [f32]) {
    for i in 0..n {
        let a_row = &a[i * n..i * n + n];
        let t_row = &mut t[i * n..i * n + n];

        let a0 = a_row[0];
        for (tv, zv) in t_row.iter_mut().zip(&z[0..n]) {
            *tv = a0 * zv;
        }
        for k in 1..n {
            let aik = a_row[k];
            let z_row = &z[k * n..k * n + n];
            for (tv, zv) in t_row.iter_mut().zip(z_row) {
                *tv += aik * zv;
            }
        }
    }
}

/// `Y ← T · Bᵀ`, all `n × n` row-major.
///
/// `Y[i][j] = ⟨T[i][·], B[j][·]⟩` — both operands contiguous, which is the
/// point of the `Bᵀ` in the convention.
#[inline]
fn gemm_t_bt(t: &[f32], b: &[f32], n: usize, y: &mut [f32]) {
    for i in 0..n {
        let t_row = &t[i * n..i * n + n];
        let y_row = &mut y[i * n..i * n + n];
        for (j, yv) in y_row.iter_mut().enumerate() {
            *yv = simd_dot_f32(t_row, &b[j * n..j * n + n], n);
        }
    }
}

// ---------------------------------------------------------------------------
// WHT fast path — A = B = W₍n₎, delegating to the shipped butterfly
// ---------------------------------------------------------------------------

/// `tiles` tiles in place at `A = B = W₍n₎`, the normalized Walsh–Hadamard
/// factor, via the `O(n log n)` butterfly instead of the two GEMMs.
///
/// `W = H/√n` is symmetric and involutive, so `(W ⊗ W) · x = W Z Wᵀ = W Z W` —
/// a per-column pass and a per-row pass, each delegating to
/// [`crate::meld::walsh_hadamard_in_place_normalized`]. The butterfly is *not*
/// reimplemented here: it is the kernel `katgpt-core` already ships, and a
/// second transcription of it is the defect class the module doc cites.
///
/// Complexity per tile: `O(n² log n)` against the generic path's `O(n³)` — a
/// 6.4× arithmetic reduction at `n = 32`, measured in Bench 842.
///
/// # Returns
/// `true` if the tiles were transformed. `false` — and **nothing written** — if
/// `n` has no const-dispatch arm (see [`WHT_TILE_WIDTHS`]); the caller must then
/// take the generic [`kron_apply`] path with an explicit factor from
/// [`wht_factor_into`]. The bool is `#[must_use]` precisely so a silent no-op
/// cannot be the outcome of ignoring it.
///
/// # Panics
/// If `x.len() != tiles · n · n`, or `scratch` is too small for one `n × n`
/// tile (the column pass needs `n`; the tile bound is the batched contract).
#[must_use]
pub fn wht_apply_tiles(n: usize, tiles: usize, x: &mut [f32], scratch: &mut KronScratch) -> bool {
    assert!(n > 0, "tile width must be non-zero");
    let nn = n * n;
    assert_eq!(
        x.len(),
        tiles * nn,
        "x must be exactly {tiles} tile(s) of {n}×{n}"
    );
    assert!(
        scratch.capacity_elems() >= nn,
        "scratch holds {} elems, need {nn} — call KronScratch::ensure({n})",
        scratch.capacity_elems()
    );
    // One generic body, dispatched: every arm is the same call, so there is
    // nothing per-width to get wrong.
    match n {
        8 => wht_tiles_const::<8>(x, tiles, scratch),
        16 => wht_tiles_const::<16>(x, tiles, scratch),
        32 => wht_tiles_const::<32>(x, tiles, scratch),
        64 => wht_tiles_const::<64>(x, tiles, scratch),
        128 => wht_tiles_const::<128>(x, tiles, scratch),
        _ => return false,
    }
    true
}

/// The single WHT tile body, const-generic over the width.
///
/// Tiles are walked by index rather than with `chunks_exact_mut(N * N)`: a
/// const-expression chunk size is `clippy::chunks_exact_to_as_chunks`, and
/// `as_chunks_mut::<{N * N}>()` is not expressible on stable (generic const
/// expressions). The ROW pass does take `as_chunks_mut::<N>()`, which is
/// strictly better than the `chunks_exact_mut` it replaced — it yields
/// `&mut [f32; N]` directly, so the butterfly call needs no `try_into` at all.
#[inline]
fn wht_tiles_const<const N: usize>(x: &mut [f32], tiles: usize, scratch: &mut KronScratch) {
    let nn = N * N;
    let col: &mut [f32] = &mut scratch.t[..N];
    for t in 0..tiles {
        let tile = &mut x[t * nn..(t + 1) * nn];

        // Columns → `W Z`. Gather strided, transform, scatter back.
        for j in 0..N {
            for (i, cv) in col.iter_mut().enumerate() {
                *cv = tile[i * N + j];
            }
            // Reborrow: `try_into` on a `&mut [f32]` would MOVE the binding and
            // the scatter below still needs it.
            let buf: &mut [f32; N] = (&mut *col).try_into().expect("col slice is exactly N");
            crate::meld::walsh_hadamard_in_place_normalized::<N>(buf);
            for (i, cv) in col.iter().enumerate() {
                tile[i * N + j] = *cv;
            }
        }

        // Rows → `· W`. Contiguous, no gather, and already `[f32; N]`.
        let (rows, rest) = tile.as_chunks_mut::<N>();
        debug_assert!(rest.is_empty(), "a tile is exactly N rows of N");
        for row in rows {
            crate::meld::walsh_hadamard_in_place_normalized::<N>(row);
        }
    }
}

/// Materialise the normalized Walsh–Hadamard factor `W₍n₎ = H/√n` into a
/// caller-owned `n × n` row-major buffer.
///
/// `H[i][j] = (−1)^popcount(i & j)` (Sylvester), so `W` is symmetric,
/// orthogonal and involutive. Exists so the *generic* path can be pointed at
/// the same operator the fast path computes — which is what makes
/// `wht_fast_path_matches_generic_path` a comparison of two implementations
/// rather than of two conventions.
///
/// # Panics
/// If `out.len() != n · n`, or `n` is not a power of two (`H` is undefined
/// otherwise, and a silently-wrong factor is worse than a panic).
pub fn wht_factor_into(n: usize, out: &mut [f32]) {
    assert_eq!(out.len(), n * n, "out must be n×n");
    assert!(
        n.is_power_of_two(),
        "Walsh–Hadamard requires n a power of two, got {n}"
    );
    let inv = 1.0f32 / (n as f32).sqrt();
    for i in 0..n {
        for j in 0..n {
            let sign = if (i & j).count_ones() % 2 == 0 {
                1.0f32
            } else {
                -1.0f32
            };
            out[i * n + j] = sign * inv;
        }
    }
}

// ---------------------------------------------------------------------------
// Inter-stage permutation — what makes a MULTI-stage composition mix at all
// ---------------------------------------------------------------------------

/// `dst[i] ← src[perm[i]]` — a fixed gather permutation over one `n²` tile
/// vector, out of place and alloc-free.
///
/// **Why this is part of the primitive and not the caller's problem.** One
/// Kronecker stage mixes only *within* rows and *within* columns: two channels
/// in a different row AND a different column never meet, whatever `A` and `B`
/// are. Research 569 is explicit about it, and so is the Monarch construction
/// it cites (Dao et al. 2022) — the fix is a **fixed** permutation between
/// stages, after which three stages give every channel a path to every other.
/// Composing three stages *without* one is not a three-stage mixer: `(A₂⊗B₂)
/// (A₁⊗B₁) = (A₂A₁) ⊗ (B₂B₁)`, a single stage with multiplied factors, so a
/// benchmark of the permutation-free composition measures the wrong operator
/// while looking like the right one.
///
/// Out of place because an in-place permutation needs cycle-following or a
/// second buffer anyway, and a multi-stage pipeline alternates two buffers as a
/// matter of course — so the caller already owns what an in-place version would
/// have had to hide in scratch.
///
/// # Panics
/// If `dst.len() != perm.len()`, or any `perm[i]` is out of range for `src`
/// (the index panics). A `perm` that is in range but **not a bijection** is a
/// silently wrong operator, not a panic — validate it ONCE at setup with
/// [`is_permutation`], which is why that function exists separately.
#[inline]
pub fn permute_into(src: &[f32], perm: &[u32], dst: &mut [f32]) {
    assert_eq!(
        dst.len(),
        perm.len(),
        "dst must have one slot per permutation entry"
    );
    for (d, &p) in dst.iter_mut().zip(perm) {
        *d = src[p as usize];
    }
}

/// Is `perm` a bijection of `0..len`? A **setup-time** check, deliberately
/// separate from [`permute_into`].
///
/// It allocates a `len`-byte seen-map and is `O(len)`, which is the same order
/// as the permutation it validates — so calling it per apply would double the
/// cost of the cheapest stage in the pipeline, and calling it once at
/// construction costs nothing measurable. The split is the same one
/// [`KronScratch::ensure`] makes: pay for the invariant when the shape is
/// chosen, not when the data flows.
#[must_use]
pub fn is_permutation(perm: &[u32], len: usize) -> bool {
    if perm.len() != len {
        return false;
    }
    let mut seen = vec![false; len];
    for &p in perm {
        let i = p as usize;
        if i >= len || seen[i] {
            return false;
        }
        seen[i] = true;
    }
    true
}

// ---------------------------------------------------------------------------
// Dense reference — the diagnostic half, deliberately public
// ---------------------------------------------------------------------------

/// Build the dense `(A ⊗ B) ∈ ℝ^{n²×n²}` row-major into a caller-owned buffer.
///
/// A **reference and diagnostic**, never a hot path: it materialises `n⁴`
/// elements (4 MiB at `n = 32`) to do what [`kron_apply`] does in `2n³` MACs
/// out of `2n²` of storage. It is `pub` rather than test-only because the G1
/// correctness test and the G2 benchmark are separate compilation units that
/// need the *same* reference — a second copy of it in `benches/` would be a
/// transcription of the very identity under test.
///
/// # Panics
/// If `a`/`b` are not `n · n` long or `out` is not `n² · n²` long.
pub fn kron_dense_into(a: &[f32], b: &[f32], n: usize, out: &mut [f32]) {
    let nn = n * n;
    assert_eq!(a.len(), nn, "A must be n×n");
    assert_eq!(b.len(), nn, "B must be n×n");
    assert_eq!(out.len(), nn * nn, "out must be n²×n²");
    for i in 0..n {
        for j in 0..n {
            let row = i * n + j;
            for k in 0..n {
                let aik = a[i * n + k];
                for l in 0..n {
                    out[row * nn + k * n + l] = aik * b[j * n + l];
                }
            }
        }
    }
}

/// `y ← M · x` for a dense row-major `M ∈ ℝ^{m×m}` — the baseline both the
/// G1 test and the G2 bench measure against.
///
/// A named **delegation** to `katgpt_types::simd::simd_matvec`, not a
/// reimplementation. It exists so the baseline arm of the G2 bench is the
/// crate's real SIMD matvec: a 16× claim measured against a hand-rolled scalar
/// loop is a speedup over a straw baseline, which is the *"speedup of a wrong
/// result"* the promotion rule refuses.
///
/// # Panics
/// If `m_mat.len() != m · m`, or `x`/`y` are not `m` long.
#[inline]
pub fn dense_matvec_into(m_mat: &[f32], m: usize, x: &[f32], y: &mut [f32]) {
    assert_eq!(m_mat.len(), m * m, "matrix must be m×m");
    assert_eq!(x.len(), m, "x must be m long");
    assert_eq!(y.len(), m, "y must be m long");
    simd_matvec(y, m_mat, x, m, m);
}

#[cfg(test)]
mod tests;
