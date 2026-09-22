# Bench 802 — NaN-safe bounded top-K JSD kernel gate (Issue 802 item 2)

**Status:** RECORD — **G1 PASS** (exact-contract tests incl. bitwise ln 2 on
disjoint supports), **G4 PASS** (zero-alloc INTO form), G2 throughput
selection-bound as anticipated (honest breakdown). Measured 2026-09-16, M3 Max,
release, LEN=32768 seeded spiky distributions.

Provenance: Issue 802 item 2 — the kernel prerequisite for (1) commitment-gap
calibration tables and (4) graded tri_mode verdicts (arXiv:2609.15177 distill;
Research 561). The KL-over-top-K-zero-padded alternative is +∞ on disjoint
supports and one NaN poisons every downstream gate; this kernel is bounded by
construction.

## Contract (all self-tested, 9 tests, 2069/0 with the feature on)

- `JSD = H(M) − ½H(P) − ½H(Q)`, natural log, over per-vector top-K restricted
  slices renormalized to sum 1 (union support).
- Disjoint restricted supports → **bitwise `f32::ln(2.0)`** (the predicate is
  exactly the condition under which H(M) = ½H(P)+½H(Q)+ln 2 — the constant is
  the honest value, not a shortcut; zero-valued top-K filler cannot break
  disjointness, exercised at k=len).
- Identical inputs → **bitwise 0.0** (each term an exact x − ½x − ½x).
- NaN-safe / no release-panic: degenerate and adversarial classes route into
  defined branches (`!(s > 0.0)` catches NaN sums); both-zero → 0.0; one-side
  zero → ln 2.
- Scale-invariance, symmetry ≤1e-7, bound [0, ln2+1e-6] over ~12.5k seeded pairs
  × K ∈ {1, 8, 64, 4096} × 5 distribution classes.
- The task-sketch sign error caught and corrected: Σ m·ln m − ½(p ln p + q ln q)
  is the NEGATIVE of the JSD expansion — shipped term = ½pm·ln pm + ½qm·ln qm −
  m·ln m (≥0 per entry by convexity; negative rounding noise clamps to 0).

## Throughput (the honest shape)

| arm | ns/op | × vs full |
|---|---:|---:|
| kernel k=8 | 90,254 | 1.95× |
| kernel k=64 | 90,794 | 1.94× |
| kernel k=1024 | 114,409 | 1.54× |
| select-only k=64 | 90,059 | 1.96× |
| full-support reference | 176,214 | 1.00× |

O(len) iota+select dominates (~90 µs); the restriction buys the SUM phase —
k=8's walk is ~0.2 µs vs ~86 µs of full-support ln-work (~400× on the bounded
phase). No SIMD claimed (the Bench 800 lesson: autovec already owns the
elementwise part). Consistency gate: kernel(k=LEN) vs full-support |Δ| = 7.45e-7.
First bench run caught its own DCE trap (discarded checksum → 0 ns arm); fixed
with a printed sink checksum (the meld-bench house answer).

API: `jsd_topk_into(p, q, k, scratch_p, scratch_q, out)` — zero-alloc (f32-encoded
index workspace, `select_nth_unstable_by` + two-pointer union merge, ≤2k entries;
len ≤ 2²⁴ for index exactness); `jsd_topk(p, q, k) -> f32` — convenience, honestly
documented 2-Vec allocation. Lands opt-in behind `jsd_topk`.
