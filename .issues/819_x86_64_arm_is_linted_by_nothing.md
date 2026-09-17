# The x86_64 arm is LINTED by nothing — 30 `unsafe_op_in_unsafe_fn` in one file

**Status:** OPEN — T1 measured, T2 repaired, T3 is the lane.

Filed 2026-09-17 from the Issue 808 session: measuring `cargo clippy -p
katgpt-attn --all-features --lib` on this x86_64 workstation with
`RUSTFLAGS="-C target-feature=+avx2"` returned **30 warnings**, every one of
them `E0133` / `unsafe_op_in_unsafe_fn` on edition 2024, every one of them in
`crates/katgpt-attn/src/dash_attn/channel_aware.rs`, and every one of them
inside the **x86_64 AVX2 arm**.

## The finding is not the 30 — it is the SIBLING

`channel_aware.rs` carries two transcriptions of one kernel:

| arm | cfg | body |
|---|---|---|
| `simd_dot_neon` | `target_arch = "aarch64"` | `// SAFETY: …` + a whole-body `unsafe { … }` |
| `simd_dot_avx2` | `all(target_arch = "x86_64", target_feature = "avx2")` | **neither** |

The edition-2024 repair was made on the arm and not on its twin, and the
reason is mechanical rather than an oversight anyone could have caught by
reading: `full_gate.sh` is macOS/**aarch64**, so it compiles `simd_dot_neon`
and lints it, and `simd_dot_avx2` compiles to **nothing** there — under
`--all-features` too, because the gate is arch-gated, not feature-gated. The
warning exists only on a lane that does not exist.

⚠ And `target_feature = "avx2"` is a **second** gate on the same item: even a
lane that selected an x86_64 triple compiles this to nothing without
`RUSTFLAGS="-C target-feature=+avx2"`. It is exactly the double gating
AGENTS.md's table records for wasm32/simd128 — *"even a wasm32 lane without
`RUSTFLAGS='-C target-feature=+simd128'` compiles the SIMD half to nothing"* —
reproduced one platform over, and measured: the avx2-**off** arm is clean and
the **on** arm has 30 findings, against Issue 737's measured 0-and-14.

## What each lane can see

| lane | arch | avx2 | sees these 30 |
|---|---|---|---|
| `full_gate.sh` layers 2/3/6 | macOS aarch64 | n/a | **no** — compiles to nothing |
| `full_gate.sh` layer 2b | wasm32 | n/a | **no** |
| `wasm32_gate.yml` | wasm32 | n/a | **no** |
| `test_gate.sh` | host | default (off) | **no** — and it does not lint |
| `x86_64_execution_matrix.sh` | x86_64 | **on** | **no** — it EXECUTES, it does not lint |
| a human typing the command | x86_64 | on | yes |

The execution matrix is the closest thing and it is the wrong axis: AGENTS.md
records `compile vs EXECUTE` as the table's last row, and this is the
**inverse** hole — an arch whose execution is now covered and whose *lint*
surface is not. Bench 806 closed the first half on 2026-09-16 and left the
second half unstated.

## Tasks

- **T1 — measure. DONE (2026-09-17).** 30 findings, one file, 5 distinct
  sites (12 `ptr::add`, 10 `_mm256_loadu_ps`, 5 `_mm256_fmadd_ps`, 2 raw-ptr
  deref, 1 `_mm_storeu_ps`). avx2-off arm: 0. Every other package clean.
- **T2 — repair `simd_dot_avx2`. DONE (2026-09-17).** Whole-body `unsafe { … }`
  + a `// SAFETY:` comment, byte-for-byte the shape its NEON sibling has
  carried since it was written. Not a `cargo heal` job: the healer is silent
  on this class and the repair is one block, not 30 edits.
- **T3 — the LANE.** `full_gate.sh` Layer **2c**, mirroring Layer 2b's
  structure exactly (derived `-p` list from the positive `target_arch =
  "x86_64"` surface, BOTH avx2 arms, `-D warnings`, residue pinned by
  MEMBERSHIP, a missing target is a PARTIAL gate that refuses). Layer 2b is
  the template because the hazard is identical — a double-gated hot kernel on
  a triple no default run selects.
  - ⛔ The triple is **not** a free choice and it is the one design decision
    here. Layer 2b names `wasm32-unknown-unknown` literally because there is
    one; x86_64 has three in play (`-pc-windows-msvc`, `-apple-darwin`,
    `-unknown-linux-gnu`) and they differ in `target_os`, which gates *other*
    code in this repo. The lane uses the **host triple when the host is
    x86_64** and a named cross triple otherwise, and says which it used on its
    own verdict line — a lane that does not disclose its triple is a lane
    whose green means something different on every box.
- **T4 — the other arms.** T1 measured `katgpt-attn` under `--all-features
  --lib`. `scripts/x86_64_execution_matrix.sh` derives **six** packages owning
  x86_64 source plus one BY-DEP row; T3's lane makes their lint surface
  readable for the first time and whatever it prints is T4's population. Do
  not pre-judge the count — Issue 737 measured 14 on wasm32 where 0 was the
  expectation.

## Why this is not a `full_gate` bug report

`full_gate.sh` refuses off macOS and says so, and its PARTIAL line names the
axes it could not measure. That is the correct behaviour and it is not what
failed here. What failed is that **no axis existed to be named**: the
`--allow-partial-platform` run on this box prints its partial line and the
x86_64 lint surface is not on it, because nothing ever declared it a surface.
A gate cannot report a lane it does not have — AGENTS.md's own rule about
a count being green over whatever the instrument can SEE, one level up, with
the LANE SET as the population nothing floored.
