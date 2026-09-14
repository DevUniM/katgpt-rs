# Issue 786 — the `.len()`-derived binding audit is a cross-repo report with no verdict half AND no AGENTS.md entry

**Filed:** 2026-09-14 · **Status:** OPEN · **Branch:** develop

## The gap

`scripts/len_derived_binding_audit.py` (983 lines, riir-train 515 T1/T3 +
Issue 766 HALF C) derives its population from `BOUNDARY.md + .git`, walks
**8,694 tracked `.rs` over 16 repos**, and classifies **164 bind sites** over
**52 `.len()`-deriving cube kernels** into nine verdict buckets.

Nothing asserts any of it.

- No per-push gate. No workstation sweep. It is the **last** cross-repo
  instrument in `scripts/` in that position — twelve others carry both halves,
  and the two documented exceptions (`suite_membership_audit.py`,
  1,203 load-bearing unpinned rows; `gguf_header_audit.py`, model-file
  introspection) were bounded deliberately at `1a5b6571`.
- It is not in `AGENTS.md` **at all** — no `##` section, no invocation line.
  Every other audit in the family has one. Its only mentions in this repo are
  three incidental lines in `HISTORY.md`.

This is the ninth instance of the standing failure mode (Issues 777, 778, 779,
782, 783, 784, 785): **a rule landed in one instrument and never generalised.**
The instrument that finds it is the census, not a symptom — and this one was
quieter than 784/785 because it never had a hand-typed standing figure to go
stale. An instrument nobody is told about cannot drift into being wrong in
public; it just stops being run.

## Why it matters here specifically

This audit has **already gone blind once** and nobody noticed from its output.
Issue 777 found it walking the filesystem behind a hand-typed skip set, which
credited seal-online-remaster's gitignored nested `mmorpg/` repository and
riir-train's cargo `OUT_DIR` sources to their enclosing repos. It was migrated
to `tracked_walk` in that commit. Had a floored sweep existed, the population
shift (11,132 → 8,694 `.rs`) would have been an assertion instead of a
paragraph.

The class it reports is not cosmetic: a kernel deriving a structural dimension
from a bound buffer's `.len()`, handed a buffer whose **declared** size exceeds
its live range, silently derives the WRONG SHAPE — reads never-written memory,
writes a measured identically-zero result, no panic and no NaN
(riir-ai `3e00c93e0`, riir-train `.issues/511`).

## Measurements taken while filing (these determine the pin design)

**1. The population is bimodal — 14 of 16 repos have nothing.**

| repo | kernels | bind sites |
|---|---|---|
| riir-ai | 43 | 143 |
| riir-train | 9 | 21 |
| the other 14 | 0 | 0 |

So `min_kernels` / `min_binds` are **vacuous in 14 of 16** and detect nothing
there. This is Issue 783's population shape, not Issue 784's: `min_rs_files` is
the only per-repo blindness detector in the majority of the set, and the
kernel/bind floors have to be **global** (a reserved `TOTALS` row) or they
certify nothing.

**2. Bucket standing (2026-09-14, 16 of 20 repos on this box).**

| bucket | n | pin shape |
|---|---|---|
| CAPACITY | 0 | **wall** — the joined finding |
| CAPACITY-UPSTREAM | 0 | **wall** |
| PERSISTENT | 0 | **wall** |
| PERSISTENT-UPSTREAM | 4 | **membership** (the EYES LIST) |
| UNRESOLVED | 118 | deliberately UNPINNED — see (4) |
| GUARDED | 25 | not a finding |
| GUARD-ONLY | 14 | not a finding |
| EXACT-UPSTREAM | 3 | clean by construction |
| NOT-LAUNCHED | 0 | — |

**3. The verdicts are cross-repo by construction, and today no verdict depends
on it.** HALF C resolves a wrapper parameter's provenance through *workspace*
callers, so a partial clone can in principle corrupt the verdict of a row in a
repo that IS present — which no other sweep in the family can do, and which
`DOCS_GATE_PARTIAL_CLONE`'s DEFERRED verdict does not cover (it addresses
absent ROWS, not corrupted present ones).

Measured rather than assumed, both directions:

- **7 of 251** cited caller references are cross-repo (all riir-ai bind sites
  resolved through riir-train callers).
- **Leave-one-out over all 16 repos: 0 verdict flips.** Dropping riir-train
  leaves riir-ai's buckets byte-identical; every one of those 7 edges is an
  *additional* caller on a row already decided by a same-repo caller.

So a per-repo-pinned sweep is sound **today**, and the day that stops being
true is a day the sweep must announce rather than defer. The check has to be
targeted, not exhaustive: 16 extra runs at 7.8s each is ~2 min, but only repos
that actually SUPPLY a cross-repo citation can flip anything — derive that set
from the run (today: `{riir-train}`, one extra run) so a new edge joins by
existing rather than by somebody remembering.

**4. UNRESOLVED is 118 of 164 (72%) and must NOT be ratcheted.** Issue 785's
rule: a ratchet on a bucket whose meaning is *unanswered* is a backlog. wasm32
could wall it at 0 because 738 T1 drove it there by ANSWERING the rows; here
the bucket is "wrapper parameter whose provenance lives one level up and whose
caller is not a path-form associated fn", which HALF C cannot reach. Report it,
name the reason at the point it is read, leave it unpinned — the
`suite_membership_audit` precedent.

## Tasks

- **T1** — Extract the workspace classification from `main()` into a reusable
  entry point so the sweep shares the classifier rather than copying it. The
  audit's HALF A/B/C + the guard-only re-verdict pass is the instrument; a
  second copy is a second thing to get wrong (Issue 755, and the wasm32
  classifier's own three wrong answers).
- **T2** — `scripts/len_derived_drift_sweep.py`: per-repo `min_rs_files`
  floors, a reserved `TOTALS` row flooring kernels + bind sites globally, the
  three 0-walls, the EYES LIST by membership, `population_verdict()` for the
  partial-clone axis, and the targeted leave-one-out stability arm from (3).
- **T3** — `scripts/len_derived_drift_floors.txt` +
  `scripts/len_derived_eyes_expected.txt`, with the (2)/(3) measurements as
  the recorded warrant.
- **T4** — Canary arms, both directions, measured not reasoned about.
- **T5** — An `AGENTS.md` section for the audit + the sweep joining the
  workstation family list.
- **T6** — Close-out in `HISTORY.md`.

## Out of scope

Reading the 118 UNRESOLVED rows or the 4 EYES rows. Those are riir-ai's and
riir-train's to adjudicate, and this repo is upstream of both; the deliverable
here is that the count stops being unasserted.
