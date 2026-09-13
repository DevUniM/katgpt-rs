//! CPU-side LoRA adapter.

use super::domain::{read_f32_le, read_u16_le, read_u32_le};
use super::*;

// ---------------------------------------------------------------------------
// LoRA Adapter — CPU inference path (Plan 025)
// ---------------------------------------------------------------------------

/// CPU-side LoRA adapter for inference.
/// Loads from the same binary format as `GpuLoraAdapter` (Plan 008):
/// `[LORA(4) | version(4) | blake3(32) | payload...]`
/// where payload = `[n_adapters(4) | rank(4) | alpha(4) | adapter_data...]`
/// and adapter_data = `[in_dim(4) | out_dim(4) | a_f32s | b_f32s]`
///
/// Use [`LoraAdapter::load`] to read ALL adapters from a multi-adapter file
/// (correct for L2+ models), or [`LoraAdapter::load_first`] when only the
/// first adapter is needed (e.g., single-forward-pass heuristic players).
///
/// Zero-copy: loaded once per domain, reference-passed during inference.
///
/// Fields ordered by descending alignment to minimize padding:
/// usize/Vec (8-byte) → f32 (4-byte).
#[derive(Clone)]
pub struct LoraAdapter {
    /// LoRA rank.
    pub rank: usize,
    /// Input dimension.
    pub in_dim: usize,
    /// Output dimension.
    pub out_dim: usize,
    /// Down-projection: [rank × in_dim]
    pub a: Vec<f32>,
    /// Up-projection: [out_dim × rank]
    pub b: Vec<f32>,
    /// Scaling factor (alpha / rank).
    pub alpha: f32,
}

impl LoraAdapter {
    /// Load ALL adapters from a Plan 008 binary LoRA file.
    ///
    /// Multi-adapter files (e.g., L2+ with 6 adapters/layer × n_layer) return every
    /// adapter in declaration order. Single-adapter files return a 1-element Vec.
    ///
    /// Issue 299: previously this returned only the first adapter, silently
    /// discarding layers 1+ and invalidating L2+ arena benchmarks.
    pub fn load(path: &std::path::Path) -> Result<Vec<Self>, String> {
        const LORA_MAGIC: &[u8; 4] = b"LORA";
        const LORA_VERSION: u32 = 1;

        let file_data =
            std::fs::read(path).map_err(|e| format!("Failed to read lora file: {e}"))?;

        if file_data.len() < 44 {
            return Err("File too small for lora header".into());
        }

        if &file_data[0..4] != LORA_MAGIC {
            return Err("Invalid lora magic bytes".into());
        }

        let version = u32::from_le_bytes(
            file_data[4..8]
                .try_into()
                .map_err(|e: std::array::TryFromSliceError| format!("Version parse: {e}"))?,
        );
        if version != LORA_VERSION {
            return Err(format!("Unsupported lora version: {version}"));
        }

        let stored_checksum = &file_data[8..40];
        let payload = &file_data[40..];

        let computed = blake3::hash(payload);
        if computed.as_bytes() != stored_checksum {
            return Err("LoRA file checksum mismatch".into());
        }

        let mut offset = 0usize;
        let n_adapters = read_u32_le(payload, &mut offset)? as usize;
        let rank = read_u32_le(payload, &mut offset)? as usize;
        let alpha = read_f32_le(payload, &mut offset)?;

        if n_adapters == 0 {
            return Err("No adapters in lora file".into());
        }

        let mut adapters = Vec::with_capacity(n_adapters);
        for i in 0..n_adapters {
            let in_dim = read_u32_le(payload, &mut offset)? as usize;
            let out_dim = read_u32_le(payload, &mut offset)? as usize;

            let a_count = rank * in_dim;
            let b_count = out_dim * rank;
            let a_bytes = a_count * std::mem::size_of::<f32>();
            let b_bytes = b_count * std::mem::size_of::<f32>();

            if offset + a_bytes + b_bytes > payload.len() {
                return Err(format!("Truncated adapter {i} data"));
            }

            let a: Vec<f32> = {
                #[cfg(target_endian = "little")]
                {
                    let mut v = Vec::with_capacity(a_count);
                    unsafe {
                        std::ptr::copy_nonoverlapping(
                            payload[offset..].as_ptr(),
                            v.as_mut_ptr() as *mut u8,
                            a_bytes,
                        );
                        v.set_len(a_count);
                    }
                    v
                }
                #[cfg(not(target_endian = "little"))]
                {
                    payload[offset..offset + a_bytes]
                        .chunks_exact(4)
                        .map(|c| f32::from_le_bytes(c.try_into().expect("chunk is 4 bytes")))
                        .collect()
                }
            };
            offset += a_bytes;

            let b: Vec<f32> = {
                #[cfg(target_endian = "little")]
                {
                    let mut v = Vec::with_capacity(b_count);
                    unsafe {
                        std::ptr::copy_nonoverlapping(
                            payload[offset..].as_ptr(),
                            v.as_mut_ptr() as *mut u8,
                            b_bytes,
                        );
                        v.set_len(b_count);
                    }
                    v
                }
                #[cfg(not(target_endian = "little"))]
                {
                    payload[offset..offset + b_bytes]
                        .chunks_exact(4)
                        .map(|c| f32::from_le_bytes(c.try_into().expect("chunk is 4 bytes")))
                        .collect()
                }
            };
            offset += b_bytes;

            adapters.push(Self {
                rank,
                in_dim,
                out_dim,
                alpha,
                a,
                b,
            });
        }

        if offset != payload.len() {
            return Err(format!(
                "LoRA payload trailing data: consumed {offset}, payload {}",
                payload.len()
            ));
        }

        Ok(adapters)
    }

