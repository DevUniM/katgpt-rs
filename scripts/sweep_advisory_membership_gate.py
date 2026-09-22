#!/usr/bin/env python3
""""Every sweep" must be a MEMBERSHIP assertion, not a count in prose.

Issue 797 T5. The Issue-797 worktree advisory landed in all sixteen sweeps that
existed that morning, and AGENTS.md said so — "wired into all sixteen sweeps",
a hand-typed figure. **Two hours later there were eighteen**: a concurrent
session landed `pipefail_discard_drift_sweep.py` and
`toolchain_override_drift_sweep.py`, neither wired, and nothing noticed. The
prose was stale before the commit that wrote it had finished being pushed.

That is the standing failure mode of this repo, recorded seven times then
(Issues 777, 778, 793, 782, 783, 789, 797): **a rule landed in one instrument
and never generalised.** Every previous instance was repaired by grepping the
family by hand and fixing the copies. This one is repaired by making the family
gate itself: a `*_drift_sweep.py` that does not call the mechanism REDS, so the
next one cannot land unwired.

⛔ **And then it happened again, to a DIFFERENT mechanism, while this gate was
already standing (Issue 824).** Issue 821 landed `pin_row_exempt()` — the
Issue-815 known-extra acknowledgement — in **16 of the 19** sweeps and wrote
"16" in its own close-out. The three it missed were exactly the three Issue 782
had already named as the quiet ones; `cfg_row_implication` was HARD RED on
three acknowledged repos with zero content findings, and the other two were
latent only because of properties of today's corpus.

The lesson is not "wire the three". It is that this gate governed ONE mechanism
by name when the class is *any* family-wide mechanism, so it could watch the
exact failure it was built for happen beside it. `MECHANISMS` is a registry
now: adding the next one is a row there, the arms walk it rather than hard-code
it, and it then cannot land in a subset.

The quantity to gate is NOT the count — this repo already has the rule written
for `cfg_gated_floor_gate`: *a set is gateable where its cardinality is not.* A
count is green on a swap (one sweep wired, one unwired, total unchanged), and
it goes stale the moment the family grows, which is precisely what happened.

⚠ **What this does NOT assert:** that the patterns a sweep passes actually name
its own population. A sweep that calls `sweep_advisory(names, ("*.lean",))`
over a Rust walk is silent forever and reads as wired. That is a per-sweep read
and is not statically decidable — the same limit `check_validation_gate`
records about arm QUALITY. Read the verdict as the weaker thing it is.

Exemptions are pinned by MEMBERSHIP with a REASON per row
(`scripts/sweep_advisory_expected.txt`), keyed by `(mechanism, sweep)`; a
reasonless row is refused, an unknown mechanism slug is refused, and a row whose
sweep has since been wired REDS — a pin file that only ever loosens is a backlog
wearing a pin (Issue 785's rule). The key is qualified for the same reason
`DOCS_GATE_KNOWN_EXTRA` takes names rather than `=1`: an unqualified row would
excuse the sweep from the mechanism nobody has looked at yet.

    scripts/sweep_advisory_membership_gate.py    # the verdict AND the arms

The arms run UNCONDITIONALLY, behind no flag: `docs_gate.sh` invokes each check
as `"$PY" "$script"` with no arguments, so an arm behind `'--canary' in
sys.argv` never fires on a push (Issue 789's finding, measured on the eight
adversary arms that had landed the day before). They cost ~0.05s.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
from pathlib import Path

# Issue 804: this instrument is documented as directly invokable, and its
# verdict glyphs (✓ ✗ ⛔ ⚠) kill it on a non-UTF-8 console — no verdict at
# all, findings unread. docs_gate.sh's PYTHONIOENCODING only covers runs
# that go through the wrapper.
import console_safe  # noqa: E402
import worktree_state  # noqa: E402

console_safe.apply()

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent

PINS = HERE / "sweep_advisory_expected.txt"
GLOB = "*_drift_sweep.py"
# ⛔ Its FIRST run found that this was ONE name where there are two. A sweep
# whose findings carry a file:line address wires the RICHER row-level split and
# calls `worktree_advisory()` directly with its UNCOMMITTED and MASKED counts;
# `sweep_advisory()` is the repo-level convenience over it.
# `citation_drift_sweep` is wired more thoroughly than any other member and read
# UNWIRED. A predicate that names one of two entry points reports the most
# careful caller as the defect — so the criterion is the MECHANISM, by set.
# ⛔ `worktree_advisory` was here and is NOT any more, and the correction is
# the measurement rather than a tightening for its own sake (2026-09-19).
#
# The pair existed because a narrower predicate once condemned
# `citation_drift_sweep` — the most carefully wired member — for calling the
# low-level entry point, and "a criterion that condemns the most careful
# caller is the criterion that is wrong" is this file's own rule. It was the
# right repair and it rested on a premise that was never checked: that the
# two entry points deliver the same thing. They did not.
# `sweep_advisory()` computes the dirty scope AND asks `behind_origin`;
# `worktree_advisory()` only RENDERS what it is handed. So the one sweep on
# the low-level path had the worktree axis and no upstream axis at all — no
# STALE, no UNVERIFIED — in the only member whose rows carry a `file:line`
# address and name another repo.
#
# Measured: it reported a CROSS finding at riir-neuron-db `HISTORY.md:49`
# with no advisory of any kind, while `origin/develop` already carried the
# repair and that checkout was 4 commits behind with one of them touching
# that file. Issue 798's founding class, *a committed FIX read dirty*.
#
# `upstream_axis` was factored out of `sweep_advisory` so the low-level path
# can get the missing half, and it replaces `worktree_advisory` here: the
# pair still has two members, so the careful caller is still credited, and
# now BOTH of them actually deliver the axis. A sweep that renders without
# asking is no longer wired, which is the true reading.
#
# ⚠ NOT a fifth MECHANISMS row, and the registry's own arm is what said so:
# `sweep_advisory` would then have served two mechanisms, and the arm that
# refuses POOLING fired immediately. It was right — this is one mechanism
# whose membership test was wrong, not two mechanisms.
WANTED = ("sweep_advisory", "upstream_axis")

# ⛔ Issue 824. This gate was built for ONE mechanism, and the very failure its
# docstring describes then happened AGAIN to a different one: Issue 821 landed
# `pin_row_exempt()` — the Issue-815 known-extra acknowledgement — in **16 of
# the 19** sweeps, wrote "16" in its own close-out, and the three it missed were
# exactly the three Issue 782 had already named as the quiet ones. One of them
# (`cfg_row_implication`) was HARD RED on three acknowledged repos with zero
# content findings; the other two were latent for reasons that are properties
# of today's corpus rather than of the checks.
#
# So the unit this gate governs is a FAMILY-WIDE MECHANISM, plural — not the
# advisory specifically. Adding the next one is a row here, and it then cannot
# land in a subset, which is the whole point of the instrument.
#
# slug -> (what it is, the call names that COUNT as wired). A SET of names per
# mechanism, not one name, for the reason WANTED is already a pair: naming one
# of two entry points reports the most careful caller as the defect.
MECHANISMS: dict[str, tuple[str, tuple[str, ...]]] = {
    "worktree-advisory": (
        "Issue 797 — otherwise a sweep's findings and floors describe "
        "whatever the working tree happened to say", WANTED),
    "known-extra-exemption": (
        "Issue 815/821 — otherwise a sweep hard-reds on a repo the contract "
        "does not claim, with zero content findings", ("pin_row_exempt",)),
    # Issue 822 T6. The third mechanism, and the one this registry was
    # generalised FOR: Issue 822 is the ninth recorded instance of a rule
    # landing in one instrument and never generalising, and its own fan-out
    # was tracked by a hand-ticked table in an issue file — in a family that
    # grew twice while the table was being written. Without a row here the
    # SEVENTEENTH sweep lands unwired and nothing objects, which is exactly
    # what Issue 821 did with `pin_row_exempt` (16 of 19, "16" in its own
    # close-out) and what 797 did with the advisory (16 of 18 within hours).
    #
    # FOUR names, because the mechanism has four entry points and naming a
    # subset reports the most careful caller as the defect (the rule this
    # dict's own comment already states, learned when the advisory predicate
    # named one of two and condemned `citation_drift_sweep`):
    #   head_delta    per-file classifiers
    #   head_overlay  cross-file, whole-run re-classification from a dict
    #   head_tree     multi-seam classifiers — a materialised HEAD checkout
    #   head_text     the raw HEAD blob, which is what `citation_drift_sweep`
    #                 uses: it carries the INLINE original the other three were
    #                 lifted out of, so it is WIRED, not exempt. Crediting it
    #                 by its actual call is the honest reading; an exemption
    #                 row would say "this sweep may count uncommitted rows",
    #                 which is false.
    "head-provenance": (
        "Issue 822 — otherwise a sweep counts rows that sit on a line NO "
        "COMMIT CONTAINS into a ceiling, and the obvious remedy is to re-pin "
        "from another session's in-flight edit",
        ("head_delta", "head_overlay", "head_tree", "head_text")),
    # Issue 842, registered 2026-09-19. The FOURTH, and it is the plainest
    # case this registry has had: 17 of 19 sweeps opened `WORKSPACE /
    # <contract-name>` directly, the repair was applied to all of them BY
    # HAND in one commit, and nothing then stopped the twentieth landing
    # unwired. On an alias box the contract spelling is not a directory, a
    # walk over a missing directory returns ZERO rather than raising, and a
    # repo whose floor is zero prints a SILENT ✓ — so the failure mode is a
    # sweep adjudicating a TRUE pin against an empty tree, in the direction
    # nothing detects.
    #
    # TWO names, the two seams the repair actually shipped:
    #   open_repo  the sweep-level seam (`sweep_population.open_repo`)
    #   real       the audit-module seam (`repo_alias.real`), identity for an
    #              unmapped name and therefore fixture-safe
    "alias-open": (
        "Issue 842 — otherwise a sweep opens a directory that does not exist "
        "on an alias box, and a walk over a missing directory returns ZERO "
        "instead of raising, so a TRUE pin is adjudicated against an empty "
        "tree",
        ("open_repo", "real")),
}

# Two floors, failing differently.
#   MIN_SWEEPS  the WALK — a glob that matches nothing reports every sweep
#               wired and prints a confident green over zero of them.
#   MIN_WIRED   the AST RESOLUTION — a walk that finds every sweep and credits
#               none looks exactly like nobody having wired any, and the
#               obvious remedy is to pin them all.
MIN_SWEEPS = 15
MIN_WIRED = 15


def tracked_sweeps(root: Path) -> list[str]:
    """The family, as git tracks it. A filesystem walk would count a scratch
    copy somebody left in `scripts/` as a member of the contract.

    ⛔ The guard is `worktree_state.is_checkout`, DELEGATED (Issue 836 T2) —
    and this gate is the sharpest case for it, because the glob fallback
    converts an untracked file into THREE findings. Measured, this repo, one
    untracked `zz_scratch_drift_sweep.py` planted in a worktree's `scripts/`:
    `✗ UNWIRED [worktree-advisory] · [known-extra-exemption] ·
    [head-provenance]`, each telling the reader to wire a sweep that is not in
    the family. With the delegation the worktree run is byte-identical to the
    ordinary one (21 sweeps, PASSED, both)."""
    if not worktree_state.is_checkout(root):
        return sorted(p.name for p in (root / "scripts").glob(GLOB))
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "scripts/" + GLOB],
        capture_output=True, encoding="utf-8", errors="replace")
    if out.returncode != 0:
        return sorted(p.name for p in (root / "scripts").glob(GLOB))
    return sorted(Path(p).name for p in out.stdout.split() if p.strip())


def calls_any(src: str, names: tuple[str, ...]) -> bool:
    """Does this module CALL one of `names`, not merely mention it?

    AST, not text, for the reason `subprocess_encoding_gate` moved to one: a
    text scanner reports the fixture strings inside this file's own arms, and
    the repairs on offer are to exempt the gate from itself or to obfuscate its
    test data. An exempt gate certifies nothing.

    An IMPORT alone is not enough either — an unused import is exactly what a
    half-finished wiring looks like, and it is the state the two Issue-797
    stragglers would have been in had somebody started and stopped.
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = (fn.id if isinstance(fn, ast.Name)
                else fn.attr if isinstance(fn, ast.Attribute) else "")
        if name in names:
            return True
    return False


