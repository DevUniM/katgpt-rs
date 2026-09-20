# Issue 861: ugc_alloc_check G4 fails on Windows/MSVC debug — 1 heap alloc per bernoulli_unmask_with_grid call, release-clean

**Status:** OPEN (filed from the Plan 602 T2.2 session, 2026-09-20)
**Affected:** `crates/katgpt-core/tests/ugc_alloc_check.rs` · `crates/katgpt-core/src/ugc_schedule.rs::bernoulli_unmask_with_grid`
**Landed-at:** the test shipped with Issue 664 (`3bb115da`, "G4 PASS" claim)

## Symptom

`cargo test -p katgpt-core --test ugc_alloc_check` (debug, default features)
fails on this Windows/MSVC box:

```
G4: 50 allocations across 50 estimate_interval + 50 sampler calls
assertion `left == right` failed: steady-state allocations detected: 50
```

Exactly **1 allocation per sampler call**, steady state (after the 3-iteration
warm-up).

## Measured characterization (2026-09-20, this box)

| experiment | result |
|---|---|
| HEAD (clean, T2.2 stashed) | **FAILED 50** — pre-existing, not caused by Plan 602 T2.2 |
| T2.2 applied (`steps_out: None` passed) | **FAILED 50** — identical count: the T2.2 change is alloc-neutral |
| measured loop reduced to `bernoulli_unmask_with_grid` ONLY | **FAILED 50** — the allocation is in the sampler call, not `estimate_interval` |
| test denoiser replaced by a flat `out[0]=out[1]=0.5` (no `powi`) | **FAILED 50** — not the test-side `NoisyBit` math |
| `--release` | **PASSED, 0 allocations** |

So: debug-profile-only, per-call, MSVC/Windows, release-clean. The
"profile is part of the claim" axis (AGENTS.md full-gate table) — the
Issue-664 G4 PASS was presumably measured on macOS/aarch64 or at a profile
where the allocation does not occur.

## Why nothing caught it

`test_gate.sh` runs `--lib` only; the x86_64 execution matrix's integration
cell covers the ROOT package's tests; **no automatic lane executes
katgpt-core integration tests** (the standing "executed by nothing" class).

## Non-causes (ruled out)

- `steps_out` recording (absent at HEAD)
- the test denoiser's `f64::powi`
- `estimate_interval` (isolated out)
- scratch regrowth (capacity `with_capacity(d)` covers every `extend`; clear()
  retains capacity)

## Suspects / next step

Nothing in `bernoulli_unmask_with_grid` visibly touches the heap
(`kl_discrete`/`sample_categorical`/`reset_obs` are pure; `masked_buf` is
take/restore within capacity). Prime suspect is a debug-only MSVC runtime or
std path (lazy TLS/errno machinery) reachable through some intrinsic under
`debug_assertions`. Next step for whoever picks this up: temporarily extend
`counting_allocator!()` to `Backtrace::force_capture()` on the first
allocation inside the measured loop and read the site directly.
