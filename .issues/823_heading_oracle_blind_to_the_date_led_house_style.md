# Issue 823 (2026-09-17) — the heading oracle was anchored to a POSITION, and its own blindness meter was anchored to the same one

**Status: RESOLVED same day (T1–T4). T5 open.**

## The symptom

`citation_drift_sweep.py` red: `riir-clippy IN-LOCAL-RANGE 13 > pinned 12`.

The pin had been bumped `10 -> 12` the **previous day** (2026-09-16), with the
mechanism diagnosed correctly in the pin comment:

> Both new rows are riir-clippy's OWN Issue 113 … They read UNDECIDED because
> `heading_allocated()` cannot parse that repo's `## <date> — Issue NNN:`
> heading form … the repair is that repo's heading convention, which is its
> owner's call.

Twenty-four hours later the bucket was 13. That is AGENTS.md's own warning
made literal — *a pin file re-typed after every run is a diary, not a wall,
and re-typing it is how a real regression gets absorbed as "probably the box
again"*. The second bump was refused and the instrument was read instead.

The last clause of that diagnosis is also the part that was wrong: it is not
that repo's convention. Six repos write it, 74 records deep.

## The defect, and it is TWO defects stacked

**(a) The oracle.** `_SELF_HEADING` is sound because of exactly one rule:
nothing may sit between the number and its delimiter, so `## Issue 043
follow-up (…)` is rejected while `## Issue 043 (…)` is read. That rule is
about the text **after** the number. It had been anchored, silently and
incidentally, to the kind **leading the heading**. Six repos write the date
first (`## 2026-09-16 — Issue 113: the auto-oracle`), and the whole family was
unreadable.

Consequence chain, measured end to end on a live specimen: riir-clippy's
Issue 113 exists in **no** `.issues/` file and **no** `git log` deletion — the
Issue-754 shape, where the HISTORY.md heading is the *whole* allocation record.
The oracle could not read it, so `113 not in mine`, so both citations of it
fell to IN-LOCAL-RANGE, so a per-repo **ratchet breached** and the sweep went
red. `.highwater` says 121: the repo provably owns the number.

**(b) The meter, which is the worse half.** `_HEADING_SHAPED` exists *only* to
measure what the oracle rejects — the width bound whose whole job is printing
the cost of (a). It was anchored to the **same leading position**, so it could
not see the family either, and it failed in the direction that reads as clean:

| repo | meter printed | actually unread |
|---|---|---|
| riir-chain | `heading_unread=0/1` — a **perfect** score | **20 of 21** |
| riir-dapps | `0/0` — nothing to measure | **22 of 23** |
| riir-clippy | 30 unread | 54 |

A blindness detector that cannot see a whole house style is not a width bound.
Workspace-wide it admitted **245** records where **341** exist.

## The repair (T1–T3)

`_SELF_HEADING_DATED` / `_HEADING_SHAPED_DATED` — the **same discriminator**,
at the position it was never applied. The number must be followed immediately
by its title delimiter (`:` or `,`, the date-led form's `(`).

⛔ **This is NOT the widening AGENTS.md calls unsound, and the distinction is
the entire justification.** That argument is against *dropping the
discriminator* — accepting `resolved` / `follow-up`, which no punctuation rule
separates from an allocation. Measured on the live corpus, the new pattern
rejects `## 2026-09-16 — Issue 152 resolved: …` and `## 2026-09-16 — Plan 064
T3 landed (…)` exactly as the leading form rejects their siblings. Arm 2's
pinned negative survives — **in both positions**, asserted by two new arms.

The foreign-repo filter runs over the whole date-led remainder rather than a
parenthetical: strictly more likely to reject, the safe direction for the only
path in this gate that can SUPPRESS a finding.

18 records became readable. Every one was read by hand at landing; all 18 are
genuine self-allocation records. Measured effect:

- workspace IN-LOCAL-RANGE **54 -> 27**
- oracle **110/319** read (was 92 read of a 245 the meter believed was the
  whole population)
- `riir-clippy` 13 -> **11**, `riir-neuron-db` 3 -> **2** — both ratchets
  **tightened** in the landing commit, never loosened
- `citation_drift_sweep.py` **PASSES**

## T4 — the stale prose

The sweep's own summary line asserted "Widening is UNSOUND" without the
qualifier that makes it true, and so did the comment on `_HEADING_SHAPED`.
Both now say which widening: dropping the discriminator, not adding a
position. A correct claim stated too broadly is how the next session concludes
the class is closed.

## T5 — OPEN: the residual 209, and the number this issue should NOT be read as

209 records remain unread, and they are the `## Issue NNN resolved — title
(date)` family the original Issue 781 measured. **This issue does not touch
them and must not be read as having closed Issue 781's class** — it removed a
*position* blind spot that was hiding underneath it, and in doing so made 781's
own figure honest for the first time (the denominator was understated by 96).

Open question, deliberately not answered here: whether the `resolved —` family
admits a sound discriminator at all. AGENTS.md's answer is no, and nothing
measured here contradicts it.

⚠ **Do not re-pin `max_in_local_range` for a heading-blind row again.** Two
sessions have now done it. The row is not a backlog entry; it is the instrument
reporting that it cannot read a record the repo owns. Read
`heading_unread=a/b` on the sweep's own per-repo line first — a repo at or near
`b/b` cannot have its IN-LOCAL-RANGE count trusted as an editorial quantity.

## Cross-repo

Nothing to file elsewhere. The defect and its repair are both in this repo's
`scripts/`; the six affected repos need no prose change, which is the point —
the previous diagnosis would have asked all six to rewrite their HISTORY.md
heading convention.
