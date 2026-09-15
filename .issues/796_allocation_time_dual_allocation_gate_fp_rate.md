# Issue 796 — the allocation-time dual-allocation gate: measure the FP rate, then build or bury

**Filed:** 2026-09-15 · **Status:** RESOLVED · **Branch:** develop

## Premise

Issue 791 T3 and Issue 795 both DEFERRED the allocation-time gate — a check that
reds when a commit allocates a number its remote parent already allocated — on
the same unmeasured quantity: **its false-positive rate**. The stated fear: "a
long-lived branch legitimately allocates ahead of its remote" (this repo's own
divergence was 57 commits). The merge-time wall (795) catches the collision
late but not silent; an allocation-time gate would catch it while both sides
are still diverging, when the fix is one `git fetch` instead of an
adjudication.

A deferral on an unmeasured rate is not a decision — it is a measurement task.
This issue takes the measurement, then either builds the gate (rate ~0) or
records the number and keeps the gate buried (rate material).

## The measurement

For each historical divergence point, the gate's would-be verdict is computed
from data git already retains:

- `L` = numbers ADDED under the numbered dirs in `merge_base..local_tip`
- `R` = numbers ADDED under the numbered dirs in `merge_base..remote_tip`
- RED iff `L ∩ R ≠ ∅` (both sides allocated since the divergence)

Historical `(local_tip, remote_tip)` pairs are reconstructed from the reflogs,
sampled at the UNION of both timelines' entry timestamps — a fetch moves the
remote-tracking ref WITHOUT moving HEAD, so local-tip-only sampling misses
the divergence-discovery moment (measured: the first cut evaluated 48 green
katgpt-rs pairs and never saw the RED it was built for). Reflog retention
(~90 d) bounds the lookback honestly; the evaluated-pair count is the
blindness floor and a zero-pair run refuses rather than printing a green
zero.

A RED is a TRUE POSITIVE iff the intersection numbers are genuinely
double-allocated in the record (the 791/795 census is the oracle for this
repo's recent history); a RED whose intersection is a renumber artifact
(`-M` undetected), a cherry-pick, or a same-session push is a FALSE POSITIVE.

## Tasks

- [x] T1 — `scripts/dual_allocation_fp_probe.py`: the probe. Pure git
  archaeology, read-only, no cargo. Runs across the contract repos that have
  an upstream reflog; prints per-repo paired divergence points, REDs, and the
  classification basis for each RED.
- [x] T2 — run it workspace-wide, record the measured rate in this file.
- [x] T3 — verdict: the naive gate (RED on any `L ∩ R ≠ ∅`) is REFUTED as a
  hard gate and CONFIRMED as a classified one — see Status for the numbers.
  `scripts/dual_allocation_gate.py` implements the classified verdict.
- [x] T4 — docs: AGENTS.md pointer (instrument reachability) + HISTORY row at
  landing.

## Status

**MEASURED 2026-09-15, 18 repos, ~90 d of reflog (T2): 634 divergent
(live_tip, upstream_tip) pair-instants evaluated; 7202 one-sided pairs (the
feared long-lived-branch shape — green BY CONSTRUCTION, the intersection is
empty whenever only one side allocated since the merge base); 164 RED
pair-instants.** Deduped by (repo, colliding numbers): **39 distinct
incidents — 31 TWIN, 8 INDEPENDENT.**

The classification is structural, not textual: a colliding number is TWIN if
the same filename STEM was added on both sides (the same document, carried on
two post-rebase/cherry-pick lines of history — the subject test MISLABELS
these, measured: seal-remake `2` flips to TWIN under stems, its twin commits
have different subjects); INDEPENDENT if the stems differ (two distinct
documents claiming one number — the class 791/795 exist for). The 8
INDEPENDENT, all stem-verified: riir-ai 722/780/935, riir-chain 30+72/34,
riir-clippy 79/83, seal-game-editor 192–195 (the bevy-branch plan family).

**Verdict (T3): the deferral's fear is measured MOOT and its caution measured
RIGHT, in different halves.** The FP-fear shape (one side allocating ahead)
never fires — it is structurally green. But a naive hard gate on `L ∩ R ≠ ∅`
cries wolf 31/39 of the time on the TWIN class (a divergence persisting
across reflog moves re-fires every sample: one incident contributed 43 pair-
REDs). So the gate is built CLASSIFIED: TWIN rows annotate (exit-neutral —
they are your own rebased line, fetch resolves them), INDEPENDENT rows RED.
Fixture-proven in both directions: the constructed two-session collision
REDs with both sides' adding commits named; the probe's first cut was caught
VOID by that same fixture (a pathspec bug made every measurement the empty
set — 105 green pairs that measured nothing) and repaired before any rate was
recorded. Reach limit, recorded because it binds every single-box instrument:
the 791 divergence itself is NOT reconstructible from this box's reflogs — it
lived on the wire between boxes, and a box only ever pairs its own tip
against the last fetched remote tip. The gate catches the divergences the
running box participates in, at fetch/push time; box-vs-box collisions that
never touch this box's worktree are the merge-time wall's (795's) jurisdiction.
Commit: see the HISTORY row "Issue 796".
