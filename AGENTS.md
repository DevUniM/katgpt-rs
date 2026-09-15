# AGENTS.md — katgpt-rs

The global `~/.agents/` rules apply; this file documents repo-local context
that supplements them.

History, resolved-issue records, gate narratives, collision precedents:
`HISTORY.md`. Removed issue files: git history.

## Boundary contract — read `BOUNDARY.md` first

[`BOUNDARY.md`](BOUNDARY.md) is the authoritative contract: what this repo
**owns**, what it **does not own** (with the correct home for each), the
crate-granular **allowlist**, and the **drift ledger**. On any conflict with
prose in this file, BOUNDARY.md wins.
- **Domain test:** is this a **modelless inference primitive** with no riir dep (this repo is upstream of everything)? NO → it belongs in another repo; file there.
- Read it before adding any dep, crate, module, System impl, or vocabulary type.
- Enforcement: `../riir-ai/scripts/ci_boundary_contract.sh` — undeclared cross-repo dep, drift row without its open issue, contract-vs-measured-graph drift. Run boundary checks VIA the `boundary-guard` skill, not ad-hoc greps.
- Found a violation? File the issue FIRST (`.issues/NNN_boundary_*.md`), add the drift row, then fix. Closing the issue removes the row in the same commit.

## Modelless-first mandate (the core principle)

**This repo ships modelless inference primitives.** No training, no backprop,
no gradient descent. The only weight mutations allowed at runtime are:

1. **Freeze/thaw** — swapping a frozen snapshot (atomic, versioned, BLAKE3-checked).
2. **Raw/lora hot-swap** — a **deterministically constructed** (not trained)
   LoRA overlay via `LoraPair { reader, writer }` (Plan 025).
3. **Latent-space updates** — direction-vector projections, sigmoid gates,
   routing tables; latent state, NOT base weights.

