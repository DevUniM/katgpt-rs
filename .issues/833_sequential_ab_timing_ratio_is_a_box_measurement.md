# Issue 833: a ratio of two SEQUENTIALLY-timed arms measures the box, not the code — `bench_105` GOAT 2 fired on x86_64, and the class is ~57 targets, not one

**Status:** T1 **DONE 2026-09-18** (`bench_105_gdn2_goat` GOAT 2 migrated + stability
measured). T2–T4 OPEN — the class is a **magnitude, not a pin**; see §What must not be
done.
**Found by:** `scripts/x86_64_execution_matrix.sh` at `d7a34822`, cell 8
(`katgpt-rs --tests --release`, `+avx2`), log `/f/matrix_0918_run1.log`. The matrix
verdict overall was **PASSED — 8 cells, 11176 assertions, 0 CONFIRMED failures, 0 pinned
rows**; this row surfaced as **PASSED-ALONE** (failed in the cell, passed 3/3 when re-run
alone), which that script prints with an explicit warning that it is an *observation, not
a diagnosis*.

## The class

```rust
let start_a = Instant::now();  for _ in 0..ITERS { arm_a(); }  let elapsed_a = start_a.elapsed();
let start_b = Instant::now();  for _ in 0..ITERS { arm_b(); }  let elapsed_b = start_b.elapsed();
assert!(elapsed_a / elapsed_b >= BAR);
```

Arm A runs to completion, then arm B runs to completion, and the verdict is the single
ratio. The two arms therefore occupy **different load windows**, so anything that moves
the box between them lands entirely on whichever arm ran second. Issue 723 T5 measured two
sequential arms of *the same work* at **+5.2% and +21.7% thirty seconds apart**; a 10% bar
cannot survive that, and neither can most of the bars in this repo.

This is **Issue 723 Class A**, and its treatment already exists and is already prescribed
by AGENTS.md: `tests/common/ab_timing.rs::ab_median_ratio` — interleaved `(a-chunk,
b-chunk)` pairs so a drift moves **both** arms and cancels in the ratio, the **median**
across pairs so one preemption spike is discarded, and a **loud zero** when an arm is
optimised away.

## Adjudication — the matrix names three classes and they need opposite responses

`x86_64_execution_matrix.sh` prints all three beside a PASSED-ALONE row. All three were
checked on this file rather than assumed (the third grep set was run independently by a
concurrent session, `katgpt-rs-c5`, which reached this row from the same matrix run):

| class | verdict | evidence |
|---|---|---|
| CONCURRENCY on a shared path | **ruled out** | 0 `env::temp_dir()` / `"/tmp"` sites in the file |
| unseeded-RNG coin flip | **ruled out** | 0 unseeded draws; 5× seeded `Rng::new(42)` |
| load-sensitive perf BAR | **CONFIRMED** | wall-clock `Instant::now()` ratio of two sequentially-timed arms |

⚠ Filing this as TRANSIENT would have been the Issue-832 mistake in its other direction —
832's defect *also* passed alone, by construction. PASSED-ALONE is evidence about the
class, never a dismissal.

## T1 — `bench_105_gdn2_goat` GOAT 2 (DONE 2026-09-18)

`goat_2_gdn2_within_10pct_of_ahla_throughput`, Plan 105 criterion 2, `gdn2_attention` +
`hla_attention` — **both reachable at DEFAULT features** (`gdn2_attention` is in `default`
and `lt2_looped` → `hla_attention`), which is why cell 8 executes it at all.

- Migrated to `ab_timing::ab_median_ratio`, `a` = AHLA (the baseline the criterion is
  *stated against*), `b` = GDN2. ⚠ `ab.median` is therefore a **time** ratio and the
  criterion's **throughput** ratio is its reciprocal — getting that backwards inverts a
  gate silently, which is the defect riir-ai Issue 977 was filed for one instrument over.
- ⚠ `ab_median_ratio`, **not** `best_of_us`: that module reserves `best_of_us` for an
  ABSOLUTE budget with no second arm, and taking a minimum per arm independently would
  compare two different load windows. Same distinction Issue 831 T2 had to make.
- **`ITERS` 500 → 5000 on the measurement, not on taste.** At 500 the per-round chunk was
  ~153 µs and the printed per-round RANGE came back **0.7310 .. 2.9859** around a 1.0028
  median — a 4× swing. The median was already doing its job; a bar read off rounds that
  noisy is one preemption from being interesting. The whole target costs 0.07 s. **The
  RANGE is the quantity that told us this — a median alone would have looked finished.**

**Stability, the claim this issue exists to fix.** Release binary run directly out of
`target/release/deps/` per AGENTS.md's diagnose-by-binary rule, `--exact`, on a box that
was NOT idle (a sibling cargo build held the lock during the run):

| run | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| median b/a | 0.9868 | 0.9838 | 0.9922 | 0.9839 | 0.9914 | 0.9905 | 0.9775 | 0.9855 |

**8/8 pass**, medians inside a **1.5%** band (0.9775 .. 0.9922), against a fail threshold
of 1.1111. Per-round ranges stayed wide (0.84 .. 1.26) — which is the point: the rounds
are noisy, the median is not.

