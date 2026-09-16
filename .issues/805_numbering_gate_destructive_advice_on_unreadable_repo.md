# Issue 805 (2026-09-16) — `numbering_gate.py` printed "remove the row" / "re-pin DOWN" for a repo it could not read

**Status:** RESOLVED 2026-09-16 — refusal landed with four arms, three
perturbations killed
**Severity:** MEDIUM — the exit code was always correct; the **advice** was
destructive, and its worked incident is already in AGENTS.md
**Found by:** Issue 556's step-1 measurement, by typing
`numbering_gate.py --help` — which the gate read as a repo path

---

## What happened

`main()` resolves `sys.argv[1]` to a repo path and hands it straight to
`tracked_paths`, which converts a `CalledProcessError` into an **empty set**.
That is the same value a repo with no numbered files would produce, so a bad
path yields `0 numbered file(s)` in every directory, and every ceiling above
the floors is then evaluated over nothing.

Measured on `--help`, on a nonexistent path, and on `/tmp/notarepo`:

```
✗ 10 HISTORICAL numbering collision finding(s) …
    STALE pin .issues/741: pinned as a collision and no longer one — remove the row …
    STALE pin .issues/775: … (×8 more)
  ⚠ legacy collisions 0 < ratchet 61 — re-pin DOWN in this commit
✗ population FLOOR breached …
```

⛔ **The floors DID red — exit 1, never 0 — so nothing was silently wrong.**
What was wrong is the ORDER and the REMEDIES. Ten lines instructing the
reader to delete collision pins, and one instructing a ratchet be re-pinned
downward, are printed **first**; the floor breach that makes all of it
vacuous is printed **last**. That is this repo's own most-repeated failure —
*"the deferral rode a Layer-2 line six hundred lines of build output
earlier"* — and the remedy is not hypothetical:

> AGENTS.md § Numbering Discipline: *an issue was closed and removed under the
> noise-reduction rule and its collision pin deleted in the same commit as
> "stale", and `develop` went red for every later run.*

That incident happened with the gate reading a **real** repo. Here the same
advice is manufactured from an unreadable one, and following it deletes the
only surviving record of a collision whose holders are both gone — the
Issue 795 majority case, recoverable from nothing else.

## The fix

`unmeasurable(repo) -> str | None`, called before anything is computed,
returning exit **2** (this module's existing "instrument untrustworthy" code:
selftest failure, missing pins file, malformed pins, empty scope) rather than
**1** ("the repo has findings").

⚠ **The check is toplevel EQUALITY, not "did `rev-parse` succeed".** `git -C`
walks UP, so a subdirectory of a real repo answers happily and then resolves
every path against the wrong root — `tracked_walk.py` records the identical
hazard for its own `.git` probe (Issue 777). Measured, all four:

| input | verdict |
|---|---|
| nonexistent path | `not a directory` |
| real dir, not a repo | `not a git repository, or git unavailable` |
| **subdirectory of a repo** | `not a repository ROOT: … sits inside …` |
| repo root | passes; gate still green at 1036 files / 70 historical / 9 pinned |

## Arms

Four, in the unconditional `selftest()`. Perturbation, one line at a time:

| mutation | verdict |
|---|---|
| `if not repo.is_dir():` → `if False:` | killed |
| `if Path(top).resolve() != repo:` → `if False:` | killed |
| `check=True` → `check=False` | killed **only after the arm asserted the REASON** |

⛔ That third row is the one worth recording. Dropping `check=True` still
**refuses** — an errored `rev-parse` prints nothing, and `Path("").resolve()`
is the cwd, which fails the root-equality test — but it refuses as *"not a
repository ROOT"*, sending the reader to look for a parent repo that does not
exist. With the arm testing only `is not None` the mutant SURVIVED. A refusal
is not one bit; the reason is part of the verdict.

