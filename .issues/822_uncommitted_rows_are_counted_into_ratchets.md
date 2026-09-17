# Issue 822 (2026-09-17) — an UNCOMMITTED row is counted into a RATCHET, and one just breached a pin over a file that exists in no commit

**Status:** OPEN — T1-T4 landed, T5 (the fan-out to 13 more sweeps) owed
**Severity:** a sweep reds on another session's in-flight edit; the obvious remedy is to re-pin from it
**Owner:** unassigned — filed with the measurement, not started

## The finding

Issue 797 established the split and stated it as a rule:

> **UNCOMMITTED** — the worktree carries a row HEAD does not. **Displayed**
> (it is what the file says today, and hiding it would be its own lie) but
> **never adjudicated against a pin**. The split of responsibility, once: the
> DISPLAY reads the worktree, the PINS read HEAD.

and then wired it into exactly one sweep, for a reason it wrote down:

> The row-level UNCOMMITTED/MASKED split is wired into `citation_drift_sweep.py`
> alone, because it is the one whose findings carry a `file:line` address and
> the one where the class was measured.

The first clause of that reason has since stopped being true. `console_encoding`,
`subprocess_encoding`, `platform_dead_code`, `instrument_reachability`,
`orphaned_attr` and `len_derived` all carry **file-addressed** rows. The second
clause is what this issue is: the class has now been measured somewhere else.

## Measured, 2026-09-17

`console_encoding_drift_sweep.py`, riir-train row, both markers set:

    ✗ riir-train   walk=61  pop=56  defended=0  undefended=56
          ✗ undefended 56 > pinned 53 — a new instrument that prints a
            non-ASCII glyph and defends neither stream

56 − 53 = **3**, and the three newest rows in that repo are exactly:

| row | state in riir-train |
|---|---|
| `scripts/plan402_gguf_probe.py` | **`A ` — staged, in NO commit** |
| `scripts/plan403_fetch_lph_corpus.py` | committed today (`1939fe3c`) |
| `scripts/plan403_modelless_floors.py` | committed (`26128ecb`), **modified uncommitted** |

So the breach is **at most two** real committed findings, and it is reported as
three. One row sits on a file `git log` cannot see at all, authored by a
concurrent session that is mid-commit in that worktree right now — its index
carries staged `crates/` work as well.

⚠ This is the shape Issue 797 measured for citations and warned about for
floors, reached through a **ratchet** instead: *"A floor or ratchet re-pinned
from such a run bakes another session's in-flight edit into a tracked
expectations file, where it reds on every other box."* The pressure to do
exactly that is real — the sweep says 56, the file says 53, and typing 56 is
one keystroke. Nothing in the run distinguishes the case.

⚠ It compounds with the STALE axis (Issue 798), which fired on the same run:
riir-train is 10 commits behind origin with 8 in this sweep's population. So
the number 56 is a function of one box's checkout **and** one session's
uncommitted index, and it is being compared to a tracked constant.

## Why the advisory does not cover it

`sweep_advisory()` is wired into all 19 sweeps and it fired correctly here —
it named riir-train. But it is a **repo-level** banner that says "some files
differ from HEAD". It cannot say *which finding* is affected, and on a run with
56 rows and a 3-row breach that is not enough to act on: the reader still has
to decide whether to re-pin, and the banner gives them no way to tell.

## Proposed tasks (not started)