    /// Load only the first adapter from a Plan 008 binary LoRA file.
    ///
    /// Convenience for consumers that store a single `LoraAdapter` and only run
    /// one forward pass (e.g., `LoraPlayer`, `FullHLPlayer`). Multi-adapter
    /// files (L2+) have layers 1+ silently dropped — this is explicit about
    /// that limitation so callers cannot accidentally regress on Issue 299.
    ///
    /// For correct multi-adapter evaluation, use [`load`](Self::load) and apply
    /// each adapter to its target projection during the forward pass.
    pub fn load_first(path: &std::path::Path) -> Result<Self, String> {
        let adapters = Self::load(path)?;
        adapters
            .into_iter()
            .next()
            .ok_or_else(|| "LoRA file declared zero-length adapter list".into())
    }

    /// Save adapters to a Plan 008 binary LoRA file (the inverse of [`load`](Self::load)).
    ///
    /// All adapters MUST share the same `rank` and `alpha` — the file format stores
    /// them once in the header. Per-adapter `in_dim`/`out_dim` are stored individually
    /// (they can differ across targets, e.g. Q vs K in GQA).
    ///
    /// Format: `["LORA" | version=1(u32) | blake3(payload)(32) | payload]` where
    /// payload = `[n_adapters(u32) | rank(u32) | alpha(f32) | per-adapter:
    /// in_dim(u32) | out_dim(u32) | a_f32s | b_f32s]`.
    ///
    /// This is the CPU-side counterpart to the private GPU LoRA exporter,
    /// producing byte-identical files that load via either path. Used by
    /// `CpuLoraTrainer` (Issue 018 CPU fallback) to produce arena-loadable
    /// adapters without a GPU.
    pub fn save(
        adapters: &[&Self],
        rank: usize,
        alpha: f32,
        path: &std::path::Path,
    ) -> Result<(), String> {
        const LORA_MAGIC: &[u8; 4] = b"LORA";
        const LORA_VERSION: u32 = 1;

        if adapters.is_empty() {
            return Err("Cannot save zero adapters".into());
        }

        let mut payload = Vec::with_capacity(12 + adapters.len() * (8 + 16));

        // Header
        payload.extend_from_slice(&(adapters.len() as u32).to_le_bytes());
        payload.extend_from_slice(&(rank as u32).to_le_bytes());
        payload.extend_from_slice(&alpha.to_le_bytes());

        // Adapter data
        for adapter in adapters {
            if adapter.rank != rank {
                return Err(format!(
                    "Adapter rank mismatch: header={rank}, adapter={}",
                    adapter.rank
                ));
            }
            payload.extend_from_slice(&(adapter.in_dim as u32).to_le_bytes());
            payload.extend_from_slice(&(adapter.out_dim as u32).to_le_bytes());

            let a_count = rank * adapter.in_dim;
            let b_count = adapter.out_dim * rank;
            if adapter.a.len() != a_count {
                return Err(format!(
                    "A matrix size mismatch: expected {a_count}, got {}",
                    adapter.a.len()
                ));
            }
            if adapter.b.len() != b_count {
                return Err(format!(
                    "B matrix size mismatch: expected {b_count}, got {}",
                    adapter.b.len()
                ));
            }
            // Bulk write matrix data on LE targets (avoids per-element
            // extend_from_slice overhead). f32 is plain-old-data with no
            // padding; on LE targets to_ne_bytes == to_le_bytes.
            // SAFETY: f32 has no padding and is plain-old-data; we reinterpret
            // the contiguous &[f32] as bytes for a single bulk copy.
            #[cfg(target_endian = "little")]
            {
                let a_bytes = unsafe {
                    std::slice::from_raw_parts(
                        adapter.a.as_ptr() as *const u8,
                        adapter.a.len() * std::mem::size_of::<f32>(),
                    )
                };
                payload.extend_from_slice(a_bytes);
                let b_bytes = unsafe {
                    std::slice::from_raw_parts(
                        adapter.b.as_ptr() as *const u8,
                        adapter.b.len() * std::mem::size_of::<f32>(),
                    )
                };
                payload.extend_from_slice(b_bytes);
            }
            #[cfg(not(target_endian = "little"))]
            {
                for val in &adapter.a {
                    payload.extend_from_slice(&val.to_le_bytes());
                }
                for val in &adapter.b {
                    payload.extend_from_slice(&val.to_le_bytes());
                }
            }
        }

        // Compute blake3 checksum of payload
        let checksum = blake3::hash(&payload);

        // Assemble file: magic + version + checksum + payload
        let mut file_data = Vec::with_capacity(4 + 4 + 32 + payload.len());
        file_data.extend_from_slice(LORA_MAGIC);
        file_data.extend_from_slice(&LORA_VERSION.to_le_bytes());
        file_data.extend_from_slice(checksum.as_bytes());
        file_data.extend_from_slice(&payload);

        std::fs::write(path, &file_data).map_err(|e| format!("Failed to write lora file: {e}"))
    }

