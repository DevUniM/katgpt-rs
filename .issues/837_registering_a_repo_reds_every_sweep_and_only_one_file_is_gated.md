# Issue 837: registering a contract repo reds the whole sweep family, and the ONE file a gate checks is not the twenty-one that make them red

**Status:** open. **Found by:** a `console_encoding_drift_sweep` run during
[Issue 836](836_a_git_worktree_makes_the_head_provenance_mechanism_silently_inert.md)
reporting `✗ riir-llm … UNPINNED — add a row (or it can never red)`, with the
failure having nothing to do with the change under test. Filed by session
`katgpt-rs-c5`.

## What happened

`riir-llm` was registered on 2026-09-18 (`b5dd81dc`, *"a contract repo joined
the workspace today and NO gate could see it"*). That commit did the gated
half correctly: `repo_set.txt` gained a row and AGENTS.md's §Repo count was
updated, which is exactly what `agents_repo_set_gate` asserts, and the gate
went green.

**Every per-repo pin file was left behind.** Measured 2026-09-18, scoped to
canonical repos that are actually ON DISK (an absent repo cannot be measured
and is correctly DEFERRED):

```
registry=21  on_disk_canonical=14  absent=7

21 of 21 per-repo pin file(s) lack a row for an on-disk canonical repo
   … and in 19 of them the ONLY missing repo is riir-llm
```

The two exceptions carry pre-existing, unrelated gaps and are the reason the
repair is not a one-line loop — see T2.

Observed effect, running the family one sweep at a time: sweep after sweep
reds with `UNPINNED — add a row`, on a repo nobody has looked at, for a reason
unrelated to anything the run was measuring.

## ⛔ The finding: the registration is a MULTI-FILE operation and exactly one
file is gated

`agents_repo_set_gate` asserts `repo_set.txt` ↔ AGENTS.md §Repo count. That is
a good check and it is complete over the question it asks. But **21 more
tracked files are keyed on that same registry**, and nothing relates them to
it — so registering a repo is a 22-file operation with 1 file gated and 21
discovered at runtime, one red sweep at a time, by whoever happens to run one
next.

This is the state AGENTS.md already names as the worst outcome for this
family, one level up from where it names it:

> a sweep that always reds is a sweep nobody runs — measured: the percentile
> sweep's Issue-777 findings, and four live citation drift rows, were sitting
> behind those reds (Issue 793)

793 fixed that for the **partial-clone** question and made the answer shared
(`sweep_population.py`, three verdicts). The *registration* question has the
identical shape, the identical consequence, and no shared answer at all. ⚠ And
it is the **eleventh** recorded instance of this repo's most-repeated failure —
a rule landed in one instrument and never generalised (Issues 777, 778, 793,
782, 783, 789, 797, 820, 822, 836).

⚠ Note what is NOT wrong here: the sweeps are behaving exactly as designed.
`UNPINNED — add a row (or it can never red)` is the correct, loud refusal — a
repo with no row has no ceiling and could never fail. The defect is that
nothing tells you the set of rows to write, at the moment you create the
obligation, and the only thing that does tell you is twenty-one separate
multi-minute runs.

## Tasks

- [ ] **T1 — write the 21 `riir-llm` rows**, each from a real measurement of
  that repo by the sweep that owns the file, in the commit that adds it.
  Unblocking work, and it comes first: the family is red *today*, and a red
  family is one nobody reads. ⚠ Take each value from the sweep's own run —
  a floor typed from a neighbouring row is the "diary, not a wall" shape this
  repo already refuses.

- [ ] **T2 — the gate: every per-repo pin file has a row for every ON-DISK
  canonical repo.** The scope must come from `repo_set.txt` ∩ the derived
  walk, so an absent repo DEFERS exactly as it does everywhere else in the
  family.
  ⛔ **The predicate cannot simply be "every file with ≥5 repo rows"**, and
  the measurement says why: `docs_drift_floors.txt` (8 rows) and
  `required_features_build_floors.txt` (11) are legitimately **SUBSET**-scoped,
  and a gate demanding completeness of them would red forever on a correct
  file — manufacturing the very cries-wolf state this issue is about. Scope is
  a per-file declaration with a reason, membership-pinned, reds in BOTH
  directions; a file that grows into every-repo coverage must not stay
  exempt by inertia.
  ⚠ It must be a **docs-gate CHECK**, not a sweep: it reads tracked files and
  the registry, needs no sibling checkout, and the whole point is to fire in
  the commit that registers a repo rather than on somebody's next workstation
  run.

- [ ] **T3 — the inverse direction, UNMEASURED.** A pin row for a repo that
  has since left `repo_set.txt` is a stale row that can never be evaluated,
  and nothing looks for it either. Whether any exist is a measurement, not an
  assumption — **count first**, the `console_encoding_gate` lesson this
  workspace has now been wrong about twice.
