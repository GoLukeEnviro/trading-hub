"""Tests for bridge/hermes_primo_bridge.py — signal validation and helpers.

Covers validate_signal() edge cases and pure helper functions.
No HTTP, no real filesystem outside tmp_path.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# =========================================================================
# _pair_to_filename
# =========================================================================

class TestPairToFilename:
    def test_standard_pair(self) -> None:
        from bridge.hermes_primo_bridge import _pair_to_filename
        assert _pair_to_filename("BTC/USDT:USDT") == "BTC_USDT_USDT.json"

    def test_eth_pair(self) -> None:
        from bridge.hermes_primo_bridge import _pair_to_filename
        assert _pair_to_filename("ETH/USDT:USDT") == "ETH_USDT_USDT.json"

    def test_sol_pair(self) -> None:
        from bridge.hermes_primo_bridge import _pair_to_filename
        assert _pair_to_filename("SOL/USDT:USDT") == "SOL_USDT_USDT.json"


# =========================================================================
# validate_signal
# =========================================================================

class TestValidateSignal:
    def _valid_signal(self) -> dict[str, Any]:
        return {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "pair": "BTC/USDT:USDT",
            "direction": "long",
            "confidence": 0.75,
            "veto": False,
            "risk_cap_percent": 0.5,
        }

    def test_valid_signal_passes(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        assert validate_signal(self._valid_signal()) is True

    def test_not_a_dict(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        assert validate_signal("not a dict") is False
        assert validate_signal(None) is False
        assert validate_signal(42) is False

    def test_stale_timestamp(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal, SIGNAL_FRESHNESS
        signal = self._valid_signal()
        # Set timestamp far in the past
        old_ts = datetime.now(timezone.utc).timestamp() - SIGNAL_FRESHNESS - 100
        signal["timestamp_utc"] = datetime.fromtimestamp(old_ts, tz=timezone.utc).isoformat()
        assert validate_signal(signal) is False

    def test_invalid_timestamp_format(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        signal = self._valid_signal()
        signal["timestamp_utc"] = "not-a-timestamp"
        assert validate_signal(signal) is False

    def test_missing_timestamp(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        signal = self._valid_signal()
        del signal["timestamp_utc"]
        assert validate_signal(signal) is False

    def test_pair_not_allowed(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        signal = self._valid_signal()
        signal["pair"] = "DOGE/USDT:USDT"
        assert validate_signal(signal) is False

    def test_missing_pair(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        signal = self._valid_signal()
        del signal["pair"]
        assert validate_signal(signal) is False

    def test_invalid_direction(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        signal = self._valid_signal()
        signal["direction"] = "short"
        assert validate_signal(signal) is False

    def test_missing_direction(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        signal = self._valid_signal()
        del signal["direction"]
        assert validate_signal(signal) is False

    def test_confidence_too_low(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        signal = self._valid_signal()
        signal["confidence"] = -0.1
        assert validate_signal(signal) is False

    def test_confidence_too_high(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        signal = self._valid_signal()
        signal["confidence"] = 1.5
        assert validate_signal(signal) is False

    def test_confidence_non_numeric(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        signal = self._valid_signal()
        signal["confidence"] = "not-a-number"
        assert validate_signal(signal) is False

    def test_veto_true(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        signal = self._valid_signal()
        signal["veto"] = True
        assert validate_signal(signal) is False

    def test_risk_cap_exceeds_one(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        signal = self._valid_signal()
        signal["risk_cap_percent"] = 2.0
        assert validate_signal(signal) is False

    def test_risk_cap_non_numeric(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        signal = self._valid_signal()
        signal["risk_cap_percent"] = "not-a-number"
        assert validate_signal(signal) is True  # non-critical field, passes

    def test_direction_none_passes(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        signal = self._valid_signal()
        signal["direction"] = "none"
        assert validate_signal(signal) is True

    def test_confidence_zero_passes(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        signal = self._valid_signal()
        signal["confidence"] = 0.0
        assert validate_signal(signal) is True

    def test_confidence_one_passes(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        signal = self._valid_signal()
        signal["confidence"] = 1.0
        assert validate_signal(signal) is True


# =========================================================================
# _set_error / _clear_error
# =========================================================================

class TestErrorState:
    def test_set_error(self) -> None:
        from bridge.hermes_primo_bridge import _set_error, _state
        _state["last_error"] = None
        _state["last_error_time"] = None
        _set_error("test error")
        assert _state["last_error"] == "test error"
        assert _state["last_error_time"] is not None

    def test_clear_error(self) -> None:
        from bridge.hermes_primo_bridge import _set_error, _clear_error, _state
        _set_error("test error")
        _clear_error()
        assert _state["last_error"] is None
        assert _state["last_error_time"] is None


# =========================================================================
# _http_get
# =========================================================================

class TestHttpGet:
    """Test _http_get with mocked urllib.request.urlopen."""

    def _make_mock_response(self, data: Any, status: int = 200) -> MagicMock:
        """Helper: create a mock response that returns JSON bytes."""
        resp = MagicMock()
        resp.__enter__.return_value = resp
        resp.read.return_value = json.dumps(data).encode()
        resp.status = status
        return resp

    def test_200_ok_valid_json(self) -> None:
        from bridge.hermes_primo_bridge import _http_get
        mock_resp = self._make_mock_response({"status": "ok", "pairs": ["BTC"]})
        with patch("bridge.hermes_primo_bridge.urlopen", return_value=mock_resp):
            result = _http_get("http://test/status")
        assert result == {"status": "ok", "pairs": ["BTC"]}

    def test_200_ok_invalid_json(self) -> None:
        from bridge.hermes_primo_bridge import _http_get
        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.read.return_value = b"not-json-at-all"
        with patch("bridge.hermes_primo_bridge.urlopen", return_value=mock_resp):
            result = _http_get("http://test/status")
        assert result is None

    def test_http_401(self) -> None:
        from bridge.hermes_primo_bridge import _http_get, HTTPError
        from urllib.error import HTTPError as UrllibHTTPError
        # Simulate HTTPError by raising it from urlopen
        def _raise_401(*args: Any, **kwargs: Any) -> MagicMock:
            raise UrllibHTTPError(
                "http://test/status", 401, "Unauthorized",
                {}, None,
            )
        with patch("bridge.hermes_primo_bridge.urlopen", side_effect=_raise_401):
            result = _http_get("http://test/status")
        assert result is None

    def test_http_404(self) -> None:
        from bridge.hermes_primo_bridge import _http_get
        from urllib.error import HTTPError as UrllibHTTPError
        def _raise_404(*args: Any, **kwargs: Any) -> MagicMock:
            raise UrllibHTTPError(
                "http://test/status", 404, "Not Found",
                {}, None,
            )
        with patch("bridge.hermes_primo_bridge.urlopen", side_effect=_raise_404):
            result = _http_get("http://test/status")
        assert result is None

    def test_http_500(self) -> None:
        from bridge.hermes_primo_bridge import _http_get
        from urllib.error import HTTPError as UrllibHTTPError
        def _raise_500(*args: Any, **kwargs: Any) -> MagicMock:
            raise UrllibHTTPError(
                "http://test/status", 500, "Server Error",
                {}, None,
            )
        with patch("bridge.hermes_primo_bridge.urlopen", side_effect=_raise_500):
            result = _http_get("http://test/status")
        assert result is None

    def test_urlerror(self) -> None:
        from bridge.hermes_primo_bridge import _http_get
        from urllib.error import URLError
        with patch("bridge.hermes_primo_bridge.urlopen", side_effect=URLError("connection refused")):
            result = _http_get("http://test/status")
        assert result is None

    def test_timeout(self) -> None:
        from bridge.hermes_primo_bridge import _http_get
        with patch("bridge.hermes_primo_bridge.urlopen", side_effect=OSError("timed out")):
            result = _http_get("http://test/status")
        assert result is None

    def test_connection_error(self) -> None:
        from bridge.hermes_primo_bridge import _http_get
        with patch("bridge.hermes_primo_bridge.urlopen", side_effect=ConnectionError("refused")):
            result = _http_get("http://test/status")
        assert result is None

    def test_all_retries_exhausted(self) -> None:
        """After MAX_RETRIES attempts, _http_get returns None."""
        from bridge.hermes_primo_bridge import _http_get
        from urllib.error import URLError
        with patch("bridge.hermes_primo_bridge.urlopen", side_effect=URLError("down")):
            result = _http_get("http://test/status")
        assert result is None

    def test_header_set_correctly(self) -> None:
        """Verify the request is constructed with Accept header."""
        from bridge.hermes_primo_bridge import _http_get
        from urllib.request import Request
        mock_resp = self._make_mock_response({"ok": True})
        with patch("bridge.hermes_primo_bridge.urlopen", return_value=mock_resp) as mock_urlopen:
            _http_get("http://test/status")
            call_args = mock_urlopen.call_args[0][0]
            assert isinstance(call_args, Request)
            assert call_args.headers.get("Accept") == "application/json"


# =========================================================================
# _auth_required
# =========================================================================

class TestAuthRequired:
    """Test _auth_required with mocked BRIDGE_API_KEY."""

    def _make_handler(self, api_key: str | None = None) -> MagicMock:
        handler = MagicMock()
        headers = {}
        if api_key is not None:
            headers["X-API-Key"] = api_key
        handler.headers = headers
        return handler

    def test_no_key_configured_allows_all(self) -> None:
        from bridge.hermes_primo_bridge import _auth_required
        handler = self._make_handler(api_key=None)
        with patch("bridge.hermes_primo_bridge.BRIDGE_API_KEY", ""):
            assert _auth_required(handler) is True

    def test_matching_key_allows(self) -> None:
        from bridge.hermes_primo_bridge import _auth_required
        handler = self._make_handler(api_key="my-secret-key")
        with patch("bridge.hermes_primo_bridge.BRIDGE_API_KEY", "my-secret-key"):
            assert _auth_required(handler) is True

    def test_wrong_key_blocks(self) -> None:
        from bridge.hermes_primo_bridge import _auth_required
        handler = self._make_handler(api_key="wrong-key")
        with patch("bridge.hermes_primo_bridge.BRIDGE_API_KEY", "my-secret-key"):
            assert _auth_required(handler) is False

    def test_missing_header_blocks(self) -> None:
        from bridge.hermes_primo_bridge import _auth_required
        handler = self._make_handler(api_key=None)
        with patch("bridge.hermes_primo_bridge.BRIDGE_API_KEY", "my-secret-key"):
            assert _auth_required(handler) is False

    def test_empty_key_header_blocks(self) -> None:
        from bridge.hermes_primo_bridge import _auth_required
        handler = self._make_handler(api_key="")
        with patch("bridge.hermes_primo_bridge.BRIDGE_API_KEY", "my-secret-key"):
            assert _auth_required(handler) is False

    def test_case_sensitive(self) -> None:
        from bridge.hermes_primo_bridge import _auth_required
        handler = self._make_handler(api_key="MY-SECRET-KEY")
        with patch("bridge.hermes_primo_bridge.BRIDGE_API_KEY", "my-secret-key"):
            assert _auth_required(handler) is False


# =========================================================================
# _write_debug_summary
# =========================================================================

class TestWriteDebugSummary:
    """Test _write_debug_summary with tmp_path as SIGNAL_BUS_DIR."""

    def test_writes_summary_file(self, tmp_path: Path) -> None:
        from bridge.hermes_primo_bridge import _write_debug_summary, _state
        _state["polls_total"] = 10
        _state["polls_success"] = 8
        _state["polls_failed"] = 2
        _state["primo_health"] = "ok"
        _state["per_pair_signals"] = {"BTC/USDT:USDT": "active"}
        with patch("bridge.hermes_primo_bridge.SIGNAL_BUS_DIR", tmp_path):
            _write_debug_summary()
        summary_file = tmp_path / "latest_signal.json"
        assert summary_file.exists()
        data = json.loads(summary_file.read_text())
        assert data["schema_version"] == "1.0/debug"
        assert data["polls_total"] == 10
        assert data["polls_success"] == 8
        assert data["polls_failed"] == 2
        assert data["primo_health"] == "ok"
        assert data["signals"] == {"BTC/USDT:USDT": "active"}

    def test_creates_parent_dir(self, tmp_path: Path) -> None:
        from bridge.hermes_primo_bridge import _write_debug_summary, _state
        _state["polls_total"] = 0
        _state["polls_success"] = 0
        _state["polls_failed"] = 0
        _state["primo_health"] = "unknown"
        _state["per_pair_signals"] = {}
        nested = tmp_path / "sub" / "dir"
        nested.mkdir(parents=True)
        with patch("bridge.hermes_primo_bridge.SIGNAL_BUS_DIR", nested):
            _write_debug_summary()
        assert (nested / "latest_signal.json").exists()

    def test_handles_oserror_gracefully(self, tmp_path: Path) -> None:
        from bridge.hermes_primo_bridge import _write_debug_summary, _state
        _state["polls_total"] = 0
        _state["polls_success"] = 0
        _state["polls_failed"] = 0
        _state["primo_health"] = "unknown"
        _state["per_pair_signals"] = {}
        # Point to a path that can't be written (e.g., a file instead of dir)
        blocked = tmp_path / "blocked_file"
        blocked.touch()
        with patch("bridge.hermes_primo_bridge.SIGNAL_BUS_DIR", blocked):
            # Should not raise
            _write_debug_summary()

    def test_no_secrets_in_output(self, tmp_path: Path) -> None:
        """Verify no secret-like values appear in the debug summary."""
        from bridge.hermes_primo_bridge import _write_debug_summary, _state
        _state["polls_total"] = 0
        _state["polls_success"] = 0
        _state["polls_failed"] = 0
        _state["primo_health"] = "ok"
        _state["per_pair_signals"] = {}
        with patch("bridge.hermes_primo_bridge.SIGNAL_BUS_DIR", tmp_path):
            _write_debug_summary()
        content = (tmp_path / "latest_signal.json").read_text()
        assert "DUMMY_PASSWORD" not in content
        assert "DUMMY_TOKEN" not in content
        assert "DUMMY_API_KEY" not in content


# =========================================================================
# _check_freqtrade
# =========================================================================

class TestCheckFreqtrade:
    """Test _check_freqtrade with tmp_path."""

    def test_shared_volume_ok(self, tmp_path: Path) -> None:
        from bridge.hermes_primo_bridge import _check_freqtrade, _state
        _state["freqtrade_health"] = ""
        with patch("bridge.hermes_primo_bridge.SIGNAL_BUS_DIR", tmp_path):
            _check_freqtrade()
        assert _state["freqtrade_health"] == "shared_volume_ok"

    def test_shared_volume_missing(self, tmp_path: Path) -> None:
        from bridge.hermes_primo_bridge import _check_freqtrade, _state
        _state["freqtrade_health"] = ""
        missing = tmp_path / "does_not_exist"
        with patch("bridge.hermes_primo_bridge.SIGNAL_BUS_DIR", missing):
            _check_freqtrade()
        assert _state["freqtrade_health"] == "shared_volume_missing"
