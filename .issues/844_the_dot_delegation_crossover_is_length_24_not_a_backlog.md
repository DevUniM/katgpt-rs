# Issue 844: delegating to `simd_dot_f32` pays only ABOVE ~length 24 (x86_64) — and at EVERY length on NEON — so the private single-accumulator dots are mostly correct, and the hand-rolled chunked ones are the actionable class

**Status:** CLOSED 2026-09-19 — T1–T4 all done. The rule (per-ISA, both arches
measured) and the full workspace per-site read are recorded here; the repairs
transfer to the owning repos' issues (Disposition below).

## What I went looking for, and why it was wrong

This workspace has **221** `fn *dot*`-shaped functions across 2,471 tracked
`.rs` files:

| verdict (by BODY, not by name) | f32 src | f32 test | f64 |
|---|---|---|---|
| DELEGATES to `simd_dot_f32` & friends | 41 | 5 | 1 |
| CHUNKED (multi-accumulator / intrinsics) | 21 | 3 | 3 |
| NAIVE (single-accumulator fold or `zip().sum()`) | 23 | 7 | 3 |
| UNRESOLVED (needs a read) | 56 | 48 | 10 |

The obvious reading — *23 naive f32 loops leaving SIMD on the table, while an
ISA-dispatched kernel ships two crates away* — is **wrong**, and the codebase
says so at the sites. Two of the first three read by hand:

- `katgpt-attn-match/src/score_matrix_simd.rs::dot_8wide` carries a measured
  note that an 8-accumulator hand-rolled pattern ran **1.26× SLOWER** than the
  simple loop on M3/NEON, *"because the 8 separate accumulators prevented LLVM
  from recognizing the dot-product idiom"*.
- `katgpt-core/src/similarity.rs::dot_8` is deliberately simple *"so recos
  stays bit-deterministic across platforms — the Phase 2 GOAT G1 gate depends
  on it"*. Converting it breaks a stated contract, and the contract is the
  point of the function.

⛔ **Those two facts are about DIFFERENT comparisons, and conflating them is
the trap in both directions.** `dot_8wide`'s note is scalar-vs-scalar: a
hand-rolled chunked loop against a plain one. It says *do not hand-roll a
chunked dot*. It says nothing about calling a real per-ISA kernel that already
exists — and the answer to that turns out to depend entirely on the length,
which neither note mentions because neither was asking.

## Measured — `tests/bench_844_dot_delegation_crossover.rs`

x86_64/AVX2, `simd_level() = Avx2`, release, 32 dots per timed call so the
kernel's fixed per-call cost is amortised the way it is inside a real GEMM
inner loop (measuring one dot in isolation would flatter the plain loop).
Interleaved A/B, 11 of 11 rounds surviving:

| dot length | `simd_dot_f32` ns/dot | plain loop ns/dot | plain/simd |
|---|---|---|---|
| 4 | 3.3 | 1.1 | **0.32** — plain 3.1× faster |
| 8 | 3.2 | 1.6 | **0.51** — plain 2.0× faster |
| 16 | 3.4 | 3.0 | **0.86** — plain 1.2× faster |
| 32 | 3.5 | 5.4 | **1.54** — delegation wins |
| 64 | 4.3 | 13.5 | **3.13** |
| 256 | 10.1 | 78.0 | **7.90** |

**Three runs, because one point is what this issue is about.** The table above
is run 2; the other two gave `0.32 / 0.51 / 0.78 / 1.61 / 3.14 / 9.15` (a
throwaway build outside the repo, its own hand-rolled interleaver) and
`0.33 / 0.49 / 0.81 / 1.54 / 3.09 / 9.41`. **The crossover rows are stable to
±0.05 and the crossover itself never moves**; only the length-256 ratio swings
(7.90 – 9.41), which is the row where the plain arm is 75 ns and most exposed to
the box. Quote the crossover, not the 256 figure.

**The mechanism is a fixed cost, and it is legible in the table.**
`simd_dot_f32` sits at a **~3.3 ns floor** from length 4 to length 32 — that is
dispatch plus call plus the reslice, not arithmetic — while the plain loop is
proportional from the first row. So the kernel is *free to be slow* below the
point where its own overhead is amortised, and above it the scaling is
completely different: 3× the elements from 16 to 64 costs the kernel 26% and
the plain loop 350%.

**Crossover on x86_64: between length 16 and 32.**

## Measured — aarch64/NEON (T4, M3, 2026-09-19): NO crossover — delegation wins at every length

`simd_level() = Neon`, same bench, same discipline, three runs (ratios stable
to ±0.13; the len-4 row is the noisiest at ±0.08):

