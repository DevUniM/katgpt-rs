// Issue 859 G4 — structured_read alloc-free hot path.
//
// `structured_read_into` must not allocate after scratch construction: the
// readout uses fixed arrays ([f32; MAX_LABELS]) and the pre-allocated
// BidirectionalContext + exp buffer. Separate test binary so the counting
// allocator is binary-unique (the bench_811 convention). The canary first
// proves the instrument is live — a green zero from a dead counter is the
// green-zero trap (Issue 741's lesson), so we require the canary to COUNT
// before trusting the measurement.

#![cfg(feature = "structured_reads")]

use katgpt_core::alloc::{TrackingAllocator, get_alloc_stats, reset_alloc_stats};
use katgpt_forward::structured_read::{
    MAX_LABELS, SlotReadout, StructuredReadScratch, structured_read_into,
};
use katgpt_transformer::TransformerWeights;
use katgpt_types::{Config, Rng};

#[global_allocator]
static A: TrackingAllocator = TrackingAllocator;

#[test]
fn structured_read_zero_alloc_after_warmup() {
    let config = Config::micro_dllm();
    let mut rng = Rng::new(0x0859_6004);
    let weights = TransformerWeights::new(&config, &mut rng);

    // 12-token canvas, 4 free slots — the G2 fixture shape.
    let canvas: Vec<usize> = vec![
        3,
        config.mask_token,
        7,
        1,
        config.mask_token,
        9,
        2,
        config.mask_token,
        5,
        8,
        config.mask_token,
        4,
    ];
    let labels: Vec<u32> = vec![1, 4, 9, 16, 22];
    let mut out = [SlotReadout {
        argmax_logprob: 0.0,
        argmax_label_prob: 0.0,
        label_entropy: 0.0,
        vocab_argmax_token: 0,
        position: 0,
        argmax_index: 0,
        n_labels: 0,
        label_logprobs: [0.0; MAX_LABELS],
    }; 4];
    let mut scratch = StructuredReadScratch::new(&config);

    // Canary: the instrument must be live (Issue 741's dead-counter trap).
    // Box::new heap-allocates — an array would not, and the allocation IS
    // the canary.
    reset_alloc_stats();
    let _canary: Box<[u8; 16]> = Box::new([0u8; 16]);
    let (count, _) = get_alloc_stats();
    assert!(count >= 1, "alloc instrument dead — canary did not count");

    // Warmup (first call may touch lazy paths), then measure 32 reads.
    structured_read_into(&mut out, &weights, &config, &canvas, &labels, &mut scratch).unwrap();
    reset_alloc_stats();
    for _ in 0..32 {
        let n = structured_read_into(&mut out, &weights, &config, &canvas, &labels, &mut scratch)
            .unwrap();
        assert_eq!(n, 4);
    }
    let (count, bytes) = get_alloc_stats();
    assert_eq!(
        count, 0,
        "structured_read_into allocated {count} times ({bytes} bytes) across 32 reads — the hot path must be alloc-free after scratch construction"
    );
}
