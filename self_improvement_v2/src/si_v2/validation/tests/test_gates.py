"""Tests for validation gate evaluators (issue #65)."""

from __future__ import annotations

from si_v2.validation.gates import (
    GATE_REGISTRY,
    evaluate_backtest_evidence,
    evaluate_dry_run_readiness,
    evaluate_episode_report_integrity,
    evaluate_evidence_sample_recency,
    evaluate_evidence_source_provenance,
    evaluate_human_review_status,
    evaluate_proposal_decision_delta,
    evaluate_safety_invariants,
    evaluate_schema_policy_compatibility,
    evaluate_shadow_readiness,
    evaluate_walk_forward_evidence,
    get_evaluator,
)
from si_v2.validation.models import (
    ValidationGateStatus,
    ValidationMatrixRequest,
)


class TestGateRegistry:
    def test_registry_has_11_gates(self) -> None:
        assert len(GATE_REGISTRY) == 11

    def test_registry_stable_order(self) -> None:
        ids = [g.gate_id for g in GATE_REGISTRY]
        assert ids == [
            "schema_policy_compatibility",
            "evidence_source_provenance",
            "evidence_sample_recency",
            "proposal_decision_delta",
            "backtest_evidence",
            "walk_forward_evidence",
            "episode_report_integrity",
            "human_review_status",
            "shadow_readiness",
            "dry_run_readiness",
            "safety_invariants",
        ]

    def test_all_evaluators_registered(self) -> None:
        for gate in GATE_REGISTRY:
            evaluator = get_evaluator(gate.gate_id)
            assert evaluator is not None

    def test_bad_evaluator_raises(self) -> None:
        import pytest
        with pytest.raises(KeyError):
            get_evaluator("nonexistent_gate")


class TestGateSchemaPolicy:
    def test_pass(self) -> None:
        req = ValidationMatrixRequest(policy_compliant=True)
        result = evaluate_schema_policy_compatibility(req)
        assert result.status == ValidationGateStatus.PASS

    def test_fail_empty_schema(self) -> None:
        req = ValidationMatrixRequest(episode_schema_version="")
        result = evaluate_schema_policy_compatibility(req)
        assert result.status == ValidationGateStatus.FAIL

    def test_fail_non_compliant(self) -> None:
        req = ValidationMatrixRequest(policy_compliant=False)
        result = evaluate_schema_policy_compatibility(req)
        assert result.status == ValidationGateStatus.FAIL


class TestGateEvidenceProvenance:
    def test_pass(self) -> None:
        req = ValidationMatrixRequest(evidence_fingerprints_valid=True)
        result = evaluate_evidence_source_provenance(req)
        assert result.status == ValidationGateStatus.PASS

    def test_fail(self) -> None:
        req = ValidationMatrixRequest(evidence_fingerprints_valid=False)
        result = evaluate_evidence_source_provenance(req)
        assert result.status == ValidationGateStatus.FAIL


class TestGateSampleRecency:
    def test_pass(self) -> None:
        req = ValidationMatrixRequest(
            evidence_sufficient_sample=True, evidence_not_stale=True
        )
        result = evaluate_evidence_sample_recency(req)
        assert result.status == ValidationGateStatus.PASS

    def test_fail_insufficient_sample(self) -> None:
        req = ValidationMatrixRequest(evidence_sufficient_sample=False)
        result = evaluate_evidence_sample_recency(req)
        assert result.status == ValidationGateStatus.FAIL

    def test_fail_stale(self) -> None:
        req = ValidationMatrixRequest(
            evidence_sufficient_sample=True, evidence_not_stale=False
        )
        result = evaluate_evidence_sample_recency(req)
        assert result.status == ValidationGateStatus.FAIL


class TestGateProposalDecision:
    def test_pass_accept(self) -> None:
        req = ValidationMatrixRequest(has_proposal_accept=True)
        result = evaluate_proposal_decision_delta(req)
        assert result.status == ValidationGateStatus.PASS

    def test_fail_reject(self) -> None:
        req = ValidationMatrixRequest(has_proposal_reject=True)
        result = evaluate_proposal_decision_delta(req)
        assert result.status == ValidationGateStatus.FAIL

    def test_defer_all_deferred(self) -> None:
        req = ValidationMatrixRequest(
            has_proposal_defer=True,
            has_proposal_accept=False,
            has_proposal_reject=False,
        )
        result = evaluate_proposal_decision_delta(req)
        assert result.status == ValidationGateStatus.DEFER

    def test_fail_negative_expectancy_increase(self) -> None:
        req = ValidationMatrixRequest(
            has_proposal_accept=True,
            evidence_expectancy_not_negative_for_increase=False,
        )
        result = evaluate_proposal_decision_delta(req)
        assert result.status == ValidationGateStatus.FAIL


