//! Tetris state enumerator + laya-format dump — katgpt-rs Plan 607 T4a.
//!
//! Enumerates a stratified, fully deterministic fixture of Tetris decision
//! states (authored board archetypes × every piece, plus a seeded
//! Dellacherie-greedy play ladder), renders the pinned laya-protocol
//! sentences (`laya-tetris-v1`, see `common/tetris_sim.rs`), and dumps one
//! JSONL record per state:
//!
//! ```json
//! {
//!   "state_id": "arch:left_stack:I",
//!   "grammar": "laya-tetris-v1",
//!   "question": "Does the stack look clean?",
//!   "state_sentence": "The stack stands tall, tall on the left and low on the right. …",
//!   "board": ["..........", "…"],
//!   "piece": "I",
//!   "options": [
//!     {"rot": 0, "col": 0, "row": 18, "cells": [[18,0]], "features": {...},
//!      "sentence": "The piece leaves one hole under it and makes a small bump on top."}
//!   ]
//! }
//! ```
//!
//! The option ORDER is pinned (rotation asc, then column asc) — the T0b
//! oracle's and the T4 arena's argmax index both refer to it. The run ends
//! with a BLAKE3 digest on stderr — that hash is the provenance anchor the
//! T0b fixture records (same seed in, same bytes out, on every box).
//!
//! Run: `cargo run --release --example tetris_01_state_enum [-- --out <path> --seed <u64>]`
//! Tests: `cargo test --example tetris_01_state_enum` (the common module's
//! closed-grammar / enumeration unit tests).

use std::path::PathBuf;

use serde::Serialize;

#[path = "common/tetris_sim.rs"]
mod tetris_sim;

use tetris_sim::{
    Board, Piece, GRAMMAR_ID, SPOT_QUESTION, dellacherie_score, landing_options,
    outcome_features, render_spot_sentence, render_state_sentence, HEIGHT, WIDTH,
};

// ── Dump record shape ────────────────────────────────────────────────────

#[derive(Serialize)]
struct OptionRecord {
    rot: usize,
    col: usize,
    row: usize,
    cells: Vec<(usize, usize)>,
    features: FeatureRecord,
    sentence: String,
}

#[derive(Serialize)]
struct FeatureRecord {
    lines_cleared: u32,
    holes: u32,
    holes_delta: i32,
    bumpiness: u32,
    max_height: u32,
    aggregate_height: u32,
    landing_height: f32,
    row_transitions: u32,
    col_transitions: u32,
    cumulative_wells: u32,
    eroded_cells: u32,
}

impl From<tetris_sim::OutcomeFeatures> for FeatureRecord {
    fn from(f: tetris_sim::OutcomeFeatures) -> Self {
        Self {
            lines_cleared: f.lines_cleared,
            holes: f.holes,
            holes_delta: f.holes_delta,
            bumpiness: f.bumpiness,
            max_height: f.max_height,
            aggregate_height: f.aggregate_height,
            landing_height: f.landing_height,
            row_transitions: f.row_transitions,
            col_transitions: f.col_transitions,
            cumulative_wells: f.cumulative_wells,
            eroded_cells: f.eroded_cells,
        }
    }
}

#[derive(Serialize)]
struct StateRecord {
    state_id: String,
    grammar: &'static str,
    question: &'static str,
    state_sentence: String,
    board: Vec<String>,
    piece: &'static str,
    options: Vec<OptionRecord>,
}

// ── Authored board archetypes (deterministic, stratified) ───────────────

/// Build a board from a per-column height profile.
fn board_from_heights(heights: &[usize; WIDTH]) -> Board {
    let mut b = Board::empty();
    for (c, &h) in heights.iter().enumerate() {
        for r in (HEIGHT - h)..HEIGHT {
            b.place(&[(r, c)]);
        }
    }
    b
}

/// A flat floor of `floor` with a single 1-wide well of depth 4 at
/// `well_col`, plus the open shaft column that keeps every row pre-clear.
fn well_heights(floor: usize, well_col: usize) -> [usize; WIDTH] {
    let mut h = [floor; WIDTH];
    h[well_col] = floor.saturating_sub(4);
    h[WIDTH - 1] = 0; // open shaft: no row can complete (pre-clear law)
    h
}

/// The authored archetype ladder: name → board. Every board is PRE-CLEAR
/// (no complete rows — real Tetris never carries them; each heights-based
/// profile keeps one 0-height shaft column so no row can complete) and
/// carries a distinct surface shape so the fixture spans the grammar's
/// bands. `holes_archetype` (covered pockets) is separate — height profiles
/// cannot express sub-surface cavities.
fn archetypes() -> Vec<(&'static str, Board)> {
    let shaft = |mut h: [usize; WIDTH]| {
        h[WIDTH - 1] = 0;
        h
    };
    vec![
        ("empty", Board::empty()),
        ("floor_low", board_from_heights(&shaft([3; WIDTH]))),
        ("floor_high", board_from_heights(&shaft([8; WIDTH]))),
        (
            "left_stack",
            board_from_heights(&shaft([14, 13, 12, 10, 8, 6, 5, 4, 3, 2])),
        ),
        (
            "right_stack",
            board_from_heights(&shaft([2, 3, 4, 5, 6, 8, 10, 12, 13, 14])),
        ),
        (
            "center_mound",
            board_from_heights(&shaft([2, 4, 7, 9, 11, 11, 9, 7, 4, 2])),
        ),
        (
            "staircase",
            board_from_heights(&shaft([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])),
        ),
        (
            "jagged",
            board_from_heights(&shaft([9, 2, 8, 3, 7, 4, 6, 5, 10, 2])),
        ),
        ("well_left", board_from_heights(&well_heights(8, 0))),
        ("well_right", board_from_heights(&well_heights(8, 2))),
        ("well_center", board_from_heights(&well_heights(8, WIDTH / 2))),
        ("holes", holes_archetype()),
    ]
}

