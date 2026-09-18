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

- [x] **T1 — the 20 `riir-llm` rows, DONE 2026-09-18.** Measured first: **19
  of 21 sweeps RED**, the two greens being `docs_drift` and `restatement`,
  both legitimately SUBSET-scoped (docs_drift's own header says it records
  "only WHICH repos are known to carry drift-auditable labels"; restatement's
  population is repos with `.proofs`). Every value read off the sweep's own
  printed row for riir-llm.

  ⛔ **The first attempt CLONED a neighbouring repo's row and was wrong
  eleven times** — riir-auth's floors are not riir-llm's measurements, so
  `citation_drift_floors` got `min_citations 8` for a repo with 0 citations.
  That is the "diary, not a wall" shape, reached by the shortcut it warns
  about. Reverted; the rows are typed from the run.

  ⚑ **The arity assertion earned its keep immediately**, and what it caught is
  its own finding: `percentile_drift_floors` and `trap_sentinel_drift_floors`
  declare **4** columns in their format headers while every row carries **6**
  and **7**. A pin file's format line is what a human adjudicates a row from,
  and a stale one reds nothing. Both repaired against the sweeps' own `FIELDS`
  tuples, which are the only authority.

### ⛔ What the pins surfaced — three live findings that were sitting behind
the reds

This is Issue 793's measured claim reproduced exactly (*"a sweep that always
reds is a sweep nobody runs"*), and it is the argument for T2 far more than
the inconvenience is. With riir-llm pinned, three sweeps went from **red for a
bookkeeping reason** to **red for a real one**:

| sweep | finding | repaired |
|---|---|---|
| `citation` | riir-kat: 3 unqualified cross-repo citations — `Bench 053` ×2 and `Proposal 006`, the first ⛔MISLEADING (the only crate in its window is riir-dapps, which does **not** own 53, while katgpt-rs owns two documents at that number) | riir-kat `51994ee` |
| `trap_sentinel` | riir-shader: `gamefx_feature_matrix.sh` EXPOSED — `set -eu`, an EXIT trap, 6 triggers, and a window that deliberately corrupts a tracked source, so a laundered abort restores the file and prints PASS having run neither arm | riir-shader `176da06` |
| `instrument_reachability` | riir-clippy: 11 unreachable vs 4 pinned — 7 plan/bench-scoped one-offs landed undocumented | ratcheted at measured (the documented OVER-CAPTURE class; documenting them is riir-clippy's own call) |
| `numbering` | riir-shader: `.plans/.highwater` left at 004 while `.plans/005` exists — the next allocator reads 004, takes 005 and files a second document at a held number | riir-shader `6f045d4` |

**Final state: 21 of 21 sweeps green** (from 19 red), docs gate 28/28.

⚠ The riir-shader row is also an Issue-798 near-miss worth recording: that repo
was **2 commits behind origin** when the finding appeared, so the first
question was whether it was already fixed upstream. It was not — neither
commit touches a `.sh` — but *confirm against origin before repairing* is what
made that a fact rather than an assumption.

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

- [x] **T3 — the inverse direction, MEASURED 2026-09-18: zero.** A pin row for
  a repo that has since left `repo_set.txt` can never be evaluated, and
  nothing looks for it. Counted rather than assumed: across every
  `scripts/*floors.txt` and `*expected.txt`, the only repo-shaped row keys
  absent from the registry are the **six package names** in
  `x86_64_matrix_floors.txt` — a package-keyed file, a false positive of the
  heuristic and not a stale row. So the direction is empty today, which is a
  measurement and not an absence of the class; T2's gate should still assert
  it, since the cost is one set difference it already computes.
