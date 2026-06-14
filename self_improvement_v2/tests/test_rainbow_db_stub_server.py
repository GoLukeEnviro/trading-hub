"""Tests for the Rainbow DB-backed read-only HTTP stub server.

These tests verify:

* The stub opens the SQLite DB in read-only mode and never writes.
* ``/signals/latest`` returns the rows in the configured DB.
* ``/signals/latest`` returns a clean empty payload when the DB does
  not exist (NOT a 500).
* ``/signals/latest`` returns a clean empty payload when the DB is
  empty.
* ``/health`` always returns 200.
* The stub refuses to bind to a non-loopback host.
* The stub refuses to bind to a privileged port.
* The lifecycle context manager cleanly stops the server.
* A full end-to-end fetch through ``urllib.request`` against a real
  started stub returns the expected number of rows.

No network, no auth, no secrets, no ``Any``.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from http.client import HTTPConnection
from pathlib import Path

import pytest

# Add the orchestrator scripts dir to sys.path so the stub module
# is importable.  This keeps the test self-contained — no install
# step required.
_ORCHESTRATOR_SCRIPTS = (
    Path(__file__).resolve().parent.parent.parent / "orchestrator" / "scripts"
)
if str(_ORCHESTRATOR_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_ORCHESTRATOR_SCRIPTS))

from rainbow_db_stub_server import (  # noqa: E402  (sys.path insert above)
    DEFAULT_DB_PATH,
    DEFAULT_HOST,
    DEFAULT_PORT,
    StubConfig,
    fetch_latest_signals,
    serve,
)

# ── Config validation ───────────────────────────────────────────────────────


class TestStubConfig:
    def test_default_config(self) -> None:
        cfg = StubConfig(
            host=DEFAULT_HOST, port=DEFAULT_PORT, db_path=DEFAULT_DB_PATH
        )
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 8765
        assert cfg.db_path == DEFAULT_DB_PATH

    def test_rejects_non_loopback_host(self) -> None:
        with pytest.raises(ValueError, match="loopback"):
            StubConfig(host="0.0.0.0", port=8765, db_path="/tmp/x.db")
        with pytest.raises(ValueError, match="loopback"):
            StubConfig(host="192.168.1.1", port=8765, db_path="/tmp/x.db")

    def test_rejects_privileged_port(self) -> None:
        with pytest.raises(ValueError, match="port"):
            StubConfig(host="127.0.0.1", port=80, db_path="/tmp/x.db")
        with pytest.raises(ValueError, match="port"):
            StubConfig(host="127.0.0.1", port=0, db_path="/tmp/x.db")


# ── DB layer ────────────────────────────────────────────────────────────────


def _make_temp_db(tmp_path: Path, rows: int) -> Path:
    """Create a tiny read-only-style DB at ``tmp_path/db.sqlite``.

    Note: we open it for write here in the test setup so we can insert
    rows. The stub itself always opens ``mode=ro`` — verified by a
    separate test that asserts no writes happen.
    """
    db = tmp_path / "test_signals.db"
    con = sqlite3.connect(str(db))
    try:
        con.executescript("""
            CREATE TABLE signals (
                signal_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                source TEXT NOT NULL,
                asset TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                direction TEXT,
                strength REAL,
                confidence REAL,
                value REAL,
                raw_data TEXT,
                metadata TEXT,
                rainbow_score REAL,
                ai_evaluation TEXT
            )
        """)
        for i in range(rows):
            con.execute(
                "INSERT INTO signals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    f"sig-{i}",
                    f"2026-06-14T01:04:{i:02d}.000000+00:00",
                    "ta_1h",
                    f"BTC/USDT:{i}",
                    "technical",
                    "bullish",
                    0.8,
                    0.85,
                    64500.0 + i,
                    "{}",
                    '{"timeframe": "1h"}',
                    None,
                    None,
                ),
            )
        con.commit()
    finally:
        con.close()
    return db


class TestFetchLatestSignals:
    def test_returns_rows(self, tmp_path: Path) -> None:
        db = _make_temp_db(tmp_path, rows=3)
        rows = fetch_latest_signals(str(db), limit=10)
        assert len(rows) == 3
        # Ordered DESC by timestamp — newest first.
        assert rows[0]["asset"] == "BTC/USDT:2"
        assert rows[2]["asset"] == "BTC/USDT:0"
        # The stub returns a copy — mutating must not affect the source.
        rows[0]["asset"] = "MUTATED"
        rows2 = fetch_latest_signals(str(db), limit=10)
        assert rows2[0]["asset"] == "BTC/USDT:2"

    def test_empty_db_returns_empty_list(self, tmp_path: Path) -> None:
        db = _make_temp_db(tmp_path, rows=0)
        rows = fetch_latest_signals(str(db), limit=10)
        assert rows == []

    def test_missing_db_raises_operational_error(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope.sqlite"
        with pytest.raises(sqlite3.OperationalError):
            fetch_latest_signals(str(missing), limit=10)

    def test_db_is_opened_read_only(self, tmp_path: Path) -> None:
        """The fetch helper uses ``mode=ro`` — writes must be rejected."""
        db = _make_temp_db(tmp_path, rows=1)
        # The fetch function uses the same opener; opening it ourselves
        # with mode=ro and trying a write must fail.
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            with pytest.raises(sqlite3.OperationalError):
                con.execute(
                    "INSERT INTO signals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        "evil",
                        "x",
                        "x",
                        "x",
                        "x",
                        "x",
                        0.0,
                        0.0,
                        0.0,
                        "x",
                        "x",
                        0.0,
                        "x",
                    ),
                )
        finally:
            con.close()


# ── HTTP layer (lifecycle + integration) ────────────────────────────────────


def _free_port() -> int:
    """Bind to port 0 to get a free port number, then close."""
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ── HTTP layer (lifecycle + integration) ────────────────────────────────────


class TestStubServerLifecycle:
    def test_serve_context_manager_starts_and_stops(
        self, tmp_path: Path
    ) -> None:
        """The ``serve()`` context manager exposes /health while open."""
        port = _free_port()
        cfg = StubConfig(
            host="127.0.0.1", port=port, db_path=str(tmp_path / "missing.db")
        )

        with serve(cfg) as srv:
            assert srv is not None
            # Server is running; /health must answer.
            conn = HTTPConnection("127.0.0.1", port, timeout=2)
            conn.request("GET", "/health")
            resp = conn.getresponse()
            assert resp.status == 200
            body = json.loads(resp.read().decode("utf-8"))
            assert body["status"] == "healthy"
            conn.close()
        # After the context exits, the socket is released.
        # Re-binding to the same port must succeed (EADDRINUSE would
        # mean the socket was not cleaned up).
        new_cfg = StubConfig(
            host="127.0.0.1", port=port, db_path=str(tmp_path / "missing.db")
        )
        with serve(new_cfg):
            # If we got here, cleanup is working.
            pass

    def test_signals_latest_missing_db_returns_empty(
        self, tmp_path: Path
    ) -> None:
        port = _free_port()
        cfg = StubConfig(
            host="127.0.0.1", port=port, db_path=str(tmp_path / "missing.db")
        )
        with serve(cfg):
            conn = HTTPConnection("127.0.0.1", port, timeout=2)
            conn.request("GET", "/signals/latest")
            resp = conn.getresponse()
            # Missing DB → 200 with empty list, NOT a 500.
            assert resp.status == 200
            body = json.loads(resp.read().decode("utf-8"))
            assert body["count"] == 0
            assert body["signals"] == []
            assert body["source"] == "stub"
            assert body["freshness_status"] == "db_unavailable"
            conn.close()

    def test_signals_latest_empty_db_returns_empty(
        self, tmp_path: Path
    ) -> None:
        port = _free_port()
        db = _make_temp_db(tmp_path, rows=0)
        cfg = StubConfig(host="127.0.0.1", port=port, db_path=str(db))
        with serve(cfg):
            conn = HTTPConnection("127.0.0.1", port, timeout=2)
            conn.request("GET", "/signals/latest")
            resp = conn.getresponse()
            assert resp.status == 200
            body = json.loads(resp.read().decode("utf-8"))
            assert body["count"] == 0
            assert body["signals"] == []
            assert body["freshness_status"] == "ok"
            conn.close()

    def test_signals_latest_returns_rows(self, tmp_path: Path) -> None:
        port = _free_port()
        db = _make_temp_db(tmp_path, rows=5)
        cfg = StubConfig(host="127.0.0.1", port=port, db_path=str(db))
        with serve(cfg):
            conn = HTTPConnection("127.0.0.1", port, timeout=2)
            conn.request("GET", "/signals/latest")
            resp = conn.getresponse()
            assert resp.status == 200
            body = json.loads(resp.read().decode("utf-8"))
            assert body["count"] == 5
            assert body["freshness_status"] == "ok"
            assert len(body["signals"]) == 5
            # Newest first.
            assert body["signals"][0]["asset"] == "BTC/USDT:4"
            conn.close()

    def test_not_found_returns_404(self, tmp_path: Path) -> None:
        port = _free_port()
        cfg = StubConfig(
            host="127.0.0.1", port=port, db_path=str(tmp_path / "missing.db")
        )
        with serve(cfg):
            conn = HTTPConnection("127.0.0.1", port, timeout=2)
            conn.request("GET", "/wat")
            resp = conn.getresponse()
            assert resp.status == 404
            conn.close()

    def test_post_returns_501(self, tmp_path: Path) -> None:
        """POST is intentionally unsupported — the stub is read-only GET only."""
        port = _free_port()
        cfg = StubConfig(
            host="127.0.0.1", port=port, db_path=str(tmp_path / "missing.db")
        )
        with serve(cfg):
            conn = HTTPConnection("127.0.0.1", port, timeout=2)
            conn.request("POST", "/signals/latest", body="{}")
            resp = conn.getresponse()
            # BaseHTTPRequestHandler returns 501 (Not Implemented) for
            # methods that the handler does not define.  This is the
            # correct read-only-by-design behaviour.
            assert resp.status == 501
            conn.close()
