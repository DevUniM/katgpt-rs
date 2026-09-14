# Issue 774 — `wasm32_surface_audit.py` is DEP-BLIND: a lane building a package TRANSITIVELY reads as UNCOVERED

**Status:** OPEN (instrument-honesty record + one measured false positive; the resolver upgrade is design work, not a patch)

**Date:** 2026-09-14
**Source:** the quiet-repo audit sweep (cfg-gated / percentile / wasm32 surface,
  scoped per-repo to avoid sibling-hot trees).

## What was measured

`scripts/wasm32_surface_audit.py ../riir-shader` reports:

```
      ✗ UNCOVERED    riir-shader-core  (1 site(s))
      ✗ UNCOVERED    riir-shader-effects  (2 site(s))
      ✓ named        riir-shader-showcase  (27 site(s), 7 file(s) walked)
```

The two UNCOVERED verdicts are FALSE, and the falseness is measured, not
argued:

- `crates/riir-shader-showcase/Cargo.toml` carries path deps on
  `riir-shader-core`, `riir-shader-effects` AND `riir-shader-pattern`.
- `scripts/build-wasm.sh` builds `-p riir-shader-showcase
  --profile wasm-release --target wasm32-unknown-unknown` — every bundle
  build compiles core + effects (and their positive wasm32 cfg arms) for
  wasm32.
- `cargo check -p riir-shader-effects --target wasm32-unknown-unknown`
  exits 0 in 30.3s (2026-09-14, this box) — the arms are live, COMPILING
  code, not the uncompilable-since-written class the UNCOVERED bucket
  exists to catch (the seal-remake `.issues/010` / Issue 737 lineage).

The effects sites in question (`adaptive_quality.rs:629` `page_visible`,
`:646` `install_battery_bridge`) are real browser code (`web_sys` /
`js_sys` via `Reflect`) — exactly the surface a lane-gap verdict should
be able to see is exercised.

## Why the resolver misses it

The audit's coverage predicate is ROW-based: a package is NAMED only when
a lane row selects it by `-p <name>` or a literal `--manifest-path`. The
two-shape resolver (Issue 738 T1) upgrades derived rows from row-bearing
lane files, but nothing models the DEPENDENCY EDGE — a row that selects a
package which path-deps on an UNCOVERED package builds that package too.
For path-dep workspaces (every repo here) the row-blind half is exactly
the transitive half.

## The honest caveat, both directions

- Not every UNCOVERED row is a false positive: a registry dep's wasm32
  code is `--cap-lints`'d and irrelevant, but a PATH dep's positive cfg
  arm is ours and needs the lane. The upgrade must credit PATH deps only
  (the manifests are local; no cargo invocation needed — a
  `[dependencies]` table read over workspace members).
- Transitive credit must not collapse the real catch: seal-remake's
  `.issues/010` arm was uncompilable even though a lane selected its
  CONSUMERS — the arm existed in a package nothing selected AND nothing
  depended on it for wasm32. Crediting path-dep edges keeps that verdict
  true (nothing depended on the broken arm's package on the wasm32 lane).

## Proposed upgrade shape (design note, not spec)

One pass over the repo's workspace members: build
`package -> set(path-dep packages)` from each member manifest. A package
with positive wasm32 cfgs is COVERED-by-dep when any NAMED package
reaches it through path-dep edges (transitive closure). Report it as a
NEW third verdict — `BY-DEP` — never folded into NAMED: the distinction
is load-bearing (a BY-DEP package's wasm32 arm can break by an innocent
dep-graph edit, and the reader should know which kind of coverage they
have). Floors re-pinned per repo after the upgrade lands.

## Related

- Issue 737 (the wasm32 lane family), Issue 738 T1 (the two-shape
  resolver this extends), seal-remake `.issues/010` T2 (the real catch
  that must stay a catch), riir-chain `bc6d4802` (same sweep's other
  finding, the cfg-gated green-zero row — different instrument, same
  quiet-repo posture).
