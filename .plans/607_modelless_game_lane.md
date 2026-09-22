# Plan 607 — Modelless game-decision lane (the laya game arenas)

**Status:** PROPOSED — owner review pending (lane priority + T2 public-surface gate A)

katgpt-rs Plan 607 (qualified everywhere — riir-ai `.plans/.highwater` is
ALSO 607; a bare "Plan 607" is the misattribution class). Spawned by the
owner prompt 2026-09-22 after https://brainfunctioncollapse.com/laya demoed
THREE games (Flappy Bird, three-lanes, Tetris) played via templated English
state sentences + one typed question. Verdict ping-pong round 1 = REVISE;
all revisions applied (lane split moved to this repo, owner gate B dropped,
T2 provenance fixed, flag renamed off "game", citations repointed).

## The thesis — why we should win the game domain

LayA's own page concedes the three facts that define its game protocol:

1. **It cannot read numbers** — "Do the arithmetic in code and hand Laya
   the conclusion in words."
2. **Action questions answer backwards** — it must be asked WHERE things
   are, never WHAT to do (their Flappy protocol: "The bird is a little
   below the gap" → P(below) > 0.5 → flap).
3. **Wording sensitivity is a measured trap** — "blocked by a barrier"
   separated lanes by 0.75, "blocked by a train" 0.45.

So laya's game protocol is: **code does the arithmetic → code renders a
templated English sentence → BERT reads it**. The sentences are
code-generated from a **closed grammar** — which is exactly the regime
where corpus-limited decode is lossless (the quest-grammar lesson, pattern
lineage only). Our modelless lane's headline weakness (0.04–0.48 on OOD
text suites, Plan 603 harness) is **irrelevant under this protocol**: the
input vocabulary is closed, and the model contributes only a
state→threshold read that a corpus-scored feature vector can match
without any text at all.

The numbers we already hold (Plan 603/606, reflex README): modelless
0.06–0.5 ms per decision vs laya 21–4500 ms (**10³–10⁵×**); zero model
weights vs 650 MB + 2.3 GB download; deterministic; no GPU. Winning the
game domain is expected on latency/deployment by construction, and on
accuracy by protocol choice — the plan's job is to PROVE it with a
measured GOAT gate, not assert it.

## Lane split (verdict round 1 — the correction that matters)

- **Arena + bench live HERE (katgpt-rs).** Precedent: the bomber/monopoly
  arenas are already chartered in `BOUNDARY.md` (the `bevy_ecs` row) as
  "GOAT evidence infrastructure … an evaluation harness with no riir dep,
  upstream of everything" (Bench 432, Bench 799). Tetris/Flappy/lanes are
  the same class. A riir-ai home would put the G1 oracle DOWNSTREAM of the
  primitive it gates — katgpt-rs cannot depend on riir-ai (dependency
  cycle), so the flag's own repo could never execute its gate
  (test_gate/full_gate/x86 matrix all blind). That is the green-zero shape
  one repo over.
- **riir-ai gets a consumer LINE, not the lane** — a separate later plan
  (its own riir-ai number) for when a shipped NPC actually consumes the
  primitive. `goal_salience`/swarm are NPC latent cognition in a game
  runtime, a different domain from a decision arena; T4 does not consume
  them.
- **riir-reflex stays game-free.** Its BOUNDARY.md domain test is explicit
  ("NOT game runtime"); Plan 603/606's scope stands. The arena book cites
  NUMBERS only.

## Tasks

- [ ] **T0 — substrate-first gate** (before any code): grep + read
  `decision_wire`, `compression_drafter` (Lz4FlexDrafter),
  `variable_rank_domain_expert` (`pick_domain`), `rating` (Elo/Beta-LCB),
  `CorpusDistanceGate`, and `katgpt-attn-match`'s `beta_fitter.rs` /
  `value_fitter.rs` (closed-form-LS-warm-started NNLS fitting — shipped
  precedent). Consume; never re-implement. Any T1/T2/T3 piece these cover
  is a forward, not new code. **G1-oracle fixture row:** decision
  agreement needs laya's PER-DECISION outputs (the published 1,799
  decisions/min / 52 lines are aggregates), and the laya forward lives in
  riir-reflex — DOWNSTREAM of katgpt-rs, so the gate cannot call it.
  Generate the trace ONCE in riir-reflex and commit it into katgpt-rs as a
  fixture with its provenance sha (the `katgpt-device-verify` rule:
  copying the code across the seam creates drift, copying the fixture
  detects it). If only aggregates turn out to be available, G1 DEGRADES
  from agreement to outcome parity and must be RELABELLED in the bench
  doc — never quietly measured.
- [ ] **T1 — the option-scoring primitive** (katgpt-core, opt-in feature
  `state_option_scoring` — named for the CAPABILITY, never "game"):
  bounded-option scoring over a structured state vector — per-option
  feature vector → corpus scoring (pick_domain centroid lineage +
  rating/Beta-LCB), zero-alloc hot path. **GOAT gate:** G1 = decision
  agreement vs laya's RECORDED protocol (their published decisions are the
  oracle — a decision-agreement measurement, not a text-understanding
  claim); G2 = p99 ≤ 10 µs/decision (`--release`; conservative vs our
  measured 0.06–0.5 ms lane); G3 = count-pinned no-regression; G4 =
  alloc-free with canary; **determinism row** = same corpus →
  bit-identical head, two runs, two boxes.
