//! Three-lanes micro-arena — katgpt-rs Plan 607 T5. The flappy_02 shape
//! over the lanes game: the T1 untuned sentence-cosine arm and the T3
//! corpus-fitted head arm, replayed against the committed oracle fixture
//! (`lanes_oracle_laya_en_v1.jsonl`) with the same G1 gate shape (raw >
//! constant-pick AND > chance, never vs laya alone), the discrimination
//! floor, and the determinism anchors. Play-loop context metric: steps
//! survived under each policy (a close-blocked pick ends the run).

#[path = "common/lanes_sim.rs"]
mod lanes_sim;
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

use lanes_sim::{LANE_NAMES, LanesState};

/// The drift detector: recompute EVERYTHING the arena consumes from the
/// seed state — state sentence, option order/labels, features (exact f64),
/// option sentences.
fn drift(st: &MicroStateFixture) -> Result<LanesState, String> {
    let s: LanesState = serde_json::from_value(st.state.clone())
        .map_err(|e| format!("{}: seed state: {e}", st.state_id))?;
    let st_sentence = lanes_sim::render_state_sentence(&s);
    if st_sentence != st.state_sentence {
        return Err(format!(
            "{}: state sentence drifted\n  fixture:    {:?}\n  recomputed: {:?}",
            st.state_id, st.state_sentence, st_sentence
        ));
    }
    if st.options.len() != LANE_NAMES.len() {
        return Err(format!(
            "{}: option count drifted (fixture {}, pinned {})",
            st.state_id,
            st.options.len(),
            LANE_NAMES.len()
        ));
    }
    if st.argmax >= st.options.len() {
        return Err(format!("{}: argmax out of range", st.state_id));
    }
    for (lane, o) in st.options.iter().enumerate() {
        if o.label != format!("lane{lane}") {
            return Err(format!("{}: option label drifted at {lane}", st.state_id));
        }
        if o.features.as_slice() != lanes_sim::feature_row(&s, lane).as_slice() {
            return Err(format!("{}: features drifted at {lane}", st.state_id));
        }
        let sentence = lanes_sim::render_option_sentence(&s, lane);
        if sentence != o.sentence {
            return Err(format!(
                "{}: option sentence drifted at {lane}\n  fixture:    {:?}\n  recomputed: {:?}",
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
    let mut fixture_path = default_fixture("lanes", "v1");
    let mut games = 16usize;
    let mut seed = 607u64;
    let mut max_steps = 60usize;
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
            "--max-steps" if i + 1 < args.len() => {
                i += 1;
                max_steps = args[i].parse().expect("--max-steps <n>");
            }
            other => {
                eprintln!(
                    "Unknown arg: {other}. Usage: [--fixture <path>] [--games <n>] [--seed <u64>] [--max-steps <n>]"
                );
                std::process::exit(1);
            }
        }
        i += 1;
    }

    println!("== Plan 607 T5 — the three-lanes micro-arena ==");
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
    let t1 = read_reading(&states, &t1_decide, &|s: &LanesState| {
        lanes_sim::clearest_pick(s)
    });
    print_reading(
        "T1 sentence-cosine (untuned, K=3)",
        &t1,
        "clearest-lane code policy",
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
    let head_reading = read_reading(&states, &head_decide, &|s: &LanesState| {
        lanes_sim::clearest_pick(s)
    });
    print_reading(
        &format!("T3 corpus-fitted head (in-corpus, D={D})"),
        &head_reading,
        "clearest-lane code policy",
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
        "\nlatency context (head pick per decision SET, K=3, D={D}; formal bar = bench_878): \
         p50 {p50} ns | p99 {p99} ns (n={}, tail support {sup50}/{sup99})",
        samples.len()
    );

    // ── Seeded runs: steps survived under each policy ────────────────────
    let run = |policy: &dyn Fn(&LanesState) -> usize| -> Vec<u32> {
        (0..games)
            .map(|i| {
                let mut rng = fastrand::Rng::with_seed(seed.wrapping_add(i as u64));
                lanes_sim::play_game(policy, &mut rng, max_steps)
            })
            .collect()
    };
    let t1_live = |s: &LanesState| -> usize {
        let st = lanes_sim::render_state_sentence(s);
        let sents: Vec<String> = (0..3)
            .map(|lane| lanes_sim::render_option_sentence(s, lane))
            .collect();
        t1_pick(&st, &sents)
    };
    let t3_live = |s: &LanesState| -> usize {
        let rows: Vec<[f64; D]> = (0..3)
            .map(|lane| stdizer.design(&lanes_sim::feature_row(s, lane)))
            .collect();
        head.pick(&rows, 3)
    };
    type NamedPolicy<'s, S, Out> = (&'s str, &'s dyn Fn(&S) -> Out);
    println!("\nsteps survived ({games} seeded runs/policy, shared streams, cap {max_steps}):");
    let policies: Vec<NamedPolicy<LanesState, usize>> = vec![
        ("always_middle", &|_| 1usize),
        ("clearest", &lanes_sim::clearest_pick),
        ("t1_cosine", &t1_live),
        ("t3_head", &t3_live),
    ];
    for (name, policy) in &policies {
        let mut per = run(policy);
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
