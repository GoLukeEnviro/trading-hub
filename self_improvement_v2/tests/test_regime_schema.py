"""Structural tests for the SI v2 canonical regime detector schema spec.

Verifies the spec document at docs/specs/si-v2-regime-detector-schema.md
contains all required sections, fields, labels, and contract rules.
"""

from __future__ import annotations

import re
import typing
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = PROJECT_ROOT.parent / "docs" / "specs" / "si-v2-regime-detector-schema.md"


class RequiredSpecContent:
    """Holds the required content expectations for the spec document."""

    REQUIRED_SECTIONS: typing.ClassVar[list[str]] = [
        "## 1. Regime Event Schema",
        "### 1.1 Canonical Regime Labels",
        "### 1.2 Schema Definition",
        "### 1.3 Pydantic Model",
        "### 1.4 Versioning Strategy",
        "## 2. Regime-to-Signal/Trade Attachment Rules",
        "### 2.1 Attachment to Signals",
        "### 2.2 Attachment to Trades",
        "### 2.3 Attachment to Decisions",
        "## 3. Unknown / Insufficient-Data Behavior",
        "### 3.1 Trigger Conditions",
        "### 3.2 UNKNOWN Emission Rules",
        "### 3.3 Recovery",
        "## 4. Versioning and Compatibility Rules",
        "### 4.1 Schema Version Lifecycle",
        "### 4.2 Forward Compatibility",
        "### 4.3 Backward Compatibility",
        "### 4.4 Model Version Rules",
        "## 5. Backward Compatibility with Existing Regime-Hybrid Strategy Attachment",
        "### 5.1 Existing v1 Labels → Canonical Mapping",
        "### 5.2 Weight Multiplier Mapping",
        "### 5.3 Integration Rule",
    ]

    REQUIRED_LABELS: typing.ClassVar[list[str]] = [
        "BULLISH",
        "BEARISH",
        "NEUTRAL",
        "UNKNOWN",
    ]

    REQUIRED_SCHEMA_FIELDS: typing.ClassVar[list[str]] = [
        "regime",
        "confidence",
        "timeframe",
        "data_source",
        "detected_at",
        "model_version",
        "schema_version",
    ]

    REQUIRED_TERMS: typing.ClassVar[list[str]] = [
        "confidence",
        "UTC",
        "versioning",
        "sufficient data",
        "insufficient data",
    ]


def _read_spec() -> str:
    """Read and return the spec document content."""
    assert SPEC_PATH.exists(), f"Spec file not found: {SPEC_PATH}"
    return SPEC_PATH.read_text()


class TestSpecExists:
    """Verify the spec document exists at the expected path."""

    def test_spec_file_exists(self) -> None:
        """The spec document must exist at the canonical path."""
        assert SPEC_PATH.exists(), (
            f"Expected spec at {SPEC_PATH}"
        )

    def test_spec_is_not_empty(self) -> None:
        """The spec document must contain meaningful content."""
        content = _read_spec()
        assert len(content.strip()) > 500, (
            "Spec document is too short or empty"
        )


class TestRequiredSections:
    """Verify all required sections are present in the spec document."""

    def test_all_required_sections_present(self) -> None:
        """Every heading in REQUIRED_SECTIONS must appear in the spec."""
        content = _read_spec()
        missing: list[str] = []
        for section in RequiredSpecContent.REQUIRED_SECTIONS:
            if section not in content:
                missing.append(section)
        assert len(missing) == 0, (
            "Missing required sections:\n" + "\n".join(missing)
        )


class TestRequiredLabels:
    """Verify all canonical regime labels are defined."""

    def test_all_canonical_labels_present(self) -> None:
        """Every canonical label must appear in the spec."""
        content = _read_spec()
        # Labels should appear in a table or as code literals
        missing: list[str] = []
        for label in RequiredSpecContent.REQUIRED_LABELS:
            # Look for backtick-quoted label (e.g. `BULLISH`)
            if f"`{label}`" not in content:
                missing.append(label)
        assert len(missing) == 0, (
            "Missing canonical regime labels:\n" + "\n".join(missing)
        )


class TestRequiredSchemaFields:
    """Verify all required schema fields are documented."""

    def test_all_required_fields_present(self) -> None:
        """Every field in REQUIRED_SCHEMA_FIELDS must appear in the spec."""
        content = _read_spec()
        missing: list[str] = []
        for field in RequiredSpecContent.REQUIRED_SCHEMA_FIELDS:
            # Look for backtick-quoted field name (e.g. `regime`)
            if f"`{field}`" not in content:
                missing.append(field)
        assert len(missing) == 0, (
            "Missing schema fields:\n" + "\n".join(missing)
        )


