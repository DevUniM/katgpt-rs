# Issue 775 — `platform_dead_code_audit.py` has no VERDICT half, and nothing automatic runs it

**Status:** OPEN (the report half landed `a0cbc398`; the gate + the sweep are the follow-on)

**Date:** 2026-09-14
**Source:** landing the instrument for the class `ea4c2873` found by hand
  (riir-clippy intake P22; HISTORY.md §"The platform-dead_code class got an
  instrument").

## The gap

`scripts/platform_dead_code_audit.py` is a REPORT (exit 0 except a classifier
MISS, which exits 2). Every other audit in this family ships in two halves,
and this one has only the first:

| audit | report | verdict (docs gate) | sweep (workstation) |
|---|---|---|---|
| cfg-gated targets | `cfg_gated_target_audit.py` | `cfg_gated_floor_gate.py` | `cfg_gated_drift_sweep.py` |
| percentile index | `percentile_index_audit.py` | `percentile_floor_gate.py` | `percentile_drift_sweep.py` |
| trap exit launder | `trap_exit_launder_audit.py` | `trap_sentinel_gate.py` | `trap_sentinel_drift_sweep.py` |
| **platform dead_code** | `platform_dead_code_audit.py` | **— none —** | **— none —** |

So the landing measurement (**0 findings · 1 MOD-REF** over 8694 files / 3433
units / 119452 candidate decls / 16 repos) is a snapshot nothing defends. The
class's whole point is that it is invisible to every automatic lane this
workspace runs — `full_gate` is macOS/aarch64, `wasm32_gate` is wasm32, and
the x86_64-native lane that emits the warning is a workstation lane. An
instrument that closes that hole and is itself run by nothing has moved the
hole one level up.

## What the verdict half needs (the family's own rules)

- **Two floors, not one.** A findings ceiling of 0 is green over whatever the
  walk can see, so pin the walk too: `min_rs_files` AND `min_candidate_decls`
  — and the second is the one that moves when the token walk breaks on an
  unchanged tree, exactly as `min_theorems` vs `min_lean_files` in
  `restatement_drift_sweep.py`.
- **MOD-REF is pinned by MEMBERSHIP, not cardinality.** There is exactly one
  row today (`katgpt-types/src/simd/mod.rs:49` `mod horizontal`) and it is a
  deliberate standing observation, not a defect. A count ceiling would go
  green on a swap; the name must be in the pin.
- **The sweep is workstation-only**, like every other member: CI's single
  checkout derives an empty population and prints a confident green over zero
  repos.
- **`--prove-fires` already exists** and must stay in the gate's path — the
  ceiling is otherwise a pin nobody has watched fail. `ea4c2873` is the
  known-answer tree (NEON_U8 PRESENT at `~1`, absent at the fix).

## The second axis: nothing NAMES it

`docs_gate.sh`'s CHECKS array does not include it (correctly — it is a report
today), and no workflow does either. Whatever lands, `scripts/ci_gate_coverage.py`
should be able to see something start it. Note that adding a row to
`docs_gate.sh` also moves `docs_gate_checks_sync.py`'s count and the AGENTS.md
table — both, in the same commit.

## Not in scope

The riir-ai rows this sweep found are already repaired (riir-ai `7b97ab97e`);
this issue is about the instrument's second half, not about findings.
