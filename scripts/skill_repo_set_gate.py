#!/usr/bin/env python3
"""Gate: a SKILL.md command block must not type the repo set out by hand.

Issue 703. An instrument that needs "all the repos" writes the list into a
command. Repos gain contracts; the list does not. The instrument then keeps
reporting clean over a set that no longer matches the workspace — and a clean
result over a partial set is indistinguishable from a clean result over the
whole one. Four instruments had drifted this way before anybody looked.

WHAT IS CHECKED, and why it is this and not the obvious thing.

The obvious check — grep every skill for an "N repos" claim and compare it
against the derived count — false-positives on history. `doc-sync` and
`boundary-guard` keep run-log tables whose rows correctly say "all 7 repos"
about a run that did cover 7. Rewriting those would destroy the record, and a
gate that cries wolf on an accurate historical row is one somebody loosens.

So this greps for the MECHANICAL DEFECT instead: inside a fenced block, two or
more repos used as PATH components (`riir-ai/…`, `/Users/katopz/git/riir-chain/…`)
or a brace list (`git/{a,b}`). Prose naming a repo does not match, because prose
does not put a slash after it — which is exactly what keeps the corrected
substrate-first block (whose comment names `riir-armageddon` and `riir-dapps`
while its command derives the set) from firing.

WHAT IS NOT CHECKED — say it out loud rather than let a green read as total.
A fenced SCOPE TABLE that lists repo names without paths (`goat-audit` §Scope,
`feature-gate-audit` §Scope) is the same defect and is invisible here. Those are
prose-shaped; catching them is the false-positive-prone case Issue 703
deliberately declined. They need a human read.

ESCAPE HATCH. A block that is genuinely about specific repos marks itself:

    <!-- repo-set-ok: <reason> -->

on any line inside the block, or on the line immediately before its opening
fence. The marker is required to carry a reason so the next reader can judge it.

    scripts/skill_repo_set_gate.py

Exit 0 = every multi-repo command block derives its set or is marked.
Exit 1 = a hand-typed repo set, or the gate could not see any skills at all.

THE PARTIAL-CLONE AXIS (Issue 765). A box carrying a SUBSET of the
workspace (the 4090: 14 of 20 repos) disagrees with the snapshot in the
gone-only direction, and the snapshot audit cannot run there. The
deferral is an explicit marker — DOCS_GATE_PARTIAL_CLONE=1, the
DOCS_GATE_CI idiom, NEVER auto-detected — because a genuine removal
whose repo_set.txt update was forgotten is set-identical to a partial
clone from the walk alone, and an inferred green would ship the stale
file. Unmarked, the gone-only shape reds naming BOTH hypotheses,
including the warning that regenerating the snapshot on a partial box
deletes live repos from the canonical set.
"""

from __future__ import annotations

import re
import sys
import os
from pathlib import Path

# The workspace root = this repo's parent, so the gate works both on the
# workstation (all 18 contract repos side by side) and in CI (a lone checkout).
# Overridable for testing. NOT hard-coded to /Users/katopz/git — a gate against
# hand-typed paths that hand-types its own path would be the joke it polices.
GIT_ROOT = Path(os.environ.get("WORKSPACE_ROOT",
                               Path(__file__).resolve().parents[2]))
SELF_REPO = Path(__file__).resolve().parents[1].name
# The detector's VOCABULARY (which names are repos) is separate from the
# POPULATION (which SKILL.md files exist). On the workstation both are derived.
# In CI only this checkout exists, so a derived vocabulary would be one name and
# the gate could never see `riir-ai/src riir-chain/src` — a green that means
# nothing, which is the exact defect this gate exists to catch, committed by the
# gate. So the vocabulary is a committed SNAPSHOT, and every workstation run
# re-derives the truth and FAILS if the snapshot disagrees. CI consumes it;
# the workstation keeps it honest.
SNAPSHOT = Path(__file__).resolve().parent / "repo_set.txt"
MARKER_RE = re.compile(r"repo-set-ok:\s*(\S.*?)\s*(?:-->|$)")

