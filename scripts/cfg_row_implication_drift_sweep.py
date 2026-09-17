#!/usr/bin/env python3
"""Run the cfg-row-implication verdict over EVERY contract repo, not just this one.

`scripts/cfg_row_implication_gate.py` is katgpt-rs-scoped by construction: its
pins live in `cfg_row_implication_floors.txt` and `docs_gate.yml` has a single
checkout, so it can never see a sibling. Right shape for a per-push gate; wrong
shape for "is anyone ELSE shipping a row that BUILDS and compiles its target to
nothing?"

This is the sixth member of a family whose every previous member found real
defects the moment it was pointed anywhere but here:

    Issue 702  ci_gate_coverage            one repo -> 7 dead workflows
    Issue 725  numbering_drift_sweep       one repo -> 35 duplicate numbers
    Issue 728  cfg_gated_drift_sweep       one repo -> 12 silent load-bearing gates

An auditor pointed at exactly one repo for months makes "a sibling with the
defect" and "a sibling nobody looked at" byte-identical.

## What this verdict is, and why it is not the compiler's

A row whose feature closure (WITH defaults) does not satisfy its target's
leading `#![cfg]` compiles that target to NOTHING. The harness prints
`running 0 tests / test result: ok. 0 passed` and cargo exits 0 — so
`required_features_build_audit.py` reports **BUILDS** and is right, and
`cfg_gated_target_audit.py` counts the reader as protected because the row
EXISTS. Measured: riir-train `054a39a2` fixed one such row and took a target
from 0 passed to 1 passed, an assertion that had never executed at any
revision.

So a green from the compiler sweep is not a claim about this, and a green here
is not a claim that any row builds. The two verdicts are independent and both
are needed.

## Why NOT in docs_gate.sh's CHECKS

Identical reasoning to every other sweep here: CI has one checkout, the
siblings are simply absent, so this would either red on every run or derive an
EMPTY population and print a confident green over zero repos.

    this script                    workstation, on demand, every contract repo
    cfg_row_implication_gate.py    CI, per-push (docs_gate.sh), katgpt-rs only

## Vocabulary vs population

Population DERIVED (BOUNDARY.md + a `.git` dir, never typed). Expectations
COMMITTED, in `cfg_row_implication_drift_floors.txt` — deriving both from one
walk is what makes a cross-repo gate permanently green.

## Two ceilings and two floors, and the floors are the load-bearing half

`max_empty` is a WALL at 0 wherever the measured value is 0 and a RATCHET at
the measured backlog otherwise (riir-ai carries one open instance, Issue 513
instance 7). `max_unresolved` is a ratchet at each repo's measured value: an
`any(feature = ...)` predicate is legitimate and simply not rulable here.

Both go green over whatever the instrument can NAME, so `min_rows` and
`min_with_cfg` sit underneath. `min_with_cfg` is the one that earns its keep —
`leading_inner_cfgs` returns `[]` for an unreadable file and for a file with no
cfg, and an early cut of it silently skipped cargo's DIRECTORY target form
(`tests/<name>/main.rs`). A source-scanner narrowing takes the cfg population
toward 0 and both ceilings pass, indistinguishable from a clean repo.

Exit 0 clean · 1 drift above the pins · 2 the instrument is untrustworthy.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# DRY: the classification is the report's, so the sweep, the per-push gate and
# the report can never disagree about what EMPTY-AT-ROW means.
import cfg_row_implication_audit as cria  # noqa: E402
from sweep_population import population_verdict, pin_row_exempt  # noqa: E402
from cfg_gated_target_audit import derive_repos  # noqa: E402
from worktree_state import (HeadDelta, delta_of,  # noqa: E402
                            head_tree, sweep_advisory)

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = REPO_ROOT.parent
PINS = Path(__file__).resolve().parent / "cfg_row_implication_drift_floors.txt"
# The per-push gate's own pins. This sweep re-states katgpt-rs's numbers, so the
# two files can drift apart — the hazard docs_gate_paths_sync.py exists for one
# workflow over. Asserted below rather than trusted.
LOCAL_PINS = Path(__file__).resolve().parent / "cfg_row_implication_floors.txt"

FIELDS = ("min_rows", "min_with_cfg", "max_empty", "max_unresolved")

# ONE list, read by the worktree advisory AND by the HEAD re-classification.
# Both inputs to every verdict: the MANIFESTS (a `required-features` row, the
# feature table, the `default` list) and the target SOURCES (the leading
# `#![cfg]`). `*.rs` deliberately OVER-triggers — most tracked sources are not
# a row's target — because the safe direction for a trigger is to pay for a
# re-classification that changes nothing, and there is no static way to know
# which sources are targets without parsing the manifests first.
SCOPE = ("*.toml", "*.rs")


def finding_key(f) -> tuple:
    """A `Finding`'s LINE-FREE, TREE-FREE identity.

    ⛔ **`Row.path` and `Row.crate_dir` must NOT be in the key.** The HEAD side
    classifies a materialised checkout, so both carry the temp directory's
    prefix — a key holding either matches NOTHING across the two sides and
    reports every row in the repo as both UNCOMMITTED and MASKED at once, which
    reads like a finding rather than like a broken key. The address that
    survives is the one the manifest actually declares: package, kind, name.
    (`Row.repo` is safe since `head_tree` names its checkout after the source
    repo — but it is left out anyway: a key should not depend on a property of
    the other instrument, and this one did not have it on the day it landed.)

    ⛔ **The VERDICT is in the key** (T5f, T5g, T5i — third sweep running):
    `delta_of` keeps the WORKTREE's object for a key-matched row, so a field
    the key omits is a field where the worktree silently overrides HEAD, and
    both ceilings here partition by verdict. `missing` rides with it because it
    is the row's content — an EMPTY that gained a second unsatisfied feature is
    a different finding, not the same one.
    """
    return (f.row.package, f.row.kind, f.row.name, f.verdict,
            tuple(sorted(f.missing)))


def adjudicate(repo: Path, found: list):
    """-> (`HeadDelta` over this repo's findings, HEAD's finding list or None).

    Issue 822 T5j. ⛔ `head_tree`, not `head_delta`, and the choice is MEASURED
    rather than preferred. Every verdict here is a JOIN of a manifest and a
    source, so `head_delta`'s per-file premise fails outright — a dirty
    `Cargo.toml` moves every row in its package. `head_overlay` does not reach
    it either: `audit_repo` reads through three modules (`manifests()` globs
    the filesystem, `parse_rows`/`rows_from_manifest` read manifests,
    `leading_inner_cfgs` reads sources), one of which backs a per-push gate.

    The cheap alternative — injecting a reader into all three — was costed and
    declined: it edits production paths under `cfg_row_implication_gate` for a
    sweep-only benefit, against materialising HEAD, which leaves the classifier
    byte-identical. ⚠ The price is real and asymmetric: this sweep is **1.9s**
    clean, an UNNARROWED tree copy took it to 36.6s on ONE dirty file, and the
    narrowed one 16.8s — so the pathspec buys 2.2x here rather than the 20x the
    archive SIZE suggests, because what is left is `git add` plus re-running the
    classifier over riir-train's 478 rows, and neither shrinks with the tar.
    `head_tree` yields None on a clean run and this returns immediately, so the
    common case pays nothing — and the archive is narrowed to `SCOPE` itself,
    which is sound here precisely because this classifier's inputs are
    ENUMERABLE: manifests and the sources they name, nothing else. Measured on
    riir-train: 604 MB -> 30.6 MB. ⛔ The pathspec is the SAME constant the
    trigger uses, deliberately — two lists could drift into a tree that is
    missing exactly what the classifier reads, and that failure is silent.

    `None` for the second element means "no HEAD to compare against" — a clean
    tree, or not a repository. The caller must then read the WORKTREE's own
    floors, because a fabricated empty HEAD would report every row as
    uncommitted and silence every ceiling in the repo.
    """
    with head_tree(repo, SCOPE, paths=SCOPE) as tree:
        if tree is None:
            return HeadDelta(list(found), [], []), None
        head = cria.audit_repo(tree)
        return delta_of(found, head, finding_key), head


# ⚠ The EMPTY arm names a feature that EXISTS and does not satisfy, never an
# empty list: `parse_rows` keeps only rows CARRYING required-features, so
# `required-features = []` is not in the population at all and the fixture
# would compare nothing against nothing — measured, it produced four arm
# failures whose shape read like a broken key.
EMPTY_MANIFEST = """[package]
name = "canary-a"
version = "0.0.0"

