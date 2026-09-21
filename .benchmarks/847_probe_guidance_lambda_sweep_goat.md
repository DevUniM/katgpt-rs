# Bench 847 — Issue 865 T3: the `probe_guidance` λ-sweep GOAT gate (NEGATIVE verdict)

**Status:** RECORD — T3 COMPLETE 2026-09-21. **Verdict: NEGATIVE — the measured
probe-guidance gain is temperature-reachable and within temperature noise;
`probe_guidance` STAYS OPT-IN** (promotion not claimed; the issue's promotion
rule is "only if a modelless gain holds" — it does not, on this lane, yet).
Feature remains fully functional (T1/T2/T2b stand); the negative verdict is
pinned as a regression gate (`tests/probe_guidance_goat.rs`) whose bars FLIP
RED the day guidance genuinely wins, which is the re-open signal.

**Issue:** `.issues/865_probe_guidance_dllm_lane.md` T3 · **Research:**
`.research/578_Probe_Guidance_Language_Flow.md` (arXiv:2609.19356) ·
**Lane:** katgpt-forward `probe_guidance` (T1 seam) + `MlpWeakProbe` (T2a) +
riir-train `weak_probe_train` (T2b trainer — regenerates the committed
fixture byte-identically, G-determ).

## Box state

Apple M3 Max (16 cores), macOS 26.6.2, **release profile** (`--release` — the
gates' mandated profile; also verified: the debug-profile trunk reproduces
the fixture pairing, G0-fixture 0.1892 in debug too — 240 s debug vs 9.8 s
release for the whole target). Pure CPU f32, DETERMINISTIC (fixed seeds end
to end; no timing bars). Load class: sibling agent sessions active in the
same repo during measurement (irrelevant — no timing claims). Eval surface:
256 held-out prompts × 8 decoded positions × 8 resamples = **16 384 decoded
tokens per arm** (SE ≈ 0.5 accuracy points at p ≈ 0.05... measured envelope
is tighter; see G-noise).

## Setup

- Trunk: `Config::micro_dllm()` (1 layer, n_embd 16, vocab 27, mask 26),
  trained seed-for-seed by the root's own `train_mini_dllm` test-helper
  (2048 train / 256 held-out alternating [a,b,…] sequences, 200 epochs,
  mask 0.3) — the exact T2b trainer procedure, so the committed fixture
  artifact pairs with the trunk **every run** (G0-fixture: probe CE on
  kernel-extracted held-out taps = **0.1892** vs uniform ln(27) = 3.2958; a
  stale/mismatched fixture reads ≈ 3.3 and reds with an actionable
  regeneration message).
- Decode: one D2F block of 8 from a 2-token prompt (a + b — the pattern is
  fully determined), τ_conf 0.3, 16 denoise steps, T0 = 2.5.
- **Quality proxy:** structure accuracy — every decoded position has exactly
  one correct token, so accuracy vs held-out ground truth is exact and
  modelless. (Mask residues count wrong; measured mask_frac = 0 everywhere.)
- **Diversity axis:** per-position resample entropy — each prompt decoded
  K=8 times under independent seeds; per-position outcome histograms across
  the K decodes; entropy averaged over positions. This measures how much the
  decode's outcome spreads — the quantity the knob actually turns.
  **Calibration finding:** the issue's draft wording said "unigram-entropy-
  style"; the POOLED outcome histogram is the wrong axis on
  deterministic-structure lanes — the ground truth is itself high-entropy
  (a, b uniform per sequence), so a CORRECT decoder maximizes pooled entropy
  (measured: ≈3.24 nats everywhere, drifting DOWN as accuracy drops at
  λ ≥ 2 — collapse-measuring, polarity inverted). The resample form is the
  fix: same estimator family, per-position support.

## The measured sweep (release, 16 384 tokens/arm)

Guided front at T0 = 2.5 (λ > 1 extrapolates away from the weak side):

| arm | acc | resample-div (nats) |
|---|---|---|
| λ=1 (≡ unguided, G1) | 99.77% | 3.2175 |
| **λ=1.25** | **99.99%** | 3.2171 |
| λ=1.5 | 99.58% | 3.2176 |
| λ=2 | 97.80% | 3.2100 |
| λ=0.75 | 99.53% | 3.2180 |
| λ=0.5 | 98.56% | 3.2136 |

Unguided temperature front:

| T | acc | div |
|---|---|---|
| 3.5 | 99.72% | 3.2178 |
| 2.5 | 99.77% | 3.2175 |
| 1.5 | 99.82% | 3.2176 |
| 1.25 | 99.91% | 3.2176 |
| **1.0** | **100.00%** | 3.2171 |

G-noise control (zero-logit probe — with it the combine is EXACTLY
temperature scaling: `λ·logits + (1−λ)·0 = logits/(T/λ)`):

| λ | acc | Δ vs its own λ=1 |
|---|---|---|
| 1 | 99.77% | — |
| 1.25 | 99.77% | +0.00 |
| 1.5 | 99.78% | +0.01 |
| 2 | 99.91% | +0.13 |