Two independent readings bracket what the old form was doing. On an **idle** box at the
original `ITERS`, `katgpt-rs-c5` measured per-round **0.9020 .. 1.0607** — so individual
rounds swung ±6% with nothing else running at all. The matrix's **failing** in-cell sample
read **0.844**, outside even that idle band. A single sample of this quantity was never a
measurement of the primitive.

## The class is ~57 targets, and that number is a MAGNITUDE

Census by `katgpt-rs-c5` over the tracked walk of `tests/` + `benches/`, **324 timed
targets**:

| bucket | count |
|---|---|
| ADOPTED (uses `common/ab_timing.rs`) | 7 |
| **DECIDED** — two-timing-arm ratio | **57** |
| UNRESOLVED — timed, ratio unclear | 148 |

Predicate: ≥2 `Instant::now()` **and** a ratio whose *both* sides are timing-derived
identifiers, minus count-like denominators (`iters` / `n_tokens` / `len` / `steps`). An
independent looser pass from this session over `tests/*.rs` + `crates/*/tests/*.rs` alone
returned 55, so the magnitude is corroborated by two predicates that disagree about the
population.

⛔ **UNRESOLVED is not clean** and is not foldable into either neighbour — it is 148
per-file reads, and this repo's rule is that a bucket meaning *unanswered* is never
counted as a pass and never ratcheted (Issue 785).

Worked examples from the DECIDED set, same shape as `bench_105`:

| target | ratio | sites |
|---|---|---|
| `tests/bench_108_lt2_looped.rs` | `sdpa_tps / loop_tps` | 9 |
| `tests/bench_simd.rs` | `sparse_tps / dense_tps` | 11 |
| `tests/bench_turboquant_zero_alloc.rs` | `flat_us / tq_us` | 24 |
| `crates/katgpt-core/benches/bench_417_cross_resolution_simd_encode_goat.rs` | `baseline_ns / candidate_ns` | — |
| `tests/channel_simd_goat.rs` | `unaligned_us / aligned_us` | 5 |

**So this is the "landed in one instrument and never generalised" shape AGENTS.md records
about nine times** (Issues 777, 778, 793, 782, 783, 789, 797). Issue 723 built the
treatment and converted the 8 targets its census could see; Issue 831 converted a 9th today
by walking into it; `bench_105` is the member that happened to fire on x86_64. **None of
the three was found by the census — all three were found by something failing.**

## Why the matrix found it and nothing else did

`bench_105_gdn2_goat` is an **integration target**, and AGENTS.md's own table says
integration targets are executed by nothing automatic: `full_gate` is macOS compile+lint,
`wasm32_gate` builds a third triple, and `test_gate` is `--lib`-only on four crates. The
x86_64 execution matrix is the only lane that runs it, it is a **workstation** instrument
with no CI lane, and it had not run since 2026-09-16.

## What must not be done

⛔ **Do not raise or lower the bar.** The 0.90 bar is not what was wrong; the instrument
was. GDN2 measures 0.98–0.99 of AHLA's time — comfortably inside the criterion — and the
bar stays at 0.90.

⛔ **Do not add a verdict half (a gate or a drift sweep) yet.** Every other class in this
repo has one, and the symmetry is not an argument: 148 UNRESOLVED means the classifier is
nowhere near calibrated enough to gate on, and a ratchet over an unread bucket is a backlog
wearing a pin. Re-measure before answering, exactly as `check_validation_gate` §T4 requires
and `console_encoding_gate` failed to do.

⛔ **Do not pin the row into `scripts/x86_64_matrix_expected.txt`.** That file is
deliberately EMPTY and this was never an arch difference — it is a defective instrument
that any loaded box can trip. It is repaired, not excused.

## Tasks

- [x] **T1 — migrate `bench_105` GOAT 2** to `ab_median_ratio`, size the chunk off the
  measured per-round range, and record the distribution rather than one green run.
- [ ] **T2 — the 57 DECIDED targets.** Per target, not mechanically: each needs its `a`/`b`
  orientation decided (which arm is the baseline the claim is *stated against*), its chunk
  sized off its own printed range, and its arms `black_box`ed at input and output — the
  `let _ = f()` elimination shape is orthogonal to interleaving and survives it.
- [ ] **T3 — read the 148 UNRESOLVED.** Each resolves to DECIDED, to a legitimate
  count-denominated rate, or to a timing that feeds no assertion. Until then the 57 is a
  floor on the class, not its size.
- [ ] **T4 — re-measure whether a verdict half is warranted** once T3 lands and the
  classifier has a calibrated population. Not before.
- [ ] **T5 — the cross-repo question is UNMEASURED.** `ab_timing.rs` is a katgpt-rs test
  module; whether the siblings carry the same shape has not been looked at, and the
  measurement comes before the answer.

## Records

- Matrix run: `/f/matrix_0918_run1.log`, `d7a34822`, 8 cells / 11176 assertions, PASSED
- The treatment + its three defenses: `tests/common/ab_timing.rs` (Issue 723 Class A, T7)
- The sibling migration that landed the same day: Issue 831 T2 (`bench_171` P3)
- Census + independent idle-box verification: session `katgpt-rs-c5`, 2026-09-18
