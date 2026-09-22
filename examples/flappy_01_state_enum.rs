//! Flappy state enumerator + laya-format dump — katgpt-rs Plan 607 T5
//! (the tetris_01 shape): enumerates decision states, renders the
//! closed-grammar sentences (`laya-flappy-v1`, see `common/flappy_sim.rs`),
//! and writes the structured dump + the oracle manifest for riir-reflex's
//! generic batch oracle.
//!
//! The run ends at the dump. To commit the fixture, re-run with the
//! oracle's output: `--join <oracle.jsonl> --fixture-out <path>` performs
//! the self-join (p_clean per option + the argmax) and writes the
//! provenance-digested fixture the 02 arena drift-checks.
//!
//!   cargo run --release --example flappy_01_state_enum -- --seed 607
//!   cargo run --release --example flappy_01_state_enum -- \
//!       --join /tmp/607/flappy_oracle.jsonl \
//!       --fixture-out tests/fixtures/flappy_oracle_laya_en_v1.jsonl \
//!       --oracle-blake3 <hex from the oracle run>

#[path = "common/flappy_sim.rs"]
mod flappy_sim;
#[path = "common/micro_dump.rs"]
mod micro_dump;

use micro_dump::{DumpOption, DumpState, JoinMeta};
use std::path::PathBuf;

fn main() {
    let mut out_dir = PathBuf::from("output/micro_states");
    let mut seed = 607u64;
    let mut n = 100usize;
    let mut join: Option<PathBuf> = None;
    let mut fixture_out = micro_dump::default_fixture("flappy", "v2");
    let mut generator = String::from("riir-reflex examples/laya_oracle_batch");
    let mut oracle_blake3 = String::new();
    let args: Vec<String> = std::env::args().skip(1).collect();
    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--out-dir" if i + 1 < args.len() => {
                i += 1;
                out_dir = PathBuf::from(&args[i]);
            }
            "--seed" if i + 1 < args.len() => {
                i += 1;
                seed = args[i].parse().expect("--seed <u64>");
            }
            "--n" if i + 1 < args.len() => {
                i += 1;
                n = args[i].parse().expect("--n <usize>");
            }
            "--join" if i + 1 < args.len() => {
                i += 1;
                join = Some(PathBuf::from(&args[i]));
            }
            "--fixture-out" if i + 1 < args.len() => {
                i += 1;
                fixture_out = PathBuf::from(&args[i]);
            }
            "--generator" if i + 1 < args.len() => {
                i += 1;
                generator = args[i].clone();
            }
            "--oracle-blake3" if i + 1 < args.len() => {
                i += 1;
                oracle_blake3 = args[i].clone();
            }
            other => {
                eprintln!(
                    "Unknown arg: {other}. Usage: [--out-dir <dir>] [--seed <u64>] [--n <usize>] \
                     [--join <oracle.jsonl>] [--fixture-out <path>] [--generator <str>] \
                     [--oracle-blake3 <hex>]"
                );
                std::process::exit(1);
            }
        }
        i += 1;
    }

    let records: Vec<DumpState> = flappy_sim::enumerate_states(seed, n)
        .into_iter()
        .map(|(id, s)| DumpState {
            state_id: id,
            grammar: flappy_sim::GRAMMAR_ID.to_string(),
            question: flappy_sim::QUESTION.to_string(),
            state_sentence: flappy_sim::render_state_sentence(&s),
            state: serde_json::to_value(s).expect("serialize seed state"),
            options: flappy_sim::ACTIONS
                .iter()
                .enumerate()
                .map(|(ai, &a)| DumpOption {
                    label: flappy_sim::ACTION_LABELS[ai].to_string(),
                    features: flappy_sim::feature_row(&s, a).to_vec(),
                    sentence: flappy_sim::render_option_sentence(&s, a),
                })
                .collect(),
        })
        .collect();

    let n_options: usize = records.iter().map(|r| r.options.len()).sum();
    let out = micro_dump::write_dump(&out_dir, "flappy", &records).expect("write dump");
    eprintln!(
        "dumped {} states ({n_options} options, {}/state) -> {}",
        records.len(),
        flappy_sim::ACTIONS.len(),
        out.dump_path.display()
    );
    eprintln!("dump blake3: {}", out.dump_blake3);
    eprintln!(
        "manifest: {} (blake3 {})",
        out.manifest_path.display(),
        out.manifest_blake3
    );
    eprintln!("grammar: {}  seed: {seed}", flappy_sim::GRAMMAR_ID);

    if let Some(oracle_path) = join {
        assert!(
            !oracle_blake3.is_empty(),
            "--join needs --oracle-blake3 (the hex the oracle run printed)"
        );
        let meta = JoinMeta {
            protocol: "katgpt-rs Plan 607 T5 \u{2014} laya Flappy oracle fixture v2".to_string(),
            grammar: flappy_sim::GRAMMAR_ID.to_string(),
            question: flappy_sim::QUESTION.to_string(),
            checkpoint: "english".to_string(),
            generator: generator.clone(),
            dump_blake3: format!("{}", out.dump_blake3),
            oracle_blake3_raw: oracle_blake3.clone(),
            dump_command: format!(
                "cargo run --release --example flappy_01_state_enum -- --seed {seed} --n {n} (katgpt-rs)"
            ),
            join_command: format!(
                "cargo run --release --example flappy_01_state_enum -- --seed {seed} --n {n} --join <oracle> --fixture-out {} --oracle-blake3 <hex> (katgpt-rs)",
                fixture_out.display()
            ),
            notes:
                "grammar v2: option sentences carry the position band ALONE \u{2014} v1's motion \
                    clause (\"rising\"/\"falling\") was a measured confound (the v1 oracle went \
                    85/100 to flap regardless of geometry, pinning every scorer at the \
                    constant-pick ceiling; Bench 880); the degenerate classes (v = +2 lands both \
                    actions on one cell; same-band results render identical sentences) are \
                    excluded at the enumerator; options pinned [flap, coast] (index 0 = flap, the \
                    lowest-index tie-break's referent); states sampled decision-interesting (bird \
                    within \u{00b1}4 cells of the gap center), deduped, seed-607"
                    .to_string(),
        };
        let digest = micro_dump::join_oracle(&out.dump_path, &oracle_path, &fixture_out, &meta)
            .expect("join oracle");
        println!("fixture: {} (blake3 {digest})", fixture_out.display());
    }
}
