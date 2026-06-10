"""Fixture-based tests for RainbowSignalEnvelopeValidator.

Each test loads a JSON fixture from ``tests/fixtures/rainbow-signals/``
and verifies the validator produces the expected verdict.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from si_v2.rainbow.validator import (
    RainbowSignalEnvelopeValidator,
    ValidationVerdict,
)

_FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "rainbow-signals"

validator = RainbowSignalEnvelopeValidator()


def _load(name: str) -> dict[str, object]:
    path = _FIXTURE_DIR / name
    if not path.exists():
        pytest.fail(f"Fixture not found: {path}")
    with open(path) as f:
        return dict(json.load(f))


# ── PASS cases ───────────────────────────────────────────────────────────────


class TestValidLongSignal:
    def test_verdict(self) -> None:
        result = validator.validate_envelope(_load("valid_long_signal.json"))
        assert result.verdict == ValidationVerdict.PASS

    def test_normalized_direction(self) -> None:
        result = validator.validate_envelope(_load("valid_long_signal.json"))
        assert result.normalized is not None
        assert result.normalized["direction"] == "long"

    def test_normalized_confidence(self) -> None:
        result = validator.validate_envelope(_load("valid_long_signal.json"))
        assert result.normalized is not None
        assert result.normalized["confidence"] == 0.85

    def test_no_errors(self) -> None:
        result = validator.validate_envelope(_load("valid_long_signal.json"))
        assert len(result.errors) == 0


class TestValidShortSignal:
    def test_verdict(self) -> None:
        result = validator.validate_envelope(_load("valid_short_signal.json"))
        assert result.verdict == ValidationVerdict.PASS

    def test_normalized_direction(self) -> None:
        result = validator.validate_envelope(_load("valid_short_signal.json"))
        assert result.normalized is not None
        assert result.normalized["direction"] == "short"

    def test_model_id_preserved(self) -> None:
        result = validator.validate_envelope(_load("valid_short_signal.json"))
        assert result.normalized is not None
        assert result.normalized["model_id"] == "claude-sonnet-4"

    def test_no_errors(self) -> None:
        result = validator.validate_envelope(_load("valid_short_signal.json"))
        assert len(result.errors) == 0


class TestNoSignal:
    def test_verdict(self) -> None:
        result = validator.validate_envelope(_load("no_signal.json"))
        assert result.verdict == ValidationVerdict.WARN

    def test_warns_no_signal(self) -> None:
        result = validator.validate_envelope(_load("no_signal.json"))
        assert any("No-signal event" in w for w in result.warnings)

    def test_normalized_direction(self) -> None:
        result = validator.validate_envelope(_load("no_signal.json"))
        assert result.normalized is not None
        assert result.normalized["direction"] == "no_signal"

    def test_no_errors(self) -> None:
        result = validator.validate_envelope(_load("no_signal.json"))
        assert len(result.errors) == 0


class TestHeartbeat:
    def test_verdict(self) -> None:
        result = validator.validate_envelope(_load("heartbeat.json"))
        assert result.verdict == ValidationVerdict.WARN

    def test_warns_heartbeat(self) -> None:
        result = validator.validate_envelope(_load("heartbeat.json"))
        assert any("Heartbeat event" in w for w in result.warnings)

    def test_no_errors(self) -> None:
        result = validator.validate_envelope(_load("heartbeat.json"))
        assert len(result.errors) == 0


class TestStaleSignal:
    def test_verdict(self) -> None:
        result = validator.validate_envelope(_load("stale_signal.json"))
        assert result.verdict == ValidationVerdict.WARN

    def test_warns_stale(self) -> None:
        result = validator.validate_envelope(_load("stale_signal.json"))
        assert any(
            "stale" in w.lower() or "stale" in w.lower()
            for w in result.warnings
        )

    def test_no_errors(self) -> None:
        result = validator.validate_envelope(_load("stale_signal.json"))
        assert len(result.errors) == 0


class TestPartialMetadata:
    def test_verdict(self) -> None:
        result = validator.validate_envelope(
            _load("partial_metadata_signal.json")
        )
        # Degraded data quality is not a hard failure — PASS is correct
        assert result.verdict == ValidationVerdict.PASS

    def test_null_signal_strength_allowed(self) -> None:
        result = validator.validate_envelope(
            _load("partial_metadata_signal.json")
        )
        assert result.normalized is not None
        assert result.normalized["signal_strength"] is None


# ── FAIL cases ───────────────────────────────────────────────────────────────


class TestMalformedMissingRequiredFields:
    def test_verdict(self) -> None:
        result = validator.validate_envelope(
            _load("malformed_missing_required_fields.json")
        )
        assert result.verdict == ValidationVerdict.FAIL

    def test_has_errors(self) -> None:
        result = validator.validate_envelope(
            _load("malformed_missing_required_fields.json")
        )
        assert len(result.errors) > 0

    def test_error_mentions_missing_fields(self) -> None:
        result = validator.validate_envelope(
            _load("malformed_missing_required_fields.json")
        )
        error_text = "\n".join(result.errors)
        assert "event_type" in error_text
        assert "symbol" in error_text
        assert "direction" in error_text
        assert "confidence" in error_text
        assert "timestamp_utc" in error_text

    def test_no_normalized_envelope(self) -> None:
        result = validator.validate_envelope(
            _load("malformed_missing_required_fields.json")
        )
        assert result.normalized is None


class TestEmptyEnvelope:
    def test_verdict(self) -> None:
        result = validator.validate_envelope({})
        assert result.verdict == ValidationVerdict.FAIL

    def test_all_required_fields_reported(self) -> None:
        result = validator.validate_envelope({})
        assert len(result.errors) >= 11  # all required fields


# ── Normalization edge cases ────────────────────────────────────────────────


class TestDirectionNormalization:
    def test_bullish_to_long(self) -> None:
        env = _load("valid_long_signal.json")
        env["direction"] = "bullish"
        result = validator.validate_envelope(env)
        assert result.normalized is not None
        assert result.normalized["direction"] == "long"

    def test_bearish_to_short(self) -> None:
        env = _load("valid_long_signal.json")
        env["direction"] = "bearish"
        result = validator.validate_envelope(env)
        assert result.normalized is not None
        assert result.normalized["direction"] == "short"

    def test_neutral_to_flat(self) -> None:
        env = _load("valid_long_signal.json")
        env["direction"] = "neutral"
        result = validator.validate_envelope(env)
        assert result.normalized is not None
        assert result.normalized["direction"] == "flat"

    def test_unknown_direction_fails(self) -> None:
        env = _load("valid_long_signal.json")
        env["direction"] = "invalid_direction_xyz"
        result = validator.validate_envelope(env)
        assert result.verdict == ValidationVerdict.FAIL

    def test_none_direction_fails(self) -> None:
        env = _load("valid_long_signal.json")
        env["direction"] = None  # type: ignore[typeddict-item]
        result = validator.validate_envelope(env)
        # None direction is treated as missing required field
        assert result.verdict == ValidationVerdict.FAIL

    def test_empty_direction_fails(self) -> None:
        env = _load("valid_long_signal.json")
        env["direction"] = ""
        result = validator.validate_envelope(env)
        assert result.verdict == ValidationVerdict.FAIL


# ── Confidence edge cases ────────────────────────────────────────────────────


class TestConfidenceValidation:
    def test_negative_confidence_fails(self) -> None:
        env = _load("valid_long_signal.json")
        env["confidence"] = -0.1
        result = validator.validate_envelope(env)
        assert result.verdict == ValidationVerdict.FAIL

    def test_over_confidence_fails(self) -> None:
        env = _load("valid_long_signal.json")
        env["confidence"] = 1.5
        result = validator.validate_envelope(env)
        assert result.verdict == ValidationVerdict.FAIL

    def test_zero_confidence_passes(self) -> None:
        env = _load("valid_long_signal.json")
        env["confidence"] = 0.0
        result = validator.validate_envelope(env)
        assert result.verdict in (ValidationVerdict.PASS, ValidationVerdict.WARN)

    def test_non_numeric_confidence_fails(self) -> None:
        env = _load("valid_long_signal.json")
        env["confidence"] = "high"  # type: ignore[typeddict-item]
        result = validator.validate_envelope(env)
        assert result.verdict == ValidationVerdict.FAIL


# ── Unknown fields ────────────────────────────────────────────────────────────


class TestExtraFields:
    def test_unknown_fields_preserved(self) -> None:
        env = _load("valid_long_signal.json")
        env["custom_metric"] = 42
        result = validator.validate_envelope(env)
        assert result.normalized is not None
        assert "_extra_fields" in result.normalized
        extra = dict(result.normalized["_extra_fields"])  # type: ignore[arg-type]
        assert extra.get("custom_metric") == 42

    def test_unknown_fields_warn(self) -> None:
        env = _load("valid_long_signal.json")
        env["custom_metric"] = 42
        result = validator.validate_envelope(env)
        assert any("Extra fields" in w for w in result.warnings)


# ── Source file tracking ─────────────────────────────────────────────────────


class TestSourceFileTracking:
    def test_source_file_included(self) -> None:
        result = validator.validate_envelope(
            {"schema_version": 1},
            source_file="test.json",
        )
        assert result.source_file == "test.json"

    def test_fail_keeps_source(self) -> None:
        result = validator.validate_envelope({}, source_file="empty.json")
        assert result.source_file == "empty.json"
        assert result.verdict == ValidationVerdict.FAIL
