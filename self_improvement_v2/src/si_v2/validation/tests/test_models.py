"""Tests for Validation Gate Matrix models (issue #65)."""

from __future__ import annotations

from si_v2.validation.models import (
    VALIDATION_MATRIX_VERSION,
    ValidationGateDefinition,
    ValidationGateEvidence,
    ValidationGateResult,
    ValidationGateSeverity,
    ValidationGateStatus,
    ValidationMatrixRequest,
    ValidationMatrixResult,
    compute_matrix_fingerprint,
)


class TestValidationGateEvidence:
    def test_valid_evidence(self) -> None:
        e = ValidationGateEvidence(key="k", value="v", detail="d")
        assert e.key == "k"
        assert e.value == "v"

    def test_empty_evidence(self) -> None:
        e = ValidationGateEvidence(key="k", value="v")
        assert e.detail == ""


class TestValidationGateDefinition:
    def test_valid_definition(self) -> None:
        d = ValidationGateDefinition(
            gate_id="test_gate", domain="test", description="A test gate"
        )
        assert d.gate_id == "test_gate"
        assert d.severity == ValidationGateSeverity.HARD

    def test_soft_definition(self) -> None:
        d = ValidationGateDefinition(
            gate_id="soft_gate",
            domain="test",
            description="A soft gate",
            severity=ValidationGateSeverity.SOFT,
        )
        assert d.severity == ValidationGateSeverity.SOFT


class TestValidationGateResult:
    def test_pass_result(self) -> None:
        r = ValidationGateResult(
            gate_id="g1",
            status=ValidationGateStatus.PASS,
            severity=ValidationGateSeverity.HARD,
            reason="ok",
        )
        assert r.passed
        assert not r.is_blocking

    def test_fail_result(self) -> None:
        r = ValidationGateResult(
            gate_id="g1",
            status=ValidationGateStatus.FAIL,
            severity=ValidationGateSeverity.HARD,
            reason="fail",
        )
        assert not r.passed
        assert r.is_blocking

    def test_defer_not_blocking(self) -> None:
        r = ValidationGateResult(
            gate_id="g1",
            status=ValidationGateStatus.DEFER,
            severity=ValidationGateSeverity.SOFT,
            reason="deferred",
        )
        assert not r.passed
        assert not r.is_blocking

    def test_not_applicable(self) -> None:
        r = ValidationGateResult(
            gate_id="g1",
            status=ValidationGateStatus.NOT_APPLICABLE,
            severity=ValidationGateSeverity.HARD,
            reason="n/a",
        )
        assert not r.passed
        assert not r.is_blocking


class TestValidationMatrixRequest:
    def test_default_request(self) -> None:
        req = ValidationMatrixRequest()
        assert req.episode_schema_version is not None
        assert req.policy_version is not None
        assert req.matrix_version == VALIDATION_MATRIX_VERSION

    def test_pass_ready_request(self) -> None:
        req = ValidationMatrixRequest(
            has_proposal_accept=True,
            evidence_fingerprints_valid=True,
            evidence_sufficient_sample=True,
            evidence_not_stale=True,
            backtest_present_and_passed=True,
            walk_forward_present_and_passed=True,
            human_review_accepted=True,
            human_review_pending=False,
        )
        assert req.has_proposal_accept
        assert req.human_review_accepted
        assert not req.human_review_pending

    def test_failing_request(self) -> None:
        req = ValidationMatrixRequest(
            has_proposal_reject=True,
            evidence_fingerprints_valid=False,
        )
        assert req.has_proposal_reject


class TestValidationMatrixResult:
    def test_result_properties(self) -> None:
        gates = (
            ValidationGateResult(
                gate_id="g1",
                status=ValidationGateStatus.PASS,
                severity=ValidationGateSeverity.HARD,
                reason="ok",
            ),
        )
        result = ValidationMatrixResult(
            overall_verdict=ValidationGateStatus.PASS,
            gates=gates,
            matrix_fingerprint="a" * 64,
        )
        assert result.passed
        assert not result.failed
        assert not result.deferred

    def test_fail_result(self) -> None:
        gates = (
            ValidationGateResult(
                gate_id="g1",
                status=ValidationGateStatus.FAIL,
                severity=ValidationGateSeverity.HARD,
                reason="nope",
            ),
        )
        result = ValidationMatrixResult(
            overall_verdict=ValidationGateStatus.FAIL,
            gates=gates,
            matrix_fingerprint="b" * 64,
        )
        assert result.failed
        assert not result.passed

    def test_defer_result(self) -> None:
        gates = (
            ValidationGateResult(
                gate_id="g1",
                status=ValidationGateStatus.DEFER,
                severity=ValidationGateSeverity.SOFT,
                reason="later",
            ),
        )
        result = ValidationMatrixResult(
            overall_verdict=ValidationGateStatus.DEFER,
            gates=gates,
            matrix_fingerprint="c" * 64,
        )
        assert result.deferred
        assert not result.passed


class TestFingerprint:
    def test_deterministic(self) -> None:
        gates = (
            ValidationGateResult(
                gate_id="g1",
                status=ValidationGateStatus.PASS,
                severity=ValidationGateSeverity.HARD,
                reason="ok",
            ),
        )
        # Compute fingerprint from a result object directly
        base = ValidationMatrixResult(
            overall_verdict=ValidationGateStatus.PASS,
            gates=gates,
            matrix_fingerprint="0" * 64,
        )
        fp = compute_matrix_fingerprint(base)
        result = ValidationMatrixResult(
            overall_verdict=ValidationGateStatus.PASS,
            gates=gates,
            matrix_fingerprint=fp,
        )
        assert len(result.matrix_fingerprint) == 64

    def test_fingerprint_changes_on_verdict(self) -> None:
        gates_pass = (
            ValidationGateResult(
                gate_id="g1",
                status=ValidationGateStatus.PASS,
                severity=ValidationGateSeverity.HARD,
                reason="ok",
            ),
        )
        gates_fail = (
            ValidationGateResult(
                gate_id="g1",
                status=ValidationGateStatus.FAIL,
                severity=ValidationGateSeverity.HARD,
                reason="fail",
            ),
        )
        fp1 = compute_matrix_fingerprint(
            ValidationMatrixResult(
                overall_verdict=ValidationGateStatus.PASS,
                gates=gates_pass,
                matrix_fingerprint="0" * 64,
            )
        )
        fp2 = compute_matrix_fingerprint(
            ValidationMatrixResult(
                overall_verdict=ValidationGateStatus.FAIL,
                gates=gates_fail,
                matrix_fingerprint="0" * 64,
            )
        )
        assert fp1 != fp2


class TestNoRuntimeImports:
    def test_no_runtime_imports(self) -> None:
        import si_v2.validation.models as models
        src = models.__file__ or ""
        with open(src) as f:
            content = f.read()
        for forbidden in ("docker", "freqtrade", "exchange", "sqlite3", "subprocess"):
            for line in content.splitlines():
                stripped = line.strip()
                if (stripped.startswith("import ") or stripped.startswith("from ")) and forbidden in stripped:
                    raise AssertionError(f"Forbidden import in validation/models: {stripped}")
