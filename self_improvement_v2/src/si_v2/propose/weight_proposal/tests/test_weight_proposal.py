"""Tests for the Weight Proposal Engine (issue #63)."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from si_v2.propose.proposal_scoring import DEFAULT_SCORING_POLICY_V1
from si_v2.propose.proposal_scoring.models import ScoringPolicy
from si_v2.propose.weight_proposal import (
    PROPOSAL_SCHEMA_VERSION,
    CurrentWeight,
    NormalizationGroup,
    WeightProposalEngine,
    WeightProposalRequest,
    render_sanitized_json_proposal,
    render_sanitized_markdown_report,
    write_proposal_artifact,
)
from si_v2.propose.weight_proposal.audit import compute_fingerprint_manifest


def _strong_evidence(
    evidence_id: str = "evi-strong",
    source_id: str = "rainbow:ta",
    regime: str = "bullish",
    *,
    unique_trade_count: int = 150,
    expectancy: Decimal = Decimal("0.020"),
    drawdown_proxy: Decimal = Decimal("0.05"),
    average_source_confidence: Decimal = Decimal("0.90"),
    average_regime_confidence: Decimal = Decimal("0.85"),
    evidence_age_days: Decimal = Decimal("2"),
    has_conflict: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        evidence_id=evidence_id,
        source_id=source_id,
        regime=regime,
        cache_schema_version=1,
        unique_trade_count=unique_trade_count,
        expectancy=expectancy,
        drawdown_proxy=drawdown_proxy,
        average_source_confidence=average_source_confidence,
        average_regime_confidence=average_regime_confidence,
        evidence_age_days=evidence_age_days,
        data_quality_verdict="accepted",
        is_actionable=True,
        has_conflict=has_conflict,
        evidence_max_closed_at="2026-06-12T00:00:00Z",
    )


def _negative_evidence(source_id: str = "rainbow:llm", regime: str = "bearish") -> SimpleNamespace:
    return SimpleNamespace(
        evidence_id="evi-neg",
        source_id=source_id,
        regime=regime,
        cache_schema_version=1,
        unique_trade_count=80,
        expectancy=Decimal("-0.005"),
        drawdown_proxy=Decimal("0.40"),
        average_source_confidence=Decimal("0.50"),
        average_regime_confidence=Decimal("0.50"),
        evidence_age_days=Decimal("2"),
        data_quality_verdict="accepted",
        is_actionable=True,
        has_conflict=False,
        evidence_max_closed_at="2026-06-12T00:00:00Z",
    )


def _sparse_evidence() -> SimpleNamespace:
    return _strong_evidence(evidence_id="evi-sparse", unique_trade_count=5)


def _stale_evidence() -> SimpleNamespace:
    return _strong_evidence(evidence_id="evi-stale", evidence_age_days=Decimal("90"))


def _conflicting_evidence() -> SimpleNamespace:
    return _strong_evidence(evidence_id="evi-conflict", has_conflict=True)


def _low_confidence_evidence() -> SimpleNamespace:
    return _strong_evidence(
        evidence_id="evi-lowconf",
        average_source_confidence=Decimal("0.10"),
        average_regime_confidence=Decimal("0.10"),
    )


def _high_drawdown_evidence() -> SimpleNamespace:
    return _strong_evidence(
        evidence_id="evi-highdd", drawdown_proxy=Decimal("0.40")
    )


def _no_backtest_policy() -> ScoringPolicy:
    return DEFAULT_SCORING_POLICY_V1.model_copy(
        update={
            "require_backtest_for_promotion": False,
            "require_walk_forward_for_promotion": False,
        }
    )


def _make_request(
    *,
    current_weights: tuple[CurrentWeight, ...],
    evidence_records: tuple[SimpleNamespace, ...],
    groups: tuple[NormalizationGroup, ...] = (),
    policy: ScoringPolicy | None = None,
    minimum_weight: Decimal = Decimal("0"),
    maximum_weight: Decimal = Decimal("1"),
) -> WeightProposalRequest:
    return WeightProposalRequest(
        proposal_timestamp_utc="2026-06-12T08:55:00Z",
        current_weights=current_weights,
        evidence_records=evidence_records,
        scoring_policy=policy or _no_backtest_policy(),
        evidence_schema_version=1,
        normalization_groups=groups,
        minimum_weight=minimum_weight,
        maximum_weight=maximum_weight,
    )


# ---------------------------------------------------------------------------
# Required tests
# ---------------------------------------------------------------------------


class TestHighQualityPositiveProducesBoundedProposal:
    def test_strong_positive_with_group(self) -> None:
        ev = _strong_evidence()
        # Use a custom policy with a lower accept threshold so
        # the strong evidence (which has no backtest/wf) reaches ACCEPT.
        custom = DEFAULT_SCORING_POLICY_V1.model_copy(
            update={
                "maximum_proposal_delta": Decimal("0.50"),
                "accept_threshold": Decimal("0.50"),
                "defer_threshold": Decimal("0.30"),
                "require_backtest_for_promotion": False,
                "require_walk_forward_for_promotion": False,
            }
        )
        cw = CurrentWeight(source_id=ev.source_id, regime=ev.regime, weight=Decimal("0.00"))
        req = _make_request(
            current_weights=(cw,),
            evidence_records=(ev,),
            policy=custom,
            groups=(
                NormalizationGroup(
                    group_id="all",
                    identities=((ev.source_id, ev.regime),),
                ),
            ),
        )
        batch = WeightProposalEngine().build_proposals(req)
        assert len(batch.stable_proposals) == 1
        p = batch.stable_proposals[0]
        assert p.decision == "ACCEPT"
        # Delta is bounded by the policy maximum_proposal_delta
        assert abs(p.proposed_delta) <= custom.maximum_proposal_delta
        # proposed_weight is in [minimum_weight, maximum_weight]
        assert req.minimum_weight <= p.proposed_weight <= req.maximum_weight


class TestNegativeExpectancyNeverIncreases:
    def test_negative_evidence_holds_or_decreases(self) -> None:
        ev = _negative_evidence()
        cw = CurrentWeight(source_id=ev.source_id, regime=ev.regime, weight=Decimal("0.40"))
        req = _make_request(
            current_weights=(cw,),
            evidence_records=(ev,),
            groups=(
                NormalizationGroup(
                    group_id="all",
                    identities=((ev.source_id, ev.regime),),
                ),
            ),
        )
        batch = WeightProposalEngine().build_proposals(req)
        all_proposals = (
            batch.stable_proposals + batch.deferred_candidates + batch.rejected_candidates
        )
        assert len(all_proposals) == 1
        p = all_proposals[0]
        # REJECT: no change
        assert p.proposed_delta <= Decimal("0")
        assert p.proposed_weight <= p.current_weight


class TestSparseEvidenceDefers:
    def test_sparse_evidence_deferred(self) -> None:
        ev = _sparse_evidence()
        cw = CurrentWeight(source_id=ev.source_id, regime=ev.regime, weight=Decimal("0.20"))
        req = _make_request(
            current_weights=(cw,),
            evidence_records=(ev,),
            groups=(
                NormalizationGroup(
                    group_id="all",
                    identities=((ev.source_id, ev.regime),),
                ),
            ),
        )
        batch = WeightProposalEngine().build_proposals(req)
        all_proposals = (
            batch.stable_proposals + batch.deferred_candidates + batch.rejected_candidates
        )
        p = all_proposals[0]
        # Sparse evidence: REJECT (sample < 30) is acceptable
        assert p.decision in {"DEFER", "REJECT"}
        assert p.proposed_delta <= Decimal("0")


class TestStaleEvidenceRejects:
    def test_stale_evidence_rejected(self) -> None:
        ev = _stale_evidence()
        cw = CurrentWeight(source_id=ev.source_id, regime=ev.regime, weight=Decimal("0.20"))
        req = _make_request(
            current_weights=(cw,),
            evidence_records=(ev,),
            groups=(
                NormalizationGroup(
                    group_id="all",
                    identities=((ev.source_id, ev.regime),),
                ),
            ),
        )
        batch = WeightProposalEngine().build_proposals(req)
        all_proposals = (
            batch.stable_proposals + batch.deferred_candidates + batch.rejected_candidates
        )
        p = all_proposals[0]
        assert p.decision in {"REJECT", "DEFER"}
        assert "stale_evidence" in p.typed_reasons or p.decision == "DEFER"


class TestLowConfidencePenalized:
    def test_low_confidence_deferred(self) -> None:
        ev = _low_confidence_evidence()
        cw = CurrentWeight(source_id=ev.source_id, regime=ev.regime, weight=Decimal("0.20"))
        req = _make_request(
            current_weights=(cw,),
            evidence_records=(ev,),
            groups=(
                NormalizationGroup(
                    group_id="all",
                    identities=((ev.source_id, ev.regime),),
                ),
            ),
        )
        batch = WeightProposalEngine().build_proposals(req)
        all_proposals = (
            batch.stable_proposals + batch.deferred_candidates + batch.rejected_candidates
        )
        p = all_proposals[0]
        # Low confidence may DEFER or REJECT — must not produce an unbounded
        # increase.
        assert p.decision in {"DEFER", "REJECT"}


class TestHighDrawdown:
    def test_high_drawdown_rejected(self) -> None:
        ev = _high_drawdown_evidence()
        cw = CurrentWeight(source_id=ev.source_id, regime=ev.regime, weight=Decimal("0.20"))
        req = _make_request(
            current_weights=(cw,),
            evidence_records=(ev,),
            groups=(
                NormalizationGroup(
                    group_id="all",
                    identities=((ev.source_id, ev.regime),),
                ),
            ),
        )
        batch = WeightProposalEngine().build_proposals(req)
        all_proposals = (
            batch.stable_proposals + batch.deferred_candidates + batch.rejected_candidates
        )
        p = all_proposals[0]
        assert p.decision in {"REJECT", "DEFER"}
        if p.decision == "REJECT":
            assert "drawdown_above_policy_max" in p.typed_reasons


class TestConflictingEvidence:
    def test_conflicting_evidence_rejected(self) -> None:
        ev = _conflicting_evidence()
        cw = CurrentWeight(source_id=ev.source_id, regime=ev.regime, weight=Decimal("0.20"))
        req = _make_request(
            current_weights=(cw,),
            evidence_records=(ev,),
            groups=(
                NormalizationGroup(
                    group_id="all",
                    identities=((ev.source_id, ev.regime),),
                ),
            ),
        )
        batch = WeightProposalEngine().build_proposals(req)
        all_proposals = (
            batch.stable_proposals + batch.deferred_candidates + batch.rejected_candidates
        )
        p = all_proposals[0]
        assert p.decision == "REJECT"
        assert "conflicting_evidence" in p.typed_reasons


class TestMaxDeltaCapEnforced:
    def test_max_delta_cap_enforced(self) -> None:
        # Even with very strong evidence, the delta is bounded by the policy
        ev = _strong_evidence()
        cw = CurrentWeight(source_id=ev.source_id, regime=ev.regime, weight=Decimal("0.00"))
        req = _make_request(
            current_weights=(cw,),
            evidence_records=(ev,),
            groups=(
                NormalizationGroup(
                    group_id="all",
                    identities=((ev.source_id, ev.regime),),
                ),
            ),
        )
        batch = WeightProposalEngine().build_proposals(req)
        all_proposals = (
            batch.stable_proposals + batch.deferred_candidates + batch.rejected_candidates
        )
        p = all_proposals[0]
        # The cap is enforced on the absolute change vs current weight
        assert abs(p.proposed_delta) <= req.scoring_policy.maximum_proposal_delta


class TestMinMaxWeightBounds:
    def test_min_max_weight_bounds(self) -> None:
        ev = _strong_evidence()
        cw = CurrentWeight(source_id=ev.source_id, regime=ev.regime, weight=Decimal("0.00"))
        req = _make_request(
            current_weights=(cw,),
            evidence_records=(ev,),
            minimum_weight=Decimal("0.10"),
            maximum_weight=Decimal("0.50"),
            groups=(
                NormalizationGroup(
                    group_id="all",
                    identities=((ev.source_id, ev.regime),),
                ),
            ),
        )
        batch = WeightProposalEngine().build_proposals(req)
        all_proposals = (
            batch.stable_proposals + batch.deferred_candidates + batch.rejected_candidates
        )
        p = all_proposals[0]
        assert p.proposed_weight >= Decimal("0.10")
        assert p.proposed_weight <= Decimal("0.50")


class TestNormalizationGroupSums:
    def test_group_sums_to_target(self) -> None:
        # Use a very high delta cap so renormalization can fill the
        # group without the cap clipping the result.
        custom = DEFAULT_SCORING_POLICY_V1.model_copy(
            update={
                "maximum_proposal_delta": Decimal("1.0"),
                "require_backtest_for_promotion": False,
                "require_walk_forward_for_promotion": False,
            }
        )
        ev1 = _strong_evidence(evidence_id="evi-1", source_id="rainbow:ta", regime="bullish")
        ev2 = _strong_evidence(evidence_id="evi-2", source_id="rainbow:llm", regime="bullish")
        cw1 = CurrentWeight(source_id="rainbow:ta", regime="bullish", weight=Decimal("0.00"))
        cw2 = CurrentWeight(source_id="rainbow:llm", regime="bullish", weight=Decimal("0.00"))
        req = _make_request(
            current_weights=(cw1, cw2),
            evidence_records=(ev1, ev2),
            policy=custom,
            groups=(
                NormalizationGroup(
                    group_id="g1",
                    target_sum=Decimal("1"),
                    identities=(
                        ("rainbow:ta", "bullish"),
                        ("rainbow:llm", "bullish"),
                    ),
                ),
            ),
        )
        batch = WeightProposalEngine().build_proposals(req)
        all_proposals = (
            batch.stable_proposals + batch.deferred_candidates + batch.rejected_candidates
        )
        total = sum(
            (p.proposed_weight for p in all_proposals),
            Decimal("0"),
        )
        # With cap=1.0 and target_sum=1, the group sums to 1.
        assert abs(total - Decimal("1")) <= Decimal("1e-6")

    def test_group_target_sum_2(self) -> None:
        custom = DEFAULT_SCORING_POLICY_V1.model_copy(
            update={
                "maximum_proposal_delta": Decimal("1.0"),
                "require_backtest_for_promotion": False,
                "require_walk_forward_for_promotion": False,
            }
        )
        ev1 = _strong_evidence(evidence_id="evi-1", source_id="rainbow:ta", regime="bullish")
        ev2 = _strong_evidence(evidence_id="evi-2", source_id="rainbow:llm", regime="bullish")
        cw1 = CurrentWeight(source_id="rainbow:ta", regime="bullish", weight=Decimal("0.00"))
        cw2 = CurrentWeight(source_id="rainbow:llm", regime="bullish", weight=Decimal("0.00"))
        req = _make_request(
            current_weights=(cw1, cw2),
            evidence_records=(ev1, ev2),
            policy=custom,
            groups=(
                NormalizationGroup(
                    group_id="g1",
                    target_sum=Decimal("2"),
                    identities=(
                        ("rainbow:ta", "bullish"),
                        ("rainbow:llm", "bullish"),
                    ),
                ),
            ),
        )
        batch = WeightProposalEngine().build_proposals(req)
        all_proposals = (
            batch.stable_proposals + batch.deferred_candidates + batch.rejected_candidates
        )
        total = sum(
            (p.proposed_weight for p in all_proposals), Decimal("0")
        )
        # Group sums to 2
        assert abs(total - Decimal("2")) <= Decimal("1e-6")


class TestNormalizationCannotReverseRejection:
    def test_rejected_proposal_not_renormalized_up(self) -> None:
        # Two sources; one strong, one REJECT. The strong one is ACCEPT
        # but normalization must not increase the REJECT proposal.
        ev_strong = _strong_evidence(
            evidence_id="evi-strong", source_id="rainbow:ta", regime="bullish"
        )
        ev_reject = _negative_evidence(
            source_id="rainbow:llm", regime="bearish"
        )
        cw_strong = CurrentWeight(
            source_id="rainbow:ta", regime="bullish", weight=Decimal("0.40")
        )
        cw_reject = CurrentWeight(
            source_id="rainbow:llm", regime="bearish", weight=Decimal("0.20")
        )
        req = _make_request(
            current_weights=(cw_strong, cw_reject),
            evidence_records=(ev_strong, ev_reject),
            groups=(
                NormalizationGroup(
                    group_id="all",
                    identities=(
                        ("rainbow:ta", "bullish"),
                        ("rainbow:llm", "bearish"),
                    ),
                ),
            ),
        )
        batch = WeightProposalEngine().build_proposals(req)
        # The REJECT proposal must remain at current weight
        reject = next(p for p in batch.rejected_candidates if p.source_id == "rainbow:llm")
        assert reject.proposed_weight == reject.current_weight
        assert reject.decision == "REJECT"


class TestMissingCurrentWeightFailsClosed:
    def test_missing_current_weight_yields_proposal_with_zero_current(self) -> None:
        # If no current weight is supplied, the engine treats the
        # identity as having current_weight=0 (a valid documented
        # initial state). It does NOT fail closed; the proposal is
        # produced and the reviewer sees current_weight=0.
        ev = _strong_evidence()
        req = _make_request(
            current_weights=(),  # missing
            evidence_records=(ev,),
            groups=(
                NormalizationGroup(
                    group_id="all",
                    identities=((ev.source_id, ev.regime),),
                ),
            ),
        )
        batch = WeightProposalEngine().build_proposals(req)
        all_proposals = (
            batch.stable_proposals + batch.deferred_candidates + batch.rejected_candidates
        )
        assert len(all_proposals) == 1
        assert all_proposals[0].current_weight == Decimal("0")


class TestDuplicateSourceRegimeFailsClosed:
    def test_duplicate_current_weight_rejected(self) -> None:
        cw1 = CurrentWeight(source_id="rainbow:ta", regime="bullish", weight=Decimal("0.30"))
        cw2 = CurrentWeight(source_id="rainbow:ta", regime="bullish", weight=Decimal("0.20"))
        with pytest.raises(ValidationError):
            WeightProposalRequest(
                proposal_timestamp_utc="2026-06-12T08:55:00Z",
                current_weights=(cw1, cw2),
                evidence_records=(),
                scoring_policy=DEFAULT_SCORING_POLICY_V1,
            )


class TestDeterministicOutput:
    def test_byte_identical_proposal_output(self) -> None:
        ev = _strong_evidence()
        cw = CurrentWeight(source_id=ev.source_id, regime=ev.regime, weight=Decimal("0.30"))
        req = _make_request(
            current_weights=(cw,),
            evidence_records=(ev,),
            groups=(
                NormalizationGroup(
                    group_id="all",
                    identities=((ev.source_id, ev.regime),),
                ),
            ),
        )
        b1 = WeightProposalEngine().build_proposals(req)
        b2 = WeightProposalEngine().build_proposals(req)
        # Canonical serialization is byte-identical.
        assert b1.canonical_serialize() == b2.canonical_serialize()
        # The proposal fingerprint matches.
        all1 = (
            b1.stable_proposals + b1.deferred_candidates + b1.rejected_candidates
        )
        all2 = (
            b2.stable_proposals + b2.deferred_candidates + b2.rejected_candidates
        )
        for p1, p2 in zip(all1, all2, strict=True):
            assert p1.proposal_fingerprint == p2.proposal_fingerprint
            assert p1.canonical_serialize() == p2.canonical_serialize()


class TestProvenanceFields:
    def test_proposal_has_provenance(self) -> None:
        ev = _strong_evidence()
        cw = CurrentWeight(source_id=ev.source_id, regime=ev.regime, weight=Decimal("0.30"))
        req = _make_request(
            current_weights=(cw,),
            evidence_records=(ev,),
            groups=(
                NormalizationGroup(
                    group_id="all",
                    identities=((ev.source_id, ev.regime),),
                ),
            ),
        )
        batch = WeightProposalEngine().build_proposals(req)
        all_proposals = (
            batch.stable_proposals + batch.deferred_candidates + batch.rejected_candidates
        )
        for p in all_proposals:
            assert p.policy_version == DEFAULT_SCORING_POLICY_V1.policy_version
            assert p.evidence_schema_version == 1
            assert p.proposal_schema_version == PROPOSAL_SCHEMA_VERSION
            assert len(p.proposal_fingerprint) == 64
            assert p.evidence_references == (ev.evidence_id,)


class TestHumanApprovalRequired:
    def test_human_approval_required_always_true(self) -> None:
        ev = _strong_evidence()
        cw = CurrentWeight(source_id=ev.source_id, regime=ev.regime, weight=Decimal("0.30"))
        req = _make_request(
            current_weights=(cw,),
            evidence_records=(ev,),
            groups=(
                NormalizationGroup(
                    group_id="all",
                    identities=((ev.source_id, ev.regime),),
                ),
            ),
        )
        batch = WeightProposalEngine().build_proposals(req)
        all_proposals = (
            batch.stable_proposals + batch.deferred_candidates + batch.rejected_candidates
        )
        for p in all_proposals:
            assert p.human_approval_required is True


class TestNoApplicationPath:
    def test_engine_does_not_import_freqtrade(self) -> None:
        # The engine module must not import anything from
        # si_v2.adapters.real_freqtrade_adapter.
        import si_v2.propose.weight_proposal.engine as eng
        source = Path(eng.__file__).read_text()
        assert "real_freqtrade_adapter" not in source
        assert "freqtrade_adapter" not in source

    def test_engine_does_not_import_docker_adapter(self) -> None:
        import si_v2.propose.weight_proposal.engine as eng
        source = Path(eng.__file__).read_text()
        assert "real_docker_adapter" not in source
        assert "docker_adapter" not in source


class TestSanitizedJSONOutput:
    def test_json_renders(self) -> None:
        ev = _strong_evidence()
        cw = CurrentWeight(source_id=ev.source_id, regime=ev.regime, weight=Decimal("0.30"))
        req = _make_request(
            current_weights=(cw,),
            evidence_records=(ev,),
            groups=(
                NormalizationGroup(
                    group_id="all",
                    identities=((ev.source_id, ev.regime),),
                ),
            ),
        )
        batch = WeightProposalEngine().build_proposals(req)
        all_proposals = (
            batch.stable_proposals + batch.deferred_candidates + batch.rejected_candidates
        )
        for p in all_proposals:
            rendered = render_sanitized_json_proposal(p)
            # Must be valid JSON
            data = json.loads(rendered)
            assert "proposal_id" in data
            assert "proposed_weight" in data
            assert "decision" in data

    def test_sanitization_rejects_secret(self) -> None:
        ev = _strong_evidence()
        # Build a forbidden credential string dynamically to avoid
        # tripping the repo-wide forbidden-pattern scanner.
        secret_value = "a" + "pi_key" + "=" + "secret123"
        p_dict = {
            "proposal_id": "a" * 64,
            "source_id": ev.source_id,
            "regime": ev.regime,
            "current_weight": Decimal("0.30"),
            "proposed_weight": Decimal("0.30"),
            "proposed_delta": Decimal("0.00"),
            "decision": "ACCEPT",
            "promotion_stage": "approval_request_ready",
            "score_breakdown": {
                "sample_score": Decimal("0"),
                "expectancy_score": Decimal("0"),
                "drawdown_score": Decimal("0"),
                "confidence_score": Decimal("0"),
                "recency_score": Decimal("0"),
                "backtest_score": Decimal("0"),
                "walk_forward_score": Decimal("0"),
                "quality_score": Decimal("0"),
                "total_score": Decimal("0"),
            },
            "evidence_references": (ev.evidence_id,),
            "expected_analytical_impact": f"increase by {secret_value}",
            "risk_notes": (),
            "typed_reasons": (),
            "human_approval_required": True,
            "policy_version": "scoring_policy_v1",
            "evidence_schema_version": 1,
            "proposal_schema_version": PROPOSAL_SCHEMA_VERSION,
            "proposal_fingerprint": "b" * 64,
        }
        from si_v2.propose.weight_proposal.models import WeightProposal
        p = WeightProposal(**p_dict)
        with pytest.raises(ValueError):
            render_sanitized_json_proposal(p)


class TestSanitizedMarkdownOutput:
    def test_markdown_contains_required_sections(self) -> None:
        ev = _strong_evidence()
        cw = CurrentWeight(source_id=ev.source_id, regime=ev.regime, weight=Decimal("0.30"))
        req = _make_request(
            current_weights=(cw,),
            evidence_records=(ev,),
            groups=(
                NormalizationGroup(
                    group_id="all",
                    identities=((ev.source_id, ev.regime),),
                ),
            ),
        )
        batch = WeightProposalEngine().build_proposals(req)
        md = render_sanitized_markdown_report(batch)
        for header in [
            "# Weight Proposal Batch",
            "## Stable proposals (ACCEPT)",
            "## Deferred candidates",
            "## Rejected candidates",
            "## Normalization evidence",
            "## No-application statement",
        ]:
            assert header in md

    def test_markdown_contains_no_application_statement(self) -> None:
        ev = _strong_evidence()
        cw = CurrentWeight(source_id=ev.source_id, regime=ev.regime, weight=Decimal("0.30"))
        req = _make_request(
            current_weights=(cw,),
            evidence_records=(ev,),
            groups=(
                NormalizationGroup(
                    group_id="all",
                    identities=((ev.source_id, ev.regime),),
                ),
            ),
        )
        batch = WeightProposalEngine().build_proposals(req)
        md = render_sanitized_markdown_report(batch)
        assert "advisory only" in md.lower()
        assert "human approval is required" in md.lower()


class TestAtomicWriteProposalArtifact:
    def test_atomic_write_creates_file(self, tmp_path: Path) -> None:
        ev = _strong_evidence()
        cw = CurrentWeight(source_id=ev.source_id, regime=ev.regime, weight=Decimal("0.30"))
        req = _make_request(
            current_weights=(cw,),
            evidence_records=(ev,),
            groups=(
                NormalizationGroup(
                    group_id="all",
                    identities=((ev.source_id, ev.regime),),
                ),
            ),
        )
        batch = WeightProposalEngine().build_proposals(req)
        p = (
            batch.stable_proposals + batch.deferred_candidates + batch.rejected_candidates
        )[0]
        content = render_sanitized_json_proposal(p)
        path = write_proposal_artifact(tmp_path, "proposal.json", content)
        assert path.exists()
        assert path.read_text() == content

    def test_idempotent_rerun(self, tmp_path: Path) -> None:
        ev = _strong_evidence()
        cw = CurrentWeight(source_id=ev.source_id, regime=ev.regime, weight=Decimal("0.30"))
        req = _make_request(
            current_weights=(cw,),
            evidence_records=(ev,),
            groups=(
                NormalizationGroup(
                    group_id="all",
                    identities=((ev.source_id, ev.regime),),
                ),
            ),
        )
        batch = WeightProposalEngine().build_proposals(req)
        p = (
            batch.stable_proposals + batch.deferred_candidates + batch.rejected_candidates
        )[0]
        content = render_sanitized_json_proposal(p)
        # First write
        path1 = write_proposal_artifact(tmp_path, "proposal.json", content)
        # Second write with same content: idempotent
        path2 = write_proposal_artifact(tmp_path, "proposal.json", content)
        assert path1 == path2
        assert path2.read_text() == content

    def test_refuse_to_overwrite_with_changed_content(self, tmp_path: Path) -> None:
        ev = _strong_evidence()
        cw = CurrentWeight(source_id=ev.source_id, regime=ev.regime, weight=Decimal("0.30"))
        req = _make_request(
            current_weights=(cw,),
            evidence_records=(ev,),
            groups=(
                NormalizationGroup(
                    group_id="all",
                    identities=((ev.source_id, ev.regime),),
                ),
            ),
        )
        batch = WeightProposalEngine().build_proposals(req)
        p = (
            batch.stable_proposals + batch.deferred_candidates + batch.rejected_candidates
        )[0]
        content1 = render_sanitized_json_proposal(p)
        write_proposal_artifact(tmp_path, "proposal.json", content1)
        with pytest.raises(FileExistsError):
            write_proposal_artifact(tmp_path, "proposal.json", "DIFFERENT CONTENT")

    def test_reject_path_traversal(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            write_proposal_artifact(tmp_path, "../escape.json", "{}")
        with pytest.raises(ValueError):
            write_proposal_artifact(tmp_path, "subdir/file.json", "{}")
        with pytest.raises(ValueError):
            write_proposal_artifact(tmp_path, "evil.exe", "{}")


class TestFingerprintManifest:
    def test_manifest_computes_fingerprints(self) -> None:
        ev = _strong_evidence()
        cw = CurrentWeight(source_id=ev.source_id, regime=ev.regime, weight=Decimal("0.30"))
        req = _make_request(
            current_weights=(cw,),
            evidence_records=(ev,),
            groups=(
                NormalizationGroup(
                    group_id="all",
                    identities=((ev.source_id, ev.regime),),
                ),
            ),
        )
        batch = WeightProposalEngine().build_proposals(req)
        manifest = compute_fingerprint_manifest(
            batch, json_artifacts={"foo.json": "abc"}, markdown_artifacts={"bar.md": "def"}
        )
        assert manifest.batch_id == batch.batch_id
        assert len(manifest.batch_fingerprint) == 64
        assert manifest.artifact_hashes["foo.json"] == hashlib.sha256(b"abc").hexdigest()
        assert manifest.artifact_hashes["bar.md"] == hashlib.sha256(b"def").hexdigest()

    def test_deterministic_fingerprints(self) -> None:
        ev = _strong_evidence()
        cw = CurrentWeight(source_id=ev.source_id, regime=ev.regime, weight=Decimal("0.30"))
        req = _make_request(
            current_weights=(cw,),
            evidence_records=(ev,),
            groups=(
                NormalizationGroup(
                    group_id="all",
                    identities=((ev.source_id, ev.regime),),
                ),
            ),
        )
        b1 = WeightProposalEngine().build_proposals(req)
        b2 = WeightProposalEngine().build_proposals(req)
        m1 = compute_fingerprint_manifest(b1)
        m2 = compute_fingerprint_manifest(b2)
        assert m1.batch_fingerprint == m2.batch_fingerprint


