#!/usr/bin/env python3
"""The pipefail measurement-discard class — an assignment whose command-
substitution pipeline can return non-zero, killing an errexit script BEFORE
its own output is written.

    set -euo pipefail
    names="$(grep -E 'pid=' "$cl" 2>/dev/null | head -3 | sed -E '...' \
        | paste -sd ';' -)"

`grep` exits 1 when it matches NOTHING; with pipefail ON that propagates,
the assignment fails, errexit kills the script — even though every LATER
pipeline member succeeded. Measured damage: riir-ai/scripts/perf_rematch.sh
lost five benchmark cells this way — both arms had RUN, the result JSON was
never written (repaired at riir-ai 512b74939, 2026-09-07, `|| true` at the
substitution tail). A second live instance stood in riir-chain
cloudflare/edge-wallet-container/teardown.sh:24, where the kill made the
script's own "already gone" re-run branch unreachable.

Provenance: riir-clippy mining-queue intake P14 item (j), 2026-09-07 entry.

A REPORT, not a gate (exit 0 on every real scan) — the class spans repos
whose owners have not taken the intake, and the classifier has honest blind
spots (Divergences). The verdict half is `pipefail_discard_drift_sweep.py`
(workstation: per-repo floors + expected rows pinned by membership).

# The bash law, per site

  (a) LINE-LEVEL NEUTRALIZER — a trailing `|| cmd` (or `&& cmd`) at top
      level AFTER the closing paren owns the list status: errexit exempts
      every command of a &&/|| list except the one following the FINAL
      operator. `x="$(grep no f)" || true` is GUARDED.
  (b) SUBSTITUTION-TAIL NEUTRALIZER — `x="$(pipeline || true)"`: the
      substitution's status is the status of its LAST command, so a later
      `||` segment owns it. GUARDED.
  (c) CONDITION POSITION — `if x="$(cmd)"; then`: errexit is suppressed in
      if/elif/while/until conditions. COND-POS, never a finding.
  (d) local/declare PREFIX — `local x="$(false)"` returns 0 (local masks
      the assignment status). Never a finding; counted as the INFO class
      LOCAL-MASKED (silent-empty hazard), listed, never gated. export/
      readonly do NOT mask — they kill.
  (e) EMPTY-CAPABLE MEMBER SET (v1 scope): grep, egrep, fgrep, rg,
      ripgrep — exit 1 on no-match. `git grep` counts. Other members out
      of scope v1.
  (f) STATUS LAW — an assignment's status is that of the LAST command
      substitution in its RHS, and within it of the LAST pipeline, and
      within that of the LAST member when pipefail is OFF. So: pipefail
      ON, any empty-capable member of the last pipeline kills
      (PIPEFAIL-KILL); pipefail OFF, only when it is the LAST member
      (TAIL-KILL — with `| head -1` after it, head's 0 owns the status);
      an empty-capable member in an EARLIER segment/pipeline never kills
      (GUARDED); only the LAST `$()` in the RHS decides
      (`x="$(grep a f)$(echo ok)"` is CLEAN).
      ⚠ the mirror trap: a LEADING `word &&` does NOT guard the list-final
      assignment — `cmd && x="$(grep no f)"` FINDS (x is the command
      following the final &&, the one errexit does NOT exempt). Modelled
      for a single command word before the operator; see Divergence (2).

# Verdicts

FINDING (PIPEFAIL-KILL | TAIL-KILL) — under errexit at the site, the last
substitution's last pipeline is empty-capable, no neutralizer. GUARDED —
an empty-capable member is present but its failure cannot propagate
(trailing ||/&&, || true tail, earlier segment, mid-pipeline under
pipefail-off, backgrounded `&`). COND-POS — condition position. INERT — no
errexit at the site. CLEAN — nothing empty-capable. LOCAL-MASKED — the (d)
info class. UNPARSED (file level) — EOF inside an unterminated `$(` or an
unclosed quote, or a heredoc never terminated; its own bucket, never
folded into clean or findings (the trap audit's UNPARSED law).

# Divergences (documented v1 scope)

  (1) ERREXIT IS FILE-FLAT: state comes from `set` lines in file order,
      and functions INHERIT the state at their DEFINITION site, not their
      call time. A `set -e` inside a function, or errexit inherited from
      an `#!/usr/bin/env -S bash -e` shebang, is unmodelled (hides).
  (2) Only assignments near the START of a logical line are sites: a
      single `word &&` / `word ||` prefix is consumed (so the mirror law
      above is testable), but `[[ -f x ]] && v="$(grep no f)"`,
      `grep -q x f && v="$(grep no g)"`, `a=1 b="$(grep x f)"`,
      `arr+=("$(grep x)")` and `a[i]="$(grep x)"` are all missed (hides).
  (3) The empty-capable test is word-based over non-dash tokens, not a
      command-position parse: `echo grep` or awk `sub(/grep/,...)` can
      over-claim. Direction: more findings, adjudicated by the sweep's
      membership pins (every row prints verbatim).
  (4) A `<<` inside an OPEN substitution is not queued (the body reads as
      substitution text); case-in-substitution (`$(case x in a) ...esac)`)
      breaks span matching at the pattern `)`. Both are rare; the walker
      raises UNPARSED rather than guess where it cannot recover.
  (5) Backtick substitutions are out of scope v1 (hides).
  (6) `x="$(grep a f) &"` (backgrounded) is GUARDED by the async check.

# Validation

`selftest()` pins 25 fixtures in BOTH directions and runs on EVERY
invocation (exit 2 on any miss — a classifier that cannot classify must not
be read as `0 findings`). `--self-test` runs ONLY the self-test.

First measured run (2026-09-15, ALL 20 contract repos): **194 tracked .sh ·
137 under errexit · 1359 sites · 53 FINDING (all PIPEFAIL-KILL) · 162
GUARDED · 0 COND-POS · 31 INERT · 1102 CLEAN · 11 LOCAL-MASKED · 0
UNPARSED.** That run's own reds caught two walker bugs before any number
was believed: line-leading `#` comments were never detected (the boundary
check omitted the NEWLINE that precedes a line-start `#` — prose
backticks in comment headers opened phantom quote frames and ~80 files
read UNPARSED), and the trailing-`&&` guard sliced at the substitution's
close, INSIDE a dangling close-quote for double-quoted sites (the guard
now walks the whole line filtered by position). One bash-law call was
MEASURED, not reasoned: `(grep x f || true) | head -1 | cut` SURVIVES
`set -euo pipefail`, so a paren-group member is judged by its interior's
last segment — six riir-dapps setup.sh rows flipped FINDING→GUARDED on
that fix. The 53 findings are membership-pinned in
`pipefail_discard_expected.txt` (4 deliberate proof_gate tripwires + 49
live kill-shapes, 21 in riir-ai's ci_feature_guard layer-summary block);
the sweep's `--prove-fires` reproduces the founding specimen at riir-ai
512b74939~1 (1 finding) vs 512b74939 (0).
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from bisect import bisect_right
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from skill_repo_set_gate import derive_repos  # noqa: E402
from tracked_walk import tracked_files  # noqa: E402

# Issue 804: this instrument is documented as directly invokable, and its
# verdict glyphs (✓ ✗ ⛔ ⚠) kill it on a non-UTF-8 console — no verdict at
# all, findings unread. docs_gate.sh's PYTHONIOENCODING only covers runs
# that go through the wrapper.
import console_safe  # noqa: E402

console_safe.apply()

# ── verdicts ────────────────────────────────────────────────────────────────
FINDING = "FINDING"
GUARDED = "GUARDED"
COND_POS = "COND-POS"
INERT = "INERT"
CLEAN = "CLEAN"
LOCAL_MASKED = "LOCAL-MASKED"
PIPEFAIL_KILL = "PIPEFAIL-KILL"
TAIL_KILL = "TAIL-KILL"

EMPTY_CAPABLE = re.compile(r"\b(grep|egrep|fgrep|rg|ripgrep)\b")
COND_WORDS = {"if", "elif", "while", "until"}
MASKING_KWS = {"local", "declare"}
SEG_SEPS = (";", "&&", "||", "&", "\n")

# Loose WORKSPACE-WIDE blindness floors (the sweep owns the per-repo ones).
FLOOR_FILES = 20
FLOOR_SITES = 10

ASSIGN = re.compile(
    r"^\s*(?:(?P<cond>if|elif|while|until)\s+)?"
    r"(?:[A-Za-z_][A-Za-z0-9_]*\s*(?:&&|\|\|)\s*)*"
    r"(?:(?P<kw>local|declare|export|readonly)\b(?:\s+-{1,2}[\w-]+)*\s+)?"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)=(?P<rhs>.*)$", re.S)
SET_LINE = re.compile(r"^\s*set\s+(.+?)\s*$")
HEREDOC_TAG = re.compile(r"<<(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")


class Unparsed(Exception):
    """EOF inside an unterminated `$(`, inside an unclosed quote, or with
    a heredoc never terminated."""


@dataclass
class Site:
    line: int          # 1-based physical line where the assignment starts
    klass: str
    sub: str = ""      # PIPEFAIL-KILL / TAIL-KILL for findings
    text: str = ""     # whitespace-collapsed source (the expected-file identity)


@dataclass
class FileScan:
    sites: list = field(default_factory=list)
    guarded: int = 0
    cond: int = 0
    inert: int = 0
    clean: int = 0
    unparsed: bool = False
    errexit: bool = False

    @property
    def findings(self):
        return [s for s in self.sites if s.klass == FINDING]

    @property
    def local(self):
        return [s for s in self.sites if s.klass == LOCAL_MASKED]


@dataclass
class RepoResult:
    repo: Path
    name: str = ""
    files: int = 0
    vendored: int = 0
    errexit_files: int = 0
    guarded: int = 0
    cond: int = 0
    inert: int = 0
    clean: int = 0
    findings: list = field(default_factory=list)
    local: list = field(default_factory=list)
    unparsed: list = field(default_factory=list)


# ── bash frame parsing ──────────────────────────────────────────────────────

def match_sub(text, open_i, hi):
    """Index of the `)` closing the `$(` at open_i, or -1.

    Quote-, escape- and comment-aware. `$((` (arithmetic) starts at depth
    2 so its `))` closes cleanly. A case-pattern `)` at depth 1 inside the
    substitution closes it EARLY — divergence (4).
    """
    depth = 1
    i = open_i + 2
    if i < hi and text[i] == "(":
        depth = 2
        i += 1
    quote = None
    comment = False
    while i < hi:
        ch = text[i]
        if comment:
            if ch == "\n":
                comment = False
            i += 1
            continue
        if quote == "'":
            if ch == "'":
                quote = None
            i += 1
            continue
        if quote == '"':
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                quote = None
            i += 1
            continue
        if ch == "\\":
            i += 2
            continue
        if ch == "#":
            prev = text[i - 1] if i > 0 else "\n"
            if prev in " \t;&|(\n":
                comment = True
            i += 1
            continue
        if ch in "'\"":
            quote = ch
            i += 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def shell_events(text, lo=0, hi=None, in_sub=False):
    """Parse events over a slice: ('ch', i, ch, kind, in_sub) and
    ('sub', open_i, close_i).

    kind ∈ top|dquote|squote|paren|comment. `$( )` interiors recurse with
    in_sub=True — live shell, but opaque to top-level splitting. Quote
    DELIMITERS carry the enclosing kind so mask keeps them. Newlines are
    yielded with kind "top" so mask preserves them as segment separators.
    `$((` arithmetic is emitted as opaque "paren" chars, never a sub event.
    """
    if hi is None:
        hi = len(text)
    i = lo
    stack = ["top"]
    comment = False
    while i < hi:
        ch = text[i]
        kind = stack[-1]
        if comment:
            if ch == "\n":
                comment = False
                yield ("ch", i, "\n", "top", in_sub)
            else:
                yield ("ch", i, ch, "comment", in_sub)
            i += 1
            continue
        if ch == "\n":
            yield ("ch", i, "\n", "top", in_sub)
            i += 1
            continue
        if kind == "squote":
            if ch == "'":
                stack.pop()
                yield ("ch", i, ch, stack[-1], in_sub)
            else:
                yield ("ch", i, ch, "squote", in_sub)
            i += 1
            continue
        if kind == "dquote":
            if ch == "\\":
                yield ("ch", i, ch, "dquote", in_sub)
                if i + 1 < hi:
                    yield ("ch", i + 1, text[i + 1], "dquote", in_sub)
                i += 2
                continue
            if ch == '"':
                stack.pop()
                yield ("ch", i, ch, stack[-1], in_sub)
                i += 1
                continue
            if ch == "$" and i + 1 < hi and text[i + 1] == "(":
                close = match_sub(text, i, hi)
                if close >= 0:
                    yield ("sub", i, close)
                    yield from shell_events(text, i + 2, close, True)
                    yield ("ch", close, ")", kind, True)
                    i = close + 1
                    continue
                for k in range(i, hi):        # unbalanced: literal rest
                    yield ("ch", k, text[k], "dquote", in_sub)
                return
            yield ("ch", i, ch, "dquote", in_sub)
            i += 1
            continue
        # top / paren frames
        if ch == "\\":
            yield ("ch", i, ch, kind, in_sub)
            if i + 1 < hi:
                yield ("ch", i + 1, text[i + 1], kind, in_sub)
            i += 2
            continue
        if ch == "#":
            prev = text[i - 1] if i > lo else "\n"
            if prev in " \t;&|(\n":
                comment = True
            yield ("ch", i, ch, "comment" if comment else kind, in_sub)
            i += 1
            continue
        if ch in "'\"":
            stack.append("squote" if ch == "'" else "dquote")
            yield ("ch", i, ch, kind, in_sub)
            i += 1
            continue
        if ch == "$" and i + 1 < hi and text[i + 1] == "(":
            close = match_sub(text, i, hi)
            if close >= 0:
                if i + 2 < close and text[i + 2] == "(":
                    for k in range(i, close + 1):      # arithmetic
                        yield ("ch", k, text[k], "paren", in_sub)
                else:
                    yield ("sub", i, close)
                    yield ("ch", i, "$", kind, in_sub)
                    yield ("ch", i + 1, "(", kind, in_sub)
                    yield from shell_events(text, i + 2, close, True)
                    yield ("ch", close, ")", kind, True)
                i = close + 1
                continue
            for k in range(i, hi):
                yield ("ch", k, text[k], kind, in_sub)
            return
        if ch == "(":
            stack.append("paren")
            yield ("ch", i, ch, kind, in_sub)
            i += 1
            continue
        if ch == ")":
            if len(stack) > 1:
                stack.pop()
            yield ("ch", i, ch, kind, in_sub)
            i += 1
            continue
        yield ("ch", i, ch, kind, in_sub)
        i += 1


def logical_lines(text):
    """[(start_lineno, ll_text)] — physical lines grouped the way bash
    reads them.

    Frames: base "top", pushed "squote"/"dquote"/"paren". `$( )` spans are
    consumed ATOMICALLY (match_sub), so newlines inside a substitution are
    just part of the logical line. Comments are buffered but inert.
    Heredoc bodies — queued from COMPLETED lines whose tags sit at top
    level, unquoted, unsubstituted — are consumed as DATA and never reach
    the classifier. Raises Unparsed at EOF inside an unterminated `$(` or
    quote, or with a heredoc undrained.
    """
    line_starts = [0]
    for i, c in enumerate(text):
        if c == "\n":
            line_starts.append(i + 1)

    def line_no(idx):
        return bisect_right(line_starts, idx)

    out = []
    buf: list = []
    first_idx = 0
    stack = ["top"]
    comment = False
    heredoc_q: deque = deque()
    dirty = False
    i, n = 0, len(text)

    def keep(s, idx):
        nonlocal first_idx
        if not buf:
            first_idx = idx
        buf.append(s)

    while i < n:
        ch = text[i]
        if heredoc_q:
            j = text.find("\n", i)
            j = n if j < 0 else j
            line = text[i:j]
            tag, dash = heredoc_q[0]
            term = line.rstrip("\r")
            if dash:
                term = term.lstrip("\t")
            if term == tag:
                heredoc_q.popleft()
            i = j + 1 if j < n else n
            continue
        kind = stack[-1]
        if comment:
            if ch != "\n":
                keep(ch, i)
                i += 1
                continue
            comment = False
        if ch == "\n":
            if len(stack) == 1:
                ll = "".join(buf)
                if ll.strip():
                    out.append((line_no(first_idx), ll))
                    heredoc_q.extend(extract_heredocs(ll))
                buf = []
            else:
                keep(ch, i)
            i += 1
            continue
        if kind == "squote":
            if ch == "'":
                stack.pop()
            keep(ch, i)
            i += 1
            continue
        if kind == "dquote":
            if ch == "\\":
                keep(ch, i)
                if i + 1 < n:
                    keep(text[i + 1], i + 1)
                i += 2
                continue
            if ch == '"':
                stack.pop()
                keep(ch, i)
                i += 1
                continue
            if ch == "$" and i + 1 < n and text[i + 1] == "(":
                close = match_sub(text, i, n)
                if close < 0:
                    dirty = True
                    break
                keep(text[i:close + 1], i)
                i = close + 1
                continue
            keep(ch, i)
            i += 1
            continue
        # top / paren frames
        if ch == "\\":
            keep(ch, i)
            if i + 1 < n:
                keep(text[i + 1], i + 1)
            i += 2
            continue
        if ch == "#":
            prev = text[i - 1] if i > 0 else "\n"
            if prev in " \t;&|(\n":
                comment = True
            keep(ch, i)
            i += 1
            continue
        if ch in "'\"":
            stack.append("squote" if ch == "'" else "dquote")
            keep(ch, i)
            i += 1
            continue
        if ch == "$" and i + 1 < n and text[i + 1] == "(":
            close = match_sub(text, i, n)
            if close < 0:
                dirty = True
                break
            keep(text[i:close + 1], i)
            i = close + 1
            continue
        if ch == "(":
            stack.append("paren")
            keep(ch, i)
            i += 1
            continue
        if ch == ")":
            if len(stack) > 1:
                stack.pop()
            keep(ch, i)
            i += 1
            continue
        keep(ch, i)
        i += 1

    if dirty:
        raise Unparsed("EOF inside an unterminated $( ... )")
    if len(stack) > 1:
        raise Unparsed("EOF inside an unclosed quote or paren")
    if heredoc_q:
        raise Unparsed("unterminated heredoc")
    if buf and "".join(buf).strip():
        out.append((line_no(first_idx), "".join(buf)))
    return out


def extract_heredocs(line_text):
    """[(tag, dash)] — heredoc tags at the logical line's top level.

    Depth-0 only: `x=$((1 << 2))` is a shift, not a heredoc (the `<<` sits
    inside paren frames); `<<<` herestrings do not match the tag grammar.
    """
    tags = []
    for ev in shell_events(line_text):
        if ev[0] != "ch" or ev[3] != "top" or ev[4]:
            continue
        _, i, ch, _kind, _sub = ev
        if ch != "<" or line_text.startswith("<<<", i):
            continue
        m = HEREDOC_TAG.match(line_text, i)
        if m:
            tags.append((m.group(3), m.group(1) == "-"))
    return tags


def find_cmd_subs(line):
    """[(open, close)] of every `$( ... )` span, sorted by close — not
    `$((`, not quoted, not backtick."""
    spans = [s for s in shell_events(line) if s[0] == "sub"]
    return sorted(((s[1], s[2]) for s in spans), key=lambda t: t[1])


def mask_quoted(text):
    """Blank the CONTENT of quoted spans and comments (delimiters and
    newlines kept) so pattern bodies and literals cannot contribute
    command words. Length-preserving."""
    out = list(text)
    for ev in shell_events(text):
        if ev[0] != "ch":
            continue
        _, i, _ch, kind, _sub = ev
        if kind in ("dquote", "squote", "comment"):
            out[i] = " "
    return "".join(out)


def split_top_any(text, seps):
    """Split at top level (unquoted, unsubstituted) on any separator."""
    parts, cur = [], []
    skip = -1
    for ev in shell_events(text):
        if ev[0] != "ch":
            continue
        _, i, ch, kind, in_sub = ev
        if i <= skip:
            continue
        if kind == "top" and not in_sub:
            hit = next((s for s in seps if text.startswith(s, i)), None)
            if hit:
                parts.append("".join(cur))
                cur = []
                skip = i + len(hit) - 1
                continue
        cur.append(ch)
    parts.append("".join(cur))
    return parts


def has_top_op_after(line, close_idx, ops):
    """Any of `ops` at top level AFTER position `close_idx` — the list-final
    exemption test. Slicing at close_idx+1 would start INSIDE a dangling
    close-quote when the substitution was double-quoted; walking the whole
    line and filtering by position cannot mis-frame."""
    for ev in shell_events(line):
        if ev[0] != "ch" or ev[3] != "top" or ev[4]:
            continue
        if ev[1] > close_idx and any(line.startswith(op, ev[1]) for op in ops):
            return True
    return False


def member_capable(member, depth=0):
    """Can this single pipeline MEMBER return non-zero with an empty-capable
    command as its effective tail? A `( ... )` group is judged by its
    interior's last segment — `(grep x f || true) | head` cannot kill
    (measured 2026-09-15: bash survives that shape under set -euo
    pipefail), so a grep behind an in-group `||` is not capable."""
    member = member.strip()
    if depth < 4 and member.startswith("(") and member.rstrip().endswith(")"):
        segs = [s.strip() for s in
                split_top_any(mask_quoted(member[1:-1]), SEG_SEPS)
                if s.strip()]
        if segs:
            return member_capable(segs[-1], depth + 1)
        return False
    return empty_capable(member)


def empty_capable(blob):
    """An empty-capable command word, over non-dash tokens (so `head -1`
    and `tr -d` cannot read as `rg`)."""
    toks = [t for t in re.split(r"[\s|;&]+", blob)
            if t and not t.startswith("-")]
    return bool(EMPTY_CAPABLE.search(" ".join(toks)))


def update_opts(line, err, pf):
    """The errexit/pipefail state machine over one `set` line.

    `set -euo pipefail` — the cluster's trailing `o` consumes the next
    token as its option name, exactly as bash parses it; `+` negates.
    """
    m = SET_LINE.match(line)
    if not m:
        return err, pf
    toks = m.group(1).replace(";", " ").split()
    i = 0
    while i < len(toks):
        t = toks[i]
        i += 1
        if t == "--":
            break
        if len(t) < 2 or t[0] not in "+-" or t.startswith("--"):
            continue
        on = t[0] == "-"
        for ch in t[1:]:
            if ch == "e":
                err = on
            elif ch == "o":                 # bash: -o is last in a cluster
                if i < len(toks):
                    if toks[i] == "errexit":
                        err = on
                    elif toks[i] == "pipefail":
                        pf = on
                i += 1
                break
    return err, pf


def analyse_line(line, lineno, err, pf):
    """Site verdict for one assignment logical line, or None."""
    m = ASSIGN.match(line)
    if not m:
        return None
    subs = [(o, c) for o, c in find_cmd_subs(line) if o > m.end("name")]
    if not subs:
        return None
    open_idx, close_idx = max(subs, key=lambda s: s[1])   # the STATUS law
    content = line[open_idx + 2:close_idx]
    masked = mask_quoted(content)
    segments = [s.strip() for s in split_top_any(masked, SEG_SEPS) if s.strip()]
    if not segments:
        return None
    empty_any = empty_capable(masked)
    last_pipe = split_top_any(segments[-1], ("|",))
    empty_in_last = any(member_capable(p) for p in last_pipe if p.strip())
    text = " ".join(line.split())

    def site(klass, sub=""):
        return Site(line=lineno, klass=klass, sub=sub, text=text)

    if not empty_any:
        return site(CLEAN)
    if m.group("kw") in MASKING_KWS:
        return site(LOCAL_MASKED)          # (d): local returns 0 — silent empty
    if line.split()[0] in COND_WORDS:
        return site(COND_POS)              # (c): condition position is exempt
    if not empty_in_last:
        return site(GUARDED)               # (b): a later segment owns the status
    if has_top_op_after(line, close_idx, ("&&", "||")):
        return site(GUARDED)               # (a): the list's final operator owns it
    if masked.rstrip().endswith("&"):
        return site(GUARDED)               # backgrounded: async status is 0
    if not err:
        return site(INERT)
    if pf:
        return site(FINDING, PIPEFAIL_KILL)
    last_members = [p for p in last_pipe if p.strip()]
    if member_capable(last_members[-1]):
        return site(FINDING, TAIL_KILL)    # pipefail OFF, but grep IS the tail
    return site(GUARDED)                   # `| head -1` after it owns the status


def scan_text(text):
    """FileScan — the classifier over one shell file's text."""
    sc = FileScan()
    try:
        lls = logical_lines(text)
    except Unparsed:
        sc.unparsed = True
        return sc
    err = pf = False
    for lineno, ll in lls:
        if ll.strip():
            site = analyse_line(ll, lineno, err, pf)
            if site is not None:
                sc.sites.append(site)
                if site.klass == GUARDED:
                    sc.guarded += 1
                elif site.klass == COND_POS:
                    sc.cond += 1
                elif site.klass == INERT:
                    sc.inert += 1
                elif site.klass == CLEAN:
                    sc.clean += 1
        err, pf = update_opts(ll, err, pf)
        if err:
            sc.errexit = True
    return sc


