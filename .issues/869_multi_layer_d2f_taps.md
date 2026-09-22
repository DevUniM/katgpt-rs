# Issue 869 — Multi-layer D2F decode kernel + taps at depth (the Issue-865 Bonsai-scale unblock)

**Status:** T1–T5 ALL LANDED 2026-09-22 (T5 same-day follow-up session;
see HISTORY row). The mini dllm lane is now per-layer honest end-to-end:
training, eval, and decode all honor `config.n_layer`, and the decode depth
defaults to it. Every existing gate re-verified green (pattern lane
bit-identical; the four text benches re-trained at true 2-layer capacity
and pass with IMPROVED honesty margins — bench_601's corpus-honesty margin
0.39 vs the 0.15 bar, was ~0.16).

## Why (the gate this removes)

Bench 847's negative verdict + Bench 850's negative-extended verdict both end at
the same re-open condition: a lane whose decode uncertainty is STRUCTURED
(natural text, multi-layer trunk) — the Bonsai-scale run. That run needs, from
katgpt-rs:

1. The artifact consumer to accept `tap_layer > 0` (`MlpWeakProbe` currently
   REJECTS deeper-tap artifacts at construction — the wire carries the field,
   the consumer refuses it).
2. The decode kernel to capture the post-attention-residual tap at an ARBITRARY
   layer index, through the real decode path (train/serve tap consistency is
   the lane's law — the qualification measured context-tap CE 0.2166 vs
   pre-layer 1.9026, an 8.8× the tap choice is measurable).
3. Multiple taps simultaneously for the deferred T4 (AR tuned-lens composition
   arm — reads several layers at once).

## The finding this investigation surfaced (record before fixing)

