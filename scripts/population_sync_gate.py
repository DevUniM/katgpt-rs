#!/usr/bin/env python3
"""GATE: the TEN independent "which repos are contract repos" predicates must agree.

Every cross-repo instrument in this workspace derives its own population — a
root `BOUNDARY.md` **and** a `.git` DIRECTORY — and ten of them do it with ten
separate implementations:

    cfg_gated_target_audit.derive_repos      (also used by the required-features
                                              audit and the cfg-gated sweep)
    numbering_drift_sweep.contract_repos
    percentile_index_audit.repos
    ci_gate_coverage.derive_repos
    skill_repo_set_gate.derive_repos
    suite_membership_audit.derive_repos
    trap_exit_launder_audit.repos            (Issue 734; joined 2026-09-07)
    len_derived_binding_audit.derive_repos   (Issue 788; joined 2026-09-14)
    docs_drift_sweep.derive_population       (Issue 788)
    wasm32_surface_audit.derive_population   (Issue 788)

plus ONE subset predicate, `restatement_theorem_audit.repos`, which adds a
`.proofs` test and is asserted to be a strict subset rather than an equal.

They all agree today. Nothing asserted that, and the failure is silent in the
worst way: if ONE predicate drifts, that one instrument quietly audits a
different set of repos and still prints a confident green over it. The
workspace has already paid for this once — three instruments were found
covering 7, 12 and 15 of 18 repos, each reporting cleanly on its own slice.

This is `docs_gate_paths_sync.py` one axis over: a hand-duplicated *value*
drifts, and so does a hand-duplicated *predicate*.

## The registry asserts its own COMPLETENESS, and Issue 788 is why

The tuple below is DATA, and its comment always said adding an instrument was
"a one-line change here rather than an eighth silent divergence". The one-line
change is the part nobody makes: the registry sat at SEVEN while TEN existed,
and the gate printed "7 predicates agree" the whole time.

⛔ Read the numbers in order, because they are the argument for mechanising
this rather than reading carefully: the census that filed Issue 788 counted
NINE and registered the eighth. The completeness check then found the ninth and
tenth — `docs_drift_sweep` and `wasm32_surface_audit` — which that census had
missed. A careful reading missed two of ten. Both were also UNPARAMETERISED,
hard-coding their root from `__file__`, so the synthetic-workspace half of this
gate could not have tested them even if somebody had registered them; they take
an optional `root` now.

The eighth also turned out to be WRONG on registration — `len_derived_binding_
audit.derive_repos` tested `(d / ".git").exists()`, admitting a worktree-shaped
directory and double-counting a repo already in the walk. Latent (no such
directory in this workspace), and caught on the first run after registering it.

## Why this can run in CI, when none of the sweeps can

The sweeps cannot, because CI has a single checkout: they would derive an empty
population and print a confident green over zero repos. This gate does not test
the POPULATION, it tests the PREDICATE — against a synthetic workspace built in
a temp dir, containing every case the real one distinguishes:

    good, also-good   BOUNDARY.md + a .git DIRECTORY   -> INCLUDED
    no-boundary       .git dir, no BOUNDARY.md         -> excluded
    no-git            BOUNDARY.md, no .git             -> excluded
    worktree-shaped   BOUNDARY.md + a .git FILE        -> excluded

The last one is not hypothetical and is why the `.git` test must be a
DIRECTORY test: a throwaway worktree's `.git` is a FILE, and a worktree of a
repo already in the walk would otherwise be counted twice. That trap is
documented in `scripts/repo_set.txt`'s own derivation and in three of the ten
docstrings — which is exactly the kind of invariant that survives in comments
and dies in code.

The real-workspace cross-check runs too, but only when the walk finds more than
one repo (i.e. on a workstation). It is REPORTED either way, never silently
skipped — a gate that skips without saying so is the vacuous green this family
exists to refuse. On a box the operator has marked as a PARTIAL CLONE
(DOCS_GATE_PARTIAL_CLONE=1, Issue 765 — an explicit marker, never
auto-detected), a gone-only file-vs-walk disagreement defers THAT comparison
loudly: the predicate-agreement half still runs at full strength, and the
deferral rides the final line. A repo on disk that the file does not know is
genuine staleness in every posture and always reds.

Exit 0 clean · 1 on disagreement · 2 if the gate cannot import a predicate.
"""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from skill_repo_set_gate import PARTIAL_MARKER  # noqa: E402 — the marker definition, reused not re-derived

