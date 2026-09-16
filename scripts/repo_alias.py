#!/usr/bin/env python3
"""Machine-local ON-DISK -> CONTRACT name mapping for the derived repo walk.

The contract repo names live in tracked artifacts (`repo_set.txt`, the drift
floors and expected-pin files, the AGENTS.md census), and the workspace
`derive_repos` / `derive_population` predicates return directory names read
from the live workspace. When a box's on-disk sibling directory names differ
from the contract names -- an owner-side rename that this repo's tracked
instruments must not hard-code -- this optional, GITIGNORED map translates the
derived names so every instrument and every tracked pin speaks ONE vocabulary.

The map file is `scripts/repo_alias.local.txt` (gitignored): one
`on-disk=contract` row per line, `#` comments allowed. Machine-local by
design -- the on-disk names may be private -- and the CONTENT never enters
tracked files or gate stdout: the only disclosure is a once-per-process
stderr line printing the COUNT, because run logs get pasted into tracked docs.

Absent file -> identity mapping, so CI (single checkout), fresh clones, and
the population_sync_gate synthetic-workspace canaries are untouched by
construction. Malformed rows exit loud: a silently skipped row is a population
change nobody can audit.

Not a contract-repo predicate (population_sync_gate's registry is unchanged):
this is a name codec consumed BY the predicates, not an eleventh population.
"""

from __future__ import annotations

import sys
from pathlib import Path

ALIAS_FILE = Path(__file__).resolve().parent / "repo_alias.local.txt"

_loaded: dict[str, str] | None = None


def _load() -> dict[str, str]:
    global _loaded
    if _loaded is None:
        _loaded = {}
        if ALIAS_FILE.is_file():
            for lineno, raw in enumerate(
                ALIAS_FILE.read_text(encoding="utf-8").splitlines(), 1
            ):
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    raise SystemExit(
                        f"⛔ {ALIAS_FILE.name}:{lineno}: malformed row, "
                        f"want on-disk=contract: {line!r}"
                    )
                disk, contract = (s.strip() for s in line.split("=", 1))
                if not disk or not contract:
                    raise SystemExit(
                        f"⛔ {ALIAS_FILE.name}:{lineno}: empty side in row: {line!r}"
                    )
                if disk in _loaded:
                    raise SystemExit(
                        f"⛔ {ALIAS_FILE.name}:{lineno}: duplicate on-disk row "
                        f"for {disk!r}"
                    )
                _loaded[disk] = contract
            if _loaded:
                # Count-only disclosure -- never the names; run logs get
                # pasted into tracked docs.
                print(
                    f"[repo-alias] {len(_loaded)} local name mapping(s) active",
                    file=sys.stderr,
                )
    return _loaded


def apply(names) -> list[str]:
    """Translate derived on-disk directory names into contract names (sorted)."""
    m = _load()
    return sorted(m.get(n, n) for n in names)


def disk(contract: str) -> str:
    """The on-disk directory name for a contract name (identity if unmapped)."""
    for d, c in _load().items():
        if c == contract:
            return d
    return contract


def display(name: str) -> str:
    """The contract spelling of one name, for gate OUTPUT lines."""
    return _load().get(name, name)
