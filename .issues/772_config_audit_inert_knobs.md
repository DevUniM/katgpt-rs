# Issue 772 — config-audit first pass over katgpt-rs (the 09-13 sweep's sibling-hot exclusion): 7 verified inert/assert-only knobs, 3 FPs (trait-operational class)

**Status:** OPEN — A/B findings verified 2026-09-14 (syn detector + workspace-grep adjudication); orphan-report layer added same session (0 orphaned / 33 stillborn → S1-S6, 5 hand-verified). **Fixes landed 2026-09-14: A1/A2 WIRED, B1-B5 + S1-S5 DELETED** (S6 remaining — in flight). Detector provenance: `cargo heal --config-audit` + `--orphan-report` (riir-clippy Plans 124/126), first katgpt-rs runs — the 2026-09-13 14-repo consumer sweep excluded this repo as sibling-hot.

## Evidence basis (why these are TPs, not detector noise)

- The detector is syn-based (destructuring/pattern reads counted); every finding below has **0 field reads**.
- Workspace-wide grep corroboration: zero reads of any flagged field in any riir-* repo (katgpt-rs is upstream; the under-reported-consumer caveat is closed by the greps).
- The assert sites cited are the class-B shape: assert against the Default's own literal — coverage that cannot fail except by transcription.

## Class A — inert knob (const shadows the field; the knob cannot be turned)

- [x] **A1** `crates/katgpt-pruners/src/monopoly/mod.rs:380` — `GameConfig.max_jail_turns` defaults to `MAX_JAIL_TURNS`; production `systems.rs:838` reads the **const** (`p.jail_turns >= MAX_JAIL_TURNS`). Set the field to 5, the game still releases at 3.
- [x] **A2** `crates/katgpt-pruners/src/monopoly/mod.rs:381` — `GameConfig.max_doubles` same shape; production `systems.rs:881` (`doubles_count >= MAX_DOUBLES`).
  Fix: thread `&GameConfig` into `execute_turn(world, player_id, ai, rng)` (the other money fields ARE consumed at setup, so the struct is live — only these two logic sites bypass it) and read the fields at `:838`/`:881`; consts stay as the Default source. Alternative: delete both fields + their assert lines (`mod.rs:898-905`) if the domain never needs tunable jail/doubles.
  **LANDED (WIRE):** both sites read `world.resource::<GameConfig>()` (`max_jail_turns` hoisted above the `get_mut::<Player>` borrow; `max_doubles` hoisted once above the doubles loop). Wire-proof tests `jail_release_respects_config_max_jail_turns` + `speeding_jail_respects_config_max_doubles` (scripted `StubPlayer` AI + self-locating seed probe — each discriminates: red under the old consts). Consts stay as Default sources.

## Class B — assert-only field (fake coverage)

- [x] **B1** `crates/katgpt-core/src/traits/mod.rs:907` — `BcConfig.anneal` read 0x; only `tests_leo.rs:188` asserts `bc.anneal`. The riir-train `anneal` hits are `GumbelSoftmax::anneal` (unrelated). Fix: wire into the Bc update schedule or delete.
  **LANDED (DELETE):** no BC application site exists in katgpt-core (no training loops — `bc_config()` has zero callers/implementors); anneal is a training-loop knob and `AlphaSchedule::LinearAnneal` on `DualLeoMixer` is the existing substrate for that pattern if a consumer ever needs it. Field + Default + assert deleted; doc note added.