# ── per-repo population + report ────────────────────────────────────────────

def audit_repo(repo: Path) -> RepoResult:
    res = RepoResult(repo=repo, name=repo.name)
    files, res.vendored = tracked_files(repo, "*.sh")
    res.files = len(files)
    for p in files:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        sc = scan_text(text)
        rel = p.relative_to(repo).as_posix()
        if sc.unparsed:
            res.unparsed.append(rel)
            continue          # UNPARSED: its sites are not trustworthy evidence
        if sc.errexit:
            res.errexit_files += 1
        res.guarded += sc.guarded
        res.cond += sc.cond
        res.inert += sc.inert
        res.clean += sc.clean
        res.findings.extend(
            {"rel": rel, "line": s.line, "sub": s.sub, "text": s.text}
            for s in sc.findings)
        res.local.extend(
            {"rel": rel, "line": s.line, "text": s.text} for s in sc.local)
    res.findings.sort(key=lambda f: (f["rel"], f["line"]))
    res.local.sort(key=lambda f: (f["rel"], f["line"]))
    return res


def report(results, verbose):
    tot = {"files": 0, "err": 0, "sites": 0, "find": 0, "guard": 0,
           "cond": 0, "inert": 0, "clean": 0, "local": 0, "unp": 0, "vend": 0}
    for r in results:
        n_sites = (r.guarded + r.cond + r.inert + r.clean
                   + len(r.findings) + len(r.local))
        if not r.files:
            continue
        tot["files"] += r.files
        tot["err"] += r.errexit_files
        tot["sites"] += n_sites
        tot["find"] += len(r.findings)
        tot["guard"] += r.guarded
        tot["cond"] += r.cond
        tot["inert"] += r.inert
        tot["clean"] += r.clean
        tot["local"] += len(r.local)
        tot["unp"] += len(r.unparsed)
        tot["vend"] += r.vendored
        head = (f"  {r.name:22s} sh={r.files:<3d} errexit={r.errexit_files:<3d} "
                f"sites={n_sites:<3d} findings={len(r.findings)} "
                f"guarded={r.guarded} cond={r.cond} inert={r.inert} "
                f"clean={r.clean} local-masked={len(r.local)}")
        if r.unparsed:
            head += f" UNPARSED={len(r.unparsed)}"
        if r.vendored:
            head += f" vendored={r.vendored}"
        print(head)
        for f in r.findings:
            print(f"      ✗ {f['sub']:14s} {f['rel']}:{f['line']}  {f['text']}")
        for f in r.local:
            print(f"      · LOCAL-MASKED {f['rel']}:{f['line']}  {f['text']}")
        for rel in r.unparsed:
            print(f"      ⛔ UNPARSED     {rel}")
        if verbose and not r.findings:
            print("      (no site can kill under errexit)")
    print()
    print(f"  totals — {tot['files']} tracked .sh over {len(results)} repo(s) "
          f"({tot['vend']} vendored excluded) · {tot['err']} under errexit · "
          f"{tot['sites']} site(s): {tot['find']} FINDING · {tot['guard']} "
          f"GUARDED · {tot['cond']} COND-POS · {tot['inert']} INERT · "
          f"{tot['clean']} CLEAN · {tot['local']} LOCAL-MASKED")
    if tot["unp"]:
        print(f"  ⚠ {tot['unp']} file(s) UNPARSED — the instrument admitting "
              f"it cannot read; never folded into clean or findings")
    print("  scope: errexit scripts; empty-capable member set = "
          "grep/egrep/fgrep/rg/ripgrep v1; LOCAL-MASKED is listed, never gated")
    return tot


