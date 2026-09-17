# Issue 825 (2026-09-18) — Issue 798's STALE advisory watches the repo a sweep READS; the citation oracle's authority comes from the repos it CONSULTS, and a stale one reds a third repo over four correct citations

**Status:** OPEN — measured, with the false red standing in `riir-shader` at
the time of filing. No pin was added: absorbing this into a ratchet is the
exact repair the finding argues against.

## The symptom

`citation_drift_sweep.py` went from PASS to FAIL within two hours, on a repo
nobody had touched in that window:

```
✗ riir-shader   docs=2 cites=43  cross=4  over 2  in_local_range=0  orphan=0
    cross: HISTORY.md:5   Plan 226  -> katgpt-rs/riir-ai
           [⛔MISATTRIBUTED: names seal-game-editor, which does NOT own 226]
    cross: HISTORY.md:14  Issue 164 -> katgpt-rs
           [⛔MISLEADING: the only crate in the window is seal-game-editor,
            which does NOT own 164]
    cross: HISTORY.md:16  Plan 226  -> katgpt-rs/riir-ai   [⛔MISATTRIBUTED]
    cross: HISTORY.md:16  Issue 164 -> katgpt-rs           [⛔MISLEADING]
    ✗ CROSS 4 > pinned 0
```

**All four citations are CORRECT.** `seal-game-editor` owns both numbers:

```
$ git -C ../seal-game-editor fetch origin
   bfa20ad3..18a1498f  develop -> origin/develop
$ git -C ../seal-game-editor rev-list --left-right --count HEAD...origin/develop
0	260
$ git -C ../seal-game-editor ls-tree -r --name-only origin/develop | grep -E '226|16[45]'
.issues/164_per_model_shader_assignment.md
.issues/165_the_canvas_water_becomes_the_gamefx_graph_water.md
.plans/226_model_shader_assignment.md
```

The checkout was **260 commits behind origin** and the allocations landed
upstream in that gap. The sweep asked a stale repo whether it owned a number,
it truthfully said no, and a **third** repo went red.

## Why this is NOT Issue 798, and the difference is the whole finding

Issue 798 wired `behind_origin()` into all 19 sweeps: if the repo a sweep is
**reading for findings** is behind its upstream on commits touching that
sweep's own population, the run prints a STALE advisory. That is the right
mechanism and it fires correctly — the same night, the pipefail sweep printed
`⚠ STALE: … seal-remake (65 behind, 4 in scope)`.

It cannot fire here, and not because of a wiring miss:

- The finding is in **riir-shader**, which is **current**. The advisory reads
  the population of the repo being audited, and riir-shader's population is
  clean.
- The stale repo, **seal-game-editor**, contributes **no rows at all**. It is
  consulted only as an **ORACLE** — `allocated()` asking "does this repo own
  this number?" — and no advisory in the family watches the repos a verdict is
  *adjudicated against*.

So the reader gets a hard red, four ⛔ labels, and **no pointer whatsoever** to
the actual cause, which lives in a repo the output never names as suspect.
Issue 798's own framing applies one level up: it is the **mirror of MASKED**
(a committed fix read dirty), except the staleness is in a *different repo*
than the one being blamed.

⛔ **This is Issue 754's sentence at workspace scale**, and that sentence is
already in AGENTS.md: *"A census is exhaustive over ROWS, not over the ORACLE
it checks them against — so never quote an error rate without naming the
instrument the sample was adjudicated against."* 754 fixed one oracle's
blindness to removed-without-commit documents. The oracle's **freshness** is
the same axis and was never given a verdict.

## The damage is in what the red invites

Both obvious repairs make things worse, and neither is discoverable as wrong
from the sweep's output:

1. **Edit riir-shader's prose.** The rows say `seal-game-editor Plan 226` —
   already the qualified form AGENTS.md prescribes. "Repairing" a correct
   citation to satisfy a stale oracle corrupts a correct record, and the next
   fetch makes the edit wrong in the other direction.
