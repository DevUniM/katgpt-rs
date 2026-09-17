# Issue 826: FlashMemory promotion gate needs a needle-axis quality gate (Research 567, arXiv:2609.13141 evidence)

**Status:** Open — PoC/measurement task, blocks Issue 584 Phase 3 promotion

**Source:** [Research 567](../.research/567_SAS_LogGate_LM_Loss_Sparse_Context_Ranking.md) — SAS (arXiv:2609.13141) states as a LIMITATION what our shipped corridor has never measured: pooling-based block summaries **destroy needle-like localized information**. Their RULER numbers at 128K / budget-4096: SAS 21.87/23.46/29.95 (4B/8B/14B) vs full attention 63.81/73.87/82.23 — even after retraining the selector on 64K sequences (0.5B tokens).

**Why it applies to us:** `flashmemory_sparse.rs` builds block centroids via `rebuild_from_cache` as the **mean of compressed KV latent** (`c_kv` mean over the block) — the same pooling class AttnGate uses (pooled per-block key statistics). The corridor is perf-validated (Bench 671: 1.8× decode at 64K on 4090) and its mechanism test (Issue 584 Phase 1 Q4) checked "sparse forward preserves accuracy" — but no needle/long-context retrieval axis was measured. SAS's tight-budget data also bounds where the modelless selector is safe: training-free ranking collapses on hard tasks at tight budgets (Quest = 0 on AIME24/25 at 2048, 40.74 on MATH500-4B vs trained-selector 93.47).

**Game-runtime framing (priority #1 surface):** the league's sparse-decode lane is what long-context NPC serving (dialogue histories, world-event transcripts) would lean on. Promotion without a needle gate would ship the exact failure axis SAS documented externally.

## Tasks

- [ ] **T1 — Needle-quality bench for `flashmemory_sparse`.** Add a RULER-class retrieval axis to the corridor's validation: planted-needle QA (needle-in-haystack + multi-needle variant) over the MLA sparse forward at 64K context, selector σ ≥ 0.5 default vs dense oracle. Floor: sparse accuracy within a stated tolerance of dense on the needle axis (the tolerance is the Phase 3 gate parameter — pick it from the measurement, then pin it).
- [ ] **T2 — Budget-stress axis.** Same bench at tightened thresholds (raise σ threshold to force smaller selected sets) to find where the modelless sigmoid selector degrades on needle retrieval — the external data predicts collapse well before full sparsity on hard retrieval. Record the safe operating band next to the perf numbers in the promotion doc.
- [ ] **T3 — Gate wiring.** If T1/T2 expose a real gap: the Phase 3 GOAT gate gains the needle axis as a required row (promotion blocked until passed), and the centroid improvement becomes a follow-up (candidates: max-pool centroid, per-block top-k key summary, SAS's pooled-statistic + learned-refinement hybrid — the trained half is riir-train 560's lane). If the corridor passes the needle gate at default settings, pin the numbers in the promotion doc and close this issue with the evidence.
- [-] **T4 — Centroid refinement (deferred behind T3).** Only if T3 shows a gap. Do NOT reach for the trained-selector class here — that is riir-train Plan 337's lane (Issue 560 recipe deltas); the modelless refinement must stay deterministic (max/top-k pooling, no GD).

## References

- Research 567 (parent note; SAS RULER limitation = the external evidence)
- Issue 584 (FlashMemory mechanism validation; Phase 1 Q4 = the accuracy check that did NOT cover needles)
- Bench 671 (1.8× decode at 64K on 4090 — the perf half of the corridor)
- riir-train Issue 560 / Plan 337 (the trained-selector lane — separate track, do not mix)
