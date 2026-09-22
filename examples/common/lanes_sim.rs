//! Three-lanes micro-arena sim — katgpt-rs Plan 607 T5. The laya page's
//! lanes demo reads each lane's state ("blocked by a barrier" vs
//! "blocked by a train" separated the same lane by 0.75 → 0.45 — wording
//! sensitivity is a MEASURED trap). Our answer is structural: ONE pinned
//! noun per obstacle class, never varied (`obstacle_noun`), so the trap is
//! avoided by construction instead of tuned around.
//!
//! Decision shape: the runner must commit to a lane now. The three options
//! are the lanes in PINNED order [left, middle, right]; each option's
//! sentence describes that lane's state; the scorer reads p(safe) per lane
//! and the argmax IS the lane.

// Each consumer compiles a different half (the 01 enumerator uses
// enumerate_states + the grammar consts; the 02 arena uses renders,
// features and the play loop) — per-consumer dead-code warns would fire.
#![allow(dead_code)]

use serde::{Deserialize, Serialize};

/// Grammar identity stamped into every dump record.
pub const GRAMMAR_ID: &str = "laya-lanes-v1";
/// The per-option question, world-anchored.
pub const QUESTION: &str = "Is this lane safe to run?";

/// The pinned lane order (index 0 = left).
pub const LANE_NAMES: [&str; 3] = ["left", "middle", "right"];

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ObsKind {
    Clear,
    Barrier,
    Train,
    Rock,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Dist {
    Close,
    Far,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct LaneObs {
    pub kind: ObsKind,
    pub dist: Dist,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct LanesState {
    pub lanes: [LaneObs; 3],
}

/// THE WORDING PIN — one noun per obstacle class, never varied. Laya's own
/// measured trap ("barrier" 0.75 vs "train" 0.45 for the same lane) is a
/// noun-choice effect; a closed grammar that never varies the noun cannot
/// trip it.
pub fn obstacle_noun(k: ObsKind) -> &'static str {
    match k {
        ObsKind::Clear => "",
        ObsKind::Barrier => "a barrier",
        ObsKind::Train => "a train",
        ObsKind::Rock => "a rock",
    }
}

fn dist_clause(d: Dist) -> &'static str {
    match d {
        Dist::Close => "close",
        Dist::Far => "far",
    }
}

/// The lane's state clause.
pub fn lane_clause(l: LaneObs) -> String {
    match l.kind {
        ObsKind::Clear => "clear ahead".to_string(),
        k => format!(
            "blocked {} ahead by {}",
            dist_clause(l.dist),
            obstacle_noun(k)
        ),
    }
}

/// The per-option sentence: `The {name} lane is {clause}.`
pub fn render_option_sentence(s: &LanesState, lane: usize) -> String {
    format!(
        "The {} lane is {}.",
        LANE_NAMES[lane],
        lane_clause(s.lanes[lane])
    )
}

/// The state context sentence: all three lanes, pinned order.
pub fn render_state_sentence(s: &LanesState) -> String {
    format!(
        "The left lane is {}; the middle lane is {}; the right lane is {}.",
        lane_clause(s.lanes[0]),
        lane_clause(s.lanes[1]),
        lane_clause(s.lanes[2])
    )
}

/// The 8 frozen feature columns in pinned order (lane-local + the state
/// context — this ORDER is part of the committed recipe).
pub const FEATURE_NAMES: [&str; 8] = [
    "blocked",
    "close",
    "far",
    "is_barrier",
    "is_train",
    "is_rock",
    "blocked_neighbors",
    "clear_lanes",
];

pub fn feature_row(s: &LanesState, lane: usize) -> [f64; 8] {
    let l = s.lanes[lane];
    let bit = |k: ObsKind| (l.kind == k) as u8 as f64;
    let blocked = l.kind != ObsKind::Clear;
    let blocked_neighbors = s
        .lanes
        .iter()
        .enumerate()
        .filter(|&(i, x)| i != lane && x.kind != ObsKind::Clear)
        .count() as f64;
    let clear_lanes = s.lanes.iter().filter(|x| x.kind == ObsKind::Clear).count() as f64;
    [
        blocked as u8 as f64,
        (blocked && l.dist == Dist::Close) as u8 as f64,
        (blocked && l.dist == Dist::Far) as u8 as f64,
        bit(ObsKind::Barrier),
        bit(ObsKind::Train),
        bit(ObsKind::Rock),
        blocked_neighbors,
        clear_lanes,
    ]
}

/// The code-arithmetic context policy: clear beats far-blocked beats
/// close-blocked, pinned lowest-index tie-break.
pub fn clearest_pick(s: &LanesState) -> usize {
    let rank = |l: &LaneObs| match l.kind {
        ObsKind::Clear => 0u8,
        _ => match l.dist {
            Dist::Far => 1u8,
            Dist::Close => 2u8,
        },
    };
    let mut best = 0usize;
    let mut best_rank = 3u8;
    for (i, l) in s.lanes.iter().enumerate() {
        let r = rank(l);
        if r < best_rank {
            best_rank = r;
            best = i;
        }
    }
    best
}

fn sample_lane(rng: &mut fastrand::Rng) -> LaneObs {
    // ~15% clear lanes; close obstacles dominate (60/40) — the interesting
    // decisions are close ones.
    if rng.u32(..100) < 15 {
        return LaneObs {
            kind: ObsKind::Clear,
            dist: Dist::Close,
        };
    }
    let kind = match rng.u32(..3) {
        0 => ObsKind::Barrier,
        1 => ObsKind::Train,
        _ => ObsKind::Rock,
    };
    let dist = if rng.u32(..5) < 3 {
        Dist::Close
    } else {
        Dist::Far
    };
    LaneObs { kind, dist }
}

/// One seeded lanes state (also the play loop's step sampler).
pub fn sample_state(rng: &mut fastrand::Rng) -> LanesState {
    LanesState {
        lanes: [sample_lane(rng), sample_lane(rng), sample_lane(rng)],
    }
}

/// Seed the corpus with the obstacle-count distribution biased toward
/// decision-interesting states (1–2 blocked lanes; all-clear and all-blocked
/// states kept but rare). Deterministic; deduped.
pub fn enumerate_states(seed: u64, n: usize) -> Vec<(String, LanesState)> {
    let mut rng = fastrand::Rng::with_seed(seed);
    let mut out: Vec<(String, LanesState)> = Vec::with_capacity(n);
    let mut seen = std::collections::HashSet::new();
    while out.len() < n {
        let s = sample_state(&mut rng);
        let blocked = s.lanes.iter().filter(|l| l.kind != ObsKind::Clear).count();
        // Reject the trivial extremes most of the time: 0-blocked states
        // are pure ties, 3-blocked states carry no safe option.
        let keep = match blocked {
            0 => rng.u32(..4) == 0,
            3 => rng.u32(..4) == 0,
            _ => true,
        };
        if keep && seen.insert(s) {
            out.push((format!("lanes_{:03}", out.len()), s));
        }
    }
    out
}

/// One run under `policy`: each step draws a seeded state, the policy picks
/// a lane, a close-blocked pick ends the run (far-blocked passes this
/// step). Returns steps survived.
pub fn play_game(
    policy: &dyn Fn(&LanesState) -> usize,
    rng: &mut fastrand::Rng,
    max_steps: usize,
) -> u32 {
    for step in 0..max_steps {
        let s = sample_state(rng);
        let lane = policy(&s);
        let l = s.lanes[lane];
        if l.kind != ObsKind::Clear && l.dist == Dist::Close {
            return step as u32;
        }
    }
    max_steps as u32
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn wording_pin_exact() {
        // The nouns are contract, not style — one spelling per class.
        assert_eq!(obstacle_noun(ObsKind::Barrier), "a barrier");
        assert_eq!(obstacle_noun(ObsKind::Train), "a train");
        assert_eq!(obstacle_noun(ObsKind::Rock), "a rock");
        let s = LanesState {
            lanes: [
                LaneObs {
                    kind: ObsKind::Clear,
                    dist: Dist::Close,
                },
                LaneObs {
                    kind: ObsKind::Train,
                    dist: Dist::Close,
                },
                LaneObs {
                    kind: ObsKind::Rock,
                    dist: Dist::Far,
                },
            ],
        };
        assert_eq!(
            render_option_sentence(&s, 0),
            "The left lane is clear ahead."
        );
        assert_eq!(
            render_option_sentence(&s, 1),
            "The middle lane is blocked close ahead by a train."
        );
        assert_eq!(
            render_option_sentence(&s, 2),
            "The right lane is blocked far ahead by a rock."
        );
        assert_eq!(
            render_state_sentence(&s),
            "The left lane is clear ahead; the middle lane is blocked close ahead by a train; the right lane is blocked far ahead by a rock."
        );
    }

    #[test]
    fn grammar_has_no_digits() {
        for (_, s) in enumerate_states(607, 50) {
            let st = render_state_sentence(&s);
            assert!(
                !st.chars().any(|c| c.is_ascii_digit()),
                "state sentence leaked a number: {st:?}"
            );
            for lane in 0..3 {
                let o = render_option_sentence(&s, lane);
                assert!(
                    !o.chars().any(|c| c.is_ascii_digit()),
                    "option sentence leaked a number: {o:?}"
                );
            }
        }
    }

    #[test]
    fn feature_columns_are_consistent() {
        for (_, s) in enumerate_states(607, 50) {
            for lane in 0..3 {
                let f = feature_row(&s, lane);
                // close XOR far for blocked lanes, neither for clear ones.
                assert_eq!((f[1] > 0.0) as u8 + (f[2] > 0.0) as u8, f[0] as u8);
                // exactly one noun bit for blocked lanes.
                assert_eq!(
                    (f[3] > 0.0) as u8 + (f[4] > 0.0) as u8 + (f[5] > 0.0) as u8,
                    f[0] as u8
                );
                // neighbors + self = state blocked count.
                let blocked_state =
                    s.lanes.iter().filter(|l| l.kind != ObsKind::Clear).count() as f64;
                assert_eq!(f[6] + f[0], blocked_state);
            }
        }
    }

    #[test]
    fn enumeration_is_deterministic() {
        let a = enumerate_states(607, 100);
        let b = enumerate_states(607, 100);
        assert_eq!(a, b);
        let distinct: std::collections::HashSet<_> = a.iter().map(|(_, s)| *s).collect();
        assert_eq!(distinct.len(), a.len());
    }

    #[test]
    fn clearest_prefers_clear_then_far() {
        let mk = |k, d| LaneObs { kind: k, dist: d };
        assert_eq!(
            clearest_pick(&LanesState {
                lanes: [
                    mk(ObsKind::Train, Dist::Close),
                    mk(ObsKind::Clear, Dist::Close),
                    mk(ObsKind::Rock, Dist::Close)
                ]
            }),
            1
        );
        // Tie between two clears → lowest index.
        assert_eq!(
            clearest_pick(&LanesState {
                lanes: [
                    mk(ObsKind::Barrier, Dist::Close),
                    mk(ObsKind::Clear, Dist::Close),
                    mk(ObsKind::Clear, Dist::Close)
                ]
            }),
            1
        );
        // Far-blocked beats close-blocked.
        assert_eq!(
            clearest_pick(&LanesState {
                lanes: [
                    mk(ObsKind::Rock, Dist::Far),
                    mk(ObsKind::Barrier, Dist::Close),
                    mk(ObsKind::Train, Dist::Close)
                ]
            }),
            0
        );
    }

    #[test]
    fn play_game_is_deterministic_and_scores() {
        let run = |policy: &dyn Fn(&LanesState) -> usize, seed: u64| {
            let mut rng = fastrand::Rng::with_seed(seed);
            play_game(policy, &mut rng, 60)
        };
        let clearest = run(&clearest_pick, 42);
        assert_eq!(clearest, run(&clearest_pick, 42));
        // The code-arithmetic policy is the sanity ceiling over the
        // constant middle-lane policy on the same streams.
        let middle = run(&|_| 1usize, 42);
        assert!(clearest >= middle, "clearest {clearest} < middle {middle}");
    }
}
