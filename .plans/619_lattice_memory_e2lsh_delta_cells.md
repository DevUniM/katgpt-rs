# Plan 619: LatticeMemory — E2LSH-Addressed Delta-Rule Cell Lattice (Open Primitive)

**Status:** ACTIVE — Phase 0 (gate designs only until measured)
**Date:** 2026-10-03
**Research:** [../riir-refine/.research/233_Percepta_Spotlight_Growing_Memory.md](../riir-refine/.research/233_Percepta_Spotlight_Growing_Memory.md) (the distill note — this plan is its track-(a) upstream half)
**Consumer plan:** [../riir-refine/.plans/199_spotlight_lattice_wasm_capability_lane.md](../riir-refine/.plans/199_spotlight_lattice_wasm_capability_lane.md) (healer consumption + WASM lane live THERE; this plan owns only the katgpt-core primitive + its bench)
**Source:** Percepta "Spotlight Memory" blog 2026-10-02 (lattice-of-delta-cells class: SDM arXiv:2607.07386, MARCH 2608.12435, Memory Layers 2412.09764 are the published lineage; our form is deterministic, no GD)
**Target:** `crates/katgpt-core/src/lattice_memory/` (new module) + Cargo feature `lattice_memory`
**Substrate duties:** the seeded projection + `seed_from_config` logic MOVES DOWN into `katgpt-core` (small shared module) and `katgpt-pruners/src/lsh_cache.rs` re-exports it — `katgpt-pruners` already depends on `katgpt-core` (its Cargo.toml), so the down-move is cycle-free and the reverse dep would be a cycle; never a second copy of the ~40 LOC. **Name disambiguation:** this module is NOT `analytic_lattice` (Plan 330 transport operators — unrelated).

---

## Goal

Ship the deterministic (modelless) extraction of Spotlight's addressing math: a 2D lattice of delta-rule cells, addressed by **continuous E2LSH per-axis coordinates**, bump-interpolated over the 3×3 neighborhood, cells allocated on first write and updated in place — the candidate fifth retrieval complexity class (growing state + constant-neighborhood access + graded near-miss recall) beside Raven O(1) / Engram O(1) / δ-Mem O(r) / PKM O(√N). GOAT-gated against PKM and Engram at OUR key distributions (C4); promote only on a measured win; demote the loser per slot.

## Phase 1 — Primitive (katgpt-core, feature `lattice_memory` opt-in)

### Tasks

