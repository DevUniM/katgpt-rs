# Issue 779 — 7 of 8 workstation drift sweeps hard-red on a partial-clone box, for the one reason that is not a finding

**Status:** OPEN

**Date:** 2026-09-14
**Source:** running the whole workstation sweep family from the Windows box
  after the Issue 777 walk repair. Every *content* assertion is green; the
  family still reports FAILED.

## The measurement

On this box (16 of 20 contract repos — a known partial clone, `4090`-class,
the Issue 765 posture the marker exists for), with
`DOCS_GATE_PARTIAL_CLONE=1` set:

| sweep | rc | why |
|---|---|---|
| `cfg_gated_drift_sweep` | 1 | 4 absent rows, nothing else |
| `citation_drift_sweep` | 1 | 4 absent rows **+** the gate cross-assert |
| `markdown_fence_drift_sweep` | 1 | 4 absent rows, nothing else |
| `numbering_drift_sweep` | 1 | 4 absent rows, nothing else |
| `percentile_drift_sweep` | 1 | 4 absent rows, nothing else |
| `required_features_drift_sweep` | 1 | 4 absent rows, nothing else |
| `trap_sentinel_drift_sweep` | 1 | 4 absent rows, nothing else |
| `platform_dead_code_drift_sweep` | **0** | honours the marker (Issue 775) |
| `docs_drift_sweep` · `cfg_row_implication_drift_sweep` · `restatement_drift_sweep` | 0 | no per-repo row for the absent four |

Seven sweeps carry this loop, **byte-identical, copy-pasted seven times**:

```python
    for name in sorted(set(pins) - <present>):
        bad = True
        print(f"✗ {name}: pinned but ABSENT from the derived walk — it was "
              f"retired (drop the row in that commit) or the walk went blind")
```

`platform_dead_code_drift_sweep.py` is the one that does it correctly, because
it was written after Issue 765 and consumes `partial_clone_state()`. Landed
once, never generalised — the third instance of that pattern in two days
(Issue 777's tracked walk, Issue 778's subprocess encoding), and by now the
lesson is that the repair is a SHARED mechanism, not a sweep of call sites.

## Why this is worth fixing rather than living with

A sweep that always reds is a sweep nobody runs, and its content assertions go
unread with it. That is not speculative here: the percentile sweep's genuine
findings under Issue 777 — a fabricated floor and a wrong-address defect — sat
behind four absent-row reds that had been firing on this box since the rows
were written.

The deferral is also strictly SAFER than the alternative somebody reaches for
under that pressure, which is to regenerate the pins on the partial box and
delete four live repos from the canonical set. That is exactly the failure
Issue 765 wrote the marker to prevent, and the raw remedy text these seven
sweeps print ("drop the row in that commit") invites it.

## Tasks

- [ ] T1 (P0) — `scripts/sweep_population.py`: the absent/unregistered verdict,
  ONE copy, lifted from `platform_dead_code_drift_sweep.main()`. Keeps the
  three-way split: **UNREGISTERED** (on disk, missing from `repo_set.txt` —
  genuine staleness, reds in EVERY posture, marker or not), **UNSEEN** (pinned
  or in the snapshot, not on this box — reds without the marker), **DEFERRED**
  (the same set, with the marker, reported loudly on the final line and never
  silently). The marker stays an explicit opt-in and is never auto-detected: a
  genuine removal whose pin update was forgotten is set-identical to a partial
  clone from the walk alone.
- [ ] T2 (P0) — The seven sweeps consume it. `platform_dead_code_drift_sweep`
  repoints at it too, or there are two copies of the rule again by the end of
  the commit that removed seven.
- [ ] T3 (P1) — `citation_drift_sweep.gate_says()` cannot read the gate's
  partial-clone output. `issue_citation_gate.py` prints `partial: N citations
  scanned in …` under the marker instead of `scanned N citations`, so the regex
  returns -1 and the sweep declares its own instrument untrustworthy — a
  correct refusal reached for the wrong reason, which reads as a second
  failure on top of the deferral. Teach it the DEFERRED shape, and keep the
  refusal for the case it is actually for.
- [ ] T4 (P1) — Self-test the helper in both postures, with the UNREGISTERED
  arm reddening under the marker. An arm whose perturbation reds nothing
  certifies nothing.

## Not in scope

Pinning the four absent repos (katgpt-web, riir-dao, riir-deployer,
riir-esp32). They are not on this box; a floor nobody measured certifies
nothing. Their rows are owed by the next full-checkout run, which is already
recorded against `platform_dead_code_drift_floors.txt`.
