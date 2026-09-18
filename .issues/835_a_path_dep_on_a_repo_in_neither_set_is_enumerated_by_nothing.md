# Issue 835: a `path = "../X"` dep on a repo that is NEITHER on disk NOR in `repo_set.txt` breaks a registered repo's build, and no check enumerates it

**Status:** T1 (the gate) **DONE 2026-09-18**. T2 and T3 open.
**Found by:** trying to run `cargo test --lib` in riir-clippy for
[Issue 832](832_fixed_shared_temp_paths_make_tests_race_across_processes.md)
T5 and getting no tests at all. Filed by session `katgpt-rs-c5`.

## What happened

riir-clippy `fbf698e6` (2026-09-18, "the ops-plane ladder rides the riir-llm
leaf") added:

```toml
riir-llm = { path = "../riir-llm", optional = true, default-features = false }
```

`E:\git\riir-llm` existed on exactly one box. On this one, **every** cargo
command in riir-clippy died at manifest load:

```
error: failed to get `riir-llm` as a dependency of package `riir-clippy`
  Caused by: failed to read `E:\git\riir-llm\Cargo.toml`
```

⛔ **`optional = true` does not save you**, which is the part that makes this
worth a gate rather than a note. Cargo resolves path dependencies to read
their package metadata during resolution, *before* feature selection — so
there is no feature flag, no `--no-default-features`, and no `-p` selection
that avoids it. `cargo check`, `cargo test`, `cargo fmt` and `cargo clippy`
are all equally dead. The blast radius is the whole crate, and here it also
took out **`cargo heal`**, whose global binary is built from
`riir-clippy/target/release/cargo-heal`.

## ⛔ The finding: a state that is not a lenient bucket, but no bucket at all

The workspace's population machinery partitions repos two ways:

| state | who notices |
|---|---|
| on disk, absent from `repo_set.txt` | **UNREGISTERED** — "a repo JOINING, reds in every posture" |
| in `repo_set.txt`, absent from disk | **UNSEEN**, or **DEFERRED** under `DOCS_GATE_PARTIAL_CLONE` |
| **neither** | **nothing** |

Every predicate in the registry either derives from the WALK or compares
walk-against-file. A repo in neither set is not something anybody decided to
be lenient about — **it is not enumerated at all**, by construction. And it is
not harmless: it breaks the build of a repo that IS registered, with no
diagnostic beyond cargo's own message, which names a path and not a cause.

⚠ **The REPAIR path was instrumented end-to-end; only DISCOVERY was not.** The
moment the repo was cloned and registered, `agents_repo_set_gate` went to
**26/27** on two independent signals — a `repo_set.txt` row AGENTS.md did not
name, *and* a workspace-count mismatch — and its own message noted that a
matching count would prove nothing. That is a well-built check. It simply sits
on the far side of the problem: it fires when somebody has already found the
repo. This issue closes the near side.

## T1 — `scripts/cross_repo_path_dep_gate.py` (DONE, docs-gate CHECK 28)

```bash
scripts/cross_repo_path_dep_gate.py               # the verdict
scripts/cross_repo_path_dep_gate.py --prove-fires # known answer: the riir-llm ORPHAN
```

Verdicts, and the middle two are the whole design:

- **RESOLVED** — the target directory exists.
- **DEFERRED** — absent from this box but PRESENT in `repo_set.txt`, with
  `DOCS_GATE_PARTIAL_CLONE=1`. The seven canonical repos this workstation
  lacks are exactly this. **Without the distinction the gate is unrunnable on
  any partial box**, which is the same as not existing — and it is only
  expressible *because* `repo_set.txt` exists to tell the two apart.
- ⛔ **ORPHAN** — absent from disk **and** from `repo_set.txt`. Walled at 0.
  ⚠ `DOCS_GATE_PARTIAL_CLONE` must NOT launder this, and an arm asserts it: a
  partial box still reds on a repo nobody has registered.
- ⛔ **BROKEN-SUBPATH** — repo present, crate directory missing. Walled at 0
  too, but kept separate because the remedy is different (fix the path vs
  clone a repo), and pooling would send the reader to the wrong one.

`DOCS_GATE_CI=1` defers the cross-repo axis — the `issue_citation_gate`
precedent. A single-checkout CI job has no siblings and would call every dep
unresolvable.

**Measured on this box:** 0 ORPHAN, 0 BROKEN-SUBPATH over **311 cross-repo
path deps in 183 tracked `Cargo.toml`**. Take live counts from the PASS line.

### ⛔ The green line proves less than it looks like, and now says so

The bucket distribution is literally `{RESOLVED: 311}`. **Every other verdict
has ZERO live cases.** Confirmed two ways — by this gate's own classification,
and independently by `katgpt-rs-54` walking manifests off disk rather than
through a git pathspec (a different population, and immune to the pathspec bug
below by construction rather than by care): **none** of the 311 deps targets
any of the seven absent-but-REGISTERED repos (`katgpt-web`, `mmorpg-editor`,
`mmorpg-remake`, `mmorpg-remaster`, `riir-dao`, `riir-deployer`,
`riir-esp32`).

So the **absent-registered vs absent-unregistered split — the load-bearing
idea in this issue — has never been exercised by a real dependency.**

| verdict | live cases | what actually asserts it |
|---|---|---|
| RESOLVED | 311 | the live run |
| DEFERRED | **0** | its synthetic arm **only** |
| BROKEN-SUBPATH | **0** | its synthetic arm **only** |
| ORPHAN | 0 today | its arms **and** `--prove-fires`, against the real riir-llm state |

This is **not** a defect in the gate and the arms must stay. It is a fact the
gate has to *disclose*, for a reason this repo already writes down for the
sweep family: *a deferral printed only on failure is one nobody reads on the
run that passes.* The PASS line now carries the census in **both** directions
— `⚠ DEFERRED 0 … UNEXERCISED by live data … a green line here is not evidence
that path works` — because otherwise `0 ORPHAN, 0 BROKEN-SUBPATH` invites
exactly the inference it cannot support.

⚠ And a bucket with no live cases is the one a later "simplification" deletes.
The only thing standing between these arms and that is their own perturbation
— `platform_dead_code_audit`'s lesson precisely: its `vendor/` arm red
**nothing** under perturbation, because one exclusion had two code paths and
the arm certified the path it was not aimed at.

⛔ **How this was found is its own lesson, and it favours the boring
instrument.** The external walk was HYPOTHESIS-DRIVEN — it asked "are the
seven absent-but-registered repos referenced?", which is a question about
DEFERRED, and it answered exactly that question. What generalised the finding
to three buckets was the classifier's **own full verdict distribution**,
`{RESOLVED: 311}`, which is not a question at all: it cannot return a clean
answer about a bucket nobody thought to ask about, because every bucket is in
the output whether or not anyone had a theory about it. BROKEN-SUBPATH was in
identical condition and no hypothesis pointed at it.
⇒ **Print the whole distribution, not the buckets you have a hypothesis
about** — and when checking an instrument, read its census before writing a
targeted probe. A targeted probe confirms or refutes; it does not enumerate.

### Three defects found while building it, all by other instruments

⛔ **1. `population_sync_gate` refused an eleventh independent walk, and it was
right for a reason better than the registry.** The first version rolled its
own `BOUNDARY.md + .git` predicate testing `(p / ".git").exists()`. The
canonical one tests **`.is_dir()`** — because a `git worktree` has a `.git`
**FILE** — so the local copy counted this box's `riir-chain.w152` worktree as
a repo and attributed its manifests to a repo that does not exist. The fix was
to DELEGATE to `skill_repo_set_gate.derive_repos` (mapped back through
`repo_alias.disk()`, since this gate *opens* these directories). Population
**323 → 311 deps / 192 → 183 manifests**, the difference being one phantom
repo. *Two predicates disagreeing about the population is exactly what that
gate exists to catch.*

⇒ **The general rule, because this one is worth stating as one:** never write
a fresh contract-repo walk — **delegate to `skill_repo_set_gate.derive_repos`**
(mapping back through `repo_alias.disk()` if you intend to OPEN the
directories). `(p / ".git").exists()` is correct on every box that has no
worktrees, which is most of them, and wrong in a way that attributes one
repo's manifests to a repo that does not exist. That is the same shape as the
misattributed-citation class this workspace already gates: **an instrument
answering a question adjacent to the one asked, and looking clean while doing
it.**

⛔ **2. The floor caught the walk being 4x too small.**
`tracked_files(repo, "Cargo.toml")` looks like it walks manifests; a bare
`Cargo.toml` is a git **pathspec** and matches at the repo ROOT only, so the
population was **18 manifests — one per repo** — with every crate-level
dependency table unread. It reported a confident `0 ORPHAN`. `MIN_MANIFESTS`
turned that into `⛔ WALK REGRESSION`. This is also why my own first hand
measurement said **133** cross-repo deps and the corrected walk says 311: the
ad-hoc probe had the identical bug, so *the instrument corrected its own
author's number.*

⛔ **3. The known-answer validation silently could not rewind.** Pointing
`scan()` at the pre-clone state by injecting `repos_on_disk` and `registry`
reported **0 ORPHAN** — because `classify` probed the **live filesystem**,
where riir-llm now exists, and the filesystem quietly overrode both injected
sets. **An oracle that cannot be pointed at the known answer is not an
oracle**, and it fails in the direction that reads as clean. The existence
probe is injectable now and `--prove-fires` reports the riir-llm ORPHAN.

## Open tasks

- [ ] **T2 — the gate answers "does something exist there", NOT "is it the
  right thing".** Version skew, a stale sibling checkout, and a dep pointing
  at the wrong crate in the right repo all RESOLVE. Whether that second
  question is worth an instrument is unmeasured — **measure before deciding**,
  the `console_encoding_gate` lesson (it assumed `check_validation_gate`'s
  population-of-one answer carried and was wrong by seven repos).

- [ ] **T3 — the cross-repo axis, deliberately NOT answered by symmetry.**
  This gate reads every repo on the box from one checkout, so it is already
  workspace-wide in effect and a `*_drift_sweep.py` sibling would re-walk the
  same tree to print the same number. What is genuinely unmeasured is the
  inverse: a sibling repo whose OWN `repo_set.txt` equivalent (if it has one)
  disagrees with this one. Do not add a sweep before measuring that.

- [ ] **T4 — the boundary question this does not settle, and should not.**
  Whether `riir-llm` *belongs* in the contract set, and whether a leaf crate
  shared by several repos should be a path dep at all rather than a published
  or git dep, is an owner call (BOUNDARY.md's jurisdiction). The gate makes
  the box readable; it does not make the layout right — the same limit
  `DOCS_GATE_KNOWN_EXTRA` states about itself.
