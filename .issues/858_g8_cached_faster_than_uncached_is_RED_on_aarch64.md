# Issue 858 — `g8_cached_faster_than_uncached` is RED on `develop`, reproducibly, and nothing automatic looks

**Status:** OPEN — measured 2026-09-19. **5 of 5 runs ALONE fail** on this box
with a tight spread; every PASSED-ALONE class is excluded. Not a flake.
**Found by:** Issue 855 T6's SILENT bucket, sideways — adding a `println!` to
two *neighbouring* arms in `tests/belief_drafter_goat.rs` meant running the
whole target, and the target was already red.

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

- [ ] **T1 — take an x86_64 reading** of the same five runs. That decides
      between arch-conditional calibration and a real cache regression, and no
      amount of re-running on aarch64 can.
- [ ] **T2 — resolve by the arch-conditional dual-pin precedent** (Bench 806
      Addendum II) if T1 confirms, naming each arch's measured value at the
      line. If T1 refutes it, the finding is a **cache-lookup regression** and
      the bar is right.
- [ ] **T3 — the gap itself is the standing finding.** A target whose repair
      was calibrated on the arch that no *executing* lane covers, in a repo
      whose only executing lane is suspended, is unknown rather than green.
      That is an owner call about lanes, not a code fix.

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
