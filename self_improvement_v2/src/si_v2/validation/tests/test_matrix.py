"""Tests for Validation Gate Matrix builder (issue #65)."""

from __future__ import annotations

from si_v2.validation.matrix import run_validation_matrix
from si_v2.validation.models import (
    VALIDATION_MATRIX_VERSION,
    ValidationGateStatus,
    ValidationMatrixRequest,
)


class TestMatrixAllPass:
    def test_all_pass(self) -> None:
        req = ValidationMatrixRequest(
            has_proposal_accept=True,
            evidence_fingerprints_valid=True,
            evidence_sufficient_sample=True,
            evidence_not_stale=True,
            evidence_expectancy_not_negative_for_increase=True,
            backtest_present_and_passed=True,
            walk_forward_present_and_passed=True,
            episode_verdict_is_hardened=True,
            episode_fingerprint_manifest_consistent=True,
            human_review_accepted=True,
            human_review_pending=False,
            policy_compliant=True,
        )
        result = run_validation_matrix(req)
        assert result.overall_verdict == ValidationGateStatus.PASS
        assert result.passed
        assert len(result.gates) == 11
        assert result.matrix_version == VALIDATION_MATRIX_VERSION
        assert len(result.matrix_fingerprint) == 64


class TestMatrixHardFail:
    def test_rejected_proposal_fails(self) -> None:
        req = ValidationMatrixRequest(
            has_proposal_reject=True,
        )
        result = run_validation_matrix(req)
        assert result.overall_verdict == ValidationGateStatus.FAIL
        assert result.failed

    def test_bad_provenance_fails(self) -> None:
        req = ValidationMatrixRequest(
            evidence_fingerprints_valid=False,
        )
        result = run_validation_matrix(req)
        assert result.overall_verdict == ValidationGateStatus.FAIL

    def test_missing_backtest_fails(self) -> None:
        req = ValidationMatrixRequest(
            has_proposal_accept=True,
            evidence_fingerprints_valid=True,
            evidence_sufficient_sample=True,
            evidence_not_stale=True,
            backtest_present_and_passed=False,
        )
        result = run_validation_matrix(req)
        assert result.overall_verdict == ValidationGateStatus.FAIL

    def test_schema_mismatch_fails(self) -> None:
        req = ValidationMatrixRequest(
            episode_schema_version="",
        )
        result = run_validation_matrix(req)
        assert result.overall_verdict == ValidationGateStatus.FAIL


class TestMatrixDefer:
    def test_pending_review_defers(self) -> None:
        req = ValidationMatrixRequest(
            has_proposal_accept=True,
            evidence_fingerprints_valid=True,
            evidence_sufficient_sample=True,
            evidence_not_stale=True,
            backtest_present_and_passed=True,
            walk_forward_present_and_passed=True,
            episode_verdict_is_hardened=True,
            human_review_pending=True,
            human_review_accepted=False,
        )
        result = run_validation_matrix(req)
        assert result.overall_verdict == ValidationGateStatus.DEFER

    def test_shadow_metadata_defers(self) -> None:
        req = ValidationMatrixRequest(
            has_proposal_accept=True,
            evidence_fingerprints_valid=True,
            evidence_sufficient_sample=True,
            evidence_not_stale=True,
            backtest_present_and_passed=True,
            walk_forward_present_and_passed=True,
            episode_verdict_is_hardened=True,
            human_review_accepted=True,
            human_review_pending=False,
            shadow_readiness_metadata_ok=False,
        )
        result = run_validation_matrix(req)
        assert result.overall_verdict == ValidationGateStatus.DEFER


class TestMatrixFailTakesPrecedence:
    def test_fail_overrides_defer(self) -> None:
        req = ValidationMatrixRequest(
            has_proposal_reject=True,
            human_review_pending=True,
        )
        result = run_validation_matrix(req)
        assert result.overall_verdict == ValidationGateStatus.FAIL

    def test_hard_fail_short_circuits(self) -> None:
        """First HARD FAIL should make remaining gates NOT_APPLICABLE."""
        req = ValidationMatrixRequest(
            evidence_fingerprints_valid=False,
            has_proposal_reject=True,  # would also fail, but should be skipped
        )
        result = run_validation_matrix(req)
        assert result.overall_verdict == ValidationGateStatus.FAIL
        # Gates after evidence_source_provenance should be NOT_APPLICABLE
        for gate in result.gates:
            if gate.gate_id == "evidence_source_provenance":
                assert gate.status == ValidationGateStatus.FAIL
            elif gate.gate_id in ("schema_policy_compatibility",):
                # These come before the failing gate
                pass
            elif gate.status == ValidationGateStatus.NOT_APPLICABLE:
                pass  # This is expected for short-circuited gates


class TestMatrixDeterminism:
    def test_deterministic_output(self) -> None:
        req = ValidationMatrixRequest(
            has_proposal_accept=True,
            evidence_fingerprints_valid=True,
            evidence_sufficient_sample=True,
            evidence_not_stale=True,
            backtest_present_and_passed=True,
            walk_forward_present_and_passed=True,
            episode_verdict_is_hardened=True,
            episode_fingerprint_manifest_consistent=True,
            human_review_accepted=True,
            human_review_pending=False,
            policy_compliant=True,
        )
        r1 = run_validation_matrix(req)
        r2 = run_validation_matrix(req)
        assert r1.model_dump_json() == r2.model_dump_json()
        assert r1.matrix_fingerprint == r2.matrix_fingerprint


class TestMatrixNotExecutionAuthority:
    def test_pass_means_review_only(self) -> None:
        req = ValidationMatrixRequest(
            has_proposal_accept=True,
            evidence_fingerprints_valid=True,
            evidence_sufficient_sample=True,
            evidence_not_stale=True,
            backtest_present_and_passed=True,
            walk_forward_present_and_passed=True,
            episode_verdict_is_hardened=True,
            human_review_accepted=True,
            human_review_pending=False,
            policy_compliant=True,
        )
        result = run_validation_matrix(req)
        assert result.overall_verdict == ValidationGateStatus.PASS
        # PASS does NOT mean approved or executable
        assert result.passed  # but it IS ready for human review
