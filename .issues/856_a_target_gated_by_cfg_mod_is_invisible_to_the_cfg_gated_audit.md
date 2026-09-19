# Issue 856: `#[cfg(feature)] mod tests { … }` zeroes a target exactly like `#![cfg]` — and the audit built for that class reports a confident `SILENT-NOW 0` over 15 of them

**Status:** OPEN — T1/T2/T3/T4 CLOSED 2026-09-19, T5 CLOSED for the two
repos that BREACHED (repaired + committed in the siblings, SHAs below) and
NAMED-not-ratcheted for the rest. The measurement below is T1's and stands
except for one row: **`test_freeze_thaw` is a TRUE NEGATIVE** — see T2.
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
- [x] **T2 — widen the CLASSIFIER, not the pin files.** DONE 2026-09-19.
      `cfg_gated_target_audit.cfg_body` falls through to a new
      `whole_body_cfg_mod()` when a file carries **no** `#![cfg]` at all, so
      both spellings land in the same buckets and every consumer
      (`cfg_gated_floor_gate`, the drift sweep, the severity split, the
      PROFILE dimension, `--json`) inherited it without changing. The masker
      is **imported** from `platform_dead_code_audit`, never re-written — a
      deferred import, because that module imports `derive_repos` from this
      one and the cycle is real rather than an artifact.

  **Measured, katgpt-rs (before → after):**

  | column | before | after |
  |---|---|---|
  | `#![cfg]`-gated | 615 | **641** (+26) |
  | SILENT-NOW | **0** | **12** (7 load-bearing) |
  | latent (default-on) | 98 | 105 (+7) |
  | `any()` | 1 | 5 (+4) |
  | w/ req-f | 515 | 518 (+3) |

  ⛔ **T1's count of 24-without-a-row was over by one, and the classifier is
  the thing that is right.** `tests/test_freeze_thaw.rs` carries four gated
  modules **and an ungated `#[test] fn frozen_struct_sizes_reasonable` at
  line 302**, so a plain `cargo test --test test_freeze_thaw` runs ONE test,
  not zero. It is the exact cries-wolf shape T1 told this task to pin, and it
  was sitting inside T1's own list. The OPT-IN 15 is **14**; the population
  is **23 without a row + 3 with one = 26**. Pinned as an arm.

  ⚑ **Two extensions past "one mod", both MEASURED rather than reasoned
  toward — 6 of the 27 candidates needed them:**
  - A **RUN** of gated modules is gated by **`any(...)`, never `all(...)`**:
    the binary empties only when EVERY module is gated out. `all()` there
    would have handed T4 a wrong `required-features` row, which is the
    "row exists and is wrong" class this repo calls strictly worse than a
    missing one. Four such targets land in `any_of` — the class cargo's
    AND-only `required-features` genuinely cannot express — and NOT in the
    fixable list: `bench_dflare_modelless`, `test_125_rmsd_goat` (both
    opt-in), `rv_gated_routing`, `test_130_epiplexity_goat` (both
    default-on).
  - A top-level **`use`** cannot carry a `#[test]`, so it never makes a
    target non-empty. `bench_dflare_modelless` — one of T1's 15 — opens with
    nine individually-gated `use` lines, and a mod-only predicate rejects it
    for an item that can never be the reason a binary has tests.
    ⚠ STATED cost, pinned as an arm: an ungated non-`use`, non-test item (a
    helper `fn`, a `const`) still makes the file read NOT-zeroed. That
    UNDER-reports and never cries wolf, which is the direction this report
    chooses everywhere.

  ⛔ **The first cut returned `None` for EVERY file and looked exactly like
  the defect it was repairing.** `_MOD_OPEN` was anchored `\A` and handed a
  non-zero `pos`; `pattern.match(s, pos)` anchors at `pos` already, and a
  `\A` in the pattern still means the start of the STRING. Caught because
  the summary line did not move — `#![cfg] 615` unchanged — not because
  anything failed. The arm that pins it carries a `//!` preamble, since every
  real specimen opens with one and the zero-offset form matched fine.

  **Every new rule is a CANARY, verified by perturbation, not asserted:**
  `any(`→`all(` reds the run arm; accepting a sibling item reds the
  ungated-`#[test]` negative; dropping the `use` skip reds the use-preamble
  arm; removing the fall-through reds the headline arm. Four perturbations,
  four reds.

  ⚑ **And the same predicate was owed to a SECOND instrument**, or the repair
  would have reproduced 856 one gate over: `cfg_row_implication_audit`
  (the check for a row that EXISTS and is WRONG) had its own private
  `#![cfg]` reader and would have checked none of T4's twelve rows. It now
  **shares** `whole_body_cfg_mod`, with `any(...)` deliberately excluded —
  no single feature is REQUIRED by a disjunction, so reading one there would
  invent a finding demanding features the row must not name. 515 → 529 rows
  with a readable leading cfg.

- [x] **T3 — expect the floors to MOVE, and do not re-pin them quietly.**
      DONE. `cfg_gated_floor_gate` went red on exactly the two pins T3
      predicted — `✗ load-bearing SILENT-NOW 7 > pinned 0` and
      `✗ SILENT-NOW 12 > pinned 0`. **Neither was re-pinned**: T4's rows took
      both back to 0 and the gate passes on its original pins (8 held).
      `scripts/cfg_gated_floors.txt` is UNCHANGED, which is the outcome the
      rule asks for.
      ⚠ The binary-COUNTING floor T3 warns about is a real consequence and it
      lands one instrument over, on a box this one is not:
      `scripts/x86_64_execution_matrix.sh`'s integration cell counts TARGETS,
      and arming 12 auto-discovered targets removes 12 `ok. 0 passed` lines
      from a root `cargo test --release`. Its ASSERTION floor is unaffected —
      those binaries assert nothing, which is the whole point. **Not re-pinned
      here**, because that gate REFUSES off x86_64 and a floor edited from a
      box that cannot run it is a floor nobody measured; the next matrix run
      on the 4090 owes `min_targets` a −12, with this issue as the reason.
      `test_gate.sh` is unaffected (it is `--lib`-scoped).