- [ ] **T2 — bounded template decode** (katgpt-core, feature-gated;
  **OWNER GATE A — the one gate kept**: this adds a new PUBLIC capability
  to the public repo, so the owner approves the surface): grammar→slot
  decoder for CLOSED sentence grammars (the laya-protocol state
  sentences), so the modelless lane can consume their protocol without
  BERT. Provenance per Proposal 014 §Fusion: **Lz4FlexDrafter lineage**
  (pattern; `quest_grammar` is riir-ai's wrapper and is never a dep).
  Decode-only, corpus-limited. Run substrate-first on T0 findings before
  writing.
- [ ] **T3 — the corpus-fitted head, determinism-constrained** (NOT an
  owner gate — closed-form/NNLS corpus fitting is admitted precedent in
  THIS repo: `katgpt-attn-match/src/beta_fitter.rs` warm-starts projected
  gradient from a clamped closed-form LS solution, in the public
  modelless repo): closed-form/NNLS-class fit over frozen features as the
  "80–90% corpus-viable" lever the owner hypothesized. The line to hold
  is **determinism, not closed-form-ness**: fixed iteration count, no
  RNG, no gradient descent on base weights, head reconstructible from the
  corpus alone (bit-identical two boxes — asserted in the GOAT, a G1 row).
  Calibration point: jimothy's TF-IDF 82% on banking77 — a TRAINED
  baseline, cited as the bar to beat modellessly, never as a method to
  adopt.
- [ ] **T4 — the Tetris arena** (`examples/` + `.benchmarks/`, bomber
  precedent): code computes the features (holes, bumpiness, stack height,
  line clears — Dellacherie-class, solved engineering); T1 scores every
  landing spot; the piece goes to argmax. **Replay laya's recorded
  protocol as the G1 oracle** (1,799 decisions/min, 52 lines, no top-out)
  and bench latency + lines-cleared against their published numbers.
- [ ] **T5 — Flappy + three-lanes micro-arenas**: same shape, STATE
  question form (where is it, never what to do — laya's own lesson).
- [ ] **T6 — bench doc + GOAT verdict**; the numbers become citable by
  the reflex arena book (numbers only; the reflex repo itself untouched).
- [ ] **T7 — doc-sync**: AGENTS.md feature-table rows for the new flags;
  arena book citation.
- [-] **PUCT/MCTS research note — DEFERRED** (verdict round 1): Dellacherie-class
  heuristics settle Tetris; PUCT over a modelless policy prior is
  modelless-legal (search is not learning) but low value-per-effort. File
  a `.research/` note only if T4's oracle replay shows the argmax scorer
  losing decisions to laya on multi-step lookahead.

## Boundary + provenance notes

- **Naming:** no "game" in any katgpt-core flag/type name — name the
  capability; "game" lives in the arenas (`examples/`), where this repo's
  charter already puts it (BOUNDARY.md `bevy_ecs` row).
- **Citation repair riding this plan's commit:** the "Proposal 017"
  counter-case cited by `.proposals/014` line 25 and
  `../riir-reflex/BOUNDARY.md` line 44 **never existed** (`.proposals`
  highwater = 014; no 017 on disk; none in history). Canonical record:
  **riir-ai Plan 484** (`../riir-ai/.plans/484_riir_games_domain_split_corrected.md`).
  Two commits by necessity (cross-repo repair rule — a record here claims
  nothing until the sibling commit exists): riir-reflex repointed at
  `3cbdca63df4141eaa214311afd37f6ce3c90e7ee` (committed FIRST); the
  katgpt-rs half (`.proposals/014` line 25) rides this plan's commit.
- **Numbering:** every mention qualified "katgpt-rs Plan 607" (riir-ai
  `.plans/.highwater` = 607 too). Allocation gate clean at write time
  (0 twin / 0 independent / 0 counter).
- **jimothy** (`github.com/AndrewPrifer/jimothy`) = adjacent, NOT our
  plan: per-task TRAINED classifier bundles (MiniLM/TF-IDF + teacher
  distill from Jev) with the SAME typed wire as our `decision_wire`
  (choice/boolean/noul/score). Validates the market direction; its
  per-task-bundle model is the opposite of our shared-engine stance.
- **laya rust-vs-python compare: already done** (Plan 603/606): G5 parity
  green both lanes (top-1 1.000, drift ≤ 3.1e-6); Bench 001 interleaved
  latency — torch MPS 30.3 ms ≈ candle Metal 31.1 ms (torch ~1.3–1.5×
  faster, kernel maturity), riir CPU 188.7 ms at candle-CPU parity; our
  wins are deployment (one SHA-pinned binary, no Python, no torch,
  offline).
