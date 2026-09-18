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
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import platform_dead_code_audit as audit          # noqa: E402
import platform_dead_code_floor_gate as gate      # noqa: E402
# Reused, never re-derived: the marker NAME and the snapshot-vs-walk comparison
# are one definition shared by population_sync_gate and issue_citation_gate too
# (Issue 765). A second copy would be a second thing to get wrong, and this one
# decides whether a short population is a partial clone or a stale file.
from sweep_population import open_repo, population_verdict, pin_row_exempt  # noqa: E402
from worktree_state import (HeadDelta, delta_of, head_overlay,  # noqa: E402
                            sweep_advisory)

REPO_ROOT = HERE.parent
# Overridable for testing — the skill_repo_set_gate precedent (Issue 765's
# partial-clone sims run the real instruments over a symlink farm).
WORKSPACE = Path(os.environ.get("WORKSPACE_ROOT", str(REPO_ROOT.parent)))
FLOORS = HERE / "platform_dead_code_drift_floors.txt"

FIELDS = ("min_rs_files", "min_candidate_decls", "max_findings", "max_modref")

# ONE list, read by the worktree advisory AND by the HEAD re-classification.
# Issue 822 T5a measured the cost of the second copy: `instrument_reachability`
# carried a hand-typed glob list beside its advisory that named `.yml` and not
# `.yaml`, so a dirty root was silently outside its own declared population.
SCOPE = ("*.rs",)


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


def row_key(f) -> tuple:
    """A finding's identity, LINE-FREE.

    Any edit above a declaration shifts its line, so a line-bearing key reports
    every row in an edited file as UNCOMMITTED *and* MASKED at once — the
    `citation_drift_sweep` rule, restated because this is the second axis where
    it bites. The identity of the row is the DECLARATION; `uses` and `atoms`
    are what the classifier concluded about it and may legitimately move
    without the row becoming a different row.
    """
    return (f.rel, f.kind, f.name)


def adjudicate(repo: Path, m: dict) -> tuple[HeadDelta, HeadDelta]:
    """Findings and MOD-REF rows split COMMITTED / UNCOMMITTED / MASKED.

    ⛔ **CROSS-FILE, deliberately — and Issue 822's own task table put this
    sweep in the other bucket.** `head_delta`'s shortcut is sound only where a
    row's existence depends on its OWN file's bytes; here it does not. A
    candidate is UNIT-scoped: `audit_repo` resolves a module chain into one
    unit and counts a declaration's uses across every member file, so editing
    one file moves its SIBLINGS' verdicts and the per-file re-read would invent
    rows. Measured by reading `audit_repo`, not assumed from the table.

    So this is `head_overlay` + `delta_of` — the whole classifier re-run with
    HEAD's bytes substituted at the one seam that turns a path into text. The
    cost is a second `audit_repo` for the repos that HAVE dirty `.rs`, and
    **zero** on a clean tree: an empty overlay means skip the second
    classification entirely, never "overlay nothing".
    """
    overlay = head_overlay(repo, SCOPE)
    if not overlay:
        return (HeadDelta(list(m["findings"]), [], []),
                HeadDelta(list(m["modref"]), [], []))
    head = audit.audit_repo(repo, overlay=overlay)
    return (delta_of(m["findings"], head.findings, row_key),
            delta_of(m["modref"], head.mod_rows, row_key))


def selftest() -> list[str]:
    """This file's own Issue 822 arithmetic — the classifier's arms cannot
    reach it (Issue 775's sentence, at the only place it applies here)."""
    fails: list[str] = []

    class R:
        def __init__(self, rel, name, kind="const"):
            self.rel, self.name, self.kind = rel, name, kind
            self.line = 1

    a, b = R("src/lib.rs", "A"), R("src/lib.rs", "B")
    d = delta_of([a], [b], row_key)
    if [r.name for r in d.uncommitted] != ["A"]:
        fails.append("delta_of: a worktree-only row is not UNCOMMITTED")
    if [r.name for r in d.masked] != ["B"]:
        fails.append("delta_of: a HEAD-only row is not MASKED")
    # ⛔ The pin reads `.head` — `committed + masked`, never `committed`. A
    # ceiling that read `committed` alone would pass a repo whose worktree
    # hides a committed finding, which is the silent direction this whole
    # issue is about.
    if {r.name for r in d.head} != {"B"}:
        fails.append("HeadDelta.head: a MASKED row is not in the pins' "
                     "population")
    # LINE-FREE: the same declaration, moved down the file, is ONE row.
    moved = R("src/lib.rs", "A")
    moved.line = 900
    if delta_of([moved], [a], row_key) != HeadDelta([moved], [], []):
        fails.append("row_key: a line shift reported one declaration as both "
                     "UNCOMMITTED and MASKED")
    # ...and the kind is part of the identity, so a `mod` row and an item row
    # of the same name never cancel each other out.
    if not delta_of([R("src/lib.rs", "A", "mod")], [a], row_key).uncommitted:
        fails.append("row_key: `kind` is not in the identity, so a MOD-REF row "
                     "and an item row of one name collapse")
    if SCOPE != ("*.rs",):
        fails.append(f"SCOPE is {SCOPE} — the advisory and the HEAD "
                     f"re-classification read this one list; widening it "
                     f"changes both, which is the point")
    fails += _git_arms()
    return fails


