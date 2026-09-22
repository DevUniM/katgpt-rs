//! Shared micro-arena fixture substrate — katgpt-rs Plan 607 T5 (the
//! `tetris_fixture.rs` `#[path]` precedent, one level out): the dump schema
//! the 01 enumerators write, the oracle self-join, the committed fixture
//! schema + drift loader, and the generic G1 reading (baselines + verdict)
//! both arenas share.
//!
//! Deliberately SERDE-ONLY (no katgpt-core imports): the 01 enumerator
//! binaries compile this module ungated — tetris_01's shape. The fit/scoring
//! helpers that DO touch the primitive live in `micro_fit.rs`, compiled only
//! by the gated arenas.

// Each consumer compiles a different half (the 01s write dumps + join; the
// 02s load fixtures + read readings) — per-consumer dead-code warns would
// fire on the other half.
#![allow(dead_code)]

use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};

// ── Dump records (the 01 enumerator's output; pre-oracle) ────────────────

#[derive(Serialize, Deserialize)]
pub struct DumpOption {
    /// The game's pinned option label ("flap"/"coast", "lane0/1/2") — the
    /// drift check demands the pinned ORDER, the label is the human echo.
    pub label: String,
    /// The frozen feature vector (game-defined order, pinned in the _meta).
    pub features: Vec<f64>,
    pub sentence: String,
}

#[derive(Serialize, Deserialize)]
pub struct DumpState {
    pub state_id: String,
    pub grammar: String,
    pub question: String,
    pub state_sentence: String,
    /// The seed state — the drift check recomputes everything from it.
    pub state: serde_json::Value,
    pub options: Vec<DumpOption>,
}

pub struct DumpOutputs {
    pub dump_path: PathBuf,
    pub manifest_path: PathBuf,
    pub dump_blake3: blake3::Hash,
    pub manifest_blake3: blake3::Hash,
}

/// Write the structured dump + the oracle manifest (the batch oracle's
/// input: state_id / question / option sentences only). Deterministic.
pub fn write_dump(dir: &Path, prefix: &str, states: &[DumpState]) -> std::io::Result<DumpOutputs> {
    std::fs::create_dir_all(dir)?;
    let dump_path = dir.join(format!("{prefix}_states.jsonl"));
    let manifest_path = dir.join(format!("{prefix}_oracle_manifest.jsonl"));
    let mut dump = String::new();
    let mut manifest = String::new();
    for st in states {
        dump.push_str(&serde_json::to_string(st).expect("serialize dump record"));
        dump.push('\n');
        let m = serde_json::json!({
            "state_id": st.state_id,
            "question": st.question,
            "options": st
                .options
                .iter()
                .map(|o| serde_json::json!({ "sentence": o.sentence }))
                .collect::<Vec<_>>(),
        });
        manifest.push_str(&serde_json::to_string(&m).expect("serialize manifest record"));
        manifest.push('\n');
    }
    std::fs::write(&dump_path, &dump)?;
    std::fs::write(&manifest_path, &manifest)?;
    Ok(DumpOutputs {
        dump_blake3: blake3::hash(dump.as_bytes()),
        manifest_blake3: blake3::hash(manifest.as_bytes()),
        dump_path,
        manifest_path,
    })
}

// ── The join (oracle output → committed fixture) ─────────────────────────

pub struct JoinMeta {
    pub protocol: String,
    pub grammar: String,
    pub question: String,
    pub checkpoint: String,
    pub generator: String,
    pub dump_blake3: String,
    pub oracle_blake3_raw: String,
    pub dump_command: String,
    pub join_command: String,
    pub notes: String,
}

