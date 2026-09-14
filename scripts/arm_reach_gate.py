#!/usr/bin/env python3
"""The VERDICT half of `arm_reach_audit.py` — Issue 790 T2.

`arm_reach_audit.py` measures, per module, whether that module's own
validation arm NOTICES a mutation of its source. On first measurement that
was a backlog (123 live survivors), and Issue 785's rule forbids ratcheting a
backlog: a ceiling over a pile of unread rows is a number that goes green the
day one row is fixed and another is added.

Issue 790 T3 read all 123 one at a time. **47 remain, every one adjudicated**,
and they fall into three classes that are not defects:

  · provably EQUIVALENT mutants (a `find() < 0` whose search starts after an
    earlier match, so the `<= 0` flip is inert on -1 and unreachable at 0)
  · the git / subprocess I/O SHELL an arm cannot enter without spawning the
    very auditor it reads
  · message-formatting arithmetic, where the mutation changes a printed
    string and no verdict

So the quantity to gate is NOT the count. It is the **SET** — this repo's own
rule, already written for `cfg_gated_floor_gate`: *a set is gateable where its
cardinality is not.* The 47 are pinned by MEMBERSHIP with a REASON per row in
`scripts/arm_reach_survivors_expected.txt`, and the wall is **0 UNPINNED
survivors**. A ratchet would tolerate a new unreached decision line as long as
somebody armed an old one; membership does not.

⛔ **Reds in BOTH directions.** A pinned row whose arm now reaches it is a
finding too: the row and its repair belong in the same commit, exactly as
`instrument_unreferenced_expected.txt` requires. A count would be green on the
swap.

## The key is LINE-FREE, and that is not a stylistic choice

A survivor's line NUMBER drifts on every edit above it, so a line-numbered pin
file reds on commits that changed nothing about it — and a pin file that reds
on noise is one people delete. The key is

    <module>::<function>::<operator-token>::<8-hex digest of the line TEXT>#<n>

with `#<n>` an ordinal **within that whole address**, the
`len_derived_eyes_expected.txt` precedent ("keyed line-free on (repo, file,
kernel, handle) plus a count within that address, because the key is not
unique in general"). Scoping the ordinal to the 4-tuple rather than to
`(module, function, operator)` is what keeps it stable: adding a new `>=` site
to a function shifts nothing, because it hashes differently. Only genuinely
DUPLICATE line text inside one function shares an ordinal sequence.

The digest is unreadable by design and the row therefore carries the source
line in a `#= ` trailing comment — **which the gate VERIFIES against the
observed text.** A comment is the part of a pin file a human actually reads,
and a comment nothing can red is a comment that drifts into a lie. That is
this issue's own lesson turned on its own pin file.

## Why this is not a `docs_gate.sh` CHECK

Cost. The audit re-execs a module once per mutant and several gates now build
fixture repos per arm, so a full run is minutes against the docs gate's ~13s
budget. It is a WORKSTATION verdict, on demand, the same standing as the
eleven cross-repo drift sweeps — and it is reachable from AGENTS.md, so
`instrument_reachability_gate.py` counts it.

There is deliberately **no `--prove-fires`**: the known-answer validation would
be a full mutation run over a `git archive`d tree, minutes per invocation, to
re-derive a fact already recorded in the issue. The canary arms carry that
weight instead, two-sided over synthetic survivor sets whose answer is known.

## The permissive directions, which a floor alone does not guard

Two sets live in the AUDIT and silently SHRINK the finding set when they grow:
`EXEMPT_FUNCTIONS` (a name added there removes every survivor in that
function) and `ARM_NAMES` (a name added there makes more source an arm BODY,
and arm bodies are never mutated). Neither is guarded by a mutant floor —
adding `main` to `ARM_NAMES` would look like a tidy-up. Both are pinned here
by MEMBERSHIP, which is `check_validation_gate.py`'s finding about its own
`ARM_NAMES`, one instrument over.
"""

from __future__ import annotations

import ast
import hashlib
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import arm_reach_audit as A  # noqa: E402

EXPECTED = HERE / "arm_reach_survivors_expected.txt"

