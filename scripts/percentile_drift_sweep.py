#!/usr/bin/env python3
"""Run the percentile-index gate's ceilings over EVERY contract repo, not just this one.

`scripts/percentile_floor_gate.py` is katgpt-rs-scoped by construction: its
pins live in `scripts/percentile_floors.txt`, whose first line says "katgpt-rs
scope only", and `docs_gate.yml` has a single checkout so it could never see a
sibling. That is the right shape for a per-push CI gate and the wrong shape for
"is anyone ELSE reporting a max under a percentile's name?"

The workspace answer to that question was hard-won and is being held by
nothing. On 2026-09-03 the audit found **12 DEGENERATE sites** and four
sibling owners fixed all of them the same day (riir-ai `03a91ed59` swept 10,
riir-mmorpg-examples `ee9da24` the one DEGENERATE-ASSERTED site,
riir-game-sdk `f896bca`, riir-chain `7f3a3910`). katgpt-rs has gated its own
zero since; the other fifteen repos have gated nothing, so the next
`sorted[(n as f64 * 0.99) as usize]` to land in a sibling bench is invisible
until somebody re-runs the report by hand.

This is the fourth instance of one shape in this workspace, and the first two
found real defects the moment they were pointed anywhere but here:

    Issue 702  ci_gate_coverage              one repo -> 7 dead workflows
    Issue 725  numbering_drift_sweep         one repo -> 35 duplicate numbers
    2026-09-06 required_features_drift_sweep one repo -> clean, and pinned there
    this file  percentile_drift_sweep        one repo -> clean, and pinned there

Why the population floor is TWO numbers here
--------------------------------------------
`max_degenerate = 0` is green over whatever the auditor's vocabulary can NAME,
so a tokenizer regression takes the count to ~0 and every ceiling passes,
indistinguishable from a clean repo. `percentile_floors.txt` already carries
`min_sites_scanned` for that reason.

A per-repo site floor cannot do that job alone across the workspace: **seven of
the sixteen repos have ZERO percentile sites**, so their site floor is 0 and
detects nothing at all. `min_rs_files` — the size of the walk that produced the
sites — still bites there, and it is the quantity a `walk_rs` regression
actually moves. Same argument as `required_features_drift_sweep.py`'s
`min_manifests`, one instrument over.

Both floors are deliberately SLACK against churn and TIGHT against blindness,
per the reasoning in `percentile_floors.txt`: a repair campaign legitimately
SHRINKS the site count (consolidating ten inline index computations behind one
correct helper removes nine sites — that is what took the workspace 130 -> 114),
and a floor that ratchets up to the last measurement would red the next such
refactor and teach whoever hits it that the gate is noise. A vocabulary or
scoping regression drops these by an order of magnitude, not by a third.

Ceilings are a WALL, not a ratchet: all four classes measure 0 in all 16 repos
(2026-09-06), there is no standing backlog to tolerate, and none of the four is
legitimate.

Why this is NOT in scripts/docs_gate.sh's CHECKS
-----------------------------------------------
Identical to the other three sweeps: CI has one checkout, the siblings are
private and simply absent, so this would either red on every run or derive an
EMPTY population and print a confident green over zero repos. It also costs
~70s, against the docs gate's ~3s budget.

    this script                  workstation, on demand, every contract repo
    percentile_floor_gate.py     CI, per-push (docs_gate.sh), katgpt-rs only

Exit 0 clean, 1 on drift above the pins, **2 if the instrument itself is
untrustworthy** — an unreliable instrument is not the same finding as drift.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# DRY: the tokenizer, the classification and the selftest are the report's, so
# the sweep, the per-push gate and the report can never disagree about what a
# DEGENERATE site is.
import percentile_index_audit as pia  # noqa: E402
from sweep_population import open_repo, population_verdict, pin_row_exempt  # noqa: E402
from worktree_state import (head_delta, ordinal_keys,  # noqa: E402
                            sweep_advisory)

REPO_ROOT = HERE.parent
WORKSPACE = REPO_ROOT.parent
PINS = HERE / "percentile_drift_floors.txt"
# The per-push gate's own pins. This sweep re-states katgpt-rs's site floor, so
# the two files can drift apart — asserted below rather than trusted, exactly
# as `docs_gate_paths_sync.py` does for the two trigger lists.
LOCAL_PINS = HERE / "percentile_floors.txt"

FIELDS = ("min_rs_files", "min_sites", "max_degenerate",
          "max_degenerate_asserted", "max_weak_asserted", "max_trunc_var")



# The four GATED classes, in one place: the pin loop, the tally and the Issue
# 822 split all iterate this rather than each restating it.
GATED = ("degenerate", "degenerate_asserted", "weak_asserted", "trunc_var")


def keyed(got: dict) -> list:
    """`[(key, cls, row)]` over the four gated classes, keys LINE-FREE.

    ⛔ The rows are `file:line`, and any edit above a site shifts the line — a
    line-bearing key reports EVERY row in an edited file as UNCOMMITTED *and*
    MASKED at once. So the address is `(file, class, kind, source text)`, with
    an ORDINAL for the case that survives it: the same shape twice in one file.
    The ordinal is scoped to the whole address, so a new site renumbers nothing.

    ⚠ `degenerate_asserted` is a SUBSET of `degenerate`, so a row appears under
    two classes by design. The class is part of the address for exactly that
    reason — pooling them would make one row's ordinal depend on the other's
    presence, and a row that stops being `asserted` would then look like it
    moved.

    The ordinal itself is `worktree_state.ordinal_keys`, shared with the rest
    of the family; only the ADDRESS is this sweep's own. ⚠ `line_free` is
    deliberately NOT called: these rows carry no `"<lineno>: "` prefix — the
    address takes `r["text"]`, already the bare source line — so calling it
    would be a no-op that reads as though a prefix were being stripped.
    """
    flat = [(cls, r) for cls in GATED for r in got[cls]]
    return [(key, cls, r) for key, (cls, r) in ordinal_keys(
        flat, lambda t: (t[1]["file"].replace(chr(92), "/"), t[0],
                         t[1]["kind"], t[1]["text"]))]


def head_sites(walk: set):
    """`head_delta`'s per-file reclassifier for the four ceilings.

    Per-file row independence holds: `audit_text` is a line scan over ONE
    file's source, and `resolve_n` looks only inside that same text. `walk` is
    the sweep's own population — `fnmatch`'s `*` crosses `/`, so the scope glob
    admits paths `walk_rs` excludes, and a row invented there reads as MASKED,
    a hard red nobody can repair.
    """

    def rescan(rel: str, src: str | None) -> list:
        # None = absent from HEAD (staged but never committed): nothing
        # committed to classify, so the worktree's row is UNCOMMITTED.
        if src is None or rel not in walk:
            return []
        t = pia.tally(pia.audit_text(src, rel))
        return keyed({cls: t[cls] for cls in GATED})

    return rescan


def adjudicate(repo: Path, got: dict, walk: set):
    """The four classes' rows, split COMMITTED / UNCOMMITTED / MASKED.

    A named seam rather than inline: this is the verdict arithmetic, and
    `arm_reach_audit`'s standing finding here is that the classifier is well
    armed and the verdict is not.
    """
    return head_delta(
        repo, ("*.rs",), keyed(got),
        lambda r: r[2]["file"], lambda r: r[0],
        head_sites(walk))


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


def local_min_sites(path: Path) -> int | None:
    """`min_sites_scanned` out of the per-push gate's pins, for the sync assert."""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line.startswith("min_sites_scanned"):
            _, _, value = line.partition("=")
            try:
                return int(value.strip())
            except ValueError:
                return None
    return None


