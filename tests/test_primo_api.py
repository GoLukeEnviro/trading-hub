"""Tests for primo/primo_api.py — pure helper functions.

Covers _freqtrade_to_spot, _build_signal, _extract_indicator_values.
No HTTP, no FastAPI, no real filesystem outside tmp_path.
"""
from __future__ import annotations

import os
from typing import Any

import pytest


# Patch LOG_DIR before any import of primo.primo_api
os.environ["PRIMO_LOG_DIR"] = "/tmp/primo_test_logs"


# =========================================================================
# _freqtrade_to_spot
# =========================================================================

class TestFreqtradeToSpot:
    def test_standard_pair(self) -> None:
        from primo.primo_api import _freqtrade_to_spot
        assert _freqtrade_to_spot("BTC/USDT:USDT") == "BTC/USDT"

    def test_no_suffix(self) -> None:
        from primo.primo_api import _freqtrade_to_spot
        assert _freqtrade_to_spot("BTC/USDT") == "BTC/USDT"

    def test_eth_pair(self) -> None:
        from primo.primo_api import _freqtrade_to_spot
        assert _freqtrade_to_spot("ETH/USDT:USDT") == "ETH/USDT"


# =========================================================================
# _build_signal
# =========================================================================

class TestBuildSignal:
    def test_minimal(self) -> None:
        from primo.primo_api import _build_signal
        signal = _build_signal("BTC/USDT:USDT", "long", 0.75, "strong trend")
        assert signal["pair"] == "BTC/USDT:USDT"
        assert signal["direction"] == "long"
        assert signal["confidence"] == 0.75
        assert signal["reason"] == "strong trend"
        assert signal["veto"] is True  # default
        assert signal["schema_version"] == "1.0"
        assert signal["source"] == "primo-agent"
        assert signal["risk_cap_percent"] == 1.0

    def test_with_llm_fields(self) -> None:
        from primo.primo_api import _build_signal
        signal = _build_signal(
            "ETH/USDT:USDT", "none", 0.0, "no edge",
            llm_verdict="veto", llm_model="gpt-4",
            llm_reason_short="bearish", market_regime="range", veto=True,
        )
        assert signal["llm_verdict"] == "veto"
        assert signal["llm_model"] == "gpt-4"
        assert signal["llm_reason_short"] == "bearish"
        assert signal["market_regime"] == "range"
        assert signal["veto"] is True

    def test_direction_none(self) -> None:
        from primo.primo_api import _build_signal
        signal = _build_signal("SOL/USDT:USDT", "none", 0.0, "no signal")
        assert signal["direction"] == "none"
        assert signal["veto"] is True

    def test_confidence_rounding(self) -> None:
        from primo.primo_api import _build_signal
        signal = _build_signal("BTC/USDT:USDT", "long", 0.12345, "test")
        assert signal["confidence"] == 0.1235  # round to 4 decimal places (banker's rounding)


# =========================================================================
# _extract_indicator_values
# =========================================================================

class TestExtractIndicatorValues:
    def test_dict_input(self) -> None:
        from primo.primo_api import _extract_indicator_values
        result = _extract_indicator_values({"rsi_14": 55.0, "ema_50": 50000.0})
        assert result["rsi_14"] == 55.0
        assert result["ema_50"] == 50000.0

    def test_empty_dict(self) -> None:
        from primo.primo_api import _extract_indicator_values
        result = _extract_indicator_values({})
        assert result == {}

    def test_none_input(self) -> None:
        from primo.primo_api import _extract_indicator_values
        result = _extract_indicator_values(None)
        assert result == {}

    def test_string_input(self) -> None:
        from primo.primo_api import _extract_indicator_values
        result = _extract_indicator_values("not a dict")
        assert result == {}
