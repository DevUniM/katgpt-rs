# Issue 829 (2026-09-18) — the FILE seam under Issue 778's PIPE seam: 273 text-I/O sites decode with the system locale, and the first one found was making a whole file of arms pass for the wrong reason

**Status: RESOLVED same day (T1-T6). 273 sites -> 2, and the 2 are outside the contract.**

## How it was found, which is the entire argument for a gate

Not by a census. Issue 828 added an arm to
`citation_drift_sweep.selftest()` asserting that the oracle reads a
dash-delimited heading. It failed — `(1, 5)` where `(3, 6)` was expected —
while **the same fixture, typed by hand into a scratch script, returned
`(3, 6)`**. Same bytes, same classifier, two answers.

The fixture is written with a bare `Path.write_text(...)`, which encodes with
`locale.getencoding()`. This workstation is **cp874**, where U+2014 encodes to
a single byte that a subsequent `read_text(encoding="utf-8",
errors="replace")` returns as U+FFFD. Every em dash in every selftest fixture
in that file had been silently corrupted since the day it was written.

⛔ **The existing arms passed anyway** — none of them depended on a dash — so
this is not "a latent defect". It is a test suite that had been **green for
the wrong reason**, and it stayed invisible until an arm was written whose
subject was the corrupted character. A locale write does not raise, does not
look wrong, and does not change a verdict until it does.

This is `subprocess_encoding_gate.py`'s class (Issue 778) one seam over — the
**FILE** seam rather than the **PIPE** seam — and it went unlooked-at for that
issue's own stated reason: macOS, `ubuntu-latest` and the M3 all speak UTF-8,
so **nothing that could notice ever runs it**.

## T1 — the census

AST over tracked `*.py`, 16 repos on this box:

| repo | sites | repo | sites |
|---|---|---|---|
| katgpt-rs | **155** | riir-chain | 7 |
| riir-train | 68 | riir-mmorpg-examples | 2 |
| riir-clippy | 27 | riir-shader | 2 |
| riir-ai | 10 | seal-game-editor | 2 |

**273 sites over 195 tracked `*.py` in 8 of 16 repos.** Two are not latent in
the "someday" sense: `riir-clippy/scripts/gen_dashboard.py` reads `git log
--pretty=%s` across the workspace and **every commit subject here uses an em
dash**; `riir-train/scripts/build_clippy_v3_corpus.py` reads and rewrites
corpus files with a bare `read_text`/`write_text` pair.

## T2 — the repair half, `scripts/locale_io_fix.py`

AST-driven, idempotent, 18 arms. Three things it learned the hard way, each
with an arm:

- ⛔ **`col_offset` is a UTF-8 BYTE offset.** Computing the insertion point in
  characters desyncs by two per em dash earlier on the line, and this repo's
  sources are full of them — the first run asserted on `' '` 59664 chars in.
- ⛔ **The newline style is part of the file.** Reading with universal
  newlines and writing `\n` flipped `suite_membership_audit.py` from CRLF to
  LF and turned an 11-site repair into a **515-line diff**, which is a repair
  nobody can review. It reads bytes, detects the style, and writes it back.
- ⛔ **The kwarg joins the last ARGUMENT, not the closing paren.** A call whose
  `)` is on its own line otherwise grows a leading-comma continuation
  (`        , encoding="utf-8")`) — valid Python, unreviewable, and 128 sites
  went in before anyone read one.
- A `**kwargs` splat is **UNKNOWN** and left alone: the caller may be supplying
  the encoding, and a repair may only ever be conservative.

## T3 — the verdict half, `scripts/locale_io_gate.py` (docs_gate CHECK)

Walled at **0** over a floored population, sharing `locale_io_fix.sites()` so
the repair and the verdict can never disagree about the rule (Issue 755).

- Population is tracked `*.py`, **not** `scripts/*.py`: 778's first real run
  found a site in `.agents/skills/doc-sync/tools/`, and this census found two
  more in `.benchmarks/` and `.agents/`. The seam is an idiom, not a directory.
- **Two floors that break separately** — `min_py_files` (the walk) and
  `min_io_calls` (the AST pass). The predicate floor counts *compliant* calls
  too, or it restates the ceiling and *a pin that restates its own input
  cannot fail*.
