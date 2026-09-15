# Issue 798 (2026-09-15) — a tracked landing record claimed a sibling-repo repair that was never committed

## The finding

Two tracked katgpt-rs files recorded cross-repo repairs as **landed and
green**. Neither repair existed in the sibling repo. Both sweeps were **RED**
for the whole interval, and the records described a **worktree state no commit
contained** — Issue 797's class, one level up: 797 covers a sweep's *findings
and floors* reading an uncommitted tree; this is a *prose landing record*
doing it, in a tracked file, where no gate reads it.

Both records were written by `cb03c8dc` (2026-09-15 10:23 +0700).

### Record 1 — `scripts/toolchain_override_drift_floors.txt`

> ⚠ LANDING RECORD, 2026-09-15: … **RESOLVED the same day: all five markers
> are in** (katgpt-rs full_gate.yml + wasm32_gate.yml via rule (b); riir-ai
> g2_netem_docker.sh via rule (c) …; riir-chain toolchain_drift.yml via rule
> (b), UNRESOLVED-MARKED; riir-game-sdk t36_netem_partition_docker.sh marked
> but NO-PIN-OVERRIDE …). **First green sweep: 0 DRIFT / 3 DELIBERATE / 0
> UNRESOLVED / 1 UNRESOLVED-MARKED / 1 NO-PIN-OVERRIDE / 13 UNPINNED-REPO.**

Measured 2026-09-15, `git grep toolchain-override-deliberate` over the four
named repos: **2 of the 5 markers existed**, both of them the katgpt-rs pair.
The three sibling markers were absent, and the sweep read
`drift 1 · unresolved 1 · ✗ FAILED`.

### Record 2 — `scripts/pipefail_discard_expected.txt`

> (dropped 2026-09-15: … and **riir-chain teardown.sh:24 got the same tail in
> the riir-chain commit**, restoring its already-gone re-run branch.)

That tail was absent. The row was `✗ UNPINNED finding
riir-chain:cloudflare/edge-wallet-container/teardown.sh:cc4d29da#1` and the
sweep read `✗ FAILED`. The row had been **dropped from the pin file on the
strength of a fix that did not exist** — the one direction in which dropping a
row is unrecoverable, because nothing then points at the site.

## Why it happened, and why it is not a new instrument gap

The shape is unambiguous from the artifacts: the sibling files were edited in
the worktree, the sweeps were run **green against those uncommitted edits**,
the records were written from that run, katgpt-rs was committed, and the
sibling edits were never committed anywhere — they are not in any sibling's
worktree, index, or stash today.

⛔ **The mechanical repair already exists and postdates the incident by
hours.** Issue 797's worktree advisory (landed `41ecdcbd`) prints, on the
final line of every sweep in both directions:

```
⚠ WORKTREE: 5 file(s) in this sweep's own population differ from HEAD —
  riir-ai (2), riir-chain (2), riir-game-sdk (1). Counts and floors from this
  run describe a state NO commit contains; do not re-pin from it (Issue 797)
```

Those are exactly the files this issue is about — the advisory fired on the
repair run for this issue, naming the same three repos. `cb03c8dc` predates
`41ecdcbd`, so the incident is the **first real-world validation of 797
against an incident 797 did not know about**, not evidence of a hole in it.

Do **not** add a gate that parses prose landing claims. The sweep is the
verification and it worked: it was red from the moment the record was written
until the repair landed. The gap was that nobody ran it in between, and a
workstation-only on-demand sweep has no mechanism that can fix that.

## The standing rule this adopts

**A cross-repo repair is not landed until it is COMMITTED in the sibling
repo, and a katgpt-rs record claiming one must cite the sibling commit.**

A record that says *"the marker is in"* is unverifiable and stayed false for
six hours. A record that cites `riir-chain 9c1f2ab` is checkable by one
`git -C ../riir-chain cat-file -e` and is wrong in a way a reader can see.
This is the same rule the repo already applies to measurements — *take the
figure from a run, not from a sentence here* (AGENTS.md, Issues 784/785) —
extended to the one claim class where the evidence lives in another checkout.

## Resolution

All four sibling-repo repairs landed with this issue, each cited by SHA in the
record it belongs to:

| repo | file | repair | verdict after |
|---|---|---|---|
| riir-ai | `scripts/g2_netem_docker.sh` | `toolchain-override-deliberate` marker above the docker-run head (rule (c)) | DELIBERATE |
| riir-game-sdk | `scripts/t36_netem_partition_docker.sh` | same, rule (c) | DELIBERATE (NO-PIN-OVERRIDE dominates) |
| riir-chain | `.github/workflows/toolchain_drift.yml` | same, rule (b), in the `env:` comment run | UNRESOLVED-MARKED |
| riir-chain | `cloudflare/edge-wallet-container/teardown.sh` | `\|\| true` at the substitution tail | finding cleared |

Both overrides are genuinely deliberate rather than decayed, which is why the
marker is the correct repair and not a value change: each script **bakes its
own image** (`IMAGE=riir-g2-netem:1.95` / `riir-t36-netem:1.95`, both
`FROM rust:1.95.0-bookworm`), so `-e RUSTUP_TOOLCHAIN=1.95.0` tracks the baked
container, not the workspace pin. Raising it to `1.98.1` without rebuilding
the image forces a rustup download inside a 1.95.0 container. Bumping the
image is a separately-reviewed act, as `riir-ai/rust-toolchain.toml`'s own
header says about raising the channel.

The teardown fix restores dead code: under `set -euo pipefail` a
legitimately-empty `grep` (nothing deployed — the normal state for a re-run of
an idempotent teardown) killed the script at the assignment, making the
script's own `(no $APP listed — already gone)` branch unreachable.

Sweeps after: `toolchain override sweep PASSED` (0 drift, 3 deliberate,
1 unresolved-marked), `pipefail discard sweep PASSED` (50 findings, 51 pinned
rows — the 51st is `riir-deployer`, absent from this box and correctly
deferred).

## Non-finding, recorded so it is not re-investigated

The pipefail sweep's PASS line reads *"every repo within its pins, every
pinned row firing"* while printing `50 FINDING · 51 pinned row(s)`. That is
**not** an unbacked claim: the both-directions membership check is at
`pipefail_discard_drift_sweep.py:425-431` (`✗ pinned row no longer fires`),
and it correctly `continue`s on repos absent from the box, whose pins ride the
population verdict. `riir-deployer` holds exactly one row and is one of the
four absent repos, so 51 − 1 deferred = 50 checked = 50 findings. The
arithmetic is consistent and the DEFERRED clause is appended to the same line.
