# Bench 850 — the probe-guidance headroom study: arm (b) unblocked, the negative extended (Issue 865 follow-up)

**Status:** RECORD — study COMPLETE 2026-09-22. **Verdict: NEGATIVE EXTENDED.** The
`DropoutHeadProbe` (Bench 847's deferred arm (b), unblocked tap-level — no kernel dropout
needed) ships as the modelless weak side, and the headroom rerun Bench 847's root-cause named
was run under its own methodology: **the mini lane cannot produce a guidance win with any
modelless weak side, in any trunk or decode regime tested.** The Bonsai-scale re-open stands
as the only remaining path. `probe_guidance` stays opt-in.

**Lands:** `DropoutHeadProbe` (katgpt-forward `weak_probe_mlp`, +3 lib tests) — the frozen
trunk head over a deterministically 50%-dropout-masked tap (fixed LCG stream keyed by
`(position, denoise step)`, reproducible, zero runtime RNG, zero-alloc). This dissolves
Bench 847's "Not run" reason for arm (b) ("no kernel dropout substrate" — masking the TAP
needs no kernel work).

**Issue:** katgpt-rs Issue 865 (closed; record trail: Bench 847 + catalog §120 + HISTORY) ·
**Study:** `tests/probe_guidance_headroom_study.rs` (`cargo test --release --features
probe_guidance --test probe_guidance_headroom_study -- --nocapture`; asserts structural
invariants only — λ=1 identity per regime — the fronts are the record).

## Box state

4090 Windows workstation (katop box), **CPU-only study** (pure f32; the GPU is not
involved). Load class: light — ~22% CPU load average, 20 GB free RAM at run time, GPU 22%
(unrelated GUI work). Single-threaded decode, fixed seeds end to end (deterministic; no
timing claims). Debug profile is the recorded run; the release rerun reproduces the
regime-3 verdicts identically (beyond-sharpening deltas byte-equal; 3.3 s release vs
90.6 s debug for the whole study). Eval surface per arm: 256 held-out prompts × 8
positions × 8 resamples = 16 384 decoded tokens; 3 regimes × 21 arms + 2 trunk trainings
per run.

## Methodology — Bench 847's, exactly

Per-position resample entropy (the working diversity axis), the zero-logit null
(`λ·logits + (1−λ)·0 = logits/(T/λ)` — the combine as EXACT temperature scaling, the
no-information envelope), the unguided temperature front as the trivial-sharpener baseline,
and the same-λ beyond-sharpening delta (dropout arm minus null at the same λ — what the
tap-masking adds over pure sharpening). Regimes:

1. **High-data 12-epoch trunk** (2048 seqs, 2-token prompt, τ_conf 0.3 / 16 steps) — the
   "training-loss headroom" cell: test acc 100% by epoch 11 (loss 0.0001).
2. **Low-data 12-epoch trunk** (96 seqs, 8-token prompt, same decode) — test acc 98.7%
   (loss 0.0031).
3. **Low-data trunk + strict decode** (τ_conf 0.7 / 8 steps — the decode_config defaults) —
   the decode-uncertainty cell: the unguided front spans a REAL tradeoff (82.15% → 98.77%
   as T falls 2.5 → 0.4; mask fraction 17.7% → 0.15%).

## Measured (beyond-sharpening deltas: dropout − same-λ null)

| regime | λ=1.25 | λ=1.5 | λ=1.75 | λ=2.0 |
|---|---|---|---|---|
| 1 (high-data) | −0.38 | −0.63 | −0.96 | −1.42 pts |
| 2 (low-data) | −0.15 | −0.27 | −0.32 | −0.50 pts |
| 3 (strict decode) | −0.13 | −0.36 | −0.45 | −0.46 pts |

At matched resample diversity vs the temperature front: one +0.09-pt and one +0.05-pt
point (both inside the ±0.6-pt temperature-noise envelope Bench 847 pinned); every other
point negative (down to −0.61). Full fronts are reproducible from the committed study test.

## Verdict, read off the data

1. **The dropout arm never beats the zero-logit null** — at no λ, in no regime. The
   tap-masking signal is worth less than its own noise: extrapolating along
   `strong − head·masked_tap` injects the mask noise scaled by λ, exactly what the
   beyond-sharpening delta measures.
2. **The headroom hypothesis is refuted at mini scale.** Training-time "headroom"
   (85–99% masked-token test accuracy at 12 epochs) does not survive the decode loop:
   regimes 1–2 decode at 98.5–100%. The one cell where decode-time uncertainty exists
   (regime 3 — manufactured by the strict τ_conf/denoise budget) is ALSO negative: the
   uncertainty there is unstructured (which pattern tokens the sampler commits late),
   carrying no correctable direction a weak side could know better than the trunk.
3. **The preliminary positive that motivated this study is retracted with cause.** An
   earlier in-session run on the regime-3 configuration with the POOLED unigram-entropy
   axis (Bench 847's refuted metric — on deterministic-structure lanes a correct decoder
   MAXIMIZES pooled entropy, so the axis measures correctness-collapse, polarity inverted)
   read "+2.7 pts at matched entropy, Pareto-dominates the T=1 default" for this same
   dropout arm. Under the resample-entropy axis + the null, that gain is entirely
   explained as sharpening-adjacent redistribution along the correctness axis the pooled
   metric secretly measures. The retraction is the axis lesson's second measured instance.

## What survives

- `DropoutHeadProbe` itself: correct, deterministic, zero-alloc, 8 lib tests green (the
  3 new ones + the module's 5). It remains the modelless weak side for lanes that DO have
  structured decode uncertainty (the class the Bonsai-scale re-open targets) — nothing in
  this study measures anything against such a lane; it measures the mini pattern lane.
- The mechanism machinery (T1/T2 wire + loaders) is unaffected: G1-style λ=1 identity
  held in every regime of this study as well.
- **The re-open condition is sharpened, not just repeated**: the mini lane is now measured
  structurally incapable of the win (three trunk/decode regimes, the null beating every
  modelless weak side at every λ). The Bonsai-scale run does not need another mini-scale
  attempt — it needs a lane whose decode uncertainty is structured (natural text), which
  is the multi-layer kernel extension + the riir-train recipe-row-B loop.

## Re-open triggers (inherited from Bench 847, now with this study closed)

- Multi-layer kernel extension + Bonsai-scale trained probe (riir-train recipe row B) →
  rerun the Bench-847 gate on that lane; its inverted bars remain the promotion decider.
- This study's test doubles as the cheap mini-scale tripwire for any future weak-side
  change: its printed fronts re-measure the three regimes deterministically.
