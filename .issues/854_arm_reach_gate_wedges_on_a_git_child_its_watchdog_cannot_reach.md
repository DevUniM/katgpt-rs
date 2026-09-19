# Issue 854: `arm_reach_gate` wedges indefinitely on a `git` child — the 10% its watchdog documents, reached on the GATE population rather than `--include-all`

⚠ **Filed as 852, renumbered to 854 before pushing — the THIRD number
collision of this session, and the first the gate caught in its designed
form.** A concurrent session allocated 852 (`852_fmlm_tau_lut_schedule`) and
853 and PUSHED both while this file was local;
`scripts/dual_allocation_gate.py` printed `⛔ INDEPENDENT 852 — two documents
claim one number`, naming both sides' adding commits, exactly as Issue 796
designed it — at allocation time rather than merge time. Adjudicated by
Issue 724 T2 on the same ground Issue 850 used: the other side is pushed, this
one was not.

**Status:** OPEN. Observed twice on 2026-09-19 (shikuwa), both times on the
plain `scripts/arm_reach_gate.py` run over the CHECKS population.

Found while doing something else — the run was started to pin survivors after
Issue 847/848 landed, and never returned.

## What was measured

Two runs, same shape:

| | run 1 | run 2 |
|---|---|---|
| invocation | `py scripts/arm_reach_gate.py` | `py -u scripts/arm_reach_gate.py` |
| wall before intervention | ~17 min | ~20 min |
| CPU at the stall | 36s over 20 min (**3%**) | same class |
| stdout produced | **0 bytes** | **0 bytes** |
| process tree | one `python`, **one `git.exe` child** | same |

Run 2 was resolved by `Stop-Process` on the **git child only**: the parent's
CPU resumed climbing immediately (36s → 40s → 250s → 525s) and a fresh child
appeared, i.e. the blocked `subprocess` call returned and the run continued.
**The parent was never wedged. It was waiting on a child that never exits.**

⚠ **The documented budget is `~130s` for this population.** A 20-minute stall
is not a slow run; it is a stop.

## Why the existing watchdog cannot help, and why that is already written down

`arm_reach_audit._deadline` says so in its own docstring:

> `signal.setitimer`/`SIGALRM` is POSIX-only and this repo's workstation is
> Windows, so the watchdog is a `threading.Timer` calling
> `_thread.interrupt_main()`. That reaches a pure-Python loop — which is the
> measured failure — and does **NOT** reach a blocking C call. […] the
> in-process watchdog is the affordable 90%, and saying which 10% it misses is
> the point of writing that down.

⛔ **The finding is not that the 10% exists — it is WHERE it turned up.** Every
sentence about this class in `arm_reach_audit.py` and in AGENTS.md is scoped to
`--include-all`: *"Run it MODULE BY MODULE with a wall timeout"*, *"a blocking
C call left the process at 3.5% CPU with the watchdog's interrupt pending"*.
The mitigation on offer is a per-module external timeout, and it is offered for
the 55-module investigation population.

This was the **22-module gate**, the one with no such instruction, the one
described as ~130s, and the one that is a VERDICT. A verdict that neither
passes nor fails nor returns is `console_encoding_gate`'s class — findings that
are not *unknown* but *unlooked at* — reached through a different door.

## T1 is PARTLY ANSWERED — and reading the completed run wrong is its own finding

Run 2 eventually completed — **33 modules, 999 mutants, 681 killed, 67 live
survivors incl. 4 TIMEOUT, 1002.0s** — and reported **13 UNPINNED survivors,
every one of them in `dual_allocation_gate.py`**: two literals in `classify`
and **eleven `check=True` / `capture_output=True` kwargs inside
`counter_fixture`**, the function that builds a real two-repo git fixture with
`git clone`, `git push` and `git fetch`.

That localises the wedge: the blocking child is a `counter_fixture` git call.

