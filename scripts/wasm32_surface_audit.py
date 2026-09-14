#!/usr/bin/env python3
"""Which packages carry POSITIVE wasm32 code, and does any lane compile them?

The wasm32 audit family (Issue 737) closed six axes, all of them about *how* a
lane compiles what it names: the triple, the `target_feature` arm, the feature
set, the arm reached via a dependent, the separate workspace, `check`-vs-lints.
This is the seventh axis and it is one level up — **is what the lane names the
whole surface?**

Found in seal-remake (`.issues/010` T2): the root package carried a positive
`#[cfg(target_arch = "wasm32")]` block that no row built and, measured, none
*could* — and the block had been uncompilable since it was written, because it
called a function declared `#[cfg(not(target_arch = "wasm32"))]`.

⛔ The predicate is the POSITIVE cfg. `not(target_arch = "wasm32")` is an
ordinary native-only guard and means the file has NO browser code (riir-ai
`.issues/892` T4); counting it inflates every number here. Comment lines are
excluded too — prose explaining a cfg is not a cfg, and a doc block that
mentions one would otherwise make a file look like browser code.

A **report, not a gate** (exit 0). Two floors are printed rather than pinned:
a ceiling ("0 uncovered") is green over whatever the instrument can see, so
the walk size has to be readable underneath it.

The eighth axis (Issue 774) is the DEPENDENCY EDGE: a row that selects a
package compiles that package's in-repo PATH DEPS for wasm32 too, so a
package with positive cfgs that no row names can still be covered — the
measured case was riir-shader's core+effects, built by every
`-p riir-shader-showcase --target wasm32` bundle build while the row-based
resolver read them UNCOVERED. The fix is a THIRD verdict, `✓ by-dep`:
reached from a named/derived package through non-optional in-repo path-dep
edges (plain `[dependencies]` plus target tables whose cfg positively names
`wasm32`; `workspace = true` entries resolve through the root table).
NEVER folded into NAMED — the distinction is load-bearing: a by-dep
package's lane dies by an innocent dep-graph edit in someone ELSE's
manifest, and the reader must know which kind of coverage they have. The
credit is reachability, not compile-verifiedness — but it is not vacuous
either: a broken wasm32 arm in a by-dep package breaks the named row's own
build the next time that row runs, which is exactly where the 010-class
catch would surface. Deliberately NOT credited: dev/build deps (host-side),
optional deps (feature off in the row), target tables gating to native, and
cross-repo path deps (a sibling's coverage is answered by the sibling's own
run). seal-poc-submodule is the standing negative control: deliberately
excluded from its repo's CI and depended on by nothing, it stays UNCOVERED.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import NamedTuple

WORKSPACE = Path(__file__).resolve().parent.parent.parent

CFG_RE = re.compile(r'target_arch\s*=\s*"wasm32"')
# `git grep -E` is POSIX ERE: no `\s`, no `\b` (the documented workspace trap).
# A Python pattern handed to git matches NOTHING and the walk reports a
# confident zero — which is what the floor below exists to catch, and did.
CFG_ERE = r'target_arch *= *"wasm32"' 
NEG_RE = re.compile(r'not\s*\(\s*target_arch\s*=\s*"wasm32"')
COMMENT_RE = re.compile(r"^\s*(//|/\*|\*)")
PKG_NAME_RE = re.compile(r'^\s*name\s*=\s*"([^"]+)"', re.M)
CARGO_ROW_RE = re.compile(r"cargo\s+(?:\+\S+\s+)?(check|clippy|build|test)\b")
DASH_P_RE = re.compile(r"(?:-p|--package)[= ]+([A-Za-z0-9_-]+)")
# `-p "$pkg"` / `-p ${p}` — a lane whose package list is DERIVED at run time
# (katgpt-rs's layer 2b builds one, deliberately, so a new wasm32-bearing
# crate joins by existing). A static reader cannot enumerate it. Calling that
# UNCOVERED would manufacture a finding out of the better design.
# `--manifest-path "$unit/Cargo.toml"` selects a package just as `-p` does, and
# riir-dapps + riir-deployer both drive their wasm32 lanes that way — over a
# DERIVED unit list, which is the stronger design. Matching only `-p $VAR`
# read both as bare rows, mis-credited the repo ROOT package, and reported
# their real Worker crates as UNCOVERED. Two false findings from one missing
# alternative.
DASH_P_VAR_RE = re.compile(r"(?:-p|--package|--manifest-path)[= ]+[\"']?\$")
MANIFEST_PATH_RE = re.compile(r"--manifest-path[= ]+[\"']?([^\"'\s]+)")

# Where a compile lane can live. Tracked files only — a filesystem walk picks
# up vendored drops no repo owns (the trap `trap_exit_launder_audit` hit).
LANE_GLOBS = ["scripts/*", ".github/*", ".github/workflows/*", "*.sh"]

# Vendored upstream code is not this workspace's to gate (Issue 738 T3): the
# lanes themselves exclude `vendor/` (riir-ai's layer 1.22 derives its `-p`
# list with `grep -v '^vendor/'`), so a vendored fork's wasm32 code would show
# UNRESOLVED forever while the workspace's own answer — "not ours" — is
# already encoded in the lane. riir-ai's tracked `wgpu-hal-30.0.0` fork (11
# positive sites, Plan 536 / Issue 663) is the case that forced the question.
VENDOR_PARTS = ("vendor/", "/vendor/")


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, encoding="utf-8", errors="replace"
    )
    return r.stdout if r.returncode == 0 else ""


def derive_population(root: Path | None = None) -> list[Path]:
    """Every sibling carrying a BOUNDARY.md contract. Derived, never typed.

    `.git` must be a DIRECTORY: a throwaway worktree's `.git` is a file, and
    counting one would double-count a repo already in the walk.

    `root` is optional and defaults to WORKSPACE (Issue 788): a predicate that
    hard-codes its root cannot be run against the synthetic workspace
    `population_sync_gate.py` uses, which is the half of that gate that works
    in CI. Two of the ten were unparameterised and therefore untestable there.
    """
    ws = WORKSPACE if root is None else Path(root)
    return sorted(
        (
            d
            for d in ws.iterdir()
            if d.is_dir() and (d / "BOUNDARY.md").is_file() and (d / ".git").is_dir()
        ),
        key=lambda p: p.name,
    )


def package_of(repo: Path, rel: str) -> str | None:
    """Nearest ancestor Cargo.toml declaring a [package] name."""
    d = (repo / rel).parent
    while True:
        manifest = d / "Cargo.toml"
        if manifest.is_file():
            try:
                text = manifest.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            if "[package]" in text:
                after = text.split("[package]", 1)[1]
                m = PKG_NAME_RE.search(after)
                if m:
                    return m.group(1)
        if d == repo or repo not in d.parents:
            return None
        d = d.parent


def positive_packages(repo: Path) -> tuple[dict[str, int], list[str], int]:
    """(package -> positive cfg site count, positive files, files walked).

    The walk size is ALL tracked wasm32-mentioning .rs (minus vendored), not
    just the positive ones: the floor's job is to catch a BLIND grep, and a
    grep that silently lost the native-only-guard half of the corpus would
    still show every positive file. Original-floor semantics (Issue 738's
    walk-size-next-to-verdict rule)."""
    files = [
        f
        for f in git(repo, "grep", "-lE", CFG_ERE, "--", "*.rs").splitlines()
        if f and not f.startswith(VENDOR_PARTS) and VENDOR_PARTS[1] not in f"/{f}"
    ]
    hits: dict[str, int] = {}
    positive_files: list[str] = []
    for rel in files:
        try:
            lines = (repo / rel).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        n = sum(
            1
            for ln in lines
            if CFG_RE.search(ln) and not COMMENT_RE.match(ln) and not NEG_RE.search(ln)
        )
        if n:
            pkg = package_of(repo, rel) or "(unattributed)"
            hits[pkg] = hits.get(pkg, 0) + n
            positive_files.append(rel)
    return hits, positive_files, len(files)


def logical_lines(text: str) -> list[str]:
    """Join shell/YAML backslash continuations.

    Without this a lane written as `cargo clippy \\` / `--target wasm32-...`
    is invisible: the triple and the verb land on different physical lines.
    That defect was in the first draft of this audit and it read two repos as
    having zero lanes minutes after their lanes were landed.
    """
    out, buf = [], ""
    for raw in text.splitlines():
        stripped = raw.rstrip()
        if stripped.endswith("\\"):
            buf += stripped[:-1] + " "
            continue
        out.append(buf + stripped)
        buf = ""
    if buf:
        out.append(buf)
    return out


def lane_coverage(repo: Path) -> tuple[set[str], int, int, int, int, list[str]]:
    """(literally-named pkgs, rows, --workspace rows, derived rows, bare rows,
    row-bearing files). The last item feeds the resolver below: an upgrade
    may only cite a file that already carries a wasm32 cargo row, so a DEPLOY
    path mentioning a unit can never upgrade a package the audit family's
    founding lesson says is not gated (737: `build-*.sh` is not a gate)."""
    named: set[str] = set()
    rows = wildcards = derived = 0
    root_only = 0
    row_files: list[str] = []
    seen: set[str] = set()
    for glob in LANE_GLOBS:
        for rel in git(repo, "ls-files", "--", glob).splitlines():
            if not rel or rel in seen:
                continue
            seen.add(rel)
            try:
                text = (repo / rel).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            file_has_row = False
            for ln in logical_lines(text):
                if "wasm32-unknown-unknown" not in ln or not CARGO_ROW_RE.search(ln):
                    continue
                # A quoted usage string / echo is documentation, not a lane.
                if re.match(r"\s*(#|//|echo\b|printf\b)", ln):
                    continue
                rows += 1
                file_has_row = True
                if DASH_P_VAR_RE.search(ln):
                    derived += 1
                    continue
                mp = MANIFEST_PATH_RE.search(ln)
                if mp:
                    # A literal manifest path names exactly one package.
                    pkg = package_of(repo, mp.group(1))
                    if pkg:
                        named.add(pkg)
                    else:
                        derived += 1
                    continue
                pkgs = DASH_P_RE.findall(ln)
                if pkgs:
                    named.update(pkgs)
                elif "--workspace" in ln or "--all" in ln:
                    # Covers this workspace's members. Which packages those
                    # are is the separate-workspace axis — undecidable here.
                    wildcards += 1
                else:
                    # Neither `-p` nor `--workspace`: cargo compiles exactly
                    # the package rooted at the invocation directory. That IS
                    # decidable, so it credits the root package by name
                    # instead of parking it in UNRESOLVED.
                    root_only += 1
            if file_has_row:
                row_files.append(rel)
    return named, rows, wildcards, derived, root_only, row_files


# The derivation formula shared by every Shape-A lane in the workspace
# (katgpt-rs full_gate.sh layer 2b, riir-ai layer 1.22, riir-mmorpg-examples
# layer 2c): map wasm32-bearing files under `crates/<name>/src/` to `-p
# <name>`. Both sed spellings occur — BRE `\([^/]*\)` (katgpt-rs, riir-ai)
# and ERE `([^/]*)` (riir-mmorpg-examples' `sed -E`) — so the backslash is
# optional in the detection pattern. Detection is the literal pattern text,
# and the resolver RE-DERIVES the set with the same rule rather than trusting
# the script — a lane whose grep filter drifts stops matching its own
# formula's scope only if the scope text drifts too, and each repo's own
# membership pin is the second net.
DERIVED_SCOPE_RE = re.compile(r"crates/\\?\(\[\^/\]\*\\?\)/src/")
# A unit-dir token (Shape B): `cloudflare/<dir>` pinned literally in a
# row-bearing lane (riir-dapps L7, riir-deployer 5/5, riir-mmorpg-examples 2e).
UNIT_TOKEN_RE = re.compile(r"\b((?:cloudflare|wasm)/[A-Za-z0-9_-]+)")


def resolve_unresolved(
    repo: Path,
    hits: dict[str, int],
    positive_files: list[str],
    row_texts: list[str],
    named: set[str],
) -> tuple[set[str], list[str]]:
    """UNRESOLVED packages the lane provably selects, per Issue 738 T1.

    Two evidence rules, both requiring row-bearing files only (a DEPLOY path
    mentioning a unit can never upgrade a package — the audit family's
    founding lesson is that `build-*.sh` is not a gate):
    A. the repo's lane carries the workspace's standard derivation formula
       (`crates/([^/]*)/src/` -> `-p <name>`); any package with a positive
       site under that scope is selected by construction — the derivation
       enumerates exactly the packages the scope matches. Deliberately NOT
       extended to root-`src/` sites: katgpt-rs's derivation appends the root
       package, riir-ai's and riir-mmorpg-examples' do not, and the one repo
       where it matters already names its root via a bare row.
    B. a unit-dir token whose manifest names the package: the membership pin
       lists the unit literally, and the pin reds when the derived set
       changes, so the lane cannot silently stop selecting it.
    Packages already literally named by a row skip the resolver. Everything
    else stays UNRESOLVED — the bucket remains the honest "a human has not
    answered this yet", never folded into NAMED.
    Returns (upgraded packages, notes explaining each upgrade).
    """
    upgraded: set[str] = set()
    notes: list[str] = []
    shape_a = any(DERIVED_SCOPE_RE.search(t) for t in row_texts)
    all_text = "\n".join(row_texts)
    if shape_a:
        scope_pkgs = {
            package_of(repo, rel)
            for rel in positive_files
            if rel.startswith("crates/") and "/src/" in rel
        }
        scope_pkgs.discard(None)
        for pkg in scope_pkgs:
            if pkg in hits and pkg not in named:
                upgraded.add(pkg)
                notes.append(f"{pkg}: derived-scope site under crates/*/src/ (Shape A)")
    for pkg in hits:
        if pkg in named or pkg in upgraded:
            continue
        # B: unit-dir token whose manifest names this package. The manifest
        # must EXIST: package_of's walk probes repo/Cargo.toml as a fallback
        # (correct for site attribution), so a phantom `cloudflare/<x>` token
        # in a row file would otherwise resolve to the repo ROOT package and
        # upgrade it on nothing (caught by the canary, not by reading).
        for m in UNIT_TOKEN_RE.finditer(all_text):
            unit = m.group(1)
            unit_manifest = repo / f"{unit}/Cargo.toml"
            if not unit_manifest.is_file():
                continue
            unit_pkg = package_of(repo, f"{unit}/Cargo.toml")
            if unit_pkg == pkg:
                upgraded.add(pkg)
                notes.append(f"{pkg}: membership pin names {unit} (Shape B)")
                break
    return upgraded, notes


# ── Coverage-by-dep (Issue 774) ─────────────────────────────────────────────
# The row predicate above is DEP-BLIND: `-p riir-shader-showcase --target
# wasm32` compiles the showcase's in-repo path deps too, so riir-shader's
# core+effects read UNCOVERED while every bundle build compiles them
# (measured: `cargo check -p riir-shader-effects --target
# wasm32-unknown-unknown` exits 0, 2026-09-14). The graph below credits
# exactly those edges — as a THIRD verdict, never folded into NAMED: by-dep
# coverage dies by a dep-graph edit in someone else's manifest, and the
# reader must see which kind of coverage they hold.


def manifest_pkg_names(repo: Path) -> dict[str, str]:
    """Tracked Cargo.toml rel-paths -> [package] name (virtual manifests drop).

    Tracked only, vendored excluded — same population rules as the cfg walk.
    """
    out: dict[str, str] = {}
    for rel in git(repo, "ls-files", "--", "*.toml").splitlines():
        if not rel or Path(rel).name != "Cargo.toml":
            continue
        if rel.startswith(VENDOR_PARTS) or VENDOR_PARTS[1] in f"/{rel}":
            continue
        try:
            with (repo / rel).open("rb") as fh:
                data = tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError):
            continue
        pkg = (data.get("package") or {}).get("name")
        if isinstance(pkg, str):
            out[rel] = pkg
    return out


def credited_dep_tables(data: dict[str, object]) -> list[dict[str, object]]:
    """The dependency tables a wasm32 row compiles: plain [dependencies] plus
    [target.'cfg(...wasm32...)'.dependencies]. Native-target tables,
    dev-dependencies and build-dependencies are NOT credited — the first
    doesn't apply to the triple, the latter two build for the host."""
    tables: list[dict[str, object]] = []
    deps = data.get("dependencies")
    if isinstance(deps, dict):
        tables.append(deps)
    targets = data.get("target")
    if isinstance(targets, dict):
        for cfg, sub in targets.items():
            if not CFG_RE.search(cfg) or NEG_RE.search(cfg):
                continue
            if isinstance(sub, dict) and isinstance(sub.get("dependencies"), dict):
                tables.append(sub["dependencies"])
    return tables


