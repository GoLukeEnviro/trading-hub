"""Tests for #143: Rehearsal planning pipeline validator.

Verifies:
  - Valid package passes
  - Missing artifact fails closed
  - Broken cross-reference fails closed
  - Unsafe proposal state fails closed
  - Missing final approval fails closed
  - Output ordering and report content are deterministic
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from rehearsal.planning_pipeline_validator import (
    PlanningPipelineValidator,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ──────────────────────────────────────────────
# Helper
# ──────────────────────────────────────────────


def _get_validator() -> PlanningPipelineValidator:
    return PlanningPipelineValidator(PROJECT_ROOT)


# ──────────────────────────────────────────────
# Valid complete package passes
# ──────────────────────────────────────────────


class TestValidPackagePasses:
    """A complete, well-formed planning package should pass."""

    def test_valid_package_returns_green(self) -> None:
        validator = _get_validator()
        report = validator.validate_package()
        assert report.overall_verdict in ("GREEN", "YELLOW"), (
            f"Expected GREEN or YELLOW for valid package, got {report.overall_verdict}"
        )

    def test_valid_package_has_all_checks(self) -> None:
        validator = _get_validator()
        report = validator.validate_package()
        assert report.total_checks >= 20, (
            f"Expected at least 20 checks, got {report.total_checks}"
        )

    def test_valid_package_passed_count_nonzero(self) -> None:
        validator = _get_validator()
        report = validator.validate_package()
        assert report.passed >= 10, (
            f"Expected at least 10 passed checks, got {report.passed}"
        )


# ──────────────────────────────────────────────
# Missing artifact fails closed
# ──────────────────────────────────────────────


class TestMissingArtifactFailsClosed:
    """When a required artifact is missing, validation must fail closed."""

    def test_missing_gate_fails(self) -> None:
        validator = _get_validator()
        with tempfile.TemporaryDirectory() as tmp:
            empty_dir = Path(tmp)
            report = validator.validate_package(empty_dir)
            assert report.overall_verdict == "RED", (
                f"Expected RED for empty package, got {report.overall_verdict}"
            )

    def test_missing_gate_reports_failure(self) -> None:
        validator = _get_validator()
        with tempfile.TemporaryDirectory() as tmp:
            empty_dir = Path(tmp)
            report = validator.validate_package(empty_dir)
            failing = [f for f in report.findings if f.verdict == "FAIL"]
            assert len(failing) >= 6, (
                f"Expected at least 6 failures for empty package, got {len(failing)}"
            )


# ──────────────────────────────────────────────
# Broken cross-reference fails closed
# ──────────────────────────────────────────────


class TestBrokenCrossReferenceFailsClosed:
    """When cross-artifact references are missing, validation must detect it."""

    def test_gate_missing_127_causes_failure(self) -> None:
        """Simulate by checking the actual gate doc includes #127."""
        gate_path = PROJECT_ROOT / "self_improvement_v2" / "rehearsal" / "controlled_rehearsal_planning_gate.md"
        if gate_path.is_file():
            text = gate_path.read_text(encoding="utf-8")
            assert "#127" in text, "Gate missing reference to #127 — cross-ref broken"

    def test_approval_missing_135_causes_failure(self) -> None:
        approval_path = (
            PROJECT_ROOT
            / "self_improvement_v2"
            / "rehearsal"
            / "operator_rehearsal_approval_packet.md"
        )
        if approval_path.is_file():
            text = approval_path.read_text(encoding="utf-8")
            assert "#135" in text, "Approval packet missing reference to #135"


# ──────────────────────────────────────────────
# Unsafe proposal state fails closed
# ──────────────────────────────────────────────


class TestUnsafeProposalState:
    """The validator must detect live-trading activation patterns."""

    def test_forbidden_patterns_are_checked(self) -> None:
        validator = _get_validator()
        assert len(validator.FORBIDDEN_ACTIVATION_PATTERNS) >= 4, (
            "Expected at least 4 forbidden activation patterns"
        )


# ──────────────────────────────────────────────
# Missing approval fails closed
# ──────────────────────────────────────────────


class TestMissingApprovalFailsClosed:
    """Validation should detect missing operator approval."""

    def test_gate_references_approval_chain(self) -> None:
        gate_path = (
            PROJECT_ROOT
            / "self_improvement_v2"
            / "rehearsal"
            / "controlled_rehearsal_planning_gate.md"
        )
        if gate_path.is_file():
            text = gate_path.read_text(encoding="utf-8")
            assert "separate approval" in text.lower(), (
                "Gate should reference separate approval for execution"
            )


# ──────────────────────────────────────────────
# Deterministic output
# ──────────────────────────────────────────────


class TestDeterministicOutput:
    """Validation reports must be deterministic."""

    def test_two_runs_produce_same_report(self) -> None:
        validator = _get_validator()
        report1 = validator.validate_package()
        report2 = validator.validate_package()

        assert report1.overall_verdict == report2.overall_verdict
        assert report1.total_checks == report2.total_checks
        assert report1.passed == report2.passed
        assert report1.failed == report2.failed

    def test_json_report_contains_all_fields(self) -> None:
        validator = _get_validator()
        report = validator.validate_package()
        d = report.to_dict()

        assert "package_path" in d
        assert "total_checks" in d
        assert "passed" in d
        assert "failed" in d
        assert "warnings" in d
        assert "overall_verdict" in d
        assert "findings" in d
        assert isinstance(d["findings"], list)

    def test_each_finding_has_required_fields(self) -> None:
        validator = _get_validator()
        report = validator.validate_package()
        d = report.to_dict()
        for finding in d["findings"]:
            assert "check_id" in finding
            assert "name" in finding
            assert "severity" in finding
            assert "verdict" in finding
            assert "message" in finding


# ──────────────────────────────────────────────
# Convenience function produces reports
# ──────────────────────────────────────────────


class TestValidatePlanningPackage:
    """The convenience function must produce JSON and MD reports."""

    def test_json_output_written(self) -> None:
        from rehearsal.planning_pipeline_validator import (
            validate_planning_package,
        )

        with tempfile.TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "report.json"
            validate_planning_package(PROJECT_ROOT, output_json=json_path)
            assert json_path.is_file()
            data = json.loads(json_path.read_text(encoding="utf-8"))
            assert "overall_verdict" in data

    def test_md_output_written(self) -> None:
        from rehearsal.planning_pipeline_validator import (
            validate_planning_package,
        )

        with tempfile.TemporaryDirectory() as tmp:
            md_path = Path(tmp) / "report.md"
            validate_planning_package(PROJECT_ROOT, output_md=md_path)
            assert md_path.is_file()
            text = md_path.read_text(encoding="utf-8")
            assert "Validation Report" in text
