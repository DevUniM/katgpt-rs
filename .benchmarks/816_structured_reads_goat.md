# Bench 816 — Jev Structured Reads POC GOAT (Issue 859 T3–T5)

**Status:** GOAT G1/G1b/G2/G3/G4 PASS (POC) — opt-in `structured_reads` (katgpt-forward); accuracy axis deferred to the 4090 reference run (T1).
**Date:** 2026-09-20
**Box state (the disclosure rule):** M3 Max, macOS, loadavg 3.8–6 during the run — a riir-train training measurement (`plan335_band_x025.sh`, ~1 core / 19 GB RSS) live throughout; a sibling cargo test had just finished. Latency figures cited with this caveat; the G2 bar (≤1.0) carried 2.2× margin, so the verdict is load-insensitive.
**Feature:** `structured_reads = ["dllm"]` (katgpt-forward), opt-in POC. NOT promoted — promotion rides Issue 859 T1 (4090 reference) + T5 (policy arm).

## The primitive

`structured_read[_into]` — the vLLM PR #57250 Jev contract on our D2F stack, zero new substrate (Research 574 §5 mapping, written before implementing per the substrate-first gate):

- **seed**: fixed schema tokens + `config.mask_token` at free slots (the denoise loop's own skip rule honors pre-seeded positions)
- **one step**: `forward_bidirectional_positions_into` (the identical call `denoise_loop` makes per step)
- **read**: per free slot — argmax over the caller-supplied label list, `logprob(t) = logits[t] − logsumexp(full vocab)` (exact full-marginal; the reference PR's top-k blindness cannot arise), entropy over the subset-NORMALIZED label distribution (the reference reviewer's nit corrected by construction)
- **skip commit**: the canvas is never written (contrast `denoise_loops.rs:188`)

Plus `sample_label_index` (T5 enabler): deterministic re-reads are bit-identical, so agreement bars are only meaningful through temperature > 0 sampling — the analog of the reference's temperature-1 logprob read.

## Gates

| Gate | Claim | Result |
|---|---|---|
| G1 | label logprobs = exact full-marginal values on the same step | ✅ f64 stable-logsumexp cross-check max delta < 1e-5 (test-owned second forward); bit-identity across two calls with fresh scratch |
| G1b | read-only — the canvas is never written | ✅ bit-identical input slice after the call |
| G2 | read-only ≤ full-loop latency, same fixture | ✅ median ratio **0.4588** (min 0.4115 / max 0.5507) over 33 interleaved pairs ×8, `Config::micro_dllm`, 12-token canvas / 4 free slots, vs `denoise_loop` (n_steps=8, threshold 0.3) — release build |
| G3 | existing D2F suite green | ✅ 154/154 (`cargo test -p katgpt-forward --features structured_reads --lib`; default-features check clean) |
| G4 | alloc-free hot path | ✅ 0 allocations across 32 `structured_read_into` calls after scratch construction — canary-armed (the canary must COUNT before the zero is trusted, Issue 741's dead-counter lesson), `--release --features structured_reads,alloc_tracking` |

Three-competitor arm (informational, printed by `tests/structured_read_goat.rs`): step-1 read vs full-loop-then-parse agreement **4/4 (100%) after 1 commit round** at threshold 0.3 — mechanically consistent (the loop commits every slot in the first pass at this threshold, so the step-1 argmax IS the committed answer); mean label entropy 0.4123 nats on the fixture. Random-init weights carry no ground truth — the accuracy axis belongs to the 4090 reference run (T1) per the issue's fallback clause.

## Divergences from the reference (deliberate, recorded)

- **Label logprobs are full-marginal, not top-k-anchored** — our logits rows are direct, so the PR's `logprob_token_ids` workaround shape is unnecessary; the M2 lesson (id-list API, never top-k) is honored by construction.
- **Entropy is subset-normalized** — the PR reviewer's unnormalized-top-set nit is our house rule.
- **Re-read stochasticity is explicit** (`sample_label_index`, temperature > 0) — our forward is deterministic; the reference's re-read variation comes from its temperature-1 sampling, ours must opt in.
- **T1 (4090 reference validation) deferred** — the sibling tap cross-check held 16.8/24.5 GB VRAM; GPU-exclusivity rule + insufficient free VRAM. Re-run when the bench drains.

## Files

- `crates/katgpt-forward/src/structured_read.rs` — the primitive + 5 unit tests (G1/G1b/coherence/validation/sampling)
- `crates/katgpt-forward/tests/structured_read_alloc_check.rs` — G4 (binary-unique counting allocator, the bench_811 convention)
- `crates/katgpt-forward/tests/structured_read_goat.rs` — G2 + the competitor informational arm
- `crates/katgpt-forward/Cargo.toml` — `structured_reads = ["dllm"]` + the `alloc_tracking` forward + two `required-features` rows