- [x] **T4 — add the 15 `required-features` rows.** DONE, and the number is
      **12**, for two reasons T4 could not have known: `test_freeze_thaw` is
      not in the class at all (T2), and two of the opt-in targets
      (`bench_dflare_modelless`, `test_125_rmsd_goat`) are `any(...)`-gated,
      which cargo's AND-only `required-features` cannot express — a row there
      would be the wrong-row class. The twelve, each landed in the root
      `Cargo.toml` under one comment block:
      `bench_181_dmoe_vocab_coreset_goat` · `bench_sdpg_bandit_modelless` ·
      `go_integration` · `go_komi_test` · `goat_090_tower_search` ·
      `interval_pruner` · `test_121_randopt_goat` · `test_122_toast_goat` ·
      `test_124_event_log_goat` · `test_127_convex_tok_goat` ·
      `test_129_opus_boltzmann_goat` · `test_pgd_analytics`.
      `required_features_static_gate` (766 rows, 0 naming an unenableable
      feature) and `cfg_row_implication_gate` (0 empty-at-row) both pass.

  **Each row is verified BY THE COMPILER, in BOTH directions** — a row that
  exists and is wrong is the class this repo calls strictly worse than a
  missing one, and neither static gate can tell "names a feature that exists"
  from "names the feature that gates the module":

  - WITH its feature, every one of the twelve BUILDS and lists a non-zero
    test count: **11 · 6 · 13 · 6 · 10 · 9 · 21 · 19 · 22 · 12 · 20 · 26 =
    175 assertions** that had been reporting `ok. 0 passed`, exit 0, to
    anyone who invoked the target by name. Seven of the twelve are
    `*_goat`/`goat_*`.
  - WITHOUT it, cargo **REFUSES by name** — `error: target … requires the
    features` — for all twelve, instead of printing the green zero. That is
    the whole point of the row and it is the half a static gate cannot see.

  (`cargo test --release --test <name> [--features <f>] --no-run` /
  `-- --list`, `CARGO_TARGET_DIR=/tmp/i856`, never `--all-features`.)

- [x] **T5 — the sibling 9 need their rows checked, and that is a per-repo
      read.** DONE as a read, not as a ratchet. The widened classifier was run
      against every contract repo and the delta taken per repo:

      | repo | gated | SILENT-NOW | standing |
      |---|---|---|---|
      | mmorpg-editor (`seal-game-editor`) | 0 → 1 | 0 → **1** | BREACHED its pin — repaired |
      | mmorpg-remake (`seal-remake`) | 12 → 13 | 2 → **3** | BREACHED its pin — repaired |
      | riir-ai | 619 → 624 | 1 → **4** | within its own ratchet (76); NAMED below |
      | riir-train | 316 → 318 | 1 → 1 | no new finding |
      | riir-clippy, riir-game-sdk, riir-neuron-db, all others | unchanged | unchanged | — |

      **Repaired and COMMITTED in the sibling, with the SHA** (Issue 798 —
      a cross-repo repair is not landed until it is committed there):
      - `seal-remake` **`964e780`** (branch `develop`) —
        `tests/scenario_doc_front.rs`, feature `scenario_doc`.
      - `seal-game-editor` **`fbb5a931`** —
        `crates/editor-data/tests/smoke_test.rs`, feature
        `real-data-validation`. ⚠ Landed on **`feature/assigned-shader-preview`**,
        the branch that repo was checked out on while two sibling sessions
        worked in it; switching branches under them would have been the worse
        disruption. It merges with their work or it does not — recorded here
        so it is followable either way.
      - Both sweeps are green again on their EXISTING pins. No ceiling was
        raised anywhere.

      ⚠ **riir-ai's three new rows are NAMED, not repaired and not
      re-pinned** — they were absorbed by a pre-existing ratchet of 76, which
      is the "backlog wearing a pin" shape, so leaving them unnamed would be
      the silent direction:
      `crates/riir-engine/tests/cgsp_rewind_recovery_poc.rs`
      (`cgsp_rewind_recovery`), `crates/riir-games/tests/bench_cold_tier.rs`
      (`turso_cold`), and `crates/riir-gpu/tests/bench_171_t27_profiling.rs`
      + `bench_171_t34_speculative.rs` (both
      `cubecl_runtime, gpu_decode_fusion` — `any_of`-shaped is worth checking
      before a row is written). Owner call in that repo.

      ⛔ T1's cross-repo figure — "35 target files, 9 across 5 siblings" — was
      a **text census**; the classifier's answer over the same population is
      **8 newly-gated targets in 4 siblings, 5 of them SILENT-NOW**. Read
      T1's 9 as the magnitude it was, never as a defect count: that is the
      distinction T1 itself asked for (*"do not read 9 as 9 defects"*), and
      the measurement confirms it.

## Records

- Found during the Issue 833 T2 screening run: `/f/ab_slack/*.log`.
- The sibling class found in the same read — a latency ceiling satisfied by a
  deleted loop — is katgpt-rs Issue 855, deliberately kept separate: that one
  is a live assertion satisfied by absent work, this one is an assertion that
  never runs at all. Both print a plausible green.
- ⚠ `riir-ai .issues/855` is a DIFFERENT document (cited in
  `cfg_gated_target_audit.py`'s own PROFILE note); this repo's 855 is the
  latency-ceiling one.