def _git_arms() -> list[str]:
    """`adjudicate` end to end, against REAL git.

    The arms above pin the arithmetic over synthetic rows; this one pins the
    join — `head_overlay` finding the dirty file, `audit_repo(overlay=)`
    re-classifying it, `delta_of` bucketing the answer — because every one of
    those three has a different way of being silently inert, and a mock of git
    would assert the mock. ~0.4s, and it is the only thing in this sweep that
    proves the ratchet stopped reading the working tree.
    """
    fails: list[str] = []
    fires = audit._case_tree("neon shape fires")["src/lib.rs"]
    clean = audit._case_tree("decl gated the same way is clean")["src/lib.rs"]

    def git(root, *args):
        return subprocess.run(("git", "-C", str(root)) + args,
                              capture_output=True, encoding="utf-8",
                              errors="replace", check=True)

    def fixture(td, committed: str, worktree: str) -> Path:
        root = Path(td)
        (root / "src").mkdir(parents=True)
        (root / "Cargo.toml").write_text(
            '[package]\nname = "t"\nversion = "0.0.0"\n', encoding="utf-8")
        (root / "src" / "lib.rs").write_text(committed, encoding="utf-8")
        git(root, "init", "-q")
        git(root, "config", "user.email", "arm@example.invalid")
        git(root, "config", "user.name", "arm")
        git(root, "add", "-A")
        git(root, "-c", "commit.gpgsign=false", "commit", "-qm", "base")
        (root / "src" / "lib.rs").write_text(worktree, encoding="utf-8")
        return root

    def names(delta) -> set:
        return {r.name for r in delta}

    # 1. UNCOMMITTED — the worktree fires, HEAD does not. The row is SHOWN and
    #    must not reach the ceiling. This is Issue 822's measured shape.
    with tempfile.TemporaryDirectory() as td:
        root = fixture(td, clean, fires)
        m = measure(root)
        if names(m["findings"]) != {"NEON_U8"}:
            fails.append("git arm: the worktree pass found no row — every "
                         "comparison in this arm is vacuous")
        d, _mod = adjudicate(root, m)
        if names(d.uncommitted) != {"NEON_U8"}:
            fails.append("adjudicate: a worktree-only finding is not "
                         "UNCOMMITTED — the ratchet is reading the tree")
        if d.head:
            fails.append("adjudicate: an UNCOMMITTED row reached `.head`, "
                         "which is the quantity the pin adjudicates")

    # 2. MASKED — the silent direction. HEAD carries the row, the worktree
    #    hides it, and a sweep that adjudicated the tree reports this clean.
    with tempfile.TemporaryDirectory() as td:
        root = fixture(td, fires, clean)
        m = measure(root)
        if m["findings"]:
            fails.append("git arm: the worktree pass found a row where the "
                         "MASKED direction needs none")
        d, _mod = adjudicate(root, m)
        if names(d.masked) != {"NEON_U8"}:
            fails.append("adjudicate: a committed finding the worktree hides "
                         "was not recovered as MASKED")
        if names(d.head) != {"NEON_U8"}:
            fails.append("adjudicate: a MASKED row is missing from `.head`, "
                         "so the ceiling passes over a committed finding")

    # 3. A CLEAN tree costs nothing — no overlay, no second classification.
    #    A helper that walks anyway on every run is one sweeps stop calling.
    with tempfile.TemporaryDirectory() as td:
        root = fixture(td, fires, fires)
        m = measure(root)
        real = audit.audit_repo
        calls = []

        def counted(repo, overlay=None):
            calls.append(overlay)
            return real(repo, overlay=overlay)

        audit.audit_repo = counted
        try:
            d, _mod = adjudicate(root, m)
        finally:
            audit.audit_repo = real
        if calls:
            fails.append(f"adjudicate: re-classified a CLEAN repo "
                         f"({len(calls)} extra audit_repo call(s)) — the empty "
                         f"overlay must mean SKIP, not 'overlay nothing'")
        if names(d.committed) != {"NEON_U8"} or d.uncommitted or d.masked:
            fails.append("adjudicate: a clean tree's rows are not all COMMITTED")
    return fails


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
    for f in selftest():
        print(f"✗ INSTRUMENT: this sweep's own HEAD arithmetic is broken: {f}")
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

    # Issue 797 — the worktree is not the repo. This run reads files that
    # concurrent sessions are editing, so a finding may sit on a line no
    # commit contains. ADVISORY, never a failure: a sweep that hard-reds on
    # an ordinary dirty worktree is a sweep nobody runs. It rides the FINAL
    # line in BOTH directions (the `deferred` precedent) and is SILENT
    # unless the dirty set meets this sweep's own population — the declaration sites.
    #
    # ⚠ Issue 822 — the row counts are filled in by the per-repo loop BELOW,
    # so this call is made after it. The advisory is a repo-level banner and
    # cannot say WHICH rows; that is the gap this issue exists for.
    for _line in pop_lines:
        print(_line)
    deferred += pop_deferred
    fail += pop_fail

    # UNPINNED is a red under the PARTIAL marker too: a repo that is ON DISK
    # and has no row is a repo joining the population, which no amount of
    # partial checkout explains.
    #
    # ⚠ Issue 821: that reasoning is right and it does not cover
    # DOCS_GATE_KNOWN_EXTRA, which says the opposite thing — those repos are on
    # disk and are declared NOT to be joining. This sweep reaches the same
    # conclusion by its own set difference rather than through the family's
    # per-repo loop, so the shared `pin_row_exempt` had to be applied here by
    # hand; it is the one bespoke shape in the family and was still red on
    # three repos it reported 0 findings in.
    unpinned = sorted(set(present) - set(floors)
                      - {n for n in present if pin_row_exempt(n)})
    if unpinned:
        print(f"⛔ UNPINNED (a repo joined the population) — re-pin deliberately, "
              f"with the numbers printed below: {', '.join(unpinned)}")
        fail += len(unpinned)

    n_uncommitted = n_masked = 0
    for repo in sorted(present):
        # Issue 842: `repo` is the CONTRACT name and `present[repo]` the
        # contract-named handle; measure the on-disk directory, label by the
        # name.
        path = open_repo(repo, WORKSPACE)
        m = measure(path)
        # Issue 822 — the ratchet is a claim about the REPO, and a repo's
        # state is its commits. The DISPLAY reads the worktree (it is what the
        # files say today, and hiding that would be its own lie); the PINS read
        # `.head`, which is the only quantity a commit of this checkout would
        # reproduce. One ghost row, two provenances, opposite verdicts.
        f_delta, mod_delta = adjudicate(path, m)
        n_uncommitted += len(f_delta.uncommitted) + len(mod_delta.uncommitted)
        n_masked += len(f_delta.masked) + len(mod_delta.masked)
        held = {row_key(r) for r in f_delta.uncommitted} | {
            row_key(r) for r in mod_delta.uncommitted}
        hidden = len(f_delta.masked) + len(mod_delta.masked)

        f = floors.get(repo)
        bad: list[str] = []
        if f is not None:
            # The FLOORS stay on the worktree deliberately: they detect the
            # instrument going blind on THIS box's checkout, which is the
            # thing that was read, and a HEAD walk cannot answer that.
            if m["files"] < f["min_rs_files"]:
                bad.append(f"WALK {m['files']} .rs < floor {f['min_rs_files']}")
            if m["candidates"] < f["min_candidate_decls"]:
                bad.append(f"PARSE {m['candidates']} candidate(s) < floor "
                           f"{f['min_candidate_decls']}")
            if len(f_delta.head) > f["max_findings"]:
                bad.append(f"findings {len(f_delta.head)} committed > ceiling "
                           f"{f['max_findings']}")
            if len(mod_delta.head) > f["max_modref"]:
                bad.append(f"MOD-REF {len(mod_delta.head)} committed > ceiling "
                           f"{f['max_modref']}")
        mark = "⛔" if f is None else ("✗" if bad else "✓")
        split = ""
        if held or hidden:
            split = (f" [{len(f_delta.committed) + len(mod_delta.committed)}"
                     f" committed"
                     + (f", {len(held)} uncommitted" if held else "")
                     + (f", {hidden} MASKED" if hidden else "") + "]")
        print(f"{mark} {repo:<22} {m['files']:>5} .rs · {m['candidates']:>6} cand · "
              f"{m['units']:>4} unit(s) · {len(m['findings'])} finding(s) · "
              f"{len(m['modref'])} MOD-REF{split}")
        for b in bad:
            print(f"     ⛔ {b}")
        for row in m["findings"]:
            print(audit.row_line(row, "⛔")
                  + (" [UNCOMMITTED — not adjudicated]"
                     if row_key(row) in held else ""))
        for row in m["modref"]:
            print(audit.row_line(row, "·")
                  + (" [UNCOMMITTED — not adjudicated]"
                     if row_key(row) in held else ""))
        # MASKED rows are NOT in the worktree lists — that is what MASKED
        # means — so they are printed from the HEAD side or they are printed
        # nowhere, and the ceiling reds over a row nobody can see.
        for row in list(f_delta.masked) + list(mod_delta.masked):
            print(audit.row_line(row, "⛔")
                  + " [MASKED — committed, hidden by this worktree]")
        fail += len(bad)

    # Issue 797/798 — the worktree is not the repo, and this checkout is not
    # origin. ADVISORY, never a failure: a sweep that hard-reds on an ordinary
    # dirty tree is a sweep nobody runs. It rides the FINAL line in BOTH
    # directions, and Issue 822's row counts ride with it — the per-row labels
    # above say WHICH, this says the class exists at all, and a notice printed
    # in only one of those places is one nobody reads on the run that needs it.
    deferred.extend(sweep_advisory(
        present, SCOPE, root=WORKSPACE,
        uncommitted_rows=n_uncommitted, masked_rows=n_masked))

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
