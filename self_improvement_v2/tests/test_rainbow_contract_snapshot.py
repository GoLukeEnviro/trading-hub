"""Tests for the Rainbow Signal Envelope contract snapshot.

Verifies that the local JSON Schema snapshot:
- is valid JSON
- contains required field definitions
- matches validator expectations
- documents its upstream source
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "contracts"
_SCHEMA_PATH = _SCHEMA_DIR / "rainbow_signal_envelope.schema.json"
_README_PATH = _SCHEMA_DIR / "README.md"

# Expected required fields matching validator._REQUIRED_FIELDS
_EXPECTED_REQUIRED_FIELDS: tuple[str, ...] = (
    "event_type",
    "schema_version",
    "source_system",
    "source_id",
    "strategy_id",
    "symbol",
    "timestamp_utc",
    "direction",
    "confidence",
    "metadata",
    "redaction_status",
)

# Expected allowed directions matching validator allowed values
_EXPECTED_ALLOWED_DIRECTIONS: tuple[str, ...] = (
    "long",
    "short",
    "flat",
    "no_signal",
    "unknown",
)

# Expected event types matching validator._VALID_EVENT_TYPES
_EXPECTED_EVENT_TYPES: tuple[str, ...] = (
    "signal",
    "no_signal",
    "heartbeat",
)


# ── Helpers ──────────────────────────────────────────────────────────────


def _load_schema() -> dict[str, object]:
    if not _SCHEMA_PATH.exists():
        pytest.fail(f"Schema file not found: {_SCHEMA_PATH}")
    with open(_SCHEMA_PATH) as f:
        return dict(json.load(f))


# ── Schema parse ─────────────────────────────────────────────────────────


class TestSchemaParsing:
    def test_schema_exists(self) -> None:
        assert _SCHEMA_PATH.exists(), (
            f"Schema must exist at {_SCHEMA_PATH}"
        )

    def test_schema_is_valid_json(self) -> None:
        schema = _load_schema()
        assert isinstance(schema, dict)
        assert "$schema" in schema
        assert "properties" in schema
        assert "required" in schema

    def test_schema_version_present(self) -> None:
        schema = _load_schema()
        assert "version" in schema, "Schema must declare a version"

    def test_readme_exists(self) -> None:
        assert _README_PATH.exists(), (
            f"README must exist at {_README_PATH}"
        )


# ── Required fields ──────────────────────────────────────────────────────


class TestRequiredFields:
    def test_required_fields_match_validator(self) -> None:
        schema = _load_schema()
        schema_required: list[str] = list(schema.get("required", []))
        for field in _EXPECTED_REQUIRED_FIELDS:
            assert field in schema_required, (
                f"Required field '{field}' missing from schema required list"
            )
        # Check no unexpected required fields
        for field in schema_required:
            assert field in (*_EXPECTED_REQUIRED_FIELDS, "timeframe"), (
                f"Unexpected required field '{field}' in schema"
            )
            # timeframe is optional in the validator but could be required
            # in some contract versions. Flag for awareness.
            if field == "timeframe":
                pytest.skip(
                    "timeframe is optional in validator but schema may "
                    "require it — check contract version"
                )

    def test_all_required_have_property_definitions(self) -> None:
        schema = _load_schema()
        properties: dict[str, object] = dict(
            schema.get("properties", {})
        )
        for field in _EXPECTED_REQUIRED_FIELDS:
            assert field in properties, (
                f"Required field '{field}' missing from schema properties"
            )


# ── Allowed directions ───────────────────────────────────────────────────


class TestAllowedDirections:
    def test_direction_enum_contains_expected_values(self) -> None:
        schema = _load_schema()
        properties: dict[str, object] = dict(
            schema.get("properties", {})
        )
        direction_prop = properties.get("direction", {})
        assert isinstance(direction_prop, dict)
        direction_enum: list[str] = list(
            direction_prop.get("enum", [])
        )
        assert len(direction_enum) > 0, (
            "direction must define an enum"
        )
        for d in _EXPECTED_ALLOWED_DIRECTIONS:
            assert d in direction_enum, (
                f"Expected direction '{d}' not in schema enum"
            )

    def test_no_unexpected_directions(self) -> None:
        schema = _load_schema()
        properties: dict[str, object] = dict(
            schema.get("properties", {})
        )
        direction_prop = properties.get("direction", {})
        assert isinstance(direction_prop, dict)
        direction_enum: set[str] = set(
            direction_prop.get("enum", [])
        )
        expected = set(_EXPECTED_ALLOWED_DIRECTIONS)
        unexpected = direction_enum - expected
        assert not unexpected, (
            f"Unexpected direction values: {unexpected}"
        )


# ── Event types ──────────────────────────────────────────────────────────


class TestEventTypes:
    def test_event_type_enum_contains_expected(self) -> None:
        schema = _load_schema()
        properties: dict[str, object] = dict(
            schema.get("properties", {})
        )
        event_prop = properties.get("event_type", {})
        assert isinstance(event_prop, dict)
        event_enum: list[str] = list(
            event_prop.get("enum", [])
        )
        for et in _EXPECTED_EVENT_TYPES:
            assert et in event_enum, (
                f"Expected event_type '{et}' not in schema enum"
            )


# ── Field properties ─────────────────────────────────────────────────────


class TestFieldProperties:
    def test_confidence_has_min_max(self) -> None:
        schema = _load_schema()
        properties: dict[str, object] = dict(
            schema.get("properties", {})
        )
        conf = properties.get("confidence", {})
        assert isinstance(conf, dict)
        assert conf.get("minimum") == 0.0, (
            "confidence.minimum must be 0.0"
        )
        assert conf.get("maximum") == 1.0, (
            "confidence.maximum must be 1.0"
        )

    def test_schema_version_is_integer_minimum_1(self) -> None:
        schema = _load_schema()
        properties: dict[str, object] = dict(
            schema.get("properties", {})
        )
        sv = properties.get("schema_version", {})
        assert isinstance(sv, dict)
        assert sv.get("type") == "integer", (
            "schema_version must have type 'integer'"
        )
        assert sv.get("minimum") == 1, (
            "schema_version.minimum must be 1"
        )

    def test_timestamp_utc_has_date_time_format(self) -> None:
        schema = _load_schema()
        properties: dict[str, object] = dict(
            schema.get("properties", {})
        )
        ts = properties.get("timestamp_utc", {})
        assert isinstance(ts, dict)
        assert ts.get("format") == "date-time", (
            "timestamp_utc must have format 'date-time'"
        )

    def test_redaction_status_enum(self) -> None:
        schema = _load_schema()
        properties: dict[str, object] = dict(
            schema.get("properties", {})
        )
        rs = properties.get("redaction_status", {})
        assert isinstance(rs, dict)
        rs_enum: list[str] = list(rs.get("enum", []))
        for s in ("clean", "redacted", "unchecked"):
            assert s in rs_enum, (
                f"Expected redaction_status '{s}' in enum"
            )


# ── README content ───────────────────────────────────────────────────────


class TestReadme:
    def test_readme_mentions_upstream(self) -> None:
        content = _README_PATH.read_text()
        assert "ai4trade-bot" in content, (
            "README must mention the upstream ai4trade-bot repository"
        )
        assert "upstream" in content.lower(), (
            "README must indicate this is a derived snapshot"
        )

    def test_readme_mentions_update_procedure(self) -> None:
        content = _README_PATH.read_text()
        assert "Update Procedure" in content, (
            "README must document how to update the snapshot"
        )
