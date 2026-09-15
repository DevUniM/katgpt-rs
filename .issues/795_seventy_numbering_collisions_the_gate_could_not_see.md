# Issue 795 — 70 numbering collisions the gate could not see, 9 of them live

**Filed:** 2026-09-15 · **Status:** RESOLVED (T1–T3 landed; T4 deferred with a
reason) · **Branch:** develop

## What happened

Issue 791 recorded **three** double-allocated numbers (776, 779, 780) and
closed. Within minutes of the instrument it built being pointed at a fourth
number, `775` came back a duplicate too — and a full scan says the real figure
is **70**, over 1374 numbers, across the four directories `numbering_gate`
already governs.

| dir | numbers | collisions | highest legacy | at/above 700 |
|---|---|---|---|---|
| `.issues` | 335 | 51 | 575 | **741, 775, 776, 777, 778, 779, 780, 781, 782** |
| `.research` | 541 | 10 | 399 | — |
| `.plans` | 485 | 9 | 332 | — |
| `.proposals` | 13 | 0 | — | — |

⛔ **791's "three" was not a count of the problem; it was a count of what the
instrument could see.** `citation_weight.candidates()` enumerated `.md` files ON
DISK, and a document closed under the noise-reduction rule is DELETED — so a
collision where BOTH sides have closed leaves nothing on disk and reads as "not
a duplicate". Every number this repo allocates is expected to end up removed, so
that is the majority case, not an edge: 6 of the 9 recent collisions were
invisible for exactly that reason, and `numbering_gate`'s tracked-duplicate
wall — which is correct about what it measures — had never reported one in its
life.

**Two sessions, one counter.** All 9 recent ones are the same event as 791: both
sides read `.issues/.highwater`, both incremented correctly from their own view,
and the rebase merged the counter with `max(ours, theirs)`, the only sound rule
for a monotonic counter and exactly what makes a double-allocation invisible.
A counter records the NEXT free number; it is not a ledger of who took what.

## ⛔ The first scan over-reported by 52, and the reason is in a file that says so

A first pass walked every numbered directory and found **122**. Fifty-two were
`.benchmarks/`, where the leading number is the **owning plan or issue** and a
family per owner is the intended convention (`010_*` ×5 are all Issue 010's
benches). `scripts/numbering_floors.txt` records that exclusion, measured
2026-09-04, in the file, with the note that a duplicate check there *"would have
produced ~55 findings, all false, and been the cries-wolf instrument AGENTS.md
warns gets ignored."*

The scope now comes from that pins file rather than from a walk. **A population
derived from the tree is not the population the gate governs**, and the
difference here was 74% inflation into the exact false-positive class somebody
had already measured and written down.

## Tasks

- **T1 — `removed_by_number()`** (`citation_weight.py`). One `git log -M
  --diff-filter=D` per directory; `removed_candidates()` is its single-number
  view and delegates. ⚠ `-M` is load-bearing: without rename detection a
  RENUMBERED document reports as a deletion at its old number and the tool
  resurrects a collision somebody already resolved.
- **T2 — the verdict, in two regimes** (`numbering_gate.py` +
  `scripts/number_collisions_expected.txt`).
  - **At or above `era_boundary = 700`: a WALL, pinned by MEMBERSHIP with a
    reason per row.** A new collision there is a live ambiguity in prose people
    are writing today. Membership, not a count — a count is green on a swap,
    and the arms assert exactly that case.
  - **Below it: a RATCHET, counted and never pinned.** Those 61 are the
    pre-gate archive (`.issues/121`'s number-recycling era). Adjudicating them
    is a backlog, and Issue 785's rule forbids ratcheting a bucket that means
    "unread" — so they are counted, may not grow, and carry no invented
    reasons. A count that DROPS is a note, not a failure: refusing the commit
    that resolved a collision would be the gate punishing the repair.
  - The boundary is measured, not chosen for roundness: the highest legacy
    collision is 575 and the lowest divergence one is 741, so nothing sits
    between them and no row is on the wrong side of it by a judgement call.
  - Two blindness floors (`min_dirs`, `min_numbers`) — every verdict above is a
    ceiling, and a git-history regression empties the population and passes all
    of them.
- **T3 — the six that were NOT renumbered, and why that is the finding.**
  791 renumbered its three (→ 792/793/794). The remaining six were adjudicated
  and deliberately left alone:

  | n | lead | decided | UNRESOLVED | verdict |
  |---|---|---|---|---|
  | 741 | +21 | 26 | 32% | clear, but both sides CLOSED |
  | 775 | +13 | 28 | **53%** | instrument DECLINES (unresolved > decided) |
  | 777 | +5 | 36 | 27% | under the margin worth 36 rewrites |
  | 778 | +1 | 18 | 36% | **TIE** by the tool's own `TIE_FRACTION` |
  | 781 | +2 | 17 | 47% | noise, not a verdict |
  | 782 | +4 | 11 | 21% | 3-site loser, below the threshold |

  ⛔ **Renumbering on a 2-site lead with 47% unresolved would be applying a rule
  past the point where it measures anything** — the mistake `TIE_FRACTION`'s own
  docstring names: *"pretending it can arbitrate is how a coin flip gets
  recorded as a measurement."* The pin file records the margin per row, so the
  decision is re-readable rather than remembered.

- **T4 — DEFERRED on a missing measurement.** 791 T3 proposed a gate that reds
  when a commit allocates a number its remote parent already allocated. Its
  false-positive rate is unmeasured, and a long-lived branch legitimately
  allocates ahead of its remote — this repo's own divergence was 57 commits.
  ⚠ Note what T2 already buys: the collision is caught on the commit that
  MERGES, which is late but not silent, and is the first time anything catches
  it at all. Measure the FP rate before adding a second, earlier gate.

## What this cost to find, recorded because it repeats

Both 791 and this issue were found by *pointing an instrument at one more case*
rather than by a symptom. 791's table was written from three known pairs;
nothing asked whether there were others, because the tool that would have
answered was blind in the direction that mattered. **A census is exhaustive over
ROWS, not over the ORACLE it checks them against** (Issue 754's sentence,
holding for a third time).

Arm reach: `numbering_gate` 7 killed of 48 → **22 of 47**, survivors 17 → 2.
⛔ Both this gate's arms and `citation_weight`'s were written, passing, and
reaching NOTHING until they were moved out of `main()` and into `selftest()` —
`arm_reach_audit` invokes an arm only by the names in its vocabulary. Measured
twice in one session, which is why it is written here and not remembered.
