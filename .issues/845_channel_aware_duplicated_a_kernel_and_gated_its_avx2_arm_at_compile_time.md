# Issue 845: `channel_aware.rs` duplicated `simd_dot_f32` and gated the copy's AVX2 arm at COMPILE time — so the shipped path ran a scalar loop

**Status:** **RESOLVED** in the same change that filed it (measured both
configurations, repaired, gated, canary-verified). Filed rather than fixed
silently because the *class* is what matters and because AGENTS.md already
cites this file for a defect whose diagnosis stopped one level short of the
cause.

Found while reading the CHUNKED bucket of [Issue 844](844_the_dot_delegation_crossover_is_length_24_not_a_backlog.md)'s
census — 844 T2, which is what that task was for.

## The defect, in two halves

`crates/katgpt-attn/src/dash_attn/channel_aware.rs` carried its own
`pub fn simd_dot_f32(a: &[f32], b: &[f32]) -> f32` over ~200 lines, with
hand-written NEON **and** AVX2 intrinsic transcriptions plus a 4-accumulator
scalar fallback.

**Half 1 — it was a duplicate of something already in the graph.**
`katgpt-attn` depends on `katgpt-core`, which re-exports `katgpt_types::simd`
wholesale, so `katgpt_core::simd::simd_dot_f32` — four arms (NEON / AVX2+FMA /
wasm32-simd128 / scalar), its own tests, executed by the x86_64 execution
matrix — was one `use` away. **Seven other files in the same crate, four of
them in the same `dash_attn/` directory** (`routing.rs`,
`kv_outer_prefill.rs`, `msa_distill.rs`, `flashmemory_sparse.rs`), already
called it. The convention was established; this one file shadowed it with a
same-named function.

**Half 2 — and this is the live one — the duplicate's AVX2 arm was gated at
COMPILE time:**

```rust
#[cfg(all(not(target_arch = "aarch64"), target_arch = "x86_64"))]
{
    #[cfg(target_feature = "avx2")]        // <- compile-time predicate
    { unsafe { simd_dot_avx2(a.as_ptr(), b.as_ptr(), n) } }
    #[cfg(not(target_feature = "avx2"))]
    { simd_dot_scalar(a, b, n) }
}
```

`target_feature = "avx2"` is **off by default** on x86_64. So on every ordinary
build the AVX2 arm compiled to nothing and the shipped path took the scalar
loop — while the kernel it duplicated probes CPUID once, caches it, and uses
AVX2 on the same build:

```rust
#[cfg(target_arch = "x86_64")]
{
    if is_avx2_fma_available() { unsafe { avx2_dot_f32(a, b, len) } }  // runtime, cached
    else { scalar_dot_f32(a, b, len) }
}
```

⛔ This is AGENTS.md's own double-gating hazard — *"an arm gated
`cfg(all(target_arch = "x86_64", target_feature = "avx2"))` compiles to nothing
without it, and the run then exercises the scalar fallback and proves
nothing"* — except that sentence is written about **gates**, where the cost is
an unproven claim. Here the same shape sat on a **shipped inference path**,
where the cost is latency on every call.

## Measured before the repair — `tests/bench_845_channel_aware_dot_dispatch.rs`

Local duplicate against the shipped kernel, 16 dots per timed call so the fixed
per-call cost is amortised as it is in `forward_indexer`, interleaved A/B
(`tests/common/ab_timing.rs`), release, 11 of 11 rounds surviving. **Both build
configurations, because the local AVX2 arm only exists in one of them** —
reporting either alone would have been the partial claim this repo files
issues about:

| dot length | default build | `-C target-feature=+avx2` |
|---|---|---|
| 32 | local **2.72×** slower | local **1.83×** slower |
| 64 | **4.12×** | **2.68×** |
| 128 | **6.54×** | **3.86×** |
| 256 | **7.76×** | **4.78×** |
| 1024 | **6.37×** | **4.00×** |

Numerical agreement: `≤ 1e-6` in the default build (different summation
orders), and **bit-identical** under `+avx2`. So the substitution was lossless
as well as faster, and the finding does not depend on the compile-time gate
being the whole story: **even where the hand-written AVX2 arm exists, it is
1.8–4.8× slower than the shipped one.** The gate made it worse; it was not what
made it wrong.

Box state: `shikuwa`, i7-13700K, release profile, `simd_level() = Avx2`,
~17 GB free physical of 31.78, commit well inside its limit, three peer agent
sessions live.

## The repair

`simd_dot_f32` **kept** (it is `pub`, and its 2-argument `(a, b)` form with
`len = min` is what its callers use) and its body replaced by a one-line
delegation. `simd_dot_neon`, `simd_dot_avx2` and `simd_dot_scalar` deleted.

- `channel_aware.rs`: **838 → 695 lines** (190 removed, 47 added, most of the
  addition being the doc that records why).
- **The file's `unsafe` surface is now ZERO** — the two remaining matches for
  the string are in prose.
- `katgpt-attn --features dash_attn --lib`: **159 passed before, 159 passed
  after.** The three in-file dot tests are tolerance-based (`1e-4`, `1e-6`) and
  an exact-zero empty case; all three pass against the shipped kernel.
