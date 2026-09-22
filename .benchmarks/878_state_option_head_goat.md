# Bench 878 — state_option_scoring::head GOAT (Plan 607 T3 corpus-fitted head)

**Status:** LANDED — **G1 HOLDS** (the T3 lever works): in-corpus 30.0% ·
LOO 29.2% vs constant-pick 10.8% and chance 5.5%; G2/G4/determinism PASS.
Date: 2026-09-23 · Box: M3 Max (macOS 26.6.2, aarch64), AC power, sibling
agent sessions active (light) · Profile: release.

## What landed

- **T3 primitive** — `katgpt-core::state_option_scoring::head` (same
  opt-in feature; no new flag): `FittedHead<D>` (weights = the
  determinism-committed artifact; `score`/`pick` are stack-local f64
  folds, zero-alloc) + `HeadFitter<D>` (the D×D Gram/Cholesky scratch
  owned and reused across refits — stable Rust rejects `[0.0; D * D]`
  under a plain const-generic, so the cold fit path owns a heap scratch;
  documented, and OUT of the G4 window). Fit = closed-form ridge LS
  CONSUMING `linalg::ridge_solve`'s f64 path (KARC Plan 308's fit math —
  the T0a substrate-first consume-not-fork rule; attn-match's beta_fitter
  is the pattern, the in-crate `linalg` is the dependency-legal copy).
  `state_option_scoring` joins linalg's gate list at birth (the
  Issue-684/707/736/763 rule). No RNG, no iterations, no gradient descent
  — Plan 607 T3's determinism line held by construction (scalar `mul_add`
  + IEEE `sqrt` are exactly rounded → two-box portable).
