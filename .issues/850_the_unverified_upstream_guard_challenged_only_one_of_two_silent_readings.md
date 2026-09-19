# Issue 850: the UNVERIFIED-upstream guard challenged only ONE of `behind_origin`'s two SILENT readings

⚠ **Filed as 849, renumbered to 850 before pushing — the SECOND number
collision of this session, and the two were caught by different instruments.**
The first (846) was caught by `dual_allocation_gate` at allocation time, which
is what that gate is for. This one it could NOT see: the sibling allocated 849,
closed it in the same commit and left the record in `HISTORY.md` with no file
on disk — the Issue-754 shape — so there was no second *document* to compare.
It surfaced only because a rebase brought `.issues/.highwater` back to 849
under a file already claiming it. Adjudicated by Issue 724 T2: the other side
is pushed and carries an inbound HISTORY record, this one was uncommitted.

**Status:** **RESOLVED** 2026-09-19 — both silent buckets are challenged now,
armed, and the arm is proven to red against the original code. T3 then observed
the line end to end and found the guard PRINTING a false statement about the
bucket T1 added; repaired, 9 new arms, 7 of them proven to red against it.
T2 answered NO on a measurement (250.2s serial / 50.2s at 8-way against a
0.04-40s sweep) and shipped `scripts/fetch_contract_repos.py` instead.

Found while chasing a red `shared_temp_path_drift_sweep`, by walking into the
exact failure Issue 798 and Issue 827 exist to prevent.

## The gap

`worktree_state.behind_origin()` has **four** answers and AGENTS.md documents
them as *"never pooled"*:

| reading | meaning | printed? |
|---|---|---|
| `None` | no upstream, or git could not answer | silent, claims nothing |
| `(0, 0)` | up to date | **SILENT** |
| `(n, 0)` | behind, but on nothing in this sweep's population | **SILENT** |
| `(n, k>0)` | behind on files this sweep reads | the STALE advisory |

Issue 827 T5 added the fetch-age guard so a *confident* silence has to rest on
something: a `(0, 0)` sitting on a ref nobody has refreshed in over 24h is
reported **UNVERIFIED UPSTREAM** rather than believed.

It was wired to `(0, 0)` **only**:

```python
elif beh == (0, 0):
    age = fetch_age_hours(path)
```

`(n, 0)` is the other silent reading, it rests on exactly the same
remote-tracking ref, and it is the **stronger** claim of the two — `(0, 0)`
says *I am not behind*, while `(n, 0)` says *I am behind, and I have read the
commits, and none of them touches what you are measuring*. Both halves of that
second sentence come from a ref that may be days old.

## What it cost, measured

`shared_temp_path_drift_sweep` reported **6 findings across 3 repos**
(mmorpg-editor 2>1, mmorpg-remake 3>1, mmorpg-remaster 1>0) with **no STALE
and no UNVERIFIED line for any of them**. Fetching those three showed them
**22, 9 and 3 commits behind**, and of the six findings:

- **4 were already FIXED upstream** — `editor_data_nav_missing`,
  `seal_core_filedb_test`, `seal_relay_mirror_front`,
  `seal_asset_explorer_idx_test`, every one already carrying
  `format!("…_{}", std::process::id())` on `origin/develop`;
