# Issue 855: a latency ceiling is satisfied by a loop the optimiser DELETED — `0 ns/op` over 100 000 iterations, asserted `< 10 000 ns`, PASS

**Status:** OPEN — T1 filed with the measurement, **T2 repaired and verified** (5 of 5 arms print a non-zero quantity, every bar unchanged), **T3 counted and the ten static candidates MEASURED** (3 VANISHED, 7 SURVIVED, 0 UNMEASURED; the 3 repaired and re-run, every bar unchanged); T4–T5 open.
**Found by:** Issue 833 T2's per-target read, 2026-09-19. Not by a census, and
not by anything failing — by **reading the printed values next to the bars**,
which is the one thing 833 T2 refuses to skip.
**Population measured:** 21 of the 38 root-`tests/` GATES targets had been run
when this was filed; **3 of the 21 carry a vanished arm, 5 arms in total**.

## The class

Issue 723 Class A2 is written down in this repo and has a treatment:

> rustc 1.98.1 + fat LTO eliminates inlined-callee work whose outer result is
> dead, *even through a `black_box` inside the callee* (Issue 723 T5: a direct
> call with a used result measured 16.6 µs; `let _ = f()` over the same fn in
> the same binary read ~0).

`tests/common/ab_timing.rs` defends against it **twice** — `ab_median_ratio`
panics when every round measured a 0 ns arm, and `best_of_us` panics when every
timed call did. Both messages say the same thing: *fix the harness, do not read
a verdict out of it.*

⛔ **Neither defense reaches a hand-rolled `Instant::now()` loop with an
absolute ceiling, and that is where the live specimens are.** The shape is:

```rust
let start = Instant::now();
for _ in 0..n {
    let _ = f(&loop_invariant_input);   // result discarded, no black_box
}
let ns_per = start.elapsed().as_nanos() as f64 / n as f64;
assert!(ns_per < 10_000.0, "too slow: {ns_per} ns/op");
```

The loop is deleted, `ns_per` is **0.0**, and the ceiling passes **with maximum
margin**. A flaky bar fails sometimes and is therefore eventually noticed; this
passes always, on every box, in every profile that optimises — and it reports a
throughput figure for work that does not happen.

**This is the `#![cfg]` green-zero rule one layer down.** AGENTS.md already
says a gated test target compiles to an empty binary and prints
`ok. 0 passed`, exit 0, byte-for-byte a real pass. Here the binary is not
empty and the test is not skipped: the assertion **runs, and is satisfied by
absent work**. The output is a plausible number rather than a zero count, so
none of the count floors that catch the first class can see this one.

## The measured specimens (release, default features unless noted)

| target | test | printed | asserted | verdict |
|---|---|---|---|---|
| `tests/bench_regime_transition.rs` | `bench_collapse_classification_throughput` | `100000 iterations in 0ns (0.0 ns/op)` | `ns_per < 10_000.0` | **PASS on nothing** |
| `tests/bench_regime_transition.rs` | `bench_gate_evaluation_throughput` | `100000 iterations in 0ns (0.0 ns/op)` | `ns_per < 10_000.0` | **PASS on nothing** |
| `tests/bench_239_posterior_evolution_goat.rs` | `g5_hot_path_overhead` | `relevance (bare): 0.0 ns/call`, `overhead: 11.8 ns (inf%)` | `overhead_ns < 1000.0` | **PASS, wrong quantity** |
| `tests/bench_bfcf_tree.rs` | B1 | `WITHOUT BFCF: 0.0 µs/iter` vs `WITH BFCF: 690.6 µs/iter` | — | baseline absent |
| `tests/bench_bfcf_tree.rs` | B1 | `Region pruning: 0.0 µs/iter` vs `Token-by-token: 30.3 µs/iter`, `Speedup: 8657.9×` | `region_per_iter < token_per_iter` | **PASS on nothing** |

Both `bench_regime_transition` sites are `let _ = classifier.classify(&stats)`
and `let _ = gate.evaluate(&trace, 5)` over an input hoisted out of the loop.

⚑ **`bench_239` is the instructive one, because it still prints a non-zero
number.** `NoScreeningPruner::relevance` returns the constant `1.0` and ignores
every argument (`crates/katgpt-core/src/traits/mod.rs:370`), so only the
BASELINE arm vanished. `overhead_ns = posterior_rel_ns - 0.0` then makes a gate
whose whole subject is *the difference between two arms* assert the candidate
arm's **absolute** cost under the name "overhead" — and pass, because
`11.8 < 1000`. The printed percentage is `inf`, which is the only part of the
output that discloses anything, and it discloses it in a field nobody reads.