- [x] **T1 — MEASURED 2026-09-17, and the set is not small.** The hope written
      here was that membership-pinned sweeps would be immune and the exposure
      would be a handful. Extracted every `… > row["max_*"]` comparison in the
      family: **14 of 19 sweeps carry at least one COUNT ceiling**, and nearly
      every counted bucket is file-addressed.

      | sweep | counted bucket(s) | rows addressed by |
      |---|---|---|
      | `console_encoding` | `undefended` | script path ← **measured breach** |
      | `instrument_reachability` | `unreachable` | script path ← **measured breach** |
      | `subprocess_encoding` | `decode`, `child` | file + call site |
      | `toolchain_override` | `drift`, `unresolved` | file + line |
      | `orphaned_attr` | `offenders` | file + line |
      | `markdown_fence` | `unterminated` | file + line |
      | `len_derived` | `findings` | file + kernel |
      | `pipefail_discard` | `findings`, `unparsed` | file + line |
      | `percentile` | four severity classes | file + line |
      | `cfg_gated` | `silent_now`, `load_bearing` | target |
      | `trap_sentinel` | per-class | script path |
      | `required_features` | `invalid` | manifest row |
      | `wasm32_surface` | `unresolved` | package (not a file) |
      | `numbering` | `dup`/`above`/`malformed`/`resets`/`hist` | number / dir |

      Two corrections to this issue's own framing:
      - **Membership does not confer immunity where a sweep has BOTH.**
        `wasm32_surface`, `pipefail_discard` and `toolchain_override` pin some
        buckets by membership *and* ratchet others by count; the count half is
        exposed regardless.
      - `citation_drift_sweep` is the one sweep WITH the row-level split, and
        it is the one whose rows are **documents** rather than source files.
        The class was measured there first and bites hardest everywhere else.

      ⛔ **This column answers "where does the row POINT?", NOT "is the
      classifier per-file?" — and the second is what picks the instrument.**
      Added 2026-09-17 after the T5b table inherited the confusion and put two
      sweeps in the wrong bucket. They are independent properties:

      | sweep | row address | classifier scope | instrument |
      |---|---|---|---|
      | `toolchain_override` | file + line | **repo** — every occurrence judged against the root `rust-toolchain.toml` | NOT the shortcut |
      | `platform_dead_code` | item | **unit** — a dirty file moves its siblings' verdicts | `head_overlay` + `delta_of` |

      A file+line address says nothing about whether a dirty file can change
      another file's verdict, and only the latter decides whether the per-file
      `head_delta` shortcut is sound — the shortcut **invents rows** where it
      isn't. I derived this column from the SHAPE OF THE PIN COMPARISON
      (`len(x) > row["max_*"]`), which is a cheap static read and cannot see
      classifier scope at all. katgpt-rs-fa found both errors the only way they
      are findable: by **reading each classifier**. Treat the column above as a
      starting hypothesis for *which sweeps are exposed*, and never as the
      instrument choice.
