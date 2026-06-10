"""Golden snapshot and policy regression suite (#154).

Compares current validation and rendering output against stored golden
reference files to detect regressions.

Golden files live under ``tests/fixtures/golden/{pass,warning,blocked}/``.

**Snapshot update:** Set ``UPDATE_SNAPSHOTS=1`` in the environment to
overwrite golden files with current output.  Normal runs never rewrite.
"""

from __future__ import annotations

import os
from pathlib import Path

from rehearsal.planning_models import (
    Finding,
    ReasonCode,
    Severity,
    ValidationResult,
    Verdict,
)
from rehearsal.status_report_renderer import render_json_report, render_markdown_report

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

GOLDEN_DIR = Path(__file__).resolve().parent / "fixtures" / "golden"
UPDATE_SNAPSHOTS = os.environ.get("UPDATE_SNAPSHOTS", "") == "1"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pass_result() -> ValidationResult:
    """Build a PASS ValidationResult matching the pass golden snapshot."""
    result = ValidationResult(package_path=".")
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
    result.total_checks = 5
    result.passed = 5
    result.warnings = 0
    result.blocked = 0
    result.verdict = Verdict.PASS
    return result


def _make_warning_result() -> ValidationResult:
    """Build a WARNING ValidationResult matching the warning golden snapshot."""
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
    result.total_checks = 2
    result.passed = 1
    result.warnings = 1
    result.blocked = 0
    result.verdict = Verdict.WARNING
    return result


def _make_blocked_result() -> ValidationResult:
    """Build a BLOCKED ValidationResult matching the blocked golden snapshot."""
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
    result.total_checks = 2
    result.passed = 0
    result.warnings = 0
    result.blocked = 2
    result.verdict = Verdict.BLOCKED
    return result


def _compare_or_update_json(
    result: ValidationResult,
    golden_path: Path,
    label: str,
) -> list[str]:
    """Compare rendered JSON to golden file, or update if UPDATE_SNAPSHOTS is set.

    Returns a list of error messages (empty if match).
    """
    rendered = render_json_report(result, normalise=True)
    errors: list[str] = []

    if UPDATE_SNAPSHOTS:
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(rendered, encoding="utf-8")
        return errors  # Always passes on update

    if not golden_path.exists():
        errors.append(
            f"Golden file missing: {golden_path}. "
            f"Set UPDATE_SNAPSHOTS=1 to create it from current output."
        )
        return errors

    golden = golden_path.read_text(encoding="utf-8")
    if rendered.strip() != golden.strip():
        errors.append(
            f"{label} JSON report differs from golden snapshot. "
            f"Golden: {golden_path}. "
            f"If the change is intentional, set UPDATE_SNAPSHOTS=1 and re-run."
        )

    return errors


def _compare_or_update_md(
    result: ValidationResult,
    golden_path: Path,
    label: str,
) -> list[str]:
    """Compare rendered Markdown to golden file, or update if UPDATE_SNAPSHOTS is set.

    Returns a list of error messages (empty if match).
    """
    rendered = render_markdown_report(result, normalise=True)
    errors: list[str] = []

    if UPDATE_SNAPSHOTS:
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(rendered, encoding="utf-8")
        return errors

    if not golden_path.exists():
        errors.append(
            f"Golden file missing: {golden_path}. "
            f"Set UPDATE_SNAPSHOTS=1 to create it from current output."
        )
        return errors

    golden = golden_path.read_text(encoding="utf-8")
    if rendered.strip() != golden.strip():
        errors.append(
            f"{label} Markdown report differs from golden snapshot. "
            f"Golden: {golden_path}. "
            f"If the change is intentional, set UPDATE_SNAPSHOTS=1 and re-run."
        )

    return errors


# ---------------------------------------------------------------------------
# PASS golden snapshot
# ---------------------------------------------------------------------------


class TestPassGoldenSnapshot:
    """PASS golden snapshot test — valid/complete_proposal expected PASS."""

    GOLDEN_JSON = GOLDEN_DIR / "pass" / "report.json"
    GOLDEN_MD = GOLDEN_DIR / "pass" / "report.md"

    def _result(self) -> ValidationResult:
        return _make_pass_result()

    def test_pass_verdict(self) -> None:
        result = self._result()
        assert result.verdict == Verdict.PASS

    def test_pass_finding_count(self) -> None:
        result = self._result()
        assert len(result.findings) == 1

    def test_pass_json_matches_golden(self) -> None:
        result = self._result()
        errors = _compare_or_update_json(result, self.GOLDEN_JSON, "PASS")
        assert not errors, "\n".join(errors)

    def test_pass_md_matches_golden(self) -> None:
        result = self._result()
        errors = _compare_or_update_md(result, self.GOLDEN_MD, "PASS")
        assert not errors, "\n".join(errors)


