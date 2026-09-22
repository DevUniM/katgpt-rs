//! Bench 800 — SIMD bf16⇄f32 conversion GOAT gate (Issue 800 Arm A).
//!
//! G1 known-answer vs `half` (RNE bit-exactness incl. NaN class) lives in the
//! module's #[cfg(test)] self-tests; THIS bench is the G2 throughput gate
//! (≥4× the scalar loop at 8 lanes, aarch64 NEON / x86_64 AVX2) + the G4
//! zero-alloc witness (into_buf over caller-owned buffers).
//!
//! Convention: std::time::Instant + harness = false (bench_417 style).
//! N = 65536 elements · 3 warmups · 7 timed reps · MEDIAN reported.
//! Traffic: 6 bytes/element both directions (widen 2R+4W, narrow 4R+2W).
//!
//! # Run
//!
//! ```bash
//! CARGO_TARGET_DIR=/tmp/krs_bf16 cargo bench -p katgpt-core \
//!   --features bf16_simd --bench bench_800_bf16_simd
//! ```

#![cfg(feature = "bf16_simd")]

use std::hint::black_box;
use std::time::Instant;

use katgpt_core::bf16_convert::{
    bf16_bits_to_f32_into, bf16_bits_to_f32_scalar_into, f32_to_bf16_rne_into,
    f32_to_bf16_rne_scalar_into, f32_to_bf16_trunc_into, f32_to_bf16_trunc_scalar_into,
};

const N: usize = 65536;
const WARMUP: usize = 3;
const REPS: usize = 7;
const G2_GATE: f64 = 4.0;

/// Median-of-REPS wall time in ns; `WARMUP` untimed calls first.
fn median_ns(mut f: impl FnMut()) -> f64 {
    for _ in 0..WARMUP {
        f();
    }
    let mut ds = Vec::with_capacity(REPS);
    for _ in 0..REPS {
        let t = Instant::now();
        f();
        ds.push(t.elapsed().as_secs_f64() * 1e9);
    }
    ds.sort_by(|a, b| a.partial_cmp(b).expect("durations are never NaN"));
    ds[ds.len() / 2]
}