⛔ **The first write-up of this said those 13 were an artifact of the kill.
That was WRONG, and the correction is the more useful finding.** The evidence
offered was that mutating `classify`'s `"counter": False` → `True` by hand and
running `selftest()` **KILLS** it, via `prove_fires`'s `mislabelled` arm — so
the gate had reported a survivor its own arms catch. The inference does not
follow: `git log -S mislabelled` puts that arm's arrival at **`9d41db17`,
10:21:56**, carrying `Session: katgpt-rs-opus5`. A **different session** wrote
it, into this **shared worktree**, while the run was executing (10:12 → 10:29).

So the 13 were REAL for the tree the run started from, and a concurrent
session armed two of them and pinned the other eleven *during* the run. By the
time the by-hand test was typed, that arm was already in the working tree. The
kill may ALSO have contaminated something — that is **unmeasured**, and the
one piece of evidence advanced for it is fully explained without it.

⚠ This is AGENTS.md § staged_set_audit's own discipline reached by getting it
wrong: *say what you CHECKED, not who you concluded*. The correction cost
nothing only because the commit carried a `Session:` marker.

⛔ **What replaces it is a bigger claim: a 1002-second run reads the WORKING
TREE, and this worktree has five-plus sessions writing it.** `arm_reach_gate`
mutates and re-execs tracked source for sixteen minutes. Any commit landing in
that window changes the population, the arms, and the pin file underneath it,
so the report describes **no single tree** — measured here, it straddled a
commit that took its own finding set from 13 to 0.

That is Issue 797's class, and the gate is outside every mechanism built for
it: `head_delta` / `head_overlay` / `head_tree` are wired into the
`*_drift_sweep.py` family and enforced by `sweep_advisory_membership_gate`,
whose predicate is the FILENAME. This is a `_gate.py`, so nothing ever asked.
⚠ And the usual repair does not transfer — a mutation run cannot be
re-classified against HEAD, because it EXECUTES the source rather than reading
rows out of it. The affordable form is a **disclosure**: record HEAD at entry,
re-read it at exit, and say on the verdict line when they differ. That is T6.

⛔ **Found on the way: the two `ARM_NAMES` sets had DIVERGED, and the audit
refused outright because of it.** `prove_counter` was added to
`arm_reach_audit.ARM_NAMES` with Issue 850 T4 and not to
`check_validation_gate.ARM_NAMES`; the audit's self-test asserts the two agree
(they are one vocabulary read by two instruments — there it decides which
bodies are never mutated, here which calls count as an arm), so
`arm_reach_audit.py <module>` exited 2 with no reach measured at all.
Reconciled. ⚠ The GATE did not refuse on the same disagreement, which is a
separate question and is T5.

## What is NOT known

- **WHICH git call.** The module is `dual_allocation_gate` and the function is
  `counter_fixture` (localised above), but that function issues `git clone`
  × 2, `git push`, `git fetch` and several plumbing calls, and
  `Win32_Process.CommandLine` came back **EMPTY** for the child on this box,
  so the invocation itself is unrecorded. ⚠ The localisation is INFERRED from
  where the contaminated survivors clustered, not observed — a weaker
  standing than the process-table facts above it, and T1 is what upgrades it.
- **Why it blocks.** Candidates, none measured: a credential/terminal prompt on
  a mutated remote path (`GIT_TERMINAL_PROMPT` is unset here), a lock
  contended by a concurrent session in a shared worktree, a `git` reading
  stdin. ⚠ Do not repair on the most plausible of these — the whole shape of
  this issue is an instrument answering a question nobody measured.
- **Whether a mutation causes it at all.** The unmutated baseline may block
  identically and simply has not been observed to.

## Tasks

- [ ] **T1 — NARROWED to `counter_fixture`'s git calls; finish it.** Give the audit a
      per-mutant progress line on **stderr** (unbuffered, one line per module
      entered) so the next stall names its module without waiting for the
      report. The run currently suppresses child output at the **file
      descriptor** level for a measured reason (436 `git archive` calls
      littering the report), so the progress line has to live outside that
      redirect rather than inside it. ⚠ Confirm the stall reproduces at the
      identified module and is not a box-wide git condition — this box runs
      five-plus concurrent sessions against shared worktrees.