# Blindness floors. Neither is redundant and they fail differently:
#   MIN_MODULES  the population walk (a verdict over zero modules is perfect)
#   MIN_MUTANTS  the operators (a harness generating no mutants has no
#                survivors, so every pin reads "gone" — which reds, but for
#                the wrong reason and with a misleading remedy)
#   MIN_KILLED   the RUNNER. If `run_arm` started reporting KILLED for
#                everything the survivor set would empty out; the pins would
#                all red as "gone" and the obvious repair is to delete them.
#                A killed FLOOR names the instrument instead.
MIN_MODULES = 15
MIN_MUTANTS = 200
MIN_KILLED = 150

# The two permissive sets in the audit, pinned by MEMBERSHIP. See the module
# docstring: growth in either one SHRINKS the finding set and no count notices.
EXPECTED_EXEMPT = {"main"}
EXPECTED_ARM_NAMES = {
    "selftest", "self_test", "selftest_scoping", "canary", "gate_selftest",
    "prove_fires",
}

# desc string -> a whitespace-free token, because the pin file splits on
# whitespace. Kept as an explicit table rather than derived by mangling: a
# mangler silently invents a token for an operator nobody has pinned, and the
# unknown-operator refusal below is how a new operator announces itself.
OP_TOKEN = {
    "== -> !=": "eq2ne", "!= -> ==": "ne2eq",
    "< -> <=": "lt2le", "<= -> <": "le2lt",
    "> -> >=": "gt2ge", ">= -> >": "ge2gt",
    "in -> not in": "in2notin", "not in -> in": "notin2in",
    "and -> or": "and2or", "or -> and": "or2and",
    "drop `not`": "dropnot",
    "True -> False": "true2false", "False -> True": "false2true",
    "- -> +": "sub2add", "+ -> -": "add2sub",
}

COMMENT_MARK = "  #= "


def digest(text: str) -> str:
    """8 hex chars over the STRIPPED source line.

    Short on purpose: it is an identity token inside a key already scoped by
    module and function, not a security primitive. A collision inside one
    function is resolved by the ordinal, exactly as duplicate text is.
    """
    return hashlib.blake2s(text.encode("utf-8"), digest_size=4).hexdigest()


def build_keys(rows: list[tuple[str, str, str, str]]) -> dict[str, str]:
    """[(module, func, desc, line_text)] -> {key: line_text}.

    The ordinal is scoped to the FULL address including the text digest, so a
    new mutation site never renumbers an unrelated one. Input order is made
    irrelevant by sorting first: the audit walks the AST breadth-first and a
    refactor that moves a function would otherwise reshuffle every ordinal.
    """
    out: dict[str, str] = {}
    seen: dict[str, int] = {}
    for module, func, desc, text in sorted(rows):
        token = OP_TOKEN.get(desc)
        if token is None:
            raise ValueError(
                f"unknown mutation operator {desc!r} — a new operator was "
                f"added to arm_reach_audit without a token here, and a "
                f"mangled fallback would invent a key nobody pinned")
        addr = f"{module}::{func}::{token}::{digest(text)}"
        n = seen[addr] = seen.get(addr, 0) + 1
        out[f"{addr}#{n}"] = text
    return out


