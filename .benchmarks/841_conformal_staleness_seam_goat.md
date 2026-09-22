# Bench 841 — seam 4: the conformal calibrator at the freeze/thaw seam (GOAT gate)

**Status:** PASSED — all five gates, 2026-09-19. Opt-in `calibration_staleness`,
**NOT promoted** (no-default-consumer rule: the guard is an additive sibling and
nothing default-on calls it). Substrate: `katgpt-core::conformal::staleness`.
Owner: Issue 841 §B-3, seam 4 of 4.

```bash
cargo bench -p katgpt-core --features calibration_staleness,alloc_tracking \
    --bench bench_841_conformal_staleness_seam_goat
cargo test  -p katgpt-core --features calibration_staleness --lib conformal::staleness
```

## Why this seam owes its own gate

[Bench 841](841_calibration_staleness_goat.md) measures a guard in front of an
`apply`, and for seams 1-3 that is the whole cost model: a per-head scale, a
Platt pair and a verifier threshold are pure functions of their fitted
parameters, so a refusal costs exactly one call and nothing accumulates.

⛔ **A `ConformalIntervalCalibrator` also GROWS its calibration.** It pushes one
residual per observation, so an unguarded snapshot swap does not merely make the
next read stale — it **contaminates the pool**, and the contamination *heals*:
after a ring-buffer's worth of post-swap observations the pool looks freshly
fitted and describes a distribution neither model has. `verify()` cannot see it,
a commitment cannot see it, and a coverage readout cannot see it, because the
empirical coverage of a mixture can sit anywhere. A conformal interval's
guarantee rests on **exchangeability** between the calibration residuals and the
test residual; swapping the forecaster under a live pool breaks that premise in
silence, and the interval keeps being emitted at full apparent confidence.

That is what G5 measures, and it is why the WRITE half is guarded and not only
the read.

## Results

| gate | claim | measured | verdict |
|---|---|---|---|
| **G1** correctness | six predicate arms, read AND write | `fresh_read` · `stale_read_refuses_and_leaves_out` · `stale_write_refuses_and_pool_unchanged` · `fresh_write_lands` · `unbumped` · `unversioned` | **PASS** |
| **G3** no-regression | an admitted interval is bit-identical to the unguarded one | 1001 swept points, `to_bits()` equal on **all three** fields | **PASS** |
| **G5** the claim | the write guard prevents a measurable, silent miscoverage | unguarded `[-0.834, 0.801]`, **81.9%** coverage vs 90% nominal (**8.1 pt** deficit, bar ≥ 5.0); guarded **0** intervals emitted, **256 of 256** post-swap writes refused; refit `[-0.930, 0.901]`, **91.6%** (‖Δ‖ ≤ 3.0 pt) | **PASS** |
| **G2** perf | the guard, and the guarded call END TO END | guard **2.459** ns/call, `interval_from_point` **3069.3** ns/call, checked end-to-end **2874.1** ns/call → `guard/work` **0.00080** (≤ 1.00), `checked/work` **0.9364** (≤ 1.25) | **PASS** |
| **G4** alloc-free | zero allocations on read AND write paths | **0 allocs / 0 bytes** over 10 000 mixed fresh/stale read+write calls | **PASS** |

**Box state** (AGENTS.md § *A latency number without its BOX STATE is not a
measurement*): M3 Max, bench profile, loadavg **37.4 / 38.7 / 30.4**, ~1.4 GB
free + ~25.1 GB inactive, three concurrent cargo builds and sibling agent
sessions active. A **loaded** box. That is adequate for G1/G3/G4/G5, none of
which is a timing verdict, and it is why G2 is read as a best-of-9 **minimum**
and why its two budgets are loose.

## ⛔ G2's first reading was 2.70x, and it was a measurement of the loop bodies

The first version of this gate timed the unguarded arm writing into a
`PredictiveInterval` hoisted **above** the loop and the guarded arm constructing
its own, and reported:

| arm | first (unpaired) | paired |
|---|---|---|
| `interval_from_point_into` | 5800.3 ns/call | **3069.3** |
| `..._checked` end to end | 15657.5 ns/call | **2874.1** |
| ratio | **2.70x** | **0.9364** |

A 2.70x "guard cost" for a 32-byte compare measured at **2.459 ns** in front of
a ~3 µs quantile read was not credible, and the resolution was to make the two
loop bodies identical rather than to explain the number. Both arms then moved —
the *unguarded* one by 1.9x — which is the tell that the shape, not the guard,
was the subject. AGENTS.md § *A ratio of two SEQUENTIALLY-timed arms measures
the BOX* is the rule; this is the same rule one level down, where the confound
is the **loop body** rather than the box.

⚠ `checked/work = 0.9364` is **not** a speedup and must not be read as one. A
guarded call cannot be cheaper than the same call unguarded; 6% under 1.0 is the
residual spread of two sequentially-timed arms on a box at loadavg 37. The
honest statement is *the guard is not measurable against the work it fronts*,
which is what the isolated `guard/work = 0.0008` says independently.

## What G5 does and does not claim

- The middle column — **0 intervals emitted** — is the guard's own
  contribution. The outer two columns exist to give that zero a **size**.
- ⚠ The deficit's *magnitude* is a property of the constructed swap (model A's
  errors 10x narrower than model B's, a 50/50 pool). It is a demonstration that
  the hazard is real and quantifiable, **not** an estimate of what any
  particular deployment would lose.
- The direction is chosen deliberately. Narrow→wide **under-covers**, which is
  the dangerous direction; wide→narrow over-covers and merely wastes width. A
  gate built on the over-covering direction would have been satisfied by a
  harmless failure.
- ⛔ The unguarded interval is **finite and well-formed**. Nothing about
  `[-0.834, 0.801]` reads as broken, which is the whole reason a guard is needed
  rather than a validity check on the output.

## Not promoted

`conformal_predictive_intervals` is default-on; the **guard** is not, and
nothing default-on calls it. Promotion is governed by the no-default-consumer
rule exactly as seams 1-3 are: a default build is byte-identical (G3 measures
this over 1001 points), and the row that could earn promotion is a default-on
*consumer* choosing to bind, which is an owner call and not this gate's to make.