- **UNPARSED reds**, never folded into the pass column.
- Exemptions by membership with a reason per row, `locale_io_expected.txt`,
  **deliberately empty** — the repair is one mechanical pass, so a row would be
  a backlog wearing a pin (Issue 785). A stale row reds too.
- `--canary` arms the gate's own pin arithmetic (Issue 775's rule: the
  classifier's self-test cannot reach the verdict), including the exemption
  READER's permissive direction and the two floors *independently* — pooling
  them means repairing one hides the other.
- `--prove-fires 072a083b` is a known answer: 128 offenders at Issue 828's
  landing commit.

## T4 — the sweep half, `scripts/locale_io_drift_sweep.py`

Landed in the **same change** as the gate, because shipping one half is the
failure this workspace has now recorded nine times (Issues 777, 778, 793, 782,
783, 789, 797, 820).

⚠ Its ceiling was landed as a **RATCHET on the derivative** rather than a
wall, on a measurement: 118 sites sat in seven repos this session did not own,
and ratcheting a bucket nobody has read is Issue 785's forbidden shape. T6 then
read them, so every row is **0** today — but the file stays a ratchet by
construction, because the next repo to join the workspace joins with whatever
it has, and a wall would make that repo's arrival somebody's emergency.

Wired to both family-wide mechanisms at landing (the gate that requires it is
`sweep_advisory_membership_gate.py`): the Issue-797 worktree advisory and
Issue-822 head provenance via `head_delta` — per-file row independence holds
by construction, since the classifier is an AST pass over one module's source.

⚑ The provenance wiring earned its keep on its first run: with the repair in
the worktree and not yet committed, it reported **128 MASKED rows** — committed
defects this worktree hides — instead of a clean sweep.

## T5 — katgpt-rs repaired

155 sites: 27 in `citation_drift_sweep.py` landed with Issue 828 (its arms are
not real without them), 128 in the other 84 files here. `docs_gate.sh` green,
26 CHECKS.

## T6 — the 118 sibling rows, LANDED, with the SHAs

This repo's own rule: *a cross-repo repair is not landed until it is COMMITTED
in the sibling repo, and a record HERE claiming one must CITE THE SIBLING
COMMIT*. Six repos, one commit each, tracked `*.py` only (three of them carry
concurrent sessions' uncommitted `.rs` and `Cargo.lock` edits, which is why
the staging is by NAME and never `-A`):

| repo | sites | commit |
|---|---|---|
| riir-train | 68 | `39d0b8d4` |
| riir-clippy | 27 | `638fa224` |
| riir-ai | 10 | `4df109c65` |
| riir-chain | 7 | `bebf78a` |
| riir-mmorpg-examples | 2 | `36005d2` |
| riir-shader | 2 | `7a65dd4` |

Every row in `locale_io_drift_floors.txt` dropped to 0 in the same change, each
carrying its SHA. **Workspace measurement after: 273 → 2**, and the 2 are
`seal-game-editor`, a known-extra repo outside the contract that is 260
commits behind its upstream — the Issue-798 advisory names it on every run, so
repairing it from this box would be repairing a checkout rather than a repo.

⛔ The riir-train run is the one to read, because its raw diff was **+101/-72
over 33 files** and looked like the newline defect T2 had just fixed. It was
not: `--numstat` over the whole worktree includes a concurrent session's
`Cargo.lock` and `plan402_p1_gemma_boundary_sweep.rs`. Scoped to `*.py` it is
**31 files, +68/-68**, exactly 1:1. *Read a shared worktree's diff through the
population you changed, or another session's work reads as your bug.*

### The gate's own foreign-repo mode, found by using it

`scripts/locale_io_gate.py ../riir-shader` — the form its own docstring
advertises — reported `parse FLOOR breached: 2 text-I/O call site(s) < 450`.
The floors are katgpt-rs's measured population and applying them to a repo
with two Python files states something true of the pin and false of the tree.
A named sibling is a **REPORT** now: floors and exemptions are not applied,
the final line says so, and the per-repo pins stay the sweep's
(`locale_io_drift_floors.txt`), which is the only place they mean anything.
