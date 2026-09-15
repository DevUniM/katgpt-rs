# Issue 799 — bevy_ecs 0.15 optional arm: bump to 0.19 or retire (BOUNDARY.md question)

**Status:** DECIDED 2026-09-15 — **BUMP to 0.19** (T1+T2 below); T3–T6 execution scoped for the landing session. Prior session's API-surface audit spot-check verified same day (zero scheduler/Commands/change-detection hits re-confirmed against `src/pruners/bomber` + `crates/katgpt-pruners/src/monopoly`).

## Why this issue exists

katgpt-rs is the public upstream (modelless inference primitives, no riir dep).
It currently carries **bevy_ecs 0.15 as an optional dependency in two places**:

- root `Cargo.toml` ~line 105: `bevy_ecs = { version = "0.15", optional = true }` — comment "Standalone ECS (Plan 033)"
- `crates/katgpt-pruners/Cargo.toml` ~line 36: `bevy_ecs = { version = "0.15", optional = true }` — comment `bomber (no, bomber stays) / monopoly`

Meanwhile **every game repo in the workspace is on bevy/bevy_ecs 0.19**
(riir-games-shared, riir-game-sdk, riir-mmorpg-examples, seal-view,
seal-game-editor editor-types at bevy_ecs 0.19.1). The lockfile resolves
bevy_ecs **0.15.4**.

This is **not** a routine version bump. katgpt-rs's `BOUNDARY.md` owns the
dependency contract, and a Bevy ECS runtime dep in the public funnel repo
needs a **domain-test answer**: is the bomber/monopoly ECS usage load-bearing
for this repo's modelless-inference mandate, or would a lighter substrate
serve? Both outcomes are acceptable:

1. **Bump to 0.19** — the arm stays, aligned with the workspace, audited.
2. **Retire the optional arm** — the dep leaves the contract (either replaced
   by a lighter substrate or the arena modules are judged non-load-bearing).

What is NOT acceptable is leaving the decision unmade while the pin drifts.

## Domain-test framing

The root BOUNDARY.md domain test: *"is this a modelless inference primitive
with no riir dep (this repo is upstream of everything)?"* A game-simulation
arena is not obviously a modelless inference primitive — it is an
**evaluation harness** that proves HL-technology value (Plan 033's verdict:
"HL thesis proven: HL (+177) > Greedy (+131) > Validator (-30) > Random (-55)
in 100-round tournament"). The arena is load-bearing **as evidence
infrastructure**: root features `binned_blend` and `kernel_blend` (Plan 436 /
Issue 428) depend on `bomber`, and kernel_blend's GOAT evidence (Benchmark
432: G2 PASS, mean delta +78.5, CI [+26.3, +130.8], Welch t=3.61 p≈0.0003)
was measured on bomber tournaments. `tests/bench_bomber_arena.rs` is the
tournament bench behind that story.

So the honest domain-test question splits in two:

- **Is the ARENA load-bearing?** Strong evidence yes — it is the benchmark
  substrate for HL-estimator GOAT gates. Retiring the arenas would orphan the
  kernel_blend/binned_blend feature story.
- **Is bevy_ecs LOAD-BEARING for the arena?** See the evidence below: the
  exercised API surface is small, schedule-free, and change-detection-free.
  This is the question the bump-vs-retire decision must answer with evidence,
  not vibes.

Workspace alignment (everyone else on 0.19) is a **weak argument** — this
repo is upstream and does not follow the game repos. The load-bearing
question is the domain test.

## Evidence — what the two arms actually use (measured 2026-09-15)

Consumers and gating:

- **bomber** — lives in the ROOT crate (`src/pruners/bomber/`, ≈18,110 LOC),
  gated `#[cfg(feature = "bomber")]`; root feature `bomber = ["bevy_ecs",
  "bandit"]` (Plan 033). Downstream root features depend on it:
  `binned_blend = ["bomber"]`, `kernel_blend = ["bomber"]`.
- **monopoly** — lives in `crates/katgpt-pruners/src/monopoly/` (5,358 LOC
  across board.rs / mod.rs / players.rs / systems.rs), gated
  `#[cfg(feature = "monopoly")]`; katgpt-pruners feature `monopoly =
  ["bevy_ecs", "bandit"]`; root feature `monopoly = ["bevy_ecs", "bandit",
  "katgpt-pruners/monopoly"]` (its plan is **035_monopoly_fsm.md** — see the
  mis-cite note below).
- **tests/benches/examples**: 35 additional bevy_ecs references across ≥8
  files, including `tests/bench_bomber_arena.rs`,
  `tests/bench_shared_vs_independent_hl.rs`, `tests/bench_gzero_modelless.rs`,
  `tests/bench_fixed_vs_procedural.rs`, and the `bomber_0N_*` examples.

API surface actually exercised (the whole inventory):

- `World::new()`, `insert_resource`, `resource::<T>()`, `resource_mut::<T>()`,
  `get_resource_mut::<T>()`, `get::<C>(entity)`, `spawn((...)).id()`
- `world.query::<(...))>()` / `world.query_filtered::<..., With<...>>()`
- `bevy_ecs::entity::Entity`
- `bevy_ecs::event::Events<GameEvent>` + `Events::drain()` (validator agent
  drains per tick via `resource_mut`; no `EventReader`/`EventWriter` handles)
- Derives: `Component` / `Resource` / `Event` — 21 derive sites across the
  two modules

API surface NOT exercised (zero hits):