# ── expected-file key helpers (shared with the sweep) ───────────────────────

def make_digest(text):
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:8]


def finding_key(repo, rel, text, ordinal):
    return f"{repo}:{rel}:{make_digest(text)}#{ordinal}"


# ── validation ──────────────────────────────────────────────────────────────

P = "set -euo pipefail\n"
E = "set -eu\n"                                     # errexit, NO pipefail


def _c(label, text, **want):
    return (label, text, want)


SELFTEST_CASES = [
    _c("the perf_rematch kill shape fires PIPEFAIL-KILL", P +
       'names="$(grep -E \'pid=\' "$cl" 2>/dev/null | head -3 | sed -E '
       "'s/ :: .*//' | paste -sd ';' -)\"\n",
       finding=PIPEFAIL_KILL),
    _c("…the same with an `|| true` tail is GUARDED", P +
       'names="$(grep -E \'pid=\' "$cl" | head -3 | sed -E \'s/ :: .*//\' '
       "| paste -sd ';' - || true)\"\n",
       finding=None, guarded=1),
    _c("…an `|| echo unknown` tail is GUARDED too", P +
       'name="$(grep -E \'name=\' "$cl" | head -1 || echo unknown)"\n',
       finding=None, guarded=1),
    _c("the proof_gate grep -c tripwire fires", P +
       'directives="$(grep -c \'^#print axioms\' PrintAxioms.lean)"\n',
       finding=PIPEFAIL_KILL),
    _c("grep as the last command under errexit WITHOUT pipefail is TAIL-KILL",
       E + 'directives="$(grep -c \'^#print axioms\' PrintAxioms.lean)"\n',
       finding=TAIL_KILL),
    _c("grep mid-pipeline under pipefail-OFF is GUARDED (head owns it)", E +
       'first="$(grep pid= "$cl" | head -1)"\n',
       finding=None, guarded=1),
    _c("condition position is exempt", P +
       'if v="$(grep x f)"; then :; fi\n',
       finding=None, cond=1),
    _c("local masks the status — LOCAL-MASKED, never gated", P +
       'local v="$(grep x f)"\n',
       finding=None, local=1),
    _c("a pipeline with no empty-capable member is CLEAN", P +
       'v="$(ls | head -1)"\n',
       finding=None, clean=1),
    _c("a single-quoted $() is literal text — no site at all", P +
       "echo '$(grep x f)'\n",
       sites=0),
    _c("a multi-line substitution still parses and fires", P +
       'NAME="$(\n  grep pattern file.txt\n)"\n',
       finding=PIPEFAIL_KILL),
    _c("a never-closed substitution is UNPARSED", P +
       'NAME="$(grep x f\n',
       unparsed=True, sites=0),
    _c("a line-level `|| true` guards the whole assignment", P +
       'NAME=$(grep x f) || true\n',
       finding=None, guarded=1),
    _c("a LEADING word && does NOT guard the list-final assignment", P +
       'true && NAME="$(grep x f)"\n',
       finding=PIPEFAIL_KILL),
    _c("…but a TRAILING && does (the list's final operator owns it)", P +
       'NAME="$(grep x f)" && echo done\n',
       finding=None, guarded=1),
    _c("arithmetic `$((1 << 2))` is not a site (nor a heredoc)", P +
       'v=$((1 << 2))\n',
       sites=0),
    _c("a heredoc body is DATA — its grep words never classify", P +
       'cat <<EOF\ngrep nothing here\nEOF\nv="$(ls)"\n',
       finding=None, sites=1, clean=1),
    _c("no errexit at all is INERT", 'v="$(grep x f)"\n',
       finding=None, inert=1),
    _c("a comment line is not a site", P + '# v="$(grep x f)"\n',
       sites=0),
    _c("only the LAST substitution decides the status", P +
       'v="$(grep x f)$(echo ok)"\n',
       finding=None, clean=1),
    _c("export does NOT mask — it kills", P +
       'export v="$(grep x f)"\n',
       finding=PIPEFAIL_KILL),
    _c("the teardown.sh shape (wrangler | grep | awk | tr | head -1)", P +
       'ID="$(npx wrangler containers list 2>/dev/null | grep "$APP" | '
       "awk -F'│' '{print $2}' | tr -d ' ' | head -1)\"\n",
       finding=PIPEFAIL_KILL),
    _c("a case-pattern `)` does not underflow the depth", P +
       'case $x in\n  a) echo hi ;;\nesac\nv="$(grep x f)"\n',
       finding=PIPEFAIL_KILL),
    _c("a backgrounded substitution is GUARDED (async status is 0)", P +
       'v="$(grep x f &)"\n',
       finding=None, guarded=1),
    _c("(grep x f || true) | head owns the failure — GUARDED (measured)", P +
       'SEED_HEX=$( (grep -E \'^X=\' "$ENV_FILE" || true) | head -1 | '
       'cut -d= -f2-)\n',
       finding=None, guarded=1),
]


