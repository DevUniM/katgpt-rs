# Issue 847: `simd_lut_dequant`'s AVX2 kernels compiled to NOTHING on every ordinary x86_64 build — a default-on feature running its scalar fallback

**Status:** **RESOLVED** for `simd_lut_dequant` (measured, repaired, gated,
canary-verified) and for `bf16_convert`'s RNE narrowing (T2: 2.4-2.5x on a
default build). **T5, T6, T4 open** — the losing trunc kernel, the widen
crossover and the aarch64 re-measure; T3's gate is landed and the class
is WALLED (`scripts/shipped_target_feature_gate.py`). ⛔ T2's finding is that the reflex repair
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
- [ ] **T5 — Delete `f32_to_bf16_trunc_avx2`?** It is measured SLOWER than
      the scalar body it replaces (1.3x at n >= 4096, both the intrinsics and
      the autovec arm), it is unreachable on every ordinary build, and an
      unreachable kernel is an untested one — the x86_64 execution matrix
      found 15 latent AVX2-transcription defects the first two times it ran.
      Issue 844 rule 3 applies. ⚠ Measure the aarch64 sibling before
      deleting: NEON is implied by the arch, so `f32_to_bf16_trunc_neon` IS
      reached and may well win where the AVX2 one does not.
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
