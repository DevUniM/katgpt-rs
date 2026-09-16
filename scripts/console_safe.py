#!/usr/bin/env python3
"""Keep an instrument's verdict printable on a non-UTF-8 console (Issue 804).

Every instrument in `scripts/` prints `✓`, `✗`, `⛔`, `⚠` and em-dashes. On a
console whose encoding is not UTF-8 — the Windows workstation is **cp874** —
`print()` raises `UnicodeEncodeError` and the process dies **with no verdict
at all**:

    UnicodeEncodeError: 'charmap' codec can't encode character '\\u2713'

`scripts/docs_gate.sh` exports `PYTHONIOENCODING=utf-8`, so every per-push
CHECK survives *when the gate runs it*. Nothing protects an instrument run
DIRECTLY — which is how AGENTS.md documents most of them
(`scripts/percentile_index_audit.py ../riir-ai`). So the class concentrates in
exactly the instruments with no automatic lane: the workstation sweeps and
audits, the ones whose whole purpose is to be run by hand on the one box that
has the whole workspace checked out.

⛔ **The consequence is not a crash, it is UNREAD FINDINGS.**
`restatement_drift_sweep.py` was the one member of the 18-sweep family without
this defence, so it was the one nobody on this box could run — its 4 repos /
255 theorems were not *unknown*, they were *unlooked at*, while the family was
being reported green.

## Why `backslashreplace`

The console encoding is **not ours to choose**. Forcing `encoding="utf-8"` on
a cp874 console produces mojibake in the terminal rather than an exception,
which is the silent direction. `backslashreplace` degrades `✓` to a visible
`\\u2713`, keeps every ASCII character exact — so a verdict line stays
greppable — and makes the substitution obvious to a reader.

It is also what 42 of the 70 in-population instruments already do inline, so
this module finishes a job rather than choosing a new policy.
`scripts/console_encoding_gate.py` accepts EITHER form, because the property
worth asserting is *the streams are defended*, not *this function was called*.

## What this does NOT claim

That the output is *readable* on such a console — `\\u2713` is worse than `✓`.
Only that the instrument RUNS and reports its verdict instead of dying, which
is the difference between a finding being read and a finding not existing.
"""

import sys


def apply(streams=None) -> int:
    """Make `sys.stdout`/`sys.stderr` survive characters they cannot encode.

    Returns the number of streams actually reconfigured — 0 is a legitimate
    answer (a detached or already-safe stream), which is why this reports a
    count instead of a bool nobody could interpret.

    `streams` is injectable for the arms: a real `reconfigure` on the live
    interpreter's stdout cannot be asserted from inside a test that is itself
    printing through it.
    """
    targets = (sys.stdout, sys.stderr) if streams is None else streams
    done = 0
    for stream in targets:
        try:
            stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            # Not a TextIOWrapper (embedded interpreter, detached stream, a
            # StringIO under capture). Keep the old behaviour rather than
            # inventing one — this is a best-effort defence, not a contract.
            continue
        done += 1
    return done


def selftest() -> list:
    """Arms. Returns a list of failure strings; empty is a pass."""
    fails = []

    class Reconfigurable:
        def __init__(self):
            self.errors = None

        def reconfigure(self, errors=None):
            self.errors = errors

    class NotAWrapper:
        def reconfigure(self, errors=None):
            raise AttributeError("detached")

    class ValueErrorer:
        def reconfigure(self, errors=None):
            raise ValueError("read-only stream")

    # 1. The mode is the whole point: `backslashreplace`, not `replace` (which
    #    prints `?` and loses which glyph was there) and not `ignore` (which
    #    deletes it silently — the same output as the character never having
    #    been printed, on an instrument whose glyphs ARE its verdict).
    a, b = Reconfigurable(), Reconfigurable()
    if apply((a, b)) != 2:
        fails.append("apply() did not report both streams reconfigured")
    if (a.errors, b.errors) != ("backslashreplace", "backslashreplace"):
        fails.append(f"wrong error mode: {a.errors!r}, {b.errors!r}")

    # 2. Both failure shapes are survivable and NEITHER is counted as done.
    #    An exception escaping here would kill the instrument at import, which
    #    is strictly worse than the crash this module exists to prevent.
    if apply((NotAWrapper(), ValueErrorer())) != 0:
        fails.append("a stream that refuses must not be counted as defended")

    # 3. Mixed: the count must be the number that actually took, so a caller
    #    reading it as "did anything happen" is not misled by a partial apply.
    c = Reconfigurable()
    if apply((NotAWrapper(), c)) != 1:
        fails.append("mixed streams must report only the ones that took")
    if c.errors != "backslashreplace":
        fails.append("a later stream must still be reached after an earlier raise")

    # 4. The premise, asserted rather than assumed: a cp874 encoder really
    #    does refuse `✓`, and really does survive it under this mode. Without
    #    this arm the module is three tests of a mock. Skipped, loudly, where
    #    the codec is unavailable — never silently passed.
    try:
        "✓".encode("cp874")
        fails.append("premise refuted: cp874 encoded U+2713 without error")
    except UnicodeEncodeError:
        pass
    except LookupError:
        fails.append("PREMISE UNMEASURED: no cp874 codec on this interpreter")
    else:
        pass
    if "✓".encode("cp874", errors="backslashreplace") != b"\\u2713":
        fails.append("backslashreplace did not produce the documented escape")

    return fails


def main() -> int:
    apply()
    fails = selftest()
    if fails:
        print("✗ console_safe SELFTEST FAILED:")
        for f in fails:
            print(f"    {f}")
        return 1
    print("✓ console_safe selftest PASSED — 4 arm group(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
