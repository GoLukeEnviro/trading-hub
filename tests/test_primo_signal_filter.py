"""Tests for primo/llm_signal_filter.py — context building and signal combination.

DECOMMISSIONED — Issue #465
---------------------------
Primo was decommissioned in Phase 44-45 (replaced by SI-v2 autonomous loop).
These tests cover ``primo/llm_signal_filter.py`` (decommissioned), NOT the
retained ``freqtrade/shared/primo_signal.py`` kill-switch integration boundary.
Tests are SKIPPED by default and will be removed when the primo/ directory
is cleaned up.

Covers build_llm_context, _fmt, combine_technical_and_llm_signal.
No LLM calls, no HTTP, no real filesystem outside tmp_path.
"""
from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.skip(reason="Primo decommissioned (Phase 44-45, ADR-2026-07-01) — Issue #465")


# =========================================================================
# _fmt
# =========================================================================

class TestFmt:
    def test_none(self) -> None:
        from primo.llm_signal_filter import _fmt
        assert _fmt(None) == "N/A"

    def test_na_string(self) -> None:
        from primo.llm_signal_filter import _fmt
        assert _fmt("N/A") == "N/A"

    def test_float(self) -> None:
        from primo.llm_signal_filter import _fmt
        assert _fmt(3.14159) == "3.1416"

    def test_int(self) -> None:
        from primo.llm_signal_filter import _fmt
        assert _fmt(42) == "42.0000"

    def test_string(self) -> None:
        from primo.llm_signal_filter import _fmt
        assert _fmt("hello") == "hello"


# =========================================================================
# build_llm_context
# =========================================================================

class TestBuildLlmContext:
    def test_happy_path(self) -> None:
        from primo.llm_signal_filter import build_llm_context
        ctx = build_llm_context(
            pair="BTC/USDT",
            pair_freqtrade="BTC/USDT:USDT",
            timeframe="1h",
            indicators={
                "rsi_14": 55.0,
                "ema_50": 50000.0,
                "ema_200": 48000.0,
                "adx_14": 25.0,
                "atr_percent": 0.02,
                "bb_width": 0.05,
                "bb_position_pct": 0.5,
                "volume_ratio": 1.2,
            },
            latest_price=51000.0,
            technical_result={"action": "BUY", "confidence": 0.7, "signal_quality": "good",
                              "strategy_fit": "trend", "reasons": ["strong_trend"]},
        )
        assert ctx["pair"] == "BTC/USDT"
        assert ctx["pair_freqtrade"] == "BTC/USDT:USDT"
        assert ctx["timeframe"] == "1h"
        assert ctx["ema_trend"] == "bullish"  # 50000 > 48000
        assert ctx["baseline_action"] == "BUY"
        assert ctx["baseline_confidence"] == "0.70"

    def test_bearish_ema_trend(self) -> None:
        from primo.llm_signal_filter import build_llm_context
        ctx = build_llm_context(
            pair="ETH/USDT", pair_freqtrade="ETH/USDT:USDT", timeframe="1h",
            indicators={"ema_50": 3000.0, "ema_200": 3200.0},
            latest_price=3100.0,
            technical_result={"action": "WATCH", "confidence": 0.0},
        )
        assert ctx["ema_trend"] == "bearish"

    def test_unknown_ema_trend(self) -> None:
        from primo.llm_signal_filter import build_llm_context
        ctx = build_llm_context(
            pair="SOL/USDT", pair_freqtrade="SOL/USDT:USDT", timeframe="1h",
            indicators={},
            latest_price=100.0,
            technical_result={"action": "WATCH", "confidence": 0.0},
        )
        assert ctx["ema_trend"] == "unknown"

    def test_missing_indicators(self) -> None:
        from primo.llm_signal_filter import build_llm_context
        ctx = build_llm_context(
            pair="BTC/USDT", pair_freqtrade="BTC/USDT:USDT", timeframe="1h",
            indicators={},
            latest_price=50000.0,
            technical_result={"action": "HOLD", "confidence": 0.0},
        )
        assert ctx["rsi_14"] == "N/A"
        assert ctx["ema_50"] == "N/A"
        assert ctx["ema_trend"] == "unknown"

    def test_alternative_indicator_keys(self) -> None:
        from primo.llm_signal_filter import build_llm_context
        ctx = build_llm_context(
            pair="BTC/USDT", pair_freqtrade="BTC/USDT:USDT", timeframe="1h",
            indicators={"RSI": 60.0, "EMA_50": 51000.0, "EMA_200": 49000.0},
            latest_price=50000.0,
            technical_result={"action": "BUY", "confidence": 0.6},
        )
        assert ctx["rsi_14"] == "60.0000"
        assert ctx["ema_trend"] == "bullish"


# =========================================================================
# combine_technical_and_llm_signal
# =========================================================================

