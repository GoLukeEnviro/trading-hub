"""Tests for primo/primo_api.py — pure helper functions.

Covers _freqtrade_to_spot, _build_signal, _extract_indicator_values,
_require_auth, _get_adapter_mod, _get_bot_mod, _get_llm_filter.
No HTTP, no FastAPI, no real filesystem outside tmp_path.
"""
from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock, patch

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


# =========================================================================
# _require_auth
# =========================================================================

class TestRequireAuth:
    """Test _require_auth FastAPI dependency with mocked PRIMO_API_KEY."""

    def _make_request(self, api_key: str | None = None) -> MagicMock:
        req = MagicMock()
        headers = {}
        if api_key is not None:
            headers["X-API-Key"] = api_key
        req.headers = headers
        return req

    def test_no_key_configured_allows_all(self) -> None:
        from primo.primo_api import _require_auth
        req = self._make_request(api_key=None)
        with patch("primo.primo_api.PRIMO_API_KEY", ""):
            # Should not raise
            _require_auth(req)

    def test_matching_key_allows(self) -> None:
        from primo.primo_api import _require_auth
        req = self._make_request(api_key="my-secret-key")
        with patch("primo.primo_api.PRIMO_API_KEY", "my-secret-key"):
            _require_auth(req)

    def test_wrong_key_raises(self) -> None:
        from primo.primo_api import _require_auth
        from fastapi import HTTPException
        req = self._make_request(api_key="wrong-key")
        with patch("primo.primo_api.PRIMO_API_KEY", "my-secret-key"):
            with pytest.raises(HTTPException) as exc:
                _require_auth(req)
        assert exc.value.status_code == 401

    def test_missing_header_raises(self) -> None:
        from primo.primo_api import _require_auth
        from fastapi import HTTPException
        req = self._make_request(api_key=None)
        with patch("primo.primo_api.PRIMO_API_KEY", "my-secret-key"):
            with pytest.raises(HTTPException) as exc:
                _require_auth(req)
        assert exc.value.status_code == 401

    def test_empty_key_header_raises(self) -> None:
        from primo.primo_api import _require_auth
        from fastapi import HTTPException
        req = self._make_request(api_key="")
        with patch("primo.primo_api.PRIMO_API_KEY", "my-secret-key"):
            with pytest.raises(HTTPException) as exc:
                _require_auth(req)
        assert exc.value.status_code == 401

    def test_case_sensitive_raises(self) -> None:
        from primo.primo_api import _require_auth
        from fastapi import HTTPException
        req = self._make_request(api_key="MY-SECRET-KEY")
        with patch("primo.primo_api.PRIMO_API_KEY", "my-secret-key"):
            with pytest.raises(HTTPException) as exc:
                _require_auth(req)
        assert exc.value.status_code == 401


# =========================================================================
# _get_adapter_mod
# =========================================================================

class TestGetAdapterMod:
    """Test _get_adapter_mod with mocked sys.modules."""

    def test_imports_adapter(self) -> None:
        from primo.primo_api import _get_adapter_mod
        mock_mod = MagicMock()
        mock_mod.fetch_ohlcv = MagicMock()
        with patch("primo.primo_api._adapter_mod", None):
            with patch.dict("sys.modules", {"crypto_data_adapter": mock_mod}):
                result = _get_adapter_mod()
        assert result is mock_mod

    def test_returns_cached(self) -> None:
        from primo.primo_api import _get_adapter_mod
        mock_mod = MagicMock()
        with patch("primo.primo_api._adapter_mod", mock_mod):
            result = _get_adapter_mod()
        assert result is mock_mod

    def test_import_error_raises(self) -> None:
        from primo.primo_api import _get_adapter_mod
        with patch("primo.primo_api._adapter_mod", None):
            # Remove from sys.modules so real import fails
            import sys
            sys.modules.pop("crypto_data_adapter", None)
            with pytest.raises(ImportError):
                _get_adapter_mod()


# =========================================================================
# _get_bot_mod
# =========================================================================

class TestGetBotMod:
    """Test _get_bot_mod with mocked imports."""

    def test_imports_bot(self) -> None:
        from primo.primo_api import _get_bot_mod
        mock_mod = MagicMock()
        mock_mod.calculate_signals = MagicMock()
        with patch("primo.primo_api._bot_mod", None):
            with patch.dict("sys.modules", {"primo_trading_bot_v0_4": mock_mod}):
                result = _get_bot_mod()
        assert result is mock_mod

    def test_returns_cached(self) -> None:
        from primo.primo_api import _get_bot_mod
        mock_mod = MagicMock()
        with patch("primo.primo_api._bot_mod", mock_mod):
            result = _get_bot_mod()
        assert result is mock_mod

    def test_import_error_raises(self) -> None:
        from primo.primo_api import _get_bot_mod
        with patch("primo.primo_api._bot_mod", None):
            import sys
            sys.modules.pop("primo_trading_bot_v0_4", None)
            with pytest.raises(ImportError):
                _get_bot_mod()


# =========================================================================
# _get_llm_filter
# =========================================================================

class TestGetLlmFilter:
    """Test _get_llm_filter with mocked imports."""

    def test_imports_filter(self) -> None:
        from primo.primo_api import _get_llm_filter
        mock_mod = MagicMock()
        mock_mod.call_llm_signal_filter = MagicMock()
        with patch("primo.primo_api._llm_filter_mod", None):
            with patch.dict("sys.modules", {"llm_signal_filter": mock_mod}):
                result = _get_llm_filter()
        assert result is mock_mod

    def test_returns_cached(self) -> None:
        from primo.primo_api import _get_llm_filter
        mock_mod = MagicMock()
        with patch("primo.primo_api._llm_filter_mod", mock_mod):
            result = _get_llm_filter()
        assert result is mock_mod

    def test_import_error_raises(self) -> None:
        from primo.primo_api import _get_llm_filter
        with patch("primo.primo_api._llm_filter_mod", None):
            with patch.dict("sys.modules", {"llm_signal_filter": None}, clear=False):
                with pytest.raises(ImportError):
                    _get_llm_filter()
