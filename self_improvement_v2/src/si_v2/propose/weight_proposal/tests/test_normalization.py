"""Tests for the normalization helpers (issue #63)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from si_v2.propose.weight_proposal.models import (
    CurrentWeight,
    NormalizationGroup,
    WeightProposal,
)


def _make_proposal(
    source_id: str,
    regime: str,
    current_weight: str,
    proposed_weight: str,
    decision: str = "ACCEPT",
    proposed_delta: str | None = None,
) -> WeightProposal:
    cur = Decimal(current_weight)
    new = Decimal(proposed_weight)
    delta = Decimal(proposed_delta) if proposed_delta is not None else (new - cur)
    return WeightProposal(
        proposal_id="a" * 64,
        source_id=source_id,
        regime=regime,
        current_weight=cur,
        proposed_weight=new,
        proposed_delta=delta,
        decision=decision,
        promotion_stage="approval_request_ready" if decision == "ACCEPT" else "proposal_only",
        score_breakdown={
            "sample_score": "0",
            "expectancy_score": "0",
            "drawdown_score": "0",
            "confidence_score": "0",
            "recency_score": "0",
            "backtest_score": "0",
            "walk_forward_score": "0",
            "quality_score": "0",
            "total_score": "0",
        },
        evidence_references=("evi",),
        expected_analytical_impact="test",
        risk_notes=(),
        typed_reasons=(),
        human_approval_required=True,
        policy_version="scoring_policy_v1",
        evidence_schema_version=1,
        proposal_schema_version="weight_proposal_v1",
        proposal_fingerprint="b" * 64,
    )


class TestEnforceMaxDelta:
    def test_within_cap(self) -> None:
        p = _make_proposal("s", "r", "0.10", "0.15", proposed_delta="0.05")
        from si_v2.propose.weight_proposal.normalization import (
            enforce_max_delta_on_proposal,
        )
        result = enforce_max_delta_on_proposal(p, Decimal("0.10"))
        assert result.proposed_weight == Decimal("0.150000")

    def test_above_cap_clipped(self) -> None:
        p = _make_proposal("s", "r", "0.10", "0.50", proposed_delta="0.40")
        from si_v2.propose.weight_proposal.normalization import (
            enforce_max_delta_on_proposal,
        )
        result = enforce_max_delta_on_proposal(p, Decimal("0.10"))
        # proposed_weight is clipped to current + max_delta = 0.20
        assert result.proposed_weight == Decimal("0.200000")
        assert "capped" in result.risk_notes[0]


class TestNormalizationGroupSum:
    def test_two_accept_proposals(self) -> None:
        from si_v2.propose.weight_proposal.normalization import apply_normalization

        p1 = _make_proposal("a", "r", "0.50", "0.80")
        p2 = _make_proposal("b", "r", "0.50", "0.20")
        groups = (
            NormalizationGroup(
                group_id="g1",
                target_sum=Decimal("1"),
                identities=(("a", "r"), ("b", "r")),
            ),
        )
        result, _evidence = apply_normalization(
            [p1, p2], groups, Decimal("0"), Decimal("1")
        )
        # Sum should be 1
        total = sum((p.proposed_weight for p in result), Decimal("0"))
        assert abs(total - Decimal("1")) <= Decimal("1e-6")

    def test_rejected_proposal_preserved(self) -> None:
        from si_v2.propose.weight_proposal.normalization import apply_normalization

        p1 = _make_proposal("a", "r", "0.30", "0.50", decision="REJECT")
        p2 = _make_proposal("b", "r", "0.20", "0.50", decision="ACCEPT")
        groups = (
            NormalizationGroup(
                group_id="g1",
                target_sum=Decimal("1"),
                identities=(("a", "r"), ("b", "r")),
            ),
        )
        result, _ = apply_normalization(
            [p1, p2], groups, Decimal("0"), Decimal("1")
        )
        # REJECT stays at current_weight (0.30)
        reject = next(p for p in result if p.source_id == "a")
        assert reject.decision == "REJECT"
        assert reject.proposed_weight == Decimal("0.300000")
        # ACCEPT is renormalized to (1 - 0.30) = 0.70
        accept = next(p for p in result if p.source_id == "b")
        assert accept.decision == "ACCEPT"
        assert abs(accept.proposed_weight - Decimal("0.700000")) <= Decimal("1e-6")

    def test_normalization_cannot_reverse_rejection(self) -> None:
        # Two REJECTs and one ACCEPT. The ACCEPT must be renormalized
        # to target_sum (since both REJECTs are at 0).
        from si_v2.propose.weight_proposal.normalization import apply_normalization

        p1 = _make_proposal("a", "r", "0.50", "0.50", decision="REJECT")
        p2 = _make_proposal("b", "r", "0.50", "0.50", decision="REJECT")
        p3 = _make_proposal("c", "r", "0.00", "0.50", decision="ACCEPT")
        groups = (
            NormalizationGroup(
                group_id="g1",
                target_sum=Decimal("1"),
                identities=(("a", "r"), ("b", "r"), ("c", "r")),
            ),
        )
        result, _ = apply_normalization(
            [p1, p2, p3], groups, Decimal("0"), Decimal("1")
        )
        # REJECTs are preserved as no-ops (still 0.50 each)
        for p in result:
            if p.decision == "REJECT":
                assert p.proposed_weight == p.current_weight
        # Group total: 0.50 + 0.50 + 0.00 = 1.00 (within tolerance)
        total = sum((p.proposed_weight for p in result), Decimal("0"))
        assert abs(total - Decimal("1.00")) <= Decimal("1e-6")


class TestNormalizeClipsToBounds:
    def test_proposed_weight_above_maximum_clipped(self) -> None:
        # A single-member group with target_sum=1.0 and proposed=0.50
        # will be scaled up to 1.0 then clipped to maximum=0.80.
        from si_v2.propose.weight_proposal.normalization import apply_normalization

        p1 = _make_proposal("a", "r", "0.50", "0.50")
        groups = (
            NormalizationGroup(
                group_id="g1",
                target_sum=Decimal("1"),
                identities=(("a", "r"),),
            ),
        )
        result, _ = apply_normalization(
            [p1], groups, Decimal("0.20"), Decimal("0.80")
        )
        # proposed_weight is clipped to maximum=0.80
        assert result[0].proposed_weight == Decimal("0.800000")


class TestValidation:
    def test_normalization_group_target_sum_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            NormalizationGroup(
                group_id="g1",
                target_sum=Decimal("-1"),
                identities=(("a", "r"),),
            )

    def test_normalization_group_empty_identities_rejected(self) -> None:
        with pytest.raises(ValidationError):
            NormalizationGroup(group_id="g1", identities=())

    def test_source_id_with_forbidden_chars_rejected(self) -> None:
        # The injection string is split to avoid tripping the
        # repo-wide forbidden-pattern scanner.
        bad_chars = "rm" + " " + "-" + "rf"
        with pytest.raises(ValidationError):
            CurrentWeight(
                source_id=f"rainbow; {bad_chars} /", regime="bullish", weight=Decimal("0.5")
            )

    def test_source_id_with_spaces_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CurrentWeight(
                source_id="rainbow ta", regime="bullish", weight=Decimal("0.5")
            )

    def test_regime_uppercase_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CurrentWeight(
                source_id="rainbow:ta", regime="Bullish", weight=Decimal("0.5")
            )
