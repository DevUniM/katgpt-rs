# Issue 821 (2026-09-17) — Issue 815's marker never reached the sweep family: 8 sweeps red on 0 findings, and two live ratchet breaches sat behind them

**Status:** CLOSED 2026-09-17
**Severity:** a sweep that always reds is a sweep nobody runs — measured, twice now
**Owner:** this session

## The finding

Issue 815 added `DOCS_GATE_KNOWN_EXTRA` so a box carrying siblings the contract
does not claim could be READ. It landed in `skill_repo_set_gate.known_extra_state`
and in `sweep_population.population_verdict`, which is where every sweep gets
its final-line disclosure — and **not** in the per-repo pin loop those same
sweeps run six hundred lines earlier.

So on this box, with **both** documented markers set
(`DOCS_GATE_PARTIAL_CLONE=1` and `DOCS_GATE_KNOWN_EXTRA=seal-game-editor,
seal-online-remaster,seal-remake`), a sweep prints

    ✗ seal-game-editor  rs=305  cfg_sites=278  orphaned=0
          ✗ UNPINNED — add a row (or it can never red)
    ...
    ⚠ 3 known-extra repo(s) outside the contract — acknowledged by
      DOCS_GATE_KNOWN_EXTRA, not measured and not expected to be

The final line says the repos are not expected to be measured. The rows above
it demand a pin so that they can be.

## Measured, 2026-09-17 — with both markers set

| sweep | rc | why it reds |
|---|---|---|
| `orphaned_attr` | 1 | seal-* UNPINNED · **0 findings** |
| `percentile` | 1 | seal-* UNPINNED · **0 findings** |
| `markdown_fence` | 1 | seal-* UNPINNED · **0 findings** |
| `subprocess_encoding` | 1 | seal-* UNPINNED · **0 findings** |
| `trap_sentinel` | 1 | seal-* UNPINNED · **0 findings** |
| `platform_dead_code` | 1 | seal-* "a repo joined the population" · **0 findings** |
| `console_encoding` | 1 | seal-* UNPINNED **+ a real breach, below** |
| `instrument_reachability` | 1 | seal-* UNPINNED **+ a real breach, below** |
| `wasm32_surface` | 1 | seal-* UNPINNED + one NEW UNCOVERED row in an extra repo |

**Eight of nine red on repos where they found nothing.** And behind those reds,
two genuine ratchet breaches in a repo the contract *does* claim:

    console_encoding         riir-train  undefended 56 > pinned 53
    instrument_reachability  riir-train  unreachable 63 > pinned 61

Three new instruments that print a non-ASCII glyph and defend neither stream,
and two new scripts no root and no document names. Both are exactly what their
ratchets exist to catch. Both were invisible, because the reader who runs a
sweep and sees `✗` on three repos they were told to ignore stops reading.

⛔ **This is the second recorded instance of this precise failure.** Issue 793
found seven sweeps hard-redding on a known-partial box with
`DOCS_GATE_PARTIAL_CLONE=1` already set and every content assertion green, and
measured what was sitting behind them: *"the percentile sweep's Issue-777
findings, and four live citation drift rows."* The repair was
`sweep_population.py`, one shared mechanism. Issue 815 then added a second
marker and did not put it through that mechanism's other half.

## Why one shared helper and not 14 edits of the same idea

AGENTS.md, in the sentence this issue is an instance of: *"before fixing such a
class, grep the whole family and land the repair as one shared mechanism."*
Issue 820 wrote that down this morning and then fixed the marker in
`numbering_drift_sweep.py` alone — which is how the count got to 14.

## Tasks

- [x] **T1** — `sweep_population.pin_row_exempt(name)`: is this repo a declared
      known-extra? The acknowledged/stale split stays `population_verdict`'s,
      on the final line, because the loop only ever visits repos that are
      PRESENT — passing a visited repo is the acknowledged case by
      construction, and a helper that re-derives the split per row would be a
      second copy of it.
- [x] **T2** — the 14 uniform call sites + `toolchain_override_drift_sweep`'s
      `repo_flags()` (different shape, same rule) + fold
      `numbering_drift_sweep`'s Issue-820 copy onto the shared helper so the
      family is ONE shape.
- [x] **T3** — arms, in `sweep_population.selftest` where the rest of the
      marker's arms already live: exempt when declared, NOT exempt when
      undeclared (the wall must stay absolute for the next unregistered repo —
      the whole reason 815's marker takes NAMES rather than `=1`), and no
      marker at all exempts nobody.
- [x] **T4** — re-run the nine and record what the reds were hiding. The two
      riir-train breaches are **riir-train's to adjudicate**, not this issue's
      to repair; this issue owes making them VISIBLE.

## Not in scope

- **The two riir-train ratchet breaches.** Filed onward once visible. Read
  `instrument_reachability`'s standing note first: that repo's `scripts/` is
  almost entirely plan-scoped one-offs where the predicate OVER-CAPTURES, so
  63-vs-61 is a derivative question, not 63 repairs.
- **Whether the seal-* repos belong in the workspace.** Issue 815 recorded that
  as owner-owned and it still is. The marker makes the box readable; it does
  not make the box right.

## Landed

`sweep_population.pin_row_exempt(name)`, one definition, wired into **16**
sweeps: 13 uniform call sites, `toolchain_override`'s `repo_flags()` call site,
`platform_dead_code`'s set-difference, and `numbering`'s Issue-820 local copy
folded onto it.

Measured before → after, both markers set:

| | before | after |
|---|---|---|
| sweeps red | 9 of 14 | 4 of 14 |
| red on 0 findings | 8 | **0** |

The four still red are red for reasons that were **hidden behind the noise**:

    console_encoding         riir-train  undefended 56 > pinned 53
    instrument_reachability  riir-train  unreachable 63 > pinned 61
    cfg_gated                riir-ai     silent_now 2, load_bearing 1
    citation                 riir-ai     1 CROSS row

⚠ **`wasm32_surface` needed more than the pin row, and finding out why is the
generalisable part.** Its UNCOVERED membership check sits OUTSIDE the
`row is not None` branch, so excusing the pin row alone still produced a hard
finding about a repo the marker had just declared outside the contract. **An
acknowledged extra contributes no VERDICT, not merely no pin row.** The row is
still PRINTED — display reads the box, pins read the contract, which is Issue
797's split — and the membership file's other direction is untouched, so a
pinned row naming an extra repo still has to be removed deliberately.

## Two process notes, both of which cost time

⛔ **The mechanical 13-file edit was WRONG and crashed.** The flat guard
`if row is None and not pin_row_exempt(name):` sent the exempt case into an
`else:` branch that dereferences `row` — `TypeError: 'NoneType' object is not
subscriptable`. The correct shape nests the exemption INSIDE `if row is None:`
so the else-branch precondition is preserved. It failed loudly on the first
run, which is the good direction; a scripted edit across 13 files is worth a
`py_compile` sweep and one real execution before it is worth trusting.

⛔ **Python `write_text` flipped every file to CRLF**, twice, turning 2-line
changes into whole-file rewrites (`345 insertions, 345 deletions` on a 345-line
file). `git diff --numstat` after any scripted edit; write BYTES, or pass an
explicit LF newline argument.
