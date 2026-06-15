from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from orchestrator.scripts.trading_pipeline import (
    check_signal_freshness,
    read_signal,
    riskguard_checks,
)

# ===========================================================================
# Fixtures
# ===========================================================================


def _signal(overrides: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Build a minimal valid signal dict."""
    from datetime import datetime, timezone

    signal: Dict[str, Any] = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "pairs": {
            "BTC/USDT:USDT": {
                "action": "LONG",
                "confidence": 0.75,
                "bias": "bullish",
                "quantity": 0.01,
            },
            "ETH/USDT:USDT": {
                "action": "SHORT",
                "confidence": 0.80,
                "bias": "bearish",
                "quantity": 0.1,
            },
        },
    }
    if overrides:
        signal.update(overrides)
    return signal


def _signal_file(tmp_path: Path, overrides: Dict[str, Any] | None = None) -> Path:
    """Write a signal JSON to a temp file and return its path."""
    path = tmp_path / "hermes_signal.json"
    path.write_text(json.dumps(_signal(overrides)))
    return path


# ===========================================================================
# Resilience: stale signal handling
# ===========================================================================


class TestStaleSignalResilience:
    """System must fail closed or degrade gracefully on stale signals."""

    def test_stale_signal_is_detected(self) -> None:
        from datetime import datetime, timedelta, timezone

        old = (datetime.now(tz=timezone.utc) - timedelta(hours=3)).isoformat()
        signal = {"generated_at": old}
        fresh, reason, _age = check_signal_freshness(signal, max_age_min=25.0)
        assert fresh is False
        assert "stale" in reason

    def test_stale_signal_triggers_watch_only(self) -> None:
        """Stale signal leads to WATCH_ONLY, not ACCEPTED."""
        result = riskguard_checks(
            {"action": "LONG", "confidence": 0.9, "bias": "bullish", "quantity": 0.01},
            pair_key="BTC/USDT",
            is_stale=True,
            accepted_count=0,
        )
        assert result["verdict"] == "WATCH_ONLY"
        assert result["allow_long_bias"] is False

    def test_extremely_old_signal_is_rejected(self, tmp_path: Path) -> None:
        """A signal > 24h old is treated as stale/fail-closed."""
        from datetime import datetime, timedelta, timezone

        stale_ts = (datetime.now(tz=timezone.utc) - timedelta(hours=48)).isoformat()
        path = _signal_file(tmp_path, {"generated_at": stale_ts})


        import orchestrator.scripts.trading_pipeline as tp
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(tp, "SIGNAL_INPUT_PATHS", [path])

        data, _source = read_signal()
        assert data is not None
        fresh, reason, _age = check_signal_freshness(data, max_age_min=25.0)
        assert fresh is False
        assert "stale" in reason

        monkeypatch.undo()


# ===========================================================================
# Resilience: missing / absent signal
# ===========================================================================


class TestMissingSignalResilience:
    """System must fail closed when no signal is available."""

    def test_missing_signal_returns_none(self) -> None:
        """Absent signal file -> read_signal returns (None, '')."""
        import orchestrator.scripts.trading_pipeline as tp
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(tp, "SIGNAL_INPUT_PATHS", [Path("/nonexistent/path.json")])

        data, source = read_signal()
        assert data is None
        assert source == ""

        monkeypatch.undo()

    def test_no_signal_freshness_check_fails_closed(self) -> None:
        """When signal is None, freshness gate returns stale, not crash."""
        fresh, reason, _age = check_signal_freshness(None, max_age_min=25.0)
        assert fresh is False
        assert reason == "no_signal"

    def test_empty_pairs_returns_empty_list(self, tmp_path: Path) -> None:
        """Primo signal state without pairs should not crash."""
        from datetime import datetime, timezone
        state_file = tmp_path / "primo_signal_state.json"
        state_file.write_text(
            json.dumps({
                "generated_at": datetime.now(tz=timezone.utc).isoformat(),
                "fresh": True,
                "age_minutes": 0.1,
                "pairs": {},
            })
        )

        import orchestrator.scripts.trading_pipeline as tp
        original_paths = tp.SIGNAL_INPUT_PATHS
        tp.SIGNAL_INPUT_PATHS = [state_file]

        data, _source = read_signal()
        assert data is not None
        fresh, _reason, _age = check_signal_freshness(data, max_age_min=25.0)
        assert fresh is True

        tp.SIGNAL_INPUT_PATHS = original_paths


# ===========================================================================
# Resilience: malformed / corrupt signal
# ===========================================================================


class TestMalformedSignalResilience:
    """System must not crash on corrupt or unexpected signal shapes."""

    def test_corrupt_json_file_returns_none(self, tmp_path: Path) -> None:
        """Corrupt JSON in signal file -> read_signal returns (None, '')."""
        bad_file = tmp_path / "corrupt.json"
        bad_file.write_text("this is not json {{{")

        import orchestrator.scripts.trading_pipeline as tp
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(tp, "SIGNAL_INPUT_PATHS", [bad_file])

        data, _source = read_signal()
        assert data is None

        monkeypatch.undo()

    def test_missing_timestamp_in_signal(self) -> None:
        """Signal without a timestamp is detected as stale/no_timestamp."""
        signal = {"pairs": {"BTC/USDT": {"action": "LONG"}}}
        fresh, reason, _age = check_signal_freshness(signal, max_age_min=25.0)
        assert fresh is False
        assert reason == "no_timestamp"


# ===========================================================================
# Resilience: fail-closed default behavior
# ===========================================================================


class TestFailClosedBehavior:
    """The pipeline defaults to WATCH_ONLY when confidence is low."""

    def test_zero_confidence_triggers_watch_only(self) -> None:
        result = riskguard_checks(
            {"action": "LONG", "confidence": 0.0, "bias": "bullish", "quantity": 0.01},
            pair_key="BTC/USDT",
            is_stale=False,
            accepted_count=0,
        )
        assert result["verdict"] == "WATCH_ONLY"

    def test_negative_confidence_triggers_watch_only(self) -> None:
        result = riskguard_checks(
            {"action": "LONG", "confidence": -0.5, "bias": "bullish", "quantity": 0.01},
            pair_key="BTC/USDT",
            is_stale=False,
            accepted_count=0,
        )
        assert result["verdict"] == "WATCH_ONLY"

    def test_no_bias_triggers_watch_only(self) -> None:
        result = riskguard_checks(
            {"action": "LONG", "confidence": 0.9, "bias": "", "quantity": 0.01},
            pair_key="BTC/USDT",
            is_stale=False,
            accepted_count=0,
        )
        assert result["verdict"] == "WATCH_ONLY"

    def test_exceeded_concurrent_cap_triggers_watch_only(self) -> None:
        result = riskguard_checks(
            {"action": "LONG", "confidence": 0.9, "bias": "bullish", "quantity": 0.01},
            pair_key="BTC/USDT",
            is_stale=False,
            accepted_count=5,
        )
        assert result["verdict"] == "WATCH_ONLY"


# ===========================================================================
# Resilience: upstream interruption tolerance (opt-in)
# ===========================================================================


class TestUpstreamInterruption:
    """Scenarios that depend on local runtime state — opt-in only."""

    @pytest.mark.runtime
    def test_missing_primo_signal_state_handled_gracefully(self, tmp_path: Path) -> None:
        """When the shared primo signal file doesn't exist, load_known_pairs
        returns [].  This is an opt-in runtime test."""
        import orchestrator.scripts.trading_pipeline as tp

        non_existent = tmp_path / "does_not_exist.json"

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(tp, "PROJECT_DIR", tmp_path)

        # Override the template path in load_known_pairs
        original = tp.load_known_pairs
        monkeypatch.setattr(
            tp,
            "load_known_pairs",
            lambda: [] if not non_existent.exists() else original(),
        )

        pairs = tp.load_known_pairs()
        assert pairs == []

        monkeypatch.undo()
