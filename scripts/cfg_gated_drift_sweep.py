#!/usr/bin/env python3
"""Run the cfg-gated silent-zero ceilings over EVERY contract repo, not just this one.

`scripts/cfg_gated_floor_gate.py` is katgpt-rs-scoped by construction: its pins
live in `scripts/cfg_gated_floors.txt`, and `docs_gate.yml` has a single
checkout so it could never see a sibling. That is the right shape for a
per-push CI gate and the wrong shape for "is anyone ELSE shipping a
`#![cfg]`-gated gate that prints `ok. 0 passed` over an empty binary?"

That question had never been asked with a verdict attached, and asking it is
what found Issue 728: run over all 16 repos, the load-bearing classifier
reported **0 in every one**, because its token set had been validated against
2,157 katgpt-rs-era target names while the workspace corpus is 3,081. Six
tokens and one compound later the count is **12**, two of them in katgpt-rs
itself. This sweep is what keeps it from becoming 13.

The fourth and last member of the sweep family:

    Issue 702  ci_gate_coverage              one repo -> 7 dead workflows
    Issue 725  numbering_drift_sweep         one repo -> 35 duplicate numbers
    2026-09-06 required_features_drift_sweep one repo -> clean, and pinned there
    2026-09-06 percentile_drift_sweep        one repo -> clean, and pinned there
    this file  cfg_gated_drift_sweep         one repo -> 12 instances, ratcheted

Ceilings here are a RATCHET, not a wall — the difference from the two sweeps
that landed the same day
--------------------------------------------------------------------------
Those two measured zero everywhere, so their ceilings are walls. This one has a
standing backlog of 12 across six repos, ten of which are sibling-owned and are
NOT this session's to arm. So each repo's ceiling is pinned at its MEASURED
count, exactly as `numbering_drift_floors.txt` does: a new instance reds
immediately, and the backlog is visible in the pins rather than silently
tolerated. Lower a pin in the commit that arms a target.

Read the SEVERITY SPLIT, never the pooled total
-----------------------------------------------
`silent_now` is the severe class — those targets zero on a **plain `cargo
test`**. `latent` ones vanish only under `--no-default-features` and are not
gated here. And `silent_now_load_bearing` is the column that decides whether a
green is EVIDENCE: a silent zero on `scratch_probe` costs a reader's time; a
silent zero on `bridge_spec_match` is a promotion argument resting on an empty
binary. Both are pinned, because they fail independently.

Why this is NOT in scripts/docs_gate.sh's CHECKS
-----------------------------------------------
Identical to the other three sweeps: CI has one checkout, the siblings are
private and simply absent, so this would either red on every run or derive an
EMPTY population and print a confident green over zero repos.

    this script                 workstation, on demand, every contract repo
    cfg_gated_floor_gate.py     CI, per-push (docs_gate.sh), katgpt-rs only

Exit 0 clean, 1 on drift above the pins, **2 if the instrument itself is
untrustworthy** — an unreliable instrument is not the same finding as drift.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# DRY: the scanner, the classifier and the selftest are the report's, so the
# sweep and the per-push gate can never disagree about what is load-bearing.
import cfg_gated_target_audit as cga  # noqa: E402
from sweep_population import open_repo, population_verdict, pin_row_exempt  # noqa: E402
from worktree_state import (  # noqa: E402
    HeadDelta, deferral_line, delta_of, head_tree, sweep_advisory)

REPO_ROOT = HERE.parent
WORKSPACE = REPO_ROOT.parent
PINS = HERE / "cfg_gated_drift_floors.txt"
# The per-push gate's pins. This sweep re-states katgpt-rs's four numbers, so
# the two files can drift apart — asserted below rather than trusted, exactly
# as docs_gate_paths_sync.py does for the two trigger lists.
LOCAL_PINS = HERE / "cfg_gated_floors.txt"

FIELDS = ("min_targets", "min_gated", "max_silent_now", "max_load_bearing")
# Every field here names the SAME quantity as the identically-named key in
# cfg_gated_floors.txt, which is what makes the sync assert total rather than
# a spot check on one number.
SYNCED = FIELDS


def parse_pins(path: Path) -> dict[str, dict[str, int]]:
    rows: dict[str, dict[str, int]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 1 + len(FIELDS):
            raise ValueError(
                f"malformed pin row (want {1 + len(FIELDS)} fields): {raw!r}")
        rows[parts[0]] = dict(zip(FIELDS, (int(v) for v in parts[1:])))
    return rows


def local_pins(path: Path) -> dict[str, int]:
    """The per-push gate's pins — `key<TAB>value`, comments stripped."""
    out: dict[str, int] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) == 2:
            try:
                out[parts[0]] = int(parts[1])
            except ValueError:
                continue
    return out