    /// Load LoRA adapters from a compact binary format.
    ///
    /// Format:
    /// ```text
    /// [MAGIC: "LORA" 4B]
    /// [VERSION: 1B]
    /// [RANK: 2B LE]
    /// [N_LAYERS: 2B LE]
    /// [N_TARGETS: 2B LE]
    /// [TARGET_IDS: N_TARGETS × 2B LE]  (0=q_proj, 1=k_proj, 2=v_proj, 3=o_proj,
    ///                                    4=gate_proj, 5=up_proj, 6=down_proj)
    /// [LAYER_DATA: for each (layer, target):
    ///   [A_ROWS: 2B][A_COLS: 2B][A_DATA: A_ROWS×A_COLS × 4B f32]
    ///   [B_ROWS: 2B][B_COLS: 2B][B_DATA: B_ROWS×B_COLS × 4B f32]
    /// ]
    /// [BLAKE3_HASH: 32B]  — covers everything before it
    /// ```
    ///
    /// Alpha defaults to `rank * 2`.
    pub fn load_from_bin(path: &std::path::Path) -> Result<Vec<Self>, String> {
        const LORA_MAGIC: &[u8; 4] = b"LORA";
        const LORA_VERSION: u8 = 1;

        let file_data =
            std::fs::read(path).map_err(|e| format!("Failed to read lora bin file: {e}"))?;

        // Minimum: magic(4) + version(1) + rank(2) + n_layers(2) + n_targets(2) + hash(32) = 43
        if file_data.len() < 43 {
            return Err("File too small for lora bin header".into());
        }

        // Validate blake3 checksum — last 32 bytes cover everything before them
        let data_len = file_data.len() - 32;
        let stored_checksum = &file_data[data_len..];
        let computed = blake3::hash(&file_data[..data_len]);
        if computed.as_bytes() != stored_checksum {
            return Err("LoRA bin file checksum mismatch".into());
        }

        let mut offset = 0usize;

        // Magic
        if &file_data[offset..offset + 4] != LORA_MAGIC {
            return Err("Invalid lora bin magic bytes".into());
        }
        offset += 4;

        // Version
        let version = file_data[offset];
        if version != LORA_VERSION {
            return Err(format!("Unsupported lora bin version: {version}"));
        }
        offset += 1;

        // Rank
        let rank = read_u16_le(&file_data, &mut offset)? as usize;

        // N_LAYERS
        let n_layers = read_u16_le(&file_data, &mut offset)? as usize;

        // N_TARGETS
        let n_targets = read_u16_le(&file_data, &mut offset)? as usize;

        if n_layers == 0 || n_targets == 0 {
            return Err("No layers or targets in lora bin file".into());
        }

        // TARGET_IDS
        let mut target_ids = Vec::with_capacity(n_targets);
        for _ in 0..n_targets {
            let tid = read_u16_le(&file_data, &mut offset)?;
            match tid {
                0..=6 => target_ids.push(tid),
                _ => return Err(format!("Invalid target ID: {tid}")),
            }
        }

        // LAYER_DATA
        let alpha = (rank * 2) as f32;
        let mut adapters = Vec::with_capacity(n_layers * n_targets);

        for _layer in 0..n_layers {
            for &_target_id in &target_ids {
                // A matrix: [rank × in_dim]
                let a_rows = read_u16_le(&file_data, &mut offset)? as usize;
                let a_cols = read_u16_le(&file_data, &mut offset)? as usize;
                let a_count = a_rows * a_cols;
                let a_bytes = a_count * std::mem::size_of::<f32>();

                if offset + a_bytes > data_len {
                    return Err("Truncated A matrix data".into());
                }

                let a: Vec<f32> = {
                    #[cfg(target_endian = "little")]
                    {
                        let mut v = Vec::with_capacity(a_count);
                        unsafe {
                            std::ptr::copy_nonoverlapping(
                                file_data[offset..].as_ptr(),
                                v.as_mut_ptr() as *mut u8,
                                a_bytes,
                            );
                            v.set_len(a_count);
                        }
                        v
                    }
                    #[cfg(not(target_endian = "little"))]
                    {
                        file_data[offset..offset + a_bytes]
                            .chunks_exact(4)
                            .map(|c| f32::from_le_bytes(c.try_into().expect("chunk is 4 bytes")))
                            .collect()
                    }
                };
                offset += a_bytes;

                // B matrix: [out_dim × rank]
                let b_rows = read_u16_le(&file_data, &mut offset)? as usize;
                let b_cols = read_u16_le(&file_data, &mut offset)? as usize;
                let b_count = b_rows * b_cols;
                let b_bytes = b_count * std::mem::size_of::<f32>();

                if offset + b_bytes > data_len {
                    return Err("Truncated B matrix data".into());
                }

                let b: Vec<f32> = {
                    #[cfg(target_endian = "little")]
                    {
                        let mut v = Vec::with_capacity(b_count);
                        unsafe {
                            std::ptr::copy_nonoverlapping(
                                file_data[offset..].as_ptr(),
                                v.as_mut_ptr() as *mut u8,
                                b_bytes,
                            );
                            v.set_len(b_count);
                        }
                        v
                    }
                    #[cfg(not(target_endian = "little"))]
                    {
                        file_data[offset..offset + b_bytes]
                            .chunks_exact(4)
                            .map(|c| f32::from_le_bytes(c.try_into().expect("chunk is 4 bytes")))
                            .collect()
                    }
                };
                offset += b_bytes;

                let in_dim = a_cols;
                let out_dim = b_rows;

                adapters.push(Self {
                    rank,
                    in_dim,
                    out_dim,
                    alpha,
                    a,
                    b,
                });
            }
        }

        if offset != data_len {
            return Err(format!(
                "Unexpected trailing data: read {offset}, expected {data_len}"
            ));
        }

        if adapters.is_empty() {
            return Err("No adapters loaded from lora bin file".into());
        }

        Ok(adapters)
    }
}