- [ ] **T1.1** Module skeleton `src/lattice_memory/` + `types.rs`: `LatticeMemory` over a preallocated flat slab with **runtime `d_k`/`d_v`** (the `DeltaMemoryState` shape — `[f32; D_K*D_V]` const-generic arrays need `generic_const_exprs`, unstable on the pinned 1.98.1 toolchain; flat slab or a single const grid `N` only). Cell state = **offset+length into the slab** (never a per-cell heap allocation); `LatticeCell { offset: u32, len: u32, writes: u32 }`. Feature `lattice_memory = []`.
- [ ] **T1.2** **Addressing = continuous E2LSH per axis, NOT integer-split SimHash.** Rejected form (recorded): sign-bit split → two integers — a 1-bit high-order change moves |Δx| ≫ 1 (lattice neighbors ≠ embedding neighbors) and yields no fractional part, killing the bump. Adopted form: per-axis `(a·x + b)/w` with seeded `a` (p-stable/Gaussian), `b`, width `w` — integer part = cell coordinate, **fractional part = bump input** (real, non-zero). Projection/seed discipline via the shared module moved DOWN from `katgpt-pruners/lsh_cache.rs` (which re-exports it — dependency direction: pruners → core already exists). Tests: per-axis locality (small embedding perturbation → same/adjacent cell with high probability); fractional-part distribution not degenerate; near-miss **property test**: queries whose primary cell differs from the stored key's cell recover through neighbor weight. **If measured locality is absent → STOP**, restate Claim A as "Engram with delta-rule cells" in the research note before any further phase.
- [ ] **T1.3** Bump weights: 3-tap per-axis LUT over the (now real) fractional coordinate, quantized 2⁸; outer-product combine; normalized `φ` (separable denominator); support exactly ±1 cell. Tests: LUT-vs-direct parity ≤ 1e-6; per-axis weights sum to 1; zero mass outside support.
- [ ] **T1.4** Delta-rule cell write `S ← S(I−βkkᵀ)+βkvᵀ` (closed-form rank-1, no GD), allocate-on-first-write, slab-only (zero per-write heap); **per-cell read-then-blend** (9 × d_k MACs each), never sum-then-read. Tests: overwrite removes-along-k (forgetting: old-value recall ≈ 0, new ≈ 1); interference bound after W near-collinear overwrites documented; counting-allocator proves 0 hot-path allocs.
- [ ] **T1.5** Grid sizer `LatticeMemory::sized(expected_items, collision_budget, byte_budget)`. ⚠ **Occupancy is NOT uniform**: E2LSH projections of real embeddings are roughly Gaussian, so with a fixed width `w` the central cells overload to `d_k` capacity long before the outer ones and the uniform Poisson law under-predicts collisions exactly where recall collapses. Fix at design time (cheaper than the histogram catch): map each axis through a **monotone Gaussian CDF** (fitted to the corpus's projected mean/spread) before quantizing — monotone ⇒ 1-D locality preserved, occupancy ≈ uniform — or state the sizing law with uneven occupancy built in. Byte budget: bytes/item = 4·d_k·d_v / occupancy; the constructor refuses configurations over the budget. Test: measured collision histogram matches the (CDF-corrected) prediction.
- [ ] **T1.6** Sigmoid-only scoring (`σ(λ·content-penalty)` for the routing/content factorization) — no softmax anywhere (grep gate); zero-alloc audit test.
- [ ] **T1.7** **GOAT bench** (next free bench slot; named `bench_408_family_lattice` or per numbering at implementation): (G1) recall@1 vs brute-force at 10⁴/10⁵/10⁶ items; (G2) read latency flat vs N (slope ≈ 0) vs PKM O(√N) vs Engram; (G3) overwrite/forgetting recall ≥ Engram on our key distributions; **(G5) near-miss recovery** — off-cell queries recover via neighbor weight, graded vs Engram's hash cliff (the Claim A differentiator, now gated directly); (G4) 0 hot-path allocs; (G6) **RSS-vs-N column** — flat latency must not hide linear memory growth; bytes/item reported. Floor: beat PKM on G2 at 10⁶ AND win G5 vs Engram AND stay under the T1.5 byte budget, else NOT promoted + negative recorded.
- [ ] **T1.8** Kernel A/B once: cos² vs tent bump (kernel shape is a tunable — cos² exists for SGD differentiability, which we don't have); pin the winner, demote the loser.

## Phase 2 — Cross-repo handoff

### Tasks

- [ ] **T2.1** Per-stack ledger entry: retrieval/memory slot — promote/demote vs PKM/Engram per T1.7; README feature row + `.docs/03_memory/` page.
- [ ] **T2.2** Consumer wiring (traj/insight evidence memory) is owned by riir-refine Plan 199 Phase 2 — no healer code in this repo; GOAT-gate results cross-referenced there.

## Guardrails

- Opt-in feature until every gate passes; `--no-default-features` and `--all-features` postures compile clean.
- Leaf-clean: zero new deps. The seeded projection + seed logic moves DOWN into katgpt-core (shared module) with `katgpt-pruners/lsh_cache` re-exporting it — the dep direction (pruners → core) already exists, so no cycle and no second copy; if the move-down is refused for another reason, that refusal is recorded here before any re-implementation is considered.
- Gate against OUR baselines (C4); the paper's numbers are external anchors, never adoption bars.
