# Issue 836: a `git worktree` makes the ENTIRE head-provenance mechanism silently inert — every guard returns the "nothing to report" value

**Status:** **CLOSED 2026-09-18** — T1 (the severe five), T2 (the three private copies, measured then delegated), T3 (the cross-repo axis, counted) and T4 (the silent self-row) are all done.
**Found by:** generalising [Issue 835](835_a_path_dep_on_a_repo_in_neither_set_is_enumerated_by_nothing.md)'s
`.git`-is-a-FILE lesson across the instrument family, as that issue's own
"general rule" paragraph asks. Filed by session `katgpt-rs-c5`.

## ⛔ The finding: the SAME lesson, applied to the WRONG question

Issue 835 defect 1 established that a contract-repo walk must test
`(p / ".git").is_dir()`, **not** `.exists()` — a `git worktree` has a `.git`
**FILE**, so `.exists()` counted this box's `riir-chain.w152` as a 22nd repo
and attributed its manifests to a repo that does not exist. That is correct
and it is now the stated general rule.

**`.is_dir()` is the wrong spelling for the other question.** `.git` is
consulted for two different purposes in this repo and each spelling is wrong
for the one it was not written for:

| the question | correct probe | why |
|---|---|---|
| *Is this directory a canonical REPO?* | **`.is_dir()`** | a worktree is not a separate repo — Issue 835 |
| *Can I run git rooted HERE?* | **`.exists()`** | a worktree is a perfectly good checkout — **this issue** |

