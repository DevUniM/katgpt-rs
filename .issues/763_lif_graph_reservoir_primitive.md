# Issue 763: Signed-graph LIF reservoir primitive — event-driven sparse propagation POC (fly-connectome survey fusion)

**Status:** OPEN — fusion idea, novelty TBD pending POC (application novelty only; mechanism prior art is published — Costi et al. 2025, Suárez et al. 2024 conn2res, Shiu et al. Nature 2024).
**Origin:** fly-connectome landscape survey ([riir-ai Research 379](../../riir-ai/.research/379_fly_connectome_fixed_wiring_reservoir.md), private) · sibling motor-half idea: riir-ai Issue 935 (flybody WPG, parked).
**Date:** 2026-09-13

---

## Background

The fly-connectome wave's core architecture — a **fixed sparse sign-constrained graph** running LIF (leaky integrate-and-fire) dynamics with a **tiny trained/closed-form readout** — is the reservoir class this repo does not ship. Current reservoir coverage: KARC (`karc/`) is a delay-basis reservoir (temporal, dense state); no kernel runs dynamics on a sparse signed adjacency; no kernel has LIF's threshold→spike→reset event discipline (which makes per-tick cost O(active) instead of O(total) — the property that let Shiu et al. simulate a whole fly brain on a laptop).

The primitive is **data-agnostic**: callers supply any signed sparse graph (CSR). NO connectome dataset files ship in this repo (FlyWire/MaleCNS carry their own licenses; fixtures are synthetic).

## The primitive (proposed `katgpt-core/src/lif_graph/`, feature `lif_graph`, opt-in)

- `SignedAdjacency` — CSR format, `#[repr(C)]`-friendly fixed layout (BLAKE3-committable by consumers).
- `LifState` — per-node membrane potential + refractory counter, fixed-size, zero-alloc.
- `step()` — leak + integrate + threshold→spike→reset; spike events propagate ONLY from spiking nodes (event queue / active-set, scratch buffer reused across calls).
- `ridge_readout()` — reuse the `linalg::ridge_solve` pattern (KARC precedent) for closed-form linear readout fitting. CEM deliberately NOT included (audited discard: ridge covers linear readouts closed-form; CEM only earns keep for nonlinear readouts — no evidence yet).

## Tasks

- [ ] **T1** Substrate-first re-check at implementation time (the class is new, but re-grep `lif|spike|graph.*propag` for anything landed since 2026-09-13).
- [ ] **T2** `lif_graph` module behind `feature = "lif_graph"`: `SignedAdjacency` (CSR), `LifState`, event-driven `step()` with reused scratch; zero allocation in the tick loop.
- [ ] **T3** G1 correctness: bit/trajectory parity of event-driven step vs a dense reference LIF on synthetic signed graphs (same spike trains).
- [ ] **T4** G2 perf bench: N = 1k / 10k nodes, ~1–5% active fraction per tick, event-driven vs dense matvec-style update; gate = ≥3× at 10k/1% (tune to a defensible bar before promoting).
- [ ] **T5** G4 alloc-free gate (existing alloc-count validator pattern).
- [ ] **T6** GOAT verdict + promote/demote decision recorded in `.benchmarks/`; if promoted, note the consumer path (riir-ai per-archetype circuit shard + per-NPC readout — riir-ai Research 379 §7).

## Implementation references (2026-09-13 dig — 10 repos cloned at pinned SHAs, read-only; full record: riir-ai Research 379 §9)

- **RuVector** `examples/connectome-fly` @ `8667f1f4e57055d063f080dfa60c80dd50874d20` (branch `research/connectome-ruvector`, **MIT — the only derivable code source**; note: `ruvnet/Connectome-OS` itself is docs-only, `d54a5270`, no license): conductance-based LIF with **exact exponential integration** (precompute `alpha_x = exp(-dt/tau_x)` once → 3 muls/neuron hot loop), CSR **SoA with sign pre-folded into `signed_weight: f32`** + delay-sorted rows, **timing wheel** (dt-buckets, ~32ms horizon, spill heap, precomputed `delay_buckets: u32` = integer add insert) + **active set with quiescence dropout** (in-place compaction when `|g_e|,|g_i|,|v-v_rest| < tol`). Measured single-thread: **3.91× over baseline, ~7.6M spikes/s**; honest caveat — active-set wins collapse to 1.01× at saturation.
- **Shiu et al. canonical model** @ `91bdd1e7` (MIT, Brian2) — the parity target + canonical constants: current-based `dv/dt = (v_0 − v + g)/t_mbr`, `dg/dt = −g/tau`, v_0=v_rst=−52mV, v_th=−45mV, t_mbr=20ms, tau_syn=5ms, refrac 2.2ms, delay 1.8ms, `w = 0.275mV × signed_count`, dt=0.1ms. Edge sign = neurotransmitter sign × synapse count.
- **FastFly** @ `c84458b4` (**NO LICENSE — ideas only, never code**): per-row INT8 + f32 scale (global scale measured useless, ~13 levels), warp-ballot → compaction → warp-per-spike push (7.8× real-time RTX 5080, 138.6k neurons/15.1M syn, 128µs/step), stateless hash noise `(i, step, seed)`.
- **fly-brain (EON)** @ `a3db62f9` (**GPL-2.0 — ideas only**): 6-backend benchmark of the same Shiu model — GeNN 1.94× RT vs PyTorch 0.10× RT; benchmark hygiene worth copying (setup vs sim time separated, spikes exported outside timing, per-backend parity vs Brian2 reference).
- **Additional Rust refs from the wave sweep** (not cloned): fly-chess (full FlyWire 138.6k LIF in Rust/WASM in-browser, Brian2 parity 2.56e-13 mV, fixed ±1 untrained readout) · Jhongdlp/FlyBrain (bit-for-bit deterministic Rust engine, >1M steps/s, looming→GF 30–70× over randomized controls) · flyverse-core (CUDA + hand-written **Metal** kernels, 0.8–1.2× RT on Apple Silicon — M3-relevant) · gnat (seeded-RNG invariant tests across 4 seeds) · fly-escape (Rust/WASM).
- **Controls for G1/G3** (FlyDoom @ `a9d9dba`, no license — methodology only): 3-tier null ladder — ER-matched (same N,E, permuted weights) / **Maslov–Sneppen degree-preserving double-edge swaps** / weight-shuffle. Wire the degree-preserving swap in as the "any sparse signed reservoir would do" control arm.

**Gate refinements from the dig:** T4's G2 must report BOTH regimes (sparse 1–5% active AND saturated) — the sparse-regime win is the claim, saturation parity is the honesty line (RuVector measured exactly this collapse). T3 parity reference = Shiu constants above. Avoid: clock-driven full-N updates on the hot path (0.10–0.34× RT measured); PyTorch-style per-tick delay-buffer allocation (use fixed ring + head index); the micro-opts both repos measured as losses (shared-mem accumulation at low collision, unconditional in-bucket sort).

## Explicitly out of scope

- Connectome data files (licensing; data-agnostic primitive).
- Any training loop (readout is closed-form ridge; gradient-free by construction).
- Neurotransmitter-realistic dynamics beyond edge signs (signs are the load-bearing part).
