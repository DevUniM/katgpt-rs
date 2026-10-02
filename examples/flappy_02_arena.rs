//! Flappy micro-arena — katgpt-rs Plan 607 T5. Replays the committed
//! oracle fixture (`flappy_oracle_laya_en_v2.jsonl` — the Bench 880/881
//! published record, grammar v2 FROZEN) through BOTH scoring
//! arms and reads the same G1 gate shape the Tetris arenas established:
//!
//! * T1 — the untuned sentence-cosine scorer (`CentroidTable::pick` over
//!   the hashbag trigram embeddings; the tetris_02 arm),
//! * T3 — the corpus-fitted head over the frozen features
//!   (`FittedHead` via `linalg::ridge_solve`'s f64 path; the tetris_03
//!   arm) — λ by state-level LOO MSE, agreement reported at the chosen λ,
//!   in-corpus AND leave-one-state-out.
//!
//! Gates: G1 = agreement > constant-pick AND > chance (never vs laya
//! alone); discrimination floor = distinct picks ≥ 2; determinism =
//! double-fit bit-identical + BLAKE3 anchors. G2/G4 formal rows live in
//! katgpt-core's bench_878 + state_option_head_alloc_check; this arena
//! prints the fixture-replay AGREEMENT half plus a play-loop context
//! metric (pipes passed under each policy).

#[path = "common/flappy_sim.rs"]
mod flappy_sim;
#[path = "common/micro_dump.rs"]
mod micro_dump;
#[path = "common/micro_fit.rs"]
mod micro_fit;

use katgpt_core::state_option_scoring::head::HeadFitter;
use micro_dump::{
    MicroStateFixture, default_fixture, load_micro_states, pct, print_reading, read_reading,
};
use micro_fit::{D, build_corpus, head_digest, loo_select, t1_pick};
use std::path::PathBuf;

use flappy_sim::{ACTION_LABELS, ACTIONS, Action, FlappyState};

/// The drift detector: recompute EVERYTHING the arena consumes from the
/// seed state — state sentence, option order/labels, features (exact f64),
/// option sentences.
fn drift(st: &MicroStateFixture) -> Result<FlappyState, String> {
    let s: FlappyState = serde_json::from_value(st.state.clone())
        .map_err(|e| format!("{}: seed state: {e}", st.state_id))?;
    let st_sentence = flappy_sim::render_state_sentence(&s);
    if st_sentence != st.state_sentence {
        return Err(format!(
            "{}: state sentence drifted\n  fixture:    {:?}\n  recomputed: {:?}",
            st.state_id, st.state_sentence, st_sentence
        ));
    }
    if st.options.len() != ACTIONS.len() {
        return Err(format!(
            "{}: option count drifted (fixture {}, pinned {})",
            st.state_id,
            st.options.len(),
            ACTIONS.len()
        ));
    }
    if st.argmax >= st.options.len() {
        return Err(format!("{}: argmax out of range", st.state_id));
    }
    for (ai, o) in st.options.iter().enumerate() {
        if ACTION_LABELS[ai] != o.label {
            return Err(format!("{}: option label drifted at {ai}", st.state_id));
        }
        if o.features.as_slice() != flappy_sim::feature_row(&s, ACTIONS[ai]).as_slice() {
            return Err(format!("{}: features drifted at {ai}", st.state_id));
        }
        // The v2 fixture's sentences are FROZEN v2 renders — the live
        // grammar moved to v3 (Issue 876), so the drift check pins the
        // frozen renderer, never the current one.
        let sentence = flappy_sim::render_option_sentence_v2(&s, ACTIONS[ai]);
        if sentence != o.sentence {
            return Err(format!(
                "{}: option sentence drifted at {ai}\n  fixture:    {:?}\n  recomputed: {:?}",
                st.state_id, o.sentence, sentence
            ));
        }
    }
    Ok(s)
}

fn feature_of(o: &micro_dump::MicroOptionFixture) -> [f64; micro_fit::F] {
    let mut row = [0.0f64; micro_fit::F];
    row.copy_from_slice(&o.features);
    row
}

