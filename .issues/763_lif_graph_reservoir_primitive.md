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

## Explicitly out of scope

- Connectome data files (licensing; data-agnostic primitive).
- Any training loop (readout is closed-form ridge; gradient-free by construction).
- Neurotransmitter-realistic dynamics beyond edge signs (signs are the load-bearing part).
