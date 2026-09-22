# Bench 841 — calibration staleness at the freeze/thaw seam (GOAT gate)

**Status:** PASSED — all four gates, 2026-09-19. Opt-in `calibration_staleness`,
**NOT promoted** (no-default-consumer rule; the named seams are unwired).
Substrate: `katgpt-core::calibration_staleness`. Owner: Issue 841 §B-3
(Research 571).

```bash
cargo bench -p katgpt-core --features calibration_staleness,alloc_tracking \
    --bench bench_841_calibration_staleness_goat
cargo test  -p katgpt-core --features calibration_staleness --lib calibration_staleness
```

## What it gates

A calibration head is fitted against ONE set of weights. The modelless
mandate's first permitted runtime mutation is **freeze/thaw** — swapping a
frozen snapshot — and the moment that lands, every attached head is describing
weights that are gone. Nothing in the stack noticed, because every such head
returns a bare `f32`: `SigmoidGateCalibrator::apply`, `StaticCalTable::get_scale`,
a conformal interval with its `alpha` intact. A stale head does not produce a
NaN or an error. It produces a **confident wrong number**, which is why the
primitive refuses rather than warns-and-continues.

`SnapshotBound<T>` binds a head to the `SnapshotId { version, commitment }` it
was fitted under and returns `None` + one loud warning per binding once that
identity moves.

## Results

| gate | claim | measured | verdict |
|---|---|---|---|
| **G1** correctness | all four predicate arms | `fresh_admits` · `swap_refuses` · `unbumped_swap_refuses` · `unversioned_refuses` | **PASS** |
| **G3** no-regression | an admitted value is bit-identical to the unguarded one | 1001 swept inputs, `to_bits()` equal | **PASS** |
| **G2** perf | guard ≤ the calibrated `apply` it protects | run 1: guard **1.155**, apply(sigmoid) **1.469**, refuse **1.657** ns/call → **ratio 0.786**. run 2: **1.525** / **1.829** / **2.010** → **ratio 0.834** (budget ≤ 1.00) | **PASS** |
| **G4** alloc-free | zero allocations on both paths | **0 allocs / 0 bytes** over 10 000 mixed fresh+stale calls | **PASS** |

**Box state** (AGENTS.md § *A latency number without its BOX STATE is not a
measurement*): M3 Max, `--release`/bench profile, loadavg **7.78 / 10.59 /
7.43**, ~24.1 GB free, concurrent sibling agent sessions active. Figures are
**best-of-9 minima over 200 000 iters/round** — the minimum, because a loaded
box can only make a round slower. Take the ratio as a magnitude; a quiet-box
re-measurement is owed before any number here is quoted as a floor.

⚑ **Two runs are recorded because one is an anecdote.** Identical binary, minutes apart, same box: the absolute figures moved **32%** (1.155 → 1.525 ns/call) while the RATIO moved **6%** (0.786 → 0.834). That is the argument for gating on the ratio and reporting the absolutes as magnitudes — both arms ride the same box, so the ratio is the part that survives the load. It is still not a paired A/B; see the G2 caveat above.

⚠ **G2 is an ABSOLUTE budget, not an A/B ratio.** The two arms are not paired
comparisons of the same work, so AGENTS.md § *A ratio of two SEQUENTIALLY-timed
arms measures the BOX* applies and the target states a budget instead. The
`assert!(acc.is_finite())` inside the timing loop is Issue 855's class: a loop
whose result is discarded is a loop LLVM may delete, and the ceiling would then
be satisfied by nothing running.

⛔ **G4 is compiled out without `alloc_tracking`**, and the target prints a loud
`⛔ NOT MEASURED` rather than passing silently — a green run with G4 compiled
away is otherwise indistinguishable from a green run with G4 satisfied
(Issue 741's class).

## The predicate, and why each rule is load-bearing

Generalised from `DefaultMpiRouterSnapshotHook::cache_valid` (katgpt-spectral),
the one shipped version-keyed invalidation at a swap boundary. Both of its
rules are kept verbatim, each with its own arm:

1. **Generation `0` is never fresh** (`t03`, `t04`). A `0`-vs-`0` pair compares
   equal on both fields, so an equality-first predicate reports `Fresh` and the
   *unwired* call site — the one this primitive exists for — reads clean
   forever. The arm pins the ORDER of the checks, not just the answer.
2. **The commitment is re-checked under a held generation** (`t05`). Catches
   the bug the version cannot see: weights swapped, counter not bumped. It gets
   its own verdict (`CommitmentMoved`) and is never pooled into `VersionMoved`,
   because the repairs are opposite — one is a refit, the other is a broken
   bump site.

`t14` pins the trap a naive adoption falls into: `SWTF_VERSION` / `SDBF_VERSION`
are **format** versions, `1` for every snapshot ever written. A `SnapshotId`
built from one holds the generation constant, the version half can never fire,
and the guard **silently** degrades to the commitment check alone.

## Why `None` and not a default

`StreamingTauCalibrator` falls back to `DEFAULT_TAU_LO`/`HI` below `min_samples`
and is right to: a cold start has no fitted claim to be wrong about. A stale
head does. The caller decides refit-vs-abstain-vs-run-uncalibrated — the
`CalibratedPolicy::fell_back` precedent, *"the caller is told, not protected by
accident"*.

## Promotion decision — NOT promoted

Opt-in, per the no-default-consumer rule. The gain is real and modelless, but
the primitive guards nothing until a seam is wired, and wiring one changes a
shipped signature to `Option`. The seams, measured and named:

| seam | file | what goes stale |
|---|---|---|
| `FuncAttnSnapshotStore::swap` | `katgpt-attn/src/funcattn_compose/freeze_thaw.rs:262` | the bump site — already carries `version: u64` + `blake3`, so it is the one seam that can supply a real `SnapshotId` today |
| `StaticCalTable::get_scale` | `katgpt-attn/src/static_cal.rs:41` | per-head attention scales, bound to specific weights; returns a bare `f32` via `get_unchecked` |
| `CalibratedVerifier::verify_embedding` | `katgpt-claim/src/clr/calibration.rs:156` | the Platt pair; its own module doc already argues the staleness and ships no mechanism |
| `ConformalIntervalCalibrator` | `katgpt-core/src/conformal/mod.rs:165` | the residual pool — **default-on**, so this is the widest-reach seam and the one whose wiring needs its own gate |

⚠ Neither `katgpt-attn` nor `katgpt-claim` depends on `log`, which is why the
warning fires in katgpt-core and the guard type lives there.

## What this does NOT claim

- It does not detect staleness from **distribution drift**, a changed prompt
  mix, or a tokenizer change. `Some` means the *snapshot identity* is
  unchanged — it is not evidence of freshness.
- It cannot invalidate a head somebody read out via `peek_unchecked`. That
  method is named to be greppable for exactly that audit.
- `rebind` asserts the caller actually refitted. Calling it to silence a
  warning re-attaches a stale head under a fresh-looking identity, which is
  worse than the original defect — the guard then certifies it.
