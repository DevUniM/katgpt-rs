# Plan 607 — Modelless game-decision lane (the laya game arenas)

**Status:** PROPOSED — owner gates RULED by verdict ping-pong round 2
(both applied below); owner read before PROPOSED → ACCEPTED.
- Lane priority: **co-developed ordering** (T0a → T4a → T0b → T1+T4 →
  first GOAT reading → T5 → {T2,T3} evidence-gated → T6 → T7).
- T2 Gate A: **approved in principle, build deferred, lapses on the first
  GOAT reading** (the lapse condition is IN T2's row — R5).

katgpt-rs Plan 607 (qualified everywhere — riir-ai `.plans/.highwater` is
ALSO 607; a bare "Plan 607" is the misattribution class). Spawned by the
owner prompt 2026-09-22 after https://brainfunctioncollapse.com/laya demoed
THREE games (Flappy Bird, three-lanes, Tetris) played via templated English
state sentences + one typed question. Verdict ping-pong round 1 = REVISE
(lane split moved to this repo, owner gate B dropped, T2 provenance fixed,
flag renamed off "game", citations repointed); **round 2 = REVISE, R1–R6
applied**: T0 split around the arena (R1 — the fixture needs the state
enumerator + renderer FIRST, and the local laya forward makes per-decision
oracles generatable, so the aggregate-degradation clause is deleted);
discrimination-floor + constant-pick/chance baselines in T1's G1 (R2); G2
restated per decision SET with the option count printed + the hot path
decided centroid-cosine-only (R3 — the old `10 µs/decision` was 6× TIGHTER
than the 0.06 ms floor it cited as headroom); T1 signature generic + T5 a
precondition for any default-on consideration (R4); T2 lapse condition (R5);
the feature-boundary fairness argument scoping T2 (R6). Round-2 AGREE
residuals also applied: the headline latency claim restated per decision
SET (with the T6 matched-units precondition) and the T1 determinism row
names the corpus centroid table.

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
p99 59–79 µs per decision SET — ~20 questions answered in one call; the
0.06–0.5 ms figure is the per-SET spread across the family suites — vs
laya 21–4500 ms per forward, ONE decision per forward. The per-question
ratio spans roughly 10³–10⁵×, and **T6 must restate it at matched units
(per-question vs per-decision) before any number is quoted** — never a
per-set figure wearing a per-decision label. Zero model weights vs
650 MB + 2.3 GB download; deterministic; no GPU. Winning the game domain
is expected on latency/deployment by construction, and on accuracy by
protocol choice — the plan's job is to PROVE it with a measured GOAT
gate, not assert it.

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

## Execution order (verdict round 2, R1)

T0a → T4a → T0b → T1 + T4 (co-developed) → first GOAT reading →
T5 → {T2, T3} evidence-gated → T6 → T7. **The fixture cannot precede the
arena**: trace generation needs the state enumerator + renderer first, and
per-decision laya outputs are generatable LOCALLY (riir-reflex's G5-parity
`RiirAgent` lane), so the oracle is a real trace, never published aggregates.

## Tasks

- [ ] **T0a — substrate-first gate** (before any code): grep + read
  `decision_wire`, `compression_drafter` (Lz4FlexDrafter),
  `variable_rank_domain_expert` (`pick_domain`), `rating` (Elo/Beta-LCB),
  `CorpusDistanceGate`, and `katgpt-attn-match`'s `beta_fitter.rs` /
  `value_fitter.rs` (closed-form-LS-warm-started NNLS fitting — shipped
  precedent). Consume; never re-implement. Any T1/T2/T3 piece these cover
  is a forward, not new code.
- [ ] **T4a — the state enumerator + laya-format renderer** (katgpt-rs
  `examples/`, the arena's first half): enumerates Tetris states (board +
  piece + the ~34 landing options) and renders the laya-protocol English
  sentence for each — closed grammar, WHERE-form questions, no numbers in
  prose (arithmetic stays in code; their own wording-sensitivity trap is
  why the grammar is pinned). Dumps (sentence, structured_state) pairs to
  disk. Both the fixture (T0b) and the arena (T4) consume this; nothing
  downstream of it can exist first.
- [ ] **T0b — the G1-oracle fixture** (generated in riir-reflex, committed
  INTO katgpt-rs with its provenance sha — the `katgpt-device-verify` rule:
  copying code across the seam creates drift, copying the fixture detects
  it): run riir-reflex's LOCAL laya forward (`laya::riir::RiirAgent`, the
  G5-parity lane: top-1 1.000, drift ≤ 3.1e-6, no skip path) over the T4a
  dump → commit (sentence, structured_state, decision) **TRIPLES**.
  R1: the old "if only aggregates are available, G1 DEGRADES to outcome
  parity" clause is DELETED — per-decision outputs are generatable locally
  (the laya forward is in-tree, not a published API), so that constraint
  does not exist. The real degradation trigger is OPERATIONAL — laya
  weights absent on the generating box — and then fixture generation
  BLOCKS; it never quietly relabels the gate.
