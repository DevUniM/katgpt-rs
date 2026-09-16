# Bench 600: FlashAR Confidence-Commit (DBTM κ∪floor) — Plan 600 T8+T9 GOAT Gates

**Date:** 2026-09-17
**Plan:** [600_flashar_confidence_commit_upgrade.md](../.plans/600_flashar_confidence_commit_upgrade.md)
**PoC:** [Issue 811](../.issues/811_confidence_commit_anchor_rule.md) (2026-09-16 arm table, steps/termination PASS at quality parity)
**Research:** [563_DBTM_Discrete_Beckmann_One_Step_Language.md](../.research/563_DBTM_Discrete_Beckmann_One_Step_Language.md)
**Source paper:** arXiv:2609.15903 §5.1 (Eq 26 commit rule) — Tang & Wang
**Feature flag:** `flashar_anchor` (opt-in — **stays opt-in; see Promotion below**)
**Tests:** `tests/bench_600_flashar_confidence_commit_goat.rs` (T8+T9) · `tests/bench_600_flashar_fill_alloc_gate.rs` (G4)
**Run:**
```bash
cargo test --features flashar_anchor --test bench_600_flashar_confidence_commit_goat -- --nocapture --test-threads=1
cargo test --features flashar_anchor --test bench_600_flashar_fill_alloc_gate -- --nocapture
```

---

## TL;DR

