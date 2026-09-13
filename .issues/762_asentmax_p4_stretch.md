# Issue 762: ASEntmax P4 stretch — HoldConcentration softmax upgrade, Kamath regime detector, per-head grid table, RoPE cutoff spectrum

**Status:** OPEN — T0 re-measure DONE (2026-09-13, Bench 713 long-context addendum: σ̂ saturates 0.35 < σ≥1 regime → T4.3/T4.4 stay deferred; T0.1 promotion-review OWNER-GATED). Stretch backlog; no owner priority on the remainder.
**Origin:** Issue 747 P4 (resolved + removed; full record in git history `.issues/747_asentmax_modelless_mining.md`) · **Research:** [katgpt-rs/.research/549](../.research/549_ASEntmax_Length_Adaptive_Entmax_Attention.md) · **Evidence base:** Bench 713 (+ P1/P2/P3/P0.7 addenda).

The real-model harness landed at Issue 747 P0.7 is reusable for every task
below: `crates/katgpt-attn/examples/asentmax_p07_gen_fixture.rs` (in-repo GGUF
reader + Q2_0_g128 dequant + qwen3 prefill of Ternary-Bonsai-8B, PPL-validated
against llama.cpp), the committed 1.16 MB fixture (1856 routing rows / 64
block-summary streams / oracle masses), and the replay gate
`tests/asentmax_p07_realmodel_regate.rs`.

Priority context from P0.7's measured verdict: real routing σ̂ ≈ 0.1409 — an
order below the σ ≥ 1 over-sparsification regime, and the derived schedule
showed NO modelless quality gain on the real path (needle parity 96.3%/96.3%,
oracle-mass −0.017 scheduled; `asentmax_schedule` stays opt-in). T4.3/T4.4
only earn their keep if a real large-σ surface or longer-context regime
(n > 32 blocks) appears — re-measure before building.

**T0 re-measure DONE (2026-09-13, Bench 713 long-context addendum):** the
long-context fixture (11,093 tokens / 173 blocks, same model + prompt shape)
answers the open question — σ̂ **climbs with n (0.14 → 0.35) but saturates
below the σ ≥ 1 regime** at every measured bucket (8 → 173): the T4.3/T4.4
premise surface does NOT exist on real paths even at 173 blocks, so both stay
deferred. Second finding: raw support erodes in coverage terms at large n
(flat ~5 blocks vs a 5.4× candidate set; covered mass 0.46–0.57) while the
scheduled arm scales support and wins mean oracle-mass at every n ≥ 24
(+0.034 overall, +0.05–0.07 at n ≥ 64) and doubles deep-needle top-8
retention — budget-confounded (support 2.1×), recorded honestly in the bench;
see T0.1 for the reopen condition.

## Tasks

- [x] **T0** Long-context re-measure (the "re-measure before building"
  prerequisite): committed 173-block fixture + `asentmax_long_context_regate`
  gate (5 tests: σ̂ trend, support/mass vs n, deep needle, latency at n≥96).
  Evidence: Bench 713 long-context addendum (2026-09-13).
- [ ] **T0.1** Promotion-review decision (OWNER-GATED): `asentmax_schedule`
  stays opt-in, but the long-context re-measure qualified the P0.7 "no gain"
  verdict — scheduled wins oracle-mass at every n ≥ 24 (+0.034 mean) and
  deep-needle top-8 retention 2× (59.3% vs 29.6%), latency +2.7%. Reopen condition
  (measurable): an equal-budget recall axis or the P1 derived-k controller
  comparison must show the SELECTION (not just the 2.1× support size) wins
  before any default-on proposal. Options: (a) close as stays-opt-in with the
  recorded condition, (b) fund the equal-budget axis (small: one metric in
  the long gate), (c) propose default-on for long-context profiles only.
- [ ] **T4.1** `SsmaxMode::HoldConcentration{c,k}` — analytic `θ*(n) = Δ̂/ln((n−k)c/(k(1−c)))` from Lemma 2's softmax side (upgrades shipped SSMax with the exact coefficient).
- [ ] **T4.2** Kamath range-law detector `ρ = Δ̂/(2σ̂√(2 log n))` (Gaussian vs spiked regime) + normalized-entropy dispersion diagnostic `H(p)/log n` (O(s) over support) — `katgpt-core` estimator module beside ssmax.
- [ ] **T4.3** Offline per-head (β,γ) grid sweep (frozen table, freeze/thaw-versioned) — only if the derived γ=−0.5 default passes P0 and a swept fit demonstrably beats it; harvested constants may also arrive from riir-train Plan 396 Ph2. **T0 verdict: stays deferred — the σ ≥ 1 regime does not appear at n ≤ 173 (σ̂ saturates 0.35).**
- [ ] **T4.4** Prop 7/8 RoPE cutoff spectrum — retention must respect periodic re-entry windows (window union, not first cutoff). **Stretch (unchanged).**
