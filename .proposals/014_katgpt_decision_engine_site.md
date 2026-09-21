# Proposal 014 — KatGPT Decisions: the open decision-engine comparison arena + the `riir-reflex` serving repo

Status: **IN FLIGHT — [Plan 603](../.plans/603_reflex_phase1_engine_harness.md) Phase 1 opened with owner go (T1.2 `katgpt_core::decision_wire` LANDED; T1.6 abstain arm GO via Bench 845; T1.1 BLOCKED on owner: `mkdir /Users/katopz/git/riir-reflex` + optional `gh repo create gist-rs/riir-reflex --private`).**
Branch: `develop` (per global rule — no feature branches)
Owner: unassigned
Fusion of: Research 562 × 573 × 574 × 576 + Issue 810/Bench 808 + Issue 859/Bench 816–817 + riir-clippy Issues 125/126 + the quest_grammar drafter pattern + the KAT contribution network (riir-kat + riir-dapps + riir-clippy)
Related: [Research 576](../.research/576_Laya_Open_Jev_Generalist_RLCD_Comparison_Arena.md) (the source distill this proposal consumes), [Research 562](../.research/562_Typesafe_SystemOne_Jev_Calibrated_Decisions.md), [Research 573](../.research/573_CUA_S1_Open_Jev_Recipe_Specialist_Option_Scorer.md), [Research 574](../.research/574_Jev_Structured_Reads_DiffusionGemma_vLLM_57250.md), [Research 322](../.research/322_Conformal_Seasonal_Pools_Calibrated_UQ_Overlay.md) (Report-the-Floor)

## TL;DR

