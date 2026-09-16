# Issue 809 — a shipped pruner drew from the UNSEEDED global RNG, so it returned a different answer every process

**Status:** CLOSED — T1 + T2 LANDED 2026-09-16 (the census is read, the class is gated); T3 `[-]` DEFERRED (the `Rng::new()` census, ~95 sites — a separate adjudication, unread rows are a backlog wearing a pin). Found while running [Issue 806](806_x86_64_execution_matrix_followup.md)'s execution matrix.

## Provenance

`scripts/x86_64_execution_matrix.sh` was run twice against the same commit on
the same box, an hour apart. Cell 4 (`katgpt-pruners --lib --all-features`)
came back **3011 passed** and then **3010 passed / 1 failed**:

```
vocab_channel_pruner::tests::test_decompose_neuron_discovers_channels
  assertion `left == right` failed: Token 2 should be the top token, got [3, 2, 1, 0]
    left: 3   right: 2
```

Not a timing bar and not a platform arm — a deterministic-looking assertion
about which token ranks first, flipping between two runs of identical source.

## The defect

`VocabChannelDecomposer::discover_channel` initialised its Householder vector
with `fastrand::f32()` and `optimize_householder` picked coordinate-descent
dimensions with `fastrand::usize(..)`. Both are the **unseeded thread-local
global**, seeded from system entropy on first use per thread. So
`decompose_neuron` was not a function of its arguments: same neuron, same
`lm_head`, different channels — and in the test fixture two tokens tie, so the
symmetry-breaking perturbation decided the order and the assertion was a coin
flip.

**It was an outlier, not a convention.** Measured across this repo:
**555 `Rng::with_seed` sites against 11 global-`fastrand` ones.** A repo whose
gates are fixture hashes, bit-identity pins and `--test-threads=1`
reproducibility had two of those eleven inside a shipped pruner's hot path.

## The fix (landed)

A per-call `fastrand::Rng` seeded from the INPUT — FNV-1a over the neuron's own
f32 **bit patterns** (`to_bits`, so `-0.0` and `0.0` seed differently and NaN
payloads do not collapse) plus the two shape scalars — threaded down through
`discover_channel` and `optimize_householder`.

Derived from the input rather than taken as a config field on purpose: the
perturbation is a **symmetry breaker, not a source of entropy**, so *same
neuron in, same channels out* is the property worth having, and a new
`VocabChannelConfig` field would have broken 21 struct-literal construction
sites to say something the input already says.

Guarded by `test_decompose_neuron_is_deterministic`, which asserts **bit
identity** (not a tolerance — a tolerance would pass on a re-seeded run) across
two calls, *and* that a different neuron does NOT produce the same
decomposition, so a constant seed cannot satisfy it. Validated by
re-introducing the global draw: the new test REDS, and the previously flaky
sibling passed 8 consecutive fresh processes after the fix.

## What is NOT done

- [x] **T1 — the census is READ (2026-09-16).** The live wide-regex census (every free-function
      `fastrand::<primitive>()` over tracked `*.rs`) found **20 sites across 9 files** — wider than
      this issue's original 9-site list (it predates the wide predicate; the simd-tests, cgsp and
      example sites were never enumerated). Every site read and adjudicated; the ONE defect-shaped
      pair is FIXED, the rest are deliberate with the reason on the row
      (`scripts/global_rng_expected.txt`):
      - **FIXED — `src/benchmark/infrastructure.rs` `bench_pflash_maxsim_block_scoring` (2 sites):**
        exactly the latent class this issue predicted ("fixture generation … probably a latent
        version of this same defect"). Unseeded noise meant every GOAT re-run measured a different
        synthetic corpus; recorded numbers were not comparable across runs. Seeded
        `fastrand::Rng::with_seed(809)` — fixture semantics = reproducibility, not entropy. The
        needle structure (spikes 10× above the noise ceiling) is realization-independent, so the
        ≤3× / ≥5% GOAT margins never flipped; the fix removes a variance source, it does not move
        a verdict.
      - `cgsp/types.rs::u8 ×4` — `snapshot_id_now()`: hand-rolled Uuid-v7-layout generator; the
        random bits are the IDENTITY component of a time-ordered id (the sanctioned
        `Uuid::now_v7()` semantics minus the uuid dep). Per-call entropy is the spec.
      - `sdar/sdar_absorb.rs::f32` — SDAR soft gate, stochastic BY DESIGN (module doc:
        `promote = draw < gate`, arXiv:2605.15155); the pure fn takes the draw as an argument.
      - `sdar_gate.rs::f32 ×3` — tests only: statistical validation of the gate's own distribution
        (n=1000, ≥6.3σ bounds); deterministic edges covered by dedicated draw=0/1 tests.
      - `correlation_budget.rs::bool` — test-only ~50% input stream; ordering assertions ~18σ from
        any realized flip at n=500.
      - `katgpt-types/src/simd/tests.rs::f32 ×2` — distributional agreement test; the fresh
        realization every run IS the coverage (1e-4 tol ≈10× realized error).
      - `examples/` ×8 (corr_budget bool ×4, go_00 usize, self_distilling usize+f32) and
        `tests/go_integration.rs::usize ×2` — demo input streams and random legal-move players;
        by-design randomness, `#[ignore]`-gated server tests for the latter.
- [x] **T2 — the class is GATED (2026-09-16).** `scripts/global_rng_gate.py` +
      `scripts/global_rng_expected.txt` + a docs-gate CHECK row + the AGENTS.md table row (the 25th
      check; the prose move-narrative reconciled). Membership pin over the free-function class,
      LINE-FREE keys (`path::call::count` + reason), both directions red (UNPINNED live site /
      STALE row), floors on the walk and the predicate, comment+string masking before matching,
      arms run unconditionally (check_validation credits it; 25/25 at landing). Canaries PROVEN:
      a planted tracked site reds UNPINNED, a moved count reds STALE (the untracked-plant hole —
      the population is what git TRACKS, so a dev-tree scratch file is invisible until staged —
      was found by the canary and is the correct per-push population, not a defect). arm_reach
      measured 22 killed / 2 EQUIVALENT survivors (the in-string EOL-backslash flips — the
      multi-line-string class mask_line documents out of scope; pinned at the arms header).
- [-] **T3 — the `fastrand::Rng::new()` census (DEFERRED with reason).** ~95 sites across 34 files
      in production paths (`crates/*/src`, root `src`), dominated by sampling-by-design paths
      (drafters, players, tournament loops, tests) where fresh entropy per run is the intended
      semantics — but at least one shipped primitive sits in the set (`katgpt-core/curator.rs`
      `CuratorBandit::new` seeds exploration from the global). Each site needs the same per-site
      read T1 did; batch-converting is forbidden by the same rule T1 followed. Unblock: a session
      picks the census as its unit; the gate's out-of-population note already names it.

## Why nothing caught it

The `--lib` suites run on the M3 weekly gate too, so this could have flipped
there at any time — it is not an x86_64 property. What the matrix supplied was
**a second execution of the same commit**, which is the only thing that
distinguishes a flaky assertion from a passing one. A gate that runs once per
commit cannot see this class at all; the two runs happened here only because
the first one was validating the script.
