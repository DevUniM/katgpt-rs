# Issue 858 — `g8_cached_faster_than_uncached` is RED on `develop`, reproducibly, and nothing automatic looks

**Status:** OPEN on T3 only (owner call about lanes) — **T1+T2 RESOLVED 2026-09-19
on the 4090/x86_64 box**: the x86_64 reading CONFIRMS the arch hypothesis
(both x86_64 configs hold the 0.5 bar; aarch64's 0.68–0.71 is a genuine ISA
gap, ~6× the run spread on both boxes) and the bar is now an arch-conditional
dual pin (aarch64 0.75 / everything else 0.5), each arch's measured value
named at the line. Not a cache regression. **Found by:** Issue 855 T6's
SILENT bucket, sideways — adding a `println!` to two *neighbouring* arms in
`tests/belief_drafter_goat.rs` meant running the whole target, and the target
was already red.

## The measurement

`cargo test --release --test belief_drafter_goat -- --exact
g8_cached_faster_than_uncached`, five consecutive runs, this target alone:

| run | ratio | per-round range | a = MLP fwd | b = cache get |
|---|---|---|---|---|
| 1 | 0.7075 | 0.5975 .. 0.7746 | 239.9 | 162.7 |
| 2 | 0.6844 | 0.5978 .. 0.7188 | 243.3 | 161.1 |
| 3 | 0.7111 | 0.6039 .. 0.7613 | 244.1 | 171.0 |
| 4 | 0.6916 | 0.6104 .. 0.7468 | 243.3 | 163.5 |
| 5 | 0.6903 | 0.6336 .. 0.7498 | 244.2 | 168.0 |

Bar: `ab.median < 0.5` ("at least 2x faster"). The **per-round minimum across
all five runs is 0.5975** — no round ever reaches the bar.

Box: M3 Max, `--release`, loadavg ~4-5, one concurrent single-core job.

## Every PASSED-ALONE class is excluded

AGENTS.md's three classes for "failed in a cell, passed alone" are load-sensitive
BAR, shared-fixed-path CONCURRENCY, and unseeded-RNG COIN FLIP. This row is the
mirror — it fails *alone* — and none of the three explains it:

- **Not load.** 5/5 alone, spread 0.6844–0.7111 (3.9%), on a quiet box.
- **Not concurrency.** No `temp_dir` site; it fails identically alone.
- **Not an unseeded draw.** 25 interleaved rounds, and the per-round range is
  reported: the whole distribution sits above the bar, not a tail of it.
- **Not Issue 855's class either.** Both arms are `black_box`'d at input *and*
  output and both measure real work (243 and 165 ns/iter). Nothing vanished.

## ⛔ What makes this worth filing rather than re-pinning

The commit that set this bar — `dd8dadbba`, Issue 833 T2's worked example —
recorded its own calibration:

> 8 runs: 0.3975 0.3966 0.3978 0.4086 0.4028 0.3870 0.4004 0.3946 — 8/8 inside
> a 2.2% band against the 0.5 bar. With the arms live the work is real and
> measurable (a 360.3 ns/iter, b 141.7).

Today: **a 243, b 165, ratio 0.69.** The baseline got *faster* and the candidate
got *slower*, and the ratio moved 0.40 → 0.69. That is a change in the ratio of
real work, not in the instrument — the instrument is the same interleaved
harness in both readings.

⚠ **The most likely cause is the ARCH, and it is NOT proven.** The only stated
difference between the two calibrations is the platform: `dd8dadbba`'s eight
runs were taken in x86_64 execution-matrix cell 8 (release + avx2), and these
five are aarch64/macOS. `b` is a BLAKE3 keyed lookup and `a` is an MLP forward;
their relative cost is exactly the kind of thing an ISA moves. That would make
this the mirror of Bench 806 T7's finding — *"NEON/FMLA-calibrated bars x86_64
never reaches"* — with the arrow reversed, and its documented resolution is
**arch-conditional dual pins**.

⛔ **I have not measured the other arch.** Do not close this on the arch
hypothesis without an x86_64 reading; a genuine cache regression produces the
same five numbers.

## Why nothing caught it

The axis is `compile vs EXECUTE`, and this target sits in the gap between every
lane:

- `full_gate.sh` is macOS/aarch64 — the right arch — but it is **compile+lint**,
  never execute.
- `scripts/x86_64_execution_matrix.sh` **executes** and would have the other
  arch's reading, but it **refuses off x86_64** and is a workstation verdict
  nobody runs on a schedule.
- `scripts/test_gate.sh` is the only executing lane and its **schedule has been
  suspended since 2026-09-09** (Actions spending limit).

So a target repaired on one arch, and red on the other since that repair, is
exactly what this workspace's instrument map predicts will go unnoticed.

## Tasks

