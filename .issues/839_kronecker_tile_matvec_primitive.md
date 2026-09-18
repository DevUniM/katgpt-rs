# Issue 839: Kronecker-tile matvec primitive (`kron_apply`) — Hadamard-MLP fusion (Research 569)

**Status:** T1–T6 + T8 DONE (2026-09-19, Bench 839 — all four gates PASS, stays OPT-IN per the no-default-consumer rule); **T7 alone is open, and T4 weakened its premise** (see §T4). GOAT-plan; modelless half of the Hadamard-MLP distill (Research 569). Training half (WHT-init structured FFN for our own drafters) routes to riir-train, not this issue.

## Motivation

Cactus Needle 3 (blog 2026-09-17) replaces the dense FFN with three Kronecker stages `Mₛ = Aₛ ⊗ Bₛ` (A,B ∈ ℝ³²ˣ³², 1024 channels as a 32×32 tile) applied as `vec(Aᵀ Z B)` — 65,536 MACs and 2,048 params per stage vs ~1M and ~1M dense (180× smaller, 22× cheaper per layer at the full 3-stage construction, 25.6K vs 4.7M params). The tile row/col apply machinery **already ships** in `katgpt-kv/src/kvarn/hadamard.rs` (`hadamard_rows`/`hadamard_cols`) — but only at A=B=H₃₂ (fixed WHT). The new primitive is the **arbitrary-factor** version: general 32×32 (or 64×64) A,B, batched over tiles — the structured-sparse-matvec slot.

Prior art (kills Super-GOAT, not GOAT): Monarch (Dao et al. 2022), Butterfly (2020), MoST (2025).

## Tasks

- [x] **T1 — DONE.** `kron_apply(A, B, tiles, scratch)` in katgpt-core (linalg): per-tile `Z ← Aᵀ Z B` as two small GEMMs, const-generic or runtime 32/64, zero-alloc (caller scratch), `#[inline]`, SIMD-chunked inner loops (optimization-guidelines: chunked, branch-free).
- [x] **T2 — DONE, and bit-parity is UNACHIEVABLE by construction (see §T2 below).** WHT fast path: when A=B=H₃₂, delegate to the existing butterfly (`walsh_hadamard_in_place_normalized`-class) and pin bit-parity with the generic path in a test.
- [x] **T3 — DONE.** G1 correctness: `(A⊗B)·x` tile apply == dense reference on random A,B,x (1e-5 f32), + exact Hadamard round-trip anchor.
- [x] **T4 — DONE, 13.56× against the FLOP-ratio floor of 16×; the ternary arm is REPORTED not barred (see §T4 below).** G2 perf bench: batched 3-stage Monarch apply vs (a) dense n=1024 matvec, (b) ternary dense matvec at matched params — expect ~16× FLOP ratio floor vs (a); record in `.benchmarks/`.
- [x] **T5 — DONE.** G3 no-regression: feature-gated (`kron_tile`), default-off; existing KVarN/meld WHT paths byte-identical.
- [x] **T6 — DONE, 0 allocs over 50 rounds, sentinel live in BOTH profiles.** G4 zero-alloc witness (fixed-size scratch, no heap on the hot path).
- [ ] **T7 — still deferred, and T4 WEAKENED its premise (see §T4).** Ternary-factor fusion spike (deferred behind T4 PASS): A,B quantized to {−1,0,+1} — stage becomes add/sub accumulate via the ternary SIMD matvec kernels; 6,144 weights ≈ 1.5 KB/layer. GOAT gate for the fused form runs in riir-train on a trained small LM (quality axis is not modelless-decidable).
- [x] **T8 — DONE.** Document the Needle-3 recipe pointer (WHT init → learnable factors, fixed permutations, rank-8 gain as sigmoid-gated variant) in the module doc; cross-link Research 569.

## Non-goals

- No FFN retrofit of served upstream checkpoints (weights are fixed upstream — Research 452 Q3 logic).
- No training loop in katgpt-rs (riir-train owns the recipe).

## T2 — bit-parity was the wrong thing to ask for, and the gap is MEASURED instead

T2's wording says *"pin bit-parity with the generic path in a test"*. It is
unachievable, and not because either path is sloppy: the butterfly sums pairwise
in a `log n`-deep tree and applies one `1/√n` scale at the end, while the
generic path reduces in `simd_dot_f32`'s per-ISA order over explicit `±1/√n`
entries. Two different summation orders over the same reals are two different
floating-point programs. A bit-parity pin would have passed only on the box that
wrote it — and only until somebody changed the lane's target features.

