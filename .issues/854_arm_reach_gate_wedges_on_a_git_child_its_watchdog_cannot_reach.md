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

**Status:** OPEN — and INTERMITTENT: observed twice on 2026-09-19 (shikuwa)
on the plain `scripts/arm_reach_gate.py` run over the CHECKS population, with a
third run of the same population completing clean in 1068.9s. T1, T2, T4 and T5 are answered — and THREE of the four resolved by
refuting the task's own proposal, which is what a measurement is for.
T3 (blocked on T1 OBSERVING a stall, not on T1 existing) and T6 are open.

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

## A clean re-run PASSES — so the wedge is INTERMITTENT, which raises the cost

Re-run on the quiet, committed tree after the `ARM_NAMES` reconciliation:
**33 modules · 999 mutants · 683 killed · 65 live survivors, all pinned with a
reason · 0 UNREACHED · 0 NO-ARM · 0 BASELINE · rc = 0 · 1068.9s**, and **no
wedge at all**. Three runs: two stalled, one did not.

⚠ **Read that as the worse news.** A deterministic hang is diagnosable on
demand; an intermittent one means the next stall arrives without warning, in a
run somebody is waiting on, and T1's stderr progress line is the only thing
that will say where. It also means a repair cannot be validated by "it did not
hang this time" — whatever lands under T3/T4 needs an argument, not a green
run.

