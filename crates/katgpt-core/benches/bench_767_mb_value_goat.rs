//! Bench 767 — mb_value GOAT G2 (Issue 767 T6).
//!
//! Arms at fly scale (686 PN / 4,064 KC top-200 / 97 MBON / 15 synapses per
//! KC — the fly's shape classes, seeded random wiring) and the saturated
//! regime (kc_active = n_kc — the honesty line where top-k selectivity buys
//! nothing and the update touches every synapse):
//!
//! 1. `code`      — the canonical fast top-k (`select_nth_unstable_by` +
//!    sort of the k winners).
//! 2. `code_ref`  — the full-sort reference path (`code_reference_into`,
//!    O(n log n)) — the G1 parity twin and the perf baseline.
//! 3. `value`     — the approach-minus-avoid readout of one code.
//! 4. `update`    — one dopamine event (bounded three-factor rule) on one
//!    code.
//!
//! Gate (the issue's T6 bar): `code` beats `code_ref` (selection wins as
//! k/n shrinks); `value`/`update` are µs-class at fly scale.
//! Run: `cargo bench -p katgpt-core --features mb_value --bench bench_767_mb_value_goat`

use criterion::{BenchmarkId, Criterion, black_box, criterion_group, criterion_main};
use katgpt_core::mb_value::{MbCircuit, MbCircuitConfig, MbScratch};

fn bench_cell(c: &mut Criterion, name: &str, cfg: &MbCircuitConfig) {
    let mut circuit = MbCircuit::new(cfg);
    // Calibrate on a synthetic batch so thresholds/eta are live.
    let n = 400;
    let mut feats = vec![0.0f32; n * cfg.n_features];
    let mut s = 0x1234_5678_9abc_def0u64;
    let mut next = || {
        s ^= s << 13;
        s ^= s >> 7;
        s ^= s << 17;
        (((s >> 40) as u32 & 0x007f_ffff) | 0x3f80_0000) as f32 - 1.0
    };
    for f in feats.iter_mut() {
        *f = next() * 2.0 - 1.0;
    }
    let mut action_codes = vec![0.0f32; 4 * cfg.n_action_dims];
    for (i, a) in action_codes.chunks_mut(cfg.n_action_dims).enumerate() {
        a[i.min(a.len().saturating_sub(1))] = 1.0;
    }
    circuit.calibrate(&feats, &action_codes, n, 0.5);

    let mut scratch = MbScratch::new(&circuit);
    let mut code = vec![0u32; circuit.kc_active()];
    let mut features = vec![0.0f32; cfg.n_features];
    for f in features.iter_mut() {
        *f = next() * 2.0 - 1.0;
    }
    let action = &action_codes[..cfg.n_action_dims];
    circuit.code_into(&features, action, &mut scratch, &mut code);

    let group_name = "mb_value";
    c.bench_with_input(
        BenchmarkId::new(format!("{group_name}/{name}/code_topk"), cfg.n_kc),
        &(),
        |b, _| {
            b.iter(|| {
                circuit.code_into(
                    black_box(&features),
                    black_box(action),
                    black_box(&mut scratch),
                    black_box(&mut code),
                );
            });
        },
    )
    .bench_with_input(
        BenchmarkId::new(format!("{group_name}/{name}/code_fullsort_ref"), cfg.n_kc),
        &(),
        |b, _| {
            b.iter(|| {
                circuit.code_reference_into(
                    black_box(&features),
                    black_box(action),
                    black_box(&mut scratch),
                    black_box(&mut code),
                );
            });
        },
    )
    .bench_with_input(
        BenchmarkId::new(format!("{group_name}/{name}/value"), cfg.n_kc),
        &(),
        |b, _| b.iter(|| circuit.value(black_box(&code), black_box(&mut scratch))),
    )
    .bench_with_input(
        BenchmarkId::new(format!("{group_name}/{name}/dopamine_update"), cfg.n_kc),
        &(),
        |b, _| {
            // NOTE: &mut circuit — each iteration is a real bounded update on
            // the same code; the clamp keeps it stationary in cost.
            b.iter(|| circuit.dopamine_update(black_box(&code), black_box(0.5)));
        },
    );
}

fn bench_mb_value(c: &mut Criterion) {
    // Fly scale, sparse regime (200 of 4,064 = 4.9% active).
    bench_cell(c, "fly_sparse", &MbCircuitConfig::fly());
    // Saturated regime: every KC active — the honesty line.
    let mut sat = MbCircuitConfig::fly();
    sat.kc_active = sat.n_kc;
    bench_cell(c, "fly_saturated", &sat);
    // Toy scale (the G1 corridor's circuit).
    bench_cell(c, "toy", &MbCircuitConfig::toy());
}

criterion_group!(benches, bench_mb_value);
criterion_main!(benches);