# ── the partial-clone axis (Issue 765) ──────────────────────────────────────
# Shared by population_sync_gate.py and issue_citation_gate.py (both already
# import from this module — the fence scanner / derive_repos precedent).
PARTIAL_MARKER = "DOCS_GATE_PARTIAL_CLONE"


def partial_clone_state(derived: list[str]) -> tuple[bool, list[str], list[str]]:
    """(marker_on, absent, unregistered) vs the committed snapshot.

    absent        in the snapshot, not on this box — the partial-clone shape
                  only when `unregistered` is empty.
    unregistered  on this box, missing from the snapshot — genuine staleness
                  in EVERY posture; never deferred, marker or not.
    """
    marker_on = os.environ.get(PARTIAL_MARKER) == "1"
    if not SNAPSHOT.is_file():
        return marker_on, [], []
    snap = [l.strip() for l in SNAPSHOT.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")]
    return marker_on, sorted(set(snap) - set(derived)), sorted(set(derived) - set(snap))


def derive_repos(root: Path) -> list[str]:
    """The contract repo set, derived. Never typed.

    `(d / ".git").is_dir()`, not `.exists()`: a `git worktree` has a `.git`
    FILE, and counting one duplicates every hit of the repo it shadows.
    """
    return sorted(
        d.name for d in root.iterdir()
        if d.is_dir() and (d / "BOUNDARY.md").is_file() and (d / ".git").is_dir()
    )


def fence_run(line: str) -> tuple[str, int]:
    """(fence character, run length); ("", 0) if the line is not a code fence.

    A CommonMark code fence is three-or-more BACKTICKS **or** three-or-more
    TILDES, and the two families do not interoperate: a ``` run cannot close a
    ~~~ block and a ~~~ run cannot close a ``` one. This returned a bare
    backtick count until Issue 789, which made every tilde fence invisible —
    silent in the direction that matters (a tilde-fenced block is never
    scanned, and a tilde-fenced UNTERMINATED block is invisible to the gate
    written for exactly that class) and loud at the wrong address in the other
    (an odd number of ``` lines inside a ~~~ block yielded a phantom
    unterminated fence on the inner line). 0 live instances over 5116 tracked
    `.md` across 16 repos when it was fixed; the arms are in `selftest`.

    `lstrip()` — any indentation — is DELIBERATE leniency over CommonMark's
    3-space limit, not an oversight: 74 fence lines in this repo alone are
    list-nested at 4+ columns, where the limit is relative to the list marker
    and not to column 0. Tightening it to 3 would red every one of them.
    """
    s = line.lstrip()
    for ch in ("`", "~"):
        if s.startswith(ch * 3):
            return ch, len(s) - len(s.lstrip(ch))
    return "", 0


def fenced_blocks(text: str):
    """(start_line, end_line, body_lines, preceding_line) per fenced block.

    NOT a naive toggle on every ``` line. A toggle silently MIS-PHASES on a
    file with an unterminated fence: from that point on it scans the complement
    — prose read as code, code read as prose — and reports clean either way.
    `rust-optimize/SKILL.md` had exactly that (an unclosed ```text at line 511),
    and it swallowed this gate's own first canary, which is how the bug was
    found. So: a closer must be a BARE run, of the SAME fence family and at
    least the opener's length, per CommonMark, and an unterminated fence is
    surfaced (see `scan`) rather than dropped.

    Three gates read this one function under Issue 755's DRY call — "a second
    copy of a rule this subtle is a second thing to get wrong" — so the canary
    that guards it is not optional. `selftest` is it, and Issue 789 is what
    happens without one: the replacement for the canary this parser's own bug
    destroyed was never written, and the tilde blindness above sat here from
    the day it was first written.
    """
    lines = text.splitlines()
    start = None
    open_ch, open_run = "", 0
    buf: list[str] = []
    for i, ln in enumerate(lines, 1):
        ch, run = fence_run(ln)
        if start is None:
            if run:
                start, open_ch, open_run, buf = i, ch, run, []
            continue
        # inside: only a bare fence of the SAME family and >= the opening run
        # closes it. ⚠ `ch == open_ch` is REDUNDANT today and the canary is how
        # that is known: perturbing it away alone reds **zero** arms, because
        # `.strip(open_ch)` already discriminates the family (a ``` line inside
        # a ~~~ block survives `strip("~")` non-empty, so it is not bare). It
        # stays because the two are independent CommonMark requirements and
        # each becomes load-bearing the moment the other is loosened — but the
        # first version of this comment claimed it was load-bearing NOW, which
        # the perturbation refuted. A line a canary cannot red is not doing the
        # work you think it is.
        if ch == open_ch and run >= open_run and not ln.strip().strip(open_ch):
            yield start, i, buf, (lines[start - 2] if start >= 2 else "")
            start = None
            continue
        buf.append(ln)
    if start is not None:
        yield start, -len(lines), buf, (lines[start - 2] if start >= 2 else "")


def load_vocabulary(derived: list[str]) -> tuple[list[str], str | None, str | None]:
    """(repo names to match on, error, partial-deferral note).

    Snapshot is truth in CI, audited on a full workstation, and used
    UNVERIFIED on a marked partial clone (Issue 765) — the deferral never
    fires from the walk alone, so a forgotten removal still reds.
    """
    if not SNAPSHOT.is_file():
        return [], (f"{SNAPSHOT.name} is missing — the gate has no repo "
                    f"vocabulary. Regenerate on the workstation."), None
    snap = [l.strip() for l in SNAPSHOT.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")]
    if len(derived) > 1 and sorted(snap) != sorted(derived):
        missing = sorted(set(derived) - set(snap))
        gone = sorted(set(snap) - set(derived))
        if missing:
            # A repo the snapshot does not know: genuine staleness in every
            # posture — including a marked partial clone.
            return [], (f"{SNAPSHOT.name} is stale vs the live workspace — "
                        f"missing {missing} — regenerate it (see the "
                        f"docstring) and commit."), None
        # Gone-only: the Issue-765 shape. The snapshot names repos this box
        # does not have; whether that is a partial clone or a stale snapshot
        # is not decidable from the walk — the marker says which, and the
        # remedy must never invite regeneration on a partial box.
        if os.environ.get(PARTIAL_MARKER) == "1":
            note = (f"partial clone ({PARTIAL_MARKER}=1): {len(gone)} snapshot "
                    f"repo(s) absent on this box — snapshot audit DEFERRED to "
                    f"a full-workstation run")
            return snap, None, note
        return [], (f"{SNAPSHOT.name} names {len(gone)} repo(s) absent from "
                    f"this box — {gone}. Either this is a PARTIAL CLONE "
                    f"(export {PARTIAL_MARKER}=1 to defer the population axis "
                    f"loudly; do NOT regenerate the snapshot on a partial box — "
                    f"that deletes live repos from the canonical set), or a "
                    f"full workstation whose snapshot is stale (regenerate per "
                    f"the docstring and commit)."), None
    return snap, None, None


def scan(path: Path, repos: list[str]) -> list[tuple[int, int, set[str], bool]]:
    alt = "|".join(map(re.escape, repos))
    # A repo used as a path component. The leading lookbehind stops
    # `seal-online-remaster-unity/` from matching a shorter repo name, and
    # stops `.../katgpt-rs/crates/riir-ai/` style nesting from double-counting.
    prefix = r"(?:\.\./|" + re.escape(str(GIT_ROOT)) + r"/)?"
    path_re = re.compile(r"(?<![\w./-])" + prefix + r"(" + alt + r")/")
    brace_re = re.compile(r"/\{([^}]*)\}")
    repo_set = set(repos)
    out = []
    for start, end, body, prev in fenced_blocks(path.read_text(encoding="utf-8")):
        if MARKER_RE.search(prev) or any(MARKER_RE.search(l) for l in body):
            continue
        names: set[str] = set()
        brace = False
        for line in body:
            names |= set(path_re.findall(line))
            for inner in brace_re.findall(line):
                parts = {p.strip() for p in inner.split(",")} & repo_set
                if len(parts) >= 2:
                    brace = True
                    names |= parts
        if end < 0:
            # Unterminated: the gate could not tell where this block ends, so a
            # clean verdict over it is not a verdict. Report, never swallow.
            out.append((start, end, names, brace))
        elif len(names) >= 2 or brace:
            out.append((start, end, names, brace))
    return out


def selftest() -> list[str]:
    """Known-answer arms over the parser AND the detector. Returns failures.

    Issue 789. Three gates (`markdown_fence_gate`, `issue_citation_gate`, this
    one) read `fenced_blocks`, and 2,050 lines of per-push CHECKS logic had no
    validation arm at all. The parser half is not the whole arm on purpose: an
    arm that covers only the imported helper would mark this gate "validated"
    while `scan`'s own verdict arithmetic stayed unasserted, which is the
    over-crediting failure Issue 789's first census committed.

    Cheap by construction — pure string work plus three temp files — so it runs
    UNCONDITIONALLY at the top of `main()` rather than behind a flag. An
    assertion nobody invokes is decoration (`docs_gate.sh`, line 18).
    """
    import tempfile

    fails: list[str] = []

    def eq(label: str, got, want):
        if got != want:
            fails.append(f"    {label}: got {got!r}, want {want!r}")

    # ── the parser: both fence families, per CommonMark ──────────────────
    def spans(*lines):
        return [(a, b) for a, b, _body, _prev in fenced_blocks("\n".join(lines))]

    eq("backtick block", spans("```", "x", "```"), [(1, 3)])
    eq("backtick unterminated", spans("```", "x"), [(1, -2)])
    eq("info string opener", spans("```rust", "x", "```"), [(1, 3)])
    # A closer may not carry an info string (CommonMark); the second ```rust
    # is body, and the block runs to the bare fence on line 5.
    eq("closer with info is not a closer",
       spans("```", "x", "```rust", "y", "```"), [(1, 5)])
    eq("longer closer closes", spans("```", "x", "`````"), [(1, 3)])
    eq("shorter run cannot close a 4-run opener",
       spans("````", "```", "````"), [(1, 3)])
    eq("indented closer closes (deliberate leniency)",
       spans("```", "x", "      ```"), [(1, 3)])
    eq("two sequential blocks",
       spans("```", "a", "```", "p", "```", "b", "```"), [(1, 3), (5, 7)])
    # The Issue 789 arms. Before the fix: arm 1 reported [] and arm 2 reported
    # [(2, -3)] — a phantom unterminated fence on a line that is body.
    eq("tilde block", spans("~~~", "x", "~~~"), [(1, 3)])
    eq("tilde block holding a backtick line",
       spans("~~~", "```", "~~~"), [(1, 3)])
    eq("backtick block holding a tilde line",
       spans("```", "~~~", "```"), [(1, 3)])
    eq("tilde unterminated is surfaced", spans("~~~", "x"), [(1, -2)])
    eq("tilde run shorter than opener cannot close",
       spans("~~~~", "~~~", "~~~~"), [(1, 3)])

    body_arms = list(fenced_blocks("lead\n```\na\nb\n```"))
    eq("body lines", [b[2] for b in body_arms], [["a", "b"]])
    eq("preceding line", [b[3] for b in body_arms], ["lead"])
    eq("preceding line at file start", [b[3] for b in fenced_blocks("```\na\n```")], [""])

    # ── the detector: scan()'s own verdict arithmetic ─────────────────────
    vocab = ["katgpt-rs", "riir-ai", "riir-chain", "seal-online-remaster"]

    def scanned(*lines):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "SKILL.md"
            p.write_text("\n".join(lines), encoding="utf-8")
            return [(s, e, sorted(n), b) for s, e, n, b in scan(p, vocab)]

    eq("path enumeration of two repos is a finding",
       scanned("```", "cd riir-ai/src && cd riir-chain/src", "```"),
       [(1, 3, ["riir-ai", "riir-chain"], False)])
    eq("one repo is not a finding",
       scanned("```", "cd riir-ai/src", "```"), [])
    eq("prose naming two repos is not a finding (no slash)",
       scanned("```", "covers riir-ai and riir-chain", "```"), [])
    eq("brace list of two repos is a finding",
       scanned("```", "cd git/{riir-ai,riir-chain}", "```"),
       [(1, 3, ["riir-ai", "riir-chain"], True)])
    # The threshold, in the direction that matters: a brace list is a finding
    # because it enumerates MULTIPLE repos. `git/{riir-ai,target}` names one,
    # and a widened `>= 1` would red every ordinary path brace in the
    # workspace's skills. Perturbing 2 -> 1 red zero arms until this one.
    eq("a brace list naming one repo is not a finding",
       scanned("```", "cd git/{riir-ai,target}", "```"), [])
    eq("marker inside the block exempts it",
       scanned("```", "<!-- repo-set-ok: both by design -->",
               "cd riir-ai/src && cd riir-chain/src", "```"), [])
    eq("marker on the line before the fence exempts it",
       scanned("<!-- repo-set-ok: both by design -->", "```",
               "cd riir-ai/src && cd riir-chain/src", "```"), [])
    # A LONGER directory name must not match the shorter repo, which would
    # leave this block at two names and red it. ⚠ This arm is INERT against
    # `(?<![\w./-])` and says so: it tests the name's RIGHT side, where the
    # trailing `/` in the pattern already does the work. The lookbehind guards
    # the LEFT side — the arm below is the one that discriminates it.
    eq("a longer name does not match a shorter repo",
       scanned("```", "cd seal-online-remaster-unity/a && cd riir-ai/b", "```"), [])
    # The lookbehind proper: a repo NESTED inside another repo's path is one
    # path, not two repos. Without it this reads as a two-repo enumeration and
    # reds every skill that cites a crate by its in-repo path.
    eq("a nested repo path does not double-count",
       scanned("```", "cd katgpt-rs/crates/riir-ai/src", "```"), [])
    # An unterminated block is surfaced whatever it names: the gate could not
    # tell where it ends, so a clean verdict over it is not a verdict.
    eq("unterminated fence is surfaced with no names",
       scanned("```", "nothing interesting here"), [(1, -2, [], False)])
    # The regression arm that ties the two halves together.
    eq("tilde-fenced path enumeration is a finding",
       scanned("~~~", "cd riir-ai/src && cd riir-chain/src", "~~~"),
       [(1, 3, ["riir-ai", "riir-chain"], False)])

    # ── the partial-clone axis: a deferral bug greens everything ──────────
    global SNAPSHOT
    _real_snap, _real_env = SNAPSHOT, os.environ.get(PARTIAL_MARKER)
    try:
        with tempfile.TemporaryDirectory() as td:
            SNAPSHOT = Path(td) / "repo_set.txt"
            SNAPSHOT.write_text("katgpt-rs\nriir-ai\nriir-chain\n", encoding="utf-8")

            os.environ.pop(PARTIAL_MARKER, None)
            eq("snapshot matches the walk",
               partial_clone_state(["katgpt-rs", "riir-ai", "riir-chain"]),
               (False, [], []))
            eq("a repo the snapshot does not know is UNREGISTERED, unmarked",
               partial_clone_state(["katgpt-rs", "riir-ai", "riir-chain", "riir-dao"]),
               (False, [], ["riir-dao"]))
            eq("gone-only without the marker is not deferred",
               partial_clone_state(["katgpt-rs", "riir-ai"]),
               (False, ["riir-chain"], []))
            eq("unmarked gone-only reds",
               load_vocabulary(["katgpt-rs", "riir-ai"])[0], [])

            os.environ[PARTIAL_MARKER] = "1"
            eq("gone-only WITH the marker still reports the absence",
               partial_clone_state(["katgpt-rs", "riir-ai"]),
               (True, ["riir-chain"], []))
            vocab_p, err_p, note_p = load_vocabulary(["katgpt-rs", "riir-ai"])
            eq("a marked partial clone DEFERS on the snapshot axis",
               (sorted(vocab_p), err_p, bool(note_p)),
               (["katgpt-rs", "riir-ai", "riir-chain"], None, True))
            # UNREGISTERED is never deferred: a repo on disk the snapshot does
            # not know is genuine staleness in EVERY posture, marker or not.
            eq("the marker does not excuse an UNREGISTERED repo",
               load_vocabulary(["katgpt-rs", "riir-ai", "riir-chain", "riir-dao"])[0],
               [])
    finally:
        SNAPSHOT = _real_snap
        if _real_env is None:
            os.environ.pop(PARTIAL_MARKER, None)
        else:
            os.environ[PARTIAL_MARKER] = _real_env

    return fails


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
    # The canary runs BEFORE any verdict is read. A mis-phasing fence parser or
    # a widened detector reports a confident green, so a failure here is not a
    # finding — it means no verdict is possible (exit 2, the house convention).
    arm_failures = selftest()
    if arm_failures:
        print("✗ INSTRUMENT: skill_repo_set_gate's own selftest does not pass, so "
              "every verdict below would be unreadable:")
        for f in arm_failures:
            print(f)
        return 2
    if not GIT_ROOT.is_dir():
        print(f"✗ {GIT_ROOT} is not a directory — cannot derive the repo set")
        return 1
    repos = derive_repos(GIT_ROOT)
    skills = sorted(
        p for r in repos for p in (GIT_ROOT / r / ".agents/skills").glob("*/SKILL.md")
    )
    # Liveness. A run that examined nothing must not read like a clean one,
    # and one that examined a SUBSET must say which subset (Issue 703 is
    # precisely the failure of instruments that do not).
    if SELF_REPO not in repos:
        print(f"✗ {SELF_REPO!r} is not in the derived set under {GIT_ROOT} — "
              f"the gate is not looking at the tree it lives in")
        return 1
    if not skills:
        print(f"✗ gate examined 0 SKILL.md across {len(repos)} repo(s); "
              f"refusing to report a pass")
        return 1
    covered = sorted({p.parents[3].name for p in skills})
    # Computed early: a partial-clone deferral (Issue 765) changes what the
    # scope line may claim — "full workspace" over 14 of 20 would be the
    # partial-set-as-whole-one defect this gate exists to catch.
    vocab, err, partial = load_vocabulary(repos)
    if partial:
        scope = (f"partial clone — {len(repos)} of {len(vocab)} canonical "
                 f"repos present, snapshot audit DEFERRED")
    else:
        # On the workstation all contract repos are present; in CI only this
        # checkout is. Both are legitimate — reporting WHICH is the point.
        scope = "full workspace" if len(repos) > 1 else f"{SELF_REPO} only (CI)"
    print(f"▸ {len(repos)} contract repo(s) under {GIT_ROOT} — {scope}")
    print(f"▸ {len(skills)} SKILL.md in {len(covered)}: {', '.join(covered)}")

    if err:
        print(f"✗ {err}")
        return 1
    if partial:
        src = " (snapshot — partial-clone deferral: NOT verified on this box)"
    elif len(repos) > 1:
        src = " (re-derived and verified against the live workspace)"
    else:
        src = " (snapshot — no siblings to verify against)"
    print(f"▸ vocabulary: {len(vocab)} repo names from {SNAPSHOT.name}{src}")

    findings = [(p, f) for p in skills for f in scan(p, vocab)]
    if not findings:
        print("  note: fenced SCOPE TABLES (repo names without paths) are out "
              "of scope by design — see this file's docstring")
        # The population goes in the LAST line on purpose: docs_gate.sh prints
        # only `tail -1` of a passing check, so a verdict that does not carry
        # its own scope reaches CI as a bare "clean" — a partial run wearing a
        # whole one's clothes, which is the entire defect being gated.
        print(f"✓ no hand-typed repo set — {len(skills)} SKILL.md across "
              f"{len(covered)} repo(s) [{scope}], vs {len(vocab)} repo names")
        return 0

    for path, (start, end, names, brace) in findings:
        rel = path.relative_to(GIT_ROOT)
        if end < 0:
            print(f"  ✗ {rel}:{start} — fence opened and never closed "
                  f"(runs to EOF, line {-end}). The block cannot be scanned, "
                  f"and an unterminated fence mis-renders every line after it.")
            continue
        kind = "brace list" if brace else "path enumeration"
        print(f"  ✗ {rel}:{start}-{end} — {kind} names {len(names)} of "
              f"{len(vocab)} repos: {', '.join(sorted(names))}")
    print(f"✗ {len(findings)} block(s) failed. Derive the repo set instead of "
          "typing it, or mark the block `<!-- repo-set-ok: <reason> -->`.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