/// Apply LoRA delta in-place: `output += (alpha/rank) × B @ (A @ input)`
///
/// `lora_buf` is a pre-allocated `[rank]` intermediate buffer — zero alloc in hot path.
/// The B×hidden multiplication and scaling are fused directly into the output accumulation,
/// avoiding a separate delta buffer.
#[inline(always)]
pub fn lora_apply(output: &mut [f32], lora: &LoraAdapter, input: &[f32], lora_buf: &mut [f32]) {
    let scale = lora.alpha / lora.rank as f32;

    // 1. hidden = A @ input  (rank × in_dim) @ [in_dim] → [rank]
    matmul(lora_buf, &lora.a, input, lora.rank, lora.in_dim);

    // 2. output += scale × (B @ hidden) — SIMD-accelerated per-row dot product
    for r in 0..lora.out_dim {
        let row_off = r * lora.rank;
        let sum =
            crate::simd::simd_dot_f32(&lora.b[row_off..row_off + lora.rank], lora_buf, lora.rank);
        unsafe {
            *output.get_unchecked_mut(r) += scale * sum;
        }
    }
}

/// Domain-separation tag for [`WeightEpoch`] identities (never hash raw
/// adapter bytes without a tag — a future format change must not alias an
/// old epoch).
const WEIGHT_EPOCH_TAG: &[u8] = b"katgpt-lora-weight-epoch-v1";

