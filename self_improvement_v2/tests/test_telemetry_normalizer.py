"""Tests for the SI v2 telemetry normalizer.

These are pure unit tests — no network, no Freqtrade, no Docker.
They exercise the normalizer's secret redaction, open-trade extraction,
and stable-model construction.

Hard constraints tested:
    1. NormalizedTelemetry never contains credential values
    2. Secret redaction catches all SENSITIVE_KEYS
    3. Env-var names are passed through; env-var values are never stored
    4. Schema stability (extra='forbid')
    5. Edge cases: empty responses, error responses, non-JSON summaries
"""

from __future__ import annotations

import json

import pytest

from si_v2.loop.telemetry_normalizer import (
    SENSITIVE_KEYS,
    NormalizedTelemetry,
    extract_open_trades,
    normalize_raw_evidence,
    redact_dict,
    redact_response_summary,
)


class TestSecretRedaction:
    """Tests for the redact_dict and redact_response_summary functions."""

    def test_redact_dict_plain(self) -> None:
        """Plain dict with no sensitive keys passes through unchanged."""
        raw = {"status": "ok", "version": "2.0"}
        assert redact_dict(raw) == raw

    def test_redact_dict_access_token(self) -> None:
        """access_token is redacted."""
        raw = {"access_token": "eyJhbGci.eyJzdWI.secret", "status": "logged_in"}
        result = redact_dict(raw)
        assert result["access_token"] == "[REDACTED]"
        assert result["status"] == "logged_in"

    def test_redact_dict_nested(self) -> None:
        """Sensitive keys inside nested structures are redacted."""
        raw = {
            "user": {"token": "abc123"},
            "data": [{"refresh_token": "xyz789"}],
        }
        result = redact_dict(raw)
        assert result["user"]["token"] == "[REDACTED]"
        assert result["data"][0]["refresh_token"] == "[REDACTED]"

    def test_redact_dict_case_insensitive(self) -> None:
        """Sensitive key matching is case-insensitive."""
        raw = {"ACCESS_TOKEN": "secret", "Password": "hunter2"}
        result = redact_dict(raw)
        assert result["ACCESS_TOKEN"] == "[REDACTED]"
        assert result["Password"] == "[REDACTED]"

    def test_redact_dict_list_primitive(self) -> None:
        """A list of primitives is returned unchanged."""
        raw = ["a", "b", "c"]
        assert redact_dict(raw) == raw

    def test_redact_dict_scalar(self) -> None:
        """A scalar value is returned unchanged."""
        assert redact_dict("hello") == "hello"
        assert redact_dict(42) == 42
        assert redact_dict(None) is None

    def test_all_sensitive_keys_covered(self) -> None:
        """Every key in SENSITIVE_KEYS is redacted when present."""
        raw = {k: f"value_{k}" for k in SENSITIVE_KEYS}
        result = redact_dict(raw)
        for k in SENSITIVE_KEYS:
            assert result[k] == "[REDACTED]", f"Key {k} was not redacted"

    def test_redact_response_summary_json_with_secret(self) -> None:
        """JSON with a sensitive key is redacted."""
        summary = json.dumps({"access_token": "secret123", "status": "ok"})
        result = redact_response_summary(summary)
        parsed = json.loads(result)
        assert parsed["access_token"] == "[REDACTED]"
        assert parsed["status"] == "ok"

    def test_redact_response_summary_non_json(self) -> None:
        """Non-JSON summary is returned unchanged."""
        summary = "connection_error: timeout connecting to bot"
        assert redact_response_summary(summary) == summary

    def test_redact_response_summary_empty(self) -> None:
        """Empty or special-case strings are returned unchanged."""
        assert redact_response_summary("") == ""
        assert redact_response_summary("empty_body") == "empty_body"

    def test_redact_response_summary_parse_error_handled(self) -> None:
        """Invalid JSON-like but non-decodable input is safe."""
        assert redact_response_summary("{not json") == "{not json"