def selftest() -> int:
    """Pin the classifier in BOTH directions. Exit 2, never 1."""
    bad = 0
    for label, text, want in SELFTEST_CASES:
        sc = scan_text(text)
        got_findings = [f.sub for f in sc.findings]
        fails = []
        if "finding" in want:
            if want["finding"] is None:
                if got_findings:
                    fails.append(f"unexpected finding(s) {got_findings}")
            elif got_findings != [want["finding"]]:
                fails.append(f"finding {got_findings} != [{want['finding']}]")
        for key, attr in (("sites", None), ("guarded", sc.guarded),
                          ("cond", sc.cond), ("inert", sc.inert),
                          ("clean", sc.clean)):
            if key in want:
                got = len(sc.sites) if key == "sites" else attr
                if got != want[key]:
                    fails.append(f"{key}={got} != {want[key]}")
        if "local" in want and len(sc.local) != want["local"]:
            fails.append(f"local={len(sc.local)} != {want['local']}")
        if "unparsed" in want and sc.unparsed != want["unparsed"]:
            fails.append(f"unparsed={sc.unparsed} != {want['unparsed']}")
        mark = "✓" if not fails else "✗"
        if fails:
            bad += 1
        print(f"  {mark} {label}")
        for f in fails:
            print(f"      {f}")
    print()
    print(f"  {len(SELFTEST_CASES) - bad}/{len(SELFTEST_CASES)} arm(s) pinned")
    if bad:
        print("  ⛔ classifier MISS — the report is not trustworthy")
        return 2
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="pipefail measurement-discard audit: errexit assignments "
                    "whose substitution pipeline can return non-zero")
    ap.add_argument("repos", nargs="*", help="repo paths (default: derived)")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        print("pipefail measurement-discard audit — classifier self-test\n")
        return selftest()

    rc = selftest()
    if rc:
        return rc
    print()

    here = Path(__file__).resolve().parent.parent
    repos = ([Path(a).resolve() for a in args.repos] if args.repos
             else [here.parent / a for a in derive_repos(here.parent)])
    print(f"pipefail measurement-discard audit — {len(repos)} repo(s)\n")
    tot = report([audit_repo(r) for r in repos], args.verbose)
    if tot["files"] < FLOOR_FILES:
        print(f"  ⛔ {tot['files']} tracked .sh < floor {FLOOR_FILES} — the "
              f"walk is blind, the zeros above mean nothing")
        return 2
    if tot["sites"] < FLOOR_SITES:
        print(f"  ⛔ {tot['sites']} site(s) < floor {FLOOR_SITES} — the "
              f"classifier saw nothing; that is instrument failure, not a "
              f"clean workspace")
        return 2
    return 0                        # a REPORT: the verdict half is the sweep's


if __name__ == "__main__":
    sys.exit(main())
