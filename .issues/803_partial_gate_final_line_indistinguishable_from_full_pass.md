# Issue 803 (2026-09-15) — the off-macOS partial gate prints the SAME final line as a full pass

> ⚑ **Renumbered 799 → 803 on 2026-09-16**, unpushed, by the Issue-796 rule:
> `dual_allocation_gate.py` reported INDEPENDENT — this box and origin had
> both allocated 799 since their merge base (origin's is the bevy_ecs
> bump-vs-retire boundary question, `2779bf87`). Adjudicated by inbound
> mentions per Issue 724 T2 and it is not close: origin carries **5**
> across `.benchmarks/799_bevy_ecs_019_bump_arena_goat.md`, `BOUNDARY.md`
> and `HISTORY.md`, this side **1** (AGENTS.md). Origin keeps the number;
> this document moves, and `.highwater` went 802 → 803. The gate is the
> reason this was caught before the push rather than at merge time.

## The finding, in two halves

### Half 1 — `develop` was red under the quoted gate command

`cargo clippy --workspace --all-targets --all-features` — the string AGENTS.md
quotes as the whole-repo claim, and which `scripts/full_gate.sh` Layer 5 asserts
AGENTS.md still quotes — reported on `develop`:

**24 × `error[E0560]: struct katgpt_core::ParallaxConfig has no field named
zero_init`**, across six root-package targets:

| target | sites |
|---|---|
| `tests/bench_140_sigmoid_parallax.rs` | 8 |
| `tests/bench_140_sigmoid_parallax_adamw.rs` | 8 |
| `tests/bench_135_parallax_attn.rs` | 5 |
| `tests/funcattn_g2_funcattn_vs_parallax_vs_sdpa.rs` | 1 |
| `tests/parallax_sigmoid_stability_grad_clip.rs` | 1 |
| `benches/sink_aware_forward_bench.rs` | 1 |

plus **4 `-D`-listed mechanical lint errors** in `crates/katgpt-core/src/dual.rs`
(lib test unit): `unusual_byte_groupings` (`0x775_FD`), `unnecessary_cast`
(`(… as f64) as f64`), and two `needless_range_loop`. Those four are on the
list AGENTS.md describes as "healed to ZERO residual", so they are gate
failures, not warnings.

The E0560 half was introduced by `a11b2dd8` (2026-09-15 05:28 +0700), which
deleted the inert field. That commit is careful work — orphan-report
adjudication, wire-vs-delete protocol, convention text rehomed — and its gate
line reads `cargo test -p katgpt-core --features parallax_attn --lib parallax`
plus `clippy --features parallax_attn -D warnings`, with the body claiming
*"No external constructors: `ParallaxConfig` literals exist only in the module's
own `tests.rs`"*. Both halves of that are the blind spots AGENTS.md already
tabulates: a `-p`-scoped run with no `--all-targets` cannot compile the ROOT
package's `tests/` and `benches/`, and a grep claim is what a `-p`-scoped
verdict feels like from the inside. Nothing careless happened; this is the exact
failure the axis table exists to describe, reached by somebody being careful.

### Half 2 — the reason it sat there is the interesting half

The first draft of this issue said "there is no lane". **That was wrong, and the
truth is worse.** `scripts/full_gate.sh --allow-partial-platform` has existed
all along and runs every layer on any host. What it does at the end is:

```
✓ full gate PASSED — 0 errors, 0 unbuildable targets (N warning finding(s) …)
```

— byte-identical to a real macOS full run. The partial-ness is announced only by
a Layer-2 `⚠ not macOS — …  This run is a PARTIAL gate` roughly six hundred
lines of build output earlier.

That is this repo's own most-repeated rule, violated by the one instrument that
is not a sweep:

> the deferral rides each check's final line, the one `docs_gate.sh` forwards
> … a deferral printed only on failure is one nobody reads on the run that
> passes

Eighteen drift sweeps, `docs_gate.sh`, `issue_citation_gate.py`,
`sweep_population.py` — all of them carry `DEFERRED` / `PARTIAL CLONE` /
`STALE` / `CPU SUPPRESSED` on the **final** line, in both directions. The full
gate has the vocabulary for partial measurement and spends it on a line that
scrolls away.

So the honest statement of the gap is not "the lane does not exist". It is:
**the one box that can compile this repo's x86_64 half has a working lane whose
output is indistinguishable from the authoritative one**, and the incentive that
follows is to not run it.

## Tasks

- [x] **T1** Repair the 24 E0560 sites (delete the stale field from each
  literal). Verified: the class is gone from the quoted command.
- [ ] **T2** The 4 `-D`-listed lint errors in `dual.rs` — `cargo heal` first per
  the house rule, manual second.
- [ ] **T3** The final line must carry the partial verdict. `--allow-partial-platform`
  (and a missing-wasm32 partial) prints a distinct, self-describing final line
  naming what was NOT measured — the macOS device-backend surface, by count, as
  Layer 2 already computes it. A full macOS run is unchanged. The existing
  refusal without the flag is unchanged.
- [ ] **T4** Name the lane in AGENTS.md next to `test_gate.sh`, with its
  standing: a workstation PARTIAL verdict, the same standing as the eighteen
  drift sweeps, and the only thing on this box that reads the consequences of a
  per-crate change. Do NOT add a workflow — `develop` has no push lane by owner
  call (Actions budget), and adding one by symmetry is the failure mode
  `check_validation_gate` records.

## What this is NOT

Not an argument to relax the macOS refusal — that refusal is correct, and T3
strengthens rather than weakens it. Not an argument that `a11b2dd8` should have
run a different command: a per-crate gate is the right gate for a per-crate
change. The missing thing is a lane that reads the CONSEQUENCES of one, in a
form whose output says what it measured.

## Notes

- Found by running the quoted command by hand during unrelated housekeeping.
  That is the discovery mode this issue exists to replace.
- `scripts/test_gate.sh` stayed **green** through the whole interval — measured
  this session: 203 + 2060 + 249 + 139, every row exactly at its floor. An
  executing gate that passes is the most convincing possible evidence that
  nothing is wrong, and its scope (`-p … --lib`) is orthogonal to both breaks.
- `wasm32_gate` also passed (both simd128 arms), for the same reason: `--lib`
  only, and a different triple.
