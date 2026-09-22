//! [`ProjectionPlan`] — how much of the vocabulary projection a legal set of a
//! given size justifies skipping.

/// What a consumer should compute, given the legal set at this position.
///
/// The four arms are deliberately not orderable by "how much work they save":
/// [`Full`](Self::Full) is reached from two opposite states (the set is too
/// big to gather, or the pruner could not name it at all) and pooling them
/// would hide which. A caller that wants to instrument the split reads
/// [`ProjectionPlan::is_unenumerable`].
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ProjectionPlan {
    /// No legal continuation. The projection cannot produce an admissible
    /// token, so the correct amount to compute is none — the caller
    /// backtracks or fails. **Not the same as "the pruner said nothing"**;
    /// this arm is only reached from an explicit `Some(0)`.
    Dead,
    /// Exactly one legal token. The projection cannot change which token is
    /// chosen, whatever the logits say, so it is skipped entirely. Not a
    /// bandwidth trade — an identity.
    Forced,
    /// `degree` legal tokens, few enough that a gathered-row pass beats the
    /// dense one. Score exactly those rows.
    Restricted { degree: usize },
    /// Do the ordinary dense pass, because either the legal set is too large
    /// for a gather to pay (see [`RestrictionPolicy::max_active_fraction`]) or
    /// the pruner cannot enumerate.
    Full {
        /// `true` when the pruner returned `None` — no legal set was
        /// available, as opposed to one that was available and too large.
        unenumerable: bool,
    },
}

impl ProjectionPlan {
    /// `true` when this is [`Full`](Self::Full) because nothing could be
    /// enumerated, rather than because the set was too large.
    #[inline]
    pub fn is_unenumerable(&self) -> bool {
        matches!(self, Self::Full { unenumerable: true })
    }

    /// Rows the LM head must actually be evaluated over, for accounting.
    /// `Dead` and `Forced` are `0`; `Full` is the whole vocabulary.
    #[inline]
    pub fn rows_scored(&self, vocab_size: usize) -> usize {
        match *self {
            Self::Dead | Self::Forced => 0,
            Self::Restricted { degree } => degree,
            Self::Full { .. } => vocab_size,
        }
    }
}

/// When a gathered-row projection is worth preferring to the dense one.
///
/// The threshold is DATA, not a constant in a branch, because it is a
/// property of the box and the weight layout rather than of the algorithm —
/// and because this repo has already measured that the naive rule is wrong
/// (see the module docs: 20.6 GB/s gathered against 108 GB/s dense).
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct RestrictionPolicy {
    /// Gather only while `degree <= max_active_fraction * vocab_size`.
    ///
    /// Default **0.10**, deliberately below the ~21–34 % band Issue 661
    /// measured for the clustered head: a gather that merely ties has still
    /// spent the enumeration, and the shape this exists for — a grammar at a
    /// structural step — sits two orders of magnitude below the threshold, so
    /// buying the marginal band costs more in false gathers than it returns.
    /// Raise it against a measurement, never against an argument.
    pub max_active_fraction: f32,
    /// Take the [`ProjectionPlan::Forced`] shortcut at degree 1.
    ///
    /// Default `true`. Set `false` to keep the logits of a forced step — a
    /// consumer that reports per-token confidence still needs the number even
    /// though it cannot change the choice.
    pub skip_forced: bool,
}

impl Default for RestrictionPolicy {
    fn default() -> Self {
        Self {
            max_active_fraction: 0.10,
            skip_forced: true,
        }
    }
}

impl RestrictionPolicy {
    /// The dense pass, always. The identity policy — useful as a control arm
    /// in an A/B, where the alternative is a second code path that is not the
    /// one under test.
    pub const DENSE: Self = Self {
        max_active_fraction: 0.0,
        skip_forced: false,
    };

    /// Gather whenever the legal set is strictly smaller than the vocabulary.
    /// **Measured to lose** above ~21 % active; provided so a consumer can
    /// re-measure its own crossover rather than inherit this module's.
    pub const ALWAYS: Self = Self {
        max_active_fraction: 1.0,
        skip_forced: true,
    };
}

/// Decide the projection plan from a legal-set size.
///
/// `legal_degree` is exactly what
/// [`ConstraintPruner::legal_degree`](crate::traits::ConstraintPruner::legal_degree)
/// returned — `None` carries "could not enumerate" all the way into the plan
/// rather than being flattened into a zero on the way.
#[inline]
pub fn plan_projection(
    legal_degree: Option<usize>,
    vocab_size: usize,
    policy: &RestrictionPolicy,
) -> ProjectionPlan {
    let Some(degree) = legal_degree else {
        return ProjectionPlan::Full { unenumerable: true };
    };
    match degree {
        0 => ProjectionPlan::Dead,
        1 if policy.skip_forced => ProjectionPlan::Forced,
        d => {
            // Multiply rather than divide: `vocab_size == 0` then yields a
            // budget of 0 and falls through to Full, where a division would
            // have produced an infinity that compares true against everything.
            let budget = policy.max_active_fraction * vocab_size as f32;
            match (d as f32) <= budget && d < vocab_size {
                true => ProjectionPlan::Restricted { degree: d },
                false => ProjectionPlan::Full {
                    unenumerable: false,
                },
            }
        }
    }
}
