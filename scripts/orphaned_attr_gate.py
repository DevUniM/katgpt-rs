#!/usr/bin/env python3
"""Gate on a `#[cfg]` separated from its item by a blank line.

Rust binds an attribute to the next item **across a blank line**. So this

    #[cfg(debug_assertions)]

    use crate::absorb_compress::{AbsorbCompress, AbsorbCompressLayer};

compiles, and makes the import debug-only. It is not a lint clippy has, and it
is invisible in review because the blank line reads as separation.

## The bug this is built from, with dates

`crates/katgpt-pruners/src/sdar/sdar_absorb.rs` was in exactly that state for
two days (fixed in `a08376a0`):

- `26d055c6` dropped `use std::cmp::Ordering;`, which is what the
  `#[cfg(debug_assertions)]` above it had correctly applied to, and left the
  attribute behind. It silently re-bound to the NEXT import.
- Every release build of `katgpt-pruners --features sdar_gate` then failed with
  5 errors: `debug_assertions` is off in release, so the import vanished while
  its five usages stayed unconditional.
- `26d055c6`'s own validation was a DEBUG run (`lib 597/0`), where
  `debug_assertions` is on and the import exists. That is `.docs/10_audits/cfg_gated_silent_zero_pass.md` T2b's
  lesson with the sign flipped — there, debug manufactured four false perf
  reds; here, debug hid a real build break.
- `7e34ccef` then deleted the blank line, which made the wrong binding look
  deliberate and would have erased the evidence.

## Why this can be a GATE and not a report

Measured across all contract repos at the fix (2026-09-03, when the workspace
was 19): **zero** sites. Not "few" — zero. So the pin is 0 and any future
occurrence is the push that introduces it. **Re-measured 2026-09-04 over the
live 16** (the three retired repos left for `git/obsolete/`): still zero in
every one of them. **Re-measured 2026-09-06**, after ~500 sibling commits:
still zero in all 16 — **11,132 `.rs` files, 49,624 outer-`#[cfg]` sites, 0
orphaned**. The site count is the part worth keeping: a zero over 49,624 sites
is evidence; a zero over a walk that has gone blind is not, which is why the
PASS line prints the population it saw rather than the one it assumed.

⛔ **Those three figures were measured over a FILESYSTEM walk, and Issue 777
retired that population the same day it landed** (`820bf8b6`). Re-measured
2026-09-14 over the TRACKED walk, same 16 repos: **8,694 `.rs` files, 26,598
outer-`#[cfg]` sites, 0 orphaned** — 22% and **46%** below the line above. The
verdict never moved; 23,026 of the sites offered as its warrant were in trees
no repo owns (mmorpg-remaster's gitignored `mmorpg/` nested repository,
riir-ai's vendored `wgpu-hal` fork, riir-train's cargo `OUT_DIR` sources under
`.runs/target-*`). Both figures are kept, dated, because a reader who cannot
see that the population DEFINITION changed reads that drop as deleted code.

Do not read either as this gate's verdict. It audits **one** repo per
invocation, and until 2026-09-04 its PASS line printed "measured 0 across 19
repos" on every run — a cross-repo claim no run had made, with a count that had
gone stale two commits earlier, printed two lines below the repo-set gate
saying 16. It now reports the repo it scanned and the population it saw.

⛔ And removing the claim from the PASS line did not stop it going stale — it
only stopped it being *printed* stale. The number went on being typed into this
docstring by hand for eleven days, and nothing re-asserted it until Issue 784
built the missing half: `scripts/orphaned_attr_drift_sweep.py`, workstation,
every contract repo, floors in `scripts/orphaned_attr_drift_floors.txt` (which
asserts `FLOOR_FILES` / `FLOOR_CFG_SITES` below against itself). **Take the
cross-repo figure from that run, not from this paragraph.**

The broader shape (**any** attribute + blank line + item) is 2,044 sites and is
NOT gateable: it is dominated by whole-file INNER attributes (`#![cfg(...)]`),
which bind to the enclosing module rather than to the next item and are
conventionally followed by a blank line. Narrowing to OUTER `#[cfg]` /
`#[cfg_attr]` is what takes 2,044 to 0 — the narrowing is the instrument.

## Scope

katgpt-rs only, same reasoning as `cfg_gated_floor_gate.py`: CI has a single
checkout. Pass a repo path to audit a sibling; adopting it there is an owner
call, like `.docs/10_audits/cfg_gated_silent_zero_pass.md` T3.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tracked_walk import tracked_files  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

# OUTER `#[cfg(...)]` / `#[cfg_attr(...)]` only. An INNER `#![cfg(...)]` binds
# to the enclosing module, so a blank line after it is correct and common —
# including it is what made the naive measurement 2,044 instead of 0.
OUTER_CFG = re.compile(r"^\s*#\s*\[\s*cfg(?:_attr)?\s*\(")
ANY_ATTR = re.compile(r"^\s*#!?\s*\[")

# The population is the TRACKED `*.rs` set (`scripts/tracked_walk.py`, Issue
# 777), not a filesystem walk behind a directory-NAME prune list. katgpt-rs'
# tracked and filesystem counts happen to be EQUAL today (2415 both ways), so
# this is not a repair of a live miscount here — it is the removal of the only
# way this gate's floors could ever be satisfied by files the repo does not
# own, which is exactly how the percentile sweep came to pin riir-train's walk
# floor at 2500 against 1129 tracked files.
#
# The prune list it replaces was not wrong about its own hazard, and the
# fallback branch of `tracked_files` keeps it: `rglob("*.rs")` followed by a
# `"target" in parts` filter still DESCENDS into target/ (117 GB, ~1.3M
# entries) — the same trap that made bench_doc_audit.py take 556s, and the
# `find -not -path` trap one level over. `git ls-files` does not walk at all.

# `max_offenders = 0` is a CEILING, and a ceiling passes over an empty
# population — a pruning bug, a moved source root or a read failure all print a
# confident "0 offender(s)" that is indistinguishable from the clean state this
# asserts. selftest() pins the tokenizer against synthetic input; these pin the
# POPULATION of the real run. katgpt-rs measured 2026-09-04: 2,418 `.rs` files,
# 6,936 outer-`#[cfg]` sites. Floors sit well below so that extracting code to a
# sibling crate does not red the gate, while a blind walk still does.
# Scope-guarded to katgpt-rs: a sibling audit has its own population.
FLOOR_FILES = 1500
FLOOR_CFG_SITES = 4000


class Scan(NamedTuple):
    """A verdict AND the population it was reached over."""

    offenders: list[tuple[str, int, str, str]]
    files: int
    cfg_sites: int


def scan_text(rel: str, text: str) -> tuple[list[tuple[str, int, str, str]], int]:
    """One SOURCE TEXT's offenders, plus its `#[cfg]` site count.

    The classifier proper, split out of `scan` for Issue 822: a caller holding
    the bytes from somewhere other than the working tree — a HEAD blob, for the
    worktree-vs-commit split — reaches the rules here without a second copy of
    them. `markdown_fence_gate.scan_text` and `percentile_index_audit.
    audit_text`, same shape, same reason.

    `rel` only ADDRESSES the rows; no decision reads it.
    """
    out: list[tuple[str, int, str, str]] = []
    lines = text.splitlines()
    cfg_seen = sum(1 for line in lines if OUTER_CFG.match(line))
    for i in range(len(lines) - 2):
        if not OUTER_CFG.match(lines[i]) or lines[i + 1].strip():
            continue
        nxt = lines[i + 2]
        # A following comment or another attribute is not the item, and
        # a blank-line run means the attribute is dangling further
        # down; both are reported only when a real item follows.
        if not nxt.strip() or nxt.lstrip().startswith("//") or ANY_ATTR.match(nxt):
            continue
        out.append((rel, i + 1, lines[i].strip(), nxt.strip()[:60]))
    return out, cfg_seen


def scan(repo: Path) -> Scan:
    """The walk around `scan_text` — the half that can go blind per-repo."""
    out: list[tuple[str, int, str, str]] = []
    files_seen = 0
    cfg_seen = 0
    for p in tracked_files(repo, "*.rs")[0]:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        files_seen += 1
        rows, n_cfg = scan_text(str(p.relative_to(repo)), text)
        cfg_seen += n_cfg
        out += rows
    return Scan(sorted(out), files_seen, cfg_seen)


def unmeasured(repo: Path, files: int, own: bool) -> str | None:
    """Why this walk is NOT a measurement, or `None` if it is.

    Extracted rather than written inline, and that is the repair rather than a
    tidy-up: `main` calls `selftest`, so a decision living in `main` cannot be
    armed without recursing. Both branches below were inline first and neither
    was reachable by any arm.

    ⛔ The class (Issue 805). `tracked_files` answers an unreadable path with
    an EMPTY SET — the same value a repo with no Rust produces — so a typo'd
    or missing path walked to 0 files and printed
    `✓ orphaned-attribute gate PASSED — pinned at 0, measured 0 over 0 .rs
    file(s) in nonexistent-repo`. Exit 0. Every verdict here is a ceiling over
    that walk, and a walk that returned nothing satisfies every ceiling.

    ⚠ The sibling branch is NOT redundant with the floors, and the floors are
    right to skip it: they are this repo's population and a sibling's belongs
    to `orphaned_attr_drift_sweep.py`. The consequence is that sibling mode
    has no blindness detector at ALL — `floors n/a` is printed on the pass
    line — so this is the only thing standing between a misspelled sibling
    path and a green.

    ⚠ And it is UNSEEN, not FAILED. A contract repo with no Rust at all walks
    to 0 legitimately, so condemning it would be wrong; refusing to call it a
    pass is not. Never folded into the pass column — the house rule for every
    bucket that means *unanswered*.
    """
    if not repo.is_dir():
        return f"not a directory: {repo}"
    if not own and files == 0:
        return (f"{repo.name} walked to 0 .rs file(s) — legitimate for a repo "
                f"with no Rust, indistinguishable here from a blind walk")
    return None


def selftest() -> None:
    """Pin both directions on every invocation.

    The false-negative direction is the one that matters: a regex regression
    makes this print `0 offenders` forever, which is indistinguishable from the
    clean state it is asserting.
    """
    import tempfile

    # ── the UNSEEN predicate (Issue 805) ────────────────────────────────────
    # Four arms over `unmeasured`. Each reds under perturbation of the line it
    # is aimed at, measured one mutation at a time.
    with tempfile.TemporaryDirectory() as _td:
        _root = Path(_td)
        _gone = _root / "no_such_dir"
        assert unmeasured(_gone, 0, False) is not None,             "a path that does not exist read as a measurement"
        assert "not a directory" in unmeasured(_gone, 0, False),             "a missing path was refused for the wrong reason"
        # An OWN-repo walk of 0 is left to the floors, which say it better —
        # this predicate must not double-report it.
        assert unmeasured(_root, 0, True) is None,             "own repo at 0 files was claimed by the sibling branch, not the floors"
        # A SIBLING at 0 has no floor behind it, so this is the only guard.
        assert unmeasured(_root, 0, False) is not None,             "a sibling walking to 0 .rs files read as a measurement"
        # A real population is a measurement in both scopes.
        assert unmeasured(_root, 1, False) is None, "a non-empty sibling was refused"
        assert unmeasured(_root, 1, True) is None, "a non-empty own repo was refused"

    positive = (
        "#[cfg(debug_assertions)]\n"
        "\n"
        "use crate::absorb_compress::AbsorbCompressLayer;\n"
    )
    negatives = {
        # Correctly attached — the overwhelmingly common shape.
        "attached": "#[cfg(feature = \"x\")]\nuse a::b;\n",
        # INNER attribute: binds to the module, blank line is conventional.
        # This single case is the difference between 2,044 hits and 0.
        "inner": '#![cfg(feature = "x")]\n\nuse a::b;\n',
        # A doc comment after the blank line is not the item.
        "comment": '#[cfg(feature = "x")]\n\n// note\nuse a::b;\n',
        # Another attribute after the blank line: still an attribute run.
        "attr": '#[cfg(feature = "x")]\n\n#[derive(Debug)]\nstruct S;\n',
        # A non-cfg attribute is formatting, not conditional compilation.
        "derive": "#[derive(Debug)]\n\nstruct S;\n",
    }
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "pos.rs").write_text(positive)
        got = scan(root)
        assert len(got.offenders) == 1, f"the real bug's shape was not detected: {got}"
        assert got.offenders[0][0] == "pos.rs"
        # ⚑ The reported LINE, added by Issue 790 T3. `arm_reach_audit` found
        # the `i + 1` 0-to-1-indexed conversion surviving an off-by-one flip:
        # nothing asserted the address, only the count. A finding at the wrong
        # line sends the reader to the wrong place, and the attribute is on
        # line 1 of the fixture — the only offset where `i + 1` and `i - 1`
        # differ visibly from each other AND from a plausible answer.
        assert got.offenders[0][1] == 1, (
            f"the orphaned attribute is on line 1 and was reported at "
            f"{got.offenders[0][1]}")
        assert got.offenders[0][2] == "#[cfg(debug_assertions)]", got.offenders[0][2]
        assert got.offenders[0][3].startswith("use crate::absorb_compress"), (
            f"the following ITEM was misreported: {got.offenders[0][3]!r}")

        # …and the line must track the attribute's actual position, not be a
        # constant that happens to be 1. Same shape, pushed down the file.
        (root / "pos.rs").write_text("// a leading comment\n\n" + positive)
        got2 = scan(root)
        assert len(got2.offenders) == 1 and got2.offenders[0][1] == 3, (
            f"the reported line does not track the attribute: {got2.offenders}")
        # The population is a separate claim from the verdict and is pinned
        # separately: a walk that counts nothing must not be able to report a
        # clean zero. This is the in-miniature version of FLOOR_* below.
        assert (got.files, got.cfg_sites) == (1, 1), f"population miscounted: {got}"

    for name, src in negatives.items():
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "n.rs").write_text(src)
            got = scan(root)
            assert got.offenders == [], f"false positive on {name}: {got.offenders}"
            # A negative is a real scanned file, not an unread one — otherwise
            # every case above would also pass on a walk that saw nothing.
            assert got.files == 1, f"{name} was not read: {got}"

    # The walk must PRUNE, not filter: a file under target/ is invisible.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "target").mkdir()
        (root / "target" / "gen.rs").write_text(positive)
        got = scan(root)
        assert got.offenders == [], "target/ was walked"
        assert got.files == 0, f"target/ was read: {got}"

    # A non-`.rs` file is not the population. Guards the extension filter, which
    # is what a floor would otherwise be silently satisfied by (`.md` is plentiful).
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "n.md").write_text(positive)
        assert scan(root) == Scan([], 0, 0), "a non-.rs file entered the population"


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
    selftest()
    repo = Path(argv[1]).resolve() if len(argv) > 1 else REPO_ROOT
    got = scan(repo)
    why = unmeasured(repo, got.files, repo == REPO_ROOT)
    if why:
        print(f"⛔ orphaned-attribute gate UNSEEN — {why}")
        print("  NOTHING was measured, so the 0 offenders below would not be a")
        print("  finding count. Every verdict this gate prints is a ceiling over a")
        print("  walk; a walk that returned nothing satisfies every ceiling there is.")
        print("  The half that CAN tell an empty repo from a blind walk is")
        print("  orphaned_attr_drift_sweep.py, which pins each repo's population.")
        return 2
    found = got.offenders
    pop = f"{got.files} .rs file(s), {got.cfg_sites} outer-#[cfg] site(s)"

    print(f"orphaned-attribute gate — {repo.name}: {len(found)} offender(s) over {pop}")
    for path, line, attr, item in found:
        print(f"  ✗ {path}:{line}  {attr}")
        print(f"      binds ACROSS the blank line to: {item}")
    if found:
        print(
            "\n  A `#[cfg]` separated from its item by a blank line still applies to "
            "that item.\n  Either attach it or delete it — see this file's header for "
            "the two-day release\n  break it is built from (a08376a0)."
        )
        print(f"✗ orphaned-attribute gate FAILED — {len(found)} site(s)")
        return 1

    # The floors are this repo's population only — a sibling audit is a
    # different population and gets the report without the verdict half.
    if repo == REPO_ROOT and (got.files < FLOOR_FILES or got.cfg_sites < FLOOR_CFG_SITES):
        print(
            f"\n  The population fell below its floor ({FLOOR_FILES} files, "
            f"{FLOOR_CFG_SITES} sites).\n  A zero over a shrunken population is not a "
            "clean repo — read it as the walk having\n  gone blind (pruning, a moved "
            "source root, a read failure) until proven otherwise.\n  If the shrink is "
            "real, re-measure and move the floor in the same commit."
        )
        print("✗ orphaned-attribute gate FAILED — population below floor")
        return 1

    scope = "this repo" if repo == REPO_ROOT else f"{repo.name} (sibling audit, floors n/a)"
    print(f"✓ orphaned-attribute gate PASSED — pinned at 0, measured 0 over {pop} in {scope}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
