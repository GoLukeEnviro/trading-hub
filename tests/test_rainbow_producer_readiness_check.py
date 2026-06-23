"""
Tests for rainbow_producer_readiness_check.py
Run: python -m pytest tests/test_rainbow_producer_readiness_check.py -q
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock

import pytest

# Import the module under test
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "orchestrator" / "scripts"))
import rainbow_producer_readiness_check as rrc


# ── Helper: build a mock urlopen that returns the given byte payload ─────────
def _mock_urlopen_factory(*payloads: bytes):
    """Returns a side_effect function that cycles through payloads for /health, /signals.

    Each call returns a proper context-manager mock whose __enter__ returns a mock
    with .read() → the corresponding bytes.
    """
    idx = [0]  # mutable counter

    def side_effect(req, timeout=None):
        data = payloads[idx[0] % len(payloads)]
        idx[0] += 1
        ctx = MagicMock()
        ctx.__enter__.return_value.read.return_value = data
        return ctx

    return side_effect


def _make_mock_response(data: bytes):
    """Simple context manager mock returning data bytes on .read()."""
    resp = MagicMock()
    resp.read.return_value = data
    ctx = MagicMock()
    ctx.__enter__.return_value = resp
    return ctx


# ── Unit: _iso_to_dt ────────────────────────────────────────────────────────
class TestIsoToDt:
    def test_z_suffix(self):
        dt = rrc._iso_to_dt("2026-06-23T08:00:00Z")
        assert dt.isoformat() == "2026-06-23T08:00:00+00:00"

    def test_offset_suffix(self):
        dt = rrc._iso_to_dt("2026-06-23T08:00:00+00:00")
        assert dt.isoformat() == "2026-06-23T08:00:00+00:00"

    def test_microseconds(self):
        dt = rrc._iso_to_dt("2026-06-23T08:00:00.123456+00:00")
        assert dt.microsecond == 123456


# ── Unit: _fetch_json ───────────────────────────────────────────────────────
class TestFetchJson:
    def test_valid_json_object(self):
        with patch("urllib.request.urlopen", return_value=_make_mock_response(b'{"status": "healthy"}')):
            result = rrc._fetch_json("http://localhost:8000/health")
        assert result == {"status": "healthy"}

    def test_valid_json_list(self):
        with patch("urllib.request.urlopen", return_value=_make_mock_response(b'[{"timestamp": "2026-01-01T00:00:00Z"}]')):
            result = rrc._fetch_json("http://localhost:8000/signals/latest")
        assert isinstance(result, list)
        assert len(result) == 1

    def test_connection_refused(self):
        with patch("urllib.request.urlopen", side_effect=OSError("Connection refused")):
            result = rrc._fetch_json("http://localhost:8000/health")
        assert result is None

    def test_malformed_json(self):
        with patch("urllib.request.urlopen", return_value=_make_mock_response(b"not json")):
            result = rrc._fetch_json("http://localhost:8000/health")
        assert result is None


# ── Unit: check_health ──────────────────────────────────────────────────────
class TestCheckHealth:
    def test_healthy(self):
        with patch("urllib.request.urlopen", return_value=_make_mock_response(b'{"status": "healthy"}')):
            result = rrc.check_health("http://127.0.0.1:8000")
        assert result["reachable"] is True
        assert result["status"] == "healthy"

    def test_unreachable(self):
        with patch("urllib.request.urlopen", side_effect=OSError("refused")):
            result = rrc.check_health("http://127.0.0.1:8000")
        assert result["reachable"] is False
        assert result["status"] == "unreachable"

    def test_unexpected_type(self):
        with patch("urllib.request.urlopen", return_value=_make_mock_response(b'"not a dict"')):
            result = rrc.check_health("http://127.0.0.1:8000")
        assert result["reachable"] is True
        assert result["status"] == "unexpected_type"


# ── Unit: check_signals ────────────────────────────────────────────────────
class TestCheckSignals:
    def test_valid_signals_list(self):
        payload = [
            {"timestamp": "2026-06-23T08:00:00Z", "signal_type": "technical", "asset": "BTCUSDT"},
            {"timestamp": "2026-06-23T08:15:00Z", "signal_type": "technical", "asset": "ETHUSDT"},
        ]
        with patch("urllib.request.urlopen", return_value=_make_mock_response(json.dumps(payload).encode())):
            result = rrc.check_signals("http://127.0.0.1:8000")
        assert result["reachable"] is True
        assert result["count"] == 2
        assert result["freshest_ts"] == "2026-06-23T08:15:00Z"

    def test_valid_signals_dict_wrapper(self):
        payload = {"signals": [{"timestamp": "2026-06-23T08:00:00Z"}]}
        with patch("urllib.request.urlopen", return_value=_make_mock_response(json.dumps(payload).encode())):
            result = rrc.check_signals("http://127.0.0.1:8000")
        assert result["reachable"] is True
        assert result["count"] == 1

    def test_empty_signals(self):
        with patch("urllib.request.urlopen", return_value=_make_mock_response(b"[]")):
            result = rrc.check_signals("http://127.0.0.1:8000")
        assert result["reachable"] is True
        assert result["count"] == 0
        assert result.get("freshest_ts") is None

    def test_no_timestamps(self):
        payload = [{"asset": "BTCUSDT"}, {"asset": "ETHUSDT"}]
        with patch("urllib.request.urlopen", return_value=_make_mock_response(json.dumps(payload).encode())):
            result = rrc.check_signals("http://127.0.0.1:8000")
        assert result["reachable"] is True
        assert result["count"] == 2
        assert result.get("freshest_ts") is None

    def test_unreachable(self):
        with patch("urllib.request.urlopen", side_effect=OSError("refused")):
            result = rrc.check_signals("http://127.0.0.1:8000")
        assert result["reachable"] is False

    def test_stale_signals(self):
        payload = [{"timestamp": "2025-01-01T00:00:00Z"}]
        with patch("urllib.request.urlopen", return_value=_make_mock_response(json.dumps(payload).encode())):
            result = rrc.check_signals("http://127.0.0.1:8000")
        assert result["reachable"] is True
        assert result["age_seconds"] > 900

    def test_unparseable_timestamp(self):
        payload = [{"timestamp": "not-a-date"}]
        with patch("urllib.request.urlopen", return_value=_make_mock_response(json.dumps(payload).encode())):
            result = rrc.check_signals("http://127.0.0.1:8000")
        assert result["reachable"] is True
        assert "error" in result


# ── Integration: main() exit codes ──────────────────────────────────────────
class TestMainExitCodes:
    def _patch_and_run(self, health_bytes: bytes, signals_bytes: bytes, extra_argv=None) -> int:
        """Run rrc.main() with mocked urlopen and controlled argv."""
        with (
            patch("urllib.request.urlopen", new=_mock_urlopen_factory(health_bytes, signals_bytes)),
            patch("sys.argv", ["check"] + (extra_argv or [])),
        ):
            try:
                return rrc.main()
            except SystemExit as e:
                return e.code

    def test_healthy_producer_exit_zero(self):
        from datetime import datetime, timezone
        now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        code = self._patch_and_run(
            b'{"status": "healthy"}',
            json.dumps([
                {"timestamp": now_ts},
                {"timestamp": now_ts},
            ]).encode(),
        )
        assert code == 0

    def test_unreachable_exit_one(self):
        with (
            patch("urllib.request.urlopen", side_effect=OSError("refused")),
            patch("sys.argv", ["check"]),
        ):
            try:
                code = rrc.main()
            except SystemExit as e:
                code = e.code
        assert code == 1

    def test_stale_signals_exit_one(self):
        code = self._patch_and_run(
            b'{"status": "healthy"}',
            json.dumps([{"timestamp": "2025-01-01T00:00:00Z"}]).encode(),
        )
        assert code == 1

    def test_empty_signals_exit_one(self):
        code = self._patch_and_run(
            b'{"status": "healthy"}',
            b"[]",
        )
        assert code == 1

    def test_json_output(self):
        from datetime import datetime, timezone
        now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        health_json = b'{"status": "healthy"}'
        signals_json = json.dumps([{"timestamp": now_ts}]).encode()
        with (
            patch("urllib.request.urlopen", new=_mock_urlopen_factory(health_json, signals_json)),
            patch("sys.argv", ["check", "--json"]),
        ):
            try:
                code = rrc.main()
            except SystemExit as e:
                code = e.code
        # Dynamic "now" timestamp → GREEN
        assert code == 0


# ── No secrets / no auth headers ───────────────────────────────────────────
class TestNoSecretsNoAuth:
    def test_no_auth_headers_in_request(self):
        """Verify _fetch_json does not send Authorization or X-API-Key headers."""
        captured_req = {}

        class MockResp:
            def read(self):
                return b"{}"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        def capture_urlopen(req, timeout=None):
            captured_req["headers"] = dict(req.headers)
            return MockResp()

        with patch("urllib.request.urlopen", side_effect=capture_urlopen):
            rrc._fetch_json("http://127.0.0.1:8000/health")

        headers = captured_req.get("headers", {})
        assert "Authorization" not in headers
        assert "X-Api-Key" not in headers

    def test_no_secret_strings_in_source(self):
        """Sanity: source code should not contain credential patterns."""
        src = (Path(__file__).resolve().parents[1] / "orchestrator" / "scripts" / "rainbow_producer_readiness_check.py").read_text()
        assert "api_key" not in src.lower()
        assert "secret" not in src.lower()
        assert "password" not in src.lower()
        assert "token" not in src.lower()


# ── CLI args ────────────────────────────────────────────────────────────────
class TestCliArgs:
    def script_path(self):
        return str(
            Path(__file__).resolve().parents[1]
            / "orchestrator"
            / "scripts"
            / "rainbow_producer_readiness_check.py"
        )

    def _run(self, *args) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, self.script_path(), *args],
            capture_output=True,
            text=True,
            timeout=15,
        )

    def test_base_url_override(self):
        proc = self._run("--base-url", "http://127.0.0.1:9999", "--freshness-max-seconds", "999999")
        assert proc.returncode == 1
        assert "unreachable" in proc.stdout.lower()

    def test_default_args_parse(self):
        proc = self._run("--help")
        assert proc.returncode == 0
        assert "--base-url" in proc.stdout
        assert "--freshness-max-seconds" in proc.stdout