/// A plateau (height 8, columns 0–8) with the open shaft at col 9 and three
/// covered holes — hand-authored mask, pinned bytes: holes at (16, 2),
/// (17, 5), (16, 8).
fn holes_archetype() -> Board {
    let mut rows: Vec<String> = Vec::with_capacity(HEIGHT);
    for r in 0..HEIGHT {
        let mut row = String::with_capacity(WIDTH);
        for c in 0..WIDTH {
            let occupied = r >= HEIGHT - 8
                && c != WIDTH - 1
                && !((r == 16 && (c == 2 || c == 8)) || (r == 17 && c == 5));
            row.push(if occupied { '#' } else { '.' });
        }
        rows.push(row);
    }
    let refs: Vec<&str> = rows.iter().map(|s| s.as_str()).collect();
    Board::from_strings(&refs)
}

// ── Seeded Dellacherie-greedy play ladder ────────────────────────────────

/// Dellacherie argmax with the pinned tie-break (lowest index wins).
fn greedy_pick(feats: &[tetris_sim::OutcomeFeatures]) -> usize {
    let mut best = 0usize;
    let mut best_score = f32::NEG_INFINITY;
    for (i, f) in feats.iter().enumerate() {
        let s = dellacherie_score(f);
        if s > best_score {
            best_score = s;
            best = i;
        }
    }
    best
}

/// Play deterministic games with `rng`; snapshot the board BEFORE every
/// placement from the 5th onward, up to `want` snapshots. Top-out ends the
/// game; the next game continues the same rng stream (still deterministic).
fn play_ladder(rng: &mut fastrand::Rng, want: usize) -> Vec<(String, Board, Piece)> {
    let mut out: Vec<(String, Board, Piece)> = Vec::with_capacity(want);
    let mut game = 0usize;
    while out.len() < want {
        let mut board = Board::empty();
        let mut placement_n = 0usize;
        loop {
            let piece = Piece::ALL[rng.usize(0..7)];
            let options = landing_options(&board, piece);
            if options.is_empty() {
                break; // top-out — next game
            }
            let feats: Vec<_> = options.iter().map(|p| outcome_features(&board, p)).collect();
            placement_n += 1;
            if out.len() < want && placement_n >= 5 {
                out.push((format!("play{game:02}:{placement_n:03}"), board.clone(), piece));
            }
            let pick = greedy_pick(&feats);
            let mut after = board.clone();
            after.place(&options[pick].cells);
            let full = after.full_rows();
            after.clear_rows(&full);
            board = after;
            if placement_n >= 200 {
                break; // safety bound; greedy rarely reaches this
            }
        }
        game += 1;
    }
    out.shrink_to_fit();
    out
}

// ── Dump assembly ────────────────────────────────────────────────────────

fn build_record(state_id: String, board: &Board, piece: Piece) -> StateRecord {
    let options = landing_options(board, piece);
    let mut recs = Vec::with_capacity(options.len());
    for p in &options {
        let f = outcome_features(board, p);
        let sentence = render_spot_sentence(board, p, &f);
        recs.push(OptionRecord {
            rot: p.rot,
            col: p.col,
            row: p.row,
            cells: p.cells.clone(),
            features: f.into(),
            sentence,
        });
    }
    StateRecord {
        state_id,
        grammar: GRAMMAR_ID,
        question: SPOT_QUESTION,
        state_sentence: render_state_sentence(board, piece),
        board: board.to_strings(),
        piece: piece.id(),
        options: recs,
    }
}

fn main() {
    let mut out_path = PathBuf::from("output/tetris_states/states.jsonl");
    let mut seed = 607u64;
    let args: Vec<String> = std::env::args().skip(1).collect();
    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--out" if i + 1 < args.len() => {
                i += 1;
                out_path = PathBuf::from(&args[i]);
            }
            "--seed" if i + 1 < args.len() => {
                i += 1;
                seed = args[i].parse().unwrap_or_else(|_| {
                    eprintln!("--seed must be an integer");
                    std::process::exit(1);
                });
            }
            other => {
                eprintln!("Unknown arg: {other}. Usage: [--out <path>] [--seed <u64>]");
                std::process::exit(1);
            }
        }
        i += 1;
    }

    // 1) Authored archetypes × every piece (84 states).
    let mut records: Vec<StateRecord> = Vec::new();
    for (name, board) in archetypes() {
        for piece in Piece::ALL {
            records.push(build_record(format!("arch:{name}:{}", piece.id()), &board, piece));
        }
    }

    // 2) Seeded play ladder (36 states) — Dellacherie-greedy, deterministic
    // given the seed.
    let mut rng = fastrand::Rng::with_seed(seed);
    for (id, board, piece) in play_ladder(&mut rng, 36) {
        records.push(build_record(id, &board, piece));
    }

    let n_states = records.len();
    let n_options: usize = records.iter().map(|r| r.options.len()).sum();
    let min_options = records.iter().map(|r| r.options.len()).min().unwrap_or(0);

    if let Some(dir) = out_path.parent() {
        std::fs::create_dir_all(dir).expect("create out dir");
    }
    let mut buf = String::new();
    for r in &records {
        buf.push_str(&serde_json::to_string(r).expect("serialize record"));
        buf.push('\n');
    }
    std::fs::write(&out_path, &buf).expect("write dump");

    let digest = blake3::hash(buf.as_bytes());
    eprintln!(
        "dumped {n_states} states ({n_options} options, min {min_options}/state) -> {}",
        out_path.display()
    );
    eprintln!("blake3: {digest}");
    eprintln!("grammar: {GRAMMAR_ID}  seed: {seed}");
}