def audit(repo: Path) -> dict:
    rep = cga.audit(repo)
    sn = rep.silent_now()
    return {
        "n_targets": rep.scanned,
        "n_gated": rep.gated,
        "silent_now": sn,
        "load_bearing": [f for f in sn if cga.is_load_bearing(f.name)],
    }


# ONE list, read by the worktree advisory, by the HEAD trigger and by the
# archive pathspec. Both inputs to every verdict: the MANIFESTS (which targets
# exist, their `required-features`, the feature table and its `default`) and
# the SOURCES (the whole-file `#![cfg]`). `*.rs` deliberately OVER-triggers —
# most sources are not a target's entry point — because the safe direction for
# a trigger is to pay for a re-classification that changes nothing.
SCOPE = ("*.toml", "*.rs")


def finding_key(f) -> tuple:
    """A `Finding`'s LINE-FREE, TREE-FREE identity.

    ⚠ MEASURED, not assumed: `manifest` and `path` are repo-RELATIVE here
    (`Cargo.toml`, `tests/t.rs`), unlike the absolute paths `restatement` and
    `len_derived` carry. So this key is tree-free by a property of the
    classifier, and the first version of this docstring said the opposite —
    a claim inherited from the neighbouring sweep rather than checked. They are
    still left out: `(kind, name)` is the address a manifest declares, and a
    target moved to another file is the same finding.

    ⚠ **What the key does and does not decide here.** Unlike its siblings, this
    sweep's ceilings read HEAD's `audit()` dict WHOLE (`len(j["silent_now"])`),
    so the key cannot under-count a pin. It drives the DISPLAY split —
    which rows are labelled UNCOMMITTED and which MASKED — and that is why
    `features` and `predicates` are in it: they are exactly the inputs to the
    `default_on` severity split, so a target whose gating changed is a
    different row to look at. ⚠ Of those two only `predicates` can actually
    vary between a finding and a finding — this classifier's finding IS "no
    `required-features` row at all", so `features` is empty by construction and
    is carried for the shape rather than for detection, which the arm for it
    had to be rewritten to discover. `reason` is NOT in the key: it is prose,
    and a key carrying prose reds on a reworded message.
    """
    return (f.repo, f.kind, f.name, tuple(f.features), tuple(f.predicates))


def adjudicate(repo: Path, got: dict):
    """-> (`HeadDelta` over the silent-now rows, HEAD's `audit()` or None).

    Issue 822 T5j. `head_tree`, for the reason `cfg_row_implication` measured
    one sweep over: every verdict is a JOIN of a manifest and a source, so
    `head_delta`'s per-file premise is false — a dirty `Cargo.toml` moves every
    target in its package — and `cga.audit` reads through a filesystem manifest
    glob plus direct source reads, which no single overlay can intercept.

    Narrowed to `SCOPE` itself, which is sound here because this classifier's
    inputs are ENUMERABLE, and stated as the SAME constant the trigger uses so
    the two cannot drift into a tree missing exactly what is read.

    `None` means there is nothing dirty in SCOPE, and the caller reads the
    worktree's own numbers — the conservative direction for a bucket the pins
    read.
    """
    with head_tree(repo, SCOPE, paths=SCOPE) as tree:
        if tree is None:
            return HeadDelta(list(got["silent_now"]), [], []), None
        head = audit(tree)
        return (delta_of(got["silent_now"], head["silent_now"], finding_key),
                head)


