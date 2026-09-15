# Issue 798 (2026-09-15) — a tracked landing record claimed a sibling-repo repair that was never committed

## The finding

Two tracked katgpt-rs files recorded cross-repo repairs as **landed and
green**. Neither repair existed in the sibling repo. Both sweeps were **RED**
for the whole interval, and the records described a **worktree state no commit
contained** — Issue 797's class, one level up: 797 covers a sweep's *findings
and floors* reading an uncommitted tree; this is a *prose landing record*
doing it, in a tracked file, where no gate reads it.

Both records were written by `cb03c8dc` (2026-09-15 10:23 +0700).

### Record 1 — `scripts/toolchain_override_drift_floors.txt`

> ⚠ LANDING RECORD, 2026-09-15: … **RESOLVED the same day: all five markers
> are in** (katgpt-rs full_gate.yml + wasm32_gate.yml via rule (b); riir-ai
> g2_netem_docker.sh via rule (c) …; riir-chain toolchain_drift.yml via rule
> (b), UNRESOLVED-MARKED; riir-game-sdk t36_netem_partition_docker.sh marked
> but NO-PIN-OVERRIDE …). **First green sweep: 0 DRIFT / 3 DELIBERATE / 0
> UNRESOLVED / 1 UNRESOLVED-MARKED / 1 NO-PIN-OVERRIDE / 13 UNPINNED-REPO.**

Measured, `git grep toolchain-override-deliberate` over the four named repos:
**2 of the 5 markers existed**, both of them the katgpt-rs pair. The three
sibling markers were absent, and the sweep read `drift 1 · unresolved 1 · ✗
FAILED`.

### Record 2 — `scripts/pipefail_discard_expected.txt`

> (dropped 2026-09-15: … and **riir-chain teardown.sh:24 got the same tail in
> the riir-chain commit**, restoring its already-gone re-run branch.)

That tail was absent. The row was `✗ UNPINNED finding
riir-chain:cloudflare/edge-wallet-container/teardown.sh:cc4d29da#1` and the
sweep read `✗ FAILED`. The row had been **dropped from the pin file on the
strength of a fix that did not exist** — the unrecoverable direction, because
nothing then points at the site.

## Why it happened, and why it needs no prose-parsing gate

The sibling files were edited in the worktree, the sweeps run **green against
those uncommitted edits**, the records written from that run, katgpt-rs
committed, and the sibling edits never committed anywhere.

⛔ **The mechanical repair already existed and postdates the incident by
hours.** Issue 797's worktree advisory (`41ecdcbd`) prints, on every sweep's
final line in both directions, exactly the three repos this issue is about.
`cb03c8dc` predates it, so this is the **first real-world validation of 797
against an incident 797 did not know about**, not a hole in it.

Do **not** add a gate that parses prose landing claims. The sweep is the
verification and it was red from the moment the record was written. The gap
was that nobody ran it in between, which no gate on a workstation-only
on-demand sweep can close.

## The standing rule this adopts

**A cross-repo repair is not landed until it is COMMITTED in the sibling
repo, and a katgpt-rs record claiming one must cite the sibling commit.**

*"The marker is in"* is unverifiable and stood false for six hours.
`riir-chain 5f814a2` is checkable with one `git -C ../riir-chain cat-file -e`.
Same rule the repo already applies to measurements — *take the figure from a
run, not from a sentence here* (Issues 784/785) — extended to the one claim
class whose evidence lives in another checkout.

## Resolution — and a concurrent-duplication lesson

⚠ **The repairs were landed twice, concurrently.** This session wrote all four
and committed them; a **second session landed equivalent repairs upstream at
the same time**. Both were discovered only at `git push`, which was rejected
non-fast-forward in all three repos. Theirs are more concise and were already
on the remote, so this session's duplicates were **dropped** in favour of
them — `reset --hard origin/develop` in the two clean repos, and in riir-ai a
`reset --mixed HEAD~1` + single-file `checkout` so that six dirty files and
six unpushed commits belonging to the other session were untouched.

| repo | file | repair | landed at |
|---|---|---|---|
| riir-ai | `scripts/g2_netem_docker.sh` | `toolchain-override-deliberate` marker, rule (c) | `194cdc9b5` |
| riir-game-sdk | `scripts/t36_netem_partition_docker.sh` | same, rule (c) | `61f11e7` |
| riir-chain | `.github/workflows/toolchain_drift.yml` | same, rule (b) | `5f814a2` |
| riir-chain | `cloudflare/edge-wallet-container/teardown.sh` | `\|\| true` at the substitution tail | `5f814a2` |

