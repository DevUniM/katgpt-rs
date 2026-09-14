# Issue 788 — the population-predicate registry is hand-maintained, and it is two short

**Filed:** 2026-09-14 · **Status:** OPEN · **Branch:** develop

## The gap

`scripts/population_sync_gate.py` exists because a hand-duplicated *predicate*
drifts exactly as a hand-typed count does: if one instrument's "which repos are
contract repos" answer diverges, that instrument quietly audits a different set
and still prints green. Its `PREDICATES` tuple is deliberately DATA, and its own
comment says so:

> Kept as DATA so adding an eighth instrument is a one-line change here rather
> than an eighth silent divergence.

The one-line change is the part nobody makes. Measured 2026-09-14 — tracked
`scripts/*.py` defining their own `BOUNDARY.md` + `.git` walk:

| predicate | registered |
|---|---|
| `cfg_gated_target_audit.derive_repos` | ✓ |
| `ci_gate_coverage.derive_repos` | ✓ |
| `numbering_drift_sweep.contract_repos` | ✓ |
| `percentile_index_audit.repos` | ✓ |
| `skill_repo_set_gate.derive_repos` | ✓ |
| `suite_membership_audit.derive_repos` | ✓ |
| `trap_exit_launder_audit.repos` | ✓ |
| **`len_derived_binding_audit.derive_repos`** | **✗** |
| **`restatement_theorem_audit.repos`** | **✗, and correctly so** |

Nine predicates, seven registered. The gate has been reporting "7 predicates
agree" over a population of nine since Issue 734 added the seventh.

## The two are not the same kind of miss

`len_derived_binding_audit.derive_repos` is a genuine eighth: same BOUNDARY.md +
`.git` test, same intended answer, never checked against the other seven. Issue
786's sweep asserts it agrees with `skill_repo_set_gate` — but only on the runs
somebody invokes that sweep, and the gate that exists for exactly this runs
per-push.

`restatement_theorem_audit.repos` is a **SUBSET** predicate: BOUNDARY.md + `.git`
**+ `.proofs`**, 4 of 16. It must NOT be registered — it would disagree with the
other eight by construction and red every run. But that exclusion is currently
recorded **nowhere**, which means the next reader has to re-derive it, and the
reader who does not will either register it (breaking the gate) or add another
subset predicate silently.

## Same class as Issue 787, one level over

787 mechanised *"is the instrument findable from the documentation?"*. This is
*"is the instrument's population predicate registered with the gate that checks
population predicates?"* — and both were hand-maintained lists that a census had
to remember to consult. A registry whose completeness is asserted by nobody is a
document, not a gate.

## Tasks

- **T1** — Register `len_derived_binding_audit.derive_repos` as the eighth.
- **T2** — Add `SUBSET_PREDICATES` as its own DATA tuple with the reason, so
  "not registered" and "deliberately not registered" stop being the same state.
  A subset predicate still gets an assertion: it must be a strict subset of the
  agreed answer, which is a real claim and catches a `.proofs` walk that has
  silently started matching something else.
- **T3** — A **registry-completeness** check inside the gate: scan tracked
  `scripts/*.py` for the derivation shape and require every hit to be in one
  tuple or the other. This is what stops the tenth from being silent.
- **T4** — Canary arms over T2 and T3, both directions.
- **T5** — The gate says **SEVEN** in its docstring, `docs_gate.sh`'s CHECKS row
  and the AGENTS.md table. `docs_gate_checks_sync.py` asserts the quantity words
  agree, so all three move together.

## Out of scope

Unifying the nine implementations into one. They are deliberately independent —
the gate's whole premise is that N independent answers agreeing is evidence and
one shared answer is not.
