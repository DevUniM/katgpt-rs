#!/usr/bin/env python3
"""Hold the platform-dead_code zero across EVERY contract repo.

`platform_dead_code_audit.py` is a REPORT: it classifies and prints, and a
report holds nothing. The zero it measured on 2026-09-14 (0 findings · 1
MOD-REF over 8694 tracked `.rs` / 3433 units / 119452 candidate decls / 16
repos) was bought the same week, by hand: `ea4c2873` here (NEON_U8) and riir-ai
`7b97ab97e` (`note_ane_dispatch`, `gen_u64_bytes`). Until this file existed,
nothing would have objected when the sixth specimen landed.

This is the seventh instance of one shape in this workspace, and the first two
found real defects the moment they were pointed anywhere but at katgpt-rs:

    Issue 702  ci_gate_coverage              one repo -> 7 dead workflows
    Issue 725  numbering_drift_sweep         one repo -> 35 duplicate numbers
    2026-09-06 required_features_drift_sweep one repo -> clean, and pinned there
    2026-09-06 percentile_drift_sweep        one repo -> clean, and pinned there
    2026-09-07 trap_sentinel_drift_sweep     one repo -> 1 finding, pinned
    2026-09-12 restatement_drift_sweep       one repo -> 0, and pinned in four
    this file  platform_dead_code_drift_sweep  -> 2 riir-ai rows, both repaired

**Not in `docs_gate.sh`'s CHECKS, deliberately** — the same reason as every
other sweep in the family: CI has a single checkout, so the derived population
would be one repo and the sweep would print a confident green over the fifteen
it could not see. The per-push half is `platform_dead_code_floor_gate.py`,
katgpt-rs-scoped, and it is in CHECKS.

# Why this class in particular needs a CROSS-REPO verdict

Because the compiler that reports it is a platform, not a lane. `full_gate.yml`
is macOS/aarch64; `wasm32_gate.yml` is wasm32; the x86_64-native build that
emits `dead_code` for an aarch64-only helper runs on a workstation and nowhere
else. Every repo in the workspace is exposed in exactly the same way, and a
katgpt-rs-only gate would be coverage-shaped without being coverage — which is
precisely how the two riir-ai rows lived long enough to be found by hand.

# Two floors, and the second is the one that bites

See `platform_dead_code_drift_floors.txt`, where the numbers and their
reasoning live together. In short: `min_rs_files` catches the WALK going blind,
`min_candidate_decls` catches the PARSE going blind, and only the second moves
when the token pass breaks on an unchanged tree — measured three times during
the classifier's construction, each time as a confident `0 findings`.

# A ceiling nobody has watched fail is a ceiling of unknown width

`--prove-fires` runs BY DEFAULT here (and is opt-in on the per-push gate, which
cannot afford ~5.6s of `git archive` on every push): it extracts `ea4c2873~1`
and `ea4c2873` and requires NEON_U8 PRESENT at the parent and absent at the
fix — a real tree whose answer is known independently, walked end to end by the
same `audit_repo` this sweep reads. `--no-prove-fires` skips it, loudly.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import platform_dead_code_audit as audit          # noqa: E402
import platform_dead_code_floor_gate as gate      # noqa: E402
# Reused, never re-derived: the marker NAME and the snapshot-vs-walk comparison
# are one definition shared by population_sync_gate and issue_citation_gate too
# (Issue 765). A second copy would be a second thing to get wrong, and this one
# decides whether a short population is a partial clone or a stale file.
from sweep_population import population_verdict  # noqa: E402

REPO_ROOT = HERE.parent
# Overridable for testing — the skill_repo_set_gate precedent (Issue 765's
# partial-clone sims run the real instruments over a symlink farm).
WORKSPACE = Path(os.environ.get("WORKSPACE_ROOT", str(REPO_ROOT.parent)))
FLOORS = HERE / "platform_dead_code_drift_floors.txt"

FIELDS = ("min_rs_files", "min_candidate_decls", "max_findings", "max_modref")


def read_floors() -> dict:
    rows: dict = {}
    with open(FLOORS, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) != 1 + len(FIELDS):
                sys.exit(f"✗ malformed floors row (want {1 + len(FIELDS)} fields): "
                         f"{raw.strip()}")
            rows[parts[0]] = {k: int(v) for k, v in zip(FIELDS, parts[1:])}
    if not rows:
        sys.exit("✗ floors file parsed to ZERO rows — a parser that returns nothing "
                 "for both 'absent' and 'malformed' disarms every ceiling below it")
    return rows


def cross_assert(floors: dict) -> list[str]:
    """The katgpt-rs row is the SAME quantity as the per-push gate's pins.

    Two files holding one number is the `docs_gate_paths_sync.py` shape: assert
    they agree rather than trusting them. A sweep floored looser than the gate
    would report a repo the gate has already red as clean.
    """
    bad: list[str] = []
    row = floors.get("katgpt-rs")
    if row is None:
        return ["katgpt-rs has no floors row, so the per-push gate's pins are "
                "cross-asserted against nothing"]
    pins = gate.read_pins(gate.PINS)
    for key in ("min_rs_files", "min_candidate_decls"):
        if row[key] != pins[key]:
            bad.append(f"katgpt-rs {key}: sweep pins {row[key]}, "
                       f"platform_dead_code_floors.txt pins {pins[key]} — one "
                       f"quantity, two files, and they disagree")
    if row["max_findings"] != pins["max_findings"]:
        bad.append(f"katgpt-rs max_findings: sweep {row['max_findings']}, gate "
                   f"{pins['max_findings']}")
    if row["max_modref"] != len(pins["modref"]):
        bad.append(f"katgpt-rs max_modref: sweep pins {row['max_modref']}, the gate "
                   f"pins {len(pins['modref'])} MOD-REF row(s) BY NAME — the count "
                   f"here must equal the membership there")
    return bad


def measure(path: Path) -> dict:
    r = audit.audit_repo(path)
    return {"files": r.files, "units": r.units, "candidates": r.candidates,
            "findings": r.findings, "modref": r.mod_rows}


def main() -> int:
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass

    print("=== platform-dead_code drift sweep (every contract repo) ===\n")

    # The classifier's own canary, before any count is read. Exit 2, never 1:
    # an untrustworthy instrument is a different verdict from drift.
    if audit.selftest():
        print("✗ the classifier's own self-test does not pass — every count below "
              "would be unreadable")
        return 2
    for f in gate.gate_selftest():
        print(f"✗ INSTRUMENT: the shared pin comparison is broken: {f}")
        return 2
    print()

    floors = read_floors()
    present = {p.name: p for p in audit.derive_repos(WORKSPACE)}

    fail = 0
    deferred: list[str] = []

    for b in cross_assert(floors):
        print(f"⛔ CROSS-ASSERT: {b}")
        fail += 1

    # The population axis, against BOTH canonical sets: the committed
    # `repo_set.txt` snapshot (via the shared Issue-765 helper) and this
    # sweep's own floors file. A derived population is only ever as wide as the
    # box, so a sweep that just walks and prints a green certifies 16 repos
    # while reading like 20 — the confident-green-over-a-subset failure this
    # whole family exists to refuse.
    pop_lines, pop_deferred, pop_fail = population_verdict(floors, present)
    for _line in pop_lines:
        print(_line)
    deferred += pop_deferred
    fail += pop_fail

    # UNPINNED is a red under the marker too: a repo that is ON DISK and has no
    # row is a repo joining the population, which no amount of partial checkout
    # explains.
    unpinned = sorted(set(present) - set(floors))
    if unpinned:
        print(f"⛔ UNPINNED (a repo joined the population) — re-pin deliberately, "
              f"with the numbers printed below: {', '.join(unpinned)}")
        fail += len(unpinned)

    for repo in sorted(present):
        m = measure(present[repo])
        f = floors.get(repo)
        bad: list[str] = []
        if f is not None:
            if m["files"] < f["min_rs_files"]:
                bad.append(f"WALK {m['files']} .rs < floor {f['min_rs_files']}")
            if m["candidates"] < f["min_candidate_decls"]:
                bad.append(f"PARSE {m['candidates']} candidate(s) < floor "
                           f"{f['min_candidate_decls']}")
            if len(m["findings"]) > f["max_findings"]:
                bad.append(f"findings {len(m['findings'])} > ceiling "
                           f"{f['max_findings']}")
            if len(m["modref"]) > f["max_modref"]:
                bad.append(f"MOD-REF {len(m['modref'])} > ceiling {f['max_modref']}")
        mark = "⛔" if f is None else ("✗" if bad else "✓")
        print(f"{mark} {repo:<22} {m['files']:>5} .rs · {m['candidates']:>6} cand · "
              f"{m['units']:>4} unit(s) · {len(m['findings'])} finding(s) · "
              f"{len(m['modref'])} MOD-REF")
        for b in bad:
            print(f"     ⛔ {b}")
        for row in m["findings"]:
            print(audit.row_line(row, "⛔"))
        for row in m["modref"]:
            print(audit.row_line(row, "·"))
        fail += len(bad)

    print()
    if "--no-prove-fires" in sys.argv:
        deferred.append("--prove-fires SKIPPED by flag — the ceilings above are "
                        "pins nobody watched fail on this run")
    else:
        print("── --prove-fires ea4c2873: the known-answer tree ──")
        if audit.prove_fires(REPO_ROOT, "ea4c2873", "NEON_U8",
                             "crates/katgpt-pruners"):
            fail += 1
        print()

    if fail:
        print(f"✗ platform dead_code drift sweep FAILED — {fail} breach(es)")
        print("  Do NOT raise a ceiling to clear a red: a finding is an item that is "
              "dead code on every platform but one, and NO automatic lane in this "
              "workspace compiles the platform that would say so. The repair is one "
              "attribute — give the declaration the same cfg its uses already carry.")
        for d in deferred:
            print(f"  ⚠ {d}")
        return 1

    line = (f"✓ platform dead_code drift sweep PASSED — {len(present)} repo(s) "
            f"(derived: BOUNDARY.md + .git), all pinned")
    if deferred:
        line += "; DEFERRED: " + "; ".join(deferred)
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