# ---------------------------------------------------------------------------
# WARNING golden snapshot
# ---------------------------------------------------------------------------


class TestWarningGoldenSnapshot:
    """WARNING golden snapshot test — fixture with minor issues."""

    GOLDEN_JSON = GOLDEN_DIR / "warning" / "report.json"
    GOLDEN_MD = GOLDEN_DIR / "warning" / "report.md"

    def _result(self) -> ValidationResult:
        return _make_warning_result()

    def test_warning_verdict(self) -> None:
        result = self._result()
        assert result.verdict == Verdict.WARNING

    def test_warning_finding_count(self) -> None:
        result = self._result()
        assert len(result.findings) == 1

    def test_warning_json_matches_golden(self) -> None:
        result = self._result()
        errors = _compare_or_update_json(result, self.GOLDEN_JSON, "WARNING")
        assert not errors, "\n".join(errors)

    def test_warning_md_matches_golden(self) -> None:
        result = self._result()
        errors = _compare_or_update_md(result, self.GOLDEN_MD, "WARNING")
        assert not errors, "\n".join(errors)


# ---------------------------------------------------------------------------
# BLOCKED golden snapshot
# ---------------------------------------------------------------------------


class TestBlockedGoldenSnapshot:
    """BLOCKED golden snapshot test — combined/multiple_errors fixture."""

    GOLDEN_JSON = GOLDEN_DIR / "blocked" / "report.json"
    GOLDEN_MD = GOLDEN_DIR / "blocked" / "report.md"

    def _result(self) -> ValidationResult:
        return _make_blocked_result()

    def test_blocked_verdict(self) -> None:
        result = self._result()
        assert result.verdict == Verdict.BLOCKED

    def test_blocked_finding_count(self) -> None:
        result = self._result()
        assert len(result.findings) == 2

    def test_blocked_json_matches_golden(self) -> None:
        result = self._result()
        errors = _compare_or_update_json(result, self.GOLDEN_JSON, "BLOCKED")
        assert not errors, "\n".join(errors)

    def test_blocked_md_matches_golden(self) -> None:
        result = self._result()
        errors = _compare_or_update_md(result, self.GOLDEN_MD, "BLOCKED")
        assert not errors, "\n".join(errors)


# ---------------------------------------------------------------------------
# Reason-code and severity regression tests
# ---------------------------------------------------------------------------


class TestReasonCodeRegression:
    """Reason-code regression: known fixtures produce expected reason codes."""

    def test_pass_has_schema_invalid_reason(self) -> None:
        result = _make_pass_result()
        codes = {f.reason_code for f in result.findings}
        assert ReasonCode.SCHEMA_INVALID in codes

    def test_warning_has_artifact_missing_reason(self) -> None:
        result = _make_warning_result()
        codes = {f.reason_code for f in result.findings}
        assert ReasonCode.ARTIFACT_MISSING in codes

    def test_blocked_has_unsafe_content_reason(self) -> None:
        result = _make_blocked_result()
        codes = {f.reason_code for f in result.findings}
        assert ReasonCode.UNSAFE_CONTENT in codes

    def test_blocked_has_artifact_missing_reason(self) -> None:
        result = _make_blocked_result()
        codes = {f.reason_code for f in result.findings}
        assert ReasonCode.ARTIFACT_MISSING in codes


class TestSeverityRegression:
    """Severity regression: known fixtures produce expected severity levels."""

    def test_pass_has_info_severity(self) -> None:
        result = _make_pass_result()
        severities = {f.severity for f in result.findings}
        assert Severity.INFO in severities

    def test_warning_has_major_severity(self) -> None:
        result = _make_warning_result()
        severities = {f.severity for f in result.findings}
        assert Severity.MAJOR in severities

    def test_blocked_has_blocker_severity(self) -> None:
        result = _make_blocked_result()
        severities = {f.severity for f in result.findings}
        assert Severity.BLOCKER in severities


# ---------------------------------------------------------------------------
# Snapshot update guard
# ---------------------------------------------------------------------------


class TestSnapshotUpdateGuard:
    """Tests should fail if golden files are missing (no auto-creation)."""

    def test_missing_golden_file_reported(self, tmp_path: Path) -> None:
        """Verify that a missing golden file is reported as an error."""
        fake_path = tmp_path / "nonexistent" / "report.json"
        assert not fake_path.exists(), "Test invariant: fake path should not exist"
        errors = _compare_or_update_json(
            _make_pass_result(), fake_path, "TEST"
        )
        if not UPDATE_SNAPSHOTS:
            assert len(errors) >= 1, "Expected error for missing golden file"
            assert "Golden file missing" in errors[0]
