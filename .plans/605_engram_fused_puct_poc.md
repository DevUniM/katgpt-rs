# Plan 605 — Engram-Fused PUCT Arena POC (Issue 868)

**Status:** COMPLETE 2026-09-22 — G5 verdict **FAIL (negative result recorded, Bench 848)**; feature stays opt-in; landed with the fused-player + miner + arena + gates.

Issue: `.issues/868_engram_fused_puct_arena_poc.md` · Proposal: `.proposals/013_engram_fused_puct_memory_augmented_moka_search.md`
Substrates (consume, never re-implement): `katgpt-core/src/engram/` (Plan 299 GOAT — `multi_head_hash`, `EngramTableBuilder`, `InMemoryEngramTable`, `build_merkle_root`) × `katgpt-moka-wasm/src/puct.rs` (Issues 204/206/207).

## Design (decided up front, from the issue's constraints)

- **Key**: TT discipline `(board, ko_point, to_play)` packed into 4 `u64` words (81 cells × 2 bits → 3 words; ko+to_play → 4th). The N-gram machinery is the hash family only — never a move-n-gram key (GHI hazard).
- **One `lookup_into` per expansion**, keyed on the expanded node's OWN state (cost-bounded: 82 per-child lookups would blow the G2 < 100 ns/expansion gate). Rows `[v̄, n, b]`, D=3.
- **Q-init** (OUR delta, not M-MCTS's decaying blend): at `expand(L)`, if the read fires (`hits > 0`), `L.visits = 1; L.total_value = gate · v̄` (memory enters as ONE damped pseudo-visit; backprop then adds real search value — one-shot, no schedule).
- **Prior sharpening**: γ = `exp(2β(b − 0.5) · gate)`, β = ln 2 ⇒ γ ∈ [0.5, 2] — bounded by construction (the issue's unbounded-`exp` hazard). γ scales the child-softmax logits inside `expand_with_policy_value`; the top-k sort is order-preserving under γ > 0 so it is untouched.
- **Evidence gate**: `sigmoid((n − n_min)/τ_n)`, pinned `n_min = 8`, `τ_n = 4` (n=1 → 0.18 "rumor", n=8 → 0.5, n≥24 → ≥0.92). `hits == 0` hard-skips everything (G1).
- **Native-gated**: every fusion site is `#[cfg(all(feature = "engram_puct", not(target_arch = "wasm32")))]` at item/call granularity — the feature-off compile is source-identical to pre-landing, so the T2.1 strong form (byte-identical wasm artifact) is attainable. Feature `engram_puct = ["dep:katgpt-core", "katgpt-core/engram"]` (katgpt-core optional, `default-features = false`). Batched (K>1) + engram: OUT of POC scope (the int8-at-K>1 precedent) — `with_engram` forces K=1.
- **Leakage controls** (T3.2): mining seeds and eval seeds are disjoint sets; fused-vs-GREEDY + unfused-vs-GREEDY on identical seeds as the independent-opponent arm.
- **G5 power fix** (T3.3): PASS = one-sided 95% Wilson lower bound > 50% at n ≈ 616 (paired, 2 games/seed); Clopper–Pearson exact lower bound reported as the conservative secondary. Budget arm (fused b25 vs unfused b50 ≈ 50%) reported descriptively.

## Tasks

- [x] T0 Pre-landing wasm artifact snapshot (raw release .wasm, sha256 + size) for the T2.1 byte-identity check; `cargo tree --target wasm32-unknown-unknown` shows no katgpt-core at default features.
- [x] T1 Phase 1 — offline miner (`examples/engram_miner.rs`, required-features `engram_puct`): N b50 self-play games; per-exact-key `(Σoutcome, count, Σconcentration)` accumulation (concentration from the root visit distribution via a new read-only `PuctPlayer::root_visit_counts`); deterministic key-sorted table build (G6) via `EngramTableBuilder` (16 heads × `add_pattern`); table file (magic + n_slots + d + heads + slots + BLAKE3 root, loader verifies root); T1.3 sanity gates — hit-rate curve vs table size {2¹⁶, 2¹⁸, 2²⁰}, count distribution, collision audit.
- [x] T2 Phase 2 — fused player: `src/engram_fuse.rs` (TT packing, `EngramPuctMemory::read` → `(v̄, gate, γ)`, file IO, gate/sharpen math); cfg-gated field + `with_engram` + fusion calls in `expand`/`expand_with_policy_value`; T2.1 assertions — post-landing wasm artifact byte-identical to T0 snapshot (strong form), `cargo tree` unchanged.
- [x] T2-gates G1/G4/G6 tests (`tests/engram_puct_gates.rs`): G1 empty-table ⇒ bit-identical moves vs feature-off player (40 fixed positions + 2 full games); G4 counting-allocator delta (fused vs unfused expansions) == 0; G6 deterministic miner (same seeds → same commitment) + file round-trip; γ-bounds + gate-monotonicity unit arms.
- [x] T3 Phase 3 — arena (`examples/engram_puct_arena.rs`): T3.1 paired head-to-head driver (each seed, both arms, both colours); T3.2 leakage arms (disjoint seeds; fused-vs-GREEDY vs unfused-vs-GREEDY same seeds); G2 measured lookup ns (direct read timing, interleaved best-of-arms); T3.3 G5 verdict (Wilson/CP lower bounds, draws counted, verdict + exit code).
- [x] T3-verdict Run the arena at n=616, record PASS/FAIL either way. **VERDICT: FAIL — 296/616 = 48.1%, Wilson one-sided 95% lower 44.8% < 50%; budget arm 35.7%; vs-GREEDY delta −4.0pp (ns); G2 293 ns > 100 ns bar. Diagnosis (T1.3): mechanism fired at 98.4% of lookups but the count-based evidence gate damped 99.98% of rows to ≤0.18 — 9×9 self-play transpositions are too rare (100% of positions n<4) to accumulate evidence.** Bench record `.benchmarks/848_engram_puct_arena_g5.md`.
- [x] T4 Record the verdict on Issue 868 + Proposal 013 status line; close issue (remove per noise-reduction; record in HISTORY.md); commit + push.
- [x] Validation: `cargo clippy -p katgpt-moka-wasm --all-targets` (default + `--features engram_puct` + `--all-features` + `--no-default-features`) clean; `cargo test -p katgpt-moka-wasm --features engram_puct` green (24 lib + 5 gates); wasm32 default artifact size-identical + tree clean; wasm32 `--all-features` compiles; docs gate run locally.

## Honest caveats carried into the verdict (from the issue)

1. Go is (nearly) Markovian; hard-hash routing has no neighbourhood — the M-MCTS win mechanism (kernel regression over neighbouring states) is absent by construction. Prior points at FAIL; the gate decides.
2. Collision dilution is real: count-based gate handles under-evidence, not contamination. The T1.3 collision audit quantifies it; G5 pays for it if it dominates.
3. Superko approximation (simple ko only) — documented, key never silently widened.
4. Table staleness by design (frozen, one distribution) — fine for the POC.