def parse_pins(path: Path) -> tuple[dict[tuple[str, str], str], list[str]]:
    """({(mechanism, sweep): reason}, errors). Reasonless row = ERROR, not pin.

    Issue 824 keyed this by MECHANISM as well as sweep. A blanket per-sweep
    exemption would excuse a sweep from the NEXT mechanism too — the one
    nobody has looked at — which is the `DOCS_GATE_KNOWN_EXTRA` asymmetry
    (names, never `=1`) applied to this file. The format change was free: the
    file is, and should stay, empty.
    """
    pins: dict[tuple[str, str], str] = {}
    errs: list[str] = []
    if not path.is_file():
        return pins, errs
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        body, _, reason = line.partition("#")
        parts, reason = body.split(), reason.strip()
        if len(parts) != 2:
            errs.append(f"{path.name}:{n}: want `<mechanism> <sweep>  # reason`, "
                        f"got {body.strip()!r} — an unqualified row would "
                        f"excuse the next mechanism too")
            continue
        slug, name = parts
        if slug not in MECHANISMS:
            errs.append(f"{path.name}:{n}: unknown mechanism {slug!r} — "
                        f"known: {', '.join(sorted(MECHANISMS))}")
            continue
        if not reason:
            errs.append(f"{path.name}:{n}: `{slug} {name}` has NO reason — a "
                        f"row nobody had to justify is a backlog wearing a pin")
            continue
        pins[(slug, name)] = reason
    return pins, errs