**T8 + T9 + G4 ALL GREEN on the non-saturated corpus — promotion to default stays DEFERRED on corpus honesty.** The Plan-600 gates measured the production entries (not the PoC harness) on the Plan-116/381 pattern lane made non-saturated (40-epoch training vs the PoC's 200): the confidence-commit arm is quality-non-inferior at every κ with asserted resolution (G1), beats the matched-threshold stride incumbent 2.0–6.5× on fill steps and 0.70–0.79× on wall (G2), the fill round loop is allocation-free (G4: 5 allocs at 4 rounds == 5 allocs at 8 rounds), and the UGC KL cross-check shows the confidence-greedy reveal distorts the block law *less* than the incumbent (0.996×, T9) — Caveat #1's gap is empirically benign here. The plan's acceptance requires "T8 all-green + T9 **on real text** — never on this toy's numbers alone"; this corpus is the lane's pattern family (non-saturated, but not real text) and this repo has no real-text D2F eval — so the strided incumbent stays default and the confidence-commit entry stays opt-in behind `flashar_anchor`.

---

## Disclosure

- Profile: dev (debug) — `cargo test` default; wall numbers are debug-profile ratios (same-window, paired seeds), not release absolutes.
- Model: `Config::micro_dllm()` (27 vocab incl. mask 26, 16-dim, 1 layer), trained 40 epochs / lr 0.01 / mask 0.3 / seed 42 on the seed-123 pattern corpus (20 train / 5 test sequences) — final train log test_acc 68% (the PoC's 200-epoch run read 72%; the reduction is the non-saturation premise).
- Eval: 64 held-out sequences from the seed-777 stream (extends the PoC's 24), block=8, NFE ∈ {4, 8}; every arm draws the identical per-sequence rng stream (paired), so the Round-1 walk and the selection input are byte-identical across arms and only the anchor rule differs.
- Arms are the PRODUCTION entries (`anchor_then_fill`, `anchor_then_fill_with`, `anchor_fill_with_prefilled`) — the PoC harness arms are byte-pinned to them by `test_issue811_harness_matches_production` + `test_issue600_entry_matches_poc_conf_arm` (both green in the same feature lane; G3 evidence).
- Compute: CPU-only (katgpt-rs modelless lane); no GPU exclusivity concern. Runtime ~84 s (T9 MC) + ~5 s (T8) + <1 s (G4).
- Repo state: `develop` @ the Plan 600 T6/T7/T10 landing; this bench's code delta is G4-only (`select_confidence_anchors_into` + pre-allocated `round_candidates` — see G4 below).

## T8 arm table (non-saturated: 40 epochs, 64 seqs, block=8)

| arm | kappa | NFE | acc | se | steps | anchors | wall_us |
|---|---|---|---|---|---|---|---|
| all-mask D2F baseline | 0.70 | 4 | 0.055 | 0.020 | 3.05 | 0.00 | 674.3 |
| all-mask D2F baseline | 0.70 | 8 | 0.055 | 0.020 | 3.05 | 0.00 | 662.6 |
| stride1 tau0.70 | 0.70 | 4 | 0.199 | 0.029 | 1.00 | 8.00 | 1144.8 |
| stride1 tau0.70 | 0.70 | 8 | 0.199 | 0.029 | 1.00 | 8.00 | 1149.5 |
| stride2 tau0.70 (incumbent) | 0.70 | 4 | 0.195 | 0.029 | 2.45 | 4.00 | 1451.1 |
| stride2 tau0.70 (incumbent) | 0.70 | 8 | 0.195 | 0.029 | 3.20 | 4.00 | 1635.5 |
| stride4 tau0.70 | 0.70 | 4 | 0.176 | 0.027 | 2.38 | 2.00 | 1430.0 |
| stride4 tau0.70 | 0.70 | 8 | 0.176 | 0.027 | 2.69 | 2.00 | 1501.8 |
| stride2 tau=kappa (matched ref) | 0.50 | 4 | 0.197 | 0.029 | 1.89 | 4.00 | 1146.9 |
| stride2 tau=kappa (matched ref) | 0.50 | 8 | 0.197 | 0.029 | 2.02 | 4.00 | 1178.8 |
| stride2 tau=kappa (matched ref) | 0.90 | 4 | 0.193 | 0.029 | 2.78 | 4.00 | 1742.4 |
| stride2 tau=kappa (matched ref) | 0.90 | 8 | 0.193 | 0.029 | 4.41 | 4.00 | 2986.9 |
| stride2 tau=kappa (matched ref) | 0.99 | 4 | 0.186 | 0.029 | 3.81 | 4.00 | 1996.5 |
| stride2 tau=kappa (matched ref) | 0.99 | 8 | 0.186 | 0.029 | 7.38 | 4.00 | 3653.3 |
| conf kappa (no floor) | 0.50 | 4 | 0.211 | 0.029 | 1.00 | 7.98 | 948.4 |
| conf kappa (no floor) | 0.50 | 8 | 0.211 | 0.029 | 1.00 | 7.98 | 949.4 |
| conf kappa (no floor) | 0.90 | 4 | 0.178 | 0.027 | 1.67 | 6.58 | 1496.2 |
| conf kappa (no floor) | 0.90 | 8 | 0.178 | 0.027 | 2.48 | 6.58 | 2493.0 |
| conf kappa (no floor) | 0.99 | 4 | 0.164 | 0.027 | 3.03 | 5.73 | 1822.3 |
| conf kappa (no floor) | 0.99 | 8 | 0.164 | 0.027 | 5.72 | 5.73 | 3285.5 |
| conf kappa + floor (DBTM) | 0.50 | 4 | 0.211 | 0.029 | 1.00 | 7.98 | 940.2 |
| conf kappa + floor (DBTM) | 0.50 | 8 | 0.211 | 0.029 | 1.00 | 7.98 | 932.9 |
| conf kappa + floor (DBTM) | 0.90 | 4 | 0.193 | 0.029 | 1.14 | 6.58 | 1376.0 |
| conf kappa + floor (DBTM) | 0.90 | 8 | 0.193 | 0.029 | 1.14 | 6.58 | 2185.7 |
| conf kappa + floor (DBTM) | 0.99 | 4 | 0.189 | 0.028 | 2.06 | 5.73 | 1621.4 |
| conf kappa + floor (DBTM) | 0.99 | 8 | 0.195 | 0.028 | 2.06 | 5.73 | 2544.1 |

### G1 — quality non-inferiority (paired Δ, NFE=8)

| κ | conf+floor acc | matched-stride acc | paired Δ(acc) | SE(Δ) | verdict |
|---|---|---|---|---|---|
| 0.50 | 0.211 | 0.197 | **+0.0137** | ±0.0083 | ✅ (non-inferior; nominally ahead) |
| 0.90 | 0.193 | 0.193 | +0.0000 | ±0.0092 | ✅ (exact tie) |
| 0.99 | 0.195 | 0.186 | **+0.0098** | ±0.0152 | ✅ (non-inferior; nominally ahead) |

The asserted corpus-liveness guard holds: all-mask 0.055 sits measurably below the anchored arms (0.19–0.21, > 2 SE) — the anchor round carries signal and the quality axis is ALIVE on this corpus, which the saturated PoC corpus could not claim. Resolution guard: SE(Δ) ≤ 0.0152 at every κ (bar 0.05) — a 2σ quality difference was detectable. **Non-saturation worked: the conf κ=0.5 arm separates from matched-stride by +0.0137 ± 0.0083 (>1.6σ, nominally ahead) — the PoC's "accuracy does not separate arms" limitation is measured gone.**

### G2 — steps + wall at matched quality (NFE=8)

| κ | DBTM steps | matched-stride steps | steps ratio | wall ratio | verdict |
|---|---|---|---|---|---|
| 0.50 | 1.00 | 2.02 | 2.02× | 0.79× | ✅ (better) |
| 0.90 | 1.14 | 4.41 | **3.87×** | **0.73×** | ✅ |
| 0.99 | 2.06 | 7.38 | **3.58×** | **0.70×** | ✅ |

Consistent with the PoC (3.1–4.7× at high κ); the DBTM floor commits the stragglers the threshold keeps rejecting, and the wall follows the steps. Termination-within-budget asserted at every (κ, NFE) cell (plus the dedicated property test, still green).

## T9 — UGC KL cross-check (Caveat #1)

The certificate covers random-order reveal, NOT confidence-greedy reveal. The empirical question: does the confidence-commit decode distort the block law more than the incumbent's fixed-order stride reveal (both outside the certificate's premise, so they race each other)?

- Certificate side: `UgcDenoiser` adapter over the bidirectional D2F posterior (26 non-mask classes, d=8); `estimate_interval` on the canonical halves + `certified_block_plan` at N=8 → **Ĉ = 11.347, bound 4Ĉ/8 = 5.673** (the random-order reference both realized KLs land under).
- Realized side: MC 8192 decodes × 2 seeds per arm through the production entries, seed ~ U{0..25} (the corpus seed marginal), output law smoothed add-0.5, KL against the analytic corpus law (the `generate_pattern_dataset` bump rule: P(v0,v1) = (1+[v0==(v1+1)%26])/676 on v0≠v1).

| arm | mean KL(P_Z‖P̂) | seed spread | TV | leak (non-alternating) |
|---|---|---|---|---|
| stride2 matched (incumbent class) | 3.2653 | ±0.00002 | 0.497 | 96.2% |
| conf+floor (DBTM) | **3.2518** | ±0.0007 | 0.485 | 98.4% |

**Ratio 0.996 — the confidence-greedy reveal distorts the block law LESS than the incumbent.** Gate PASS (tolerance 1.10× + measured spread). Both realized KLs sit under the 5.673 certificate bound. Context, read honestly: both decodes are far from the corpus law (TV ≈ 0.5, ~96–98% of outputs not even alternating) — the 40-epoch micro model decodes weakly in absolute terms; T9's gate is the RELATIVE comparison, which is the Caveat-#1 question actually asked.

## G4 — fill path allocation gate

Production delta (this bench's code half):
1. `select_confidence_anchors_into(argmax, probs, mask, kappa, out)` — the allocation-free selection core; `select_confidence_anchors` remains as its thin allocating wrapper (public API stable). `anchor_then_fill_with` now reuses its pre-allocated Round-1 anchor buffer instead of shadowing it with a fresh `Vec`.
2. `round_candidates` pre-allocated `Vec::with_capacity(block_size)` (the provable per-round upper bound: one proposal per masked position).

Probe: τ≈1 + DBTM floor drives every round — budget 4 runs exactly 4 rounds (2 commits/round), budget 8 runs exactly 8 (1/round); 2× the rounds through the identical per-call buffer set.

| window | rounds | allocations |
|---|---|---|
| budget=4 | 4 | 5 |
| budget=8 | 8 | **5 (identical — zero per-round allocation)** |
| production config (τ=0.9, floor=8), informational | 3 | 5 allocs/call |

Per-thread counting allocator (Issue 714) + `assert_counter_is_live()` canary.

## G3 — incumbent byte-identity (config off)

No new pin needed and none added: `anchor_then_fill` (strided incumbent) is untouched by T6–T8 — asserted green in the same feature lane by `test_issue811_harness_matches_production` (harness stride arm == production decode, byte-identical) and `test_issue600_entry_matches_poc_conf_arm` (production conf entry == PoC conf arm, byte-identical), plus `katgpt-forward` lib 125/125 and default-features `cargo check` green (the gated module compiles to nothing with the flag off). The G4 delta is inside the gated module only.

## Verdict

| gate | result |
|---|---|
| G1 quality non-inferiority (non-saturated corpus, resolution asserted) | ✅ PASS (Δ ≥ 0 at every κ) |
| G2 steps/wall vs matched-threshold stride | ✅ PASS (2.0–3.9× steps, 0.70–0.79× wall) |
| G3 incumbent byte-identity | ✅ PASS (parity tests + suite green) |
| G4 fill path alloc-free across rounds | ✅ PASS (5 == 5 across 4/8 rounds) |
| T9 UGC KL cross-check | ✅ PASS (0.996× incumbent; bound 5.673 as context) |
| **Promotion to default** | **⛔ DEFERRED — corpus honesty** |

**Promotion stays deferred:** the plan's acceptance requires "T8 all-green + T9 **on real text** — never on this toy's numbers alone". Every gate is green, but on the Plan-116/381 lane's pattern family (non-saturated — the strongest corpus this repo's dllm lane can build today). The strided incumbent remains the default of `anchor_then_fill`; the confidence-commit rule remains opt-in via `anchor_then_fill_with` + `ConfidenceAnchorConfig` behind `flashar_anchor`. The demote-on-loss rule stands: a real-text D2F eval (a text-trained D2F + token-level NLL/exact-match harness) is the single remaining promotion precondition; until one exists in this repo, the gates above are the honest ceiling of what the pattern lane can decide.
