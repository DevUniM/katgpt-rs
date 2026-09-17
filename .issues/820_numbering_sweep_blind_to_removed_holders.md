# Issue 820 (2026-09-17) — the numbering sweep is blind to Issue 795's class, so 15 repos read `dup=0` over 113 collisions

**Status:** CLOSED 2026-09-17
**Severity:** the sweep prints a confident green over the MAJORITY case
**Owner:** this session

## The finding

`scripts/numbering_gate.py` grew `historical_collisions()` at Issue 795,
against a measured reason written into its own docstring:

> A document closed under the noise-reduction rule is DELETED, so a double
> allocation where both sides have closed leaves NOTHING on disk and reads as
> clean — and every number this repo allocates is expected to end up removed.
> Measured 2026-09-15: 70 collisions in scope, 9 of them from one 57-commit
> divergence, and this gate had never reported one.

`scripts/numbering_drift_sweep.py` — **the cross-repo verdict half of that
exact gate** — never got it. It calls `ng.tracked_paths()` and `ng.scan()`,
both of which read the WORKTREE, and reports `dup=` over what is on disk. So
the class Issue 795 exists for is measured in **one repo of sixteen**, and the
sweep's summary line says `0 tracked duplicate(s)` for the other fifteen.

This is the eighth recorded instance of the never-generalised shape
(Issues 777, 778, 793, 782, 783, 789, 797) and the second one where the
un-generalised half is the *verdict for everybody else*.

## Measured, 2026-09-17

`numbering_gate.historical_collisions(repo, SERIAL_DIRS)` run over the derived
contract population, unchanged, on this box:

| repo | collisions | ≥ 700 | numbers walked | time |
|---|---:|---:|---:|---:|
| katgpt-rs | 70 | 9 | 1407 | 0.7s |
| riir-ai | **71** | **3** | 1435 | 0.4s |
| riir-train | 11 | 0 | 553 | 0.5s |
| seal-game-editor | 10 | 0 | 337 | 0.4s |
| riir-chain | 6 | 0 | 225 | 0.3s |
| seal-online-remaster | 5 | 0 | 72 | 0.1s |
| riir-mmorpg-examples | 4 | 0 | 135 | 0.2s |
| riir-clippy | 3 | 0 | 443 | 0.2s |
| riir-neuron-db | 3 | 0 | 111 | 0.2s |
| (7 others) | 0 | 0 | 196 | — |
| **TOTAL** | **183** | **12** | **4914** | **3.7s** |

katgpt-rs's 70 are the ones its own gate already pins. **113 are in repos the
sweep covers and calls clean**, and **3 of those are at or above the era
boundary** — live ambiguities in prose people are writing today, in riir-ai:

    .issues/702  702_l2_normalize_suite_order_numeric_divergence
                 702_persistent_grid_stride_gemv
    .issues/753  753_qwen38_cudarc_kv_dtype_f32_lever
                 753_webrtc_tier_gate_too_narrow_for_whip_client_server
    .issues/959  959_feature_gap_dead_code_consumer_sweep
                 959_heart_icon_text2d_raster_hierarchy_traps

⚠ A prior session's hand-off recorded riir-ai as carrying "3 unpinned
historical numbering collisions". That figure was the **tracked-only** view
arrived at by eye; the instrument says **71**. The hand count was not wrong
about the three that matter — it was wrong about the population, which is the
reason to have the instrument point at every repo instead.

**3.7s for the whole workspace.** There was never a cost argument for the
omission either; it is a step that was skipped, not a judgement that was made.

## Tasks

- [x] **T1** — `audit()` gains a `hist` class and the `n_numbers` population
      that produced it, from `ng.historical_collisions` **imported, not
      re-derived** (the `-M` rename exclusion is subtle enough that a second
      copy is a second thing to get wrong — Issue 755).
- [x] **T2** — two new columns in `numbering_drift_floors.txt`, and they must
      fail differently:
      - `max_hist` — a **RATCHET at the measured count**, the existing
        `max_dup` / `max_resets` doctrine. Not a wall: resolving one is a
        citation-weight arbitration (Issue 724 T2), 113 of them are in repos
        this session does not own, and a pin of 0 would red on landing and be
        ignored — the cries-wolf failure `docs_gate.sh`'s preamble records.
        Not a membership set either: the gate's ≥700 wall needs a reason per
        row, and 15 repos' worth of invented reasons is a backlog wearing a
        pin (Issue 785).
      - `min_numbers` — a **FLOOR on the HISTORY walk**, which is a genuinely
        different instrument from `min_files`. `min_files` counts tracked
        files on disk; `min_numbers` counts distinct numbers recovered from
        `git log -M --diff-filter=D` **plus** disk. A `git log` regression
        leaves `min_files` untouched and takes `n_numbers` down to the on-disk
        count, and every ceiling then passes green over a blind instrument.
- [x] **T3** — katgpt-rs's row does not RESTATE its gate. The sweep imports
      the same function, so a count comparison would be true by construction —
      *a pin that restates its own input cannot fail* (the Layer 2c rule). It
      asserts instead that the **gate's own verdict** on those rows is clean:
      `collision_verdict(rows, *parse_collision_pins(...))` must return no
      failures, so a stale membership pin or a legacy ratchet drifting in
      `number_collisions_expected.txt` reds the sweep too.
