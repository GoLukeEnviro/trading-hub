#!/usr/bin/env python3
"""Tests for export_trade_history.py — multi-schema trade DB support."""

import os
import sqlite3
import sys
import tempfile
import unittest

# Ensure the tool can be imported from the tools directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import export_trade_history  # noqa: E402


class TestPickColumn(unittest.TestCase):
    """pick_column finds the first matching column from candidates."""

    def test_first_match(self):
        cols = {"id", "trade_id", "open_date"}
        self.assertEqual(export_trade_history.pick_column(cols, "trade_id", "id"), "trade_id")

    def test_fallback_match(self):
        cols = {"id", "open_date"}
        self.assertEqual(export_trade_history.pick_column(cols, "trade_id", "id"), "id")

    def test_no_match(self):
        cols = {"open_date"}
        self.assertIsNone(export_trade_history.pick_column(cols, "trade_id", "id"))

    def test_empty_cols(self):
        self.assertIsNone(export_trade_history.pick_column(set(), "trade_id"))


class TestGetTradeColumns(unittest.TestCase):
    """get_trade_columns introspects the trades table."""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

    def tearDown(self):
        self.conn.close()

    def test_standard_schema(self):
        self.conn.execute("""
            CREATE TABLE trades (
                id INTEGER PRIMARY KEY,
                trade_id INTEGER,
                is_open INTEGER,
                close_date TEXT,
                open_date TEXT,
                pair TEXT,
                stake_amount REAL,
                open_rate REAL,
                close_rate REAL,
                profit_abs REAL,
                profit_ratio REAL,
                exchange TEXT,
                strategy TEXT
            )
        """)
        cols = export_trade_history.get_trade_columns(self.conn)
        self.assertIn("id", cols)
        self.assertIn("trade_id", cols)
        self.assertIn("is_open", cols)
        self.assertIn("close_date", cols)

    def test_minimal_schema_no_is_open(self):
        """Schema without is_open column (some Freqtrade variants)."""
        self.conn.execute("""
            CREATE TABLE trades (
                id INTEGER PRIMARY KEY,
                close_date TEXT,
                open_date TEXT,
                pair TEXT,
                stake_amount REAL
            )
        """)
        cols = export_trade_history.get_trade_columns(self.conn)
        self.assertIn("id", cols)
        self.assertNotIn("is_open", cols)
        self.assertIn("close_date", cols)


class TestFetchTradesIsOpen(unittest.TestCase):
    """fetch_trades correctly filters closed trades with and without is_open."""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

    def tearDown(self):
        self.conn.close()

    def test_with_is_open_column(self):
        """Schema with is_open=0 filter works."""
        self.conn.execute("""
            CREATE TABLE trades (
                id INTEGER PRIMARY KEY,
                trade_id INTEGER,
                is_open INTEGER,
                open_date TEXT,
                close_date TEXT,
                pair TEXT,
                stake_amount REAL,
                profit_abs REAL,
                profit_ratio REAL
            )
        """)
        # Insert one closed, one open
        self.conn.execute(
            "INSERT INTO trades (trade_id, is_open, open_date, close_date, pair, "
            "stake_amount, profit_abs, profit_ratio) "
            "VALUES (1, 0, '2026-06-01T00:00:00Z', '2026-06-02T00:00:00Z', 'BTC/USDT', 100.0, 5.0, 0.05)"
        )
        self.conn.execute(
            "INSERT INTO trades (trade_id, is_open, open_date, close_date, pair, "
            "stake_amount, profit_abs, profit_ratio) "
            "VALUES (2, 1, '2026-06-03T00:00:00Z', NULL, 'ETH/USDT', 100.0, 0.0, 0.0)"
        )

        trades = export_trade_history.fetch_trades(self.conn, None, None)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["trade_id"], 1)

    def test_without_is_open_column(self):
        """Schema without is_open uses close_date IS NOT NULL filter."""
        self.conn.execute("""
            CREATE TABLE trades (
                id INTEGER PRIMARY KEY,
                trade_id INTEGER,
                open_date TEXT,
                close_date TEXT,
                pair TEXT,
                stake_amount REAL,
                profit_abs REAL,
                profit_ratio REAL
            )
        """)
        # One closed (has close_date), one open (no close_date)
        self.conn.execute(
            "INSERT INTO trades (trade_id, open_date, close_date, pair, "
            "stake_amount, profit_abs, profit_ratio) "
            "VALUES (1, '2026-06-01T00:00:00Z', '2026-06-02T00:00:00Z', 'BTC/USDT', 100.0, 5.0, 0.05)"
        )
        self.conn.execute(
            "INSERT INTO trades (trade_id, open_date, close_date, pair, "
            "stake_amount, profit_abs, profit_ratio) "
            "VALUES (2, '2026-06-03T00:00:00Z', NULL, 'ETH/USDT', 100.0, 0.0, 0.0)"
        )

        trades = export_trade_history.fetch_trades(self.conn, None, None)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["trade_id"], 1)

    def test_without_is_open_all_open_returns_empty(self):
        """All open trades (no close_date) returns empty list."""
        self.conn.execute("""
            CREATE TABLE trades (
                id INTEGER PRIMARY KEY,
                trade_id INTEGER,
                open_date TEXT,
                close_date TEXT,
                pair TEXT,
                stake_amount REAL,
                profit_abs REAL,
                profit_ratio REAL
            )
        """)
        for i in range(3):
            self.conn.execute(
                "INSERT INTO trades (trade_id, open_date, close_date, pair, "
                "stake_amount, profit_abs, profit_ratio) "
                "VALUES (?, '2026-06-01T00:00:00Z', NULL, 'BTC/USDT', 100.0, 5.0, 0.05)",
                (i + 1,),
            )
        trades = export_trade_history.fetch_trades(self.conn, None, None)
        self.assertEqual(len(trades), 0)