⚠ **4 mutants TIMEOUT on every run and are PINNED.** They are counted
separately and never as arm reach (the gate's own rule), but they are also
~4 deadlines' worth of the 1069s, and a standing TIMEOUT is a decision line
the harness has never been able to read. Not this issue's subject; recorded
here because the next person to look at the runtime will find them first.

## Telling SLOW from WEDGED — the recipe, because the progress line alone cannot

T1's per-module line says WHERE the run is. It does not say whether the run
is stuck, and the first use of it made that obvious: `dual_allocation_gate`
held the line for several minutes at **6% of one core**, which looks exactly
like the 3% of a real stall. It was not stuck — that module's arms build
two-repo git fixtures (clone × 2, push, fetch) once per mutant, so the parent
is legitimately idle waiting on children that complete.

⛔ **The discriminator is whether the git CHILD PID changes**, not the CPU
figure:

```bash
tail -1 <progress-file>                     # WHICH module
Get-Process -Id <py> | Select CPU            # sample twice, ~20s apart
Get-CimInstance Win32_Process -Filter "Name='git.exe'"   # sample twice
```

- child pid **changes** + CPU creeping → SLOW. Wait.
- child pid **identical** across samples + CPU flat → WEDGED. Kill the CHILD
  (measured: the parent resumes) and RESTART the run rather than nursing it,
  because a straddling run's report describes no single tree (T6).

⚠ This is the `PASSED-ALONE` lesson from AGENTS.md's x86_64 matrix, one
instrument over: a label that asserts a CAUSE the instrument cannot observe
gets it wrong, and the fix is to name the OBSERVATION and print the
disambiguating check where the reader decides. Both states produce "a module
line that has not moved".

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

- [x] **T1 — DONE: a progress channel that SURVIVES the fd-level
      suppression.** The next stall names its module instead of producing
      zero bytes for twenty minutes.

      ⛔ **The obvious implementation does not work, and that is the whole
      content of this task.** `_silence()` redirects fd **1 and 2** to devnull
      — deliberately, because a subprocess inherits fd 1 and writes straight
      past `contextlib.redirect_stdout` — so `print(..., file=sys.stderr)`
      from inside a mutant is swallowed by exactly the mechanism that
      swallows the child output it was added for. The channel is a
      **duplicate of the original stderr taken once at import**
      (`os.dup(2)`), which is the only handle that still reaches a terminal
      or a log from inside the suppression.

      - Per-MODULE (`[arm-reach] enter <name>`) is **always on**: 33 lines,
        and naming the module is what this task asked for, because
        `arm_reach_audit.py <module>` then reproduces in minutes.
      - Per-MUTANT is opt-in (`ARM_REACH_PROGRESS=mutant`): ~1000 lines is
        right when somebody is hunting a stall and noise otherwise.
      - `_progress` never raises. A diagnostic aid that can kill the run it
        is diagnosing is worse than no aid, and an arm pins that.

      ⚠ **It went in at the WRONG SEAM first, and the mistake is instructive:**
      the first draft instrumented the audit's own `main()` loop — but
      `arm_reach_gate` has its OWN `measure()`, so the instrumentation reached
      precisely the caller that was *not* the one wedging. Caught by running
      the gate and reading an empty progress file. It lives at the top of
      `audit_module()` now, the one seam both callers share.

      **The arm asserts the property that matters, which is not "does it
      print".** It writes through a REAL pipe from inside `_silence()` and
      requires the bytes to arrive. Two-sided: replaced with the naive
      `print(msg, file=sys.stderr)`, the arm reports *"the progress channel
      does NOT survive `_silence()`"* — and the mutant's own output leaks to
      the console while doing so, which is the failure made visible.

      ⚠ **It cannot be validated by reproducing the wedge** — that is
      intermittent (two stalls, one clean 1069s run). This is diagnostic
      equipment for the next occurrence, and the honest claim is that it
      makes the next stall readable, not that it prevents one.

- [x] **T2 — CENSUS TAKEN, and it REFUTES the task's own proposal.** The task
      said the bound belongs at the spawn and the population is the whole of
      `scripts/`. Counted first, as it demanded, by AST over tracked
      `scripts/*.py` across the contract repos:

      **206 files · 386 subprocess calls · 138 statically-readable `git`
      spawns · 7 WITH a `timeout=` · 131 WITHOUT**, over 5 repos — katgpt-rs
      121, riir-clippy 4, riir-ai 3, riir-dapps 2, riir-train 1. So the
      population is **not** one repo (do not inherit `check_validation_gate`'s
      answer) and it is **92% concentrated here**.

      ⛔ **A gate over those 131 is exactly the cries-wolf instrument the task
      warned about, and the census is what shows it.** Most are `rev-parse`,
      `ls-files`, `log`, `show` — plumbing where any bound is arbitrary — and
      a handful are `archive`, `clone`, `fetch`, `push`, where a bound has to
      be large or absent (`git archive` of riir-train is legitimately slow).
      131 rows demanding a hand-typed number with a reason is a **backlog
      wearing a pin**, which Issue 785's rule forbids, and it would be paid in
      four repos this session does not own.

      ⚠ **And the exposure is not where the count is.** Those 131 calls have
      run thousands of times across every gate, sweep and audit in this repo
      without wedging. Both observed stalls were inside a **mutation run**,
      where ~1000 git children are spawned from bodies whose control flow has
      been deliberately corrupted — a `check=True` flipped to `False` leaves a
      half-built fixture, and the NEXT git call against it is the one that can
      block. The bound therefore belongs in **the harness that creates that
      condition**, not in 131 call sites that never meet it.

      **Resolution: no gate, no convention, no sweep. The repair is scoped to
      `arm_reach_audit`** — T3 (a non-interactive git environment for every
      mutant) and T4 (whether the run needs a wall bound), both of which are
      one file. ⚠ If a stall is ever observed OUTSIDE a mutation run, this
      answer is void and the census above is the starting point; it is
      recorded here so the next reader re-reads it rather than re-deriving it.

- [ ] **T3 — Non-interactive git for any spawned child.** `GIT_TERMINAL_PROMPT=0`
      plus `GCM_INTERACTIVE=never` turn a credential prompt from an infinite
      wait into an immediate non-zero exit, which a caller can classify.
      ⛔ Do NOT land this as "the fix" — it is a hardening whose relevance is
      **unmeasured** until T1 names the call, and landing it would make the
      stall stop reproducing while leaving the class open. T1 first, and if T1
      shows the child was not prompting, this stays valuable and stays
      un-credited. ⚠ T2's census promoted this from "one of several
      candidates" to **the leading repair**: the bound cannot go in 131 call
      sites, so the mutant's ENVIRONMENT is the only layer that governs every
      git child at once.

- [x] **T4 — ANSWERED: NO in-process wall bound. It would have the
      watchdog's defect BY CONSTRUCTION, which is the one thing this issue
      already knows.**

      The task warned against adding a timeout by symmetry and offered the
      honest alternative that a workstation verdict a human starts may need
      no bound at all. The argument that settles it is stronger than either:

      ⛔ **A wall bound implemented in-process is the SAME mechanism that
      already fails here.** Python has no portable way to interrupt a thread
      blocked in a C call; `_deadline` is a `threading.Timer` plus
      `_thread.interrupt_main()` precisely because `SIGALRM` is POSIX-only
      and this workstation is Windows, and its own docstring states it
      "reaches a pure-Python loop and does NOT reach a blocking C call". A
      module-level or run-level timer is that same construction one scope up.
      It would fire reliably on every case that is **not** this bug and stay
      undeliverable on the one that is.

      So the proposal cannot fix what it aims at. The only bound that WOULD
      is **external** — a real process with a real kill — and that already
      exists as documented practice: AGENTS.md's *"run it MODULE BY MODULE
      with a wall timeout, not as one invocation"*, priced at ~2400
      interpreter starts for `--include-all` and measured at 10.28s vs 7.52s
      for the per-module subprocess variant. Nothing new is owed.

      ⚠ **And a bound would be arbitrary even if it worked.** The legitimate
      duration is **1069s** and moves with the CHECKS population, which grew
      from 22 modules to 33 in a fortnight. A number chosen today reds on a
      population that has merely grown — the cries-wolf instrument this repo
      names, on the one gate that already costs seventeen minutes to run.

      **T1 is the repair.** What was missing was not a bound but the ability
      to SEE where the run is, and a stalled run is now one `tail` away from
      naming its module — after which a human kills the git child (measured:
      that resumes the run) or re-runs that module alone. ⚠ Read the honesty
      of this: it makes the failure cheap to diagnose, and does not prevent
      it. T3 is the candidate that might.

- [x] **T5 — DONE. The gate did not run its classifier's self-test at all,
      and three sibling gates already do.**

      Checked before repairing, as the task demanded. The gate's own
      `EXPECTED_ARM_NAMES` membership pin was NOT the gap — it already
      contained `prove_counter`, so the gate agreed with the audit; the
      disagreement was audit-vs-`check_validation_gate`, which only the
      AUDIT's self-test asserts. And `arm_reach_gate.main()` calls
      `gate_selftest()` and **never** `A.selftest()`.

      ⛔ **It is the one verdict in this family that skipped the Issue 790 T4
      rule.** `platform_dead_code_floor_gate`, `trap_sentinel_gate` and
      `percentile_floor_gate` each call their classifier's `selftest()` first
      and document it. This one did not, which is how it came to run **1002
      seconds and print a verdict over 33 modules while its classifier was
      refusing to classify**.

      The task warned that a second copy of the audit's rule is the shape this
      repo gates against. It is not a copy — it is the same DELEGATION the
      three siblings use, and the two checks cover different axes: the gate's
      membership pin is audit-vs-gate, the audit's self-test is
      audit-vs-`check_validation_gate` plus its own 27 classifier arms.
      Neither makes the other redundant.

      **Cost measured before wiring: 1.115s**, against a ~1069s run.

      Two-sided, against the live condition rather than a synthetic one: with
      `check_validation_gate.ARM_NAMES` put back to its pre-repair value the
      gate prints *"the CLASSIFIER's self-test does not pass, so no verdict is
      claimed"* and returns **2 after 1.1s** — it refuses instead of spending
      the seventeen minutes and then claiming something. Canary 0 failures.

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
