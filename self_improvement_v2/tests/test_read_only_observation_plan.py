"""Tests for #139: Read-only observation plan.

Verifies the observation plan exists, defines read-only boundaries,
marks write-capable adapters as disabled-by-default, lists forbidden
sources, and contains a no-automatic-action rule.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import ClassVar

OBSERVATION_PLAN_PATH = Path(__file__).resolve().parent.parent / "rehearsal" / "read_only_observation_plan.md"


# ──────────────────────────────────────────────
# Artifact existence
# ──────────────────────────────────────────────


class TestObservationPlanArtifactExists:
    """The observation plan markdown must exist."""

    def test_plan_file_exists(self) -> None:
        assert OBSERVATION_PLAN_PATH.is_file(), (
            f"Observation plan not found: {OBSERVATION_PLAN_PATH}"
        )

    def test_plan_file_nonempty(self) -> None:
        text = OBSERVATION_PLAN_PATH.read_text(encoding="utf-8")
        assert len(text) > 500, "Observation plan file is too short"


# ──────────────────────────────────────────────
# Required sections
# ──────────────────────────────────────────────


class TestObservationPlanRequiredSections:
    """The observation plan must contain specific sections."""

    REQUIRED_HEADERS: ClassVar[list[str]] = [
        "Purpose",
        "Observation Sources",
        "Observation Rules",
        "Reporting",
        "Disabled-by-Default Adapters",
        "No-Automatic-Action Rule",
    ]

    def test_all_required_headers_present(self) -> None:
        text = OBSERVATION_PLAN_PATH.read_text(encoding="utf-8")
        for header in self.REQUIRED_HEADERS:
            assert re.search(rf"## \d+\.\s*{re.escape(header)}\s*$", text, re.MULTILINE), (
                f"Required header '{header}' not found in observation plan"
            )


# ──────────────────────────────────────────────
# Read-only boundaries
# ──────────────────────────────────────────────


class TestObservationPlanReadOnlyBoundaries:
    """The plan must enforce read-only observation."""

    def test_read_only_stated_in_purpose(self) -> None:
        text = OBSERVATION_PLAN_PATH.read_text(encoding="utf-8")
        assert "Read-Only" in text or "read-only" in text.lower(), (
            "Missing read-only designation"
        )

    def test_observation_rules_include_read_only(self) -> None:
        text = OBSERVATION_PLAN_PATH.read_text(encoding="utf-8")
        assert "read-only" in text.lower(), (
            "Missing read-only constraint in observation rules"
        )

    def test_no_state_modification_stated(self) -> None:
        text = OBSERVATION_PLAN_PATH.read_text(encoding="utf-8")
        assert "modify" in text.lower(), (
            "Missing modify prohibition in observation rules"
        )


# ──────────────────────────────────────────────
# Observation sources
# ──────────────────────────────────────────────


class TestObservationPlanSources:
    """The plan must categorise observation sources."""

    def test_read_only_sources_section_exists(self) -> None:
        text = OBSERVATION_PLAN_PATH.read_text(encoding="utf-8")
        assert "Read-Only Sources" in text, "Missing Read-Only Sources section"

    def test_conditional_sources_section_exists(self) -> None:
        text = OBSERVATION_PLAN_PATH.read_text(encoding="utf-8")
        assert "Conditional Sources" in text, "Missing Conditional Sources section"

    def test_forbidden_sources_section_exists(self) -> None:
        text = OBSERVATION_PLAN_PATH.read_text(encoding="utf-8")
        assert "Forbidden Sources" in text, "Missing Forbidden Sources section"


# ──────────────────────────────────────────────
# Forbidden sources
# ──────────────────────────────────────────────


class TestObservationPlanForbiddenSources:
    """The plan must list forbidden observation sources."""

    FORBIDDEN_SOURCES: ClassVar[list[str]] = [
        "Exchange",
        "Telegram",
        "live",
        "credential",
        "secret",
    ]

    def test_forbidden_sources_mentioned(self) -> None:
        text = OBSERVATION_PLAN_PATH.read_text(encoding="utf-8")
        for source in self.FORBIDDEN_SOURCES:
            assert source.lower() in text.lower(), (
                f"Forbidden source '{source}' not mentioned"
            )


# ──────────────────────────────────────────────
# Disabled-by-default adapters
# ──────────────────────────────────────────────


class TestObservationPlanDisabledAdapters:
    """Write-capable adapters must be disabled by default."""

    def test_disabled_by_default_section_exists(self) -> None:
        text = OBSERVATION_PLAN_PATH.read_text(encoding="utf-8")
        assert "Disabled-by-Default" in text, (
            "Missing Disabled-by-Default section"
        )

    def test_real_docker_adapter_mentioned(self) -> None:
        text = OBSERVATION_PLAN_PATH.read_text(encoding="utf-8")
        assert "RealDockerAdapter" in text, (
            "Missing RealDockerAdapter reference"
        )

    def test_real_freqtrade_adapter_mentioned(self) -> None:
        text = OBSERVATION_PLAN_PATH.read_text(encoding="utf-8")
        assert "RealFreqtradeAdapter" in text, (
            "Missing RealFreqtradeAdapter reference"
        )

    def test_disabled_default_stated(self) -> None:
        text = OBSERVATION_PLAN_PATH.read_text(encoding="utf-8")
        assert "Disabled" in text, "Missing disabled default state"


# ──────────────────────────────────────────────
# No-automatic-action rule
# ──────────────────────────────────────────────


class TestObservationPlanNoAutoAction:
    """The plan must contain a no-automatic-action rule."""

    def test_no_automatic_action_section_exists(self) -> None:
        text = OBSERVATION_PLAN_PATH.read_text(encoding="utf-8")
        assert "No-Automatic-Action" in text or "No Automatic Action" in text, (
            "Missing No-Automatic-Action section"
        )

    def test_no_automatic_action_stated(self) -> None:
        text = OBSERVATION_PLAN_PATH.read_text(encoding="utf-8")
        assert "never trigger automatic" in text.lower() or (
            "no automatic" in text.lower()
        ), "Missing no-automatic-action language"


# ──────────────────────────────────────────────
# Reporting format
# ──────────────────────────────────────────────


class TestObservationPlanReporting:
    """The plan must define a structured observation reporting format."""

    REQUIRED_REPORT_FIELDS: ClassVar[list[str]] = [
        "observation_id",
        "source",
        "observed_at",
        "observed_by",
        "observation",
    ]

    def test_reporting_section_exists(self) -> None:
        text = OBSERVATION_PLAN_PATH.read_text(encoding="utf-8")
        assert "Reporting" in text, "Missing Reporting section"

    def test_required_report_fields_mentioned(self) -> None:
        text = OBSERVATION_PLAN_PATH.read_text(encoding="utf-8")
        for field in self.REQUIRED_REPORT_FIELDS:
            assert field in text, f"Required report field '{field}' not mentioned"