fn main() {
    let backend = if cfg!(target_arch = "aarch64") {
        "NEON (aarch64)"
    } else if cfg!(all(target_arch = "x86_64", target_feature = "avx2")) {
        "AVX2 (x86_64 +avx2)"
    } else {
        "scalar fallback (no SIMD arm on this target)"
    };

    println!("════════════════════════════════════════════════════════════════════");
    println!("  Bench 800 — SIMD bf16⇄f32 conversion G2 gate (Issue 800 Arm A)");
    println!("  backend: {backend} · N={N} · warmup={WARMUP} · reps={REPS} (median)");
    println!("  G2 gate: narrow RNE ≥ {G2_GATE}× the scalar loop");
    println!("════════════════════════════════════════════════════════════════════\n");

    // ── deterministic mixed-class buffers ────────────────────────────────
    let mut rng = fastrand::Rng::with_seed(0x800_BEEF);
    let mut f32_src = Vec::with_capacity(N);
    for i in 0..N {
        if i % 64 == 0 {
            // full bit-space sample: NaN / Inf / denormals included
            f32_src.push(f32::from_bits(rng.u32(..)));
        } else {
            let sign = (rng.u32(..) & 1) << 31;
            let exp = (0x3Eu32 + rng.u8(0..8) as u32) << 23; // ~[6e-4, 1e2]
            let man = rng.u32(..) & 0x007F_FFFF;
            f32_src.push(f32::from_bits(sign | exp | man));
        }
    }
    let mut u16_src = vec![0u16; N];
    f32_to_bf16_rne_scalar_into(&f32_src, &mut u16_src);

    // ── in-bench parity guard (the full `half` G1 oracle lives in cfg(test))
    {
        let mut ref16 = vec![0u16; N];
        let mut simd16 = vec![0u16; N];
        f32_to_bf16_rne_scalar_into(&f32_src, &mut ref16);
        f32_to_bf16_rne_into(&f32_src, &mut simd16);
        assert_eq!(ref16, simd16, "RNE SIMD/scalar parity on bench data");
        let mut ref32 = vec![0f32; N];
        let mut simd32 = vec![0f32; N];
        bf16_bits_to_f32_scalar_into(&u16_src, &mut ref32);
        bf16_bits_to_f32_into(&u16_src, &mut simd32);
        assert_eq!(
            bytemuck::cast_slice::<f32, u32>(&ref32),
            bytemuck::cast_slice::<f32, u32>(&simd32),
            "widen SIMD/scalar bit-parity on bench data"
        );
        println!("parity guard: scalar == SIMD on bench data ✓\n");
    }

    let mut dst_f32 = vec![0f32; N];
    let mut dst_u16 = vec![0u16; N];
    let mut sink = 0u32;

    let w_scalar = median_ns(|| {
        bf16_bits_to_f32_scalar_into(black_box(&u16_src), &mut dst_f32);
        sink ^= dst_f32[0].to_bits() ^ dst_f32[N - 1].to_bits();
    });
    black_box(sink);
    let w_simd = median_ns(|| {
        bf16_bits_to_f32_into(black_box(&u16_src), &mut dst_f32);
        sink ^= dst_f32[0].to_bits() ^ dst_f32[N - 1].to_bits();
    });
    black_box(sink);

    let r_scalar = median_ns(|| {
        f32_to_bf16_rne_scalar_into(black_box(&f32_src), &mut dst_u16);
        sink = sink.wrapping_add(dst_u16[0] as u32) ^ dst_u16[N - 1] as u32;
    });
    black_box(sink);
    let r_simd = median_ns(|| {
        f32_to_bf16_rne_into(black_box(&f32_src), &mut dst_u16);
        sink = sink.wrapping_add(dst_u16[0] as u32) ^ dst_u16[N - 1] as u32;
    });
    black_box(sink);

    let t_scalar = median_ns(|| {
        f32_to_bf16_trunc_scalar_into(black_box(&f32_src), &mut dst_u16);
        sink = sink.wrapping_add(dst_u16[0] as u32) ^ dst_u16[N - 1] as u32;
    });
    black_box(sink);
    let t_simd = median_ns(|| {
        f32_to_bf16_trunc_into(black_box(&f32_src), &mut dst_u16);
        sink = sink.wrapping_add(dst_u16[0] as u32) ^ dst_u16[N - 1] as u32;
    });
    black_box(sink);

    // ── report ───────────────────────────────────────────────────────────
    println!(
        "  {:<20} {:>11} {:>11} {:>7}  {:>12} {:>12}",
        "kernel", "scalar ns", "simd ns", "×", "scalar M/s", "simd M/s"
    );
    println!("  {}", "-".repeat(78));
    for (label, s, d) in [
        ("widen  u16→f32", w_scalar, w_simd),
        ("narrow RNE f32→u16", r_scalar, r_simd),
        ("narrow trunc f32→u16", t_scalar, t_simd),
    ] {
        println!(
            "  {:<20} {:>11.0} {:>11.0} {:>6.2}× {:>12.1} {:>12.1}",
            label,
            s,
            d,
            s / d,
            N as f64 / s * 1e3,
            N as f64 / d * 1e3
        );
        println!(
            "  {:<20} {:>11} {:>11.1} {:>7}  {:>12.1} {:>12.1}",
            "",
            "GB/s:",
            (N * 6) as f64 / s,
            "",
            "",
            (N * 6) as f64 / d
        );
    }

    let g2 = r_scalar / r_simd;
    let g2_pass = g2 >= G2_GATE;
    println!();
    println!(
        "  G2 gate (narrow RNE ≥ {G2_GATE}×): {:.2}× — {}",
        g2,
        if g2_pass { "PASS" } else { "FAIL" }
    );
    println!(
        "  G2 (widening, reported honestly): {:.2}×",
        w_scalar / w_simd
    );
    println!(
        "  G2 (trunc arm, not gated):        {:.2}×",
        t_scalar / t_simd
    );
    println!();
    println!("  G4 zero-alloc: into_buf kernels write into caller-owned buffers —");
    println!("  zero allocation in the measured path by construction (stack-buffer");
    println!("  witness test in the module's cfg(test) suite).");
    if w_scalar / w_simd < 2.0 {
        println!();
        println!("  note: widen × < 2.0 — the scalar widening loop is trivially");
        println!("  auto-vectorizable by LLVM; read × as explicit-SIMD vs");
        println!("  auto-vectorized-scalar (the honest bar for promotion).");
    }
    if !g2_pass {
        println!();
        println!("  honest verdict: G2 did NOT clear — bf16_simd stays opt-in per");
        println!("  Issue 800 A3 (promotion to default only on pass).");
    }
}
