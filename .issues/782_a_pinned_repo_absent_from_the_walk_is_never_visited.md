# Issue 782 — a pinned repo absent from the walk is never visited, and `cfg_row_implication_drift_sweep` prints "every repo within its pins"

**Filed:** 2026-09-14 · **Status:** OPEN · **Scope:**
`scripts/cfg_row_implication_drift_sweep.py` · **Class:** Issue 779 family

## The defect

Issue 779 gave the sweep family one shared partial-clone verdict
(`scripts/sweep_population.py`) because **seven** sweeps carried a copy-pasted
"pinned but ABSENT from the derived walk" loop that hard-red on a known
16-of-20 box. Three sweeps were left alone because they had no such loop.

`cfg_row_implication_drift_sweep.py` is one of those three, and the reason it
had no loop is that it has **no absence check at all**:

```python
for repo in sorted(repos, key=lambda p: p.name):   # DERIVED, not pinned
    ...
    pin = pins.get(repo.name)
    if pin is None:
        fails.append(f"{repo.name}: no pin row — …")   # UNREGISTERED: caught
```

The walk→pins direction reds. The **pins→walk** direction is unchecked: a
pinned repo the walk never found is simply not iterated, and nothing says so.
Measured on this box (16 of 20), with four rows pinned for repos that are not
here:

```
16 repos · 2246 rows · 1549 with a leading #![cfg] · 0 EMPTY-AT-ROW · 12 UNRESOLVED
✓ cfg-row-implication drift sweep PASSED — every repo within its pins
```

`katgpt-web`, `riir-dao`, `riir-deployer`, `riir-esp32` each carry a
`0 0 0 0` row in `cfg_row_implication_drift_floors.txt` and were evaluated by
nothing. The sweep says "**every repo**" over 16 of 20.

**This is the worse direction of the two.** The seven sweeps Issue 779 repaired
failed LOUDLY on a partial clone — annoying, and impossible to misread. This
one reports a confident green over a subset, which is the green-zero shape the
whole instrument family exists to refuse, and it survived 779 *because* it was
quieter, not because it was correct.

## Scope check — the other two exempt sweeps

| sweep | pinned rows | absent on this box |
|---|---|---|
| `docs_drift_sweep.py` | 8 (floor-bearing subset) | 0 |
| `restatement_drift_sweep.py` | 4 (repos with `.proofs`) | 0 |
| `cfg_row_implication_drift_sweep.py` | **20** | **4** |

The other two are clean **on this box today**, not by construction — both
derive a *subset* population and would have the same hole the day a pinned
repo goes missing. They are a separate, smaller question from the one live
defect and must not be pooled with it.

## Tasks

- [ ] **T1** — repoint `cfg_row_implication_drift_sweep.py` at
      `sweep_population.population_verdict()`, matching the other eight: the
      three verdicts (UNREGISTERED / UNSEEN / DEFERRED), the deferral riding
      the FINAL line in both directions, and `bad = True` on a failure.
- [ ] **T2** — verify BOTH postures on this box: with the marker the run
      passes carrying a named DEFERRED line for the four; without it, the run
      must red UNSEEN and must NOT print "every repo".
- [ ] **T3** — decide the other two exempt sweeps: same repair if their
      derived subsets can go absent, or a recorded reason why the question
      cannot arise. Do not leave the answer implicit — that is how this one
      survived 779.