⚠ An `if not top:` branch was written and then **removed rather than armed**:
`check=True` means the call succeeded, and a successful `--show-toplevel`
always prints a path (a bare repo fails at 128 with *"must be run in a work
tree"* and is caught above). It was unreachable, and removing it loses nothing
even if some git did return empty — `Path("")` resolves to the cwd and the
equality test refuses anyway. Same call as the two decisions removed from
`plan401_pcalm_sweep.rs` the same day: an unarmable line dressed as a
decision.

## Scope — the first answer here was WRONG, and measuring it is what caught that

This section first read: *"the sibling gates that take a repo path derive their
population from `repo_set.txt` + a `.git` probe and already answer an
unreadable repo with UNSEEN / DEFERRED … `numbering_gate` is the outlier."*
That was written from the shape of the code, not from running it, and running
it refutes it. Fourteen `scripts/*.py` that accept a repo path, each handed
`/e/git/nonexistent-repo`:

| instrument | verdict on a repo that does not exist |
|---|---|
| `pipefail_discard_audit` | **exit 2**, `⛔ 0 tracked .sh < floor 20 — the walk is blind` |
| `platform_dead_code_audit` | `⛔ ZERO candidate declarations — that is an instrument failure, not a clean repo` |
| `orphaned_attr_gate` | `✓ orphaned-attribute gate PASSED — pinned at 0, measured 0 over 0 .rs file(s) in nonexistent-repo`, **exit 0** |
| `cfg_row_implication_audit` | `0 rows over 1 repo(s); 0 carry a leading #![cfg]; 0 EMPTY-AT-ROW, 0 UNRESOLVED` |
| the remaining ten | report-only, exit 0 by design; no blindness line |

So the class is **not** confined to `numbering_gate`, and the two instruments
that DO catch it catch it with a real population floor rather than a path
check — which is the better repair where a floor is available.

### `orphaned_attr_gate` — fixed here, because it is a GATE

It is a `docs_gate.sh` CHECK, and it printed `✓ … PASSED … in
nonexistent-repo` at exit 0. Its floors are deliberately scope-guarded to
`repo == REPO_ROOT` — *"a sibling audit is a different population and gets the
report without the verdict half"* — and that reasoning is **right**: a
sibling's population belongs to `orphaned_attr_drift_sweep.py`, which pins it.
The consequence is what nobody had looked at: in sibling mode there is then no
blindness detector at all, and `floors n/a` is printed on the pass line.

⚠ **The predicate is NOT the one `numbering_gate` needed, and assuming it was
would have broken something.** `numbering_gate` runs `git ls-files` and
`git log`, so it requires a repository ROOT. `orphaned_attr_gate` goes through
`tracked_files`, which **falls back to a filesystem walk** where there is no
`.git` — deliberately, for `git archive` trees and synthetic fixtures
(Issue 777). Refusing a non-repo there would have broken a legitimate use. The
two decidable cases are instead:

- path is not a directory → **UNSEEN**, exit 2. Unambiguous.
- sibling, 0 `.rs` files → **UNSEEN**, exit 2. Legitimate for a
  TypeScript-only contract repo, so **not FAILED** — but not a pass either,
  the house rule for every bucket meaning *unanswered*.

`unmeasured(repo, files, own)` is EXTRACTED rather than inline, and that is
the repair rather than a tidy-up: `main` calls `selftest`, so a decision
living in `main` cannot be armed without recursing. Six arms; the one that
earns its keep asserts `unmeasured(root, 0, own=True) is None`, pinning the
division of labour with the floors — without it, dropping `not own` survives
and the gate double-reports its own repo.

⛔ **`arm_reach_gate` found four survivors here that hand perturbation did
not**, with operators hand-sed cannot express: `and2or`
(`not own and files == 0` → `… or …`), `dropnot`, `eq2ne`. Run it after
touching a gate; `if False:` substitution is not a mutation suite.

### Left alone, with the reason

`cfg_row_implication_audit` and the nine other report-only instruments are
recorded above and **not** changed. They are exit-0 by design, their verdict
halves (`*_gate.py` / `*_drift_sweep.py`) derive population from
`repo_set.txt` and answer an absent repo with UNSEEN/DEFERRED, and widening
this issue to fourteen instruments on the strength of one measurement is the
symmetry argument AGENTS.md tells you to re-measure first. The census is here
so the next reader starts from data rather than from the paragraph this
section used to contain.
