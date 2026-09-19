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
armed, and the arm is proven to red against the original code.

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
- [ ] **T2 — Should a sweep FETCH?** It deliberately does not: a sweep is a
      read-only verdict and fetching 17 siblings is a network round trip per
      run, on a box where other sessions own those checkouts. But the advisory
      is only as good as the last fetch, and this incident is the second
      recorded time a stale ref produced a false red (Issue 827 was the
      first). ⚠ **Do not answer by reflex** — an `--fetch` flag nobody passes
      is not a repair, and an automatic fetch changes a sweep from an observer
      into a writer of other repos' refs.
- [ ] **T3 — The three seal repos were never named by ANY advisory line.**
      After T1 they would be, if their fetch was stale. Re-run the family
      after leaving this box alone for a day and check that the line appears
      — an advisory whose trigger no run has been observed to reach is the
      same silence one layer up.