G-bonus control (mean-zero token-0 pull at fixed T — the directionality
check): 99.78 → 99.77 → 99.58 → 99.08 → 98.61% over bonus 0/1/2/4/8 —
**monotone down, −1.17 pts total**: the harness CAN see a followed
direction.

## The verdict, read off the data

1. **G1 PASS** (correctness stands): λ=1 with the trained probe installed is
   bit-identical to unguided, prompt-for-prompt, at the pipeline level, real
   artifact path.
2. **G2a-as-measured**: the guided front's best point (λ=1.25, +0.21 pts at
   lower diversity) beats the unguided same-temperature baseline — but the
   gain sits INSIDE the temperature front's own reach: unguided T=1.0
   achieves 100.00% at the SAME diversity (3.2171).
3. **G2b-as-measured (the promotion question) FAILS**: at matched diversity
   the unguided temperature point (100.00%) dominates the guided point
   (99.99%). The trivial sharpener wins.
4. **The zero-logit control explains most of the λ axis**: with a
   no-information weak side, the combine is exactly temperature scaling by
   λ — accuracy moves in the sharpening direction (+0.13 at λ=2) with no
   probe at all. The trained probe BEAT this null by only +0.21 pts at one
   λ and LOST to it at every other (−0.20 at λ=1.5, −2.11 at λ=2): the
   probe's disagreement direction is worth less than its noise at this
   scale.
5. **The bonus control rules out "the harness can't see signal"**: a known
   direction is followed monotonically (−1.17 pts). The λ sweep's
   non-monotone bumps are therefore real (small) distribution changes, not
   measurement artifacts — they are just not worth anything at matched
   diversity.

**Root cause (mechanistic, consistent with every arm):** the T2b trunk is
trained to loss 0.0000 / 100% train+test accuracy — a saturated one-hot
decoder. The paper's mechanism needs strong−weak DISAGREEMENT to extrapolate
along; here the trained probe (held-out CE 0.2166) is nearly as strong as
the trunk, so the disagreement direction carries ≈ no exploitable
information, and λ>1 mostly amplifies the difference's noise (λ≥2 actively
poisons). The lane is a fair *machinery* qualification (T2's purpose) and an
unfair *mechanism* test (T3's question) — the mechanism verdict needs a
trunk with headroom, which is the Bonsai-scale run.

## Gates shipped (all green, pinned)

`tests/probe_guidance_goat.rs` (required-features `probe_guidance`,
`#[cfg]` belt-and-braces — the Issue 808/856 double protection):

- **G0-fixture** < 0.5 probe CE — the committed artifact can never silently
  rot against the trunk.
- **G1** bit-identity at λ=1 (64 prompts, pipeline level, real artifact).
- **G2a INVERTED**: guided λ* advantage stays ≤ the temperature-noise
  envelope (+0.6 pts, read off the unguided front's own T=3.5 dip, floored
  at the 0.006 measurement SE) — a flip = the promotion case exists.
- **G2b INVERTED**: the matched-diversity unguided point ≥ guided λ* −
  envelope — a flip = guidance genuinely wins at matched diversity.
- **G-noise**: the zero-logit control stays within ±0.6 pts of its own
  baseline at every λ>1 — the no-signal envelope is itself pinned.
- **G-bonus**: directionality control monotone down, ≥ 1 pt total drop.
- (print-only) softening arms λ<1.

`tests/probe_guidance_alloc_gate.rs` (own process, counting allocator):
**G4 PASS — 1,000 probe calls, 0 allocations**; the affine combine itself
indexes pre-existing context buffers only (structural:
`apply_probe_guidance`, reviewed — no allocation sites).

Clippy clean on both targets (`--features probe_guidance`, 0 findings).

## Not run (deferred, with reason)

**The dropout-autoguidance arm** (issue T3's arm (b)): the D2F forward has
no kernel dropout, so "enable dropout at inference for the weak side" has no
substrate to run on — implementing inference-time dropout in the denoise
kernel is real kernel work. Post-verdict it is also MOOT for promotion (the
gate decided negative on the trained-probe arm + controls; a cheaper weak
side would not flip a verdict whose failure mode is "the trunk gives the
weak side nothing to disagree about"). Folded into the Bonsai-scale re-open
scope, where the multi-layer kernel extension is already a prerequisite.
If the lane re-opens, arm (b) should be re-scoped there (owner call).

## Re-open triggers

- The multi-layer kernel extension lands and the Bonsai-scale probe trains
  (riir-train recipe row B) → re-run this gate with a NON-saturated trunk;
  G2a/G2b's inverted bars are the promotion decider, already wired to flip.
- Any change to `train_mini_dllm`, the D2F decode cores, or the combine →
  the gate re-measures the whole verdict automatically (it is deterministic
  and self-contained).
- Fixture drift (trunk change) → G0-fixture reds with the regeneration
  command.
