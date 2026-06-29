"""Tests for Bridge/Primo/Intelligence signal pipeline.

Tests cover:
- bridge/hermes_primo_bridge.py: validate_signal, _pair_to_filename
- primo/llm_signal_filter.py: build_llm_context, _fmt, call_llm_signal_filter (mocked)
- intelligence/regime_detector.py: detect_regime, regime_to_weight_multiplier
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch


# ======================================================================
# bridge/hermes_primo_bridge.py
# ======================================================================

class TestBridgePairToFilename:
    """_pair_to_filename mapping."""

    def _import(self) -> Any:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "bridge"))
        import hermes_primo_bridge as hpb
        return hpb

    def test_standard_pair(self) -> None:
        hpb = self._import()
        assert hpb._pair_to_filename("BTC/USDT:USDT") == "BTC_USDT_USDT.json"

    def test_eth_pair(self) -> None:
        hpb = self._import()
        assert hpb._pair_to_filename("ETH/USDT:USDT") == "ETH_USDT_USDT.json"

    def test_sol_pair(self) -> None:
        hpb = self._import()
        assert hpb._pair_to_filename("SOL/USDT:USDT") == "SOL_USDT_USDT.json"


class TestBridgeValidateSignal:
    """validate_signal — the core signal validation function."""

    def _import(self) -> Any:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "bridge"))
        import hermes_primo_bridge as hpb
        return hpb

    def _valid_signal(self) -> dict:
        return {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "pair": "BTC/USDT:USDT",
            "direction": "long",
            "confidence": 0.75,
            "veto": False,
            "risk_cap_percent": 0.5,
        }

    def test_valid_signal_passes(self) -> None:
        hpb = self._import()
        assert hpb.validate_signal(self._valid_signal()) is True

    def test_not_a_dict(self) -> None:
        hpb = self._import()
        assert hpb.validate_signal("not a dict") is False

    def test_none_input(self) -> None:
        hpb = self._import()
        assert hpb.validate_signal(None) is False

    def test_stale_timestamp(self) -> None:
        hpb = self._import()
        signal = self._valid_signal()
        # Set timestamp 2x freshness in the past
        signal["timestamp_utc"] = datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()
        assert hpb.validate_signal(signal) is False

    def test_invalid_timestamp(self) -> None:
        hpb = self._import()
        signal = self._valid_signal()
        signal["timestamp_utc"] = "not-a-timestamp"
        assert hpb.validate_signal(signal) is False

    def test_missing_timestamp(self) -> None:
        hpb = self._import()
        signal = self._valid_signal()
        del signal["timestamp_utc"]
        assert hpb.validate_signal(signal) is False

    def test_disallowed_pair(self) -> None:
        hpb = self._import()
        signal = self._valid_signal()
        signal["pair"] = "XRP/USDT:USDT"
        assert hpb.validate_signal(signal) is False

    def test_missing_pair(self) -> None:
        hpb = self._import()
        signal = self._valid_signal()
        del signal["pair"]
        assert hpb.validate_signal(signal) is False

    def test_invalid_direction(self) -> None:
        hpb = self._import()
        signal = self._valid_signal()
        signal["direction"] = "short"
        assert hpb.validate_signal(signal) is False

    def test_missing_direction(self) -> None:
        hpb = self._import()
        signal = self._valid_signal()
        del signal["direction"]
        assert hpb.validate_signal(signal) is False

    def test_confidence_out_of_range_high(self) -> None:
        hpb = self._import()
        signal = self._valid_signal()
        signal["confidence"] = 1.5
        assert hpb.validate_signal(signal) is False

    def test_confidence_out_of_range_low(self) -> None:
        hpb = self._import()
        signal = self._valid_signal()
        signal["confidence"] = -0.5
        assert hpb.validate_signal(signal) is False

    def test_confidence_non_numeric(self) -> None:
        hpb = self._import()
        signal = self._valid_signal()
        signal["confidence"] = "high"
        assert hpb.validate_signal(signal) is False

    def test_confidence_zero(self) -> None:
        hpb = self._import()
        signal = self._valid_signal()
        signal["confidence"] = 0.0
        assert hpb.validate_signal(signal) is True  # 0.0 is valid

    def test_confidence_one(self) -> None:
        hpb = self._import()
        signal = self._valid_signal()
        signal["confidence"] = 1.0
        assert hpb.validate_signal(signal) is True  # 1.0 is valid

    def test_veto_true(self) -> None:
        hpb = self._import()
        signal = self._valid_signal()
        signal["veto"] = True
        assert hpb.validate_signal(signal) is False

    def test_risk_cap_exceeds_one(self) -> None:
        hpb = self._import()
        signal = self._valid_signal()
        signal["risk_cap_percent"] = 2.0
        assert hpb.validate_signal(signal) is False

    def test_risk_cap_non_numeric(self) -> None:
        hpb = self._import()
        signal = self._valid_signal()
        signal["risk_cap_percent"] = "high"
        assert hpb.validate_signal(signal) is True  # non-critical field, passes

    def test_direction_none_allowed(self) -> None:
        hpb = self._import()
        signal = self._valid_signal()
        signal["direction"] = "none"
        assert hpb.validate_signal(signal) is True


# ======================================================================
# primo/llm_signal_filter.py
# ======================================================================

class TestLlmSignalFilterFmt:
    """_fmt helper — format values for prompt table."""

    def _import(self) -> Any:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "primo"))
        import llm_signal_filter as lsf
        return lsf

    def test_float_value(self) -> None:
        lsf = self._import()
        assert lsf._fmt(3.14159) == "3.1416"

    def test_none_value(self) -> None:
        lsf = self._import()
        assert lsf._fmt(None) == "N/A"

    def test_na_string(self) -> None:
        lsf = self._import()
        assert lsf._fmt("N/A") == "N/A"

    def test_string_value(self) -> None:
        lsf = self._import()
        assert lsf._fmt("hello") == "hello"

    def test_int_value(self) -> None:
        lsf = self._import()
        assert lsf._fmt(42) == "42.0000"

    def test_zero(self) -> None:
        lsf = self._import()
        assert lsf._fmt(0) == "0.0000"


class TestLlmSignalFilterBuildContext:
    """build_llm_context — pure function, no I/O."""

    def _import(self) -> Any:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "primo"))
        import llm_signal_filter as lsf
        return lsf

    def _minimal_indicators(self) -> dict:
        return {
            "rsi_14": 55.0,
            "ema_50": 50000.0,
            "ema_200": 48000.0,
            "adx_14": 25.0,
            "atr_percent": 0.02,
            "bb_width": 0.05,
            "bb_position_pct": 0.5,
            "volume_ratio": 1.2,
        }

    def _minimal_technical(self) -> dict:
        return {
            "action": "BUY",
            "confidence": 0.7,
            "signal_quality": "good",
            "strategy_fit": "trend_following",
            "reasons": ["ema_cross", "rsi_momentum"],
        }

    def test_builds_context(self) -> None:
        lsf = self._import()
        ctx = lsf.build_llm_context(
            pair="BTC/USDT",
            pair_freqtrade="BTC/USDT:USDT",
            timeframe="15m",
            indicators=self._minimal_indicators(),
            latest_price=50000.0,
            technical_result=self._minimal_technical(),
        )
        assert ctx["pair"] == "BTC/USDT"
        assert ctx["pair_freqtrade"] == "BTC/USDT:USDT"
        assert ctx["timeframe"] == "15m"
        assert ctx["baseline_action"] == "BUY"
        assert ctx["baseline_confidence"] == "0.70"
        assert ctx["ema_trend"] == "bullish"  # 50 > 200

    def test_bearish_ema_trend(self) -> None:
        lsf = self._import()
        indicators = self._minimal_indicators()
        indicators["ema_50"] = 45000.0
        indicators["ema_200"] = 50000.0
        ctx = lsf.build_llm_context(
            pair="BTC/USDT", pair_freqtrade="BTC/USDT:USDT",
            timeframe="15m", indicators=indicators,
            latest_price=47000.0, technical_result=self._minimal_technical(),
        )
        assert ctx["ema_trend"] == "bearish"

    def test_unknown_ema_trend(self) -> None:
        lsf = self._import()
        indicators = self._minimal_indicators()
        indicators["ema_50"] = "N/A"
        ctx = lsf.build_llm_context(
            pair="BTC/USDT", pair_freqtrade="BTC/USDT:USDT",
            timeframe="15m", indicators=indicators,
            latest_price=47000.0, technical_result=self._minimal_technical(),
        )
        assert ctx["ema_trend"] == "unknown"

    def test_missing_indicators_fallback(self) -> None:
        lsf = self._import()
        ctx = lsf.build_llm_context(
            pair="BTC/USDT", pair_freqtrade="BTC/USDT:USDT",
            timeframe="15m", indicators={},
            latest_price=50000.0, technical_result={},
        )
        assert ctx["rsi_14"] == "N/A"
        assert ctx["ema_50"] == "N/A"
        assert ctx["baseline_action"] == "WATCH"
        assert ctx["baseline_confidence"] == "0.00"

    def test_alt_indicator_names(self) -> None:
        """Should handle alternative indicator names (RSI, EMA_50, etc.)."""
        lsf = self._import()
        indicators = {"RSI": 60.0, "EMA_50": 51000.0, "ADX": 30.0}
        ctx = lsf.build_llm_context(
            pair="BTC/USDT", pair_freqtrade="BTC/USDT:USDT",
            timeframe="15m", indicators=indicators,
            latest_price=50000.0, technical_result={},
        )
        assert ctx["rsi_14"] == "60.0000"
        assert ctx["ema_50"] == "51000.0000"
        assert ctx["adx_14"] == "30.0000"


class TestLlmSignalFilterCallLlm:
    """call_llm_signal_filter — LLM call with mocked dependencies."""

    def _import(self) -> Any:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "primo"))
        import llm_signal_filter as lsf
        return lsf

    def test_disabled_returns_watch(self, monkeypatch: MonkeyPatch) -> None:
        lsf = self._import()
        monkeypatch.setattr(lsf, "LLM_ENABLED", False)
        result = lsf.call_llm_signal_filter({"pair": "BTC/USDT"})
        assert result["action"] == "WATCH"
        assert result["confidence"] == 0.0

    def test_llm_error_returns_fallback(self, monkeypatch: MonkeyPatch) -> None:
        """When LLM import fails, should return fallback veto."""
        lsf = self._import()
        monkeypatch.setattr(lsf, "LLM_ENABLED", True)
        # Mock the import to fail
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "src.config.model_factory":
                raise ImportError("Mock import error")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        result = lsf.call_llm_signal_filter({"pair": "BTC/USDT"})
        assert result["action"] in ("WATCH", "HOLD")
        assert result["confidence"] == 0.0


# ======================================================================
# intelligence/regime_detector.py
# ======================================================================

class TestRegimeDetectorRegimeToWeight:
    """regime_to_weight_multiplier — pure function."""

    def _import(self) -> Any:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "intelligence"))
        import regime_detector as rd
        return rd

    def test_strong_trend_up(self) -> None:
        rd = self._import()
        assert rd.regime_to_weight_multiplier("strong_trend_up") == 1.15

    def test_strong_trend_down(self) -> None:
        rd = self._import()
        assert rd.regime_to_weight_multiplier("strong_trend_down") == 0.85

    def test_weak_trend_up(self) -> None:
        rd = self._import()
        assert rd.regime_to_weight_multiplier("weak_trend_up") == 1.05

    def test_weak_trend_down(self) -> None:
        rd = self._import()
        assert rd.regime_to_weight_multiplier("weak_trend_down") == 0.95

    def test_ranging(self) -> None:
        rd = self._import()
        assert rd.regime_to_weight_multiplier("ranging") == 0.80

    def test_high_volatility(self) -> None:
        rd = self._import()
        assert rd.regime_to_weight_multiplier("high_volatility") == 0.70

    def test_choppy(self) -> None:
        rd = self._import()
        assert rd.regime_to_weight_multiplier("choppy") == 0.60

    def test_unknown(self) -> None:
        rd = self._import()
        assert rd.regime_to_weight_multiplier("unknown") == 1.0

    def test_unmapped_regime(self) -> None:
        rd = self._import()
        assert rd.regime_to_weight_multiplier("nonexistent") == 1.0


class TestRegimeDetectorDetectRegime:
    """detect_regime — needs pandas DataFrame."""

    def _import(self) -> Any:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "intelligence"))
        import regime_detector as rd
        return rd

    def test_missing_columns(self) -> None:
        """Missing required columns should return unknown."""
        rd = self._import()
        import pandas as pd
        df = pd.DataFrame({"close": [100]})
        result = rd.detect_regime(df)
        assert result["regime"] == "unknown"
        assert "missing_columns" in result.get("error", "")

    def test_insufficient_data(self) -> None:
        """Too few rows should return unknown."""
        rd = self._import()
        import pandas as pd
        df = pd.DataFrame({"high": [100], "low": [99], "close": [100]})
        result = rd.detect_regime(df)
        assert result["regime"] == "unknown"
        assert "insufficient_data" in result.get("error", "")

    def test_sufficient_data_returns_regime(self) -> None:
        """With enough data, should return a regime."""
        rd = self._import()
        import pandas as pd
        import numpy as np
        # Generate 250 rows of trending data
        np.random.seed(42)
        close = 50000 + np.cumsum(np.random.randn(250) * 100)
        high = close + np.random.rand(250) * 200
        low = close - np.random.rand(250) * 200
        df = pd.DataFrame({"high": high, "low": low, "close": close})
        result = rd.detect_regime(df)
        assert result["regime"] != "unknown"
        assert 0 <= result["confidence"] <= 1
        assert isinstance(result["adx"], float)
        assert isinstance(result["atr_pct"], float)