[features]
on = []
other = []

[[test]]
name = "t"
path = "tests/t.rs"
required-features = ["other"]
"""
SATISFIED_MANIFEST = EMPTY_MANIFEST.replace('required-features = ["other"]',
                                            'required-features = ["on"]')
GATED_SRC = '#![cfg(feature = "on")]\n\n#[test]\nfn t() {}\n'


def adjudicate_cases() -> list[str]:
    """`adjudicate` end to end against REAL git — Issue 822 T5j.

    This sweep has no `selftest` of its own: it delegates to `cria.selftest()`,
    which covers the CLASSIFIER and structurally cannot reach the join landed
    here (Issue 775's sentence, and the reason `check_validation_gate` credits
    delegation but `arm_reach_audit` still finds the seam unarmed). So these
    run from `main`, unconditionally, beside that call.

    The fixture is the audit's own subject reduced to one row: a `[[test]]`
    whose target opens `#![cfg(feature = "on")]`, and a `required-features`
    list that either supplies `on` or does not.
    """
    import tempfile

    fails: list[str] = []

    def git(root, *args):
        subprocess.run(("git", "-C", str(root)) + args,
                       capture_output=True, check=True)

    def fixture(td: str, committed: str, worktree: str | None):
        repo = Path(td) / "r"
        (repo / "tests").mkdir(parents=True)
        (repo / "Cargo.toml").write_text(committed, encoding="utf-8")
        (repo / "tests" / "t.rs").write_text(GATED_SRC, encoding="utf-8")
        git(repo.parent, "init", "-q", "r")
        git(repo, "config", "user.email", "arm@example.invalid")
        git(repo, "config", "user.name", "arm")
        git(repo, "add", "-A")
        git(repo, "-c", "commit.gpgsign=false", "commit", "-qm", "base")
        if worktree is not None:
            (repo / "Cargo.toml").write_text(worktree, encoding="utf-8")
        return repo

    def run(repo):
        found = cria.audit_repo(repo)
        delta, head = adjudicate(repo, found)
        return found, delta, (found if head is None else head)

    # a. ⛔ Issue 798's direction: a repair that is not COMMITTED is not landed.
    #    An uncommitted `required-features` fix must NOT clear `max_empty`,
    #    which is a WALL at 0 in every repo but one.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, EMPTY_MANIFEST, SATISFIED_MANIFEST)
        found, delta, judged = run(repo)
        if any(f.verdict == cria.EMPTY for f in found):
            fails.append(f"arm a: the fixture is INERT — the worktree must "
                         f"read SATISFIED ({[f.verdict for f in found]})")
        if not any(f.verdict == cria.EMPTY for f in judged):
            fails.append("adjudicate: an UNCOMMITTED fix cleared the EMPTY "
                         "wall — the committed row still compiles its target "
                         "to nothing for everyone else")
        if not delta.masked:
            fails.append(f"adjudicate: the committed EMPTY row was not MASKED "
                         f"({delta})")

    # b. And its mirror: a defect introduced in the worktree must not red a
    #    wall at 0 over a line no commit contains.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, SATISFIED_MANIFEST, EMPTY_MANIFEST)
        found, delta, judged = run(repo)
        if not any(f.verdict == cria.EMPTY for f in found):
            fails.append("arm b: the fixture is INERT — the worktree must "
                         "read EMPTY")
        if any(f.verdict == cria.EMPTY for f in judged):
            fails.append("adjudicate: an uncommitted EMPTY row reached the "
                         "wall instead of UNCOMMITTED")
        if len(delta.uncommitted) != 1:
            fails.append(f"adjudicate: the worktree-only EMPTY row is not "
                         f"UNCOMMITTED ({delta})")

    # c. ⛔ The key must be TREE-FREE. `Row.repo` is the checkout's directory
    #    name and both paths carry its prefix, so a key holding any of them
    #    matches nothing across the two sides — every row in the repo then
    #    reads as UNCOMMITTED *and* MASKED at once, which looks like a finding
    #    rather than like a broken key.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, SATISFIED_MANIFEST, None)
        found = cria.audit_repo(repo)
        with head_tree(repo, SCOPE) as tree:
            if tree is not None:
                fails.append("arm c: a clean tree materialised HEAD")
        # Materialise deliberately, bypassing the clean-tree short-circuit, to
        # compare the two sides' keys directly.
        (repo / "tests" / "extra.rs").write_text("// dirt\n", encoding="utf-8")
        git(repo, "add", "-A")
        with head_tree(repo, SCOPE) as tree:
            head = cria.audit_repo(tree) if tree is not None else []
        if not head:
            fails.append("arm c: HEAD produced no findings — the fixture "
                         "cannot compare keys")
        elif {finding_key(f) for f in found} != {finding_key(f) for f in head}:
            fails.append(f"row key: the two sides disagree on an UNCHANGED "
                         f"row — the key is carrying the tree "
                         f"({ {finding_key(f) for f in found} } vs "
                         f"{ {finding_key(f) for f in head} })")

    # d. The FLOORS read HEAD too: a staged-new manifest row exists in no
    #    commit, and `min_rows` is a pin (Issue 797 measured this class on a
    #    population rather than on a finding).
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, SATISFIED_MANIFEST, None)
        (repo / "Cargo.toml").write_text(
            SATISFIED_MANIFEST + '\n[[test]]\nname = "t2"\npath = "tests/t.rs"\n'
            'required-features = ["on"]\n', encoding="utf-8")
        found, delta, judged = run(repo)
        if len(found) != 2 or len(judged) != 1:
            fails.append(f"adjudicate: the row floor read the worktree "
                         f"({len(found)}) instead of HEAD ({len(judged)})")

    # e. A CLEAN tree must cost NOTHING — this instrument copies a tree, so a
    #    sweep paying for it every run is one nobody runs.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, SATISFIED_MANIFEST, None)
        calls = []
        real = cria.audit_repo
        cria.audit_repo = lambda r: calls.append(r) or real(r)
        try:
            found, delta, judged = run(repo)
        finally:
            cria.audit_repo = real
        if len(calls) != 1:
            fails.append(f"adjudicate: re-classified a CLEAN repo "
                         f"({len(calls)} calls) — `head_tree` must yield None "
                         f"and the caller must SKIP")
        if delta.uncommitted or delta.masked or not delta.committed:
            fails.append(f"adjudicate: a clean tree's rows are not all "
                         f"COMMITTED ({delta})")
    return fails


def adjudicate_arms() -> list[str]:
    """The cases above, plus the STUB PROBE proving they sit on the seam.

    ⛔ Aimed at `delta_of` — the helper `adjudicate` ACTUALLY calls — because
    two of this family's first three probes reported a false all-clear by
    being aimed at a function the target never invokes.
    """
    fails = adjudicate_cases()
    real = globals()["delta_of"]
    globals()["delta_of"] = lambda wt, hd, key: HeadDelta(list(wt), [], [])
    try:
        probed = adjudicate_cases()
    finally:
        globals()["delta_of"] = real
    if len(probed) < 2:
        fails.append(f"STUB PROBE: a `delta_of` that files every row as "
                     f"COMMITTED red only {len(probed)} of the provenance "
                     f"arms — they are not sitting under the seam")
    return fails


def parse_pins(path: Path) -> dict[str, dict[str, int]]:
    rows: dict[str, dict[str, int]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 5:
            raise ValueError(f"malformed pin row (want 5 fields): {raw!r}")
        rows[parts[0]] = dict(zip(FIELDS, (int(p) for p in parts[1:])))
    return rows


def local_pin(path: Path, key: str) -> int | None:
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line.startswith(key):
            _, _, value = line.partition("=")
            try:
                return int(value.strip())
            except ValueError:
                return None
    return None


def main(argv: list[str]) -> int:
    # Prints carry glyphs the Windows locale codecs cannot encode (checked
    # 2026-09-06 on cp874: check/cross/middot/arrow FAIL, em-dash OK); keep the
    # locale encoding and degrade only the fatal chars to escapes -- the
    # staged_set_audit house pattern (utf-8 pinning would mojibake legacy consoles).
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass  # not a TextIOWrapper (embedded / detached); keep old behavior
    # The report's selftest exits 2 on its own — run it before anything else so
    # an untrustworthy instrument is never reported as drift.
    cria.selftest()
    # The seam this sweep LANDED (Issue 822 T5j) — the classifier's own
    # selftest structurally cannot reach it, and there is no `selftest` here to
    # hang it from, so it runs beside that call with the same exit code: an
    # untrustworthy instrument is never reported as drift.
    arm_fails = adjudicate_arms()
    if arm_fails:
        print("✗ cfg-row-implication sweep ADJUDICATION ARMS FAILED "
              "— instrument untrustworthy:")
        for f in arm_fails:
            print(f"    {f}")
        return 2

    if not PINS.is_file():
        print(f"✗ pins file missing: {PINS}")
        return 2
    try:
        pins = parse_pins(PINS)
    except ValueError as e:
        print(f"✗ pins file unparseable: {e}")
        return 2
    if not pins:
        # An empty allowlist would make every repo "unpinned" and the sweep
        # would report a confident nothing. Refuse, as its siblings do.
        print("✗ pins file declares no repos — refusing to run vacuously")
        return 2

    repos = derive_repos(Path(argv[0]) if argv else WORKSPACE)
    if len(repos) < 2:
        print(f"✗ derived only {len(repos)} repo(s) — this sweep is cross-repo "
              f"by definition and a single-checkout run would be vacuous")
        return 2

    fails: list[str] = []
    # (repo name, finding, provenance marker) — see the loop for why the repo
    # name cannot be taken from `Row.label` on the HEAD side.
    empties: list[tuple[str, cria.Finding, str]] = []
    tot = {k: 0 for k in ("rows", "with_cfg", "empty", "unresolved")}

    print(f"{'repo':<24} {'rows':>6} {'#![cfg]':>8} {'EMPTY':>6} {'UNRES':>6}   pins")
    n_uncommitted = n_masked = 0
    for repo in sorted(repos, key=lambda p: p.name):
        found = cria.audit_repo(repo)
        # Issue 822 — the DISPLAY reads the worktree (it is what the files say
        # today); every CEILING and both FLOORS read what a commit of this
        # checkout would produce. `judged` falls back to the worktree's own
        # findings when there is no HEAD to compare against, which is the
        # conservative direction for a bucket the pins read.
        delta, head = adjudicate(repo, found)
        judged = found if head is None else head
        held = {finding_key(f) for f in delta.uncommitted}
        n_uncommitted += len(delta.uncommitted)
        n_masked += len(delta.masked)
        n_rows = len(judged)
        with_cfg = sum(1 for f in judged if f.verdict != cria.NO_CFG)
        empty = sum(1 for f in judged if f.verdict == cria.EMPTY)
        unres = sum(1 for f in judged if f.verdict == cria.UNRESOLVED)
        # ⛔ Carry the REPO NAME beside the finding. `Row.label` opens with
        # `Row.repo`, which on the HEAD side is the temp checkout's directory
        # name — a MASKED row would otherwise print an address that exists on
        # no box, for a ceiling that just red because of it.
        masked_keys = {finding_key(f) for f in delta.masked}
        empties += [(repo.name, f,
                     " [MASKED — committed, hidden by this worktree]"
                     if finding_key(f) in masked_keys else "")
                    for f in judged if f.verdict == cria.EMPTY]
        empties += [(repo.name, f, " [UNCOMMITTED — not adjudicated]")
                    for f in delta.uncommitted if f.verdict == cria.EMPTY]
        tot["rows"] += n_rows
        tot["with_cfg"] += with_cfg
        tot["empty"] += empty
        tot["unresolved"] += unres

        pin = pins.get(repo.name)
        if pin is None:
            # Issue 824. An ACKNOWLEDGED extra owes no pin row. Issue 821
            # landed this in 16 of the 19 sweeps and this was one of the three
            # it missed — the three Issue 782 had already named as the quiet
            # ones. Nested INSIDE `pin is None`, never flattened into the
            # condition: 821's own process note records the flat form crashing
            # on `pin["max_empty"]` in the else-branch.
            if not pin_row_exempt(repo.name):
                fails.append(f"{repo.name}: no pin row — a new repo must be "
                             f"pinned deliberately, not defaulted to permissive")
            note = "UNPINNED"
        else:
            note = "ok"
            if empty > pin["max_empty"]:
                fails.append(f"{repo.name}: EMPTY-AT-ROW {empty} > pinned {pin['max_empty']}")
                note = "DRIFT"
            if unres > pin["max_unresolved"]:
                fails.append(f"{repo.name}: UNRESOLVED {unres} > pinned {pin['max_unresolved']}")
                note = "DRIFT"
            if n_rows < pin["min_rows"]:
                fails.append(f"{repo.name}: only {n_rows} rows < floor {pin['min_rows']} "
                             f"— the manifest walk shrank, so the ceilings are vacuous")
                note = "DRIFT"
            if with_cfg < pin["min_with_cfg"]:
                fails.append(f"{repo.name}: only {with_cfg} rows carry a leading #![cfg] "
                             f"< floor {pin['min_with_cfg']} — the source scanner narrowed")
                note = "DRIFT"
        split = ""
        if held or delta.masked:
            split = (f"  [{len(held)} uncommitted"
                     + (f", {len(delta.masked)} MASKED" if delta.masked else "")
                     + f"; worktree rows={len(found)}]")
        print(f"{repo.name:<24} {n_rows:>6} {with_cfg:>8} {empty:>6} {unres:>6}   "
              f"{note}{split}")

    # The katgpt-rs row here and the per-push gate's own pins name the same
    # quantities. Hand-duplicated values drift; assert rather than trust.
    local_rows = local_pin(LOCAL_PINS, "min_rows_scanned")
    local_cfg = local_pin(LOCAL_PINS, "min_with_cfg")
    mine = pins.get("katgpt-rs")
    if mine is not None:
        if local_rows is not None and local_rows != mine["min_rows"]:
            fails.append(f"pin desync: katgpt-rs min_rows {mine['min_rows']} here vs "
                         f"min_rows_scanned {local_rows} in {LOCAL_PINS.name}")
        if local_cfg is not None and local_cfg != mine["min_with_cfg"]:
            fails.append(f"pin desync: katgpt-rs min_with_cfg {mine['min_with_cfg']} here "
                         f"vs {local_cfg} in {LOCAL_PINS.name}")

    # The population axis, shared (Issue 782, the Issue 793 verdict). The loop
    # above walks the DERIVED repos, so it catches walk->pins (UNREGISTERED)
    # and is blind to pins->walk: a pinned repo the walk never found is never
    # iterated, and this sweep used to print "every repo within its pins" over
    # 16 of 20. That silent green is the WORSE direction — the seven sweeps 779
    # repaired failed LOUDLY, which is impossible to misread.
    pop_lines, deferred, pop_fail = population_verdict(
        pins, {r.name for r in repos})

    # Issue 797 — the worktree is not the repo. This run reads files that
    # concurrent sessions are editing, so a finding may sit on a line no
    # commit contains. ADVISORY, never a failure: a sweep that hard-reds on
    # an ordinary dirty worktree is a sweep nobody runs. It rides the FINAL
    # line in BOTH directions (the `deferred` precedent) and is SILENT
    # unless the dirty set meets this sweep's own population — required-features rows + the sources they gate.
    # ⛔ The advisory carried its own copy of the population and it was NARROWER
    # than the classifier's: `Cargo.toml` matches only that basename, while
    # `manifests()` reaches `crates/*/Cargo.toml` — which `_matches` happens to
    # cover by its basename arm — and neither says anything about a workspace
    # `*.toml` that is not named Cargo.toml. One SCOPE, stated where the
    # classifier's inputs are listed. T5g measured this shape going wrong three
    # ways at once.
    deferred.extend(sweep_advisory(
        repos, SCOPE, root=WORKSPACE,
        uncommitted_rows=n_uncommitted, masked_rows=n_masked))
    for _line in pop_lines:
        print(_line)
    if pop_fail:
        fails.append(f"{pop_fail} contract repo(s) could not be measured — see "
                     f"the population rows above")

    print(f"\n{len(repos)} repos · {tot['rows']} rows · {tot['with_cfg']} with a leading "
          f"#![cfg] · {tot['empty']} EMPTY-AT-ROW · {tot['unresolved']} UNRESOLVED")
    if empties:
        print("\nEMPTY-AT-ROW — the row builds, and compiles the target to NOTHING:")
        for repo_name, f, mark in empties:
            print(f"  {repo_name}:{f.row.package}:{f.row.kind}:{f.row.name}{mark}")
            print(f"      row={f.row.features}  needs={sorted(f.needs)}  "
                  f"MISSING={sorted(f.missing)}")
    if fails:
        print("\n✗ cfg-row-implication drift sweep FAILED:")
        for f in fails:
            print(f"    {f}")
        return 1
    # "every repo" is a claim about the POPULATION, so it survives only when
    # nothing was deferred; a deferral rides the final line in BOTH directions
    # (one printed only on failure is one nobody reads on the run that passes).
    scope = ("every repo within its pins" if not deferred
             else "every MEASURED repo within its pins; " + "; ".join(deferred))
    print(f"\n✓ cfg-row-implication drift sweep PASSED — {scope}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