⛔ **The `Speedup: 8657.9×` line in `bench_bfcf_tree` is the reason this is
filed rather than fixed quietly.** A number like that in a benchmark log is
read by a human as a result. It is a division by a deleted loop.

## What is NOT the finding

- ⛔ **Not "the bars are too loose."** `< 10_000 ns/op` is a perfectly
  reasonable smoke ceiling for a classifier. The defect is that the quantity
  compared against it does not exist. Raising or lowering any bar here repairs
  nothing.
- ⛔ **Not Issue 833's subject.** 833/834 are about a ratio whose verdict the
  **box** decides — a bar that flips under load. This is a bar that **cannot**
  flip, because the measurement is a constant 0. The two classes want opposite
  responses (interleave vs. consume the result) and a target can have both;
  `bench_239` and `bench_bfcf_tree` do. Do not fold the counts.
- ⚠ **Not settled for `bench_252`.** `t27b`'s `let _ = expr.eval(&results)`
  is the same spelling and measured **483.1%** overhead, i.e. it was *not*
  eliminated — the `.collect()` above it keeps the work alive. Read the
  measured value before calling a spelling a defect; the spelling is a
  candidate, the zero is the finding.

## Tasks

- [x] **T1 — file the measurement.** 3 of 21 targets, 5 arms, each with its
      printed value and its assertion. Done above.
- [x] **T2 — repair the five arms.** Done 2026-09-19. Every arm now measures
      something; **every bar is byte-identical to what it was**, which is the
      constraint that makes the repair readable as a repair.

      | target :: test | arm | before | after |
      |---|---|---|---|
      | `bench_regime_transition` :: `bench_collapse_classification_throughput` | `classify` | `100000 iterations in 42ns` — **0.0 ns/op** | `10 samples × 10000 iterations, best 124.2µs` — **12.4 ns/op** |
      | `bench_regime_transition` :: `bench_gate_evaluation_throughput` | `evaluate` | `100000 iterations in 0ns` — **0.0 ns/op** | `10 samples × 10000 iterations, best 7.0µs` — **0.7 ns/op** |
      | `bench_239_posterior_evolution_goat` :: `g5_hot_path_overhead` | bare baseline | `relevance (bare): 0.0 ns/call`, overhead `11.8 ns (inf%)` | **0.4 ns/iter**, overhead **7.7 ns (+1912.5%)**, 21 of 21 rounds survived |
      | `bench_bfcf_tree` :: B1 `bench_region_pruning_vs_token_pruning` | region pruning | **0.0 µs/iter** → `Speedup: 3799.6×` | **6.1 ns/iter** vs token 24.6 µs/iter → `Speedup: 4060.9×`, 11 of 11 rounds survived |
      | `bench_bfcf_tree` :: B3 `bench_bfcf_throughput_gain` | WITHOUT BFCF | **0.0 µs/iter** → `Throughput change: -169873680.5%` | **79.2 µs/iter** vs 391.4 µs/iter → `Throughput change: -394.3%`, 11 of 11 rounds survived |

      - ⚑ **The measurement is proved to EXIST, not merely to be non-zero.**
        A 4× chunk probe on the two `best_of_us` sites scaled **3.99×** and
        **4.05×** (7.0 → 27.9 µs, 124.2 → 503.0 µs) with the per-op figures
        flat at 0.7 and 12.6 ns. A deleted loop does not scale with its bound.
      - ⚠ `evaluate`'s **0.7 ns/op is a real reading, not a residual zero**:
        the body is two `Vec::len()` loads through an opaque pointer, three
        flops and a compare (`regime_transition.rs:171`). The 4× probe is what
        separates that from the class this issue is about.
      - ⛔ **The issue's own table mislabelled one row.** Both `bench_bfcf_tree`
        rows were filed as `B1`; the `WITHOUT BFCF` / `WITH BFCF` strings are
        printed by **B3** (`bench_bfcf_throughput_gain`). Corrected above. The
        arm count is unchanged at five.
      - Harnesses, per the treatment rule: `best_of_us` for the two ONE-ARM
        absolute ceilings in `bench_regime_transition`; `ab_median_ratio` for
        the three A/B-shaped arms. `bench_239` G5 was **already migrated at
        HEAD** — verified by compiling and running it, not by reading it.
        `bench_bfcf_tree` B1 and B3 are new adopters (`ROUNDS = 11 ×
        ITERS_PER_ROUND = 20` = 220, against the 200 the sequential loops did).
      - ⚠ **One DISPLAY change, deliberate and not a bar.** B1's region arm is
        genuinely ~6 ns/iter, and `{:.1} µs` renders that as the literal `0.0`
        this issue was filed for — a live measurement must not print like a
        dead one. That line prints ns now; the `region_per_iter <
        token_per_iter` bar is untouched and still reads the same two
        quantities, now sourced from `ab.a_ns_per_iter()` / `ab.b_ns_per_iter()`.
      - ⚠ B3's baseline arm gained one `screened += (rel >= 0.7) as usize;` —
        the minimum consumption that keeps a pure callee alive, and the same
        shape B1's token arm already had. B3 carries no wall-clock bar
        (`eval_reduction > 10.0` is static arithmetic), so nothing moved.
      - Verified: `CARGO_TARGET_DIR=/tmp/i855 cargo test --release` per target
        at its own features (`regime_transition`; `bfcf_tree`;
        `posterior_evolution,mux_latent_context`) — never `--all-features`.
        `cargo clippy --release` clean on all three targets; both touched files
        were rustfmt-clean at HEAD and still are.
