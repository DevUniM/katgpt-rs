# Issue 785 — the wasm32 surface audit has no verdict half, and its standing figure is hand-typed

Filed 2026-09-14. Class: report without a verdict / hand-typed standing.

## The claim

Issues 783 and 784 closed the last two *per-push gates* with no cross-repo
sweep. `scripts/wasm32_surface_audit.py` is the mirror gap: it is already
cross-repo (it derives its own population), and it has **no verdict half at
all**. Nothing pins its buckets, so a new UNCOVERED package is a line in a
report that runs on demand.

AGENTS.md carries its standing by hand:

> Standing (measured 2026-09-14, post-774): **26 NAMED · 2 BY-DEP · 0
> UNRESOLVED · 1 UNCOVERED** over 216 files / 29 packages / 20 repos

That is the exact shape Issue 784 just closed one instrument over — a
cross-repo total, typed into prose, re-asserted by nothing. 784's went **46%**
stale without a single run noticing. This one is not stale today (this box
measures 25 NAMED over 16 repos, which is the partial-clone difference and not
drift), and "not stale today" is precisely the state 784's figure was in for
eleven days.

## Why this class is worth a wall and not just a report

The buckets are not decoration. Issue 738 found seal-remake carrying a positive
`#[cfg(target_arch = "wasm32")]` block that **no row built and that had been
uncompilable since it was written** — it called a `cfg(not(wasm32))` function.
An UNCOVERED package is code that has never compiled and that nothing will ever
tell you about, because the arch it is gated on is one no lane passes.

UNRESOLVED is the one that must be walled at 0 rather than ratcheted: the audit
already refuses to fold it into either neighbour ("a human has not answered it,
and that is the bucket's job"), and a ratchet on a bucket whose whole meaning is
*unanswered* converts it into a backlog.

## The one UNCOVERED row is a NEGATIVE CONTROL, and that is why the pin is by MEMBERSHIP

`seal-online-remaster: seal-poc-submodule` is deliberately excluded from its
repo's CI and depended on by nothing; AGENTS.md already records it as the
standing negative control, and that repo is read-only from here (arm-vs-row is
its owner's call). A **count** pin of `max_uncovered = 1` would go green if
that row were repaired and a different package regressed on the same day — a
count is not a checksum over a set, which is `trap_sentinel_gate.py`'s rule.
So: UNCOVERED is pinned by NAME, and the cardinality falls out.

## Tasks

- **T1** — extract the per-repo classification out of
  `wasm32_surface_audit.main()` into a callable (`classify_repo(repo)`), and
  have `main()` consume it. It is ~40 lines of buckets computed inline inside a
  print loop today; the sweep cannot reuse it without either that extraction or
  a second copy, and a second copy of the 738/774 resolution rules is a second
  thing to get wrong (Issue 755).
- **T2** — `scripts/wasm32_surface_drift_sweep.py`: the verdict, every contract
  repo, pins in `scripts/wasm32_surface_drift_floors.txt`. Population axis is
  `sweep_population.population_verdict` (Issues 779 + 782).
- **T3** — pins, per repo: `min_files` (walk floor), `max_unresolved = 0`
  (wall), and UNCOVERED by **membership** in a companion
  `scripts/wasm32_uncovered_expected.txt`, the
  `scripts/all_ignored_load_bearing.txt` pattern.
  ⚠ There is no useful *parse* floor here: `min_packages` would be the analogue,
  but a repo with zero positive-cfg packages is the common case (the audit skips
  it entirely), so the walk floor is the only blindness detector — state that as
  the measured fact it is, as `subprocess_encoding_drift_floors.txt` does.
- **T4** — AGENTS.md: the sweep joins the workstation family list; the standing
  paragraph says where the figure now comes from.

## What this issue does NOT claim

That the 16-repo numbers this box can produce are the canonical ones. They are
not — `seal-poc-submodule`'s repo is present here, so the membership pin is
measurable, but the four absent repos stay `DEFERRED` per Issue 779 and any
positive-cfg package they carry is unpinned until the next full checkout.