- [x] **T2 — LANDED 2026-09-17. `worktree_state.head_delta()`, and the
      affordability question was the wrong shape.** The hoped-for answer was
      the right one: only the FINDING paths need re-reading, and not even all
      of those. A clean file's rows are identical at HEAD **by construction**,
      so the only files that need a `git show` are the dirty ones inside the
      sweep's own population — the quantity `dirty_in_scope()` already prints
      on the advisory line, and **zero on an ordinary run**. A 2415-file Rust
      walk never has to be re-walked at all.

      Three things the implementation had to get right, each with its own arm:

      - **`HeadDelta.head` is `committed + masked`, NOT `committed`.** A masked
        row is committed-and-hidden, so a pin reading `committed` alone
        understates its ceiling by exactly the silent direction. The
        arithmetic lives in the helper because getting it right independently
        in fourteen sweeps is fourteen chances to get it wrong.
      - **The MASKED comparison is SCOPED to the dirty files.** Widening it to
        every worktree row reds nothing under a path-bearing key and is not
        equivalent in general: an address-less key (a bare script NAME — the
        shape this sweep's rows have) lets a CLEAN file's identical row
        suppress a genuinely masked one. Measured — the first arm written for
        it perturbed green, and the arm that separates them had to use such a
        key.
      - **The premise is PER-FILE row independence**, and it is stated rather
        than asserted because it is a property of the caller's classifier.
        `len_derived` (provenance through other repos),
        `instrument_reachability` (a closure from roots — a dirty `AGENTS.md`
        changes other scripts' verdicts), `numbering` and `citation` are
        cross-file and must keep re-running the classifier whole.

      78 assertions in `worktree_state.py`, every new rule perturbed and red.
      The one perturbation that does NOT red is recorded at the line: the
      empty-scope fast path is provably equivalent to falling through and is
      there for the COST, so the arm that bites is the one asserting zero
      rescan calls.
- [x] **T3 — LANDED.** `console_encoding_drift_sweep.py` prints
      `undefended 56 (53 committed + 3 uncommitted)` and labels each listed
      row `[UNCOMMITTED — not adjudicated]` / `[MASKED — committed, and this
      worktree hides it]`. Nothing is hidden; the ratchet reads `.head`.
- [x] **T4 — LANDED, and it needs no separate teeth.** The pins read `.head`,
      so a committed row the worktree hides breaches the ceiling on its own —
      AGENTS.md's existing rule, now true for this sweep too. It is *named* as
      MASKED in the row list and on the advisory line so the reader is not
      left hunting for a row the file does not contain. Still **0 by
      measurement** in this workspace.
- [x] **T5a — the CROSS-FILE instrument, and the second MEASURED sweep.**
      `worktree_state.head_overlay()` + `delta_of()` are the two pieces
      `citation_drift_sweep`'s inline version consists of, lifted so the next
      caller does not copy them, and
      `instrument_reachability_drift_sweep.py` is wired with them.
      `instrument_reachability_gate.reachable()` takes an injected `read` (the
      default is the module function, so every existing caller is
      byte-identical).

      Two things this half had that the per-file half did not:

      - **The POPULATION moves, not just the rows.** A staged-only script is in
        `git ls-files` and in no commit, so it is not part of what HEAD would
        report and cannot be an unreachable row there. Same for a root. Issue
        797 measured this for citations (`n_cites` 601 vs 607) and it is the
        part a row-level read alone misses.
      - ⛔ **The advisory's glob list was a SECOND hand-typed copy of the
        scope, and it disagreed.** It named `.yml` and not `.yaml`, so a dirty
        `.yaml` workflow — a ROOT, able to move scripts in and out of the
        unreachable set — was silently outside the sweep's declared
        population. One `SCOPE` constant now, used by both.
- [x] **T5c — the LINE-BEARING key, solved once.** `subprocess_encoding` is
      the third sweep wired and the first whose rows carry a line number
      (`"{lineno}: {call text}"`) — the shape most of the remaining nine have.
      The key drops the line and keys on `(file, kind, call text, ordinal)`:

      - ⛔ A line-bearing key reports **every** row in an edited file as
        UNCOMMITTED *and* MASKED at once, because any insertion above a call
        shifts it.
      - Two identical calls in one file would then collide, so an ORDINAL
        within `(file, kind, text)` disambiguates — the
        `len_derived_eyes_expected.txt` precedent, scoped to the whole address
        so a new call site renumbers nothing. The ordinal is assigned per
        row-set and never shared between the worktree and HEAD passes, or the
        two sides count from different bases and every row looks moved.

      ⛔ **And this one had to be armed rather than canaried, for a reason the
      remaining sweeps will share.** It reports **0 DECODE / 0 CHILD across the
      whole workspace** — Issue 783 repaired the class — and it has no
      `--canary` at all. So every line the split adds is decision code that no
      real run executes, and `split_arms()` (wired into `selftest`, which runs
      on every invocation) is the only thing standing between this wiring and
      code that has never run. Five perturbations, all red. **Check whether a
      sweep's findings are empty before deciding its arms are optional** — an
      empty finding set is exactly when a display change is unexercised.
- [x] **T5e — ⛔ THE ARMS WERE INERT ON THE FIRST SWEEP WIRED, and a peer
      session's question found it, not a run.** The question was exactly right
      and is worth reusing on anything with a seam: *if `head_delta` were
      stubbed to return `committed = worktree` unconditionally, would any arm
      red?* Measured, all three sweeps wired at the time:

      | sweep | verdict against the stub |
      |---|---|
      | `subprocess_encoding` | **red, 5 failures** — load-bearing |
      | `instrument_reachability` | **red, 6 failures** — but only once the probe was aimed at `delta_of`, the function it actually calls |
      | `console_encoding` | ⛔ **14/14 canary arms PASSED** |

      `console_encoding`'s `adjudicate()` body was asserted by **nothing**.
      Every canary arm that exercises the split MONKEYPATCHES `adjudicate`, so
      those arms assert that `main()` *uses* the delta correctly and assert
      nothing about the delta being computed at all — and the baseline arm
      cannot cover it, because this repo has 0 undefended rows and an empty
      input yields an empty delta either way. `instrument_reachability` got
      `adjudicate_arms` when it was wired and `console_encoding` did not; the
      asymmetry was an oversight, not a judgement.

      ⚠ **Two of the three first answers were the PROBE being wrong, not the
      wiring being inert** — `instrument_reachability` uses `head_overlay` +
      `delta_of` and never calls `head_delta`, and `console_encoding`'s
      verification lives in `canary()` rather than `selftest()`. A stub probe
      has to be aimed at the function the target actually calls, or it reports
      a false all-clear in the same breath as a true one.

      Fixed: `console_encoding.adjudicate_arms()` in `selftest`, which reds
      with 6 failures against the stub. Canary still 14/14.

      ⛔ **And no automatic instrument could have found it — measured, and the
      obvious statement of why is wrong.** A peer suggested `arm_reach_gate`
      structurally cannot see the drift sweeps. Checked directly rather than
      taken on trust, and the true shape is sharper:

      | population | modules | drift sweeps in it |
      |---|---|---|
      | `arm_reach_audit.population(include_all=False)` — what the GATE walls | 25 | **0** |
      | `arm_reach_audit.population(include_all=True)` — the report | 68 | **17** |

      So the sweeps are not invisible to the *instrument*; they are invisible
      to the *verdict*. The gate's population is the `docs_gate.sh` CHECKS set
      plus itself, and AGENTS.md already records that `--include-all`'s
      survivors are a deliberate unread backlog kept out of the gate. The
      consequence for this issue is the same either way: **every
      `adjudicate`/`split` seam landed by T5b is arm-reach-unwalled**, so a
      future one going inert reds nothing. The manual stub probe is the only
      thing covering it, which is why T5b makes it a step rather than a habit.
- [x] **T5d — `percentile`, fourth wired, and the first with FOUR ceilings.**
      The delta carries the class in its key and `.head` splits back by class
      for the four pins. Two things specific to it:

      - `degenerate_asserted` is a **subset** of `degenerate`, so one row
        appears under two classes by design. The class is part of the address
        for that reason — pooling them would make one row's ordinal depend on
        the other's presence, and a row that stopped being `asserted` would
        look like it moved.
      - ⚠ The advisory's scope (`*.rs`, `Cargo.toml`) is **wider** than the
        split's (`*.rs`): a dirty manifest can change what the sweep reads but
        produces no ROW. Two scopes, one deliberate difference, stated at the
        line.

      It needed `audit_text` extracted out of `audit_file` first —
      `subprocess_encoding` was cheap to wire *because* it already had that
      split (`scan_text` / `scan`). Pure refactor; every caller byte-identical.

      ⛔ **The ordinal arm was missing and the perturbation said so.** Dropping
      the ordinal red NOTHING until a fixture actually carried a repeated site:
      identical keys collapse, HEAD dedupes to one row, and the ceiling is
      UNDERCOUNTED by the number of duplicates — a ratchet silently tolerating
      the second copy of a defect. `subprocess_encoding` had that arm from the
      start and this one did not, which is the same asymmetry as T5e one level
      down. Both perturbations red now.
- [ ] **T5b — the FAN-OUT, which is the part that is not done.** T1 measured 14
      sweeps with a count ceiling; **four** are wired. Do not read the helpers'
      existence as the fan-out having happened — that substitution is this
      repo's most-repeated error and it is what made this issue the *ninth*
      instance. The per-sweep instrument is decided by T2's premise, not by
      preference:

      | sweep | instrument |
      |---|---|
      | ~~`orphaned_attr`, `markdown_fence`, `toolchain_override`, `pipefail_discard`, `platform_dead_code`~~ | **done** — `head_delta`, per-file classifiers |
      | ~~`percentile`~~ | **done (T5d)** — `head_delta`, four ceilings, class in the key |
      | ~~`console_encoding`~~ | **done (T3/T4)** — `head_delta`, name-keyed |
      | ~~`subprocess_encoding`~~ | **done (T5c)** — `head_delta`, line-free key + ordinal |
      | ~~`instrument_reachability`~~ | **done (T5a)** — `head_overlay` + `delta_of` |
      | `len_derived` | whole-classifier re-run, and its HALF C reaches other REPOS |
      | ~~`numbering`~~ | **done (T5h)** — the classes split by ORACLE; see below |
      | `cfg_gated`, `required_features` | manifest+source joins — read each before choosing |
      | ~~`wasm32_surface`~~ | **done (T5g)** — `head_tree`, the THIRD instrument |
      | `restatement`, `trap_sentinel`, `cfg_row_implication` | ⚠ carry count ceilings and were NOT in T1's table at all — see T5j |
      | `docs`, `citation` | `docs` has no count ceiling (nothing to overstate); `citation` carries the INLINE original — T5j |

      ⛔ **T5g — `wasm32_surface` needed a THIRD instrument, and the reason
      generalises to every remaining row.** `head_delta` and `head_overlay`
      both assume the classifier takes its text from ONE interceptable place.
      `wasm32_surface_audit` has FOUR seams (`git grep` for the walk, `git
      ls-files` twice, direct reads), and an overlay missing any one builds a
      verdict half from HEAD and half from the worktree — worse than either
      half. `worktree_state.head_tree()` materialises HEAD (`git archive` +
      extract + `git init`/`git add -A -f`) and the classifier runs
      UNMODIFIED. ⚠ It is the EXPENSIVE one: measured 22.5s (katgpt-rs), 31.6s
      (riir-ai), 28.0s (riir-train) to materialise, 0.04–0.26s on a clean repo
      because it yields `None` and the caller SKIPS. Reach for it only when a
      classifier genuinely cannot be read through one seam.

      ⛔ **T5h — `numbering`, and the class split is by ORACLE, not by
      instrument.** `dup`/`above`/`malformed`/`n_files` read the worktree (the
      pins read HEAD); `hist`/`resets`/`n_numbers` read `git log` and a dirty
      tree cannot move them; `unbumped` is a WORKTREE quantity by construction
      — Issue 770's checkout-state class — and adjudicating it to HEAD would
      destroy it. It needed no `head_tree` and no skip branch: HEAD is
      `ls-tree -r -z` + six `git show` (0.05s over riir-ai's 1601 numbered
      paths), so running it UNCONDITIONALLY closes the UNTRACKED hole
      `markdown_fence` had to split by hand — an untracked file is in no `git
      status` diff and in no HEAD listing, so its row is UNCOMMITTED by
      construction. ⚠ `above` counts untracked numbered files and `dup` does
      not; the two classes disagree about the population and each owes its own
      arm.

      ⛔ **A DIAGNOSTIC rule, and it cost a peer session an hour to find
      (2026-09-18).** `katgpt-rs-54` ran the numbering sweep during ~90
      seconds of another session's `git rebase` and got `malformed 1 > pinned
      0` + `duplicates 1 > pinned 0`: `.issues/.highwater` held conflict
      markers ON DISK and `.issues/` carried two 825 files, one staged-as-added
      by the commit being replayed. Both rows were TRUE of that instant and
      false of every commit. The peer then verified the worktree, HEAD's blob,
      the last 30 commits and `.git/rebase-merge`, found nothing, and concluded
      the instrument was reading a rerere preimage.

      **Every one of those checks inspects STATE, and state had moved.** A
      transient-worktree finding is in no commit *by definition*, so scanning
      commits is structurally incapable of separating "phantom" from "true but
      gone" — it can only ever return the reassuring answer. The one cheap
      decisive test is to **RE-RUN THE INSTRUMENT**; the peer's re-run after
      the rebase settled returned `dup=0 malformed=0`, which transient-worktree
      predicts and "the reader is broken" does not. A second clue was present
      and misread: the dirty-file SET changed under them (one session's files
      vanished, another's appeared), which reads as "they are editing the
      instrument" and was "they are rebasing the data" — concurrent git
      activity, not just concurrent editing.

      The misdiagnosis is the more valuable half, and it is why this is
      recorded as a rule rather than an anecdote: *"I cannot reproduce it, so
      the instrument is broken"* is available to anybody who verifies state
      instead of re-running, and it is wrong in the direction that deletes a
      real finding. Nothing wrong reached a tracked file — the peer corrected
      both its message and its user report — which is exactly why the protocol,
      not the incident, is what belongs here.

      ⛔ **Every one of these owes, as STEPS and not as tips:**

      1. an `adjudicate_arms` in its `selftest`, not only canary arms — T5e is
         why, and nothing automatic walls the seam (the table above);
      2. the stub probe afterwards, **aimed at the helper that sweep actually
         calls** — two of the first three probes reported a false all-clear
         because they were aimed at a function the target never invokes;
      3. an ordinal fixture that actually **REPEATS**. Dropping the ordinal red
         nothing on `percentile` until a file carried two identical sites. An
         arm over inputs that cannot exercise the rule passes for the wrong
         reason — the same family as (2), one level down.

      ⚠ **Budget the canary cost.** Each `--canary` runs `main()` once per arm
      over every contract repo, so four new arms is roughly a 45% increase:
      `console_encoding` went 9 arms/~15s to 14 arms/**~42s**. Workstation-only
      — none of these runs per push — but it is why the arms are four and not
      fourteen. A sweep with no canary (like `subprocess_encoding`) pays
      nothing here and needs `selftest` arms instead, which are cheaper and
      run on every invocation.

- [ ] **T5j — ⛔ T1's "14 sweeps with a count ceiling" was a MEASUREMENT of the
      set to wire, and it is not the set.** Re-measured 2026-09-18 by grepping
      every `> row["max_*"]`/`> f["max_*"]` comparison in the family:
      `restatement` (`max_restatement`, `max_identity`), `trap_sentinel` (SIX
      — `max_exposed`, `max_precautionary`, `max_live_forward`, `max_unparsed`,
      `max_replaced`, plus two floors) and `cfg_row_implication` (`max_empty`,
      `max_unresolved`) all carry ceilings and appear in T1's table NOWHERE.
      `docs` is the one sweep with no count ceiling at all — an exemption
      candidate, not a task — and `citation` carries the INLINE original the
      helpers were lifted out of, which owes a migration to them so one rule
      has one copy (AGENTS.md already describes the helpers as exactly that).

      The lesson is the issue's own: **do not carry a table forward as a
      population.** T1's table was right about what it looked at and is not a
      derived set, which is why the closing step of this issue is a REGISTRY
      row rather than a tick — see T6.

- [ ] **T6 — make the fan-out impossible to forget, the way Issue 824 did for
      its two mechanisms.** `scripts/sweep_advisory_membership_gate.py` is
      already a per-mechanism REGISTRY gated by MEMBERSHIP, and its whole
      warrant is that Issue 821 "landed a mechanism in 16 of 19 sweeps and
      wrote 16 in its own close-out". This issue is that shape again: a table
      in a file, ticked by hand, in a family that grows. Add
      `head-provenance` (`head_delta` / `head_overlay` / `head_tree`, plus
      whatever entry point `citation` ends up calling) as a third MECHANISM
      once the fan-out is complete — and **not before**, because a registry
      row added over unwired sweeps reds the docs gate on `develop`, and
      pinning them as exemptions in the meantime is a backlog wearing a pin
      (Issue 785's rule). `docs` is the only legitimate exemption row: no
      count ceiling, so nothing to overstate.

## ⚠ Workspace hazard this issue kept tripping over

Every commit in this shared worktree is authored `katopz <katopz@gmail.com>`,
so **git cannot distinguish the sessions writing it** and a SHA carries no
ownership. This issue was worked by at least three sessions concurrently, and
the visible cost was two misattributions in one hour — `202e8241` and the
`worktree_state` key helpers were both credited to the wrong session, and a
split was proposed to a session that had never touched the task. The
inference is unavoidable from the repository alone; the repair is to name the
task and the session in the commit BODY, or to not infer ownership at all and
ask. Recorded here because the next multi-session task inherits it.

⛔ **And "name the session in the body" is necessary and not sufficient — the
body's own `mine` is a second unresolvable field** (2026-09-18, measured by
katgpt-rs-54, recorded here at its request so one copy exists where a reader
hits the problem). Two fields, both useless alone:

* the **author line** is machine-checkable and identifies nobody — every
  session commits as `katopz <katopz@gmail.com>`;
* **"Nth of mine"** in a body is human-readable and identifies somebody you
  *cannot resolve*, because it is relative to a writer the repository does not
  name.

So the only reliable signal is an **explicit self-identification** — a
`Session: <name>` line — and even the NAME is not a key: `ListAgents` on this
box showed **two live sessions both called `katgpt-rs-54`**, distinguished only
by ref. Measured cost: reading `e13d3702`'s closing "Remaining on my side:
cfg_gated and required_features" as the *messaging peer's* claim, when its
author was a third session entirely. That produced a wrong WORK SPLIT — two
sweeps left untouched by both sessions that were talking, each believing the
other had them — rather than merely a wrong story. The standing note this
workspace already had ("never infer a SHA's owner") is the right rule and had
never been seen to cost anything until it cost an allocation decision.

⚠ A second-order specimen from the same hour, and it is the one worth
generalising: I asserted *"ListAgents shows only the two of us live"* in a
message **arguing against inferring things from git** — without having run
`ListAgents`. Running it returned three peers, not one. A claim about a cheap
verification is exactly as unreliable as the inference it replaces when the
verification was not performed; the repair is the same one this issue's T5h
rule gives for findings — **run the instrument**.

## What landed (2026-09-17)

- `scripts/worktree_state.py` — `HeadDelta`, `head_delta()`,
  `dirty_in_population()`, `_matches()` (extracted from `_match_count`, one
  copy), `sweep_advisory(uncommitted_rows=, masked_rows=)`, `delta_arms()`.
- `scripts/console_encoding_drift_sweep.py` — `head_undefended()` (the
  per-file HEAD reclassifier), `adjudicate()` (the named seam the canary
  monkeypatches, extracted so the verdict arithmetic is not stranded inside
  `main()` beside its own error messages), the honest display, and five canary
  arms including the pair that IS this issue: **one ghost row, two
  provenances, opposite verdicts.** 14/14 arms pass.
- `scripts/worktree_state.py` (T5a) — `head_overlay()`, `delta_of()`,
  `overlay_arms()`. 87 assertions.
- `scripts/instrument_reachability_gate.py` — `reachable(read=)`.
- `scripts/instrument_reachability_drift_sweep.py` — `SCOPE` (one list, was
  two that disagreed), `adjudicate()`, the honest display, five canary arms.
- `scripts/percentile_index_audit.py` (T5d) — `audit_text()` extracted out of
  `audit_file()`, which is now a thin wrapper. Pure refactor.
- `scripts/percentile_drift_sweep.py` (T5d) — `GATED`, `keyed()` (converted to
  the shared `ordinal_keys`; `line_free` deliberately NOT called, as these rows
  carry no `"<lineno>: "` prefix and it would read as stripping one),
  `head_sites()`, `adjudicate()`, `adjudicate_arms()`, the honest display, and
  `audit()` now returns its `walk` so the guard has the real population.
- `scripts/console_encoding_drift_sweep.py` (T5e) — `adjudicate_arms()`, the
  arms that were missing.
- `scripts/subprocess_encoding_drift_sweep.py` (T5c) — `row_key()` / `keyed()`
  / `flatten()` (the line-free key with its ordinal), `head_offenders()`,
  `adjudicate()`, the honest display with MASKED rows printed separately
  because the worktree loop cannot reach a row the worktree does not have,
  and `split_arms()` in `selftest`. Five perturbations, all red.

⛔ **Two DISPLAYS need two arms.** The MASKED arm first asserted only that the
string `MASKED` appeared somewhere, which the ROW LABEL satisfies — so dropping
the total from the final ADVISORY line red nothing. Measured. The row label
says *which* row; the final line says the class exists at all, and Issue 797's
own rule is that a notice printed in one place is one nobody reads on the run
that needs it.

## Not in scope

- **Repairing riir-train's rows.** That worktree has another session's work
  staged in its index; touching it is the collision AGENTS.md's
  `staged_set_audit` section exists to prevent. The two committed ones are
  riir-train's to fix, and its 53-row standing backlog is the plan-scoped
  over-capture `instrument_reachability` documents for the same repo.
- **Re-pinning 53 → 56.** That is precisely the action this issue exists to
  prevent being taken blind.