def dep_graph(repo: Path, names: dict[str, str]) -> dict[str, set[str]]:
    """package -> in-repo packages it path-depends on for a wasm32 build.

    Non-optional path deps only. `workspace = true` entries resolve through
    the ROOT [workspace.dependencies] table. Cross-repo path targets are
    dropped: a sibling's coverage is answered by the sibling's own run, and
    crediting it here would make this repo's verdict depend on another
    repo's manifests. Edge targets are named by their OWN [package] table,
    so renames (`foo = { path = "../bar" }`) land on the real name."""
    root: dict[str, object] = {}
    try:
        with (repo / "Cargo.toml").open("rb") as fh:
            root = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        root = {}
    ws = root.get("workspace")
    ws_deps = ws.get("dependencies") if isinstance(ws, dict) else None
    ws_deps = ws_deps if isinstance(ws_deps, dict) else {}
    graph: dict[str, set[str]] = {}
    for rel, pkg in names.items():
        try:
            with (repo / rel).open("rb") as fh:
                data = tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError):
            continue
        edges: set[str] = set()
        manifest_dir = os.path.dirname(rel) or "."
        for table in credited_dep_tables(data):
            for key, spec in table.items():
                if not isinstance(spec, dict):
                    continue  # version-string registry dep
                if spec.get("optional") is True:
                    continue  # compiles only when the row enables its feature
                base = manifest_dir
                if spec.get("workspace") is True:
                    spec = ws_deps.get(key)
                    if not isinstance(spec, dict):
                        continue
                    # workspace-table paths are WORKSPACE-ROOT-relative,
                    # not member-manifest-relative
                    base = "."
                path = spec.get("path")
                if not isinstance(path, str) or not path:
                    continue
                target_dir = os.path.normpath(os.path.join(base, path))
                target_rel = os.path.join(target_dir, "Cargo.toml").replace(os.sep, "/")
                target = names.get(target_rel)
                if target and target != pkg:
                    edges.add(target)
        if edges:
            graph[pkg] = edges
    return graph