- **T3 arena** — `examples/tetris_03_head_fit.rs` + the extracted shared
  substrate `examples/common/tetris_fixture.rs` (fixture schema + drift
  detector + play loop + Dellacherie policy — one copy now behind the
  `tetris_02`/`tetris_03` pair; the `#[path]` common-module precedent).
  Method: standardize the 11 frozen features corpus-side (fixed order),
  intercept in the design matrix (D=12), y = the oracle's per-option
  `p_clean`; **λ selected by state-level LOO MSE over the pinned grid**
  (corpus-only — the agreement number is never selected on); the G1
  reading reports BOTH in-corpus (the "corpus-viable" claim, explicitly
  not a generalization claim) and leave-one-STATE-out (sibling options of
  a state never leak into that state's fit).

## Gates

| gate | result | evidence |
|---|---|---|
| G1a planted-fit ranking (bench, synthetic) | **PASS 200/200** | the fit recovers a planted head's ranking at every fresh decision pair (near-tie pairs redrawn deterministically — a ranking claim, never a coin flip on f64 noise) |
| G1b discrimination floor | **PASS** | distinct ≥ 2 both postures (arena: in-corpus 22 / LOO 22 distinct picks; bench: 2 distinct over the 2-option synthetic sets, constant-pick fraction printed 53.5%) |
| **G1 agreement vs the T0b oracle triples (arena)** | **HOLDS** | **in-corpus 36/120 (30.0%) · LOO 35/120 (29.2%)** vs constant-pick 13/120 (10.8%) and chance 5.5% — the bar is strict `>`, cleared 2.7×; detail below |
| G2 latency | **PASS** | head pick per decision SET p99 **42 ns (K=9) / 84 ns (K=17) / 167 ns (K=34)** at D=12 (≤1 ms bar, 3+ orders of headroom; option count + tail support printed; n=2000) |
| G4 alloc | **PASS** | `state_option_head_alloc_check`: 0 allocs / 0 deallocs across 100 steady-state head decision sets at K=34, D=12 (HeadFitter's one-time scratch construction deliberately outside the window — documented in the binary) |
| determinism | **PASS** | double-fit bit-identical; two full arena passes byte-identical; digests below |
| G3 no-regression | **PASS** | default `--lib` clean; bench_876's anchors byte-identical post-T3 (table `f2e231b2…`, decisions `8f5d9f91…` — the T1 path untouched); tetris_02's 3 arena tests green after the shared-module extraction |

## The G1 reading (T3 vs T1's Bench 876)

| reader | agreement | vs constant-pick (10.8%) |
|---|---|---|
| T1 untuned sentence-cosine (876) | 13/120 (10.8%) | TIES — G1 did not hold |
| **T3 corpus-fitted head, in-corpus** | **36/120 (30.0%)** | **2.7× — HOLDS** |
| **T3 corpus-fitted head, LOO** | **35/120 (29.2%)** | **2.7× — HOLDS** |
| vs Dellacherie argmax (context) | 46/120 (38.3%) | the head agrees with the classic heuristic MORE than with laya (the features carry Dellacherie columns; laya reads cleanliness sentences) |

- **The headline is the in-corpus ≈ LOO gap: 30.0% vs 29.2%.** At n=120
  states / 2,660 options the fitted head barely overfits — the ridge +
  11 features keep the fit honest, so the corpus-viable claim and the
  generalization claim are nearly the same number. THAT is what makes
  the G1 HOLD honest rather than circular.
- **λ selection is nearly flat** (LOO MSE 0.023152 at λ ∈ {1e-3, 1e-2,
  1e-1}, 0.023154 at 1.0) — the fit is stable across two orders of
  magnitude of ridge; the selection picked λ=0.1 by a strict-`<` margin
  beyond print precision. The flatness is itself the finding: the head
  does not need tuning to clear constant-pick, it needs STRUCTURED
  FEATURES (the T1 scorer had the same corpus and could not).
- **Lines-cleared** (8 seeded games/policy, shared piece streams, cap
  500): Dellacherie 195.62 mean vs **t3_fitted_head 60.75** (median 52,
  max 152) — 18× the T1-sentence policy's 3.4 (876), still below
  Dellacherie by design: the head imitates LAYA's p_clean, and laya
  itself agrees with Dellacherie on only 7/120 states. The head plays
  the oracle's game, not the win-condition's.
- Class-level (same-sentence equivalence): 42/120 (35.0%) in-corpus.

## Determinism anchors (two-box comparison — the standing claim)

- head blake3 (in-corpus fit @ chosen λ): `65409c14fd7573c6ea821d2d32ab9aa44cbda2f59c707759db2df39870fa2e66`
- arena decisions blake3: `04644b0c6bcfb290582735e1ec890972799e24f1761514f06a60ba9827c8fb0c`
- bench head blake3 (synthetic): `8d703f6adb0a9572318d91d3e176158739468e218bc94f73bbad0dde54498482`
- bench decisions blake3: `c81f3b57f71805bce2a990eceab2ab4066d1793bc8054506f9287cb3fc91bd09`

All from THIS box (M3 Max aarch64, release). A second box re-running
`cargo run --release --features state_option_scoring --example
tetris_03_head_fit` and `cargo bench -p katgpt-core --features
state_option_scoring --bench bench_878_state_option_head_goat` must print
byte-identical digests (f64 scalar `mul_add` + IEEE `sqrt` are exactly
rounded — the f64 solve path is box-portable by construction, unlike the
SIMD f32 dispatchers). (The 4090 leg was not run this session — the
digests above are the anchors to compare.)

## Test-gate wiring (the executing lanes)

- `katgpt-core:2085:state_option_scoring` — 14 feature-gated lib tests
  (8 T1 + 6 new head: planted recovery, bit-determinism, lowest-index
  ties, ridge shrinkage, the two refusal panics) + distance_abstain's,
  over the default base — measured 2085 at landing (was 2079).
- `katgpt-core:1:state_option_head_alloc_check:state_option_scoring` —
  the G4 binary (PERF_ROWS grammar, `--release --test-threads=1`).
- The T3 arena's 3 example tests (drift, head bit-determinism on the real
  corpus, discrimination floor) run via `cargo test --example
  tetris_03_head_fit --features state_option_scoring`.

## Re-run commands

```bash
cargo run   --release --features state_option_scoring --example tetris_03_head_fit
cargo test  --release --features state_option_scoring --example tetris_03_head_fit
cargo bench -p katgpt-core --features state_option_scoring --bench bench_878_state_option_head_goat
cargo test  -p katgpt-core --features state_option_scoring --test state_option_head_alloc_check
```