_SILENT_MANIFEST = """[package]
name = "canary-a"
version = "0.0.0"

[features]
on = []

[[test]]
name = "bridge_spec_match"
path = "tests/t.rs"
"""
_ARMED_MANIFEST = _SILENT_MANIFEST.replace(
    'path = "tests/t.rs"\n',
    'path = "tests/t.rs"\nrequired-features = ["on"]\n')
_GATED_SRC = '#![cfg(feature = "on")]\n\n#[test]\nfn t() {}\n'


def adjudicate_cases() -> list[str]:
    """`adjudicate` end to end against REAL git — Issue 822 T5j.

    The fixture is this sweep's own subject: a `[[test]]` whose source opens
    `#![cfg(feature = "on")]` and whose row does NOT require it, so a plain
    `cargo test` compiles it to an empty binary and prints `ok. 0 passed`. The
    name is load-bearing on purpose — that is the column whose ceiling says a
    green is evidence.
    """
    import tempfile

    fails: list[str] = []

    def git(root, *args):
        subprocess.run(("git", "-C", str(root)) + args,
                       capture_output=True, check=True)

    def fixture(td, committed, worktree=None):
        repo = Path(td) / "r"
        (repo / "tests").mkdir(parents=True)
        (repo / "Cargo.toml").write_text(committed, encoding="utf-8")
        (repo / "tests" / "t.rs").write_text(_GATED_SRC, encoding="utf-8")
        git(repo.parent, "init", "-q", "r")
        git(repo, "config", "user.email", "arm@example.invalid")
        git(repo, "config", "user.name", "arm")
        git(repo, "add", "-A")
        git(repo, "-c", "commit.gpgsign=false", "commit", "-qm", "base")
        if worktree is not None:
            (repo / "Cargo.toml").write_text(worktree, encoding="utf-8")
        return repo

    def run(repo):
        got = audit(repo)
        delta, head = adjudicate(repo, got)
        return got, delta, (got if head is None else head)

    # a. ⛔ Issue 798's direction: a repair that is not COMMITTED is not landed.
    #    An uncommitted `required-features` row must not clear the ratchet.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, _SILENT_MANIFEST, _ARMED_MANIFEST)
        got, delta, j = run(repo)
        if got["silent_now"]:
            fails.append(f"arm a: the fixture is INERT — the worktree must "
                         f"read no SILENT-NOW ({len(got['silent_now'])})")
        if len(j["silent_now"]) != 1 or not delta.masked:
            fails.append(f"adjudicate: an UNCOMMITTED fix cleared the "
                         f"SILENT-NOW ceiling ({len(j['silent_now'])}, masked "
                         f"{len(delta.masked)}) — the committed row still "
                         f"reports `ok. 0 passed` over an empty binary")
        if len(j["load_bearing"]) != 1:
            fails.append(f"adjudicate: the load-bearing column lost the "
                         f"committed row ({len(j['load_bearing'])}) — that is "
                         f"the ceiling that says a green is EVIDENCE")

    # b. And its mirror: a target silenced in the worktree must not red a
    #    ratchet over a line no commit contains.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, _ARMED_MANIFEST, _SILENT_MANIFEST)
        got, delta, j = run(repo)
        if len(got["silent_now"]) != 1:
            fails.append("arm b: the fixture is INERT — the worktree must "
                         "read one SILENT-NOW")
        if j["silent_now"] or len(delta.uncommitted) != 1:
            fails.append(f"adjudicate: an uncommitted SILENT-NOW reached the "
                         f"ceiling ({len(j['silent_now'])}) instead of "
                         f"UNCOMMITTED ({len(delta.uncommitted)})")

    # c. The FLOORS read HEAD too — Issue 797 measured this class on a
    #    POPULATION rather than on a finding.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, _ARMED_MANIFEST,
                       _ARMED_MANIFEST + '\n[[test]]\nname = "second"\n'
                       'path = "tests/t2.rs"\nrequired-features = ["on"]\n')
        # ⚠ Its OWN source file. `scanned` counts gated SOURCES, not manifest
        # rows — measured: two `[[test]]` rows pointing at one path scan as
        # ONE, and the first cut of this arm compared 1 against 1, which reads
        # as a pin defect rather than as an inert fixture.
        (repo / "tests" / "t2.rs").write_text(_GATED_SRC, encoding="utf-8")
        got, delta, j = run(repo)
        if got["n_targets"] <= j["n_targets"]:
            fails.append(f"adjudicate: the target floor read the worktree "
                         f"({got['n_targets']}) instead of HEAD "
                         f"({j['n_targets']})")

    # d. The key must be TREE-FREE: unrelated dirt must move no row. An
    #    absolute `manifest`/`path` in the key reports every target as
    #    UNCOMMITTED *and* MASKED at once.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, _SILENT_MANIFEST, None)
        (repo / "tests" / "other.rs").write_text("// dirt\n", encoding="utf-8")
        git(repo, "add", "-A")
        got, delta, j = run(repo)
        if delta.uncommitted or delta.masked:
            fails.append(f"row key: an UNCHANGED target moved on unrelated "
                         f"dirt — the key is carrying the tree "
                         f"(uncommitted={len(delta.uncommitted)}, "
                         f"masked={len(delta.masked)})")

    # d2. ⛔ The FEATURES must be in the key, and (a)/(b) cannot show it: there
    #     the row EXISTS on one side only, so every key agrees. This is the
    #     case where both sides carry a finding for the SAME target and only
    #     its gating moved — the row somebody has to look at twice. Without
    #     `features` the two match and the display calls it COMMITTED,
    #     reporting a gating change nobody committed as settled fact.
    #     ⚠ It varies the PREDICATE, not `required-features`, and that is a
    #     measurement: this classifier's finding IS "no `required-features` row
    #     at all", so a finding's `features` list is empty by construction and
    #     a fixture varying it produces one finding and one non-finding — which
    #     is arm (a) again, not this case.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, _SILENT_MANIFEST, None)
        (repo / "tests" / "t.rs").write_text(
            _GATED_SRC.replace('feature = "on"', 'feature = "other"'),
            encoding="utf-8")
        got, delta, j = run(repo)
        if len(got["silent_now"]) != 1 or len(j["silent_now"]) != 1:
            fails.append(f"arm d2: the fixture is INERT — both sides must "
                         f"carry one SILENT-NOW ({len(got['silent_now'])} vs "
                         f"{len(j['silent_now'])})")
        elif not (delta.uncommitted and delta.masked):
            fails.append(f"row key: a target whose GATING moved was not split "
                         f"in both directions ({delta}) — `features` is out of "
                         f"the key and the display calls it COMMITTED")

    # e. A CLEAN tree must cost NOTHING: this instrument copies a tree.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, _ARMED_MANIFEST, None)
        calls = []
        real = cga.audit
        cga.audit = lambda r: calls.append(r) or real(r)
        try:
            got, delta, j = run(repo)
        finally:
            cga.audit = real
        if len(calls) != 1:
            fails.append(f"adjudicate: re-classified a CLEAN repo "
                         f"({len(calls)} calls) — `head_tree` must yield None "
                         f"and the caller must SKIP")
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


