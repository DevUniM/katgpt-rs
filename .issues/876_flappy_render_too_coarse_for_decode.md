# Issue 876 — flappy v2 render is too coarse for decode-based consumption (Bench 881 finding)

**Status:** OPEN — filed 2026-09-23 from katgpt-rs Plan 607 T2 (Bench 881).

## The finding

The T2 losslessness arm (Bench 881) measured the sentence-arm vs
structured-arm agreement delta across all three arenas. Flappy is the
lossy one, at maximum severity:

- structured arm (8 exact features): **96/100** in-corpus = LOO
- decoded arm (sentence-only input): **77/100** — Δ −19 — with **ONE
  distinct pick**: the arm degenerates to constant-flap, which ties the
  constant-pick baseline exactly (77). Discrimination floor FAIL.

The `laya-flappy-v2` grammar renders the post-placement POSITION BAND
alone (7 bands) — the v1 motion clause was removed as a measured wording
confound (Bench 880). The band drops what the structured head actually
reads: exact post_rel (linear), post_v, in_gap, edge_margin. Pre-rel is
banded 5 ways; pre-v and gap-half recover exactly. What remains is not
enough for the ridge head to beat constant-pick at imitating laya.

The decoder is NOT the defect: all 200 option + 100 state sentences
decode exactly (re-render byte-identical, fills == semantic forward,
v/h exact). The RENDER is the bottleneck — exactly the branch T2's
"(a) a non-zero delta is a finding about the RENDER" anticipated.

## The work item (render-side, never a decoder fix)

Widen `laya-flappy-v2` → v3 with decision-relevant, non-value-loaded
clauses — the two candidates the structured head's weights say matter:

1. a quantized OFFSET clause ("just under the center / under the center /
   at the center / over the center / just over the center") — recovers
   fine post_rel without raw numbers;
2. a NEUTRAL motion clause for the post-placement velocity — the v1
   wording was a confound because "rising" read as safe REGARDLESS of
   position; a v3 motion clause must be value-neutral or position-anchored
   (e.g. "holding this height" vs "drifting down one step").

Then: regenerate the oracle fixture (riir-reflex `laya_oracle_batch`,
G5-parity lane, isolated worktree), re-fit both arms, and demand the
decoded arm beat constant-pick with ≥ 2 distinct picks BEFORE any
decode-based consumer is considered on flappy. The grammar-closure and
no-digits tests must hold.

## Non-goals

- No decoder change — `template_decode` is correct by the Bench 881
  decode-layer assertions.
- No tuning against the oracle — the render widening changes the
  INFORMATION the grammar carries, not the scorer's knobs; the scorer
  recipe stays frozen (same standardize → LOO-λ → fit path).

📖 katgpt-rs Plan 607 T2 · Bench 881 · Catalog §125.