def verdict(root: Path, pins: dict[tuple[str, str], str]) -> tuple[
        dict[str, list[str]], dict[str, list[str]],
        list[tuple[str, str]], int]:
    """({slug: wired}, {slug: unwired}, stale_pins, n_sweeps) for one repo.

    Per MECHANISM (Issue 824). Pooling the mechanisms would reproduce the very
    defect this gate exists to stop — a sweep wired for one and not the other
    reads as wired, which is exactly how `pin_row_exempt` reached 16 of 19
    while the advisory reached all of them.
    """
    sweeps = tracked_sweeps(root)
    srcs: dict[str, str] = {}
    for name in sweeps:
        f = root / "scripts" / name
        if f.is_file():
            srcs[name] = f.read_text(encoding="utf-8", errors="replace")
    wired: dict[str, list[str]] = {}
    unwired: dict[str, list[str]] = {}
    for slug, (_why, names) in MECHANISMS.items():
        wired[slug] = [n for n, s in srcs.items() if calls_any(s, names)]
        unwired[slug] = [n for n in srcs if n not in wired[slug]]
    # A pin whose sweep is wired for THAT mechanism, or gone, no longer
    # describes anything. Both directions red: the file must not be allowed to
    # only ever loosen.
    stale = [(slug, n) for (slug, n) in pins
             if slug in MECHANISMS and (n in wired[slug] or n not in sweeps)]
    return wired, unwired, stale, len(sweeps)