def by_dep_cover(
    graph: dict[str, set[str]], seeds: set[str], hits: dict[str, int]
) -> tuple[set[str], list[str]]:
    """(by-dep packages, chain notes). BFS from the seeds — everything a row
    provably compiles, literally named OR derived — through path-dep edges.
    A reached package carrying positive cfgs that no row selects itself is
    covered-by-dep. The note names the seed and the edge chain so the credit
    is auditable: `core: path-dep closure of showcase (showcase -> core)`."""
    parent: dict[str, str] = {}
    seen: set[str] = set(seeds)
    frontier = sorted(seeds)
    while frontier:
        cur = frontier.pop(0)
        for nxt in sorted(graph.get(cur, ())):
            if nxt in seen:
                continue
            seen.add(nxt)
            parent[nxt] = cur
            frontier.append(nxt)
    bydep = {p for p in seen if p in hits and p not in seeds}
    notes: list[str] = []
    for pkg in sorted(bydep):
        chain = [pkg]
        cur = pkg
        while cur in parent:
            cur = parent[cur]
            chain.append(cur)
        chain.reverse()
        notes.append(f"{pkg}: path-dep closure of {chain[0]} ({' -> '.join(chain)})")
    return bydep, notes


def verdict_for(
    pkg: str, named: set[str], resolved: set[str], bydep: set[str], reachable: bool
) -> str:
    """The single classification, shared by main() and the --self-test
    canary — two copies would be the two-parsers-disagree trap the
    required-features family documents."""
    if pkg in named:
        return "\u2713 named"
    if pkg in resolved:
        return "\u2713 derived"
    if pkg in bydep:
        return "\u2713 by-dep"
    if reachable:
        return "? UNRESOLVED"
    return "\u2717 UNCOVERED"