| dot length | `simd_dot_f32` ns/dot | plain ns/dot | plain/simd |
|---|---|---|---|
| 4 | 0.8–1.5 | 1.5–1.8 | **1.94–2.02** — delegation wins |
| 8 | 0.9 | 1.6–1.7 | **1.80–1.81** |
| 16 | 1.5 | 2.5–2.6 | **1.70** |
| 32 | 1.8–2.0 | 5.7–6.4 | **3.19–3.32** |
| 64 | 3.2–6.0 | 16.3–17.2 | **5.10–5.20** |
| 256 | 12.3–12.5 | 112–113 | **9.06–9.08** |

T4's original expectation ("NEON is 4-wide against AVX2's 8, so the crossover
is expected LOWER") was **refuted in the strongest direction**: the crossover
is not lower — it is BELOW THE MEASURED RANGE, i.e. below length 4. Two
mechanisms, both legible: (1) the aarch64 dispatch is COMPILE-TIME
(`#[cfg(target_arch)]` + direct call — no runtime CPUID probe), so the kernel's
floor is ~0.8 ns against x86_64's ~3.3 ns; (2) the plain runtime-length loop
is SLOWER on NEON than x86_64 at every length (1.5 ns vs 1.1 ns at len 4; 113
vs 78 ns at 256). The "no crossover in range" branch the bench prints is not a
fixed-overhead-model violation — it means the intersection sits below len 4,
where no real dot site lives.

**So the workspace rule is per-ISA:**
- **x86_64/AVX2**: plain loop wins ≤16; delegate ≥~24 (crossover 16–32).
- **aarch64/NEON**: **always delegate** (every length ≥4, 1.7×–9.1×).
- Rule 1 above is therefore ISA-conditional: a plain small-D loop is
  "correct" on x86_64 and a 1.7×–1.9× NEON loss. For crates whose prod path
  is aarch64/wasm32-heavy, small-D delegation is the better default; the
  wasm32-simd128 arm of the kernel makes delegation the cross-arch answer.

## The rule this establishes

1. **A plain single-accumulator loop over a small fixed `D` is CORRECT on
   x86_64, not a defect.** At `D ≤ 16` it is the faster code there. Most of
   the 23 "naive" sites are over `[f32; 8]`-shaped data. Do not
   blanket-convert them — and do not file a lint for it. ⚠ On NEON the same
   loop concedes 1.7×–1.9× (T4); arch-weight the decision per crate.
2. **Above ~24 elements (x86) — or always (NEON) — delegate.** The margin
   only widens; by length 256 a hand-written loop pays 8–9×.
3. **Never hand-roll a chunked/multi-accumulator dot.** It is the worst of
   the three options: slower than a plain loop at small lengths (`dot_8wide`'s
   1.26×, measured on NEON) *and* slower than the real kernel at large ones,
   while costing a second transcription of arithmetic — the duplication class
   AGENTS.md prices at 30 findings in `dash_attn/channel_aware.rs`.
4. **Bit-determinism beats all three when a gate depends on it.** The arms are
   not bit-identical (max |Δ| 2.4e-7 at length 8, 3.8e-6 at 256 on x86_64;
   2.9e-6 at 256 on NEON) because the summation orders differ, so a site with
   a cross-platform determinism contract is out of scope by construction,
   whatever the length.

## Tasks

- [x] **T1 — DONE. Measure the crossover** rather than asserting one.
      `tests/bench_844_dot_delegation_crossover.rs`, reproduced three times
      across two independent harnesses.
