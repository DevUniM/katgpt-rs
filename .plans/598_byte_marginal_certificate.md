# Plan 598: Byte Marginal + Terminal-Mass Certificate Primitive

**Date:** 2026-09-15
**Status:** COMPLETE 2026-09-16 — T1–T8 landed (Bench 770: G2 FAIL honest → stays opt-in, no promotion); T9/T10 `- [-]` deferred per plan

> Source: Research 559 (arXiv:2609.12303). GOAT-tier modelless primitive: single-pass
> token→byte distribution conversion with a closed-form terminal-mass error certificate.
> Substrate-first check done (Research 559 §3): nothing ships; `katgpt-tokenizer` BPE
> decode provides the vocab→bytes table; `katgpt-core` is the leaf home for the generic
> refinement-tree math (no game/chain semantics — public per commercial strategy).

---

## Phase 1 — Generic math (katgpt-core, feature `refinement_marginal`)

- [x] T1: `crates/katgpt-core/src/refinement_marginal.rs` behind `refinement_marginal = []`:
      `RefinementTable` (symbol→child-symbol trie rows, built once per checkpoint), and
      `coarse_grain(probs, table, realized_prefix) -> CoarseRecord` where `CoarseRecord`
      = 257-bin (256 symbols + terminal) fixed-size array + `terminal_mass M_k`.
      Zero-alloc (caller-provided scratch), branch-free inner scatter-add, chunked lanes.
      LANDED 2026-09-16 — as `coarse_grain_first`/`coarse_grain_step` streaming frontier
      (the per-call-rescan signature is O(vocab × prefix) per byte; the frontier form is
      one pass over the flattened table worst case — same 257-bin record, same zero-alloc
      contract, and the caller's loop variable replaces the `realized_prefix` re-scan).
      Chunked lanes: NOT taken — the scatter is a variable-offset gather (the G2 finding;
      chunking cannot fix the access pattern). [Bench 770](../.benchmarks/770_refinement_marginal_goat.md)
- [x] T2: certificate arithmetic: `error_bound(record) -> f32` (TV ≤ M/(1−M) worst case)
      + `expected_escalation_cost = Σ_k M_k`; sigmoid gate helper (never softmax).
      LANDED 2026-09-16 (+ derivation proving the bound over-reports by construction).
- [x] T3: unit tests: (a) first-symbol marginal exact vs brute-force over vocab;
      (b) 257-bin round-trip reconstructs token-space marginals (KL=0 to fp tolerance);
      (c) certificate never under-reports on adversarial fixtures (terminal-heavy vocabs);
      (d) all-terminal vocab (every symbol length 1) → certificate ≡ 0, conversion exact.
      5/5 PASS 2026-09-16 (a–d + escalation helpers).

## Phase 2 — Tokenizer instantiation (katgpt-tokenizer)

- [x] T4: bridge `katgpt-tokenizer`: build `RefinementTable` from `BpeTokenizerImpl` vocab
      (token→bytes via existing decode; cache beside model like the tokenizer itself).
      Offline `tokenizer_geometry` profile: E[len], trie breadth/depth, dead-prefix mass.
      LANDED 2026-09-16 — home is the ROOT crate (`katgpt_rs::refinement_bridge`):
      katgpt-tokenizer is a categorical leaf (no katgpt-* deps) and the bridge needs
      both crates; feature-forward `refinement_marginal = ["katgpt-core/refinement_marginal"]`.
- [x] T5: integration test on a real GGUF vocab: byte marginal vs two-pass reference
      conversion on sampled prompts; measured TV vs certificate bound (bound must hold 100%).
      LANDED 2026-09-16 with a RECORDED DEVIATION: real trained-BPE vocab (in-tree
      deterministic `BpeTrainer` over a real corpus) instead of GGUF — katgpt-tokenizer
      ships no GGUF reader and the leaf constraint blocks adding one; 98 cells, bound
      held 100% (min slack +8.4e-5). `tests/refinement_marginal_tokenizer_bridge.rs`.

## Phase 3 — GOAT gate + bench

- [x] T6: `cargo bench` — µs overhead of coarse_grain on top of the already-paid softmax
      (target <5%); table build <1s per 100K vocab; zero allocs asserted (`#[cfg(alloc_tracking)]`).
      MEASURED 2026-09-16 — [Bench 770](../.benchmarks/770_refinement_marginal_goat.md):
      full loop 2.63–2.83× softmax, depth-0 alone 1.97–1.98× (the gather defeats the
      sequential-exp sweep — the <5% premise is REFUTED); table build 1.4 ms @ 131K (bar
      passes ~700×); 0 steady-state allocs (release + alloc_tracking).
- [x] T7: GOAT verdict G1–G4 (G1 = T3+T5 green; G2 = T6; G3 = no regression on existing
      tokenizer benches; G4 = alloc-free). All pass → promote `refinement_marginal` to
      default; else stay opt-in with recorded numbers.
      VERDICT 2026-09-16: G1 PASS / G2 **FAIL (honest)** / G3 PASS (scoped: default suites
      2060 + 203 unchanged; clippy −D clean at the feature state; one PRE-EXISTING slt.rs
      all-targets lint at HEAD reported to its lane) / G4 PASS → **stays OPT-IN, no
      promotion, no consumer wiring**. [Bench 770](../.benchmarks/770_refinement_marginal_goat.md)
- [x] T8: docs — crate README row + `.docs/` entry citing Research 559; update
      `.research/559` Status → Done with commit hash.
      LANDED 2026-09-16 (same commit as the code: README opt-in table row,
      `.docs/09_feature_catalog/` opt-in entry, R559 status delta, this plan, Bench 770).

## Phase 4 — Deferred (file as issues if audit fires; `- [-]` per discipline)

- [-] T9: certificate-gated batched-exact escalation (boundary crossings batched into ONE
      extra forward pass) — needs a serving consumer first.
- [-] T10: DDTree/verifier path-scoring terminal-bin audit (absorbing-symbol law applied
      to our own variable-depth scorers) — separate concern, audit before any fix.
- [-] T11: cross-tokenizer byte-space interchange (vs OmniDraft/vLLM token-intersection)
      — capability published; only pursue with a concrete heterogeneous draft/target need.
