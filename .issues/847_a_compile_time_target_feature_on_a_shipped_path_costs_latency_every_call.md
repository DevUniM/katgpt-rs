# Issue 847: `simd_lut_dequant`'s AVX2 kernels compiled to NOTHING on every ordinary x86_64 build — a default-on feature running its scalar fallback

**Status:** **RESOLVED** for `simd_lut_dequant` (measured, repaired, gated,
canary-verified). **T2 open** for `bf16_convert`, whose finding is a different
one and must not be repaired by the same reflex.

⚠ **Filed as 846, renumbered to 847 before pushing.** A concurrent session
allocated 846 for `citation_drift_first_real_alias_read` and pushed it first
(`dc2539d3`, `8130d167`). `scripts/dual_allocation_gate.py` caught it at
ALLOCATION time — `⛔ INDEPENDENT 846 — two documents claim one number`, both
sides' adding commits named — which is the whole point of that gate: this is
the case Issue 791 T2's protocol used to reach at merge time. Adjudicated by
Issue 724 T2's rule: the other side carried two commits and an inbound citation
of its landing SHA, this side one unpushed commit and a link it wrote itself,
so 846 stays there and this moved. No `number_collisions_expected.txt` row is
owed — after the renumber the number is not doubly held.

This is [Issue 845](845_channel_aware_duplicated_a_kernel_and_gated_its_avx2_arm_at_compile_time.md)
T4 — the generalisation 845 named and did not do. 845 was a duplicated kernel
that *also* had this defect; this is the defect on its own, in a feature that is
**default-on**.

## The class, stated once

```rust
#[cfg(all(target_arch = "x86_64", target_feature = "avx2"))]   // COMPILE time
{ unsafe { fast_arm(..) } return; }
#[cfg(not(any(target_arch = "aarch64", all(target_arch = "x86_64", target_feature = "avx2"))))]
{ scalar_arm(..) }
```

`target_feature = "avx2"` is **off by default** on x86_64, so the fast arm
compiles to nothing on every ordinary build and the dispatcher silently takes
the scalar path. `katgpt-types` gets this right and shows the correct form —
`if is_avx2_fma_available() { … }`, a cached CPUID probe — so the fix needs no
new machinery.

⛔ **AGENTS.md already documents this shape, and only for GATES**: *"an arm
gated `cfg(all(target_arch = "x86_64", target_feature = "avx2"))` compiles to
nothing without it, and the run then exercises the scalar fallback and proves
nothing."* On a gate the cost is an unproven claim, which is why the x86_64
execution matrix passes `+avx2`. **On a shipped path the cost is latency on
every call, in the configuration everybody builds** — and nothing was looking
for it there.

## Census — 13 sites, in exactly two files

Over 1,459 tracked `src/**/*.rs`: **77** `#[cfg(… target_feature …)]` attribute
sites, of which most are `wasm32`/`simd128` (compile-time by nature — wasm has
no runtime feature detection here) or `aarch64`/NEON (implied by the arch).
Narrowing to **x86_64 features that HAVE runtime detection** (`avx2`, `fma`,
`avx512*`, `sse4.*`):

| file | sites | verdict |
|---|---|---|
| `katgpt-core/src/simd_lut_dequant.rs` | 6 | **the defect** — 3 dispatchers + 3 kernels |
| `katgpt-core/src/bf16_convert.rs` | 6 | the same shape, **different finding** — see T2 |
| `katgpt-types/src/simd/mod.rs` | 2 | **CORRECT** — this *is* the runtime probe's own body |

`#[target_feature(enable = …)]` — 65 sites — is the *right* attribute and is
not this class: it makes a body compile on any build, which is what pairs with
a runtime probe.

## Measured — `crates/katgpt-core/tests/bench_847_avx2_arm_reachability.rs`

Each dispatcher against its own **public scalar** function, 16–3000 iterations
per round, interleaved A/B (`tests/common/ab_timing.rs`), release, 11 of 11
rounds surviving, `simd_level() = Avx2`.