class TestGateBacktest:
    def test_pass(self) -> None:
        req = ValidationMatrixRequest(backtest_present_and_passed=True)
        result = evaluate_backtest_evidence(req)
        assert result.status == ValidationGateStatus.PASS

    def test_fail(self) -> None:
        req = ValidationMatrixRequest(backtest_present_and_passed=False)
        result = evaluate_backtest_evidence(req)
        assert result.status == ValidationGateStatus.FAIL


class TestGateWalkForward:
    def test_pass(self) -> None:
        req = ValidationMatrixRequest(walk_forward_present_and_passed=True)
        result = evaluate_walk_forward_evidence(req)
        assert result.status == ValidationGateStatus.PASS

    def test_fail(self) -> None:
        req = ValidationMatrixRequest(walk_forward_present_and_passed=False)
        result = evaluate_walk_forward_evidence(req)
        assert result.status == ValidationGateStatus.FAIL


class TestGateEpisodeIntegrity:
    def test_pass(self) -> None:
        req = ValidationMatrixRequest(
            episode_verdict_is_hardened=True,
            episode_fingerprint_manifest_consistent=True,
        )
        result = evaluate_episode_report_integrity(req)
        assert result.status == ValidationGateStatus.PASS

    def test_fail_not_hardened(self) -> None:
        req = ValidationMatrixRequest(episode_verdict_is_hardened=False)
        result = evaluate_episode_report_integrity(req)
        assert result.status == ValidationGateStatus.FAIL

    def test_fail_inconsistent_manifest(self) -> None:
        req = ValidationMatrixRequest(
            episode_verdict_is_hardened=True,
            episode_fingerprint_manifest_consistent=False,
        )
        result = evaluate_episode_report_integrity(req)
        assert result.status == ValidationGateStatus.FAIL


class TestGateHumanReview:
    def test_pass_accepted(self) -> None:
        req = ValidationMatrixRequest(
            human_review_accepted=True,
            human_review_pending=False,
        )
        result = evaluate_human_review_status(req)
        assert result.status == ValidationGateStatus.PASS

    def test_fail_rejected(self) -> None:
        req = ValidationMatrixRequest(human_review_rejected=True)
        result = evaluate_human_review_status(req)
        assert result.status == ValidationGateStatus.FAIL

    def test_defer_pending(self) -> None:
        req = ValidationMatrixRequest(human_review_pending=True)
        result = evaluate_human_review_status(req)
        assert result.status == ValidationGateStatus.DEFER

    def test_defer_deferred(self) -> None:
        req = ValidationMatrixRequest(
            human_review_pending=False,
            human_review_deferred=True,
        )
        result = evaluate_human_review_status(req)
        assert result.status == ValidationGateStatus.DEFER

    def test_defer_unknown(self) -> None:
        req = ValidationMatrixRequest(
            human_review_accepted=False,
            human_review_rejected=False,
            human_review_pending=False,
            human_review_deferred=False,
        )
        result = evaluate_human_review_status(req)
        assert result.status == ValidationGateStatus.DEFER


class TestGateShadowReadiness:
    def test_pass(self) -> None:
        req = ValidationMatrixRequest(shadow_readiness_metadata_ok=True)
        result = evaluate_shadow_readiness(req)
        assert result.status == ValidationGateStatus.PASS

    def test_defer(self) -> None:
        req = ValidationMatrixRequest(shadow_readiness_metadata_ok=False)
        result = evaluate_shadow_readiness(req)
        assert result.status == ValidationGateStatus.DEFER


class TestGateDryRunReadiness:
    def test_pass(self) -> None:
        req = ValidationMatrixRequest(dry_run_readiness_metadata_ok=True)
        result = evaluate_dry_run_readiness(req)
        assert result.status == ValidationGateStatus.PASS

    def test_defer(self) -> None:
        req = ValidationMatrixRequest(dry_run_readiness_metadata_ok=False)
        result = evaluate_dry_run_readiness(req)
        assert result.status == ValidationGateStatus.DEFER


class TestGateSafety:
    def test_pass(self) -> None:
        req = ValidationMatrixRequest(policy_compliant=True)
        result = evaluate_safety_invariants(req)
        assert result.status == ValidationGateStatus.PASS

    def test_fail(self) -> None:
        req = ValidationMatrixRequest(policy_compliant=False)
        result = evaluate_safety_invariants(req)
        assert result.status == ValidationGateStatus.FAIL
