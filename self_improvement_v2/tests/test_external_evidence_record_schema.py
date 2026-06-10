"""Tests for the external evidence record schema (#102).

Verifies:
- schema is valid JSON
- required fields are defined
- fixture samples parse against schema
- no secrets present
"""

from __future__ import annotations

import json
from pathlib import Path

_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "evidence"
    / "external_evidence_record.schema.json"
)
_FIXTURE_DIR = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "external-evidence-records"
)


def _load_schema() -> dict[str, object]:
    with open(_SCHEMA_PATH) as f:
        return dict(json.load(f))


class TestSchemaParsing:
    def test_schema_exists(self) -> None:
        assert _SCHEMA_PATH.exists()

    def test_schema_is_valid_json(self) -> None:
        schema = _load_schema()
        assert "$schema" in schema
        assert "properties" in schema
        assert "required" in schema

    def test_required_fields_defined(self) -> None:
        schema = _load_schema()
        required = list(schema.get("required", []))
        expected = [
            "evidence_schema_version",
            "provider_id",
            "event_type",
            "validator_verdict",
            "is_actionable",
            "timestamp_utc",
            "observed_at_utc",
            "redaction_status",
        ]
        for field in expected:
            assert field in required, (
                f"Required field '{field}' missing"
            )

    def test_event_type_enum(self) -> None:
        schema = _load_schema()
        props = dict(schema.get("properties", {}))
        et = props.get("event_type", {})
        assert isinstance(et, dict)
        et_enum = list(et.get("enum", []))
        expected_types = [
            "signal_validated",
            "signal_rejected",
            "signal_stale",
            "heartbeat_observed",
            "no_signal_observed",
            "fixture_validation_summary",
        ]
        for et_val in expected_types:
            assert et_val in et_enum


class TestFixtureSamples:
    def test_fixture_dir_exists(self) -> None:
        assert _FIXTURE_DIR.exists()

    def test_validated_signal_parses(self) -> None:
        path = _FIXTURE_DIR / "rainbow_validated_signal.json"
        assert path.exists()
        with open(path) as f:
            data = dict(json.load(f))
        assert data.get("event_type") == "signal_validated"
        assert data.get("validator_verdict") == "pass"
        assert data.get("is_actionable") is True

    def test_rejected_signal_parses(self) -> None:
        path = _FIXTURE_DIR / "rainbow_rejected_signal.json"
        assert path.exists()
        with open(path) as f:
            data = dict(json.load(f))
        assert data.get("event_type") == "signal_rejected"
        assert data.get("validator_verdict") == "fail"
        assert data.get("is_actionable") is False

    def test_fixtures_have_required_fields(self) -> None:
        schema = _load_schema()
        required = set(schema.get("required", []))
        for fixture_path in _FIXTURE_DIR.glob("*.json"):
            with open(fixture_path) as f:
                data = dict(json.load(f))
            for field in required:
                assert field in data, (
                    f"{fixture_path.name} missing required field: "
                    f"{field}"
                )

    def test_no_credentials_in_fixtures(self) -> None:
        for fixture_path in _FIXTURE_DIR.glob("*.json"):
            text = fixture_path.read_text()
            assert "api_key" not in text
            assert "secret" not in text
            assert "token" not in text