**Dispatcher ns/call, default build, before → after the repair:**

| kernel | n | before | after | `+avx2` (after) |
|---|---|---|---|---|
| `dequant_via_lut` | 256 | 50 | **30** | 28 |
| `dequant_via_lut` | 4096 | 783 | **458** | 421 |
| `dequant_via_lut` | 32768 | 6,461 | **3,459** | 3,912 |
| `dequant_dot_via_lut` | 256 | 169 | **30** | 32 |
| `dequant_dot_via_lut` | 4096 | 2,397 | **529** | 481 |
| `dequant_dot_via_lut` | 32768 | 19,573 | **4,401** | 4,844 |
| `bf16_bits_to_f32_into` | 4096 | 177 | 198 *(unrepaired)* | 100 |

**So a default x86_64 build was giving up 1.7× on `dequant_via_lut` and
4.4–5.6× on the fused `dequant_dot_via_lut`.** And the sharpest confirmation is
the last column: after the repair the **default** build measures what only the
`+avx2` build measured before. That is what a runtime probe is supposed to do,
and it is a stronger check than the before/after alone.

Box state: `shikuwa`, i7-13700K, release, ~17 GB free physical of 31.78, commit
inside its limit, three peer agent sessions live.

### Two instrument defects found while measuring, both worth keeping

⛔ **The within-build RATIO is confounded and the first reading of this target
was wrong because of it.** Under `+avx2` the *scalar* arm is also compiled with
AVX2 available, so LLVM may autovectorise it — `bf16`'s scalar went 200 → 97 ns
at n=4096 while its intrinsic arm went 201 → 169. **Both arms move between
builds**, so the ratio mixes two effects; the quantity that isolates the gate's
cost is the **dispatcher's own absolute ns, default vs `+avx2`**. The target
prints grep-able `ROW847` lines for exactly that diff.

⛔ **And a ratio near 1.00 is evidence only when the two arms are the same
code.** `dequant_via_lut` read **1.5–1.7× while broken**, because a generic
`#[inline]` dispatcher gets its `shift`/`mask` constants propagated into the
inlined scalar body while a direct out-of-line call to the same function does
not. The first version of this bench also passed the scalar arm a
`lut.as_f32_slice().to_vec()` — a heap `Vec` whose length LLVM cannot prove —
which added a bounds-check asymmetry on top. ⚑ **The target's own fail-safe
branch caught it**: it printed *"something OTHER than the AVX2 kernel is
providing the gain — investigate before quoting this as the AVX2 price"* rather
than a clean-looking number. That branch existed because this repo's culture
demands the instrument say when it cannot tell, and it is the only reason the
first figure was not published.

## The repair

Three dispatchers (`dequant_via_lut`, `dequant_dot_via_lut`,
`dequant_dot_via_lut_multi_stage_slice`) now select their arm with the runtime
probe, and the three AVX2 kernels are gated on the **arch alone**:

```rust
#[cfg(target_arch = "x86_64")]
{
    if crate::simd::simd_level() == crate::simd::SimdLevel::Avx2 {
        return unsafe { dequant_dot_via_lut_avx2(..) };
    }
    return dequant_dot_via_lut_scalar(..);
}
```

`simd_level()` is public, cached, and on x86_64 returns `Avx2` **only for
AVX2+FMA** — which is exactly what `#[target_feature(enable = "avx2", enable =
"fma")]` on these kernels requires. Relaxing the kernel cfg to
`#[cfg(target_arch = "x86_64")]` is sound because that attribute, not the cfg,
is what makes the intrinsic body compile.

- `cargo test -p katgpt-core --lib` (default features): **2,063 passed**, above
  the `test_gate` floor of 2,060.
- The 29 `simd_lut_dequant` tests — including three **bit-exact** vs-scalar
  oracles and `g1_multi_stage_matches_scalar_reference` — pass, and this is the
  first time they have ever exercised the AVX2 kernels on a default build.
  ⚑ That is not a formality: the x86_64 execution matrix found **15 latent
  AVX2-transcription defects** the first two times it ran, and these three
  kernels had been asserted by nothing except a `+avx2` run nobody makes.
