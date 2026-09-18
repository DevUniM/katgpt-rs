# Issue 839 — Kronecker-tile matvec (`kron_apply`): GOAT results

**Date:** 2026-09-19 (T1–T6)
**Primitive:** `katgpt_core::linalg::kron_tile` — `kron_apply` / `kron_apply_tile_into`
/ `wht_apply_tiles` / `wht_factor_into` / `permute_into` / `is_permutation` /
`kron_dense_into` / `dense_matvec_into`
**Feature:** `kron_tile = ["meld"]` in `katgpt-core` — **OPT-IN**, plus a root
passthrough `kron_tile = ["katgpt-core/kron_tile"]` so Bench 839 can name it in
`required-features`. Not promoted to default-on: all four gates pass, but there
is no default-path consumer in this repo (no-default-consumer rule), and the
learnable-factor half of Research 569 is riir-train's.
**Gates:** `cargo test -p katgpt-core --no-default-features --features kron_tile --lib linalg::kron_tile` — **14 tests**
**Bench:** `cargo test --release --features kron_tile --test bench_839_kron_tile_goat -- --nocapture --test-threads=1`

## What it is

`(A ⊗ B) · x` for arbitrary `n × n` factors, batched over tiles, computed as two
small GEMMs instead of one `n² × n²` matvec: **`2n³` MACs and `2n²` parameters
against `n⁴` and `n⁴`**. At `n = 32` — Research 569's stage, 1024 channels as a
32×32 tile — that is 65,536 MACs / 2,048 params against ~1M / ~1M.

Row-major reshape gives `(A ⊗ B) · x ≡ A Z Bᵀ`, derived in the module doc and
pinned by `kron_apply_matches_dense_reference_{n8,n32}` rather than asserted.
Research 569 and the Monarch literature write `vec(Aᵀ Z B)`, the same operation
under a column-major `vec`; the caller supplies transposed factors for that
reading.

## Box state — read at launch, because a bar without it is not a measurement

`shikuwa`, Windows 11 Pro, i7-13700K (16 cores), **17.34 GB free physical of
31.78**, commit **36.92 / 62.78 GB** (25.9 GB headroom, limit re-read at launch
per AGENTS.md § Feature Flag Discipline G2), no concurrent cargo build in
another target dir. Three peer agent sessions live, one busy — heaviest
non-agent holder was `zed` at 10.12 GB commit / 2.59 GB working set. Release
profile; `simd_level()` disclosed as `Avx2` on the verdict line.

## G1 — correctness (PASS)

| arm | claim | measured |
|---|---|---|
| `kron_apply_matches_dense_reference_n8` | tile apply == explicit `(A⊗B)` 64×64 matvec | max `\|Δ\|` ≤ 1e-5 ✓ |
| `kron_apply_matches_dense_reference_n32` | same at 1024×1024 | max scaled `\|Δ\|` ≤ 1e-5 ✓ |
| `kron_apply_batched_matches_per_tile` | 5 tiles batched == 5 single-tile calls | **bit-identical** ✓ |
| `wht_fast_path_matches_generic_path` | butterfly == two-GEMM path at `A=B=W` | max `\|Δ\|` = **4.3e-7** over `n ∈ {8,16,32,64}` (pin 1e-5) ✓ |
| `wht_apply_is_involutive` | `(W⊗W)` applied twice == identity | max `\|Δ\|` ≤ 1e-6 ✓ |
| `wht_factor_is_symmetric_and_orthogonal` | `W = Wᵀ`, `W Wᵀ = I` | exact / ≤ 1e-6 ✓ |
| `stages_collapse_without_a_permutation` | 2 stages, no Π == 1 stage at `A₂A₁ ⊗ B₂B₁` | max scaled `\|Δ\|` ≤ 1e-5 ✓ |
| `permute_into_is_a_gather_and_round_trips` | `dst[i]=src[perm[i]]`; `Π⁻¹∘Π = id` | **exact** ✓ |
| `is_permutation_rejects_in_range_non_bijections` | duplicate / out-of-range / wrong length | ✓ |

⚠ **T2 asked for bit-parity between the fast and generic paths and it is
unachievable by construction, not by sloppiness.** The butterfly sums pairwise
in a `log n`-deep tree with one `1/√n` scale at the end; the GEMM path reduces
in `simd_dot_f32`'s per-ISA order over explicit `±1/√n` entries. Different
summation orders over the same reals are different floating-point programs. The
measured gap (4.3e-7) is asserted instead and **printed by the test**, so a
later tightening has a number to tighten against rather than folklore. Bit
equality across *architectures* is explicitly not claimed — the
arch-conditional-pin shape AGENTS.md records for `t698_t5_kv_mean_gates`.