# ───────────────────────────── arms ───────────────────────────────────────

def _fixture(tmp: Path, bodies: dict[str, str]) -> Path:
    root = tmp / "repo"
    (root / "scripts").mkdir(parents=True)
    for name, body in bodies.items():
        (root / "scripts" / name).write_text(body, encoding="utf-8")
    return root


WIRED_SRC = ("from worktree_state import sweep_advisory\n"
             "def main():\n"
             "    deferred.extend(sweep_advisory(names, ('*.rs',), root=W))\n")
IMPORT_ONLY_SRC = ("from worktree_state import sweep_advisory\n"
                   "def main():\n"
                   "    pass\n")
MENTION_ONLY_SRC = ('S = "call sweep_advisory here one day"\n'
                    "def main():\n"
                    "    pass\n")
# Issue 824. A sweep wired for ONE mechanism and not the other is the exact
# state 16 of 19 were in, and a pooled predicate reports it as wired.
EXEMPT_ONLY_SRC = ("from sweep_population import pin_row_exempt\n"
                   "def main():\n"
                   "    if not pin_row_exempt(name):\n"
                   "        fails.append('unpinned')\n")
# ⛔ DERIVED from the registry, not typed. Issue 822 T6 added a third mechanism
# and this fixture — a hand-written "fully wired sweep" — was the one place the
# arms did NOT walk `MECHANISMS`, so the gate's own selftest failed on a
# correctly-wired registry and reported the ADDITION as the defect. A fixture
# that has to be edited whenever the thing it tests grows is the same shape as
# the hand-ticked table this mechanism exists to replace.
BOTH_SRC = ("def main():\n"
            + "".join(f"    {names[0]}(a)\n"
                      for _why, names in MECHANISMS.values()))


