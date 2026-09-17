#!/usr/bin/env python3
"""Run the locale-text-I/O verdict over EVERY contract repo (Issue 829).

`scripts/locale_io_gate.py` walks `REPO_ROOT` and `docs_gate.yml` has a single
checkout, so it can never see a sibling. That is the right shape for a
per-push gate and the wrong shape for "is anybody ELSE round-tripping a
document through the box's codec?"

This is the **ninth** recorded instance of a rule landing in one instrument
and never generalising (Issues 777, 778, 793, 782, 783, 789, 797, 820), so the
sweep half lands in the same change as the gate rather than after it. The
first workspace measurement, taken before either existed:

    katgpt-rs 155 · riir-train 68 · riir-clippy 27 · riir-ai 10 · riir-chain 7
    riir-mmorpg-examples 2 · riir-shader 2 · seal-game-editor 2   =  273 sites
    over 195 tracked `*.py` in 16 repos

## The ceiling is a RATCHET, and that is measured rather than preferred

`subprocess_encoding_drift_sweep` walls its class at 0 because its whole
workspace population was 31 and every row was repaired in the landing change.
This class is **118 sites in seven repos this session does not own**, which is
Issue 785's forbidden shape for a wall: a pin whose rows nobody has read is a
backlog wearing a pin. So the ceiling constrains the DERIVATIVE — the commit
that adds ANOTHER locale-dependent read reds — and the existing rows stay
their own repos' to adjudicate, exactly as `instrument_reachability_drift_sweep`
resolved the same question.

⛔ katgpt-rs's own row is **0**, and it is not a ratchet: the repair is one
mechanical, idempotent, 14-arm pass (`scripts/locale_io_fix.py <paths>`), so
there is nothing here to adjudicate. Its two floors must EQUAL the per-push
gate's, and this sweep asserts that rather than trusting it — the
`docs_gate_paths_sync.py` pattern.

## Two floors, and `min_io_calls` is vacuous in the repos with no Python

`max_locale_io` is green over whatever the walk can SEE. `min_py_files` moves
when the WALK goes blind; `min_io_calls` when the AST PASS breaks on an
unchanged tree. Six of sixteen repos have **zero** tracked `*.py`, so their
parse floor is 0 and cannot detect anything — in exactly those repos the walk
floor is the only blindness detector there is. Issue 783's measured population
shape, not Issue 784's.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# DRY: the classifier, the walk and the floors are the per-push gate's, so the
# two can never disagree about what "uses the system locale" means (Issue 755).
import locale_io_gate as lig  # noqa: E402
from skill_repo_set_gate import derive_repos  # noqa: E402
from sweep_population import population_verdict, pin_row_exempt  # noqa: E402
from tracked_walk import tracked_files  # noqa: E402
from worktree_state import (head_delta, line_free,  # noqa: E402
                            ordinal_keys, sweep_advisory)

import console_safe  # noqa: E402

console_safe.apply()

REPO_ROOT = HERE.parent
WORKSPACE = REPO_ROOT.parent
PINS = HERE / "locale_io_drift_floors.txt"

FIELDS = ("min_py_files", "min_io_calls", "max_locale_io")


def keyed(rows) -> list:
    """`[(key, rel, row)]`, ordinals assigned in order — a LINE-FREE key.

    The rows are `"{lineno}: {call text}"` and a line-bearing key reports
    EVERY row in an edited file as UNCOMMITTED *and* MASKED at once, since any
    insertion above a call shifts it. `line_free` strips the prefix only when
    it is a bare integer, so a row whose own text begins `note: …` survives
    whole; `ordinal_keys` disambiguates two identical calls in one file.
    """
    return [(k, rel, row)
            for k, (rel, row) in ordinal_keys(rows, lambda t: (t[0], line_free(t[1])))]


def flatten(offenders: dict) -> list:
    return [(rel, r) for rel in sorted(offenders) for r in offenders[rel]]


def head_offenders(walk: set):
    """`head_delta`'s per-file reclassifier.

    Per-file row independence holds by construction: the classifier is an AST
    pass over ONE module's source, so a clean file's rows are identical at
    HEAD and the cost is |dirty ∩ population| `git show` calls.

    `walk` is the sweep's own tracked population, passed in rather than
    re-derived: `fnmatch`'s `*` crosses `/`, so the scope glob admits paths
    the walk excludes, and a row invented there reads as MASKED — a hard red
    nobody can repair.
    """

    def rescan(rel: str, src: str | None) -> list:
        # None = tracked but absent from HEAD (staged, never committed): there
        # is nothing committed to classify, so the worktree row is UNCOMMITTED.
        if src is None or rel not in walk:
            return []
        try:
            rows, _ = lig.scan_text(src)
        except SyntaxError:
            # UNPARSED at HEAD is the instrument admitting it cannot read. It
            # has its own bucket one level up and is never folded into the
            # ceiling — clean hides exposure, offender invents it.
            return []
        return [(rel, r) for r in rows]

    return rescan


def adjudicate(repo: Path, offenders: dict, walk: set):
    """The rows, split COMMITTED / UNCOMMITTED / MASKED (Issue 822).

    A named seam rather than four lines inline: this is the verdict
    arithmetic, and `arm_reach_audit`'s standing finding in this repo is that
    the classifier is well armed and the verdict is not.
    """
    rows = keyed(flatten(offenders))
    rescan = head_offenders(walk)
    return head_delta(
        repo, ("*.py",), rows,
        lambda r: r[1], lambda r: r[0],
        lambda rel, src: keyed(rescan(rel, src)))


def row_tag(key, held: set, hidden: set) -> str:
    """The provenance LABEL for one printed row (Issue 822).

    Module level, not a closure inside `main()`: a label is the only thing
    telling a reader that a row the pins did not adjudicate is on the screen,
    and a closure is unarmable by construction — `arm_reach_audit`'s standing
    finding in this repo is that the classifier is armed and the verdict is
    not. Never hidden, only labelled: hiding them is the lie Issue 797
    refuses.
    """
    if key in held:
        return "  [UNCOMMITTED — not adjudicated]"
    if key in hidden:
        return "  [MASKED — committed, and this worktree hides it]"
    return ""


def parse_pins(path: Path) -> dict[str, dict[str, int]]:
    rows: dict[str, dict[str, int]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 1 + len(FIELDS):
            raise ValueError(
                # EQUIVALENT under mutation: this arithmetic is inside the
                # MESSAGE of a raise the line above already decided to make.
                f"malformed pin row (want {1 + len(FIELDS)} fields): {raw!r}")
        rows[parts[0]] = dict(zip(FIELDS, (int(v) for v in parts[1:])))
    return rows


def selftest() -> list[str]:
    """Arms over this sweep's OWN arithmetic — the pin reader and the key.

    The classifier has its own arms in `locale_io_gate.selftest()` and is not
    re-asserted here; what is asserted is everything this file adds.
    """
    import tempfile

    fails: list[str] = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "pins.txt"
        p.write_text("# c\nrepo-a  40 30 0\n", encoding="utf-8")
        check(parse_pins(p) == {"repo-a": dict(zip(FIELDS, (40, 30, 0)))},
              f"pin row not parsed: {parse_pins(p)}")
        p.write_text("repo-a  40 30\n", encoding="utf-8")
        try:
            parse_pins(p)
            fails.append("a SHORT pin row parsed — a missing column would "
                         "silently shift every later field")
        except ValueError:
            pass

    # The key is LINE-FREE: the same call at two line numbers is ONE key, or
    # every row in an edited file reads UNCOMMITTED and MASKED at once.
    a = keyed([("x.py", "10: p.write_text(s)")])
    b = keyed([("x.py", "77: p.write_text(s)")])
    check([k for k, _, _ in a] == [k for k, _, _ in b],
          f"the row key is line-BEARING: {a} vs {b}")
    # Two identical calls in one file are two rows, or a repair of one reads
    # as a repair of both.
    two = keyed([("x.py", "1: p.write_text(s)"), ("x.py", "9: p.write_text(s)")])
    check(len({k for k, _, _ in two}) == 2,
          f"duplicate calls collapsed to one key: {two}")
    # A row whose text begins with a non-integer prefix must survive whole.
    check(line_free("note: open(p)") == "note: open(p)",
          "line_free beheaded a row whose prefix is not a line number")

    # The reclassifier's three refusals, each of which invents or hides a row.
    rescan = head_offenders({"x.py"})
    check(rescan("x.py", None) == [],
          "a file absent from HEAD produced committed rows")
    check(rescan("out-of-walk.py", "open(p)\n") == [],
          "a path outside the walk produced a row — it would read MASKED")
    check(rescan("x.py", "def f(:\n") == [],
          "an UNPARSED file at HEAD produced rows")
    check(rescan("x.py", "open(p)\n") == [("x.py", "1: open(p)")],
          f"the reclassifier missed a real row: {rescan('x.py', 'open(p)')}")

    # The provenance LABEL, both directions plus the default. A row printed
    # without its label reads as an ordinary adjudicated finding, which is
    # exactly what Issue 822 exists to prevent — and UNCOMMITTED must win on a
    # key in both sets, or a row the pins did not read is shown as one they did.
    check("UNCOMMITTED" in row_tag("k", {"k"}, set()), "the held label is gone")
    check("MASKED" in row_tag("k", set(), {"k"}), "the hidden label is gone")
    check(row_tag("k", set(), set()) == "",
          "an ordinary committed row was labelled")
    check("UNCOMMITTED" in row_tag("k", {"k"}, {"k"}),
          "a row in BOTH sets did not take the UNCOMMITTED label")
    return fails


def main() -> int:
    fails = selftest()
    if fails:
        print("✗ locale-io sweep SELFTEST FAILED — instrument untrustworthy:")
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

    names = derive_repos(WORKSPACE)
    if not names:
        print(f"✗ derived population is EMPTY under {WORKSPACE} — refusing to "
              f"report a green over zero repos")
        return 2

    # Same quantities, two files. Asserted, not trusted.
    mine = pins.get(REPO_ROOT.name, {})
    for field, owned in (("min_py_files", lig.FLOOR_PY_FILES),
                         ("min_io_calls", lig.FLOOR_IO_CALLS)):
        if mine.get(field) != owned:
            print(f"✗ pin drift: {PINS.name} says {field}={mine.get(field)} for "
                  f"{REPO_ROOT.name}, locale_io_gate owns {owned}. Same "
                  f"quantity, two files — change both.")
            return 1

    bad = False
    tot_files = tot_calls = tot_hits = tot_unp = tot_vend = 0
    n_uncommitted = n_masked = 0

    for name in names:
        repo = WORKSPACE / name
        offenders, py_files, calls, unparsed = lig.scan(repo)

        # ── Issue 822: the DISPLAY reads the worktree, the PINS read HEAD ──
        kept, vendored = tracked_files(repo, "*.py")
        walk = {str(f.relative_to(repo)).replace(chr(92), "/") for f in kept}
        delta = adjudicate(repo, offenders, walk)
        n_uncommitted += len(delta.uncommitted)
        n_masked += len(delta.masked)
        held = {r[0] for r in delta.uncommitted}
        hidden = {r[0] for r in delta.masked}

        n_hits = sum(len(v) for v in offenders.values())
        tot_files += py_files
        tot_calls += calls
        tot_hits += n_hits
        tot_unp += len(unparsed)
        tot_vend += vendored

        row = pins.get(name)
        flags = []
        if row is None:
            # Issue 821: an acknowledged known-extra owes no pin row.
            if not pin_row_exempt(name):
                flags.append("UNPINNED — add a row (or it can never red)")
        else:
            if py_files < row["min_py_files"]:
                flags.append(f"walk FLOOR breached: {py_files} tracked .py < "
                             f"{row['min_py_files']} — files were removed, or "
                             f"`git ls-files` went blind and the count below "
                             f"means nothing")
            if calls < row["min_io_calls"]:
                flags.append(f"parse FLOOR breached: {calls} text-I/O call "
                             f"site(s) < {row['min_io_calls']} — the walk is "
                             f"intact but the AST pass found nothing")
            if len(delta.head) > row["max_locale_io"]:
                flags.append(f"LOCALE-IO {len(delta.head)} committed > pinned "
                             f"{row['max_locale_io']} — repair with "
                             f"`scripts/locale_io_fix.py`, do NOT raise the "
                             f"ceiling")
        if unparsed:
            flags.append(f"{len(unparsed)} file(s) the parser could not read — "
                         f"UNPARSED is the instrument admitting it cannot see, "
                         f"never a pass")

        status = "✗" if flags else ("·" if n_hits else "✓")
        vend = f" vendored={vendored}" if vendored else ""
        split = ""
        if delta.uncommitted or delta.masked:
            split = (f" ({len(delta.head)} committed"
                     + (f", {len(delta.uncommitted)} uncommitted"
                        if delta.uncommitted else "")
                     + (f", {len(delta.masked)} MASKED" if delta.masked else "")
                     + ")")
        print(f"{status} {name:22s} py={py_files:<4d} io={calls:<4d} "
              f"locale={n_hits}{vend}{split}")

        def _tag(key, _held=held, _hidden=hidden):
            return row_tag(key, _held, _hidden)

        for key, rel, r in keyed(flatten(offenders))[:12]:
            print(f"      ⛔ LOCALE-IO {rel}:{r}{_tag(key)}")
        if n_hits > 12:
            print(f"      … {n_hits - 12} more (run "
                  f"`scripts/locale_io_gate.py {repo}` for the full list)")
        # A MASKED row is in HEAD and NOT in the worktree, so the loop above
        # cannot reach it — it has no line here to hang a label on.
        for key, rel, r in delta.masked:
            print(f"      ⛔ LOCALE-IO {rel}:{r}  [MASKED — committed, and this "
                  f"worktree hides it]")
        for r in unparsed:
            print(f"      ⛔ UNPARSED   {r}")
        for f in flags:
            bad = True
            print(f"      ✗ {f}")

    pop_lines, deferred, pop_fail = population_verdict(pins, names)
    deferred.extend(sweep_advisory(
        names, ("*.py",), root=WORKSPACE,
        uncommitted_rows=n_uncommitted, masked_rows=n_masked))
    for _line in pop_lines:
        print(_line)
    if pop_fail:
        bad = True

    print(f"\n{len(names)} contract repo(s) · {tot_files} tracked .py "
          f"({tot_vend} vendored, excluded) · {tot_calls} text-I/O call site(s) "
          f"· {tot_hits} LOCALE-IO · {tot_unp} UNPARSED")
    print("  scope: `Path.read_text` / `Path.write_text` / builtin `open()` in "
          "TEXT mode with no `encoding=`. Binary mode is skipped and a "
          "`**kwargs` splat is UNKNOWN, never counted — this repair may only "
          "ever be conservative.")
    print("  ⚠ the ceiling is a RATCHET on the DERIVATIVE, not a wall: the "
          "standing rows are their own repos' to adjudicate, and ratcheting a "
          "bucket nobody has read is a backlog wearing a pin (Issue 785). "
          "katgpt-rs's own row is 0 and is not a ratchet.")

    if bad:
        print("✗ locale-io sweep FAILED — see the ✗ rows above")
        for _d in deferred:
            print(f"  ⚠ {_d}")
        print("    The repair is one mechanical, idempotent pass: "
              "`scripts/locale_io_fix.py <paths>`. Do NOT raise a ceiling.")
        return 1
    _line = "✓ locale-io sweep PASSED — every repo within its pins"
    if deferred:
        _line += "; DEFERRED: " + "; ".join(deferred)
    print(_line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
