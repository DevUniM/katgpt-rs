# Issue 773 — katgpt-rs root lib E0432 under `flashar_consensus,plasma_path`: the 772-B2 removal deleted `ternary_fusion_gate` from katgpt-forward but left the root shim's re-export

**Status:** OPEN — filed 2026-09-14, found by riir-ai's post-bump full-guard run (Layer 1 died compiling the path-depped katgpt-rs root crate)

## Finding

`3c3c52ce` (Issue 772 A1/A2+B1–B5+S1–S5, B2) removed
`ternary_fusion_gate` + `ConsensusConfig.use_ternary_gate` from
`crates/katgpt-forward/src/flashar_consensus.rs` (the REMOVED ledger
comment sits at line 322) but left the root shim's gated re-export:

```
src/speculative/flashar_consensus.rs:17-19
// `ternary_fusion_gate` is gated `plasma_path` upstream.
#[cfg(feature = "plasma_path")]
pub use katgpt_forward::flashar_consensus::ternary_fusion_gate;
```

Proof (both directions, this box, katgpt-rs @ `1ae67cfb`):

```
$ cargo check -p katgpt-rs --lib --features flashar_consensus,plasma_path
error[E0432]: unresolved import `katgpt_forward::flashar_consensus::ternary_fusion_gate`
  --> src/speculative/flashar_consensus.rs:19:9
```

`cargo check -p katgpt-rs --lib` (default features) is GREEN — the shim
module is compiled only under `flashar_consensus`
(`src/speculative/mod.rs:324`), which is not a default feature, and the
stale re-export is additionally `plasma_path`-gated. That double gate is
why the 772 wave's own validations (default-lane clippy + `--lib` tests)
never saw it: the cfg-gated-target green-zero class this repo's AGENTS.md
documents, biting its own landing lane.

**Blast radius:** every consumer whose feature graph enables
`katgpt-rs/flashar_consensus` + `plasma_path` — measured live: riir-ai's
`ci_feature_guard.sh` Layer 1 (workspace baseline, default features —
riir-ai's default graph forwards both) dies with E0432 before any riir-ai
crate is checked. No in-repo consumers of the symbol exist (grep over
src/ crates/ tests/ benches/ = the stale re-export itself only); no
downstream sibling references it (grepped riir-ai, riir-neuron-db,
riir-chain, riir-game-sdk, seal-remake, riir-mmorpg-examples).

## Fix

Delete the stale re-export + its comment (3 lines). The item is gone
upstream by owner verdict (772 B2); the re-export cannot compile and
nothing consumes it.

## Validation

- `cargo check -p katgpt-rs --lib --features flashar_consensus,plasma_path`
  — red before, green after.
- `cargo check -p katgpt-rs --lib` — green before and after (no default
  surface change).
- riir-ai full guard re-run — the original red reporter — lands green past
  Layer 1 (tracked in riir-ai Issue 944's validation note).
