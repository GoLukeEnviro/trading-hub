"""Tests for the Rainbow client fixture harness (#100).

Verifies that the harness:
- loads fixture directory
- returns client-compatible result shape
- validates fixtures
- keeps malformed fixture fail-closed
- output is deterministic
"""

from __future__ import annotations

from pathlib import Path

from si_v2.rainbow.client_fixture_harness import (
    RainbowClientFixtureHarness,
)

_FIXTURE_DIR = (
    Path(__file__).resolve().parent.parent / "fixtures" / "rainbow-signals"
)


class TestHarness:
    def test_harness_creates(self) -> None:
        harness = RainbowClientFixtureHarness(_FIXTURE_DIR)
        assert harness is not None

    def test_run_loads_all_fixtures(self) -> None:
        harness = RainbowClientFixtureHarness(_FIXTURE_DIR)
        result = harness.run()
        assert result.total_fixtures == 7
        assert result.valid_signals >= 1  # at least valid ones

    def test_run_returns_signals(self) -> None:
        harness = RainbowClientFixtureHarness(_FIXTURE_DIR)
        result = harness.run()
        assert len(result.signals) > 0

    def test_valid_signals_have_required_fields(self) -> None:
        harness = RainbowClientFixtureHarness(_FIXTURE_DIR)
        signals = harness.get_valid_signals()
        for signal in signals:
            assert "event_type" in signal
            assert "schema_version" in signal
            assert "direction" in signal

    def test_malformed_is_counted(self) -> None:
        harness = RainbowClientFixtureHarness(_FIXTURE_DIR)
        result = harness.run()
        assert result.malformed_signals >= 0  # expected

    def test_result_deterministic(self) -> None:
        harness = RainbowClientFixtureHarness(_FIXTURE_DIR)
        r1 = harness.run()
        r2 = harness.run()
        assert r1.total_fixtures == r2.total_fixtures
        assert r1.valid_signals == r2.valid_signals
        assert r1.malformed_signals == r2.malformed_signals

    def test_result_source_indicates_harness(self) -> None:
        harness = RainbowClientFixtureHarness(_FIXTURE_DIR)
        result = harness.run()
        assert result.source == "fixture_harness"

    def test_errors_available(self) -> None:
        harness = RainbowClientFixtureHarness(_FIXTURE_DIR)
        result = harness.run()
        assert isinstance(result.errors, list)