Ship the **KatGPT decision engine + benchmark harness** (new private repo `riir-reflex`, riir-clippy-shaped): a localhost serving binary over the landed substrate — modelless heads, `SigmoidGateCalibrator`-calibrated bridges, `structured_read` — benchmarked head-to-head against the Laya family and TypeSafe Jev in four lanes (byte-identical questions): (1) **KatGPT latent** (in-process), (2) **Laya latent** (their Apache-2.0 checkpoints loaded locally on the same machine, by a NATIVE-RUST runner — zero Python, owner directive), (3) **Jev API** via the *visitor's own* key (browser-side; we never pay anyone), (4) **KatGPT API** (the same engine behind localhost HTTP — apples-to-apples API-vs-API). Phase 1 is the primary deliverable and needs no marketing call: it alone discharges `structured_reads`' recorded promotion trigger ("when a consumer appears") and builds the **corpus flywheel's intake** — consent-gated decision outcomes flowing through the existing KAT contribution network, growing the labeled corpus that riir-clippy Issue 125's *measured* reopen trigger (10⁴–10⁵ contexts) demands; at threshold the specialist retrains (RLCD recipe — now published via laya, Research 576 §3), freeze/thaws as a BLAKE3 vessel, and ships as a selectable per-domain engine profile. The **public arena site** at **`reflex.gist.rs`** (dark-red rust theme — explicitly not laya's yellow; public product name **Reflex** under the KatGPT funnel) is Phase 2 — **GREEN-LIT (owner 2026-09-21)**: per-task losses published (the standing recommendation, adopted) and distribution following the cargo-heal pattern (new public binary-release repo + tap + bucket; source stays private in `riir-reflex`). The substrate race is already won and landed (562's arena scoreboard: 11W/2L/2SPLIT; Benches 808/816/817); the missing pieces are the consumer, the corpus engine, and the surface. This is a katgpt-rs + new-repo product proposal distilling a public competitor set, not a new research claim. **Hosted serving (added 2026-09-21, the owner's six service/economics questions — TUNA trial, devnet/mainnet, tokenomics, CF container deploy, site pricing, CLI-vs-API parity): designed in §"The hosted serving plane" as a Phase-4 sketch — one ledger, no second token, the shop press/hold settlement pattern, per-decision µKAT as an owner constant.**

## The problem this solves

- **We hold the strongest calibrated-decision substrate in any workspace and zero public surface proving it.** laya's arena converts "open weights + measured benchmark + agent skill" into 5.3k GitHub stars; TypeSafe has marketing; we have research notes nobody outside the workspace can run. The 562 addendum's scoreboard (what they cannot enter at any price: 20 Hz, determinism, sync-path) is invisible to everyone but us.
- **`structured_read` is evidence-banked opt-in whose own landing note (574 §9) says promotion is "one line when a consumer appears"** — no consumer exists. The engine below is that consumer.
- **Issue 125's specialist was REFUTED at ~101 labeled contexts with a measured reopen at 10⁴–10⁵** — and no corpus-growth engine is running for decision tasks. riir-clippy built exactly this loop for code fixes (mine → contribute → settle → corpus → healer improves, all on-chain); nothing carries it for decisions.
- The public-brand posture is already settled strategy (Research 003): *what* = public katgpt-rs primitives; *how* = private riir-*; game code hidden. The arena is the public *what*; `riir-reflex` is a private *how* that touches no game domain.

## The proposed design

### Branding + repo layout

- **Public brand: `Reflex`** (product name — owner call 2026-09-21, caveat 7a resolved) under the **KatGPT** funnel (the established public name, `gist-rs` org). Theme: **dark red rust** (`#B7410E`/`#7C1D05` family) — the owner's explicit color call (caveat 7d resolved); no yellow anywhere. All site content original; the *arena shape* (playground + measured benchmark + agent-skill download) is replicated as an unprotectable concept, with zero prose/games copied from brainfunctioncollapse. Disclaimers: "not affiliated with or endorsed by TypeSafe AI; Jev is their product, named only to compare" (the laya-site idiom) + Apache-2.0 attribution for the laya checkpoints the arena loads.
- **New private repo `riir-reflex`** — decision-engine serving + benchmark harness + contribution client. riir-clippy-shaped boundaries: `katgpt-core` non-optional; `katgpt-forward` under the `structured_reads` root forward (the promotion consumer); `riir-kat` for the contribution wire (the `--mine`/`--sync`/`--stats` client precedent); optional `riir-rag` for corpus-distance abstain (Research 576 §2.1's extraction). **Zero game deps; zero Python deps** — BOUNDARY.md domain test: "decision-engine serving + comparison + contribution; NOT game runtime, NOT code healing." The new-repo decision passes the boundary test (`boundary_rationale.md`): the borrowed substrate patterns fit in ~200-LOC reimplementations (the quest_grammar drafter lineage, §Fusion) and there is zero game-domain coupling from ANY feature combination — the same test that placed riir-clippy in its own repo. The counter-case is on record: Proposal 017's extraction of `riir-games` was correctly REFUSED for bidirectional engine coupling — riir-reflex has no such coupling, which is what makes it the new-repo case rather than the rejected one. Repo birth carries the dependency-graph artifact (`sibling_layout.md` shape): default build = one code-level dep (`katgpt-core`), opt-in feature arms consume non-game whole substrates only where reimplementation would be absurd duplication (the Plan-005 nuance), and no game crate is reachable from any feature combination. The 22-file workspace registration (repo_set.txt + boundary gates + floors) lands as its own dedicated commit.
- **Public site: `reflex.gist.rs`** (RESOLVED — owner call 2026-09-21). Static page + client JS only; the playground talks to `http://127.0.0.1:<port>`; the Jev BYO-key lane runs browser→TypeSafe **directly** (the key never touches our infrastructure, satisfying "we won't pay API in any way" structurally). Hosting repo: new public repo for the site content (default; katgpt-web stays pure-explainer per its contract) — a minor implementation detail, not an open design question.
- **Distribution — the cargo-heal pattern (RESOLVED — owner call 2026-09-21, caveat 7e):** binary-only public releases, source never leaves `riir-reflex` (Research 003 posture). Three tiny source-free public repos, exactly the Plan-105 shape: `gist-rs/reflex` (GitHub Releases + `install.sh` + `install.ps1` + capabilities-only README) · `gist-rs/homebrew-tap` (Formula) · `gist-rs/scoop-bucket` (manifest). Four refinements over the template, learned from it: **(1) laya weights are NOT bundled in release assets** — runtime download from HF with BLAKE3-pinned per-file digests + Apache-2.0 attribution in `THIRD_PARTY_LICENSES.md` (lean assets, provenance pins kept, no rehosting); **(2) the no-source CI guard seeds at repo creation** (zero `.rs` files allowed in any public repo — the cargo-heal arm); **(3) the binary build-stamps itself** (`--version` prints the compiled feature set + `STALE` marker when incomplete — the cargo-heal Issue-117 lesson, `src/build_stamp.rs` shape); **(4) release notes LINK the CI-generated arena tables** (hosted at `reflex.gist.rs/bench`) rather than hosting copies — one source of truth.
- **katgpt-rs public additions**: decision wire-contract types (Jev/laya-compatible vocabulary: `choice`/`score`/`noul`; `DecisionRequest { state, questions }` → `DecisionResponse { answers, routing, calibration }`) in a small public crate or `katgpt-core::types`; the arena harness (count-pinned benches + scripted laya runner); the one-line `structured_reads` promotion when the engine lands.

### The four lanes (apple-to-apples, per the user's #3)

| Lane | Runs where | Who pays | Notes |
|---|---|---|---|
| KatGPT latent | in-process (visitor's machine via localhost engine; our CI box for published tables) | nobody | modelless heads + `CalibratedActionBridge` + `structured_read` + rule_embed vessel; ns–µs tier; bit-deterministic |
| Laya latent | same machine — **NATIVE-RUST runner, no Python anywhere (owner directive 2026-09-21: the whole lane is Python-free, cost be damned)**: candle (or in-crate forward) port of ModernBERT-large + mmBERT-base + the mask-scoring head + their tokenizers + a Rust script-detector Router; checkpoints consumed from their Apache-2.0 safetensors unmodified | nobody | their protocol mirrored: byte-identical questions, fixed seed, all three checkpoints + their Router; **parity gate: top-1 agreement ≥ 99.9% + probability drift ≤ 1e-3 vs the reference checkpoint on a fixture corpus** (bit-identity is not claimed — op order differs from PyTorch; honest tolerance, not a vibe) |
| Jev API | visitor's browser, **their** key | the visitor's tokens | optional lane, hidden unless a key is present; latency numbers labeled as network-inclusive (outside-latent-space latency is the visitor's path, not ours) |
| KatGPT API | the same localhost engine over HTTP | nobody | API-vs-API parity with the Jev lane; identical wire vocabulary |

### Benchmark protocol (the arena's integrity)

laya's own public tasks (typed-decisions 400 cases / 2,000 decisions; AG News; DAIR Emotion; Banking77; SST-5; prompt-injections; MASSIVE/XNLI subsets) **plus our code-domain fixtures** (healer retrieval_eval spans, fixseq-ring verdict shapes). Metrics per lane: top-1 accuracy, soft accuracy, Brier, **decision-level ECE measured against the conformal-naive floor** (Research 322/Plan 340 Report-the-Floor — a lane claiming "calibrated" without beating the floor is marked, not trusted), p50/p99 latency, abstain rate + selective accuracy (573's metric taxonomy), determinism (bit-identical repeat runs), cost. **Honest per-task tables; no single "we win" number** — 562's Arena row #15 LOSS (zero-shot breadth) stands and gets published, because the same HN crowd that audited TypeSafe will audit us. Published tables are CI-regenerated from the harness; a hand-typed number on the site is a defect by definition.

### The self-evolve flywheel (the moat lane — user's #4)

Consent-gated decision outcomes (semantics mirroring `--stats`: **Unset never pushes**) → `decstat` rows `{domain, primitive, question-shape, outcome}` → riir-kat wire → riir-dapps epoch settle + KAT rewards (the mining-pipeline reuse) → corpus grows → at the measured reopen threshold (~10⁴–10⁵ labeled contexts) the **specialist retrains** (supervised-CE per the CUA-S1 recipe or RLCD per Research 576 §3 — GPU-minutes/2×T4-hours on the 4090) → BLAKE3-sealed frozen artifact (`rule_embed_frozen_v1.bin` precedent) → freeze/thaw-distributed → selectable per-domain profile. **Three selectable lanes per domain:** model-based (tinyx specialist + `SigmoidGateCalibrator`-calibrated confidence; PUCT-over-options for sequential decision chains — the Bench-205 recipe; LoRA/freeze-thaw versioning), modelless (tables + corpus-is-the-model scoring + conformal/Platt refit from outcomes), hybrid (small corpus vessels). Launch domains: code-fix (forwards to the healer), triage/routing, guard/injection, moderation, scoring.

### What the site shows

Hero ("Typed decisions. Calibrated against a floor. Self-evolving. Free."), stat chips (ECE-vs-floor, latency, abstain rate, $0 local — hosted on KAT per the Phase-4 plane, bit-identical, on-chain provenance), the four-column comparison table (KatGPT vs Laya vs Jev vs a generic LLM: open weights / runs local / typed+probs / calibrated-vs-floor / abstains / self-evolves / cost), live playground (paste text → pick a pattern: Route / Guard / Score / Filter / Watch / Cascade), benchmark tab (the four-lane CI tables), agent-skill download (`SKILL.md` teaching coding agents to wire the engine — the laya-integration analog, and our home format), clone-and-run block.

## The hosted serving plane — services & economics, e2e (added 2026-09-21; the owner's six questions)

The arena makes the engine free to run locally. This section designs the plane where the engine is ALSO a service — hosted decisions for people who don't run the binary — wired into the EXISTING KAT/TUNA economy. One ledger, one identity, no second token, zero new payment code.

### The three access surfaces (one account, one balance)

| Surface | Runs where | Pays | Identity | Tier posture |
|---|---|---|---|---|
| `reflex` local engine | the visitor's machine | nothing — free forever, the hero claim | none | **Lite** (the anonymous binary, outside the economy) |
| `reflex` CLI → hosted engine | our compute | KAT burn (the cargo-heal plane) | Ed25519 account key (`reflex login` — the heal login chain) | **Pro** (account + burn; earns via mining today; decstat DESIGNED, Phase 3 — does not settle yet, the P013 cell wording) |
| Hosted HTTP API | our compute | KAT burn (the press/hold plane) | the same account key → session (SIWR/passkey or key verify) | **Pro** (session posture — no new tier) |

**No new chain tier — an access surface, never a tier** (the Proposal-005 discipline `node_tiers.md` names): all three postures ride the existing Lite/Pro vocabulary, which is what lets reflex join the ai.gist.rs roles × tiers matrix and the front-page lanes strip for free when the plane lands. That landing is a **one-place rule**: the node-tiers table (riir-clippy `.docs/01_orientation/node_tiers.md` — the spec ai.gist.rs mirrors and the dist README carries) gains the hosted-decisions row in the SAME commit as T4.1's routes, or the fleet answers "what can I run and what does it cost" from two places that drift (the node_tiers per-token-figure repair is the drift precedent).

**Price the decision, not the client.** One µKAT-per-decision rate across CLI and API; cargo heal and reflex are two burners on ONE account and ONE balance — which is exactly why the trial wording must go fleet-wide (§1). Differences between the surfaces are service posture, never price (§6).

**Pre-launch copy obeys the P013 capabilities-only law** (the tiers-matrix wording rule — no earnings promise beyond what settles): until T4.4's rate constant exists, nothing anywhere says hosted decisions are available or payable. The same "designed — does not settle yet" cell wording the matrix uses for replay.

### 1. TUNA trial — mechanically free, narratively a reword

- **The draw is account-level, not lane-level.** `record_burn` draws TUNA-first (oldest expiry first) then KAT, against the account's balances — there is no per-lane filter in the ledger. A hosted decision burn goes through the SAME call as a heal burn, so every existing property holds unchanged: once-per-account-life claim (`/account/claim`, 30-day TTL from claim), expired credit inert until swept, trial burns do NOT fund the mining pool, and the plane split (`charged_tuna_micro`/`charged_kat_micro`) rides every ack.
- **What changes is the strings.** The fleet FAQ says trial credit is "spent on healing only" — true today only because heal is the only burner. The first non-heal burner (reflex) must land the fleet-wide reword ("your free trial credit pays first — healing, decisions, everything on the network") in the SAME commit as the first reflex burn lane: front-page FAQ + `/tuna/stats` copy + the client `--info` render. A consumer-facing string describing scope is part of the wire of trust, not docs debt.
- **Sizing stays envelope doctrine.** The 100 KAT-equivalent trial (the Issue-094 D1 recalibration) is sized for evaluation, not free hosting — the dao envelope gate ([7 days, 2 years] drain for a heavy user at the sustained rate) applies to reflex spend identically; the Phase-4 plan re-measures the envelope with the decision rate included.

### 2. devnet / mainnet — no second ledger, the standing ladder

- **reflex hosted rides the EXISTING kat-service ledger** — the same DOs, the same epoch settle, the same burn watermark, the same faucet-never posture. No new worker ledger, no new genesis, no new consensus surface. `reflex.gist.rs` is the product FRONT (static + playground + pricing); the money plane is routes on the kat-service worker (the `/shop/*` + `/art/*` route-family precedent), reachable at `ai.gist.rs/reflex/*` with a worker route binding `api.reflex.gist.rs` if a vanity host is wanted.
- **Arming is fail-closed, and the ordering de-risks the owner constant.** The `/reflex/*` money routes land INERT — `unconfigured` (503, the error-code table's fail-closed class) — until TWO owner acts arm them: the per-decision rate constant in the bounds table AND the env kill-switch flipped per env (the `KAT_FAST_SETTLE` posture: default OFF in code, owner-enabled in prod vars). So T4.1's routes can deploy before the owner ever prices a decision without creating a half-live money surface; arming is a secret put + var flip, never a redeploy. `/pricing` may ship with the routes but renders the honest not-yet-live state until armed.
- **The ladder is the fleet's:** Phase 1 (localhost) and Phase 2 (static site) touch NO money. Phase 3 (decstat contributions) lands on the devnet fleet ledger first. Phase 4 (hosted burn/press lanes) is devnet-first — apex `ai.gist.rs` stays THE mainnet, and mainnet promotion is the owner ceremony it already is (SettlementSubmitter owner-gated; unfunded planes answer fail-closed `unconfigured`, never a silent half-live surface). TUNA genesis for the hosted plane is a dated operator batch like every reservoir action.

### 3. tokenomics — a burn sink that closes the flywheel

- **Hosted decisions are a new KAT burn source, and KAT burns fund the mining pool.** The loop closes: hosted spend pays the pool that pays decstat contributors — the two-sided economy gains its spend side exactly when the contribution side (Phase 3) lands. TUNA trial burns still fund nothing (honest, unchanged).
- **Pricing is an owner constant, never-lever class.** The per-decision rate sits beside the pack prices in the ledger bounds table — KAT-denominated money-adjacent constants are owner territory (the NEVER_LEVERS doctrine). NO dao lever at launch. A future bounded lever (a per-decision-rate lever under per-lever delta bounds + circuit breaker, the guard engine) is a recorded OPTION for a later plan, not a promise.
- **No new mints anywhere.** No grant change, no reservoir change, no never-lever touched. The only new ledger motion is burn (debit) and press hold/settle (escrow-style, the shop plane pattern).

### 4. Cloudflare container deploy — three tiers, one measurement

| Tier | What | Shape |
|---|---|---|
| 0 | reflex.gist.rs (site, playground, `/pricing`, `/bench` tables) | Workers static assets — zero marginal cost |
| 1 | hosted API edge (session, identity, hold/settle, rate limit, error codes) | `/reflex/*` routes on the kat-service worker — ALL existing machinery |
| 2 | the engine runner | decided by MEASUREMENT at the Phase-4 plan (below) |

**Tier 2's two postures, one discriminator:**
- **(a) wasm-in-Worker** — the modelless lane is ns–µs tier and katgpt-core already has wasm32 lanes with simd128 kernels (the wasm32 gate builds both arms). If the modelless lane's frozen tables fit the Workers script/memory budget, the API edge serves decisions with NO second compute shape at all. The discriminator is a number: measured frozen-vessel size vs the budget — read at the Phase-4 plan, never assumed.
- **(b) CF Container** — the `edge-wallet-container` precedent: the native `riir-reflex` binary (the SAME release artifact `gist-rs/reflex` ships) in a distroless image, HEALTHCHECK + `--cpus`/`--memory` budgets, behind the Worker edge. The deploy mechanics are riir-deployer's: `deploy.yaml` in riir-reflex (cf-container destination, `cross-build.sh` linux-x86 artifact staged from the mac, stage → verify, L3 rolling drain/flip for updates, explicit rollback). The container exists for process isolation + specialist vessels — modelless marginal compute is µs-tier CPU, never a GPU story.
- **The laya lane is NEVER hosted** — two BERT-class encoders (421M + 322M) are the visitor's hardware in this proposal's design, deliberately: hosting them is a GPU cost center with no moat, while the local binary IS the product. Hosted = modelless + specialist lanes only.
- **Every hosted decision carries a verifiable receipt** — toolchain fingerprint (blake3 of `rustc -vV`: version + commit + host — the replay lane's exact axis; two builds of one feature set under different rustc are NOT re-derivable, so the feature-set stamp alone would under-pin the claim) + compiled feature set (the `--version` lesson) + BLAKE3(input) + lane id + the decision. A client running the SAME release on the same platform class can re-derive and check — which turns the determinism selling point (caveat 5 scopes it to the modelless lane) from a claim into an auditable property: nobody has to trust "our compute". The receipt is also the runner-staleness tripwire (the stale-binary lesson): a stamp on the status line names the exact build serving, so a drifted runner is visible, never silent. Like-for-like only — SIMD dispatch differs across arches, so the receipt NAMES the build and the client compares like-for-like; cross-arch bit-identity is never claimed (the same honesty the laya parity gate uses). The replay lane's toolchain-fingerprint pin is the precedent (a verdict computed under the wrong build is refused unscored); hosted is the softer form — the receipt DISCLOSES, the client DECIDES. laya/Jev lanes carry their own stamps or none, never the modelless lane's determinism claim.

### 5. service cost & payment on the website — reuse, then honesty

- **`/pricing` on reflex.gist.rs, three cards:** Free local (unlimited, $0, no account) · Trial (the once-per-life TUNA grant, 30 days) · Pay-per-decision (µKAT rate + KAT packs). A live balance widget renders the account's KAT+TUNA position (`/balance` + `/history` — the web twin of `cargo heal --info`) and a burn meter.
- **Payment reuses the fleet rails VERBATIM:** Stripe + Solana Pay (`kat_payments`/`kat_solana`), the payreq signature seams, the machine-readable money-route error codes, mint receipts with the stats stamp. ZERO new payment code in reflex — the pricing page links the existing ai.gist.rs top-up flow.
- **The cost page publishes the honest model:** modelless marginal compute ≈ nil; what the KAT funds (the pool → contributors); the reconcile posture ai.gist.rs already runs. A pricing page that hides where the money goes gets audited by the same crowd that audits the losses table.

### 6. CLI vs API keys — one rate, two settlement planes

- **One rate.** Per-decision µKAT is identical for CLI and API — no client-class discount. What differs is service: API = programmatic sessions + SLA posture; CLI = contributor-first (decstat/mining rebates — the ~2/3 pool rebate — offsetting or exceeding spend; the "contribute or pay" doctrine extended to decisions).
- **The real difference is the settlement wire, and it is already built twice.** The CLI keeps the cumulative signed burn watermark (`kat:burnwm`, offline stacking) because it executes locally and reports honestly; a HOSTED call cannot serve-then-trust, so it uses the press/hold plane (`katsvc:shophold:` precedent): the client signs a hold for N decisions, the service settles the ACTUAL count in ONE CommitBatch, and the press-fate matrix is inherited verbatim — RETAINED on pre-settle refusals, REAPED on expiry, SPENT at settle. An expired hold is a retry, never a lost debit and never a free serve. **No-debt is inherited structurally, and hosted is the STRONGER case** (the `kat_billing.md` property): heal bills offline and reconciles later because it cannot know the balance at run time — a hosted call CAN, so serving checks balance BEFORE serving and refuses with `insufficient_balance` + the refuel contract; the warn-and-pay clamp that heal tolerates never arises mid-settle, nothing ever goes negative, no credit is extended. Two edges are named now for the Phase-4 plan to answer, both chaos-matrix arms (T4.5): actual count > hold N (settle clamps at N — the hold is the prepaid envelope; excess is a new hold, never a free serve and never an overcharge) and balance moving between hold creation and settle (another machine burning the same account) — the all-or-nothing batch discipline decides it, per-round conservation asserted.
- **Refusals reuse the error-code table** (`insufficient_balance` / `rate_limited` / `account_banned` / `bad_signature` / `unconfigured`) — the soft-gate posture ("contribute or top up") reads identically on the web pricing page. No new codes unless a decision-specific terminal class actually appears.
- **The depleted posture crosses to HTTP as a response contract, not a prompt.** The 075 soft gate is TTY-shaped (a y/N contribute-now offer); an API refusal is a JSON body. T4.4's "soft-gate wording parity" therefore means exactly: `insufficient_balance` carries a machine-readable `refuel` object naming the SAME two doors (contribute — `--mine` + sync via the CLI; top_up — the payment URL) plus the count-only survey analog ("N decisions would have been served"). Two doors, never a hidden third — the D4 doctrine rendered as a wire shape.
- **The burn footer is inherited SHAPE, golden-pinned, never a shared UI crate.** reflex's CLI renders the same footer contract `kat_billing.md` documents (neutral `fixed` label, count × rate, the tank the run drew from, sync state) with decision-lane wording — re-implemented against the ack-v4 fixtures per the Issue-082 wire law, because the footer render lives in riir-clippy (presentation) and reflex must not grow a riir-clippy dep for a display. This is the borrow-pattern-not-dep convention (`09_lessons/borrow_without_dep.md` — the riir-clippy founding rule this proposal's repo decision already rides), with its measured nuance: the ~200-LOC reimplementation default holds for the footer; only whole-substrate consumption justifies a feature-gated dep. If a third burner ever materializes, the render is the extraction candidate (riir-kat, the second-consumer law) — not before.
- **API keys ARE account keys** (the `account_key` substrate; SIWR/passkey session mint for browsers). One account, one key — the heal posture; per-key scopes are a later need, not a Phase-4 design input.

### Phase 4 sketch — the hosted plane (after Phase 3 lands; owner constants at plan time)

- [ ] T4.1 dapps: `/reflex/*` route family + press/hold decision settlement + the fleet-wide trial-string reword (same commit as the first reflex burn lane) — routes land FAIL-CLOSED (`unconfigured` until armed; the `KAT_FAST_SETTLE` posture) + the node-tiers table row lands the same commit (the one-place rule)
- [ ] T4.2 runner posture decided by MEASUREMENT (wasm-in-worker vs CF container, the vessel-size discriminator); `deploy.yaml` + `cross-build.sh` + the rolling ladder
- [ ] T4.3 `/pricing` + balance widget + top-up links on reflex.gist.rs + the front-page lanes-strip / tiers-matrix row (P013 capabilities-only wording until armed)
- [ ] T4.4 the rate constant (owner) → ledger bounds-table row + envelope re-measure with decisions included + the `refuel` response contract (soft-gate-over-HTTP parity: two doors + count-only survey) + the arming env flip
- [ ] T4.5 devnet e2e (the shop chaos-matrix pattern over hold/settle: retention/reap/spend + conservation per round) → mainnet promote = the owner ceremony

### Honest status (the P013 law — read before advertising anything)

| Axis | State |
|---|---|
| Shipped | nothing — this whole section is a Phase-4 sketch (caveat 8) |
| Armed | nothing — no per-decision rate constant exists in any bounds table |
| Pays | nothing — hosted decisions settle nowhere; TUNA trial burns fund nothing (unchanged) |

**Do not advertise hosted availability** until the rate constant + env arming land (T4.4): the site's "hosted on KAT" chip reads as DESIGN until then, and `/pricing` does not exist before Phase 4. Where the truth will live when it ships: balance → `/balance` + `/history`; footer tanks → burn ack v4; hosted receipt → the settle response + build stamp; what the money funds → the pool ledger.

## Honest caveats — READ BEFORE IMPLEMENTING

1. **Zero-shot breadth loss is structural today.** On laya's home tasks (emotion, AG News, intent) our modelless lane loses to their fine-tuned checkpoint and to Jev. The arena must publish per-task honesty or it gets picked apart exactly the way TypeSafe was. The win axes are calibration-vs-floor, latency, abstain, determinism, cost, self-evolve, and code-domain depth. **RESOLVED 2026-09-21: owner green-lit Phase 2 with the losses published (caveat 7e) — the honesty posture is adopted, and the cargo-heal-pattern binary distribution reinforces it (releases + honest tables + a one-line install is the credibility loop).**
2. **The laya lane is a NATIVE-RUST port (owner directive 2026-09-21: NO Python — no sidecar, no `uv`, no HF transformers, anywhere in the lane; accepted cost "no matter year").** Scope: candle or in-crate forward over safetensors — ModernBERT-large (421M) + mmBERT-base (322M, RoPE→8k) + the mask-scoring head + their tokenizers (WordPiece-class; the mmBERT 256k vocab is the bigger half) + a Rust script-detector Router (pure logic, trivial). Multi-week honest estimate; the parity gate (top-1 ≥ 99.9%, p-drift ≤ 1e-3 on a fixture corpus) replaces "runs unmodified" — bit-identity is NOT claimed (op order differs from PyTorch). **The ban is also the product story:** "no Python required" is a selling point against laya's own `pip install` posture — the reflex binary runs the whole four-lane arena standalone.
3. **The flywheel spans four repos** (riir-reflex, riir-kat, riir-dapps, katgpt-rs) and needs a dapps-side row type + adoption surfaces — cross-repo cost outside this repo. Each phase must land independently green; the flywheel is worthless half-landed (the cross-repo-repair law: not landed until committed in the sibling, with the SHA cited).
4. **Trademark/nominative care.** "Jev" is TypeSafe's product name — nominative use with the laya-style disclaimer only. No brainfunctioncollapse prose, games, or benchmark text copied; protocols restated in our own words with citation.
5. **The 20 Hz / determinism selling points apply only to the modelless lane.** laya/Jev lanes are ms-tier and non-deterministic; per-lane scoping or the comparison table is a false claim by aggregation.
6. **Bench 817's policy verdict binds the engine's confidence readout**: label-entropy for narrow option sets, argmax-label-prob for wide ones; agreement-across-rereads is NOT a better ranking signal on deterministic forwards. Inherit, don't re-derive.
7. **Owner-gated calls — ALL RESOLVED 2026-09-21:** (a) brand = **`Reflex`** (product name) under the KatGPT funnel; (b) repo name = **`riir-reflex`** (not riir-jev — "Jev" is TypeSafe's product name); (c) site domain = **`reflex.gist.rs`**; (d) theme = **dark red rust, no yellow** (the owner's explicit directive in the filing message — the branding section records it; exact hex/typography refinement is T2.1 implementation detail, never an owner gate); **(e) THE MARKETING GATE: Phase 2 GREEN-LIT** — per-task losses published (the recommendation adopted), distribution = the cargo-heal pattern (`gist-rs/reflex` releases + tap + bucket, source private). The new-repo registration is a workspace-contract change — one dedicated commit with the boundary gates green.
8. **The hosted plane (§"The hosted serving plane") is DESIGNED, not green-lit as a build order.** Phases 1–3 are unchanged by it. Three owner constants live inside it and none is decided here: the per-decision µKAT rate, the mainnet promotion, and any future dao-lever promotion — all deliberately owner territory per the NEVER_LEVERS doctrine. The wasm-vs-container posture is a measurement, not a preference (the Phase-4 plan reads the vessel size before anything deploys). And a wording clarification: "No paid API usage anywhere" (below) was always about THIRD-party APIs (we never pay for Jev) — our own hosted plane charging KAT is the Phase-4 sketch, not an exclusion.

## Fusion lineage

- Research 562 (arena scoreboard + the calibration-gap finding) × Issue 810/Bench 808 (SigmoidGateCalibrator + CalibratedActionBridge landed) → the calibration-differentiated engine.
- Research 574 / Issue 859 / Bench 816–817 (`structured_read` GOAT, opt-in, promotion-when-consumer) × this engine → the promotion consumer, closing that loop.
- Research 573 / riir-clippy Issue 125 (specialist refuted at corpus scale; measured reopen) × riir-clippy's KAT contribution loop × laya's published RLCD recipe → the flywheel that un-refutes the specialist with fleet corpus.
- quest_grammar drafter pattern — **the split named explicitly**: the consumable half is katgpt-rs's `Lz4FlexDrafter` (`crates/katgpt-core/src/compression_drafter.rs`, "the corpus IS the model" modelless candidate scoring); `CompressionQuestDrafter` is the riir-ai GAME wrapper (`riir-games-quest/src/quest_grammar/compression_draft.rs`) and is **pattern lineage only — never a riir-reflex dep** (the zero-game-deps boundary holds). Third consumer of the pattern riir-clippy borrowed first.
- brainfunctioncollapse.com/laya (arena packaging: playground + measured benchmark + agent skill + honest-limits FAQ) → the product shape, replicated under KatGPT branding with original content.

## GOAT gate

- **G1 (calibration):** engine decision-level ECE/Brier must beat (a) its own uncalibrated outputs and (b) the conformal-naive floor, per Report-the-Floor. Any lane claiming "calibrated" without flooring fails.
- **G2 (perf):** modelless lane p99 ≤ 1 ms per decision set in-process; API lane p50 ≤ 2× the latent lane on localhost; `structured_read` ≤ 0.5× full-loop (Bench 816's bar).
- **G3 (no regression):** riir-reflex consumes katgpt-rs, never edits it; healer score-bench + game benches untouched; katgpt-rs additions count-pinned in the existing gates (docs gate + test gate).
- **G5 (laya-port parity):** the Rust laya runner meets the parity gate — top-1 agreement ≥ 99.9% and probability drift ≤ 1e-3 vs the reference checkpoint on a fixed fixture corpus, per checkpoint — before ANY published table cites its numbers. A failed parity gate marks the lane PROVISIONAL in every table it appears in.
- **G4 (alloc):** modelless hot path alloc-free (the bench-811 counting-allocator convention), canary-armed.
- **Arena integrity:** published tables CI-regenerated; the flywheel's specialist retrain fires ONLY at the measured corpus threshold and is GOAT-gated vs the modelless default on ID + withheld-pair OOD (Bench-062 discipline), freeze/thaw-committed, demote-the-loser on loss.

## What ships now (katgpt-rs) vs deferred

### Ships now — katgpt-rs (public primitive surface)
- Decision wire-contract types + arena harness (public crate or `katgpt-core::types`; feature-flagged, GOAT-gated).
- The `structured_reads` root promotion line once riir-reflex lands (the recorded re-arm trigger — one line).

### Deferred — riir-reflex (new private repo; the body of this proposal)
- Engine server (localhost HTTP), lanes 1+2+4 (incl. the native-Rust laya runner), benchmark runner, contribution client (`decstat`), per-domain profiles.

### Deferred — public dist surface (the cargo-heal pattern, Phase 2)
- `gist-rs/reflex` (releases + installers + no-source guard) · `gist-rs/homebrew-tap` formula · `gist-rs/scoop-bucket` manifest · `release.yml` matrix + license generation. Source stays in `riir-reflex` (private) — binaries only in public.

### Deferred — riir-kat + riir-dapps (flywheel server half)
- `decstat` row type, settle integration, adoption-surface rows.

### Deferred — the hosted serving plane (the Phase-4 sketch above)
- dapps `/reflex/*` routes (fail-closed until armed) + press/hold decision settlement + the fleet trial-string reword; the runner posture (wasm-in-worker vs CF container, measured); the verifiable-decision receipt; `/pricing` + balance widget + the node-tiers table row + the front-page lanes-strip row; the rate constant + bounds row + the `refuel` response contract; the devnet chaos matrix over hold/settle.

### Explicitly NOT shipped by this proposal
- No game code and no riir-ai deps in the public surface or riir-reflex (boundary; the game moat stays hidden by construction). **No Python anywhere in the lane** (owner directive — no sidecar, no `uv`, no HF transformers dependency; the laya lane is the native-Rust port). **No paid THIRD-party API usage anywhere** (the Jev lane is BYO-key; we never pay anyone — our OWN hosted plane charging KAT is the Phase-4 sketch, deliberately outside Phases 1–3). No multilingual lane of OUR OWN (honest gap — the ported mmBERT checkpoint serving multilingual requests is laya's capability running locally, not a claim about our engine). No copy of brainfunctioncollapse content. No replacement of riir-clippy's healer surface (the code-fix domain forwards to it).

## Phased rollout (sketch — the plan expands)

### Phase 1 — engine + harness (riir-reflex skeleton + katgpt-rs contract) — THE PRIMARY DELIVERABLE

*Standalone value even if Phases 2–3 never ship: this phase alone discharges the two strongest claims — `structured_reads`' recorded promotion trigger ("when a consumer appears", no consumer exists today, verified in Cargo.toml) and the Issue-125 corpus engine (measured reopen at 10⁴–10⁵, no engine running). It requires no marketing decision.*

- [ ] T1.1 BOUNDARY.md + repo registration (repo_set.txt + boundary gates, one dedicated commit); the workspace drift sweeps DERIVE the new repo automatically (root BOUNDARY.md + `.git`), but the repo keeps its own gate discipline from day one — every `#![cfg]`-gated test target gets a `[[test]]` row with `required-features` in the SAME commit, proven at the EXACT feature set (`cargo test --test <name> --no-run --features <set>` must NAME the executable, then once for the passed count — the silent-now rule: a gated target nobody names prints `ok. 0 passed`, exit 0, byte-for-byte a real pass)
- [ ] T1.2 wire-contract types in katgpt-rs (+ feature flag + GOAT gate scaffold)
- [ ] T1.3 engine modelless lane (pick_domain/CalibratedActionBridge + rule_embed vessel + corpus-is-the-model scoring via katgpt-rs's `Lz4FlexDrafter`) behind localhost HTTP — landed primitives only
- [ ] T1.4 laya lane: **NATIVE-RUST runner (no Python — owner directive)** — candle/in-crate forward over their safetensors: ModernBERT-large + mmBERT-base + the mask-scoring head + tokenizers + Rust script-detector Router; their protocol mirrored (byte-identical questions, fixed seed); **G5 parity gate (top-1 ≥ 99.9%, p-drift ≤ 1e-3 vs reference, per checkpoint)** before any published number. **The G5 gate is the repo's highest-stakes silent-now candidate**: the laya lane is feature-gated, so its parity test ships as a whole-file `#![cfg(feature = "laya")]` target — without a `[[test]]` row + `required-features` in the SAME commit it prints `ok. 0 passed`, exit 0 forever, and the arena publishes a comparison table resting on a gate that never executed. The row is proven at the EXACT laya feature set (`--no-run` names the executable; one run for the passed count). **Precondition: re-pin the laya sources at a full sha (`.raw/` clone) before ANY published table is CI-generated against their numbers — the live-fetch provenance caveat in Research 576 is not sufficient for landed artifacts**
- [ ] T1.5 harness: laya's public tasks + our fixtures; Report-the-Floor metrics; CI-regenerated tables
- [x] T1.6 corpus-distance abstain arm — **VALIDATED (Bench 845, 2026-09-21, GO for the opt-in lane; `distance_abstain` feature + `CorpusDistanceGate`):** beats the score-threshold ABSTAIN baseline in the world the arena targets (W1 OOD-blind: AURC −17%, Δ sel-acc +0.97 pp @ ρ=30%, 8/8 replicates, ~89% of the labeled oracle's ρ=30% gain) with the W2 negative control proving the signal is the OOD mechanism, not fixture bias. ⚠ Rank fusion is load-bearing (raw min(p, d_conf) degenerates to distance-only). NOT promoted to default — margin_gate precedent: the live consumer is the Phase-1 engine (this plan), where it joins as the abstain arm behind outcome calibration

### Phase 2 — the arena site + binary distribution (GREEN-LIT, owner 2026-09-21)
- [ ] T2.1 static site at **`reflex.gist.rs`** (rust theme; playground → 127.0.0.1; benchmark tab; agent skill; disclaimers)
- [ ] T2.2 Jev BYO-key browser lane (optional; key stays client-side)
- [ ] T2.3 publish the first arena tables — **per-task honesty INCLUDING the losses (adopted: the honest table IS the differentiator — the Report-the-Floor argument one layer up; the same audience that audited TypeSafe will audit a losses-free table faster)**
- [ ] T2.4 binary distribution, the cargo-heal pattern: `gist-rs/reflex` (releases + install.sh + install.ps1 + capabilities-only README carrying the roles × tiers table shape — the cargo-heal dist README precedent, where the same README needed a burn-unit-figure repair; no earnings promise beyond what settles; zero-`.rs` CI guard seeded at creation) + `gist-rs/homebrew-tap` formula + `gist-rs/scoop-bucket` manifest; `release.yml` builds the matrix with the pinned release feature set; `SHA256SUMS` + `THIRD_PARTY_LICENSES.md` (Apache-2.0 laya attribution) in every archive; laya weights runtime-downloaded from HF with BLAKE3-pinned digests — never bundled; `--version` build-stamps the feature set (the stale-binary lesson)

### Phase 3 — the flywheel (the moat lane; needs the Phase-1 engine, not the site)
- [ ] T3.1 `decstat` consent + wire (riir-kat; the `--stats` consent precedent) + dapps row type
- [ ] T3.2 epoch settle + rewards for decision rows; adoption surfaces
- [ ] T3.3 corpus-threshold monitor → specialist-retrain plan (RLCD or CE, Research 576 §3) → freeze/thaw vessel → per-domain promotion (demote the loser)

### Phase 4 — the hosted serving plane (sketch; after Phase 3, owner constants at plan time)
- [ ] T4.1 dapps `/reflex/*` routes + press/hold settlement + fleet trial-string reword — routes land FAIL-CLOSED (`unconfigured` until armed) + the node-tiers row the same commit
- [ ] T4.2 runner posture by measurement (wasm-in-worker vs CF container); deploy.yaml + cross-build + rolling ladder
- [ ] T4.3 `/pricing` + balance widget + top-up links + the lanes-strip / tiers-matrix row (P013 wording until armed)
- [ ] T4.4 rate constant (owner) + bounds row + envelope re-measure + the `refuel` response contract + the arming env flip
- [ ] T4.5 devnet chaos e2e → mainnet = owner ceremony

## Risks

1. **Phase-2 marketing exposure — ACCEPTED (owner 2026-09-21, caveat 7e):** the honest table shows losses on their home turf; the mitigation IS the honesty (credibility with the audience that audits everything) plus the cargo-heal-pattern distribution (install one-liner next to the tables). Phase 1 carries no exposure.
2. **Architectural:** four-repo flywheel — phased, independently-green landings; the boundary contract keeps riir-reflex from becoming a game or healer dependency surface.
3. **Legal/brand:** nominative use + disclaimers; original content only.
4. **Effort:** the native-Rust laya port IS the long pole — a deliberate, owner-directed cost (multi-week: two encoders + head + tokenizers + parity fixtures), accepted for the standing property it buys: the whole arena ships as ONE dependency-free Rust binary, "no Python required" as a first-class selling point against laya's `pip install` posture.

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

**Ship it, phased, engine-first — every owner gate is resolved:** Phase 1 (engine + harness + riir-reflex, incl. the native-Rust laya runner) is the primary deliverable — it discharges `structured_reads`' recorded promotion trigger and builds the Issue-125 corpus engine with standalone value; Phase 2 (the arena at `reflex.gist.rs` + the `gist-rs/reflex` binary distribution, cargo-heal pattern) is GREEN-LIT with the losses published; Phase 3 (the flywheel) needs only Phase 1. **The hosted serving plane (TUNA trial → KAT burn → packs; devnet-first, mainnet = the owner ceremony; CF container deploy via riir-deployer; `/pricing` reusing the fleet rails; CLI/API one-rate parity; routes fail-closed until the owner's rate constant arms them; every hosted decision carrying a verifiable receipt) is designed as the Phase-4 sketch — owner constants at plan time. Open the Phase-1 plan (next `.plans/` number) now.**