def classifier_arms() -> list[str]:
    fails: list[str] = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    check(calls_any(WIRED_SRC, WANTED), "a real call was not credited")
    check(not calls_any(IMPORT_ONLY_SRC, WANTED),
          "an IMPORT with no call was credited — that is exactly what a "
          "half-finished wiring looks like")
    check(not calls_any(MENTION_ONLY_SRC, WANTED),
          "a STRING mentioning the name was credited — this gate's own arms "
          "carry such strings, and a text scanner reports them as wiring")
    check(calls_any("import m\ndef f():\n    m.sweep_advisory(a, b)\n", WANTED),
          "a qualified `module.sweep_advisory(...)` call was not credited")
    # ⛔ BOTH directions of the low-level path, and this pair replaces an arm
    # that asserted the OPPOSITE (2026-09-19). That arm pinned "a bare
    # `worktree_advisory(...)` counts", written when the gate's first run
    # condemned `citation_drift_sweep` — the most thoroughly wired member —
    # as UNWIRED. The repair was right about the CALLER and wrong about the
    # REASON: it assumed the two entry points deliver the same thing.
    # `worktree_advisory` only RENDERS what it is handed and asks
    # `behind_origin` nothing, so the sweep on that path had the worktree
    # axis and NO upstream axis — measured, it reported a CROSS finding
    # whose repair was already on origin, with no STALE line. An arm that
    # pins a false premise is worse than no arm: it makes the defect a
    # REQUIREMENT.
    check(not calls_any("def f():\n    worktree_advisory(s, u, m)\n", WANTED),
          "a bare `worktree_advisory(...)` was credited — it RENDERS what it "
          "is handed and asks `behind_origin` nothing, so a sweep on that "
          "path silently has no STALE and no UNVERIFIED")
    check(calls_any("def f():\n    a, b = upstream_axis(r, p)\n"
                    "    worktree_advisory(s, u, m, stale=a, unverified=b)\n",
                    WANTED),
          "the low-level path WITH the extracted upstream half was not "
          "credited: a sweep computing its own sharper scope is the careful "
          "caller, and condemning it is the criterion being wrong again")
    check(not calls_any("def f(:\n", WANTED),
          "an UNPARSED module was credited — silence is not evidence")
    # ── Issue 824: the mechanisms must be INDEPENDENT ─────────────────────
    # Walked from the registry rather than hard-coded, so a mechanism added
    # later is armed by EXISTING — which is the whole reason this gate was
    # generalised instead of copied.
    for slug, (_why, names) in MECHANISMS.items():
        others = [n for s, (_w, ns) in MECHANISMS.items() if s != slug
                  for n in ns]
        src = f"def f():\n    {names[0]}(a)\n"
        check(calls_any(src, names), f"[{slug}] its own call was not credited")
        check(not calls_any(src, tuple(others)),
              f"[{slug}] calling it credited a DIFFERENT mechanism — pooling "
              f"is exactly how `pin_row_exempt` sat in 16 of 19 sweeps while "
              f"every one of them read as wired")
    check(calls_any(EXEMPT_ONLY_SRC, MECHANISMS["known-extra-exemption"][1]),
          "a real pin_row_exempt() call was not credited")
    check(not calls_any(EXEMPT_ONLY_SRC, WANTED),
          "a sweep wired ONLY for the exemption was credited with the "
          "advisory — the precise shape Issue 824 found in 3 of 19")
    check(all(calls_any(BOTH_SRC, ns) for _w, ns in MECHANISMS.values()),
          "a fully-wired sweep was not credited for every mechanism")
    return fails