- [x] **T4** — arms. The existing `selftest()` pins the scope split and the row
      parser; extend it over the new column's own arithmetic, which no
      classifier reaches (Issue 775's rule): the ratchet in BOTH directions
      (over → fail, under → "re-pin DOWN" note), the walk floor firing, and a
      reasonless/short row being REFUSED by the widened parser.

## Not in scope

- **Resolving any of the 113.** Each is an Issue 724 T2 citation-weight
  arbitration over a corpus in a repo another session owns. The ratchet makes
  the standing backlog visible and reds the next one; that is the repair this
  issue owes.
- **riir-ai's 3 above-boundary rows.** They are real and they are riir-ai's to
  adjudicate. Recorded here so the number is written down somewhere; the
  ratchet is what keeps them from growing to 4.
- **A per-push gate in riir-ai.** riir-ai has no `docs_gate.sh` CHECKS array
  (`check_validation_gate.py`'s own measurement, Issue 789 T4). The workstation
  sweep is the right cadence.

## Landed

Sweep line is now `files= nums= dup= hist= stale= malformed= resets= unbumped=`;
first green run with the class measured workspace-wide reports **0 tracked
duplicates against 184 historical collisions over 16 repos**. (184, not the
183 this issue was filed on: a concurrent session allocated `.issues/819` the
same day — see below.)

**T5, unplanned — a live above-boundary collision, found by running the gate
this issue's work made me run.** `numbering_gate.py` was RED on `develop` and
nothing had noticed: two sessions allocated 819 off one counter value. Hand
census 10 sites / 0% UNRESOLVED, splitting **7 to the sigmoid prior-logit
forecast issue** (`.research/566` x5, `.research/258`, `.research/392`) against
**3 to the x86_64 lint lane** (`AGENTS.md` x2, `HISTORY.md` x1); citation_weight
agreed 6-3. The sigmoid issue KEEPS 819 under the Issue 724 T2 rule.
- ⚠ The margin was hand-checked because `lane` is a distinctive token of the
  winning file and AGENTS.md's Layer 2c prose is about a lint LANE — the exact
  shape that would hand the loser's own sites to the winner. It did not.
- The loser is CLOSED and REMOVED, so there is no file to `git mv` and the `-M`
  rename exclusion has nothing to exclude: **this pair is permanent in the
  recovery walk.** Repair is the pin plus a three-site disambiguation in the
  losing prose (Issue 794's rule), not a renumber.

**T6, unplanned — Issue 815's marker did not reach the sweeps.**
`DOCS_GATE_KNOWN_EXTRA` was honoured by `population_verdict` and not by the
per-repo pin loop, so a box carrying acknowledged extras printed "not measured
and not expected to be" on its final line while reddening those same three
repos for having no pin row. Excused by NAME now, both directions asserted.

**T7, unplanned — riir-clippy's `.research` allocator was stale at 176 with
177 on disk**, so the next allocation was *guaranteed* to collide. Confirmed
against origin first (Issue 798 — this box was 7 behind and the defect was
upstream too). Repaired at riir-clippy `672ba8a8`.

## Verification addendum (2026-09-17) — the floor was argued, then EXECUTED

Prompted by katgpt-rs-9a's Issue 823 finding: `heading_style_blind` printed
`0/0 records read` — a **perfect** score — when its own regex went blind. The
generalisable question they posed is worth applying to every triage quantity
here: *what does this print when it breaks?*

T2's `min_numbers` was **argued** ("a git-log regression leaves `min_files`
untouched and collapses `n_numbers` to the on-disk count") and never run. The
two `selftest` arms pin the mechanism on a synthetic fixture — that recovery
WIDENS the population, and that a collapsed population trips the ceiling — but
neither can tell you whether the **real** pins are tight enough that a real
blinding actually crosses them. Arms use invented numbers.

Executed by blinding `citation_weight.removed_by_number` exactly as a failing
`git log -M --diff-filter=D` does today (it returns `{}` on error), across the
derived population:

| repo | nums | blinded | `min_numbers` | hist | blinded | fires? |
|---|---:|---:|---:|---:|---:|---|
| katgpt-rs | 1412 | 1047 | 1200 | 71 | 0 | ✓ |
| riir-ai | 1436 | 678 | 1200 | 71 | 0 | ✓ |
| riir-chain | 225 | 80 | 180 | 6 | 0 | ✓ |
| riir-clippy | 444 | 332 | 350 | 3 | 0 | ✓ |
| riir-dapps | 92 | 44 | 70 | 0 | 0 | ✓ |
| riir-game-sdk | 42 | 9 | 33 | 0 | 0 | ✓ |
| riir-mmorpg-examples | 135 | 32 | 108 | 4 | 0 | ✓ |
| riir-neuron-db | 111 | 52 | 88 | 3 | 0 | ✓ |
| riir-shader | 23 | 5 | 18 | 0 | 0 | ✓ |
| riir-train | 553 | 372 | 440 | 11 | 0 | ✓ |
| riir-viewbridge | 8 | 0 | 6 | 0 | 0 | ✓ |

**All 184 collisions vanish under the blinding and not one repo reports a green
zero** — every non-zero floor reds first. `riir-auth` and `riir-kat` carry
`min_numbers 0` because they have 3 and 0 numbers respectively; there is
genuinely nothing to floor there, which is a disclosed gap rather than a
silent one.

⚠ Deliberately NOT landed as a tracked script. It is a one-shot validation of a
frozen design argument — the `--prove-fires` shape — and a tracked
`scripts/*.py` that no root names is the `instrument_reachability_gate` finding
one level down. The durable artifacts are the floor and this table.

## What this does NOT claim

- The 113 sibling collisions are **not** adjudicated. The ratchet makes them
  visible and reds the 114th; each one is an Issue 724 T2 arbitration in a
  repo another session owns.
- Seven repos are absent from this box and their two new columns are
  **UNMEASURED**, pinned `0 0` and saying so on the row. `max_hist = 0` will
  red for any of them that has collisions on the first canonical-workstation
  run — deliberately, because a ceiling invented to be comfortable is a ceiling
  that never fires. Re-pin all seven from one full-checkout run.