- [x] **T3 — the RUNTIME detector is exact and nearly free, and it is the one
      worth having.** A timed region that measures **0 ns over n ≥ 1000
      iterations** is an instrument failure with no false-positive story on any
      box this workspace runs: the timer's own resolution cannot produce a
      0 over that many iterations of work that happened. `ab_timing.rs`
      already asserts exactly this twice. The question T3 must answer by
      **measurement, not by symmetry**: how many hand-rolled timed regions in
      tracked `tests/` + `benches/` carry NO such assertion? Count before
      proposing anything.

      ### T3 answer — the count, then the ten it ordered

      Counted over tracked `tests/` + `benches/`, 2026-09-19:
      **609 hand-rolled timed regions · 41 guarded · 568 UNGUARDED.** Of the
      568, **60 loop ≥ 1000 iterations** (below that a 0 ns reading is not
      yet evidence — the premise this task rests on), **34 of those 60
      ASSERT something**, and **10 of the 34** carry `let _ =` with no
      `black_box`, i.e. Issue 855's exact measured spelling.

      So the answer to the question as asked is **568**, and the answer to
      the question worth acting on — *unguarded, asserting, and at a bound
      where a zero means something* — is **34**.

      ### The ten candidates, RUN (release, per-target `required-features`, never `--all-features`)

      ⛔ **The spelling is a candidate, never a finding** — the T1 note on
      `bench_252` already measured that. **7 of the 10 SURVIVED**, which is a
      70% false-positive rate for the static spelling and is the whole
      argument against reading T4's grep as a verdict.

      | # | target :: fn | bound | printed | asserted | verdict |
      |---|---|---|---|---|---|
      | 1 | `bench_164_gepa_reflective_goat` :: `..._proof` | 1000 | `1000 inserts in 30.708µs`, `0.030 µs` avg; Proof 1 `3.3 ns/call (10000 calls in 33.167µs)` | `avg ≤ 1µs`, `overhead_pct ≤ 10.0` | **SURVIVED** |
      | 2 | `bench_250_breakeven_goat` :: `t1_overhead_per_forward` | 1000 (warmup) / 10 000 (timed) | `81.542µs total`, `8.2 ns/call` | `ns_per_call < 100.0` | **SURVIVED** |
      | 3 | `bench_272_progressive_mcgs_goat` :: `g4b_latency_pick_mode_under_1us` | 100 000 | **`0.0 ns`** | `per_call_ns < 1000.0` | ⛔ **VANISHED** |
      | 4 | `bench_274_cgsp_goat` :: `g4_per_cycle_overhead` | 100 000 | `71.588166ms total`, `715.9 ns/cycle` | `ns_per_cycle ≤ 1000.0` | **SURVIVED** |
      | 5 | `bench_trust_region` :: `bench_adaptive_window_trivial` | 1 000 000 | **`0.0 ns/call`** | `per_call_ns < 100.0` | ⛔ **VANISHED** |
      | 6 | `bench_trust_region` :: `bench_trust_arm_roundtrip` | 100 000 | `17.0 ns/call` | `per_call_ns < 500.0` | **SURVIVED** |
      | 7 | `bench_trust_region` :: `goat_trust_region_overhead_acceptable` | 1000 | `0.20 μs/token` | `per_token_us < 100.0` | **SURVIVED** |
      | 8 | `goat_234_manifold_pruner` :: `g9_kernel_score_simd_vs_scalar_benchmark` | 100 000 | `Scalar 11.791167ms`, `SIMD 2.084584ms`, `Ratio 5.66x` | `(s - si).abs() < 1e-4` (not a timing bar) | **SURVIVED** |
      | 9 | `pipeline_pruner_goat` :: `test_pipeline_latency_no_regression` | 100 000 | `43ns per query` | `ns < 10_000.0` | **SURVIVED** |
      | 10 | `test_wealth_bandit` :: `test_goat_g1_relevance_overhead` | 100 000 | `WealthPruner **42ns**` (for 100 000 iters) vs `BanditPruner 690.458µs` → `overhead = 0.00x` | `overhead < 3.0` | ⛔ **VANISHED** |

      - ⚑ **Row 10 is the `bench_239` shape again, and it is the worst of the
        three**: only the NUMERATOR vanished, so the gate printed a
        well-formed `0.00x` rather than a zero, and `0.00 < 3.0` passed with
        maximum margin. Nothing in that line reads as broken.
      - ⚠ **Row 8's `let _ =` is in the WARMUP only** — both timed loops
        accumulate into `scalar_result` / `simd_result`, which an assertion
        consumes. A static pass that does not distinguish the warmup from the
        timed region reports it; it was never a candidate.
      - Row 1's two relevance arms print an equal `3.3 ns/call` and `+0.3%`.
        That is Issues 833/834's class (a SEQUENTIAL A/B), **not** this one,
        and is deliberately not folded in.

      ### The 4× scaling probe — the only thing that separates *fast* from *partly deleted*

      Four SURVIVED rows printed small figures, so each had its loop bound
      multiplied by 4 and its WALL time read. A deleted loop does not scale
      with its bound. Every source file was restored byte-identically
      afterwards (`git diff --quiet`, verified).

      | row | 1× | 4× | scaling |
      |---|---|---|---|
      | 1 `bench_164` Proof 1 (reflective) | `33.167µs` | `184.208µs` | **5.55×** |
      | 1 `bench_164` Proof 1 (baseline) | `33.083µs` | `145.042µs` | **4.38×** |
      | 2 `bench_250` | `81.542µs` | `328.75µs` | **4.03×** |
      | 9 `pipeline_pruner_goat` | `43 ns/query` | `173 ns/query` (divisor held) | **4.02×** |
      | 6 `bench_trust_region` roundtrip | `17.0 ns/call` | `64.7 ns/call` (divisor held) | **3.81×** |

      Over-scaling on row 1 is the box, not the instrument — see the box
      state below. All five scale; none is partly eliminated.

      ### The three repairs — every bar byte-identical

      | target :: test | before | after | 4× probe |
      |---|---|---|---|
      | `bench_272` :: `g4b_latency_pick_mode_under_1us` | `0.0 ns` over 100 000 iters | `best_of_us`, `10 × 10 000`, best **7.2 µs** — **0.7 ns/call** | `7.2 → 31.5 µs` = **4.38×** |
      | `bench_trust_region` :: `bench_adaptive_window_trivial` | `0.0 ns/call` over 1 000 000 iters | `best_of_us`, `10 × 100 000`, best **954.5 µs** — **9.5 ns/call** | `954.5 → 4489.7 µs` = **4.70×** |
      | `test_wealth_bandit` :: `test_goat_g1_relevance_overhead` | wealth arm `42ns`/100 000 iters → `overhead 0.00x` | `ab_median_ratio`, `11 × 10 000`, a **7.8**, b **0.8 ns/iter**, **11 of 11 rounds survived** → `overhead 0.11x` | per-iter FLAT at 7.7 / 0.8 across 4× |

      - Harness per the T2 treatment rule: `best_of_us` for the two ONE-ARM
        absolute ceilings, `ab_median_ratio` for the one A/B ratio (with
        `a` = BanditPruner denominator and `b` = WealthPruner numerator, so
        `median` IS the `wp/bp` quantity the bar has always read).
      - Every sink is consumed through `std::hint::black_box`. Bars
        `per_call_ns < 1000.0`, `per_call_ns < 100.0` and `overhead < 3.0`
        are **unchanged**; the message strings are unchanged.
      - Total timed iterations preserved or raised (100 000 → 100 000;
        1 000 000 → 1 000 000; 100 000 → 110 000 per arm).
      - Verified: `CARGO_TARGET_DIR=/tmp/i855t3 cargo test --release` per
        target at its own features (`progressive_mcgs`; default;
        `wealth_pruner`) — never `--all-features`. Full-target counts
        unchanged: **7 / 6 / 11 passed**. `cargo clippy --release` adds no
        finding (`bench_272`'s `assert_alloc_tracking_live` dead-code warning
        is present at HEAD too). `bench_trust_region` and `test_wealth_bandit`
        were rustfmt-clean at HEAD and still are; `bench_272`'s rustfmt
        complaint count is unchanged.

      ### ⛔ Two green zeros, found on the way and not folded in

      - `cargo test --test bench_250_breakeven_goat -- --exact
        t1_overhead_per_forward` reports **`running 0 tests`, exit 0** — the
        whole file is `#[cfg(test)] #[cfg(feature = "breakeven_routing")] mod
        tests`, so the test's real name is `tests::t1_overhead_per_forward`.
        That is **Issue 856's** class (a `#[cfg] mod` the audit cannot see),
        met live. It is why the row-2 measurement above was taken twice.
      - Row 8 asserts a CORRECTNESS equality and no timing bar at all, so it
        can never fail on the box — 833 T3's "SEQUENTIAL, asserts nothing
        about time" bucket. Not a defect; not a candidate.

      ### Box state (§Feature Flag Discipline)

      - **Screening runs (rows 1–10, first pass):** M3 Max, 68.7 GB physical,
        load averages **43.05 / 36.47 / 28.04**, a sibling session's `rustc`
        at 99% CPU, ~1.46 GB free. A **screening** class — adequate for a
        ZERO, which no load can manufacture, and NOT adequate for
        adjudicating slack on any of the SURVIVED bars.
      - **Repairs + 4× probes:** load averages **6.04 / 12.22 / 18.55**,
        2.38 GB free + 25.97 GB inactive, swap 8.70 of 10.24 GB used, no
        concurrent cargo. Still not a quiet box; the 5.55× and 4.70×
        readings are that, and they are reported as ranges rather than
        constants for exactly that reason.
      - Dedicated `CARGO_TARGET_DIR=/tmp/i855t3` throughout, so no shared
        target-dir contention with sibling sessions.
