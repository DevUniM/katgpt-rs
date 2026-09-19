# Issue 859 — Jev structured reads: 4090 open-reference validation + read-only seeded-canvas read primitive POC

**Status:** OPEN — research-derived POC (Research 574; the vLLM open reference of the Jev contract Research 562/573 track). No code yet. Owner-routed to the 4090.

## Why

vLLM PR #57250 (unmerged, `ready`) turns DiffusionGemma into a Jev-style structured-decision server: seed canvas → ONE denoise step → argmax + exact label-id logprobs at free slots → **skip the commit forward**; entropy-gated re-reads ship mean ± bars. Research 574's grep: the **composition is zero-prior-art in-workspace while every component ships** (`canvas_schema` masks, `ac_prefix::conditional_logprob`, `SamplerFeatures` slot stats, D2F denoise stack, `margin_gate`, CalibratedSigmoidGate/810). Two deliverables: (A) validate the open reference on our silicon — numbers as *intel* for Research 573 / riir-clippy Issue 125, never league evidence (different model class + silicon; league absolute-numbers rule); (B) POC the read-only primitive on OUR D2F stack.

## Pinned claim (defend-wrong shape)

`structured_read()` = seed(canvas: fixed schema tokens + single-token free slots) → one denoise step → per-free-slot {argmax, logprob over caller-supplied label-id list, entropy} → return; **no commit forward**. Distinguished from `ac_prefix` (commits; scores for AR drafting) and `diffusion_sampler` (remask confidence inside generation, not a request).

## Tasks

- [ ] 0. Probe the 4090 (Tailscale `100.85.179.44` when remote; LAN timed out this session): reachability, vLLM install/version, free VRAM, no sibling compute job (GPU-exclusivity rule)
- [ ] 1. **Reference validation**: clone `mmastrac/vllm@structured-reads-main` (PIN sha at clone), serve `nvidia/diffusiongemma-26B-A4B-it-NVFP4` (`--diffusion-config '{"canvas_length": 32}'`); if the SM89 NVFP4-marlin bf16 garble fires → `--dtype float16`; run `examples/features/diffusion_reads/structured_server.py`; reproduce the programming-language + unit-comparison corpora; record req/s + accuracy + reads-per-decision on OUR box into Research 574 (intel table, separate from league cells)
- [ ] 2. **Substrate read (substrate-first, before any code)**: `katgpt-forward` `denoise_loops.rs`/`d2f_verifier.rs`/`diffusion_sampler.rs` + `katgpt-core` `canvas/` + `ac_prefix/` — map seed/read/skip-commit onto them; write the mapping row into Research 574 before implementing
- [ ] 3. **POC primitive** behind a feature flag: `structured_read()` per the pinned claim; label-id list API (the M2 lesson — never top-k); entropy over the NORMALIZED label distribution (the PR reviewer's nit is our house rule)
- [ ] 4. **GOAT gates** (three competitors per §3.6: read-only read vs full-loop-then-parse vs AR constrained decode): G1 label logprobs from the read path bit-identical to a full-marginal reference on the same step; G2 read-only ≤ full loop latency on the same fixture; G3 existing D2F tests green; G4 alloc-free hot path; any *calibration*/uncertainty claim (entropy bars, re-read agreement) benchmanced against the conformal-naive floor (UQ-bearing rule, Research 322)
- [ ] 5. Entropy-gated re-read policy arm (M3: H1 > τ → N re-reads, mean ± bars) — measure whether agreement bars beat single-read entropy as a confidence proxy on the fixture corpus
- [ ] 6. Numbers + verdict into Research 574; if GOAT → plan for promotion decision; close this issue under the noise-reduction rule with the commit hash

## Fallbacks / risks

- NVFP4-marlin on SM89 = workaround path (known bf16 bug; float16 dtype); if unrunnable: skip T1 (defer reference validation to a fp8/fp16 community quant or `pst2154/Nemotron_Jev` dense variant becoming runnable) and do T2–T5 on CPU/small fixtures.
- PR is UNMERGED and moving (5 prerequisite PRs split out; head `58aacf2` page-derived) — re-pin at clone; the API surface (`vllm_xargs`) may shift before landing.
- DGX Spark numbers are NOT headroom evidence for us; only same-box cells from T1 count as intel.
- Do not touch the perf league: no cell in `perf_rematch_league.md` moves for a diffusion-LM decision mode.
