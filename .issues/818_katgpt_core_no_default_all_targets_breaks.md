# Issue 818: four katgpt-core test/bench targets break the no-default `--all-targets` state

**Status:** Open — filed 2026-09-17 (repro measured this session while wiring Plan 599 Phase 4; the Plan 599 session's handoff named 3 targets, the repro found **4**).
**Repo:** katgpt-rs (`crates/katgpt-core`)
**Repro (measured):**

```bash
cargo check -p katgpt-core --no-default-features --all-targets
# error: could not compile `katgpt-core` (bench "bench_371_mean_field_regime_goat")
# error: could not compile `katgpt-core` (test  "bench_416_region_subspace_goat")
# error: could not compile `katgpt-core` (test  "bench_778_subspace_intervention_poc")
# error: could not compile `katgpt-core` (test  "velocity_field_ensemble_alloc_check")
```

## The four targets

| Target | Kind | Defect class |
|---|---|---|
| `benches/bench_371_mean_field_regime_goat.rs` | bench (harness=false, `[[bench]]` row present — required-features row REMOVED when mean_field_regime was promoted default-on, Plan 371 Phase 6) | E0601 `main` not found under no-default: the binary body is feature-conditional but carries no `#![cfg]`/required-features; the promotion removed the row instead of moving the gate |
| `tests/bench_416_region_subspace_goat.rs` | integration test | E0432 imports `katgpt_core::velocity_field_ensemble` + `subspace_phase_gate` (both opt-in) with NO whole-file `#![cfg(feature = ...)]` and NO `required-features` row |
| `tests/bench_778_subspace_intervention_poc.rs` | integration test | E0432 under no-default — same class: imports an opt-in surface, no `#![cfg]`, no row |
| `tests/velocity_field_ensemble_alloc_check.rs` | integration test | E0432 imports `katgpt_core::velocity_field_ensemble` — no `#![cfg]`, no row |

## Why it matters (the standing rules)

- The no-default `--all-targets` state is the "every gated target compiles at its own feature set" axis: a `#![cfg]`-gated target with a missing `required-features` row compiles to an EMPTY binary and prints `ok. 0 passed` (the green-zero trap, Issue 713's class); a target with NO cfg at all fails to compile outright (this issue). Both directions break the claim "the manifest's targets build at their declared feature sets".
- The `bench_371` row is the promotion-time hazard: demoting/promoting a feature must MOVE the gate (`#![cfg]` or a re-added `required-features` row), not delete it. The comment says "required-features removed: mean_field_regime is now DEFAULT-ON" — true at default, false at no-default.

## Fix shape (owner/plan-lane work, not urgent)

1. `bench_416` / `bench_778` / `velocity_field_ensemble_alloc_check`: add `#![cfg(feature = "<the feature they import>")]` AND the matching `required-features` row (both halves — the cfg protects the count, the row protects the reader).
2. `bench_371`: since `mean_field_regime` is DEFAULT-ON, the cheapest correct state is a `#![cfg(feature = "mean_field_regime")]` at the top (compiles to nothing + row-silent when off, honest `0 passed` with the required-features row re-added) or simply re-adding `required-features = ["mean_field_regime"]` (it is default-on, so plain `cargo test` still runs it; only `--no-default-features` skips it, which is the point).

## Refs

- Found while wiring Plan 599 Phase 4 (the handoff summary carried the 3-target list; the measured repro added `velocity_field_ensemble_alloc_check`).
- Issue 713 / Issue 723 (the green-zero + required-features doctrine), katgpt-rs AGENTS.md §"cfg-gated targets".
