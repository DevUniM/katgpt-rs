# Issue 809 — a shipped pruner drew from the UNSEEDED global RNG, so it returned a different answer every process

**Status:** CLOSED — T1 + T2 LANDED 2026-09-16 (the census is read, the class is gated); T3 LANDED 2026-09-16 (the `Rng::new()` census is read and the constructor class joined the gate). Found while running [Issue 806](806_x86_64_execution_matrix_followup.md)'s execution matrix.

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
- [x] **T3 — the `fastrand::Rng::new()` census LANDED (2026-09-16).** Measured population: **131
      `Rng::new()` sites across 50 tracked `*.rs` at HEAD** (95 in production paths — the estimate in
      this issue's original text — plus the tests/benches/examples tail; `Rng::default()` measured 0).
      Every site adjudicated per-site (three parallel read passes, verdicts quote the decisive fact);
      **0 defect-shaped in production logic beyond the three fixed below; the rest are sampling-by-design**
      (test-gated statistical margins, injector-designed production APIs that take `&mut Rng` from the
      caller, players/drafters/generators whose entropy is the semantics, bench harnesses where the
      draw IS the timed workload, doc-comment examples, dead-plumbing rng forwarded to mocks that
      ignore it). The class joined the gate: `global_rng_gate.py` now matches `\bRng::new\(\)|
      \bRng::default\(\)` under the key `new` (the `\b` keeps `StdRng::new()` out; over-detection lands
      loud), the pin file carries a reasoned row per (file, call) — **147 sites / 55 files, every row
      pinned**, floors re-based to the merged population (60/20). Canary re-proven both directions.
      FIXED (3):
      - `katgpt-pruners/src/lsh_cache.rs` — `LshApproximateCache::new` seeded the ±1 SimHash
        projection — the LSH hash function itself — from OS entropy, so the same constructor arguments
        produced different fingerprints every process and the GOAT-recorded capture rate
        (`tests/bfcf_lsh_cms_goat.rs` g2, `l1_rate >= 0.10`) was not comparable across runs. Now
        `seed_from_config` (FNV-1a over the four constructor scalars — the Issue-809 house pattern),
        guarded by `test_lsh_projection_is_config_deterministic` (bit identity + a different config
        must NOT reproduce it). LSH GOAT gate 10/10 green post-fix.
      - `katgpt-pruners/src/bt_rank.rs` — `bt_fit_from_fn` drew its K-regular pairings from an internal
        unseeded `Rng::new()` while its own tests seed `bt_pair_random` — the shipped wrapper denied
        callers the reproducibility the crate treats as the convention. Takes a `seed: u64` parameter
        now (zero callers at fix time — the free-API moment).
      - `katgpt-spectral/src/peira.rs` — `alignment_converges_on_synthetic_data` asserted a numeric
        floor (`alignment > 0.1`) that the unseeded draws genuinely DRIVE; a failing run would have
        been irreproducible — this issue's exact symptom class. `Rng::with_seed(42)` (the sibling-test
        convention). The `no_collapse` sibling stays unseeded (all-zero sample has measure ~zero).
      BORDERLINE adjudicated BY-DESIGN (2):
      - `katgpt-core/src/curator.rs` `CuratorBandit::new` — Thompson-sampling exploration noise; no
        test/bench pins the trajectory and arm selection crosses no sync/replay boundary today. The
        recorded trigger for adding a `with_seed` seam is either of those materializing (the pin row
        carries it).
      - root `src/benchmark/{distillation,heuristic}.rs` — read directly: the draws ARE the timed
        workload (`bt_pair_random`, `TemplateProposer::propose`); recorded numbers are wall-clock
        throughput. Same class as the GOAT benches.
      Hygiene note recorded, deliberately NOT fixed here (not this issue's class): `traits/mod.rs`
      includes `mod tests_leo;` ungated (its sibling `tests_spec_gen` carries `#[cfg(test)]`) — the
      `#[test]` fns are inert in production builds, but the asymmetry is real.

## Why nothing caught it

The `--lib` suites run on the M3 weekly gate too, so this could have flipped
there at any time — it is not an x86_64 property. What the matrix supplied was
**a second execution of the same commit**, which is the only thing that
distinguishes a flaky assertion from a passing one. A gate that runs once per
commit cannot see this class at all; the two runs happened here only because
the first one was validating the script.