- `Schedule` / `add_systems` / any scheduler — `systems.rs` header states it
  explicitly: "All systems operate on `&mut World` for tick-based game loop
  control. Called in deterministic order by `run_tick`; **no ECS schedule is
  used**."
- `Commands` — zero hits
- Change detection — `Changed<` / `Added<` / `RemovedComponents` / `Local<` /
  `NonSend` — zero hits
- `SystemState` / `QueryState` — zero hits
- Plugins / `App` — not used

Second-order surface: the bevy_ecs dep is the reason the workspace pins the
**getrandom wasm32 backends** (root `Cargo.toml` ~line 158: bevy_ecs →
bevy_utils → ahash pulls BOTH getrandom 0.2 and 0.3; without the pins
`secure_vessel` / `bomber-wasm` / `bomber` fail their wasm32 builds). Any
bump changes this transitive tree and must re-verify the wasm32 lanes.

BOUNDARY.md currently mentions bevy only once (the getrandom wasm-backend
pin note) — the dep contract itself does not name bevy_ecs explicitly. That
is part of the gap this issue closes.

## Comment-drift findings (fix alongside the decision)

1. **Plan mis-cite:** root `Cargo.toml` ~line 377 cites "(Plan 034)" for the
   `monopoly` feature, but Plan 034 is `034_bomber_wasm_validator.md`
   (zero monopoly mentions). Monopoly's actual plan is
   `.plans/035_monopoly_fsm.md`.
2. **Confusing consumer comment:** `crates/katgpt-pruners/Cargo.toml` ~line
   36 reads `# bomber (no, bomber stays) / monopoly`. The actual consumer of
   katgpt-pruners' bevy_ecs is **monopoly only** — bomber stayed in the root
   crate (confirmed by `crates/katgpt-pruners/src/lib.rs`: "The `bomber`
   sub-module stays in `katgpt-rs`"). The comment should say monopoly and
   stop re-mentioning bomber.
3. Root `Cargo.toml` ~line 105's comment cites only "(Plan 033)" (bomber) —
   accurate for the root dep, but the root feature `monopoly` also pulls
   bevy_ecs through `katgpt-pruners/monopoly`; worth one clarifying word
   when the decision lands.

## Tasks

- [x] Answer the domain test with evidence: is the bomber/monopoly bevy_ecs
      usage load-bearing for this repo's modelless-inference mandate (arena =
      GOAT evidence substrate), or would a lighter substrate serve the
      schedule-free World/query/events pattern the arenas actually use?
      **VERDICT (2026-09-15): the ARENA is load-bearing; bevy_ecs is not —
      but a replacement does not clear the cost/benefit bar.** The arena is
      evidence infrastructure (kernel_blend/binned_blend GOAT gates measured
      on bomber tournaments, Bench 432) — retiring it orphans the feature
      story and breaks benchmark comparability. bevy_ecs itself serves as a
      schedule-free data-structure layer (verified: the entire exercised
      surface is `World` + `world.query{,_filtered}` + `Events` via
      `resource_mut` + 21 derive sites; zero scheduler/Commands/change-
      detection), so a lighter substrate COULD serve — but replacing it means
      rewriting ≈23.5K LOC across two arenas, re-validating every tournament
      result for byte-comparability, for zero mandate gain (bevy_ecs is
      optional, costs nothing unless a consumer enables bomber/monopoly, and
      carries no riir dep). The mandate test passes: an evaluation harness
      with no riir dep, upstream of everything.
- [x] Decide **bump to 0.19 vs retire the optional arm**, recording the
      reasoning (domain-test verdict, API-surface audit result, wasm32
      transitive-tree impact). **DECISION: BUMP to 0.19.** Reasoning: (1)
      retirement fails cost/benefit (above); leaving at 0.15 fails the
      drift bar this issue was filed under. (2) The exercised API is the
      stable core of bevy_ecs — `World::query{,_filtered}`, `Events` drain
      via `resource_mut`, `Component`/`Resource`/`Event` derives, `Entity` —
      all present in 0.19 with minimal delta (no scheduler migration, no
      observer surface, no change-detection migration exists to migrate).
      (3) Alignment with the workspace's 0.19 wave simplifies cross-repo
      reasoning (getrandom/ahash transitive tree converges with the game
      repos' bevy 0.19 pins). (4) The wasm32 transitive-tree impact (root
      `Cargo.toml` ~158 getrandom backend pins) is the one real risk and is
      owned by T3's re-verification step.
- [ ] If bump: audit bevy_ecs 0.15→0.19 API deltas against the ACTUAL usage
      sites above (World::query/query_filtered signatures, Events::drain,
      Component/Resource/Event derive requirements, Entity semantics) and
      re-verify the wasm32 lanes (getrandom backend pin set, bevy_utils →
      ahash version shift) — feature-gated code needs
      `--verify-args "--features bomber"` / `--features monopoly` builds.
- [ ] If retire: define the replacement (lighter substrate vs archiving the
      arenas) and what happens to `binned_blend`/`kernel_blend` whose GOAT
      evidence lives on bomber tournaments — reproducibility of Benchmark 432
      must survive the change.
- [ ] Record the decision in `BOUNDARY.md` if the dep contract changes
      (either way: name bevy_ecs in the allowlist explicitly, or record its
      removal), and fix the three comment-drift findings above in the same
      landing commit.
- [ ] If bump: run the GOAT gate on `bench_bomber_arena` before/after to
      prove no perf regression in the tournament harness (the arenas are
      benchmark infrastructure; a silent slowdown poisons future GOAT gates).