⛔ **This session then committed the SAME defect it filed the issue about.**
`b592a213` cited the three SHAs it had just created locally — and those
commits were dropped minutes later, leaving a record citing three hashes
resolvable in no remote. A SHA is only verifiable if it is *pushed*: the rule
above is **cite the sibling commit and check that it resolves**, which is now
done explicitly (all three verified with `git -C ../<repo> cat-file -e`).

Both overrides are genuinely deliberate rather than decayed, which is why the
marker is the correct repair and not a value change: each script **bakes its
own image** (`IMAGE=riir-g2-netem:1.95` / `riir-t36-netem:1.95`, both
`FROM rust:1.95.0-bookworm`), so `-e RUSTUP_TOOLCHAIN=1.95.0` tracks the baked
container, not the workspace pin. Raising it to `1.98.1` without rebuilding
forces a rustup download inside a 1.95.0 container.

The teardown fix restores dead code: under `set -euo pipefail` a
legitimately-empty `grep` (nothing deployed — the normal state for a re-run of
an idempotent teardown) killed the script at the assignment, making the
script's own `(no $APP listed — already gone)` branch unreachable.

## T2 — a sweep reads the WORKTREE, and a worktree can be behind ORIGIN

Dropping the duplicates surfaced a class Issue 797 cannot see. The toolchain
sweep went **RED on riir-ai again** — not because the fix was missing, but
because this box's riir-ai checkout is **109 commits behind origin**, 14 of
them touching the sweep's own population. The marker is committed at
`194cdc9b5`; the worktree has never seen it.

797's advisory compares the worktree to **local HEAD**, so a checkout that
matches its own HEAD and is 109 commits stale is invisible to it. This is the
**mirror of MASKED**: MASKED is a committed defect read clean (a false green);
this is a committed **fix** read dirty (a false RED). A false red is the
cries-wolf outcome this family refuses to pay for, and it cost this session
real time — the row was investigated as an unfixed defect.

`scripts/worktree_state.py` gains `behind_origin(root, patterns)`, wired into
`sweep_advisory()` so **all 18 sweeps get it with zero call-site changes**:

```
⚠ STALE: 1 repo(s) sit BEHIND their upstream on commits that touch this
  sweep's own population — riir-ai (109 behind, 14 in scope). A finding there
  may already be FIXED upstream; this box's checkout is what the sweep read,
  so confirm against origin before repairing (Issue 798)
```

- **Four verdicts, never pooled.** `None` = no upstream configured or git
  could not answer — **never guessed at**, because assuming `origin/main`
  invents a verdict for a repo that may not have one (five workspace repos
  have no `origin/main` at all, `ci_gate_coverage.py`'s standing finding).
  `(0, 0)` = up to date, silent. `(n, 0)` = upstream moved outside this
  sweep's population, silent — otherwise it is the banner nobody reads.
  `(n, k>0)` = the advisory.
- **The three-dot `HEAD...ref` diff is load-bearing.** A two-dot diff also
  reports every file this checkout's own *unpushed* commits touched, so a repo
  that is merely AHEAD would read as stale. Its arm asserts exactly that.
- **ADVISORY, never a failure**, and the sweep deliberately **stays RED**.
  Converting a red to a deferral on staleness would let a genuinely-unfixed
  drift hide behind "you are behind origin", and `max_drift` is a wall at 0.
  The reader is told how to check; the wall still holds.
- **One matcher, shared.** `dirty_in_scope` and `behind_origin` both call
  `_match_count`. A git **pathspec** was the obvious implementation for the
  second and has different semantics from `fnmatch` — a bare `Dockerfile`
  pathspec matches only at the repo root — so the two axes would have
  disagreed about what a sweep's population *is*. An arm pins the nested case.

## T3 — the selftest's hand-typed assertion count was already wrong

`worktree_state.py` printed `✓ … 36 assertion(s)`. Counted by AST over its own
`*_arms` functions at the **parent commit**, before any change here: **40**.
It had been stale on arrival, in a module whose entire subject is records that
drift away from what they describe.

`n_assertions()` derives it now. Counted over `*_arms` functions only, so a
`check` in production code cannot inflate it; it returns 0 rather than raising
on a read or parse failure, because a selftest that PASSED must not be turned
into a crash by its own summary line. The line reads **50** today and will not
need editing again.

## Non-finding, recorded so it is not re-investigated

The pipefail sweep's PASS line reads *"every repo within its pins, every
pinned row firing"* while printing `50 FINDING · 51 pinned row(s)`. That is
**not** an unbacked claim: the both-directions membership check is at
`pipefail_discard_drift_sweep.py:425-431` (`✗ pinned row no longer fires`),
and it correctly `continue`s on repos absent from the box, whose pins ride the
population verdict. `riir-deployer` holds exactly one row and is one of the
four absent repos, so 51 − 1 deferred = 50 checked = 50 findings.