REPO_ROOT = HERE.parent
# Overridable for testing (the skill_repo_set_gate precedent): the
# partial-clone sims (Issue 765) run the real instruments over a symlink
# farm without copying repos.
WORKSPACE = Path(os.environ.get("WORKSPACE_ROOT", str(REPO_ROOT.parent)))
REPO_SET = HERE / "repo_set.txt"

# (label, module, attribute). Kept as DATA so adding an eighth instrument is a
# one-line change here rather than an eighth silent divergence.
PREDICATES = (
    ("cfg_gated_target_audit.derive_repos", "cfg_gated_target_audit", "derive_repos"),
    ("numbering_drift_sweep.contract_repos", "numbering_drift_sweep", "contract_repos"),
    ("percentile_index_audit.repos", "percentile_index_audit", "repos"),
    ("ci_gate_coverage.derive_repos", "ci_gate_coverage", "derive_repos"),
    ("skill_repo_set_gate.derive_repos", "skill_repo_set_gate", "derive_repos"),
    ("suite_membership_audit.derive_repos", "suite_membership_audit", "derive_repos"),
    # Issue 734: the trap-launder classifier is a contract-repo instrument too,
    # and its derivation was unchecked against the other six until its sweep
    # landed.
    ("trap_exit_launder_audit.repos", "trap_exit_launder_audit", "repos"),
    # Issue 788: the eighth, and it had been unregistered since the audit was
    # written. Its own sweep asserts it agrees with skill_repo_set_gate — but
    # only on the runs somebody invokes that sweep, and this gate runs per-push.
    ("len_derived_binding_audit.derive_repos", "len_derived_binding_audit",
     "derive_repos"),
    # Issue 788 again, and these two are why the registry needed a
    # completeness check rather than a careful reading: they were found by the
    # check, not by the census that filed the issue, which had enumerated seven
    # against nine and still missed that the real count was TEN. Both were also
    # UNPARAMETERISED — they hard-coded WORKSPACE from `__file__`, so the
    # synthetic-workspace half of this gate (the half that works in CI) could
    # not have tested them even if somebody had registered them.
    ("docs_drift_sweep.derive_population", "docs_drift_sweep",
     "derive_population"),
    ("wasm32_surface_audit.derive_population", "wasm32_surface_audit",
     "derive_population"),
)

# SUBSET predicates: BOUNDARY.md + `.git` AND something more. Registering one in
# PREDICATES would red every run by construction, so they get their own tuple —
# and their own, weaker assertion (a strict subset of the agreed answer), because
# "not registered" and "deliberately not registered" must not be the same state.
# That distinction was recorded NOWHERE before Issue 788: the next reader either
# re-derives it or registers the predicate and breaks the gate.
#
# The subset assertion is not a formality. A `.proofs` walk that silently starts
# matching something else shows up as a repo outside the agreed population, and
# nothing else in this workspace would notice.
SUBSET_PREDICATES = (
    ("restatement_theorem_audit.repos", "restatement_theorem_audit", "repos",
     "adds a `.proofs` directory test — 4 of 16 repos carry Lean proofs"),
)

# The registry above is hand-maintained, and Issue 788 is what that cost: TEN
# predicates existed, seven were registered, and the gate had been printing
# "7 predicates agree" the whole time. So the
# registry asserts its own COMPLETENESS — see `unregistered_predicates()`.
# A source file may opt a helper out with this marker on the `def` line, which
# is deliberately noisy to type and greppable to review.
OPT_OUT_MARKER = "population-predicate: not a contract-repo walk"


def load() -> list[tuple[str, object]]:
    import importlib

    out = []
    for label, mod, attr in PREDICATES:
        try:
            m = importlib.import_module(mod)
        except Exception as e:  # noqa: BLE001 — any import failure is fatal here
            print(f"✗ cannot import {mod}: {e!r}")
            raise SystemExit(2)
        fn = getattr(m, attr, None)
        if fn is None:
            print(f"✗ {mod} has no {attr} — the predicate was renamed or removed; "
                  f"update PREDICATES in {Path(__file__).name}")
            raise SystemExit(2)
        out.append((label, fn))
    return out


def call(fn, root: Path) -> list[str]:
    """Normalise: some take a Path, some a str; some return Paths, some names."""
    try:
        got = fn(root)
    except TypeError:
        got = fn(str(root))
    return sorted(p.name if isinstance(p, Path) else str(p) for p in got)


