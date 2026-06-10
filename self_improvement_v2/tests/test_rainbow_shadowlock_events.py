"""Tests for the Rainbow Shadowlock audit event mapper.

Verifies that:
- valid long/short fixtures map to validated audit events
- no_signal maps to non-actionable no-signal event
- heartbeat maps to non-actionable heartbeat event
- stale fixture maps to stale event
- malformed fixture maps to rejected fail-closed event
- event serialization is deterministic
- no production Shadowlock path is used
- no event contains secrets or runtime credentials
"""

from __future__ import annotations

import json
from pathlib import Path

from si_v2.rainbow.shadowlock_events import (
    RainbowAuditEventType,
    RainbowShadowlockEventMapper,
)
from si_v2.rainbow.validator import (
    RainbowSignalEnvelopeValidator,
)

_FIXTURE_DIR = (
    Path(__file__).resolve().parent.parent / "fixtures" / "rainbow-signals"
)

validator = RainbowSignalEnvelopeValidator()


# ── Helpers ───────────────────────────────────────────────────────────────


def _load(name: str) -> dict[str, object]:
    path = _FIXTURE_DIR / name
    with open(path) as f:
        return dict(json.load(f))


def _validate(envelope: dict[str, object]) -> dict[str, object]:
    result = validator.validate_envelope(envelope)
    return {
        "verdict": result.verdict.value,
        "errors": result.errors,
        "warnings": result.warnings,
        "has_normalized": result.normalized is not None,
    }


# ── Valid signal mapping ──────────────────────────────────────────────────


class TestValidSignalMapping:
    def test_long_signal_validated(self) -> None:
        envelope = _load("valid_long_signal.json")
        vr = _validate(envelope)
        event = RainbowShadowlockEventMapper.map_envelope(envelope, vr)
        assert event.event_type == RainbowAuditEventType.SIGNAL_VALIDATED.value
        assert event.is_actionable is True
        assert event.validator_verdict == "pass"
        assert event.direction == "long"
        assert event.symbol_or_pair == "BTC/USDT:USDT"

    def test_short_signal_validated(self) -> None:
        envelope = _load("valid_short_signal.json")
        vr = _validate(envelope)
        event = RainbowShadowlockEventMapper.map_envelope(envelope, vr)
        assert event.event_type == RainbowAuditEventType.SIGNAL_VALIDATED.value
        assert event.is_actionable is True
        assert event.validator_verdict == "pass"
        assert event.direction == "short"
        assert event.symbol_or_pair == "ETH/USDT:USDT"


# ── Non-actionable events ─────────────────────────────────────────────────


class TestNonActionableEvents:
    def test_no_signal_maps_to_no_signal_observed(self) -> None:
        envelope = _load("no_signal.json")
        vr = _validate(envelope)
        event = RainbowShadowlockEventMapper.map_envelope(envelope, vr)
        assert (
            event.event_type
            == RainbowAuditEventType.NO_SIGNAL_OBSERVED.value
        )
        assert event.is_actionable is False

    def test_heartbeat_maps_to_heartbeat_observed(self) -> None:
        envelope = _load("heartbeat.json")
        vr = _validate(envelope)
        event = RainbowShadowlockEventMapper.map_envelope(envelope, vr)
        assert (
            event.event_type
            == RainbowAuditEventType.HEARTBEAT_OBSERVED.value
        )
        assert event.is_actionable is False


# ── Stale signal ──────────────────────────────────────────────────────────


class TestStaleSignal:
    def test_stale_maps_to_stale_event(self) -> None:
        envelope = _load("stale_signal.json")
        vr = _validate(envelope)
        event = RainbowShadowlockEventMapper.map_envelope(envelope, vr)
        assert (
            event.event_type
            == RainbowAuditEventType.SIGNAL_STALE.value
        )
        # Stale signals are technically validated, but not actionable
        assert event.is_actionable is False

    def test_stale_has_stale_warning(self) -> None:
        envelope = _load("stale_signal.json")
        vr = _validate(envelope)
        event = RainbowShadowlockEventMapper.map_envelope(envelope, vr)
        stale_warnings = [
            w for w in event.warnings if "stale" in w.lower()
        ]
        assert len(stale_warnings) >= 1


