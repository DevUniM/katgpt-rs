# Benchmark 872: SIMD bitstream whitespace splitter GOAT Gate

**Feature:** `fast_bpe` (opt-in — same posture as Bench 191; NOT default)
**Date:** 2026-09-22
**Origin:** Issue 872 (closed same day; this benchmark is the lasting record).
Technique lineage: HF `tokenizers` v1 "bitcannon" (blog 2026-09-21) / Parabix /
simdjson / gigatoken (the crate's own vendored upstream — see Research 580).
**Hardware:** Windows/MSYS, i7-13700K (x86_64, AVX2 confirmed via runtime probe),
**loaded box** — CPU ~24% at session start, one sibling agent session active
("4090 Idle Queue Sync Sweep"), RAM 11.5/31.8 GiB. Rust stable, release profile,
`CARGO_TARGET_DIR` isolated. Read every ratio below with that load class (the
AGENTS.md box-state law: a latency number without its box state is not a
measurement).

> Numbering note: this research note was first allocated as 579 and renumbered
> to 580 on landing day — a sibling session allocated `.research/579`
> concurrently (the Issue-556 class; the incumbent keeps the number).
> "Research 580" below refers to `580_Bitstream_Whitespace_Splitting.md`.

## What landed

`crates/katgpt-tokenizer/src/fast_bpe/simd_split.rs` — the scan half of
`FastBpeEncoder::encode_into_pretok` rewritten as a bit-parallel splitter:

- `WhitespaceSplitter` iterator over `SplitEvent::{Word(&[u8]), AsciiWsRun{byte,count}, MultibyteWs(char)}` — zero-alloc, word events borrow byte ranges straight from the input (the per-char accumulation buffer `pretoken_bytes` is deleted).
- Per-chunk classification masks (`stop = is_ascii_ws(b) || b >= 0x80`), 16B SSE2 (x86_64 baseline) / 32B AVX2 (runtime-probed, `#[target_feature(enable="avx2")]` kernel — the `shipped_target_feature_gate` law) / 16B NEON (aarch64 baseline, u64-lane SWAR movemask) / scalar elsewhere (incl. wasm32) through the same iterator.
- Bytes ≥ 0x80 fall to a scalar per-char path using the exact `char::is_whitespace` predicate — full Unicode `White_Space` bit-identity by construction (NBSP/U+3000/U+2028/9/…).
- Identical-byte ASCII ws runs coalesce (`AsciiWsRun`) — one vocab lookup per run instead of per char.

## The trap this issue exists to hold (found live, twice)

1. **ASCII `White_Space` is SIX bytes** — `{0x09..=0x0D, 0x20}`, including
   vertical tab `0x0B`. `u8::is_ascii_whitespace` is FIVE (excludes `0x0B`)
   and is banned here; the SIMD predicate is `(b == 0x20) | (b.wrapping_sub(0x09) <= 4)`
   (pinned by `ascii_ws_predicate_is_six_bytes`).
2. **`b >= 0x80` ⇔ the raw byte is negative as i8** — the first draft used
   `cmpgt(b^0x80, 0)`, which misses exactly `b == 0x80` (bx == 0). Caught by the
   random-buffer mask differential (`masks_match_scalar_random_buffers`, byte
   0x80 in the first random buffer that contained it).
3. **`1u32 << 32` shift overflow** (AVX2 width): in release it wraps to
   `1<<0`, making the ws-run "all-matching" mask `0` — every NON-matching chunk
   read as all-matching and the run count ate the rest of the text. Caught by
   `events_agree_on_random_ascii` (a 1-tab text produced a 35-tab run). In
   debug this panics loudly; release wraps silently — the profile axis again.
4. **Multibyte ws at word end was swallowed** (`decode_char_at` advanced past
   the char before the `is_whitespace` check) — the differential
   (`aa\u{85}bb`) caught both the word-slice and the missing-event forms.

All four were caught by the differential harness, not by review — which is the
argument for the harness.

## Gates

- **G1 (correctness) ✅** — three layers of differential, all green:
  - mask-level: SIMD masks == scalar masks over all 256 byte values + 64 random buffers per level;
  - event-level: SIMD levels == scalar level == a semantic reference (`chars()` + `is_whitespace`) over every Unicode ws char (25), near-miss non-ws (U+180E, U+200B, U+FEFF, …), CJK/emoji/regional indicators, ws runs 1..70, chunk-boundary tails at 14..34 offsets, random ASCII at 11 lengths;
  - end-to-end: `encode_into_pretok` bit-identical to `BpeTokenizerImpl::encode` on trained tokenizers (ASCII/code/corpus + the full Unicode ws set + long ws-run amortization) — `tests/fast_bpe_goat_simd_split.rs` 3/3.
- **G2 (perf) ✅** — scan-only A/B (~940KB varied ASCII, interleaved rounds, median of 9, THIS loaded box):
  - `avx2` vs scalar-level: **1.60×** (spread 1.06–1.97)
  - `avx2` vs the OLD loop's shape (per-char decode+classify+accumulate): **1.69×**
  - gate: median ≥ 1.25 (catches dispatch-silently-falls-to-scalar; expected ≥3× on a quiet box — the NEON number belongs to the M3 lane, same unit test).
- **G3 (no-regression) ✅** — `fast_bpe_goat_pretok` 5+1 ignored, `fast_bpe_pretok_hypothesis` 3/3, `fast_bpe_goat_g4_alloc` 1/1 (the zero-alloc audit still holds — the rewrite REMOVED an allocation site), lib 25/25. Default-features and `--all-features` clippy clean.
- **Platform axes**: wasm32-unknown-unknown `cargo check` ✅ (scalar level; NEON/SSE variants cfg'd out); aarch64-apple-darwin `cargo check` ✅ (**NEON arm typechecks** — check never links; NEON *execution* is unmeasured on this box, covered by the M3 lane via the same differential unit tests).

## Honest scope

- This is the *scan half* of the pretok path. The merge loop + pretoken cache
  (Bench 191 Phases 2.5–2.7) are unchanged and still dominate cold/novel
  inputs; the scan win compounds where Bench 191's G6 said it would — the
  warm-cache / corpus-scale regime, where the scan was the dominant remaining
  CPU cost — plus the per-run memcpy batching and per-ws-run vocab-lookup
  amortization the scan-only number does not show.
- NOT bitcannon's regex grammars (GPT-2/cl100k/o200k/…). Those belong to
  tokenizer *formats* this crate does not load; see Research 580 §scope.
- fast_bpe stays **opt-in** (Bench 191's Phase 3 deferral stands — no
  corpus-scale consumer has opened the pull).

## Known issue (pre-existing, NOT this change)

`fast_bpe_goat.rs::g2_perf_smoke_per_call_short_input_documented_regression`
fails on this box **at clean HEAD too** (verified in an isolated
`git worktree` at `e2f77e70`): 100× the per-call 16MB `PairRankTable`
dense-grid allocation measured 9827× vs the ≤1000× gate (5.1ms/call under
load; calibrated on the M3). The amortized-path gate
(`g2_perf_smoke_amortized_no_regression_on_short_input`) passes. Box-state
sensitivity of a documented-regression gate — file separately if it repeats.

## Reproducing

```sh
CARGO_TARGET_DIR=/tmp/872 cargo test -p katgpt-tokenizer --features fast_bpe --release --lib simd_split -- --nocapture
CARGO_TARGET_DIR=/tmp/872 cargo test -p katgpt-tokenizer --features fast_bpe --release --test fast_bpe_goat_simd_split
CARGO_TARGET_DIR=/tmp/872 cargo check -p katgpt-tokenizer --features fast_bpe --target aarch64-apple-darwin
CARGO_TARGET_DIR=/tmp/872 cargo check -p katgpt-tokenizer --features fast_bpe --target wasm32-unknown-unknown
```
