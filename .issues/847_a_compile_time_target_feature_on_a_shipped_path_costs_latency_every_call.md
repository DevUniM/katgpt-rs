# Issue 847: `simd_lut_dequant`'s AVX2 kernels compiled to NOTHING on every ordinary x86_64 build — a default-on feature running its scalar fallback

**Status:** **RESOLVED** for `simd_lut_dequant` (measured, repaired, gated,
canary-verified) and for `bf16_convert`'s RNE narrowing (T2: 2.4-2.5x on a
default build). **T4 + T5 DONE 2026-09-19** — the aarch64 re-measure landed
(`t4_neon_vs_scalar_aarch64`: RNE NEON wins 1.23x everywhere; widen + trunc
NEON lose to LLVM's own loop) and the trunc AVX2 kernel is DELETED (T5, with
the transcription hypothesis refuted — the loss is the `+avx2` build).
**T6 alone remains** — the widen crossover on a quiet x86_64 box. T3's gate
is landed and the class is WALLED
(`scripts/shipped_target_feature_gate.py`). ⛔ T2's finding is that the reflex repair
was right for ONE of three kernels, a REGRESSION for the second, and
undecidable on this box for the third.

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
- [x] **T2 — DONE, and it split THREE ways, which is why the issue refused
      to apply the reflex repair.** The third arm the task demanded is the
      scalar body compiled WITH AVX2 available
      (`#[target_feature(enable = "avx2", enable = "fma")]` on a wrapper —
      the attribute exists precisely to compile a body for an ISA the build
      does not target), so a runtime probe can reach LLVM's autovectoriser on
      an ordinary build. Measured on all three dispatchers x three sizes x
      both builds, twice each.

      **ns/call, shikuwa i7-13700K, release, ranges over two runs:**

      | kernel | n | default (SCALAR) | +avx2 (INTRINSICS) | AUTOVEC |
      |---|---|---|---|---|
      | widen | 256 | 13–17 | **6–7** | 10–14 |
      | widen | 4096 | 172–183 | 97–173 | 99–168 |
      | widen | 32768 | **1668–1670** | 1837–2432 | 1684–2077 |
      | rne | 256 | 66–67 | **29–30** | 39–43 |
      | rne | 4096 | 1037–1061 | **430–465** | 617–663 |
      | rne | 32768 | 8582–8732 | **3495–3699** | 4937–5368 |
      | trunc | 256 | 13 | 13 | 12–13 |
      | trunc | 4096 | **145** | 197 | 194 |
      | trunc | 32768 | **1179** | 1550 | 1557 |

      **`f32_to_bf16_rne_into` REPAIRED — the intrinsics win decisively and
      consistently, 6 of 6 cells.** Runtime-probed; a default build now
      measures **28 / 440 / 3397** against the scalar path's 66 / 1037 /
      8582, i.e. **2.4x / 2.4x / 2.5x**, and those figures land on the +avx2
      build's 29 / 430 / 3495 — the same "the default build now measures what
      only `+avx2` measured before" signature T2a established. The nine
      `bf16_convert` tests pass, including the G1 bit-exact oracles against
      `half::bf16::from_f32`, which have **never before executed the AVX2 RNE
      kernel on a default build**.

      ⛔ **`f32_to_bf16_trunc_into` is NOT repaired, and the reflex repair
      would have been a REGRESSION.** Its intrinsics LOSE to the scalar path
      at every size that matters — 197 vs 145 at n=4096, 1550 vs 1179 at
      32768 — and the autovec arm loses by the same margin, which is the
      corroboration: a bare `>> 16` truncation is already whatever LLVM wants
      it to be, and the wrapper only adds a call. Probing it in would have
      cost 1.3x on a shipped path in the name of fixing a defect. **The
      compile-time gate is accidentally doing the right thing here**, and the
      honest follow-up is T5 (delete the losing kernel), not a probe.

      ⚠ **`bf16_bits_to_f32_into` is UNDECIDED and the instrument says so.**
      The best arm changes with n — intrinsics at 256 (6 vs 13), autovec
      around 4096, plain scalar at 32768 (1670 vs 1837–2432) — and the same
      binary measured **97 and 173 ns** for one cell on two runs, a 78% swing
      on a box carrying peer agent sessions. That is AGENTS.md's own *"a
      latency number without its BOX STATE is not a measurement"*, and it is
      the reason no widen repair is in this change: the crossover is real
      (Issue 844's shape one operation over) and needs a quiet box, which is
      T6.

      Instrument: `crates/katgpt-core/tests/bench_847_avx2_arm_reachability.rs`
      `t2_bf16_autovec_vs_intrinsics`, a REPORT with grep-able `ROW847T2`
      lines. It bars nothing — a bar written before the sweep would be a bar
      written from a hypothesis, and this hypothesis was wrong for two of
      three kernels. What it DOES assert is bit-identity between the
      dispatcher and the autovec arm, which no box state can invalidate.
      ⛔ That assertion had to compare **BITS, not values**: `assert_eq!` on
      `Vec<f32>` is `PartialEq`, under which `NaN != NaN`, and a random `u16`
      fixture widens to NaN — so the first run failed on two byte-identical
      256-element vectors. A value comparison could not have expressed the
      bit-exactness claim even on the runs where it passed.
- [x] **T5 — DONE. DELETED, and the re-measurement sharpened the finding:
      the loss is not the TRANSCRIPTION, it is the `+avx2` BUILD.**

      Re-measured three times over two build configurations, box state
      recorded per §Feature Flag Discipline G2 (shikuwa, 22.3 GB free
      physical, commit 28.3 / 62.8 GB limit, no heavy sibling job in the
      top-5 by commit):

      | trunc n | default build | `+avx2` build |
      |---|---|---|
      | 256 | 11–14 | 12 |
      | 4096 | 153–184 | 197–205 |
      | 32768 | **1138–1255** | 1578–1594 |

      ⛔ **The decisive cell is what the `_autovec` arm does, and it refutes
      the transcription hypothesis the T2 write-up left standing.** That arm
      is the SAME scalar body carrying `#[target_feature(enable = "avx2")]`,
      and it measures **1556–1591 in BOTH builds** — it lands on the
      intrinsics, never on the scalar. After the deletion, a `+avx2` build's
      dispatcher (now the plain scalar body) measures **1594** and the ratio
      against autovec is **exactly 1.00**, because they are the same code.

      So nothing was wrong with the AVX2 transcription of `bits >> 16`. What
      is measured is that **LLVM's default-target vectorisation of this loop
      beats its own AVX2 vectorisation by ~1.3–1.4x**, however the loop is
      spelled — the 256-bit `_mm256_srli_epi32` → `vextracti128` →
      `_mm_packus_epi32` sequence pays a lane-crossing shuffle that the
      128-bit default codegen does not. A hand-written kernel could not have
      won; it was competing with a better compiler output, not a worse one.

      **The deletion costs nothing on either build and removes an untested
      kernel** (default build 1138 → 1255, run noise on a path that never
      reached the kernel; `+avx2` 1578 → 1594). It removes three rows from
      `shipped_target_feature_expected.txt` — 162 attributes / 5 pins / 0
      stale — and the block is kept there as a comment so a reader arriving
      from this write-up finds the resolution where the rows were.

      ⚠ **No aarch64 measurement was needed to do it, and the task's warning
      was about the FAMILY rather than this arm.** NEON is implied by the
      arch, so `f32_to_bf16_trunc_neon` is reached, has always been reached,
      is exercised by `g1_trunc_neon_matches_scalar`, and is untouched — the
      per-ISA rule Issue 844 T4 established after its own expectation was
      refuted. Generalising "the trunc SIMD arm loses" across ISAs is exactly
      what that rule forbids; this deletion does not.

      The 9 `bf16_convert` tests pass in both builds.
      `t2_bf16_autovec_vs_intrinsics` keeps measuring the absence every run,
      so a future re-transcription has to argue with a number.

- [ ] **T6 — The widen crossover, on a QUIET box.** Three arms with three
      different winners across 256 / 4096 / 32768, and a 78% run-to-run swing
      in one cell here. Record free RAM, commit-vs-limit and concurrent heavy
      jobs beside the figures (§Feature Flag Discipline G2), or the answer is
      a measurement of the box.
- [x] **T3 — DONE. It needed one, and the census is what made it
      cheap: `scripts/shipped_target_feature_gate.py`** (docs-gate CHECK).

      **Counted first, as the task demanded, and NOT inherited.**
      `check_validation_gate` T4 declined a sweep on a population of ONE and
      was right; `console_encoding_gate` inherited that answer and was wrong
      by seven repos. Measured over the 17 contract repos on this box:
      **166 `target_feature` cfg attributes in `src/`, ALL 166 in
      katgpt-rs**, zero in every sibling — so there is a gate and no sweep,
      and `--workspace` re-derives the table rather than leaving the figure
      in prose.

      The three exclusions the task warned about are each counted on the
      verdict line rather than remembered: **67** `#[target_feature(enable =
      ..)]` (the correct attribute, and the ORDER of the predicate matters —
      it contains the string `target_feature` too, so testing feature values
      first would read its enable list as a cfg and flag every correct kernel
      in the repo), **87** wasm32/`simd128`, **0** NEON.

      ⛔ **The fourth exclusion could not be a predicate and had to be a
      PIN.** `#[cfg(target_feature = "avx2")] { true }` inside
      `is_avx2_fma_available()` is the same attribute doing the opposite job
      — the runtime probe's own short-circuit. Nothing distinguishes it from
      the defect structurally, so it is two pinned rows with the reason
      written down.

      **Live: 8 CLASS sites, every one pinned with a MEASUREMENT** — 2 the
      probe's own body, 3 the trunc family (T5: the intrinsics are measured
      SLOWER, so the compile-time gate is accidentally right), 3 the widen
      family (T6: undecided on a loaded box). No row reads "not fixed yet",
      which Issue 785's rule forbids.

      The key is **LINE-FREE** — `<path>::<enclosing fn>#<ordinal>` —
      resolved by brace counting over `platform_dead_code_audit.mask_file`'s
      masked text, so a `#[cfg(..)]` inside a raw-string fixture is test
      input rather than a site (the class three sibling instruments here have
      each met). ⚠ The two cases need OPPOSITE lookups and both are armed: an
      attribute INSIDE a body belongs to its innermost enclosing fn, one ON
      an item to the NEXT fn declared after it. Line-invariance is armed
      directly — padding above a site must not move its key.

      `--prove-fires 32056164` is two-sided against an independently known
      answer: **23 CLASS sites at the parent, 20 after**, naming the three
      `channel_aware.rs` rows that commit repaired. (That the live count is
      now **8** rather than 20 is the 847 + 847 T2 repairs, not classifier
      drift.)

      ⚠ **STATED blind spot**: a dispatcher that reads
      `cfg!(target_feature = ..)` as a runtime-looking boolean is not seen —
      it is a compile-time constant wearing an `if`, and it is exactly the
      shape 847's own canary used to re-introduce the defect.