/// Self-join the oracle's per-option p_clean into the dump records and write
/// the committed fixture (`_meta` provenance record first, one state per
/// line). Sanity: every record's option count must match, and the oracle's
/// own argmax must agree with its p_clean under the pinned lowest-index
/// tie-break — a disagreement is oracle-file corruption, not a finding.
pub fn join_oracle(
    dump_path: &Path,
    oracle_path: &Path,
    fixture_out: &Path,
    meta: &JoinMeta,
) -> std::io::Result<blake3::Hash> {
    let read_jsonl = |p: &Path| -> std::io::Result<Vec<serde_json::Value>> {
        Ok(std::fs::read_to_string(p)?
            .lines()
            .map(|l| serde_json::from_str(l).expect("parse JSONL line"))
            .collect())
    };
    let dump: Vec<DumpState> = read_jsonl(dump_path)?
        .into_iter()
        .map(|v| serde_json::from_value(v).expect("parse dump record"))
        .collect();
    let oracle = read_jsonl(oracle_path)?;
    assert_eq!(
        dump.len(),
        oracle.len(),
        "dump/oracle record count mismatch"
    );

    let mut buf = String::new();
    let m = serde_json::json!({
        "state_id": "_meta",
        "protocol": meta.protocol,
        "grammar": meta.grammar,
        "question": meta.question,
        "checkpoint": meta.checkpoint,
        "generator": meta.generator,
        "dump_blake3": meta.dump_blake3,
        "oracle_blake3_raw": meta.oracle_blake3_raw,
        "dump_command": meta.dump_command,
        "join_command": meta.join_command,
        "notes": meta.notes,
    });
    buf.push_str(&serde_json::to_string(&m).expect("serialize meta"));
    buf.push('\n');

    for (st, orc) in dump.iter().zip(&oracle) {
        assert_eq!(
            st.state_id,
            orc["state_id"].as_str().expect("oracle state_id"),
            "dump/oracle state order mismatch"
        );
        let pcs: Vec<f64> = orc["p_clean"]
            .as_array()
            .expect("oracle p_clean array")
            .iter()
            .map(|p| p.as_f64().expect("p_clean f64"))
            .collect();
        assert_eq!(
            pcs.len(),
            st.options.len(),
            "{}: oracle option count mismatch",
            st.state_id
        );
        let mut bi = 0usize;
        let mut bp = f64::NEG_INFINITY;
        for (i, &p) in pcs.iter().enumerate() {
            if p > bp {
                bp = p;
                bi = i;
            }
        }
        let oarg = orc["argmax"].as_u64().expect("oracle argmax") as usize;
        assert_eq!(
            bi, oarg,
            "{}: oracle argmax {oarg} disagrees with its own p_clean under the lowest-index tie-break",
            st.state_id
        );
        let rec = serde_json::json!({
            "state_id": st.state_id,
            "grammar": st.grammar,
            "question": st.question,
            "state_sentence": st.state_sentence,
            "state": st.state,
            "options": st
                .options
                .iter()
                .zip(&pcs)
                .map(|(o, p)| serde_json::json!({
                    "label": o.label,
                    "features": o.features,
                    "sentence": o.sentence,
                    "p_clean": p,
                }))
                .collect::<Vec<_>>(),
            "argmax": oarg,
        });
        buf.push_str(&serde_json::to_string(&rec).expect("serialize fixture record"));
        buf.push('\n');
    }

    std::fs::write(fixture_out, &buf)?;
    Ok(blake3::hash(buf.as_bytes()))
}

// ── Fixture records (post-join, the committed artifact) ──────────────────

#[derive(Deserialize)]
pub struct MicroStateFixture {
    pub state_id: String,
    #[allow(dead_code)]
    pub grammar: String,
    #[allow(dead_code)]
    pub question: String,
    pub state_sentence: String,
    pub state: serde_json::Value,
    pub options: Vec<MicroOptionFixture>,
    pub argmax: usize,
}

#[derive(Deserialize)]
pub struct MicroOptionFixture {
    pub label: String,
    pub features: Vec<f64>,
    pub sentence: String,
    pub p_clean: Option<f64>,
}

pub fn default_fixture(prefix: &str, version: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(format!(
        "tests/fixtures/{prefix}_oracle_laya_en_{version}.jsonl"
    ))
}

/// Parse the fixture (skipping the `_meta` provenance record) and run the
/// game's drift check on every state. Panics on drift — the fixture is
/// provenance-digested and must recompute byte-identically before any
/// scoring happens.
pub fn load_micro_states<R>(
    path: &Path,
    drift: impl Fn(&MicroStateFixture) -> Result<R, String>,
) -> Vec<(MicroStateFixture, R)> {
    let raw =
        std::fs::read_to_string(path).unwrap_or_else(|e| panic!("read fixture {path:?}: {e}"));
    let mut out = Vec::new();
    for (ln, line) in raw.lines().enumerate() {
        let value: serde_json::Value =
            serde_json::from_str(line).unwrap_or_else(|e| panic!("fixture line {}: {e}", ln + 1));
        if value["state_id"] == "_meta" {
            continue;
        }
        let f: MicroStateFixture = serde_json::from_value(value)
            .unwrap_or_else(|e| panic!("fixture line {}: {e}", ln + 1));
        if f.options.iter().any(|o| o.p_clean.is_none()) {
            panic!(
                "{}: p_clean missing — the corpus needs the oracle's per-option read",
                f.state_id
            );
        }
        let r = drift(&f).unwrap_or_else(|e| panic!("DRIFT: {e}"));
        out.push((f, r));
    }
    out
}

