# Issue 772 — config-audit first pass over katgpt-rs (the 09-13 sweep's sibling-hot exclusion): 7 verified inert/assert-only knobs, 3 FPs (trait-operational class)

**Status:** OPEN — A/B findings verified 2026-09-14 (syn detector + workspace-grep adjudication); orphan-report layer added same session (0 orphaned / 33 stillborn → S1-S6, 5 hand-verified). Fixes pending. Detector provenance: `cargo heal --config-audit` + `--orphan-report` (riir-clippy Plans 124/126), first katgpt-rs runs — the 2026-09-13 14-repo consumer sweep excluded this repo as sibling-hot.

## Evidence basis (why these are TPs, not detector noise)

- The detector is syn-based (destructuring/pattern reads counted); every finding below has **0 field reads**.
- Workspace-wide grep corroboration: zero reads of any flagged field in any riir-* repo (katgpt-rs is upstream; the under-reported-consumer caveat is closed by the greps).
- The assert sites cited are the class-B shape: assert against the Default's own literal — coverage that cannot fail except by transcription.

## Class A — inert knob (const shadows the field; the knob cannot be turned)

- [ ] **A1** `crates/katgpt-pruners/src/monopoly/mod.rs:380` — `GameConfig.max_jail_turns` defaults to `MAX_JAIL_TURNS`; production `systems.rs:838` reads the **const** (`p.jail_turns >= MAX_JAIL_TURNS`). Set the field to 5, the game still releases at 3.
- [ ] **A2** `crates/katgpt-pruners/src/monopoly/mod.rs:381` — `GameConfig.max_doubles` same shape; production `systems.rs:881` (`doubles_count >= MAX_DOUBLES`).
  Fix: thread `&GameConfig` into `execute_turn(world, player_id, ai, rng)` (the other money fields ARE consumed at setup, so the struct is live — only these two logic sites bypass it) and read the fields at `:838`/`:881`; consts stay as the Default source. Alternative: delete both fields + their assert lines (`mod.rs:898-905`) if the domain never needs tunable jail/doubles.

## Class B — assert-only field (fake coverage)

