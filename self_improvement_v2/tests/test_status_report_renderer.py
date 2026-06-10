"""Tests for #153: Deterministic status report renderer.

Verifies that ``render_json_report`` and ``render_markdown_report`` produce
deterministic, testable output that never implies operational approval.
"""

from __future__ import annotations

import json

from rehearsal.planning_models import (
    Finding,
    ReasonCode,
    Severity,
    ValidationResult,
    Verdict,
)
from rehearsal.status_report_renderer import (
    render_json_report,
    render_markdown_report,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pass_result() -> ValidationResult:
    """Build a ValidationResult that yields a PASS verdict."""
    result = ValidationResult(package_path=".")
    # A single info finding about successful validation
    result.add(
        Finding(
            reason_code=ReasonCode.SCHEMA_INVALID,
            severity=Severity.INFO,
            verdict=Verdict.PASS,
            message="Schema validates OK",
            check_id="PP-SCHEMA-001",
            field_path="artifacts/schema",
            evidence="All schema checks passed",
            remediation="No action needed",
        )
    )
    result.finalize()
    # Override verdict to PASS even though the only finding is a pass-type
    result.verdict = Verdict.PASS
    result.passed = result.total_checks
    return result


def _make_warning_result() -> ValidationResult:
    """Build a ValidationResult that yields a WARNING verdict."""
    result = ValidationResult(package_path=".")
    result.add(
        Finding(
            reason_code=ReasonCode.ARTIFACT_MISSING,
            severity=Severity.MAJOR,
            verdict=Verdict.WARNING,
            message="Minor artifact issue: missing optional doc",
            check_id="PP-EXISTS-002",
            field_path="artifacts/#999",
            evidence="Optional file not found",
            remediation="Add the optional documentation file",
        )
    )
    result.finalize()
    return result


def _make_blocked_result() -> ValidationResult:
    """Build a ValidationResult that yields a BLOCKED verdict."""
    result = ValidationResult(package_path=".")
    result.add(
        Finding(
            reason_code=ReasonCode.UNSAFE_CONTENT,
            severity=Severity.BLOCKER,
            verdict=Verdict.BLOCKED,
            message="Unredacted API key found in artifact",
            check_id="RC-UNSAFE_CONTENT-api_key",
            field_path="artifact_text",
            evidence="Found 'key_name=sk-...' in proposal text",
            remediation="Replace with [REDACTED_API_KEY] placeholder",
        )
    )
    result.add(
        Finding(
            reason_code=ReasonCode.ARTIFACT_MISSING,
            severity=Severity.BLOCKER,
            verdict=Verdict.BLOCKED,
            message="Required artifact #135 missing",
            check_id="PP-EXISTS-001",
            field_path="artifacts/#135",
            evidence="File does not exist",
            remediation="Create the controlled_rehearsal_planning_gate.md",
        )
    )
    result.finalize()
    return result


# ---------------------------------------------------------------------------
# JSON report tests
# ---------------------------------------------------------------------------


class TestJsonReport:
    """Tests for ``render_json_report``."""

    def test_json_pass_valid_json(self) -> None:
        """PASS result should produce valid JSON."""
        result = _make_pass_result()
        report = render_json_report(result, normalise=True)
        data = json.loads(report)
        assert data["verdict"] == "PASS"

    def test_json_warning_valid_json(self) -> None:
        """WARNING result should produce valid JSON."""
        result = _make_warning_result()
        report = render_json_report(result, normalise=True)
        data = json.loads(report)
        assert data["verdict"] == "WARNING"

    def test_json_blocked_valid_json(self) -> None:
        """BLOCKED result should produce valid JSON."""
        result = _make_blocked_result()
        report = render_json_report(result, normalise=True)
        data = json.loads(report)
        assert data["verdict"] == "BLOCKED"

    def test_json_stable_output(self) -> None:
        """Two calls with the same result should produce identical JSON."""
        result = _make_blocked_result()
        report1 = render_json_report(result, normalise=True)
        report2 = render_json_report(result, normalise=True)
        assert report1 == report2, "JSON report is not deterministic"

    def test_json_has_coverage_matrix(self) -> None:
        """JSON report should include artifact coverage matrix."""
        result = _make_pass_result()
        report = render_json_report(result, normalise=True)
        data = json.loads(report)
        assert "artifact_coverage" in data
        assert len(data["artifact_coverage"]) > 0

    def test_json_has_grouped_severity(self) -> None:
        """JSON report should include findings grouped by severity."""
        result = _make_blocked_result()
        report = render_json_report(result, normalise=True)
        data = json.loads(report)
        assert "findings_grouped_by_severity" in data

    def test_json_has_grouped_reason_code(self) -> None:
        """JSON report should include findings grouped by reason code."""
        result = _make_blocked_result()
        report = render_json_report(result, normalise=True)
        data = json.loads(report)
        assert "findings_grouped_by_reason_code" in data

    def test_json_has_remediation(self) -> None:
        """JSON report should include remediation suggestions."""
        result = _make_blocked_result()
        report = render_json_report(result, normalise=True)
        data = json.loads(report)
        assert "remediation_suggestions" in data

    def test_json_no_approval_language(self) -> None:
        """JSON report must not contain 'approved' or 'operational approval' implying approval."""
        result = _make_pass_result()
        report = render_json_report(result, normalise=True)
        data = json.loads(report)
        note = data.get("note", "")
        # Must contain a disclaimer
        assert "not imply operational approval" in note.lower() or "does NOT imply" in note
        # Must NOT say "approved" in a way that implies operational go-ahead
        assert "APPROVED" not in json.dumps(data)

    def test_json_normalised_timestamp(self) -> None:
        """With normalise=True, the timestamp should be the canonical test value."""
        result = _make_pass_result()
        report = render_json_report(result, normalise=True)
        data = json.loads(report)
        assert data["timestamp"] == "2026-06-10T00:00:00Z"

    def test_json_normalised_path(self) -> None:
        """With normalise=True, package_path should become './'."""
        result = _make_pass_result()
        report = render_json_report(result, normalise=True)
        data = json.loads(report)
        assert data["package_path"] == "./"


# ---------------------------------------------------------------------------
# Markdown report tests
# ---------------------------------------------------------------------------


class TestMarkdownReport:
    """Tests for ``render_markdown_report``."""

    def test_md_pass_has_content(self) -> None:
        """PASS result should produce a non-empty Markdown report."""
        result = _make_pass_result()
        report = render_markdown_report(result, normalise=True)
        assert len(report) > 100
        assert "# Planning Pipeline Validation Report" in report

    def test_md_warning_has_content(self) -> None:
        """WARNING result should produce a non-empty Markdown report."""
        result = _make_warning_result()
        report = render_markdown_report(result, normalise=True)
        assert "WARNING" in report
        assert "⚠️" in report or "WARNING" in report

    def test_md_blocked_has_content(self) -> None:
        """BLOCKED result should produce a non-empty Markdown report."""
        result = _make_blocked_result()
        report = render_markdown_report(result, normalise=True)
        assert "BLOCKED" in report
        assert "❌" in report or "BLOCKED" in report

    def test_md_stable_output(self) -> None:
        """Two calls with the same result should produce identical Markdown."""
        result = _make_blocked_result()
        report1 = render_markdown_report(result, normalise=True)
        report2 = render_markdown_report(result, normalise=True)
        assert report1 == report2, "Markdown report is not deterministic"

    def test_md_has_summary_table(self) -> None:
        """Markdown report should include a summary table."""
        result = _make_pass_result()
        report = render_markdown_report(result, normalise=True)
        assert "| Metric | Value |" in report
        assert "| Total Checks |" in report

    def test_md_has_finding_table(self) -> None:
        """Markdown report should include a findings table."""
        result = _make_warning_result()
        report = render_markdown_report(result, normalise=True)
        assert "| Check ID | Reason Code | Severity | Verdict | Message |" in report or \
               "All Findings" in report

    def test_md_has_coverage_matrix(self) -> None:
        """Markdown report should include an artifact coverage matrix."""
        result = _make_pass_result()
        report = render_markdown_report(result, normalise=True)
        assert "Artifact Coverage Matrix" in report
        assert "| Artifact | Status |" in report

    def test_md_has_severity_grouping(self) -> None:
        """Markdown report should include findings grouped by severity."""
        result = _make_blocked_result()
        report = render_markdown_report(result, normalise=True)
        assert "Findings by Severity" in report

    def test_md_has_reason_code_grouping(self) -> None:
        """Markdown report should include findings grouped by reason code."""
        result = _make_blocked_result()
        report = render_markdown_report(result, normalise=True)
        assert "Findings by Reason Code" in report

    def test_md_has_remediation(self) -> None:
        """Markdown report should include a remediation summary."""
        result = _make_warning_result()
        report = render_markdown_report(result, normalise=True)
        assert "Remediation Summary" in report

    def test_md_has_reference_summary(self) -> None:
        """Markdown report should include a reference summary table."""
        result = _make_pass_result()
        report = render_markdown_report(result, normalise=True)
        assert "Reference Summary" in report
        assert "| #135 |" in report

    def test_md_no_approval_language(self) -> None:
        """Markdown report must contain a no-approval disclaimer."""
        result = _make_pass_result()
        report = render_markdown_report(result, normalise=True)
        # Must contain a disclaimer
        assert "does **NOT** imply" in report
        assert "operational approval" in report.lower()

    def test_md_uses_env_independent_separators(self) -> None:
        """Markdown report should use horizontal rules as section separators."""
        result = _make_pass_result()
        report = render_markdown_report(result, normalise=True)
        assert "---" in report  # Horizontal rule separator