- [x] **B2** `crates/katgpt-forward/src/flashar_consensus.rs:125` — `ConsensusConfig.use_ternary_gate` promises "If true, use `simd_ternary_matvec` fusion gate instead of heuristic. Requires `plasma_path`" — **no dispatch exists**; `ternary_fusion_gate` (`:336-350`, root re-export under `plasma_path`) has ZERO callers. The only finding with a real primitive behind it: wire the consensus evaluate path to dispatch on the flag (cfg'd `plasma_path`), or delete flag + re-export + gate fn. Prefer wire — the primitive is measured substrate and the flag is documented behavior.
  **LANDED (DELETE — overrides the wire-preference with evidence):** no weight source exists for the gate (a learned/stored 6→1 `TernaryWeights` row nobody constructs), and a linear gate cannot encode `route_one`'s threshold-cascade semantics — there is no honest deterministic derivation. The lane is opt-in after its G1 quality FAIL (Issue 136, KL 2.9-6.5), `use_ternary_gate` had zero callers, and the only test asserted the default `false`. `simd_ternary_matvec` remains plasma-path substrate with its own consumers. Flag + Default + assert + `ternary_fusion_gate` + its `TernaryWeights` import deleted; removal note in the T5 section.
- [x] **B3** `crates/katgpt-percepta/src/transformer.rs:63` — `TransformerConfig.stop_token` is a write-only mirror: `generate()` stops on `vocab.stop_token_id` (built from `TransformerVocab::new`'s own param). `runner.rs:315` writes `stop_token: "halt"` into the config AND `runner.rs:325` passes the literal `"halt"` separately — proof the field is ignored: `test_predict_token_argmax` sets config `"halt"` while the vocab stops on `"c"`. All riir-ai consumers go through `Runner::build_from_graph` (no external field writes → fix is API-compatible in-workspace). Fix: `VanillaTransformer::new` validates/derives from the config (single source of truth) or delete the field and let the vocab own it.
  **LANDED (DELETE — vocab owns stopping):** removed the mirror field + Default entry + runner/test literals (9 construction sites). `TransformerVocab` is the single source of truth; the mismatch trap is gone. All in-workspace consumers verified unaffected (riir-ai goes through `Runner::build_from_graph`).
- [x] **B4** `crates/katgpt-sense/src/reconstruction.rs:133` — `ReconstructionConfig.lod_adaptive` ("Enable LOD-adaptive pruning") read 0x; only the defaults test asserts it. Fix: gate the adaptive-depth branch on it or delete.
  **LANDED (DELETE):** no LOD machinery exists in the reconstruction path to gate (no depth/LOD notion at all — wiring would invent the feature). Field + Default + assert deleted.
- [x] **B5** `crates/katgpt-speculative/src/precision_aware_draft.rs:25` — `BoundaryPenalty.quant_levels` accepted by `new()` but read 0x (2 asserts: unit + `tests/precision_aware_draft_goat.rs:86`). Documentation-as-field (the doc derives `quant_scale` from it; the math uses only `quant_scale`/`boundary_epsilon`). Fix: read it in the boundary math or delete field + param.
  **LANDED (DELETE):** field + Default + `new()` param + asserts removed; `new(quant_scale)` single param; 4 callers updated (level count is implicit in the scale — noted on `new`).

## FP record — the C2 "self-referential config struct" trio, all refuted by trait-dispatch (harvest for the detector's post-mining intake; NOT filed in riir-clippy — its tree is sibling-hot)

- `ColinearityBatchGate` (cgsp/filters.rs:71): "own-validate-impl" read is `is_degenerate` — the `BatchQualityGate` trait method **dispatched in production** by `CgspLoop::cycle` (`loop_.rs:326`), wired via `.with_batch_gate(...)` in `cgsp_minimal.rs:160`, `cgsp_collapse_recovery.rs:216`, doc example, integration test.
- `RuleBasedVerifier` (spechop/verifier.rs:83): `verify()` reads both knobs operationally (`:124-127` short-answer rule, `:151-155` jaccard rule), driven by `SpecHopPipeline`.
- `EntropyConflictDetector` (speculative/types.rs:1091): bench arms construct non-defaults (`tests/bench_ldt_lattice_deduction.rs:506-515`) and exercise all three fields through `is_conflicted_at_depth`.
- Detector refinement candidate: a read inside an `impl Trait for X` method is OPERATIONAL (externally dispatchable), unlike an inherent validate-shaped method — the cheap syn-only approximation is to exempt trait-impl bodies from the "own-validate-impl" bucket.

## Orphan-report layer (same session, `cargo heal --orphan-report`): 0 orphaned / 33 stillborn — the born-dead population

**0 orphaned** — none of the A/B findings above has a vanished-reader story: they were born inert, not orphaned by optimization (no repair-by-archaeology needed; the fix is wire-or-delete, not restore).

Hand-verified stillborn TPs (read-site greps done):
- [x] **S1** `crates/katgpt-core/src/branching/router.rs:115` — `BranchRouter.tau_spawn` — the sharpest finding: a knob on a HEAVILY-USED router whose logic reads `tau_snap` (`:216/:217/:231`) and `tau_jaccard` (`:249`) but NEVER `tau_spawn`; the documented spawn threshold ("Max dot-product score < this → consider spawn", `DEFAULT_TAU_SPAWN=0.0`) is unimplemented — the spawn decision is hardcoded elsewhere. Wire the threshold into the spawn branch or delete field+const+param.
  **LANDED (DELETE):** the router tests PIN spawn-on-no-snap as the intended semantics (`route_returns_spawn_when_below_snap_threshold` expects Spawn at cosine 0.707; `route_with_tokens_empty_query_tokens_skips_jaccard` expects Spawn at cosine 0.0) — wiring `best_score < tau_spawn` would invert that band to Frozen and break 4+ pinned tests. Deleted: field + `DEFAULT_TAU_SPAWN` + `new()` 3rd param + re-exports (branching/mod.rs, core lib.rs) + the riir-ai `cognitive_branches_runtime` re-export line (updated same commit) + 4 in-repo call sites. Rationale comment left at the const's old site.
- [x] **S2** `crates/katgpt-core/src/mux_latent/spectral_lod.rs:27` — `SpectralLOD.fft_size` — def/Default/`new()` param only; the analyze path never reads it.
  **LANDED (DELETE):** the analysis is a zero-alloc variance heuristic — no FFT runs, no window size consumed (the field documented an abandoned implementation approach). Field + Default + `new()` param + 2 test callers updated.
- [x] **S3** `crates/katgpt-core/src/mux_latent/config.rs:63` — `MuxLatentConfig.injection_layer` — never read; the injection layer cannot be overridden despite the doc.
  **LANDED (DELETE):** the injection machinery (`inject.rs`) carries no layer index at all — mid-layer injection is conceptual (the `PrefillEntry::Latent` doc), nothing downstream reads a layer override. Wiring would invent a plumbing axis no consumer carries. Field + Default entry deleted.
- [x] **S4** `crates/katgpt-kv/src/shard_kv/types.rs:69` — `ShardConfig.avg_bits_v` — written `2.0` in production (`kv_cache.rs:1082`) but never read — the write-only sibling of the live `avg_bits_k`.
  **LANDED (DELETE):** the V path is VQ-sized by `v_vq_group_size`/`v_vq_codebook_size` (4×256 → 2.0 bits/coord); the field's "used for VQ sizing" doc was false. Field + Default + 4 construction sites cleaned, `make_shard_cache`/`bench_shard_kv` params dropped. BONUS HONESTY FIX: test_147's "Proof 7 asymmetric (K=4,V=2) vs symmetric (K=3,V=3)" was fiction — the V path was identical VQ in both arms; relabeled as the K-bit sweep it actually measured (K=4 vs K=3, V=VQ fixed).
- [x] **S5** `crates/katgpt-core/src/cgsp/loop_.rs:71-72` — `CgspConfig.solve_rate_floor`/`solve_rate_ceiling` — bench constructions only; the breakeven drop-below/drop-above behavior they document is not implemented in the loop.
  **LANDED (DELETE):** the loop carries no solve-rate estimation — the documented breakeven-router bridge was never built (the `breakeven_routing` feature has its own separate machinery). Fields + Default + the one bench construction removed. Zero riir-* struct-literal constructions (verified by workspace grep) — consumers use `CgspConfig::default()`.

Detector-verified stillborn config knobs (syn 0-reads at HEAD + 0 read-shaped occurrences at every history probe; workspace grep shows no riir-* reads):
- [ ] **S6** the remaining knob-class rows: `BranchRouter.tau_spawn` covered above; `DepthInvarianceConfig.magnitude_slope_collapse` (katgpt-types), `HydraBudgetConfig.cumulative_threshold`+`.modelless` (katgpt-types), `CollapseDetectorFrozen.budget_ema_mean` (option_stripper), `InfluenceConfig.min_repetition_length` (mech_attribution), `InfoNceConfig.default_critic` (katgpt-band), `QbConfig.causality_strict` (katgpt-spectral), `QueryFeatures.expected_output_len` (pipeline_pruner), `SpKvConfig.predictor_lr_mult` (katgpt-kv sp_kv), `TrdConfig.max_refinement_steps`/`.refine_correct_branches`/`.elf_noise_scale` (speculative distill).

Excluded from action (benign/documented classes):
- `CompactionAuditRecord._pad` — repr(C) padding (the documented benign class).
- 4× `InferenceResult.*` in `katgpt-deprecated` — frozen crate.
- 12× trace/record fields (`AnchorTrace.future_accuracy`, `DecisionRecord.num_choices`, `FailureTrace.death_tick`, `GoldenTrace.expected_survival`, `TrialRecord.base_correct`/`reviewed_correct`, `GoGameAnalytics.unstable_round_count`, `ArenaEvaluation.candidate_id`, `P5Derived.derived_from`, `CompactionAuditRecord._pad` counted above) — audit-data class: written for records, plausibly serialization-consumed (the fn-scoped wire-clearance is deliberately conservative); adjudicate against wire formats before any deletion.

## Non-goals

- No behavioral change without the fix decision per finding (wire vs delete is a per-case call; B2 prefers wire, B5 likely delete).
- Not sweeping the negative-results book — these are code findings, not verdict changes.
