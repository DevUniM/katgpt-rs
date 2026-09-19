# Issue 856: `#[cfg(feature)] mod tests { … }` zeroes a target exactly like `#![cfg]` — and the audit built for that class reports a confident `SILENT-NOW 0` over 15 of them

**Status:** OPEN — T1 filed with the measurement; T2–T5 open.
**Found by:** Issue 833 T2's per-target read, 2026-09-19 —
`cargo test --release --test test_122_toast_goat` printed
`running 0 tests … ok. 0 passed; 0 failed; 0 ignored; 0 measured;
0 filtered out`, exit 0, in the middle of a run whose whole subject was
*reading the printed value next to the bar*.
**Instruments:** `scripts/cfg_gated_target_audit.py`,
`scripts/cfg_gated_floor_gate.py` (a docs-gate CHECK).

## The class

AGENTS.md §cfg-gated targets is exactly right and is written about **one
spelling**:

> A test file opening with `#![cfg(feature = "x")]` compiles to an **empty
> binary** when `x` is off; cargo prints `ok. 0 passed` and **exits 0** —
> byte-for-byte a real pass. The `#![cfg]` protects the **count**;
> `required-features` protects the **reader** — both are needed.

⛔ **A file whose entire body is `#[cfg(feature = "x")] mod tests { … }`
produces a byte-identical outcome** — same empty binary, same `ok. 0 passed`,
same exit 0 — and the audit cannot see it. Its predicate is one line:

```python
# scripts/cfg_gated_target_audit.py:82
# A whole-file inner attribute at the top of a file. `#![cfg(...)]` only —
# `#![allow]`, `#![doc]` etc. are not gates.
INNER_CFG = re.compile(r"^\s*#!\s*\[\s*cfg\s*\(", re.MULTILINE)
```

⚑ **Read that comment carefully — it is the finding.** `"#![cfg(...)]` only"
is distinguishing `#![cfg]` from *other inner attributes*. It is **not** a
decision to exclude the outer-attribute-on-a-module form, and nothing in the
file, in AGENTS.md, or in the pin files mentions that form at all. This is an
**unstated blind spot**, not a scoped exclusion — which is the worse of the
two, because a stated exclusion is re-readable and this one is invisible.

## The measurement (katgpt-rs, 2026-09-19)

The audit's own summary line for this repo:

```
repo          targets  #![cfg]  w/ req-f  SILENT-NOW  load-bear  latent  …
katgpt-rs        1007      615       515           0          0      98
```

> `SILENT-NOW 0: a plain cargo test --test <name> compiles the file to
> nothing and prints 0 passed with exit 0.`

**There are 24.** Root-package targets (`tests/`, `benches/`) whose entire body
is a `#[cfg(feature = …)] mod`, carrying **no `required-features` row at all**,
over 417 scanned root-package target files. Severity split — AGENTS.md's own
rule, *read the split, never the pooled total*:

**⛔ OPT-IN — 15. A green zero on EVERY ordinary run.**

| target | gating feature |
|---|---|
| `tests/bench_181_dmoe_vocab_coreset_goat.rs` | `vocab_coreset` |
| `tests/bench_dflare_modelless.rs` | `dflare_fusion` |
| `tests/bench_sdpg_bandit_modelless.rs` | `sdpg_bandit` |
| `tests/go_integration.rs` | `go` |
| `tests/go_komi_test.rs` | `go` |
| `tests/goat_090_tower_search.rs` | `unit_distance` |
| `tests/interval_pruner.rs` | `interval_pruner` |
| `tests/test_121_randopt_goat.rs` | `randopt_weight` |
| `tests/test_122_toast_goat.rs` | `toast_tokenizer` |
| `tests/test_124_event_log_goat.rs` | `event_log` |
| `tests/test_125_rmsd_goat.rs` | `rmsd_distill` |
| `tests/test_127_convex_tok_goat.rs` | `convex_tok` |
| `tests/test_129_opus_boltzmann_goat.rs` | `opus_selection` |
| `tests/test_freeze_thaw.rs` | `bomber` |
| `tests/test_pgd_analytics.rs` | `go` |

**· DEFAULT-ON — 9.** `bench_181_dmoe_bandit_top_p_goat`,
`bench_250_breakeven_goat`, `bench_252_cubical_topology_goat`,
`bench_manifold_residual`, `critical_interval_integration`,
`rv_gated_routing`, `test_128_proof_sketch_goat`, `test_130_epiplexity_goat`,
`test_130_epiplexity_integration`. These RUN under plain `cargo test` and
zero only under `--no-default-features` — the audit's own `latent` class,
same standing, and they are listed so the next reader does not re-derive
the split.

