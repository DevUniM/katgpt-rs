# Issue 780 — a wrong address whose number is IN-LOCAL-RANGE reads as UNDECIDED: `⛔MISATTRIBUTED` is computed only in the CROSS bucket

**Filed:** 2026-09-14 · **Status:** OPEN · **Scope:** `scripts/issue_citation_gate.py`,
`scripts/citation_drift_sweep.py` · **Class:** Issue 749 / 752 / 754 family

## The defect

`is_qualified()` (Issue 752) fixed the question *"is a repo named?"* → *"does
that repo **own** the number?"*, and the gate annotates the answer:

```python
bad = adj - set(owners)
if cls is CROSS and bad:
    got["misattributed"] += 1
    tag = "⛔MISATTRIBUTED: names X, which does NOT own N"
```

`cls is CROSS` is the bug. The three-way bucketing runs **first**:

```python
cls = (IN_RANGE if n <= top[kind] else CROSS if owners else ORPHAN)
```

so a citation that carries an **explicit attribution sitting ON it** to a repo
that does not own the number is silently reclassified as IN-LOCAL-RANGE —
"UNDECIDED, never clean" — whenever the number happens to fall under the
document's own repo ceiling. It is never counted, never tagged, and never
gated. The gate's own `is_qualified` docstring cites `katgpt-rs Issue 513` as
one of the eight explicit wrong addresses the Issue 752 census found; the
workspace still carries an instance of exactly that string, and this is why.

**IN-LOCAL-RANGE's premise is refuted by the row itself.** The bucket exists
because "a local referent that was skipped or never committed is plausible" —
but this row reaches the bucket only when `n not in mine[kind]`, i.e. the
oracle that reads worktree **and** `git log` **and** headings (Issue 754) found
no local allocation, *and* the author wrote a different repo's name directly on
the citation. Both halves of the plausibility argument are gone.

## The finding it hides (1, workspace-wide, hand-verified)

`riir-neuron-db/AGENTS.md:82`

```
# Workstation-only pre-push layer (katgpt-rs Issue 513 T6): the
# required-features rows this branch TOUCHES must build at their own
# feature set. …
./scripts/required_features_touched.sh
```

- katgpt-rs has **never** allocated 513 (`git log --all -- '.issues/513*'` is
  empty; `.highwater` 779).
- **riir-train** owns it — `.issues/513_required_features_rows_are_unverified.md`,
  filed `389a0a6b`, closed+removed `5a4265df`.
- Its **T6** is this exact paragraph's subject, by name:
  *"T6 — BLOCKED ON OWNER CALL (Actions spend) … 2026-09-11 owner verdict:
  DECLINED for riir-neuron-db … the workstation `required_features_touched.sh`
  layer already covers it (ndb guard's last layer, loud-skip under `$CI`); ndb
  CI is main-only anyway."*

riir-neuron-db's own top allocation is 617, so 513 ≤ 617 and the row landed in
IN-RANGE. Correct address: **`riir-train Issue 513 T6`**.

## The boundary is MEASURED, and it is not the obvious one

The same predicate has a second place it could go — the `n in mine[kind]`
short-circuit, where a locally-allocated number carries an adjacent sibling
name. Measured over 16 repos × `AGENTS.md`+`HISTORY.md` (~3k citations),
after `is_qualified` clears the rows some named owner covers:

| bucket | rows | hand-read verdict |
|---|---|---|
| `n <= top` (IN-RANGE) | **1** | 1 true finding, 0 false |
| `n in mine` (locally allocated) | **19** | **19 false, 0 true** |

The 19 are one shape: the prose is *contrasting* a local number with a remote
one, and the 40-char lead catches the neighbour's address —
``riir-ai Issue 853 / this repo's Issue 093``, ``riir-ai Issues
574/589/537/672 + local Issue 059``, ``in `riir-neuron-db/src/local_kv.rs`
(Issue 043``, ``at `riir-game-sdk/crates/riir-games-cluster/`. Plan 010``.
The mechanism is what makes the asymmetry principled rather than lucky: when
the number **is** local there is a local referent for the prose to contrast
against, so an adjacent repo name is most likely the *other* citation's
address. When the number was never allocated locally there is nothing to
contrast with.

So the rule extends to IN-RANGE **only**, and the local-allocation
short-circuit stays exactly as it is — with the 19-row measurement recorded so
the exemption is a finding rather than an oversight. ⚠ The IN-RANGE column is
`n = 1`: "0 false positives" there is one row's worth of evidence, not a rate.

## Tasks

- [ ] **T1** — compute `bad = adj - owners` for the IN-RANGE bucket too and
      emit it as its own class (`MISATTRIBUTED-IN-RANGE`), never pooled into
      CROSS: CROSS is "unfollowable", this is "followable to the wrong place".
- [ ] **T2** — same rule in `issue_citation_gate.py` (the per-push verdict),
      pinned separately from `max_cross` so a regression names which half moved.
- [ ] **T3** — self-test arms in both halves, including the negative: a row
      whose adjacent name DOES own the number stays clean, and a
      locally-allocated number with an adjacent sibling name is NOT promoted.
- [ ] **T4** — repair `riir-neuron-db/AGENTS.md:82` → `riir-train Issue 513 T6`.
- [ ] **T5** — pin both halves at the post-repair measurement.