def pin_arms() -> list[str]:
    """The gate's own pin arithmetic, which the classifier cannot reach."""
    fails: list[str] = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        f = tmp / "pins.txt"

        f.write_text("# comment\n\nworktree-advisory a_drift_sweep.py  "
                     "# deliberate: reason here\n", encoding="utf-8")
        pins, errs = parse_pins(f)
        check(pins == {("worktree-advisory", "a_drift_sweep.py"):
                       "deliberate: reason here"} and not errs,
              f"a well-formed pin did not parse: {pins} {errs}")

        f.write_text("worktree-advisory b_drift_sweep.py\n", encoding="utf-8")
        pins, errs = parse_pins(f)
        check(pins == {} and len(errs) == 1,
              f"a REASONLESS row was accepted as a pin: {pins} {errs}")

        # Issue 824: an UNQUALIFIED row is refused. It would excuse the sweep
        # from the NEXT mechanism too — the one nobody has looked at — which is
        # the DOCS_GATE_KNOWN_EXTRA asymmetry (names, never `=1`) one file over.
        f.write_text("c_drift_sweep.py  # no mechanism named\n", encoding="utf-8")
        pins, errs = parse_pins(f)
        check(pins == {} and len(errs) == 1,
              f"an UNQUALIFIED pin row was accepted: {pins} {errs}")

        # …and a row naming a mechanism that does not exist is an error, not a
        # silently-ignored line: a typo'd slug would otherwise pin nothing while
        # reading as a deliberate exemption.
        f.write_text("no-such-mechanism d_drift_sweep.py  # typo\n",
                     encoding="utf-8")
        pins, errs = parse_pins(f)
        check(pins == {} and len(errs) == 1,
              f"an UNKNOWN mechanism slug was accepted: {pins} {errs}")

        pins, errs = parse_pins(tmp / "absent.txt")
        check((pins, errs) == ({}, []),
              "an absent pin file was an error rather than an empty set")

        # ── the verdict, over a synthetic family ──────────────────────────
        ADV, EXE = "worktree-advisory", "known-extra-exemption"
        root = _fixture(tmp, {
            "x_drift_sweep.py": BOTH_SRC,
            "y_drift_sweep.py": MENTION_ONLY_SRC,
            "not_a_sweep.py": MENTION_ONLY_SRC,
        })
        wired, unwired, stale, n = verdict(root, {})
        check(n == 2 and all(wired[s] == ["x_drift_sweep.py"] for s in wired)
              and all(unwired[s] == ["y_drift_sweep.py"] for s in unwired),
              f"the verdict mis-partitioned: {wired} {unwired} {n}")
        check(all("not_a_sweep.py" not in wired[s] + unwired[s] for s in wired),
              "a non-sweep entered the population")

        # ⛔ Issue 824's own defect, as an arm: a sweep wired for the advisory
        # and NOT the exemption must read UNWIRED for the exemption alone. A
        # pooled verdict calls it wired, which is how 3 of 19 went unnoticed
        # through a close-out that said "16".
        half = _fixture(tmp / "half", {"h_drift_sweep.py": WIRED_SRC})
        wired, unwired, _, _ = verdict(half, {})
        check(wired[ADV] == ["h_drift_sweep.py"] and unwired[ADV] == [],
              f"the advisory half was not credited: {wired[ADV]}")
        check(unwired[EXE] == ["h_drift_sweep.py"] and wired[EXE] == [],
              f"a sweep missing the EXEMPTION read as wired — the pooled "
              f"verdict Issue 824 exists to prevent: {wired[EXE]}")

        # A pin removes the unwired row from the finding set …
        _, unwired, stale, _ = verdict(root, {(ADV, "y_drift_sweep.py"): "r"})
        check(unwired[ADV] == ["y_drift_sweep.py"] and stale == [],
              f"a pinned row was not still reported as unwired: {unwired[ADV]}")
        # … and it does so for THAT mechanism only: the same sweep is still an
        # unpinned finding under the other one.
        check(unwired[EXE] == ["y_drift_sweep.py"],
              "a pin excused a mechanism it did not name")
        # … and a pin on a WIRED sweep is STALE, which reds. This is the
        # direction a pin file left to loosen would never catch.
        _, _, stale, _ = verdict(root, {(ADV, "x_drift_sweep.py"): "r"})
        check(stale == [(ADV, "x_drift_sweep.py")],
              f"a pin on an already-wired sweep did not read STALE: {stale}")
        # A pin naming a sweep that no longer exists is stale too.
        _, _, stale, _ = verdict(root, {(ADV, "gone_drift_sweep.py"): "r"})
        check(stale == [(ADV, "gone_drift_sweep.py")],
              f"a pin for a DELETED sweep did not read STALE: {stale}")

        # The walk floor's premise: an empty family must not read as perfect.
        empty = _fixture(tmp / "e", {"not_a_sweep.py": WIRED_SRC})
        _, _, _, n = verdict(empty, {})
        check(n == 0, f"an empty family did not report 0 sweeps: {n}")
        check(MIN_SWEEPS > 0 and MIN_WIRED > 0,
              "a floor of 0 is not a floor — an empty walk would pass")
    return fails


