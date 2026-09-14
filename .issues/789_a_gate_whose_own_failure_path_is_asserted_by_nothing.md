# Issue 789 — a gate whose own failure path is asserted by nothing

**Filed:** 2026-09-14 · **Status:** OPEN · **Branch:** develop

## How this was found

Issue 775 landed `platform_dead_code_floor_gate.py` with **six canary arms
over the gate's own pin arithmetic, which the classifier's self-test cannot
reach**. That sentence is in AGENTS.md, it is correct, and it names a rule.

The rule landed in **one** gate and was never generalised — the sixth
recorded instance of that exact shape (Issues 777, 778, 779, 782, 783). It was
found by asking the question one level up from Issue 787: 787 mechanised *"is
every instrument findable?"*; nothing asks *"is every gate's own verdict
validated?"*

⛔ **The first census of this was wrong, and wrong in the over-reporting
direction** — it grepped for the *flag names* `--canary` / `--prove-fires` /
`--self-test` and reported 9 of 20 checks bare. Three of those nine invoke a
validation arm they **delegate** to the classifier they read
(`percentile_floor_gate` → `percentile_index_audit.selftest`,
`cfg_row_implication_gate`, `trap_sentinel_gate`), which is the DRY answer and
the correct one. A census over one representation — here, a CLI flag string —
is blind to whatever that representation omits. Same lesson as 787, one axis
over, reproduced within ten minutes of starting to look for it.

## The measurement

`scripts/docs_gate.sh` `CHECKS`: **20**. Arm resolved by AST — a function
named `selftest` / `self_test` / `canary` / `gate_selftest` / `prove_fires`
that is *called*, whether defined locally or reached through an imported
module:

| | count |
|---|---|
| invokes its own arm | 10 |
| invokes a **delegated** arm (the classifier it reads) | 3 |
| invokes both (775's shape) | 1 |
| **invokes NOTHING** | **6** |

The six, with the per-push logic each carries unasserted:

| check | lines | arithmetic nothing validates |
|---|---|---|
| `issue_citation_gate.py` | 750 | `allocated()` / `heading_allocated()` / three-way bucketing |
| `cargo_comment_audit.py` | 480 | the default-closure comparison |
| `skill_repo_set_gate.py` | 306 | `fenced_blocks` + command-block repo-set scan |
| `count_features.py` | 261 | flag counts, 5 README sites × 29 manifests |
| `docs_gate_checks_sync.py` | 141 | membership both ways + quantity words |
| `markdown_fence_gate.py` | 112 | `fenced_blocks` + a 0 ceiling over a 1517-file walk |
| | **2,050** | |

`docs_gate.sh`'s own opening comment is the argument for why this matters:
*"An assertion nobody invokes is decoration, and a red one nobody invokes is
worse."* Two of the three checks that file was written for were **RED on
develop** when it landed. The same sentence applies one level in: an assertion
whose failure path nobody has executed is decoration too, and it reports a
confident green.

## The defect this found — `fenced_blocks` is blind to half of CommonMark

Two of the six share one function, and it is the subtlest parser in the set.
`skill_repo_set_gate.fenced_blocks` is imported by `markdown_fence_gate.py`
under Issue 755's explicit DRY call — *"a second copy of a rule this subtle is
a second thing to get wrong"* — which is right, and which concentrated the
whole risk into one untested function. AGENTS.md documents the hazard it
exists to prevent (a naive toggle **mis-phases** permanently on an
unterminated fence and thereafter scans the complement, reporting clean either
way) and records that **its own first canary was swallowed by exactly that
bug**. The canary was never replaced.

Ten known-answer arms, run 2026-09-14. **Eight pass. Two FAIL:**

| arm | expected | got |
|---|---|---|
| `~~~` / `x` / `~~~` | one block `(1,3)` | **`[]` — invisible** |
| `~~~` / ` ``` ` / `~~~` | one block `(1,3)` | **`[(2,-3)]` — a false unterminated fence at line 2** |

`fence_run()` counts leading **backticks only**. CommonMark fences are
backtick **or tilde**, and the blindness runs in both directions:

- **Silent:** a tilde-fenced command block is never scanned, so
  `skill_repo_set_gate` certifies a hand-typed repo set it never read; a
  tilde-fenced **unterminated** block is invisible to `markdown_fence_gate`,
  which is the entire class that gate exists for.
- **Loud, at the wrong address:** an *odd* number of backtick lines inside a
  tilde block yields a phantom unterminated fence — a red pointing at a line
  that is not the defect, the failure mode `markdown_fence_gate`'s own
  docstring warns the reader about.

**Exposure is LATENT: 0 tilde-fence lines over 5116 tracked `.md` across 16
repos** (measured 2026-09-14). That is the `orphaned_attr_gate` standing —
pinned at zero, measured zero everywhere, worth having because the shape costs
nothing to forbid and the guarded gate's own docstring claims to be
"CommonMark-ish" on precisely the axis it cannot read.

## Tasks

- **T1** — `fence_run`/`fenced_blocks` read tilde fences (a tilde closer must
  match the tilde opener's run and a backtick run must not close a tilde
  block, and vice versa — the two families do not interoperate in CommonMark).
  Add `selftest()` beside it with the ten arms above plus the mis-phase arms;
  both consumers invoke it and exit **2** on failure (the "instrument
  untrustworthy" convention `percentile_floor_gate` and `markdown_fence_gate`
  already use for the blind-walk case). Re-run the workspace fence sweep and
  confirm 0 holds with tildes visible.
- **T2** — mechanise the census: a per-push check that every `docs_gate.sh`
  `CHECKS` entry invokes a validation arm, own or delegated, resolved by
  **AST** and not by flag string. Two floors, and the permissive direction is
  the one to get right (787's `min_roots` lesson): an empty CHECKS parse reds
  loudly, but an arm-name set that quietly *widens* greens everything.
  Exemptions pinned by **membership with a reason per row**; a reasonless row
  is refused.
- **T3** — retire the remaining four bare rows with real arms, so T2's pin
  file lands at zero membership: `count_features`, `cargo_comment_audit`,
  `issue_citation_gate`, `docs_gate_checks_sync`. A row reading "not written
  yet" is a backlog wearing a pin, and 785's rule forbids ratcheting one.
- **T4** — the workspace half. `markdown_fence_drift_sweep.py` imports the
  same parser, so T1 propagates for free; the open question is whether the
  arm-invocation predicate generalises to sibling gate sets or is
  katgpt-rs-scoped like `cfg_gated_floor_gate`. Decide from a measurement, not
  by symmetry with the other sweeps.

## Why not a report

Every instrument in this family that is report-only is report-only because its
findings are **latent across repos this repo does not own**. This one is about
`scripts/docs_gate.sh`'s own CHECKS array — a file this repo owns, edited by
the commit that adds a check, and cheap to read. `instrument_reachability_gate`
(~0.24s) is the precedent: the check that answers *"did somebody add an
instrument nothing runs?"* belongs on the push that adds it.
