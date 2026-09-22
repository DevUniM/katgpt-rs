//! [`SinkWindowPolicy`] — the ceiling, the classification, and the fidelity
//! verdict.

/// What a live KV slot is, under a sink + window policy.
///
/// Three verdicts and none of them is pooled: `Sink` and `Window` are both
/// "kept", but for opposite reasons — a sink is kept *unconditionally* and a
/// window row is kept *for now* — and a caller that treats them alike will
/// evict the system prompt the moment the scorer dislikes it.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SlotClass {
    /// Absolute position `< n_sink`. Never evicted, at any score, for any
    /// eviction budget. The system prompt / tool schema.
    Sink,
    /// Inside the trailing window. Evictable, ordered by the caller's score.
    Window,
    /// Outside both. Out of POLICY rather than merely low-scoring, so it is
    /// evicted before any window row regardless of how much mass it holds.
    Stale,
}

/// Whether a window's evictions can change the output at all.
///
/// The distinction is load-bearing for promotion, not descriptive: one of
/// these is a lossy surface under AGENTS.md's rule and the other is not.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum WindowFidelity {
    /// `window >= d_max`: every evicted row carried **exactly** zero
    /// attention mass, by the Issue-747 / Research-549 ALiBi × entmax-1.5
    /// theorem. Output is bit-identical, so this is not a lossy surface and
    /// the Plan-585 runaway gate does not apply.
    Lossless {
        /// The caller's proven zero-mass distance.
        d_max: usize,
    },
    /// `window < d_max`, or no `d_max` is known. Rows with real mass are
    /// dropped. ⛔ **A lossy surface**: the Plan-585 `runaway_gate` on a
    /// sealed long-context eval is mandatory before promotion, because
    /// aggregate perplexity stays flat while output length runs to the cap.
    Lossy,
}

impl WindowFidelity {
    /// `true` when evictions provably cannot change the output.
    #[inline]
    pub fn is_lossless(&self) -> bool {
        matches!(self, Self::Lossless { .. })
    }
}

/// Permanent sinks + a bounded trailing window.
///
/// The invariant, for every step and every sequence length:
///
/// ```text
/// live_slots <= n_sink + window
/// ```
///
/// which makes decode-time KV memory a function of the POLICY and not of how
/// long the conversation has run. That is the whole product claim; everything
/// else here exists to make it hold structurally rather than numerically.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SinkWindowPolicy {
    /// Positions `[0, n_sink)` never evict.
    pub n_sink: usize,
    /// How many trailing positions stay resident behind the sinks.
    pub window: usize,
}

impl Default for SinkWindowPolicy {
    /// 4 sinks + a 256-token window — the Research 571 §B-8 shape. Both are
    /// the LEAD's numbers, not a measurement of this repo; a consumer should
    /// size `window` against its own recall, and against `d_max` if it has
    /// one (see [`Self::fidelity`]).
    fn default() -> Self {
        Self {
            n_sink: 4,
            window: 256,
        }
    }
}

impl SinkWindowPolicy {
    /// A policy with explicit sinks and window.
    #[inline]
    pub const fn new(n_sink: usize, window: usize) -> Self {
        Self { n_sink, window }
    }

    /// The identity policy: no sinks, unbounded window.
    ///
    /// Every slot classifies [`SlotClass::Window`], so
    /// [`select_evict_windowed`](super::select_evict_windowed) reduces
    /// EXACTLY to `kv_eviction::select_evict_into` with an all-unpinned mask.
    /// The control arm for an A/B, and the thing a reduction test asserts —
    /// an "off" switch that is a second code path is not an off switch.
    pub const UNBOUNDED: Self = Self {
        n_sink: 0,
        window: usize::MAX,
    };

    /// The hard ceiling on live slots. Saturating: a `window` of
    /// [`usize::MAX`] means unbounded, and must not wrap to something small,
    /// which is the direction that silently evicts everything.
    #[inline]
    pub const fn capacity(&self) -> usize {
        self.n_sink.saturating_add(self.window)
    }

    /// How many slots must go this step to sit at or under the ceiling.
    /// `0` when already within it.
    #[inline]
    pub const fn evictions_needed(&self, live_slots: usize) -> usize {
        live_slots.saturating_sub(self.capacity())
    }

    /// Classify one slot by its absolute token position.
    ///
    /// The sink test comes FIRST and is unconditional. Order matters: a sink
    /// that has scrolled far outside the window is still a sink, and a
    /// window-first predicate would classify it `Stale` and evict the system
    /// prompt at exactly the sequence length this policy exists for.
    #[inline]
    pub const fn classify(&self, position: u64, current_pos: u64) -> SlotClass {
        if (position as u128) < self.n_sink as u128 {
            return SlotClass::Sink;
        }
        // ⛔ `usize::MAX` means UNBOUNDED, and the literal comparison does
        // not deliver that. A window of `w` covers distances `0..w`, so
        // `w = usize::MAX` covers `0..=usize::MAX-1` — and on a 64-bit target
        // `usize::MAX == u64::MAX`, which leaves exactly one representable
        // distance (position 0 at `current_pos = u64::MAX`) classified
        // `Stale` by the policy whose entire purpose is to classify nothing
        // stale. Found by w07, not reasoned about. On a 32-bit target
        // (wasm32) this is also the widest window expressible, so the
        // sentinel reading is the only one that can mean "no window".
        if self.window == usize::MAX {
            return SlotClass::Window;
        }
        // Saturating, and computed as a DISTANCE rather than as a lower
        // bound: `current_pos - window` underflows for every early position
        // when the window is large, and `usize::MAX as u64` is a second wrap
        // waiting on a 32-bit target.
        let distance = current_pos.saturating_sub(position);
        match (distance as u128) < self.window as u128 {
            true => SlotClass::Window,
            false => SlotClass::Stale,
        }
    }

    /// Whether this window's evictions can change the output.
    ///
    /// `d_max` is the caller's proven zero-mass distance — `katgpt-attn`'s
    /// `alibi_entmax_window_1p5(z_min, z_max, slope)` for an ALiBi ×
    /// entmax-1.5 head. It is a parameter and not an import because
    /// `katgpt-attn` is DOWNSTREAM of this crate; importing it would be a
    /// dependency cycle, and this is the same caller-supplied-signal pattern
    /// `kv_eviction` uses for attention mass.
    ///
    /// `None` is [`WindowFidelity::Lossy`], deliberately: *not knowing*
    /// `d_max` is not evidence that the window clears it, and the permissive
    /// reading here would exempt a real lossy surface from the runaway gate.
    #[inline]
    pub const fn fidelity(&self, d_max: Option<usize>) -> WindowFidelity {
        match d_max {
            Some(d) if self.window >= d => WindowFidelity::Lossless { d_max: d },
            _ => WindowFidelity::Lossy,
        }
    }
}