def parse_expected(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    """-> ({key: reason}, {key: commented line text}).

    The reason is REQUIRED and a reasonless row is refused: an exemption
    nobody can adjudicate reads as coverage while asserting nothing, which is
    strictly worse than a missing row (AGENTS.md, the `required-features`
    rule, one axis over).

    The `#= ` comment is split off FIRST and from the RIGHT, because a pinned
    source line may itself contain `#` — `if "#" in line:` is a real decision
    in three modules here. A line whose text contains the marker itself
    truncates and then fails the digest check, which is the safe direction.
    """
    rows: dict[str, str] = {}
    texts: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        body, mark, commented = raw.rpartition(COMMENT_MARK)
        if not mark:
            body, commented = raw, ""
        parts = body.strip().split(None, 1)
        if len(parts) != 2 or not parts[1].strip():
            raise ValueError(
                f"malformed pin row (want `<key>  <reason>`): {raw!r}")
        key = parts[0]
        if key in rows:
            raise ValueError(f"duplicate pin key: {key}")
        rows[key] = parts[1].strip()
        if commented:
            texts[key] = commented.rstrip()
    return rows, texts


def verdict_problems(observed: dict[str, str], pinned: dict[str, str],
                     unreached: list[str], no_arm: list[str]) -> list[str]:
    """The WALL, as a pure function so an arm can reach it.

    Issue 790 T4's finding, applied to this file on the way in: in every
    module read, the classifier was well armed and the VERDICT was not —
    because the verdict arithmetic sat inline in `main()` beside its own
    error messages, unreachable by construction.
    """
    problems: list[str] = []
    for key in sorted(set(observed) - set(pinned)):
        problems.append(
            f"UNPINNED survivor: {key}\n"
            f"        {observed[key]}\n"
            f"      No arm distinguishes this line's behaviour. Widen an arm, "
            f"or pin it with a reason if it is EQUIVALENT / unreachable I/O.")
    for key in sorted(set(pinned) - set(observed)):
        problems.append(
            f"pinned row no longer survives: {key}\n"
            f"      ({pinned[key]})\n"
            f"      An arm reaches it now, or the line changed. Remove the "
            f"row in the commit that reached it — a stale pin hides the next "
            f"survivor at that address.")
    for name in sorted(unreached):
        problems.append(
            f"UNREACHED module: {name} — its arm killed ZERO mutants, so it "
            f"distinguishes nothing these operators can express. Issue 790 T3 "
            f"took this bucket to 0 and it is walled there.")
    for name in sorted(no_arm):
        problems.append(
            f"NO-ARM module: {name} — no arm of its own, so every mutant "
            f"survives VACUOUSLY. Issue 790 T4 took this bucket to 0 by giving "
            f"all four delegating gates a `gate_selftest`; a classifier's "
            f"self-test cannot reach its consumer's pin arithmetic (Issue 775).")
    return problems


def comment_problems(pinned_texts: dict[str, str],
                     observed: dict[str, str]) -> list[str]:
    """A pin row's `#= ` comment must match the line it pins.

    The key carries a DIGEST, which is unreadable, so the comment is the only
    part of this file a human adjudicates from. A comment nothing can red is a
    comment that drifts into a lie — this issue's own lesson, turned on its
    own pin file.
    """
    problems = []
    for key, commented in sorted(pinned_texts.items()):
        actual = observed.get(key)
        if actual is not None and commented != actual:
            problems.append(
                f"stale `#= ` comment on {key}\n"
                f"        pinned:   {commented}\n"
                f"        observed: {actual}")
    return problems


def floor_problems(n_modules: int, n_mutants: int, n_killed: int,
                   exempt: set[str], arm_names: set[str]) -> list[str]:
    """Blindness floors AND the two permissive-set membership pins.

    The floors and the memberships are in one function because they answer one
    question — *is the measurement underneath the verdict trustworthy?* — and
    splitting them invites arming one and not the other.
    """
    problems = []
    if n_modules < MIN_MODULES:
        problems.append(
            f"walk FLOOR breached: {n_modules} module(s) < {MIN_MODULES} — the "
            f"population went blind and a verdict over a handful of modules "
            f"is not a verdict over the CHECKS set")
    if n_mutants < MIN_MUTANTS:
        problems.append(
            f"mutant FLOOR breached: {n_mutants} < {MIN_MUTANTS} — the "
            f"operators stopped firing. Every pin would read `no longer "
            f"survives` and the obvious remedy is to delete them all")
    if n_killed < MIN_KILLED:
        problems.append(
            f"killed FLOOR breached: {n_killed} < {MIN_KILLED} — the RUNNER is "
            f"the suspect, not the pins. A runner that reports KILLED for "
            f"everything empties the survivor set and reds every row with a "
            f"misleading remedy")
    if exempt != EXPECTED_EXEMPT:
        problems.append(
            f"arm_reach_audit.EXEMPT_FUNCTIONS drifted: "
            f"{sorted(exempt)} != {sorted(EXPECTED_EXEMPT)} — this is the "
            f"PERMISSIVE direction. Every name added there deletes every "
            f"survivor in that function from the finding set, and no floor "
            f"notices")
    if arm_names != EXPECTED_ARM_NAMES:
        problems.append(
            f"arm_reach_audit.ARM_NAMES drifted: {sorted(arm_names)} != "
            f"{sorted(EXPECTED_ARM_NAMES)} — also PERMISSIVE: arm bodies are "
            f"never mutated, so a name added there turns decision code into "
            f"unwatched code. `check_validation_gate` found the same shape in "
            f"its own vocabulary")
    return problems


def measure(only: list[str] | None = None) -> dict:
    """Run the audit and reduce it to what the verdict needs.

    The population is the `docs_gate.sh` CHECKS set **plus this file**. The
    `+ this file` is not symmetry for its own sake: an exempt gate certifies
    nothing (`subprocess_encoding_gate`'s rule, which was forced when that gate
    reported four offenders inside its own fixtures), and this one is a
    `scripts/*.py` with an arm exactly like the modules it judges. It found a
    degenerate arm in its OWN key builder on the first self-hosted run — the
    ordinal counter's `+ 1` flipped to `- 1` still yields two distinct keys, so
    a count-only assertion read green.
    """
    paths = A.population(include_all=False)
    me = Path(__file__).resolve()
    if me not in {p.resolve() for p in paths}:
        paths = list(paths) + [me]
    if only:
        paths = [p for p in paths if any(o in p.name for o in only)]
    rows, unreached, no_arm, survivors = {}, [], [], []
    killed = mutants = 0
    for path in sorted(paths):
        r = A.audit_module(path)
        rows[path.name] = r
        if r.get("error"):
            continue
        mutants += r["total"]
        if not (set(r["arms"]) & A.RUN_ARMS):
            no_arm.append(path.name)
            continue
        killed += r["killed"]
        if r["killed"] == 0 and r["total"] > 0:
            unreached.append(path.name)
        src = path.read_text(encoding="utf-8").splitlines()
        for func, ln, desc in r["survived"]:
            if func in A.EXEMPT_FUNCTIONS:
                continue
            text = src[ln - 1].strip() if 0 < ln <= len(src) else ""
            survivors.append((path.name, func, desc, text))
    return {
        "modules": len(rows), "mutants": mutants, "killed": killed,
        "unreached": unreached, "no_arm": no_arm,
        "errored": [n for n, r in rows.items() if r.get("error")],
        "observed": build_keys(survivors),
    }


def gate_selftest() -> list[str]:
    """Canary arms over this gate's OWN arithmetic.

    Issue 775's sentence, which Issue 790 T4 spent its whole budget on: a
    classifier's self-test cannot reach its consumer's pin arithmetic. The
    classifier here is `arm_reach_audit`, whose `--self-test` says nothing
    about the key builder, the pin parser or the wall below.
    """
    import tempfile
    f: list[str] = []

    # ── 1. the key is stable against LINE MOVEMENT, which is the whole point.
    a = build_keys([("m.py", "g", ">= -> >", "if n >= floor:")])
    b = build_keys([("m.py", "g", ">= -> >", "if n >= floor:")])
    if a != b:
        f.append("key: not deterministic")
    if len(next(iter(a)).split("::")) != 4:
        f.append("key: shape is not module::func::op::digest#n")

    # ── 2. …and it DISCRIMINATES text, operator, function and module. Four
    # arms, because a key that ignores any one field silently merges two rows
    # and the second one stops being gated.
    base = ("m.py", "g", ">= -> >", "if n >= floor:")
    for label, row in (
        ("text", ("m.py", "g", ">= -> >", "if k >= floor:")),
        ("operator", ("m.py", "g", "> -> >=", "if n >= floor:")),
        ("function", ("m.py", "h", ">= -> >", "if n >= floor:")),
        ("module", ("n.py", "g", ">= -> >", "if n >= floor:")),
    ):
        if set(build_keys([base])) == set(build_keys([row])):
            f.append(f"key: does not discriminate {label}")

    # ── 3. the ORDINAL is scoped to the FULL address. Adding a DIFFERENT site
    # with the same operator must NOT renumber an existing one — that is the
    # difference between this file and a line-numbered one, and it is the
    # reason the digest is in the key at all.
    one = build_keys([base])
    two = build_keys([base, ("m.py", "g", ">= -> >", "if z >= cap:")])
    if not set(one) <= set(two):
        f.append("ordinal: an unrelated new site renumbered an existing key")
    # DUPLICATE text in one function does share a sequence — the case the
    # ordinal exists for. ⚠ Asserting only the COUNT here was degenerate and
    # this gate's own self-hosted run caught it: flipping the `+ 1` counter to
    # `- 1` yields `#-1` and `#-2`, still two distinct keys, and the arm read
    # green. The ordinal VALUES are the assertion.
    dup = build_keys([base, base])
    if sorted(k.rpartition("#")[2] for k in dup) != ["1", "2"]:
        f.append(f"ordinal: duplicate text numbered {sorted(dup)}, want #1/#2")
    if not all(k.endswith("#1") for k in one):
        f.append(f"ordinal: a lone site is not #1: {sorted(one)}")

    # ── 4. input ORDER is irrelevant (the audit walks breadth-first; moving a
    # function would otherwise reshuffle every ordinal in the file).
    x, y = ("m.py", "g", ">= -> >", "aaa"), ("m.py", "g", ">= -> >", "bbb")
    if build_keys([x, y]) != build_keys([y, x]):
        f.append("key: ordinal depends on input order")

    # ── 5. an operator with no token is REFUSED, never mangled into a key.
    try:
        build_keys([("m.py", "g", "?? -> !!", "x")])
        f.append("key: unknown operator was not refused")
    except ValueError:
        pass

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "pins.txt"

        # ── 6. the pin parser: comments, blanks, reason REQUIRED, `#= ` text.
        p.write_text(
            "# a header\n"
            "\n"
            "m.py::g::ge2gt::deadbeef#1  EQUIVALENT: floor is never equal"
            "  #= if n >= floor:\n",
            encoding="utf-8")
        rows, texts = parse_expected(p)
        if rows != {"m.py::g::ge2gt::deadbeef#1":
                    "EQUIVALENT: floor is never equal"}:
            f.append(f"pin parse: wrong rows {rows}")
        if texts != {"m.py::g::ge2gt::deadbeef#1": "if n >= floor:"}:
            f.append(f"pin parse: wrong `#= ` text {texts}")

        # ── 7. a reasonless row is REFUSED. A bare key reads as coverage.
        p.write_text("m.py::g::ge2gt::deadbeef#1\n", encoding="utf-8")
        try:
            parse_expected(p)
            f.append("pin parse: reasonless row accepted")
        except ValueError:
            pass

        # ── 8. a DUPLICATE key is refused: the second reason is dead text and
        # whichever one is wrong can never be found by reading the file.
        p.write_text("k  reason one\nk  reason two\n", encoding="utf-8")
        try:
            parse_expected(p)
            f.append("pin parse: duplicate key accepted")
        except ValueError:
            pass

        # ── 9. a pinned line containing `#` survives the comment split. Three
        # modules here really do decide on `#`, and splitting from the LEFT
        # would eat the reason and report a malformed row.
        p.write_text('k  a reason  #= if "#" in line:\n', encoding="utf-8")
        rows, texts = parse_expected(p)
        if rows.get("k") != "a reason" or texts.get("k") != 'if "#" in line:':
            f.append(f"pin parse: `#` in pinned text broke the split: "
                     f"{rows} {texts}")

    # ── 10. the WALL, both directions, and NEITHER may be silent.
    obs = {"k1": "line one", "k2": "line two"}
    if verdict_problems(obs, {"k1": "r", "k2": "r"}, [], []):
        f.append("wall: a fully pinned set is not clean")
    if not any("UNPINNED" in p for p in
               verdict_problems(obs, {"k1": "r"}, [], [])):
        f.append("wall: an UNPINNED survivor passed")
    if not any("no longer survives" in p for p in
               verdict_problems({"k1": "x"}, {"k1": "r", "k9": "r"}, [], [])):
        f.append("wall: a stale pin passed — the gate is one-directional")

    # ── 11. UNREACHED and NO-ARM are walled SEPARATELY. Pooling either into
    # the survivor count is what Issue 790's bucket note forbids, and a gate
    # that only counts survivors is green on a module whose arm died entirely.
    if not any("UNREACHED" in p for p in verdict_problems({}, {}, ["m.py"], [])):
        f.append("wall: an UNREACHED module passed")
    if not any("NO-ARM" in p for p in verdict_problems({}, {}, [], ["m.py"])):
        f.append("wall: a NO-ARM module passed")

    # ── 12. the `#= ` comment is VERIFIED, not decoration.
    if comment_problems({"k": "if a > b:"}, {"k": "if a > b:"}):
        f.append("comment: a matching comment was reported stale")
    if not comment_problems({"k": "if a > b:"}, {"k": "if a < b:"}):
        f.append("comment: a stale comment passed")
    # A pin whose row is ALREADY reported as `no longer survives` must not
    # ALSO be reported as a stale comment — one defect, one message.
    if comment_problems({"k": "if a > b:"}, {}):
        f.append("comment: an absent observation was reported stale")

    # ── 13. the floors, each at its exact boundary. Driving a floor to
    # pin-minus-one only proves the comparison fires SOMEWHERE; Issue 790 T3
    # found six of this repo's own arms degenerate for exactly that reason, so
    # every floor here is asserted AT the pin and one below it.
    ok = dict(exempt=EXPECTED_EXEMPT, arm_names=EXPECTED_ARM_NAMES)
    if floor_problems(MIN_MODULES, MIN_MUTANTS, MIN_KILLED, **ok):
        f.append("floors: the exact pin values read as a breach")
    for label, args in (
        ("modules", (MIN_MODULES - 1, MIN_MUTANTS, MIN_KILLED)),
        ("mutants", (MIN_MODULES, MIN_MUTANTS - 1, MIN_KILLED)),
        ("killed", (MIN_MODULES, MIN_MUTANTS, MIN_KILLED - 1)),
    ):
        if not any(label[:6] in p for p in floor_problems(*args, **ok)):
            f.append(f"floors: {label} floor did not fire one below the pin")

    # ── 14. the two PERMISSIVE sets, and the direction that matters is
    # GROWTH: a name added to either one deletes rows from the finding set,
    # and every floor above stays green while it happens.
    grown = floor_problems(MIN_MODULES, MIN_MUTANTS, MIN_KILLED,
                           exempt=EXPECTED_EXEMPT | {"report"},
                           arm_names=EXPECTED_ARM_NAMES)
    if not any("EXEMPT_FUNCTIONS" in p for p in grown):
        f.append("membership: a GROWN exempt set passed")
    grown = floor_problems(MIN_MODULES, MIN_MUTANTS, MIN_KILLED,
                           exempt=EXPECTED_EXEMPT,
                           arm_names=EXPECTED_ARM_NAMES | {"main"})
    if not any("ARM_NAMES" in p for p in grown):
        f.append("membership: `main` added to the arm vocabulary passed")
    # Shrinkage is a finding too — it is not the dangerous direction, but an
    # unannounced narrowing means the pin file below was measured elsewhere.
    if not floor_problems(MIN_MODULES, MIN_MUTANTS, MIN_KILLED,
                          exempt=set(), arm_names=EXPECTED_ARM_NAMES):
        f.append("membership: an EMPTIED exempt set passed")

    # ── 15. the memberships are pinned against the LIVE audit, so this file
    # cannot drift from the module it gates while both self-tests pass.
    if set(A.EXEMPT_FUNCTIONS) != EXPECTED_EXEMPT:
        f.append(f"live audit EXEMPT_FUNCTIONS {sorted(A.EXEMPT_FUNCTIONS)} "
                 f"!= {sorted(EXPECTED_EXEMPT)}")
    if set(A.ARM_NAMES) != EXPECTED_ARM_NAMES:
        f.append(f"live audit ARM_NAMES {sorted(A.ARM_NAMES)} "
                 f"!= {sorted(EXPECTED_ARM_NAMES)}")

    # ── 16. every operator the audit can EMIT has a token here. Without this
    # the refusal in arm 5 is a trap that fires on the next real run instead
    # of in the self-test — and `OP_TOKEN` is read only when a survivor
    # appears at that operator, which may be months later.
    emitted = set(A._CMP_NAME.values())
    for name in sorted(emitted):
        flip = A._CMP_NAME[A._CMP_FLIP[
            next(k for k, v in A._CMP_NAME.items() if v == name)]]
        if f"{name} -> {flip}" not in OP_TOKEN:
            f.append(f"OP_TOKEN missing the comparison `{name} -> {flip}`")
    for desc in ("and -> or", "or -> and", "drop `not`", "True -> False",
                 "False -> True", "- -> +", "+ -> -"):
        if desc not in OP_TOKEN:
            f.append(f"OP_TOKEN missing `{desc}`")
    if len(set(OP_TOKEN.values())) != len(OP_TOKEN):
        f.append("OP_TOKEN: two operators share a token — their keys collide")

    return f


def main(argv: list[str]) -> int:
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass

    if "--canary" in argv[1:]:
        fails = gate_selftest()
        for line in fails:
            print(f"    {line}")
        print(f"{'✗' if fails else '✓'} arm-reach gate canary: "
              f"{len(fails)} failure(s)")
        return 2 if fails else 0

    fails = gate_selftest()
    if fails:
        print("✗ arm-reach gate SELFTEST FAILED — untrustworthy:")
        for line in fails:
            print(f"    {line}")
        return 2

    only = [a for a in argv[1:] if not a.startswith("-")]
    if only:
        print(f"⚠ MODULE FILTER {only} — a PARTIAL run. The membership wall is "
              f"meaningless here (every pin outside the filter reads `no longer "
              f"survives`); use it to iterate on one module, never to claim a "
              f"pass.")

    if not EXPECTED.is_file():
        print(f"✗ pin file missing: {EXPECTED}")
        return 2
    try:
        pinned, pinned_texts = parse_expected(EXPECTED)
    except ValueError as e:
        print(f"✗ pin file unreadable: {e}")
        return 2

    t0 = time.time()
    m = measure(only or None)
    wall = time.time() - t0

    print(f"▸ arm-reach VERDICT over {m['modules']} module(s), "
          f"{m['mutants']} mutant(s), {m['killed']} killed, "
          f"{len(m['observed'])} live survivor(s), {wall:.1f}s")

    if m["errored"]:
        print(f"✗ {len(m['errored'])} module(s) do not parse: "
              f"{', '.join(sorted(m['errored']))} — a classifier that cannot "
              f"read a module reports zero survivors for it, which is "
              f"indistinguishable from a perfect one")
        return 2

    problems: list[str] = []
    if not only:
        problems += floor_problems(
            m["modules"], m["mutants"], m["killed"],
            set(A.EXEMPT_FUNCTIONS), set(A.ARM_NAMES))
        problems += verdict_problems(
            m["observed"], pinned, m["unreached"], m["no_arm"])
    problems += comment_problems(pinned_texts, m["observed"])

    if problems:
        print(f"✗ arm-reach gate: {len(problems)} problem(s)")
        for p in problems:
            print(f"    · {p}")
        print()
        print("  ⚠ SURVIVED is arm REACH, not a defect count. Before writing "
              "an arm, check the two documented false-positive classes: a rule "
              "asserted by a DIFFERENT module's arm reads SURVIVED here "
              "(Issue 755 shares rules across modules deliberately), and an "
              "EQUIVALENT mutant survives correctly.")
        return 1

    print(f"✓ arm-reach gate: {len(m['observed'])} live survivor(s), all "
          f"pinned with a reason; 0 UNREACHED, 0 NO-ARM")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
