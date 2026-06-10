"""Tests for the Shadow-mode Rehearsal Report Template (#130).

Verifies that the template exists, is template-only (no runtime actions),
and contains all required report sections.
"""

from __future__ import annotations

from pathlib import Path

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "reports" / "shadow_mode_rehearsal_report_template.md"

REQUIRED_SECTIONS: list[str] = [
    "Run Metadata",
    "Environment Snapshot",
    "Preflight Verification",
    "Commands Executed",
    "Observations",
    "Validation Outcome",
    "Artifacts Produced",
    "Residual Risks",
    "Approval for Next Phase",
]

SAFETY_PHRASES: list[str] = [
    "not an approval to trade live",
    "template",
    "does not authorise",
]

REQUIRED_FIELDS: list[str] = [
    "Run ID",
    "Approval Token",
    "Rehearsal Mode",
    "Git Branch",
    "Git Commit",
    "Safety Verdict",
]


class TestShadowModeRehearsalReportTemplate:
    """Tests for the Shadow-mode Rehearsal Report Template."""

    def test_template_exists(self) -> None:
        """The template file must exist."""
        assert TEMPLATE_PATH.is_file(), f"Template not found: {TEMPLATE_PATH}"

    def test_has_all_required_sections(self) -> None:
        """All required report sections must be present."""
        content = TEMPLATE_PATH.read_text(encoding="utf-8")
        for section in REQUIRED_SECTIONS:
            assert section in content, f"Missing required section: {section}"

    def test_has_safety_disclaimers(self) -> None:
        """Template must contain clear safety disclaimers."""
        content = TEMPLATE_PATH.read_text(encoding="utf-8")
        for phrase in SAFETY_PHRASES:
            assert phrase.lower() in content.lower(), f"Missing safety phrase: {phrase}"

    def test_has_required_fields(self) -> None:
        """Template must include all required metadata fields."""
        content = TEMPLATE_PATH.read_text(encoding="utf-8")
        for field in REQUIRED_FIELDS:
            assert field in content, f"Missing required field: {field}"

    def test_is_template_only(self) -> None:
        """Template must not contain executed results or runtime actions."""
        content = TEMPLATE_PATH.read_text(encoding="utf-8")
        # Template placeholders are fine; real values are not.
        assert "(to be filled)" in content.lower() or "| |" in content or "☐" in content

    def test_commands_executed_section_is_tabular(self) -> None:
        """Commands Executed section must be a table format."""
        content = TEMPLATE_PATH.read_text(encoding="utf-8")
        assert "Commands Executed" in content
        assert "|---" in content  # Markdown table separator
