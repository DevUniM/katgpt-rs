# Issue 787 — an instrument no document names is invisible to the census that would have found it

**Filed:** 2026-09-14 · **Status:** OPEN · **Branch:** develop

## How this was found

`1a5b6571` (2026-09-14, hours before this file) corrected the Issue 785
close-out from "every cross-repo class in `scripts/` now has both halves" to
the bounded claim:

> every cross-repo class in `scripts/` whose verdict is **walled at a small
> number** has both halves

That bounded claim was **still false**, by exactly one instrument.
`len_derived_binding_audit.py` is cross-repo, its joined-finding buckets were
walled at **0**, and it had no verdict half — Issue 786, filed and closed the
same day.

The interesting part is not the miss. It is the **mechanism** of the miss. Both
censuses — the one that produced 783/784/785 and the one that produced the
bounding correction — enumerated the audits **AGENTS.md documents** against
their sweep halves. `len_derived_binding_audit.py` was not in AGENTS.md at all.
A census that reads the document cannot see an instrument the document does not
name, and it will report a confident, complete-sounding answer over the subset
it can see. That is the same failure shape as every blindness floor in this
repo, one level up: the population was the *documentation*, and nothing floored
it against the *directory*.

## The measurement

Tracked `.py` under `scripts/`: **63**. Reachable transitively from
`AGENTS.md` + `scripts/docs_gate.sh` + `.github/workflows/*.yml` (following
script → script references, so a helper invoked by a documented gate counts):
**54**. **UNREACHABLE: 9.**

| script | standing |
|---|---|
| `scripts/kimi_ref/dump_kda_internals.py` | reference-implementation drop |
| `scripts/kimi_ref/dump_layer0.py` | reference-implementation drop |
| `scripts/kimi_ref/dump_layer3.py` | reference-implementation drop |
| `scripts/kimi_ref/fla_stub.py` | reference-implementation drop |
| `scripts/kimi_ref/run_reference.py` | reference-implementation drop |
| `scripts/generate_npc_brain_model.py` | manual CoreML generator |
| `scripts/gguf_header_audit.py` | manual model-file introspection; `1a5b6571` already records it as outside the class-audit family |
| `scripts/citation_weight.py` | Issue 725 T4 helper; named in `HISTORY.md` only |
| `scripts/list_unresolved_percentile_sites.py` | named in **no** tracked file anywhere |

Transitive reachability is the right predicate, and the cases prove it:
`all_ignored_target_audit.py`, `cfg_row_implication_audit.py` and
`ci_test_execution_report.py` appear in no document either, but each is invoked
by an instrument that IS documented (`cfg_gated_floor_gate.py`,
`cfg_row_implication_gate.py`, `suite_membership_audit.py`) and each runs
per-push as a result. A basename-in-AGENTS.md rule would red all three and
teach whoever hit it to stop reading the gate.

**And the known-answer validation is free.** At `18dbe980~1`,
`len_derived_binding_audit.py` was named only in `HISTORY.md` — not a root — so
it was the **tenth** unreachable script, and this gate would have red on it.
That is a two-sided proof against a tree whose answer is known independently,
in the `platform_dead_code_audit.py --prove-fires` idiom, and it costs one
`git archive`.

## Why HISTORY.md is deliberately NOT a root

It is the archive. Its own header says operational rules live in `AGENTS.md`
and that it exists so agent context stays small — it is not loaded into a
session. An instrument findable only from the archive is exactly the instrument
that stops being run, which is what 786 measured. Treating HISTORY.md as a root
would have made 786 read as reachable and this gate vacuous on the one case
that motivated it.

## Tasks

- **T1** — `scripts/instrument_reachability_gate.py`: population = tracked
  `scripts/**/*.py`; roots = AGENTS.md + `scripts/docs_gate.sh` +
  `.github/workflows/*.yml`; transitive closure; UNREACHABLE pinned by
  **MEMBERSHIP** in `scripts/instrument_unreferenced_expected.txt` with a
  reason per row, reds in BOTH directions. Population floor (a walk that goes
  blind must red, not report a clean zero) and a ROOTS floor (an empty or
  unreadable root set makes every script unreachable, which would red loudly —
  but the inverse, a root glob that silently matches everything, makes every
  script reachable and reports a confident green; that direction needs the
  assertion).
- **T2** — Adjudicate the 9. The five `kimi_ref/` files, the CoreML generator
  and `gguf_header_audit.py` are exemption rows with reasons. The other two are
  judgement calls, and the default should be to make them findable rather than
  to exempt them.
- **T3** — `--prove-fires 18dbe980`: require `len_derived_binding_audit.py`
  UNREACHABLE at the parent and reachable at the commit.
- **T4** — Canary arms over the gate's own pin arithmetic, both directions.
- **T5** — Join `docs_gate.sh`'s CHECKS + the AGENTS.md table (membership both
  ways, `docs_gate_checks_sync.py`), and update the CHECKS-count prose.
- **T6** — The sweep half, `scripts/instrument_reachability_drift_sweep.py`.
  Shipping a gate without one is the defect Issue 783 records, and doing it
  again in the issue that exists *because* a rule was not generalised would be
  its own punchline. Each repo has its own `AGENTS.md` and its own workflows,
  so the classifier takes a repo path and the roots are derived per repo.
- **T7** — Close-out in `HISTORY.md`, including the correction to `1a5b6571`'s
  bounded claim: it was wrong, and the reason it was wrong is this issue.

## Out of scope

Adding AGENTS.md prose for every script. The predicate is *reachable*, not
*documented in prose* — a helper invoked by a documented instrument is
findable, and inflating AGENTS.md is the opposite of why HISTORY.md exists.
