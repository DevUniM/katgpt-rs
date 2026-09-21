# Proposal 014 — KatGPT Decisions: the open decision-engine comparison arena + the `riir-jev` serving repo

Status: **draft**
Branch: `develop` (per global rule — no feature branches)
Owner: unassigned
Fusion of: Research 562 × 573 × 574 × 576 + Issue 810/Bench 808 + Issue 859/Bench 816–817 + riir-clippy Issues 125/126 + the quest_grammar drafter pattern + the KAT contribution network (riir-kat + riir-dapps + riir-clippy)
Related: [Research 576](../.research/576_Laya_Open_Jev_Generalist_RLCD_Comparison_Arena.md) (the source distill this proposal consumes), [Research 562](../.research/562_Typesafe_SystemOne_Jev_Calibrated_Decisions.md), [Research 573](../.research/573_CUA_S1_Open_Jev_Recipe_Specialist_Option_Scorer.md), [Research 574](../.research/574_Jev_Structured_Reads_DiffusionGemma_vLLM_57250.md), [Research 322](../.research/322_Conformal_Seasonal_Pools_Calibrated_UQ_Overlay.md) (Report-the-Floor)

## TL;DR

Ship the **KatGPT decision engine + benchmark harness** (new private repo `riir-jev`, riir-clippy-shaped): a localhost serving binary over the landed substrate — modelless heads, `SigmoidGateCalibrator`-calibrated bridges, `structured_read` — benchmarked head-to-head against the Laya family and TypeSafe Jev in four lanes (byte-identical questions): (1) **KatGPT latent** (in-process), (2) **Laya latent** (their Apache-2.0 checkpoints loaded locally on the same machine), (3) **Jev API** via the *visitor's own* key (browser-side; we never pay anyone), (4) **KatGPT API** (the same engine behind localhost HTTP — apples-to-apples API-vs-API). Phase 1 is the primary deliverable and needs no marketing call: it alone discharges `structured_reads`' recorded promotion trigger ("when a consumer appears") and builds the **corpus flywheel's intake** — consent-gated decision outcomes flowing through the existing KAT contribution network, growing the labeled corpus that riir-clippy Issue 125's *measured* reopen trigger (10⁴–10⁵ contexts) demands; at threshold the specialist retrains (RLCD recipe — now published via laya, Research 576 §3), freeze/thaws as a BLAKE3 vessel, and ships as a selectable per-domain engine profile. The **public arena site** (dark-red rust theme — explicitly not laya's yellow; KatGPT branding) is Phase 2, the *wrapper* — gated on the owner's marketing call (publish per-task losses: recommended). The substrate race is already won and landed (562's arena scoreboard: 11W/2L/2SPLIT; Benches 808/816/817); the missing pieces are the consumer, the corpus engine, and the surface. This is a katgpt-rs + new-repo product proposal distilling a public competitor set, not a new research claim.

## The problem this solves

- **We hold the strongest calibrated-decision substrate in any workspace and zero public surface proving it.** laya's arena converts "open weights + measured benchmark + agent skill" into 5.3k GitHub stars; TypeSafe has marketing; we have research notes nobody outside the workspace can run. The 562 addendum's scoreboard (what they cannot enter at any price: 20 Hz, determinism, sync-path) is invisible to everyone but us.
- **`structured_read` is evidence-banked opt-in whose own landing note (574 §9) says promotion is "one line when a consumer appears"** — no consumer exists. The engine below is that consumer.
- **Issue 125's specialist was REFUTED at ~101 labeled contexts with a measured reopen at 10⁴–10⁵** — and no corpus-growth engine is running for decision tasks. riir-clippy built exactly this loop for code fixes (mine → contribute → settle → corpus → healer improves, all on-chain); nothing carries it for decisions.
- The public-brand posture is already settled strategy (Research 003): *what* = public katgpt-rs primitives; *how* = private riir-*; game code hidden. The arena is the public *what*; `riir-jev` is a private *how* that touches no game domain.

## The proposed design

### Branding + repo layout

- **Public brand: KatGPT** (the established public funnel name). Theme: **dark red rust** (`#B7410E`/`#7C1D05` family) — the user's explicit color call; no yellow anywhere. All site content original; the *arena shape* (playground + measured benchmark + agent-skill download) is replicated as an unprotectable concept, with zero prose/games copied from brainfunctioncollapse. Disclaimers: "not affiliated with or endorsed by TypeSafe AI; Jev is their product, named only to compare" (the laya-site idiom) + Apache-2.0 attribution for the laya checkpoints the arena loads.
- **New private repo `riir-jev`** — decision-engine serving + benchmark harness + contribution client. riir-clippy-shaped boundaries: `katgpt-core` non-optional; `katgpt-forward` under the `structured_reads` root forward (the promotion consumer); `riir-kat` for the contribution wire (the `--mine`/`--sync`/`--stats` client precedent); optional `riir-rag` for corpus-distance abstain (Research 576 §2.1's extraction). **Zero game deps** — BOUNDARY.md domain test: "decision-engine serving + comparison + contribution; NOT game runtime, NOT code healing." The 22-file workspace registration (repo_set.txt + boundary gates + floors) lands as its own dedicated commit.
- **Public static site** — new public repo (e.g. `gist-rs/katgpt-decisions`) or a katgpt-web subpage (**owner call**; default recommendation: separate repo — katgpt-web's contract is pure-explainer, and the playground is a product surface). Static page + client JS only; the playground talks to `http://127.0.0.1:<port>`; the Jev BYO-key lane runs browser→TypeSafe **directly** (the key never touches our infrastructure, satisfying "we won't pay API in any way" structurally).
- **katgpt-rs public additions**: decision wire-contract types (Jev/laya-compatible vocabulary: `choice`/`score`/`noul`; `DecisionRequest { state, questions }` → `DecisionResponse { answers, routing, calibration }`) in a small public crate or `katgpt-core::types`; the arena harness (count-pinned benches + scripted laya runner); the one-line `structured_reads` promotion when the engine lands.

### The four lanes (apple-to-apples, per the user's #3)

| Lane | Runs where | Who pays | Notes |
|---|---|---|---|
| KatGPT latent | in-process (visitor's machine via localhost engine; our CI box for published tables) | nobody | modelless heads + `CalibratedActionBridge` + `structured_read` + rule_embed vessel; ns–µs tier; bit-deterministic |
| Laya latent | same machine — v1: `uv`-managed Python sidecar driving HF transformers locally (their checkpoints, Apache-2.0); v2 option: candle port | nobody | their own protocol mirrored: byte-identical questions, fixed seed, all three checkpoints + their Router |
| Jev API | visitor's browser, **their** key | the visitor's tokens | optional lane, hidden unless a key is present; latency numbers labeled as network-inclusive (outside-latent-space latency is the visitor's path, not ours) |
| KatGPT API | the same localhost engine over HTTP | nobody | API-vs-API parity with the Jev lane; identical wire vocabulary |

### Benchmark protocol (the arena's integrity)

laya's own public tasks (typed-decisions 400 cases / 2,000 decisions; AG News; DAIR Emotion; Banking77; SST-5; prompt-injections; MASSIVE/XNLI subsets) **plus our code-domain fixtures** (healer retrieval_eval spans, fixseq-ring verdict shapes). Metrics per lane: top-1 accuracy, soft accuracy, Brier, **decision-level ECE measured against the conformal-naive floor** (Research 322/Plan 340 Report-the-Floor — a lane claiming "calibrated" without beating the floor is marked, not trusted), p50/p99 latency, abstain rate + selective accuracy (573's metric taxonomy), determinism (bit-identical repeat runs), cost. **Honest per-task tables; no single "we win" number** — 562's Arena row #15 LOSS (zero-shot breadth) stands and gets published, because the same HN crowd that audited TypeSafe will audit us. Published tables are CI-regenerated from the harness; a hand-typed number on the site is a defect by definition.

### The self-evolve flywheel (the moat lane — user's #4)

Consent-gated decision outcomes (semantics mirroring `--stats`: **Unset never pushes**) → `decstat` rows `{domain, primitive, question-shape, outcome}` → riir-kat wire → riir-dapps epoch settle + KAT rewards (the mining-pipeline reuse) → corpus grows → at the measured reopen threshold (~10⁴–10⁵ labeled contexts) the **specialist retrains** (supervised-CE per the CUA-S1 recipe or RLCD per Research 576 §3 — GPU-minutes/2×T4-hours on the 4090) → BLAKE3-sealed frozen artifact (`rule_embed_frozen_v1.bin` precedent) → freeze/thaw-distributed → selectable per-domain profile. **Three selectable lanes per domain:** model-based (tinyx specialist + `SigmoidGateCalibrator`-calibrated confidence; PUCT-over-options for sequential decision chains — the Bench-205 recipe; LoRA/freeze-thaw versioning), modelless (tables + corpus-is-the-model scoring + conformal/Platt refit from outcomes), hybrid (small corpus vessels). Launch domains: code-fix (forwards to the healer), triage/routing, guard/injection, moderation, scoring.

### What the site shows

Hero ("Typed decisions. Calibrated against a floor. Self-evolving. Free."), stat chips (ECE-vs-floor, latency, abstain rate, $0, bit-identical, on-chain provenance), the four-column comparison table (KatGPT vs Laya vs Jev vs a generic LLM: open weights / runs local / typed+probs / calibrated-vs-floor / abstains / self-evolves / cost), live playground (paste text → pick a pattern: Route / Guard / Score / Filter / Watch / Cascade), benchmark tab (the four-lane CI tables), agent-skill download (`SKILL.md` teaching coding agents to wire the engine — the laya-integration analog, and our home format), clone-and-run block.

## Honest caveats — READ BEFORE IMPLEMENTING

1. **Zero-shot breadth loss is structural today.** On laya's home tasks (emotion, AG News, intent) our modelless lane loses to their fine-tuned checkpoint and to Jev. The arena must publish per-task honesty or it gets picked apart exactly the way TypeSafe was. The win axes are calibration-vs-floor, latency, abstain, determinism, cost, self-evolve, and code-domain depth. If that honesty is not acceptable marketing, **Phase 2** is the wrong investment (this proposal's recommendation is to publish the losses; Phase 1 carries no exposure — see caveat 7e) — say so now, not after launch.
2. **The laya lane is a real work item.** v1 sidecar (local Python, `uv`, HF transformers) is honest and fast but makes "pure-Rust engine" partial; a candle port of ModernBERT/mmBERT + the mask-scoring head is multi-day. Decide before Phase 1 — the benchmark's credibility does not depend on which, only that the checkpoints run unmodified.
3. **The flywheel spans four repos** (riir-jev, riir-kat, riir-dapps, katgpt-rs) and needs a dapps-side row type + adoption surfaces — cross-repo cost outside this repo. Each phase must land independently green; the flywheel is worthless half-landed (the cross-repo-repair law: not landed until committed in the sibling, with the SHA cited).
4. **Trademark/nominative care.** "Jev" is TypeSafe's product name — nominative use with the laya-style disclaimer only. No brainfunctioncollapse prose, games, or benchmark text copied; protocols restated in our own words with citation.
5. **The 20 Hz / determinism selling points apply only to the modelless lane.** laya/Jev lanes are ms-tier and non-deterministic; per-lane scoping or the comparison table is a false claim by aggregation.
6. **Bench 817's policy verdict binds the engine's confidence readout**: label-entropy for narrow option sets, argmax-label-prob for wide ones; agreement-across-rereads is NOT a better ranking signal on deterministic forwards. Inherit, don't re-derive.
7. **Owner-gated calls:** (a) the public brand posture (KatGPT naming), (b) the repo name `riir-jev`, (c) the site repo choice (new repo vs katgpt-web page), (d) the theme, and **(e) THE MARKETING GATE — the decision that gates Phase 2, promoted from caveat 1:** *zero-shot breadth loss is structural today — on laya's home tasks our modelless lane loses to their fine-tuned checkpoint and to Jev. If publishing per-task losses (the reviewer-recommended posture, and this proposal's recommendation) is not acceptable marketing, Phase 2 is the wrong investment — say so now, not after launch. Phase 1 does not depend on this decision.* The new-repo registration is a workspace-contract change — one dedicated commit with the boundary gates green.

## Fusion lineage

- Research 562 (arena scoreboard + the calibration-gap finding) × Issue 810/Bench 808 (SigmoidGateCalibrator + CalibratedActionBridge landed) → the calibration-differentiated engine.
- Research 574 / Issue 859 / Bench 816–817 (`structured_read` GOAT, opt-in, promotion-when-consumer) × this engine → the promotion consumer, closing that loop.
- Research 573 / riir-clippy Issue 125 (specialist refuted at corpus scale; measured reopen) × riir-clippy's KAT contribution loop × laya's published RLCD recipe → the flywheel that un-refutes the specialist with fleet corpus.
- quest_grammar drafter pattern — **the split named explicitly**: the consumable half is katgpt-rs's `Lz4FlexDrafter` (`crates/katgpt-core/src/compression_drafter.rs`, "the corpus IS the model" modelless candidate scoring); `CompressionQuestDrafter` is the riir-ai GAME wrapper (`riir-games-quest/src/quest_grammar/compression_draft.rs`) and is **pattern lineage only — never a riir-jev dep** (the zero-game-deps boundary holds). Third consumer of the pattern riir-clippy borrowed first.
- brainfunctioncollapse.com/laya (arena packaging: playground + measured benchmark + agent skill + honest-limits FAQ) → the product shape, replicated under KatGPT branding with original content.

## GOAT gate

- **G1 (calibration):** engine decision-level ECE/Brier must beat (a) its own uncalibrated outputs and (b) the conformal-naive floor, per Report-the-Floor. Any lane claiming "calibrated" without flooring fails.
- **G2 (perf):** modelless lane p99 ≤ 1 ms per decision set in-process; API lane p50 ≤ 2× the latent lane on localhost; `structured_read` ≤ 0.5× full-loop (Bench 816's bar).
- **G3 (no regression):** riir-jev consumes katgpt-rs, never edits it; healer score-bench + game benches untouched; katgpt-rs additions count-pinned in the existing gates (docs gate + test gate).
- **G4 (alloc):** modelless hot path alloc-free (the bench-811 counting-allocator convention), canary-armed.
- **Arena integrity:** published tables CI-regenerated; the flywheel's specialist retrain fires ONLY at the measured corpus threshold and is GOAT-gated vs the modelless default on ID + withheld-pair OOD (Bench-062 discipline), freeze/thaw-committed, demote-the-loser on loss.

## What ships now (katgpt-rs) vs deferred

### Ships now — katgpt-rs (public primitive surface)
- Decision wire-contract types + arena harness (public crate or `katgpt-core::types`; feature-flagged, GOAT-gated).
- The `structured_reads` root promotion line once riir-jev lands (the recorded re-arm trigger — one line).

### Deferred — riir-jev (new private repo; the body of this proposal)
- Engine server (localhost HTTP), lanes 1+2+4, benchmark runner, contribution client (`decstat`), per-domain profiles.

### Deferred — riir-kat + riir-dapps (flywheel server half)
- `decstat` row type, settle integration, adoption-surface rows.

### Explicitly NOT shipped by this proposal
- No game code and no riir-ai deps in the public surface or riir-jev (boundary; the game moat stays hidden by construction). No paid API usage anywhere. No multilingual lane (honest gap — out of scope). No copy of brainfunctioncollapse content. No replacement of riir-clippy's healer surface (the code-fix domain forwards to it).

## Phased rollout (sketch — the plan expands)

### Phase 1 — engine + harness (riir-jev skeleton + katgpt-rs contract) — THE PRIMARY DELIVERABLE

*Standalone value even if Phases 2–3 never ship: this phase alone discharges the two strongest claims — `structured_reads`' recorded promotion trigger ("when a consumer appears", no consumer exists today, verified in Cargo.toml) and the Issue-125 corpus engine (measured reopen at 10⁴–10⁵, no engine running). It requires no marketing decision.*

- [ ] T1.1 BOUNDARY.md + repo registration (repo_set.txt + boundary gates, one dedicated commit)
- [ ] T1.2 wire-contract types in katgpt-rs (+ feature flag + GOAT gate scaffold)
- [ ] T1.3 engine modelless lane (pick_domain/CalibratedActionBridge + rule_embed vessel + corpus-is-the-model scoring via katgpt-rs's `Lz4FlexDrafter`) behind localhost HTTP — landed primitives only
- [ ] T1.4 laya lane: sidecar loader + their protocol mirrored (byte-identical questions, fixed seed). **Precondition: re-pin the laya sources at a full sha (`.raw/` clone) before ANY published table is CI-generated against their numbers — the live-fetch provenance caveat in Research 576 is not sufficient for landed artifacts**
- [ ] T1.5 harness: laya's public tasks + our fixtures; Report-the-Floor metrics; CI-regenerated tables
- [x] T1.6 corpus-distance abstain arm — **VALIDATED (Bench 845, 2026-09-21, GO for the opt-in lane; `distance_abstain` feature + `CorpusDistanceGate`):** beats the score-threshold ABSTAIN baseline in the world the arena targets (W1 OOD-blind: AURC −17%, Δ sel-acc +0.97 pp @ ρ=30%, 8/8 replicates, ~89% of the labeled oracle's ρ=30% gain) with the W2 negative control proving the signal is the OOD mechanism, not fixture bias. ⚠ Rank fusion is load-bearing (raw min(p, d_conf) degenerates to distance-only). NOT promoted to default — margin_gate precedent: the live consumer is the Phase-1 engine (this plan), where it joins as the abstain arm behind outcome calibration

### Phase 2 — the arena site (OPTIONAL PENDING THE OWNER MARKETING CALL — the wrapper, not the product)
- [ ] T2.1 static site (rust theme; playground → 127.0.0.1; benchmark tab; agent skill; disclaimers)
- [ ] T2.2 Jev BYO-key browser lane (optional; key stays client-side)
- [ ] T2.3 publish the first arena tables — **per-task honesty INCLUDING the losses (adopted reviewer recommendation: the honest table IS the differentiator — the Report-the-Floor argument one layer up; the same audience that audited TypeSafe will audit a losses-free table faster). Owner holds the final call — see the owner-gate block**

### Phase 3 — the flywheel (the moat lane; needs the Phase-1 engine, not the site)
- [ ] T3.1 `decstat` consent + wire (riir-kat; the `--stats` consent precedent) + dapps row type
- [ ] T3.2 epoch settle + rewards for decision rows; adoption surfaces
- [ ] T3.3 corpus-threshold monitor → specialist-retrain plan (RLCD or CE, Research 576 §3) → freeze/thaw vessel → per-domain promotion (demote the loser)

## Risks

1. **Phase-2 marketing exposure (owner-gated, see caveat 7e):** the honest table shows losses on their home turf — if that honesty is not acceptable marketing, **Phase 2** is the wrong investment (this proposal's recommendation is to publish the losses; Phase 1 carries no exposure).
2. **Architectural:** four-repo flywheel — phased, independently-green landings; the boundary contract keeps riir-jev from becoming a game or healer dependency surface.
3. **Legal/brand:** nominative use + disclaimers; original content only.
4. **Effort:** the laya-lane loader is the long pole — sidecar-first keeps Phase 1 honest while the candle port is evaluated.

## Out of scope

Multilingual decision lane; training our own generalist base; hosting anyone's paid API; replacing the healer; riir-ai game wiring (stays private; the moat book may cite the arena as a selling point, nothing more).

## References

1. brainfunctioncollapse.com/laya — the arena packaging model (cited-only; content not copied)
2. NandhaKishorM/laya (Apache-2.0) + HF convaiinnovations/laya — distilled in Research 576
3. arXiv:2503.23303 "SalesRLAgent" — distilled (Research 576 §2.1; synthetic-only caveats recorded)
4. arXiv:2510.01237 "Confidence-Aware Routing" — distilled abstract-level (Research 576 §2.2)
5. TypeSafe "System One Models & Jev" blog + HN thread — via Research 562
6. trycua CUA-S1 — via Research 573
7. vLLM PR #57250 + razorback16/openjev — via Research 574

## TL;DR (closer)

**Ship it, phased, engine-first:** Phase 1 (engine + harness + riir-jev) is the primary deliverable — it discharges `structured_reads`' recorded promotion trigger and builds the Issue-125 corpus engine with standalone value and no marketing dependency; Phase 2 (the arena site) is the wrapper, gated on the owner's marketing call (publish the losses — recommended); Phase 3 (the flywheel) needs only Phase 1. Open the Phase-1 plan (next `.plans/` number) after owner sign-off on brand, repo name, and site-repo choice.