- `cargo clippy -p katgpt-attn --features dash_attn --all-targets -D warnings`:
  clean.
- Post-repair ratio: **0.97–1.02× and bit-identical at every length**, so the
  2-argument wrapper costs nothing measurable.

## What survives as a GATE, and why bit-identity rather than a tolerance

The bench's original subject no longer exists, so it was **converted rather
than deleted**: it now asserts the property the repair established — that the
local entry point and the shipped kernel are *the same code path*.

1. **Bit-identity** (`sink_local == sink_shipped`). A delegation returns exactly
   what it delegates to. Any re-introduced private kernel changes the summation
   order and reds. Arch-free by construction: it compares a function against
   itself through a wrapper, so it means the same thing on NEON, AVX2 and
   scalar.
2. **A loose timing band, 0.80–1.30.** Not redundant with (1): it catches the
   *wrapper* becoming expensive (a lost `#[inline]`, a bounds-check cascade)
   rather than a new kernel. Wide on purpose — a tight band would be a bar on
   the box, and the regression this guards against measured 2.7–7.8×.

⛔ **Canary-verified, and the canary is the argument for gate 1's form.** A
4-accumulator private kernel was planted in the wrapper and the gate red at
`len=32` with **max |Δ| = 4.77e-7**. That difference is *well inside* every
tolerance the three in-file tests use (`1e-4`, `1e-6`) — so a tolerance-based
gate would have passed the exact regression this issue exists to prevent. Bit
equality is not pedantry here; it is the only form that fires.

## The generalisation, which is the part worth keeping

- **A `target_feature` cfg on a SHIPPED path is a different thing from one on a
  gate.** On a gate it costs a claim; on a shipped path it costs latency on
  every call, silently, in the configuration everybody builds. Prefer the
  runtime probe (`is_avx2_fma_available()`) — it is cached, it is what
  `katgpt-types` already does, and it cannot compile to nothing.
- **A same-named duplicate is the hardest kind to notice**, because every call
  site reads correctly and `use` resolution decides which kernel runs. Four
  sibling files in one directory disagreeing about which `simd_dot_f32` they
  mean is not a thing a reviewer sees.
- AGENTS.md cites this file for **30 `unsafe_op_in_unsafe_fn` findings** and
  blames *"two transcriptions of one kernel [where] only `simd_dot_neon` had
  the `unsafe { }` block"*. That diagnosis is right and stops one level short:
  **both transcriptions were of a kernel already in the graph.** The repair for
  "a defect was applied to only the arm somebody can see" is not to fix the
  other arm — it is to stop carrying arms.

## Tasks

- [x] **T1 — Measure both build configurations** before touching anything.
- [x] **T2 — Repair by delegation**, API-preserving, and re-run the crate's lib
      suite (159 = 159) and clippy.
- [x] **T3 — Convert the bench into a regression gate** and verify the canary
      fires on a planted private kernel.
- [x] **T4 — DONE, and it found a live defect in a DEFAULT-ON feature:
      [Issue 847](847_a_compile_time_target_feature_on_a_shipped_path_costs_latency_every_call.md).**
      Census: 13 x86_64 runtime-detectable `target_feature` cfg sites over 1,459
      tracked `src/**/*.rs`, in exactly two files — `simd_lut_dequant.rs` (6,
      repaired: a default build was giving up **4.4–5.6×** on the fused
      `dequant_dot_via_lut`) and `bf16_convert.rs` (6, a DIFFERENT finding: its
      intrinsics lose to LLVM's autovectorised scalar). The remaining 64 of 77
      sites are wasm32/`simd128` (compile-time by nature), aarch64/NEON (implied
      by the arch), or the runtime probe's own body — which is why the
      gate-or-sweep question is 847 T3 and not answered here. Original text:
      Sweep for the SHIPPED-PATH `target_feature` shape workspace-wide.
      This one was found by reading a census bucket for a different issue. The
      class — a compile-time `target_feature` cfg selecting between a fast arm
      and a fallback in `src/`, rather than in a test or a gate — is mechanically
      findable, and unlike Issue 844's length rule it has no legitimate
      counter-example in `src/`: if you want the fast arm on a default build you
      need the runtime probe. ⚠ Count the population before deciding whether it
      is a gate or a sweep (the `console_encoding_gate` lesson — do not inherit
      "population of one" from another issue).
- [ ] **T5 — Re-measure on aarch64.** Every number here is x86_64. The NEON arm
      of the deleted duplicate was *not* compile-time gated (`target_arch =
      "aarch64"` implies NEON), so half 2 does not apply there and only the DRY
      half does — but "the shipped kernel is faster" is an x86_64 measurement
      and should not be quoted as an aarch64 one. Shares a box with Issue 844 T4.

## Non-goals

- No change to the other CHUNKED sites from the 844 census in this pass.
  `simd_lut_dequant.rs`'s five are a *different operation* (dequantize through a
  LUT, then dot) and `katgpt-moka-wasm`'s three are a standalone wasm bundle
  whose dependency surface is its own decision. Both need their own read; see
  844 T2.
- `katgpt-types/src/simd/**` is the kernel OWNER. Its per-ISA transcriptions are
  the thing everything else should call, not instances of this defect.
