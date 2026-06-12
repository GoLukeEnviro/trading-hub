"""Deterministic proposal scoring engine (issue #35).

Public function:

    score_proposal(input: ProposalScoreInput,
                   policy: ScoringPolicy) -> ProposalDecision

The function is **pure**: no I/O, no logging, no side effects. Two
identical calls with the same input and policy return two
``ProposalDecision`` objects whose canonical JSON serializations are
**byte-identical**.

Pipeline
--------

1. Validate numeric inputs (already done by Pydantic, but we re-check
   that the policy's component weights sum to 1.0).
2. Run the hard rejection gates in a documented order; collect the
   first failing gate (if any) and the failing-gate detail.
3. Compute the eight component scores using ``Decimal`` arithmetic.
4. Compute the total score as the weighted sum (bounded to ``[0, 1]``).
5. Determine the decision:
     * If a hard gate failed → ``REJECT`` with the gate's promotion
       stage (``PROPOSAL_ONLY`` for most gates, ``BACKTEST_REQUIRED``
       for missing backtest, ``WALK_FORWARD_REQUIRED`` for missing
       walk-forward).
     * Else if total >= accept_threshold → ``ACCEPT`` with stage
       ``APPROVAL_REQUEST_READY``.
     * Else if total >= defer_threshold → ``DEFER`` with stage
       ``PROPOSAL_ONLY``.
     * Else → ``REJECT`` with stage ``PROPOSAL_ONLY``.
6. Compute the ``decision_fingerprint`` (SHA-256 over canonical JSON).
7. Return the typed ``ProposalDecision``.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal

from si_v2.propose.proposal_scoring.decimal_safe import (
    quantize_score,
)
from si_v2.propose.proposal_scoring.models import (
    POLICY_VERSION,
    BacktestMetrics,
    HardGateResult,
    PromotionGateResult,
    PromotionStage,
    ProposalDecision,
    ProposalRejectionReason,
    ProposalScoreBreakdown,
    ProposalScoreInput,
    ScoringPolicy,
    WalkForwardMetrics,
)
from si_v2.propose.proposal_scoring.policy import validate_policy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _saturating_ramp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    """Return ``(value - lo) / (hi - lo)`` clamped to ``[0, 1]``.

    Used for ``sample_score`` (ramp from ``minimum_sample_count`` to
    ``2 * minimum_sample_count``) and for ``recency_score`` (inverse
    ramp from 0 to ``maximum_evidence_age_days``).
    """
    if hi <= lo:
        # Degenerate policy — the caller should have caught this in
        # ``validate_policy``, but be defensive.
        if value >= hi:
            return Decimal("1")
        return Decimal("0")
    if value <= lo:
        return Decimal("0")
    if value >= hi:
        return Decimal("1")
    return (value - lo) / (hi - lo)


def _expectancy_score(
    expectancy: Decimal,
    minimum_expectancy: Decimal,
    span: Decimal,
) -> Decimal:
    """Map ``expectancy`` to a score in ``[0, 1]``.

    ``minimum_expectancy`` corresponds to 0.0. ``minimum_expectancy +
    span`` corresponds to 1.0. ``span`` defaults to 0.05 (5%) for
    default policy. Negative expectancy is clamped to 0.0 — the
    negative-for-increase gate is a separate concern.
    """
    if expectancy <= minimum_expectancy:
        return Decimal("0")
    if expectancy >= minimum_expectancy + span:
        return Decimal("1")
    return (expectancy - minimum_expectancy) / span


def _drawdown_score(drawdown: Decimal, max_dd: Decimal) -> Decimal:
    """Inverse ramp: 1.0 when drawdown is 0, 0.0 at max, clipped below."""
    if max_dd <= Decimal("0"):
        return Decimal("1") if drawdown <= Decimal("0") else Decimal("0")
    if drawdown <= Decimal("0"):
        return Decimal("1")
    if drawdown >= max_dd:
        return Decimal("0")
    return Decimal("1") - (drawdown / max_dd)


def _backtest_score(
    backtest: BacktestMetrics | None,
    policy: ScoringPolicy,
) -> Decimal:
    """Compute ``backtest_score`` from a ``BacktestMetrics`` or ``None``.

    Returns ``0.0`` if ``backtest`` is ``None``.
    """
    if backtest is None:
        return Decimal("0")
    bt = backtest
    score = Decimal("0")
    if bt.passed:
        score += Decimal("0.4")
    if bt.profit_total_pct >= policy.minimum_backtest_thresholds.minimum_profit_total_pct:
        score += Decimal("0.2")
    if bt.profit_factor is not None and bt.profit_factor >= policy.minimum_backtest_thresholds.minimum_profit_factor:
        score += Decimal("0.2")
    if bt.max_drawdown_pct <= policy.minimum_backtest_thresholds.maximum_drawdown_pct:
        score += Decimal("0.1")
    if bt.win_rate_pct >= policy.minimum_backtest_thresholds.minimum_win_rate_pct:
        score += Decimal("0.05")
    if bt.total_trades >= policy.minimum_backtest_thresholds.minimum_total_trades:
        score += Decimal("0.05")
    return min(score, Decimal("1"))


def _walk_forward_score(
    walk_forward: WalkForwardMetrics | None,
    policy: ScoringPolicy,
) -> Decimal:
    """Compute ``walk_forward_score`` from ``WalkForwardMetrics`` or ``None``."""
    if walk_forward is None:
        return Decimal("0")
    wf = walk_forward
    score = Decimal("0")
    if wf.passed:
        score += Decimal("0.5")
    if wf.stability_score >= policy.minimum_walk_forward_stability.minimum_stability_score:
        score += Decimal("0.3")
    if (
        wf.out_of_sample_profit_total_pct is not None
        and wf.out_of_sample_profit_total_pct
        >= policy.minimum_walk_forward_stability.minimum_out_of_sample_profit_total_pct
    ):
        score += Decimal("0.2")
    return min(score, Decimal("1"))


# ---------------------------------------------------------------------------
# Hard gates
# ---------------------------------------------------------------------------


def _run_hard_gates(
    inp: ProposalScoreInput, policy: ScoringPolicy
) -> tuple[tuple[HardGateResult, ...], ProposalRejectionReason | None, str]:
    """Run every hard rejection gate and return the results.

    Returns:
        A tuple of:
          * all hard gate results (in documented order);
          * the first failing ``ProposalRejectionReason`` or ``None``;
          * a free-form detail string for the first failing gate
            (empty string if all gates pass).
    """
    results: list[HardGateResult] = []
    first_fail: ProposalRejectionReason | None = None
    first_detail: str = ""

    # 1. Policy version
    if policy.policy_version != POLICY_VERSION:
        results.append(
            HardGateResult(
                reason=ProposalRejectionReason.UNSUPPORTED_POLICY_SCHEMA,
                passed=False,
                detail=f"policy_version={policy.policy_version!r}",
            )
        )
        if first_fail is None:
            first_fail = ProposalRejectionReason.UNSUPPORTED_POLICY_SCHEMA
            first_detail = f"policy_version={policy.policy_version!r}"
    else:
        results.append(
            HardGateResult(
                reason=ProposalRejectionReason.UNSUPPORTED_POLICY_SCHEMA,
                passed=True,
            )
        )

    # 2. Evidence schema version
    if inp.evidence_schema_version not in policy.accepted_evidence_schema_versions:
        results.append(
            HardGateResult(
                reason=ProposalRejectionReason.UNSUPPORTED_EVIDENCE_SCHEMA,
                passed=False,
                detail=(
                    f"evidence_schema_version={inp.evidence_schema_version} "
                    f"not in accepted set "
                    f"{policy.accepted_evidence_schema_versions}"
                ),
            )
        )
        if first_fail is None:
            first_fail = ProposalRejectionReason.UNSUPPORTED_EVIDENCE_SCHEMA
            first_detail = (
                f"evidence_schema_version={inp.evidence_schema_version} "
                f"not in accepted set "
                f"{policy.accepted_evidence_schema_versions}"
            )
    else:
        results.append(
            HardGateResult(
                reason=ProposalRejectionReason.UNSUPPORTED_EVIDENCE_SCHEMA,
                passed=True,
            )
        )

    # 3. Data quality verdict
    if inp.data_quality_verdict != "accepted":
        results.append(
            HardGateResult(
                reason=ProposalRejectionReason.MISSING_DATA_QUALITY_VERDICT,
                passed=False,
                detail=f"data_quality_verdict={inp.data_quality_verdict!r}",
            )
        )
        if first_fail is None:
            first_fail = ProposalRejectionReason.MISSING_DATA_QUALITY_VERDICT
            first_detail = f"data_quality_verdict={inp.data_quality_verdict!r}"
    else:
        results.append(
            HardGateResult(
                reason=ProposalRejectionReason.MISSING_DATA_QUALITY_VERDICT,
                passed=True,
            )
        )

    # 4. Numeric finiteness
    numeric_ok = (
        inp.expectancy.is_finite()
        and inp.drawdown_proxy.is_finite()
        and inp.evidence_age_days.is_finite()
        and (
            inp.average_source_confidence is None
            or inp.average_source_confidence.is_finite()
        )
        and (
            inp.average_regime_confidence is None
            or inp.average_regime_confidence.is_finite()
        )
    )
    if not numeric_ok:
        results.append(
            HardGateResult(
                reason=ProposalRejectionReason.INVALID_NUMERICS,
                passed=False,
                detail="one or more numeric inputs are not finite",
            )
        )
        if first_fail is None:
            first_fail = ProposalRejectionReason.INVALID_NUMERICS
            first_detail = "one or more numeric inputs are not finite"
    else:
        results.append(
            HardGateResult(
                reason=ProposalRejectionReason.INVALID_NUMERICS,
                passed=True,
            )
        )

    # 5. Sample count
    if inp.unique_trade_count < policy.minimum_sample_count:
        results.append(
            HardGateResult(
                reason=ProposalRejectionReason.INSUFFICIENT_EVIDENCE_SAMPLE,
                passed=False,
                detail=(
                    f"unique_trade_count={inp.unique_trade_count} < "
                    f"minimum_sample_count={policy.minimum_sample_count}"
                ),
            )
        )
        if first_fail is None:
            first_fail = ProposalRejectionReason.INSUFFICIENT_EVIDENCE_SAMPLE
            first_detail = (
                f"unique_trade_count={inp.unique_trade_count} < "
                f"minimum_sample_count={policy.minimum_sample_count}"
            )
    else:
        results.append(
            HardGateResult(
                reason=ProposalRejectionReason.INSUFFICIENT_EVIDENCE_SAMPLE,
                passed=True,
            )
        )

    # 6. Stale evidence
    if inp.evidence_age_days > policy.maximum_evidence_age_days:
        results.append(
            HardGateResult(
                reason=ProposalRejectionReason.STALE_EVIDENCE,
                passed=False,
                detail=(
                    f"evidence_age_days={inp.evidence_age_days} > "
                    f"maximum_evidence_age_days={policy.maximum_evidence_age_days}"
                ),
            )
        )
        if first_fail is None:
            first_fail = ProposalRejectionReason.STALE_EVIDENCE
            first_detail = (
                f"evidence_age_days={inp.evidence_age_days} > "
                f"maximum_evidence_age_days={policy.maximum_evidence_age_days}"
            )
    else:
        results.append(
            HardGateResult(
                reason=ProposalRejectionReason.STALE_EVIDENCE,
                passed=True,
            )
        )

    # 7. Conflicting evidence
    if inp.has_conflict:
        results.append(
            HardGateResult(
                reason=ProposalRejectionReason.CONFLICTING_EVIDENCE,
                passed=False,
                detail="has_conflict=True",
            )
        )
        if first_fail is None:
            first_fail = ProposalRejectionReason.CONFLICTING_EVIDENCE
            first_detail = "has_conflict=True"
    else:
        results.append(
            HardGateResult(
                reason=ProposalRejectionReason.CONFLICTING_EVIDENCE,
                passed=True,
            )
        )

    # 8. Drawdown cap
    if inp.drawdown_proxy > policy.maximum_drawdown_proxy:
        results.append(
            HardGateResult(
                reason=ProposalRejectionReason.DRAWDOWN_ABOVE_POLICY_MAX,
                passed=False,
                detail=(
                    f"drawdown_proxy={inp.drawdown_proxy} > "
                    f"maximum_drawdown_proxy={policy.maximum_drawdown_proxy}"
                ),
            )
        )
        if first_fail is None:
            first_fail = ProposalRejectionReason.DRAWDOWN_ABOVE_POLICY_MAX
            first_detail = (
                f"drawdown_proxy={inp.drawdown_proxy} > "
                f"maximum_drawdown_proxy={policy.maximum_drawdown_proxy}"
            )
    else:
        results.append(
            HardGateResult(
                reason=ProposalRejectionReason.DRAWDOWN_ABOVE_POLICY_MAX,
                passed=True,
            )
        )

    # 9. Negative expectancy for increase
    if inp.direction_hint == "increase" and inp.expectancy < policy.minimum_expectancy:
        results.append(
            HardGateResult(
                reason=ProposalRejectionReason.NEGATIVE_EXPECTANCY_FOR_INCREASE,
                passed=False,
                detail=(
                    f"direction_hint=increase but expectancy={inp.expectancy} "
                    f"< minimum_expectancy={policy.minimum_expectancy}"
                ),
            )
        )
        if first_fail is None:
            first_fail = ProposalRejectionReason.NEGATIVE_EXPECTANCY_FOR_INCREASE
            first_detail = (
                f"direction_hint=increase but expectancy={inp.expectancy} "
                f"< minimum_expectancy={policy.minimum_expectancy}"
            )
    else:
        results.append(
            HardGateResult(
                reason=ProposalRejectionReason.NEGATIVE_EXPECTANCY_FOR_INCREASE,
                passed=True,
            )
        )

    # 10. Backtest mandatory
    backtest_missing = policy.require_backtest_for_promotion and inp.backtest_metrics is None
    if backtest_missing:
        results.append(
            HardGateResult(
                reason=ProposalRejectionReason.MISSING_MANDATORY_BACKTEST,
                passed=False,
                detail="backtest_metrics is None and policy requires backtest",
            )
        )
        if first_fail is None:
            first_fail = ProposalRejectionReason.MISSING_MANDATORY_BACKTEST
            first_detail = "backtest_metrics is None and policy requires backtest"
    else:
        results.append(
            HardGateResult(
                reason=ProposalRejectionReason.MISSING_MANDATORY_BACKTEST,
                passed=True,
            )
        )

    # 11. Walk-forward mandatory
    wf_missing = (
        policy.require_walk_forward_for_promotion
        and inp.walk_forward_metrics is None
    )
    if wf_missing:
        results.append(
            HardGateResult(
                reason=ProposalRejectionReason.MISSING_MANDATORY_WALK_FORWARD,
                passed=False,
                detail="walk_forward_metrics is None and policy requires walk-forward",
            )
        )
        if first_fail is None:
            first_fail = ProposalRejectionReason.MISSING_MANDATORY_WALK_FORWARD
            first_detail = (
                "walk_forward_metrics is None and policy requires walk-forward"
            )
    else:
        results.append(
            HardGateResult(
                reason=ProposalRejectionReason.MISSING_MANDATORY_WALK_FORWARD,
                passed=True,
            )
        )

    # 12. Human approval (non-bypassable)
    if not inp.human_approval_available:
        results.append(
            HardGateResult(
                reason=ProposalRejectionReason.HUMAN_APPROVAL_UNAVAILABLE,
                passed=False,
                detail="human_approval_available=False",
            )
        )
        if first_fail is None:
            first_fail = ProposalRejectionReason.HUMAN_APPROVAL_UNAVAILABLE
            first_detail = "human_approval_available=False"
    else:
        results.append(
            HardGateResult(
                reason=ProposalRejectionReason.HUMAN_APPROVAL_UNAVAILABLE,
                passed=True,
            )
        )

    return tuple(results), first_fail, first_detail


def _run_promotion_gates(
    inp: ProposalScoreInput,
    policy: ScoringPolicy,
) -> tuple[PromotionGateResult, ...]:
    """Compute the (advisory) promotion-gate results.

    These results are reported in the ``ProposalDecision`` so reviewers
    can see which promotion stage is required; they are **not** used to
    start any execution path.
    """
    return (
        PromotionGateResult(
            stage=PromotionStage.BACKTEST_REQUIRED,
            required=policy.require_backtest_for_promotion,
            satisfied=inp.backtest_metrics is not None,
            detail=(
                "backtest_metrics present"
                if inp.backtest_metrics is not None
                else "backtest_metrics missing"
            ),
        ),
        PromotionGateResult(
            stage=PromotionStage.WALK_FORWARD_REQUIRED,
            required=policy.require_walk_forward_for_promotion,
            satisfied=inp.walk_forward_metrics is not None,
            detail=(
                "walk_forward_metrics present"
                if inp.walk_forward_metrics is not None
                else "walk_forward_metrics missing"
            ),
        ),
    )


def _promotion_stage_for_gate(
    first_fail: ProposalRejectionReason | None,
) -> PromotionStage:
    """Map a failing hard gate to its associated promotion stage."""
    if first_fail == ProposalRejectionReason.MISSING_MANDATORY_BACKTEST:
        return PromotionStage.BACKTEST_REQUIRED
    if first_fail == ProposalRejectionReason.MISSING_MANDATORY_WALK_FORWARD:
        return PromotionStage.WALK_FORWARD_REQUIRED
    return PromotionStage.PROPOSAL_ONLY


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def score_proposal(
    inp: ProposalScoreInput,
    policy: ScoringPolicy,
) -> ProposalDecision:
    """Score one proposal input against one policy. Pure function."""
    # Validate the policy once more (defence in depth — Pydantic already
    # enforces most of these checks).
    validate_policy(policy)

    hard_gates, first_fail, _first_detail = _run_hard_gates(inp, policy)
    promotion_gates = _run_promotion_gates(inp, policy)

    # Component scores
    sample = _saturating_ramp(
        Decimal(inp.unique_trade_count),
        Decimal(policy.minimum_sample_count),
        Decimal(policy.minimum_sample_count) * Decimal("2"),
    )
    expectancy = _expectancy_score(
        inp.expectancy,
        policy.minimum_expectancy,
        Decimal("0.05"),
    )
    drawdown = _drawdown_score(inp.drawdown_proxy, policy.maximum_drawdown_proxy)
    if (
        inp.average_source_confidence is not None
        and inp.average_regime_confidence is not None
    ):
        confidence = min(
            inp.average_source_confidence,
            inp.average_regime_confidence,
        )
    elif inp.average_source_confidence is not None:
        confidence = inp.average_source_confidence
    elif inp.average_regime_confidence is not None:
        confidence = inp.average_regime_confidence
    else:
        confidence = Decimal("0")
    if confidence < policy.minimum_confidence:
        # Soft penalty: scale by the ratio of actual/policy minimum.
        if policy.minimum_confidence > Decimal("0"):
            confidence = confidence * (Decimal("1") / policy.minimum_confidence) * Decimal("0.5")
        else:
            confidence = Decimal("0")
    confidence = max(Decimal("0"), min(Decimal("1"), confidence))

    recency = _saturating_ramp(
        policy.maximum_evidence_age_days - inp.evidence_age_days,
        Decimal("0"),
        policy.maximum_evidence_age_days,
    )
    backtest = _backtest_score(inp.backtest_metrics, policy)
    walk_forward = _walk_forward_score(inp.walk_forward_metrics, policy)
    quality = (
        Decimal("1")
        if inp.data_quality_verdict == "accepted" and inp.is_actionable
        else Decimal("0")
    )

    # Quantize each component
    q_sample = quantize_score(sample, "sample_score")
    q_expectancy = quantize_score(expectancy, "expectancy_score")
    q_drawdown = quantize_score(drawdown, "drawdown_score")
    q_confidence = quantize_score(confidence, "confidence_score")
    q_recency = quantize_score(recency, "recency_score")
    q_backtest = quantize_score(backtest, "backtest_score")
    q_walk_forward = quantize_score(walk_forward, "walk_forward_score")
    q_quality = quantize_score(quality, "quality_score")

    # Weighted total
    w = policy.component_weights
    total_unscaled = (
        q_sample * w.sample
        + q_expectancy * w.expectancy
        + q_drawdown * w.drawdown
        + q_confidence * w.confidence
        + q_recency * w.recency
        + q_backtest * w.backtest
        + q_walk_forward * w.walk_forward
        + q_quality * w.quality
    )
    q_total = quantize_score(total_unscaled, "total_score")

    breakdown = ProposalScoreBreakdown(
        sample_score=q_sample,
        expectancy_score=q_expectancy,
        drawdown_score=q_drawdown,
        confidence_score=q_confidence,
        recency_score=q_recency,
        backtest_score=q_backtest,
        walk_forward_score=q_walk_forward,
        quality_score=q_quality,
        total_score=q_total,
    )

    # Decision logic
    if first_fail is not None:
        decision: str = "REJECT"
        typed_reasons: tuple[ProposalRejectionReason, ...] = (first_fail,)
        promotion_stage = _promotion_stage_for_gate(first_fail)
    elif q_total >= policy.accept_threshold:
        decision = "ACCEPT"
        typed_reasons = ()
        promotion_stage = PromotionStage.APPROVAL_REQUEST_READY
    elif q_total >= policy.defer_threshold:
        decision = "DEFER"
        typed_reasons = ()
        promotion_stage = PromotionStage.PROPOSAL_ONLY
    else:
        decision = "REJECT"
        typed_reasons = ()
        promotion_stage = PromotionStage.PROPOSAL_ONLY

    # Build a temporary decision to compute its fingerprint.
    temp = ProposalDecision(
        decision=decision,
        evidence_id=inp.evidence_id,
        source_id=inp.source_id,
        regime=inp.regime,
        policy_version=POLICY_VERSION,
        evidence_schema_version=inp.evidence_schema_version,
        score=breakdown,
        hard_gate_results=hard_gates,
        promotion_gate_results=promotion_gates,
        typed_reasons=typed_reasons,
        promotion_stage=promotion_stage,
        human_approval_required=True,
        decision_fingerprint="0" * 64,  # placeholder for fingerprint
    )
    fingerprint = hashlib.sha256(
        temp.canonical_serialize().encode("utf-8")
    ).hexdigest()
    return temp.model_copy(update={"decision_fingerprint": fingerprint})