## G2 — throughput (PASS), via the interleaved A/B harness

Every ratio here is two timed arms compared, which is AGENTS.md's
sequential-A/B class — the one measured at **+5.2% and +21.7%** for two arms of
identical work thirty seconds apart, and the subject of the live Issue 833/834
census that counted **152** instances. This target **ADOPTS**
`tests/common/ab_timing.rs` (interleaved chunks, one ratio per pair, median
across pairs, loud zero) rather than adding the 153rd. Candidate is always the
`b` arm; bars are stated and asserted as `speedup = a_ns / b_ns`, never on the
`b/a` median, because a flipped orientation inverts a bar silently.

| arm | baseline (a) | candidate (b) | FLOP ratio | measured speedup | bar | verdict |
|---|---|---|---|---|---|---|
| **G2a** | dense 1024×1024 `simd_matvec` — 63.3 µs | `kron_apply` — 4.66 µs | `n/2` = 16.0× | **13.56×** (runs 13.6× / 13.7×) | ≥ 8× | PASS |
| **G2b** | generic two-GEMM at `A=B=W` — 4.93 µs | `wht_apply_tiles` — 1.16 µs | `n/log₂n` = 6.4× | **4.26×** (runs 4.03× / 4.26×) | ≥ 2× | PASS |
| **G2c** | ternary dense `simd_ternary_matvec` — 122.7 µs | `kron_apply` — 4.39 µs | — | **27.98×** | *reported, not barred* | — |
| **G2d** | dense 1024×1024 `simd_matvec` — 64.0 µs | **3-stage Monarch** — 13.94 µs | `n/6` = 5.33× | **4.59×** | ≥ 3× | PASS |

Per-round ranges, which are half the claim: G2a `0.0628 .. 0.1010`, G2b
`0.2335 .. 0.4236`, G2c `0.0340 .. 0.0473`, G2d `0.2067 .. 0.2422` — 11 of 11
rounds surviving in all four. Run-to-run across three executions of the same
binary: G2a **13.22 / 13.56 / 13.70×**, G2b **3.87 / 4.03 / 4.26×**, so the
bars (8×, 2×) are not close calls and are not the box's to decide. G2b's one
0.42 round is the interleaving doing its job — a preemption that a single
sequential ratio would have reported as the verdict.

- **G2a reaches 85% of its FLOP ratio** against a baseline that is the crate's
  *real* ISA-dispatched `simd_matvec`, not a hand-rolled scalar loop. That
  choice is deliberate: a 16× claim measured against a straw baseline is the
  "speedup of a wrong result" the promotion rule refuses. `dense_matvec_into` is
  a named delegation to it for exactly this reason.
- **G2d reaches 86% of its 5.33× FLOP ratio** and is Issue 839 T4's literal
  ask: `M₃ Π₂ M₂ Π₁ M₁`, three stages with **fixed permutations between
  them**. The Πs are load-bearing rather than decorative —
  `(A₂⊗B₂)(A₁⊗B₁) = (A₂A₁)⊗(B₂B₁)`, so a permutation-free "three-stage"
  composition is one stage with multiplied factors, and the arm would have
  measured the wrong operator while looking like the right one. That collapse
  is pinned by `stages_collapse_without_a_permutation` rather than cited, and it
  is why [`permute_into`] / [`is_permutation`] are part of the primitive.
  Parameters: **6,144 against 1,048,576 (171×)**, against Research 569's
  claimed 180× per layer — the gap is the two diagonals and the bias this
  primitive does not own.
- **G2b reaches 60% of its 6.4× FLOP ratio**, and the shortfall is structural:
  the butterfly's column pass is a strided gather/scatter while the generic path
  is two contiguous GEMMs, so part of the arithmetic win is spent on memory
  order. 4.26× is comfortably above the 2× threshold below which a second code
  path would not be worth keeping — which is the decision that arm exists to
  inform.

⛔ **G2c is REPORTED and deliberately not barred, and the reason is the honest
one.** The arms are **512× apart in parameters** (2,048 f32 = 8 KiB of factors
against `n⁴` = 1,048,576 trits ≈ 197 KiB of bitplanes). "Matched params" — Issue
839 T4's wording — is not a comparison these two shapes admit at a fixed
operator size, so the number is throughput at a **matched operator** and nothing
more. Losing it would not make the Kronecker stage worse at its own job, and
winning it is not a matched-parameter result. It is in the record because a GOAT
that quietly omits the strongest available competitor is the kind this repo has
learned to distrust.