fn main() {
    let mut fixture_path = default_fixture("flappy", "v2");
    let mut games = 16usize;
    let mut seed = 607u64;
    let mut max_pipes = 100usize;
    let args: Vec<String> = std::env::args().skip(1).collect();
    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--fixture" if i + 1 < args.len() => {
                i += 1;
                fixture_path = PathBuf::from(&args[i]);
            }
            "--games" if i + 1 < args.len() => {
                i += 1;
                games = args[i].parse().expect("--games <n>");
            }
            "--seed" if i + 1 < args.len() => {
                i += 1;
                seed = args[i].parse().expect("--seed <u64>");
            }
            "--max-pipes" if i + 1 < args.len() => {
                i += 1;
                max_pipes = args[i].parse().expect("--max-pipes <n>");
            }
            other => {
                eprintln!(
                    "Unknown arg: {other}. Usage: [--fixture <path>] [--games <n>] [--seed <u64>] [--max-pipes <n>]"
                );
                std::process::exit(1);
            }
        }
        i += 1;
    }

    println!("== Plan 607 T5 — the Flappy micro-arena ==");
    println!("fixture: {}", fixture_path.display());

    let states = load_micro_states(&fixture_path, drift);
    let n_options: usize = states.iter().map(|(f, _)| f.options.len()).sum();
    println!(
        "drift check: PASS — {} states / {n_options} options recompute byte-identically",
        states.len()
    );

    // ── T1 arm: untuned sentence cosine ──────────────────────────────────
    let t1_decide = |_s: usize, f: &MicroStateFixture| -> usize {
        let sents: Vec<String> = f.options.iter().map(|o| o.sentence.clone()).collect();
        t1_pick(&f.state_sentence, &sents)
    };
    let t1 = read_reading(&states, &t1_decide, &|s: &FlappyState| {
        flappy_sim::gap_center_pick(s)
    });
    print_reading(
        "T1 sentence-cosine (untuned, K=2)",
        &t1,
        "gap-center code policy",
    );

    // ── T3 arm: the corpus-fitted head ───────────────────────────────────
    let argmaxes: Vec<usize> = states.iter().map(|(f, _)| f.argmax).collect();
    let (corpus, stdizer) = build_corpus(&states, feature_of);
    let mut fitter = HeadFitter::<D>::new();
    println!(
        "\nλ selection (state-level LOO MSE over the pinned grid; agreement reported, never selected):"
    );
    let (chosen, loo_picks, lam_rows) = loo_select(&mut fitter, &corpus, &argmaxes);
    for r in &lam_rows {
        println!(
            "  λ={:<5.3}  LOO MSE {:.6}  LOO agreement {}/{} ({})",
            r.lam,
            r.mse,
            r.agree,
            states.len(),
            pct(r.agree, states.len())
        );
    }
    println!("  chosen λ = {chosen} (lowest LOO MSE)");

    let head = fitter.fit_into(&corpus.rows, &corpus.targets, chosen);
    let head_decide = |s: usize, _f: &MicroStateFixture| -> usize {
        let (a, b) = (corpus.offsets[s], corpus.offsets[s + 1]);
        head.pick(&corpus.rows[a..b], states[s].0.options.len())
    };
    let head_reading = read_reading(&states, &head_decide, &|s: &FlappyState| {
        flappy_sim::gap_center_pick(s)
    });
    print_reading(
        &format!("T3 corpus-fitted head (in-corpus, D={D})"),
        &head_reading,
        "gap-center code policy",
    );
    let loo_agree = loo_picks
        .iter()
        .zip(&argmaxes)
        .filter(|(p, a)| p == a)
        .count();
    println!(
        "  LOO raw agreement:  {}/{} ({})  [fit per held-out state — the generalization reading]",
        loo_agree,
        states.len(),
        pct(loo_agree, states.len())
    );

    // ── Determinism: double fit bit-identical + BLAKE3 anchors ───────────
    let head2 = fitter.fit_into(&corpus.rows, &corpus.targets, chosen);
    let (d1, d2) = (head_digest(&head), head_digest(&head2));
    println!(
        "\ndeterminism: double-fit {} (head blake3 {d1})",
        if d1 == d2 {
            "bit-identical ✓"
        } else {
            "DIVERGED ✗"
        }
    );
    assert_eq!(
        d1, d2,
        "same corpus → bit-identical head (Plan 607 T3's line)"
    );
    let picks_digest = || -> blake3::Hash {
        let mut stream: Vec<u8> = Vec::new();
        for (s, (f, _)) in states.iter().enumerate() {
            stream.push(head_decide(s, f) as u8);
        }
        blake3::hash(&stream)
    };
    let (p1, p2) = (picks_digest(), picks_digest());
    println!(
        "decisions: two passes {} (blake3 {p1})",
        if p1 == p2 {
            "byte-identical ✓"
        } else {
            "DIVERGED ✗"
        }
    );
    assert_eq!(p1, p2, "same corpus → bit-identical decisions");

    // ── Latency context (formal G2 = katgpt-core bench_878) ─────────────
    let mut samples: Vec<u128> = Vec::with_capacity(states.len() * 25);
    for _ in 0..25 {
        for ((a, b), (f, _)) in corpus
            .offsets
            .windows(2)
            .map(|w| (w[0], w[1]))
            .zip(states.iter())
        {
            let t = std::time::Instant::now();
            let pick = head.pick(&corpus.rows[a..b], f.options.len());
            samples.push(t.elapsed().as_nanos());
            std::hint::black_box(pick);
        }
    }
    samples.sort_unstable();
    let (p50, sup50) = katgpt_core::stats::nearest_rank(&samples, 0.50);
    let (p99, sup99) = katgpt_core::stats::nearest_rank(&samples, 0.99);
    println!(
        "\nlatency context (head pick per decision SET, K=2, D={D}; formal bar = bench_878): \
         p50 {p50} ns | p99 {p99} ns (n={}, tail support {sup50}/{sup99})",
        samples.len()
    );

    // ── Seeded flights: pipes passed under each policy ───────────────────
    let flight = |policy: &dyn Fn(&FlappyState) -> Action| -> Vec<u32> {
        (0..games)
            .map(|i| {
                let mut rng = fastrand::Rng::with_seed(seed.wrapping_add(i as u64));
                flappy_sim::play_game(policy, &mut rng, max_pipes)
            })
            .collect()
    };
    let to_action = |pick: usize| ACTIONS[pick];
    // The flight policies replay the fixture's FROZEN v2 grammar (the
    // fixture replay above is v2; the live renders must match it).
    let t1_live = |s: &FlappyState| -> Action {
        let st = flappy_sim::render_state_sentence(s);
        let sents: Vec<String> = ACTIONS
            .iter()
            .map(|&a| flappy_sim::render_option_sentence_v2(s, a))
            .collect();
        to_action(t1_pick(&st, &sents))
    };
    let t3_live = |s: &FlappyState| -> Action {
        let rows: Vec<[f64; D]> = ACTIONS
            .iter()
            .map(|&a| stdizer.design(&flappy_sim::feature_row(s, a)))
            .collect();
        to_action(head.pick(&rows, ACTIONS.len()))
    };
    println!("\npipes passed ({games} seeded flights/policy, shared streams, cap {max_pipes}):");
    let gap_center_live = |s: &FlappyState| to_action(flappy_sim::gap_center_pick(s));
    type NamedPolicy<'s, S, Out> = (&'s str, &'s dyn Fn(&S) -> Out);
    let policies: Vec<NamedPolicy<FlappyState, Action>> = vec![
        ("always_flap", &|_| Action::Flap),
        ("gap_center", &gap_center_live),
        ("t1_cosine", &t1_live),
        ("t3_head", &t3_live),
    ];
    for (name, policy) in &policies {
        let mut per = flight(policy);
        let total: u32 = per.iter().sum();
        per.sort_unstable();
        let mean = total as f64 / games as f64;
        println!(
            "  {name:>13}: total {total:>4} | mean {mean:6.2} | median {} | max {}",
            per[games / 2],
            per[games - 1]
        );
    }

    println!(
        "\nGate pointers: G2 = katgpt-core bench_878_state_option_head_goat · G4 = \
         katgpt-core state_option_head_alloc_check · this run's agreement = the \
         .benchmarks/880 G1 row"
    );
}
