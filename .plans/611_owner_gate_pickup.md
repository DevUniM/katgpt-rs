# Owner-gate pickup — katgpt-rs (refs .issues/906)

**Status:** OPEN — agent-pickupable prep tasks; executions stay owner-gated.

Local record: `.issues/906_owner_gate_pickup.md`. Cross-workspace context lives in the private workspace hub and is intentionally not linked from this public repo.

## Tasks

- [ ] E12 — draft the Gemma-license one-pager (accept + provision HF token to the 4090, vs retire the check as permanently blocked); attach to `.issues/906` on landing.
- [x] E13 — draft the `[workspace.package] rust-version` patch and the ~30-manifest affected list in a scratch worktree; land on owner go only. **LANDED 2026-10-03 (owner go via Claude verdict AGREE, session 13cf6ceb — round 1, two conditions both applied): 33 manifests carry `rust-version.workspace = true` + the root `[workspace.package] rust-version = "1.98.1"` table; the reviewer's bump-procedure note added to the `rust-toolchain.toml` comment (pin untouched); verification: `cargo metadata` parse + `Counter({'1.98.1': 33})` + `cargo check -p katgpt-core` + `cargo check -p katgpt-rs --lib` + FULL `docs_gate.sh` 35/35 (`DOCS_GATE_PARTIAL_CLONE=1`, this box). Gate-liveness probe (old-toolchain refusal) NOT RUN — no older toolchain installed here; the change landed unproven on that axis, one command with e.g. `RUSTUP_TOOLCHAIN=1.93.0` proves it. Draft `.plans/614` PREP row superseded by this landing.**
