# Issue 781 — the heading oracle matches one house STYLE, and three repos' entire convention is invisible to it

**Filed:** 2026-09-14 · **Status:** OPEN · **Scope:**
`scripts/issue_citation_gate.py` (`_SELF_HEADING` / `heading_allocated`),
`scripts/citation_drift_sweep.py` · **Class:** Issue 754 family

## The measurement

`heading_allocated()` (Issue 754) recovers numbers whose file was created and
removed without an intervening commit — the repo's own heading is then the
whole allocation record. Its pattern anchors the parenthetical **immediately**
after the number:

```python
_SELF_HEADING = re.compile(
    r"^#{2,}\s+(?:\*\*)?(%s)\s+0*(\d{2,4})\s*\(([^)\n]*)\)" % "|".join(KINDS))
```

So it reads `## Issue 042 (2026-01-01) — resolved` and not
`## Issue 097 resolved — … (2026-09-12)`. Measured over 16 repos ×
AGENTS.md+HISTORY.md, against a loose `^#{2,}\s+(?:\*\*)?<Kind>\s+0*(\d{2,4})\b`:

| repo | heading-shaped | accepted | missed |
|---|---|---|---|
| riir-mmorpg-examples | 46 | **46** | 0 |
| seal-remake | 17 | 16 | 1 |
| katgpt-rs | 31 | 8 | **23** |
| riir-ai | 25 | **0** | 25 |
| riir-clippy | 25 | **0** | 25 |
| riir-train | 14 | **0** | 14 |
| riir-game-sdk | 2 | 0 | 2 |
| **total** | **160** | **70** | **90** |

**56% of the record is outside the oracle**, and it splits by *house style*,
not by correctness: riir-mmorpg-examples writes `## Issue NNN (date) — title`
and scores 46/46; riir-ai, riir-clippy and riir-train write
`## Issue NNN resolved — title (date)` and score **0 of 64**. katgpt-rs is
mixed (8/31) — its own newest closes, Issues 777–780 included, are in the
style its own instrument cannot read.

## Why this is a REPORT and not a repair

The obvious fix — accept a trailing parenthetical anywhere in the heading — is
**unsound, and the existing self-test already proves it.** Arm 2 pins
`## Issue 043 follow-up (2026-01-01) — about a FOREIGN number` as a measured
NEGATIVE: a heading that comments on a number is not an allocation of it, and
crediting it would absolve a wrong address. `043 follow-up (…)` and
`097 resolved — … (…)` are the **same shape**. No punctuation rule separates
them; the distinction is semantic. A widened pattern was run end to end and
fails that arm, which is the arm doing its job.

This path is also the only one in the instrument that can **suppress** a
finding, so a speculative widening trades a reported blind spot for an
unreported one.

## The consequence, in both directions

- **Incomplete LOCAL set** → a correct local citation lands in
  IN-LOCAL-RANGE ("UNDECIDED, never clean") instead of being skipped. This is
  visible today: riir-clippy's 10 undecided rows are `Issue 013/027/029/097`,
  every one of them recorded in its own HISTORY.md as
  `## Issue 0NN resolved — …` or `**Issue 0NN (date, RESOLVED same day +
  removed per noise-reduction rule)**`. Noise, not a hidden finding.
- **Incomplete OWNERS set** → a correctly-qualified citation reads as naming a
  repo that does not own the number: a **false** `⛔MISATTRIBUTED`. That is
  Issue 754's exact failure, and Issue 780's new `MISATTRIBUTED-IN-RANGE`
  class inherits it. 0 live instances today (CROSS 1, MISATTRIBUTED 0), so
  this is latent — which is precisely why it must be *printed* rather than
  remembered.

## Tasks

- [ ] **T1** — measure the blind spot every run and print it next to the
      verdict, per repo and in total: heading-shaped self-records that name no
      foreign repo and that `_SELF_HEADING` rejects **on style alone**. A
      triage quantity with the standing of AMBIGUOUS and the width-bound
      complement — never a verdict, never folded into a finding count.
- [ ] **T2** — a self-test arm, because a probe wired to nothing also reports
      0 (Issue 753). Both directions: the accepted style must NOT count, the
      rejected one must.
- [ ] **T3** — record the style split in AGENTS.md so `allocated()` is never
      read as complete, and so a future widening starts from arm 2 rather than
      from the pattern.