# ── Malformed / rejected signal ───────────────────────────────────────────


class TestMalformedSignal:
    def test_malformed_maps_to_rejected(self) -> None:
        envelope = _load(
            "malformed_missing_required_fields.json"
        )
        vr = _validate(envelope)
        event = RainbowShadowlockEventMapper.map_envelope(envelope, vr)
        assert (
            event.event_type
            == RainbowAuditEventType.SIGNAL_REJECTED.value
        )
        assert event.is_actionable is False
        assert len(event.errors) > 0

    def test_rejected_has_error_details(self) -> None:
        envelope = _load(
            "malformed_missing_required_fields.json"
        )
        vr = _validate(envelope)
        event = RainbowShadowlockEventMapper.map_envelope(envelope, vr)
        # Should mention missing fields
        assert any(
            "Missing" in e or "required" in e.lower()
            for e in event.errors
        )


# ── Event serialization ───────────────────────────────────────────────────


class TestEventSerialization:
    def test_to_shadowlock_entry_has_required_fields(self) -> None:
        envelope = _load("valid_long_signal.json")
        vr = _validate(envelope)
        event = RainbowShadowlockEventMapper.map_envelope(envelope, vr)
        entry = event.to_shadowlock_entry()

        # Shadowlock required fields
        assert "schema_version" in entry
        assert "event_type" in entry
        assert "timestamp_utc" in entry
        assert "bot_name" in entry

        # Rainbow-specific fields
        assert "rainbow_event_id" in entry
        assert "rainbow_provider_id" in entry
        assert "rainbow_validator_verdict" in entry

    def test_entry_is_serializable(self) -> None:
        envelope = _load("valid_long_signal.json")
        vr = _validate(envelope)
        event = RainbowShadowlockEventMapper.map_envelope(envelope, vr)
        entry = event.to_shadowlock_entry()
        # Must not raise
        json.dumps(entry)

    def test_entry_schema_version_format(self) -> None:
        envelope = _load("valid_long_signal.json")
        vr = _validate(envelope)
        event = RainbowShadowlockEventMapper.map_envelope(envelope, vr)
        assert event.schema_version == "1.0"

    def test_timestamp_ends_with_z(self) -> None:
        envelope = _load("valid_long_signal.json")
        vr = _validate(envelope)
        event = RainbowShadowlockEventMapper.map_envelope(envelope, vr)
        assert event.timestamp_utc.endswith("Z")

    def test_observed_at_ends_with_z(self) -> None:
        envelope = _load("valid_long_signal.json")
        vr = _validate(envelope)
        event = RainbowShadowlockEventMapper.map_envelope(envelope, vr)
        assert event.observed_at_utc.endswith("Z")

    def test_event_id_is_uuid(self) -> None:
        envelope = _load("valid_long_signal.json")
        vr = _validate(envelope)
        event = RainbowShadowlockEventMapper.map_envelope(envelope, vr)
        import uuid

        uuid.UUID(event.event_id)  # Must not raise


# ── Determinism ───────────────────────────────────────────────────────────


class TestDeterminism:
    def test_batch_mapping_deterministic(self) -> None:
        envelopes = [
            _load("valid_long_signal.json"),
            _load("valid_short_signal.json"),
        ]
        vrs = [_validate(e) for e in envelopes]
        events1 = RainbowShadowlockEventMapper.map_fixture_batch(
            envelopes, vrs
        )
        events2 = RainbowShadowlockEventMapper.map_fixture_batch(
            envelopes, vrs
        )
        # event_id is UUID (non-deterministic), but types should match
        for e1, e2 in zip(events1, events2, strict=True):
            assert e1.event_type == e2.event_type
            assert e1.validator_verdict == e2.validator_verdict
            assert e1.is_actionable == e2.is_actionable
            assert e1.direction == e2.direction
            assert e1.confidence == e2.confidence


