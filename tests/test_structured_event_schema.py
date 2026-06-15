from __future__ import annotations

from datetime import datetime

from orchestrator.scripts.structured_event import (
    VALID_SEVERITIES,
    build_event,
    generate_correlation_id,
    validate_event,
)


class TestStructuredEventSchema:
    """Verify the structured event schema contract."""

    def test_build_event_has_required_fields(self) -> None:
        event = build_event(component="test_pipeline", event_type="signal_cycle")
        assert event["schema_version"] == "1.0"
        assert event["component"] == "test_pipeline"
        assert event["event_type"] == "signal_cycle"
        assert event["severity"] == "info"
        assert "correlation_id" in event
        assert "timestamp_utc" in event
        assert "message" in event

    def test_timestamp_is_valid_iso8601(self) -> None:
        event = build_event("test", "test_event")
        parsed = datetime.fromisoformat(event["timestamp_utc"])
        assert parsed.tzinfo is not None

    def test_validate_passes_for_valid_event(self) -> None:
        event = build_event("pipeline", "riskguard_verdict", severity="warning", message="test")
        errors = validate_event(event)
        assert errors == []

    def test_validate_fails_without_required_fields(self) -> None:
        errors = validate_event({"bad": "data"})
        assert len(errors) >= 1
        assert any("missing required" in e for e in errors)

    def test_validate_rejects_invalid_severity(self) -> None:
        event = build_event("test", "test", severity="INVALID")
        errors = validate_event(event)
        assert any("invalid severity" in e for e in errors)

    def test_validate_rejects_invalid_timestamp(self) -> None:
        event = build_event("test", "test")
        event["timestamp_utc"] = "not-a-date"
        errors = validate_event(event)
        assert any("invalid timestamp" in e for e in errors)

    def test_correlation_id_present_in_valid_event(self) -> None:
        event = build_event("pipeline", "cycle")
        _errors = validate_event(event)
        # Missing correlation_id is a warning, not hard error in validate
        assert "correlation_id" in event

    def test_generate_correlation_id_returns_string(self) -> None:
        cid = generate_correlation_id()
        assert isinstance(cid, str)
        assert len(cid) > 10
        assert "-" in cid

    def test_metadata_is_optional(self) -> None:
        event = build_event("test", "test")
        assert "metadata" not in event or event["metadata"] is None

    def test_custom_severity_accepted(self) -> None:
        for sev in VALID_SEVERITIES:
            event = build_event("test", "test", severity=sev)
            errors = validate_event(event)
            assert errors == [], f"severity {sev!r} should be valid"


class TestSensitiveKeyRedaction:
    """Verify the schema detects sensitive keys in metadata."""

    def test_password_key_detected(self) -> None:
        event = _event_with_metadata({"password": "super-secret"})
        errors = validate_event(event)
        assert any("sensitive key" in e for e in errors)

    def test_api_key_detected(self) -> None:
        event = _event_with_metadata({"api_key": "sk-1234"})
        errors = validate_event(event)
        assert any("sensitive key" in e for e in errors)

    def test_token_key_detected(self) -> None:
        event = _event_with_metadata({"token": "ghp_abc123"})
        errors = validate_event(event)
        assert any("sensitive key" in e for e in errors)

    def test_safe_metadata_passes(self) -> None:
        event = _event_with_metadata({"pair": "BTC/USDT", "confidence": 0.85})
        errors = validate_event(event)
        assert errors == []

    def test_nested_sensitive_key_detected(self) -> None:
        event = _event_with_metadata({"exchange": {"secret": "s3cr3t"}})
        errors = validate_event(event)
        assert any("sensitive key" in e for e in errors)

    def test_no_false_positive_on_safe_field(self) -> None:
        event = _event_with_metadata({"condition": "EMA50 > EMA200"})
        errors = validate_event(event)
        assert errors == []


def _event_with_metadata(metadata: dict) -> dict:
    return build_event(
        component="test",
        event_type="test",
        severity="info",
        message="metadata test",
        metadata=metadata,
    )