- **2 were correct at their pins** — `TmpDirStore::new()` is a *production*
  API whose stable `<temp_dir>/seal-game-editor/` path is deliberate and
  already adjudicated (it is the reason mmorpg-editor's pin is 1, not 0), and
  `seal_quest_sim_front` is the single row mmorpg-remake's pin of 1 allows.

So the sweep's red was **entirely** a stale-checkout artifact, the class
Issue 798 names as *the mirror of MASKED — a committed FIX read dirty*, and
the advisory built to catch it said nothing.

⛔ **And it cost real work before it was understood.** Six "repairs" were
applied and committed across the three sibling repos before anyone fetched;
four were duplicates of upstream and one — the `TmpDirStore` row — would have
**undone a recorded adjudication** and changed a user-visible path. All three
commits were reset. Read that as the cries-wolf cost the sweep family exists
to avoid, paid in the one place the instrument was blind.

⚠ **What is NOT claimed:** that this gap is what silenced those three repos on
this box. The pre-fetch state was destroyed by the fetch that diagnosed it, so
the causal chain is **unmeasured**. The gap itself is read off the code and is
reproducible in a fixture, which is what the repair rests on.

## The repair

```python
elif beh is not None:      # (0, 0) AND (n, 0) — both silent, both on the ref
```

- `None` still claims nothing and is untouched.
- `(n, k>0)` still gets the STALE line and **not** a second one — the buckets
  stay unpooled, and the existing arm for that is unchanged.
- A **freshly**-fetched `(n, 0)` stays SILENT. That is the point of the
  bucket: an out-of-scope behind-ness is the banner nobody reads.

## The arm, and why it needed its own fixture

`worktree_state.py` selftest: **144 → 148 assertions**. The new arm builds its
OWN upstream/clone pair, and that is not tidiness — the first draft reused the
`(0, 0)` arms' fixture, where upstream has already moved an **in-scope** file,
so its precondition could not hold and it failed with `(2, 1)`. A fixture that
cannot express the state is the failure mode this repo records for benchmarks
one axis over.

Proven two-sided: with `elif beh == (0, 0)` planted back, the arm reds with
`… was SILENT … : []`; with the repair it greens.

## Tasks

- [x] **T1 — Challenge both silent readings, arm it, prove the arm reds.**
- [x] **T4 — `dual_allocation_gate` gained the COUNTER axis, because the
      renumber that produced this issue was a collision it could not see.**
      Both existing verdicts compare DOCUMENTS (`git log --diff-filter=A`),
      and a number allocated and CLOSED in one commit never has a file in any
      tree — the record goes to HISTORY.md. That is what a sibling did with
      849 while this checkout held `.issues/849_*.md`, and the gate printed
      `0 independent colliding number(s)`.

      The counter IS the missing document: both sides bumping `.highwater`
      past the merge-base value means both SPENT the overlapping range,
      `(base, min(mine, theirs)]`, file or no file. A one-sided bump — the
      ordinary case on every push — stays green by construction, and a
      MISSING base counter yields nothing rather than being read as 0, which
      would make every number in the other side's range look contested.

      Armed in BOTH halves: the arithmetic on every push with the git reader
      INJECTED (the extraction is the repair — without it the range logic is
      reachable only through a real fixture, i.e. only under the opt-in
      flag), and a real two-repo fixture under `--prove-fires` that builds
      the no-document shape and requires the row, with the one-sided bump as
      its negative side.
- [x] **T2 — ANSWERED: NO, and it is a MEASUREMENT, not a preference.**

      The task forbids answering by reflex, so the cost was measured over the
      17 contract repos on this box: **250.2s serial, 50.2s at 8-way
      parallelism, 0 failures** cold; **21.5s wall / 119.2s of work** warm.
      Against that, a sweep in this family costs **0.04–40s** and the whole
      32-check docs gate costs **~164s wall**. A per-sweep fetch is therefore
      **5–30x the cost of the thing it precedes**, paid ~19 times over a
      family run. That is decisive on its own and needed no design argument.

      The design half points the same way and is worth recording because it
      is the half that would still hold if the network were free:

      - A fetch **WRITES** remote-tracking refs in repos other sessions own.
        It cannot break a build (`refs/remotes` is neither HEAD nor the
        worktree — asserted, not assumed, by the new instrument's own arm),
        but it can move a concurrently-running sweep's verdict mid-run. That
        is Issue 797's class with the sweep as the **perpetrator**.
      - It makes a verdict depend on the network. This box has a recorded
        ssh-transport failure mode; a sweep that cannot answer offline is a
        sweep that stops being run.
      - A `--fetch` flag is not the repair either, exactly as the task warns:
        a flag nobody passes is not a repair.

      **Freshness is a property of the BOX at a moment, not of any one
      sweep.** So it is fetched ONCE per session and the sweeps stay
      observers that DISCLOSE — which, after T1 and T3, they now do
      correctly.

      ⛔ **And measuring it surfaced a defect in the REMEDY TEXT that is
      worth more than the cost answer.** The advisory said *"`git fetch` in
      the named repo before trusting it"* and named repos by their CONTRACT
      spelling — correctly, because `repo_alias`'s rule is that machine-local
      alias content must never reach stdout (run logs get pasted into tracked
      docs). On an aliased box those are directories that **DO NOT EXIST**:
      measured here, the advisory told the reader to fetch `mmorpg-editor`
      while the checkout is `seal-game-editor`. Both rules right, remedy
      unusable — so it now names the one command that resolves the codec
      itself.

      **Landed: `scripts/fetch_contract_repos.py`** (workstation, documented
      in AGENTS.md § worktree_state, reachability-gated).

      - `origin` **NAMED**, never a bare `git fetch`: riir-chain carries a
        second remote that is stale by design.
      - Population **delegated** to `skill_repo_set_gate.derive_repos`,
        opened through `repo_alias.disk()`. An eleventh private
        contract-repo walk is what `population_sync_gate` exists to catch.
      - Exit 1 only on a fetch FAILURE, never on "nothing moved", and the
        failure line says the honest thing: those repos' upstream readings
        still rest on an unrefreshed ref, so a red finding there is **not
        confirmed**.
      - A repo with no upstream is **reported, never guessed at** —
        `behind_origin`'s own rule; five workspace repos have none.
      - Arms assert the safety claim rather than stating it: after a fetch
        that provably advanced `refs/remotes`, **HEAD is unmoved and the
        upstream's new file is not in the worktree**.
      - ⚠ The per-repo `--timeout` is not garnish. While this task was being
        measured, `arm_reach_gate` **wedged on this box for twenty minutes**
        against a `git` child that never returned, at 3% CPU with the child
        visible in the process table; killing the child resumed the run.
        AGENTS.md already states that gate's watchdog *"reaches a pure-Python
        loop and NOT a blocking C call"* — this is that 10%, observed.
        Anything here that spawns git in a loop needs the bound at the SPAWN,
        because that is the only layer that has one. Filed separately.

- [x] **T3 — DONE, and the observation found a SECOND defect: the line the
      guard prints makes a FALSE statement about the bucket T1 added.**

      The task said to re-run the family after a day idle and check the line
      appears. That was the wrong instrument for the question: measured
      2026-09-19, **all 17 repos on this box are 0.2–9.7h fresh**, so the
      trigger is unreachable by waiting and the observation would have been
      deferred indefinitely. It was made by CONSTRUCTION instead — stub only
      the clock-reading seam (`fetch_age_hours`), run a REAL sweep, read its
      real stdout. That is this module's own `premise_arms` pattern: assert
      the thing that could actually change, rather than waiting for the world
      to produce it.

      **Reachable, confirmed end to end.** `trap_sentinel_drift_sweep`
      printed the line, on its FINAL line, naming all 17 repos, with
      **rc = 0** — advisory, never a failure, exactly as specified.

      ⛔ **And the line said this, of every repo:** *"17 repo(s) report 'up
      to date' from a remote-tracking ref last refreshed over 24h ago"*. For
      an `(n, 0)` repo that is FALSE, and it is false about the one fact the
      sweep has already read — it knows the repo is `n` commits behind,
      because that is what `(n, 0)` MEANS. T1 widened the trigger to both
      silent readings and left a sentence written for `(0, 0)` alone.

      A reader is then given the worst of both: told a repo is "up to date"
      (wrong, and it is the reassuring direction) while being told not to
      trust it. The module's own rule is that the four readings are **never
      pooled**; T1 honoured that in the TRIGGER and the DISPLAY pooled them
      one layer down — the `heading_style_blind` shape, where the meter was
      anchored to the same thing the rule was.

      **Repair:** the bucket rides along. `unverified` carries
      `(age, commits_behind)` rather than a bare age, and each repo renders
      its own reading on the one line:

          ⚠ UNVERIFIED UPSTREAM: 17 repo(s) rest a SILENT verdict on a
          remote-tracking ref last refreshed over 24h ago — katgpt-rs (38h,
          reads 'up to date'), mmorpg-editor (38h, reads '3 behind, none in
          this population'), …

      ONE line, not two — splitting a class across lines is the banner nobody
      reads, and an arm pins that.

      ⚠ **Why the existing arm could not catch it: it asserted PRESENCE, not
      CONTENT.** Every arm in this bucket tested `"UNVERIFIED UPSTREAM" in
      ln`, which is true of a line saying anything at all. `worktree_state`
      selftest **148 → 157**, and the nine are two-sided: replayed against
      the pre-repair renderer, **7 of the 9 red** (the other two are the
      pre-existing never-fetched/hours arms, re-typed for the tuple), and 0
      red at HEAD. Both directions of the split are armed — a `(0, 0)` row
      must still SAY 'up to date', or the repair blurs them the other way.

      ⚠ Cosmetic, NOT repaired and recorded rather than fixed silently: on
      the population-FAILURE print path the advisory line comes out as
      `⚠ ⚠ UNVERIFIED…` (the failure printer prepends its own glyph). It is
      per-sweep display, not this module, and it appears only on a run that
      is already red.