- [ ] **T4 — the STATIC detector is tempting and is the weaker instrument;
      decide deliberately.** `let _ = f(…)` inside a timed region with no
      `black_box` is greppable, and `bench_252` above is the measured
      false positive — the spelling is present and the work survived. So a
      static pass reports CANDIDATES, never findings, which is the
      `percentile_index_audit` standing (*UNRESOLVED is not clean*). ⛔ Do not
      add a verdict half by symmetry with the sweep family: AGENTS.md records
      that `check_validation_gate` declined a sweep on a measured population of
      one and `console_encoding_gate` assumed that answer carried and was wrong
      by seven repos. **Re-measure the population first** — and note the
      population here is *timed regions*, not repos.
- [ ] **T5 — the cross-repo axis is UNMEASURED and must not inherit an
      answer.** `let _ = f()` in a timed loop is not a katgpt-rs idiom; the
      siblings carry 71 sequential-timing targets (Issue 834 T3). Whether any
      of them prints a zero is unknown, and the honest first step is to run
      their benches and grep the output — the same thing that found these five.
      ⚠ A static census would answer a different question; see T4.

## Records

- Screening run: `/f/ab_slack/*.log`, summary `/f/ab_slack_summary.txt`,
  bar inventory `/f/ab_bars.txt` (release, per-target `required-features`,
  never `--all-features`).
- Box state at measurement: 20.6 GB free of 31.8, commit 36.0 GB avail of a
  62.8 GB limit, ~13% CPU, 21 drift sweeps concurrent. ⚠ A **screening**
  class, per §Feature Flag Discipline's box-state rule — adequate for a zero,
  which no load can manufacture, and NOT adequate for adjudicating a 9-point
  slack.
- The treatment and its loud-zero defense: `tests/common/ab_timing.rs`
  (Issue 723 Class A, T7).
- The flaky-ratio sibling class, deliberately kept separate: Issues 833, 834.