`scripts/tracked_walk.py:88` already had the second one right, and AGENTS.md
already documents why (*"a tree with no `.git` — `git archive`, a synthetic
self-test fixture — falls back to the walk"*). `worktree_state.py` took the
other spelling for all five of its guards.

## ⛔ Why this one is severe: every null answer IS the "clean" answer

Measured 2026-09-18 against a real worktree (`git worktree add --detach`,
`AGENTS.md` modified, git itself demonstrably answering):

| function | git ground truth | `worktree_state` | what the caller concludes |
|---|---|---|---|
| `dirty_files` | `M AGENTS.md` | **`frozenset()`** | nothing dirty → advisory SILENT, every row filed COMMITTED |
| `head_text` | rc 0, content | **`None`** | nothing committed to compare → the **MASKED** direction is dead |
| `head_tree` | — | **`None`** | caller SKIPS provenance entirely |
| `behind_origin` | upstream configured | **`None`** | no upstream → the **STALE** advisory is silent |
| `fetch_age_hours` | `FETCH_HEAD` readable | **`None`** | cannot tell → the unverified-fetch line is silent |

Not one of these is an error path. Every one is the value that means *there is
nothing to report*, and each is individually documented as a legitimate
reading — which is exactly why five of them failing at once produces no signal
anywhere.

End to end, identical dirty state, one `sweep_advisory` call:

```
ordinary : ["⚠ WORKTREE: 2 file(s) in this sweep's own population differ from
             HEAD — katgpt-rs (2). Counts and floors from this run describe a
             state NO commit contains; do not re-pin from it (Issue 797)"]
worktree : []
```

So **a sweep run from inside a worktree re-pins from another session's
in-flight edits with no warning at all** — Issue 797's founding defect,
reintroduced in the mechanism built to prevent it, by the repair for a
different question. The pins read the worktree while believing they read HEAD.

⚠ **It is reachable by this workspace's own documented practice**, not
hypothetically: an isolated sibling worktree pair is the recorded way to work
riir-train against a current riir-ai, and this box carries `riir-chain.w152`
today. The population walk correctly EXCLUDES worktrees, so no sweep hands one
to `worktree_state` while iterating — the live path is the ordinary one, an
agent with its **cwd inside a worktree** running a sweep on its own repo.

## T1 — `.exists()` for all five guards (DONE)

The probe's load-bearing requirement is stated in its own arm and is **not**
about directory-ness: *"a non-repo directory INSIDE a repo must not inherit
its PARENT's dirty set"*, because `git -C` walks up. `.exists()` satisfies it
exactly — a plain subdirectory has no `.git` entry of any kind — so the change
is strictly widening on the one case that should have answered all along:

- non-repo dir inside a repo → still `False`, still protected ✓
- `git archive` extraction with no `.git` → still `False`, still the walk ✓
- **worktree → now `True`, and git is asked** ✓

⛔ **A widening with no arm is the `platform_dead_code` vendor-arm failure**
(an arm that red nothing under perturbation, because one exclusion had two
code paths and the arm certified the path it was not aimed at). So the repair
lands with a `worktree_arms` group that builds a REAL `git worktree` and
asserts all five guards against git's own answers — it reds if any guard goes
back to `.is_dir()`, in both directions.

## Open tasks

- [x] **T2 — the MILD half, MEASURED 2026-09-18 and then repaired.** The
  three were measured one by one before anything was changed, as this task
  demanded, and the measurement moved one of them out of the MILD class.

  Fixture: `git worktree add --detach F:/scratch/kg836_wt HEAD` off this
  repo, with one untracked scratch file planted in the worktree's `scripts/`
  — the ordinary shape of an agent working in a worktree.

  | instrument | worktree, `.is_dir()` | worktree, `.exists()` | ordinary |
  |---|---|---|---|
  | `console_encoding_gate` | **✗ UNDEFENDED `zz_scratch_probe.py`** | ✓ 83 in population | ✓ 83 |
  | `sweep_advisory_membership_gate` | **✗ UNWIRED ×3** on one untracked file | ✓ 21 sweeps | ✓ 21 |
  | `numbering_drift_sweep.head_listing` | **`None` → head-provenance SKIPPED** | reads HEAD | reads HEAD |

  - The first two are the **cries-wolf** direction, and the second is the
    sharper one: the glob fallback converts a single untracked file into
    **three** findings, one per mechanism, each telling the reader to wire a
    sweep that is not in the family. With the delegation both worktree runs
    are **byte-identical** to the ordinary run.
  - ⚠ The **shrink** direction was measured too and is NOT this class: a
    tracked file deleted in the worktree gives 82 under *both* spellings (the
    glob never lists it; `ls-files` lists it and the read then skips it). Same
    answer by two routes — so it discriminates nothing here, and the wrong
    fixture would have credited a repair with it.
  - ⛔ `head_listing` is the **severe** shape, not the mild one the task text
    guessed: its `None` propagates through `head_audit` and the whole
    head-provenance adjudication is skipped, so every row is judged against
    the worktree while the pins believe they read HEAD. It is also **measured
    unreachable by its own caller** — `repos = contract_repos(WORKSPACE)` is
    Issue 835's `.is_dir()` walk, verified against this box's real
    `riir-chain.w152` (on disk with a `BOUNDARY.md`, absent from the derived
    17). Repaired anyway, with an arm pinning that exclusion from both sides:
    *correct by a caller's property* is precisely what 835 → 836 cost once.

  **DRY.** A fourth private copy of a one-line predicate is a fourth chance to
  pick the wrong one, so `_is_checkout` is now public `is_checkout` and all
  three delegate. The arms share `worktree_state.worktree_fixture` — a REAL
  `git worktree add`, measured **0.167s**, which is what makes it affordable
  in a per-push canary at all; a hand-written `.git` file would assert the
  probe and not the behaviour (the `platform_dead_code` vendor-arm failure).
  Every new arm was perturbation-verified: reverting each delegation to
  `.is_dir()` reds it by name, rc 2.

- [x] **T4 — a name match that never fires, found by T2's fixture.** The same
  silence one layer up, and in the block AGENTS.md calls *"the delegation is
  asserted, never assumed"*: `numbering_drift_sweep`'s gate cross-check was
  guarded by `if repo.name == REPO_ROOT.name:` with **no else**, so from a
  checkout directory not named for its repo it simply did not run and the
  sweep printed a clean summary with 0 of its own rows cross-checked.
  Reachable three ways, one of them this box's own convention: a worktree at
  `E:/git/katgpt-rs.w836` (cf. the live `riir-chain.w152`), a fork clone, or
  an alias row.

  `.name` twice was **also the wrong comparison**: the derived repos carry the
  CONTRACT spelling (`contract_repos` maps them through `repo_alias`) and
  `REPO_ROOT` carries the on-disk one, so a box with a `repo_alias.local.txt`
  row for this repo took the silent branch on *every* run. Now
  `repo_alias.apply([REPO_ROOT.name])[0]`, with a `✗ SELF-ROW MISSING`
  failure — loud, and never a deferral: a partial clone can lack any sibling,
  but it cannot lack the repo the script is running out of. Perturbation-
  verified against the `.w836` name: rc 1, named.

  ⚠ The family was grepped before fixing (the repeated-shape rule). The
  ~10 sweeps using `pins.get(REPO_ROOT.name)` all print `✗ … has no row for
  …` and are loud already; `citation_drift_sweep`'s `repo.resolve() ==
  REPO_ROOT` crashes on `mine_row[c]` — loud by accident, but loud.
  `numbering_drift_sweep` was the only silent one.

- [x] **T3 — the cross-repo axis, MEASURED 2026-09-18.** *Counted first*, per
  the `console_encoding_gate` lesson — and it was right to: the population is
  **not** one. Across the 13 canonical repos present, `.git` probes in
  `scripts/*.py`:

  | repo | sites |
  |---|---|
  | katgpt-rs | 26 (19 `.is_dir()` + 7 `.exists()`) |
  | riir-ai | 2 |
  | riir-clippy | 1 |
  | the other 10 | 0 |

  So the class is overwhelmingly local but genuinely present in two siblings —
  a sweep is **not** warranted (3 sites do not need an instrument), and the
  three were read one by one instead:

  - ⛔ **riir-ai `inert_config_knob_report.py:366` — Issue 835's defect
    verbatim.** A contract-repo walk on `.exists()`, counting this box's
    `riir-chain.w152` as a 17th repo (17 vs 16, measured). Its own docstring
    cited *"the workspace's contract-repo predicate, per derive-the-repo-set
    rule"* over a hand-rolled copy. **Filed and repaired in that repo as
    riir-ai Issue 978, committed `9637d09ea`** — a cross-repo repair is not
    landed until it is committed in the sibling with a cited SHA (Issue 798).
  - ✓ riir-ai `transport_selection_dry_gate.py:140` — contract-repo walk,
    `.is_dir()`. **Correct**, and the reason 978 is one site rather than a
    house style.
  - ✓ riir-clippy `gen_dashboard.py:565` — the *other* question (it goes on to
    run `git log` across siblings), `.exists()`. **Correct**, and the standing
    argument against sweeping one spelling: a blanket `.exists()` → `.is_dir()`
    pass would have broken it.
