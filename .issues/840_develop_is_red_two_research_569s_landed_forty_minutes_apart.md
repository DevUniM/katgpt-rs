# Issue 840: `origin/develop` is RED — two `.research/569` documents landed, and one defect trips two independent detectors

**Status:** **RESOLVED 2026-09-18** — T1/T2/T3 all landed by `katgpt-rs-fa` after both
live peers confirmed neither document was theirs. `numbering_gate.py` passes and **both
rows cleared together**, which is T3's own assertion holding. No pin was touched.
⛔ T2's premise was WRONG in the safe direction and the correction is the finding: the
rewrite set is **EMPTY**, not 3 sites — see §T2.

**Found by:** an ordinary `git fetch` during Issue 833 T3 work, 2026-09-18 ~23:15. Not
by a gate — no lane runs on `develop` pushes (AGENTS.md § Trigger health: CI is
MAIN-ONLY + dispatch-only since 2026-09-09), so nothing automatic was ever going to
report this.

## The defect

Two commits each added a `.research/569_*.md`:

| commit | time | file |
|---|---|---|
| `a4277fb7` | 22:42 | `569_Hadamard_MLP_Monarch_Kronecker_FFN.md` |
| `d41d4c43` | later | `569_SAN_Attention_Only_FFN_Deletion_Cost.md` |

`.research/.highwater` reads **569**, and the **per-commit diffstats settle which of
those two it was** — the first version of this paragraph said "skipped or raced" and the
hedge was unnecessary:

| commit | files changed |
|---|---|
| `a4277fb7` 22:42:41 | 4 — `.issues/.highwater`, `.issues/839_*.md`, **`.research/.highwater`**, `569_Hadamard_*.md` |
| `d41d4c43` 22:45:53 | **1** — `569_SAN_*.md`, and nothing else |

**Not a race.** Hadamard did the read-and-write-back correctly and bumped the counter;
SAN three minutes later added a file and never touched `.research/.highwater` at all. So
`.research/.highwater = 569` is **Hadamard's own correct value**, and the structural rule
below is not merely arbitration-free — it is the reading the commits themselves support.

## Verified against origin/develop, not reasoned about

`git worktree add --detach F:/scratch/kg569 origin/develop`, then the gate in that tree:

```
✗ 1 TRACKED duplicate number(s) (pinned ≤ 0):
    .research/569 ×2: 569_Hadamard_MLP_Monarch_Kronecker_FFN.md · 569_SAN_Attention_Only_FFN_Deletion_Cost.md
✗ 1 HISTORICAL numbering collision finding(s) …
    legacy collisions 62 > ratchet 61 — a number below the era boundary was allocated twice AGAIN
rc=1
```

**`numbering_gate.py` exits 1 on `origin/develop`,** so `docs_gate.sh` is red there for
everyone. It is one of the 29 CHECKS.

⛔ **ONE defect, TWO findings, and they are not two views of one quantity** — that
distinction is the whole of Issue 820 and the gate prints it. The legacy set was diffed
between this checkout (61) and `origin/develop` (62) rather than inferred: the single
new member is `.research/569`. So repairing the duplicate clears both rows, and **no pin
should be touched for either**. `max_duplicate_numbers = 0` is a WALL, not a ratchet, and
`legacy_ratchet = 61` must not be re-typed to 62 — that is this repo's own *"a pin file
re-typed after every run is a diary, not a wall"*, and it would absorb a live collision
as history.

## Why this was NOT fixed here

`citation_weight.py` was run, because AGENTS.md § Numbering Discipline says the holder
with the most inbound mentions keeps the number:

```
569_Hadamard_MLP_Monarch_Kronecker_FFN    by-name 0   attributed 2
569_SAN_Attention_Only_FFN_Deletion_Cost  by-name 0   attributed 0
UNRESOLVED 1 (33% of sites)
→ VERDICT: Hadamard leads by 2 over 2 decided site(s)
```

A **2-site lead over 2 decided sites with 33% UNRESOLVED** is precisely the margin
AGENTS.md names as not worth acting on — *"Renumbering on a 2-site lead with 47%
unresolved is the mistake `TIE_FRACTION`'s own docstring names"* — and the instrument
prints its own warning that the loser's ZERO is not evidence nothing cites it. Neither
document belongs to this session, and the `.issues/779` pin records the standing
precedent directly: *"renumbering OPEN work needs agreement"*, which is why that
collision was resolved by moving **this** session's side rather than the other's.