- [x] **T4 — DONE 2026-09-19 (M3 Max, aarch64/NEON, release, `bench_847_avx2_arm_reachability::t4_neon_vs_scalar_aarch64` — the new aarch64 arm, interleaved `ab_median_ratio` harness, bit-identity asserted per family).** Box state: 84% free mem (~54 GiB/64), load 3.91 declining (of 16 cores), no concurrent cargo (Zed + RustDesk only, the exempt class). Figures are dispatcher(NEON) vs scalar-reference; on aarch64 the scalar arm is compiled WITH NEON available, so LLVM autovectorises it — the ratio column is autovec-scalar/NEON-intrinsics, the module-doc confound one arch over, and both absolute figures print beside it:

      | kernel | n=256 | n=4096 | n=32768 |
      |---|---|---|---|
      | widen `bf16_bits_to_f32` | 15 vs 14 (0.89) | 363 vs 294 (0.80) | 1465 vs 1331 (0.91) |
      | rne `f32_to_bf16_rne` | 51 vs 62 (**1.23**) | 742 vs 909 (**1.23**) | 5425 vs 6675 (**1.23**) |
      | trunc `f32_to_bf16_trunc` | 14 vs 11 (0.81) | 181 vs 128 (**0.71**) | 1265 vs 953 (**0.76**) |

      Three findings, and the third is the aarch64 confirmation of T5's
      mechanism: (1) **RNE's NEON kernel EARNS its keep** — a stable 1.23x at
      every size (the branchy NaN-handling scalar body does not autovectorise);
      the aarch64 arm of the 847 repair class is healthy. (2) **widen's NEON
      kernel loses to LLVM's own loop** (0.80–0.91) — the aarch64 sibling of
      the x86_64 widen finding, now on both arches. (3) **trunc's NEON kernel
      loses everywhere** (0.71–0.81) — same mechanism as T5's x86_64 finding
      (the compiler's default-target vectorisation of `bits >> 16` beats the
      hand-written SIMD), measured on the second arch: the NEON trunc kernel
      is REACHED on aarch64 and slower than the autovectorised scalar loop,
      so its deletion would be a ~1.3x win on the shipped aarch64 path — one
      cfg-arm + one fn once taken, recorded here as the measured follow-up.
      The x86_64 `avx2_cfg` bar-skips stay as they were (x86_64-only); on
      aarch64 there was never a defect, and now there are figures where there
      were none.

## Non-goals

- No change to `katgpt-types/src/simd/mod.rs`. Its two
  `#[cfg(target_feature = "avx2")]` sites **are** the runtime probe's own body
  (`#[cfg(target_feature = "avx2")] { true }` — a build that already has AVX2
  need not ask CPUID), which is the correct pattern and the thing everything
  else should call.
- No change to any wasm32/`simd128` site. That arch has no runtime feature
  detection in this workspace, so a compile-time gate is the only option and
  `full_gate.sh` layer 2b already builds both arms.
