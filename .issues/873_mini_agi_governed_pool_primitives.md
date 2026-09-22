# 873 — Governed paged pool primitives from mini-AGI (admission / rate_control / dying)

**Status:** OPEN — three katgpt-core primitive candidates, opt-in features, GOAT-gated before any default promotion. Source: [Research 581](../.research/581_Mini_AGI_Governed_Pool_Modelless.md) (volotat/mini-AGI @ `96784b7`, MIT). Consumer wiring: riir-ai working sets / `PagedKVCache` / riir-neuron-db `zone_cache`; riir-train [Plan 416](../../riir-train/.plans/416_mini_agi_trunk_lr_plasticity_forgetting_probe.md) consumes B.

Reference evidence (pinned sha, read-only):
- admission policy: `minagi/paged.py:569-714` (`choose_by_demand`, `swap_to`)
- rate controller: `minagi/plasticity.py:63-358`
- dying metric: `minagi/paged.py:284-325`; anti-predictive-gate lesson `paged.py:292-299`

## A. `pool_admission` — hysteresis admission policy

A zero-alloc admission policy for a fixed-size resident set: candidate displaces the weakest *evictable* resident only when its want-score beats it by multiplicative `margin` (×1.10); a newcomer is un-evictable for `dwell` measured from its **admission tick, not last-use tick** (residents are touched every cycle — a last-use clock makes them permanently young and the set can never move); exactly one never-admitted item receives a fair turn per cycle in index order until the sweep terminates for good (re-arms only on growth); the accepted set applies by identity match so load count = true set delta.

- [ ] A1: feature `pool_admission = []` in katgpt-core; generic over caller-supplied want-scores + admission/last-seen ticks + resident set (leaf-clean, no mass-producer dep — the `suspect_indices` house pattern)
- [ ] A2: G1 known-answer vectors — no-movement-on-noise; burst-on-real-shift; newborn immunity; `since`-vs-`last_seen` divergence arm (the clock-correctness law); fair-turn termination + re-arm-on-growth
- [ ] A3: G2 ns/decision bench; G4 alloc-free
- [ ] A4: prior-art arm in the module docs: TinyLFU/W-TinyLFU is the nearest published cousin (frequency-sketch candidate-vs-victim); delta = dwell + since-clock + fair-turn sweep + margin over arbitrary scores (no sketch)

## B. `rate_control` — dual-EWLS effect-size rate controller

Closed-form multiplicative controller: nudge a scale factor by `exp(gain·tanh((v−T_MID)/width))` where `v = min(t_slow, EFFECT·e_slow, EFFECT·e_fast)` from two exponentially-weighted least-squares fits kept as 7 running sums (slow λ≈0.97 supplies significance; fast λ≈0.85 caps stale optimism; no window ⇒ no edge-jump artifacts); the deciding quantity is the **effect size** `e = slope/residual-σ` (t-statistic shrinks its SE with accumulated weight — it measures watch-time, not progress); asymmetric gains AND widths (up 0.005/w0.75 = slow probe; down 0.025/w6.0 = responds to deterioration magnitude); floor/ceiling; confirmed regime-jump step (jump > max(4·se, floor), still > 2·se next obs → ×2 + fit reset).

- [ ] B1: feature `rate_control = []` in katgpt-core; `observe(val, se) -> Option<Note>`, `factor()`, state save/restore
- [ ] B2: constants PINNED (the Issue-033 adaptive-blend negative law — knobs are constants, never adaptive); report-first posture (R135/Bench 047 — gates nothing until evidence volume exists)
- [ ] B3: G1 hand-built signal series known answers: plateau / improving / deteriorating / regime-jump (confirm + discard arms); window-edge-absence arm (no staircase on window rollover)
- [ ] B4: G2 ns/observe; G4 alloc-free
- [ ] B5: consumer A/B — riir-train Plan 416 Phase 2 (vs cosine at fixed budget + regime-change arm)

## C. `dying` — dual-threshold staleness death metric

Per-item death score `d = min(now − last_addressed, own_age)/window` with newborns pinned 0 until trial end (clamping to own age stops a newborn scoring dead from birth); the window's unit conversion self-calibrated from the system's own cumulative counters (mini-AGI's `segments/step`); ONE definition read at TWO thresholds (d ≥ 0.75 = stop growth/feeding; d ≥ 1.0 = delete) so brakes and prunes can never disagree about "dead".

- [ ] C1: extend `kv_eviction` (sibling module if cleaner): the delete-side complement of `UsageRow`'s keep-side `cum_mass/age`
- [ ] C2: G1 falsifier arm — magnitude-vs-recency disagreement fixture (busiest items carry smallest gates; the death metric must rank by recency while magnitude ranks oppositely)
- [ ] C3: G2/G4; consumer adapters recorded (not wired here): riir-neuron-db `shard_compactor` freeze gating, riir-clippy corpus rule retirement (`frontier_report` deliberately never deletes — this is its missing deletion half), belief GC
- [ ] C4: GOAT + promote decision: promote to default only on measured gain; demote losers per the stack-slot rule

## Standing notes

- GOAT gates per katgpt-rs discipline: G1 correctness, G2 perf, G3 no-regression, G4 alloc-free. Bench file lands in `.benchmarks/` on gate run.
- Order: B5 (consumer) can land before/after B1-B4; A and C are independent.
- Closing this issue does NOT wire consumers — consumer repos file their own wiring when scheduled (goat-audit skill before consuming).