- [ ] **T2 — The bound belongs at the SPAWN, and the population is the whole
      of `scripts/`.** A thread-based interrupt provably cannot reach a
      blocking C call, so no amount of watchdog work fixes this; a `timeout=`
      on `subprocess.run` does, because the bound is enforced by the same layer
      that owns the child. `scripts/fetch_contract_repos.py` (Issue 850 T2) was
      written with it for exactly this reason and says so at the call.
      **Count the population before choosing between a gate and a convention**
      — `console_encoding_gate` inherited a no-sweep answer and was wrong by
      seven repos. A census of timeout-less `subprocess.run(["git", …])` across
      tracked `scripts/*.py` is the first measurement, and `subprocess_encoding_gate`
      already walks that exact population with an AST, so the predicate has a
      home rather than needing a new walk.
      ⚠ A timeout is only correct where the caller can say what a timeout
      MEANS. A `git archive` of riir-train is legitimately slow; a bound that
      turns a big repo into a failure is the cries-wolf instrument this repo
      warns about. Per-call, with a reason, not one constant.

- [ ] **T3 — Non-interactive git for any spawned child.** `GIT_TERMINAL_PROMPT=0`
      plus `GCM_INTERACTIVE=never` turn a credential prompt from an infinite
      wait into an immediate non-zero exit, which a caller can classify.
      ⛔ Do NOT land this as "the fix" — it is a hardening whose relevance is
      **unmeasured** until T1 names the call, and landing it would make the
      stall stop reproducing while leaving the class open. T1 first, and if T1
      shows the child was not prompting, this stays valuable and stays
      un-credited.

- [ ] **T4 — Does the gate need a WALL bound of its own?** The audit bounds a
      MUTANT (derived from the module's own baseline, 10x floored at 30s). The
      gate has no bound on the whole run, so an unbounded child is unbounded
      end to end. ⚠ Answer with the same discipline Issue 850 T2 used: the
      honest alternative may be that a workstation verdict does not need a wall
      bound at all, because a human is watching it — in which case the repair
      is the stderr progress line (T1) and nothing else. **Do not add a
      timeout by symmetry.**

- [ ] **T5 — The GATE did not refuse on a classifier self-test the AUDIT
      refuses on.** `arm_reach_audit`'s self-test runs on every invocation of
      the audit and exits 2 — *"a mutation harness whose runner always reports
      KILLED prints a PERFECT score, which is the same output as
      perfection"*. `arm_reach_gate.py` ran 1002s and printed a verdict over
      33 modules with that same self-test failing. ⚠ Check before repairing
      whether the gate has its own equivalent (it carries three floors of its
      own, and duplicating the audit's check would be the second copy of a
      rule this repo gates against). If it does not, the gate is exactly the
      consumer the classifier's self-test *"cannot reach"* — Issue 775's
      sentence, which this family already records four times.

- [ ] **T6 — A 1002s run over a shared worktree must DISCLOSE that the tree
      moved.** Measured above: this run straddled another session's commit and
      its finding set was 13 at one end and 0 at the other, with nothing in
      the output saying so. The sweep family's head-provenance mechanisms do
      not transfer — a mutation run EXECUTES the source rather than reading
      rows from it, so there is nothing to re-classify. Record `HEAD` and the
      dirty-set at entry, re-read at exit, and name the drift on the verdict
      line. ⚠ Keep it ADVISORY: a gate that hard-reds because a sibling
      committed during a sixteen-minute run is the cries-wolf instrument this
      repo warns about. ⚠ `sweep_advisory_membership_gate` keys on the
      `*_drift_sweep.py` FILENAME, which is why nothing asked this gate for
      wiring — whether that predicate should widen is a separate question and
      should be MEASURED (how many `_gate.py` files carry a long tree-reading
      run?) rather than answered by symmetry.

## What this does not claim

Nothing about the gate's VERDICTS. When it completes, it completes correctly;
the survivors it reports and the pins it adjudicates are unaffected. This is
about a run that does not finish, which is a different failure from a run that
finishes wrong — and the worse one only because it is silent.
