# Research 565: SentencePiece GGUF Parity — the Unigram Whitespace-Run Bug and the Near-Identity Charsmap

> **Source:** google/sentencepiece @ `b2db4719c3f41e1b0c61dd948c5d8bf445bef1a0` (Apache-2.0; clone per skill §0.5, deleted after pinning — quotes re-verifiable by re-cloning at this sha). Papers: Kudo & Richardson, "SentencePiece" ([arXiv:1808.06226](https://arxiv.org/abs/1808.06226)); Kudo, "Subword Regularization" ([arXiv:1804.10959](https://arxiv.org/abs/1804.10959)).
> **Date:** 2026-09-17
> **Status:** RECORD — verdict GAIN; riir-ai Issue 970 **resolved 2026-09-17** (riir-ai `576bf1ef1`) — and the fix was larger than filed: see §6 Addendum (the shipped path ran the wrong ALGORITHM, not just the wrong whitespace rule). No katgpt-rs issue (restraint — see Row B).
> **Related Research:** 137 (Pplx unigram Viterbi + Datrie — vocab-trie cousin, shipped `datrie_vocab`), 456 (Gigatoken SIMD BPE — vendored `fast_bpe`, Bench 191)
> **Cross-ref (riir-ai):** Issue 400 (SentencePieceGgufTokenizer), Issue 970 (this note's consumer fix), Bench 780 (unigram Viterbi mode), Bench 723 (C++ dep containment)
> **Classification:** Public

---

## TL;DR

SentencePiece is the upstream reference for two things our stack already implements independently — unigram Viterbi segmentation (`SentencePieceGgufTokenizer::encode_unigram`, riir-ai Issue 400 + Bench 780) and BPE merges (`fast_bpe`, Bench 191). Distilling the reference against our implementation with the file-based oracle (`riir-train/data/tokenizer.model` via the sentencepiece Python API) found **one real, measured parity bug**: our unigram normalizer hardcodes the *generic* SentencePiece whitespace defaults (collapse interior runs, strip leading/trailing), while gemma-2's model normalizer is **pure space-escaping** — every `0x20`→`▁`, nothing else — with the vocab itself carrying run pieces (`▁`, `▁▁`, `▁▁▁`). Every multi-space input therefore tokenizes wrong on our GGUF serving path. Second finding, correcting this session's own initial hypothesis: **gemma-2's precompiled charsmap is near-identity** (NBSP, ideographic space, ZWSP, BOM, full-width, decomposed é, Thai SARA AM all pass through raw) — a generic NFKC prepass would *introduce* divergence, and the missing `precompiled_charsmap` GGUF field is harmless for this model family. Verdict: **GAIN** — one measured bug fix (riir-ai Issue 970), everything else recorded with explicit reopen triggers.

**Distilled for katgpt-rs (modelless, inference-time):**
A tokenizer-parity methodology + golden fixture set (measured 2026-09-17, ids below): the *normalizer spec* (`remove_extra_whitespaces`, `add_dummy_prefix`, charsmap) is per-model configuration, not a constant — GGUF converters mirror only `add_dummy_prefix` (as `add_space_prefix`), so the other axes must be pinned per model family from the reference oracle, and multi-space inputs are the fixture class that exposes them. No new primitive filed for katgpt-tokenizer: the Darts-clone charsmap-blob consumer has no live consumer once gemma-2's map is measured near-identity (Row B records the recipe + reopen trigger).

---

## 1. What the source ships (coverage map)

| SentencePiece surface | Our shipped analog | Where | Status |
|---|---|---|---|
| Unigram Viterbi encode (+ lattice) | `SentencePieceGgufTokenizer::encode_unigram` (scores from GGUF, byte fallback, unk penalty) | riir-ai `riir-engine/src/tokenizer.rs` (Issue 400, Bench 780) | ✅ ships — **normalize pre-step has a measured bug (§3)** |
| BPE merge encode | `fast_bpe` (gigatoken vendored, Bench 191) + `BpeTokenizer::from_gguf` | katgpt-tokenizer / riir-engine | ✅ ships |
| Byte fallback `<0xNN>` | type-6 token table both paths | riir-engine tokenizer.rs | ✅ ships (reference tab→`<0x09>` reproduced by our table) |
| Special tokens (control=3 / user_defined=4) | longest-match partitioner | riir-engine tokenizer.rs | ✅ ships |
| Normalizer: `escape_whitespaces` (0x20→▁) | both paths | riir-engine tokenizer.rs | ✅ ships |
| Normalizer: `remove_extra_whitespaces`, leading/trailing strip | hardcoded collapse+strip in `encode_unigram` | riir-engine tokenizer.rs ~L936-957 | ❌ **measured wrong for gemma-2 (Row A)** |
| Normalizer: precompiled charsmap (Darts-clone trie) | — (documented limitation comment ~L919) | — | ⚪ **measured near-identity for gemma-2 — not a live gap** (Row B) |
| Darts double-array (vocab-trie accel) | `datrie_vocab` | katgpt-tokenizer `datrie.rs` (Research 137) | ✅ ships (Aoe layout; Darts-clone blob layout differs) |
| Trainer (unigram EM / BPE merge learning) | ConvexTok LP vocab optimizer | katgpt-tokenizer `convex_*` | ✅ different algorithm, same role (Row C) |
| `SampleEncodeAndScore` (subword regularization, α-sampling) | — | — | recorded, no consumer (Row C) |
| Vocabulary restriction (`SetVocabulary`) | constrained-decoding surfaces (ConstraintPruner family) | katgpt-core | ✅ different shape, covered |

The C++ reference itself remains in-repo as the file-based oracle: `SentencePieceTokenizer` wraps `sentencepiece = "0.13"` (native-only feature, riir-engine Cargo.toml L197; deliberately contained per Bench 723).

## 2. The measured evidence (oracle: `riir-train/data/tokenizer.model`, sentencepiece 0.2.x, 2026-09-17)

### 2.1 gemma-2's normalizer is pure space-escaping — nothing else

| input | reference ids | reference pieces |
|---|---|---|
| `'world'` | `[9097]` | `['world']` (no dummy prefix) |
| `' world'` | `[2134]` | `['▁world']` (leading space KEPT → ▁) |
| `'  world'` | `[139, 9097]` | `['▁▁', 'world']` (run kept as ▁▁ piece) |
| `'world '` | `[9097, 235248]` | `['world', '▁']` (trailing KEPT) |
| `'a  b'` | — | `['a', '▁▁', 'b']` (no collapse) |
| `'end.  Next'` | `[615, 235265, 139, 6353]` | `['end', '.', '▁▁', 'Next']` |
| `'   '` | `[140]` | `['▁▁▁']` |
| `'a\tb'` | — | `['a', '<0x09>', 'b']` (byte fallback) |

Non-ASCII passes through **raw** (charsmap ≈ identity for every probed class):

| input | reference pieces | NFKC would have |
|---|---|---|
| `'ทำ'` (U+0E17+U+0E33 SARA AM) | `['ทำ']` single piece | decomposed ำ → ํ+า |
| `'！'` (U+FF01) | `['！']` full-width kept | folded to `!` |
| `'é'` decomposed (e+U+0301) | `['e', '́']` two pieces | composed to `é` |
| `'ﬁ'`, `'½'`, NBSP, U+3000, ZWSP, BOM, VT, CR | raw pieces each | changed |

**Corollary 1:** a generic NFKC prepass (e.g. `unicode-normalization::nfkc()`) would *break* parity on full-width and decomposed-accent input. Do not add one for gemma parity.
**Corollary 2:** the absent `tokenizer.ggml.precompiled_charsmap` in our GGUFs (measured absent in both `gemma-2-2b-it-f16.gguf` — `model=llama, pre=default, add_space_prefix=False` — and `gemma-4-12B-it.Q4_K_M.gguf`) is harmless *for this model family*: the map it would carry is near-identity for the probed classes.

### 2.2 Our `encode_unigram` diverges on exactly the whitespace-run class

riir-engine `tokenizer.rs` normalize loop (~L936-957): `last_was_space = true` init strips leading, the conditional push collapses interior runs, the tail `while normalized.ends_with(SP_SPACE) { pop() }` strips trailing. Predicted vs reference:

| input | reference | ours (code-read) |
|---|---|---|
| `' world'` | `[2134] ▁world` | `[9097] world` ❌ |
| `'  world'` | `[139, 9097]` | `[9097]` ❌ |
| `'world '` | `[9097, 235248]` | `[9097]` ❌ |
| `'end.  Next'` | `[615, 235265, 139, 6353]` | collapse → 3 tokens ❌ |
| single-space ASCII, all probed non-ASCII | ✓ | ✓ (parity holds) |

Why it survived: the Issue 400 T7 agreement test is llama-tokenize-based and ASCII/single-space scoped; every behavior-gate bench feeds template text without leading/trailing/multiple spaces. The bug is invisible exactly where the fixtures are thin — the classic green-zero shape. Note the gguf **BPE** path (`encode_no_special`, gemma-4) already does plain replace without collapse/strip, so the bug is scoped to the unigram path; the same fixture suite should still run against gemma-4 for symmetry (cheap).

Real-input reach: double-space-after-period prose, LLM-generated text with irregular spacing, user prompts with trailing whitespace — token streams diverge from the training distribution on precisely those inputs. Thai content is *not* affected by this bug class (Thai encodes identically both ways — measured §2.1), which corrects this session's own initial NFKC/Thai hypothesis.

## 3. Distillation rows

- **Row A (primary — riir-ai Issue 970, filed):** fix `encode_unigram` normalization to pure space-escaping (replace every `0x20`→`▁`, no collapse, no strip; honor `add_dummy_prefix` as now — GGUF `add_space_prefix=False` matches the reference's no-prefix). Golden ids from §2.1/§2.2 are pinned in the issue. Caveat recorded there: *generic* SentencePiece defaults (`remove_extra_whitespaces=true`) do collapse — the fix must be per-model-family truth (gemma-2: no collapse), documented at the code site.
- **Row B (recorded, NOT filed — restraint):** precompiled-charsmap blob consumer for katgpt-tokenizer (decode `NormalizerSpec.precompiled_charsmap` → Darts-clone double-array units, big-endian u32, values = offsets into a NUL-delimited replacement pool; zero-alloc longest-match walk; `kMaxTrieResultsSize=32` cap; the same double-array family as `datrie.rs`, different unit packing — source `normalizer.cc` `Init`/`NormalizePrefix`). No live consumer once gemma-2's map is measured near-identity, so no issue is filed — a primitive without a consumer is backlog wearing a pin. **Reopen trigger:** the first non-gemma SentencePiece-family model entering `riir-train/data` (its charsmap may be a real NFKC-class map; then the blob consumer lands in katgpt-tokenizer and the GGUF-less blob is read from the `.model` sidecar).
- **Row C (recorded):** trainer + subword regularization. Vocab construction is owned in-stack by ConvexTok's LP optimizer (different algorithm, same role — katgpt-tokenizer `convex_*`); SentencePiece's EM trainer adds nothing we lack. `SampleEncodeAndScore` α-sampling is training-data augmentation with zero current consumers (riir-train corpora are English/code). **Reopen trigger:** any Thai/non-ASCII fine-tune corpus plan in riir-train — segmentation sampling is then a one-plan item.
- **Row D (conditional):** `ThaiUnigramTokenizer` for riir-neuron-db `Bm25Index`. The extension point ships (`Bm25Index::with_tokenizer`, `Tokenizer` trait, bm25.rs; `CodeTokenizer` is the riir-rag default per Issue 589) and `WhitespaceTokenizer` degenerates on unspaced Thai (whole doc → one term). The reference's own Thai segmentation (`'สวัสดี'` → `['ส','วัส','ดี']`) shows a Gemma-vocab unigram segmenter would give BM25 real Thai terms. No live Thai BM25 corpus was verified this session — **check named:** does any gateway/editor feed land Thai docs in `Bm25Index`? Reopen on the first Thai-content consumer.

### Consumer-context reframes (per skill step 4)

- **Game:** every text→model boundary (NPC dialogue, behavior-gate prompts, quest templates) inherits tokenizer divergence; the measured class is *irregular spacing*, not Thai — fixing it makes gemma-2 prompts token-exact for the training distribution on any user/LLM-generated text.
- **Healer:** riir-clippy retrieval is AST/code-shape (`AstChunker`; `CodeTokenizer` BM25 default, Issue 589) — ASCII-class, no SentencePiece angle beyond the already-vendored `fast_bpe`. Honest no.

## 4. Verdict

**GAIN** — actionable repair of a measured parity bug + recorded rows. Per-tier one-liners:

- **Super-GOAT: NO** — Q1 prior art fails outright (SentencePiece *is* the prior art; llama.cpp and HF `tokenizers` implement every piece), Q2 no new behavior class, Q3 no selling point, Q4 parity work.
- **GOAT: NO** — no provable gain over an incumbent of ours; the axis is correctness-parity on one path.
- **GAIN: YES** — measured bug + golden fixtures + one issue (riir-ai 970); everything else explicitly recorded with reopen triggers rather than speculatively filed.

**MOAT gate (§1.6):** katgpt-rs — note only; no primitive promoted (datrie/fast_bpe already own the trie/BPE slots; the blob consumer is deferred to its reopen trigger). riir-ai — consumer wiring only, engine-internal; no pillar claim. Domain fit: clean.

## 5. Validation protocol (carried into Issue 970)

- **G1 correctness:** fixture suite §2.1/§2.2 (leading/trailing/interior runs, spaces-only, `end.  Next`, tab byte-fallback, Thai set incl. `ทำ`/`สวัสดี`, full-width, decomposed é) — token-id equality vs the in-repo C++ oracle (`SentencePieceTokenizer`, native `sentencepiece` feature) or the pinned golden ids.
- **G3 no-regression:** Issue 400 T7 llama-tokenize ASCII agreement must stay green (pure-ASCII single-space inputs are unchanged by the fix — collapse/strip were no-ops there); existing tokenizer tests updated where they pinned the old collapse behavior.
- **G4:** normalize stays allocation-light (the fix *deletes* logic — collapse/strip — and keeps the single-pass replace).

## 6. Addendum 2026-09-17 — the consumer fix landed, and the note was right for a smaller reason than it said

riir-ai Issue 970 is **resolved** (riir-ai `576bf1ef1`; HISTORY row there). Three
corrections to this note, all measured while writing its fixture suite, and two
of them are corrections to *this document*:

**(a) §2.1's normalizer claim is now read off the spec, not inferred.** A
protobuf scan of `riir-train/data/tokenizer.model` — no `sentencepiece` module
needed, and it is not installed on the Windows workstation — returns
`trainer_spec.model_type = BPE`, `normalizer_spec { name = "identity",
precompiled_charsmap = 0 bytes, add_dummy_prefix = false,
remove_extra_whitespaces = false }`. "Near-identity charsmap" is **literally
identity**, and `remove_extra_whitespaces = false` is stated by the model rather
than probed. Corollaries 1 and 2 stand, strengthened.

**(b) §2.2's predicted-damage table was wrong in BOTH directions.** It was a
code read of the normalize loop, and the loop is not the only thing in the path.
The GGUF spells space runs of 2..63 as **type-4 `user_defined` pieces of literal
ASCII spaces** (ids 139…), not the `▁▁`/`▁▁▁` that `tokenizer.model` prints — so
the special-token partitioner already caught every multi-space run on raw text,
before escaping. `'  world'` and `'end.  Next'` were **not** losing their run
piece. The collapse/strip loop's live damage was narrower: the leading and
trailing **single** space of each partition segment (`' world'`, `'world '`).
The lesson is the one this workspace keeps re-learning one instrument over: a
predicted finding read off one component is not a measurement of the path.

**(c) The bigger defect was one level under the one we filed, and the fixture
found it.** §1's coverage map credits `encode_unigram` as "✅ ships" with a
normalizer footnote. It was the **wrong algorithm**: `model_type = BPE` means
the GGUF scores are negative **merge ranks** (`▁world` = −1661, `Next` = −5880,
floor −255494 ≈ −|vocab|), so a Viterbi maximizing Σ score rewards short
frequent pieces without bound. Measured: `"Next"` → `["Ne","xt"]`, `" world"` →
`["▁w","or","ld"]`, **+94.9% tokens** over 8 prose / code / chat-template
prompts (`Explain the difference` → `Ex pl ain ▁t he ▁di ff er en ce`).
Repaired to llama.cpp's `llm_tokenizer_spm` score-priority bigram merge; **9 of
9** golden rows from §2.1 now agree, Thai / full-width / decomposed-é included.

`'end.  Next'` was the row that carried both errors at once — predicted at 3
tokens, actually 5, for a reason that had nothing to do with whitespace. A
single row disagreeing with a prediction in the *unexpected direction* is worth
more than the five that agreed.

**What this does to §4's verdict: nothing, and that is the honest reading.**
GAIN stands and the tier answers are unchanged — the axis is still
correctness-parity on one consumer path, and SentencePiece is still the prior
art. What changed is the *size* of the repair, not its class. **§5's G1 was the
load-bearing task all along**: the golden-id fixture was specified as validation
for a known fix and functioned as a discovery instrument, which is the argument
for writing the oracle table before the repair rather than after it.

**Open, tracked in riir-ai `.issues/972`:** Bench 780's behavior gate ran both
arms through the defective tokenizer. Its T3 lossy-surface promotion rule —
the one quoted in katgpt-rs `AGENTS.md` §Feature Flag Discipline — **stands**,
being a comparative claim over a shared defect. Its "floor-limited — ref solves
2/72" competence figure does not: a reference arm fed ~2× shredded prompts
produces a low ceiling by construction, so the honest status is UNKNOWN.

## References

- google/sentencepiece @ `b2db4719c3f41e1b0c61dd948c5d8bf445bef1a0` (Apache-2.0) — `normalizer.cc` (`Init`, `Normalize`, `NormalizePrefix`), `unigram_model.cc`, `sentencepiece_processor.h`.
- Kudo & Richardson 2018, [arXiv:1808.06226](https://arxiv.org/abs/1808.06226); Kudo 2018, [arXiv:1804.10959](https://arxiv.org/abs/1804.10959).
- llama.cpp tokenizer parity context: ggml-org/llama.cpp#7476 (old-GGUF tokenization drift class).
- In-stack: Research 137 (datrie), Research 456 + Bench 191 (fast_bpe), riir-ai Issue 400 / Bench 780 (GGUF tokenizer), Bench 723 (C++ dep containment), riir-neuron-db Issue 589 (CodeTokenizer default).