// ── The generic G1 reading ───────────────────────────────────────────────

pub struct Reading {
    pub n_states: usize,
    pub raw_agree: usize,
    pub class_agree: usize,
    pub constant_agree: usize,
    pub constant_index: usize,
    pub chance: f64,
    pub distinct_picks: usize,
    pub ctx_agree: usize,
    pub oracle_ties: usize,
    pub our_ties_at_oracle: usize,
}

/// One policy's full G1 reading over the fixture: raw + class-level
/// agreement vs the oracle argmax, the strongest constant policy (always
/// the oracle-majority index), chance, the code-arithmetic context policy,
/// and the discrimination floor.
pub fn read_reading<R>(
    states: &[(MicroStateFixture, R)],
    decide: &dyn Fn(usize, &MicroStateFixture) -> usize,
    ctx_pick: &dyn Fn(&R) -> usize,
) -> Reading {
    let n = states.len();
    let mut raw_agree = 0usize;
    let mut class_agree = 0usize;
    let mut ctx_agree = 0usize;
    let mut picks_seen = HashSet::new();
    let mut hist: HashMap<usize, usize> = HashMap::new();
    let mut chance_sum = 0.0f64;
    let mut oracle_ties = 0usize;
    let mut our_ties_at_oracle = 0usize;
    for (s, (f, r)) in states.iter().enumerate() {
        let pick = decide(s, f);
        picks_seen.insert(pick);
        *hist.entry(f.argmax).or_insert(0) += 1;
        chance_sum += 1.0 / f.options.len() as f64;
        if pick == f.argmax {
            raw_agree += 1;
        }
        if f.options[pick].sentence == f.options[f.argmax].sentence {
            class_agree += 1;
        }
        if pick == ctx_pick(r) {
            ctx_agree += 1;
        }
        let max = f
            .options
            .iter()
            .filter_map(|o| o.p_clean)
            .fold(f64::NEG_INFINITY, f64::max);
        let tied = f.options.iter().filter(|o| o.p_clean == Some(max)).count();
        if tied > 1 {
            oracle_ties += 1;
            if f.options[pick].sentence == f.options[f.argmax].sentence {
                our_ties_at_oracle += 1;
            }
        }
    }
    let constant_index = *hist
        .iter()
        .max_by_key(|(_, c)| **c)
        .map(|(k, _)| k)
        .unwrap_or(&0);
    let constant_agree = hist.get(&constant_index).copied().unwrap_or(0);
    Reading {
        n_states: n,
        raw_agree,
        class_agree,
        constant_agree,
        constant_index,
        chance: chance_sum / n.max(1) as f64,
        distinct_picks: picks_seen.len(),
        ctx_agree,
        oracle_ties,
        our_ties_at_oracle,
    }
}

pub fn pct(n: usize, d: usize) -> String {
    format!("{:.1}%", 100.0 * n as f64 / d.max(1) as f64)
}

/// The shared verdict print. G1's law (Plan 607): raw > constant-pick AND
/// raw > chance — never vs laya alone.
pub fn print_reading(name: &str, r: &Reading, ctx_name: &str) {
    println!("\n{name} — decision agreement vs laya oracle:");
    println!(
        "  raw agreement:      {}/{} ({})",
        r.raw_agree,
        r.n_states,
        pct(r.raw_agree, r.n_states)
    );
    println!(
        "  class-level:        {}/{} ({})  [same-sentence equivalence]",
        r.class_agree,
        r.n_states,
        pct(r.class_agree, r.n_states)
    );
    println!(
        "  constant-pick:      {}/{} ({})  [always oracle-majority index {}]",
        r.constant_agree,
        r.n_states,
        pct(r.constant_agree, r.n_states),
        r.constant_index
    );
    println!("  chance baseline:    {:.1}%", 100.0 * r.chance);
    println!(
        "  vs {ctx_name}:  {}/{} ({})  [context]",
        r.ctx_agree,
        r.n_states,
        pct(r.ctx_agree, r.n_states)
    );
    println!(
        "  oracle ties:        {} states (ours matched same-sentence at {})",
        r.oracle_ties, r.our_ties_at_oracle
    );
    println!(
        "  distinct picks:     {} [floor ≥ 2] {}",
        r.distinct_picks,
        if r.distinct_picks >= 2 {
            "PASS"
        } else {
            "FAIL"
        }
    );
    let g1 = r.raw_agree > r.constant_agree && (r.raw_agree as f64) > r.chance * r.n_states as f64;
    println!(
        "  G1 verdict: {} (raw > constant-pick AND raw > chance)",
        if g1 { "HOLDS" } else { "DOES NOT HOLD" }
    );
}
