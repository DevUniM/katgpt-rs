# Issue 767: `mb_value` — bounded three-factor (dopamine) plasticity value circuit

**Status:** OPEN — primitive spec (research-distill POC; no consumer wired yet)

**Source:** adonis-singh/TMNF-C @ `eb6be045970e1f490aa02b92b2b39c560782503a` (MIT) — `python/tmnf_fly/mushroom_body.py` (circuit + rule), `train_mb.py` (TD drive). Mechanism prior art: Bennett/Nowotny et al., Nat. Commun. 12:2569 (2021); Handler et al. 2019. Distillation record: [riir-ai Research 380](../../riir-ai/.research/380_tmnf_c_mb_dopamine_value_circuit.md) — re-opens R379 §2 row-40. Substrate consumed: `SignedAdjacency` + fixture-RNG pattern from `lif_graph` (Issue 763); bisection precedent `entropic_tilt::solve_beta`; observability precedent `twist_cache` hit/miss counters.

## What

The missing quadrant of the value-learning space, as one small opt-in katgpt-core primitive: **online × reward-RPE × context-generalizing × bounded** — a mushroom-body-shaped value circuit whose entire learning machinery is one clamp-arithmetic rule:

- `SparseCodeCircuit`: fixed random sparse feature rows (seeded; each PN reads k random input features) with quantile-calibrated ReLU thresholds → top-k sparse code (k of n_kc) over a supplied or random wiring matrix. Bisection on an action/input gain to hit a target code-overlap statistic (17 steps, `[0,64]`) — deterministic calibration, "nothing learned from reward."
- `MbValue`: approach-minus-avoid linear readout over the code (readout gains fixed `±gain/n`, V=0 at start; **no softmax anywhere**).
- `dopamine_update(code, rpe)`: `coincidence = Σ code·rpe; w ← min(clamp(w − η·coincidence·compartment_sign, ≥0), w0)` — weights **bounded [0, w0] by construction**; recovery below-baseline dopamine via the sign structure. η derived (`alpha/(eff_app+eff_avd)`) so ΔV-per-RPE ≈ alpha is scale-free.
- Saturation/usage diagnostics (floor/ceiling fractions, code-overlap far/near, usage Gini).

## Why (the honest gate)

- **G1 correctness**: (i) `w ∈ [0, w0]` invariant under adversarial RPE streams (by construction — assert it); (ii) toy-MDP: V converges toward true returns (ranking axis, see floor); (iii) code determinism bit-identical across runs at same seed.
- **G1 floor (mandatory)**: **ridge-batch readout on the SAME sparse code** (the Issue-763 path) is the baseline. Online rule must (a) match ridge on ranking quality (Spearman of V vs realized return — the source's own `value_progress_corr` axis, measured r=0.8 there) on a stationary toy, or (b) win on the **within-episode adaptation axis** where batch cannot compete (distribution shift mid-stream). Losing both = the primitive does not ship.
- **G2 perf**: update cost O(active_kc × n_mbon) — µs-class at n_kc≈4k/n_mbon≈100; code gen vs full sort (partial-select). Report sparse AND saturated regimes (the R379 §9 G2-bar-honesty import).
- **G4 alloc-free**: all hot paths into preallocated buffers.
- **Not UQ-bearing**: point value for ranking — any future distribution/interval claim owes the conformal-naive floor first (Report-the-Floor rule, recorded in module docs).
- **Measured negatives to carry into docs** (TMNF-C's honesty): candidate actions sharing the code → values barely differ → action selection from shared codes is near-random (50% overlap); frozen weights degrade. The primitive targets **value formation feeding external selection** (utility scoring/pruners), not selection.

## Constraints

- NO connectome dataset ships here (dataset licenses are their own; `lif_graph` rule) — synthetic fixtures + seeded random wiring; a real-wiring loader is a private-side consumer concern.
- Modelless mandate-compliant: the rule is local bounded latent-state mutation (the `rating.rs` Elo precedent — online error-driven state mutation, public crate), not gradient descent; base wiring is frozen/committable.
- Feature flag `mb_value = []` (opt-in), joins the linalg/cfg any-list discipline if it consumes `linalg`.

## Tasks

- [ ] T1 `SparseCodeCircuit` (seeded sparse rows, quantile θ/scale calibration, top-k code into preallocated buffer; wiring via `SignedAdjacency` or seeded random)
- [ ] T2 `dopamine_update` with bounds-by-construction + derived-η calibration; adversarial-RPE bounds test
- [ ] T3 gain bisection to target code-overlap (the `solve_beta` precedent shape) + calibration report struct
- [ ] T4 saturation/usage diagnostics (floor/ceiling, overlap far/near, Gini)
- [ ] T5 G1: toy-MDP value convergence + **ridge-batch floor comparison on the same code** + within-episode-shift arm
- [ ] T6 G2 bench (update µs-class; sparse+saturated regimes reported)
- [ ] T7 G4 alloc-free audit (`--features mb_value`)
- [ ] T8 docs: feature-catalog row + module docs carrying the measured negatives + provenance (sha, Nat. Commun. 2021)
- [ ] T9 GOAT verdict recorded in `.benchmarks/`; promotion decision (default-on ONLY if the floor gate wins modellessly; else stays opt-in)