- `cargo clippy -p katgpt-core --features simd_lut_dequant,bf16_simd
  --all-targets -D warnings`: clean.

## What survives as a GATE

Bench 847 is a **gate** now, not a report, and it bars exactly **one** row:

- **`dequant_dot_via_lut` at n ≥ 4096 must measure ≥ 1.5× its own scalar
  reference on x86_64.** Measured **5.30× / 5.33×** after the repair and
  **1.00–1.01×** before it, so the bar sits in a 3× gap with nothing near it.
- **`dequant_via_lut` is NOT barred** — it read 1.5–1.7× *while broken*, so the
  same bar would have greened on the defect. A guard that passes the thing it
  guards against is worse than none.
- **`bf16_bits_to_f32_into` is NOT barred** — T2, below.
- ⛔ **Canary-verified.** Re-introducing the defect in the barred dispatcher
  (`if cfg!(target_feature = "avx2")` in place of the probe) reds it at
  **1.08×**. The reachability claim is not a pin nobody has watched fail.

## Tasks

- [x] **T1 — Census the class**, narrowed to x86_64 runtime-detectable features
      so the wasm32 and aarch64 sites (correct by construction) are not counted.
- [x] **T2a — Measure both builds, repair `simd_lut_dequant`, gate it, canary.**
- [ ] **T2 — `bf16_convert` is a DIFFERENT finding and must not get this
      repair by reflex.** Its 6 sites have the same shape, and the measurement
      says something else: under `+avx2` the hand-written intrinsic arm runs
      **169 ns** at n=4096 while the plain scalar loop, compiled with AVX2
      available, runs **97 ns** — *LLVM beats the intrinsics at their own
      job*. A runtime probe would still be a ~1.2× win on a default build
      (198 → ~169), so it is not nothing; but the better question is whether
      the intrinsic arm should exist at all, which is
      [Issue 844](844_the_dot_delegation_crossover_is_length_24_not_a_backlog.md)
      rule 3 one operation over. bf16 widening is `u16 → u32 << 16 → f32`,
      lossless and bit-identical between arms, so this is a pure perf decision
      with no correctness axis — measure a third arm (scalar + `+avx2`,
      runtime-probed) before writing any code.
- [ ] **T3 — Decide whether this class needs a per-push GATE.** The census is
      13 sites in 3 files and the correct form is one call, so a mechanical
      check is cheap and — unlike 844's length rule — has **no legitimate
      counter-example in `src/`**: if you want the fast arm on a default build
      you need the runtime probe. ⚠ But the population predicate must exclude
      wasm32 (`simd128` genuinely is compile-time), aarch64 (implied), and the
      probe's own body — three exclusions, each of which a naive grep gets
      wrong, and getting one wrong makes the cries-wolf instrument AGENTS.md
      warns about. **Count first, and do not inherit another issue's
      gate-or-sweep answer.**
- [ ] **T4 — Re-measure on aarch64.** Every figure here is x86_64. The NEON
      arms were never compile-feature-gated, so the *defect* does not exist
      there — but "the vector arm is 5× the scalar" is an x86_64 measurement,
      and the gate's bar is skipped off x86_64 rather than assumed. Shares a
      box with 844 T4 and 845 T5.

## Non-goals

- No change to `katgpt-types/src/simd/mod.rs`. Its two
  `#[cfg(target_feature = "avx2")]` sites **are** the runtime probe's own body
  (`#[cfg(target_feature = "avx2")] { true }` — a build that already has AVX2
  need not ask CPUID), which is the correct pattern and the thing everything
  else should call.
- No change to any wasm32/`simd128` site. That arch has no runtime feature
  detection in this workspace, so a compile-time gate is the only option and
  `full_gate.sh` layer 2b already builds both arms.
