"""Tests for si_v2_t4_close_watcher.py — read-only T4 readiness detector.

Tests use in-memory SQLite databases (no Docker, no host filesystem).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from orchestrator.scripts.si_v2_t4_close_watcher import (
    STILL_WAITING,
    STILL_WAITING_CONTROL_MISSING,
    T4_READY,
    UNKNOWN,
    _count_closed_since,
    _parse_t3,
    check_t4_readiness,
    main,
)


# ---------------------------------------------------------------------------
# _parse_t3
# ---------------------------------------------------------------------------

class TestParseT3:
    def test_iso_with_z(self):
        assert _parse_t3("2026-06-28T18:27:00Z") == "2026-06-28 18:27:00"

    def test_iso_without_z(self):
        assert _parse_t3("2026-06-28T18:27:00") == "2026-06-28 18:27:00"

    def test_space_separated(self):
        assert _parse_t3("2026-06-28 18:27:00") == "2026-06-28 18:27:00"

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="Invalid T3 timestamp"):
            _parse_t3("not-a-date")


# ---------------------------------------------------------------------------
# _count_closed_since
# ---------------------------------------------------------------------------

class TestCountClosedSince:
    """Test the low-level SQLite query helper."""

    def make_db(self, trades: list[dict]) -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE trades ("
            "  id INTEGER PRIMARY KEY,"
            "  pair TEXT,"
            "  is_open INTEGER,"
            "  open_date TEXT,"
            "  close_date TEXT,"
            "  close_profit_abs REAL"
            ")"
        )
        for t in trades:
            conn.execute(
                "INSERT INTO trades (id, pair, is_open, open_date, close_date, close_profit_abs) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (t["id"], t["pair"], t["is_open"], t["open_date"], t["close_date"], t.get("close_profit_abs")),
            )
        conn.execute("PRAGMA query_only = ON")
        return conn

    def test_zero_closed(self):
        conn = self.make_db([
            {"id": 1, "pair": "BTC/USDT", "is_open": 1, "open_date": "2026-06-30 10:00:00", "close_date": None},
        ])
        assert _count_closed_since(conn, "2026-06-28 18:27:00") == 0
        conn.close()

    def test_one_closed_after_t3(self):
        conn = self.make_db([
            {"id": 1, "pair": "UNI/USDT", "is_open": 0, "open_date": "2026-06-29 21:15:00",
             "close_date": "2026-06-30 12:00:00", "close_profit_abs": 0.5},
        ])
        assert _count_closed_since(conn, "2026-06-28 18:27:00") == 1
        conn.close()

    def test_closed_before_t3_not_counted(self):
        conn = self.make_db([
            {"id": 1, "pair": "LINK/USDT", "is_open": 0, "open_date": "2026-06-22 14:45:00",
             "close_date": "2026-06-24 16:51:00", "close_profit_abs": -2.24},
        ])
        assert _count_closed_since(conn, "2026-06-28 18:27:00") == 0
        conn.close()

    def test_mixed_trades(self):
        conn = self.make_db([
            {"id": 1, "pair": "LINK/USDT", "is_open": 0, "open_date": "2026-06-22 14:45:00",
             "close_date": "2026-06-24 16:51:00", "close_profit_abs": -2.24},
            {"id": 2, "pair": "UNI/USDT", "is_open": 0, "open_date": "2026-06-29 21:15:00",
             "close_date": "2026-06-30 12:00:00", "close_profit_abs": 0.5},
            {"id": 3, "pair": "DOT/USDT", "is_open": 1, "open_date": "2026-06-30 14:15:00",
             "close_date": None},
        ])
        assert _count_closed_since(conn, "2026-06-28 18:27:00") == 1
        conn.close()

    def test_null_close_date_not_counted(self):
        conn = self.make_db([
            {"id": 1, "pair": "UNI/USDT", "is_open": 0, "open_date": "2026-06-29 21:15:00",
             "close_date": None, "close_profit_abs": None},
        ])
        assert _count_closed_since(conn, "2026-06-28 18:27:00") == 0
        conn.close()


# ---------------------------------------------------------------------------
# check_t4_readiness — integration with temp SQLite files
# ---------------------------------------------------------------------------

class TestCheckT4Readiness:
    """Integration tests using temporary SQLite files (no Docker)."""

    @pytest.fixture
    def t3(self) -> str:
        return "2026-06-28T18:27:00Z"

    def _make_db_file(self, tmp_path: Path, trades: list[dict], name: str = "trades") -> Path:
        path = tmp_path / f"{name}.db"
        conn = sqlite3.connect(str(path))
        conn.execute(
            "CREATE TABLE trades ("
            "  id INTEGER PRIMARY KEY,"
            "  pair TEXT,"
            "  is_open INTEGER,"
            "  open_date TEXT,"
            "  close_date TEXT,"
            "  close_profit_abs REAL"
            ")"
        )
        for t in trades:
            conn.execute(
                "INSERT INTO trades (id, pair, is_open, open_date, close_date, close_profit_abs) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (t["id"], t["pair"], t["is_open"], t["open_date"], t["close_date"], t.get("close_profit_abs")),
            )
        conn.commit()
        conn.close()
        return path

    def test_still_waiting_no_new_closed(self, tmp_path, t3):
        """Canary has 0 new closed trades since T3 → STILL_WAITING."""
        canary = self._make_db_file(tmp_path, [
            {"id": 60, "pair": "UNI/USDT", "is_open": 1, "open_date": "2026-06-29 21:15:00",
             "close_date": None},
        ], name="canary")
        control = self._make_db_file(tmp_path, [
            {"id": 80, "pair": "BTC/USDT", "is_open": 0, "open_date": "2026-06-29 04:45:00",
             "close_date": "2026-06-30 12:24:00", "close_profit_abs": 5.13},
        ], name="control")
        verdict, details = check_t4_readiness(canary, control, t3)
        assert verdict == STILL_WAITING
        assert details["canary_new_closed"] == 0
        assert details["control_new_closed"] == 1

    def test_t4_ready_both_have_new_closed(self, tmp_path, t3):
        """Both bots have >=1 new closed trade → T4_READY."""
        canary = self._make_db_file(tmp_path, [
            {"id": 60, "pair": "UNI/USDT", "is_open": 0, "open_date": "2026-06-29 21:15:00",
             "close_date": "2026-06-30 12:00:00", "close_profit_abs": 0.5},
        ], name="canary")
        control = self._make_db_file(tmp_path, [
            {"id": 80, "pair": "BTC/USDT", "is_open": 0, "open_date": "2026-06-29 04:45:00",
             "close_date": "2026-06-30 12:24:00", "close_profit_abs": 5.13},
        ], name="control")
        verdict, details = check_t4_readiness(canary, control, t3)
        assert verdict == T4_READY
        assert details["canary_new_closed"] >= 1
        assert details["control_new_closed"] >= 1

    def test_still_waiting_control_missing(self, tmp_path, t3):
        """Canary has new closed but Control has 0 → STILL_WAITING_CONTROL_MISSING."""
        canary = self._make_db_file(tmp_path, [
            {"id": 60, "pair": "UNI/USDT", "is_open": 0, "open_date": "2026-06-29 21:15:00",
             "close_date": "2026-06-30 12:00:00", "close_profit_abs": 0.5},
        ], name="canary")
        control = self._make_db_file(tmp_path, [
            {"id": 79, "pair": "SOL/USDT", "is_open": 0, "open_date": "2026-06-22 18:00:00",
             "close_date": "2026-06-23 05:19:00", "close_profit_abs": 2.24},
        ], name="control")
        verdict, details = check_t4_readiness(canary, control, t3)
        assert verdict == STILL_WAITING_CONTROL_MISSING
        assert details["canary_new_closed"] >= 1
        assert details["control_new_closed"] == 0

    def test_unknown_canary_db_missing(self, tmp_path, t3):
        """Missing Canary DB → UNKNOWN."""
        canary = tmp_path / "nonexistent.db"
        control = self._make_db_file(tmp_path, [
            {"id": 80, "pair": "BTC/USDT", "is_open": 0, "open_date": "2026-06-29 04:45:00",
             "close_date": "2026-06-30 12:24:00", "close_profit_abs": 5.13},
        ])
        verdict, details = check_t4_readiness(canary, control, t3)
        assert verdict == UNKNOWN
        assert any("canary_db_not_found" in e for e in details["errors"])

    def test_unknown_both_dbs_missing(self, tmp_path, t3):
        """Both DBs missing → UNKNOWN."""
        canary = tmp_path / "no-canary.db"
        control = tmp_path / "no-control.db"
        verdict, details = check_t4_readiness(canary, control, t3)
        assert verdict == UNKNOWN
        assert len(details["errors"]) == 2

    def test_unknown_corrupt_db(self, tmp_path, t3):
        """Corrupt Canary DB → UNKNOWN."""
        canary = tmp_path / "corrupt.db"
        canary.write_text("not a valid sqlite file")
        control = self._make_db_file(tmp_path, [
            {"id": 80, "pair": "BTC/USDT", "is_open": 0, "open_date": "2026-06-29 04:45:00",
             "close_date": "2026-06-30 12:24:00", "close_profit_abs": 5.13},
        ])
        verdict, details = check_t4_readiness(canary, control, t3)
        assert verdict == UNKNOWN
        assert any("canary_db_error" in e for e in details["errors"])

    def test_t4_ready_multiple_new_trades(self, tmp_path, t3):
        """Multiple new closed trades on both bots → T4_READY."""
        canary = self._make_db_file(tmp_path, [
            {"id": 60, "pair": "UNI/USDT", "is_open": 0, "open_date": "2026-06-29 21:15:00",
             "close_date": "2026-06-30 12:00:00", "close_profit_abs": 0.5},
            {"id": 61, "pair": "DOT/USDT", "is_open": 0, "open_date": "2026-06-30 14:15:00",
             "close_date": "2026-06-30 16:00:00", "close_profit_abs": 0.3},
        ], name="canary")
        control = self._make_db_file(tmp_path, [
            {"id": 80, "pair": "BTC/USDT", "is_open": 0, "open_date": "2026-06-29 04:45:00",
             "close_date": "2026-06-30 12:24:00", "close_profit_abs": 5.13},
            {"id": 81, "pair": "ETH/USDT", "is_open": 0, "open_date": "2026-06-29 04:45:00",
             "close_date": "2026-06-30 14:00:00", "close_profit_abs": -2.0},
        ], name="control")
        verdict, details = check_t4_readiness(canary, control, t3)
        assert verdict == T4_READY
        assert details["canary_new_closed"] == 2
        assert details["control_new_closed"] == 2


# ---------------------------------------------------------------------------
# CLI main()
# ---------------------------------------------------------------------------

class TestCLI:
    def test_still_waiting_stdout(self, tmp_path):
        """Default output is plain text verdict."""
        canary = tmp_path / "canary.db"
        control = tmp_path / "control.db"
        # Create empty DBs (no trades at all)
        for p in (canary, control):
            conn = sqlite3.connect(str(p))
            conn.execute(
                "CREATE TABLE trades ("
                "  id INTEGER PRIMARY KEY, pair TEXT, is_open INTEGER,"
                "  open_date TEXT, close_date TEXT, close_profit_abs REAL"
                ")"
            )
            conn.commit()
            conn.close()

        exit_code = main([
            "--canary-db", str(canary),
            "--control-db", str(control),
            "--t3-timestamp", "2026-06-28T18:27:00Z",
        ])
        assert exit_code == 0  # STILL_WAITING

    def test_json_output(self, tmp_path, capsys):
        """JSON output includes verdict and details."""
        canary = tmp_path / "canary.db"
        control = tmp_path / "control.db"
        for p in (canary, control):
            conn = sqlite3.connect(str(p))
            conn.execute(
                "CREATE TABLE trades ("
                "  id INTEGER PRIMARY KEY, pair TEXT, is_open INTEGER,"
                "  open_date TEXT, close_date TEXT, close_profit_abs REAL"
                ")"
            )
            conn.commit()
            conn.close()

        exit_code = main([
            "--canary-db", str(canary),
            "--control-db", str(control),
            "--t3-timestamp", "2026-06-28T18:27:00Z",
            "--json",
        ])
        captured = capsys.readouterr()
        assert exit_code == 0
        data = json.loads(captured.out)
        assert "verdict" in data
        assert data["verdict"] == STILL_WAITING
        assert "canary_new_closed" in data
        assert "control_new_closed" in data

    def test_unknown_exit_code(self, tmp_path):
        """Missing DBs → exit code 2."""
        exit_code = main([
            "--canary-db", str(tmp_path / "no.db"),
            "--control-db", str(tmp_path / "no.db"),
        ])
        assert exit_code == 2

    def test_help(self):
        with pytest.raises(SystemExit):
            main(["--help"])