def walk_arms() -> list[str]:
    """`tracked_sweeps` against a REAL git tree, both branches.

    The synthetic fixtures below have no `.git`, so they take the FALLBACK
    walk and the `git ls-files` half was reached by nothing — measured by
    `arm_reach_audit`, four live survivors in one function. Its whole documented
    purpose lives on that branch: a scratch copy somebody left in `scripts/` is
    not a member of the contract, and only git can say so.
    """
    fails: list[str] = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    def git(cwd, *args):
        subprocess.run(["git", "-C", str(cwd), *args], check=True,
                       capture_output=True)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "repo"
        (root / "scripts").mkdir(parents=True)
        (root / "scripts" / "a_drift_sweep.py").write_text(WIRED_SRC,
                                                           encoding="utf-8")
        (root / "scripts" / "helper.py").write_text(WIRED_SRC, encoding="utf-8")
        git(root, "init", "-q", "-b", "main")
        git(root, "config", "user.email", "t@t")
        git(root, "config", "user.name", "t")
        git(root, "add", "-A")
        git(root, "commit", "-qm", "init")

        check(tracked_sweeps(root) == ["a_drift_sweep.py"],
              f"the tracked walk did not return the committed sweep: "
              f"{tracked_sweeps(root)}")

        # The branch's REASON: an untracked scratch copy is not a member.
        (root / "scripts" / "zz_scratch_drift_sweep.py").write_text(
            MENTION_ONLY_SRC, encoding="utf-8")
        check(tracked_sweeps(root) == ["a_drift_sweep.py"],
              f"an UNTRACKED scratch copy entered the population — that is "
              f"exactly what asking git instead of the filesystem is for: "
              f"{tracked_sweeps(root)}")
        # …and the fallback, one directory over, DOES see it. Both halves, so
        # the arm cannot pass by taking the branch it was not aimed at.
        nogit = Path(td) / "extracted"
        (nogit / "scripts").mkdir(parents=True)
        (nogit / "scripts" / "zz_scratch_drift_sweep.py").write_text(
            MENTION_ONLY_SRC, encoding="utf-8")
        check(tracked_sweeps(nogit) == ["zz_scratch_drift_sweep.py"],
              f"the no-.git FALLBACK did not walk the filesystem \u2014 an extracted "
              f"tree is a legitimate population, not an error: "
              f"{tracked_sweeps(nogit)}")

        # Issue 836 T2 — the THIRD branch: a checkout whose `.git` is a FILE.
        # Both arms above pass under EITHER spelling, so without this one a
        # revert to `.is_dir()` is silent — and here the fallback's cost is
        # three findings per untracked file, one per MECHANISM, each telling
        # the reader to wire a sweep that is not in the family.
        _main, wt = worktree_state.worktree_fixture(
            Path(td) / "wtf", tracked="scripts/a_drift_sweep.py",
            untracked="scripts/zz_scratch_drift_sweep.py")
        check((wt / ".git").is_file(),
              "the fixture's .git is not a FILE — `git worktree add` no longer "
              "produces the shape this arm is about, so it asserts nothing")
        check(tracked_sweeps(wt) == ["a_drift_sweep.py"],
              f"in a WORKTREE the walk fell back to the filesystem and counted "
              f"an untracked scratch sweep as a family member: "
              f"{tracked_sweeps(wt)}. The guard is `is_checkout`, not "
              f"`.git`.is_dir() — Issue 836")

        # The verdict end-to-end over the real tree, so the git branch is
        # reached by the PRODUCTION path and not only by the helper.
        wired, unwired, stale, n = verdict(root, {})
        check(n == 1 and wired["worktree-advisory"] == ["a_drift_sweep.py"],
              f"the verdict over a real git tree disagreed with the walk: "
              f"{wired} {unwired} {n}")
    return fails


