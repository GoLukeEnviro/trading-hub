"""Tests for the read-only Rainbow Signal Provider Client.

Verifies that:
- default config is disabled
- fixture mode loads local fixtures
- fixture mode validates through #79 validator
- malformed fixture returns fail-closed
- read-only non-fixture mode requires explicit config
- no network calls in tests
- no secrets required
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request

from si_v2.rainbow.client import (
    RainbowClientConfig,
    RainbowSignalProviderClient,
)

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | dict[str, "JsonValue"] | list["JsonValue"]
JsonObject = dict[str, JsonValue]

_FIXTURE_DIR = (
    Path(__file__).resolve().parent.parent / "fixtures" / "rainbow-signals"
)


# ── Default config ────────────────────────────────────────────────────────


class TestDefaultConfig:
    def test_default_disabled(self) -> None:
        config = RainbowClientConfig()
        assert config.enabled is False

    def test_default_mode_is_fixture(self) -> None:
        config = RainbowClientConfig()
        assert config.mode == "fixture"

    def test_disabled_client_returns_empty(self) -> None:
        client = RainbowSignalProviderClient()
        result = client.get_latest_signals()
        assert len(result.signals) == 0
        assert result.source == "empty"

    def test_disabled_client_has_error(self) -> None:
        client = RainbowSignalProviderClient()
        result = client.get_latest_signals()
        assert len(result.errors) > 0


# ── Fixture mode ──────────────────────────────────────────────────────────


class TestFixtureMode:
    def test_from_config_with_fixture_path(self) -> None:
        config = RainbowClientConfig(
            enabled=True,
            mode="fixture",
            fixture_path=str(_FIXTURE_DIR),
        )
        client = RainbowSignalProviderClient.from_config(config)
        assert client is not None
        assert client._config.enabled is True

    def test_load_from_fixture_path(self) -> None:
        client = RainbowSignalProviderClient(
            config=RainbowClientConfig(enabled=True)
        )
        result = client.load_from_fixture_path(_FIXTURE_DIR)
        assert result.source == "fixture"
        assert result.count > 0
        assert len(result.signals) > 0

    def test_fixture_loading_returns_valid_signals(self) -> None:
        client = RainbowSignalProviderClient(
            config=RainbowClientConfig(enabled=True)
        )
        result = client.load_from_fixture_path(_FIXTURE_DIR)
        # At least valid_long and valid_short should load
        assert result.count >= 2, (
            f"Expected >=2 valid signals, got {result.count}"
        )

    def test_get_latest_signals_after_load(self) -> None:
        client = RainbowSignalProviderClient(
            config=RainbowClientConfig(enabled=True, fixture_path=str(_FIXTURE_DIR))
        )
        client.load_from_fixture_path(_FIXTURE_DIR)
        result = client.get_latest_signals()
        assert result.count > 0
        assert result.source == "fixture"

    def test_signals_have_required_fields(self) -> None:
        client = RainbowSignalProviderClient(
            config=RainbowClientConfig(enabled=True)
        )
        result = client.load_from_fixture_path(_FIXTURE_DIR)
        for signal in result.signals:
            assert "event_type" in signal
            assert "schema_version" in signal
            assert "symbol" in signal
            assert "direction" in signal
            assert "confidence" in signal


# ── Validator integration ─────────────────────────────────────────────────


class TestValidatorIntegration:
    def test_validate_signals_returns_results(self) -> None:
        client = RainbowSignalProviderClient(
            config=RainbowClientConfig(enabled=True)
        )
        client.load_from_fixture_path(_FIXTURE_DIR)
        results = client.validate_signals()
        assert len(results) > 0

    def test_valid_signals_pass_validation(self) -> None:
        client = RainbowSignalProviderClient(
            config=RainbowClientConfig(enabled=True)
        )
        client.load_from_fixture_path(_FIXTURE_DIR)
        validation_results = client.validate_signals()
        for vr in validation_results:
            if "error" not in vr:
                assert vr["verdict"] is not None


# ── Malformed fixture handling ────────────────────────────────────────────


class TestMalformedHandling:
    def test_load_from_fixture_path_does_not_crash(self) -> None:
        """Malformed fixture should be excluded, not crash."""
        client = RainbowSignalProviderClient(
            config=RainbowClientConfig(enabled=True)
        )
        result = client.load_from_fixture_path(_FIXTURE_DIR)
        # It should not raise an exception
        assert result is not None


# ── Config enforcement ────────────────────────────────────────────────────


class TestConfigEnforcement:
    def test_disabled_config_returns_empty(self) -> None:
        config = RainbowClientConfig(enabled=False)
        client = RainbowSignalProviderClient.from_config(config)
        result = client.get_latest_signals()
        assert result.source == "empty"
        assert len(result.signals) == 0

    def test_disabled_client_with_fixture_path(self) -> None:
        """Even with fixture_path set, disabled client returns empty."""
        config = RainbowClientConfig(
            enabled=False,
            fixture_path=str(_FIXTURE_DIR),
        )
        client = RainbowSignalProviderClient.from_config(config)
        result = client.get_latest_signals()
        assert result.source == "empty"

    def test_nonexistent_fixture_path(self) -> None:
        client = RainbowSignalProviderClient(
            config=RainbowClientConfig(enabled=True)
        )
        result = client.load_from_fixture_path(Path("/tmp/nonexistent"))
        assert len(result.signals) == 0
        assert len(result.errors) > 0


# ── Max records ───────────────────────────────────────────────────────────


class TestMaxRecords:
    def test_max_records_limits_signals(self) -> None:
        config = RainbowClientConfig(
            enabled=True,
            max_records=2,
        )
        client = RainbowSignalProviderClient(config=config)
        client.load_from_fixture_path(_FIXTURE_DIR)
        result = client.get_latest_signals()
        assert result.count <= 2, (
            f"Expected <=2 signals, got {result.count}"
        )


# ── Result integrity ──────────────────────────────────────────────────────


class TestResultIntegrity:
    def test_result_has_count_matching_signals(self) -> None:
        client = RainbowSignalProviderClient(
            config=RainbowClientConfig(enabled=True)
        )
        result = client.load_from_fixture_path(_FIXTURE_DIR)
        assert result.count == len(result.signals)

    def test_multiple_loads_replace_fixtures(self) -> None:
        client = RainbowSignalProviderClient(
            config=RainbowClientConfig(enabled=True)
        )
        result1 = client.load_from_fixture_path(_FIXTURE_DIR)
        count1 = result1.count
        # Load again
        result2 = client.load_from_fixture_path(_FIXTURE_DIR)
        assert result2.count == count1  # Same fixtures

    def test_result_serializable(self) -> None:
        client = RainbowSignalProviderClient(
            config=RainbowClientConfig(enabled=True)
        )
        result = client.load_from_fixture_path(_FIXTURE_DIR)
        # Ensure we can read all fields
        assert isinstance(result.signals, list)
        assert isinstance(result.errors, list)
        assert isinstance(result.source, str)
        assert isinstance(result.count, int)


def _crypto_signal_payloads() -> list[JsonObject]:
    return [
        {
            "signal_id": "sig-btc-1",
            "timestamp": "2026-06-14T01:04:16.232556Z",
            "source": "ta_1h",
            "asset": "BTC/USDT",
            "signal_type": "technical",
            "direction": "bullish",
            "strength": 0.8,
            "confidence": 0.8,
            "value": 64501.03,
            "raw_data": {
                "rsi": 64.87,
                "macd": 224.1463,
                "macd_signal": 198.0549,
                "macd_hist": 26.0914,
                "ema_50": 63900.12,
                "ema_200": 61250.45,
                "bollinger": {"upper": 64890.0, "lower": 63120.5},
                "price": 64501.03,
            },
            "metadata": {"timeframe": "1h", "pair": "BTC/USDT"},
            "rainbow_score": None,
            "ai_evaluation": None,
        },
        {
            "signal_id": "sig-eth-1",
            "timestamp": "2026-06-14T01:04:16.486032Z",
            "source": "ta_1h",
            "asset": "ETH/USDT",
            "signal_type": "technical",
            "direction": "bullish",
            "strength": 0.95,
            "confidence": 0.95,
            "value": 1680.4,
            "raw_data": {
                "rsi": 54.59,
                "macd": 3.0733,
                "macd_signal": 3.047,
                "macd_hist": 0.0263,
                "ema_50": 1669.2,
                "ema_200": 1610.8,
                "bollinger": {"upper": 1693.5, "lower": 1638.2},
                "price": 1680.4,
            },
            "metadata": {"timeframe": "1h", "pair": "ETH/USDT"},
            "rainbow_score": None,
            "ai_evaluation": None,
        },
        {
            "signal_id": "sig-sol-1",
            "timestamp": "2026-06-14T01:04:16.742653Z",
            "source": "ta_1h",
            "asset": "SOL/USDT",
            "signal_type": "technical",
            "direction": "bullish",
            "strength": 0.8,
            "confidence": 0.8,
            "value": 68.65,
            "raw_data": {
                "rsi": 60.33,
                "macd": 0.4561,
                "macd_signal": 0.4219,
                "macd_hist": 0.0342,
                "ema_50": 67.46,
                "ema_200": 65.74,
                "bollinger": {"upper": 69.3, "lower": 66.97},
                "price": 68.65,
            },
            "metadata": {"timeframe": "1h", "pair": "SOL/USDT"},
            "rainbow_score": None,
            "ai_evaluation": None,
        },
    ]


class _FakeResponse:
    def __init__(self, payload: list[JsonObject], status: int = 200) -> None:
        self.status = status
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        del exc_type, exc, tb
        return None


class TestReadOnlyMode:
    def test_read_only_missing_base_url_fails_closed(self) -> None:
        config = RainbowClientConfig(
            enabled=True,
            mode="read_only",
        )
        client = RainbowSignalProviderClient.from_config(config)
        result = client.get_latest_signals()
        assert result.source == "empty"
        assert result.count == 0
        assert any("base_url" in error for error in result.errors)

    def test_read_only_successful_fetch_maps_and_validates_3_signals(
        self,
        monkeypatch: MonkeyPatch,
    ) -> None:
        captured: dict[str, object] = {}

        def fake_urlopen(request: Request, timeout: int = 0) -> _FakeResponse:
            captured["request"] = request
            captured["timeout"] = timeout
            return _FakeResponse(_crypto_signal_payloads())

        monkeypatch.setattr("si_v2.rainbow.client.urlopen", fake_urlopen)

        config = RainbowClientConfig(
            enabled=True,
            mode="read_only",
            base_url="http://rainbow.local:8000",
            endpoint_path="/signals/latest",
            timeout_seconds=7,
        )
        client = RainbowSignalProviderClient.from_config(config)
        result = client.get_latest_signals()

        assert result.source == "read_only"
        assert result.count == 3
        assert len(result.errors) == 0
        assert [signal["direction"] for signal in result.signals] == [
            "long",
            "long",
            "long",
        ]

        request = cast("Request", captured["request"])
        assert request.get_method() == "GET"
        assert request.full_url == (
            "http://rainbow.local:8000/signals/latest"
        )
        headers = {k.lower(): v for k, v in request.header_items()}
        assert "authorization" not in headers
        assert captured["timeout"] == 7

    def test_read_only_invalid_payload_fails_closed(
        self,
        monkeypatch: MonkeyPatch,
    ) -> None:
        invalid_payload = _crypto_signal_payloads()
        invalid_payload[0] = {"asset": "BTC/USDT"}

        def fake_urlopen(request: Request, timeout: int = 0) -> _FakeResponse:
            del request, timeout
            return _FakeResponse(invalid_payload)

        monkeypatch.setattr("si_v2.rainbow.client.urlopen", fake_urlopen)
        config = RainbowClientConfig(
            enabled=True,
            mode="read_only",
            base_url="http://rainbow.local:8000",
        )
        client = RainbowSignalProviderClient.from_config(config)
        result = client.get_latest_signals()

        assert result.source == "read_only"
        assert result.count == 2
        assert len(result.errors) >= 1

    def test_read_only_stale_signal_warns_without_crash(
        self,
        monkeypatch: MonkeyPatch,
    ) -> None:
        stale_payload = _crypto_signal_payloads()
        stale_payload[0]["timestamp"] = "2020-01-01T00:00:00Z"

        def fake_urlopen(request: Request, timeout: int = 0) -> _FakeResponse:
            del request, timeout
            return _FakeResponse(stale_payload)

        monkeypatch.setattr("si_v2.rainbow.client.urlopen", fake_urlopen)
        config = RainbowClientConfig(
            enabled=True,
            mode="read_only",
            base_url="http://rainbow.local:8000",
        )
        client = RainbowSignalProviderClient.from_config(config)
        result = client.get_latest_signals()

        assert result.source == "read_only"
        assert result.count == 3
        assert len(result.errors) == 0

    def test_http_non_200_returns_empty_and_error(
        self,
        monkeypatch: MonkeyPatch,
    ) -> None:
        def fake_urlopen(request: Request, timeout: int = 0) -> _FakeResponse:
            del timeout
            raise HTTPError(
                url=request.full_url,
                code=503,
                msg="service unavailable",
                hdrs=None,
                fp=None,
            )

        monkeypatch.setattr("si_v2.rainbow.client.urlopen", fake_urlopen)
        config = RainbowClientConfig(
            enabled=True,
            mode="read_only",
            base_url="http://rainbow.local:8000",
        )
        client = RainbowSignalProviderClient.from_config(config)
        result = client.get_latest_signals()

        assert result.source == "empty"
        assert result.count == 0
        assert any("HTTP 503" in error for error in result.errors)

    def test_timeout_network_error_returns_empty_and_error(
        self,
        monkeypatch: MonkeyPatch,
    ) -> None:
        def fake_urlopen(request: Request, timeout: int = 0) -> _FakeResponse:
            del request, timeout
            raise URLError("timed out")

        monkeypatch.setattr("si_v2.rainbow.client.urlopen", fake_urlopen)
        config = RainbowClientConfig(
            enabled=True,
            mode="read_only",
            base_url="http://rainbow.local:8000",
        )
        client = RainbowSignalProviderClient.from_config(config)
        result = client.get_latest_signals()

        assert result.source == "empty"
        assert result.count == 0
        assert any("timed out" in error for error in result.errors)

    def test_read_only_max_records_works(
        self,
        monkeypatch: MonkeyPatch,
    ) -> None:
        def fake_urlopen(request: Request, timeout: int = 0) -> _FakeResponse:
            del request, timeout
            return _FakeResponse(_crypto_signal_payloads())

        monkeypatch.setattr("si_v2.rainbow.client.urlopen", fake_urlopen)
        config = RainbowClientConfig(
            enabled=True,
            mode="read_only",
            base_url="http://rainbow.local:8000",
            max_records=2,
        )
        client = RainbowSignalProviderClient.from_config(config)
        result = client.get_latest_signals()

        assert result.source == "read_only"
        assert result.count == 2