/// Stable identity of the effective weights a KV-cache entry was computed
/// under — the weight-epoch contract for cache exactness (riir-ai Issue 938,
/// the RLT §5.4/App-C staleness law; Plan 025's `LoraPair` design).
///
/// **The law:** a cache entry is exact only when computed under the SAME
/// weight epoch as the read (plus prefix, positions, init, window
/// convention). KV rows written under epoch `v` and read under `v' != v`
/// are a mixed-epoch computation — invalid for any exactness claim (scored
/// replays, deterministic re-runs, verified regeneration). For latent-domain
/// emergent consumers the acceptance may be legitimate, but it must be
/// DOCUMENTED at the swap site, never implicit.
///
/// Identity is BLAKE3 over the adapter's canonical serialization — so two
/// adapters with identical bytes share an epoch (swapping A→B→A may reuse a
/// cache written under the first A), while any byte difference (weights,
/// rank, dims, alpha) defines a new epoch. O(adapter) to compute at swap
/// time; O(1) memcmp to compare; zero hot-path cost.
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub struct WeightEpoch([u8; 32]);

impl WeightEpoch {
    /// The epoch of "no adapter installed" (domain-separated from every
    /// adapter identity by construction — it hashes a distinct tag).
    pub fn none() -> Self {
        let mut h = blake3::Hasher::new();
        h.update(WEIGHT_EPOCH_TAG);
        h.update(b"none");
        Self(*h.finalize().as_bytes())
    }

    /// Identity over an arbitrary tagged weight walk — the general
    /// constructor for consumers whose "effective weights" are not a single
    /// [`LoraAdapter`] (e.g. a full frozen transformer: hash every tensor in
    /// a documented fixed order, plus any forward-affecting scalars, in the
    /// `tag`).
    ///
    /// Each part is length-prefixed, so part boundaries cannot alias
    /// (`[a,b],[c]` ≠ `[a],[b,c]`). The caller's `tag` must name the weight
    /// family + layout (two different walks must never share a tag).
    /// Compute ONCE per model load / swap — never in a hot loop.
    pub fn from_parts<'a>(tag: &[u8], parts: impl IntoIterator<Item = &'a [u8]>) -> Self {
        let mut h = blake3::Hasher::new();
        h.update(WEIGHT_EPOCH_TAG);
        h.update(&(tag.len() as u64).to_le_bytes());
        h.update(tag);
        for part in parts {
            h.update(&(part.len() as u64).to_le_bytes());
            h.update(part);
        }
        Self(*h.finalize().as_bytes())
    }

    /// The raw 32-byte identity — for wire formats that carry the epoch
    /// (e.g. riir-ai's KVCA v2 header) and operator-facing hex rendering.
    pub const fn as_bytes(&self) -> &[u8; 32] {
        &self.0
    }
}

