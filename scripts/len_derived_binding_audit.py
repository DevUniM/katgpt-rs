#!/usr/bin/env python3
"""The `.len()`-derived kernel dimension vs oversized-buffer join (riir-train 515 T1/T3).

A CubeCL kernel that derives a structural dimension from a bound buffer's
`.len()` — `n_positions = kv.len() / 2 / kv_stride` — computes that dimension
from the buffer's **declared size**, NOT from the length metadata passed to
`BufferArg::from_raw_parts` (measured: riir-ai `3e00c93e0`, riir-train `.issues/511`).
Hand such a kernel a buffer whose declared size exceeds the live range and it
silently derives the WRONG shape — reads never-written memory, writes a
plausible-looking (measured: identically-zero) result. No panic, no NaN.

The defect is the JOIN of two facts that live in different files:

- HALF A: the kernel derives a dimension from `.len()` (in-kernel), and
- HALF B: the bound handle's DECLARED SIZE can exceed the live range
  (a persistent struct-field handle, a capacity-sized `client.empty()`, or a
  host slice that is itself a reused scratch buffer).

A report over either half alone is noise — almost every `.len()` kernel is
correct because its call sites bind exactly-sized buffers. This script reports
the join, classifying every bind site of every `.len()`-deriving kernel:

- `PERSISTENT`   — the handle expression is a struct field (`self.x`,
  `cache.x`, ...): the declared size is whatever the field was created as.
  The compact_temp class. Needs eyes unless the field is provably exact.
- `CAPACITY`     — the handle is `client.empty(EXPR)` (or `create_buffer`)
  where EXPR names a capacity/block-size constant or field rather than a
  logical dim. Declared size ≠ live range by construction. JOINED finding.
- `PARAM-LOCAL`  — the handle is created at the bind site from a local
  slice or a logical-dim `empty()` — declared size follows the logical dim
  at this site (the caller of an outer wrapper can still lie; depth-1 only).
- `UNRESOLVED`   — the handle is a wrapper parameter: provenance lives one
  level up and this instrument does not walk callers. A work list, never a
  clean verdict.

## What this is NOT

A **report, not a gate** — always exit 0 (the `cfg_gated_target_audit.py`
discipline). The static join cannot prove a PERSISTENT handle wrong (the field
may be exactly sized — the norm-gamma handles are), and it cannot walk wrapper
chains through re-exports, which the workspace already documents as defeating
grep. The runtime half of this defense is `assert_binding_derives_units`
(riir-ai `cubecl_runtime.rs`, riir-train 515 T4) — this report names the
launchers that should grow it next.

## Population is derived, walk is floored

Repos come from the workspace walk (root `BOUNDARY.md` AND `.git`), never a
typed list. The `min_rs_files` floor refuses the confident-zero: a regex
regression that recognises no kernels must RED, not print 0 findings.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ── HALF A: cube kernels that derive dims from `.len()` ────────────────────

CUBE_FN_RE = re.compile(
    r"#\[cube\((?P<attrs>[^)]*)\)\]\s*(?:pub\s+)?fn\s+(?P<name>\w+)\s*\((?P<params>[^)]*)\)",
)
LEN_USE_RE = re.compile(r"\b(?P<buf>\w+)\.len\(\)")

# ── Bind sites ──────────────────────────────────────────────────────────────

LAUNCH_RE = re.compile(r"\b(?P<kernel>\w+)::launch_unchecked\b")
FROM_RAW_RE = re.compile(
    r"BufferArg::from_raw_parts\(\s*(?P<handle>[^,]+?),\s*(?P<length>[^,)]+?)\s*\)"
)
# Creation shapes at/near a bind: `client.empty(N)`, `create_from_slice(&v)`,
# `create_buffer(N)`.
EMPTY_CALL_RE = re.compile(r"\.empty\(\s*(?P<n>[^)]+?)\s*\)")
SLICE_CALL_RE = re.compile(r"create_from_slice\(\s*(?:f32::as_bytes\(\s*)?(?:&\s*)?(?P<v>[\w.\[\]]+)")

CAPACITY_WORDS = ("block_size", "capacity", "max_seq", "n_ctx", "max_positions")


@dataclass
class Kernel:
    repo: str
    file: str
    name: str
    len_params: set[str]


@dataclass
class BindSite:
    kernel: str
    repo: str
    file: str
    line: int
    handle_expr: str
    length_expr: str
    verdict: str = "UNRESOLVED"
    reason: str = ""


@dataclass
class Report:
    kernels: list[Kernel] = field(default_factory=list)
    binds: list[BindSite] = field(default_factory=list)
    files_scanned: int = 0


def derive_repos(workspace: Path) -> list[Path]:
    """A root BOUNDARY.md AND a `.git` dir — never a typed list."""
    return sorted(
        d
        for d in workspace.iterdir()
        if d.is_dir() and (d / "BOUNDARY.md").is_file() and (d / ".git").exists()
    )


def rs_files(repo: Path):
    """Tracked-shape walk: .rs files, pruning build/vendor trees up front.

    `rglob` enumerates `target/` before any filter can skip it — the walk,
    not the parse, is the cost (measured: full timeout on the 4090 box).
    """
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = [d for d in dirnames if d not in ("target", ".git", "node_modules")]
        for fn in filenames:
            if fn.endswith(".rs"):
                yield Path(dirpath) / fn


def half_a(repo: Path, rep: Report) -> None:
    """Cube kernels whose bodies derive from `.len()`, with the buffers."""
    for f in rs_files(repo):
        rep.files_scanned += 1
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "#[cube(" not in src:
            continue
        for m in CUBE_FN_RE.finditer(src):
            body = src[m.end() : m.end() + 6000]
            bufs = {g.group("buf") for g in LEN_USE_RE.finditer(body)}
            if not bufs:
                continue
            rep.kernels.append(
                Kernel(repo.name, str(f.relative_to(repo)), m.group("name"), bufs)
            )


def classify(handle_expr: str, length_expr: str, line_src: str) -> tuple[str, str]:
    """Depth-1 provenance classification of one binding."""
    h = handle_expr.strip()
    # The attention fix pattern: a trimmed view — clean by construction.
    if "offset_end" in line_src or ".slice(" in line_src:
        return "TRIMMED", "offset_end/slice view — declared size is the live range"
    # Length taken from a handle's own size METHOD — allocation-as-length,
    # the direct shape of the compact_temp bug. (Identifier substrings like
    # `vocab_size` / `as usize` are NOT this: only member calls are.)
    if re.search(r"\.\s*(len|size|size_in_bytes)\s*\(", length_expr):
        return "CAPACITY", f"bind length from a handle size method: {length_expr.strip()}"
    # A capacity constant naming the bind length directly.
    if any(w in length_expr for w in ("block_size", "max_seq", "n_ctx", "max_positions")):
        return "CAPACITY", f"bind length names a capacity constant: {length_expr.strip()}"
    # Persistent struct-field handle.
    if re.match(r"^(self|cache|state|weights|scratch)\.", h):
        return "PERSISTENT", "struct-field handle — declared size is the field's"
    # Created at the bind site from a slice of a local: follows the local.
    sm = SLICE_CALL_RE.search(line_src)
    if sm and sm.group("v") in line_src:
        v = sm.group("v")
        if v.startswith(("self.", "cache.", "scratch.")):
            return "PERSISTENT", f"create_from_slice of persistent host vec {v}"
        return "PARAM-LOCAL", f"create_from_slice of local {v}"
    em = EMPTY_CALL_RE.search(line_src)
    if em and "empty" in line_src:
        n = em.group("n")
        if any(w in n for w in CAPACITY_WORDS):
            return "CAPACITY", f"empty({n}) sized by a capacity constant"
        return "PARAM-LOCAL", f"empty({n}) sized by a local dim"
    return "UNRESOLVED", "wrapper-param handle — provenance is one level up"


def half_b(repo: Path, kernels: list[Kernel], rep: Report) -> None:
    """Every `K::launch_unchecked` call in the repo, with its bindings."""
    names = {k.name for k in kernels}
    if not names:
        return
    for f in rs_files(repo):
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Runtime-guarded windows: lines within 60 lines of an
        # `assert_binding_derives_units` call site (515 T4/T2). Loose on
        # purpose — a report credit, not a proof; the refusal pins are the
        # proof.
        guarded_lines: set[int] = set()
        for gm in re.finditer(r"assert_binding_derives_units\s*\(", src):
            line_no = src[: gm.start()].count("\n") + 1
            guarded_lines.update(range(line_no - 60, line_no + 60))
        for m in LAUNCH_RE.finditer(src):
            if m.group("kernel") not in names:
                continue
            # Call span: to the matching close paren of launch_unchecked(.
            open_at = src.find("(", m.end() - 1)
            span = src[open_at : open_at + 4000]
            # Only the first nesting level: cut at the matching paren.
            depth, end = 0, 0
            for i, ch in enumerate(span):
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            call = span[:end]
            line = src[: m.start()].count("\n") + 1
            for b in FROM_RAW_RE.finditer(call):
                v, why = classify(b.group("handle"), b.group("length"), b.group(0))
                if v in ("UNRESOLVED", "PARAM-LOCAL", "PERSISTENT", "CAPACITY") and line in guarded_lines:
                    # The launcher carries the runtime refusal guard — the
                    # oversized-binding class is refused at launch (pinned by
                    # the refusal tests), whatever the static provenance says.
                    v = "GUARDED"
                    why = "launcher carries assert_binding_derives_units (515 T4/T2)"
                rep.binds.append(
                    BindSite(
                        m.group("kernel"),
                        repo.name,
                        str(f.relative_to(repo)),
                        line,
                        b.group("handle").strip(),
                        b.group("length").strip(),
                        v,
                        why,
                    )
                )
            if not FROM_RAW_RE.search(call):
                rep.binds.append(
                    BindSite(
                        m.group("kernel"),
                        repo.name,
                        str(f.relative_to(repo)),
                        line,
                        "<no BufferArg in span>",
                        "",
                        "UNRESOLVED",
                        "call span parsed but no from_raw_parts found (macro/moved args?)",
                    )
                )


def selftest() -> None:
    """Pin the parse shapes. Runs on EVERY invocation.

    Without this the audit degrades silently: a regex regression makes it
    recognise fewer kernels and still print a confident `0 findings` — the
    exact failure mode it exists to catch, committed by the tool that catches
    it (`cfg_gated_target_audit.py`'s precedent).
    """
    kernel_src = """#[cube(launch_unchecked)]
fn attention_decode_f32(query: &[f32], kv: &[f32]) {
    let kv_half = kv.len() as u32 / 2u32;
}"""
    m = CUBE_FN_RE.search(kernel_src)
    assert m and m.group("name") == "attention_decode_f32", "kernel parse broke"
    body = kernel_src[m.end() :]
    bufs = {g.group("buf") for g in LEN_USE_RE.finditer(body)}
    assert "kv" in bufs, "len-use parse broke"

    lm = LAUNCH_RE.search("unsafe { attention_decode_f32::launch_unchecked::<R>(c, a) }")
    assert lm and lm.group("kernel") == "attention_decode_f32", "launch parse broke"

    fm = FROM_RAW_RE.search("BufferArg::from_raw_parts(kv_handle, combined_kv_len)")
    assert fm and fm.group("handle") == "kv_handle", "bind parse broke"

    assert classify("self.compact_temp", "n", "")[0] == "PERSISTENT"
    assert classify("h", "h.len()", "")[0] == "CAPACITY"
    assert classify("h", "h.size()", "")[0] == "CAPACITY"
    assert classify("h", "h.size_in_bytes()", "")[0] == "CAPACITY"
    assert classify("h", "block_size * 4", "")[0] == "CAPACITY"
    # Identifier substrings are NOT size methods — pinned after the first run
    # flagged all 7 CAPACITY rows off `vocab_size` / `as usize` substrings.
    assert classify("input", "vocab_size", "")[0] == "UNRESOLVED"
    assert classify("input", "n as usize", "")[0] == "UNRESOLVED"
    assert classify("h", "dim * 4", "let h = client.empty(dim * 4); x")[0] == "PARAM-LOCAL"
    assert classify("q", "q_len", "")[0] == "UNRESOLVED"


def main() -> int:
    selftest()
    here = Path(__file__).resolve().parent
    workspace = here.parent.parent
    repos = derive_repos(workspace)
    if not repos:
        print("✗ no contract repos derived — refusing to print a confident zero")
        return 1

    rep = Report()
    for repo in repos:
        half_a(repo, rep)
    for repo in repos:
        own = [k for k in rep.kernels if k.repo == repo.name]
        half_b(repo, own, rep)

    # Kernel names are crate-unique enough for the join; report per kernel.
    by_kernel: dict[str, list[BindSite]] = {}
    for b in rep.binds:
        by_kernel.setdefault(b.kernel, []).append(b)

    print(f"▸ {len(repos)} contract repo(s) · {rep.files_scanned} .rs scanned")
    print(f"▸ HALF A: {len(rep.kernels)} `.len()`-deriving cube kernel(s)")
    print(f"▸ HALF B: {len(rep.binds)} bind site(s) over those kernels\n")

    order = ["CAPACITY", "PERSISTENT", "UNRESOLVED", "TRIMMED", "GUARDED", "PARAM-LOCAL"]
    counts = {v: 0 for v in order}
    for b in rep.binds:
        counts[b.verdict] = counts.get(b.verdict, 0) + 1

    never_launched = [k for k in rep.kernels if k.name not in by_kernel]
    for verdict in order:
        rows = [b for b in rep.binds if b.verdict == verdict]
        if not rows:
            continue
        print(f"── {verdict} ({len(rows)}) " + "─" * 40)
        for b in sorted(rows, key=lambda r: (r.repo, r.file, r.line)):
            print(f"  {b.repo}/{b.file}:{b.line}  {b.kernel}  {b.handle_expr}  [len: {b.length_expr}]")
            print(f"      {b.reason}")
        print()
    if never_launched:
        print(f"── NOT-LAUNCHED ({len(never_launched)}) — no launch_unchecked site found")
        for k in never_launched:
            print(f"  {k.repo}/{k.file}  {k.name}  (derives from {sorted(k.len_params)})")
        print()

    floors = {"min_rs_files": 1500, "min_kernels": 40}
    problems = []
    if rep.files_scanned < floors["min_rs_files"]:
        problems.append(f"files_scanned {rep.files_scanned} < {floors['min_rs_files']}")
    if len(rep.kernels) < floors["min_kernels"]:
        problems.append(f"kernels {len(rep.kernels)} < {floors['min_kernels']}")
    if problems:
        print("✗ WALK REGRESSION: " + "; ".join(problems) + " — refusing the confident zero")
        return 1

    print("✓ report complete (report-only; exit 0 by design — see docstring)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