class TestCombineTechnicalAndLlmSignal:
    def test_both_buy_above_threshold(self) -> None:
        from primo.llm_signal_filter import combine_technical_and_llm_signal
        result = combine_technical_and_llm_signal(
            technical_result={"action": "BUY", "confidence": 0.8},
            llm_verdict={"action": "BUY", "confidence": 0.7, "reasoning_summary": "bullish"},
            pair="BTC/USDT:USDT",
        )
        assert result["direction"] == "long"
        assert result["confidence"] == 0.7  # min(0.8, 0.7)
        assert result["veto"] is False

    def test_both_buy_below_threshold(self) -> None:
        from primo.llm_signal_filter import combine_technical_and_llm_signal, MIN_CONFIDENCE_FOR_LONG
        result = combine_technical_and_llm_signal(
            technical_result={"action": "BUY", "confidence": 0.5},
            llm_verdict={"action": "BUY", "confidence": 0.4, "reasoning_summary": "weak"},
            pair="BTC/USDT:USDT",
        )
        assert result["direction"] == "none"
        assert result["veto"] is True

    def test_tech_buy_llm_sell(self) -> None:
        from primo.llm_signal_filter import combine_technical_and_llm_signal
        result = combine_technical_and_llm_signal(
            technical_result={"action": "BUY", "confidence": 0.8},
            llm_verdict={"action": "SELL", "confidence": 0.6, "reasoning_summary": "bearish"},
            pair="BTC/USDT:USDT",
        )
        assert result["direction"] == "none"
        assert result["veto"] is True

    def test_tech_buy_llm_watch(self) -> None:
        from primo.llm_signal_filter import combine_technical_and_llm_signal
        result = combine_technical_and_llm_signal(
            technical_result={"action": "BUY", "confidence": 0.8},
            llm_verdict={"action": "WATCH", "confidence": 0.0, "reasoning_summary": "neutral"},
            pair="BTC/USDT:USDT",
        )
        assert result["direction"] == "none"

    def test_tech_watch_llm_buy(self) -> None:
        from primo.llm_signal_filter import combine_technical_and_llm_signal
        result = combine_technical_and_llm_signal(
            technical_result={"action": "WATCH", "confidence": 0.0},
            llm_verdict={"action": "BUY", "confidence": 0.9, "reasoning_summary": "bullish"},
            pair="BTC/USDT:USDT",
        )
        assert result["direction"] == "none"

    def test_tech_hold_llm_buy(self) -> None:
        from primo.llm_signal_filter import combine_technical_and_llm_signal
        result = combine_technical_and_llm_signal(
            technical_result={"action": "HOLD", "confidence": 0.0},
            llm_verdict={"action": "BUY", "confidence": 0.9, "reasoning_summary": "bullish"},
            pair="BTC/USDT:USDT",
        )
        assert result["direction"] == "none"

    def test_market_regime_mapping(self) -> None:
        from primo.llm_signal_filter import combine_technical_and_llm_signal
        result = combine_technical_and_llm_signal(
            technical_result={"action": "BUY", "confidence": 0.8, "regime": "trending"},
            llm_verdict={"action": "BUY", "confidence": 0.7, "reasoning_summary": "bullish"},
            pair="BTC/USDT:USDT",
        )
        assert result["market_regime"] == "trend"

    def test_market_regime_ranging(self) -> None:
        from primo.llm_signal_filter import combine_technical_and_llm_signal
        result = combine_technical_and_llm_signal(
            technical_result={"action": "WATCH", "confidence": 0.0, "regime": "ranging"},
            llm_verdict={"action": "WATCH", "confidence": 0.0, "reasoning_summary": ""},
            pair="BTC/USDT:USDT",
        )
        assert result["market_regime"] == "range"

    def test_market_regime_volatile(self) -> None:
        from primo.llm_signal_filter import combine_technical_and_llm_signal
        result = combine_technical_and_llm_signal(
            technical_result={"action": "WATCH", "confidence": 0.0, "regime": "volatile"},
            llm_verdict={"action": "WATCH", "confidence": 0.0, "reasoning_summary": ""},
            pair="BTC/USDT:USDT",
        )
        assert result["market_regime"] == "high_volatility"

    def test_market_regime_unknown(self) -> None:
        from primo.llm_signal_filter import combine_technical_and_llm_signal
        result = combine_technical_and_llm_signal(
            technical_result={"action": "WATCH", "confidence": 0.0},
            llm_verdict={"action": "WATCH", "confidence": 0.0, "reasoning_summary": ""},
            pair="BTC/USDT:USDT",
        )
        assert result["market_regime"] == "unknown"

    def test_llm_verdict_category(self) -> None:
        from primo.llm_signal_filter import combine_technical_and_llm_signal
        result = combine_technical_and_llm_signal(
            technical_result={"action": "BUY", "confidence": 0.8},
            llm_verdict={"action": "BUY", "confidence": 0.7, "reasoning_summary": "bullish"},
            pair="BTC/USDT:USDT",
        )
        assert result["llm_verdict"] == "approve"

    def test_llm_verdict_veto(self) -> None:
        from primo.llm_signal_filter import combine_technical_and_llm_signal
        result = combine_technical_and_llm_signal(
            technical_result={"action": "BUY", "confidence": 0.8},
            llm_verdict={"action": "SELL", "confidence": 0.6, "reasoning_summary": "bearish"},
            pair="BTC/USDT:USDT",
        )
        assert result["llm_verdict"] == "veto"


# =========================================================================
# call_llm_signal_filter (disabled path only — no real LLM)
# =========================================================================

class TestCallLlmSignalFilter:
    def test_disabled_returns_watch(self, monkeypatch: Any) -> None:
        from primo.llm_signal_filter import call_llm_signal_filter
        monkeypatch.setattr("primo.llm_signal_filter.LLM_ENABLED", False)
        result = call_llm_signal_filter({})
        assert result["action"] == "WATCH"
        assert result["confidence"] == 0.0
        assert "disabled" in result["reasoning_summary"]