class RepoSurface(NamedTuple):
    """One repo's wasm32 surface, bucketed — the verdict AND its population.

    Extracted from `main()` by Issue 785 so the workstation verdict half
    (`wasm32_surface_drift_sweep.py`) consumes the SAME 738/774 resolution
    rules the report does. A second copy of those rules would be the
    two-parsers-disagree trap the required-features family documents, and
    they are the whole instrument here: the derived-row upgrade (738 T1) and
    the path-dep closure (774) are what separate 25 NAMED from 17 false
    UNCOVERED.
    """

    files_walked: int
    hits: dict           # package -> positive-cfg site count
    rows: int
    wildcards: int
    derived: int
    root_only: int
    named: set
    resolved: set
    bydep: set
    res_notes: list
    dep_notes: list

    @property
    def reachable(self) -> bool:
        """A `--workspace` or derived row exists — the precondition that makes
        an unclassified package UNRESOLVED rather than UNCOVERED."""
        return (self.wildcards + self.derived) > 0

    def verdicts(self) -> dict:
        """package -> verdict string, for every package with positive cfgs."""
        return {
            pkg: verdict_for(pkg, self.named, self.resolved, self.bydep,
                             self.reachable)
            for pkg in self.hits
        }

    def bucket(self, mark: str) -> list:
        return sorted(p for p, v in self.verdicts().items() if v == mark)


