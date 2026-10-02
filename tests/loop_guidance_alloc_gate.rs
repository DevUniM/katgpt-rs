//! Plan 617 T1.5 — the LoopCD guidance zero-alloc pin (G4 house pattern).
//!
//! Own test target (its own process) so the process-wide counting allocator
//! observes nothing but this test's work — the
//! `probe_guidance_alloc_gate` precedent (a multi-test target cannot hold
//! this pin: sibling tests run on parallel threads and bump the same
//! process-wide counter).
//!
//! Contract: a GUIDED steady-state decode step allocates exactly what the
//! UNGUIDED step allocates (guidance ADDS zero — the scratch is pre-sized
//! at `LoopGuidance::new`, the object's one allocation, and only
//! `resize`d — a no-op at capacity — inside the forward).
//!
//! Run: `cargo test --release --features loop_guidance,lt2_looped --test
//! loop_guidance_alloc_gate`

#![cfg(all(feature = "loop_guidance", feature = "lt2_looped"))]

use std::alloc::{GlobalAlloc, Layout, System};
use std::sync::atomic::{AtomicU64, Ordering};

use katgpt_rs::hla::MultiLayerAhlaCache;
use katgpt_rs::transformer::loop_guidance::{GuidanceMode, LoopGuidance, LoopGuidanceConfig};
use katgpt_rs::transformer::{forward_looped, ForwardContext, MultiLayerKVCache, TransformerWeights};
use katgpt_rs::types::{Config, HybridPattern, LoopMode, ResidualGate, Rng, SdpaOutputGate};

static ALLOCS: AtomicU64 = AtomicU64::new(0);

struct CountingAlloc;

unsafe impl GlobalAlloc for CountingAlloc {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        ALLOCS.fetch_add(1, Ordering::Relaxed);
        unsafe { System.alloc(layout) }
    }
    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        unsafe { System.dealloc(ptr, layout) }
    }
}

#[global_allocator]
static GLOBAL: CountingAlloc = CountingAlloc;

fn make_config(loop_count: usize) -> Config {
    let mut config = Config::micro();
    config.loop_mode = LoopMode::WeightShared { loop_count };
    config.hybrid_pattern = HybridPattern::Uniform;
    config
}

fn run_once_with(
    config: &Config,
    weights: &TransformerWeights,
    pos: usize,
    guidance: Option<&mut LoopGuidance>,
) -> Vec<f32> {
    let mut ctx = ForwardContext::new(config);
    let mut cache = MultiLayerKVCache::new(config);
    let mut ahla_cache = MultiLayerAhlaCache::new(config);
    let residual_gate = ResidualGate::new(4, config.n_embd);
    let sdpa_gate = SdpaOutputGate::new(config.n_head, config.head_dim, config.n_embd);
    let logits = forward_looped(
        &mut ctx,
        weights,
        &mut cache,
        &mut ahla_cache,
        0,
        pos,
        config,
        &residual_gate,
        &sdpa_gate,
        None,
        None,
        #[cfg(feature = "weight_shared_advantage_gate")]
        None,
        None,
        #[cfg(feature = "gain_cost_halt")]
        None,
        None, // deep_run
        #[cfg(feature = "cadence_gate")]
        None,
        #[cfg(feature = "loop_guidance")]
        guidance,
    );
    logits.to_vec()
}

#[test]
fn guided_step_adds_zero_allocations_over_unguided() {
    let config = make_config(3);
    let mut rng = Rng::new(99);
    let weights = TransformerWeights::new(&config, &mut rng);
    let cfg = LoopGuidanceConfig {
        mode: GuidanceMode::Logits,
        omega: 0.3,
        omega_max: 0.5,
        adaptive: true,
        ref_loop: 1,
    };
    // Construction OUTSIDE the counted region (the object's ONE allocation).
    let mut g = LoopGuidance::new(cfg, config.vocab_size, config.n_embd);

    // Warmup: scratch resize-to-capacity no-ops settle here (the first
    // guided step also warms any lazy machinery on the guided path).
    let _ = run_once_with(&config, &weights, 0, Some(&mut g));
    let _ = run_once_with(&config, &weights, 1, None);

    let before_unguided = ALLOCS.load(Ordering::Relaxed);
    let _ = run_once_with(&config, &weights, 2, None);
    let unguided = ALLOCS.load(Ordering::Relaxed) - before_unguided;

    let before_guided = ALLOCS.load(Ordering::Relaxed);
    let _ = run_once_with(&config, &weights, 2, Some(&mut g));
    let guided = ALLOCS.load(Ordering::Relaxed) - before_guided;

    assert_eq!(
        guided, unguided,
        "guided steady-state decode must add ZERO allocations over unguided \
         (unguided={unguided}, guided={guided})"
    );
}