def audit(repo: Path) -> dict:
    """One repo -> the four gated classes + BOTH populations that produced them."""
    n_rs = 0
    findings = []
    walk = set()
    for f in pia.walk_rs(str(repo)):
        n_rs += 1
        rel = os.path.relpath(f, repo).replace(chr(92), "/")
        walk.add(rel)
        findings += pia.audit_file(f, os.path.relpath(f, repo))
    t = pia.tally(findings)
    return {
        "walk": walk,
        "n_rs": n_rs,
        "n_sites": len(t["sites"]),
        "degenerate": t["degenerate"],
        "degenerate_asserted": t["degenerate_asserted"],
        "weak_asserted": t["weak_asserted"],
        "trunc_var": t["trunc_var"],
    }


def adjudicate_arms() -> list[str]:
    """`adjudicate`, two-sided, against a real git tree.

    ⛔ These exist because a peer session asked the right question of the two
    sweeps wired before this one: *if `head_delta` were stubbed to return
    every row as committed, would any arm red?* For `console_encoding` the
    answer was no — 14/14 canary arms passed against a stub, because they all
    monkeypatch `adjudicate` and so never reach its body. Measured, not
    reasoned. These arms red against that stub.
    """
    fails: list[str] = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    def git(cwd, *args):
        subprocess.run(["git", "-C", str(cwd), *args], check=True,
                       capture_output=True)

    # A DEGENERATE site: n=100 at p99 indexes 99 == n-1, the MAX. The
    # VOCAB needs an IDENTIFIER for n (a literal `50` matches nothing),
    # and `resolve_n` reads its value out of the enclosing scope — so
    # this is the shape the sweep's own selftest plants, not a new one.
    BAD = ("fn main() {\n"
           "    let n = 100;\n"
           "    let mut sorted = vec![0u64; n];\n"
           "    let p99 = sorted[(n as f64 * 0.99) as usize];\n"
           "    assert!(p99 < 5_000);\n"
           "}\n")
    OK = ("fn main() {\n"
          "    let n = 100;\n"
          "    let mut sorted = vec![0u64; n];\n"
          "    let p99 = sorted[((n as f64 * 0.99).ceil() as usize) - 1];\n"
          "    assert!(p99 < 5_000);\n"
          "}\n")

    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "r"
        (repo / "src").mkdir(parents=True)
        git(repo.parent, "init", "-q", "-b", "main", "r")
        git(repo, "config", "user.email", "t@t")
        git(repo, "config", "user.name", "t")
        (repo / "src/a.rs").write_text(BAD, encoding="utf-8")
        (repo / "src/b.rs").write_text(OK, encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "base")

        def now():
            got = audit(repo)
            return got, adjudicate(repo, got, got["walk"])

        got, d = now()
        check(len(got["degenerate"]) == 1,
              f"fixture: degenerate={len(got['degenerate'])}, want 1")
        check(not d.uncommitted and not d.masked,
              f"a clean tree produced a split: {d}")

        # ── UNCOMMITTED: the worktree INVENTS a degenerate site ─────────────
        (repo / "src/b.rs").write_text(BAD, encoding="utf-8")
        got, d = now()
        check(len(d.uncommitted) >= 1
              and all(r[2]["file"].endswith("b.rs") for r in d.uncommitted),
              f"UNCOMMITTED direction: {[r[2]['file'] for r in d.uncommitted]}")
        check(not d.masked, f"an invented row was also MASKED: {d.masked}")
        check(all(r[2]["file"].endswith("a.rs") for r in d.head),
              f"the pins' view is not HEAD's own set: "
              f"{[r[2]['file'] for r in d.head]}")

        # ── MASKED: the worktree HIDES a committed one ──────────────────────
        git(repo, "checkout", "--", "src/b.rs")
        (repo / "src/a.rs").write_text(OK, encoding="utf-8")
        got, d = now()
        check(not got["degenerate"],
              f"the fixture did not hide the site: {got['degenerate']}")
        check(len(d.masked) >= 1
              and all(r[2]["file"].endswith("a.rs") for r in d.masked),
              f"MASKED direction: {[r[2]['file'] for r in d.masked]}")
        check(len(d.head) == len(d.masked),
              f"a MASKED row is missing from the pins' view: {d.head}")

        # ── the key is LINE-FREE ────────────────────────────────────────────
        # Any insertion above a site shifts its line; a line-bearing key
        # reports every row in an edited file as UNCOMMITTED *and* MASKED.
        git(repo, "checkout", "--", "src/a.rs")
        (repo / "src/a.rs").write_text("// pad\n// pad\n" + BAD,
                                       encoding="utf-8")
        got, d = now()
        check(not d.uncommitted and not d.masked,
              f"padding above a site reclassified it: "
              f"uncommitted={len(d.uncommitted)} masked={len(d.masked)}")

        # ── a STAGED-only file has no HEAD blob ─────────────────────────────
        git(repo, "checkout", "--", "src/a.rs")
        (repo / "src/new.rs").write_text(BAD, encoding="utf-8")
        git(repo, "add", "src/new.rs")
        got, d = now()
        check(any(r[2]["file"].endswith("new.rs") for r in d.uncommitted),
              f"a staged-only file's row was not UNCOMMITTED: "
              f"{[r[2]['file'] for r in d.uncommitted]}")
        check(all(not r[2]["file"].endswith("new.rs") for r in d.head),
              f"a file in no commit entered the pins' view: {d.head}")

        # ── the ORDINAL: two IDENTICAL sites in one file stay distinct ──────
        # ⛔ Without it their keys collapse, HEAD dedupes to ONE row, and the
        # ceiling is UNDERCOUNTED by the number of duplicates — a ratchet that
        # silently tolerates the second copy of a defect. Measured: dropping
        # the ordinal reds nothing until a fixture actually carries a repeat.
        git(repo, "checkout", "--", ".")
        (repo / "src/new.rs").unlink(missing_ok=True)
        git(repo, "rm", "-q", "--cached", "src/new.rs")
        twice = BAD.replace(
            "    assert!(p99 < 5_000);" + chr(10),
            "    let p99 = sorted[(n as f64 * 0.99) as usize];" + chr(10)
            + "    assert!(p99 < 5_000);" + chr(10))
        (repo / "src/a.rs").write_text(twice, encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "twice")
        got, d = now()
        check(len(got["degenerate"]) == 2,
              f"fixture: want 2 identical degenerate sites, got "
              f"{len(got['degenerate'])}")
        check(len({r[0] for r in d.committed}) == len(d.committed),
              f"two identical sites collapsed to one key: "
              f"{[r[0] for r in d.committed]}")
        # ...and the pins' view counts BOTH.
        check(len([r for r in d.head if r[1] == "degenerate"]) == 2,
              f"the ceiling undercounts a repeated site: {len(d.head)}")

        # ── the KEY must carry every field a CEILING reads ──────────────────
        # ⛔ Four ceilings partitioned by CLASS, and `degenerate_asserted` is a
        # SUBSET of `degenerate` that turns on one boolean. A site that stays
        # degenerate but stops being load-bearing changes CLASS and nothing
        # else; with class out of the key the worktree's row would absorb
        # HEAD's and `max_degenerate_asserted` would count zero. A peer's
        # toolchain_override shipped exactly that shape.
        git(repo, "checkout", "--", ".")
        (repo / "src/new.rs").unlink(missing_ok=True)
        try:
            git(repo, "rm", "-q", "--cached", "src/new.rs")
        except Exception:
            pass
        (repo / "src/a.rs").write_text(BAD, encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "asserted")
        got, _d = now()
        check(len(got["degenerate_asserted"]) == 1,
              f"fixture: the committed site is not load-bearing: "
              f"{len(got['degenerate_asserted'])}")
        # Drop the assert! so the site stays DEGENERATE and stops being asserted.
        (repo / "src/a.rs").write_text(
            BAD.replace("    assert!(p99 < 5_000);" + chr(10), ""),
            encoding="utf-8")
        got, d = now()
        check(len(got["degenerate"]) == 1 and not got["degenerate_asserted"],
              f"fixture: want degenerate-but-not-asserted, got "
              f"{len(got['degenerate'])}/{len(got['degenerate_asserted'])}")
        # ⛔ Assert the KEY, not the tuple's class field. The first version of
        # this arm read `r[1]` — which carries the class whether or not the KEY
        # does — and passed with class removed from the address, because the
        # ordinal happens to order `degenerate` before `degenerate_asserted`
        # and the counts came out right by accident. An arm that reads the
        # field the rule is about is the only one that tests the rule.
        check(any("degenerate_asserted" in r[0] for r in d.masked),
              f"class is not in the KEY — a committed degenerate_asserted row "
              f"is absorbed by the worktree's degenerate row at the same "
              f"address: {[r[0] for r in d.masked]}")

        # ── the WALK guard ──────────────────────────────────────────────────
        check(head_sites(set())("src/a.rs", BAD) == [],
              "a path outside the sweep's own walk produced a row")

    return fails


