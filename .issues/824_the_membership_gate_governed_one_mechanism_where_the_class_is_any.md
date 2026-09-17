# Issue 824 (2026-09-17) — the family gate watched the failure it was built for happen beside it

**Status: RESOLVED same day (T1–T3).**

## The symptom

`cfg_row_implication_drift_sweep.py` hard-red on three repos with **zero
content findings**:

    seal-game-editor: no pin row — a new repo must be pinned deliberately
    seal-online-remaster: no pin row — …
    seal-remake: no pin row — …

All three are acknowledged by `DOCS_GATE_KNOWN_EXTRA`. This is Issue 821's
symptom exactly, in a sweep Issue 821 closed.

## What actually happened

Issue 821 landed `sweep_population.pin_row_exempt()` and its close-out says
*"wired into **16** sweeps"*. The family is **19**. The three missed are:

| sweep | state | why it wasn't noticed |
|---|---|---|
| `cfg_row_implication` | **hard red, live** | nobody had run it since 821 |
| `restatement` | hard-fails, **latent** | its population is the `.proofs` subset and no acknowledged extra carries one *today* |
| `docs` | advisory only | it would merely *advise* pinning a repo the contract does not claim — an action the reader cannot correctly take |

⛔ **Those three are not a random subset.** They are precisely the three
AGENTS.md already names, from Issue 782, as the ones that "were not exempt —
they were quieter". The same three were missed twice, by two different repairs,
for the same reason both times: **a hand-grep of a family finds the loud
members.**

## The real finding — and it is about the gate, not the sweeps

`scripts/sweep_advisory_membership_gate.py` exists *because of this class*. Its
own docstring:

> That is the standing failure mode of this repo, recorded seven times now …
> **a rule landed in one instrument and never generalised.** Every previous
> instance was repaired by grepping the family by hand and fixing the copies.
> This one is repaired by making the family gate itself.

And then Issue 821 did it again, to a different mechanism, **while that gate
was standing and green** — because the gate governed `sweep_advisory()` *by
name*. The class is not "the advisory"; the class is **any mechanism every
member of the family must call**. A gate scoped to one instance of a class it
was written to prevent can watch the next instance happen next to it and report
a pass.

That is the eighth recorded instance (777, 778, 793, 782, 783, 789, 797, 821),
and the first where the *prevention itself* was the thing that didn't
generalise.

## The repair (T1–T3)

**T1 — wire the three.** All 19 now call `pin_row_exempt()`. `cfg_row_implication`,
`docs`, `restatement` green; the nesting follows Issue 821's own process note
(the exemption goes INSIDE `if pin is None:`, never flattened into it, or the
else-branch dereferences the missing row).

**T2 — `MECHANISMS` is a registry, not a name.** The gate takes
`slug -> (why, call-names)`; the verdict is computed **per mechanism and never
pooled**, because a pooled verdict is exactly what reports a sweep wired for
one and missing the other as wired — the 16-of-19 state. Adding the next
family-wide mechanism is one row, and the arms **walk the registry** rather
than hard-coding it, so a mechanism added later is armed by EXISTING.

**T3 — the pin key is `(mechanism, sweep)`.** A bare per-sweep row would excuse
that sweep from the mechanism nobody has looked at yet. This is the
`DOCS_GATE_KNOWN_EXTRA` asymmetry (NAMES, never `=1`) applied one file over. An
unqualified row and an unknown slug are both REFUSED. The file stays
**deliberately empty**, and both mechanisms now carry their own argument for
why a row there would be wrong.

Canaried two ways:
- **arms**, on a fixture wired for the advisory only — it must read UNWIRED for
  the exemption and WIRED for the advisory, independently;
- **production path**, by unwiring `citation_drift_sweep` in the real tree:
  `✗ UNWIRED [known-extra-exemption] citation_drift_sweep.py`, exit 1, naming
  the mechanism.

## Postscript — how it was found

Not by a sweep run, but by running **every** sweep and reading EXIT CODES
rather than grepping verdict lines for a glyph. The glyph grep had silently
matched nothing on the first two attempts and printed `<no verdict line>` 19
times, which reads like a harness problem rather than a finding.

⚠ The same run reported `numbering` at **exit 127 with a 0-byte log** — the
process never started, during a box-wide memory squeeze (free RAM 1.29 GB, a
concurrent 29.6 GB training job). It passes standalone. **A batch runner that
reports exit codes reports infrastructure failures in the same column as
instrument failures**; 127 with an empty log is the signature, and it is worth
re-running alone before believing it — the `x86_64_execution_matrix` rule
(every failure is RE-RUN ALONE, then adjudicated) reached by a different road.
