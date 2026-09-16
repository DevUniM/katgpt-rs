# Bench 770: refinement_marginal GOAT gate — single-pass token→byte marginal with terminal-mass certificate (Plan 598 / Research 559)

**Status:** RECORD — **G1 + G3 + G4 PASS, G2 FAIL (honest) → `refinement_marginal`
stays OPT-IN, no promotion, no consumer wiring.** Measured 2026-09-16, M3 Max,
release profile.

Provenance: Plan 598 (T6/T7) — the byte-marginal + terminal-mass certificate
primitive from Research 559 (arXiv:2609.12303, Marginalize-It family). The
premise under test: the conversion is a "thin scatter-add on top of the
already-paid softmax" (plan T6 bar: <5% of softmax cost).

## What shipped (`f`eat landing, same commit as this record)

- `katgpt-core::refinement_marginal` (feature `refinement_marginal = []`,
  OPT-IN): `RefinementTable` (flat symbol→child-symbol sequences, `byte_at`
  O(1)), `CoarseRecord` (257-bin = 256 byte bins + [`TERMINAL_BIN`]), the
  streaming frontier conversion (`coarse_grain_first` exact depth-0 +
  `coarse_grain_step` conditional per realized byte, caller-owned
  `CoarseGrainScratch`, zero per-step alloc), `error_bound` (TV ≤ M/(1−M),
  over-reports by construction — derivation in the module doc),
  `expected_escalation_cost` (Σ_k M_k), `escalation_sigmoid` (never softmax).
- `katgpt_rs::refinement_bridge` (root crate, same-named feature forward):
  the BPE instantiation — `refinement_table_from_bpe` +
  `tokenizer_geometry` (E[len], max-len, per-depth distinct-byte breadth via
  256-bit bitmaps, dead-prefix mass) + `decode_argmax` (terminal-aware).
  Root-crate home recorded: `katgpt-tokenizer` is a categorical leaf
  (no `katgpt-*` deps), the bridge needs both crates.
- T5 deviation (recorded in the test header): "real GGUF vocab" replaced by
  a real-corpus-trained BPE vocab (`BpeTrainer`, deterministic) —
  katgpt-tokenizer ships no GGUF reader and adding one violates the leaf.

## The measurement (G2)

| vocab | softmax ns | full loop ns (8 steps) | × | depth-0 alone ns | × | table ms |
|---|---|---|---|---|---|---|
| 2,048 | 1,750 | 4,958 | 2.83× | 3,459 | 1.98× | 0.0 |
| 32,768 | 29,667 | 78,042 | 2.63× | 58,583 | 1.97× | 0.3 |
| 131,072 | 118,709 | 311,959 | 2.63× | 233,292 | 1.97× | 1.4 |

Median of 51 after 7 warmups, `std::time::Instant` (repo bench convention),
two independent runs stable (second run in the bench output, ±3%).

**G2 verdict: FAIL — the <5% bar is missed by ~53×, and the failure is
structural, not tunable.** Depth-0 alone is ~2× softmax at every vocab size:
softmax is a sequential exp sweep (vectorizable, one pointer), the marginal
is a per-symbol GATHER (`child[cursor[s] + k]` — variable offset, random
access) that defeats both prefetch and auto-vectorization. The 8-step loop
adds ~35% over depth-0 (the frontier shrinks geometrically on real vocab
shape; the synthetic random-byte vocab here is near-worst-case for sharing
and near-best-case for frontier collapse — the ratio is stable across both
runs). No restructure under consideration removes the gather without
re-staging the whole table per depth (a 256-way scatter transpose — more
memory traffic than the gather it replaces at byte-domain width 256).

## What DID pass

- **G1**: 5/5 core unit tests — depth-0 exact vs independent brute force;
  streaming ≡ independent full-rescan reference along a realized path (KL=0
  fp); certificate never under-reports on adversarial terminal-heavy
  fixtures (concentrated-dropped-mass TV measured ≤ M ≤ bound); all-terminal
  vocab (certificate ≡ 0 at depth 0, vacuous-cell 1.0 at the boundary,
  clean empty record after); escalation cost + sigmoid gate monotonicity.
  T5 integration: 98 (prompt, depth) cells over a real trained BPE vocab —
  streaming matches the reference per bin (1e-4), alive mass reconstructs
  the prefix-matched token mass, **bound held 100%** (min slack +8.4e-5).
- **G3**: default suites unchanged (katgpt-core 2060 / katgpt-rs 203);
  clippy `-D warnings` clean on both crates at `--features
  refinement_marginal` (lib + tests). One PRE-EXISTING clippy error at HEAD
  (`slt.rs:1388` `field_assignment_outside_of_initializer`, landed
  `7352a75ab`, fires only under `--all-targets` on the test target) — not
  this change's surface, reported to the owning lane.
- **G4**: 0 steady-state allocs across the streaming loop (release +
  `alloc_tracking`); table build 1.4 ms @ 131K vocab — the 1 s/100K bar
  passes by ~700×.

## Consequences (per the plan's own promotion rule)

- `refinement_marginal` ships **opt-in**, never promoted; no serving/
  spec-decode consumer wired.
- The certificate machinery itself is CORRECT and cheap (G4's alloc-free
  loop, per-step cost tiny after frontier collapse) — the wall is the
  depth-0 gather. Revisit only if a consumer needs the byte marginal where
  (a) the vocab's first-byte distribution is all it consumes (depth-0
  replaces a full byte-level softmax — 1.97× a token softmax but delivers
  256-byte output the token softmax cannot), or (b) an ISA-guaranteed
  gather (explicit SIMD) is independently justified.
- The terminal-mass certificate law (R559's uncovered delta) is validated
  on-stack: the bound never under-reported in 98 adversarial cells. That
  finding survives the G2 fail — any future exact-conversion lane (the
  certificate-gated escalation of R559 §2.3) inherits a proven bound.

Landing: this commit (Plan 598 T1–T8; T9/T10 remain `- [-]` deferred per
the plan).