2. **Ratchet `citation_drift_floors.txt`.** riir-shader is pinned at
   `cross = 0`. Bumping it to 4 pins four *correct* citations as permanent
   known-bad and blinds the wall to a genuinely unfollowable fifth. This is
   the "a pin file re-typed after every run is a diary, not a wall" shape —
   reached, for the third time in this repo's history, by a stale input rather
   than by a real regression (Issue 823's `max_in_local_range` was the last).

## Second axis, and it is independent — the oracle has authority over a repo the contract does not claim

`seal-game-editor` is a **known-extra** repo: present on this box, not in
`repo_set.txt`, acknowledged by `DOCS_GATE_KNOWN_EXTRA` (Issue 815). That
marker excuses a known-extra repo from *supplying its own pin rows*. It does
nothing about the repo being **consulted as an oracle**, and so:

- a repo whose numbering the contract does not govern,
- whose checkout freshness is nobody's contractual responsibility,
- decides whether a **contract** repo's citation is followable, and can hard-red
  it.

⚠ This is a genuine open question, not obviously a defect: riir-shader really
does cite seal-game-editor, and refusing to adjudicate would simply move those
four rows into an UNDECIDED bucket. Recorded so the choice is made rather than
inherited. It is also the same asymmetry Issue 815 already names — the marker
takes NAMES rather than `=1` precisely so it stays loud for the unexamined
case — and "consulted as an oracle" is an unexamined case it does not cover.

## ⛔ Addendum, same session — the red is GONE, and not because anything was fixed

After the diagnostic `git fetch origin` above, `citation_drift_sweep.py` exits
**0** and riir-shader's row is clean. **The seal-game-editor WORKTREE never
moved** — still `bfa20ad3`, still 260 behind:

```
$ git -C ../seal-game-editor rev-list --left-right --count HEAD...origin/develop
0	260
```

So `allocated()` resolves through **refs**, not the checked-out tree, and a
fetch in one repo silently changed a verdict in a **third**. Two consequences,
and both make the tasks below sharper rather than optional:

- **The cure is the thing T2 forbids.** The only action taken was a fetch, and
  the wall went green. Anyone hitting this red and running `git fetch` in the
  named repo will see it clear and reasonably conclude the sweep was noise.
  The gap is untouched: the next oracle repo that ages past a citation
  reproduces it exactly, and the greenness here is an artifact of my having
  gone looking.
- ⛔ **The staleness detector's own input is stale by the same mechanism.**
  `behind_origin()` compares HEAD to a **local remote-tracking ref**, which is
  only as fresh as the last fetch. Before the fetch, seal-game-editor reported
  **0 behind / 0 ahead** — the advisory was silent *and wrong* — with its last
  fetch dated Sep 16 12:42. After, the numbering sweep prints
  `⚠ STALE: … seal-game-editor (260 behind, 53 in scope)`.

  A staleness detector that never fetches does not measure staleness; it
  measures *staleness known as of the last fetch*, and it reports the
  reassuring answer when it knows least. That is the same shape as this repo's
  blindness floors — an instrument whose failure mode is a confident zero —
  and it has no floor. The honest verdict for "no fetch within N" is
  **UNKNOWN**, never `(0, 0)`, which the helper already has a slot for: it
  returns `None` rather than guessing when there is no upstream.

⚠ This does NOT argue for auto-fetching (T2's ⛔ stands, for its own reason).
It argues that `(0, 0)` and "last fetch was two days ago" must not print the
same thing. The fetch TIME is available locally — `.git/FETCH_HEAD` mtime —
with no network call at all.

## Tasks

- [ ] **T1 — the oracle repos are part of the claim.** When a CROSS row's
      verdict turns on `allocated()` in some other repo, that repo's
      `behind_origin()` state belongs on the output beside the ⛔ label —
      per-row, not as a banner, since a run may consult a dozen repos of which
      one is stale. The existing `worktree_state.behind_origin()` already
      answers it and already returns `None` rather than guessing when there is
      no upstream (five workspace repos have none), so the mechanism is
      present and only the call site is missing.
- [ ] **T2 — a stale oracle must not produce a ⛔ label at all.** Printing the
      staleness next to a wrong verdict is not enough: the verdict is
      **wrong**, and the wall counts it. A CROSS row whose named repo is
      behind its upstream on commits touching that repo's numbered directories
      should land in an UNDECIDED bucket — *never clean, never counted* —
      exactly as `IN-LOCAL-RANGE` and `UNRESOLVED` already do elsewhere in
      this family. The ceiling then cannot be breached by another repo's
      fetch schedule.
      ⛔ Do NOT resolve this by auto-fetching. A sweep that mutates other
      repos' refs to make its own verdict true is a sweep with a side effect,
      and on a box with five concurrent sessions it is a race.
- [ ] **T3 — arms, and they must be two-sided.** A fixture pair of throwaway
      repos where the cited number exists only on `origin/<branch>` and not in
      the worktree: the row must NOT be labelled ⛔ and must NOT be counted;
      with the same number present in the worktree it must be clean; absent
      from both, it must still red. The middle arm is the one this issue
      exists for and the one a naive fix will skip.
### T5's hole is MEASURED, and it is live right now

Fetch age vs reported behind-ness, every contract repo on this box, 2026-09-18
(`stat .git/FETCH_HEAD` — no network):

| repo | last fetch | reports |
|---|---|---|
| riir-viewbridge | **60h** | `behind=0` |
| seal-online-remaster | 12h | `behind=0` |
| seal-remake | 12h | `behind=65` |
| seal-game-editor | 0h *(I fetched)* | `behind=260` |
| the other 12 | 1–2h | `behind=0` |

**riir-viewbridge's `behind=0` rests on a fetch from two and a half days ago**
— it is not a measurement of anything, and no output distinguishes it from the
twelve repos whose zeros are an hour old and trustworthy. That is the whole
defect, with a name attached.

And the class is not hypothetical here: **before tonight's fetch,
seal-game-editor was in exactly that bucket** — last fetch Sep 16 12:42,
roughly 36 hours stale, reporting `0 behind / 0 ahead` while hiding the 260
commits that produced this issue's false red. The only reason it now reads
honestly is that somebody went looking.

- [ ] **T5 — `(0, 0)` must not mean "not measured".** `behind_origin()` reads a
      remote-tracking ref whose own freshness it never reports, so a repo last
      fetched days ago reads *up to date*. Stat `.git/FETCH_HEAD` (no network)
      and return a distinct UNKNOWN-ish answer beyond some age, printed the way
      `None` already is. The arm is a fixture repo with a backdated
      `FETCH_HEAD` and an upstream ref that has moved: today it prints silence,
      and it must not.
      ⚠ Also the reason this issue's own red "fixed itself" — see the addendum.

- [ ] **T4 — decide the known-extra oracle question** (the second axis). Owner
      call: either known-extra repos are legitimate oracles (status quo, now
      documented) or a citation naming one is UNDECIDED by construction.
      ⚠ Not folded into T2 — T2 is about *freshness* and would be right even
      if every repo were in the contract.

## Not in scope

- Repairing riir-shader's four rows. They are correct; the instrument is
  wrong. Nothing to repair.
- Fetching seal-game-editor into its worktree. The fetch performed here
  updated remote refs only (worktree untouched, still 260 behind), which is
  what made the measurement possible without disturbing whoever owns that
  checkout.
- riir-clippy's `.plans/.highwater` staleness, found on the same run and
  repaired at riir-clippy `9f2f4078` — an unrelated, genuine defect.

## Measured basis

2026-09-18, this box. `citation_drift_sweep.py` red on riir-shader only;
katgpt-rs, riir-ai and the other 13 contract repos within their pins. The four
rows entered riir-shader's `HISTORY.md` on 2026-09-17 via commits `3d7e213`,
`5956121` and `2db6352` — correct when written, red because a *different*
repo's checkout aged.
