# Bench 766: `subspace_intervention` — protocol promotion + the FUNCATTN spectral arm (Issue 779 T1+T2 / Research 557)

**Status:** PASS — T1 (module promotion, opt-in per the no-default-consumer
rule) + T2 (the deferred `spectral_pre_rotate` eval, POSITIVE arm). T3
(real-bank affinity capture) stays deferred — needs a real-model run
(riir-ai CollectingHook / riir-train fixtures; sibling lanes active).

**Date:** 2026-09-15 · **Lanes:** `cargo test -p katgpt-core --features
subspace_intervention --lib subspace_intervention` (7 tests) · `cargo test
-p katgpt-attn --features funcattn_spectral_pre_rotate --test
funcattn_spectral_triad` · release/allocTracking · default-floor ·
`--all-features` check · clippy `-D warnings` both crates.

## T1 — the promoted module (feature `subspace_intervention`, opt-in)

`katgpt_core::subspace_intervention` over `subspace_phase_gate::thin_svd_into`
(zero new deps): the modelless ridge probe (`ridge_probe_fit_into`), frozen
head eval (`eval_head_into` + `InterventionScratch::eval_into`), basis
projection (`project_through_into`), seeded control (`random_basis_into` +
public `InterventionRng`), principal-angle `basis_similarity`,
`three_arm_eval` (probe basis) / `three_arm_eval_on_basis` (caller basis —
the FUNCATTN arm), `affinity_sweep` (task→layer affinity over a packed
bank). Zero-alloc eval paths (caller-owned `InterventionScratch`); the
sweep allocates its gather rows once per call (documented).

**The promotion found a real bug in the POC harness (design record, in the
module doc):** the 778 harness's "ridge" algebraically collapses to the
class-sum readout `W = XᵀY` — it formed `G⁺·(XᵀY)` and then divided by
`σⱼ²`, i.e. computed `(G⁺)⁻¹·(G⁺·M) = M`. A serviceable nearest-mean probe
(which is why 778's gates passed), but not ridge. The promoted primitive
computes the true solve `Wᵀ = Σⱼ vⱼ·(vⱼᵀ·M)/σⱼ` — verified on a
two-class sanity cell (w = ±0.5 exactly, acc 1.0) and the planted bank
(full accuracy 1.0 where the POC-form head sat at 0.208 under an
aliasing-aliased test split — see below).

**Test-bank traps found on the way (kept as notes in the tests):** a
parity train/test split with `labels = i % C` at even C aliased the split —
train never saw half the classes and the probe sat at chance with BOTH triad
arms equal (the projection-identity gate alone cannot catch a broken head —
it held at chance too). The bank now uses `(i/2) % C`.

### Gates (7 tests, deterministic)

| Gate | Assert | Result |
|---|---|---|
| G1 identity | aligned@k=rank == full, exact | PASS |
| G1 contrast | aligned@k=4 ≥ random + 0.15; residual ≤ chance + 0.05 | PASS |
| affinity | sweep picks the task layer (all class peaks on it) | PASS |
| basis_similarity | same span → 1.0; independent → ≪ 0.5 | PASS |
| orthonormality | Gram–Schmidt contract (±1e-4) | PASS |
| probe sanity | 2-class separable ⇒ acc > 0.99 | PASS |
| G4 alloc | three_arm_eval: 0 allocs (release + alloc_tracking, Issue-741 predicate) | PASS |

G3: default suite 2060 unchanged (opt-in feature); clippy `-D warnings`
clean; `--all-features` check clean.

## T2 — the FUNCATTN spectral arm (the spectral_pre_rotate.rs:29-31 deferral closed)

`katgpt-attn/tests/funcattn_spectral_triad.rs` (dev-dep feature-forward —
the lib surface unchanged): the REAL production eigenbasis path
(`katgpt_spectral::calibrate_eigenbasis` — exactly what
`calibrate_and_pre_rotate_basis` calls) on the SpectralQuant-hypothesis
geometry (top eigendirections carry the class-mean signal; variances
4.0/2.0/0.5/0.25; d=32, C=4, task rank 2), then the triad at matched
budgets through the frozen ridge-probe head:

| k | eigen-aligned | random | residual |
|---|---|---|---|
| 2 (= task rank) | **0.802** | 0.354 | 0.208 |
| 4 | **0.792** | 0.250 | 0.208 |

(full head accuracy 0.656; chance 0.25.)

**The deferred hypothesis lands POSITIVE at composition level:** the
eigen-aligned k-subspace at matched param budget beats the random control
by **+0.45** — and BEATS the unprojected head (+0.15 over full: projecting
onto the top-2 eigenspace DENOISES the readout). Residual ≈ chance: the
task signal genuinely lives in the eigen-subspace. This is the
mechanism-level evidence `spectral_pre_rotate` deferred; whether it holds
on REAL model activations is T3's capture (still deferred — a real-model
run, sibling lanes active in riir-ai/riir-train).

## Verdict

- `subspace_intervention` ships OPT-IN (no default consumer — the house
  rule; the FUNCATTN arm is a dev-dep test consumer, not a default-path
  consumer). Promotion to default needs a production consumer.
- T3 (real-bank affinity, `FutureBehaviorProbe` layer re-pin) remains the
  open follow-up — recorded in R557 §PoC Addendum + the issue.

## Reproduce

```sh
cargo test -p katgpt-core --features subspace_intervention --lib subspace_intervention -- --nocapture
cargo test -p katgpt-attn --features funcattn_spectral_pre_rotate --test funcattn_spectral_triad -- --nocapture
cargo test -p katgpt-core --release --features subspace_intervention,alloc_tracking --lib subspace_intervention
```