impl LoraAdapter {
    /// The weight epoch this adapter defines (see [`WeightEpoch`] for the
    /// cache-exactness law). Compute ONCE per install/swap — never in a
    /// hot loop.
    pub fn weight_epoch(&self) -> WeightEpoch {
        let mut h = blake3::Hasher::new();
        h.update(WEIGHT_EPOCH_TAG);
        h.update(&u64::try_from(self.rank).unwrap_or(u64::MAX).to_le_bytes());
        h.update(&u64::try_from(self.in_dim).unwrap_or(u64::MAX).to_le_bytes());
        h.update(
            &u64::try_from(self.out_dim)
                .unwrap_or(u64::MAX)
                .to_le_bytes(),
        );
        h.update(&self.alpha.to_le_bytes());
        // Length prefixes make the serialization unambiguous (no concatenation
        // aliasing across dims).
        h.update(
            &u64::try_from(self.a.len())
                .unwrap_or(u64::MAX)
                .to_le_bytes(),
        );
        for f in &self.a {
            h.update(&f.to_le_bytes());
        }
        h.update(
            &u64::try_from(self.b.len())
                .unwrap_or(u64::MAX)
                .to_le_bytes(),
        );
        for f in &self.b {
            h.update(&f.to_le_bytes());
        }
        WeightEpoch(*h.finalize().as_bytes())
    }
}

/// A loaded LoRA pair for modality-specific inference (Plan 025).
/// Reader is active during bidirectional prefill, writer during causal decode.
/// Switching is a reference swap — zero data movement.
///
/// # KV-cache epoch contract (Issue 938 — the acceptance is BY DESIGN here)
///
/// A pipeline that prefills under `reader` and decodes under `writer` while
/// sharing one KV cache produces, by this very design, a **mixed-epoch
/// cache**: rows `[0..P)` carry the reader's weight epoch, appended rows the
/// writer's. Plan 025 accepts this (the modality switch is the point); the
/// acceptance is documented HERE, at the type that creates it. Consumers
/// making exactness claims on top of such a cache must either re-prefill
/// under a single adapter or treat the mixed rows as a distinct composite
/// epoch — never silently assume single-epoch exactness.
pub struct LoraPair {
    /// LoRA active during bidirectional prefill (e.g., Python Reader).
    pub reader: Option<LoraAdapter>,
    /// LoRA active during causal decode (e.g., Rust Writer).
    pub writer: Option<LoraAdapter>,
}

