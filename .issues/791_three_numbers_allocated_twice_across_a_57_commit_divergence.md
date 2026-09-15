# Issue 791 — three issue numbers allocated twice across a 57-commit divergence

**Filed:** 2026-09-15 · **Status:** OPEN · **Branch:** develop

## What happened

`develop` diverged 57 local commits against 31 remote ones. Both sides read
`.issues/.highwater`, both incremented it correctly **from their own view**,
and both allocated the same numbers to different documents:

| number | this session's allocation | the other session's allocation (live file) |
|---|---|---|
| 776 | the docs-gate CPU figure suppressed on Windows/MSYS | `776_contrastive_matched_swap_norm_matched_noise.md` |
| 779 | `sweep_population.py` — the shared partial-clone verdict | `779_subspace_intervention_followup.md` |
| 780 | the `MISATTRIBUTED-IN-RANGE` citation class | `780_online_linear_readout_primitive.md` |

Both sides are legitimately **katgpt-rs** issues — the other session's 776
records a katgpt-rs implementation commit — so this is not the cross-repo
mis-attribution class (Issue 749). It is the straight duplicate-allocation
class, at three numbers.

## Why no gate caught it

`numbering_gate.py` checks TRACKED duplicates, and there are none: this
session's 775–789 files were removed under the noise-reduction rule as they
closed, so only the other session's three files exist on disk. The gate is
correct about what it measures. **The duplication is in the RECORD** — git
history, `HISTORY.md`, and AGENTS.md prose — where a reader following
"Issue 776" opens a document about contrastive interventions.

⛔ `.highwater` cannot detect this either, and the rebase made that concrete:
the merge resolution is `max(ours, theirs)` at every step, which is the only
sound rule for a monotonic counter — and `max` is exactly what makes a
double-allocation invisible. A counter records the NEXT free number; it is not
a ledger of who took what. `highwater_contiguity_audit.py` already measured
that (438 gaps + 27 resets over 73 counters) and this is the same fact from
the other side.

## Why `citation_weight.py` cannot adjudicate it

Issue 724 T2's rule — *the document with the most inbound mentions keeps the
number, the other moves* — is implemented by `scripts/citation_weight.py`.
It cannot be run here: `candidates()` enumerates `.md` files ON DISK in the
numbered directory, and **one side of each pair has been removed**. The tool
assumes both candidates are live files; a collision where one side closed and
was deleted under the noise rule is outside its reach.

⚠ A raw `git grep -c "Issue 776"` returns 27, and that number must NOT be read
as 27 citations of either meaning: sampled, the hits mix `riir-ai Issue 775`
on the same line, the other session's file citing itself, and genuine
references to both documents. **Unadjudicated.** Getting a real count is the
first task below, and it needs the tool taught about removed candidates.

## Tasks

- **T1** — teach `citation_weight.py` to accept a candidate that exists only in
  HISTORY (a `--candidate <stem>` override, or recovery through `git log
  --diff-filter=D`). Without it the adjudication rule has no instrument for the
  commonest collision shape, which is precisely a closed-and-removed document
  meeting a live one.
- **T2** — adjudicate the three pairs with it, and move the loser. ⚠ The loser
  may be the OTHER session's live file; renumbering another session's open work
  is not a unilateral act — agree it, or move this session's HISTORY references
  instead and record the reallocation.
- **T3** — the preventable half. Two sessions cannot both hold a counter. The
  cheap mitigation is procedural (fetch before allocating, which the
  `riir-train-concurrent-agents` memory already says for a different reason);
  the durable one is a gate that reds when a number is allocated in a commit
  whose parent already has that number allocated on the remote. Measure the
  false-positive rate before building — a long-lived branch legitimately
  allocates ahead of its remote.
