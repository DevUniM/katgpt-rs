#!/usr/bin/env python3
"""Hold the restatement-theorem zero across EVERY repo that ships Lean proofs.

`restatement_theorem_audit.py` is a REPORT: it classifies and prints, and a
report holds nothing. The zero it measured on 2026-09-12 (0
RESTATEMENT-INLINE over 4 repos / 68 `.lean` / 255 theorems) was bought by
riir-neuron-db Issue 617 — four theorems removed after four independent probes
each — and until this file existed, nothing would have objected when the fifth
one landed.

This is the sixth instance of one shape in this workspace, and the first two
found real defects the moment they were pointed anywhere but at katgpt-rs:

    Issue 702  ci_gate_coverage              one repo -> 7 dead workflows
    Issue 725  numbering_drift_sweep         one repo -> 35 duplicate numbers
    2026-09-06 required_features_drift_sweep one repo -> clean, and pinned there
    2026-09-06 percentile_drift_sweep        one repo -> clean, and pinned there
    2026-09-07 trap_sentinel_drift_sweep     one repo -> 1 finding, pinned
    this file  restatement_drift_sweep       one repo -> 0, and pinned in four

**Not in `docs_gate.sh`'s CHECKS, deliberately** — same reason as every other
sweep in the family: CI has a single checkout, so the derived population would
be one repo and the sweep would print a confident green over the three that
carry the actual class (riir-neuron-db has 44 composite defs, riir-chain 32,
katgpt-rs **1**). A per-push gate that can only see the repo where the class
barely exists is worse than no gate, because it reads like coverage.

# Two floors, and the second is the one that bites

`max_restatement = 0` is green over whatever the classifier can SEE, and this
classifier has two independent ways to go blind:

  * the WALK — `.proofs` moves, or a repo's proofs are vendored under a name
    the walk skips: file count -> 0, every ceiling passes. `min_lean_files`.
  * the PARSE — a tokenizer or block-splitter regression yields zero theorems
    from a perfectly good tree. The walk is unchanged and only `min_theorems`
    moves. This is not hypothetical: while it was being written, this pass
    went from 0 defs (a `:=` tokenized as `:` + `=`) to 4 findings, with the
    walk identical in both runs.

Both floors sit at ~60% of measured: SLACK against churn (consolidating spec
modules legitimately shrinks a count), TIGHT against blindness (a walk or
tokenizer regression drops these by an order of magnitude, not by a third).

# A ceiling nobody has watched fail is a ceiling of unknown width

`--prove-fires` plants a synthetic restatement into a COPY of each repo's
`.proofs` and requires the verdict to RED, end to end: walk -> parse ->
classify -> compare. It is not a mock — it runs the same `audit_repo` over a
real tree. The historical real-subject probe is recorded in the audit's
docstring: riir-neuron-db at `24957a2^` reports exactly the four theorems
Issue 617 removed, and 0 at HEAD.
"""

import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import restatement_theorem_audit as audit  # noqa: E402
from sweep_population import population_verdict, pin_row_exempt  # noqa: E402
from worktree_state import (HeadDelta, delta_of,  # noqa: E402
                            head_tree, ordinal_keys, sweep_advisory)

FLOORS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "restatement_drift_floors.txt")

CANARY = """import NeuronDbProof.Shard.Layout

namespace RestatementCanary

def alphaSize : Nat := 16
def betaSize : Nat := 24
def totalSize : Nat := alphaSize + betaSize

theorem totalSize_eq_sum : totalSize = alphaSize + betaSize := by decide

end RestatementCanary
"""


def read_floors():
    rows = {}
    with open(FLOORS, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) != 5:
                sys.exit(f"✗ malformed floors row (want 5 fields): {raw.strip()}")
            repo, a, b, c, d = parts
            rows[repo] = dict(min_lean_files=int(a), min_theorems=int(b),
                              max_restatement=int(c), max_identity=int(d))
    if not rows:
        sys.exit("✗ floors file parsed to ZERO rows — a parser that returns "
                 "nothing for both 'absent' and 'malformed' disarms every "
                 "ceiling below it")
    return rows


