# Issue 840: `origin/develop` is RED — two `.research/569` documents landed, and one defect trips two independent detectors

**Status:** OPEN — **verified, not repaired.** The repair is a renumber of somebody
else's just-landed document and this session declined to make it unilaterally; see
§Why this was not fixed here.

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

`.research/.highwater` reads **569**, so the second allocation did not bump it — the
`.highwater` read-and-write-back step in AGENTS.md § Numbering Discipline was skipped or
raced.

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

1. One of the two moves to **570** — the owner's call, not the instrument's, on a margin
   this thin. The later commit (`d41d4c43`, SAN) is the natural mover: the first
   allocation was legitimate and the second is the one that did not bump the counter.
2. `.research/.highwater` → **570**.
3. Rewrite the loser's inbound `Research 569` citations — there are 3 ambiguous sites and
   1 is UNRESOLVED, so this is a hand read, not a `sed`.
4. Re-run `py scripts/numbering_gate.py`; **both** rows must clear together. If only the
   tracked-duplicate row clears, the legacy diff above was wrong and should be re-taken.

## Tasks

- [ ] **T1 — renumber one side to 570 + bump `.research/.highwater`**, owner's call which.
- [ ] **T2 — rewrite the 3 ambiguous `Research 569` citation sites** by hand.
- [ ] **T3 — do NOT bump `legacy_ratchet`.** Assert it returns to 61 once T1 lands; if it
      does not, a second, genuinely-historical collision is hiding behind this one.

## ⚠ The standing gap this exposes, which is NOT this issue's to fix

Nothing ran. `docs_gate.yml` is `branches: [main]`, and both commits went to `develop`.
The collision was found by a human-equivalent `git fetch` forty minutes after it landed,
and `dual_allocation_gate.py` could not have caught it either — that gate compares **this
checkout against its upstream**, and here *both* sides are upstream, which is the reach
limit its own write-up records (*"box-vs-box collisions on the wire are the merge-time
wall's jurisdiction"*). The merge-time wall is `numbering_gate`, and on a develop-only
push there is no merge and no lane. See `scripts/ci_gate_coverage.py` and AGENTS.md
§ Trigger health; the Actions spending call is the owner's and stands.