This session also cannot push (owner-gated), so a local repair would not unbreak
`develop` for anyone; what it would do is race whichever session owns those documents.

## The repair, for whoever owns them

1. **`d41d4c43` (SAN) moves to 570.** This no longer rests on the thin citation margin
   at all — the diffstat above shows the first allocation did the whole documented
   procedure and the second did not touch the counter. Proposed independently by
   **katgpt-rs-fa** as a structural rule needing no arbitration, and confirmed by this
   evidence; ownership was checked across sessions first (neither document belongs to
   katgpt-rs-54 or katgpt-rs-fa).
2. `.research/.highwater` → **570**.
3. Rewrite the loser's inbound `Research 569` citations — there are 3 ambiguous sites and
   1 is UNRESOLVED, so this is a hand read, not a `sed`.
4. Re-run `py scripts/numbering_gate.py`; **both** rows must clear together. If only the
   tracked-duplicate row clears, the legacy diff above was wrong and should be re-taken.

## Tasks

- [x] **T1 — DONE.** `569_SAN_Attention_Only_FFN_Deletion_Cost.md` → `570_…`, its own
      title line `# Research 569:` → `570`, and `.research/.highwater` → **570**. A
      `git mv` so the rename is recorded as one (`-M` reads it as a rename, which
      `removed_by_number()` depends on — without it a renumber reports as a deletion at
      the old number and a later scan resurrects a collision somebody already resolved).
- [x] **T2 — DONE, and the rewrite set was EMPTY.** See §T2 below.
- [x] **T3 — DONE, ratchet NOT bumped.** `legacy_ratchet = 61` is untouched and the gate
      returns `71 historical over 1433 numbers, 10 pinned above the era boundary` —
      71 − 10 = **61**, exactly the ratchet. So no second historical collision was
      hiding behind this one, and the legacy diff in §The defect was right.

## ⚠ The standing gap this exposes, which is NOT this issue's to fix

Nothing ran. `docs_gate.yml` is `branches: [main]`, and both commits went to `develop`.
The collision was found by a human-equivalent `git fetch` forty minutes after it landed,
and `dual_allocation_gate.py` could not have caught it either — that gate compares **this
checkout against its upstream**, and here *both* sides are upstream, which is the reach
limit its own write-up records (*"box-vs-box collisions on the wire are the merge-time
wall's jurisdiction"*). The merge-time wall is `numbering_gate`, and on a develop-only
push there is no merge and no lane. See `scripts/ci_gate_coverage.py` and AGENTS.md
§ Trigger health; the Actions spending call is the owner's and stands.

## 2026-09-18 — cross-session resolution, and a shared-worktree note

`katgpt-rs-fa` proposed the structural rule independently and asked both peers whether
either owned a document. **Neither does** — katgpt-rs-54's five commits (`d8bfa9b8`,
`dd8dadbb`, `b5dd81dc`, `f49d4e64`, `d7a34822`, each carrying `Session: katgpt-rs-54` in
its body) touch `scripts/`, `AGENTS.md` and `.issues/` and **none touches `.research/`
at all**. The repair is katgpt-rs-fa's, with the side to move settled by evidence rather
than by the margin `citation_weight` declined to arbitrate.

⛔ **This issue was filed by `katgpt-rs-c5`, not by katgpt-rs-54**, who only inherited
commit `6b911ef3` when the shared worktree was rebased. An earlier draft of this section
said "katgpt-rs-54's ten commits" and implicitly treated that session as the author and
therefore the best witness to 22:42; it was neither, and c5 has since ended. Corrected
here because the mistake is this issue's own subject one level up — **an anonymous commit
made a session's own contribution unidentifiable, including to a reader trying to credit
it.**

⚠ **This worktree was REBASED onto the collision while the issue was open.** It is
shared between sessions, so katgpt-rs-54's HEAD moved from `6b911ef3` to `c4bed8f1`
without that session running a rebase, and its checkout now carries both `569` files —
`numbering_gate.py` exits 1 locally as well. That is the gate working, not a second
defect, but it means **`docs_gate.sh` cannot go green in any checkout here until T1
lands**, and a session that reads a red docs gate in the interim should check this issue
before diagnosing its own change.

