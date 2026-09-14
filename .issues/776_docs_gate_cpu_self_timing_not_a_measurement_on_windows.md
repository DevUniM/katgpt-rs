# Issue 776 — the docs gate's CPU self-timing reads ~1.3s on Windows, and its own "NOT a measurement" guard does not fire

**Status:** OPEN
**Date:** 2026-09-14
**Source:** landing Issue 775's 18th check on the Windows workstation

## The measurement

Three runs of `./scripts/docs_gate.sh` on this box (Windows 11, i7-13700K,
interpreter resolved to `py` → CPython 3.14):

| date | checks | CPU printed | wall |
|---|---|---|---|
| 2026-09-13 | 17 | **1.81s** | 14.1s |
| 2026-09-14 | 18 | **1.26s** | 19.7s |

Against the M3 series AGENTS.md documents for the same gate: **14.42s** CPU at
15 checks, **13.96s** at 16, **13.37s** at 17 — on WALL clocks of 128.3s /
299.1s / 15.0s. The whole point of citing CPU there is that it is the
load-invariant figure; a tenth of it, on a box whose wall time is comparable,
is not a faster run. It is a different quantity.

And the direction matters: the 18-check run ADDED ~6.2s of measured work
(`platform_dead_code_floor_gate.py`, a 2415-file Rust-source walk) and the CPU
figure went DOWN, 1.81 → 1.26.

## Why this is the same class the gate exists to catch

`docs_gate.sh` already knows this failure mode and says so in its own header:
`times` reports `0m0.000s` children CPU from any forked context, so the total
is REDIRECTED to a file rather than captured, and the gate prints
`⛔ … NOT a measurement` instead of the number when the total reads ~0 over a
multi-second run.

The guard fires at **~0**. It does not fire at **1.26s**, which is a
well-formed, plausible-looking number — exactly the failure shape that
paragraph was written about, one order of magnitude over.

## Two live hypotheses, neither measured

1. **The interpreter shim.** `resolve_py` picks `py`, which on this box is a
   launcher, and the gate invokes each check as `"$PY" "$script"`. If the
   work is done by a grandchild that bash does not reap as its own child, the
   `times` children column never sees it.
2. **Windows/MSYS `times` accounting** for native (non-MSYS) child processes
   generally — in which case NO amount of shim-avoidance fixes it and the
   honest output is a refusal, not a number.

They are distinguishable in one run: time a single check three ways (direct
`py`, via the resolved `$PY`, and a pure-MSYS child that burns known CPU) and
compare the `times` delta against the wall.

## What is NOT in scope

Re-pinning the documented CPU series. AGENTS.md now says the 18-check CPU
figure is UNMEASURED rather than unchanged, and that 1.26s must not be read as
a speedup. The series is an M3 measurement and stays one until this is
resolved.

## Proposed work

- **T1** — the distinguishing measurement above; record which hypothesis holds.
- **T2** — if the shim is the cause: measure the CPU through a direct
  interpreter path and, if that recovers it, resolve to the real executable
  rather than the launcher.
- **T3** — regardless of T1's answer, widen the guard so a CPU total that is
  IMPLAUSIBLE against the wall clock refuses instead of printing. The
  threshold has to be a ratio, not a constant: this gate's own history is that
  wall and CPU are legitimately 20× apart under load (the 128.3s / 12.65s
  run), so the refusal must be on the side that cannot happen — CPU far below
  what the run's own per-check `⏱` lines already account for. The per-check
  wall times are already collected; their sum is the natural witness.
- **T4** — an honest fallback: on a box where children CPU cannot be measured,
  print the platform and the refusal, never a number. A wrong measurement is
  worse than a missing one here, because AGENTS.md instructs the reader to
  cite this figure.

## Not a blocker for

Anything. Every check's VERDICT is unaffected — 17/17 and 18/18 green on the
runs above. Only the timing line is wrong.
