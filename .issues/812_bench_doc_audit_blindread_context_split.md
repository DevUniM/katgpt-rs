# Issue 812: `bench_doc_audit.py` BlindRead self-test arm — deterministic context split (red in some execution contexts, blob unchanged)

**Status:** Open — owner: the Issue-804 unit (script last touched `59ad87ea5` "feat(804): 28 instruments crashed when run the way AGENTS.md says to run them"); NOT the DBTM research session (its commits `e0e63f47b`/`d7d73fc44` are docs-only; `git diff e0e63f47b d7d73fc44 -- scripts/bench_doc_audit.py` is empty)
**Date:** 2026-09-16
**Found by:** verdict-review second opinion (fresh reviewer thread), 2026-09-16 — three deterministic reproductions
**Affected:** `scripts/bench_doc_audit.py` `blindness_arms()` (L1360–1376), the "unreadable MANIFEST / unreadable DOC aborts rather than reporting a number" assertions; surfaces via `./scripts/docs_gate.sh` as `✗ docs gate FAILED — 1 of 25`

## Measured facts (both sides, same box, same blob)

- **Red side (reviewer's context):** `./scripts/docs_gate.sh` FAILED 1/25 at `e0e63f47b` and twice at `d7d73fc44` (clean tree); running the script directly reproduces in ~1s: `an unreadable MANIFEST aborts rather than reporting a number: got False, want True` (and the DOC twin), `exit=1`.
- **Green side (research session's context):** three `docs_gate.sh` runs (post-commit at `e0e63f47b`; re-run at `e0e63f47b`; pre-commit at the `d7d73fc44` state) all PASSED 25/25; a direct bare run exits 0 with the arms silent (all-pass). The chmod premise is enforced in that context too (`uid 501`; `chmod 000` → `cat: Permission denied`) — so the earlier load/concurrency explanation for the split is REFUTED, and so is any chmod-premise theory: **the arm monkeypatches `Path.open`/`Path.read_text` to raise `OSError(1450, "Insufficient system resources")` for paths under a temp root — no real file permission is involved.**

## Interpretation (per the reviewer, adopted)

The split is in the **execution premise, not the tree**: in the red context the patched I/O layer does not intercept the manifest read (no `BlindRead` raised → `eq(False, True)` records the failure); in the green context it does (arm passes — "a green canary may be inert" cuts the other way here: the GREEN side is the one whose evidence is weaker, since a pass on this arm only proves the patch fired, and the failure mode is a patch that silently does not). Candidate mechanisms to check on repro: Python version / interpreter resolution differences (`python3 -V` both sides), pathlib `Path.open` vs `io.open` dispatch, import-time caching of `real_open` under different entry points.

## Required reproduction protocol (whoever picks this up)

Record ALL of: `id -u`, `python3 -V` + `command -v python3`, the exact invocation (bare vs docs_gate wrapper), full assertion text, and exit code — a PASS on this arm without those is unreadable (the check's own thesis).

## Tasks

- [ ] T1 Reproduce in a clean shell capturing the protocol above; identify the execution-premise difference (interpreter, entry point, or patch-target drift)
- [ ] T2 Classify: (a) patch-target bug (the audit's manifest read bypasses `Path.open`/`Path.read_text` under some condition — e.g. a `io.open`/`os.read` fallback path) → fix the arm to patch the layer the audit actually reads through; or (b) environmental (interpreter difference) → pin/detect the premise in the arm and document
- [ ] T3 Verify both directions: the arm reds when the patch does not fire (plant a canary the arm itself checks, per the `full_gate.sh` sentinel precedent) and passes when it does; re-run docs_gate from both contexts
- [ ] T4 Close with the measured record in this file; remove per the noise rule once landed

## Non-goal

The audit's production logic (`load_manifests`, `iter_bench_doc_labels`, the `BlindRead` guard itself) is measured-good (Issue 790 Finding 9); this issue is about the ARM's own liveness, not the guard.