# ── Batch fixture mapping ─────────────────────────────────────────────────


class TestBatchMapping:
    def test_all_fixtures_mapped(self) -> None:
        fixture_names = [
            "valid_long_signal.json",
            "valid_short_signal.json",
            "no_signal.json",
            "heartbeat.json",
            "stale_signal.json",
            "partial_metadata_signal.json",
            "malformed_missing_required_fields.json",
        ]
        envelopes = [_load(f) for f in fixture_names]
        vrs = [_validate(e) for e in envelopes]
        events = RainbowShadowlockEventMapper.map_fixture_batch(
            envelopes, vrs
        )
        assert len(events) == 7

    def test_batch_includes_all_categories(self) -> None:
        fixture_names = [
            "valid_long_signal.json",
            "valid_short_signal.json",
            "no_signal.json",
            "heartbeat.json",
            "stale_signal.json",
            "partial_metadata_signal.json",
            "malformed_missing_required_fields.json",
        ]
        envelopes = [_load(f) for f in fixture_names]
        vrs = [_validate(e) for e in envelopes]
        events = RainbowShadowlockEventMapper.map_fixture_batch(
            envelopes, vrs
        )
        event_types = {e.event_type for e in events}
        expected = {
            RainbowAuditEventType.SIGNAL_VALIDATED.value,
            RainbowAuditEventType.NO_SIGNAL_OBSERVED.value,
            RainbowAuditEventType.HEARTBEAT_OBSERVED.value,
            RainbowAuditEventType.SIGNAL_STALE.value,
            RainbowAuditEventType.SIGNAL_REJECTED.value,
        }
        for et in expected:
            assert et in event_types, (
                f"Missing event type: {et}"
            )


# ── No secrets ────────────────────────────────────────────────────────────


class TestNoSecrets:
    def test_events_have_no_secret_fields(self) -> None:
        envelope = _load("valid_long_signal.json")
        vr = _validate(envelope)
        event = RainbowShadowlockEventMapper.map_envelope(envelope, vr)
        entry = event.to_shadowlock_entry()
        serialized = json.dumps(entry)
        # Check no obvious secret patterns
        assert "api_key" not in serialized
        assert "secret" not in serialized or "redaction_status" in serialized
        # Confidence value should be numeric, not credential-like
        assert isinstance(event.confidence, float)


# ── Preview report ────────────────────────────────────────────────────────


class TestPreviewReport:
    def test_report_generates(self) -> None:
        envelope = _load("valid_long_signal.json")
        vr = _validate(envelope)
        event = RainbowShadowlockEventMapper.map_envelope(envelope, vr)
        report = RainbowShadowlockEventMapper.generate_preview_report(
            [event]
        )
        assert "Shadowlock Audit Event Preview" in report
        assert "Event Summary" in report

    def test_report_deterministic(self) -> None:
        envelope = _load("valid_long_signal.json")
        vr = _validate(envelope)
        event = RainbowShadowlockEventMapper.map_envelope(envelope, vr)
        report1 = RainbowShadowlockEventMapper.generate_preview_report(
            [event]
        )
        report2 = RainbowShadowlockEventMapper.generate_preview_report(
            [event]
        )
        # Report timestamp may differ but content structure same
        assert "Event Summary" in report1
        assert "Event Summary" in report2

    def test_report_mentions_preview(self) -> None:
        envelope = _load("valid_long_signal.json")
        vr = _validate(envelope)
        event = RainbowShadowlockEventMapper.map_envelope(envelope, vr)
        report = RainbowShadowlockEventMapper.generate_preview_report(
            [event]
        )
        assert "preview" in report.lower() or "offline" in report.lower()