class TestBackwardCompatibility:
    """Verify backward compatibility rules are documented."""

    def test_v1_label_mapping_present(self) -> None:
        """The v1-to-canonical label mapping must be present."""
        content = _read_spec()
        v1_labels = [
            "strong_trend_up",
            "strong_trend_down",
            "weak_trend_up",
            "weak_trend_down",
            "ranging",
            "high_volatility",
            "choppy",
        ]
        missing: list[str] = []
        for label in v1_labels:
            if f"`{label}`" not in content:
                missing.append(label)
        assert len(missing) == 0, (
            "Missing v1 label mapping entries:\n" + "\n".join(missing)
        )


class TestUnknownBehavior:
    """Verify the UNKNOWN / insufficient-data behavior section."""

    def test_unknown_confidence_zero(self) -> None:
        """UNKNOWN events must specify confidence = 0.0."""
        content = _read_spec()
        assert "confidence = 0.0" in content or "confidence=0.0" in content, (
            "Spec must define UNKNOWN confidence as 0.0"
        )

    def test_insufficient_data_triggers(self) -> None:
        """The spec must list trigger conditions for UNKNOWN."""
        content = _read_spec()
        triggers = ["NaN", "missing", "insufficient"]
        found = [t for t in triggers if t.lower() in content.lower()]
        assert len(found) >= 2, (
            f"Expected at least 2 insufficient-data trigger terms, found: {found}"
        )

    def test_downstream_consumers_must_not_trade_on_unknown(self) -> None:
        """The spec must state that UNKNOWN regimes are not tradeable."""
        content = _read_spec()
        assert (
            "must not" in content.lower() and "trade" in content.lower()
        ), (
            "Spec must forbid trading on UNKNOWN regimes"
        )


class TestVersioning:
    """Verify versioning and compatibility rules are documented."""

    def test_schema_version_field(self) -> None:
        """The schema must include a schema_version field."""
        content = _read_spec()
        assert "schema_version" in content, (
            "Missing schema_version field documentation"
        )

    def test_model_version_field(self) -> None:
        """The schema must include a model_version field."""
        content = _read_spec()
        assert "model_version" in content, (
            "Missing model_version field documentation"
        )

    def test_semver_mention(self) -> None:
        """The spec must reference SemVer for model versioning."""
        content = _read_spec()
        assert "SemVer" in content, (
            "Spec must mention SemVer for model versioning"
        )


class TestIntegrationPoints:
    """Verify the spec references the known integration boundaries."""

    def test_shadowlock_referenced(self) -> None:
        """Shadowlock must be referenced as an integration target."""
        content = _read_spec()
        assert "Shadowlock" in content, (
            "Spec must reference Shadowlock integration"
        )

    def test_rainbow_referenced(self) -> None:
        """Rainbow / ai4trade must be referenced as an integration target."""
        content = _read_spec()
        assert "Rainbow" in content or "ai4trade" in content, (
            "Spec must reference Rainbow Intelligence Engine"
        )

    def test_regime_hybrid_strategy_referenced(self) -> None:
        """The regime-hybrid strategy must be referenced for backward compat."""
        content = _read_spec()
        assert "RegimeSwitchingHybrid" in content or "regime-hybrid" in content.lower(), (
            "Spec must reference the regime-hybrid strategy"
        )


class TestHardSafetyRules:
    """Verify the spec enforces the Phase 1 hard safety rules."""

    def test_no_live_trading_rule(self) -> None:
        """The spec must state no live trading decisions."""
        content = _read_spec()
        assert "no live trading" in content.lower(), (
            "Spec must state no live trading"
        )

    def test_no_automatic_weight_changes(self) -> None:
        """The spec must disallow automatic weight changes."""
        content = _read_spec()
        assert "no automatic weight" in content.lower(), (
            "Spec must forbid automatic weight changes"
        )


class TestPydanticReference:
    """Verify the Pydantic model reference is present and correct."""

    def test_pydantic_model_reference(self) -> None:
        """The spec must include a Pydantic model reference."""
        content = _read_spec()
        assert "RegimeEvent" in content, (
            "Spec must include RegimeEvent class reference"
        )
        assert "BaseModel" in content, (
            "Spec must reference Pydantic's BaseModel"
        )

    def test_pydantic_imports(self) -> None:
        """The Pydantic model must use __future__ annotations."""
        content = _read_spec()
        # Check within the code block
        code_blocks = re.findall(r"```python\n(.*?)```", content, re.DOTALL)
        combined = "\n".join(code_blocks)
        assert "from __future__ import annotations" in combined, (
            "The Pydantic model must use `from __future__ import annotations`"
        )
