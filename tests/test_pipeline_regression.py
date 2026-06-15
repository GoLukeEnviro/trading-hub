from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest


# ===========================================================================
# Pipeline regression: read_signal, check_signal_freshness
# ===========================================================================


def _signal_file(tmp_path: Path, overrides: Dict[str, Any] | None = None) -> Path:
    """Write a minimal signal JSON and return its path."""
    payload = {
        "generated_at": "2026-06-15T12:00:00Z",
        "pairs": {
            "BTC/USDT": {
                "action": "LONG",
                "confidence": 0.75,
                "bias": "bullish",
                "quantity": 0.01,
            }
        },
    }
    if overrides:
        payload.update(overrides)
    path = tmp_path / "hermes_signal.json"
    path.write_text(json.dumps(payload))
    return path


class TestReadSignal:
    """trading_pipeline.read_signal behavior."""

    def test_reads_valid_signal(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        from orchestrator.scripts.trading_pipeline import read_signal

        signal_path = _signal_file(tmp_path)
        monkeypatch.setattr(
            "orchestrator.scripts.trading_pipeline.SIGNAL_INPUT_PATHS", [signal_path]
        )
        data, source = read_signal()
        assert data is not None
        assert "BTC/USDT" in data.get("pairs", {})

    def test_returns_none_on_missing_file(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        from orchestrator.scripts.trading_pipeline import read_signal

        missing = tmp_path / "nonexistent.json"
        monkeypatch.setattr(
            "orchestrator.scripts.trading_pipeline.SIGNAL_INPUT_PATHS", [missing]
        )
        data, source = read_signal()
        assert data is None
        assert source == ""

    def test_returns_none_on_invalid_json(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        from orchestrator.scripts.trading_pipeline import read_signal

        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not-json")
        monkeypatch.setattr(
            "orchestrator.scripts.trading_pipeline.SIGNAL_INPUT_PATHS", [bad_file]
        )
        data, source = read_signal()
        assert data is None


class TestSignalFreshness:
    """trading_pipeline.check_signal_freshness behavior."""

    def test_fresh_signal_passes(self) -> None:
        from orchestrator.scripts.trading_pipeline import check_signal_freshness
        from datetime import datetime, timezone

        signal = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        fresh, reason, age = check_signal_freshness(signal, max_age_min=25.0)
        assert fresh is True
        assert reason == "fresh"
        assert age is not None and age < 1.0

    def test_stale_signal_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from orchestrator.scripts.trading_pipeline import check_signal_freshness
        from datetime import datetime, timedelta, timezone

        old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        signal = {"generated_at": old}
        fresh, reason, age = check_signal_freshness(signal, max_age_min=25.0)
        assert fresh is False
        assert "stale" in reason

    def test_no_signal_returns_false(self) -> None:
        from orchestrator.scripts.trading_pipeline import check_signal_freshness

        fresh, reason, age = check_signal_freshness(None, max_age_min=25.0)
        assert fresh is False
        assert reason == "no_signal"

    def test_no_timestamp_returns_false(self) -> None:
        from orchestrator.scripts.trading_pipeline import check_signal_freshness

        fresh, reason, age = check_signal_freshness({}, max_age_min=25.0)
        assert fresh is False
        assert reason == "no_timestamp"


# ===========================================================================
# RiskGuard regression
# ===========================================================================


class TestRiskGuard:
    """trading_pipeline.riskguard_checks behavior."""

    def test_accepts_high_confidence_bullish(self) -> None:
        from orchestrator.scripts.trading_pipeline import riskguard_checks

        result = riskguard_checks(
            {"action": "LONG", "confidence": 0.85, "bias": "bullish", "quantity": 0.01},
            pair_key="BTC/USDT",
            is_stale=False,
            accepted_count=0,
        )
        assert result["verdict"] == "ACCEPTED"
        assert result["allow_long_bias"] is True

    def test_accepts_high_confidence_bearish(self) -> None:
        from orchestrator.scripts.trading_pipeline import riskguard_checks

        result = riskguard_checks(
            {"action": "SHORT", "confidence": 0.85, "bias": "bearish", "quantity": 0.01},
            pair_key="ETH/USDT",
            is_stale=False,
            accepted_count=0,
        )
        assert result["verdict"] == "ACCEPTED"
        assert result["allow_short_bias"] is True

    def test_rejects_low_confidence(self) -> None:
        from orchestrator.scripts.trading_pipeline import riskguard_checks

        result = riskguard_checks(
            {"action": "LONG", "confidence": 0.3, "bias": "bullish", "quantity": 0.01},
            pair_key="BTC/USDT",
            is_stale=False,
            accepted_count=0,
        )
        assert result["verdict"] == "WATCH_ONLY"
        assert "RG-2" in result.get("riskguard_reason", "")

    def test_stale_signal_is_watch_only(self) -> None:
        from orchestrator.scripts.trading_pipeline import riskguard_checks

        result = riskguard_checks(
            {"action": "LONG", "confidence": 0.9, "bias": "bullish", "quantity": 0.01},
            pair_key="BTC/USDT",
            is_stale=True,
            accepted_count=0,
        )
        assert result["verdict"] == "WATCH_ONLY"
        assert "RG-1" in result.get("riskguard_reason", "")

    def test_missing_bias_is_watch_only(self) -> None:
        from orchestrator.scripts.trading_pipeline import riskguard_checks

        result = riskguard_checks(
            {"action": "LONG", "confidence": 0.85, "bias": "neutral", "quantity": 0.01},
            pair_key="BTC/USDT",
            is_stale=False,
            accepted_count=0,
        )
        assert result["verdict"] == "WATCH_ONLY"
        assert "RG-3" in result.get("riskguard_reason", "")

    def test_concurrent_cap_blocks(self) -> None:
        from orchestrator.scripts.trading_pipeline import riskguard_checks

        result = riskguard_checks(
            {"action": "LONG", "confidence": 0.85, "bias": "bullish", "quantity": 0.01},
            pair_key="BTC/USDT",
            is_stale=False,
            accepted_count=5,
        )
        assert result["verdict"] == "WATCH_ONLY"
        assert "RG-4" in result.get("riskguard_reason", "")

    def test_zero_quantity_blocks_directional_signal(self) -> None:
        from orchestrator.scripts.trading_pipeline import riskguard_checks

        result = riskguard_checks(
            {"action": "LONG", "confidence": 0.85, "bias": "bullish", "quantity": 0.0},
            pair_key="BTC/USDT",
            is_stale=False,
            accepted_count=0,
        )
        assert result["verdict"] == "WATCH_ONLY"
        assert "RG-5" in result.get("riskguard_reason", "")


# ===========================================================================
# Strategy compile/import tests (no live exchange access)
# ===========================================================================


class TestStrategyImports:
    """Verify active strategies compile and import cleanly."""

    STRATEGY_PATHS = [
        "freqtrade/shared/strategies/MinimalViableStrategy_v1.py",
        "freqtrade/shared/exit_agent_v9.py",
    ]

    def test_strategies_compile(self) -> None:
        import py_compile

        for rel in self.STRATEGY_PATHS:
            path = Path(__file__).resolve().parent.parent / rel
            assert path.exists(), f"Strategy file not found: {path}"
            py_compile.compile(path, doraise=True)

    def test_freqforge_strategies_importable(self) -> None:
        import sys
        repo = Path(__file__).resolve().parent.parent
        freqtrade_shared = repo / "freqtrade" / "shared"
        if str(freqtrade_shared) not in sys.path:
            sys.path.insert(0, str(freqtrade_shared))
        # At minimum the shared module imports cleanly
        import freqtrade.shared.kill_switch  # noqa: F401
        import freqtrade.shared.primo_signal  # noqa: F401
