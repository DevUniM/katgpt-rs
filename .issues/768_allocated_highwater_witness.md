# Issue 768: `allocated()` has no `.highwater` witness — highwater-only allocations are invisible to the citation instruments

**Status:** OPEN — filed from the Issue 766 mis-repair arc (HISTORY 2026-09-13); no code touched yet.
**Origin:** `4573af13` "qualified" a correct LOCAL citation (katgpt-rs HISTORY's bare `## Issue 766 resolved — …` heading) to riir-ai because `allocated()` could not see katgpt-rs's own allocation: `e4792a4b` bumped `.issues/.highwater` 765→766 with the issue file never committed (file-and-resolve, the Issue 754 invisible class) and the heading was not in the `## Issue NNN (date)` form `heading_allocated()` reads. Two sessions stumbled on the same blind spot in one day — the 4090 session wrote the bare heading, the M3 gate session mis-repaired it.

## The gap

`allocated(repo, subdir)` (scripts/issue_citation_gate.py) resolves ownership from three witnesses: worktree files, `git log` history, and `heading_allocated()` (Issue 754). A fourth witness — the committed, monotone `.highwater` counter — is consulted by NOTHING on the ownership path, even though the sweep already trusts it for the IN-LOCAL-RANGE class's "local top". Per the Numbering Discipline (read value+1, write back; numbers contiguous and never reused), `n <= highwater` implies `n` was allocated in that repo. Today such numbers are invisible until a `.issues/NNN_*.md` file or a readable heading exists — and the failure mode is not a missed finding but an INVERTED one (a correct local citation "repaired" into a wrong cross-repo address).

## Tasks (measure before widening — the `_SELF_HEADING` law, Issue 754)

- [ ] T1 — measure the reclassification: run the sweep before/after a prototype highwater witness over all 20 contract repos; enumerate every row that changes class (CROSS→valid, CROSS→AMBIGUOUS, IN-RANGE→AMBIGUOUS, ORPHAN→AMBIGUOUS). No landing without this table.
- [ ] T2 — dual-allocation honesty: with the witness, BOTH repos of a dual (katgpt-rs 766 + riir-ai 766) read as owners, so a wrong-referent attribution (`riir-ai Issue 766` naming the August holding queue while meaning the len_derived issue) validates. Document the residual blind spot in the sweep footer — owner-consistency is only as sound as `allocated()`.
- [ ] T3 — counter semantics audit: confirm every contract repo's `.highwater` is contiguous-by-discipline across its git history; decide and document whether a bumped-without-filing counter still SPENDS the number (the working assumption: yes — monotonicity is the discipline's own rule, and the `.issues/121` collision precedent says intra-repo dual-allocation creates no gaps).
- [ ] T4 — land behind the measured table; re-pin any floors the reclassification moves (cross/orphan ceilings fire upward only, so they cannot red from suppression; IN-LOCAL-RANGE pins may fall as rows graduate to AMBIGUOUS — re-pin in the landing commit with the reason).

## Design note (filed with the arc, 2026-09-13)

There are TWO places the witness could land, and they are not equivalent:

- In `mine` (the local-allocation set): collapses every IN-LOCAL-RANGE row to
  "local, no finding" — but IN_RANGE exists precisely to hold that
  undecidability OPEN (a bare `513` under a local top of 617 may mean
  riir-train's). This direction SUPPRESSES real signal and is presumed WRONG
  until the measured table says otherwise.
- In `owners` (sibling ownership for QUALIFIED citations only): a named repo
  whose highwater covers `n` reads as an owner, so MISATTRIBUTED/MISLEADING
  verdicts soften — including FALSE validations in dual allocations
  (`katgpt-rs Issue 513` would validate because katgpt-rs, contiguous to 768,
  spent a 513 long ago, while the prose means riir-train's). Bounded to
  named-attribution rows; this is the T2 risk the table prices.

Start from the owners-side prototype; take the mine-side variant only if the
 table shows it buys rows the owners-side cannot.

## Non-goals

- Topical referent verification ("does the named repo's issue MATCH the prose's subject") — out of scope forever per the 752 doctrine; the instrument validates addresses, not meanings. The 766 arc's wrong-referent RISK (T2) is documented, not solved.