**MANDATORY: exhaust modelless paths before deferring to riir-train.** Before
deferring ANY gate, mechanism, or plan task ("this needs training"), check the
three paths above first (research skill §3.5,
`.agents/skills/research/SKILL.md`). Systematic, characterizable biases are
modelless-correctable candidates, NOT automatic riir-train dependencies — for
a known, named bias ("signal doubled", "position offset", "attention
asymmetry"), try a deterministic reader-LoRA or freeze-state correction before
concluding "needs gradient descent." Canonical-failure story: HISTORY.md.

## Build Commands

```bash
# Toolchain: pinned by rust-toolchain.toml (1.98.1, issue 739) — cargo resolves
# it automatically; full_gate.yml is the deliberate RUSTUP_TOOLCHAIN=stable
# rot-gate exception.

# Default features (the GOAT-validated, promoted primitives)
cargo check
cargo test -p katgpt-core --lib

# Single feature
cargo check --features <feature_name>

# All features
cargo check --all-features

# Specific feature's tests
cargo test -p katgpt-core --features <feature_name> --lib
```

### The full gate — none of the above is a whole-repo claim

Every command listed above is narrow in at least one **independent** axis, and
a green result says nothing about what it compiled to nothing:

| Axis | Blind spot |
|---|---|
| `check` vs `clippy` | two `cargo heal` escape classes are rejected by clippy's typeck and accepted by `check` (E0689 ambiguous-integer, E0631 deref-coercion in `redundant_closure`) |
| default vs `--all-features` | non-default gated code compiles to **nothing** |
| `-p <crate>` vs `--workspace` | a crate's own non-default feature can be switched on by the ROOT crate's defaults once the root is in the selected set — and per-crate runs silently *shrink* coverage |
| no `--all-targets` | skips every test / bench / example — which is where gated code lives |
| dev vs `--release` | `debug_assertions` is always **ON** in dev, so every item behind `#[cfg(debug_assertions)]` — and everything that depends on one — only ever compiles in the configuration where it works. **Neither profile is the safe default — the profile is part of the claim.** |
| `--all-targets` vs **doc-tests** | `--all-targets` does **not** include doc-tests — only `cargo test --doc` reaches them (`.issues/723` Class F) |
| host triple vs **`wasm32`** | a `--target` you never pass is a platform you never compile. Worse than the macOS axis because it is gated **twice**: the hot kernels are `all(target_arch = "wasm32", target_feature = "simd128")` and the triple defaults to simd128 **OFF**, so even a wasm32 lane without `RUSTFLAGS='-C target-feature=+simd128'` compiles the SIMD half to nothing. Measured (Issue 737): the simd128-**off** arm was clean and the **on** arm had 14 findings, 11 of them `unsafe_op_in_unsafe_fn` on edition 2024. `full_gate.sh` layer 2b runs both arms |
| **compile vs EXECUTE** | every axis above is about *compilation*. The scoped core (katgpt-rs + katgpt-core `--lib` at default features, count floors) was EXECUTED weekly (`test.yml` + `scripts/test_gate.sh` — SCHEDULE SUSPENDED 2026-09-09, Actions spending limit; run `scripts/test_gate.sh` locally). ⛔ **katgpt-types joined that population on 2026-09-15 and the reason is this axis one PLATFORM over** (riir-train Issue 549): the `avx2_exp_sum_inplace` n-clamp regression test landed and was executed by NOTHING — full_gate is macOS/aarch64, where the NEON sibling always clamped and the class is invisible, and is compile+lint rather than execute; wasm32_gate builds a different kernel; and this lane, the only executing one and the only x86_64 one, did not select the crate; the other 477 integration-test and 176 bench targets are executed by nothing automatic, and `--all-features` is not a supported TEST configuration (fixture RNG streams and GOAT calibrations are per-feature). An uninvoked assertion is *unknown*, not passing |

So before claiming a repo-wide green, run:

```bash
cargo clippy --workspace --all-targets --all-features --keep-going -- -D clippy::needless_range_loop -D clippy::map_clone -D clippy::iter_cloned_collect -D clippy::identity_op -D clippy::bool_comparison -D clippy::manual_is_multiple_of -D clippy::collapsible_if -D clippy::map_all_any_identity -D clippy::unnecessary_cast -D clippy::manual_repeat_n -D clippy::question_mark -D clippy::empty_line_after_outer_attr -D clippy::unusual_byte_groupings -D unused_mut -D unused_parens
```

The `-D` list (Issue 701 R3b, 2026-09-03) is the mechanical lints whose
all-features warning surface was healed to ZERO residual — a lint with
residual > 0 must NOT be added to it. `--keep-going` is not optional: without
it the run stops at the first failing target and under-reports. Don't run it
by hand — `scripts/full_gate.sh` is the assertion (it refuses to report a pass
off macOS, where the `target_os = "macos"` device backends compile to nothing
even with `--all-features`, and checks that this document still quotes the
command it runs).

**And `wasm32` is a second platform axis, not a variation on the first.**
Nothing in this repo compiled it until 2026-09-07 — the only script naming the
triple was `scripts/build-moka-wasm.sh`, which is a deploy build a human runs,
not a gate. `full_gate.sh` layer 2b closes it: derived `-p` list (a new
wasm32-bearing crate joins by existing) **including the root package**, both
simd128 arms, the two wasm32 GOAT targets by name, and the residue pinned by
**membership** so the gate reds when that set changes rather than silently
shrinking. A missing `wasm32-unknown-unknown` target is a PARTIAL gate that
refuses, exactly as an off-macOS run is.

Selecting the **root package** is what makes that lane wide, and it was not
why it was added: clippy lints every **workspace path dependency** it pulls
in (registry crates are `--cap-lints`'d, workspace ones are not), so
`-p katgpt-rs --lib` puts the whole internal graph under `-D warnings` on
wasm32. That is how an orphaned doc block on
`katgpt-attn-match::select_highest_attn_keys` — a crate with no wasm32 code
of its own — surfaced. `--all-targets` is NOT the way to widen further: it
dies on dev-deps (`statrs`, `proptest`) that do not resolve for wasm32, so
extra coverage goes in as **named targets**.

**The inverse holds too:** running **on** macOS silently drops every
`not(target_os = "macos")` backend, `--all-features` included — **a platform
is part of the claim, exactly as the profile is.** Typecheck that half from
the M3 (`cargo check` never links; `--canary` is not optional — it requires
`E0425` from a planted undefined call, because otherwise "Finished" is
indistinguishable from the modules compiling to nothing):

```bash
scripts/check_platform_gated_modules.sh ../riir-train riir-train-gpu numeric_drift_cuda
scripts/check_platform_gated_modules.sh --canary ../riir-train riir-train-gpu \
    crates/riir-train-gpu/src/numeric_drift_tap.rs numeric_drift_cuda
```

**The profile axis is feature-shaped too (Layer 6b, Issue 758).** Layer 6
runs `--all-features` — which SUPPLIES `alloc_tracking` — so the (release ×
default-features) cell was asserted by nothing until slice_tca's module-level
`use crate::alloc` fell through it (E0432 under `cargo test --release -p
katgpt-core --lib`, Layer 6 green the whole time). `full_gate.sh` Layer 6b
closes it: the test_gate population (katgpt-rs, katgpt-core, katgpt-dec at
its pca_global row) at `cargo check --tests --release`, deliberately not
`--workspace` (that inherits the platform axis Layer 2 refuses on — the metal
examples). The matrix: (dev, default) test_gate · (dev, all) Layer 3 ·
(release, all) Layer 6 · (release, default) Layer 6b. Alloc-gated tests carry
`#[cfg(any(debug_assertions, feature = "alloc_tracking"))]` — the full
Issue-741 predicate, so they RUN under `--release --features alloc_tracking`
(the configuration alloc gates are meant to be read in) and compile away at
release-default instead of breaking the harness.

Trigger health: CI is MAIN-ONLY + dispatch-only since 2026-09-09 (owner call:
Actions spending limit + no CI on `develop` pushes) — every `push` trigger is
`branches: [main]` and every `schedule:` block is suspended in-file (commented,
riir-train 507 precedent). `scripts/ci_gate_coverage.py` reports which declared
triggers can actually fire, per workflow, per repo. Layer 2b also has its own
push lane: `.github/workflows/wasm32_gate.yml` runs `full_gate.sh
--wasm32-only` on ubuntu-latest (Issue 737 T4), now MAIN-ONLY too — the lane is
host-independent and `--lib`-only; dispatch it manually after a run of develop
work, since no automatic lane covers develop pushes anymore.

## Docs gate + drift sweeps

`scripts/docs_gate.sh` runs the manifest/doc/skill drift assertions and
**prints its own timing** — a hand-typed duration drifts exactly like a
hand-typed count, and it was also the wrong quantity. Measured three times:
**12.65s · 12.52s · 12.69s CPU** on runs whose WALL clocks were **128.3s ·
299.1s · 15.0s** — a **20x** wall spread against **1.4%** of CPU spread. That
is the whole argument for the quantity: **cite CPU, read wall as a range.**
⚠ Those three are a **14-check** measurement, and the CHECKS set is part of
the claim exactly as the profile is. Two checks later: **14.42s** CPU at 15
checks, **13.96s** at 16, and **13.37s** at 17 (Issue 756's
`markdown_fence_gate.py`, a 1517-file walk). Read that honestly — the added
checks did NOT show up as a clean increase; those three RUN DOWNWARD as the
CHECKS set grows, which is the opposite of what any per-check cost model
predicts, and the 3.3% spread across the first two is **wider than the
1.4%** the three 14-check runs suggested. So CPU is the load-invariant figure
and still the right one to cite, but it is tight-ish, not exact, and a
difference this size is not evidence a check got slower. Only compare CPU
within a fixed CHECKS set, and only as a range.
⚠ The set moved to **18** on 2026-09-14 (Issue 775's
`platform_dead_code_floor_gate.py`, a 2415-file Rust-source walk measured at
**~6.2s wall** standalone), and the CPU figure at 18 checks is **UNMEASURED,
not unchanged**: the landing run was on the Windows workstation, where `times`
does not account for native children at all (Issue 792, measured below) and
the gate now prints `CPU SUPPRESSED` rather than the 1.26s it used to. Take
the 18-check CPU figure from the next M3 run; do NOT read 13.37s forward
across a CHECKS change, and do not read a Windows run's number — there is
none — as a speedup. The set moved again the SAME DAY, to **19** (Issue 778's
`subprocess_encoding_gate.py`, a 60-file tracked-`*.py` walk over 44
`subprocess` call sites, measured **~0.6s wall**), so the M3 run owes a 19-check
figure and the 18-check cell will never be measured at all — which is the
point of writing the CHECKS count next to the number instead of the number
alone. It moved to **20** on 2026-09-14 (Issue 787's
`instrument_reachability_gate.py`, a 63-script transitive closure over 13
roots, measured **~0.24s wall** standalone — the cheapest check in the set,
because the closure re-reads only files a root or a script actually names),
so the 19-check cell joins 18 in
never having a POSIX figure — this box has printed `CPU SUPPRESSED` for every
run since the set left 17. It moved to **21** the same day (Issue 789's
`check_validation_gate.py`, an AST pass over the CHECKS array's own 21 scripts,
measured **~0.11s wall** standalone — cheaper still than 787's, because it
parses each check once and reads no tree at all), so 18, 19 **and** 20 are now
cells no POSIX run will ever measure. Four consecutive same-day CHECKS moves is
the argument for the convention, not an embarrassment to it: a bare number in
this paragraph would have been wrong four times in one day. It moved to
**22** on 2026-09-15 (Issue 796's `dual_allocation_gate.py`, a handful of
git-plumbing calls over this checkout and its upstream, measured **~0.10s
wall** standalone). The 21-check cell did get one POSIX figure — **22.75s
CPU** (2026-09-15, loaded M3, sibling agents active; quiet-box class unknown,
so the loaded-box scope the paragraph below demands applies). In CI the new
check green-exits by construction — a main-push checkout has HEAD ==
origin/main, merge base == HEAD — so its live reach is the workstation dev
loop, where the divergence actually exists at run time.
⛔ And "load-invariant" has a measured LIMIT (2026-09-14): two runs at the
same 17 checks / 1517-file fence floor, on a box carrying the g50 training
precompute plus ≥3 concurrent agent sessions, measured **44.97s · 36.28s
CPU** — 2.7–3.4× the 13.37s figure, with a **20%** run-to-run spread where
the quiet-box spread was 1.4%. The verdicts were unaffected (17/17 both
runs); only the timing figure moved. So the invariance claim is
**quiet-box-scoped**: under sustained multi-tenant load even CPU-seconds
inflate and destabilize (mechanism unmeasured — E-core placement is the
suspect, not the finding). Cite CPU *with the load class it was measured
under*, or the number carries a quiet-box premise onto a busy box.
⛔ A discredited fourth figure is why this paragraph is worded so insistently:
an earlier version called 11.7s wall a *quiet-box baseline*, and it was taken
at load 5-7 — the 15.0s run (2026-09-11) is the first one actually measured on
a quiet box, and it is SLOWER than the number that was being quoted as the
floor.

The wall inflation lands on the checks that walk the tree —
`cargo_comment_audit` 54.7s, `bench_doc_audit` 50.4s, `cfg_gated_floor_gate`
31.2s in the 128.3s run, everything else under 4s — and **none of those
invokes cargo**, so it is not the cargo build lock (the first version of this
paragraph said it was, on no evidence; the per-check line refuted it). Which
check dominates is not stable either: the 299.1s run put
`percentile_floor_gate` at 61.3s and `bench_doc_audit` at 73.1s, and on the
quiet 15.0s run no check crossed 4s at all. Beyond "a
busy box starves the tree walks" the mechanism is **unmeasured**. Read the
per-check `⏱` line to see which check is BLOCKING, never to conclude a check
got slower.

The CPU figure **asserts itself non-inert**, because its failure mode is a
well-formed number rather than an error: `times` reports `0m0.000s` children
CPU from any forked context — a pipeline and a command substitution both fork,
and the fork has no children of its own, so even `times | sed` purely to
indent destroys it (the first two versions printed a confident zero next to a
308s run). It is REDIRECTED to a file, never captured, and the gate prints
`⛔ … NOT a measurement` instead of the number if the total reads ~0 over a
multi-second run. Both arms verified against the block extracted from the
tracked file: redirect → 0.45s from a child that burned 0.43s; pipe → 0.00s
and the ⛔ fires.
⛔ **And the ~0 guard is not the whole hazard — the figure has a PLATFORM
premise (Issue 792, 2026-09-14).** On Windows/MSYS, `times` accounts for MSYS
children and reports essentially nothing for NATIVE ones, so a run whose work
is all Python prints a well-formed, plausible number built from `sed`/`tail`
overhead alone: **1.26s CPU against a 19.7s wall**, with the ~0 guard quiet.
Measured one child at a time, each burning ~2s CPU: an MSYS `bash -c` loop →
**1.796s user + 0.468s sys**, `py -c` → **0.000s + 0.015s**, python.exe by
absolute path → **0.000s + 0.045s**. So it is the MSYS/native boundary, **not**
the `py` launcher shim — resolving a real executable recovers nothing. A
wall-ratio test cannot separate that from a busy box (this gate's own 12.65s
CPU on a 299.1s wall is 4%), so the gate CALIBRATES instead: it burns a known
0.25s of CPU in a child of the resolved interpreter and requires `times` to
have seen at least half of it, printing `CPU SUPPRESSED` and wall-only when it
did not. Both arms measured on the same box: native child → 0.000s seen,
suppressed; MSYS child → 0.358s seen, figure printed. **Cite the CPU figure
from a POSIX workstation; a Windows run has no CPU number to compare.**

`.github/workflows/docs_gate.yml` runs it per-push on **`main` only** —
develop pushes do not fire it, so run `./scripts/docs_gate.sh` locally for
develop work. One line per check:

| check | asserts |
|---|---|
| `count_features.py` | flag counts in README + examples/README vs every manifest |
| `bench_doc_audit.py` | default-on / opt-in labels in .benchmarks + .docs vs Cargo defaults — plus two blindness floors and `BlindRead`, exit **2**: an `OSError` on a file the walk just listed means the tree is unreadable, and a PARTIAL manifest read fabricates mismatches ABOVE any floor (Issue 790 F9) |
| `cargo_comment_audit.py` | inline Cargo.toml comments vs the default closure |
| `skill_repo_set_gate.py` | hand-typed repo sets in SKILL.md command blocks (Issue 703) |
| `agents_repo_set_gate.py` | AGENTS.md §Repo count membership vs `scripts/repo_set.txt` — pins the paragraph below |
| `cfg_gated_floor_gate.py` | `#![cfg]`-gated targets that report a green 0-pass (Issue 713) |
| `orphaned_attr_gate.py` | a `#[cfg]` separated from its item by a blank line |
| `percentile_floor_gate.py` | a percentile index that lands on n-1 and so reports the MAX |
| `numbering_gate.py` | a number allocated twice, or a stale/malformed `.highwater` (Issues 724, 725) — including the majority case where BOTH holders have CLOSED and been removed, so nothing is on disk and the tracked check reads clean: walled by membership above the era boundary, ratcheted below it (Issue 795) |
| `dual_allocation_gate.py` | this checkout and its upstream both allocated a numbered document since their merge base — TWIN (same stem, the rebased own line) annotates exit-neutral, INDEPENDENT (two documents claiming one number) exits 1 naming both sides' adding commits (Issue 796) |
| `docs_gate_paths_sync.py` | docs_gate.yml's two hand-duplicated trigger `paths:` lists stay identical |
| `required_features_static_gate.py` | a required-features row naming a feature its package cannot enable (riir-train Issue 513) |
| `cfg_row_implication_gate.py` | a required-features row that BUILDS and compiles its target to NOTHING (riir-train Issue 513) |
| `population_sync_gate.py` | the ten independent contract-repo predicates must agree, and the registry that lists them must be COMPLETE (Issue 788) |
| `trap_sentinel_gate.py` | a shell gate whose abort would report exit 0 — this repo's own two, by MEMBERSHIP (Issue 734) |
| `issue_citation_gate.py` | a cross-repo `Issue N` citation naming no repo — it rebinds to the WRONG document once that number is allocated locally (Issue 749). In CI the cross-repo axis is DEFERRED to the workstation run — the `DOCS_GATE_CI` marker's instrument-alive verdict, because the sibling workspace is absent in a single checkout |
| `markdown_fence_gate.py` | a fenced code block never closed — everything after it renders as code, and a fence scanner mis-phases on it (Issue 756) |
| `platform_dead_code_floor_gate.py` | an item declared ungated whose every use sits behind a platform cfg — dead code on a platform no automatic lane compiles (Issue 775) |
| `subprocess_encoding_gate.py` | a `subprocess` call that decodes with the SYSTEM locale — silent mojibake, or `stdout = None` with the returncode intact (Issue 778) |
| `instrument_reachability_gate.py` | a tracked `scripts/*.py` no root and no documented instrument names — invisible to the census that would find it (Issue 787) |
| `sweep_advisory_membership_gate.py` | a `*_drift_sweep.py` that does not call the Issue-797 worktree advisory — its findings and floors then describe whatever the working tree happened to say; gated by MEMBERSHIP, because a count is green on a swap and went stale two hours after it was typed (Issue 797 T5) |
| `check_validation_gate.py` | a CHECK in this array whose own arithmetic no arm asserts — including one whose arm is flag-gated and so never runs (Issue 789) |
| `docs_gate_checks_sync.py` | this CHECKS array vs the AGENTS.md table documenting it — membership both ways + quantity words (Issue 750) |

The `CHECKS` count is deliberately not written here — it drifted once, which
is exactly the drift this gate exists to catch.

**Partial-clone boxes (Issue 765):** the three population checks
(`skill_repo_set_gate`, `population_sync_gate`, `issue_citation_gate`)
hard-red on a box carrying a subset of the workspace — and their raw remedy
used to invite regenerating `repo_set.txt` there, which deletes live repos
from the canonical set. A known-partial box (the 4090: 14 of 20) exports
`DOCS_GATE_PARTIAL_CLONE=1` and gets a loud instrument-alive DEFERRAL on the
population axis instead (predicate agreement + the local axes still run; the
deferral rides each check's final line, the one `docs_gate.sh` forwards). The
marker is an explicit opt-in in the `DOCS_GATE_CI` idiom — **never
auto-detected**, because a genuine removal whose `repo_set.txt` update was
forgotten is set-identical to a partial clone from the walk alone, and an
inferred green would ship the stale file. Gone-only disagreement WITHOUT the
marker reds naming both hypotheses; a repo on disk the file does not know
reds in every posture, marker or not.

**Every sweep below answers the partial-clone question the same way, once
(Issue 793): `scripts/sweep_population.py`.** Seven of them carried a
copy-pasted "pinned but ABSENT from the derived walk" loop and hard-red on a
known 16-of-20 box with `DOCS_GATE_PARTIAL_CLONE=1` already set and every
content assertion green — and a sweep that always reds is a sweep nobody runs.
Measured: the percentile sweep's Issue-777 findings, and four live citation
drift rows, were sitting behind those reds. Three verdicts, never
interchangeable — **UNREGISTERED** (on disk, absent from `repo_set.txt`: a repo
JOINING, reds in every posture), **UNSEEN** (absent, no marker: never a pass),
**DEFERRED** (the same set with the marker, riding the FINAL line in BOTH
directions, because a deferral printed only on failure is one nobody reads on
the run that passes). Never auto-detected: a genuine removal whose row update
was forgotten is set-identical to a partial clone from the walk alone.

⛔ **"Every sweep" was a claim about eight of eleven, and the three left out
were not exempt — they were quieter (Issue 782).** Two of them
(`docs_drift_sweep`, `restatement_drift_sweep`) still carried the copy-pasted
loop and only LOOKED clean because their *pinned subsets* happen to be checked
out on this box; the third, `cfg_row_implication_drift_sweep`, had **no absence
check at all** — it iterates the DERIVED repos, so it caught walk→pins
(UNREGISTERED) and was blind to pins→walk, and printed
`PASSED — every repo within its pins` over **16 of 20** with four pinned rows
evaluated by nothing. **That silent green is the worse direction:** a sweep
that hard-reds is impossible to misread, and this one survived the 779 census
*because* it was quieter, not because it was correct. All eleven share the
verdict now. ⛔ **"Eleven" is that day's measurement, and every count of this
family in prose has gone stale — including one written the same morning.**
Issue 797 wired the worktree advisory into the family and typed **sixteen**
into this document; two hours later a concurrent session landed two more sweeps
and the figure was wrong. The repair is not a fresher number: it is
`sweep_advisory_membership_gate.py`, which reds on a `*_drift_sweep.py` that
does not call the advisory, so the next one cannot land unwired. **Take the
family size from that gate's PASS line, never from a sentence here.** ⚠ A **subset**-population sweep has TWO populations and they are
not interchangeable: hand `population_verdict` the **contract walk**, never the
subset — the restatement sweep, handed its own `.proofs` set, reported **16
phantom absences** and failed. The hole the shared verdict cannot see is
therefore local to each subset sweep and needs its own check: a repo pinned and
checked out that has **dropped out** of the subset (`DROPPED`), whose ceiling
can no longer fail.

Workstation-only cross-repo sweep family — `docs_drift_sweep.py`,
`numbering_drift_sweep.py`, `required_features_drift_sweep.py`,
`percentile_drift_sweep.py`, `cfg_gated_drift_sweep.py`,
`cfg_row_implication_drift_sweep.py`, `trap_sentinel_drift_sweep.py`,
`citation_drift_sweep.py`, `restatement_drift_sweep.py` (every contract repo,
on demand), `markdown_fence_drift_sweep.py` (every contract repo, on demand —
the Issue 756 unterminated-fence verdict workspace-wide, two-axis pins
(`min_md_files` walk floor + `max_unterminated = 0` wall); its FIRST workspace
run caught the then-new `seal-online-remaster`'s `.plans/005:600`, 14 swallowed
lines, repaired there at `99064c5`),
`platform_dead_code_drift_sweep.py` (every contract repo, on demand — the
Issue 775 verdict half of `platform_dead_code_audit.py`, and the one sweep
whose `--prove-fires` runs by DEFAULT: the per-push gate cannot afford the
`git archive` of the known-answer tree, this can),
`subprocess_encoding_drift_sweep.py` (every contract repo, on demand — the
Issue 778 locale-decoding verdict workspace-wide, and the **seventh** time one
of these was pointed anywhere but here and found something: **29 DECODE + 2
CHILD-ENCODER over 5 repos**, all repaired at landing, Issue 783. Its two
floors are not interchangeable and neither is redundant — `min_calls` is **0
in 10 of 16 repos**, because they have `.py` files and no `subprocess` at all,
so in exactly those repos `min_py_files` is the only blindness detector there
is),
`pipefail_discard_audit.py` + `pipefail_discard_drift_sweep.py` (every
contract repo, on demand — the shell class where a `var="$(pipeline)"`
assignment under `set -euo pipefail` is killed by a legitimately-empty grep
(e exit 1 on no-match) AFTER the measured work ran and BEFORE the result was
written — the riir-ai `perf_rematch.sh` incident that lost five benchmark
cells (fix `512b74939`, the sweep's `--prove-fires` known answer; `-S`
cannot locate it — the fix added `|| true` without changing occurrence
counts — so the sweep locates it via `git log -L`). First-run census
(2026-09-15): 194 tracked `.sh` / 1,359 substitution sites / **51 findings,
0 UNPARSED**, every row pinned with a reason in `pipefail_discard_expected.txt`
as an EYES LIST (4 deliberate `grep -c` tripwires in the four `proof_gate.sh`
copies + 47 live kill-shapes awaiting owner triage — the 21-row
`riir-ai/scripts/ci_feature_guard.sh` layer-summary cluster is the
highest-value block: a failing layer's missing `ok` line kills the gate
mid-summary instead of letting the comparison report it). Two bash laws are
MEASURED, not reasoned: `local x="$(fails)"` does not kill (local masks the
status — its own LOCAL-MASKED bucket, listed never gated), and a
`(grep ‖ true) | tail` paren-group is guarded by its interior — which is
what moved 6 dapps `setup.sh` rows to GUARDED),
`toolchain_override_audit.py` + `toolchain_override_drift_sweep.py` (every
contract repo, on demand — the class where a hardcoded `RUSTUP_TOOLCHAIN`
override outlives the workspace pin it contradicts (intake P14 (k): a
`1.95.0` netem-script override survived the 09-04 bump to 1.98.1 and built a
sibling at the box default). Scans tracked `.sh/.yml/.yaml/.toml/.py` +
Dockerfiles comment-aware; verdicts MATCH / DELIBERATE (the in-source
`toolchain-override-deliberate` marker — same line, contiguous comment run
above the line, or above the HEAD of the backslash-continuation command,
because a comment cannot live inside a continuation chain) / DRIFT (walled
at 0) / UNRESOLVED (TOKEN values, counted ceiling) / NO-PIN-OVERRIDE +
repo-level UNPINNED-REPO (both INFO — 13 of 20 repos carry no
`rust-toolchain.toml` against the owner's every-workspace-pins directive;
the real repair is pin files, owner-owned). First green run: 0 DRIFT, 3
DELIBERATE, 1 UNRESOLVED-MARKED, 1 NO-PIN-OVERRIDE),
`orphaned_attr_drift_sweep.py` (every contract repo, on demand — the Issue 784
verdict half of `orphaned_attr_gate.py`, and the **eighth** instance of this
shape. The one that found **no** new offenders, which is the honest outcome to
report: 0 orphaned now holds across three measurements and TWO population
definitions. What it did find is a stale WARRANT — the gate's docstring carried
`11,132 .rs / 49,624 sites` by hand, and Issue 777's tracked walk put the same
16 repos at **8,694 / 26,598**, 22% and **46%** lower, because 23k of those
sites were in trees no repo owns. Both floors bite in all 16 here, unlike 783's
population — a measured difference, not an assumption),
`wasm32_surface_drift_sweep.py` (every contract repo, on demand — the Issue 785
verdict half of `wasm32_surface_audit.py`, which had been a report with no
verdict at all. `max_unresolved = 0` is a WALL (a ratchet on a bucket whose
meaning is *unanswered* is a backlog), UNCOVERED is pinned by **NAME** in
`scripts/wasm32_uncovered_expected.txt` and reds in BOTH directions, and the
walk floor is the ONLY blindness detector here — vacuous in 7 of 16 repos,
which is why a reserved `TOTALS` row floors the population globally),
`len_derived_drift_sweep.py` (every contract repo, on demand — the Issue 786
verdict half of `len_derived_binding_audit.py`, and the **ninth** instance of
this shape. The QUIETEST one: unlike 784 and 785 it had no hand-typed standing
figure to go stale, so there was nothing to catch being wrong — an instrument
nobody is told about does not drift into error in public, it just stops being
run, which is why these are found by census and not by symptom. It is the one
sweep in the family whose classifier is **cross-repo by construction** (HALF C
resolves provenance through workspace callers), so a partial clone can corrupt
a PRESENT repo's verdict and `DEFERRED` does not cover that; measured, both
directions, 7 of 251 cited caller refs are cross-repo and leave-one-out over
all 16 repos produces **0 verdict flips**, so the sweep runs a TARGETED
leave-one-out over the derived supplier set every run rather than assuming the
axis away. It is also the one sweep with **no `min_rs_files` column** —
three others floor that identical walk over that identical population, and the
delegation is ASSERTED rather than assumed),
`instrument_reachability_drift_sweep.py` (every contract repo, on demand — the
Issue 787 verdict half of `instrument_reachability_gate.py`, and the one sweep
in the family whose ceiling is a **RATCHET** rather than a wall or a membership
set. Measured on its first run: **95 unreachable of 152** tracked
`scripts/*.py` over 16 repos, riir-train **61 of 61** — that repo's `scripts/`
is almost entirely plan-scoped one-offs, where the predicate OVER-CAPTURES,
because "unfindable from AGENTS.md" is the correct state for a script whose
whole life was one plan task. So the per-push gate pins this repo's own 7 rows
by MEMBERSHIP with a reason each, and the sweep constrains the DERIVATIVE
everywhere else: the commit that adds ANOTHER unfindable script reds, and the
existing rows stay their own repos' to adjudicate),
`highwater_contiguity_audit.py` (report-only, every contract repo: is a
repo's `.highwater` a contiguous allocation ledger — Issue 768's measured
REFUTATION of the counter-as-ownership-witness: 438 gaps + 27 resets over 73
counters under the Issue-770 per-commit-parent walk, no major repo contiguous;
the reset verdict half + the report-only unbumped observation live in
`numbering_drift_sweep.py` per Issues 769+770),
`sibling_docs_drift.yml` (reusable workflow, one caller), and
`ci_gate_coverage.py` (report, always exit 0: which repos gate their full
compile+lint surface in CI, and whether anything automatically starts it).
⛔ **Its standing finding is not that the main-only owner call is wrong — it is
that the lane it produces is ZERO, not reduced.** Measured 2026-09-15: **12 of
16** repos carry a real compile/lint command that no schedule and no push ever
starts, and every one of their `push: branches: [main]` filters is inert. The
two causes need different repairs and the report names them apart, because
`carries no copy` quietly suggests a fix that the other case cannot have:
**five repos have no `origin/main` AT ALL** (riir-auth, riir-kat,
riir-mmorpg-examples, seal-online-remaster, seal-remake) while their filter
names it, and the six that do have one carry no `.github/workflows/` directory
there. Promoting the file repairs the second; the first needs somebody to decide
whether the filter or the branching model is wrong. Until then those gates run
only when a human clicks them.
NOT in docs_gate's CHECKS — CI's single checkout would derive an empty
population and print a confident green over zero repos. Population derived
(BOUNDARY.md + `.git`); expectations committed in `scripts/*_floors.txt`.

`citation_drift_sweep.py` is the one that **prints its own error rates next to
its finding count** — plural, because there are two populations and a SAMPLE
rate does not transfer to rows it never sampled. Its CROSS rows split into the
pre-752 corpus, carrying **7/43 = 16%** false positives from a stratified
manual read (Issue 751 T1), and the **45** rows recovered by owner-consistency,
carrying **1/45** from a full census (Issue 752, re-rated by Issue 754).
Neither number is quotable without the other, nor without the ~3k-citation walk
and 19-repo population that produced them — a magnitude, deliberately, because
five-plus concurrent sessions edit these documents and an exact figure in
prose is drift waiting to happen (the dated snapshot lives in the sweep's own
docstring, where it is a measurement record rather than a claim); the
**IN-LOCAL-RANGE** bucket is UNDECIDED and never folded into either
neighbour. It also asserts its
katgpt-rs row against `issue_citation_gate.py`'s own parsed run rather than
trusting the two to agree.

Those 45 are the reason to distrust a lone error rate: every other FP class
this family documents **inflates** a count, and this one **deflated** it by
~15%. Qualification asked *"is a repo named?"* and never *"does that repo own
the number?"*, so `riir-chain Plan 211` (riir-chain's `.plans` top out at 058)
and `katgpt-rs Issue 513` (513 is riir-train's) both read as clean — the
attribution following the CODE while the number followed the DOCUMENT. Reading
a measured error rate as if it bounded the error in ONE direction is the
mistake; it bounds only the direction somebody thought to sample.

⛔ And that census's own `0/45` did not survive either (Issue 754). Its third
"outright wrong address", `riir-mmorpg-examples Issue 059`, was **correct**:
that repo records 059 in its own HISTORY.md heading, with the file removed the
day it was filed and never committed, so neither the worktree walk nor `git
log` could see it. Reading all 45 rows by hand could not have caught that,
because every read asked the same blind `allocated()` the same question. **A
census is exhaustive over ROWS, not over the ORACLE it checks them against** —
so never quote an error rate without naming the instrument the sample was
adjudicated against.

⛔ **And the wrong address the paragraph above names as a worked example —
riir-train Issue 513 written up as `katgpt-rs Issue 513` — was still standing
in the workspace when Issue 794 went looking for it** (riir-neuron-db `AGENTS.md:82`, repaired to `riir-train Issue
513 T6`). Not because `is_qualified` missed it: because the `⛔MISATTRIBUTED`
tag was computed **only in the CROSS bucket**, and the three-way bucketing runs
first. A citation whose number also falls under the *citing* repo's own ceiling
was reclassified **IN-LOCAL-RANGE** — "UNDECIDED, never clean" — and the tag
never ran. Never counted, never gated. IN-LOCAL-RANGE's premise is refuted by
such a row's own text: it reaches that bucket only when the Issue-754 oracle
found **no** local allocation *and* the author wrote a different repo's name
directly on the citation. **CROSS is unfollowable; this is followable, to the
wrong place** — its own class (`MISATTRIBUTED-IN-RANGE`), walled at 0
globally rather than ratcheted per repo, because it has no backlog. The
leniency was never a COUNT (`gate_says()` already asserts the sweep partitions
the gate's finding set); it was the **label plus the per-repo
`max_in_local_range` ratchet**, which tolerates a wrong address in the 15 repos
the per-push gate never runs in.
⛔ The boundary is **measured, and it is not the obvious one.** The same
predicate one branch up — at the `n in mine` short-circuit, where the number
*is* locally allocated — is **19 rows workspace-wide and 19 of them are
FALSE**: prose contrasting a local number with a remote one, the 40-char lead
catching the *neighbour's* address (`riir-ai Issue 853 / this repo's Issue
093`). That asymmetry is mechanism, not luck — a locally-allocated number has
a local referent for the prose to contrast against — so the rule stops at
IN-RANGE and the exemption is a measurement rather than an oversight. Read the
other column honestly too: it is **n = 1**, so "0 false positives" there is one
row's worth of evidence, not a rate. The per-push gate needed **no** change and
that is itself the finding — it has no IN-RANGE bucket at all, so the sweep
that cross-checks it was the **more lenient** of the two.

⚠ **`allocated()` is not a complete record, and the gap is a house STYLE**
(Issue 781). `heading_allocated()` — the Issue-754 path that recovers a number
whose file was created and removed without an intervening commit — anchors the
parenthetical immediately after the number, so `## Issue NNN (date) — title`
reads and `## Issue NNN resolved — title (date)` does not. Measured over 16
repos, **under half** the self-allocation records are read — and the split is
by convention, not by correctness: one repo scores 100%, **three score zero**,
and katgpt-rs is mixed, its own newest closes in the form its own instrument
cannot read. The figures are printed by the sweep every run and the dated
snapshot lives in `heading_style_blind`'s docstring; a magnitude here, because
an exact count in prose about documents five-plus sessions edit daily is drift
waiting to happen. Widening the pattern is **unsound and the sweep's
own self-test proves it**: arm 2 pins `## Issue NNN follow-up (date)` as a
measured negative — commentary on a number is not an allocation of it — and
`NNN follow-up (…)` is the same SHAPE as `NNN resolved — … (…)`. No
punctuation rule separates them. So the cost is **printed every run** rather
than guessed at, with the standing of AMBIGUOUS: on the local side it lands as
UNDECIDED noise (riir-clippy's 10 undecided rows are its own four numbers),
and on the owners side as a **false** `⛔MISATTRIBUTED` — Issue 754's exact
failure, inherited by Issue 794's in-range class. 0 live instances today, which
is the reason to print it rather than remember it.

⚠ **A document that discusses a misattribution has to reproduce it**, and the
instrument cannot tell a quoted specimen from a live one: the Issue-780
write-up above introduced **4 rows of the very class it documents**. The repair
is not a pin — it is to name the true owner inside the citation's own 3-line
window ("riir-train Issue 513, written up as `katgpt-rs Issue 513`"), which
clears the row *and* makes the sentence followable. Reach for that before
ratcheting a ceiling for prose about prose.

Each sweep carries **two floors, not one**: a ceiling is green over whatever
the instrument can SEE, so the finding count needs the *population* that
produced it, and the population floor is 0 in every repo that has none of the
thing — so it needs the *walk* size underneath it too (`min_rs_files`,
`min_manifests`, `min_scripts`). Where a sweep re-states a quantity its
per-push gate owns, it **asserts** the two agree rather than trusting them
(`trap_sentinel_drift_sweep.py` vs `trap_sentinel_gate.POPULATION_FLOOR`) —
`docs_gate_paths_sync.py`, one axis over.

## cfg-gated targets — the green-zero rule

A test file opening with `#![cfg(feature = "x")]` compiles to an **empty
binary** when `x` is off; cargo prints `ok. 0 passed` and **exits 0** —
byte-for-byte a real pass. The `#![cfg]` protects the **count**;
`required-features` protects the **reader** — both are needed, and only the
second is visible to whoever reads the output. A *default-on* gated target
still runs on a plain `cargo test`; a *default-off* one reports a green zero
every time anyone names it — read the severity split, never the pooled total.
`not(debug_assertions)` is a separate overlapping dimension: silent under
plain `cargo test`, and it **survives the fix** — adding a
`required-features` row moves the target into "w/ req-f", which reads as
protected and does not make it compile.

**Two traps in the profile dimension (Issue 741).** First: a file may carry
**more than one** whole-file `#![cfg]`, and rustc **ANDs** them — reading only
the first under-reports the profile term AND the feature set (56 of 1634 gated
targets workspace-wide carry 2+, up to 5 in one file). Second, and the one to
internalise: **gating a MEASUREMENT on `debug_assertions` makes it impossible
in the configuration that ships.** Every alloc gate here was unrunnable under
`--release` — the profile this document mandates for gates — because
`katgpt_core::alloc` itself was `cfg(debug_assertions)`, so the whole target
compiled to an empty binary and printed `ok. 0 passed`, exit 0. A profile is
not a knob; a feature is. Ask of any `debug_assertions` gate whether the thing
behind it is a **capability** (→ give it a feature, `any(debug_assertions,
feature = "x")`, and gate the machinery on `x` too — including any in-body
liveness sentinel, or the release binary runs the gate and asserts NOTHING) or
genuinely a **profile property** (an assertion about `debug_assert!`). It was a
capability the whole time, and "debug-only by design" had been written into the
guarding pin's own header as if it were a constraint. Read the split the
auditor prints — `unfixable` (bare term, no flag compiles it in release; the
pin worth having) vs `escapable` (`any(…, feature = …)`, already runnable in
release) — never the pooled DEBUG-only count, which reports the repair as if it
changed nothing.

Do not answer "how much of this is affected" by reading manifests. Run:

```bash
scripts/cfg_gated_target_audit.py            # all contract repos (derived)
scripts/cfg_gated_target_audit.py ../riir-ai # or one, by path
```

`scripts/suite_membership_audit.py` answers the next axis down: which
`[[test]]` targets no script/workflow names — run it when landing a new gate;
if nothing names it, add a suite row or record why not.

- A **report, not a gate** (exit 0): `cfg` on `target_os`/`miri` and an
  `any(...)` of features genuinely cannot be expressed as
  `required-features` — reported as their own classes.
- **Arming a target can RED a binary-counting floor**: an empty gated binary
  prints `test result: ok. 0 passed` and COUNTS as one — adding the row
  removes a line. Repair with a **passed-test floor**, not a re-pin.
- **Run the armed gates with `--release`** — a latency gate in a debug build
  measures an unoptimised binary.
- Verdict half: `scripts/cfg_gated_floor_gate.py` (katgpt-rs-scoped pins in
  `scripts/cfg_gated_floors.txt`; `max_load_bearing = 0` earns its keep; some
  pins are FLOORS — a ceiling cannot fail once the instrument goes blind;
  `scripts/all_ignored_load_bearing.txt` pins the ALL-IGNORED set by
  MEMBERSHIP — a set is gateable where its cardinality is not).

## A `required-features` row can EXIST and be WRONG — `scripts/required_features_build_audit.py`

Every audit above treats a target as protected once it **has** a
`required-features` row. A row that exists and is wrong is strictly worse
than a missing one: `cargo test --workspace` silently **skips** the target,
`--all-features` **builds** it (the union supplies whatever the row forgot —
the one configuration anybody runs it in passes), and every audit counts it
as protected. The row is wrong relative to what the file *imports*, and
imports resolve through cfg-gated re-exports that defeat grep — ask the
compiler, once per target:

```bash
scripts/required_features_build_audit.py --list            # rows only, no builds
scripts/required_features_build_audit.py ../riir-train     # one repo
scripts/required_features_build_audit.py . --grep pruners  # one slice
scripts/required_features_build_audit.py ../riir-train --batch  # 1 run per set
```

- A **report, not a gate** (exit 0; ~28 s/row — filter with `--package` /
  `--kind` / `--grep` / `--limit`; `--target-dir` when a sibling is building).
- `--batch` = **one cargo run per (package, EXACT feature set)**, never a
  superset — a superset build may supply the very import the row forgot.
- **Neither an error nor an artifact = UNSEEN, never BUILDS** — silence is
  not evidence; UNSEEN is never folded into the pass column.
- The free static verdict is correct AND insufficient: `dep/feat` / `dep?/feat`
  rows are valid cargo (a DEPENDENCY's feature); only the compiler
  distinguishes "names a feature that exists" from "names the feature that
  gates the module".
- **Read the USE SITES, not the error:** widen the ROW when the body needs
  the feature unconditionally; narrow the cfg when the use site is already
  gated.
- Push half (MAIN-ONLY since 2026-09-09): `.github/workflows/required_features_touched.yml` checks the

  rows a main push could have broken (a changed file that IS a row's target

  source selects the row; a changed `Cargo.toml` selects rows whose

  `(kind, name, required-features)` tuple differs base-vs-head; `--max-rows`
  REFUSES rather than truncates).

## A reported "p99" is often the MAX — `scripts/percentile_index_audit.py`

`sorted[(n as f64 * 0.99) as usize]` and `sorted[n * 99 / 100]` both land on
`n - 1` — the **maximum** — for every `n <= 1/(1-p)`: n ≤ 100 at p99, n ≤ 20
at p95, n ≤ 1000 at p999. Below that boundary the site reports one
observation under a percentile's name; a `.min(len - 1)` clamp prevents a
panic, not a wrong statistic. The quantity to print is **tail support** =
`n - idx` (samples at or above the reported rank): 1 at n=100, 2 at n=200,
10 at n=1000 — anything under 10 is weak.

```bash
scripts/percentile_index_audit.py             # all contract repos (derived)
scripts/percentile_index_audit.py ../riir-ai  # or one, by path
```

A **report, not a gate** (exit 0) — half the sites take their sample count
from a runtime length no static pass can reach. **UNRESOLVED is not
"clean"** — it is "needs a per-site read". Vocabulary is data (`VOCAB`),
population derived. Verdict half: `scripts/percentile_floor_gate.py` (pins in
`scripts/percentile_floors.txt`; `min_sites_scanned` is a FLOOR — a tokenizer
regression takes the population to ~0 and every ceiling passes).

The audit prints site rows only for the four severe classes, so the
UNRESOLVED bucket appears in the tally and nowhere else.
`scripts/list_unresolved_percentile_sites.py <repo>` dumps those rows for the
per-site read that resolves each to OK / DEGENERATE / not-a-percentile; the
2026-09-04
workspace-wide read (every UNRESOLVED row, all 16 repos) is recorded in its
own docstring.

**The POPULATION is what git TRACKS — `scripts/tracked_walk.py`, one copy
(Issue 777).** A filesystem walk behind a hand-typed directory-name skip set
is not the same set, and a name list cannot express "not ours". Measured, on
the run of this sweep that found it: seal-online-remaster's `mmorpg/` is
gitignored AND its own git repository, so its 1404 `.rs` files were credited
to the outer repo — and produced this audit's only TRUNC-VAR finding at an
address where the repair cannot be made. That is worse than a false positive;
it is a **correctly-shaped defect at the wrong address**, one axis over from
what `issue_citation_gate.py` exists for. riir-train's cargo OUT_DIR sources
sit under `.runs/target-release/`, `-cuda`, `-v2cpu`, `-bench`: the skip set
names `target`, and none of those IS `target`.

Read the second-order damage, because it is the part that lasts: **two
`percentile_drift_floors.txt` rows were unsatisfiable by any tracked walk of
their repo** — riir-train `2500` against 1129, and riir-chain `500` against
the **460** that repo had on the day the file was written. Neither had ever
been edited. A floor exists to catch an instrument going blind; a floor
measured over content the repo does not own reds on every box but the one and
the hour that produced it, and teaches whoever hits it that the sweep is
noise. Tracked-only was landed twice before (Issue 734 for the trap audit —
"25 findings in a gitignored vendored drop no repo owns"; Issue 738 T3 for the
platform/wasm32 pair) and not generalised, which is the whole reason the walk
now lives in one file with its own 8-arm self-test. `vendor/` exclusions ride
the per-repo line; the `.git` probe is load-bearing (`git -C` walks UP, so a
non-repo directory inside a repo would answer with its PARENT's paths); a tree
with no `.git` — `git archive`, a synthetic self-test fixture — falls back to
the walk rather than erroring.

## A Lean theorem can RESTATE its own definition — `scripts/restatement_theorem_audit.py`

`theorem sidecarHeaderSize_eq_sum : sidecarHeaderSize = magicSize + versionSize
+ …` where the RHS **is** the `def` body. `decide` closes it whatever the
constants hold, so it is green on every transcription typo it was written to
catch — while `lake build`, `#print axioms` and the proof gate's audited-surface
count all report it as a theorem that proves something. Four shipped in
riir-neuron-db for months (Issue 617, removed `24957a2`).

```bash
scripts/restatement_theorem_audit.py               # all repos with .proofs (derived)
scripts/restatement_theorem_audit.py ../riir-chain # or one, by path
scripts/restatement_theorem_audit.py -v            # every row, not just findings
```

- A **report, not a gate** (exit 0). The criterion is symbolic equality over
  **leaf** constants: unfold every composite nullary `def`, keep numeral-bodied
  leaves as symbols, compare as polynomials. Unfolding all the way to numerals
  instead would compare `464` with `464` and condemn every sound literal pin —
  **the leaf boundary IS the classifier.**
- **CROSS-DEF is not a finding.** `commitmentOffset = RAW_PREFIX_LEN` is
  symbolically equal too, but it pins two *independently maintained*
  definitions against each other and a perturbation arm proves it reds. The
  removed four had an RHS that existed only inside the theorem. Pooling the two
  would have condemned a load-bearing theorem.
- **UNRESOLVED is not clean** (function application, Mathlib, ℚ/ℝ ops), and
  `HYPOTHETICAL` — a theorem with binders — is split out rather than pooled,
  because it is 199 of 255 and pooling hides how few statements the arithmetic
  pass ever sees.
- Validated against a tree whose answer was known independently: riir-neuron-db
  at `24957a2^` reports **exactly** the four Issue-617 theorems, 0 at HEAD.
  That run is also what exposed the classifier's own defect — a repo-wide def
  table unfolded `Shard.zoneHashOffset` through ExperienceGraph's same-named
  chain. Scoped per module + transitive imports now.
- Standing (2026-09-12): **0 RESTATEMENT-INLINE** over 4 repos / 68 `.lean` /
  255 theorems; 19 UNRESOLVED + 6 conjuncts read one by one, all value pins.
- Verdict half: `scripts/restatement_drift_sweep.py` (workstation, every repo
  with `.proofs`, pinned in `scripts/restatement_drift_floors.txt`). **Two
  floors** — `min_lean_files` catches a WALK regression, `min_theorems` a PARSE
  one, and only the second moves when a tokenizer breaks on an unchanged tree.
  `--prove-fires` plants a restatement into a COPY of each repo and requires
  the count to move, so the ceiling is never a pin nobody has watched fail.

## A gate that ABORTS reports exit 0 — `scripts/trap_exit_launder_audit.py`

Every script above is a shell gate with `set -euo pipefail` and a cleanup
trap. On **macOS `/bin/bash` 3.2.57 — and only there** (Issue 735): when bash
aborts on an **unbound expansion** or an **`eval` syntax error**, it enters
the EXIT trap with `$?` **already 0** — so an EXIT trap whose last command
succeeds (`rm -f "$TMP"` always does) makes the abort exit **0**. Everything
after the abort silently did not run, and the caller reads a pass.

⛔ **This bites every macOS run — workstation AND the macOS CI lane; it is
`ubuntu-latest` that is immune.** This paragraph has now been wrong in BOTH
directions, which is the lesson: it first said "and CI reads a pass" (false —
over-claimed), was corrected to "a WORKSTATION defect, **not** a CI one"
(also false — under-claimed, and in the direction that hides a live
exposure), and is now measured on both sides. Interpreters, one at a time
(`scripts/trap_launder_premise_matrix.py`, 11 of them): bash **4.4.23 /
5.0.18 / 5.2.37 / 5.3.15**, dash and busybox ash **all preserve** the status;
fixed no later than 4.4. Every gate-running workflow in the workspace is
`runs-on: ubuntu-latest` → bash 5 → an aborting gate exits non-zero and the
job reds. **The exception is the macOS lane, and it was measured, not
reasoned about** (Issue 735 T3, answered early by the 737 layer-2b push run
`34137014037`): GitHub's `macos-26-arm64` ships bash **3.2.57 ONLY** — PATH =
`/bin` = `env`, no Homebrew bash in PATH — and reproduces all five errexit
LAUNDERS cells. So on `full_gate.yml`, this repo's only macos-latest runner of
a sentinelled script, **the sentinel is load-bearing in CI**, not merely on
workstations; its preamble step re-measures every run, so image drift is
observed rather than silent. T4 resolved **do not pin — measure**: a `shell:`
pin cannot govern a script's own `#!/usr/bin/env bash` shebang anyway. There
is no `bash:3.2` docker tag, so the premise's own interpreter is measurable
**only** on macOS — a workstation or that runner.

**Keep the sentinel regardless.** It costs nothing on 5.x, is load-bearing on
3.2, and "did the script reach its own completion point?" catches every other
premature death — a SIGTERM, a `set -e` trip in an unguarded spot, a future
editing slip — on **every** shell. The rescoping changes the class's
*severity*, not the value of the repair.

**`errexit` is the precondition, NOT `nounset`** — the first version of this
section had that backwards, because the premise harness hard-coded `set -euo
pipefail` and never varied the axis it was claiming about (Issue 734 T10):

| shell options | unbound expansion | `eval` syntax error |
|---|---|---|
| `set -u` (no `-e`) | aborts, **1** — *not* laundered | does **not abort at all** |
| `set -e` (no `-u`) | no abort (expands empty) | 2 bare, **0** trapped ✗ |
| `set -eu` / `set -euo pipefail` | 1 bare, **0** trapped ✗ | 2 bare, **0** trapped ✗ |
| (`set -e` command failure → 1 both ✓; command not found → 127 both ✓) | | |

So `set -u` **without** `set -e` cannot launder anything today — that is
**PRECAUTIONARY**, not EXPOSED, and pooling the two over-claimed on 15 of 41
rows. Two corollaries: the population predicate is the **union** (`set -e`
OR `set -u`) because errexit-without-nounset launders via the `eval` trigger
(measured: 0 such scripts, so that blind spot was empty — but it is a
measurement now), and the measurement **mode** is part of the claim — the
nounset fatal error exits **127** from `bash -c` and **1** from a script
FILE, so the harness writes a temp script.

`trap 'rc=$?; cleanup; exit $rc' EXIT` does **not** repair it — the rc it
saves is itself 0. Only a **completion sentinel** does: a flag set on the
script's own last line, checked by the handler, forcing exit 1 when the run
is INCOMPLETE *and* claiming success. An ordinary layer failure still exits 1
with its own message, untouched. `scripts/full_gate.sh` and
`scripts/proof_negative_test.sh` carry it (Issue 734).

```bash
scripts/trap_exit_launder_audit.py            # population + verdict, all repos
scripts/trap_exit_launder_audit.py ../riir-ai # or one, by path
scripts/trap_sentinel_drift_sweep.py          # the verdict, every repo, pinned
scripts/trap_launder_premise_matrix.py        # the PREMISE, 11 interpreters
```

Three halves, and they answer different questions — do not read one for
another. `trap_exit_launder_audit.py` derives the **population** and
classifies it (report, exit 0). `trap_sentinel_gate.py` is the **verdict** for
this repo (in the docs gate) and `trap_sentinel_drift_sweep.py` the verdict
for all 17 (workstation, pinned in `scripts/trap_sentinel_drift_floors.txt`).
`trap_launder_premise_matrix.py` measures the **premise** — one interpreter at
a time, via docker, script files not `bash -c`. It always measures the local
box first and prints **UNSEEN, never a zero**, when docker is absent: a
premise instrument that silently skips its arms reports "nothing launders" and
retires the whole class.

A **report, not a gate** (exit 0) — EXPOSED is latent, and a report that
exits 1 on dozens of latent rows is a report nobody runs. Population derived
(BOUNDARY.md + `.git`) and restricted to **tracked** `*.sh`: walking the
filesystem instead reported 25 findings in a **gitignored** vendored drop no
repo owns. Verdicts: **LIVE-FORWARD** (a double-quoted `trap "… $VAR …"`
naming a later-assigned variable — a *provable* abort, every run, and how
this was found), **EXPOSED**, **SENTINELLED**, **UNPARSED**, plus the
orthogonal **REPLACED** (2+ EXIT traps — `trap` replaces, it does not
accumulate, so earlier cleanup is silently dropped).

Each finding also carries its **exposure window** — `[last trap
registration, EOF)` — and the count of abort **triggers** (`$VAR` / `eval`,
with the body of any function the window *calls* folded in). Nothing before
the handler exists can be laundered by it, so a window with **zero** triggers
provably cannot launder whatever its `set` line says. A triage aid, not a
verdict (same standing as tail support in the percentile audit): it ORDERS
the rows, and a 2-line/0-trigger row and an 863-line/253-trigger row are
otherwise one row each. It is how the last EXPOSED row in the workspace —
`riir-ai/scripts/e2e_internet.sh`, trap on line 41 of 43 — is known to be
inert rather than merely inconvenient to fix.

**UNPARSED is the instrument admitting it cannot read** — the trap names a
function whose body never closed under brace counting, so *both* verdicts
would be guesses. It is not the safe direction and must not be pooled: a
runaway body swallows the rest of the file, and with it somebody else's
`exit 1` and some late literal flag, and reads as a **false SENTINELLED**,
which HIDES exposure. Found because riir-chain's
`block_pipeline_reachability_gate.sh` embeds a multi-line **single-quoted**
`awk` program containing `mod[[:space:]]*tests[[:space:]]*\{` — one
unmatched brace in DATA — and read EXPOSED while carrying a correct
sentinel. `scan_braces` is quote- and heredoc-aware now; UNPARSED covers
whatever it still cannot parse, and the verdict gate reds on it.

**shellcheck does not find this** (measured, Issue 734 T7): pointed at the
script carrying the live defect it reports one `SC2001` at default severity,
and with `-o all` its only remark on the fatal line is `SC2250` — brace
style. SC2154 does not fire, because the variables *are* assigned, just too
late.

Canonical failure: seal-remake's `ci_feature_guard.sh` — the script its
`rust.yml` runs — could not fail past layer 13 for months, because its
layer-13 trap named two variables assigned ~20 and ~45 lines later. It stayed
hidden because a ratchet ceiling had been red for three commits and stopped
every run *before* the bad line (seal-remake `26a18191`).

Verdict half: `scripts/trap_sentinel_gate.py` (in the docs gate). It pins this
repo's two by **membership**, floors the population (a classifier that goes
blind must RED, not report a green zero), and reds on the commit that adds a
new unsentinelled gate script. Its canary is two-sided and it earned that:
the first classifier called `full_gate.sh` SENTINELLED with its sentinel
assignment DELETED, because the script also has an unrelated
`if [ "$KEEP_LOG" -eq 1 ]` and the rule only asked for "tests the flag" and
"exits non-zero" *independently*. The flag must gate the failure branch —
tie them by block structure or the pin certifies nothing.

## A lane compiles what it NAMES — `scripts/wasm32_surface_audit.py`

Every axis in the wasm32 family (Issue 737) is about *how* a lane compiles
what it names. The seventh is one level up: **is what it names the whole
surface?** A row cannot notice a package it does not select, and seal-remake
had a positive `#[cfg(target_arch = "wasm32")]` block that no row built and
that had been **uncompilable since it was written** — it called a
`cfg(not(wasm32))` function (`.issues/010` T2, `.issues/738`).

```bash
scripts/wasm32_surface_audit.py            # all contract repos (derived)
scripts/wasm32_surface_audit.py ../riir-ai # or one, by path
```

- A **report, not a gate** (exit 0). Four buckets: **NAMED** (a row selects
  it by `-p` or a literal `--manifest-path`), **BY-DEP** (Issue 774: no row
  names it, but a named/derived package reaches it through non-optional
  in-repo path-dep edges — reachability, never folded into NAMED, because
  that coverage dies by a dep-graph edit in someone else's manifest),
  **UNRESOLVED** (a `--workspace` or *derived* row exists — whether it reaches
  this package is the separate-workspace axis, undecidable statically),
  **UNCOVERED** (no row could reach it). **UNRESOLVED is not clean** and is
  never folded into either neighbour. `--self-test` proves the by-dep
  detectors fire in BOTH directions (five canary verdicts: named / by-dep /
  uncovered / optional-not-credited / workspace-table-resolved).
- The predicate is the **positive** cfg: `not(target_arch = "wasm32")` is an
  ordinary native-only guard and counting it inflates everything (riir-ai
  `.issues/892` T4). **Comment lines are excluded** — prose explaining a cfg
  is not a cfg, and the comment recording why a file has *no* wasm32 arm
  otherwise makes that file read as browser code.
- ⛔ **And it reads ATTRIBUTES, not lines** (2026-09-15). A line scan cannot
  tell a real `#[cfg(target_arch = "wasm32")]` from one inside a raw string,
  and riir-clippy's `src/platform_audit.rs` is four such fixtures — Rust
  source embedded in `r#"…"#` as test INPUT for the platform-dead-code
  classifier. Those four were that repo's ENTIRE count, so the audit reported
  `1 package UNCOVERED, its arm compiles nowhere` about a repo with no wasm32
  code at all, and hard-failed its sweep row. **Third instrument to meet this
  class**: `platform_dead_code_audit` masks literals and says why, and
  `subprocess_encoding_gate` moved to an AST because its text scanner *"reported
  four offenders in the gate's own file — every one a fixture string inside its
  `selftest()`."* The masker is IMPORTED from `platform_dead_code_audit`, not
  re-written: it is a hand-rolled Rust lexer with its own measured defect
  history, and a second copy is a second thing to get wrong.
- ⚠ `cfg!(target_arch = "wasm32")` is split out and **not counted as
  surface**. It is a RUNTIME branch — it compiles on every target, so no lane
  can fail to reach it and it is not the question this audit asks. Seven sites
  workspace-wide; printed on the per-repo line as `EXCLUDED` so the decision is
  re-measurable rather than remembered, never folded into the gated count.
- First measurement (2026-09-07): **9 NAMED · 15 UNRESOLVED · 0 UNCOVERED**
  over 196 files / 24 positive-cfg packages / 17 repos. Resolved 2026-09-08
  (738 T1): the two-shape resolver upgrades a derived-row package only on
  row-bearing static evidence; the vendored `wgpu-hal` fork left the walk
  (738 T3); the per-package reads surfaced one real lane gap
  (riir-mmorpg-examples' standalone `warm-tier-do`, lane landed same day)
  and one uncompilable surface (riir-ai's `riir-examples` browser examples,
  filed there as `.issues/894`). 894 resolved same day in riir-ai (uuid `js`
  feature + a real clippy fix the never-linted wasm32 arm was carrying + a
  LITERAL `-p riir-examples` example row in that repo's guard layer 1.22 —
  a variable row reads as derived and would have kept the bucket). Standing:
  **23 NAMED · 0 UNRESOLVED · 0 UNCOVERED** over 191 files / 23 packages
  (measured 2026-09-08).
- The DEPENDENCY EDGE (Issue 774, 2026-09-14): the row predicate is
  dep-blind — `-p riir-shader-showcase --target wasm32` compiles the
  showcase's in-repo path deps too, so riir-shader's core+effects read
  UNCOVERED while every bundle build compiles them (compile-verified:
  `cargo check -p riir-shader-effects --target wasm32-unknown-unknown`
  exits 0). The `✓ by-dep` verdict credits exactly those edges —
  non-optional, plain + wasm32-target tables, `workspace = true` resolved
  through the root table, in-repo targets only; dev/build, optional,
  native-target, and cross-repo edges credit nothing. `seal-poc-submodule`
  is the standing negative control — deliberately excluded from its repo's
  CI and depended on by nothing, it stays UNCOVERED (that repo is read-only
  here; arm-vs-row is its owner's call). Standing (measured 2026-09-14,
  post-774): **26 NAMED · 2 BY-DEP · 0 UNRESOLVED · 1 UNCOVERED** over
  216 files / 29 packages / 20 repos — the growth vs 2026-09-08 is
  sibling-added wasm32 surface, not audit drift.
- ⛔ **That standing sentence was hand-typed and asserted by nothing** until
  Issue 785 — the shape Issue 784 had just closed one instrument over, where
  the same kind of cross-repo total went **46%** stale with no run noticing.
  The verdict half is `scripts/wasm32_surface_drift_sweep.py` now, sharing the
  report's `classify_repo()` so the 738 resolver and the 774 closure exist in
  one place. **Take the figure from a run, not from this bullet.** The 16-repo
  measurement on a partial box is 213 files / 28 packages / 25 NAMED, and
  `TOTALS` in `scripts/wasm32_surface_drift_floors.txt` is pinned against that
  — re-pin it, and the four absent per-repo rows, from one full-checkout run.
- ⛔ It produced three confident wrong answers before it produced a right one,
  all in the classifier: a walk of **0 files** (a Python `\s` handed to
  `git grep -E`, which is POSIX ERE — caught only because the walk size prints
  next to the verdict), then **17** false UNCOVERED (a *derived* `-p` list —
  the better design — read as the worst result), then **2** more (a
  `--manifest-path "$unit/…"` lane read as a bare row). A classifier's bucket
  boundaries ARE the finding, and they are only testable against cases whose
  answer is known independently.

## An arm that exists and RUNS may still reach nothing — `scripts/arm_reach_audit.py`

Issue 790. `check_validation_gate.py` (below) asserts that every CHECK invokes
an arm, and had to state the limit in its own docstring: *"arm QUALITY is not
statically decidable and is not claimed here."* The first clause is true and
the second is too strong — quality is not **statically** decidable, but
**reach** is measurable by EXECUTION, and Issue 789 measured it 53 times by
hand, finding **seven** arms that certified nothing until they were re-aimed.
A census done by hand is a census that stops being done.

```bash
scripts/arm_reach_audit.py                    # the report, the CHECKS population
scripts/arm_reach_audit.py --self-test        # 27 arms over its own buckets
scripts/arm_reach_audit.py skill_repo_set     # one module, by substring
scripts/arm_reach_audit.py --include-all      # every scripts/*.py DEFINING an arm
scripts/arm_reach_gate.py                     # the VERDICT (T2) — workstation, minutes
scripts/arm_reach_gate.py --canary            # 16 arm groups over its own arithmetic
```

Mutate a module's source **outside its own arm bodies**, re-exec, run its arm,
ask whether the arm noticed. Standing (2026-09-15, after T6): **22 modules ·
559 mutants · 372 KILLED · 26 SURVIVED (live) · 0 CRASHED · 0 NO-ARM ·
0 UNREACHED · 0 BASELINE**, every live survivor pinned with a reason. The 22nd
module is the gate itself. ⚠ The intermediate figures were **21 modules · 519
mutants · 317 KILLED · 47 SURVIVED** (T3/T4) and **552 · 360 · 31** (T2); T2
closed 16 of the 47 as real gaps and T6 closed 5 more, so read each drop as
arms being written, not as the population shrinking.

⚠ **The wall clock moved from ~73s to ~370s over T3 and that is the arms
working, not a regression.** The repairs gave several gates fixture-repo arms
(temp manifests, temp docs, temp git trees), so each of the 519 mutants now
buys a great deal more assertion. Read the cost as the price of reach; it is
still a workstation report and nothing runs it per-push.

⛔ **An earlier version of this paragraph read `99 KILLED · 88 CRASHED · 33 in
4 NO-ARM · 6 UNREACHED`, and the CRASHED column was a classification DEFECT in
the harness, not a property of the code.** `run_arm` wrapped the module `exec`
and the arm CALL in one `try`, so an arm that signals by raising — 
`required_features_static_gate.selftest` returns `None` and raises
`SystemExit(2)`, and several others do the same — had every mutant it caught
filed as CRASHED. Those modules could never show a KILL at all. The two phases
are separate now (import failure → CRASHED, *evidence of nothing*; a raise
while the arm runs → KILLED, the arm noticing), and the corrected figure is
**243 killed against 127 previously, with CRASHED at 0**. Read the first
number as having been wrong in the pessimistic direction; the harness was
blaming the gates for its own boundary.

- A **report, not a gate** (exit 0), except a blindness floor or a failing
  self-test (exit 2) — a harness that generates no mutants, or whose runner
  always says KILLED, prints a *perfect* score, which is the same output as
  perfection. Two floors: `MIN_MODULES` the walk, `MIN_MUTANTS` the operators.
- ⛔ **`BASELINE` is the bucket that was missing, and one of its two arms looks
  like a PERFECT score** (T6, 2026-09-15). The harness never asked the arm
  about the module's own **unmutated** source. An arm that is *already failing*
  kills every mutant, so the module reports 100% reach having distinguished
  nothing — and it does not merely escape the gate's `MIN_KILLED` floor, it
  **inflates** it. `BASELINE-RED` (arm fails unmutated) and `BASELINE-CRASH`
  (module will not exec unmutated) are their own module-level verdicts, the
  mutants are counted but **not run**, and neither is pooled into KILLED,
  SURVIVED or `UNREACHED` — `UNREACHED` says *the arm cannot express this* and
  sends the reader to widen an arm that is not the problem. The gate walls both
  at 0. Check the **environment** first on a RED: a drift sweep whose canary
  runs the real workspace needs the same markers the gates get
  (`DOCS_GATE_PARTIAL_CLONE=1` on a known-subset box), and two of them read RED
  without it.
- ⛔ **`--include-all` had NEVER been measured, and T6 measured it** — 55
  modules, ~2400 mutants, run **module by module with a wall timeout** rather
  than as one invocation. That is the operating instruction, not a detail: one
  run is unbounded in the worst case and not resumable, and the worst case
  happened twice on the day it was written (a two-hour non-terminating mutant,
  then a *blocking C call* the watchdog provably cannot reach — 3.5% CPU, no
  children, interrupt pending). The per-module walk took ~35 minutes, named
  both stragglers, and lost nothing when one was killed. Standing over **55 of
  55** modules: **2376 mutants · 1182 KILLED · 652 live SURVIVED · 535 exempt ·
  1 CRASHED · 6 TIMEOUT · 1 NO-ARM (19 more mutants)**. ⚠ Read that against the
  CHECKS population and **not** as a comparable number: these arms cover a
  *classifier*, and the whole 652 is an unread backlog — exactly the shape
  Issue 785 forbids ratcheting, and deliberately NOT in the gate's population.
- ⚠ **The three weakest were armed on the measurement, and every one needed
  an EXTRACTION before an arm could be written at all** — T4's finding three
  more times. `feature_isolation_gate` went **4 killed of 62 → 24** and
  `citation_weight` **3 of 41 → 12**: `parse_changed_flags` was welded to its
  `git diff` call, and `attribute()`, the scoring function § Numbering
  Discipline sends you to, had **no arm at all** while its module's arm covered
  only the two INPUTS that feed it. Both are pure over plain data and neither
  needed a fixture repo. `ci_gate_coverage` was the standing worst at **4
  killed of 74** (5% reach) and is **54 of 73** (1 live survivor); it needed
  both halves of the pattern — four verdicts extracted out of `main()` and a
  branch probe injected out of `git ls-tree`.
  - ⛔ **The extraction found a live defect, which is the argument for doing it
    even where the arms are the goal.** `main()` classified for DISPLAY with one
    ladder and COUNTED with independent predicates, so a repo carrying both a
    partial command and a data-borne signal was counted **twice**: the summary
    read `6 full; 1 dynamic; 9 partial; 1 no CI` over **16** repos. A verdict
    and a tally that disagree about how many states a repo is in is the same
    class as a count that is not a checksum.
  - ⚠ **An injected probe asserts the ABSTRACTION, so the production path is
    then free to disagree with it.** Measured: the injection that made every
    reachability rule reachable left `_git`, `_on_branch` and `default_branch`
    as the module's last three unreached decisions. They get a REAL git tree
    (`update-ref` into `refs/remotes/origin/*` — no network, no bare remote),
    and it reports **UNSEEN** rather than passing where git is absent. Budget
    the cost: the module's run went **3.2s → 33.4s** for those nine arms.
- ⚠ **Expensive is not wedged, and the report cannot tell you which.**
  `platform_dead_code_audit` (393s, 132/269) and `len_derived_drift_sweep`
  (1039s, 37/48) both blew a 300s budget and both completed cleanly when given
  one; `len_derived_drift_sweep` has the BEST reach in the extra population
  (2 live of 48) and would have been written off as a hang. An external
  timeout is a scheduling bound, never a verdict.
- ⛔ **A mutant can never RETURN, and without a bucket the hang is the MILD
  failure** (T6). Flipping a conjunct out of a loop condition produces a module
  that computes forever, and the harness had no bound at all: a
  `--include-all` run predicted at 13 minutes was still burning 98% of a core
  at **two hours**, wedged on one mutant of `restatement_theorem_audit`. The
  worse half is what happens when you interrupt it — the watchdog raises
  `KeyboardInterrupt`, `except BaseException` reads that as *the arm noticed*,
  and a non-terminating mutant is credited **KILLED**. `TIMEOUT` is its own
  verdict with CRASHED's standing (*evidence of nothing*), the rows are named
  individually, and the flag is checked BEFORE the kill. The deadline is
  **derived from the module's own baseline** run (10x, floored at 30s) rather
  than typed — one constant cannot mean the same thing to a 0.03s gate and an
  8.3s workspace sweep. Measured: the module that never terminated now finishes
  in **33s with 1 TIMEOUT**. ⚠ The watchdog is a thread + `interrupt_main`,
  because `SIGALRM` is POSIX-only and the workstation is Windows; it reaches a
  pure-Python loop and NOT a blocking C call. A subprocess per mutant would be
  airtight at ~2400 interpreter starts — naming the 10% it misses is the point
  of writing it down.
- ⛔ **The exec namespace is a registered module, and the bare dict was the
  harness's THIRD bucket-boundary defect** — invisible in the default
  population, which is why T1–T4 never saw it. `dataclasses` resolves a class's
  defining namespace through `sys.modules.get(cls.__module__).__dict__`, so a
  module exec'd into a plain dict dies at its `@dataclass` line. Measured:
  **seven** classifiers — `platform_dead_code`, `len_derived_binding`,
  `required_features_build`, `cfg_gated_target`, `cfg_row_implication`,
  `all_ignored_target`, `suite_membership` — read CRASHED on their own
  unmutated source, carrying **796 of `--include-all`'s 2382 mutants**. ⚠ The
  bare-dict direction is a **premise, not an assertion**: CPython ≤3.12 guards
  that lookup and 3.14 does not, so the self-test asserts only that a
  `@dataclass` module EXECs in the registered namespace (sufficient wherever
  the defect is live) and `dataclass_premise()` prints which side this
  interpreter is on, next to the verdict.
- **`NO-ARM` carried the finding that motivated T4, and pooling it either way
  destroys it.** Four CHECKS had no arm of their own —
  `percentile_floor_gate`, `cfg_row_implication_gate`, `trap_sentinel_gate`,
  `markdown_fence_gate` — because they **delegate** to the classifier they
  import. 789 credits that, correctly. But a classifier's self-test **cannot
  reach its consumer's pin arithmetic**, which is Issue 775's exact sentence:
  789's predicate asked whether an arm runs, never whether it can SEE the gate
  it guards. All four carry a `gate_selftest` now and the bucket is **0** —
  and each needed a small EXTRACTION first, which is the finding underneath:
  the verdict arithmetic sat inline in `main()` beside its own error messages,
  so it was unreachable by construction.
- **`UNREACHED` is its own marker** and it exists because the first version of
  this report printed `✓` for it: `orphaned_attr_gate` scored 0 killed / 5
  crashed / 7 exempt, so the arm distinguished *nothing* and the row read as
  the cleanest in the set. Now **0** — one of the six was a genuine gap
  (`required_features_static_gate`'s pin READER, whose line filter and
  REQUIRED_PINS completeness check had no arm) and the other five were the
  CRASHED misfiling above.
- ⛔ **OPERATOR SCOPE is narrow and the whole report must be read through it.**
  Only control flow and off-by-one are mutated (comparison flips, `and`↔`or`,
  dropped `not`, bool constants, `+`↔`-`). **Regex and string literals are NOT
  touched** — and that is where most of this repo's decision logic lives.
  Measured: `docs_gate_checks_sync` has 20 hand-verified arms that red under
  regex perturbation and scores **2 killed of 10** here. A low kill count is
  not evidence an arm is weak.
  - `+`↔`-` was added in T4 for a measured reason: with comparisons alone,
    `markdown_fence_gate` read UNREACHED while its arms asserted real
    behaviour, because its only real decision is `n_lines - first` and no
    comparison touches it. This repo's whole percentile section is about an
    index landing on `n-1`, so off-by-one is the operator class that matters
    most here.
  - `if __name__ == "__main__"` is **skipped**, not exempted: it is the entry
    point rather than a decidable rule, no arm can kill it, and it is in all
    61 tracked scripts. Skipped so it cannot inflate the total `MIN_MUTANTS`
    floors.
- ⚠ **Reach is per MODULE, so a rule asserted by a DIFFERENT module's arm reads
  SURVIVED** — check this class FIRST on any survivor. Measured:
  `skill_repo_set_gate.derive_repos` survives here and is covered by
  `population_sync_gate`'s synthetic-workspace canary. This repo shares rules
  across modules deliberately (Issue 755), so the audit is blind in exactly the
  direction the architecture points.
- ⚠ **EQUIVALENT mutants are the other false-positive class** (a `>=` whose
  operands can never be equal; a `< 0` sentinel test flipped to `<= 0`). So
  SURVIVED is arm reach per function, never a defect count.
- `prove_fires` bodies are excluded from mutation but the arm is **not run**:
  it is a known-answer validation against a FROZEN commit, so no mutation of
  the working source can change its verdict, and running it per mutant was 436
  `git archive` calls — measured at **80.2s vs 4.4s**, with the children's
  output escaping `redirect_stdout` (a subprocess writes to fd 1) and littering
  the report. Output is suppressed at the **file-descriptor** level for the
  same reason.
- Validated by sampling: of the first five survivors read one by one, **three
  were real and closable, one was cross-module-covered, one was EQUIVALENT** —
  and closing the three took `skill_repo_set_gate` from 18 to 22 killed with
  its survivors from 7 to 3, leaving exactly the two EQUIVALENT rows and the
  one cross-module row. T3 then read the rest module by module: **123 → 47**.
  **Do not quote the SURVIVED total as a defect count** — the 47 that remain
  are dominated by three classes, each documented at the line it lives on:
  redundant guards that are provably EQUIVALENT (a `find() < 0` after an
  earlier match; a set membership test `or`-ed with another; the closure
  bound whose slack-less form is exactly sufficient), the **git/subprocess I/O
  shell** an arm cannot enter without spawning the auditor it reads, and
  message-formatting arithmetic.
- ⛔ **That three-class characterisation of the 47 was TOO GENEROUS, and T2
  found it by trying to write the reasons down.** A pin file demands one
  sentence per row, and the sentence could not be written for about a third of
  them: they were plain functions over plain data — `_parse_feature_spec`,
  `parse_status_phrase`, the `local_default_closure` walk, the three manifest
  READERS that decide which packages enter the model at all — with no fixture
  repo and no subprocess between an arm and the decision. They were **real
  gaps wearing an EQUIVALENT label**, and pinning them would have been a
  backlog wearing a pin, which is exactly what Issue 785 forbids. Closing them
  first took the set **47 → 27**: `bench_doc_audit` 23 → 9, `markdown_fence`
  3 → 1, `cfg_gated_floor_gate` 4 → 2, `skill_repo_set` 3 → 2,
  `trap_sentinel` 1 → 0. **Writing the reason is the adjudication** — a
  classification made while reading a list is not the same act.

### The verdict half — `scripts/arm_reach_gate.py` (T2)

The quantity to gate is **not the count**, and this repo already had the rule
written for `cfg_gated_floor_gate`: *a set is gateable where its cardinality is
not.* The survivors are pinned by MEMBERSHIP with a REASON per row in
`scripts/arm_reach_survivors_expected.txt`, and the wall is **0 UNPINNED**. A
ratchet would tolerate a new unreached decision line as long as somebody armed
an old one; membership does not. It reds in BOTH directions, and `UNREACHED`
and `NO-ARM` are walled at 0 **separately** — pooling either into the survivor
count is what the bucket note above forbids.

- **The key is LINE-FREE**, and that is load-bearing rather than tidy: a line
  NUMBER drifts on every edit above it, so a line-numbered pin file reds on
  commits that changed nothing about it, and a pin file that reds on noise is
  one people delete. It is
  `<module>::<function>::<operator-token>::<8-hex digest of the line TEXT>#<n>`,
  with the ordinal scoped to the WHOLE address — the
  `len_derived_eyes_expected.txt` precedent. Scoping it that way is what makes
  it stable: a new `>=` site in a function hashes differently and renumbers
  nothing. Only genuinely duplicate line text shares a sequence (there are two
  such rows, both real: three `+` on one `print`, two `True` kwargs on one
  `subprocess` line).
- The digest is unreadable by design, so each row carries its source line in a
  `#= ` comment **which the gate VERIFIES against the observed text**. A
  comment is the part of a pin file a human adjudicates from, and a comment
  nothing can red is a comment that drifts into a lie. ⚑ It earned its keep on
  the first real run: the membership wall was clean and the only failure was a
  hand-copied comment missing its trailing `:`.
- **It gates ITSELF** (population = the CHECKS set **+ this file**). Not
  symmetry: an exempt gate certifies nothing, and on its first self-hosted run
  it found a degenerate arm in its own key builder — the ordinal counter's
  `+ 1` flipped to `- 1` still yields two distinct keys, so a count-only
  assertion read green. Assert the ordinal VALUES.
- **The two PERMISSIVE sets are pinned by membership**, because no floor
  guards them: `EXEMPT_FUNCTIONS` (a name added there deletes every survivor
  in that function from the finding set) and `ARM_NAMES` (arm bodies are never
  mutated, so a name added there turns decision code into unwatched code —
  adding `main` would look like a tidy-up). `check_validation_gate` found the
  same shape in its own vocabulary.
- Three floors, failing differently: `MIN_MODULES` the walk, `MIN_MUTANTS` the
  operators, and `MIN_KILLED` the **runner** — a runner that reports KILLED for
  everything empties the survivor set, reds every pin as "no longer survives",
  and the obvious remedy is to delete them all.
- **Not a `docs_gate.sh` CHECK, and not a sweep.** Measured **157.6s** over
  22 modules / 552 mutants, against the docs gate's ~13s budget. It is a
  workstation verdict, the same standing as the eleven drift sweeps. There is also deliberately **no `--prove-fires`** — the
  known-answer validation would be a full mutation run over a `git archive`d
  tree to re-derive a fact the issue already records.
- ⚠ **Unlike Issue 789's, this class DOES generalise and a sweep half is
  owed.** 789 measured its population at ONE (katgpt-rs is the only repo with
  a CHECKS array) and declined a sweep on that measurement. Re-measured here
  for arms rather than CHECKS: **18 arm-bearing `scripts/*.py` across three
  sibling repos** (riir-train 14, riir-ai 3, riir-clippy 1). Do not carry 789's
  "no sweep" answer across — it was an answer to a different question. ⚠ But
  the population's SHAPE settles the ceiling, and it is **4 standing
  instruments + 14 plan-SCOPED** riir-train `planNNN_*.py` gates — so the
  ceiling is a **RATCHET on the derivative**, not a wall
  (`instrument_reachability_drift_sweep`'s answer, for its reason). ⛔ And
  T5 is BLOCKED on something no other sweep in the family faces: all eleven
  are STATIC readers, and this one would **EXECUTE** ~700 mutated copies of
  another repo's gate scripts, whose arms may read metrics blobs or write
  artifacts, in a repo another agent writes concurrently. It needs a sandbox
  story first. Do not land it by symmetry.
- **What T3 found by fixing, and it is the pattern worth carrying forward:**
  in every module the CLASSIFIER was well armed and the **VERDICT** was not.
  `bench_doc_audit` had fixtures from real workspace shapes for its
  reachability model and its tokenizer, and nothing at all for the function
  that joins them; `cargo_comment_audit` had a 20-arm precedence ladder and
  nothing for the scope choice that consumes it; `issue_citation_gate` had 39
  arms and none on the deferral line it prints on every partial-clone run.
  Both halves take a repo path, so all three were armable the whole time.

## A gate whose own failure path is asserted by nothing — `scripts/check_validation_gate.py`

Issue 775 landed six canary arms over a gate's **own pin arithmetic, which the
classifier's self-test cannot reach**. The sentence above is in this file, it is
correct, and it names a rule. The rule landed in **one** gate and was never
generalised — the sixth recorded instance of that shape (Issues 777, 778, 793,
782, 783). Measured 2026-09-14: **six of twenty** CHECKS invoked no arm at all,
own or delegated, carrying **2,050 lines** of per-push logic whose failure path
no test had ever executed.

```bash
scripts/check_validation_gate.py                    # the verdict, per push
scripts/check_validation_gate.py --canary           # 11 arms over its own arithmetic
scripts/check_validation_gate.py --prove-fires 6804d983
```

- The predicate is **invokes an arm UNCONDITIONALLY**, not "has an arm".
  `docs_gate.sh` runs each check as `"$PY" "$script"` — **no arguments** — so an
  arm behind `'--canary' in sys.argv` never fires on a push. Not hypothetical:
  `population_sync_gate.py`'s eight adversary arms, landed by Issue 788 the
  **day before**, were flag-gated and ran on no push at all. They cost 0.17s,
  so there was never a cost argument for the flag either.
- **Delegation is credited, and must be.** Four checks reach their arm through
  the classifier they import (`percentile_floor_gate` →
  `percentile_index_audit.selftest`, plus `cfg_row_implication_gate`,
  `trap_sentinel_gate`, `platform_dead_code_floor_gate`). That is Issue 755's
  DRY answer; refusing it pushes every gate toward a second copy of a rule it
  does not own.
- ⛔ **The first census of this was wrong in the OVER-reporting direction.** It
  grepped the CLI flag strings `--canary` / `--prove-fires` / `--self-test`,
  credited none of those four, and claimed nine bare checks where there were
  six. A census over one representation is blind to whatever that
  representation omits — Issue 787's lesson, reproduced within ten minutes of
  going looking for a new instance of it.
- **`ARM_NAMES` is the permissive direction** and the floor alone does not
  guard it: an empty set reds every check and is impossible to miss, while a
  set that quietly widens (add `main`) greens every check silently. Two floors
  (`MIN_CHECKS` the array parse, `MIN_ARMED` the AST resolution — a walk that
  finds every check and credits none looks exactly like nobody having written
  any arms), plus a canary arm asserting `main` is not in the vocabulary.
- Exemptions are pinned by **membership with a reason per row**
  (`scripts/check_validation_expected.txt`); a reasonless row is refused and a
  row whose check has since grown an arm reds. The file is **deliberately
  empty** — a row reading "not written yet" is a backlog wearing a pin, which
  Issue 785's rule forbids.
- ⚠ **What it does NOT assert:** that an arm which exists and runs is any
  *good*. An arm whose perturbation reds nothing certifies nothing, and Issue
  789 found **seven** such arms while writing the ones this gate counts — one
  whose anchor string was wrong, one whose fixture had no terminated fence for
  the fail-safe to discard, one aimed at the wrong side of a lookbehind, one
  whose input order already matched sorted order. Arm quality is not statically
  decidable and is not claimed. Read the verdict as the weaker thing it is.
- `--prove-fires 6804d983` (the commit that FILED 789) is two-sided against an
  independently known answer: seven checks unarmed there, six bare and one
  flag-gated, named individually. ~0.3s, opt-in on the
  `platform_dead_code_floor_gate` precedent — only `scripts/` is extracted.
- ⛔ **There is NO sweep half, and that is a measurement rather than an
  omission** (Issue 789 T4). Every other verdict class here got one because the
  question generalised; this one does not. Measured over the 16 repos on this
  box: **katgpt-rs is the only repo with a `scripts/docs_gate.sh` CHECKS array
  at all** (riir-train has 58 `scripts/*.py` and riir-ai 7, but no such array).
  A sweep would derive a population of ONE and print a confident green over it
  — the exact reason `ci_gate_coverage.py` is kept out of the CHECKS set. The
  cross-repo question that *does* generalise is "is this instrument findable?",
  and `instrument_reachability_drift_sweep.py` already ratchets it. Do not add
  a sweep here by symmetry with the family; re-run the measurement first.

## A census reads the DOCUMENT, so an undocumented instrument is invisible — `scripts/instrument_reachability_gate.py`

Issue 785's close-out claimed every cross-repo class in `scripts/` had both
halves. `1a5b6571` bounded that to "every cross-repo class **whose verdict is
walled at a small number**". The bounded claim was **still false** by exactly
one instrument — `len_derived_binding_audit.py`, cross-repo, findings walled at
0, no verdict half, closed hours later as Issue 786.

The miss is not the point; the **mechanism** is. Both censuses enumerated the
audits **AGENTS.md documents** against their sweep halves, and that file did
not name the audit at all. *A census that reads the document cannot see an
instrument the document omits*, and it reports a confident, complete-sounding
answer over the subset it can see — every blindness floor in this repo, one
level up, with the DOCUMENTATION as the population nothing floored.

```bash
scripts/instrument_reachability_gate.py                  # the verdict, this repo
scripts/instrument_reachability_gate.py --canary         # the 9 adversary arms
scripts/instrument_reachability_gate.py --prove-fires 18dbe980
scripts/instrument_reachability_drift_sweep.py           # every repo, ratcheted
```

- The predicate is **REACHABLE**, not "named in AGENTS.md". Roots are
  `AGENTS.md`, `scripts/docs_gate.sh` and `.github/workflows/*.yml`; the
  closure then follows script → script references, so a helper invoked by a
  documented instrument counts. The cases demand it —
  `all_ignored_target_audit.py`, `cfg_row_implication_audit.py` and
  `ci_test_execution_report.py` are in no document either, yet each runs
  per-push via an instrument that IS documented.
- ⛔ **`HISTORY.md` is deliberately NOT a root.** It is the archive, it is not
  loaded into a session, and an instrument findable only from it is the
  instrument that stops being run — counting it would have made the gate
  vacuous on the one case that motivated it.
- Pinned by **MEMBERSHIP** with a **REASON per row**
  (`scripts/instrument_unreferenced_expected.txt`); a reasonless row is
  refused. Reds in both directions. **The default for a real instrument is to
  make it findable, not to add a row** — two of the nine measured were wired
  into AGENTS.md instead (`list_unresolved_percentile_sites.py`,
  `citation_weight.py`).
- Two floors. `min_scripts` is the walk. `min_roots` is the **permissive**
  direction and the one easy to leave out: an empty root set makes everything
  unreachable and reds loudly, but a root set that quietly *widens* makes
  everything reachable and prints a green.
- `--prove-fires 18dbe980` is a known-answer validation: at the parent, the
  Issue 786 audit was named only in `HISTORY.md`, so it was the **tenth**
  unreachable script and this gate reds there.
- Verdict half across the workspace:
  `scripts/instrument_reachability_drift_sweep.py` — a **ratchet**, and the
  reason is measured (95 of 152 unreachable, riir-train 61 of 61 where the
  predicate over-captures). See the sweep family list above.

## A kernel can derive its SHAPE from a buffer's declared size — `scripts/len_derived_binding_audit.py`

`let n_positions = kv.len() / 2 / kv_stride;` inside a CubeCL kernel computes
that dimension from the bound buffer's **declared size**, not from the length
metadata handed to `BufferArg::from_raw_parts`. Bind a buffer whose declared
size exceeds the live range and the kernel silently derives the WRONG shape —
reads never-written memory, writes a measured identically-zero result. No
panic, no NaN, no wrong-looking output (riir-ai `3e00c93e0`, riir-train
Issue 511).

The defect is a **JOIN** of two facts in two files, and a report over either
half alone is noise: HALF A is the in-kernel `.len()` derivation, HALF B is a
bind site whose declared size can exceed the live range (a persistent
struct-field handle, a capacity-sized `client.empty()`, a reused scratch
slice). HALF C (Issue 766) resolves a wrapper parameter's provenance through
**workspace** callers — which is why this instrument's verdicts are cross-repo
by construction, the only ones in the family that are.

```bash
scripts/len_derived_binding_audit.py        # the report, all contract repos (derived)
scripts/len_derived_drift_sweep.py          # the verdict, every repo, pinned
scripts/len_derived_drift_sweep.py --no-stability   # skip the leave-one-out arm
scripts/len_derived_drift_sweep.py --canary         # the 12 adversary arms
```

- The report is a **report, not a gate** (exit 0), except a WALK REGRESSION —
  it carries two loose global floors (`FLOOR_RS_FILES`, `FLOOR_KERNELS`) and
  refuses a confident zero below them. Population derived (BOUNDARY.md +
  `.git`), **tracked** `*.rs` only (Issue 777 — it was one of the three
  instruments walking a gitignored nested repository).
- **UNRESOLVED is not clean** and is never folded into a neighbour: it is 118
  of 164 bind sites, and a ratchet on a bucket meaning *unanswered* is a
  backlog (Issue 785's rule). It is reported, unpinned, with the reason printed
  where it is READ.
- **PERSISTENT-UPSTREAM is the EYES LIST, not the finding list** — some caller
  binds a struct FIELD, so the declared size is whatever that field was created
  as. Pinned by MEMBERSHIP in `scripts/len_derived_eyes_expected.txt`, keyed
  line-free on `(repo, file, kernel, handle)` **plus a count within that
  address**, because the key is not unique in general.
- The verdict half walls the joined buckets (CAPACITY, CAPACITY-UPSTREAM,
  PERSISTENT) at 0 and floors `min_kernels` / `min_binds` per repo. ⚠ Those
  floors are **vacuous in 14 of 16 repos** (riir-ai 43/143, riir-train 9/21,
  everyone else 0/0) — Issue 783's population shape, not Issue 784's.
- ⛔ **`DEFERRED` is not enough here, and that is the axis no other sweep has.**
  A partial clone can corrupt the verdict of a row in a repo that IS present,
  which is a row measured WRONG rather than a row not measured. Measured both
  directions (2026-09-14): **7 of 251** cited caller references are cross-repo,
  and **leave-one-out over all 16 repos produces 0 verdict flips** — so
  per-repo pins are sound TODAY, and the sweep re-measures a TARGETED
  leave-one-out (the supplier set derived from the run) every time rather than
  carrying that measurement forward as a claim.
- It carries **no `min_rs_files` column** on purpose: `orphaned_attr`,
  `platform_dead_code` and `percentile` already floor that identical
  `tracked_files(repo, "*.rs")` call over the identical population, and they
  already disagree with each other about the number. The delegation is
  **asserted** — the sweep reds if any repo it pins loses its non-zero row
  there.

## An item can be dead on a platform NO lane compiles — `scripts/platform_dead_code_audit.py`

`const NEON_U8: usize = 16;` declared ungated, used only inside an
`#[cfg(target_arch = "aarch64")]` fn: **dead code everywhere but aarch64**,
and silent on aarch64. `full_gate` is macOS/aarch64 (the const is alive
there), `wasm32_gate` compiles wasm32 — so the x86_64-native lane that emits
the warning is a **workstation** lane and no automatic gate in this workspace
ever sees it. Five specimens in two days across two repos (riir-clippy intake
P22), the first being `ea4c2873` here.

```bash
scripts/platform_dead_code_audit.py             # all contract repos (derived)
scripts/platform_dead_code_audit.py ../riir-ai  # or one, by path
scripts/platform_dead_code_audit.py --self-test # the 24 classifier arms
scripts/platform_dead_code_audit.py --prove-fires ea4c2873
```

- A **report, not a gate** (exit 0) — except a classifier MISS, which exits
  **2**: an instrument that cannot classify must not be read as `0 findings`.
  The self-test runs on every invocation. Population derived (BOUNDARY.md +
  `.git`), **tracked** `*.rs` only, `vendor/` excluded with its count on the
  per-repo line (Issue 738 T3's rule — riir-ai's `wgpu-hal` fork supplied 5
  rows nobody owns).
- **MOD-REF is a separate bucket and is never folded into the count.** A
  `mod name;` referenced only from gated code satisfies the rule and is *not*
  a rustc finding: measured on `katgpt-types::simd::horizontal`, a wasm32
  `cargo check` is silent because every item inside that module is itself
  x86_64-gated, so the module is **empty** rather than dead — appending one
  ungated `fn` reproduces the warning, on the **fn**. rustc reports dead code
  at the ITEM, which this audit reaches independently.
- ⛔ Its header claimed "no known direction in which this INVENTS a finding"
  and that was **false on the first sweep it ever ran**: masking string
  literals dropped Rust 2021 **inline format args**, so riir-ai's
  `SWEEP_COUNTS` — `println!("{SWEEP_COUNTS:?}")` ungated in `main`, gated
  everywhere else — read as a finding. A conservative-by-construction
  argument is a claim about code somebody else wrote; this one survived until
  a real corpus contradicted it.
- ⛔ **An arm is only a canary if its own perturbation REDS it.** Of the three
  arms added with the buckets, the `vendor/` one red **nothing** under
  perturbation — the synthetic trees have no `.git`, so they took the
  filesystem-walk branch where a redundant `"vendor"` in `SKIP_DIRS` was doing
  the filtering. One exclusion, two code paths, and the arm certified the path
  it was not aimed at.
- Standing (2026-09-14, 16 of 20 repos on this box): **0 findings · 1
  MOD-REF** over 8694 files / 3433 units / 119452 candidate decls. The first
  sweep's two riir-ai rows were compile-verified and repaired —
  `note_ane_dispatch` (x86_64, `--features ane_prefill`) and `gen_u64_bytes`
  (wasm32, `--features chacha20_rng`).
- Verdict halves (Issue 775, 2026-09-14):
  `scripts/platform_dead_code_floor_gate.py` per-push in the docs gate
  (katgpt-rs scope, pins in `scripts/platform_dead_code_floors.txt` — two
  blindness floors, the MOD-REF row by **membership**, plus six canary arms
  over the gate's own pin arithmetic, which the classifier's self-test cannot
  reach) and `scripts/platform_dead_code_drift_sweep.py` on the workstation
  (every contract repo, pins in `scripts/platform_dead_code_drift_floors.txt`;
  population taken from `repo_set.txt` as well as the walk, so a partial box
  DEFERS loudly instead of greening over 16 of 20). `--prove-fires ea4c2873`
  runs by DEFAULT in the sweep and is opt-in on the gate: ~5.6s of `git
  archive` to re-prove a fact about a frozen commit is worth a workstation run
  and not a per-push one (the gate is ~6.2s against a ~13s whole-docs-gate
  budget).

## `text=True` decodes with the SYSTEM locale — `scripts/subprocess_encoding_gate.py`

`subprocess.run(..., text=True)` decodes the child's pipe with
`locale.getencoding()`. macOS, `ubuntu-latest` and the M3 are all UTF-8, so
**nothing that could notice this ever runs it** — and every instrument in
`scripts/` prints `✓`, `✗`, `⛔` and em-dashes. Measured on the Windows
workstation (cp874), against this repo's own `git log -3 --format=%s`:

| form | the em dash `E2 80 94` comes back as |
|---|---|
| `text=True` | `0xe42 0x20ac 0x201d` — three cp874 chars, silently |
| `encoding="utf-8"` | `0x2014` |

Two failure modes, and the **crash is the better one**. Silent mojibake: rc 0,
a plausible string, and a caller matching `re.search(r"FAILED — (\d+)", out)`
matches nothing and reads a confident **zero findings**. Or the decode raises
inside `subprocess`'s reader THREAD, where the exception dies — `run()` returns
normally with the **returncode PRESERVED and `stdout = None`**, which is what
`citation_drift_sweep.gate_says()` got.

`PYTHONIOENCODING=utf-8` does **not** fix the first mode and makes the second
MORE likely: it pins the CHILD's encoder, so the child emits correct UTF-8 that
the parent then decodes as cp874. Both halves are needed, and they are pinned
as separate classes — **DECODE** (`text=True` with no `encoding=`) and
**CHILD-ENCODER** (a `sys.executable` spawn with no `PYTHONIOENCODING` in its
`env=`) — because a shared pin would hide which half regressed.

It is a per-push **gate** and not a sweep-and-done for one reason:
`staged_set_audit.py` has carried the correct form *and a comment naming this
exact defect, dated 2026-09-04*, since the day it was written, and 27 more call
sites were added without it. The ceiling is 0 on both classes over a floored
population (tracked `*.py` AND `subprocess` call sites). Its first real run
found a 28th site nobody had grepped for —
`.agents/skills/doc-sync/tools/linkcheck_sweep.py`, outside `scripts/`
entirely.

⛔ **And it shipped with one half — the gate, no sweep (Issue 783).** Eleven
other verdict classes here carry both, and the asymmetry was not a judgement
call that was made; it was a step that was skipped. `scan()` already took a
repo path, so the question was answerable the whole time, and the answer was
**29 DECODE + 2 CHILD-ENCODER over 5 of 16 repos** — riir-train 12+1,
riir-clippy 9+1, riir-ai 6, riir-dapps 1, seal-game-editor 1. Two were not
latent: `riir-clippy/scripts/gen_dashboard.py:552` reads `git log --pretty=%s`
across the siblings, and **every commit subject in this workspace uses an
em-dash**. Read that as the standing failure mode, now recorded five times
(Issues 777, 778, 793, 782, 783): a rule landed in one instrument and never
generalised. Before fixing such a class, grep the whole family and land the
repair as one shared mechanism.

**It scans the AST, and that was not the first design.** A text scanner has to
be paren-matched rather than line-scoped (`encoding=` sits on a later line than
`text=True` in every wrapped call here), and the paren-matched version then
reported **four offenders in the gate's own file** — every one a fixture string
inside its `selftest()`. The repairs on offer were to exempt the gate from
itself or to obfuscate its test data, and an exempt gate certifies nothing.
`ast` sees a string literal as a literal; a file it cannot parse is
**UNPARSED** and reds, never folded into the pass column.

## A sweep reads the WORKTREE, so a finding may exist in NO commit — `scripts/worktree_state.py`

Issue 797. Every instrument in the sweep family above walks the **working
tree**. This workspace runs five-plus concurrent agent sessions against
**shared worktrees** — `staged_set_audit.py` (below) exists for exactly that
hazard one axis over — so a row a sweep prints may sit on a line no commit
contains, and a repo a sweep calls clean may be clean only because somebody's
uncommitted edit removed the offending line.

Measured 2026-09-15, `citation_drift_sweep.audit()` run twice per dirty repo
(the worktree, then every dirty in-scope document replaced by its HEAD blob):
the workspace's **entire** standing CROSS finding — 1 of 1 — was an artifact.
HEAD carries `Filed … from the riir-train Research 453 session`; an uncommitted
edit by another session strips the qualifier, and the sweep reports an
unfollowable citation. It had already cost a session, carried across a context
boundary as backlog reading *"blocked, that session has HISTORY.md
uncommitted"*. The correct verdict was not *blocked*; it was **there is nothing
to fix**, and no amount of reading the sweep's own output could say which.

**The POPULATION moves too**, which a row-level read alone misses: the same two
runs put `n_cites` at **601 (worktree) vs 607 (HEAD)** and `ambiguous` at 162 vs
163, because that session's uncommitted deletion of a 30-line block took six
citations out of the denominator. A floor or ratchet re-pinned from such a run
bakes another session's in-flight edit into a tracked expectations file, where
it reds on every other box.

Three verdicts, never interchangeable:

- **COMMITTED** — the finding's file matches HEAD. An ordinary finding.
- **UNCOMMITTED** — the worktree carries a row HEAD does not. **Displayed**
  (it is what the file says today, and hiding it would be its own lie) but
  **never adjudicated against a pin**. The split of responsibility, once: the
  DISPLAY reads the worktree, the PINS read HEAD.
- **MASKED** — HEAD carries a row the worktree does not. A *false green*: the
  defect is committed, in the repo, and the sweep says the repo is clean. The
  silent direction and therefore the worse one. **0 today, which is a
  measurement and not an absence of the class** — nothing had ever looked.

```bash
scripts/worktree_state.py            # the 36 arms (exit 1 on failure)
```

- ⚠ **ADVISORY, never a failure.** A sweep that hard-reds on an ordinary dirty
  worktree is a sweep nobody runs — the cries-wolf outcome this document names
  for `.benchmarks/` in the numbering gate. It rides the sweep's FINAL line in
  BOTH directions (the `DEFERRED` precedent) and is **SILENT** when nothing
  dirty meets that sweep's own population. MASKED is the exception, and it
  needs no separate teeth: the pins already count it, because they read HEAD.
- **Wired into EVERY sweep**, at the existing `population_verdict()` call
  site, each with the globs naming its OWN population — so the `*.lean` sweep
  stays silent while somebody edits Rust. Verified per-population on the landing
  run: the `*.rs` sweeps reported riir-ai (3), the `*.md` ones riir-ai (1),
  `numbering` katgpt-rs (1) + riir-ai (1), `subprocess_encoding` katgpt-rs (16)
  — its own in-flight edits — and `trap_sentinel` / `restatement` printed
  nothing at all. Landing it in one instrument and not the family is the
  failure mode recorded six times here already (Issues 777, 778, 793, 782, 783,
  789).
- ⛔ **And "every" was typed as a NUMBER first, which made it wrong within two
  hours.** The landing commit said *"all sixteen sweeps"*; a concurrent session
  then pushed `pipefail_discard_drift_sweep.py` and
  `toolchain_override_drift_sweep.py`, neither wired, and nothing noticed. So
  this is the **seventh** instance of the never-generalised shape and the first
  one repaired mechanically rather than by hand:
  `scripts/sweep_advisory_membership_gate.py` (docs-gate CHECK) reds on a
  tracked `*_drift_sweep.py` calling neither `sweep_advisory()` nor
  `worktree_advisory()`. Gated by **MEMBERSHIP**, because *a set is gateable
  where its cardinality is not* — a count is green on a swap. Exemptions carry
  a reason each and the file is deliberately EMPTY; a stale pin (its sweep
  wired since, or gone) reds too, so the file cannot only ever loosen.
  ⚠ It asserts the CALL, never that the patterns name the sweep's own
  population — a sweep passing `("*.lean",)` over a Rust walk is silent forever
  and reads as wired. That is a per-sweep read, the same limit
  `check_validation_gate` records about arm quality.
  ⛔ Its FIRST run reported `citation_drift_sweep` — the most thoroughly wired
  member, the only one with the row-level split — as UNWIRED, because the
  predicate named one of the mechanism's **two** entry points. A criterion that
  condemns the most careful caller is the criterion that is wrong.
- The row-level UNCOMMITTED/MASKED split is wired into `citation_drift_sweep.py`
  alone, because it is the one whose findings carry a `file:line` address and
  the one where the class was measured. `audit()` takes an injected
  `read(path) -> str | None` so the SAME classifier can be pointed at HEAD's
  blobs; `None` means "absent from the source being read" and must stay
  distinguishable from empty text.
- ⛔ **The row key is deliberately LINE-FREE** — `(document, kind, number)`.
  Any edit above a citation shifts its line, so a line-bearing key reports
  every row in an edited document as UNCOMMITTED *and* MASKED at once. The arm
  for it plants two citations behind a padding line and requires the key sets
  to be equal.
- ⛔ **An arm whose perturbation reds nothing certifies nothing, and this
  module caught one of its own.** `dirty_files` normalises `\` to `/`, and
  deleting that line reds NOTHING: `git status --porcelain` emits POSIX
  separators on every platform, measured on the Windows workstation where a
  naive reading expects the opposite. The arm asserts git's OUTPUT SHAPE — the
  premise — rather than pretending to test a defensive line. The normalisation
  that does bite is in `split_rows`, on the CALLER's path.
- ⛔ **A bare string is a footgun, not a convenience.** `("*.rs")` is not a
  tuple; iterating it yields characters, `fnmatch(rel, "*")` matches
  everything, and the advisory silently reports every dirty file in the repo.
  Caught in this module's own wiring commit, where **8 of 15** call sites had
  written it without the comma. The helper coerces and an arm pins both sides.
- Arm reach (`--include-all`): **19 of 23**, the three live survivors being
  `check=True` / `capture_output=True` on the fixture BUILDERS — flipping one
  makes the fixture wrong rather than a rule wrong, and the reason is written
  at the line.

## Before committing in a shared worktree — `scripts/staged_set_audit.py`

Several agent sessions write into one worktree routinely, and `git add -A`
from a repo root is indistinguishable, to git, from intent. Stage **named
files** (`git -C <repo> add <paths>`), never `-A` — and before a multi-file
commit, run:

```bash
scripts/staged_set_audit.py            # any repo: pass its path as $1
```

A **report, not a gate** (exit 0) — a refusing pre-commit hook was decided
against: every cheap signal has a legitimate-use false positive; a report
that is read beats a gate that is bypassed. Four signals: **mtime clusters**
(two clusters = two editing episodes; the older is probably not yours) ·
**also-dirty** (a staged path with unstaged changes = a concurrent editor) ·
**stale-vs-HEAD** (a file LACKING substantive lines the newest commit on its
path added — committing it reverts them) · **rustfmt round-trip** (`--fmt`:
identical to `rustfmt(HEAD)` provably carries zero content — the only
signal that yields a proof).

When you must commit into a file a sibling is editing, commit **your blob**:
build HEAD's version + your edit, `git hash-object -w`, then `git
update-index --cacheinfo`. Their hunks stay uncommitted; the worktree stays
coherent for them.

**Shared target dir:** a count-pinned or feature-switching gate run
concurrently with another cargo process in the same `target/` reports a
failing test that passes when run alone. Read the failure's **shape**:
`error: test failed` with **no `failures:` block and no `test … FAILED`
line** means the harness process *died* — nothing asserted anything.
Diagnose by running the compiled binary directly from
`target/<profile>/deps/` (no build lock needed; filter out the `#![cfg]`-gated
copies `--list` reports as 0 tests). A gate whose verdict the box can
invalidate should **refuse**, not warn — detect concurrent cargo by working
directory, not command line; a lock-based check cannot work (cargo releases
`target/<profile>/.cargo-lock` *before* running the test binaries).

## Lint healing — `cargo heal` before manual fixes (adopted 2026-08-24)

Mechanical clippy findings (format-arg inlining, `match_bool`, `map_or`,
capacity, `needless_return`, …) are fixed by the riir-clippy healer FIRST,
manual second:

```bash
cargo heal <paths>                                        # DRY RUN (the bare default — zero edits)
cargo heal --fix <paths>                                  # REAL fix: writes + compile-gates (fix_verify builds)
cargo heal --fix --write --verify <paths>                 # compile-gated apply
cargo heal --fix --write --verify --verify-args "--features <set>" <paths>  # gated code
```

- Global binary `cargo heal` = `~/.cargo/bin/cargo-heal` → the sibling
  `riir-clippy/target/release/cargo-heal` (built `--features
  fix_verify,clippy_verify`; rebuild after healer source changes). Missing
  sibling → fall back to manual fixes + `cargo clippy --fix`.
- `--verify` compiles baseline → applies → re-checks → auto-REVERTS breaking
  edits. Feature-gated code needs `--verify-args "--features <set>"` (a
  default-features check compiles gated files empty — a green check proves
  nothing about them).
- The healer is deliberately SILENT on documented divergence classes
  (comment-guarded matches, array-literal defaults, named-arg renames,
  nested macro args) — those stay manual; see the `cargo-heal` skill
  (`~/.agents/skills/cargo-heal/`) for the full table + discipline.
- `cargo clippy --fix` remains fine for one-off trivial fixes; the healer
  wins on batches (span-preserving, comment guards, compile gate,
  self-evolve memory) and was validated across the full katgpt-rs sweep
  (every surface, count-identical test validation, 2026-08-19).
- Observed misses / wrong suggestions → note in the session record; they feed
  riir-clippy's post-mining queue (usage-artifact improvement intake).

## Feature Flag Discipline

Every new primitive ships behind a feature flag (opt-in). Promotion to
default-on requires the GOAT gate to pass:

1. Implement behind `feature_name = []` (opt-in).
2. Write a benchmark proving the gain (latency, quality, or security).
3. Run the GOAT gate (G1 correctness, G2 perf, G3 no-regression, G4 alloc-free
   or equivalent).
4. If all gates pass AND the gain is **modelless** → promote to `default`.
5. If the gain requires riir-train (training) → keep opt-in, note the
   dependency, do NOT promote to default.

**Promotion requires modelless gain.** A perf gain on a biased/incorrect answer
is NOT a modelless gain — it's a speedup of a wrong result. The quality gate
(G1 or equivalent) must pass modellessly for the GOAT to hold.

**Lossy-surface promotion rule (riir-ai Issue 750 T3):** a **lossy** surface
(quantization, compression, any bit-changing transform) gates on
**deployed-path behavior — per-family, conditional retention**, not on
bit-identity or aggregate perplexity alone: aggregate perplexity can be flat
while family-conditional behavior flips. (Full rule + confirmations: HISTORY.md.)

**UQ-bearing primitive GOAT gate extension (the "Report the Floor" rule,
Research 322 / Plan 340):** any primitive claiming a probability
distribution, predictive interval, quantile, coverage guarantee, confidence
score, or calibrated uncertainty MUST benchmark against the
**conformal-naive floor** — `ConformalIntervalCalibrator<SeasonalNaiveForecaster>`
(Plan 340 with `m=1`, plain split conformal) — on CRPS / coverage / Winkler
score. Cannot beat the floor ⇒ the GOAT gate FAILS. Grandfathered UQ
primitives include the floor at their next re-gate. (History: HISTORY.md.)

## Substrate-First Gate (MANDATORY before implementing)

Before implementing ANY new System impl, trait, perception/cognition/emotion
pipeline, state management, spatial query, or vocabulary type, run the
`.agents/skills/substrate-first/SKILL.md` skill: (1) **vocabulary
translation** — grep 3+ name variants (concepts ship under operator names
like `GenericSpatialBelief`; a single-vocabulary grep returns ZERO hits even
when substrate fully exists); (2) **codebase grep** across `*.rs`, not just
`.plans`/`.docs`/`.issues`; (3) **architectural rule check** — domain
classification, two-brain model, sync boundary, bridge pattern; (4)
**consume vs build** — if substrate exists, consume it; if not, file an
issue in the right repo FIRST. Prevents the drift pattern of a parallel
system re-implementing shipped substrate under a different name (ThreatField
Issue 047; orchard/motivation riir-ai Issues 490/493).

Research workflow (paper classification, 7-repo routing, fusion-first
distillation, novelty + GOAT gates, modelless-unblock protocol §3.5):
`.agents/skills/research/SKILL.md`.

> **Repo count:** the **product/distillation set is 7** — `katgpt-rs` (public) +
> `riir-ai`, `riir-chain`, `riir-neuron-db`, `riir-train`, `riir-game-sdk`,
> `riir-dapps` (private). That is NOT the repo total: the
> workspace is **20 repos**, all of which carry a root `BOUNDARY.md`
> (add `riir-mmorpg-examples`, `riir-clippy`, `riir-viewbridge`,
> `riir-auth`, `katgpt-web`, `riir-dao`, `riir-deployer`,
> `riir-esp32`, `seal-game-editor`, `seal-remake`,
> `seal-online-remaster`, `riir-kat`, `riir-shader`).
>
> Read a count in prose as a claim, not a fact — and read a count that
> MATCHES as a claim too: a count is not a checksum over a set. Drift
> history: HISTORY.md.

## Numbering Discipline

Issue, plan, doc, benchmark, and research numbers are **monotonic and never
reused** — even after a file is removed per the noise-reduction rule. Before
creating a new `.issues/` file, read `.issues/.highwater`, use `value + 1` as
the number, and write the new value back. This prevents the number-recycling
collision documented in `.issues/121`. The same rule applies to `.plans/`,
`.docs/`, `.benchmarks/`, and `.research/` — never recycle a number that git
history shows was already allocated.

When two documents already share a number, Issue 724 T2's rule is that the one
with the most inbound mentions KEEPS it and the other moves — and the obvious
count is the wrong one. Measured on riir-ai's six duplicates (2026-09-05), the
by-NAME citations are 0-2 per side and TIED in four of the six pairs, while the
`Plan 175` form carries 35-98 each: **the weight is entirely in the citations
that do not say which document they mean.** `scripts/citation_weight.py <repo>
<dir> <number>` attributes those instead of counting them — a context window
scored against each candidate's distinctive filename tokens, awarded only on a
strict margin, with everything else printed as its own UNRESOLVED number and
never folded into a winner.

At ALLOCATION time the same class is caught earlier: `scripts/dual_allocation_gate.py`
(Issue 796) reds when this checkout and its upstream have both added numbered
documents since their merge base — classified structurally by filename stem:
same stem on both lines = TWIN (your own rebased work, exit-neutral, a fetch
resolves it), different stems = INDEPENDENT (two documents about to own one
number, exit 1, both sides' adding commits named). Measured basis (the probe,
`dual_allocation_fp_probe.py`): the deferral's feared shape — one side
allocating ahead — is green BY CONSTRUCTION (7202 one-sided pairs, zero
fires), while 39 real divergence incidents in 90 days split 31 TWIN / 8
INDEPENDENT. Reach limit: it sees divergences THIS box participates in at
fetch/push time; box-vs-box collisions on the wire are the merge-time wall's
(Issue 795's) jurisdiction.

⛔ **A collision where BOTH holders have CLOSED is the MAJORITY case, and the
instrument was blind to it** (Issue 795). A document closed under the
noise-reduction rule is deleted, so the pair leaves nothing on disk and reads as
"not a duplicate" — and every number this repo allocates is expected to end up
removed. `removed_by_number()` recovers them from `git log -M --diff-filter=D`
(`-M` is load-bearing: without rename detection a RENUMBERED document reports as
a deletion at its old number and the tool resurrects a collision somebody
already resolved). Issue 791 recorded **three** collisions; the same scan with
the recovery says **70**, over 1374 numbers, 9 of them at or above 700 and all 9
from one 57-commit divergence.

⚠ **Take the SCOPE from `scripts/numbering_floors.txt`, never from a walk of
the tree.** A first pass over every numbered directory found 122, and 52 of
those were `.benchmarks/`, where the leading number is the OWNING plan or issue
and a family per owner is the intended convention — an exclusion that file
records, measured, with the note that checking there *"would have been the
cries-wolf instrument AGENTS.md warns gets ignored."* A population derived from
the tree is not the population the gate governs.

The verdict is `numbering_gate.py` in the docs gate, in **two regimes**
(`scripts/number_collisions_expected.txt`): at or above `era_boundary = 700` a
**WALL pinned by MEMBERSHIP** with a reason per row — a count is green on a
swap, and the arms assert that case — and below it a **RATCHET**, counted and
never pinned, because those 61 are the pre-gate archive and Issue 785's rule
forbids ratcheting a bucket that means *unread*. The boundary is measured, not
round: the highest legacy collision is 575 and the lowest divergence one is 741.

⛔ **And do not renumber on a margin the instrument did not award.** Six of
the nine were adjudicated and deliberately left alone — leads of +1 to +5 with
21–53% UNRESOLVED, one an outright `TIE_FRACTION` tie and one where the tool
DECLINED (unresolved outnumbered decided). The pin file carries the margin per
row so the decision is re-readable. Renumbering on a 2-site lead with 47%
unresolved is the mistake `TIE_FRACTION`'s own docstring names: *pretending it
can arbitrate is how a coin flip gets recorded as a measurement.*

## Branch

`develop` is the working branch. Don't create feature branches; commit
directly on `develop` per the global rule.

## Models
- riir-train/data/gemma-2-2b-it-f16.gguf
- riir-train/data/MiniCPM5-1B-F16.gguf