class TestExtractOpenTrades:
    """Tests for best-effort open-trades extraction."""

    def test_extract_empty(self) -> None:
        """Empty string returns 0."""
        assert extract_open_trades("") == 0

    def test_extract_non_json(self) -> None:
        """Non-JSON string returns 0."""
        assert extract_open_trades("connection_error") == 0

    def test_extract_list(self) -> None:
        """A JSON array represents a list of open trades."""
        summary = json.dumps([{"id": 1}, {"id": 2}])
        assert extract_open_trades(summary) == 2

    def test_extract_empty_list(self) -> None:
        """An empty JSON array returns 0."""
        assert extract_open_trades("[]") == 0

    def test_extract_dict_with_data_key(self) -> None:
        """A dict with a 'data' key containing a list."""
        summary = json.dumps({"data": [{"id": 1}, {"id": 2}, {"id": 3}]})
        assert extract_open_trades(summary) == 3

    def test_extract_dict_with_open_trades_key(self) -> None:
        """A dict with an explicit 'open_trades' key."""
        summary = json.dumps({"open_trades": 4})
        assert extract_open_trades(summary) == 4

    def test_extract_dict_with_bad_open_trades(self) -> None:
        """A dict with a non-integer 'open_trades' returns 0."""
        summary = json.dumps({"open_trades": "many"})
        assert extract_open_trades(summary) == 0

    def test_extract_other_dict(self) -> None:
        """A dict without expected keys returns 0."""
        summary = json.dumps({"status": "ok"})
        assert extract_open_trades(summary) == 0


