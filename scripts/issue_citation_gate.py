#!/usr/bin/env python3
"""GATE: a CROSS-REPO `Issue N` / `Plan N` / `Bench N` citation that names no repo.

`numbering_gate.py` protects a number from being allocated TWICE in one repo.
It structurally cannot see the failure one level up: a citation whose referent
lives in a DIFFERENT repo. `Issue 750` in this repo's prose meant
`riir-ai/.issues/750_behavior_first_quantization_promotion_gate.md`, and this
repo's own `.issues/.highwater` read **748** — two away. The moment anybody
follows the Numbering Discipline and allocates 749, then 750, that citation
stops dangling and starts resolving, silently, to the WRONG document. A
dangling reference is an inconvenience; a reference that rebinds to a real but
unrelated issue is a wrong answer delivered with a straight face.

Measured when this gate landed (2026-09-12): EIGHT unqualified rows over THREE
numbers — `Issue 513` (riir-train, x3), `Issue 750` (riir-ai, x3), `Issues
490/493` (riir-ai, x2). Every one resolved uniquely by TITLE match, and the
convention for writing them was already in the same file four lines away
("riir-ai `.issues/892`", "894 resolved same day in riir-ai").

⛔ **The AMBIGUOUS bucket is this gate's stated blind spot, not a clean pass.**
A number that exists BOTH locally and in a sibling is undecidable from the
number alone, and there were **35** such cited Issue numbers at landing. This
gate is green over them by construction: its predicate is "does NOT resolve
locally", so a bare `Issue 47` naming riir-ai's 47 reads as this repo's 47 and
always will. It is REPORTED every run and deliberately NOT gated: a
ceiling on it reds whenever somebody writes a perfectly correct citation to a
NEW local number that a sibling also happens to have — a nuisance red for a
right action, and a gate that reds on right actions is a gate that gets
bypassed (`staged_set_audit.py`'s rationale, one axis over). So it has the
standing of tail support in the percentile audit: a quantity that ORDERS the
rows and sizes the blind spot, never a verdict. The only real defence is the
writing convention — name the repo whenever the referent is not local,
ambiguous or not.

Exit 0 clean, 1 on an unqualified citation, **2 if the instrument is
untrustworthy** (a floor breached => the walk went blind; a scanned document
missing). An unreliable instrument is not the same finding as drift.

⛔ **The CI lane cannot adjudicate and does not pretend to.** docs_gate.yml
runs per-push on main in a SINGLE checkout — no sibling workspace, so the
ownership lookup is structurally empty and every cross-repo citation would
read as a false finding. A blind run therefore refuses (exit 2) UNLESS the
workflow has marked the context with DOCS_GATE_CI=1, in which case the gate
verifies only the axes decidable from this checkout (documents present, the
width bound, the citation walk over its floor) and says in its LAST line —
docs_gate.sh prints only tail -1 of a passing check — that the cross-repo
axis is DEFERRED to the workstation run. The marker is an explicit opt-in
recorded in the workflow file, never auto-detected, so a blind WORKSTATION
run (a moved repo, a missing sibling) still refuses. Found the hard way:
the gate landed during a main-only CI window and the first promote push was
its first CI run (HISTORY.md 2026-09-12).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from numbering_drift_sweep import contract_repos  # noqa: E402 — the SEVENTH predicate, reused not re-derived
from skill_repo_set_gate import PARTIAL_MARKER, fenced_blocks, partial_clone_state  # noqa: E402 — the fence scanner + the partial-clone axis (Issue 765), reused not re-derived

REPO_ROOT = HERE.parent
# Overridable for testing (the skill_repo_set_gate precedent): the
# partial-clone sims (Issue 765) run the real instruments over a symlink
# farm without copying repos.
WORKSPACE = Path(os.environ.get("WORKSPACE_ROOT", str(REPO_ROOT.parent)))
FLOORS = HERE / "issue_citation_floors.txt"

# ── vocabulary: DATA, not derived ──────────────────────────────────────────
# Deriving both the scope and the population from one walk is what makes a gate
# permanently green. Only the population (which repos, which numbers) is
# derived; the citation vocabulary and the scanned documents are pinned.
KINDS = {
    "Issue": ".issues",
    "Plan": ".plans",
    "Research": ".research",
    "Bench": ".benchmarks",
    "Proposal": ".proposals",
}

# A plural kind word may head a LIST: "Issues 724, 725", "Issues 490/493",
# "Plans 596 and 597". Reading only the head number under-reports the class —
# `Issues 490/493` hid its second referent from the first version of this scan.
_HEAD = re.compile(r"\b(%s)(s?)\s+(\d{2,4})" % "|".join(KINDS))
# `.match(s, pos)` already anchors AT pos — Python `re` has no `\G`.
_TAIL = re.compile(r"\s*(?:,|/|and|&)\s*(\d{2,4})")

NUMBERED = re.compile(r"^(\d+)_")

# ── the WIDTH BOUND is LOAD-BEARING, not a blind spot awaiting repair ────────
# `\d{2,4}` was recorded (Issue 751 T2b) as "a blind spot, measured at zero
# cost today: 0 single-digit citations in the workspace". True in this gate's
# scope, and the framing invited the wrong repair — widening to `\d{1,4}` reads
# as free. Measured over every tracked `.md` in 19 repos (Issue 753,
# 2026-09-12) it is not free:
#
#   51 false HEADS  — `## Bench 1: Throughput`, `| Bench 3 | …`: a section
#                     NUMBERING inside a document, never a citation of
#                     `.benchmarks/001_*`. 0 of them are real.
#    0 false TAILS  — because the list expander already carries a PLURAL
#                     precondition. That is the load-bearing half, and it is
#                     what keeps `Plan 460, 31.5%` -> Plan 31 and
#                     `Issue 096, 2,294 LOC` -> Issue 2 from ever being built:
#                     both heads are SINGULAR. Re-measured with `\d{2,4}` in
#                     force, 0 tail expansions anywhere in the corpus land on
#                     the integer part of a measurement.
#
# ⛔ The 0 is a correction of this session's own first number, which was 55 —
# measured with the plural precondition DROPPED, and so over-stating the cost
# of a widening in the direction that flattered the conclusion. The two rules
# are not independent and neither may be costed alone. The head count moved
# 44 -> 51 between two runs an hour apart for the ordinary reason (the corpus
# is edited by five-plus concurrent sessions): read it as a magnitude.
#
# So the bound buys ~51 suppressed false rows for 0 suppressed true ones.
# What the class DOES need is liveness: "0 occurrences" is a dated measurement
# over documents edited daily, and the day somebody writes `Issue 6` the
# verdict regex goes silently blind on it. These two patterns are the bound's
# own complement — counted every run, pinned at 0, and a breach is exit 2
# (instrument untrustworthy), not exit 1 (prose drift): the prose did not get
# worse, the scope grew a form the verdict cannot see.
_HEAD_1D = re.compile(r"\b(?:%s)s?\s+(\d)(?!\d)" % "|".join(KINDS))
# The tail complement carries `_HEAD`'s own PLURAL precondition: a singular
# head never expands a list, which is exactly why `Plan 460, 31.5%` is inert
# TODAY and why dropping the width bound without dropping the plural rule would
# still be a regression. Measuring the complement without it over-states what a
# widening would cost, in the direction that makes the widening look worse.
_TAIL_1D = re.compile(
    r"\b(?:%s)s\s+\d{2,4}\s*(?:,|/|and|&)\s*(\d)(?!\d)" % "|".join(KINDS))


def unseen_by_width(text: str) -> tuple[int, int]:
    r"""(single-digit heads, single-digit list tails) `\d{2,4}` cannot see."""
    return len(_HEAD_1D.findall(text)), len(_TAIL_1D.findall(text))


def parse_pins(path: Path) -> dict[str, int | list[str]]:
    pins: dict[str, int | list[str]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        pins[key] = [v for v in val.split() if v] if key == "documents" else int(val)
    return pins


_SUBDIR_KIND = {v: k for k, v in KINDS.items()}

# `## Issue 059 (2026-08-14) — Demonstration-teachable pets`: a heading whose
# number is IMMEDIATELY followed by a parenthetical. Both halves are
# load-bearing, and both were measured (Issue 754) against the 11 candidate
# headings in the workspace rather than reasoned about:
#
#   `## Issue 667 consumer-side follow-ups (2026-08-14/15)` — words between the
#       number and the parenthetical: a heading ABOUT a foreign number, not a
#       record of a local one. Same shape: `## Plan 539 follow-up (…)`.
#   `## Issue 092 (riir-mmorpg-examples) — …` — the parenthetical NAMES the
#       owner, and it is not this repo.
#   `# Proposal 031 §0 + §3: …` — H1, and inside a fenced block besides.
#
# 7 of the 11 survive; all 7 read as genuine local allocations. A heading
# inside a fenced code block is EXCLUDED by `fenced_lines()` below — measured
# EMPTY today (0 of 57 matches workspace-wide), so the filter changes no
# verdict and is landed for the SUPPRESSION direction it closes: a quoted
# heading in an example block is not an allocation record, and a false
# allocation does not drop a row, it INVERTS one (Issue 754).
# ── fenced code blocks: excluded from the ALLOCATION path ONLY ──────────────
# The asymmetry is MEASURED on both sides, not reasoned about:
#
#   allocation (`heading_allocated`) — can only ever SUPPRESS a finding, and a
#       heading inside a fence is a QUOTED example, not a record. Excluded.
#       Measured population: 0 of 57 `_SELF_HEADING` matches workspace-wide.
#   citations (`citations`) — PRODUCES the findings, and 57 of 2972 citations
#       (1.9%) live inside fences. They are not incidental: riir-auth's layout
#       block writes `/git/riir-ai  <- ... Plan 307` and riir-clippy's writes
#       `Bench 010` / `Issue 081` — genuine sibling ATTRIBUTIONS a reader
#       follows. Excluding fences there would hide 57 real rows. NOT excluded.
#
# Matching is delegated to `skill_repo_set_gate.fenced_blocks()` — the same
# scanner, imported rather than re-derived, exactly as `contract_repos` is. It
# is already CommonMark-ish (opening run length recorded; only a BARE run of at
# least that length closes it, so an inner ```bash does not) because it was
# written after a naive toggle mis-phased on `rust-optimize/SKILL.md`'s
# unclosed ```text and swallowed that gate's own first canary. A second copy
# here would be a second thing to get wrong.
#
# It reads BACKTICK fences only; `~~~` is unsupported. Measured 2026-09-12: 0
# tilde fences in tracked `.md` across all 19 contract repos (the one hit in
# the workspace is vendored llama.cpp, outside the population). A WATCHED
# class, not a silent one.


def fenced_lines(text: str) -> tuple[set[int], int | None]:
    """(0-indexed lines inside a fence, opening index of an UNTERMINATED one).

    An unterminated fence is returned rather than swallowed: its tail would
    otherwise be excluded to EOF, which is the same suppression this filter
    exists to prevent, just moved somewhere nobody would look for it. Callers
    fail SAFE on it (see `heading_allocated`) and it is surfaced as a verdict.
    """
    inside: set[int] = set()
    open_at: int | None = None
    for first, last, _body, _prev in fenced_blocks(text):
        if last < 0:            # the unterminated-block sentinel
            open_at = first - 1
            continue
        inside.update(range(first - 1, last))
    return (set() if open_at is not None else inside), open_at


def unterminated_fences(repo: Path) -> list[tuple[str, int]]:
    """(document, 1-indexed line) for every unterminated fence in the pinned docs.

    A parse hazard AND a real rendering bug, worth reporting for its own sake:
    katgpt-rs's own rust-optimize SKILL.md once swallowed 43 lines this way.
    """
    out = []
    for doc in _self_docs():
        p = repo / doc
        if not p.is_file():
            continue
        _, open_at = fenced_lines(p.read_text(encoding="utf-8", errors="replace"))
        if open_at is not None:
            out.append((doc, open_at + 1))
    return out


_SELF_HEADING = re.compile(
    r"^#{2,}\s+(?:\*\*)?(%s)\s+0*(\d{2,4})\s*\(([^)\n]*)\)" % "|".join(KINDS))

_DOCS_CACHE: list[str] | None = None
_NAMES_CACHE: list[str] | None = None


def _self_docs() -> list[str]:
    """The pinned document list, read ONCE from the floors file, not re-typed."""
    global _DOCS_CACHE
    if _DOCS_CACHE is None:
        docs = parse_pins(FLOORS)["documents"]
        assert isinstance(docs, list)
        _DOCS_CACHE = docs
    return _DOCS_CACHE


def heading_allocated(repo: Path, subdir: str,
                      repo_names: list[str] | None = None) -> set[int]:
    """Numbers this repo records for ITSELF in a heading of its own documents.

    A resolved file is REMOVED by the noise-reduction rule; a file created and
    removed without an intervening commit leaves nothing in `git log` either,
    and the repo's own HISTORY.md heading is then the WHOLE allocation record.
    Measured (Issue 754): 7 such numbers workspace-wide, and two of them were
    driving a `⛔MISATTRIBUTED` verdict against prose that was CORRECT —
    riir-game-sdk's `riir-mmorpg-examples Issue 059`, which Issue 752's census
    had adjudicated the other way and recorded as an "outright WRONG address".

    This is the only path here that can SUPPRESS a finding, so its two filters
    are measured (see `_SELF_HEADING`) rather than assumed.
    """
    kind = _SUBDIR_KIND.get(subdir)
    if kind is None:
        return set()
    global _NAMES_CACHE
    if repo_names is None:
        if _NAMES_CACHE is None:
            _NAMES_CACHE = [p.name for p in contract_repos(WORKSPACE)]
        repo_names = _NAMES_CACHE
    foreign = [n for n in repo_names if n != repo.name]
    out: set[int] = set()
    for doc in _self_docs():
        p = repo / doc
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        # Unterminated fence => `fenced_lines` returns an EMPTY set, so nothing
        # is excluded and behaviour is exactly today's measured-correct one.
        # The hazard is reported by `unterminated_fences()`, never swallowed.
        fenced, _ = fenced_lines(text)
        for i, line in enumerate(text.splitlines()):
            if i in fenced:
                continue
            m = _SELF_HEADING.match(line)
            if not m or m.group(1) != kind:
                continue
            if any(_NAME[n].search(m.group(3)) for n in foreign):
                continue
            out.add(int(m.group(2)))
    return out


# Issue 781: the SAME shape, without the style anchor. Used only to MEASURE
# what `_SELF_HEADING` rejects — never to allocate. Widening the oracle to this
# is unsound and `citation_drift_sweep.selftest()` arm 2 proves it: it pins
# `## Issue 043 follow-up (2026-01-01)` as a measured negative, and
# `043 follow-up (…)` and `097 resolved — … (…)` are the same shape. No
# punctuation rule separates commentary from allocation; the distinction is
# semantic. So the cost is printed instead of guessed at.
_HEADING_SHAPED = re.compile(
    r"^#{2,}\s+(?:\*\*)?(%s)\s+0*(\d{2,4})\b(.*)$" % "|".join(KINDS))


def heading_style_blind(repo: Path, subdir: str,
                        repo_names: list[str] | None = None) -> tuple[int, int]:
    """(accepted, heading_shaped) self-allocation records in this repo's docs.

    A triage quantity with the standing of AMBIGUOUS and the width-bound
    complement — NEVER a verdict, never folded into a finding count. It answers
    one question: how much of this repo's own allocation record does
    `heading_allocated()` decline to read, **on style alone**?

    The foreign-repo filter is applied to BOTH sides, over the whole heading,
    so a row rejected for naming a sibling is not counted as a style loss. The
    gap is therefore exactly the style gap.

    Measured 2026-09-14 over 16 repos x AGENTS.md+HISTORY.md (the
    foreign-filtered population this function counts): **64 of 152 read, 88
    unread**, and the split is by HOUSE STYLE rather than correctness —
    riir-mmorpg-examples 43/43 (`## Issue NNN (date) — title`); riir-ai 0/25,
    riir-clippy 0/25 and riir-train 0/13 (`## Issue NNN resolved — title
    (date)`); seal-remake 14/15; katgpt-rs mixed at 7/29, its own newest closes
    in the form its own instrument cannot read. A dated measurement RECORD, not
    a claim — the live figures are printed by `citation_drift_sweep.py` on
    every run, per repo and in total.

    Why it matters in the direction that is currently 0: an incomplete OWNERS
    set turns a correctly-qualified citation into a FALSE ⛔MISATTRIBUTED —
    Issue 754's exact failure, inherited by Issue 780's MISATTRIBUTED-IN-RANGE.
    Latent, so it is printed rather than remembered.
    """
    kind = _SUBDIR_KIND.get(subdir)
    if kind is None:
        return (0, 0)
    global _NAMES_CACHE
    if repo_names is None:
        if _NAMES_CACHE is None:
            _NAMES_CACHE = [p.name for p in contract_repos(WORKSPACE)]
        repo_names = _NAMES_CACHE
    foreign = [n for n in repo_names if n != repo.name]
    accepted = shaped = 0
    for doc in _self_docs():
        p = repo / doc
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        fenced, _ = fenced_lines(text)
        for i, line in enumerate(text.splitlines()):
            if i in fenced:
                continue
            m = _HEADING_SHAPED.match(line)
            if not m or m.group(1) != kind:
                continue
            if any(_NAME[n].search(m.group(3)) for n in foreign):
                continue          # rejected for NAMING a sibling, not on style
            shaped += 1
            if _SELF_HEADING.match(line):
                accepted += 1
    return (accepted, shaped)


def allocated(repo: Path, subdir: str,
              repo_names: list[str] | None = None) -> set[int]:
    """Every number EVER allocated under `repo/subdir` — worktree AND history.

    History is not optional: the noise-reduction rule REMOVES a resolved issue
    file, so a worktree-only walk reports a live citation as dangling. Issue
    750 is exactly that shape — resolved and removed in riir-ai `b559d2da3`.

    Nor is the FILE walk sufficient (Issue 754): remove a file that was never
    committed and `git log` is empty too. `heading_allocated()` recovers those.
    """
    out: set[int] = set(heading_allocated(repo, subdir, repo_names))
    d = repo / subdir
    if d.is_dir():
        for f in d.iterdir():
            m = NUMBERED.match(f.name)
            if m:
                out.add(int(m.group(1)))
    log = subprocess.run(
        ["git", "-C", str(repo), "log", "--all", "--name-only", "--pretty=format:", "--", f"{subdir}/"],
        capture_output=True, encoding="utf-8", errors="replace",
    )
    prefix = re.compile(re.escape(subdir) + r"/(\d+)_")
    for line in log.stdout.splitlines():
        m = prefix.match(line.strip())
        if m:
            out.add(int(m.group(1)))
    return out


def aliases(repo_name: str) -> list[str]:
    """Full directory name, plus a SHORT-FORM alias where one is unambiguous.

    Prose names a sibling both ways — "riir-ai Issue 750" and "dapps Issue 027"
    are equally followable, and a test matching only the directory name calls
    the second one unqualified. Measured over the workspace, 2 of the first 4
    flagged rows were exactly that false positive.

    The alias is the name minus a `riir-` prefix, and ONLY when >= 4 characters:
    `ai`, `kat`, `dao` are too short to appear in prose without colliding with
    ordinary words. Short aliases keep the full name as their only form.
    """
    out = [repo_name]
    stem = repo_name[5:] if repo_name.startswith("riir-") else ""
    if len(stem) >= 4:
        out.append(stem)
    return out


class _NameRx(dict):
    """`riir-viewbridge` names `seal-remake-unity`; a plain `"seal-remake" in
    ctx` reads that as naming **seal-remake**, a different repo, and qualified
    a `Plan 031` citation on it (Issue 752). A repo name is only a repo name
    when no further name-segment extends it — `riir-ai/scripts/…` and
    `riir-ai's` still match, `riir-games-mmorpg` does not match
    `riir-game-sdk`."""

    def __missing__(self, name: str) -> re.Pattern:
        rx = re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])")
        self[name] = rx
        return rx


_NAME = _NameRx()

# An alias only qualifies a citation when it sits right ON it ("dapps Issue 27"),
# never merely somewhere nearby: `chain`, `train` and `shader` are ordinary
# words in this prose, and a 3-line window full of them would qualify every
# citation in the repo and quietly retire the gate. The FULL directory name is
# unambiguous enough to accept from the wider window.
_ALIAS_REACH = 40


def qualifiers(lines: list[str], ln: int, lead: str, sibs: list[Path]) -> tuple[set[str], set[str]]:
    """Repo names the prose offers as this citation's address -> (window, adjacent).

    `window` is the full directory name anywhere in the 3-line backward window;
    `adjacent` is the subset sitting ON the citation (inside `lead`), plus the
    short-form aliases, which are only ever accepted there.

    Split because the two carry different weight once the caller checks
    OWNERSHIP (Issue 752): an adjacent non-owner is somebody writing a wrong
    address, a window-only non-owner is a name that was never an attribution.
    """
    ctx = "\n".join(lines[max(0, ln - 3):ln])
    window = {s.name for s in sibs if _NAME[s.name].search(ctx)}
    adjacent = {s.name for s in sibs if _NAME[s.name].search(lead)}
    adjacent |= {s.name for s in sibs for a in aliases(s.name)[1:]
                 if re.search(rf"\b{re.escape(a)}\b", lead)}
    return window | adjacent, adjacent


def alias_trail_owners(line: str, kind: str, n: int,
                       sibs: list[Path]) -> set[str]:
    """Repos whose SHORT alias sits just AFTER the citation — the population
    `qualifiers()` deliberately does not read, reported so the cost of that
    decision is re-measured rather than remembered.

    `_ALIAS_REACH` is a LEAD: aliases qualify only when they precede the number
    ("dapps Issue 27"). The full directory name is accepted from the whole
    3-line window (which includes the citation's own line, forward text and
    all), so only the short form is one-directional.

    Measured (Issue 753, 2026-09-12) over the 274-row CROSS set: **1** row has
    an owner's alias trailing within 40 chars, and reading it settles the
    question against widening — riir-game-sdk's ``chain_viz` (Plan 032, DeFi
    dashboard). The chain viz is` matches on `chain` in *prose about the
    crate*, not an attribution to riir-chain. So widening forward buys 0
    genuine repairs and SUPPRESSES 1 true finding (itself a crate-hint row,
    the class Issue 751 T2(a) ruled must be counted, not excused).

    That is the backward-only window's argument (Issue 752) on a second axis,
    and it lands the same way for the same reason: an emitted false positive is
    read and dismissed, a suppressed row is invisible to the sample that
    measures the error rate. Lead-only stays — MEASURED, not assumed."""
    m = re.search(rf"\b{kind}s?\s+0*{n}\b", line)
    if not m:
        return set()
    trail = line[m.end():m.end() + _ALIAS_REACH]
    return {s.name for s in sibs for a in aliases(s.name)[1:]
            if re.search(rf"\b{re.escape(a)}\b", trail)}


def is_qualified(named: set[str], owners: list[str]) -> bool:
    """A repo name qualifies a citation only if that repo OWNS the number.

    ⛔ The predicate used to be `named != {}` — "is a repo named?", never "does
    that repo own it?". Measured over the workspace (Issue 752): of 368
    qualified citations, **45 named no owner at all** — 37 where the 3-line
    window merely contained a sibling name (a crate-inventory table row, an
    adjacent unrelated clause) and 8 carrying an explicit attribution to a repo
    that does not have the number. `riir-chain Plan 211` where riir-chain's
    `.plans` tops out at 058; `katgpt-rs Issue 513` where 513 is riir-train's.
    Every one of the 45 read as CLEAN.

    ⛔ The census's own `riir-mmorpg-examples Issue 059` example was REFUTED by
    Issue 754 — that repo does own 059, in a heading no file walk could see.
    Owner-consistency is only as sound as `allocated()`, which is why the
    heading path exists and why its filters are measured, not assumed.

    This is Issue 751 T2(a)'s argument, applied to the path it was never
    applied to. Crate hints were counted as findings *because* a plausible
    address that is wrong is worse than no address — and the directory-name
    path, which silently absolves rather than merely annotating, was exempted
    from it with no measurement behind the exemption.

    Owner-consistency applies **exactly when the number has owners**. With no
    owner anywhere in the workspace there is nothing to be consistent with, the
    row is a dangling reference rather than a rebinding hazard, and any named
    repo is accepted — ORPHAN is a different repair and keeps its own bucket.
    """
    return bool(named & set(owners)) if owners else bool(named)


def citations(text: str) -> list[tuple[int, str, int, str]]:
    """(line, kind, number, lead-text) for every citation, list forms expanded."""
    lines = text.splitlines()
    out = []
    for i, line in enumerate(lines, 1):
        for m in _HEAD.finditer(line):
            kind = m.group(1)
            lead = line[max(0, m.start() - _ALIAS_REACH):m.start()]
            out.append((i, kind, int(m.group(3)), lead))
            if not m.group(2):  # singular "Issue 47" never heads a list
                continue
            pos = m.end()
            while (t := _TAIL.match(line, pos)):
                out.append((i, kind, int(t.group(1)), lead))
                pos = t.end()
    return out


def ci_deferred(pins: dict, docs: list, n_repos: int, posture: str = "CI") -> int:
    """The marked-deferred verdict: instrument ALIVE, cross-repo
    adjudication DEFERRED.

    Only the locally-decidable axes run here: the pinned documents exist, the
    `\\d{2,4}` width bound's complement is still empty, and the citation walk
    still clears its floor. The ownership half is impossible without the
    sibling workspace and is NOT guessed at — the verdict says so in its last
    line, which is the one docs_gate.sh forwards on a pass.

    `posture` names WHY the workspace is absent: "CI" (DOCS_GATE_CI=1, a
    single checkout) or "partial" (DOCS_GATE_PARTIAL_CLONE=1, a box with a
    subset of the canonical repos — Issue 765). Same instrument-alive
    verdict; a partial clone additionally CANNOT adjudicate citations naming
    its absent repos, so the full path would manufacture MISATTRIBUTED rows.
    """
    local = {k: allocated(REPO_ROOT, d) for k, d in KINDS.items()}
    scanned = local_hits = 0
    unseen_h = unseen_t = 0
    for doc in docs:
        p = REPO_ROOT / doc
        if not p.is_file():
            print(f"✗ INSTRUMENT: pinned document {doc} is missing — a gate cannot "
                  f"report clean over a file it never opened")
            return 2
        text = p.read_text(encoding="utf-8")
        h, t = unseen_by_width(text)
        unseen_h += h
        unseen_t += t
        for _ln, kind, n, _lead in citations(text):
            scanned += 1
            if n in local[kind]:
                local_hits += 1
    if (unseen_h + unseen_t) > pins["max_single_digit"]:
        print(f"✗ INSTRUMENT: {unseen_h + unseen_t} single-digit citation form(s) "
              f"now in scope, over the pinned {pins['max_single_digit']} — the "
              f"width bound cannot SEE them (same verdict as the workstation run)")
        return 2
    if scanned < pins["min_citations_scanned"]:
        print(f"✗ INSTRUMENT: scanned {scanned} citations < floor "
              f"{pins['min_citations_scanned']} — the citation regex went blind")
        return 2
    print(f"  {posture}: {scanned} citations scanned in {len(docs)} document(s); "
          f"{local_hits} resolve locally, {scanned - local_hits} cross-repo")
    label = ("CI scope (DOCS_GATE_CI=1)" if posture == "CI"
             else f"partial-clone scope ({PARTIAL_MARKER}=1)")
    print(f"✓ {label} — instrument alive over {n_repos} repo(s): "
          f"width bound clean, walk above floor; cross-repo adjudication DEFERRED "
          f"to the full-workspace docs_gate run — this line is not an adjudication")
    return 0


def main() -> int:
    pins = parse_pins(FLOORS)
    docs = pins["documents"]
    assert isinstance(docs, list)

    repos = contract_repos(WORKSPACE)
    sibs = [r for r in repos if r.resolve() != REPO_ROOT]
    # The partial-clone axis (Issue 765): a marked box with a SUBSET of the
    # canonical repos defers the cross-repo half exactly like CI — not only
    # below the floor, because a 15-of-20 box would run the full path and
    # manufacture MISATTRIBUTED rows for citations naming the 5 absent repos
    # (absent repos cannot own anything). The marker is explicit, never
    # auto-detected; a full box (walk == snapshot) ignores it entirely.
    _, absent, _ = partial_clone_state(sorted(r.name for r in repos))
    marker_partial = (os.environ.get(PARTIAL_MARKER) == "1"
                      and bool(absent) and len(repos) > 1)
    if len(repos) < pins["min_repos"] or marker_partial:
        if os.environ.get("DOCS_GATE_CI") == "1":
            return ci_deferred(pins, docs, len(repos))
        if marker_partial:
            return ci_deferred(pins, docs, len(repos), posture="partial")
        if len(repos) > 1:
            print(f"✗ INSTRUMENT: derived {len(repos)} contract repos < floor "
                  f"{pins['min_repos']} — the population went blind; every ceiling "
                  f"below would pass vacuously. Either this box is a PARTIAL "
                  f"CLONE (canonical repos simply not cloned here; the snapshot "
                  f"names {len(absent)} absent: {absent}) — export "
                  f"{PARTIAL_MARKER}=1 for the instrument-alive deferral, do "
                  f"NOT regenerate anything — or it is a full workstation and a "
                  f"sibling moved or went missing: fix the walk, do not mark "
                  f"the box.")
        else:
            print(f"✗ INSTRUMENT: derived {len(repos)} contract repos < floor "
                  f"{pins['min_repos']} — the population went blind; every ceiling "
                  f"below would pass vacuously. A single checkout cannot "
                  f"adjudicate cross-repo citations — the CI lane marks the "
                  f"context with DOCS_GATE_CI=1 for the deferred verdict; a "
                  f"workstation run must fix the walk instead.")
        return 2

    # An unterminated fence disarms the allocation path's fence filter (it fails
    # SAFE, excluding nothing), so the gate would still be correct — but it is a
    # real rendering bug and the filter's premise, so it REDS rather than being
    # noted. Scoped to the repos whose allocations this verdict rests on.
    stray = [(r.name, d, ln) for r in repos for d, ln in unterminated_fences(r)]
    if stray:
        for name, doc, ln in stray:
            print(f"✗ INSTRUMENT: {name}/{doc}:{ln} opens a fenced code block that is "
                  f"never closed — the tail of that file renders as code, and the "
                  f"allocation path's fence filter is disarmed over it")
        return 2

    local = {k: allocated(REPO_ROOT, d) for k, d in KINDS.items()}
    elsewhere = {k: {} for k in KINDS}
    for r in sibs:
        for k, d in KINDS.items():
            for n in allocated(r, d):
                elsewhere[k].setdefault(n, []).append(r.name)

    scanned = 0
    unseen_h = unseen_t = 0
    unqualified: list[str] = []
    ambiguous: set[tuple[str, int]] = set()
    for doc in docs:
        p = REPO_ROOT / doc
        if not p.is_file():
            print(f"✗ INSTRUMENT: pinned document {doc} is missing — a gate cannot "
                  f"report clean over a file it never opened")
            return 2
        text = p.read_text(encoding="utf-8")
        lines = text.splitlines()
        h, t = unseen_by_width(text)
        unseen_h += h
        unseen_t += t
        for ln, kind, n, lead in citations("\n".join(lines)):
            scanned += 1
            owners = elsewhere[kind].get(n, [])
            if n in local[kind]:
                if owners:
                    ambiguous.add((kind, n))
                continue
            # Cross-repo: a sibling repo name within the citation's own
            # paragraph-scale context (3 lines) is what OFFERS an address.
            # THREE lines, and the window size is a MEASURED trade-off, not a
            # guess. This prose hard-wraps at 80 columns, so a single sentence
            # routinely spans 2-3 lines ("Downstream: riir-ai\nIssue 912 T4's"
            # is one attribution split by a line break). Tightening to
            # same-line-only was measured at **4 false positives**, all of that
            # shape. The cost of the wider window is the opposite error: an
            # unrelated repo name that happens to sit within 3 lines is offered
            # as an address for a citation that names nothing — a
            # `riir-train/data/*.gguf` path two lines up in a model list does
            # it. Both directions are real; 3 lines is where the errors were
            # fewest. What makes the OFFER an ANSWER is `is_qualified` —
            # the named repo has to own the number (Issue 752).
            named, adj = qualifiers(lines, ln, lead, sibs)
            if is_qualified(named, owners):
                continue
            where = "/".join(owners) if owners else "NO REPO IN THE WORKSPACE"
            why = "names no repo"
            bad = adj - set(owners)
            if bad:
                why = (f"⛔MISATTRIBUTED — names {'/'.join(sorted(bad))}, "
                       f"which does NOT own {n}")
            elif named:
                why = (f"the only repo in its window is "
                       f"{'/'.join(sorted(named))}, which does NOT own {n}")
            unqualified.append(f"  {doc}:{ln}  {kind} {n} — lives in {where}, "
                               f"{why}\n      {lines[ln - 1].strip()[:120]}")

    if (unseen_h + unseen_t) > pins["max_single_digit"]:
        print(f"✗ INSTRUMENT: {unseen_h + unseen_t} single-digit citation form(s) "
              f"({unseen_h} head, {unseen_t} list-tail) now in scope, over the pinned "
              f"{pins['max_single_digit']} — the `\\d{{2,4}}` width bound cannot SEE them, "
              f"so a clean verdict no longer covers the scope. Adjudicate the rows: they "
              f"are citations (qualify them, and widen the bound with the 51-false-head "
              f"cost re-measured) or section numbering (leave both alone).")
        return 2

    if scanned < pins["min_citations_scanned"]:
        print(f"✗ INSTRUMENT: scanned {scanned} citations < floor {pins['min_citations_scanned']} — "
              f"the citation regex went blind, not the prose clean")
        return 2

    print(f"  scanned {scanned} citations in {len(docs)} document(s) over "
          f"{len(repos)} contract repos ({len(sibs)} siblings)")
    # REPORTED, never gated — see the module docstring. This is the size of
    # what the gate cannot decide, printed next to the verdict so a green is
    # never mistaken for a green over everything.
    print(f"  AMBIGUOUS (local AND sibling — undecidable by number, NOT a pass): {len(ambiguous)}")
    # The width bound's own complement, re-counted rather than remembered: a
    # blind spot recorded as empty ONCE is a claim about a corpus five-plus
    # sessions edit daily (Issue 753).
    print(f"  width bound `\\d{{2,4}}`: {unseen_h + unseen_t} single-digit form(s) "
          f"in scope (pinned max {pins['max_single_digit']}) — NOT scanned, by design")

    if unqualified:
        print(f"✗ issue citation gate FAILED — {len(unqualified)} unqualified cross-repo citation(s)")
        for row in unqualified:
            print(row)
        print("  Fix: name the owning repo in the prose — `riir-ai Issue 750`, "
              "`riir-train Issue 513`. The number alone is not an address.")
        if absent:
            # Reached only on the FULL path (a marked partial clone deferred
            # above) — but the walk can still be short of the canonical set on
            # an UNMARKED box above the floor. Those rows are then suspect,
            # and the box, not the prose, is the likely cause.
            print(f"  note: {len(absent)} canonical repo(s) absent on this box "
                  f"({', '.join(absent)}) — citations naming them CANNOT be "
                  f"adjudicated here; if this is a partial clone, export "
                  f"{PARTIAL_MARKER}=1 and re-run for the deferral verdict")
        return 1

    print(f"✓ issue citation gate PASSED — every cross-repo citation names its repo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