def selftest() -> list[str]:
    """Pin that the verdict FIRES, that the severity split survives, and the
    parsers. A silent failure here reports a clean workspace."""
    import tempfile

    fails = []
    # The classifier's own widening (Issue 728) is what this sweep gates on.
    # If a future edit narrows it back, every ceiling below goes green over a
    # smaller population — the exact failure the issue documents. Pin the two
    # katgpt-rs instances by NAME, and the homonyms that must stay excluded.
    for name in ("bridge_spec_match", "pencil_spec_match",
                 "gemma4_q4k_gguf_parity", "kat_grant_reachability",
                 "net_ffi_roundtrip", "ledger_exactness"):
        if not cga.is_load_bearing(name):
            fails.append(f"classifier narrowed: {name!r} no longer load-bearing")
    for name in ("spec_reconciliation_bench", "spec_reconciliation_demo",
                 "attn_match_online", "quest_match_tui", "checkpoint_cost",
                 "aggregate_delegate_propagate", "bench_578_mcts_budget_sweep"):
        if cga.is_load_bearing(name):
            fails.append(f"classifier over-wide: {name!r} wrongly load-bearing")

    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        repo = ws / "fake-repo"
        (repo / "tests").mkdir(parents=True)
        (repo / "BOUNDARY.md").write_text("x", encoding="utf-8")
        (repo / ".git").mkdir()
        (repo / "Cargo.toml").write_text(
            "[package]\nname = 'fake'\nversion = '0.1.0'\n[features]\noff = []\n", encoding="utf-8"
        )
        # Auto-discovered, gated on a DEFAULT-OFF feature, load-bearing name.
        (repo / "tests" / "thing_spec_match.rs").write_text(
            '#![cfg(feature = "off")]\n#[test]\nfn t() { assert!(true); }\n', encoding="utf-8"
        )
        # Same shape, NOT load-bearing by name — must count as silent_now but
        # not as load_bearing, or the severity split has collapsed.
        (repo / "tests" / "scratch_probe.rs").write_text(
            '#![cfg(feature = "off")]\n#[test]\nfn t() { assert!(true); }\n', encoding="utf-8"
        )
        got = audit(repo)
        if len(got["silent_now"]) != 2:
            fails.append(f"expected 2 SILENT-NOW, got "
                         f"{[f.name for f in got['silent_now']]}")
        if [f.name for f in got["load_bearing"]] != ["thing_spec_match"]:
            fails.append(f"severity split broken: "
                         f"{[f.name for f in got['load_bearing']]}")

        # population derivation: BOUNDARY.md + a .git DIRECTORY, both required
        (ws / "no-boundary").mkdir()
        (ws / "no-boundary" / ".git").mkdir()
        (ws / "worktree-shaped").mkdir()
        (ws / "worktree-shaped" / "BOUNDARY.md").write_text("x", encoding="utf-8")
        (ws / "worktree-shaped" / ".git").write_text("gitdir: elsewhere", encoding="utf-8")
        if [p.name for p in cga.derive_repos(ws)] != ["fake-repo"]:
            fails.append("population derivation is not BOUNDARY.md + .git dir")

        pins = ws / "pins.txt"
        pins.write_text("# c\nrepo-a 10 5 3 0  # trailing\n\n", encoding="utf-8")
        if parse_pins(pins) != {"repo-a": {"min_targets": 10, "min_gated": 5,
                                           "max_silent_now": 3,
                                           "max_load_bearing": 0}}:
            fails.append("pin parse: 5-field row not read correctly")
        pins.write_text("repo-a 1 2\n", encoding="utf-8")
        try:
            parse_pins(pins)
            fails.append("pin parse: short row accepted")
        except ValueError:
            pass
    # Issue 822 T5j. In `selftest` and behind no flag: this sweep has no
    # `--canary`, and an arm behind a flag runs on no invocation anybody makes
    # (Issue 789). ~2.7s.
    return fails + adjudicate_arms()


