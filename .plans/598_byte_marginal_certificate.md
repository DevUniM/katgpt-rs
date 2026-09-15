# Plan 598: Byte Marginal + Terminal-Mass Certificate Primitive

**Date:** 2026-09-15
**Status:** In flight — T1 not started (filed from Research 559)

> Source: Research 559 (arXiv:2609.12303). GOAT-tier modelless primitive: single-pass
> token→byte distribution conversion with a closed-form terminal-mass error certificate.
> Substrate-first check done (Research 559 §3): nothing ships; `katgpt-tokenizer` BPE
> decode provides the vocab→bytes table; `katgpt-core` is the leaf home for the generic
> refinement-tree math (no game/chain semantics — public per commercial strategy).

---

## Phase 1 — Generic math (katgpt-core, feature `refinement_marginal`)

- [ ] T1: `crates/katgpt-core/src/refinement_marginal.rs` behind `refinement_marginal = []`:
      `RefinementTable` (symbol→child-symbol trie rows, built once per checkpoint), and
      `coarse_grain(probs, table, realized_prefix) -> CoarseRecord` where `CoarseRecord`
      = 257-bin (256 symbols + terminal) fixed-size array + `terminal_mass M_k`.
      Zero-alloc (caller-provided scratch), branch-free inner scatter-add, chunked lanes.
- [ ] T2: certificate arithmetic: `error_bound(record) -> f32` (TV ≤ M/(1−M) worst case)
      + `expected_escalation_cost = Σ_k M_k`; sigmoid gate helper (never softmax).
- [ ] T3: unit tests: (a) first-symbol marginal exact vs brute-force over vocab;
      (b) 257-bin round-trip reconstructs token-space marginals (KL=0 to fp tolerance);
      (c) certificate never under-reports on adversarial fixtures (terminal-heavy vocabs);
      (d) all-terminal vocab (every symbol length 1) → certificate ≡ 0, conversion exact.

## Phase 2 — Tokenizer instantiation (katgpt-tokenizer)

- [ ] T4: bridge `katgpt-tokenizer`: build `RefinementTable` from `BpeTokenizerImpl` vocab
      (token→bytes via existing decode; cache beside model like the tokenizer itself).
      Offline `tokenizer_geometry` profile: E[len], trie breadth/depth, dead-prefix mass.
- [ ] T5: integration test on a real GGUF vocab: byte marginal vs two-pass reference
      conversion on sampled prompts; measured TV vs certificate bound (bound must hold 100%).

## Phase 3 — GOAT gate + bench

- [ ] T6: `cargo bench` — µs overhead of coarse_grain on top of the already-paid softmax
      (target <5%); table build <1s per 100K vocab; zero allocs asserted (`#[cfg(alloc_tracking)]`).
- [ ] T7: GOAT verdict G1–G4 (G1 = T3+T5 green; G2 = T6; G3 = no regression on existing
      tokenizer benches; G4 = alloc-free). All pass → promote `refinement_marginal` to
      default; else stay opt-in with recorded numbers.
- [ ] T8: docs — crate README row + `.docs/` entry citing Research 559; update
      `.research/559` Status → Done with commit hash.

## Phase 4 — Deferred (file as issues if audit fires; `- [-]` per discipline)

- [-] T9: certificate-gated batched-exact escalation (boundary crossings batched into ONE
      extra forward pass) — needs a serving consumer first.
- [-] T10: DDTree/verifier path-scoring terminal-bin audit (absorbing-symbol law applied
      to our own variable-depth scorers) — separate concern, audit before any fix.
- [-] T11: cross-tokenizer byte-space interchange (vs OmniDraft/vLLM token-intersection)
      — capability published; only pursue with a concrete heterogeneous draft/target need.