What landed instead: `wht_fast_path_matches_generic_path` asserts a **measured**
tolerance at every dispatched width and **prints the observed gap**, so a later
tightening has a number rather than folklore. Measured x86_64/AVX2: max `|Δ|` =
**4.3e-7** over `n ∈ {8,16,32,64}` against a 1e-5 pin. Cross-**architecture**
bit-identity is explicitly not claimed — the arch-conditional-pin shape
AGENTS.md records for `t698_t5_kv_mean_gates`.

Two anchors cover what a parity test structurally cannot: both paths could share
a wrong `1/√n` and still agree with each other, so `wht_apply_is_involutive`
pins `W² = I` and `wht_factor_is_symmetric_and_orthogonal` pins the reference
factor itself.

## T4 — the ternary arm, and why it is reported rather than barred

T4 asks for *"(b) ternary dense matvec at matched params"*. Measured, and the
comparison does not exist in that form: at a fixed 1024×1024 operator the arms
are **512× apart in parameters** (2,048 f32 = 8 KiB of factors against 1,048,576
trits ≈ 197 KiB of bitplanes). So G2c reports **throughput at a matched
OPERATOR** and bars nothing — losing it would not make the Kronecker stage worse
at its own job, and winning it is not a matched-parameter result.

⛔ **And the arm returned a result that belongs to a different owner.** With the
baseline's dispatch disclosed on the verdict line (`simd_level() = Avx2`, so not
a scalar-fallback artifact) the ternary dense matvec measures **122.7 µs**
against the f32 `simd_matvec`'s **63.3 µs** — **1.94× slower than the multiply
it removes**, on a default-on flag. Probed against its own scalar reference it is
a healthy 4.32× (539.7 µs → 125.0 µs), which refutes the obvious explanation.
Filed as **Issue 843**; deliberately not folded into this GOAT's verdicts.

⛔ **And the measurement that paragraph asked for has now been TAKEN, at the
factor widths, and it refutes T7's latency premise** (Bench 843's sweep,
2026-09-19). An earlier version of this section said the hypothesis "may still
hold for 32×32 factors, where the operand fits a register file and the SWAR
balance is different". Measured:

| width | f32 ns | ternary ns | ternary/f32 |
|---|---|---|---|
| 32 | 111 | 172 | **1.56× slower** |
| 64 | 277 | 593 | **2.24× slower** |

The register-file intuition points the wrong way: a 32×32 f32 factor is **4
KiB** and already L1-resident, so a 16× smaller footprint relieves no pressure,
and what is left is the per-MAC cost — where add/sub-accumulate loses to FMA on
this box. The ternary/f32 ratio across `m = 32..4096` peaks at 3.70× (m=512)
and only crosses 1.0 above 2048, i.e. the win is a **cache-residency** effect
and 32 is as deep inside the losing regime as the sweep goes.

⚠ **A proxy, and only the latency half is refuted.** A stage is two 32×32
matrix products, not one matvec, so a fused kernel could beat this ratio; and
T7's **footprint** claim (6,144 weights ≈ 1.5 KB/layer) is untouched and is a
different argument on the axis the sweep shows actually pays. So T7 stays
deferred with its justification narrowed to size rather than speed — not
cancelled, and no longer resting on a hypothesis this repo can already
contradict.

## Where it lives

- `crates/katgpt-core/src/linalg/kron_tile.rs` + `kron_tile/tests.rs` — 14 tests,
  including `permute_into` / `is_permutation`, which are in the primitive because
  T4's three-stage arm is not the right operator without them (one Kronecker
  stage mixes only within rows and within columns; `stages_collapse_without_a_permutation`
  pins the collapse)
- `crates/katgpt-core/Cargo.toml` — `kron_tile = ["meld"]`, OPT-IN. The `meld`
  edge is not incidental: a `cfg(feature = "meld")` fast path would compile to
  nothing under `--features kron_tile` alone, which is the Issue 741 shape.
- `crates/katgpt-core/src/lib.rs` — `kron_tile` joins the `linalg`
  `#[cfg(any(...))]` list **at birth** (the rule two features broke silently,
  Issue 701 R1b); `--no-default-features --features kron_tile` compiles and runs.
- `Cargo.toml` (root) — passthrough + the Bench 839 `[[test]]` row.
- `tests/bench_839_kron_tile_goat.rs` — ADOPTS `tests/common/ab_timing.rs`
  rather than adding the 153rd sequential A/B (Issues 833/834).
- `.benchmarks/839_kron_tile_goat.md` — the GOAT record, with box state.