def selftest() -> list[str]:
    """Pin that the verdict FIRES, that the WEAK/TRUNC_VAR asymmetry survives,
    and the parsers. Each fails SILENTLY otherwise, and a silent failure here
    reports a clean workspace."""
    import tempfile

    fails = []
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        repo = ws / "fake-repo"
        (repo / "benches").mkdir(parents=True)
        (repo / "BOUNDARY.md").write_text("x", encoding="utf-8")
        (repo / ".git").mkdir()

        # A planted DEGENERATE site: n=100 at p99 indexes 99 == n-1, the MAX.
        (repo / "benches" / "b.rs").write_text(
            "fn main() {\n"
            "    let n = 100;\n"
            "    let mut sorted = vec![0u64; n];\n"
            "    sorted.sort();\n"
            "    let p99 = sorted[(n as f64 * 0.99) as usize];\n"
            "    assert!(p99 < 5_000);\n"
            "}\n", encoding="utf-8"
        )
        got = audit(repo)
        if len(got["degenerate"]) != 1:
            fails.append(f"planted degenerate site: expected 1, got "
                         f"{[r['text'] for r in got['degenerate']]}")
        if len(got["degenerate_asserted"]) != 1:
            fails.append("planted site is load-bearing but did not count as asserted")
        if got["n_sites"] != 1 or got["n_rs"] != 1:
            fails.append(f"population wrong: {got['n_rs']} files, {got['n_sites']} sites")

        # A CONTROL: the correct nearest-rank form must produce no finding, or
        # the sweep reds on every correct repair and gets switched off.
        (repo / "benches" / "b.rs").write_text(
            "fn main() {\n"
            "    let n = 100;\n"
            "    let mut sorted = vec![0u64; n];\n"
            "    sorted.sort();\n"
            "    let p99 = sorted[((n as f64 * 0.99).ceil() as usize) - 1];\n"
            "    assert!(p99 < 5_000);\n"
            "}\n", encoding="utf-8"
        )
        if audit(repo)["degenerate"]:
            fails.append("control: correct ceil()-1 nearest rank reported as DEGENERATE")

        # The tally asymmetry is load-bearing and invisible if it inverts:
        # WEAK counts only when asserted, TRUNC_VAR regardless.
        t = pia.tally([
            {"verdict": pia.WEAK, "asserted": False},
            {"verdict": pia.WEAK, "asserted": True},
            {"verdict": pia.TRUNC_VAR, "asserted": False},
            {"verdict": pia.DEGENERATE, "asserted": False},
        ])
        if len(t["weak_asserted"]) != 1:
            fails.append("tally: WEAK must be counted only when asserted")
        if len(t["trunc_var"]) != 1:
            fails.append("tally: TRUNC_VAR must be counted regardless of asserted")
        if len(t["degenerate"]) != 1 or t["degenerate_asserted"]:
            fails.append("tally: DEGENERATE / DEGENERATE-ASSERTED split broken")

        # population derivation: BOUNDARY.md + a .git DIRECTORY, both required
        (ws / "no-boundary").mkdir()
        (ws / "no-boundary" / ".git").mkdir()
        (ws / "worktree-shaped").mkdir()
        (ws / "worktree-shaped" / "BOUNDARY.md").write_text("x", encoding="utf-8")
        (ws / "worktree-shaped" / ".git").write_text("gitdir: elsewhere", encoding="utf-8")
        if pia.repos(str(ws)) != ["fake-repo"]:
            fails.append(f"population derivation wrong: {pia.repos(str(ws))}")

        # pin parser: arity ENFORCED, comments stripped
        pins = ws / "pins.txt"
        pins.write_text("# c\nrepo-a 10 5 0 0 0 0  # trailing\n\n", encoding="utf-8")
        if parse_pins(pins) != {"repo-a": {"min_rs_files": 10, "min_sites": 5,
                                           "max_degenerate": 0,
                                           "max_degenerate_asserted": 0,
                                           "max_weak_asserted": 0,
                                           "max_trunc_var": 0}}:
            fails.append("pin parse: 7-field row not read correctly")
        pins.write_text("repo-a 1 2 3\n", encoding="utf-8")
        try:
            parse_pins(pins)
            fails.append("pin parse: short row accepted")
        except ValueError:
            pass
    # ⛔ Issue 822: `adjudicate`'s body is reached by nothing else.
    # Measured on the sibling sweep wired before this one: 14/14 canary
    # arms passed with `head_delta` STUBBED, because every arm that
    # exercises the split monkeypatches `adjudicate` and so never enters
    # it. These arms red against that stub.
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
    # The report's own selftest first: it exits 2 on failure. Without it a
    # tokenizer regression takes every count to zero and this sweep certifies
    # the workspace clean on the strength of an instrument that has gone blind.
    pia.selftest()

    fails = selftest()
    if fails:
        print("✗ percentile sweep SELFTEST FAILED — instrument untrustworthy:")
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

    names = pia.repos(str(WORKSPACE))
    if not names:
        print(f"✗ derived population is EMPTY under {WORKSPACE} — refusing to "
              f"report a green over zero repos")
        return 2

    local = local_min_sites(LOCAL_PINS)
    if local is None:
        print(f"✗ could not read min_sites_scanned from {LOCAL_PINS.name}")
        return 2
    mine = pins.get(REPO_ROOT.name, {}).get("min_sites")
    if mine != local:
        print(f"✗ pin drift: {PINS.name} says min_sites={mine} for "
              f"{REPO_ROOT.name}, {LOCAL_PINS.name} says min_sites_scanned="
              f"{local}. Same quantity, two files — change both.")
        return 1

    bad = False
    tot = {"n_rs": 0, "n_sites": 0, "degenerate": 0,
           "degenerate_asserted": 0, "weak_asserted": 0, "trunc_var": 0}
    n_uncommitted = n_masked = 0

    for name in names:
        repo = open_repo(name, WORKSPACE)
        got = audit(repo)

        # ── Issue 822: the DISPLAY reads the worktree, the PINS read HEAD ───
        # A ceiling is a claim about the repo, and a repo's state is its
        # commits. Concurrent sessions share these worktrees, so a row here may
        # sit on a line no commit contains — and re-pinning from such a run
        # bakes another session's in-flight edit into a tracked file, where it
        # reds on every other box.
        delta = adjudicate(repo, got, got["walk"])
        n_uncommitted += len(delta.uncommitted)
        n_masked += len(delta.masked)
        head_of = {cls: [r for r in delta.head if r[1] == cls]
                   for cls in GATED}

        row = pins.get(name)
        tot["n_rs"] += got["n_rs"]
        tot["n_sites"] += got["n_sites"]
        for k in ("degenerate", "degenerate_asserted", "weak_asserted", "trunc_var"):
            tot[k] += len(got[k])
        flags = []
        if row is None:
            # Issue 821: an acknowledged known-extra owes no pin row —
            # the marker reached population_verdict's FINAL line and not
            # this loop, so 8 of 9 sweeps red on repos they found
            # nothing in, hiding two live ratchet breaches.
            if not pin_row_exempt(name):
                flags.append("UNPINNED — add a row (or it can never red)")
        else:
            if got["n_rs"] < row["min_rs_files"]:
                flags.append(f"walk FLOOR breached: {got['n_rs']} .rs files "
                             f"< {row['min_rs_files']} — code was removed, or "
                             f"walk_rs went blind")
            if got["n_sites"] < row["min_sites"]:
                flags.append(f"site FLOOR breached: {got['n_sites']} < "
                             f"{row['min_sites']} — a repair campaign, or the "
                             f"tokenizer stopped naming these shapes")
            for cls in GATED:
                if len(head_of[cls]) > row[f"max_{cls}"]:
                    flags.append(f"{cls} {len(head_of[cls])} committed > "
                                 f"pinned {row[f'max_{cls}']}")
        findings = (got["degenerate"] + got["weak_asserted"] + got["trunc_var"])
        status = "✗" if flags else ("·" if findings else "✓")
        print(f"{status} {name:22s} rs={got['n_rs']:<5d} sites={got['n_sites']:<4d} "
              f"deg={len(got['degenerate'])} deg_asserted="
              f"{len(got['degenerate_asserted'])} weak_asserted="
              f"{len(got['weak_asserted'])} trunc_var={len(got['trunc_var'])}")
        for r in findings:
            if r["verdict"] == pia.TRUNC_VAR:
                # p is a parameter here, so p/n/idx/support are all None and
                # printing them tells the reader nothing. The line IS the finding.
                print(f"      {r['file']}:{r['line']}  {r['text']}")
            else:
                print(f"      {r['file']}:{r['line']}  p={r['p']} n={r['n']} "
                      f"idx={r['idx']} support={r['support']} "
                      f"asserted={r['asserted']}")
        for f in flags:
            bad = True
            print(f"      ✗ {f}")

    # The population axis, shared (Issue 793): UNREGISTERED reds in every
    # posture, UNSEEN reds without the marker, and the same set DEFERS loudly
    # with it. Never auto-detected — a genuine removal whose row update was
    # forgotten is set-identical to a partial clone from the walk alone.
    pop_lines, deferred, pop_fail = population_verdict(pins, names)

    # Issue 797 — the worktree is not the repo. This run reads files that
    # concurrent sessions are editing, so a finding may sit on a line no
    # commit contains. ADVISORY, never a failure: a sweep that hard-reds on
    # an ordinary dirty worktree is a sweep nobody runs. It rides the FINAL
    # line in BOTH directions (the `deferred` precedent) and is SILENT
    # unless the dirty set meets this sweep's own population — the percentile sites.
    if n_uncommitted or n_masked:
        # T3: the count stays honest in BOTH directions. A bare total invites
        # the one action Issue 822 exists to prevent — typing it into the pin.
        print(f"  ⚠ {n_uncommitted} row(s) UNCOMMITTED and {n_masked} MASKED "
              f"across the run; the class counts above are what HEAD carries")
    # ⚠ The advisory scope is WIDER than the split's: a dirty Cargo.toml
    # can change what a sweep reads, but it produces no ROW here, so
    # `adjudicate` scopes its HEAD reads to `*.rs` alone. Two scopes, one
    # deliberate difference.
    deferred.extend(sweep_advisory(
        names, ("*.rs", "Cargo.toml"), root=WORKSPACE,
        uncommitted_rows=n_uncommitted, masked_rows=n_masked))
    for _line in pop_lines:
        print(_line)
    if pop_fail:
        bad = True

    print(f"\n{len(names)} contract repo(s) · {tot['n_rs']} .rs file(s) · "
          f"{tot['n_sites']} percentile site(s) · {tot['degenerate']} degenerate "
          f"({tot['degenerate_asserted']} asserted) · {tot['weak_asserted']} "
          f"weak-asserted · {tot['trunc_var']} trunc-var")
    # State the scope where it is READ, not only in the docstring: the numbering
    # sweep's `dup=0` was read as a claim about `.benchmarks/` for a day.
    print("  scope: UNRESOLVED sites are NOT counted clean — a sample count no "
          "static pass can reach (a runtime length, a fn parameter) needs a "
          "per-site read, and that bucket is where findings hide. This sweep "
          "gates the four DECIDABLE classes only.")
    if bad:
        print("✗ percentile sweep FAILED — see the ✗ rows above")
        for _d in deferred:
            print(f"  ⚠ {_d}")
        print("    A 'p99' whose index is n-1 IS the max. Use nearest rank")
        print("    (ceil(p*n)-1) and report tail support, or drop the column")
        print("    when the sample count cannot support the quantile at all.")
        return 1
    _line = "✓ percentile sweep PASSED — 0 in all four classes, both floors held"
    if deferred:
        _line += "; DEFERRED: " + "; ".join(deferred)
    print(_line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
