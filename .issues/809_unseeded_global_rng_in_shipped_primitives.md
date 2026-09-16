# Issue 809 — a shipped pruner drew from the UNSEEDED global RNG, so it returned a different answer every process

**Status:** OPEN — the measured instance is FIXED; the remaining 9 sites are an
unread census. Found while running [Issue 806](806_x86_64_execution_matrix_followup.md)'s
execution matrix.

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

- [ ] **T1 — the other 9 global-`fastrand` sites are an unread census.** They
      are `katgpt-pruners/src/sdar/sdar_absorb.rs:486`,
      `katgpt-pruners/src/sdar_gate.rs:{538,555,572}`,
      `katgpt-speculative/src/correlation_budget.rs:294`,
      `src/benchmark/infrastructure.rs:{815,825}` and the second
      `vocab_channel_pruner` site (fixed). ⚠ **Do not batch-convert them.** The
      four `sdar` ones look like a genuinely stochastic inference gate
      (`let draw = fastrand::f32();` against a threshold), where per-process
      variation may be the intended semantics; the two in `benchmark/` are
      fixture generation, where it is probably a latent version of this same
      defect. Each needs a read, and the answer differs by site.
- [ ] **T2 — nothing gates the class.** A new `fastrand::f32()` in a shipped
      primitive lands silently today. The cheap form is a membership pin over
      the global-`fastrand` call sites with a reason per row, in the style of
      `scripts/console_encoding_expected.txt` — the commit that adds a tenth
      reds, the nine existing ones stay their owners' to adjudicate. Do not
      write it before T1: a pin file full of rows nobody has read is a backlog
      wearing a pin (Issue 785's rule).

## Why nothing caught it

The `--lib` suites run on the M3 weekly gate too, so this could have flipped
there at any time — it is not an x86_64 property. What the matrix supplied was
**a second execution of the same commit**, which is the only thing that
distinguishes a flaky assertion from a passing one. A gate that runs once per
commit cannot see this class at all; the two runs happened here only because
the first one was validating the script.
