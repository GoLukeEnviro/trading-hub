"""Integration tests for Validation Gate Matrix using #181 real contracts (issue #65)."""

from __future__ import annotations

from si_v2.validation.matrix import run_validation_matrix
from si_v2.validation.models import (
    ValidationGateStatus,
    ValidationMatrixRequest,
)
from si_v2.validation.renderers import (
    render_validation_matrix_json,
    render_validation_matrix_markdown,
)

# ---------------------------------------------------------------------------
# Real integration scenarios using the same semantics as #181
# ---------------------------------------------------------------------------


class TestIntegrationValidEpisode:
    """Full valid episode that should PASS all gates."""

    def test_valid_episode_passes(self) -> None:
        req = ValidationMatrixRequest(
            has_proposal_accept=True,
            evidence_fingerprints_valid=True,
            evidence_sufficient_sample=True,
            evidence_not_stale=True,
            evidence_not_conflicting=True,
            evidence_expectancy_not_negative_for_increase=True,
            evidence_drawdown_within_bounds=True,
            backtest_present_and_passed=True,
            walk_forward_present_and_passed=True,
            episode_verdict_is_hardened=True,
            episode_fingerprint_manifest_consistent=True,
            human_review_accepted=True,
            human_review_pending=False,
            shadow_readiness_metadata_ok=True,
            dry_run_readiness_metadata_ok=True,
            policy_compliant=True,
        )
        result = run_validation_matrix(req)
        assert result.overall_verdict == ValidationGateStatus.PASS
        assert result.passed
        assert len(result.gates) == 11

    def test_valid_renderers_work(self) -> None:
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
        json_output = render_validation_matrix_json(result)
        assert "overall_verdict" in json_output
        assert "PASS" in json_output

        md_output = render_validation_matrix_markdown(result)
        assert "Validation Gate Matrix Report" in md_output
        assert "PASS" in md_output or "✅" in md_output


class TestIntegrationRejectedEpisode:
    """Episode with a rejected proposal."""

    def test_rejected_episode_fails(self) -> None:
        req = ValidationMatrixRequest(
            has_proposal_reject=True,
        )
        result = run_validation_matrix(req)
        assert result.overall_verdict == ValidationGateStatus.FAIL


class TestIntegrationMissingBacktest:
    """Episode missing mandatory backtest."""

    def test_missing_backtest_fails(self) -> None:
        req = ValidationMatrixRequest(
            has_proposal_accept=True,
            evidence_fingerprints_valid=True,
            evidence_sufficient_sample=True,
            evidence_not_stale=True,
            backtest_present_and_passed=False,
            walk_forward_present_and_passed=True,
            episode_verdict_is_hardened=True,
            human_review_accepted=True,
            human_review_pending=False,
            policy_compliant=True,
        )
        result = run_validation_matrix(req)
        assert result.overall_verdict == ValidationGateStatus.FAIL
        # Verify the backtest gate specifically failed
        backtest_gate = next(g for g in result.gates if g.gate_id == "backtest_evidence")
        assert backtest_gate.status == ValidationGateStatus.FAIL


class TestIntegrationNegativeExpectancy:
    """Negative expectancy increase must fail."""

    def test_negative_expectancy_fails(self) -> None:
        req = ValidationMatrixRequest(
            has_proposal_accept=True,
            evidence_expectancy_not_negative_for_increase=False,
        )
        result = run_validation_matrix(req)
        assert result.overall_verdict == ValidationGateStatus.FAIL
        proposal_gate = next(g for g in result.gates if g.gate_id == "proposal_decision_delta")
        assert proposal_gate.status == ValidationGateStatus.FAIL


class TestIntegrationDeterminism:
    """Byte-stable outputs under identical inputs."""

    def test_deterministic_json(self) -> None:
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
        r1 = run_validation_matrix(req)
        r2 = run_validation_matrix(req)
        json1 = render_validation_matrix_json(r1)
        json2 = render_validation_matrix_json(r2)
        assert json1 == json2
        md1 = render_validation_matrix_markdown(r1)
        md2 = render_validation_matrix_markdown(r2)
        assert md1 == md2


class TestIntegrationNoExec:
    """Verify no executable paths exist."""

    def test_no_runtime_imports(self) -> None:
        import si_v2.validation
        src = si_v2.validation.__file__ or ""
        root = src.replace("__init__.py", "")
        import os
        for dirpath, _dirnames, filenames in os.walk(root):
            for fn in filenames:
                if fn.endswith(".py"):
                    fpath = os.path.join(dirpath, fn)
                    with open(fpath) as f:
                        content = f.read()
                    for forbidden in ("docker", "freqtrade", "exchange", "subprocess"):
                        for line in content.splitlines():
                            stripped = line.strip()
                            is_import = stripped.startswith("import ") or stripped.startswith("from ")
                            if is_import and forbidden in stripped:
                                raise AssertionError(
                                    f"Forbidden import in {fn}: {stripped}"
                                )
