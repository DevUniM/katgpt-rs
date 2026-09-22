# Issue 870 — `distance_abstain` ships a rationale-free single-branch sigmoid copy beside three sanctioned in-crate patterns

Status: **OPEN — filed by the 2026-09-22 substrate-first Mode 2 audit (detection only; fix is a separate commit per the issue-first rule).**

Source: substrate-first skill Mode 2 audit, 2026-09-22 wave (fresh files since 09-21 18:00).
Substrate duplicated: `crate::exact_sigmoid` (`src/lib.rs:54` → `simd::exact_sigmoid`, the libm two-branch reference form) and `crate::sigmoid` (`src/lib.rs:38`, Cephes).

## Finding

`crates/katgpt-core/src/distance_abstain.rs:46-49` (landed `62d73730`, 2026-09-21 19:05 — after the 09-21 audit rows, so unaudited until now):

```rust
#[inline]
fn sigmoid(x: f32) -> f32 {
    1.0 / (1.0 + (-x).exp())
}
```

- **No in-source rationale** (the copy-gate convention: a justified copy needs in-source rationale + a divergence-failing test — this has neither).
- **No divergence pin** vs the in-crate substrate forms.
- The module doc documents the sigmoid's *role* ("sigmoid projection of the max cosine similarity", "sigmoid, never softmax") but not the *form choice*.

## Why this is the copy-class, not a sanctioned local

Three sanctioned patterns already exist **in the same crate, in the same audit wave**:

| site | pattern |
|---|---|
| `closure/bridge.rs:155-162` | local `fn sigmoid` **delegates** to `crate::simd::fast_sigmoid` (Cephes) with in-source rationale |
| `katgpt-forward/src/d2f/mod.rs:308-313` | local `fn sigmoid` **delegates** to `katgpt_core::simd::fast_sigmoid` with doc comment |
| 6 modules (`closure/bridge_certified.rs`, `salience/gate.rs`, `successor_density_critic.rs`, `refinement_marginal.rs`, `ugc_schedule.rs`, `breakeven/mod.rs`) | consume `exact_sigmoid` directly |

`distance_abstain` is the only fresh module that neither delegates nor documents why not.

## Divergence envelope (measured reasoning, not hand-waving)

- vs `exact_sigmoid` (two-branch): **bit-identical for x ≥ 0** (identical expression); for x < 0 differs by ≤1 ULP in the normal range; differs materially only for x < −88.7 where the single-branch form returns 0.0 vs the two-branch denormal.
- The gate's actual argument domain is `scale·(max_sim − mid)` = `8·(sim − 0.35)` with sim ∈ [−1, 1] → **[−10.8, +5.2]** — no overflow reachable; agreement ≤1 ULP everywhere in-domain.
- vs `crate::sigmoid` (Cephes `fast_sigmoid`): ~1 ULP everywhere (the standing lesson: delegation to Cephes is a semantic change — do NOT use the Cephes form here without re-validating Bench 845).

## Proposed fix (the Issue-156 permanent-pin pattern)

1. Delegate the local fn: `fn sigmoid(x: f32) -> f32 { crate::exact_sigmoid(x) }` (or call it directly at the two call sites — `:95` and the doc reference).
2. Add a **bit-identity/divergence-bounded test**: for the gate's domain [−10.8, 5.2], assert the delegated form agrees with the frozen single-branch body (≤1 ULP, and exact for x ≥ 0) — the permanent pin vs future form drift.
3. Re-run `bench_845_distance_abstain_goat` gates at the `distance_abstain` feature to confirm the GOAT verdicts (AURC −17%, Δ sel-acc +0.97pp, 8/8 replicates) hold — expected: ULP-level movement cannot move thresholds at scale 8/mid 0.35.
4. If any gate moves, fall back to documenting the copy in-source with the rationale + keeping the frozen form (the justified-copy escape hatch) — a recorded refusal, never a silent keep.

## Classification

**DRY violation (copy-class)** — the ndb Issue 611 / chain Issue 156 family, caught at ONE site before it multiplies. Not architectural (no two-brain/sync/domain rule touched); not POC (this is a validated GOAT-gated primitive, not a scratch path).

## Substrate check (substrate-first skill)

- Searched for: `fn sigmoid`, `1.0/(1.0+`, `.exp()` forms over the 09-21→09-22 fresh wave (katgpt-rs, riir-ai, riir-clippy, riir-game-sdk, riir-mmorpg-examples fresh files; vendor/ excluded per Issue 738 T3).
- Found: the substrate (`exact_sigmoid` + Cephes `sigmoid`) and three sanctioned delegation/consumption patterns; this file is the sole rationale-free copy (riir-clippy `rule_embed.rs:71` two-branch copy is bit-identical WITH rationale — consumer-side arrival #1, below the 4-arrival consolidation threshold, note-level only).
- Decision: file (this issue); fix = consume `exact_sigmoid` + permanent pin.
- Architectural rules checked: none engaged (pure numerics, no sync/latent boundary) — the finding is DRY-only.