impl LoraPair {
    /// Empty pair — no LoRA applied.
    pub fn none() -> Self {
        Self {
            reader: None,
            writer: None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_test_adapters() -> Vec<LoraAdapter> {
        // 6 adapters mirroring the Bomber/Generic layout: Q, K, V, O, Mlp1, Mlp2.
        // rank=4, in_dim=32 (n_embd), out_dim varies (GQA: K/V are n_kv_head*head_dim).
        vec![
            LoraAdapter {
                rank: 4,
                in_dim: 32,
                out_dim: 32,
                a: (0..4 * 32).map(|i| i as f32 * 0.01).collect(),
                b: (0..32 * 4).map(|i| i as f32 * -0.01).collect(),
                alpha: 8.0,
            },
            LoraAdapter {
                rank: 4,
                in_dim: 32,
                out_dim: 8, // kv_dim (n_kv_head=1, head_dim=8)
                a: (0..4 * 32).map(|i| i as f32).collect(),
                b: (0..8 * 4).map(|i| i as f32 * 2.0).collect(),
                alpha: 8.0,
            },
            LoraAdapter {
                rank: 4,
                in_dim: 32,
                out_dim: 8,
                a: (0..4 * 32).map(|i| i as f32 * 0.5).collect(),
                b: (0..8 * 4).map(|i| i as f32 * -2.0).collect(),
                alpha: 8.0,
            },
            LoraAdapter {
                rank: 4,
                in_dim: 32,
                out_dim: 32,
                a: (0..4 * 32).map(|i| i as f32 * 0.1).collect(),
                b: (0..32 * 4).map(|i| i as f32 * 0.3).collect(),
                alpha: 8.0,
            },
            LoraAdapter {
                rank: 4,
                in_dim: 32,
                out_dim: 32, // FFN up (mlp1)
                a: (0..4 * 32).map(|i| i as f32 * 1.5).collect(),
                b: (0..32 * 4).map(|i| i as f32 * -1.5).collect(),
                alpha: 8.0,
            },
            LoraAdapter {
                rank: 4,
                in_dim: 32,
                out_dim: 32, // FFN down (mlp2)
                a: (0..4 * 32).map(|i| i as f32 * 2.5).collect(),
                b: (0..32 * 4).map(|i| i as f32 * -2.5).collect(),
                alpha: 8.0,
            },
        ]
    }

    #[test]
    fn save_load_roundtrip_preserves_all_adapters() {
        let tmp = std::env::temp_dir().join("katgpt_lora_roundtrip_test.bin");
        let original = make_test_adapters();
        let refs: Vec<&LoraAdapter> = original.iter().collect();

        LoraAdapter::save(&refs, 4, 8.0, &tmp).expect("save should succeed");
        let loaded = LoraAdapter::load(&tmp).expect("load should succeed");

        assert_eq!(loaded.len(), original.len(), "adapter count must match");
        for (i, (orig, load)) in original.iter().zip(loaded.iter()).enumerate() {
            assert_eq!(load.rank, orig.rank, "adapter {i} rank");
            assert_eq!(load.in_dim, orig.in_dim, "adapter {i} in_dim");
            assert_eq!(load.out_dim, orig.out_dim, "adapter {i} out_dim");
            assert_eq!(load.alpha, orig.alpha, "adapter {i} alpha");
            assert_eq!(load.a.len(), orig.a.len(), "adapter {i} A length");
            assert_eq!(load.b.len(), orig.b.len(), "adapter {i} B length");
            for (j, (a, b)) in orig.a.iter().zip(load.a.iter()).enumerate() {
                assert_eq!(a.to_bits(), b.to_bits(), "adapter {i} A[{j}] bit-identical");
            }
            for (j, (a, b)) in orig.b.iter().zip(load.b.iter()).enumerate() {
                assert_eq!(a.to_bits(), b.to_bits(), "adapter {i} B[{j}] bit-identical");
            }
        }

        let _ = std::fs::remove_file(&tmp);
    }

    #[test]
    fn save_rejects_empty_adapter_list() {
        let tmp = std::env::temp_dir().join("katgpt_lora_empty_test.bin");
        let empty: Vec<&LoraAdapter> = vec![];
        let result = LoraAdapter::save(&empty, 4, 8.0, &tmp);
        assert!(result.is_err());
        let _ = std::fs::remove_file(&tmp);
    }

    #[test]
    fn save_rejects_rank_mismatch() {
        let tmp = std::env::temp_dir().join("katgpt_lora_rankmismatch_test.bin");
        let adapters = make_test_adapters();
        let refs: Vec<&LoraAdapter> = adapters.iter().collect();
        // Pass rank=8 but adapters have rank=4
        let result = LoraAdapter::save(&refs, 8, 8.0, &tmp);
        assert!(result.is_err());
        let _ = std::fs::remove_file(&tmp);
    }

    // ── WeightEpoch (riir-ai Issue 938 — the weight-epoch cache contract) ──

    #[test]
    fn weight_epoch_stable_for_identical_adapters() {
        let adapters = make_test_adapters();
        for (i, a) in adapters.iter().enumerate() {
            assert_eq!(
                a.weight_epoch(),
                a.clone().weight_epoch(),
                "adapter {i}: identical bytes must share an epoch"
            );
        }
        // Round-trip through the binary format: same bytes, same epoch.
        let tmp = std::env::temp_dir().join("katgpt_lora_epoch_roundtrip.bin");
        let refs: Vec<&LoraAdapter> = adapters.iter().collect();
        LoraAdapter::save(&refs, 4, 8.0, &tmp).expect("save should succeed");
        let loaded = LoraAdapter::load(&tmp).expect("load should succeed");
        for (i, (orig, ld)) in adapters.iter().zip(loaded.iter()).enumerate() {
            assert_eq!(
                orig.weight_epoch(),
                ld.weight_epoch(),
                "adapter {i}: save/load round-trip must preserve the epoch"
            );
        }
        let _ = std::fs::remove_file(&tmp);
    }

    #[test]
    fn weight_epoch_differs_on_every_field() {
        let base = &make_test_adapters()[0];
        let base_epoch = base.weight_epoch();

        let mut tweaked = base.clone();
        tweaked.a[0] += 1.0;
        assert_ne!(
            base_epoch,
            tweaked.weight_epoch(),
            "a byte must change the epoch"
        );

        let mut tweaked = base.clone();
        tweaked.b[0] += 1.0;
        assert_ne!(
            base_epoch,
            tweaked.weight_epoch(),
            "b byte must change the epoch"
        );

        let mut tweaked = base.clone();
        tweaked.alpha += 1.0;
        assert_ne!(
            base_epoch,
            tweaked.weight_epoch(),
            "alpha must change the epoch"
        );

        // Dims change the serialization shape → new epoch.
        let mut tweaked = base.clone();
        tweaked.in_dim += 1;
        // Keep lengths consistent so the epoch is well-defined (identity does
        // not validate shapes; the lengths are hashed as-is).
        tweaked.a.push(0.0);
        assert_ne!(
            base_epoch,
            tweaked.weight_epoch(),
            "in_dim must change the epoch"
        );

        let _ = tweaked;
    }

    #[test]
    fn weight_epoch_none_is_distinct_and_stable() {
        assert_eq!(
            WeightEpoch::none(),
            WeightEpoch::none(),
            "none epoch is stable"
        );
        for (i, a) in make_test_adapters().iter().enumerate() {
            assert_ne!(
                WeightEpoch::none(),
                a.weight_epoch(),
                "adapter {i}: no-adapter epoch must never alias a real adapter"
            );
        }
    }

    #[test]
    fn weight_epoch_from_parts_is_deterministic_and_tag_sensitive() {
        let p1: &[u8] = &[1, 2, 3];
        let p2: &[u8] = &[4, 5];
        let t_a: &[u8] = b"frozen-model-a";
        let t_b: &[u8] = b"frozen-model-b";
        assert_eq!(
            WeightEpoch::from_parts(t_a, [p1, p2]),
            WeightEpoch::from_parts(t_a, [p1, p2]),
            "same tag + same parts → same epoch"
        );
        assert_ne!(
            WeightEpoch::from_parts(t_a, [p1, p2]),
            WeightEpoch::from_parts(t_b, [p1, p2]),
            "different weight-family tag → different epoch"
        );
        assert_ne!(
            WeightEpoch::from_parts(t_a, [p1, p2]),
            WeightEpoch::from_parts(t_a, [p2, p1]),
            "part ORDER is part of the identity"
        );
    }

    #[test]
    fn weight_epoch_from_parts_length_prefixes_prevent_concat_aliasing() {
        // [1,2],[3] must NOT equal [1],[2,3] — the failure the length
        // prefixes exist to prevent.
        let left: [&[u8]; 2] = [&[1, 2], &[3]];
        let right: [&[u8]; 2] = [&[1], &[2, 3]];
        assert_ne!(
            WeightEpoch::from_parts(b"t", left),
            WeightEpoch::from_parts(b"t", right)
        );
    }

    #[test]
    fn weight_epoch_from_parts_is_distinct_from_adapter_and_none_epochs() {
        let from_parts = WeightEpoch::from_parts(b"t", [&[1u8][..]]);
        assert_ne!(from_parts, WeightEpoch::none());
        for (i, a) in make_test_adapters().iter().enumerate() {
            assert_ne!(
                from_parts,
                a.weight_epoch(),
                "adapter {i}: a tagged walk must never alias an adapter identity"
            );
        }
    }
}