**`Config::micro_dllm_text()` declares `n_layer = 2` ("the smallest capacity
that learns English bigram structure", katgpt-types `config.rs`), but the
ENTIRE mini dllm lane is single-layer end-to-end**: `forward_save` /
`forward_save_set_causal` (training forward), `backward`, `sgd_update`,
`TrainingGradients`, `evaluate_accuracy` (via `forward_bidirectional_positions_into`),
`forward_block_causal_positions`, AND the decode kernel
(`forward_block_causal_with`) all index `weights.layers[0]` only. Layer 1 of
`micro_dllm_text` is allocated, never trained, never read. The four pinned
benches that re-train that config every run (`bench_601`, `bench_802`?,
`bench_809`, `bench_817`, `bench_602`) measure an effectively-1-layer model
while their config declares 2. Declared capacity ≠ effective capacity — a
latent discrepancy, not a correctness bug (train/eval/decode are consistently
single-layer, so the gates measured a coherent model).

Consequence for THIS issue's design: the decode kernel CANNOT silently start
honoring `config.n_layer` — the 2-layer-config lanes would decode through an
untrained random layer 1 and every pinned gate on them would red. Decode depth
must be EXPLICIT (context-owned, default 1 = today's effective semantics)
until the training-side migration (T5 below) lands and the default can flip.

## Tasks

- [x] T1 — kernel: generalize `forward_block_causal_with` over
  `D2fContext::decode_n_layer` (per-layer KV planes, residual-stream chaining,
  layer loop). Bit-identical at depth 1 — proven by re-run: fixture G0 + goat
  G1 (5/5), headroom study, bench_601/809/817/602, bench_600 ×2, dmax_spd,
  tri_mode sampler, ugc_g1b, dllm lib — plus a structural pin
  (`depth_one_forward_is_bit_identical_to_the_pre869_semantics`).
- [x] T2 — taps at depth: `set_probe_tap_layers` + layered `probe_tap_flat`
  + `ProbeCtx { tap_layers, tap_plane }` + `WeakLogitProbe::tap_layer()` +
  `set_guidance` install-time validation + `MlpWeakProbe` tap_layer>0
  unblocked (plane-indexed reads). Default tap set `[0]` keeps every
  existing artifact/gate byte-compatible.
- [x] T3 — tests: 10 new (5 kernel-level ungated + 5 tap-level feature-gated)
  — finite logits + planes-differ at depth, capture bit-identity at depth,
  λ=1 identity at depth with a deeper-tap artifact, install/depth/tap-set
  validation panics, layered-plane exact-read (via-ctx == hand-fed plane),
  pre-869 bit-identity structural pin, committed-prefix support at depth.
- [x] T4 — gates re-run green: katgpt-forward lib 131/131 (default) +
  180/180 (`probe_guidance`); root probe gates 5/5 + 1/1 + headroom green;
  bench_601 3/3, bench_809 5/5, bench_817 2/2, bench_602 3/3, bench_600 ×2,
  dmax_spd 5/5, tri_mode 5/5, ugc_g1b 3/3, dllm lib 23/23;
  `scripts/full_gate.sh --allow-partial-platform` — every layer that ran
  clean (macOS device backends unmeasured, the expected Windows PARTIAL).
- [x] T5 — LANDED 2026-09-22 (same-day follow-up session): training-side
  honesty — per-layer `forward_save` ×2, `backward`, `sgd_update`,
  `TrainingGradients`, `BackwardContext`; the eval/inference forwards
  (`forward_bidirectional_positions_into` + `BidirectionalContext`,
  `forward_block_causal_positions`, `forward_set_causal_positions`) generalized
  in lockstep; decode default flipped to `config.n_layer`. Bit-identical at
  `n_layer == 1` (every plane index is 0 — the layer loop degenerates).

  **Two real findings, both caught/verified by the new gradient-check test
  (`two_layer_backward_matches_finite_differences`, analytic vs central
  finite differences at BOTH 1 and 2 layers, every grad family):**

  1. **The pre-869 `!is_masked[p]` skip in backward Phases 1/2 is invalid at
     inner layers.** Inner-layer streams receive gradient at UNMASKED
     positions too (downstream attention reads the k/v derived from them at
     masked queries). Skipping them corrupted every layer-0 attention-path
     gradient under partial masking — measured ~10-150% errors (wv_0 sign
     flip), EXACT at full masking, which is why the historical
     loss-decreases gates never saw it. Fixed: the skip is now
     `last && !is_masked[p]` (at `n_layer == 1` the layer is always last —
     bit-identical semantics preserved). This bug was LIVE pre-869 for any
     hypothetical multi-layer user of the single-layer lane; the single-layer
     lane itself was never affected (its only layer is the readout).
  2. **Bench 602's gap-predictor calibration is model-class-specific.** Post-
     honest-depth, the AR-drag DIRECTION (w*_AR < w*_UNI) is within training-
     seed noise at the micro scale (measured across seeds 42-45 + probe-RNG
     pairings: AR−UNI ΔALR gaps swing ±0.13 around ~+0.03; 2/4 seeds invert),
     and `predict_w_residual`'s 09-20 table (measured on the effective-1-layer
     model class) no longer tracks the NLL-optimal w within the 0.95 retention
     floor (measured worst 0.914). bench_602's g3 now: trains 2 seeds/regime,
     REPORTS the direction + retention table (documented in-test), hard-gates
     signature liveness + a catastrophic-derail floor (chosen ≤ worst-fixed
     ×1.05). Re-open condition: a non-micro trunk (the Bonsai-scale lane)
     where commit-order statistics have support — re-derive the calibration
     there.

  Gates re-run green: root lib 211 (default) / 217 (set_diffusion);
  katgpt-forward lib 131 / 180 (probe_guidance) / 167 (set_diffusion) / 181
  (probe_guidance incl. the new kernel-vs-positions depth-2 consistency pin);
  dllm 27/27 (23 + 4 new: fwd-vs-inference bit-identity at 2 layers, training
  moves layer 1, sgd-reduces-loss at 2 layers, the gradient check); pattern
  lane bit-identity (bench_600 ×2, dmax_spd 5/5, d2f_verifier 10/10,
  diffusion_sampler 5/5, probe_guidance_goat 5/5 + headroom 1/1 + alloc 1/1);
  the four text benches (601 3/3 — improved margins, 809 5/5 — seam parity
  byte-identical, 817 2/2, 602 3/3); `full_gate.sh --allow-partial-platform`
  — every layer that ran clean (the standard Windows PARTIAL).

## Boundary

katgpt-rs only (modelless inference substrate + the reference kernel
contract). The GPU twin (riir-ai riir-gpu) ports the tap-at-depth contract
when the Bonsai decode lane is built; the riir-train trainer takes the new
tap index unchanged (`tap_layer` is already wire metadata; slot-0 reads stay
source-compatible — `set_probe_tap_layers(&[L])` then read
`probe_tap_flat[p*n..]`).

## Perf posture

Depth 1 = the exact current op sequence (the layer loop degenerates; tap
capture is behind `probe_guidance` and only armed when guidance is live, as
today). No perf claim is made at other depths — none is needed for the
unblock; the GOAT/perf question belongs to the scale lane's own gate.