- [x] **T1 — take an x86_64 reading** of the same five runs. That decides
      between arch-conditional calibration and a real cache regression, and no
      amount of re-running on aarch64 can.
      **DONE 2026-09-19, 4090 box (i7-13700K, Windows, sibling riir-ai build+
test running concurrently — recorded per the box-state rule). BOTH x86_64
configurations measured, default features, `--release`, `--exact`:**

| config | run | median | per-round range | a = MLP fwd | b = cache get |
|---|---|---|---|---|---|
| +avx2 (matrix-lane cfg) | 1 | 0.4566 | 0.3695..0.5648 | 337.7 | 155.2 |
| +avx2 | 2 | 0.4697 | 0.4366..0.5796 | 325.0 | 153.3 |
| +avx2 | 3 | 0.4523 | 0.3766..0.5376 | 346.5 | 154.2 |
| +avx2 | 4 | 0.4575 | 0.3972..0.4891 | 329.0 | 149.3 |
| +avx2 | 5 | 0.4574 | 0.4145..0.6647 | 327.4 | 154.9 |
| +avx2 (post-T2-edit reruns) | 6–7 | 0.4579 / 0.4712 | .. | 340.5 / 321.8 | 153.7 / 151.6 |
| plain (no RUSTFLAGS) | 1 | 0.3973 | 0.3439..0.4408 | 369.5 | 145.3 |
| plain | 2 | 0.3896 | 0.3579..0.4533 | 348.2 | 136.7 |
| plain | 3 | 0.3923 | 0.3483..0.5827 | 357.7 | 141.2 |
| plain | 4 | 0.3955 | 0.3298..0.4859 | 355.2 | 140.9 |
| plain | 5 | 0.3959 | 0.3671..0.4203 | 361.6 | 141.9 |
| plain (post-T2-edit rerun) | 6 | 0.3947 | 0.3633..0.4870 | 359.6 | 145.7 |

**Verdict: 13/13 x86_64 runs PASS.** +avx2 median band 0.4523–0.4712 (4.2%
spread — same spread class as the M3's 3.9%); plain band 0.3896–0.3973.
The arch gap (x86_64 ~0.39–0.47 vs aarch64 0.68–0.71) is ~0.23 — ~6× the
run-to-run spread on both boxes. **Arch hypothesis CONFIRMED; cache
regression REFUTED** (b ≈ 137–155 ns across all x86_64 runs, consistent
with the `dd8dadbba` b=141.7).

⚠ Two honest observations for the record: (1) the `dd8dadbba` calibration
band (0.3975–0.4086, a=360.3, b=141.7) matches today's **plain** build
almost exactly, while today's **+avx2** build reads ~0.06 higher with a
~10% faster / b ~8% slower — i.e. the flag's codegen shifts the arms'
absolute costs and the ratio; both configs hold the bar, so the claim
stands either way, but the calibration's attribution to "cell 8
(release + avx2)" may actually describe a plain-build reading. (2) The
+avx2 config's headroom under sibling-build load is 2.9–4.8 points — a
future red there is a BOX-CONDITIONS question first (re-run alone per the
Bench 806 T7 discipline) before any regression reading.
- [x] **T2 — resolve by the arch-conditional dual-pin precedent** (Bench 806
      Addendum II) if T1 confirms, naming each arch's measured value at the
      line. If T1 refutes it, the finding is a **cache-lookup regression** and
      the bar is right.
      **DONE 2026-09-19**: `tests/belief_drafter_goat.rs` g8 now pins
      `G8_BAR` — aarch64 0.75 (the M3's worst median 0.7111 + ~5% headroom,
      mirroring the x86_64 bar's own headroom over 0.4712); every other arch
      keeps the strict 0.5 claim (an unmeasured arch must meet the stated
      claim or red loudly — that red is information, exactly how this issue
      was found — never silently inherit the relaxed bar). Both x86_64
configs re-run green post-edit (12/12 target tests, clippy clean).
      The claim itself did NOT move on x86_64 — this is the sanctioned
dual-pin form, not the forbidden silent global 0.75.
- [ ] **T3 — the gap itself is the standing finding.** A target whose repair
      was calibrated on the arch that no *executing* lane covers, in a repo
      whose only executing lane is suspended, is unknown rather than green.
      That is an owner call about lanes, not a code fix. (T1 sharpened it:
      the M3 red existed for one day and was found by accident; the
      suspended `test_gate.sh` schedule is the only executing lane either
      arch has.)

## What is NOT the finding

- ⛔ **Not "raise the bar to 0.75."** The 2x claim is Plan 217's, stated in
  documentation; weakening it silently to make a red go away is the thing this
  repo's gate discipline exists to prevent. Either the claim holds on the arch
  it was stated for and needs a dual pin, or it does not hold and the claim is
  what should move.
- ⚠ **Not the two neighbouring arms.** `g2_variable_length_control` and
  `g3_cache_empty_overhead_near_zero` in the same file were made to PRINT in
  the same session and are both live (5.6 ms / 4.8 ms, and 184.28 ns/call).
  They are untouched by this.