**3 more** use the `#[cfg] mod` spelling and DO carry a row, so the reader is
protected and only the audit's bookkeeping is wrong for them
(`bench_008_gpart_pruning_goat` is one).

## Why this matters more than 15 rows

⛔ **`test_122_toast_goat` is a GOAT proof**, and a GOAT gate is the thing this
repo promotes features on. Nine of the fifteen are named `*_goat` or
`test_1NN_*_goat`. Invoking one by name and reading `ok. 0` is
indistinguishable, at the terminal, from having proved something — which is
the sentence AGENTS.md already writes about the other spelling.

⛔ **And a gate that cannot see a class reports it as ZERO, not as unknown.**
`SILENT-NOW 0` is the most reassuring cell in that table. This repo's own rule
for the shape is one section down: *a ceiling is green over whatever the
instrument can SEE, so the finding count needs the population that produced
it* — here the population itself was wrong, and the blindness floors
(`min_*`) cannot detect it because the walk is complete; it is the
**classifier** that is narrow.

## Cross-repo population (MEASURED, not assumed)

Over the 17 contract repos on this box, target files (`tests/`, `benches/`,
every package) whose entire body is a feature-gated `#[cfg] mod`:

```
katgpt-rs 26 · riir-ai 5 · mmorpg-editor 1 · mmorpg-remake 1 ·
riir-chain 1 · riir-train 1                     TOTAL 35 of 2485 target files
(1793 of which carry the whole-file `#![cfg]` the audit does see)
```

So the class **does** generalise — 9 targets across 5 siblings — and is
concentrated here (26 of 35, 74%). ⚠ Whether each of the sibling 9 carries a
`required-features` row is **UNMEASURED**: resolving that needs per-package
manifest lookup across workspaces, which this count did not do. Do not read
9 as 9 defects.

## Tasks

- [x] **T1 — file the measurement**, with the severity split and the
      cross-repo population. Done above.
- [ ] **T2 — widen the CLASSIFIER, not the pin files.** `cfg_body()` should
      return the gate for a file whose entire body is a single feature-gated
      `#[cfg] mod`, so both spellings land in the same buckets and every
      existing consumer (`cfg_gated_floor_gate`, the drift sweep, the
      severity split, the PROFILE dimension) inherits it for free. ⛔ The
      predicate must be **"the mod is the whole body"**, never "a `#[cfg] mod`
      exists" — a file with live `#[test]` fns outside a gated helper module
      is not zeroed and flagging it is the cries-wolf outcome. The arms must
      pin that negative.
- [ ] **T3 — expect the floors to MOVE, and do not re-pin them quietly.**
      AGENTS.md: *arming a target can RED a binary-counting floor — an empty
      gated binary prints `test result: ok. 0 passed` and COUNTS as one.* T2
      moves 24 katgpt-rs rows from invisible into SILENT-NOW, so
      `scripts/cfg_gated_floors.txt` and the drift floors will red. Repair
      with a **passed-test floor**, not a re-pin, per the rule already
      written there.
- [ ] **T4 — add the 15 `required-features` rows.** One per opt-in target;
      the row is what protects the READER, and `required_features_static_gate`
      + `cfg_row_implication_gate` already assert a row is not merely present
      but correct. ⚠ Land T2 first: adding rows before the classifier can see
      them makes the repair unobservable, which is how the same work gets
      done twice.
- [ ] **T5 — the sibling 9 need their rows checked, and that is a per-repo
      read.** Do NOT ratchet a cross-repo ceiling here: the count is 9 over 5
      repos this session does not own, and a ceiling over an unread bucket is
      a backlog wearing a pin (Issue 785). A cross-repo repair is not landed
      until it is COMMITTED in the sibling with a cited SHA (Issue 798).

## Records

- Found during the Issue 833 T2 screening run: `/f/ab_slack/*.log`.
- The sibling class found in the same read — a latency ceiling satisfied by a
  deleted loop — is katgpt-rs Issue 855, deliberately kept separate: that one
  is a live assertion satisfied by absent work, this one is an assertion that
  never runs at all. Both print a plausible green.
- ⚠ `riir-ai .issues/855` is a DIFFERENT document (cited in
  `cfg_gated_target_audit.py`'s own PROFILE note); this repo's 855 is the
  latency-ceiling one.