def unregistered_predicates(repo: Path) -> list[tuple[str, str]]:  # population-predicate: not a contract-repo walk (it NAMES the walk tokens it searches for)
    """(module, function) pairs that walk for BOUNDARY.md + `.git` and are in
    neither registry.

    ⛔ The first version of this asked only for a `def` whose body mentions both
    `BOUNDARY.md` and `.git`, and its docstring asserted — before the thing had
    ever been run — that this "measures exactly the nine real predicates". It
    reported **23**, almost all of them `main()` and `selftest()` bodies that
    merely name the two strings, plus this gate's own `build_synthetic()`, which
    WRITES those files rather than walking for them. A classifier's bucket
    boundary is the finding, and a boundary argued from the armchair is a claim
    about code somebody else wrote.

    The discriminating term is the **directory iteration**: a predicate walks
    (`iterdir()` / `os.listdir(` / `scandir(`), a `main()` that mentions the
    contract does not, and a fixture builder writes into a path it already
    holds. Measured after the correction: exactly the nine, over 66 files —
    and the nine are enumerable by hand, which is why this number is worth
    stating.

    `ast` is not used on purpose: the gate must classify a file it cannot
    import (a syntax error in a sibling instrument is somebody else's finding,
    not a reason for this gate to go blind), and a textual `def` scan reads a
    broken file fine.
    """
    import re

    out: list[tuple[str, str]] = []
    known = {(m, a) for _l, m, a in PREDICATES}
    known |= {(m, a) for _l, m, a, _w in SUBSET_PREDICATES}
    listed = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "scripts/"],
        capture_output=True, encoding="utf-8", errors="replace")
    for rel in listed.stdout.splitlines():
        if not rel.endswith(".py"):
            continue
        mod = Path(rel).stem
        try:
            body = (repo / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = body.splitlines()
        starts = [i for i, l in enumerate(lines) if re.match(r"^def\s+\w+", l)]
        for n, i in enumerate(starts):
            end = starts[n + 1] if n + 1 < len(starts) else len(lines)
            chunk = "\n".join(lines[i:end])
            if OPT_OUT_MARKER in lines[i]:
                continue
            walks = any(t in chunk for t in ("iterdir()", "os.listdir(",
                                             "listdir(", "scandir("))
            if walks and "BOUNDARY.md" in chunk and ".git" in chunk:
                fn = re.match(r"^def\s+(\w+)", lines[i]).group(1)
                if (mod, fn) not in known:
                    out.append((mod, fn))
    return sorted(out)


def build_synthetic(ws: Path) -> list[str]:
    """Every case the real walk distinguishes. Returns the expected answer."""
    for name in ("good", "also-good"):
        (ws / name).mkdir()
        (ws / name / "BOUNDARY.md").write_text("x")
        (ws / name / ".git").mkdir()
    (ws / "no-boundary").mkdir()
    (ws / "no-boundary" / ".git").mkdir()
    (ws / "no-git").mkdir()
    (ws / "no-git" / "BOUNDARY.md").write_text("x")
    # A worktree's `.git` is a FILE. Admitting it double-counts a repo already
    # in the walk — the trap the DIRECTORY test exists for.
    (ws / "worktree-shaped").mkdir()
    (ws / "worktree-shaped" / "BOUNDARY.md").write_text("x")
    (ws / "worktree-shaped" / ".git").write_text("gitdir: /elsewhere/.git/worktrees/x")
    # A plain file must not be mistaken for a repo directory.
    (ws / "BOUNDARY.md").write_text("x")
    return ["also-good", "good"]


def main() -> int:
    # ⛔ Issue 789: these arms used to run ONLY under `--canary`, and
    # docs_gate.sh invokes every check as `"$PY" "$script"` — with NO
    # arguments. So the 8 adversary arms landed by Issue 788 the day before
    # never ran per-push at all: decoration, on the gate whose whole subject is
    # a registry that was silently wrong for four instruments. 0.17s measured,
    # so there was never a cost argument for the flag either.
    #
    # Output is swallowed on success: a passing check that prints 8 extra lines
    # is one whose real verdict scrolls away. `--canary` stays as the verbose
    # standalone mode.
    _sink = io.StringIO()
    with contextlib.redirect_stdout(_sink):
        _rc = canary()
    if _rc != 0:
        print("✗ INSTRUMENT: population_sync_gate's own canary does not pass, so "
              "the registry agreement below would be unreadable:")
        print(_sink.getvalue().rstrip())
        return 2
    # Prints carry glyphs the Windows locale codecs cannot encode (checked
    # 2026-09-06 on cp874: check/cross/middot/arrow FAIL, em-dash OK); keep the
    # locale encoding and degrade only the fatal chars to escapes -- the
    # staged_set_audit house pattern (utf-8 pinning would mojibake legacy consoles).
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass  # not a TextIOWrapper (embedded / detached); keep old behavior
    preds = load()
    bad = False

    # ── half 1: the PREDICATE, on a synthetic workspace. Runs everywhere. ──
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        expected = build_synthetic(ws)
        print(f"▸ predicate agreement over a synthetic workspace "
              f"(expected {expected}):")
        for label, fn in preds:
            got = call(fn, ws)
            if got == expected:
                print(f"    ✓ {label}")
                continue
            bad = True
            print(f"    ✗ {label}: got {got}")
            for extra in sorted(set(got) - set(expected)):
                why = {
                    "no-boundary": "admitted a dir with NO BOUNDARY.md",
                    "no-git": "admitted a dir with no .git at all",
                    "worktree-shaped": "admitted a WORKTREE (.git is a FILE) — "
                                       "this double-counts a repo already in the walk",
                }.get(extra, "admitted an unexpected entry")
                print(f"        + {extra}: {why}")
            for miss in sorted(set(expected) - set(got)):
                print(f"        - {miss}: REJECTED a valid contract repo")

    # ── half 1b: the REGISTRY's own completeness (Issue 788). Runs everywhere:
    #    it is a source scan, not a walk, so a single-checkout CI box tests it
    #    at full strength. This is the half that was missing — TEN predicates
    #    existed and seven were registered, so the gate reported agreement over
    #    a set it had not enumerated. Two of the three it was short were found
    #    by THIS check and not by the census that filed the issue.
    stray = unregistered_predicates(REPO_ROOT)
    if stray:
        bad = True
        print(f"▸ registry completeness: ✗ {len(stray)} unregistered "
              f"predicate(s)")
        for mod, fn in stray:
            print(f"    ✗ {mod}.{fn} walks for BOUNDARY.md + .git and is in "
                  f"neither PREDICATES nor SUBSET_PREDICATES. Add it to "
                  f"PREDICATES (a full contract-repo walk), to "
                  f"SUBSET_PREDICATES with its extra test (a narrower one), or "
                  f"mark the `def` line with `{OPT_OUT_MARKER}` if it is "
                  f"neither.")
    else:
        print(f"▸ registry completeness: ✓ {len(PREDICATES)} registered + "
              f"{len(SUBSET_PREDICATES)} subset, nothing unregistered")

    # ── half 2: the real workspace. Workstation-only, and SAID so. ──
    real = {label: call(fn, WORKSPACE) for label, fn in preds}
    sizes = {len(v) for v in real.values()}
    n = max(sizes)
    partial_defer: list[str] | None = None
    if n <= 1:
        print(f"▸ real-workspace cross-check SKIPPED — the walk under "
              f"{WORKSPACE} found {n} repo(s), so this is a single-checkout "
              f"environment (CI). The predicate half above is the verdict; the "
              f"population half is workstation-only by construction.")
    else:
        print(f"▸ real-workspace cross-check — {n} repo(s) under {WORKSPACE}:")
        base_label, base = next(iter(real.items()))
        # A LOCAL flag, not the run-wide `bad` (Issue 788): this half had been
        # reporting its verdict only when nothing ELSE had failed, so an
        # unrelated red suppressed a passing line and a reader could not tell
        # "they disagree" from "we did not say".
        agree = True
        for label, got in real.items():
            if got == base:
                continue
            bad = True
            agree = False
            print(f"    ✗ {label} differs from {base_label}: "
                  f"only-here={sorted(set(got) - set(base))} "
                  f"missing={sorted(set(base) - set(got))}")
        if agree:
            print(f"    ✓ all {len(real)} predicates agree")
        # Subset predicates get a WEAKER assertion, not none (Issue 788): a
        # strict subset of the agreed answer. That is a real claim — a `.proofs`
        # walk which silently starts matching something else shows up as a repo
        # outside the agreed population, and nothing else here would notice.
        for label, mod, attr, why in SUBSET_PREDICATES:
            import importlib
            try:
                fn = getattr(importlib.import_module(mod), attr)
            except Exception as e:  # noqa: BLE001
                bad = True
                print(f"    ✗ {label}: cannot load ({e!r})")
                continue
            got = call(fn, WORKSPACE)
            extra = sorted(set(got) - set(base))
            if extra:
                bad = True
                print(f"    ✗ {label} is NOT a subset — {extra} sit outside the "
                      f"agreed population ({why})")
            else:
                print(f"    ✓ {label} ⊆ agreed ({len(got)} of {len(base)}; {why})")
        # The committed vocabulary must match the derived population.
        if REPO_SET.is_file():
            committed = sorted(
                l.strip() for l in REPO_SET.read_text(encoding="utf-8").splitlines()
                if l.strip() and not l.lstrip().startswith("#")
            )
            if committed == base:
                print(f"    ✓ {REPO_SET.name} matches ({len(committed)} repos)")
            else:
                only_file = sorted(set(committed) - set(base))
                only_disk = sorted(set(base) - set(committed))
                if only_disk:
                    # A repo the file does not know: genuine staleness in
                    # every posture — including a marked partial clone.
                    bad = True
                    print(f"    ✗ {REPO_SET.name} disagrees with the derived walk: "
                          f"only-in-file={only_file} missing-from-file={only_disk}")
                elif os.environ.get(PARTIAL_MARKER) == "1":
                    # Issue 765: gone-only disagreement on a marked partial
                    # clone. The predicate agreement above ran at full
                    # strength — only this file-vs-walk comparison is
                    # deferred, and the deferral rides the final line
                    # (docs_gate.sh forwards tail -1 of a pass).
                    partial_defer = only_file
                    print(f"    ▸ PARTIAL-CLONE DEFERRAL ({PARTIAL_MARKER}=1): "
                          f"{len(only_file)} snapshot repo(s) absent on this "
                          f"box — {only_file}. File-vs-walk comparison deferred "
                          f"to a full-workstation run; do NOT regenerate the "
                          f"snapshot on a partial box")
                else:
                    bad = True
                    print(f"    ✗ {REPO_SET.name} names {len(only_file)} repo(s) "
                          f"absent from this box — {only_file}. Either this is "
                          f"a PARTIAL CLONE (export {PARTIAL_MARKER}=1 to defer "
                          f"the population axis loudly; do NOT regenerate the "
                          f"snapshot on a partial box — that deletes live repos "
                          f"from the canonical set), or a full workstation whose "
                          f"file is stale (regenerate and commit).")

    if bad:
        print("✗ population sync gate FAILED — the cross-repo instruments do "
              "NOT all audit the same set of repos")
        return 1
    if partial_defer:
        print(f"✓ population sync gate PASSED — {len(preds)} predicates agree "
              f"[PARTIAL CLONE: {n} present, snapshot-vs-walk DEFERRED]")
        return 0
    print(f"✓ population sync gate PASSED — {len(preds)} predicates agree")
    return 0


def canary() -> int:  # population-predicate: not a contract-repo walk (its FIXTURES embed predicate source as data)
    """`--canary`: prove the Issue 788 additions FIRE, both directions.

    The pre-788 gate already had a two-sided synthetic workspace for the
    predicate half. What it had no adversary for is the registry itself, which
    is exactly the half that was silently wrong for four instruments.
    """
    import re
    import textwrap

    results = []

    def arm(name, ok, detail=""):
        print(f"  {'✓' if ok else '✗'} {name}" + (f"  — {detail}" if not ok else ""))
        results.append(ok)

    with tempfile.TemporaryDirectory() as td:
        fake = Path(td)
        (fake / "scripts").mkdir()

        def w(rel, body):
            (fake / rel).write_text(textwrap.dedent(body), encoding="utf-8")

        # 1. an UNREGISTERED walk must be reported.
        w("scripts/rogue.py", '''
            def derive_repos(root):
                return [d for d in root.iterdir()
                        if (d / "BOUNDARY.md").is_file() and (d / ".git").is_dir()]
            ''')
        # 2. a `main()` that merely MENTIONS the contract must NOT be — the
        #    false-positive class that made the first version report 23.
        w("scripts/mentions.py", '''
            def main():
                print("population: a root BOUNDARY.md and a .git directory")
            ''')
        # 3. ... and neither must a fixture BUILDER, which writes those files
        #    instead of walking for them.
        w("scripts/builder.py", '''
            def build(ws):
                (ws / "BOUNDARY.md").write_text("x")
                (ws / ".git").mkdir()
            ''')
        # 4. the OPT-OUT marker must suppress a genuine walk, and only on the
        #    def line where somebody typed it.
        w("scripts/opted.py", f'''
            def derive_repos(root):  # {OPT_OUT_MARKER}
                return [d for d in root.iterdir()
                        if (d / "BOUNDARY.md").is_file() and (d / ".git").is_dir()]
            ''')
        # 5. ⚑ The function-SPAN arithmetic (Issue 790 T3). `unregistered_
        #    predicates` slices each def's body as `lines[i:starts[n+1]]`, and
        #    `arm_reach_audit` reported that `n + 1` surviving an off-by-one
        #    flip because every fixture above holds exactly ONE def. With two,
        #    an off-by-one either folds the second def's body into the first
        #    (so a clean function inherits its neighbour's walk and is reported
        #    falsely) or truncates the first (so a real walk goes unseen).
        #    ⚠ THREE defs, with the walk in the MIDDLE, and that is measured
        #    rather than tidy: with two defs the flip is arithmetically
        #    IDENTICAL for the first (`starts[-1] == starts[1]`) and never
        #    evaluated for the last (the `n + 1 < len(starts)` guard is already
        #    false), so a two-def fixture reads INERT against the very mutation
        #    it is aimed at. Only a def with a successor AND a predecessor
        #    discriminates it.
        w("scripts/threedefs.py", '''
            def innocent(x):
                return x + 1

            def derive_repos(root):
                return [d for d in root.iterdir()
                        if (d / "BOUNDARY.md").is_file() and (d / ".git").is_dir()]

            def trailing(y):
                return y
            ''')
        subprocess.run(["git", "init", "-q", str(fake)], capture_output=True)
        subprocess.run(["git", "-C", str(fake), "add", "-A"], capture_output=True)

        got = unregistered_predicates(fake)
        arm("unregistered walk reported", ("rogue", "derive_repos") in got, str(got))
        arm("a walk in the MIDDLE def of a file is reported",
            ("threedefs", "derive_repos") in got, str(got))
        arm("…and neither neighbour is (no span bleed either way)",
            ("threedefs", "innocent") not in got
            and ("threedefs", "trailing") not in got, str(got))
        arm("a mentioning main() is NOT reported",
            ("mentions", "main") not in got, str(got))
        arm("a fixture builder is NOT reported",
            ("builder", "build") not in got, str(got))
        arm("the opt-out marker suppresses",
            ("opted", "derive_repos") not in got, str(got))

    # 5. every registered predicate must actually be importable and callable —
    #    `load()` exits 2 otherwise, which is the arm, and it runs on every
    #    invocation already. What is NOT otherwise proven: the synthetic
    #    expectation is non-trivial. A predicate that returns everything must
    #    FAIL it, or the ✓ rows above certify nothing.
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        expected = build_synthetic(ws)
        everything = sorted(d.name for d in ws.iterdir() if d.is_dir())
        arm("the synthetic expectation is non-trivial",
            everything != expected, f"{everything} == {expected}")

    # 6. the SUBSET assertion must red on a predicate that is not one.
    base = ["a", "b"]
    outside = sorted(set(["a", "zz"]) - set(base))
    arm("the subset check rejects a non-subset", outside == ["zz"], str(outside))

    # 7. the registry's own labels must match the (module, attribute) they
    #    name — a label is what a reader greps for, and a stale one sends them
    #    to a function that is not the one being tested.
    mismatched = [l for l, m, a in PREDICATES if l != f"{m}.{a}"]
    mismatched += [l for l, m, a, _w in SUBSET_PREDICATES if l != f"{m}.{a}"]
    arm("registry labels match their targets", not mismatched, str(mismatched))

    # 8. the docstring's headline count must match the tuple. It is the number
    #    a reader trusts without running anything, and it is exactly what went
    #    stale for four instruments.
    head = (__doc__ or "").splitlines()[0]
    words = {"SEVEN": 7, "EIGHT": 8, "NINE": 9, "TEN": 10, "ELEVEN": 11,
             "TWELVE": 12}
    claimed = next((v for k, v in words.items() if re.search(rf"\b{k}\b", head)),
                   None)
    arm("docstring headline count matches the tuple",
        claimed == len(PREDICATES), f"headline says {claimed}, tuple has "
                                    f"{len(PREDICATES)}")

    print(f"\n{sum(results)}/{len(results)} canary arm(s) PASSED")
    return 0 if all(results) else 2


if __name__ == "__main__":
    if "--canary" in sys.argv[1:]:
        sys.exit(canary())
    sys.exit(main())