- [ ] **B1** `crates/katgpt-core/src/traits/mod.rs:907` — `BcConfig.anneal` read 0x; only `tests_leo.rs:188` asserts `bc.anneal`. The riir-train `anneal` hits are `GumbelSoftmax::anneal` (unrelated). Fix: wire into the Bc update schedule or delete.
- [ ] **B2** `crates/katgpt-forward/src/flashar_consensus.rs:125` — `ConsensusConfig.use_ternary_gate` promises "If true, use `simd_ternary_matvec` fusion gate instead of heuristic. Requires `plasma_path`" — **no dispatch exists**; `ternary_fusion_gate` (`:336-350`, root re-export under `plasma_path`) has ZERO callers. The only finding with a real primitive behind it: wire the consensus evaluate path to dispatch on the flag (cfg'd `plasma_path`), or delete flag + re-export + gate fn. Prefer wire — the primitive is measured substrate and the flag is documented behavior.
- [ ] **B3** `crates/katgpt-percepta/src/transformer.rs:63` — `TransformerConfig.stop_token` is a write-only mirror: `generate()` stops on `vocab.stop_token_id` (built from `TransformerVocab::new`'s own param). `runner.rs:315` writes `stop_token: "halt"` into the config AND `runner.rs:325` passes the literal `"halt"` separately — proof the field is ignored: `test_predict_token_argmax` sets config `"halt"` while the vocab stops on `"c"`. All riir-ai consumers go through `Runner::build_from_graph` (no external field writes → fix is API-compatible in-workspace). Fix: `VanillaTransformer::new` validates/derives from the config (single source of truth) or delete the field and let the vocab own it.
- [ ] **B4** `crates/katgpt-sense/src/reconstruction.rs:133` — `ReconstructionConfig.lod_adaptive` ("Enable LOD-adaptive pruning") read 0x; only the defaults test asserts it. Fix: gate the adaptive-depth branch on it or delete.
- [ ] **B5** `crates/katgpt-speculative/src/precision_aware_draft.rs:25` — `BoundaryPenalty.quant_levels` accepted by `new()` but read 0x (2 asserts: unit + `tests/precision_aware_draft_goat.rs:86`). Documentation-as-field (the doc derives `quant_scale` from it; the math uses only `quant_scale`/`boundary_epsilon`). Fix: read it in the boundary math or delete field + param.

## FP record — the C2 "self-referential config struct" trio, all refuted by trait-dispatch (harvest for the detector's post-mining intake; NOT filed in riir-clippy — its tree is sibling-hot)

- `ColinearityBatchGate` (cgsp/filters.rs:71): "own-validate-impl" read is `is_degenerate` — the `BatchQualityGate` trait method **dispatched in production** by `CgspLoop::cycle` (`loop_.rs:326`), wired via `.with_batch_gate(...)` in `cgsp_minimal.rs:160`, `cgsp_collapse_recovery.rs:216`, doc example, integration test.
- `RuleBasedVerifier` (spechop/verifier.rs:83): `verify()` reads both knobs operationally (`:124-127` short-answer rule, `:151-155` jaccard rule), driven by `SpecHopPipeline`.
- `EntropyConflictDetector` (speculative/types.rs:1091): bench arms construct non-defaults (`tests/bench_ldt_lattice_deduction.rs:506-515`) and exercise all three fields through `is_conflicted_at_depth`.
- Detector refinement candidate: a read inside an `impl Trait for X` method is OPERATIONAL (externally dispatchable), unlike an inherent validate-shaped method — the cheap syn-only approximation is to exempt trait-impl bodies from the "own-validate-impl" bucket.

## Orphan-report layer (same session, `cargo heal --orphan-report`): 0 orphaned / 33 stillborn — the born-dead population

**0 orphaned** — none of the A/B findings above has a vanished-reader story: they were born inert, not orphaned by optimization (no repair-by-archaeology needed; the fix is wire-or-delete, not restore).

Hand-verified stillborn TPs (read-site greps done):
- [ ] **S1** `crates/katgpt-core/src/branching/router.rs:115` — `BranchRouter.tau_spawn` — the sharpest finding: a knob on a HEAVILY-USED router whose logic reads `tau_snap` (`:216/:217/:231`) and `tau_jaccard` (`:249`) but NEVER `tau_spawn`; the documented spawn threshold ("Max dot-product score < this → consider spawn", `DEFAULT_TAU_SPAWN=0.0`) is unimplemented — the spawn decision is hardcoded elsewhere. Wire the threshold into the spawn branch or delete field+const+param.
- [ ] **S2** `crates/katgpt-core/src/mux_latent/spectral_lod.rs:27` — `SpectralLOD.fft_size` — def/Default/`new()` param only; the analyze path never reads it.
- [ ] **S3** `crates/katgpt-core/src/mux_latent/config.rs:63` — `MuxLatentConfig.injection_layer` — never read; the injection layer cannot be overridden despite the doc.
- [ ] **S4** `crates/katgpt-kv/src/shard_kv/types.rs:69` — `ShardConfig.avg_bits_v` — written `2.0` in production (`kv_cache.rs:1082`) but never read — the write-only sibling of the live `avg_bits_k`.
- [ ] **S5** `crates/katgpt-core/src/cgsp/loop_.rs:71-72` — `CgspConfig.solve_rate_floor`/`solve_rate_ceiling` — bench constructions only; the breakeven drop-below/drop-above behavior they document is not implemented in the loop.

Detector-verified stillborn config knobs (syn 0-reads at HEAD + 0 read-shaped occurrences at every history probe; workspace grep shows no riir-* reads):
- [ ] **S6** the remaining knob-class rows: `BranchRouter.tau_spawn` covered above; `DepthInvarianceConfig.magnitude_slope_collapse` (katgpt-types), `HydraBudgetConfig.cumulative_threshold`+`.modelless` (katgpt-types), `CollapseDetectorFrozen.budget_ema_mean` (option_stripper), `InfluenceConfig.min_repetition_length` (mech_attribution), `InfoNceConfig.default_critic` (katgpt-band), `QbConfig.causality_strict` (katgpt-spectral), `QueryFeatures.expected_output_len` (pipeline_pruner), `SpKvConfig.predictor_lr_mult` (katgpt-kv sp_kv), `TrdConfig.max_refinement_steps`/`.refine_correct_branches`/`.elf_noise_scale` (speculative distill).

Excluded from action (benign/documented classes):
- `CompactionAuditRecord._pad` — repr(C) padding (the documented benign class).
- 4× `InferenceResult.*` in `katgpt-deprecated` — frozen crate.
- 12× trace/record fields (`AnchorTrace.future_accuracy`, `DecisionRecord.num_choices`, `FailureTrace.death_tick`, `GoldenTrace.expected_survival`, `TrialRecord.base_correct`/`reviewed_correct`, `GoGameAnalytics.unstable_round_count`, `ArenaEvaluation.candidate_id`, `P5Derived.derived_from`, `CompactionAuditRecord._pad` counted above) — audit-data class: written for records, plausibly serialization-consumed (the fn-scoped wire-clearance is deliberately conservative); adjudicate against wire formats before any deletion.

## Non-goals

- No behavioral change without the fix decision per finding (wire vs delete is a per-case call; B2 prefers wire, B5 likely delete).
- Not sweeping the negative-results book — these are code findings, not verdict changes.