def measure(repo_path):
    r = audit.audit_repo(repo_path)
    return {
        "files": r["files"],
        "theorems": r["theorems"],
        "restatement": r["counts"][audit.RESTATEMENT],
        "identity": r["counts"][audit.IDENTITY],
        "rows": [x for x in r["rows"]
                 if x[0] in (audit.RESTATEMENT, audit.IDENTITY)],
    }


# ONE list, read by the worktree advisory, by the HEAD trigger and by the
# archive pathspec. `audit_repo` walks `.proofs` with `os.walk` and reads
# `*.lean` and nothing else, which is what makes both the narrowing and this
# constant sound — its inputs are ENUMERABLE.
SCOPE = ("*.lean",)


def untracked_lean(repo_path):
    """Untracked-not-ignored `*.lean`, repo-relative — this sweep's own half.

    ⛔ `audit_repo` walks the FILESYSTEM (`os.walk` over `.proofs`), so an
    untracked theorem file IS in this sweep's population while producing zero
    `git status` dirt — `dirty_files` excludes untracked by design (Issue 777)
    and that is right for every caller whose walk is `git ls-files`. Without
    widening the trigger there is no HEAD to compare against and the row is
    filed COMMITTED, straight into a ceiling: Issue 822's defect in its purest
    form, which `markdown_fence` met one instrument over. Handed to `head_tree`
    as `extra_dirty` rather than by widening `dirty_files`, because the
    exclusion is correct everywhere else.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_path), "ls-files", "--others",
             "--exclude-standard", "-z", "--", "*.lean"],
            capture_output=True, encoding="utf-8", errors="replace", check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return []
    return [r for r in out.split("\0") if r.strip()]


def row_addr(repo_path, row):
    """A finding row's TREE-FREE address: `(bucket, rel path, theorem name)`.

    ⛔ The audit's rows carry an ABSOLUTE path, and the HEAD side classifies a
    materialised checkout — so a key holding it matches nothing across the two
    sides and reports every theorem in the repo as UNCOMMITTED *and* MASKED at
    once, which reads like a finding rather than like a broken key (measured
    one sweep over, T5j).

    The BUCKET is in the address because both ceilings partition by it
    (`max_restatement`, `max_identity`): a theorem that is IDENTITY at HEAD and
    RESTATEMENT in somebody's edit must not silently keep HEAD's bucket. The
    `note` is NOT — it is display prose, and a key carrying prose reds on a
    reworded message.
    """
    bucket, path, name, _note = row
    rel = os.path.relpath(path, repo_path).replace("\\", "/")
    return (bucket, rel, name)


def adjudicate(repo_path, m):
    """-> (`HeadDelta` over this repo's rows, the dict the FLOORS read).

    Issue 822 T5j. `head_tree`, for T5g's reason: `audit_repo` scopes every def
    table to its module plus its TRANSITIVE IMPORTS, so one dirty `.lean`
    changes the verdicts of every file importing it — `head_delta`'s per-file
    premise is not merely unproven here, it is false — and the classifier takes
    its text from an `os.walk`, which no overlay can intercept.

    Narrowed to `*.lean`: `prove_fires` already demonstrates that `audit_repo`
    runs against a tree containing nothing but `.proofs`, so the pathspec is
    provably sufficient rather than hopefully so.

    `None` for the second element means there is no HEAD to compare against —
    a clean tree, or not a repository — and the caller then reads the
    worktree's own numbers, the conservative direction for a bucket the pins
    read.
    """
    with head_tree(repo_path, SCOPE, paths=SCOPE,
                   extra_dirty=untracked_lean(repo_path)) as tree:
        if tree is None:
            return HeadDelta(list(m["rows"]), [], []), None
        head = measure(tree)
        # `(key, row)` pairs, not bare keys: the buckets are DISPLAYED, and a
        # delta that has thrown the rows away can only print addresses.
        return (delta_of(
            ordinal_keys(m["rows"], lambda r: row_addr(repo_path, r)),
            ordinal_keys(head["rows"], lambda r: row_addr(tree, r)),
            lambda kr: kr[0]), head)


RESTATE_LEAN = """namespace Canary

def alphaSize : Nat := 16
def betaSize : Nat := 24
def totalSize : Nat := alphaSize + betaSize

theorem totalSize_eq_sum : totalSize = alphaSize + betaSize := by decide

end Canary
"""
CLEAN_LEAN = """namespace Canary

def alphaSize : Nat := 16

theorem alphaSize_val : alphaSize = 16 := by decide

end Canary
"""


def adjudicate_cases():
    """`adjudicate` end to end against REAL git — Issue 822 T5j.

    The fixture is this sweep's own subject: a theorem whose RHS is its `def`
    body (RESTATEMENT) against one pinning a literal (clean). Every arm turns
    on which of the two a COMMIT carries.
    """
    fails = []

    def git(root, *args):
        subprocess.run(("git", "-C", str(root)) + args,
                       capture_output=True, check=True)

    def fixture(td, committed, worktree=None, untracked=None):
        repo = os.path.join(td, "r")
        proofs = os.path.join(repo, ".proofs")
        os.makedirs(proofs)
        with open(os.path.join(proofs, "A.lean"), "w", encoding="utf-8") as fh:
            fh.write(committed)
        git(td, "init", "-q", "r")
        git(repo, "config", "user.email", "arm@example.invalid")
        git(repo, "config", "user.name", "arm")
        git(repo, "add", "-A")
        git(repo, "-c", "commit.gpgsign=false", "commit", "-qm", "base")
        if worktree is not None:
            with open(os.path.join(proofs, "A.lean"), "w",
                      encoding="utf-8") as fh:
                fh.write(worktree)
        if untracked is not None:
            with open(os.path.join(proofs, "B.lean"), "w",
                      encoding="utf-8") as fh:
                fh.write(untracked)
        return repo

    def run(repo):
        m = measure(repo)
        delta, head = adjudicate(repo, m)
        return m, delta, (m if head is None else head)

    # a. ⛔ Issue 798's direction: a REMOVAL that is not committed is not
    #    landed. `max_restatement` is a WALL at 0 in all four repos.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, RESTATE_LEAN, worktree=CLEAN_LEAN)
        m, delta, j = run(repo)
        if m["restatement"] != 0:
            fails.append(f"arm a: the fixture is INERT — the worktree must "
                         f"read 0 RESTATEMENT ({m['restatement']})")
        if j["restatement"] != 1 or not delta.masked:
            fails.append(f"adjudicate: an UNCOMMITTED removal cleared the "
                         f"RESTATEMENT wall (judged {j['restatement']}, "
                         f"masked {len(delta.masked)}) — the committed "
                         f"theorem still proves nothing for everyone else")

    # b. And its mirror: a restatement introduced in the worktree must not red
    #    a wall at 0 over a line no commit contains.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, CLEAN_LEAN, worktree=RESTATE_LEAN)
        m, delta, j = run(repo)
        if m["restatement"] != 1:
            fails.append(f"arm b: the fixture is INERT — the worktree must "
                         f"read 1 RESTATEMENT ({m['restatement']})")
        if j["restatement"] != 0 or len(delta.uncommitted) != 1:
            fails.append(f"adjudicate: an uncommitted RESTATEMENT reached the "
                         f"wall (judged {j['restatement']}) instead of "
                         f"UNCOMMITTED ({len(delta.uncommitted)})")

    # c. ⛔ The UNTRACKED half. `audit_repo` walks the FILESYSTEM, so an
    #    untracked theorem file is IN the population and produces ZERO
    #    `git status` dirt — without `extra_dirty` the trigger never fires,
    #    there is no HEAD, and the row is filed COMMITTED.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, CLEAN_LEAN, untracked=RESTATE_LEAN)
        m, delta, j = run(repo)
        if m["restatement"] != 1:
            fails.append(f"arm c: the fixture is INERT — the walk must SEE "
                         f"the untracked file ({m['restatement']})")
        if j["restatement"] != 0 or len(delta.uncommitted) != 1:
            fails.append(f"adjudicate: an UNTRACKED theorem file's row reached "
                         f"the wall (judged {j['restatement']}) — a finding "
                         f"on a file `git log` cannot see, counted against a "
                         f"pin, is this issue's whole subject")

    # d. The FLOORS read HEAD too, and this is the direction only a file
    #    nobody committed can reach: the worktree walk GREW, HEAD's did not.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, CLEAN_LEAN, untracked=CLEAN_LEAN)
        m, delta, j = run(repo)
        if m["files"] != 2 or j["files"] != 1:
            fails.append(f"adjudicate: the walk floor read the worktree "
                         f"({m['files']}) instead of HEAD ({j['files']})")

    # e. The key must be TREE-FREE and ORDINAL-stable: a repo whose only dirt
    #    is elsewhere must report its unchanged rows as MOVED nowhere. A key
    #    carrying the absolute path reports every theorem as UNCOMMITTED *and*
    #    MASKED at once, which reads like a finding rather than a broken key.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, RESTATE_LEAN, untracked=CLEAN_LEAN)
        m, delta, j = run(repo)
        moved = ([k for k, _r in delta.uncommitted]
                 + [k for k, _r in delta.masked])
        if any(k[0] == audit.RESTATEMENT for k in moved):
            fails.append(f"row key: an UNCHANGED restatement row moved — the "
                         f"key is carrying the tree ({moved})")

    # f. A CLEAN tree must cost NOTHING: this instrument copies a tree.
    with tempfile.TemporaryDirectory() as td:
        repo = fixture(td, CLEAN_LEAN)
        calls = []
        real = audit.audit_repo
        audit.audit_repo = lambda r: calls.append(r) or real(r)
        try:
            m, delta, j = run(repo)
        finally:
            audit.audit_repo = real
        if len(calls) != 1:
            fails.append(f"adjudicate: re-classified a CLEAN repo "
                         f"({len(calls)} calls) — `head_tree` must yield "
                         f"None and the caller must SKIP")
        if delta.uncommitted or delta.masked:
            fails.append(f"adjudicate: a clean tree reported moved rows "
                         f"({delta})")
    return fails


def adjudicate_arms():
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
    if len(probed) < 3:
        fails.append(f"STUB PROBE: a `delta_of` that files every row as "
                     f"COMMITTED red only {len(probed)} of the provenance "
                     f"arms — they are not sitting under the seam")
    return fails


def prove_fires(root, present):
    """Plant a restatement in a COPY of each repo and require a RED."""
    print("── --prove-fires: a planted restatement must RED every row ──")
    bad = 0
    for repo in present:
        src = os.path.join(root, repo, ".proofs")
        tmp = tempfile.mkdtemp(prefix=f"restatement-probe-{repo}-")
        try:
            dst = os.path.join(tmp, ".proofs")
            shutil.copytree(src, dst,
                            ignore=shutil.ignore_patterns(".lake", "build"))
            before = measure(tmp)["restatement"]
            with open(os.path.join(dst, "RestatementCanary.lean"), "w",
                      encoding="utf-8") as fh:
                fh.write(CANARY)
            after = measure(tmp)["restatement"]
            ok = after == before + 1
            print(f"   {'✓' if ok else '✗'} {repo}: {before} -> {after} "
                  f"with one planted restatement")
            if not ok:
                bad += 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    if bad:
        print(f"✗ the ceiling is INERT in {bad} repo(s) — a planted "
              f"restatement did not move the count")
        return 1
    print("✓ every row's ceiling is armed end to end (walk → parse → "
          "classify → compare)\n")
    return 0


def main():  # population-predicate: not a contract-repo walk (it CALLS restatement_theorem_audit.repos, the registered subset predicate)
    # ⛔ Without this the sweep CRASHES on the Windows workstation (cp874
    # console) at its first `✓` — `UnicodeEncodeError` out of the print, no
    # verdict, exit 1. 17 of the 18 `*_drift_sweep.py` carry this block
    # verbatim; this one did not, so it was the one member of the family
    # nobody on this box could run at all, and its findings went unread —
    # the shape AGENTS.md names for a sweep that always reds. Not
    # `encoding="utf-8"`: the console encoding is not ours to choose, and
    # `backslashreplace` degrades `✓` to `✓` rather than dying.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass  # not a TextIOWrapper (embedded / detached); keep old behavior

    audit.selftest()
    audit.selftest_scoping()

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    root = os.path.dirname(here)
    floors = read_floors()
    present = audit.repos(root)

    print("=== restatement-theorem drift sweep (every repo with .proofs) ===\n")

    fail = 0
    # The population axis, shared (Issue 782 T3). This sweep still carried the
    # copy-pasted UNSEEN loop that Issue 793 replaced in eight others — on a
    # partial clone it hard-red with no marker support, and it only LOOKED
    # exempt because its four pinned repos all happen to be checked out here.
    #
    # ⛔ The shared verdict takes the CONTRACT walk, not this sweep's derived
    # subset. Handing it `present` (repos with `.proofs`) makes every contract
    # repo WITHOUT proofs read as absent — measured: 16 phantom rows, and the
    # run failed. A subset-population sweep has TWO populations and they are
    # not interchangeable.
    contract = [d for d in os.listdir(root)
                if os.path.isfile(os.path.join(root, d, "BOUNDARY.md"))
                and os.path.isdir(os.path.join(root, d, ".git"))]
    pop_lines, deferred, pop_fail = population_verdict(floors, contract)

    # Issue 797 — the worktree is not the repo. This run reads files that
    # concurrent sessions are editing, so a finding may sit on a line no
    # commit contains. ADVISORY, never a failure: a sweep that hard-reds on
    # an ordinary dirty worktree is a sweep nobody runs. It rides the FINAL
    # line in BOTH directions (the `deferred` precedent) and is SILENT
    # unless the dirty set meets this sweep's own population — the theorem sources.
    for _line in pop_lines:
        print(_line)
    fail += pop_fail
    # The hole the shared verdict CANNOT see, because it asks about the
    # contract walk: a pinned repo that is checked out but has dropped out of
    # THIS sweep's subset (its `.proofs` directory is gone). The loop below
    # would skip it in silence, and a floors row nothing measures is a ceiling
    # that cannot fail.
    dropped = sorted((set(floors) & set(contract)) - set(present))
    if dropped:
        print(f"⛔ DROPPED (pinned and checked out, but no longer carries "
              f"`.proofs` — its ceiling can no longer fail): "
              f"{', '.join(dropped)}")
        fail += len(dropped)
    # Issue 824. LATENT here rather than live: this sweep's population is the
    # `.proofs` subset and no acknowledged extra carries one today, so the
    # missing exemption has never fired. That is a property of the corpus, not
    # of the check — one `.proofs` directory in an extra repo turns it into
    # cfg_row_implication's live red. Wired for the same reason 782 says the
    # quiet members were the dangerous ones.
    unpinned = sorted(r for r in set(present) - set(floors)
                      if not pin_row_exempt(r))
    if unpinned:
        print(f"⛔ UNPINNED (a repo joined the population): "
              f"{', '.join(unpinned)} — re-pin deliberately")
        fail += len(unpinned)

    n_uncommitted = n_masked = 0
    for repo in present:
        if repo not in floors:
            continue
        f = floors[repo]
        repo_path = os.path.join(root, repo)
        m = measure(repo_path)
        # Issue 822 T5j — the DISPLAY reads the worktree (it is what the files
        # say today); every CEILING and both FLOORS read what a commit of this
        # checkout would produce. `j` falls back to the worktree's own numbers
        # where there is no HEAD to compare against.
        delta, head = adjudicate(repo_path, m)
        j = m if head is None else head
        held = {k for k, _r in delta.uncommitted}
        n_uncommitted += len(delta.uncommitted)
        n_masked += len(delta.masked)
        bad = []
        if j["files"] < f["min_lean_files"]:
            bad.append(f"walk {j['files']} < floor {f['min_lean_files']}")
        if j["theorems"] < f["min_theorems"]:
            bad.append(f"parsed {j['theorems']} < floor {f['min_theorems']}")
        if j["restatement"] > f["max_restatement"]:
            bad.append(f"RESTATEMENT {j['restatement']} committed > "
                       f"ceiling {f['max_restatement']}")
        if j["identity"] > f["max_identity"]:
            bad.append(f"IDENTITY {j['identity']} committed > "
                       f"ceiling {f['max_identity']}")
        mark = "✗" if bad else "✓"
        split = ""
        if held or delta.masked:
            split = (f"  [{len(held)} uncommitted"
                     + (f", {len(delta.masked)} MASKED" if delta.masked else "")
                     + f"; HEAD {j['files']} .lean / {j['theorems']} theorems]")
        print(f"{mark} {repo:<16} {m['files']:>3} .lean · "
              f"{m['theorems']:>3} theorems · "
              f"RESTATEMENT {m['restatement']} · IDENTITY {m['identity']}"
              f"{split}")
        for b in bad:
            print(f"     ⛔ {b}")
        # A MASKED row is NOT in the worktree buckets — that is what MASKED
        # means — so it prints from the HEAD side or it prints nowhere, and a
        # ceiling reds over a theorem nobody can see.
        for _k, (bucket, path, name, note) in sorted(delta.masked,
                                                     key=lambda kr: kr[0]):
            print(f"     ⛔ {bucket:<12} {name}  [MASKED — committed, "
                  f"hidden by this worktree]")
        for k, (bucket, path, name, note) in ordinal_keys(
                m["rows"], lambda r: row_addr(repo_path, r)):
            wip = " [UNCOMMITTED — not adjudicated]" if k in held else ""
            print(f"     {bucket}  "
                  f"{os.path.relpath(path, repo_path)} :: "
                  f"{name}  — {note}{wip}")
        fail += len(bad)

    # ...after the loop, because Issue 822's row counts are its input and the
    # population verdict above runs before a single repo has been measured.
    deferred.extend(sweep_advisory(
        contract, SCOPE, root=root,
        uncommitted_rows=n_uncommitted, masked_rows=n_masked))

    print()
    if "--prove-fires" in sys.argv:
        fail += prove_fires(root, present)

    if fail:
        print(f"✗ restatement drift sweep FAILED — {fail} breach(es)")
        print("  Do NOT raise a ceiling to clear a red: a new "
              "RESTATEMENT-INLINE row is a theorem that cannot fail on any "
              "constant being wrong. Remove it (riir-neuron-db Issue 617 is "
              "the worked precedent) or, if it pins two independently "
              "maintained definitions, it should be reading CROSS-DEF —"
              " check which side is inline.")
        # ⛔ A deferral rides the final line in BOTH directions, and this
        # branch used to drop it: on the run that FAILS, the reader most needs
        # to know that seven repos were never measured, that rows sit on
        # uncommitted lines, or that the checkout is behind origin.
        for _d in deferred:
            print(f"  ⚠ {_d}")
        return 1
    # A deferral rides the FINAL line in both directions — one printed only
    # on failure is one nobody reads on the run that passes.
    scope = "all pinned" if not deferred else "all pinned; " + "; ".join(deferred)
    print(f"✓ restatement drift sweep PASSED — {len(present)} repo(s) "
          f"(derived: BOUNDARY.md + .git + .proofs), {scope}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
