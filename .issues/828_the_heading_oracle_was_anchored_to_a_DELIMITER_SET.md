# Issue 828 (2026-09-18) — Issue 823's anchor class, third position: the heading oracle was anchored to a DELIMITER SET, and the biggest unread family is this repo's own house style

**Status: RESOLVED same day (T1–T3). T4 = Issue 823 T5's residual, unchanged.**

## The symptom

Issue 823 T5 left one open question and one number:

> Open question, deliberately not answered here: whether the `resolved —`
> family admits a sound discriminator at all. AGENTS.md's answer is no, and
> nothing measured here contradicts it.

The number — read off the sweep, never typed — was ~213 unread heading
records. **T5 was answered by measuring the residual instead of arguing about
it, and 60 of the 213 are not the `resolved` family at all.**

## The finding

`_SELF_HEADING` is sound because of ONE rule, written in its own comment:

> nothing may sit between the number and its delimiter

Issue 823 found that rule anchored, silently, to the **kind LEADING the
line**, and moved it one POSITION over. It was anchored a second time, to the
**delimiter SET** — `(` for the leading form, `[:,]` for the dated one. The
workspace's most common title delimiter is the **em dash**, and it was in
neither set.

Measured (16 repos × the pinned documents, foreign-filtered, unread only):

| first char after the number | n | verdict |
|---|---|---|
| `—` (leading form) | **56** | delimiter, nothing interstitial — **sound to read** |
| `(` (dated form) | **4** | the leading form accepts it; the dated one did not — **sound to read** |
| `resolved` / `RESOLVED` | 64 | genuinely interstitial — Issue 781's family, untouched |
| `closed` / `close-out` / `CLOSED` | 28 | interstitial |
| `T1` … `T8`, `Arm`, `wave`, `phase`, `complete` | ~45 | interstitial |
| `follow-up`, `filed` | 3 | interstitial — the **pinned negative** |
| other | ~13 | interstitial |

The 56 are `## Issue 788 — the population-predicate registry …: CLOSED
(2026-09-14)`. That is **katgpt-rs's own house style, its own newest closes**,
in the repo that owns the instrument. The discriminator was never violated by
them; the pattern simply could not spell their delimiter.

⛔ **This is NOT the widening AGENTS.md calls unsound**, and the distinction is
Issue 823's, restated at a third position: the unsound widening is *dropping
the discriminator* (accepting text between the number and its delimiter). This
adds a delimiter and keeps the rule. `## Issue 043 follow-up — title` is
rejected by the new pattern exactly as `## Issue 043 follow-up (…)` is rejected
by the old one, and T2 pins that in both delimiters.

## T1 — the delimiter set

- `_SELF_HEADING_DASH`: the same discriminator, either position (the date
  prefix is optional), delimiter = `—`/`–`, or an ASCII `-` **that is
  space-separated on both sides**.
  - ⛔ The ASCII hyphen must NOT be accepted bare: `## Issue 366-class
    (pos-uniform chunk forward) FIXED in riir-gpu` is a live riir-ai heading
    where the hyphen is part of a WORD. The `\s+…-(?=\s)` shape rejects it and
    an arm pins the case.
- `_SELF_HEADING_DATED` gains `(` — the leading form always accepted it, and
  four riir-chain records (`## 2026-09-16 — Plan 062 (Proposal 010 D6/T1.2):`)
  were rejected by an asymmetry between two patterns documented as the same
  rule at two positions.
- The new pattern's group(3) is the **whole remainder**, the dated form's
  precedent, not the leading form's parenthetical: the foreign filter then runs
  over more text, which is strictly more likely to REJECT — the safe direction
  for the only path here that can SUPPRESS a finding.
  - ⛔ `_SELF_HEADING`'s own scope is deliberately **left alone**. Widening it
    to the whole remainder would reject `## Issue 059 (2026-01-01) — <sibling>
    did X`, which is the suppression Issue 754 landed; the "safe direction" for
    a NEW pattern is a regression for an existing one.

## T2 — the arms

`citation_drift_sweep.selftest()` arm 2, the four-negative fixture, gains the
delimiter axis on the SAME fixture rather than a second one:

- `## Issue 047 — title` reads (the new positive).
- `## Issue 048 follow-up — title` does **not** (the discriminator survives the
  new delimiter — the arm the whole issue rests on).
- `## Issue 049-class — title` does **not** (the bare ASCII hyphen).
- `## 2026-01-01 — Issue 050 (parenthetical): title` reads (the dated `(`).

The style-blind meter's expected pair moves with the fixture, so the width
bound still measures exactly the style gap.

## T3 — the numbers move in the SUPPRESSING direction only

`heading_allocated()` can only ever suppress. More numbers read ⇒ fewer
IN-LOCAL-RANGE rows and fewer false `⛔MISATTRIBUTED` — every ratchet in
`citation_drift_floors.txt` goes green-er or holds. Re-pinning a ratchet
DOWNWARD is deliberately **not** done here: they are ceilings, and tightening
them on one box's run is the diary AGENTS.md refuses.

## T4 — OPEN, and it is Issue 823 T5 verbatim

The ~153 genuinely interstitial records stand. The open question is unchanged
and this issue must not be read as having narrowed it: `resolved`, `closed`,
`T3`, `Arm C` and `follow-up` are the same SHAPE, no punctuation rule separates
them, and the distinction is semantic. What changed is the **denominator** —
60 rows that were being counted against that question were never part of it.

⚠ Read the live figure off `citation_drift_sweep.py`'s own `heading oracle`
summary line. A number typed here is a claim about one run.

## ⛔ The arm that could not pass, and why it is a separate issue

T2's first run reported `(1, 5)` where `(3, 6)` was expected — 047 unread, 050
not even *shaped* — while the same fixture, written by hand in a scratch
script, returned `(3, 6)` and `{42, 47, 50}`. The fixture in
`citation_drift_sweep.selftest()` is written with a bare `Path.write_text(...)`,
which encodes with the **system locale**. This workstation is **cp874**, where
U+2014 encodes to the single byte `0x97`; the oracle then reads the file back
with `encoding="utf-8", errors="replace"` and sees U+FFFD. Every em dash in
every selftest fixture in that file was mangled.

The existing arms passed anyway — none of them depended on the dash — so the
corruption was invisible until an arm was written that did. **27 sites in that
one file; 155 in this repo; 273 across 8 repos**, measured. That is **Issue
829**, filed with its own gate; the 27 sites in `citation_drift_sweep.py` land
here because T2's arms are not real without them.
