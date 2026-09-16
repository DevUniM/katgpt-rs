#!/usr/bin/env python3
"""Which workspace repos actually gate their full compile+lint surface in CI?

Issue 701 R2. That question has now been answered by hand twice and been wrong
both times, in three separate ways — which is the argument for a script:

  1. The repo list was TYPED. It covered 12 of 18, so 5 repos with no CI at all
     and 1 with CI were simply absent from the answer (the Issue 703 class).
  2. Only workflow YAML was grepped. The gate frequently lives in a SCRIPT the
     workflow calls — `katgpt-rs/.github/workflows/full_gate.yml` runs
     `./scripts/full_gate.sh`, and `riir-neuron-db/rust.yml` runs
     `./scripts/ci_feature_guard.sh`. Grepping YAML alone under-reports both.
  3. Grepping YAML *including comments* over-reports: several workflows discuss
     `--all-features --all-targets` in a preamble while running nothing of the
     kind. Signals are read from non-comment lines only.
  4. It read the WORKING TREE and never asked whether those workflows can RUN.
     A gate on a branch GitHub will never dispatch from is decoration, and this
     script scored it identically to one that runs — see below.

Reachability is a separate axis from coverage, and it dominates
--------------------------------------------------------------
A workflow that covers every axis but never executes covers nothing. This repo
already applies that rule one level down ("treat an uninvoked assertion as
unknown, not as passing"); the reachability columns apply it to the workflows
themselves. Two GitHub rules do the work, and they differ:

  * `schedule` and `workflow_dispatch` fire ONLY from the repository's DEFAULT
    branch. A weekly cron in a file that lives only on `develop` never runs.
  * `push` / `pull_request` are evaluated against the workflow file ON THE
    PUSHED REF, so a develop-only workflow with `branches: [develop]` is fine —
    but one with `branches: [main]` never fires if work lands on develop.

Measured 2026-09-01, this axis changed the verdict for FIVE repos, including
this one: katgpt-rs `full_gate.yml` carries `schedule: 17 4 * * 1` and
`workflow_dispatch` while the default branch (`main`) does not carry the file,
so the weekly run AGENTS.md advertises has never fired. Its comment calls the
schedule "the rot check"; the rot check had rotted.

"Full surface" here is the katgpt-rs AGENTS.md definition — the axes a green
narrow gate cannot speak for: `--all-targets` (tests/benches/examples, where
gated code lives), `--all-features` (non-default code otherwise compiles to
nothing), `--workspace` (a crate's non-default feature can be switched on by the
root crate's defaults), clippy rather than check, and `--keep-going` (without it
the run stops at the first failing target and under-reports).

    scripts/ci_gate_coverage.py [--markdown]

Exit 0 always: this reports, it does not gate. Each repo owns its own CI per
BOUNDARY.md, so this cannot be a pass/fail assertion from here.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
import pathlib

# Issue 804: this instrument is documented as directly invokable, and its
# verdict glyphs (✓ ✗ ⛔ ⚠) kill it on a non-UTF-8 console — no verdict at
# all, findings unread. docs_gate.sh's PYTHONIOENCODING only covers runs
# that go through the wrapper.
import console_safe  # noqa: E402
import repo_alias  # noqa: E402 — the machine-local name codec (see its docstring)

console_safe.apply()

# === ci_gate_coverage

GIT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_RE = re.compile(r"(?:\./|\b)((?:scripts|ci|\.ci)/[A-Za-z0-9_.-]+\.sh)")
# Ordered: the report reads left-to-right as increasing surface.
SIGNALS = ("clippy", "--workspace", "--all-targets", "--all-features",
           "--each-feature", "--keep-going")


def derive_repos(root: Path) -> list[str]:
    """`-d .git`, not `-e`: a git worktree has a .git FILE and would double-count."""
    return repo_alias.apply(d.name for d in root.iterdir()
                            if d.is_dir() and (d / "BOUNDARY.md").is_file()
                            and (d / ".git").is_dir())


def _git(root: Path, repo: str, *args: str) -> str:
    import subprocess
    r = subprocess.run(["git", "-C", str(root / repo), *args],
                       capture_output=True, encoding="utf-8", errors="replace")
    return r.stdout.strip() if r.returncode == 0 else ""


def default_branch(root: Path, repo: str) -> str:
    # origin/HEAD is a LOCAL symref that does not follow server-side default
    # flips (caught live 2026-09-03: riir-dapps, flipped 09-02, still reported
    # main -> a phantom UNREACHABLE row). Refresh it from the remote first;
    # --atomic-update is not a thing for set-head, and a repo with no remote
    # (or offline) keeps its last-known value — reported as-is, never guessed.
    _git(root, repo, "remote", "set-head", "origin", "-a")
    return parse_head_ref(
        _git(root, repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD"))


def parse_head_ref(ref: str) -> str:
    """`origin/develop` -> `develop`; nothing readable -> `?`.

    Extracted from the subprocess wrapper because the `?` it returns is a
    VERDICT, not a formatting detail: main() reads it as UNMEASURED and every
    workflow in that repo is withheld from the dead/live classification. A repo
    with no remote refs is not a repo full of dead gates, and scoring it as one
    would be this family's confident-green-over-nothing inversion pointed the
    other way.
    """
    return ref.split("/", 1)[1] if "/" in ref else (ref or "?")


def _on_branch(root: Path, repo: str, branch: str, rel: str) -> bool:
    """Does this workflow file exist on origin/<branch>? Working-tree presence
    is not the question — GitHub reads the file from a ref, never from disk."""
    return _git(root, repo, "ls-tree", "--name-only", f"origin/{branch}", rel) == rel


def _tracked(root: Path, repo: str, rel: str) -> bool:
    """Is this workflow committed at all, on any branch?

    An untracked file is UNFINISHED WORK, not a dead gate — it reaches no
    branch because nobody has pushed it yet. Reporting it as "cannot fire"
    raises a false alarm against a colleague's in-flight edit, which is how a
    report earns the reputation that gets it ignored. Caught live: a sibling
    agent added riir-deployer/rust.yml mid-run and it landed in the dead
    block."""
    return bool(_git(root, repo, "ls-files", "--", rel))

def _on_block(wf: Path) -> str:
    """The `on:` block, comments stripped, or "" if the file declares none.

    Deliberately parsed from raw text rather than with a YAML load: this script
    must not acquire a PyYAML dependency to answer a question about a handful
    of keywords. Shared by both trigger readers so they cannot disagree about
    where the block ends."""
    try:
        raw = wf.read_text(errors="replace")
    except OSError:
        return ""
    body = re.split(r"^jobs:", raw, maxsplit=1, flags=re.M)[0]
    live = "\n".join(l for l in body.splitlines()
                      if not l.lstrip().startswith("#"))
    parts = re.split(r"^on:", live, maxsplit=1, flags=re.M)
    return parts[1] if len(parts) > 1 else ""


def _branch_exists(root: Path, repo: str, branch: str) -> bool:
    """Does `origin/<branch>` exist at all?

    Split out from `_on_branch` because the two failures need DIFFERENT
    repairs and `_on_branch` returns False for both. Measured 2026-09-15 over
    the five repos this report flags hand-only: THREE have no `origin/main` at
    all (riir-auth, riir-kat, mmorpg-remake) while their `push` filter names it,
    and the two that do have one (riir-ai, riir-viewbridge) carry no
    `.github/workflows/` directory there. "Promote the file to main" is the fix
    for the second and is not even expressible for the first.
    """
    return bool(_git(root, repo, "rev-parse", "--verify", "--quiet",
                     f"refs/remotes/origin/{branch}"))


def push_gap(root: Path, repo: str, wf: Path, dflt: str, on_branch=None,
             branch_exists=None) -> str:
    """Why a declared `push` cannot fire — named, because the fix depends on it.

    GitHub evaluates `push` against the workflow file ON THE PUSHED REF, so a
    filter naming a branch that carries no copy of the file is inert no matter
    how many pushes land there. Two different repairs follow from the two
    causes (promote the file to that branch, or widen the filter to a branch
    that has it), and "never fires" alone does not say which."""
    blk = _on_block(wf)
    m = re.search(r"^\s+push:(.*?)(?=^\s{2}\S|\Z)", blk, re.M | re.S)
    if not m:
        return ""
    rel = wf.relative_to(root / repo).as_posix()
    probe = on_branch or (lambda b: _on_branch(root, repo, b, rel))
    exists = branch_exists or (lambda b: _branch_exists(root, repo, b))
    brs = re.search(r"branches:\s*\[([^\]]*)\]", m.group(1))
    names = ([b.strip().strip("'\"") for b in brs.group(1).split(",") if b.strip()]
             if brs else [dflt])
    missing = [b for b in names if not probe(b)]
    if not missing:
        return ""
    # Name WHICH failure, because the repairs are different and only one of
    # them is a repair at all. A branch that does not exist cannot be handed
    # the file; somebody has to decide whether the filter or the branching
    # model is wrong, and "carries no copy" quietly suggests the former.
    absent = [b for b in missing
              if exists is not None and not exists(b)]
    detail = ", ".join(
        f"{b} DOES NOT EXIST" if b in absent else f"{b} carries no copy of this file"
        for b in missing)
    return f"push[{','.join(names)}] inert — {detail}"


def reachable_triggers(root: Path, repo: str, wf: Path, dflt: str,
                       on_branch=None) -> set[str]:
    """Which of this workflow's triggers can actually fire.

    Deliberately parsed from the raw `on:` block rather than with a YAML load:
    this script must not acquire a PyYAML dependency to answer a question about
    two keywords, and the block is regular enough to read directly."""
    rel = wf.relative_to(root / repo).as_posix()
    probe = on_branch or (lambda b: _on_branch(root, repo, b, rel))
    on_blk = _on_block(wf)
    if not on_blk:
        return set()
    out: set[str] = set()
    declared: set[str] = set()
    for kw in ("schedule", "workflow_dispatch", "workflow_call", "push",
               "pull_request"):
        if re.search(rf"^\s+{kw}:", on_blk, re.M):
            declared.add(kw)
    on_default = probe(dflt)
    # schedule / workflow_dispatch: default branch only, full stop.
    for kw in ("schedule", "workflow_dispatch"):
        if re.search(rf"^\s+{kw}:", on_blk, re.M) and on_default:
            out.add(kw)
    # workflow_call is invoked BY REF from another repo, so it is reachable
    # from any branch a caller pins. Not a default-branch question.
    if re.search(r"^\s+workflow_call:", on_blk, re.M):
        out.add("workflow_call")
    # push: evaluated against the workflow file on the PUSHED ref, so the
    # question is whether the file exists on a branch the filter names.
    m = re.search(r"^\s+push:(.*?)(?=^\s{2}\S|\Z)", on_blk, re.M | re.S)
    if m:
        brs = re.search(r"branches:\s*\[([^\]]*)\]", m.group(1))
        names = ([b.strip().strip("'\"") for b in brs.group(1).split(",") if b.strip()]
                 if brs else [dflt])
        if any(probe(b) for b in names):
            out.add("push")
    # pull_request is CONDITIONAL, not default-branch-bound: the run uses the
    # file from the PR's merge commit, so a develop-only workflow does fire on
    # a PR. Whether one is ever opened is a workflow-policy question git cannot
    # answer — several repos here land work directly on develop and never open
    # one. Reported as its own state rather than folded into either verdict;
    # calling it live would over-report and calling it dead would over-claim.
    if re.search(r"^\s+pull_request:", on_blk, re.M):
        out.add("pull_request?")
    # Declared-but-dead is the finding a workflow-level verdict cannot make: a
    # file can be "reachable" on one trigger while the two its documentation
    # advertises never fire. katgpt-rs full_gate.yml is exactly that shape.
    lost = declared - {t.rstrip("?") for t in out}
    return out | {f"-{t}" for t in lost}


def live_lines(path: Path) -> list[str]:
    """Non-comment lines. A workflow preamble that DISCUSSES --all-features is
    not a workflow that runs it; reading comments is how the hand survey called
    two repos gated that are not."""
    try:
        raw = path.read_text(errors="replace").splitlines()
    except OSError:
        return []
    return [l for l in raw if not l.lstrip().startswith("#")]


def cargo_commands(lines: list[str]) -> list[str]:
    """Every `cargo ...` invocation, with backslash continuations joined."""
    joined: list[str] = []
    acc = ""
    for raw in lines:
        s = raw.strip()
        if acc:
            acc += " " + s.rstrip("\\").strip()
            if not s.endswith("\\"):
                joined.append(acc)
                acc = ""
            continue
        if "cargo " not in s:
            continue
        acc = s.rstrip("\\").strip()
        if not s.endswith("\\"):
            joined.append(acc)
            acc = ""
    if acc:
        joined.append(acc)
    return joined


def _best(lines: list[str]) -> tuple[list[str], str]:
    """Highest-scoring single cargo command in a pool, scored PER COMMAND.

    Extracted so the repo-wide pool and the per-workflow pools cannot drift
    apart in how they score — the join below is only meaningful if both sides
    answer the same question the same way."""
    best: list[str] = []
    best_cmd = ""
    for cmd in cargo_commands(lines):
        sig = [s for s in SIGNALS if s in cmd]
        if len(sig) > len(best):
            best, best_cmd = sig, cmd
    return best, best_cmd


def _wf_pool(root: Path, repo: str, wf: Path) -> list[str]:
    """One workflow's own lines plus those of every script IT invokes.

    Deliberately NOT deduped against sibling workflows. survey()'s aggregate
    pool follows each script once, which is right for "what does this repo
    run" and wrong for "which workflow starts this command" — a script
    invoked by two workflows belongs to both, and dropping it from the second
    would report that workflow as carrying no compile surface."""
    wl = live_lines(wf)
    out, seen = list(wl), set()
    for m in SCRIPT_RE.finditer("\n".join(wl)):
        rel = m.group(1)
        cand = root / repo / rel
        if cand.is_file() and rel not in seen:
            seen.add(rel)
            out += live_lines(cand)
    return out


def WF_DIR(repo: str) -> Path:
    return GIT_ROOT / repo / ".github" / "workflows"


def survey(root: Path, repo: str, on_branch=None, dflt: str | None = None) -> dict:
    wf_dir = root / repo / ".github" / "workflows"
    workflows = sorted(p for p in wf_dir.glob("*")
                       if p.suffix in (".yml", ".yaml")) if wf_dir.is_dir() else []
    lines: list[str] = []
    scripts: list[str] = []
    for wf in workflows:
        wl = live_lines(wf)
        lines += wl
        for m in SCRIPT_RE.finditer("\n".join(wl)):
            cand = root / repo / m.group(1)
            if cand.is_file() and m.group(1) not in scripts:
                scripts.append(m.group(1))
                lines += live_lines(cand)
    blob = "\n".join(lines)
    # Score PER COMMAND, not over a blob. `--all-targets` in one script and
    # `--all-features` in another is not a full-surface gate: AGENTS.md's whole
    # point is that the axes are INDEPENDENT, so a green on each separately says
    # nothing about their combination. A blob scan cannot tell those apart and
    # rated riir-chain "full" on axes spread across 15 scripts.
    best, best_cmd = _best(lines)
    # Both injectable, for the same reason `reachable_triggers` is: this
    # function is the AGGREGATOR — the dedup, the per-command scoring and the
    # data-borne `dynamic` split all live here — and every one of those rules
    # sat behind a `git` subprocess no arm could stage.
    if dflt is None:
        dflt = default_branch(root, repo)
    reach = {wf.name: reachable_triggers(root, repo, wf, dflt, on_branch=on_branch)
             for wf in workflows}
    # Per-workflow attribution. The aggregate `best` above answers "does a
    # full-surface command exist in this repo"; it cannot answer "does anything
    # START it", because it pools every workflow into one bag. Keeping the
    # per-workflow score lets the join below cross coverage with reachability
    # without disturbing the columns Issue 701 R2 quotes.
    per_wf = {}
    for wf in workflows:
        wl = _wf_pool(root, repo, wf)
        sigs, cmd = _best(wl)
        in_cmds = {s for c in cargo_commands(wl) for s in SIGNALS if s in c}
        per_wf[wf.name] = {
            "signals": sigs, "cmd": cmd,
            "dynamic": sorted({s for s in SIGNALS if s in "\n".join(wl)} - in_cmds,
                              key=SIGNALS.index)}
    return {"repo": repo, "workflows": len(workflows), "scripts": scripts,
            "default_branch": dflt, "reach": reach, "per_wf": per_wf,
            "signals": best, "cmd": best_cmd,
            "any": sorted({s for c in cargo_commands(lines) for s in SIGNALS
                           if s in c}, key=SIGNALS.index),
            # A gate whose command is BUILT FROM DATA (a CONFIGS table of
            # pkg:features:flags rows, looped) carries its flags in array
            # literals, not in a `cargo ...` line, so per-command scoring reads
            # it as absent. riir-chain's clippy_gate.sh is exactly this and is
            # arguably MORE thorough than a single command — a feature matrix.
            # Report it as a third state. Scoring it low would be the silent
            # truncation this script exists to stop.
            # A signal that appears in the FILES but in no cargo command is
            # sitting in a data structure — a CONFIGS table of
            # pkg:features:flags rows that a loop later expands. riir-chain's
            # clippy_gate.sh is exactly that, and it is arguably MORE thorough
            # than one command (a feature matrix). Per-command scoring reads it
            # as absent, so report it as a third state; scoring it low would be
            # the silent truncation this script exists to stop.
            "dynamic": sorted(
                {s for s in SIGNALS if s in blob}
                - {s for c in cargo_commands(lines) for s in SIGNALS if s in c},
                key=SIGNALS.index)}



# The full-surface bar: clippy over every target AND every feature.
FULL_SURFACE = frozenset({"clippy", "--all-targets", "--all-features"})
# Display strings per output format, keyed by verdict. Two formats, ONE ladder:
# main() carried the ladder twice, once per format, and nothing asserted that
# the two agreed about which repo was which.
MARK_PLAIN = {"FULL": "FULL ", "DYN": "DYN? ", "PART": "part ",
              "NOCI": "NOCI ", "NONE": "none "}


def mark_md(r: dict, v: str) -> str:
    """The markdown column for one verdict. Paired with MARK_PLAIN so the two
    output formats read the SAME ladder — main() carried it twice, in two
    vocabularies, and nothing asserted they agreed about which repo was which.
    """
    if v == "DYN":
        return ("**needs a human read** \u2014 "
                + " ".join(f"`{x}`" for x in r["dynamic"])
                + " live in data, not in a command")
    return {"FULL": "**yes**", "PART": "partial",
            "NOCI": "no CI", "NONE": "no"}[v]


def surface_verdict(r: dict) -> str:
    """FULL | DYN | PART | NOCI | NONE — the surface classification.

    Extracted from main() for Issue 775's reason: a report's own verdict
    arithmetic sitting inline beside its print statements is unreachable by
    any arm, which is why this module scored 4 killed of 74 (Issue 790).

    It is a PARTITION, and that is a behaviour change with a measured cause.
    main() classified for display with this ladder (DYN before PART) and then
    COUNTED with independent predicates, where `partial` was `signals and not
    full` -- so a repo carrying both a partial command and a data-borne signal
    was counted twice. Measured 2026-09-15: riir-chain is exactly that shape,
    and the summary line read `6 full; 1 dynamic; 9 partial; 1 no CI` over
    SIXTEEN repos. A verdict and a tally that disagree about how many states a
    repo is in is the same defect class as a count that is not a checksum.
    """
    if FULL_SURFACE <= set(r["signals"]):
        return "FULL"
    if r.get("dynamic"):
        return "DYN"
    if r["signals"]:
        return "PART"
    return "NONE" if r["workflows"] else "NOCI"


def reachability_findings(rows: list[dict], tracked) -> dict[str, list[str]]:
    """Split every workflow into dead / unknown / partial-trigger findings.

    `tracked(repo, rel) -> bool` is injected so the classification is reachable
    without a git tree. Same extraction reason as surface_verdict(): this loop
    decided four verdicts inline in main() and no arm could enter it.
    """
    out: dict[str, list[str]] = {"dead": [], "unknown": [], "partial": []}
    for r in rows:
        for name, trig in sorted(r["reach"].items()):
            live = {t for t in trig if not t.startswith("-")}
            lost = sorted(t[1:] for t in trig if t.startswith("-"))
            if lost and live:
                out["partial"].append(
                    f"{r['repo']}/{name}: declared {' '.join(lost)} — never fires")
            if r["default_branch"] == "?":
                out["unknown"].append(f"{r['repo']}/{name}")
            elif not live and not tracked(r["repo"], f".github/workflows/{name}"):
                out["unknown"].append(
                    f"{r['repo']}/{name} (untracked — not committed yet)")
            elif not live:
                out["dead"].append(f"{r['repo']}/{name}")
            elif live == {"pull_request?"}:
                out["unknown"].append(f"{r['repo']}/{name} (PR-only)")
    return out


def hand_only(rows: list[dict]) -> list[tuple[dict, list[str]]]:
    """Repos whose STRONGEST compile/lint command no automatic trigger starts.

    Separated from the printing so it can be pinned by selftest(): an assertion
    nothing has ever seen fail is not known to be able to fail, which is the
    defect this whole family of scripts exists to catch."""
    # Strength is compared, not mere presence. A first cut asked only "does ANY
    # automatically-triggered workflow carry a cargo signal", and riir-chain
    # slipped through it: the scheduled toolchain_drift.yml names the full-gate
    # flags in a data table, which was enough to mask rust.yml — the repo's
    # actual compile gate, and dispatch-only. A weak automatic gate must not
    # vouch for a strong manual one.
    #
    # Lexicographic (real commands, then data-borne): a signal sitting in a
    # CONFIGS table is worth something — riir-chain's feature matrix is
    # arguably more thorough than any single command — but never enough to
    # outrank a signal in an actual `cargo` invocation.
    AUTOMATIC = {"schedule", "push"}

    def strength(v):
        return (len(v.get("signals", ())), len(v.get("dynamic", ())))

    handonly = []
    for r in rows:
        live_wf = {n for n, t in r["reach"].items()
                   if any(not x.startswith("-") for x in t)}
        # Workflows with no live trigger at all are the `dead` block's finding,
        # already printed above; counting them here would report one defect
        # twice and blur "cannot run" into "runs only when asked".
        #
        # EQUIVALENT under `>=`, proven rather than assumed (Issue 790 T7): a
        # strength-(0,0) workflow can only change `best_all` when `carriers`
        # would otherwise be EMPTY, and in that case `best_all` is (0,0) too,
        # so `best_auto >= best_all` holds and the repo is not flagged either
        # way. It is this module's one standing arm-reach survivor.
        carriers = {n for n in live_wf if strength(r["per_wf"].get(n, {})) > (0, 0)}
        if not carriers:
            continue
        auto = {n for n, t in r["reach"].items()
                if AUTOMATIC & {x for x in t if not x.startswith("-")}}
        best_all = max(strength(r["per_wf"][n]) for n in carriers)
        best_auto = max([strength(r["per_wf"][n]) for n in carriers & auto],
                        default=(0, 0))
        if best_auto >= best_all:
            continue
        handonly.append((r, sorted(n for n in carriers
                                   if strength(r["per_wf"][n]) == best_all)))
    return handonly


def _tmp_wf(tmp, repo: str, name: str, body: str):
    """A workflow file at its real relative address, so `relative_to` resolves.

    The path SHAPE is load-bearing, not decoration: reachable_triggers() derives
    `rel` from it and hands that to the branch probe, so a fixture that writes
    the file anywhere else exercises a different code path than production.
    """
    d = tmp / repo / ".github" / "workflows"
    d.mkdir(parents=True, exist_ok=True)
    f = d / name
    f.write_text(body, encoding="utf-8")
    return f


def text_reader_arms() -> list[str]:
    """live_lines / cargo_commands / _best / _on_block -- pure over plain text."""
    fails: list[str] = []

    def eq(label, got, want):
        if got != want:
            fails.append(f"    {label}: got {got!r}, want {want!r}")

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        wf = _tmp_wf(tmp, "r", "a.yml",
                     "name: x\n"
                     "# on:\n"
                     "#   schedule: [{cron: '0 0 * * *'}]\n"
                     "on:\n"
                     "  push:\n"
                     "    branches: [main]\n"
                     "  workflow_dispatch:\n"
                     "jobs:\n"
                     "  b:\n"
                     "    steps:\n"
                     "      - run: cargo clippy --all-features\n")
        # A COMMENTED trigger is not a trigger: the comment strip is the whole
        # reason this reads raw text instead of loading YAML, and a preamble
        # DISCUSSING a schedule read as declaring one.
        blk = _on_block(wf)
        eq("_on_block drops commented triggers", "schedule" in blk, False)
        eq("_on_block keeps live triggers",
           ("push" in blk, "workflow_dispatch" in blk), (True, True))
        # `jobs:` ends the block -- a `cargo ... --all-features` step below it
        # must not leak in as an `on:` keyword.
        eq("_on_block stops at jobs:", "steps" in blk, False)
        eq("_on_block on a file with no on: block",
           _on_block(_tmp_wf(tmp, "r", "b.yml", "name: x\njobs: {}\n")), "")
        eq("_on_block on an unreadable path",
           _on_block(tmp / "r" / "nope.yml"), "")
        # live_lines strips comment lines only where the # LEADS.
        eq("live_lines strips leading-# lines and keeps trailing ones",
           live_lines(_tmp_wf(tmp, "r", "c.yml",
                              "  # gone\nkept  # here\n")),
           ["kept  # here"])
        eq("live_lines on an unreadable path",
           live_lines(tmp / "r" / "nope.yml"), [])

    # cargo_commands: continuation joining is the rule, and a command SPLIT
    # across lines is how every full-surface gate in this workspace is written.
    eq("cargo_commands joins backslash continuations",
       cargo_commands(["cargo clippy \\", "  --workspace \\", "  --all-features",
                       "echo done"]),
       ["cargo clippy --workspace --all-features"])
    eq("cargo_commands ignores non-cargo lines",
       cargo_commands(["echo cargo-ish", "rustc --all-features"]), [])
    eq("cargo_commands flushes a trailing unterminated continuation",
       cargo_commands(["cargo test \\"]), ["cargo test"])
    eq("cargo_commands keeps two commands apart",
       cargo_commands(["cargo clippy --all-targets", "cargo test --all-features"]),
       ["cargo clippy --all-targets", "cargo test --all-features"])

    # _best scores PER COMMAND. The regression it exists for: --all-targets in
    # one command and --all-features in another is NOT a full-surface gate.
    sig, cmd = _best(["cargo clippy --all-targets", "cargo test --all-features"])
    eq("_best never pools signals across commands", len(sig), 2)
    eq("_best returns the winning command", cmd, "cargo clippy --all-targets")
    eq("_best on a pool with no cargo command", _best(["echo hi"]), ([], ""))
    eq("_best prefers the wider single command",
       _best(["cargo clippy --all-targets",
              "cargo clippy --workspace --all-targets --all-features"])[0],
       ["clippy", "--workspace", "--all-targets", "--all-features"])
    # On a TIE the FIRST command wins, and the choice is visible: the report
    # prints `best-cmd` verbatim and a reader uses it to find the gate.
    eq("_best keeps the first of two equally wide commands",
       _best(["cargo clippy --all-targets", "cargo clippy --all-features"])[1],
       "cargo clippy --all-targets")

    return fails


def reachability_arms() -> list[str]:
    """reachable_triggers / push_gap, with the branch probe INJECTED.

    Injection is what makes these reachable at all: production resolves branch
    membership through `git ls-tree`, so every verdict below was previously
    behind a subprocess an arm could not stage.
    """
    fails: list[str] = []

    def eq(label, got, want):
        if got != want:
            fails.append(f"    {label}: got {got!r}, want {want!r}")

    import tempfile
    ON = "on:\n  schedule:\n    - cron: '0 0 * * *'\n  push:\n    branches: [main]\n"
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        wf = _tmp_wf(tmp, "r", "g.yml", ON + "jobs: {}\n")

        # Everything present on `main`, which is also the default.
        eq("reachable: file on the default branch, push filter matches",
           reachable_triggers(tmp, "r", wf, "main", on_branch=lambda b: True),
           {"schedule", "push"})
        # The file is on NO branch: schedule dies (default-branch-bound) and so
        # does push (evaluated against the file on the pushed ref). Both are
        # reported LOST, which is the finding a workflow-level verdict cannot
        # make -- a file can run on one trigger while another never fires.
        eq("reachable: file on no branch loses both triggers",
           reachable_triggers(tmp, "r", wf, "main", on_branch=lambda b: False),
           {"-schedule", "-push"})
        # The asymmetry that motivates the split: default=develop, filter=main,
        # file on develop only. schedule fires, push cannot.
        eq("reachable: schedule lives while a main-only push is inert",
           reachable_triggers(tmp, "r", wf, "develop",
                              on_branch=lambda b: b == "develop"),
           {"schedule", "-push"})

        # workflow_call is invoked BY REF from another repo -- reachable from
        # any branch a caller pins, so it must NOT be default-branch-bound.
        wc = _tmp_wf(tmp, "r", "c.yml", "on:\n  workflow_call:\njobs: {}\n")
        eq("reachable: workflow_call is not default-branch-bound",
           reachable_triggers(tmp, "r", wc, "main", on_branch=lambda b: False),
           {"workflow_call"})
        # pull_request is its own state, never folded into either verdict.
        pr = _tmp_wf(tmp, "r", "p.yml", "on:\n  pull_request:\njobs: {}\n")
        eq("reachable: pull_request reports as CONDITIONAL, not live",
           reachable_triggers(tmp, "r", pr, "main", on_branch=lambda b: False),
           {"pull_request?"})
        eq("reachable: a file declaring no on: block reaches nothing",
           reachable_triggers(tmp, "r",
                              _tmp_wf(tmp, "r", "n.yml", "jobs: {}\n"), "main",
                              on_branch=lambda b: True),
           set())

        # push_gap NAMES the cause, because two different repairs follow from
        # it and "never fires" alone does not say which.
        gap = push_gap(tmp, "r", wf, "main", on_branch=lambda b: False,
                       branch_exists=lambda b: True)
        eq("push_gap names the missing branch", "main" in gap, True)
        # The two causes, told apart. Measured on the live workspace: three of
        # the five hand-only repos have no `origin/main` AT ALL while their
        # filter names it, so "promote the file" is not even expressible.
        eq("a branch that EXISTS without the file reads as `carries no copy`",
           ("carries no copy" in gap, "DOES NOT EXIST" in gap), (True, False))
        gone = push_gap(tmp, "r", wf, "main", on_branch=lambda b: False,
                        branch_exists=lambda b: False)
        eq("a branch that does not exist says so instead",
           ("DOES NOT EXIST" in gone, "carries no copy" in gone), (True, False))
        eq("push_gap is silent when the branch carries the file",
           push_gap(tmp, "r", wf, "main", on_branch=lambda b: True,
                    branch_exists=lambda b: True), "")
        # A MIXED filter reports each branch with its own cause, because a
        # single verdict for `[main, release]` sends the reader to one repair
        # for two different problems.
        mixed = _tmp_wf(tmp, "r", "mx.yml",
                        "on:\n  push:\n    branches: [main, release]\njobs: {}\n")
        mg = push_gap(tmp, "r", mixed, "develop", on_branch=lambda b: False,
                      branch_exists=lambda b: b == "main")
        eq("a mixed filter reports each branch with its own cause",
           ("main carries no copy" in mg, "release DOES NOT EXIST" in mg),
           (True, True))
        eq("push_gap is silent on a workflow with no push trigger",
           push_gap(tmp, "r", wc, "main", on_branch=lambda b: False,
                    branch_exists=lambda b: False), "")
        # No `branches:` filter means the DEFAULT branch, not "every branch".
        bare = _tmp_wf(tmp, "r", "d.yml", "on:\n  push:\njobs: {}\n")
        eq("push_gap falls back to the default branch with no filter",
           "develop" in push_gap(tmp, "r", bare, "develop",
                                 on_branch=lambda b: False,
                                 branch_exists=lambda b: True),
           True)
        eq("push with no filter is live when the default carries the file",
           reachable_triggers(tmp, "r", bare, "develop",
                              on_branch=lambda b: b == "develop"),
           {"push"})

    return fails


def pool_arms() -> list[str]:
    """derive_repos / _wf_pool -- the two filesystem walks that decide the
    population and the per-workflow evidence."""
    fails: list[str] = []

    def eq(label, got, want):
        if got != want:
            fails.append(f"    {label}: got {got!r}, want {want!r}")

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        # A contract repo is BOUNDARY.md + a .git DIRECTORY. The `is_dir` is
        # load-bearing: a git worktree has a .git FILE and would double-count.
        for name, boundary, git in (("good", True, "dir"), ("nogit", True, None),
                                    ("noboundary", False, "dir"),
                                    ("worktree", True, "file")):
            d = tmp / name
            d.mkdir()
            if boundary:
                (d / "BOUNDARY.md").write_text("x", encoding="utf-8")
            if git == "dir":
                (d / ".git").mkdir()
            elif git == "file":
                (d / ".git").write_text("gitdir: elsewhere", encoding="utf-8")
        (tmp / "loose.md").write_text("x", encoding="utf-8")
        eq("derive_repos wants BOUNDARY.md AND a .git DIRECTORY",
           derive_repos(tmp), ["good"])

        # _wf_pool folds in the lines of every script the workflow INVOKES --
        # which is the only way a `run: scripts/full_gate.sh` workflow carries
        # any cargo signal at all.
        (tmp / "r").mkdir(parents=True, exist_ok=True)
        (tmp / "r" / "scripts").mkdir(parents=True, exist_ok=True)
        (tmp / "r" / "scripts" / "g.sh").write_text(
            "cargo clippy --workspace --all-features\n", encoding="utf-8")
        wf = _tmp_wf(tmp, "r", "w.yml",
                     "jobs:\n  b:\n    steps:\n      - run: ./scripts/g.sh\n")
        eq("_wf_pool follows an invoked script",
           _best(_wf_pool(tmp, "r", wf))[0],
           ["clippy", "--workspace", "--all-features"])
        miss = _tmp_wf(tmp, "r", "m.yml",
                       "jobs:\n  b:\n    steps:\n      - run: ./scripts/absent.sh\n")
        eq("_wf_pool credits nothing for a script that is not there",
           _best(_wf_pool(tmp, "r", miss))[0], [])
        # Deduped WITHIN one workflow (a script named twice is followed once)
        # and deliberately NOT across workflows -- a script invoked by two
        # workflows belongs to both, and dropping it from the second would
        # report that workflow as carrying no compile surface.
        twice = _tmp_wf(tmp, "r", "t.yml",
                        "jobs:\n  b:\n    steps:\n"
                        "      - run: ./scripts/g.sh\n"
                        "      - run: ./scripts/g.sh\n")
        once = _tmp_wf(tmp, "r", "o.yml",
                       "jobs:\n  b:\n    steps:\n      - run: ./scripts/g.sh\n")
        eq("_wf_pool follows a twice-named script once",
           len(_wf_pool(tmp, "r", twice)) - len(live_lines(twice)),
           len(_wf_pool(tmp, "r", once)) - len(live_lines(once)))

    return fails


def surface_verdict_arms() -> list[str]:
    """The ladder, and the PARTITION property the old inline counts broke."""
    fails: list[str] = []

    def eq(label, got, want):
        if got != want:
            fails.append(f"    {label}: got {got!r}, want {want!r}")

    def row(sig, dyn=(), wf=1):
        return {"signals": list(sig), "dynamic": list(dyn), "workflows": wf}

    FULL = ["clippy", "--all-targets", "--all-features"]
    eq("FULL needs all three signals", surface_verdict(row(FULL)), "FULL")
    eq("FULL survives extra signals",
       surface_verdict(row(FULL + ["--workspace"])), "FULL")
    eq("a missing signal is not FULL",
       surface_verdict(row(["clippy", "--all-targets"])), "PART")
    eq("data-borne signals outrank a partial command",
       surface_verdict(row(["--each-feature"], dyn=["--all-targets"])), "DYN")
    eq("FULL outranks data-borne signals",
       surface_verdict(row(FULL, dyn=["--all-targets"])), "FULL")
    eq("no signals but workflows exist is NONE",
       surface_verdict(row([], wf=2)), "NONE")
    eq("no workflows at all is NOCI", surface_verdict(row([], wf=0)), "NOCI")
    # The regression this extraction fixed: the display ladder and the tally
    # disagreed, so a DYN repo carrying a partial command was counted twice and
    # the summary summed to 17 over 16 repos.
    rows = [row(FULL), row(["--each-feature"], dyn=["--all-targets"]),
            row(["clippy"]), row([], wf=0), row([], wf=3)]
    seen = [surface_verdict(r) for r in rows]
    eq("the ladder is a partition over the report's own repos",
       sum(seen.count(k) for k in ("FULL", "DYN", "PART", "NOCI", "NONE")),
       len(rows))
    eq("every verdict has a display string", sorted(MARK_PLAIN), sorted(set(seen)))

    return fails


def reachability_findings_arms() -> list[str]:
    """dead / unknown / partial, and the three ways a row escapes `dead`."""
    fails: list[str] = []

    def eq(label, got, want):
        if got != want:
            fails.append(f"    {label}: got {got!r}, want {want!r}")

    def row(repo, reach, dflt="main"):
        return {"repo": repo, "reach": reach, "default_branch": dflt}

    TRACKED = lambda repo, rel: True
    UNTRACKED = lambda repo, rel: False

    f = reachability_findings([row("a", {"g.yml": set()})], TRACKED)
    eq("a tracked workflow with no live trigger is DEAD",
       (f["dead"], f["unknown"]), (["a/g.yml"], []))
    # An UNTRACKED file is unfinished work, not a dead gate -- reporting it
    # raises a false alarm against a colleague's in-flight edit.
    f = reachability_findings([row("a", {"g.yml": set()})], UNTRACKED)
    eq("an untracked workflow is UNKNOWN, never dead",
       (f["dead"], len(f["unknown"])), ([], 1))
    # No remote refs => no default branch => UNMEASURED, and the tracked probe
    # must not even be consulted.
    probed = []
    f = reachability_findings([row("a", {"g.yml": set()}, dflt="?")],
                              lambda r, x: probed.append(x) or True)
    eq("no default branch is UNKNOWN without probing tracked-ness",
       (f["dead"], f["unknown"], probed), ([], ["a/g.yml"], []))
    # PR-only is a workflow-policy question git cannot answer.
    f = reachability_findings([row("a", {"g.yml": {"pull_request?"}})], TRACKED)
    eq("PR-only is UNKNOWN, not live and not dead",
       (f["dead"], len(f["unknown"])), ([], 1))
    eq("PR plus a live trigger is neither",
       reachability_findings([row("a", {"g.yml": {"pull_request?", "push"}})],
                             TRACKED),
       {"dead": [], "unknown": [], "partial": []})
    # PARTIAL is orthogonal: the file RUNS and still lost a declared trigger.
    f = reachability_findings([row("a", {"g.yml": {"push", "-schedule"}})], TRACKED)
    eq("a live workflow that lost a trigger is PARTIAL only",
       (f["dead"], f["unknown"], len(f["partial"])), ([], [], 1))
    eq("the lost trigger is named", "schedule" in f["partial"][0], True)
    # A workflow with NO live trigger is dead, and its lost triggers are not
    # ALSO reported as partial -- that would report one defect twice.
    f = reachability_findings([row("a", {"g.yml": {"-push", "-schedule"}})], TRACKED)
    eq("a dead workflow is not also reported PARTIAL",
       (f["dead"], f["partial"]), (["a/g.yml"], []))
    eq("no rows yields no findings",
       reachability_findings([], TRACKED),
       {"dead": [], "unknown": [], "partial": []})

    return fails


def hand_only_arms() -> list[str]:
    """Pin the join's verdict on five shapes, including the regression it hit.

    Case C is the one that matters: a scheduled workflow naming the full-gate
    flags in a DATA table must not vouch for a dispatch-only workflow that runs
    them. A first cut asked only "is any automatic workflow a carrier" and let
    riir-chain through.
    """
    fails: list[str] = []

    def eq(label, got, want):
        if got != want:
            fails.append(f"    {label}: got {got!r}, want {want!r}")

    def repo(name, per_wf, reach):
        return {"repo": name, "per_wf": per_wf, "reach": reach}
    FULL = {"signals": ["clippy", "--all-targets", "--all-features"], "dynamic": []}
    WEAK = {"signals": [], "dynamic": ["clippy", "--all-targets", "--all-features"]}
    cases = [
        # (row, must_be_flagged, why)
        (repo("A-auto-full", {"g.yml": FULL},
              {"g.yml": {"push", "schedule"}}), False,
         "a full gate on push+schedule is covered"),
        (repo("B-manual-only", {"g.yml": FULL},
              {"g.yml": {"workflow_dispatch"}}), True,
         "dispatch-only compile gate is a button, not a schedule"),
        (repo("C-weak-auto-masks", {"rust.yml": FULL, "drift.yml": WEAK},
              {"rust.yml": {"workflow_dispatch"},
               "drift.yml": {"schedule", "workflow_dispatch"}}), True,
         "a data-borne signal on a schedule must not vouch for a manual gate"),
        (repo("D-dead-carrier", {"g.yml": FULL}, {"g.yml": set()}), False,
         "a workflow with no live trigger is the dead block's finding"),
        (repo("E-equal", {"a.yml": FULL, "b.yml": FULL},
              {"a.yml": {"workflow_dispatch"}, "b.yml": {"push"}}), False,
         "the same surface also runs on push"),
        # A LOST push does not count as automatic coverage: the `-` prefix is
        # how reachable_triggers reports a declared trigger that cannot fire,
        # and reading it as live would vouch for a gate nothing starts.
        (repo("F-lost-push", {"g.yml": FULL},
              {"g.yml": {"workflow_dispatch", "-push"}}), True,
         "a push that CANNOT fire is not automatic coverage"),
        # pull_request is conditional, never automatic.
        (repo("G-pr-only", {"g.yml": FULL},
              {"g.yml": {"pull_request?", "workflow_dispatch"}}), True,
         "a PR trigger is a policy question, not a schedule"),
    ]
    flagged = {r["repo"] for r, _ in hand_only([c[0] for c in cases])}
    for row, want, why in cases:
        eq(f"hand_only({row['repo']}): {why}", row["repo"] in flagged, want)
    # The carriers list is what the report PRINTS under each flagged repo.
    rows = [repo("H", {"strong.yml": FULL, "weak.yml": WEAK},
                 {"strong.yml": {"workflow_dispatch"},
                  "weak.yml": {"workflow_dispatch"}})]
    eq("hand_only names only the strongest carriers",
       [c for _, c in hand_only(rows)], [["strong.yml"]])

    return fails


def survey_arms() -> list[str]:
    """parse_head_ref / mark_md / survey -- the aggregator and its two readers.

    `survey` carried ELEVEN of this module's arm-reach survivors (Issue 790):
    the script-following dedup, the per-command scoring and the data-borne
    `dynamic` split all live in it, and every one sat behind a `git` subprocess
    no arm could stage. The injection added for that is the only reason the
    rules below are assertable at all.
    """
    fails: list[str] = []

    def eq(label, got, want):
        if got != want:
            fails.append(f"    {label}: got {got!r}, want {want!r}")

    # parse_head_ref: the `?` is a VERDICT (UNMEASURED), not a formatting nicety.
    eq("parse_head_ref strips the remote", parse_head_ref("origin/develop"),
       "develop")
    eq("parse_head_ref keeps a slashed branch whole",
       parse_head_ref("origin/release/1.x"), "release/1.x")
    eq("parse_head_ref: no remote refs is ? (UNMEASURED)", parse_head_ref(""), "?")
    eq("parse_head_ref passes an unqualified ref through",
       parse_head_ref("main"), "main")

    # mark_md must agree with MARK_PLAIN about which repo is which.
    row = {"signals": [], "dynamic": ["--all-targets"], "workflows": 1}
    eq("mark_md renders DYN as a human read",
       "needs a human read" in mark_md(row, "DYN"), True)
    eq("mark_md names the data-borne signal",
       "--all-targets" in mark_md(row, "DYN"), True)
    eq("mark_md has a string for every verdict MARK_PLAIN has",
       [mark_md(row, v) is not None for v in sorted(MARK_PLAIN)],
       [True] * len(MARK_PLAIN))
    eq("mark_md distinguishes no-CI from no-gate",
       mark_md(row, "NOCI") == mark_md(row, "NONE"), False)

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        (tmp / "r" / "scripts").mkdir(parents=True)
        (tmp / "r" / "scripts" / "gate.sh").write_text(
            "cargo clippy --workspace --all-targets --all-features\n",
            encoding="utf-8")
        (tmp / "r" / "scripts" / "matrix.sh").write_text(
            'CONFIGS=("pkg:--each-feature")\nfor c in "${CONFIGS[@]}"; do :; done\n',
            encoding="utf-8")
        _tmp_wf(tmp, "r", "gate.yml",
                "on:\n  push:\n    branches: [main]\n  workflow_dispatch:\n"
                "jobs:\n  b:\n    steps:\n      - run: ./scripts/gate.sh\n")
        _tmp_wf(tmp, "r", "matrix.yml",
                "on:\n  workflow_dispatch:\n"
                "jobs:\n  b:\n    steps:\n      - run: ./scripts/matrix.sh\n")
        _tmp_wf(tmp, "r", "notes.txt", "cargo clippy --all-features\n")
        # A second workflow naming the SAME script, and one naming a script
        # that is not there. The repo-wide list must follow each real script
        # once and credit the absent one with nothing -- two halves of one
        # guard, and an `or` between them is satisfied by either.
        _tmp_wf(tmp, "r", "again.yml",
                "on:\n  workflow_dispatch:\n"
                "jobs:\n  b:\n    steps:\n      - run: ./scripts/gate.sh\n"
                "      - run: ./scripts/absent.sh\n")

        r = survey(tmp, "r", on_branch=lambda b: True, dflt="main")
        eq("survey counts only .yml/.yaml workflows", r["workflows"], 3)
        eq("survey reports the default branch it was given",
           r["default_branch"], "main")
        eq("survey follows each invoked script once",
           sorted(r["scripts"]), ["scripts/gate.sh", "scripts/matrix.sh"])
        eq("survey scores the best command PER COMMAND", r["signals"],
           ["clippy", "--workspace", "--all-targets", "--all-features"])
        # `dynamic` is the third state: a signal in the FILES but in no cargo
        # command is sitting in a data structure (a CONFIGS feature matrix),
        # which is arguably MORE thorough than one command. Scoring it low
        # would be the silent truncation this script exists to stop.
        eq("survey reports a data-borne signal as DYNAMIC, not as absent",
           r["dynamic"], ["--each-feature"])
        eq("survey: the data-borne signal is NOT in the per-command set",
           "--each-feature" in r["any"], False)
        eq("survey: a workflow whose flags are all in real commands has "
           "NO data-borne signal", r["per_wf"]["gate.yml"]["dynamic"], [])
        eq("survey attributes per workflow, not to a repo-wide bag",
           r["per_wf"]["gate.yml"]["signals"],
           ["clippy", "--workspace", "--all-targets", "--all-features"])
        eq("survey gives the matrix workflow no per-command signal",
           (r["per_wf"]["matrix.yml"]["signals"],
            r["per_wf"]["matrix.yml"]["dynamic"]),
           ([], ["--each-feature"]))
        eq("survey carries each workflow's reachability",
           (r["reach"]["gate.yml"], r["reach"]["matrix.yml"]),
           ({"push", "workflow_dispatch"}, {"workflow_dispatch"}))
        # The join this whole report exists for: the repo's strongest command
        # is real and its workflow fires on push, so it is NOT hand-only.
        eq("survey feeds hand_only: an automatic full gate is covered",
           hand_only([r]), [])
        # ... and the same repo is hand-only once the push goes inert. The
        # fixture is this workspace's actual shape: default=develop, the file
        # lives there, and the push filter names a `main` that carries no copy
        # of it -- so workflow_dispatch survives and the push cannot fire.
        r2 = survey(tmp, "r", on_branch=lambda b: b == "develop", dflt="develop")
        eq("survey feeds hand_only: an inert push is not coverage",
           [x["repo"] for x, _ in hand_only([r2])], ["r"])
        eq("survey on a repo with no workflow directory at all",
           survey(tmp, "absent", on_branch=lambda b: True,
                  dflt="main")["workflows"], 0)

    return fails


def git_probe_arms() -> list[str]:
    """`_git` / `_on_branch` / `default_branch` against a REAL git tree.

    Every other arm here injects past these three, which is what made the rest
    of the module reachable -- and is exactly why they need a fixture of their
    own: an injected probe asserts the ABSTRACTION, and the production path is
    then free to disagree with it. Measured 2026-09-15, injection alone left
    these as the module's last three unreached decisions.

    No network and no bare remote: `update-ref` writes `refs/remotes/origin/*`
    directly, which is the same ref namespace a fetch populates. Reports UNSEEN
    rather than passing when git is unavailable -- an arm that skips itself on
    a box without its tool reports a clean run over nothing.
    """
    import shutil
    import subprocess
    import tempfile

    if not shutil.which("git"):
        return ["    git_probe_arms: UNSEEN \u2014 no `git` on PATH, so the "
                "production branch probe was asserted by NOTHING"]

    fails: list[str] = []

    def eq(label, got, want):
        if got != want:
            fails.append(f"    {label}: got {got!r}, want {want!r}")

    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        r = tmp / "repo"
        r.mkdir()

        def git(*a, check=True):
            return subprocess.run(["git", "-C", str(r), *a], capture_output=True,
                                  encoding="utf-8", errors="replace",
                                  check=check).stdout.strip()

        git("init", "-q", "-b", "develop")
        git("config", "user.email", "arm@example.invalid")
        git("config", "user.name", "arm")
        # Commit ONE: no workflow. This becomes `origin/main` -- a branch that
        # exists and does not carry the file, which is the shape the whole
        # push-inert finding turns on.
        (r / "README.md").write_text("x\n", encoding="utf-8")
        git("add", ".")
        git("commit", "-q", "-m", "one")
        main_sha = git("rev-parse", "HEAD")
        # Commit TWO adds the workflow; this becomes `origin/develop`.
        wf_dir = r / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        wf = wf_dir / "g.yml"
        wf.write_text("on:\n  push:\n    branches: [main]\n"
                      "  workflow_dispatch:\njobs: {}\n", encoding="utf-8")
        git("add", ".")
        git("commit", "-q", "-m", "two")
        dev_sha = git("rev-parse", "HEAD")
        git("update-ref", "refs/remotes/origin/main", main_sha)
        git("update-ref", "refs/remotes/origin/develop", dev_sha)

        REL = ".github/workflows/g.yml"
        eq("_git returns stdout on success",
           _git(tmp, "repo", "rev-parse", "HEAD"), dev_sha)
        # A FAILING git call returns "" -- never stderr, never a traceback.
        # `_on_branch` reads that "" as absent, which is the safe direction
        # only because it is also the documented one.
        eq("_git returns empty on a failing call",
           _git(tmp, "repo", "rev-parse", "no/such/ref"), "")
        eq("_on_branch sees the file on the branch that carries it",
           _on_branch(tmp, "repo", "develop", REL), True)
        eq("_on_branch does NOT see it on a branch that does not",
           _on_branch(tmp, "repo", "main", REL), False)
        eq("_on_branch on a branch with no ref at all",
           _on_branch(tmp, "repo", "nope", REL), False)
        eq("_tracked sees a committed workflow", _tracked(tmp, "repo", REL), True)
        eq("_tracked does not see an uncommitted one",
           _tracked(tmp, "repo", ".github/workflows/absent.yml"), False)
        # The reachability verdict end to end through the REAL probe: develop
        # carries the file and the push filter names main, so the push that the
        # repo's docs advertise cannot fire.
        eq("reachable_triggers through the REAL probe: main-only push is inert",
           reachable_triggers(tmp, "repo", wf, "develop"),
           {"workflow_dispatch", "-push"})
        real_gap = push_gap(tmp, "repo", wf, "develop")
        eq("push_gap through the REAL probe names the branch lacking the file",
           "main" in real_gap, True)
        eq("...and the REAL branch probe sees that main DOES exist",
           ("carries no copy" in real_gap, "DOES NOT EXIST" in real_gap),
           (True, False))
        eq("_branch_exists: a ref that is there", _branch_exists(tmp, "repo", "main"),
           True)
        eq("_branch_exists: a ref that is not", _branch_exists(tmp, "repo", "nope"),
           False)
        # default_branch, both ways. No `origin` REMOTE exists, so its
        # `remote set-head` refresh fails harmlessly and the symbolic-ref is
        # what answers -- present, then deleted.
        git("symbolic-ref", "refs/remotes/origin/HEAD",
            "refs/remotes/origin/develop")
        eq("default_branch reads origin/HEAD", default_branch(tmp, "repo"),
           "develop")
        git("symbolic-ref", "-d", "refs/remotes/origin/HEAD")
        eq("default_branch with no origin/HEAD is ? (UNMEASURED, not a finding)",
           default_branch(tmp, "repo"), "?")

    return fails


def selftest() -> None:
    """Every classifier in this module, over fixtures rather than the workspace.

    Issue 790 measured this script at 4 killed of 74 mutants -- the WEAKEST
    instrument in the workspace -- because selftest() covered hand_only() alone
    while the text readers, the reachability rules and the surface ladder had no
    arm at all. Two repairs made the rest reachable, and both were the T4
    pattern: an EXTRACTION (surface_verdict, reachability_findings, out of
    main()) and a dependency INJECTION (the branch probe, out of `git ls-tree`).
    """
    fails = (text_reader_arms() + reachability_arms() + pool_arms()
             + surface_verdict_arms() + reachability_findings_arms()
             + survey_arms() + git_probe_arms() + hand_only_arms())
    if fails:
        raise SystemExit(
            "\u2717 ci_gate_coverage self-test FAILED \u2014 a classifier does "
            "not behave as documented:\n" + "\n".join(fails))


def main(argv: list[str]) -> int:
    selftest()
    repos = derive_repos(GIT_ROOT)
    rows = [survey(GIT_ROOT, r) for r in repos]
    md = "--markdown" in argv
    verdict = {r["repo"]: surface_verdict(r) for r in rows}

    if md:
        print(f"| repo | workflows | scripts followed | signals | full surface |")
        print("|---|---|---|---|---|")
        for r in rows:
            sig = " ".join(f"`{s}`" for s in r["signals"]) or "—"
            if r["any"] != r["signals"]:
                sig += (" <br>*(scattered across commands: "
                        + " ".join(f"`{s}`" for s in r["any"]) + ")*")
            scr = ", ".join(f"`{s}`" for s in r["scripts"]) or "—"
            mark = mark_md(r, verdict[r["repo"]])
            print(f"| `{r['repo']}` | {r['workflows']} | {scr} | {sig} | {mark} |")
    else:
        print(f"▸ {len(repos)} contract repos derived under {GIT_ROOT}")
        for r in rows:
            mark = MARK_PLAIN[verdict[r["repo"]]]
            print(f"  {mark} {r['repo']:<22} wf={r['workflows']:<2} "
                  f"scripts={len(r['scripts'])}  best-cmd: "
                  f"{' '.join(r['signals']) or '—'}"
                  + (f"   | anywhere: {' '.join(r['any'])}"
                     if r["any"] != r["signals"] else ""))

    # A PARTITION over the same ladder the marks come from -- these four used to
    # be independent predicates and summed to 17 over 16 repos (see
    # surface_verdict).
    n_full, n_dyn, n_part, n_noci = (
        sum(1 for r in rows if verdict[r["repo"]] == k)
        for k in ("FULL", "DYN", "PART", "NOCI"))
    print(f"\n{n_full}/{len(rows)} repos statically gate the full surface; "
          f"{n_dyn} build the command from data and CANNOT be classified here "
          f"(read them by hand); {n_part} partial; {n_noci} have no CI at all.")
    if n_dyn:
        for r in rows:
            if verdict[r["repo"]] == "DYN":
                print(f"  DYN? {r['repo']}: {' '.join(r['dynamic'])} appear in "
                      f"the files but in no cargo command")

    # ── Reachability, reported separately ────────────────────────────────────
    # Kept out of the rows above deliberately: those columns answer "what would
    # this gate cover", and Issue 701 R2 quotes them. This answers the prior
    # question — "does it run at all" — and a repo can score FULL above and
    # zero here. Merging them would silently restate 701's measured table.
    # A repo with no remote refs (never pushed, or fetch unavailable) yields no
    # default branch. That is an unmeasured repo, NOT a dead workflow — scoring
    # it as a finding would be the confident-green-over-nothing inversion this
    # whole family of scripts exists to prevent, pointed the other way.
    found = reachability_findings(
        rows, lambda repo, rel: _tracked(GIT_ROOT, repo, rel))
    dead, unknown, partial = found["dead"], found["unknown"], found["partial"]
    print(f"\n▸ reachability (default branch vs where the workflow file lives)")
    for r in rows:
        if not r["reach"]:
            continue
        bits = []
        for name, trig in sorted(r["reach"].items()):
            live = sorted(t for t in trig if not t.startswith("-"))
            bits.append(f"{name}[{','.join(live) if live else 'UNREACHABLE'}]")
        print(f"  {r['repo']:<22} default={r['default_branch']:<8} " + "  ".join(bits))
    if dead:
        print(f"\n  {len(dead)} workflow(s) cannot fire from any trigger — a gate "
              f"that never runs is decoration, not coverage:")
        for d in dead:
            print(f"    - {d}")
        print("  schedule/workflow_dispatch need the file on the DEFAULT branch; "
              "push/pull_request\n  need it on a branch their filter names.")
    else:
        print("  all workflows have at least one live trigger")
    if partial:
        print(f"\n  {len(partial)} workflow(s) RUN but lost a declared trigger — the "
              f"file fires on one\n  trigger while another it declares (and its docs "
              f"may advertise) never does:")
        for w in partial:
            print(f"    ! {w}")
    if unknown:
        print(f"\n  {len(unknown)} workflow(s) NOT classified — no remote refs to "
              f"read a default branch from, or PR-only in a repo whose\n  policy "
              f"this script cannot see. Unmeasured, not clean:")
        for u in unknown:
            print(f"    ? {u}")

    # ── The join: coverage x reachability ────────────────────────────────────
    # The two blocks above are each honest on its own and, read one after the
    # other, add up to a claim neither of them makes. The top table credits
    # riir-neuron-db with `--all-targets --all-features`; the reachability
    # table says its rust.yml fires on `workflow_dispatch` alone. Nothing
    # crossed them, so the repo read as covered while the command it was
    # credited for only ever ran when a human clicked it. A dispatch-only gate
    # is a button, not a schedule — the same "decoration, not coverage" the
    # dead-workflow block above says out loud, one step less obvious because
    # the workflow genuinely can run.
    #
    # Note what this deliberately does NOT do: it leaves the columns above
    # untouched. They answer "what would this gate cover" and Issue 701 R2
    # quotes their numbers; this answers "does anything start it".
    handonly = hand_only(rows)
    if handonly:
        print(f"\n▸ {len(handonly)} repo(s) whose compile/lint gate fires ONLY by "
              f"hand — the command is\n  real and the workflow can run, but no "
              f"schedule and no push ever starts it:")
        for r, carriers in handonly:
            print(f"    ⌾ {r['repo']}")
            for n in carriers:
                trig = sorted(t for t in r["reach"].get(n, ()) if not t.startswith("-"))
                sig = (" ".join(r["per_wf"][n]["signals"])
                       or " ".join(r["per_wf"][n]["dynamic"]) + " (in data)")
                print(f"        {n}[{','.join(trig) or 'UNREACHABLE'}]  {sig}")
                gap = push_gap(GIT_ROOT, r["repo"], WF_DIR(r["repo"]) / n,
                               r["default_branch"])
                if gap:
                    print(f"          └─ {gap}")
        print("  Several of these are a DOCUMENTED owner call (main-only, to spend\n"
              "  no Actions minutes on develop pushes) — read the workflow preamble\n"
              "  before filing. The finding is not that the choice is wrong; it is\n"
              "  that a main-only push cannot fire while main carries no copy of\n"
              "  the file, so the intended promote-to-main trigger is inert too.\n"
              "  ⛔ Read the two causes apart. `DOES NOT EXIST` is strictly worse\n"
              "  than `carries no copy`: the second is repaired by promoting the\n"
              "  file, and the first cannot be, because the filter names a branch\n"
              "  the repo does not have. That lane is not reduced, it is ZERO —\n"
              "  the gate runs only when a human clicks it, forever.")
    else:
        print("\n▸ every repo carrying a compile/lint command has an automatic "
              "trigger for it")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