⚑ **G2c's baseline dispatch is disclosed on the verdict line** (`simd_level() =
Avx2`). `simd_ternary_matvec` picks its arm from a **runtime** probe, so a
ternary number taken on the scalar fallback would be a measurement of the
fallback — "a lane compiles what it names", one layer down, where the arm is
chosen at run time. The disclosure is what makes the 122.7 µs readable, and it
is what turned an unexpected result into **Issue 843** rather than into a
caveat: the ternary path is on its AVX2 arm (probed at **4.32×** its own scalar
reference, 539.7 µs → 125.0 µs) and is still **~1.9× slower than the f32 dense
matvec** at this size. That belongs to whoever owns that kernel; it is not a
`kron_tile` finding and is not folded into these verdicts.

## G3 — no regression (PASS)

- Feature is **default-off**; `linalg::kron_tile` does not exist without it.
- `kron_tile` joins the `linalg` `#[cfg(any(...))]` list **at birth** — the rule
  two features broke silently (Issue 701 R1b) — so
  `--no-default-features --features kron_tile` compiles and its 11 tests run.
  Verified: that exact isolation command is the gate command above.
- The existing KVarN / meld WHT paths are untouched: `wht_apply_tiles`
  **delegates** to `meld::walsh_hadamard_in_place_normalized` and adds no
  second transcription of the butterfly. `katgpt-kv::kvarn::hadamard` is not
  modified or referenced.

## G4 — zero-alloc (PASS)

`g4_zero_alloc_steady_state`: **0 allocations** over 50 rounds of
`kron_apply` + `wht_apply_tiles` at `n = 32`, 8 tiles, after one warm-up call.
Carries the liveness sentinel (a missing `TrackingAllocator` reports a perfect
zero, which is the same output as success) — the sentinel **fired in both
configurations**, so neither run was a silent skip.

Gated `#[cfg(any(debug_assertions, feature = "alloc_tracking"))]` — the full
Issue-741 predicate, not a bare `debug_assertions`, which would make the
measurement impossible in the profile that ships. Verified in both:

| configuration | result |
|---|---|
| `cargo test -p katgpt-core --no-default-features --features kron_tile --lib` | 14 passed |
| `cargo test --release -p katgpt-core --no-default-features --features kron_tile,alloc_tracking --lib` | 14 passed, sentinel live |

## What this does NOT claim

- **No quality axis.** `A` and `B` are inputs; nothing here chooses them. Whether
  a WHT-initialised *learnable* factor pair matches a dense FFN is a training
  question (Research 569's other half) and routes to riir-train. This is the
  modelless half only, and its gates are arithmetic ones.
- **T7 (ternary-factor fusion) is untouched and stays deferred.** Issue 839
  scopes it behind a T4 pass, and G2c is the reason to look harder before
  spending it: the ternary dense arm on this box is *slower* than f32 dense, so
  "ternary factors will be cheaper" is a hypothesis this bench actively
  weakens at `n = 32`. It may still hold for the 32×32 factors themselves,
  where the operand fits a register file — that is a measurement nobody has
  taken.
- **One box, one arch.** All figures are x86_64/AVX2 on `shikuwa`. The aarch64
  and wasm32/simd128 arms compile (the reduction is `simd_dot_f32`, which has
  both) and are **executed by nothing here**.
- **Nothing automatic runs this target.** `scripts/suite_membership_audit.py`
  puts it in katgpt-rs's 442 load-bearing unpinned rows — no script and no
  workflow names it, which is this repo's standing state for benches rather
  than an oversight about this one (AGENTS.md: *"the other 477 integration-test
  and 176 bench targets are executed by nothing automatic"*). Re-run it by hand
  from the Bench line above.
- ⛔ **And the 14 lib gates are not covered either — do not read them as the
  safety net.** `scripts/test_gate.sh` runs katgpt-core `--lib` at **default**
  features, where `kron_tile` is off and `linalg::kron_tile` compiles to
  nothing: the cell reports a green count that does not include them. That is
  the correct behaviour for an opt-in feature and it is also this repo's
  green-zero shape, so it is stated rather than left to be discovered. Both
  commands at the top of this record are hand-run, on this box, by a human or
  an agent who chose to.
