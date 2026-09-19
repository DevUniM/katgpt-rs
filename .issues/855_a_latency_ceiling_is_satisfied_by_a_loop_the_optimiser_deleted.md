# Issue 855: a latency ceiling is satisfied by a loop the optimiser DELETED — `0 ns/op` over 100 000 iterations, asserted `< 10 000 ns`, PASS

**Status:** OPEN — T1 filed with the measurement, **T2 repaired and verified** (5 of 5 arms print a non-zero quantity, every bar unchanged), **T3 COMPLETE — all 34 asserting timed regions at n ≥ 1000 have now been RUN** (10 + 24; **7 VANISHED, 27 SURVIVED, 0 UNMEASURED**; all 7 repaired and re-run, every bar unchanged, every full-target pass count unchanged); **T4 CLOSED** — the proposed `let _ =` predicate is REFUTED by the execution run (20.0% vs a 21.1% base rate) and `scripts/timed_region_guard_gate.py` shipped in its place as a docs-gate CHECK (membership wall over the READ tier, ratchet over the unread one); **T5 RUN — all 33 sibling rows executed 2026-09-19** (1 UNBUILDABLE, 32 executed, **2 VANISHED = 6.3%** against this repo's 20.6%; both repaired in riir-ai `3712d51b6`, issue `986` there; riir-chain `039728c8` filed for the unbuildable one). Three new buckets fell out of the run — PRINTS-NOTHING, `#[ignore]`d, UNBUILDABLE — none foldable. Only the **ratchet-only sweep half** remains open.
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

      ### The REMAINING 24, RUN — T3 is now COMPLETE over its own population

      The ten above were the `let _ =`-spelled slice. These 24 are the rest of
      the 34: unguarded timed regions looping ≥ 1000 times that ASSERT
      something, i.e. every remaining verdict a deleted loop could satisfy.
      Release, per-target `required-features`, never `--all-features`, dedicated
      `CARGO_TARGET_DIR=/tmp/i855t3b*` per feature set.

      **4 VANISHED of 24.**

      | # | target :: fn | bound | printed | asserted | verdict |
      |---|---|---|---|---|---|
      | 11 | `bench_377_local_branch_routing_goat` :: `main` | 1000 | `route_argmax 10.4 ns/call`, `route_sampled 22.8 ns/call` | `< 1000 ns` | **SURVIVED** |
      | 12 | `bench_412_subspace_steering_goat` :: `g4_structural_size_and_latency_smoke` | 100 000 | **prints nothing**; probe: `100k applies in 407.459µs` = 4.07 ns/call | `elapsed.as_millis() < 400` | **SURVIVED** |
      | 13 | `bench_416_region_subspace_goat` :: `g4_latency_smoke_and_struct_size` | 100 000 | **`elapsed: 0ns`, `per-call: 0ns`** | `elapsed.as_millis() < 1000` | ⛔ **VANISHED** |
      | 14 | `switch_cost_663_poc` :: `g2_lookup_latency_single_digit_ns` | 1 000 000 | `1.39 ns/op (best of 3 × 1M)` | `≤ 9 ns` | **SURVIVED** |
      | 15 | `switch_cost_663_poc` :: `g2_sequence_entropy_under_300ns` | 100 000 | `13.99 ns/eval (best of 3 × 100k)` | `< 300 ns` | **SURVIVED** |
      | 16 | `bench_815_coulomb_redistribution_poc` :: `run_case` | 1000 | `solve = 2.04 / 13.76 / 74.61 µs` (3 cases) | T1c budget | **SURVIVED** |
      | 17 | `katgpt-ruliology` `tests::benchmarks` :: `bench_irreducibility_gate_fsm2` | 1000 | `2.188µs per check` | `< 1000 µs` | **SURVIVED** |
      | 18 | `async_qdq_goat` :: `test_double_buffer_swap_latency` | 10 000 | **`Double-buffer swap latency: 0ns`** | `ns < 10_000.0` | ⛔ **VANISHED** |
      | 19 | `bench_225_rat_bridge` :: `bench_bridge_projection_overhead` | 10 000 | **`Gate computation: 0.00ns per call`** | `per_gate < 10µs` | ⛔ **VANISHED** |
      | 20 | `bench_235_slod_goat` :: `g1_pruner_overhead_under_100ns` | 100 000 | `0.8 ns/call` | `≤ 100.0` | **SURVIVED** (4× = 3.98×) |
      | 21 | `bench_replaid_variance_schedules` :: `bench_variance_minimizer_overhead` | 1 000 000 | `3.5 ns/obs`, and `Observations: 1001000` | `< 100.0` | **SURVIVED** |
      | 22 | `bench_trust_region` :: `bench_trust_tracker_record` | 1 000 000 | `0.8 ns/call` | `< 100.0` | **SURVIVED** (4× = 3.9×) |
      | 23 | `bfcf_lsh_cms_goat` :: `g5_roaring_batch_speedup` | 6400 | no figure on pass — both arms cleared its **own** 1 µs floor | `speedup ≥ 2.0` | **SURVIVED** (already guarded) |
      | 24 | `goat_195_chain_fold` :: `goat1_zero_perf_hurt_noop_baseline` | 1000 | `1000 empty folds in 5.9µs` (median of 3) | `as_secs() < 5` | **SURVIVED** (4× = 3.2×) |
      | 25 | `goat_195_chain_fold` :: `goat4_binary_search_fold_throughput` | 1000 | `1000 folds in 553.75µs` | `as_secs() < 5` | **SURVIVED** |
      | 26 | `goat_195_chain_fold` :: `goat4_attention_importance_no_redundant_allocations` | 1000 | `1000 score_steps in 277.958µs` | `as_secs() < 3` | **SURVIVED** |
      | 27 | `goat_195_chain_fold` :: `summary_goat_195_chain_fold` | 1000 | `1000 folds in 270.208µs` | `goat4_pass` → `all_pass` | **SURVIVED** |
      | 28 | `pipeline_pruner_goat` :: `test_classify_simple_fast` | 10 000 | `126μs (0.01μs each)` | `as_secs() < 1` | **SURVIVED** |
      | 29 | `pipeline_pruner_goat` :: `test_classify_code_fast` | 10 000 | `514μs (0.05μs each)` | `as_secs() < 1` | **SURVIVED** |
      | 30 | `pipeline_pruner_goat` :: `test_classify_long_context_fast` | 10 000 | `128μs` | `as_secs() < 1` | **SURVIVED** |
      | 31 | `pipeline_pruner_goat` :: `test_classify_reasoning_fast` | 10 000 | `126μs` | `as_secs() < 1` | **SURVIVED** |
      | 32 | `precision_aware_draft_goat` :: `test_boundary_detection_speed` | 10 000 | `1711μs (0.17μs each)` | `as_secs() < 5` | **SURVIVED** |
      | 33 | `precision_aware_draft_goat` :: `test_boundary_penalty_overhead` | 1000 | `7665μs (7.66μs each)` | `as_secs() < 10` | **SURVIVED** |
      | 34 | `rv_gated_routing` :: `test_tracker_overhead_bounded` | 10 000 × 2 arms | **prints nothing**; probe: observe `43.708µs`, reset **`0ns`** | `as_millis() < 10` (twice) | ⛔ **VANISHED** (reset arm) |

      ### The combined population — 34 of 34, and what the spelling was worth

      **All 34 asserting timed regions at n ≥ 1000 have now been RUN**
      (10 + 24). **7 VANISHED, 27 SURVIVED, 0 UNMEASURED.**

      ⛔ **The `let _ =` spelling has almost NO discriminating power, and
      that is the measurement T4 was waiting for.** Split the 34 by the
      spelling that ordered the first pass:

      | slice | n | VANISHED | false-positive rate |
      |---|---|---|---|
      | carries `let _ =` | 15 | 3 | **80.0%** |
      | does not | 19 | 4 | **78.9%** |

      A predicate that fires on 20% of what it selects and 21% of what it
      rejects is not a classifier — it is the base rate wearing a grep. Every
      figure T4 needs to decide against a static `let _ =` pass is in that
      table, and the honest reading is that the spelling was a way to ORDER a
      read, never a way to shorten one.

      ⛑ **A far sharper predicate fell out of the same run, and it is the
      OTHER column: `black_box`.**

      | slice | n | VANISHED | hit rate |
      |---|---|---|---|
      | timed region contains **no** `black_box` | 23 | **7** | **30.4%** |
      | contains `black_box` | 11 | **0** | **0%** |

      **All 7 VANISHED rows, in both passes, are in the no-`black_box`
      slice** — a clean separation across 34 rows, where `let _ =` separated
      nothing. ⚠ It is still a CANDIDATE predicate, not a verdict: 16 of the
      23 survived, so it orders a read at 30% rather than 21% and does not
      shorten one either. T4 owns whether that is worth an instrument; it now
      has a measured number instead of an argument.

      ### The four repairs — every bar byte-identical

      | target :: test | before | after | 4× probe |
      |---|---|---|---|
      | `bench_416` :: `g4_latency_smoke_and_struct_size` | `elapsed: 0ns`, `per-call: 0ns` over 100 000 | `best_of_us`, `10 × 10 000`, `elapsed 864.6µs` — **8 ns/call** | per-call FLAT at 8 ns |
      | `async_qdq_goat` :: `test_double_buffer_swap_latency` | `0ns` over 10 000 | `best_of_us`, `10 × 10 000` — **1 ns/swap** | per-call FLAT at 1 ns |
      | `bench_225_rat_bridge` :: `bench_bridge_projection_overhead` | `0.00ns per call` over 10 000 | `best_of_us`, `10 × 10 000` — **8–22 ns/call** (box-dependent) | per-call FLAT at 10–11 ns |
      | `rv_gated_routing` :: `test_tracker_overhead_bounded` (reset arm) | `0ns` over 10 000 | `best_of_us`, `10 × 10 000` — **6.3–16.1µs per 10K resets** | `6.334 → 25.084µs` = **3.96×** |

      - Harness per the T2/T3a treatment rule: `best_of_us` for all four —
        every one is a ONE-ARM absolute ceiling, so `ab_median_ratio` is the
        wrong instrument here. Every sink is consumed through
        `std::hint::black_box`.
      - Bars `ns < 10_000.0`, `per_gate < Duration::from_micros(10)`,
        `elapsed.as_millis() < 1000` and `elapsed.as_millis() < 10` are
        **unchanged**, and so are the message and `println!` format strings —
        `bench_225` and `bench_416` rebuild a `Duration` from `best_of_us`'s
        µs precisely so the pre-existing `{per_gate:.2?}` / `{elapsed:?}`
        renderings keep meaning what they meant.
      - Total timed iterations preserved or RAISED: 100 000 → 100 000;
        10 000 → 100 000; 10 000 → 100 000; 10 000 → 100 000.
      - Full-target pass counts **unchanged**: **5 / 6 / 5 / 25**
        (`bench_416` / `async_qdq_goat` / `bench_225_rat_bridge` /
        `rv_gated_routing`). `cargo clippy --release` on each of the four
        targets adds **no** finding (the only line is the pre-existing
        `block v0.1.6` future-incompat note). All four files were rustfmt-
        DIVERGENT at HEAD and their divergence line count is unchanged
        (1 / 1 / 3 / 11), per AGENTS.md's no-`cargo fmt -p` rule.

      ⛔ **A sink is NOT always enough, and two of the four proved it on the
      first re-run.** Both `async_qdq` and `bench_225` still printed ~0 after
      the textbook repair (accumulate into a sink, `black_box` the sink,
      `best_of_us`), because the SINK was not the thing LLVM was removing:

      - `bench_225`'s `compute_gate` is pure in its two arguments and both are
        loop-invariant, so the dot product was hoisted OUT of the loop and the
        sink was computed once — `1.00ns per call`. The fix is `black_box` on
        the **inputs**, per iteration.
      - `async_qdq`'s round is an EVEN number of `mem::swap`es over the same
        two buffers, i.e. the identity, with `swapped` a constant — so the
        whole round folded away and it still printed `0ns`. The fix is a
        `black_box(&mut db)` **receiver**, per iteration.

      Read that as the sharper form of this issue's own rule: *consume the
      result* is a heuristic; the invariant is **the optimiser must not be able
      to prove the loop's effect**, and the sink is only one of the three
      places that proof can come from (result, arguments, receiver).

      ### ⛔ Four notes found on the way, none folded into the counts

      - **Two rows print NO number at all** (`bench_412` g4, `rv_gated_routing`
        `test_tracker_overhead_bounded`) — their quantities appear only inside
        an `assert!` message, i.e. only on failure. Neither could be
        adjudicated by *reading the printed value*, the method that found every
        other row; both needed a temporary `eprintln!` probe, run, then
        restored byte-identically (`git diff --quiet`, verified). **That is a
        strictly worse shape than a bar printing a zero**: a zero in a log is
        at least visible to a human reading it, and these are invisible in the
        configuration that passes. `rv_gated_routing` is where it cost
        something — its reset arm is one of the four VANISHED.
      - **`rv_gated_routing`'s bar could not have caught it anyway.**
        `elapsed.as_millis() < 10` over 10 000 `reset()` calls reads `0 ms`
        whether the loop runs or not (a live round measures 6–16 **µs**). A
        millisecond-granular bar over a nanosecond-scale body is satisfied by
        its own units, which is this issue's class with the resolution rather
        than the optimiser doing the deleting. The repair fixes the
        measurement; the bar is still 4 orders of magnitude loose, and that is
        the target owner's call, not this issue's.
      - **`bfcf_lsh_cms_goat` g5 was misfiled as unguarded** — it carries an
        explicit `roaring_time >= 1_000ns && linear_time >= 1_000ns` floor with
        a written-out account of the exact `0.00μ/0.00μ` incident that earned
        it (Issue 806). Both arms cleared the floor. `switch_cost_663_poc`'s
        two rows likewise already print `best of 3 × N`. So the static
        UNGUARDED count over-captures in a second way the first pass did not
        see: it misses a guard spelled as a bare `assert!` on the raw
        `Instant` deltas.
      - **A single sample refuted itself.** `bench_235_slod` at 4× first read
        `wall 911µs`, `2.3 ns/call` — a 10× scaling that would have been a
        finding. Re-measured 3× at each bound it is `83.3 / 84.0 / 83.2µs`
        against `331.3 / 342.7 / 331.7µs` = **3.98×** with per-call flat at
        0.8 ns. The first reading was the box. *Repair the instrument before
        blaming the code, and a scaling probe is a median, never a sample.*

      ### Box state, second pass (§Feature Flag Discipline)

      - **Screening (rows 11–34):** M3 Max, 68.7 GB physical, load averages
        from **3.77 / 7.83 / 15.25** at the first run to **10.96 / 8.51 /
        12.68** mid-sweep; ~2.9 GB free + ~25.6 GB inactive; 585 GB free on
        the data volume; no sibling `cargo` (a dedicated
        `CARGO_TARGET_DIR=/tmp/i855t3b_*` per feature set, and every stage run
        SEQUENTIALLY in one job so no two builds overlapped a measurement).
        A **screening** class — adequate for a ZERO, which no load can
        manufacture, and NOT adequate for adjudicating slack on any SURVIVED
        bar.
      - **Repairs + 4× probes:** load averages **6.24 / 8.01 / 11.81** rising
        to **24.82 / 18.02 / 14.99** by the final verification pass — which is
        visible in the numbers and is why they are quoted as ranges
        (`bench_225` read 8, 10, 11 and 22 ns/call across the session; the bar
        it must clear is 10 000 ns).
      - The only other heavy process throughout was `Zed Dev` at ~183% CPU.
- [x] **T4 — the STATIC detector is tempting and is the weaker instrument;
      decide deliberately.** DECIDED 2026-09-19, on the population T4 demanded
      be re-measured first. The verdict is **the proposed detector is REFUTED,
      and a different, decidable gate shipped in its place.**

  **What the execution run says about the proposed predicate.** All 34
  asserting regions at n ≥ 1000 were run (T3). Split by the spelling T4 names:

  | slice | n | VANISHED | rate |
  |---|---|---|---|
  | carries `let _ =` | 15 | 3 | **20.0%** |
  | does not | 19 | 4 | **21.1%** |

  ⛔ **It has essentially no discriminating power — it fires on 20% of what it
  selects and 21% of what it rejects. It is the base rate wearing a grep.**
  T4 expected a low-precision CANDIDATE list and `bench_252` as the measured
  false positive; the truth is worse than that, because a candidate list whose
  precision equals the base rate ORDERS nothing. Building it would have
  produced a report that costs a read and buys no information.

  ⚑ **The column that DOES separate is `black_box`: 7 of 23 without it
  vanished, 0 of 11 with it.** That is a real 30.4%-vs-0% split, and it is
  still not a finding predicate — it is a reason to gate the *defence* rather
  than the *symptom*.

  **What shipped instead — `scripts/timed_region_guard_gate.py`, a docs-gate
  CHECK.** It does not try to predict which region is broken. It gates the
  strictly decidable thing: *does a timed region that loops ≥ 1000 times and
  ASSERTS carry a loud-zero defence at all* — the shared harness
  (`best_of_us` / `ab_median_ratio`, both of which panic when every measured
  arm read 0) or its own non-zero assertion.
  - Both halves of the scope are load-bearing and are pinned by arms.
    **n ≥ 1000** is what makes a zero EXACT (below it a 0 is a
    timer-resolution artefact and the detector would be guessing);
    **asserts something** is what makes a zero MATTER (a region that only
    prints has no verdict a deleted loop can satisfy — that residue is
    reported on the verdict line, never gated, because it can still print
    nonsense: T1's `Speedup: 8657.9×` and `-169873680.5%` are both prints).
  - ⛔ **Two tiers, and the split is the honest part.** A LITERAL loop bound
    is the population T3 executed end to end, 34 of 34, so it is adjudicated
    and gets a MEMBERSHIP wall with one MEASURED number per row
    (`scripts/timed_region_survivors_expected.txt`, 27 rows, both directions).
    A bound that needs a hop of resolution is real and **unread** — 93 more
    regions — and pinning an unread bucket by name is the backlog-wearing-a-pin
    shape Issue 785 forbids, so it is a **ratchet on the derivative**: the
    commit that adds a NEW unguarded timed region reds, the existing 93 stay
    somebody's afternoon with a terminal.
  - ⛔ **One hop is not optional, and finding that out is what stopped this
    gate shipping blind to its own founding cases.** A literal-only predicate
    cannot see `tests/bench_regime_transition.rs` — `let n = 100_000; for _ in
    0..n` — and **both** arms T1 filed sit in that shape. A gate blind to the
    cases that motivated it is a gate that would have shipped them. Two hops
    is deliberately out (it needs a value model) and an arm pins that boundary.
  - `--prove-fires 796fabfac^` is two-sided against a known answer: 34
    unguarded regions at that commit, of which the pins admit 27, and the 7
    extras are **exactly** the 7 measured as VANISHED — no more, no fewer.
  - Perturbation-verified in all four directions: a dropped pin reds UNPINNED,
    a phantom row reds STALE, a lowered ratchet reds, and a raised one prints
    the tighten-it warning without failing (a ratchet that reds on an
    improvement is a ratchet people delete).
  - ⚠ STATED and printed on the verdict line rather than remembered: it does
    NOT claim a pinned region is safe. `black_box` is the **weakest** of the
    three defences, and T3 measured two arms that vanished carrying one — the
    optimiser proved the loop's effect through a loop-invariant **argument**
    (a pure fn of hoistable inputs) and through an identity **receiver** (an
    even number of `mem::swap`es). The invariant is that the optimiser must
    not be able to prove the loop's effect; the sink is one of three sources.
- [x] **T5 — the cross-repo axis is MEASURED: counted, then RUN.** (The
      ratchet-only sweep half is carved out as T6.) Original framing follows.
      **T5 — the cross-repo axis is UNMEASURED and must not inherit an
      answer.** `let _ = f()` in a timed loop is not a katgpt-rs idiom; the
      siblings carry 71 sequential-timing targets (Issue 834 T3). Whether any
      of them prints a zero is unknown, and the honest first step is to run
      their benches and grep the output — the same thing that found these five.
      ⚠ A static census would answer a different question; see T4.
      - ⛔ **And T4's measurement sharpens what a sweep half would have to be.**
        It cannot be a port of the refuted `let _ =` predicate. The gate that
        shipped is decidable and cross-repo-portable (`scan()` already takes a
        root), but its **wall** tier rests on somebody having EXECUTED the
        population — and 27 rows took two agent sessions and ~30 minutes of
        release builds **in this repo alone**. In a sibling the wall would be
        a wall over an unread bucket, which is the thing T4 refused. So a
        sweep half is a **ratchet-only** instrument there, and the honest
        first step is still T5's: run their benches and read the numbers.
        ⚠ Do **not** add it by symmetry with the sweep family — `check_validation_gate`
        declined a sweep on a measured population of one and `console_encoding_gate`
        assumed that answer carried and was wrong by seven repos. **Count the
        sibling timed regions first**; the count this repo produced (608
        regions, 120 unguarded in scope) is not evidence about theirs.
      - ⚑ **COUNTED 2026-09-19, and the axis is no longer unmeasured.** The
        shipped classifier was run over all 21 contract repos (it already takes
        a root), which is the cheap half of T5 — a static census of *regions
        lacking a defence*, NOT of defects:

        | | files | timed regions | READ-tier unguarded | UNREAD tier | print-only |
        |---|---|---|---|---|---|
        | katgpt-rs | 753 | 608 | 27 | 93 | 147 |
        | riir-ai | 854 | 552 | **18** | 58 | 53 |
        | riir-chain | 161 | 47 | **6** | 11 | 6 |
        | riir-neuron-db | 91 | 61 | **3** | 12 | 15 |
        | riir-clippy | 98 | 23 | **2** | 3 | 1 |
        | riir-train | 311 | 131 | **2** | 28 | 4 |
        | riir-game-sdk | 69 | 32 | **1** | 3 | 1 |
        | riir-shader | 6 | 1 | **1** | 0 | 0 |
        | 13 others | 198 | 37 | 0 | 5 | 0 |
        | **TOTAL** | **2541** | **1492** | **60** | **213** | **227** |

        ⛔ **The class generalises: 33 of the 60 strictly-decidable regions are
        OUTSIDE this repo, across 7 siblings.** T5's premise — *"`let _ = f()`
        in a timed loop is not a katgpt-rs idiom"* — was a guess about the
        wrong quantity; the population is not the idiom, it is the missing
        defence, and it is everywhere.
        ⚠ **33 is not 33 defects and must never be read as one.** The only
        measured conversion rate is this repo's: **7 of 34 (20.6%)** of the
        in-scope regions that were RUN were satisfied by absent work. Applied
        to 33 that is a *magnitude* — expect a handful — and AGENTS.md's own
        rule is that a static count over an unread bucket is a candidate
        ordering, not a finding.
      - ⚑ **RUN 2026-09-19 — all 33 executed, and the sibling rate is ONE
        THIRD of this repo's.** 1 UNBUILDABLE, 32 executed, **2 VANISHED
        (6.3%)** against katgpt-rs's 7 of 34 (20.6%).

        | repo | rows | VANISHED | note |
        |---|---|---|---|
        | riir-ai | 18 | **2** | both in `riir-games-civ`, repaired |
        | riir-chain | 6 | 0 | 1 UNBUILDABLE, 4 `#[ignore]`d |
        | riir-neuron-db | 3 | 0 | |
        | riir-clippy | 2 | 0 | |
        | riir-train | 2 | 0 | |
        | riir-game-sdk | 1 | 0 | |
        | riir-shader | 1 | 0 | |

        **The two VANISHED** (riir-ai `.issues/986`, committed there at
        `3712d51b6`):

        | target :: fn | bound | before | asserted | after |
        |---|---|---|---|---|
        | `feeling_brain_p5_goat` :: `g2_reactive_fsm_node_tick_sub_5ns` | 100 000 | **`0.00 ns/tick`** | `< 5 ns` | **0.56 ns/tick** |
        | `feeling_brain_p7_goat` :: `g2_from_inputs_latency_under_10ns` | 10 000 | **printed NOTHING**; probe `0 ns/call` | `< 10 ns` | **6.04–6.32 ns/call** |

        ⛔ **Neither was fixable by `black_box` on the RESULT**, which is the
        T3 lesson reproduced in a different repo: `from_inputs` is pure in a
        loop-invariant ARGUMENT (the `bench_225` shape — the call hoists and
        a result-only sink is computed once) and `tick` returns `()`, so there
        is no result at all (the `async_qdq` RECEIVER shape). Both arms gained
        the loud-zero assertion; every bar is byte-identical; pass counts
        unchanged (12 / 17).
        ⚑ **The p7 arm consumed 63% of its budget once it was real** —
        6.04–6.32 ns against `< 10 ns`. It was passing on nothing *while
        sitting close to a bar it had never been measured against*.

      - ⛔ **THREE buckets this issue did not have, each found by running
        rather than by reasoning, and none foldable into the others:**
        - **PRINTS NOTHING — 4 of 33, and it is the highest-yield slice by
          a factor of four.** Their quantity lives only inside an `assert!`
          message, i.e. it is visible ONLY on failure, so the method that
          found every other row — *read the printed value next to the bar* —
          cannot see them at all. Each needed a temporary `eprintln!` probe,
          run, then restored byte-identically (`git diff --quiet`, verified).
          **1 of those 4 was a VANISHED (25%)** against the population rate of
          6.3%. That is a real ordering signal and the mechanism is plain:
          nobody can have read a number nobody prints.
        - **`#[ignore]`d — 4 of 33, all riir-chain.** `cargo test --exact <fn>`
          reports `ok. 0 passed; 1 ignored`, **exit 0** — byte-for-byte the
          green-zero shape this issue family is about, met inside T5's own
          runner and nearly recorded as a result. Re-run with `--ignored` all
          four are live (0.430 / 16.92 / 194.76 / 198.62 ns). ⚠ The region is
          neither guarded nor satisfied-by-absent-work: it is **unexecuted**,
          which is a third state, and `timed_region_guard_gate` cannot see it
          because `#[ignore]` is orthogonal to every axis the gate reads.
        - **UNBUILDABLE — 1 of 33.** riir-chain's
          `crates/riir-chain-engine-bridge` is workspace-`exclude`d, so it is
          its own root, and its `[patch]` covers katgpt-rs but not the forked
          `arc-swap` its path dep `riir-engine` needs. **Every** cargo command
          there dies at manifest resolution, so that GOAT gate is compiled by
          nothing. Filed as riir-chain `.issues/157` (`039728c8`). An unbuilt
          gate is *unknown*, not passing — and the one instrument that looks
          at that crate reads its MANIFEST for three hand-typed patch rows,
          so it is structurally incapable of noticing a fourth is missing.
      - ⚠ **A residue, stated rather than resolved.** Four SURVIVED rows print
        sub-nanosecond figures (riir-ai `bench_133` 0.78–1.08 ns/check,
        riir-chain `bench_013` 0.430 ns, `sufficiency_gates` 2 ns). They are
        non-zero, which is this issue's criterion, and they did **not** get the
        4x scaling probe that T3 applied to this repo's small readings — so
        *fast* and *partly eliminated* are not separated for them. Unmeasured,
        deliberately, and recorded so a later census does not read the 2 as
        exhaustive.
      - ⚠ **One row is Issues 833/834's class and is NOT folded in:**
        `feeling_brain_p7_goat::g2_auto_tier_tick_overhead_under_50ns_vs_manual`
        measures two sequentially-timed arms (auto 14.16, manual 17.79 ns) and
        reports overhead **−3.63 ns** — negative, so the sign its bar reads is
        decided by the box. It wants the opposite repair (interleave, not
        consume) and a target can carry both.
      - **What is left.** A cross-repo sweep half, still **RATCHET-ONLY**: Until somebody does, a cross-repo
        verdict half must be **RATCHET-ONLY** — the shipped gate's membership
        WALL rests on a per-row MEASURED number, and 27 such rows cost two
        agent sessions of release builds in this repo alone; a wall in a
        sibling would be a wall over an unread bucket, which is exactly what
        T4 refused. And a cross-repo repair is not landed until it is
        COMMITTED in the sibling with a cited SHA (Issue 798).

- [ ] **T6 — the cross-repo sweep half, RATCHET-ONLY.** T5 supplies what the
      wall tier needed and the shipped gate could not have: a MEASURED number
      per sibling row. But 30 of the 32 are SURVIVED readings taken once, on a
      loaded box, without the 4x scaling probe — enough to pin a ratchet on the
      derivative, not enough for a membership wall with a reason per row. ⚠ And
      three of the buckets T5 found are invisible to the current classifier:
      `#[ignore]`d, PRINTS-NOTHING, and UNBUILDABLE. A sweep that reports 33
      rows while 4 of them are never executed and 1 cannot compile is reporting
      a population it has not measured. Decide whether those become reported
      columns (the `print-only` precedent) before the sweep lands, not after.

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