def selftest() -> list[str]:
    return classifier_arms() + pin_arms() + walk_arms()


def main() -> int:
    fails = selftest()
    if fails:
        print("✗ sweep-advisory membership gate SELFTEST FAILED — instrument "
              "untrustworthy:")
        for f in fails:
            print("    ✗ " + f)
        return 2

    pins, errs = parse_pins(PINS)
    for e in errs:
        print("✗ " + e)
    wired, unwired, stale, n = verdict(REPO_ROOT, pins)

    if n < MIN_SWEEPS:
        print(f"✗ INSTRUMENT: the walk found {n} sweep(s) < floor {MIN_SWEEPS} "
              f"— the family went blind and every row below passes vacuously")
        return 2
    if min(len(v) for v in wired.values()) < MIN_WIRED:
        thin = min(wired, key=lambda s: len(wired[s]))
        print(f"✗ INSTRUMENT: {thin} has {len(wired[thin])} wired < floor "
              f"{MIN_WIRED} — a walk "
              f"that finds every sweep and credits none looks exactly like "
              f"nobody having wired any, and the obvious remedy is to pin "
              f"them all")
        return 2

    bad = bool(errs)
    for slug, name in stale:
        bad = True
        print(f"✗ STALE pin `{slug} {name}` — it is wired now, or gone. Remove "
              f"the row; a pin file that only ever loosens is a backlog")
    for slug, (why, names) in MECHANISMS.items():
        for name in sorted(unwired[slug]):
            if (slug, name) in pins:
                print(f"  · pinned unwired [{slug}]: {name} — "
                      f"{pins[(slug, name)]}")
                continue
            bad = True
            print(f"✗ UNWIRED [{slug}] {name} — it calls none of "
                  f"{'/'.join(w + '()' for w in names)}. {why}. Wire it at the "
                  f"population_verdict() call site, or pin it in "
                  f"{PINS.name} with a reason")

    if bad:
        return 1
    # ⛔ The count and the CLAIM must agree. This read "every one of {n}" with
    # a per-mechanism list beside it, which was true only while the pin file
    # was empty — the first live exemption made the sentence contradict the
    # number three words later. That is `skill_repo_set_gate`'s own recorded
    # defect ("16 of 20 canonical repos" over 13 canonical + 3 extra)
    # committed by this gate's display, and a count that is not a checksum
    # over its own set is what this file exists to object to.
    parts = ", ".join(f"{slug} {len(wired[slug])}" for slug in MECHANISMS)
    every = all(len(wired[slug]) == n for slug in MECHANISMS)
    claim = (f"every one of {n} tracked {GLOB} calls" if every else
             f"each of {n} tracked {GLOB} calls, or is PINNED for,")
    print(f"✓ sweep-advisory membership gate PASSED — {claim} "
          f"each of the {len(MECHANISMS)} family-wide mechanisms "
          f"({parts}; floors {MIN_SWEEPS}/{MIN_WIRED}), "
          f"{len(pins)} pinned exemption(s), 0 stale. ⚠ It does NOT assert the "
          f"patterns name each sweep's own population — that is a per-sweep "
          f"read, not statically decidable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
