# Issue 844: delegating to `simd_dot_f32` pays only ABOVE ~length 24 — so the private single-accumulator dots are mostly correct, and the hand-rolled chunked ones are the actionable class

**Status:** OPEN — the measurement is DONE (§Measured); what remains is a
per-site read of one named class. Found while auditing a hypothesis that turned
out to be wrong, which is why it is filed as a *rule* rather than as a backlog.

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

**Crossover: between length 16 and 32.**

## The rule this establishes

1. **A plain single-accumulator loop over a small fixed `D` is CORRECT, not a
   defect.** At `D ≤ 16` it is the faster code. Most of the 23 "naive" sites
   are over `[f32; 8]`-shaped data, which is exactly this case. Do not
   blanket-convert them — and do not file a lint for it.
2. **Above ~24 elements, delegate.** The margin only widens, and by length 256
   a hand-written loop is paying 8×.
3. **Never hand-roll a chunked/multi-accumulator dot.** It is the worst of the
   three options: slower than a plain loop at small lengths (`dot_8wide`'s
   1.26×, measured on NEON) *and* slower than the real kernel at large ones,
   while costing a second transcription of arithmetic — the duplication class
   AGENTS.md prices at 30 findings in `dash_attn/channel_aware.rs`.
4. **Bit-determinism beats all three when a gate depends on it.** The arms are
   not bit-identical (max |Δ| 2.4e-7 at length 8, 3.8e-6 at 256) because the
   summation orders differ, so a site with a cross-platform determinism
   contract is out of scope by construction, whatever the length.

## Tasks

- [x] **T1 — DONE. Measure the crossover** rather than asserting one.
      `tests/bench_844_dot_delegation_crossover.rs`, reproduced three times
      across two independent harnesses.
- [~] **T2 — STARTED, and the first read found a live defect: [Issue 845](845_channel_aware_duplicated_a_kernel_and_gated_its_avx2_arm_at_compile_time.md).**
      `channel_aware.rs` carried a same-named ~200-line duplicate of
      `simd_dot_f32` whose AVX2 arm was gated on a COMPILE-time
      `target_feature`, so the shipped path ran a scalar loop — 2.7–7.8× slower
      on a default build, 1.8–4.8× slower even with `+avx2`. Repaired by
      delegation, `unsafe` surface of that file now zero, regression-gated with
      a canary. **11 of the 21 are outside `katgpt-types`; 5 of those
      (`simd_lut_dequant.rs`) are a different operation (dequant-through-LUT,
      then dot) and 3 are `katgpt-moka-wasm`'s standalone wasm bundle, whose
      dependency surface is its own call.** So the residual read is small and
      named. Remaining:
      This is the actionable class per rule 3, and the classifier cannot do it:
      the bucket mixes `katgpt-types`' *genuine* intrinsic kernels (correct, and
      the thing everything else should call) with hand-rolled multi-accumulator
      scalar loops (wrong at both ends). Only the second kind is a finding.
      Exclude `crates/katgpt-types/src/simd/**` first, then read what is left.
- [ ] **T3 — Read the 56 UNRESOLVED f32 `src` sites.** UNRESOLVED is not clean;
      it is "the census could not classify the body". The shapes it stumbled on
      include accumulate-into-slice forms (`dot_acc_into`), tropical/semiring
      dots that are not f32 sums at all, and const-generic wrappers. Expect most
      to be out of scope and say so per site.
- [ ] **T4 — Re-measure the crossover on aarch64.** It is a **per-ISA**
      property: NEON is 4-wide against AVX2's 8, so the fixed cost is amortised
      by fewer elements and the crossover is expected LOWER. Any rule quoted as
      "~24" without this is an x86_64 rule wearing a workspace rule's clothes —
      and this repo has the `dot_8wide` note as a standing reminder that the two
      arches disagree about dot products specifically.

## Consumers already affected

`katgpt_core::linalg::kron_tile` (Issue 839) delegates in its step-2 reduction
and is **correct at the widths it exists for** — `n = 32` (1.54×) and `n = 64`
(3.13×). ⚠ It also *supports* `n ∈ {8, 16}`, where by this table the delegation
**costs** 2.0× and 1.2×. Recorded in its module doc rather than repaired: a
length-conditional branch would add a second summation order and a second code
path for widths nothing in Research 569 uses, and AGENTS.md's own threshold
(*"2× is the threshold below which the fast path would not be worth the second
code path"*) cuts against it at exactly the sizes in question.

## Non-goals

- **No lint, and no sweep.** The rule is length-conditional and
  contract-sensitive, so a mechanical check would fire on the 23 sites that are
  right. This is a documented rule plus a reproducible measurement; that is the
  correct instrument for it.
- No change to `similarity.rs::dot_8` or any other site with a stated
  determinism contract, at any length.