def classify_repo(repo: Path) -> RepoSurface:
    """Walk + classify one repo. No printing — the caller decides the shape."""
    hits, positive_files, files_walked = positive_packages(repo)
    if not hits:
        return RepoSurface(files_walked, {}, 0, 0, 0, 0,
                           set(), set(), set(), [], [])
    named, rows, wildcards, derived, root_only, row_files = lane_coverage(repo)
    row_texts = []
    for rel in row_files:
        try:
            row_texts.append((repo / rel).read_text(encoding="utf-8",
                                                    errors="replace"))
        except OSError:
            pass
    if root_only:
        root_pkg = package_of(repo, "Cargo.toml")
        if root_pkg:
            named.add(root_pkg)
    # Issue 738 T1: resolve the derived-row question per package, with the
    # evidence rule recorded per upgrade. UNRESOLVED stays UNRESOLVED for
    # anything no rule covers — the bucket remains the honest "a human has not
    # answered this yet", never folded into NAMED.
    resolved, res_notes = resolve_unresolved(repo, hits, positive_files,
                                             row_texts, named)
    # Issue 774: seeds are EVERYTHING a row provably compiles — the
    # literally-named set plus the derived upgrades — because a derived row's
    # `-p` list compiles its path-dep closure exactly like a literal one does.
    seeds = set(named) | set(resolved)
    graph = dep_graph(repo, manifest_pkg_names(repo))
    bydep, dep_notes = by_dep_cover(graph, seeds, hits)
    return RepoSurface(files_walked, hits, rows, wildcards, derived, root_only,
                       named, resolved, bydep, res_notes, dep_notes)