- [x] **T2 — DONE 2026-09-19 (the residual read).** The census's 21 CHUNKED
      f32-src sites, read by body across the workspace (re-derived census:
      398 fn-dot defs → 247 src candidates after excluding test trees and
      `katgpt-types/src/simd/**`). Disposition:
      - 10 genuine kernels in `katgpt-types/src/simd/**` (the thing to call).
      - 5 `simd_lut_dequant.rs` — different operation (dequant-through-LUT
        then dot). OUT.
      - 3 `katgpt-moka-wasm` — standalone wasm bundle. OUT (its manifest
        declares katgpt-types, so the exemption is soft — recorded, not
        acted on).
      - 1 already-repaired: `channel_aware.rs` (Issue 845).
      - 3 KERNEL-HOME: `newton_schulz.rs::blocked_dot8{,_neon,_scalar}` — a
        batched 8-output GEMM micro-kernel (one acc per OUTPUT, not
        multi-acc-within-one-dot), per-ISA dispatch + scalar fallback, whose
        remainder columns already delegate to `simd_dot_f32`. Correct as-is.
      - **3 FINDINGS (rule c, un-repaired at close):**
        `katgpt-core/src/cgsp/types.rs:41 dot_f32_fma4` (4-acc; katgpt-types
        already a dep; doc admits mirroring the kernel's scalar fallback);
        `katgpt-kv/src/still_kv/perceiver.rs:486 dot_chunk4` (katgpt-types
        already a dep; sibling module `gating.rs` delegates);
        `katgpt-dec/src/simd.rs:50 simd_dot_f32` (4-acc + `get_unchecked`;
        ⚠ katgpt-dec is zero-dep BY DESIGN — published to crates.io
        standalone; adding katgpt-types changes that posture. Owner call.)
- [x] **T3 — DONE 2026-09-19 (the UNRESOLVED read).** The re-derived census
      subsumed the 56-UNRESOLVED bucket; every src candidate was read by body
      (three parallel reads, spot-verified). Outcomes: the UNRESOLVED shapes
      resolved exactly as predicted — accumulate-into-slice (`rrq_quant::
      dot_acc_into` — dequant-fused GEMV, OUT), tropical/semiring dots
      (`tropical_dot_into` — max-sum, OUT), const-generic wrappers (fixed-D,
      rule-1 OK), plus `#[cfg(test)]` fns, f64 families (`peira`,
      `ridge_solve`, `mi/*`), i8 families (`moka_int8`), and name-collisions
      (DoT damage-over-time, UI dots, dotfiles). **No hidden findings beyond
      the T2 set** — plus the rule-b CANDIDATES (naive, large-D), filed with
      the owning repos (Disposition).
- [x] **T4 — DONE 2026-09-19 (aarch64).** Measured above; expectation
      refuted; rule made per-ISA; the bench's no-crossover print branch
      repaired in the same change (it read as a model violation where the
      truth is "delegation wins throughout").

## Disposition — the findings, by owning repo

| repo | issue | contents |
|---|---|---|
| riir-ai | [Issue 982](../../riir-ai/.issues/982_hand_rolled_chunked_dots_and_large_d_naive_dots.md) | 3 CHUNKED findings (`cross_game_prefix.rs:528`, `motivation/math.rs:38`, `lora_still_forward.rs:575`) + 6 large-D candidates (64/32-dim engine + poc sites) |
| riir-train | [Issue 562](../../riir-train/.issues/562_hand_rolled_chunked_dots_844_read.md) | 2 CHUNKED findings (`embedding_translator/model.rs:568 dot8`, `edge_lora/sigmoid_gate.rs:233 dot_product_chunked`) |
| riir-neuron-db | [Issue 621](../../riir-neuron-db/.issues/621_large_d_naive_dots_844_read.md) | 2 large-D candidates (`transition_error_taxonomy.rs:274`, `hebbian_bridge.rs:849`, both fixed-64) |
| katgpt-rs | this issue | `cgsp/types.rs:41`, `kv/perceiver.rs:486` (delegable now) + `katgpt-dec/simd.rs:50` (owner call: zero-dep posture) — repair with the next touch of each crate; NOT a blanket sweep |

Also filed from the read: `katgpt-attn-match/score_matrix_simd.rs:121
dot_8wide` (runtime head_dim, perf-tested at d=64 — delegate) and
`katgpt-sparse/specialist_projection.rs:206 dot_truncated` (d_hidden ≥32 —
delegate) as katgpt-rs candidates; same per-site contract.

## Consumers already affected

`katgpt_core::linalg::kron_tile` (Issue 839) delegates in its step-2 reduction
and is **correct at the widths it exists for** — `n = 32` (1.54×) and `n = 64`
(3.13×). ⚠ It also *supports* `n ∈ {8, 16}`, where by this table the delegation
**costs** 2.0× and 1.2× on x86_64 (and WINS 1.8×/1.7× on NEON, T4 — the
recorded x86-only caveat is itself now ISA-conditional). Recorded in its
module doc rather than repaired: a length-conditional branch would add a
second summation order and a second code path for widths nothing in Research
569 uses, and AGENTS.md's own threshold (*"2× is the threshold below which the
fast path would not be worth the second code path"*) cuts against it at
exactly the sizes in question.

## Non-goals

- **No lint, and no sweep.** The rule is length-conditional, arch-conditional
  and contract-sensitive, so a mechanical check would fire on the sites that
  are right. This is a documented rule plus a reproducible measurement; that
  is the correct instrument for it.
- No change to `similarity.rs::dot_8` or any other site with a stated
  determinism contract, at any length.