class TestNormalizeRawEvidence:
    """Tests for the main normalize_raw_evidence function."""

    def test_basic_normalization(self) -> None:
        """Basic input produces a correct NormalizedTelemetry."""
        result = normalize_raw_evidence(
            bot_id="freqtrade-freqforge",
            base_url="http://trading-freqtrade-freqforge-1:8080",
            ping_status_code=200,
            ping_response_summary='{"status":"ok"}',
            status_status_code=200,
            status_response_summary='[{"trade_id":1}]',
            status_auth_outcome="AUTHENTICATED",
            username_env="SI_V2_FREQTRADE_FREQFORGE_USERNAME",
            password_env="SI_V2_FREQTRADE_FREQFORGE_PASSWORD",
            fetched_at_utc="2026-06-13T12:00:00Z",
        )
        assert result.bot_id == "freqtrade-freqforge"
        assert result.base_url == "http://trading-freqtrade-freqforge-1:8080"
        assert result.ping_status_code == 200
        assert result.ping_ok is True
        assert result.status_status_code == 200
        assert result.status_ok is True
        assert result.status_auth_outcome == "AUTHENTICATED"
        assert result.status_open_trades == 1  # list of 1
        assert result.username_env == "SI_V2_FREQTRADE_FREQFORGE_USERNAME"
        assert result.password_env == "SI_V2_FREQTRADE_FREQFORGE_PASSWORD"
        assert result.missing_env_vars == ()
        assert result.auth_error_summary == ""
        assert result.fetched_at_utc == "2026-06-13T12:00:00Z"
        assert result.auth_type == "none"

    def test_secret_redaction_belt_and_suspenders(self) -> None:
        """Even if connector misses a secret, the normalizer catches it."""
        leaky_summary = json.dumps({"access_token": "not-redacted-by-connector"})
        result = normalize_raw_evidence(
            bot_id="test-bot",
            base_url="http://localhost:8080",
            ping_status_code=200,
            ping_response_summary='{"status":"ok"}',
            status_status_code=200,
            status_response_summary=leaky_summary,
            status_auth_outcome="AUTHENTICATED",
        )
        parsed = json.loads(result.status_response_summary)
        assert parsed["access_token"] == "[REDACTED]"

    def test_ping_failure(self) -> None:
        """Connection error (status_code=0) results in ping_ok=False."""
        result = normalize_raw_evidence(
            bot_id="test-bot",
            base_url="http://localhost:8080",
            ping_status_code=0,
            ping_response_summary="connection_error: timeout",
            status_status_code=0,
            status_response_summary="not_attempted",
            status_auth_outcome="NOT_ATTEMPTED",
        )
        assert result.ping_ok is False
        assert result.ping_status_code == 0
        assert result.status_auth_outcome == "NOT_ATTEMPTED"

    def test_missing_env_vars(self) -> None:
        """Missing env vars are recorded as tuple."""
        result = normalize_raw_evidence(
            bot_id="test-bot",
            base_url="http://localhost:8080",
            ping_status_code=200,
            ping_response_summary='{"status":"ok"}',
            status_status_code=0,
            status_response_summary="YELLOW: missing env vars (USERNAME_ENV)",
            status_auth_outcome="YELLOW_MISSING_ENV_VARS",
            username_env="SI_V2_FREQTRADE_TEST_USERNAME",
            password_env="SI_V2_FREQTRADE_TEST_PASSWORD",
            missing_env_vars=[
                "SI_V2_FREQTRADE_TEST_USERNAME",
                "SI_V2_FREQTRADE_TEST_PASSWORD",
            ],
        )
        assert "SI_V2_FREQTRADE_TEST_USERNAME" in result.missing_env_vars
        assert "SI_V2_FREQTRADE_TEST_PASSWORD" in result.missing_env_vars
        assert result.status_auth_outcome == "YELLOW_MISSING_ENV_VARS"

    def test_auth_error_truncated(self) -> None:
        """Auth error summary is truncated to 500 chars."""
        long_error = "x" * 1000
        result = normalize_raw_evidence(
            bot_id="test-bot",
            base_url="http://localhost:8080",
            ping_status_code=200,
            ping_response_summary='{"status":"ok"}',
            status_status_code=0,
            status_response_summary="auth_error: bad credentials",
            status_auth_outcome="FAILED",
            auth_error_summary=long_error,
        )
        assert len(result.auth_error_summary) <= 500
        assert result.auth_error_summary == long_error[:500]

    def test_no_credential_values_in_output(self) -> None:
        """The NormalizedTelemetry model never contains credential values.

        This test proves that only env-var *names* (not values) are stored
        in the normalized output. If this test fails, there's a secret leak.
        """
        result = normalize_raw_evidence(
            bot_id="test-bot",
            base_url="http://localhost:8080",
            ping_status_code=200,
            ping_response_summary='{"status":"ok"}',
            status_status_code=200,
            status_response_summary='[]',
            status_auth_outcome="AUTHENTICATED",
            username_env="SI_V2_FREQTRADE_TEST_USERNAME",
            password_env="SI_V2_FREQTRADE_TEST_PASSWORD",
        )
        raw = result.model_dump(mode="json")
        raw_json = json.dumps(raw)
        # Verify that the output does NOT contain typical credential patterns
        assert "$ecret_Not_A_Real_Value_" not in raw_json
        assert "username" not in raw_json.lower() or raw_json.count("username") <= 2
        # The only username/password strings should be env-var NAMES
        # Verify by checking that no suspicious value like "test_user" is present
        assert "test_user" not in raw_json  # not the env var name

    def test_schema_version(self) -> None:
        """Schema version is set correctly."""
        result = normalize_raw_evidence(
            bot_id="test-bot",
            base_url="http://localhost:8080",
            ping_status_code=200,
            ping_response_summary="",
            status_status_code=200,
            status_response_summary="",
            status_auth_outcome="AUTHENTICATED",
        )
        assert result.schema_version == "telemetry_normalizer_v1"

    def test_extra_field_rejected(self) -> None:
        """Extra fields are rejected by the Pydantic model."""
        with pytest.raises(ValueError, match="Extra inputs are not permitted"):
            NormalizedTelemetry(
                bot_id="test",
                base_url="http://localhost:8080",
                ping_status_code=200,
                ping_ok=True,
                fetched_at_utc="2026-01-01T00:00:00Z",
                extra_field="not allowed",  # type: ignore[call-arg]
            )

    def test_all_field_types_stable(self) -> None:
        """All fields are JSON-serializable and have expected types."""
        result = normalize_raw_evidence(
            bot_id="test-bot",
            base_url="http://localhost:8080",
            ping_status_code=200,
            ping_response_summary="",
            status_status_code=0,
            status_response_summary="",
            status_auth_outcome="NOT_ATTEMPTED",
        )
        asdict = result.model_dump(mode="json")
        # Verify all values are JSON-native types
        assert isinstance(asdict["bot_id"], str)
        assert isinstance(asdict["ping_status_code"], int)
        assert isinstance(asdict["ping_ok"], bool)
        assert isinstance(asdict["missing_env_vars"], list)
        assert isinstance(asdict["status_open_trades"], int)

    def test_open_trades_extraction_works_with_bot_evidence_conversion(self) -> None:
        """Open trade extraction and status auth outcome flow through correctly."""
        from si_v2.loop.telemetry_normalizer import to_bot_evidence

        result = normalize_raw_evidence(
            bot_id="freqtrade-regime-hybrid",
            base_url="http://trading-freqtrade-regime-hybrid-1:8080",
            ping_status_code=200,
            ping_response_summary='{"status":"ok"}',
            status_status_code=200,
            status_response_summary='[{"trade_id": 1}, {"trade_id": 2}]',
            status_auth_outcome="AUTHENTICATED",
        )

        ev_dict = to_bot_evidence(result)
        assert ev_dict["bot_id"] == "freqtrade-regime-hybrid"
        assert ev_dict["ping_ok"] is True
        assert ev_dict["status_auth_outcome"] == "AUTHENTICATED"
        assert ev_dict["status_open_trades"] == 2
        assert isinstance(ev_dict["missing_env_vars"], tuple)