class TestFetchTradesFailClosed(unittest.TestCase):
    """fetch_trades fails closed on unsupported schemas."""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

    def tearDown(self):
        self.conn.close()

    def test_missing_id_column(self):
        """No id or trade_id column raises OperationalError."""
        self.conn.execute("""
            CREATE TABLE trades (
                pair TEXT,
                close_date TEXT,
                open_date TEXT
            )
        """)
        with self.assertRaises(sqlite3.OperationalError) as ctx:
            export_trade_history.fetch_trades(self.conn, None, None)
        self.assertIn("unsupported trades schema", str(ctx.exception))

    def test_missing_date_columns(self):
        """Missing open_date and close_date raises OperationalError."""
        self.conn.execute("""
            CREATE TABLE trades (
                id INTEGER PRIMARY KEY,
                pair TEXT
            )
        """)
        with self.assertRaises(sqlite3.OperationalError) as ctx:
            export_trade_history.fetch_trades(self.conn, None, None)
        self.assertIn("unsupported trades schema", str(ctx.exception))

    def test_missing_profit_columns(self):
        """Missing both profit_abs variants and profit_ratio raises OperationalError."""
        self.conn.execute("""
            CREATE TABLE trades (
                id INTEGER PRIMARY KEY,
                trade_id INTEGER,
                pair TEXT,
                close_date TEXT,
                open_date TEXT
            )
        """)
        with self.assertRaises(sqlite3.OperationalError) as ctx:
            export_trade_history.fetch_trades(self.conn, None, None)
        self.assertIn("cannot derive profit columns", str(ctx.exception))


class TestComputeSummary(unittest.TestCase):
    """compute_summary edge cases."""

    def test_no_trades_summary(self):
        """Empty trade list produces NO_TRADE_DATA summary."""
        summary = export_trade_history.compute_summary(
            [], "test-bot", ":memory:", None, None
        )
        self.assertTrue(summary.get("NO_TRADE_DATA", False))
        self.assertEqual(summary["total_trades"], 0)

    def test_zero_gross_loss_undefined_pf(self):
        """Zero gross loss returns UNDEFINED_PF."""
        trades = [
            {"profit_abs": 10.0, "trade_duration_seconds": 3600},
            {"profit_abs": 5.0, "trade_duration_seconds": 7200},
        ]
        summary = export_trade_history.compute_summary(
            trades, "test-bot", ":memory:", None, None
        )
        self.assertEqual(summary["profit_factor"], "UNDEFINED_PF")
        self.assertEqual(summary["gross_loss"], 0.0)


if __name__ == "__main__":
    unittest.main()