- [ ] **T1 — the option-scoring primitive, minimal + generic** (katgpt-core,
  opt-in feature `state_option_scoring` — named for the CAPABILITY, never
  "game"): v1 signature takes `(state vector, option feature matrix)` with
  the option count bounded/const-generic and **nothing Tetris-specific in
  the signature** (R4 — a public upstream surface may not be shaped by one
  arena); surface scoped to what T4 exercises, widened only when T5 lands.
  **Design decision (R3): the hot path is centroid-cosine scoring ONLY —
  the compression drafter is OUT of the per-decision loop** (drafter deltas,
  if used at all, are a precomputed axis); decided HERE, never a number
  relaxed at T6.
  **GOAT gate:** G1 = decision agreement vs the T0b triples AND vs a
  **constant-pick baseline** AND vs chance — never vs laya alone (R2:
  reflex T7 measured 4-of-5 families constant-picking — a short option
  encoding never moves a long shared context's compressed length, and
  class-balanced fixtures made "exactly chance" indistinguishable from
  "constant pick"; Tetris is the same shape at ~34 options); plus the
  **discrimination floor** = distinct picks ≥ 2 over distinct state vectors
  (reflex's shipped floor); G2 = **p99 ≤ 1 ms per decision SET with the
  OPTION COUNT printed beside it** (the sibling's shipped bar form —
  measured 59–79 µs at ~20 options; a latency bar without its option
  count is the box-state defect class); G3 = count-pinned no-regression;
  G4 = alloc-free with canary; **determinism row** = same corpus →
  bit-identical scoring state — at T1 that is the corpus CENTROID TABLE
  (the fitted head is T3 and deferred; this row must not read as asserting
  something T1 does not build) — two runs, two boxes.
- [ ] **T4 — the Tetris arena** (`examples/` + `.benchmarks/`, bomber
  precedent): code computes the features (holes, bumpiness, stack height,
  line clears — Dellacherie-class, solved engineering); T1 scores every
  landing spot; the piece goes to argmax. **First GOAT reading** = replay
  the T0b fixture + bench latency + lines-cleared against their published
  numbers. The reading gates {T2, T3}.
- [ ] **T5 — Flappy + three-lanes micro-arenas**: same shape, STATE
  question form (where is it, never what to do — laya's own lesson).
  **T5 is a PRECONDITION for even considering default-on promotion of the
  T1 flag** (R4 — one arena cannot promote a flag).
- [ ] **T2 — bounded template decode** (katgpt-core, feature-gated).
  **OWNER GATE A — APPROVED IN PRINCIPLE (verdict round 2), build DEFERRED
  until after T4's first GOAT reading; the approval LAPSES if that reading
  shows decode buys neither agreement nor a second consumer — re-approval
  is then required** (R5 — an approval without a reopen condition is a
  permanent half-state that gets cashed against evidence that has moved).
  Grammar→slot decoder for CLOSED sentence grammars (the laya-protocol
  state sentences). **The fairness argument that scopes it (R6):** in
  laya's own protocol the game code computes the features and renders
  English ONLY because BERT cannot read numbers — the sentence is laya's
  input requirement, NOT the task's; rendering is pure loss over state the
  code already holds. Our lane reading the structured state is the honest
  architecture, and the head-to-head belongs at the FEATURE boundary. T2
  therefore has exactly two jobs: (a) the **losslessness measurement arm**
  — decode the T0b sentences and score sentence-arm vs structured-arm,
  reported as an AGREEMENT DELTA where a non-zero delta is a finding about
  the RENDER, not automatically a decode bug; (b) **third-party
  laya-format traffic intake** — the only durable consumer justification.
  Provenance per Proposal 014 §Fusion: **Lz4FlexDrafter lineage** (pattern;
  `quest_grammar` is riir-ai's wrapper and is never a dep). Decode-only,
  corpus-limited. Run substrate-first on T0a findings before writing.
- [ ] **T3 — the corpus-fitted head, determinism-constrained** (NOT an
  owner gate — closed-form/NNLS corpus fitting is admitted precedent in
  THIS repo: `katgpt-attn-match/src/beta_fitter.rs` warm-starts projected
  gradient from a clamped closed-form LS solution, in the public
  modelless repo): closed-form/NNLS-class fit over frozen features as the
  "80–90% corpus-viable" lever the owner hypothesized — **built only after
  T4's first GOAT reading shows plain corpus scoring falling short of
  agreement** (evidence-gated, same reading that gates T2). The line to
  hold is **determinism, not closed-form-ness**: fixed iteration count, no
  RNG, no gradient descent on base weights, head reconstructible from the
  corpus alone (bit-identical two boxes — asserted in the GOAT, a G1 row).
  Calibration point: jimothy's TF-IDF 82% on banking77 — a TRAINED
  baseline, cited as the bar to beat modellessly, never as a method to
  adopt.
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