def self_test() -> int:
    """Prove the by-dep detectors fire, BOTH directions (Issue 774 landing).

    Five canary crates in a throwaway git repo:
      canary-a  named by the lane row        -> ✓ named
      canary-b  non-optional path dep of a   -> ✓ by-dep
      canary-c  depended on by nothing       -> ✗ UNCOVERED
      canary-d  optional path dep of a       -> ✗ UNCOVERED (not credited)
      canary-e  workspace=true dep of a      -> ✓ by-dep (root-table resolve)
    The c/d shape is the seal-remake `.issues/010` lineage — the real catch
    this upgrade must NOT collapse. A verdict drift reds here instead of
    shipping a silent misclassification.
    """
    tmp = Path(tempfile.mkdtemp(prefix="wasm32_bydep_canary_"))
    try:
        (tmp / "scripts").mkdir(parents=True)
        (tmp / "Cargo.toml").write_text(
            "[workspace]\nmembers = [\n"
            + "".join(f'    "crates/canary-{c}",\n' for c in "abcde")
            + "]\n\n[workspace.dependencies]\n"
            + 'canary-e = { path = "crates/canary-e" }\n',
            encoding="utf-8",
        )
        a_deps = (
            "\n[dependencies]\n"
            'canary-b = { path = "../canary-b" }\n'
            'canary-d = { path = "../canary-d", optional = true }\n'
            "canary-e = { workspace = true }\n"
        )
        for c in "abcde":
            d = tmp / "crates" / f"canary-{c}"
            (d / "src").mkdir(parents=True)
            (d / "Cargo.toml").write_text(
                f'[package]\nname = "canary-{c}"\nversion = "0.0.0"\nedition = "2021"\n'
                + (a_deps if c == "a" else ""),
                encoding="utf-8",
            )
            (d / "src" / "lib.rs").write_text(
                '#[cfg(target_arch = "wasm32")]\npub fn w() {}\n', encoding="utf-8"
            )
        (tmp / "scripts" / "lane.sh").write_text(
            "cargo build -p canary-a --target wasm32-unknown-unknown\n",
            encoding="utf-8",
        )
        for args in (
            ("init", "-q"),
            ("add", "-A"),
            ("-c", "user.name=canary", "-c", "user.email=canary@x",
             "commit", "-qm", "canary"),
        ):
            subprocess.run(["git", "-C", str(tmp), *args], capture_output=True, encoding="utf-8", errors="replace")
        hits, positive_files, _ = positive_packages(tmp)
        named, _, wildcards, derived, root_only, row_files = lane_coverage(tmp)
        row_texts = []
        for rel in row_files:
            try:
                row_texts.append((tmp / rel).read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
        if root_only:
            root_pkg = package_of(tmp, "Cargo.toml")
            if root_pkg:
                named.add(root_pkg)
        resolved, _ = resolve_unresolved(tmp, hits, positive_files, row_texts, named)
        graph = dep_graph(tmp, manifest_pkg_names(tmp))
        bydep, _ = by_dep_cover(graph, set(named) | set(resolved), hits)
        got = {
            p: verdict_for(p, named, resolved, bydep, (wildcards + derived) > 0)
            for p in hits
        }
        expect = {
            "canary-a": "\u2713 named",
            "canary-b": "\u2713 by-dep",
            "canary-c": "\u2717 UNCOVERED",
            "canary-d": "\u2717 UNCOVERED",
            "canary-e": "\u2713 by-dep",
        }
        ok = True
        for pkg in sorted(expect):
            want, actual = expect[pkg], got.get(pkg, "(missing)")
            good = want == actual
            ok = ok and good
            print(f"  {'ok' if good else 'FAIL':<4} {pkg}: want {want!r}, got {actual!r}")
        print(f"\n  {'PASS' if ok else 'FAIL'} — all five canary verdicts hold" if ok
              else "\n  FAIL — a verdict drifted")
        return 0 if ok else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    argv = sys.argv[1:]
    if argv == ["--self-test"]:
        print("wasm32 SURFACE audit — by-dep canary (Issue 774)\n")
        return self_test()
    repos = [Path(a).resolve() for a in argv] if argv else derive_population()
    print(f"wasm32 SURFACE audit — {len(repos)} repo(s)\n")
    tot_pos_pkgs = tot_uncov = tot_unres = tot_files = tot_bydep = 0
    findings: list[tuple[str, str, int]] = []
    unresolved: list[tuple[str, str, int]] = []
    for repo in repos:
        # ONE classifier, shared with the workstation verdict half (Issue 785).
        # The 738 derived-row upgrade and the 774 path-dep closure ARE the
        # instrument here — they are what separate 25 NAMED from 17 false
        # UNCOVERED — so the sweep imports them rather than restating them.
        s = classify_repo(repo)
        tot_files += s.files_walked
        if not s.hits:
            if s.files_walked:
                print(f"  {repo.name}: {s.files_walked} file(s) mention wasm32, "
                      f"0 with POSITIVE cfgs (all native-only guards) — nothing to compile")
            continue
        tot_pos_pkgs += len(s.hits)
        print(f"  {repo.name}: {s.files_walked} file(s) walked · "
              f"{len(s.hits)} package(s) with positive cfgs · "
              f"{s.rows} wasm32 row(s) ({s.wildcards} --workspace, "
              f"{s.derived} derived, {s.root_only} root-only)")
        for pkg, mark in sorted(s.verdicts().items()):
            if mark == "? UNRESOLVED":
                tot_unres += 1
                unresolved.append((repo.name, pkg, s.hits[pkg]))
            elif mark == "✗ UNCOVERED":
                tot_uncov += 1
                findings.append((repo.name, pkg, s.hits[pkg]))
            elif mark == "✓ by-dep":
                tot_bydep += 1
            print(f"      {mark:<14} {pkg}  ({s.hits[pkg]} site(s))")
        # sorted: the resolver's note sets iterate in PYTHONHASHSEED order,
        # and an unsorted report is not diffable run-to-run (cosmetic-only
        # churn was masking real verdict flips in the landing diff).
        for note in sorted(s.res_notes):
            print(f"        · {note}")
        for note in sorted(s.dep_notes):
            print(f"        · {note}")
    print()
    print(f"  floors — {tot_files} file(s) walked over {len(repos)} repo(s); "
          f"{tot_pos_pkgs} package(s) with positive wasm32 cfgs")
    print(f"  {tot_pos_pkgs - tot_uncov - tot_unres - tot_bydep} NAMED · "
          f"{tot_bydep} BY-DEP · {tot_unres} UNRESOLVED · {tot_uncov} UNCOVERED")
    if findings:
        print("\n  ⛔ UNCOVERED — the repo has NO wasm32 row that could reach "
              "these at all:")
        for repo, pkg, n in findings:
            print(f"      {repo}: {pkg} ({n} positive site(s))")
    if unresolved:
        print("\n  ? UNRESOLVED — a wildcard or derived row exists; whether it "
              "reaches these\n    is the separate-workspace axis (737 #5), "
              "undecidable statically. NOT clean:")
        for repo, pkg, n in unresolved:
            print(f"      {repo}: {pkg} ({n} positive site(s))")
    print("\n  A report, not a gate — exit 0. Neither bucket is automatically a "
          "defect: a\n  package can be unbuildable for wasm32 by construction "
          "(seal-remake's authority\n  bin), where the repair is deleting the "
          "dead arm, not adding a row.\n")
    print("  Resolution (Issue 738 T1): a derived-row package upgrades to ✓ "
          "derived only\n  on static evidence from a row-bearing lane file — "
          "Shape A: the repo carries\n  the workspace's standard derivation "
          "formula (crates/([^/]*)/src/ -> -p <name>)\n  and the package has a "
          "site in that scope; Shape B: a membership pin names\n  a unit dir "
          "whose manifest IS the package. Anything else stays ? UNRESOLVED —\n  "
          "a human has not answered it, and that is the bucket's job.")
    print("\n  By-dep (Issue 774): a ✓ by-dep package is reached from a "
          "named/derived\n  package through non-optional in-repo path-dep "
          "edges (workspace-table deps\n  resolved; plain + wasm32-target "
          "tables). Reachability, not compile-proof —\n  but not vacuous "
          "either: a broken wasm32 arm there fails the named\n  row's own "
          "build. Optional, dev/build, native-target, and cross-repo\n  "
          "edges credit nothing. --self-test proves all five canary "
          "verdicts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
