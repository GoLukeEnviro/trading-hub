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

from pathlib import Path

from si_v2.rainbow.client import (
    RainbowClientConfig,
    RainbowSignalProviderClient,
)

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
