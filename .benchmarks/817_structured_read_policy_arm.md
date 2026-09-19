# Bench 817 — Issue 859 T5: the entropy-gated re-read policy arm (M3), measured on the trained fixture

**Status:** MEASUREMENT COMPLETE (not a GOAT gate — the AUROC comparison is the research question; both outcomes were recordable). Pre-registered prediction HELD, CI-decisive.
**Date:** 2026-09-20
**Box state (the disclosure rule):** the 4090 box (shikuwa, i7-13700K) — CPU-only run (the `micro_dllm_text` micro fixture uses no GPU; the GPU sat at its 306 MiB baseline throughout), release profile, no concurrent cargo (verified before launch), wall **8.0 s** end-to-end. Determinism: an immediate re-run reproduced every figure bit-identically (all seeds pinned: train 42, distractors 7M, sampling 9M, bootstrap 11M).
**Feature:** `structured_reads` (root forward added this commit: `structured_reads = ["dllm", "katgpt-forward/structured_reads"]`).

## The question

Issue 859 T5: **do agreement bars beat single-read entropy as a confidence proxy?** — the reference protocol (Research 574 §8) fires reads=4 where H1 > 0.1 at temperature 1 and reports p(want) ± stderr + agreement as first-class outputs. Instantiated on OUR primitive (`structured_read` + `sample_label_index`, N=4, t=1.0 — the reference's numbers) against ground truth from the held-out Austen eval window.

Pre-registered prediction (defend-wrong, written into the harness header before the run): on a deterministic forward, correctness is a deterministic function of the readout and sample draws are conditionally independent of correctness given the readout — agreement is a noisy finite-sample estimator of functionals the readout already carries exactly. Predicted: AUROC(agreement) < AUROC(maxprob) ≈ AUROC(−H1).

## Protocol

- Fixture: bench-601's exact recipe — `Config::micro_dllm_text()`, 2048 train / 512 held-out eval blocks (disjoint windows), 40 epochs, lr 0.01, mask ratio 0.3, seed 42. **Corpus honesty asserted: masked NLL 2.4867 < unigram entropy 2.8884 nats** (below the floor the marginals contain).
- Canvas shapes: S1 = one masked position (9/block); S3 = three contiguous masked positions (starts {0,3,6} — 33% masked, the training corruption density).
- Label arms: **A** = 4-option per slot (truth + 3 uniform seeded distractors; S3 reads over the union set, 3..=12 options — the multi-field decision form); **B** = full 31-token alphabet (the free-decode shape).
- 9216 items per arm; signals per item: H1 (`label_entropy`), maxprob (`argmax_label_prob`), agreement (fraction of 4 samples = first-read argmax), correctness, sampled correctness.
- Metrics: midrank AUROC (tie-safe); paired bootstrap over items (5k reps) for ΔAUROC 95% CIs; selective accuracy at 80/90% coverage; the M3 gate table. Instrument self-check test with known-answer vectors (perfect/anti/all-tied/midrank-tie/single-class + selective-accuracy + percentile interpolation).

## Results

**Arm A — option-set (corpora mirror):** argmax acc 50.3% (S1 69.4% / S3 31.1%), sampled(t=1) acc 41.5%, mean H1 1.188 nats.

| Signal | AUROC | selective @80% / @90% |
|---|---|---|
| −H1 (single-read entropy) | **0.7807** | 57.3% / 53.6% |
| maxprob (single-read) | 0.7728 | 57.3% / 53.8% |
| agreement (4 re-reads) | 0.7004 | 55.4% / 52.8% |

Paired bootstrap 95% CIs: **Δ(agree−(−H1)) [−0.0893, −0.0714]** · Δ(agree−maxp) [−0.0808, −0.0640] · Δ(maxp−(−H1)) [−0.0119, −0.0040].

**Arm B — full-alphabet (31 options):** argmax acc 26.4% (S1 30.9% / S3 22.0%), sampled acc 15.1%, mean H1 2.502 nats.

| Signal | AUROC | selective @80% / @90% |
|---|---|---|
| maxprob (single-read) | **0.6930** | 29.6% / 28.0% |
| −H1 (single-read entropy) | 0.6724 | 28.8% / 27.5% |
| agreement (4 re-reads) | 0.6298 | 28.4% / 27.3% |

Paired bootstrap 95% CIs: Δ(agree−(−H1)) [−0.0555, −0.0298] · Δ(agree−maxp) [−0.0755, −0.0513] · **Δ(maxp−(−H1)) [+0.0151, +0.0262]**.

**M3 gate** (re-reads where H1 > τ; cost 1 + 3 × gate rate): gate rates 97.8/96.2/93.6/88.1% (arm A) and 99.8→99.2% (arm B) at τ = 0.05/0.1/0.2/0.4 — on this fixture the gate fires almost everywhere (mean reads 3.6–4.0), and **on every gated subset the ordering is unchanged**: agreement below both analytic signals by wide margins (e.g. arm A τ=0.1 gated: −H1 0.7631 · maxprob 0.7546 · agreement 0.6800).

## Findings

1. **Agreement bars do NOT beat single-read entropy — decisively.** Worse in both arms, every gate subset, CIs excluding 0 by ~4–10× their margin-to-zero. The prediction held exactly: on a deterministic forward, re-read samples carry no information about correctness beyond the readout, and N=4 binomial noise strictly degrades ranking. The M3 gate buys error BARS (a display/calibration quantity), never discrimination.
2. **Entropy vs maxprob resolves by option-set width** — the genuinely open sub-question:
   - narrow sets (4–12 options): −H1 ≥ maxprob (Δ CI [−0.0119, −0.0040] — entropy marginally better);
   - wide sets (31 options): **maxprob > −H1** (Δ CI [+0.0151, +0.0262]) — tail mass over many near-zero options dilutes entropy while maxprob measures argmax concentration directly.
   - Deployable guidance for `structured_read` consumers: confidence = `label_entropy` on narrow option sets; `argmax_label_prob` on wide ones (and it is never worse than −0.012 AUROC either way).
3. **Sampled deployment costs accuracy**: temperature-1 sampled answers lose 8.8pp (arm A) / 11.3pp (arm B) vs argmax — the price of stochastic answers; maxprob/entropy remain the confidence for that regime too.
4. **The reference's re-read value must live in stochastic-forward variance, not in sampling** — our control arm shows resampling a fixed distribution adds nothing; where the reference COULD differ is per-read forward stochasticity (e.g. diffusion noise per step). The reference-side proxy re-run (persisting per-item answers + first-read H1 + agreement) remains the optional follow-up, data-spec in Research 574 §8's note — not promotion-blocking.

## Promotion decision (Issue 859 T6)

**`structured_reads` STAYS OPT-IN — evidence-banked, re-arm = first production consumer.** The Feature-Flag-Discipline conditions are MET (GOAT G1–G4 PASS, Bench 816; modelless gain — 0.46× full-loop latency, exact full-marginal readouts, alloc-free; accuracy axis now measured here), but promotion to default-on is declined on layer posture: `katgpt-forward`'s `default = []` is deliberately minimal, `structured_reads = ["dllm"]` would drag the whole D2F stack into every default build of the crate, and the primitive has zero production consumers today (POC landed 2026-09-20). Same shape as the flashar_anchor precedent (GOAT green, feature stays opt-in, blessed defaults recorded inside the seam). The root feature forward added in this commit makes the lane consumable without flag archaeology — the promotion itself is one line when a consumer appears.

## Files

- `tests/bench_817_structured_read_policy_arm.rs` — the measurement + instrument self-check
- `Cargo.toml` — root `structured_reads` forward + the `[[test]]` required-features row