def main() -> int:
    # Prints carry glyphs the Windows locale codecs cannot encode (checked
    # 2026-09-06 on cp874: check/cross/middot/arrow FAIL, em-dash OK); keep the
    # locale encoding and degrade only the fatal chars to escapes -- the
    # staged_set_audit house pattern (utf-8 pinning would mojibake legacy consoles).
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass  # not a TextIOWrapper (embedded / detached); keep old behavior
    # The report's own selftest raises a bare AssertionError rather than
    # exiting, so let it through and this sweep dies with a traceback — which
    # reads as a crash, not as the "instrument untrustworthy" verdict it IS.
    # Exit 2 is the whole point of having a third exit code.
    try:
        cga.selftest()
    except AssertionError as e:
        print("✗ cfg-gated sweep SELFTEST FAILED — the REPORT's own selftest "
              "does not hold, so no verdict is possible:")
        print(f"    {e}")
        return 2

    fails = selftest()
    if fails:
        print("✗ cfg-gated sweep SELFTEST FAILED — instrument untrustworthy:")
        for f in fails:
            print(f"    {f}")
        return 2

    if not PINS.is_file():
        print(f"✗ pins file missing: {PINS}")
        return 2
    try:
        pins = parse_pins(PINS)
    except ValueError as e:
        print(f"✗ pins file unreadable: {e}")
        return 2
    if not pins:
        print("✗ pins file declares NO repos — an empty expectation set is refused")
        return 2

    repos = cga.derive_repos(WORKSPACE)
    if not repos:
        print(f"✗ derived population is EMPTY under {WORKSPACE} — refusing to "
              f"report a green over zero repos")
        return 2

    # All four numbers are stated twice. A hand-duplicated pin drifts.
    lp = local_pins(LOCAL_PINS)
    mine = pins.get(REPO_ROOT.name)
    if mine is None:
        print(f"✗ {PINS.name} has no row for {REPO_ROOT.name}")
        return 2
    for key in SYNCED:
        if lp.get(key) != mine[key]:
            print(f"✗ pin drift: {PINS.name} says {key}={mine[key]} for "
                  f"{REPO_ROOT.name}, {LOCAL_PINS.name} says {key}="
                  f"{lp.get(key)}. Same quantity, two files — change both.")
            return 1

    seen = {p.name for p in repos}
    bad = False
    tot = {"n_targets": 0, "n_gated": 0, "silent_now": 0, "load_bearing": 0}

    n_uncommitted = n_masked = 0
    for repo in repos:
        # Issue 842: the derived handle is CONTRACT-named; the DIRECTORY is
        # the on-disk spelling. Audit the real checkout, label by the handle.
        path = open_repo(repo.name, WORKSPACE)
        got = audit(path)
        # Issue 822 T5j — the DISPLAY reads the worktree (it is what the files
        # say today); every CEILING and both FLOORS read what a commit of this
        # checkout would produce.
        delta, head = adjudicate(path, got)
        j = got if head is None else head
        held = {finding_key(f) for f in delta.uncommitted}
        n_uncommitted += len(delta.uncommitted)
        n_masked += len(delta.masked)
        row = pins.get(repo.name)
        tot["n_targets"] += got["n_targets"]
        tot["n_gated"] += got["n_gated"]
        tot["silent_now"] += len(got["silent_now"])
        tot["load_bearing"] += len(got["load_bearing"])
        flags = []
        if row is None:
            # Issue 821: an acknowledged known-extra owes no pin row —
            # the marker reached population_verdict's FINAL line and not
            # this loop, so 8 of 9 sweeps red on repos they found
            # nothing in, hiding two live ratchet breaches.
            if not pin_row_exempt(repo.name):
                flags.append("UNPINNED — add a row (or it can never red)")
        else:
            if j["n_targets"] < row["min_targets"]:
                flags.append(f"target FLOOR breached: {j['n_targets']} committed < "
                             f"{row['min_targets']} — targets were removed, or "
                             f"the manifest walk went blind")
            if j["n_gated"] < row["min_gated"]:
                flags.append(f"gated FLOOR breached: {j['n_gated']} committed < "
                             f"{row['min_gated']} — or the #![cfg] scanner "
                             f"stopped recognising the shape")
            if len(j["silent_now"]) > row["max_silent_now"]:
                flags.append(f"SILENT-NOW {len(j['silent_now'])} committed > pinned "
                             f"{row['max_silent_now']}")
            if len(j["load_bearing"]) > row["max_load_bearing"]:
                flags.append(f"load-bearing SILENT-NOW {len(j['load_bearing'])} committed "
                             f"> pinned {row['max_load_bearing']} — a target whose "
                             f"NAME says its green is evidence reports "
                             f"`ok. 0 passed` over an EMPTY binary")
        status = "✗" if flags else ("·" if got["load_bearing"] else "✓")
        split = ""
        if held or delta.masked:
            split = (f"  [{len(held)} uncommitted"
                     + (f", {len(delta.masked)} MASKED" if delta.masked else "")
                     + f"; HEAD targets={j['n_targets']} "
                     f"silent_now={len(j['silent_now'])}]")
        print(f"{status} {repo.name:22s} targets={got['n_targets']:<5d} "
              f"gated={got['n_gated']:<5d} silent_now={len(got['silent_now']):<3d} "
              f"load_bearing={len(got['load_bearing'])}{split}")
        for f in got["load_bearing"]:
            wip = (" [UNCOMMITTED — not adjudicated]"
                   if finding_key(f) in held else "")
            print(f"      load-bearing: {f.kind}:{f.name}  features={f.features}  "
                  f"({f.reason}){wip}")
        # A MASKED row is NOT in the worktree buckets — that is what MASKED
        # means — so it prints from the HEAD side or it prints nowhere, and a
        # ceiling reds over a target nobody can see.
        for f in sorted(delta.masked, key=finding_key):
            print(f"      ⛔ {f.kind}:{f.name}  features={f.features}  "
                  f"[MASKED — committed, hidden by this worktree]")
        for f in flags:
            bad = True
            print(f"      ✗ {f}")

    # The population axis, shared (Issue 793): UNREGISTERED reds in every
    # posture, UNSEEN reds without the marker, and the same set DEFERS loudly
    # with it. Never auto-detected — a genuine removal whose row update was
    # forgotten is set-identical to a partial clone from the walk alone.
    pop_lines, deferred, pop_fail = population_verdict(pins, seen)

    # Issue 797 — the worktree is not the repo. This run reads files that
    # concurrent sessions are editing, so a finding may sit on a line no
    # commit contains. ADVISORY, never a failure: a sweep that hard-reds on
    # an ordinary dirty worktree is a sweep nobody runs. It rides the FINAL
    # line in BOTH directions (the `deferred` precedent) and is SILENT
    # unless the dirty set meets this sweep's own population — manifests + the gated test targets they select.
    # ⛔ The advisory carried its own copy of the population, NARROWER than the
    # classifier's: `Cargo.toml` is one basename, while a workspace `*.toml`
    # that is not named Cargo.toml still reaches the manifest reader. One
    # SCOPE, stated where the classifier's inputs are listed — T5g measured
    # this shape disagreeing three ways at once.
    deferred.extend(sweep_advisory(
        seen, SCOPE, root=WORKSPACE,
        uncommitted_rows=n_uncommitted, masked_rows=n_masked))
    for _line in pop_lines:
        print(_line)
    if pop_fail:
        bad = True

    print(f"\n{len(repos)} contract repo(s) · {tot['n_targets']} target(s) · "
          f"{tot['n_gated']} #![cfg]-gated · {tot['silent_now']} SILENT-NOW · "
          f"{tot['load_bearing']} of those load-bearing")
    # State the scope where it is READ. A pooled count means nothing here.
    print("  scope: SILENT-NOW only — targets that zero on a PLAIN `cargo "
          "test`. Targets gated on a DEFAULT-ON feature (`latent`) vanish only "
          "under --no-default-features and are not gated by this sweep; nor "
          "are target_os/miri/any(...) gates, which required-features cannot "
          "express. A ceiling here is a RATCHET at the measured backlog, not a "
          "claim of zero.")
    if bad:
        print("✗ cfg-gated sweep FAILED — see the ✗ rows above")
        for _d in deferred:
            print(f"  {deferral_line(_d)}")
        print("    The fix is a `required-features` row: the #![cfg] protects")
        print("    the COUNT, required-features protects the READER. Adding one")
        print("    cannot red an existing CI — cargo SKIPS a target whose")
        print("    features are unmet; it only stops the green zero.")
        return 1
    _line = "✓ cfg-gated sweep PASSED — nothing above its pinned ratchet"
    if deferred:
        _line += "; DEFERRED: " + "; ".join(deferred)
    print(_line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