## T2 — the rewrite set is EMPTY, and the estimate was wrong in the SAFE direction

This issue told the repairer to *"rewrite the loser's inbound `Research 569` citations —
there are 3 ambiguous sites and 1 is UNRESOLVED, so this is a hand read, not a `sed`."*
The hand read was done and **no citation needed rewriting at all.**

The three sites are all in `.issues/839_kronecker_tile_matvec_primitive.md` — its title,
its Status line, and T8. That file is titled *"Kronecker-tile matvec primitive
(`kron_apply`) — Hadamard-MLP fusion (Research 569)"*, so every mention in it refers to
**Hadamard**, which is the side that KEEPS 569. The one `citation_weight` left
UNRESOLVED (T8's *"cross-link Research 569"*) resolves the same way on a read, for the
same reason: the enclosing document is about Hadamard end to end.

⛔ **The reason to write this down is that the error had a direction.** `citation_weight`
reported `Hadamard attributed 2 / SAN attributed 0` and the issue read the 0 as *"the
loser's ZERO is not evidence nothing cites it"* — correctly, as a caution. But the
caution was then carried into the repair plan as work to do, and the *actual* count of
SAN-inbound citations is zero for the ordinary reason: the document was three minutes
old. A repair estimate inherited from an instrument's own hedge is not a measurement.
Checked in both directions before calling it empty — `git grep` for `Research 569`, for
the `research/569` LINK-PATH form (peer `katgpt-rs-54`'s warning from the riir-ai 975/976
renumber, where a prose-only grep left a stale citation behind), and for SAN's
distinctive title tokens across `*.rs` and `*.md`. The only surviving `569_SAN` strings
are inside THIS issue, where they are the historical record of the collision and are
correct as written.

⚠ **Two things in the paragraph above must not be pooled, and only one of them was
wrong.** The *"3 ambiguous sites, a hand read not a `sed`"* estimate is THIS ISSUE's
(filed by `katgpt-rs-c5`) and it was a prediction about what the read would find.
`katgpt-rs-54`'s *"worth one targeted grep across `*.rs` and `*.md` link targets before
calling it done"* is a different kind of statement — a hedge recommending a CHECK, which
an empty result does not falsify. That check is what established the link-path form was
clean, and it is the reason the EMPTY verdict is trustworthy rather than merely lucky.
**A recommendation to verify is confirmed, not refuted, by the verification coming back
clean** — recording it as a failed estimate would teach the next reader to skip it.

**Corollary for the next renumber:** when both holders are younger than citation accrual,
the loser's inbound set is empty by construction and the expensive half of a renumber
does not exist. That is the same premise that makes `citation_weight` unable to arbitrate
the choice — so the instrument being useless *for picking the mover* and the rewrite
being free are the SAME fact, not two.

## The precedent this sets — when to escalate past inbound weight

AGENTS.md § Numbering Discipline says the holder with the most inbound mentions keeps the
number. That rule has a precondition nobody had written down: **the documents must be old
enough to have accumulated citations.** Here they were 3 minutes apart and 40 minutes old,
so `citation_weight`'s `2 vs 0` is not a thin lead — it is an **empty measurement**, and
reading it as a lead is precisely what `TIE_FRACTION`'s docstring forbids (*"pretending it
can arbitrate is how a coin flip gets recorded as a measurement"*).

The escalation, proposed by `katgpt-rs-fa` and endorsed by `katgpt-rs-54`:

> **When both holders are younger than citation accrual, the LATER-COMMITTED document
> moves.** It is the only deterministic, reviewable tiebreak available once inbound
> weight is empty.

⚠ **The justification is deliberately weaker than the evidence appears to support.** The
diffstats show Hadamard bumped `.research/.highwater` and SAN did not, which is tempting
to state as *"SAN skipped the read-and-write-back"* — but **commit order is not allocation
order** (`katgpt-rs-54`'s caveat). SAN's author may have read the counter first and
committed second. What is observable is the commit order and the diffstat; what is not is
who read what when. The rule is kept and the causal story dropped, so it survives being
wrong about intent.

## What made this answerable in one round — and what did not

Both `.research/569` commits are anonymous: every commit in this shared worktree authors
as `katopz@gmail.com`, so git cannot distinguish sessions. `katgpt-rs-54` could rule
itself out in one `git log` grep because it puts `Session: <name>` in its commit bodies;
neither 569 commit carries such a marker, which is why ownership had to be established by
asking live peers — and why the one witness who could have answered directly
(`katgpt-rs-c5`, this issue's actual author) was unavailable, having ended.

**Put a session marker in the commit body.** It is the cheapest thing that would have made
this question answerable without a cross-session round trip, and this is the second
recorded case today of a session blocking on ownership it could not infer from a SHA.

### ⛔ But the bare marker is NOT a unique key — names are REUSED across time

Raised by `katgpt-rs-54` against its own recommendation, and verified here:
`git log --all --grep="Session: katgpt-rs-54"` returns **nine** commits, not the five
that session owns. Four more — `8aac6034`, `cecb22c8`, `7464fc6e`, `6d084c38`, the
Issue 827 work — were committed between 01:58 and 02:49, sixteen hours before that
session existed. **A different session carried the same name.**

The five-commit answer that established ownership above was correct only by accident of
window choice: it was taken over a ~20-hour window and the collision sits just outside
it. That is this thread's recurring shape one more time — *a predicate adjacent to the
question, returning a clean-looking answer* — and it arrived through the mechanism
introduced to prevent exactly that.

**Write the marker as name + session epoch:** `Session: katgpt-rs-54, 2026-09-18 evening`,
not `Session: katgpt-rs-54`. The bare form disambiguates sessions running CONCURRENTLY
and silently conflates them ACROSS TIME, which is the axis anyone grepping it later is
actually on.

### ⛔ And the shared worktree makes the REFLOG shared too — attribution fails there identically

A shared worktree has ONE `HEAD` reflog, so every session's checkouts, resets and commits
interleave in it under no identifying mark. It is therefore **not** a fallback for the
authorship that `katopz@gmail.com` cannot provide — it has the same defect, one layer
down, and it reads as authoritative because it is mechanical.

⛔ **A fourth fallback failed here too, and it is the one that actually produced a wrong
answer — ELIMINATION OVER AN INCOMPLETE ROSTER.** This section first recorded that the
`reset: moving to HEAD^` at 23:25:49 belonged to `katgpt-rs-54`, reasoning from the
bracketing commit `fd9f5d75`: *it refers to katgpt-rs-fa in the third person, therefore
it is not fa's, therefore it is 54's.* **That is valid only in a two-session worktree,
and at least four sessions were live.** Corrected and verified:

- `fd9f5d75` carries **no `Session:` marker at all** — 0 matches for `^Session:`. It is
  anonymous, at the centre of a dispute about attribution.
- Its body claims *"this session's ten commits are 833 T3 / 836 / 837 / 840 work"*.
  Those are **`katgpt-rs-c5`'s** issues. `katgpt-rs-54`'s own work is 833 T1/T2, the
  riir-llm registration and the box-state commit — which that sentence explicitly
  excludes. Of the ten rebased commits, exactly **one** (`d8bfa9b8`) carries a marker,
  and it reads `Session: katgpt-rs-54`; the other nine carry none.
- It also says *"HEAD moved `6b911ef3` → `c4bed8f1` without this session running a
  rebase"* — and `katgpt-rs-54` ran that rebase. The author is disowning the very
  action that identifies the session it was attributed to.

So the commit is a third session's, and the `reset` was not `katgpt-rs-54`'s.

⚑ **Two findings survive that correction, and they point opposite ways.** The first is
that the reflog did **not** produce this error — it reported order correctly; an
eliminator run over an assumed roster of 2 did. The second is an argument FOR the
marker, visible only because one commit had one: `fd9f5d75` claims **ten** commits over a
range that contains ten, but one of those is `d8bfa9b8`, marked as another session's. The
range is 9 + 1 and the claim over-reaches by exactly the marked commit. **An unmarked
commit is claimable by anyone reading a range**, and a range in a shared worktree is not
a session's work merely because that session rebased it.

⚠ So when a shared-worktree question is about **who**, a commit's own TEXT is the only
self-identifying evidence in the repository — and prose is not a substitute for the
marker. `fd9f5d75` was resolvable at all only because its body happened to enumerate the
issues it touched, which could be matched against a marked commit elsewhere. That is
luck. The reflog answers *what happened and in what order*, never *whose*; elimination
answers nothing until the roster is counted, and `ListAgents` lists only sessions still
ALIVE, so it is a floor on that count and never the count itself.
