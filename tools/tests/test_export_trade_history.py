"""Tests for tools/export_trade_history.py — pure functions only, no Docker/runtime."""

import json
import csv
import os
import sys
import sqlite3
from pathlib import Path
from collections import OrderedDict

import pytest

from tools.export_trade_history import (
    SCHEMA_VERSION,
    TRADE_FIELDS,
    SUMMARY_KEYS,
    parse_args,
    connect_db,
    get_trade_columns,
    pick_column,
    fetch_trades,
    compute_summary,
    write_csv,
    write_summary,
    main,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def db_path(tmp_path):
    """Create a minimal tradesv3.sqlite with a trades table."""
    path = tmp_path / "tradesv3.sqlite"
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE trades (
            id INTEGER PRIMARY KEY,
            open_date TEXT,
            close_date TEXT,
            pair TEXT,
            profit_abs REAL,
            profit_ratio REAL,
            stake_amount REAL,
            open_rate REAL,
            close_rate REAL,
            is_open INTEGER,
            exchange TEXT,
            strategy TEXT
        )
    """)
    conn.commit()
    conn.close()
    return str(path)


@pytest.fixture
def db_with_trades(db_path):
    """Populate the db with sample trades."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    trades = [
        (1, "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "BTC/USDT", 100.0, 0.05, 2000.0, 50000.0, 51000.0, 0, "binance", "strategy_a"),
        (2, "2026-01-03T00:00:00Z", "2026-01-04T00:00:00Z", "ETH/USDT", -50.0, -0.025, 2000.0, 3000.0, 2925.0, 0, "binance", "strategy_a"),
        (3, "2026-01-05T00:00:00Z", "2026-01-06T00:00:00Z", "BTC/USDT", 200.0, 0.10, 2000.0, 51000.0, 56100.0, 0, "binance", "strategy_b"),
        (4, "2026-01-07T00:00:00Z", "2026-01-08T00:00:00Z", "SOL/USDT", -25.0, -0.0125, 2000.0, 100.0, 98.75, 0, "binance", "strategy_a"),
        (5, "2026-01-09T00:00:00Z", "2026-01-10T00:00:00Z", "LINK/USDT", 75.0, 0.0375, 2000.0, 20.0, 20.75, 0, "binance", "strategy_a"),
    ]
    conn.executemany(
        "INSERT INTO trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        trades,
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def db_conn(db_with_trades):
    """Return a connection with row_factory set to the populated db."""
    conn = sqlite3.connect(db_with_trades)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture
def sample_trades():
    """Synthetic trade list for compute_summary tests."""
    return [
        {"profit_abs": 100.0, "profit_ratio": 0.05, "trade_duration_seconds": 86400},
        {"profit_abs": -50.0, "profit_ratio": -0.025, "trade_duration_seconds": 43200},
        {"profit_abs": 200.0, "profit_ratio": 0.10, "trade_duration_seconds": 172800},
        {"profit_abs": -25.0, "profit_ratio": -0.0125, "trade_duration_seconds": 21600},
        {"profit_abs": 75.0, "profit_ratio": 0.0375, "trade_duration_seconds": 64800},
    ]


# ── parse_args ───────────────────────────────────────────────────────────────


class TestParseArgs:
    def test_requires_db(self):
        """Missing --db should exit."""
        with pytest.raises(SystemExit):
            parse_args()

    def test_requires_bot(self, monkeypatch):
        """Missing --bot should exit."""
        monkeypatch.setattr(sys, "argv", ["prog", "--db", "/tmp/x.sqlite"])
        with pytest.raises(SystemExit):
            parse_args()

    def test_requires_output(self, monkeypatch):
        """Missing --output should exit."""
        monkeypatch.setattr(sys, "argv", ["prog", "--db", "/tmp/x.sqlite", "--bot", "test"])
        with pytest.raises(SystemExit):
            parse_args()

    def test_minimal_args(self, monkeypatch):
        """Minimal valid args parse successfully."""
        monkeypatch.setattr(sys, "argv", [
            "prog", "--db", "/tmp/x.sqlite", "--bot", "test", "--output", "/tmp/out",
        ])
        args = parse_args()
        assert args.db == "/tmp/x.sqlite"
        assert args.bot == "test"
        assert args.output == "/tmp/out"
        assert args.since is None
        assert args.until is None
        assert args.format == "csv"

    def test_all_args(self, monkeypatch):
        """All optional args parse correctly."""
        monkeypatch.setattr(sys, "argv", [
            "prog", "--db", "/tmp/x.sqlite", "--bot", "test", "--output", "/tmp/out",
            "--since", "2026-01-01", "--until", "2026-06-01", "--format", "both",
        ])
        args = parse_args()
        assert args.since == "2026-01-01"
        assert args.until == "2026-06-01"
        assert args.format == "both"

    def test_format_choices(self, monkeypatch):
        """--format accepts csv, json, both."""
        for fmt in ("csv", "json", "both"):
            monkeypatch.setattr(sys, "argv", [
                "prog", "--db", "/tmp/x.sqlite", "--bot", "test", "--output", "/tmp/out",
                "--format", fmt,
            ])
            args = parse_args()
            assert args.format == fmt

    def test_invalid_format(self, monkeypatch):
        """--format rejects invalid values."""
        monkeypatch.setattr(sys, "argv", [
            "prog", "--db", "/tmp/x.sqlite", "--bot", "test", "--output", "/tmp/out",
            "--format", "parquet",
        ])
        with pytest.raises(SystemExit):
            parse_args()


# ── connect_db ───────────────────────────────────────────────────────────────


class TestConnectDb:
    def test_connects_to_valid_db(self, db_path):
        """Happy path: valid db with trades table."""
        conn = connect_db(db_path)
        assert conn is not None
        conn.close()

    def test_missing_db(self, tmp_path):
        """Missing db file exits with code 1."""
        missing = str(tmp_path / "nonexistent.sqlite")
        with pytest.raises(SystemExit) as exc:
            connect_db(missing)
        assert exc.value.code == 1

    def test_missing_trades_table(self, tmp_path):
        """DB without trades table exits with code 1."""
        path = tmp_path / "empty.sqlite"
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE other (id INTEGER)")
        conn.commit()
        conn.close()
        with pytest.raises(SystemExit) as exc:
            connect_db(str(path))
        assert exc.value.code == 1

    def test_corrupt_db(self, tmp_path):
        """Corrupt db file exits with code 1."""
        path = tmp_path / "corrupt.sqlite"
        path.write_bytes(b"\x00\x01\x02\x03")
        with pytest.raises(SystemExit) as exc:
            connect_db(str(path))
        assert exc.value.code == 1


# ── pick_column ──────────────────────────────────────────────────────────────


class TestPickColumn:
    def test_first_match(self):
        """Returns first matching candidate."""
        cols = {"trade_id", "id", "other"}
        assert pick_column(cols, "trade_id", "id") == "trade_id"

    def test_second_match(self):
        """Returns second candidate if first missing."""
        cols = {"id", "other"}
        assert pick_column(cols, "trade_id", "id") == "id"

    def test_no_match(self):
        """Returns None when no candidates match."""
        cols = {"other"}
        assert pick_column(cols, "trade_id", "id") is None

    def test_empty_columns(self):
        """Returns None for empty column set."""
        assert pick_column(set(), "trade_id") is None

    def test_empty_candidates(self):
        """Returns None for empty candidates."""
        cols = {"trade_id"}
        assert pick_column(cols) is None


# ── get_trade_columns ────────────────────────────────────────────────────────


class TestGetTradeColumns:
    def test_returns_column_names(self, db_path):
        """Returns set of column names from trades table."""
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cols = get_trade_columns(conn)
        conn.close()
        assert "id" in cols
        assert "pair" in cols
        assert "profit_abs" in cols

    def test_empty_table(self, tmp_path):
        """Works on empty trades table."""
        path = tmp_path / "empty.sqlite"
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE trades (id INTEGER)")
        conn.commit()
        cols = get_trade_columns(conn)
        conn.close()
        assert cols == {"id"}


# ── fetch_trades ─────────────────────────────────────────────────────────────


class TestFetchTrades:
    def test_fetches_all_closed(self, db_conn):
        """Returns all closed trades."""
        trades = fetch_trades(db_conn, None, None)
        assert len(trades) == 5
        assert all(t["is_open"] == 0 for t in trades)

    def test_fetches_with_since(self, db_conn):
        """Filters by since date."""
        trades = fetch_trades(db_conn, "2026-01-05", None)
        assert len(trades) == 3  # trades 3, 4, 5
        assert all(t["trade_id"] in (3, 4, 5) for t in trades)

    def test_fetches_with_until(self, db_conn):
        """Filters by until date."""
        trades = fetch_trades(db_conn, None, "2026-01-04")
        assert len(trades) == 2  # trades 1, 2
        assert all(t["trade_id"] in (1, 2) for t in trades)

    def test_fetches_with_both_filters(self, db_conn):
        """Filters by both since and until."""
        trades = fetch_trades(db_conn, "2026-01-03", "2026-01-06")
        assert len(trades) == 2  # trades 2, 3
        assert all(t["trade_id"] in (2, 3) for t in trades)

    def test_returns_dicts_with_correct_keys(self, db_conn):
        """Each trade dict has all TRADE_FIELDS keys."""
        trades = fetch_trades(db_conn, None, None)
        for t in trades:
            for key in TRADE_FIELDS:
                assert key in t, f"Missing key: {key}"

    def test_numeric_types(self, db_conn):
        """Numeric fields are float/int, not strings."""
        trades = fetch_trades(db_conn, None, None)
        for t in trades:
            assert isinstance(t["profit_abs"], float)
            assert isinstance(t["profit_ratio"], float)
            assert isinstance(t["stake_amount"], float)
            assert isinstance(t["trade_duration_seconds"], int)

    def test_empty_result(self, tmp_path):
        """Returns empty list when no closed trades match."""
        path = tmp_path / "empty_trades.sqlite"
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE trades (
                id INTEGER, open_date TEXT, close_date TEXT, pair TEXT,
                profit_abs REAL, profit_ratio REAL, stake_amount REAL,
                open_rate REAL, close_rate REAL, is_open INTEGER,
                exchange TEXT, strategy TEXT
            )
        """)
        conn.commit()
        trades = fetch_trades(conn, None, None)
        conn.close()
        assert trades == []

    def test_schema_variant_trade_id(self, tmp_path):
        """Works with 'trade_id' column instead of 'id'."""
        path = tmp_path / "variant.sqlite"
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE trades (
                trade_id INTEGER, open_date TEXT, close_date TEXT, pair TEXT,
                profit_abs REAL, profit_ratio REAL, stake_amount REAL,
                open_rate REAL, close_rate REAL, is_open INTEGER,
                exchange TEXT, strategy TEXT
            )
        """)
        conn.execute(
            "INSERT INTO trades VALUES (1, '2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z', "
            "'BTC/USDT', 100.0, 0.05, 2000.0, 50000.0, 51000.0, 0, 'binance', 'strategy_a')"
        )
        conn.commit()
        trades = fetch_trades(conn, None, None)
        conn.close()
        assert len(trades) == 1
        assert trades[0]["trade_id"] == 1

    def test_schema_variant_close_profit(self, tmp_path):
        """Works with 'close_profit' instead of 'profit_ratio'."""
        path = tmp_path / "variant2.sqlite"
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE trades (
                id INTEGER, open_date TEXT, close_date TEXT, pair TEXT,
                close_profit REAL, close_profit_abs REAL, stake_amount REAL,
                open_rate REAL, close_rate REAL, is_open INTEGER,
                exchange TEXT, strategy TEXT
            )
        """)
        conn.execute(
            "INSERT INTO trades VALUES (1, '2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z', "
            "'BTC/USDT', 0.05, 100.0, 2000.0, 50000.0, 51000.0, 0, 'binance', 'strategy_a')"
        )
        conn.commit()
        trades = fetch_trades(conn, None, None)
        conn.close()
        assert len(trades) == 1
        assert trades[0]["profit_ratio"] == 0.05
        assert trades[0]["profit_abs"] == 100.0

    def test_missing_core_columns(self, tmp_path):
        """Raises OperationalError when core columns are missing."""
        path = tmp_path / "bad_schema.sqlite"
        conn = sqlite3.connect(str(path))
        conn.execute("CREATE TABLE trades (id INTEGER, junk TEXT)")
        conn.commit()
        with pytest.raises(sqlite3.OperationalError, match="unsupported trades schema"):
            fetch_trades(conn, None, None)
        conn.close()

    def test_missing_profit_columns(self, tmp_path):
        """Raises OperationalError when all profit columns are missing."""
        path = tmp_path / "no_profit.sqlite"
        conn = sqlite3.connect(str(path))
        conn.execute("""
            CREATE TABLE trades (
                id INTEGER, open_date TEXT, close_date TEXT, pair TEXT,
                stake_amount REAL, open_rate REAL, close_rate REAL,
                is_open INTEGER, exchange TEXT, strategy TEXT
            )
        """)
        conn.commit()
        with pytest.raises(sqlite3.OperationalError, match="cannot derive profit columns"):
            fetch_trades(conn, None, None)
        conn.close()


# ── compute_summary ──────────────────────────────────────────────────────────


class TestComputeSummary:
    def test_empty_trades(self):
        """Empty trade list returns zero summary with NO_TRADE_DATA flag."""
        summary = compute_summary([], "test_bot", "/tmp/db.sqlite", None, None)
        assert summary["total_trades"] == 0
        assert summary["winning_trades"] == 0
        assert summary["losing_trades"] == 0
        assert summary["win_rate"] is None
        assert summary["gross_profit"] == 0.0
        assert summary["gross_loss"] == 0.0
        assert summary["profit_factor"] is None
        assert summary["net_profit_usdt"] == 0.0
        assert summary["NO_TRADE_DATA"] is True

    def test_basic_summary(self, sample_trades):
        """Computes correct aggregate metrics."""
        summary = compute_summary(sample_trades, "test_bot", "/tmp/db.sqlite", None, None)
        assert summary["total_trades"] == 5
        assert summary["winning_trades"] == 3  # 100, 200, 75
        assert summary["losing_trades"] == 2  # -50, -25
        assert summary["win_rate"] == 0.6  # 3/5
        assert summary["gross_profit"] == 375.0  # 100 + 200 + 75
        assert summary["gross_loss"] == 75.0  # 50 + 25
        assert summary["net_profit_usdt"] == 300.0  # 375 - 75
        assert summary["avg_win"] == 125.0  # 375/3
        assert summary["avg_loss"] == 37.5  # 75/2

    def test_profit_factor(self, sample_trades):
        """Profit factor is gross_profit / gross_loss."""
        summary = compute_summary(sample_trades, "test", "/tmp/db.sqlite", None, None)
        assert summary["profit_factor"] == 5.0  # 375 / 75

    def test_profit_factor_undefined(self):
        """Profit factor is UNDEFINED_PF when gross_loss is 0."""
        trades = [{"profit_abs": 100.0, "profit_ratio": 0.05, "trade_duration_seconds": 86400}]
        summary = compute_summary(trades, "test", "/tmp/db.sqlite", None, None)
        assert summary["profit_factor"] == "UNDEFINED_PF"

    def test_avg_risk_reward(self, sample_trades):
        """avg_risk_reward = avg_win / avg_loss."""
        summary = compute_summary(sample_trades, "test", "/tmp/db.sqlite", None, None)
        assert summary["avg_risk_reward"] == round(125.0 / 37.5, 4)  # 3.3333

    def test_avg_risk_reward_none_when_no_losses(self):
        """avg_risk_reward is None when there are no losing trades."""
        trades = [{"profit_abs": 100.0, "profit_ratio": 0.05, "trade_duration_seconds": 86400}]
        summary = compute_summary(trades, "test", "/tmp/db.sqlite", None, None)
        assert summary["avg_risk_reward"] is None

    def test_max_drawdown(self):
        """Max drawdown is computed correctly."""
        trades = [
            {"profit_abs": 100.0, "profit_ratio": 0.05, "trade_duration_seconds": 86400},
            {"profit_abs": -150.0, "profit_ratio": -0.075, "trade_duration_seconds": 43200},
            {"profit_abs": 200.0, "profit_ratio": 0.10, "trade_duration_seconds": 172800},
        ]
        summary = compute_summary(trades, "test", "/tmp/db.sqlite", None, None)
        # Cumulative: 100, -50, 150
        # Peak: 100, then 100, then 150
        # Drawdown: 0, 150, 0
        # Max DD: 150/100 = 150% (but capped by peak logic)
        # Actually: peak=100, cumulative after trade2=-50, drawdown=100-(-50)=150, dd_pct=150/100*100=150
        # peak after trade3=150, cumulative=150, drawdown=0
        # max_dd = 150.0
        assert summary["max_drawdown_pct"] == 150.0

    def test_avg_trade_duration(self, sample_trades):
        """Average trade duration is computed correctly."""
        summary = compute_summary(sample_trades, "test", "/tmp/db.sqlite", None, None)
        expected = (86400 + 43200 + 172800 + 21600 + 64800) // 5  # 77760
        assert summary["avg_trade_duration_seconds"] == expected

    def test_avg_trade_duration_none_when_empty(self):
        """avg_trade_duration_seconds is None for empty trades."""
        summary = compute_summary([], "test", "/tmp/db.sqlite", None, None)
        assert summary["avg_trade_duration_seconds"] is None

    def test_schema_version_present(self, sample_trades):
        """Summary includes schema_version."""
        summary = compute_summary(sample_trades, "test", "/tmp/db.sqlite", None, None)
        assert summary["schema_version"] == SCHEMA_VERSION

    def test_bot_name_present(self, sample_trades):
        """Summary includes bot_name."""
        summary = compute_summary(sample_trades, "my_bot", "/tmp/db.sqlite", None, None)
        assert summary["bot_name"] == "my_bot"

    def test_db_path_abs(self, sample_trades):
        """db_path is converted to absolute path."""
        summary = compute_summary(sample_trades, "test", "relative/path.sqlite", None, None)
        assert os.path.isabs(summary["db_path"])

    def test_since_until_present(self, sample_trades):
        """since and until are passed through."""
        summary = compute_summary(sample_trades, "test", "/tmp/db.sqlite", "2026-01-01", "2026-06-01")
        assert summary["since"] == "2026-01-01"
        assert summary["until"] == "2026-06-01"

    def test_summary_keys_order(self, sample_trades):
        """Summary keys match SUMMARY_KEYS order."""
        summary = compute_summary(sample_trades, "test", "/tmp/db.sqlite", None, None)
        keys = list(summary.keys())
        # Remove NO_TRADE_DATA if present (only for empty trades)
        expected = [k for k in SUMMARY_KEYS if k != "NO_TRADE_DATA"]
        assert keys[:len(expected)] == expected

    def test_all_winners(self):
        """All winning trades: gross_loss=0, profit_factor=UNDEFINED_PF."""
        trades = [
            {"profit_abs": 50.0, "profit_ratio": 0.02, "trade_duration_seconds": 3600},
            {"profit_abs": 30.0, "profit_ratio": 0.01, "trade_duration_seconds": 7200},
        ]
        summary = compute_summary(trades, "test", "/tmp/db.sqlite", None, None)
        assert summary["winning_trades"] == 2
        assert summary["losing_trades"] == 0
        assert summary["profit_factor"] == "UNDEFINED_PF"
        assert summary["win_rate"] == 1.0

    def test_all_losers(self):
        """All losing trades: win_rate=0, avg_win=None."""
        trades = [
            {"profit_abs": -10.0, "profit_ratio": -0.01, "trade_duration_seconds": 3600},
            {"profit_abs": -20.0, "profit_ratio": -0.02, "trade_duration_seconds": 7200},
        ]
        summary = compute_summary(trades, "test", "/tmp/db.sqlite", None, None)
        assert summary["winning_trades"] == 0
        assert summary["losing_trades"] == 2
        assert summary["win_rate"] == 0.0
        assert summary["avg_win"] is None
        assert summary["avg_loss"] == 15.0

    def test_zero_profit_trade(self):
        """Trade with profit_abs=0 counts as winning (>= 0)."""
        trades = [
            {"profit_abs": 0.0, "profit_ratio": 0.0, "trade_duration_seconds": 3600},
        ]
        summary = compute_summary(trades, "test", "/tmp/db.sqlite", None, None)
        assert summary["winning_trades"] == 1
        assert summary["losing_trades"] == 0


# ── write_csv ─────────────────────────────────────────────────────────────────


class TestWriteCsv:
    def test_writes_csv_file(self, sample_trades, tmp_path):
        """Writes CSV with correct headers and data."""
        out = str(tmp_path / "output")
        path = write_csv(sample_trades, out)
        assert path == f"{out}_trades.csv"
        assert os.path.isfile(path)

        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 5
            assert reader.fieldnames == TRADE_FIELDS

    def test_empty_trades_writes_header(self, tmp_path):
        """Empty trade list still writes CSV with headers."""
        out = str(tmp_path / "empty")
        path = write_csv([], out)
        assert os.path.isfile(path)

        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 0
            assert reader.fieldnames == TRADE_FIELDS

    def test_writes_correct_values(self, sample_trades, tmp_path):
        """CSV values match input data."""
        out = str(tmp_path / "output")
        write_csv(sample_trades, out)

        with open(f"{out}_trades.csv", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert float(rows[0]["profit_abs"]) == 100.0
            assert float(rows[1]["profit_abs"]) == -50.0
            assert float(rows[2]["profit_abs"]) == 200.0

    def test_unwritable_path(self, tmp_path):
        """Unwritable path exits with code 1."""
        out = str(tmp_path / "nonexistent" / "output")
        with pytest.raises(SystemExit) as exc:
            write_csv([], out)
        assert exc.value.code == 1


# ── write_summary ────────────────────────────────────────────────────────────


class TestWriteSummary:
    def test_writes_json_file(self, sample_trades, tmp_path):
        """Writes JSON with correct keys."""
        summary = compute_summary(sample_trades, "test", "/tmp/db.sqlite", None, None)
        out = str(tmp_path / "output")
        path = write_summary(summary, out)
        assert path == f"{out}_summary.json"
        assert os.path.isfile(path)

        with open(path) as f:
            data = json.load(f)
        assert data["total_trades"] == 5
        assert data["bot_name"] == "test"

    def test_empty_summary(self, tmp_path):
        """Empty trade summary writes valid JSON."""
        summary = compute_summary([], "test", "/tmp/db.sqlite", None, None)
        out = str(tmp_path / "empty")
        write_summary(summary, out)

        with open(f"{out}_summary.json") as f:
            data = json.load(f)
        assert data["total_trades"] == 0
        assert data["NO_TRADE_DATA"] is True

    def test_unwritable_path(self, tmp_path):
        """Unwritable path exits with code 1."""
        out = str(tmp_path / "nonexistent" / "output")
        with pytest.raises(SystemExit) as exc:
            write_summary({"a": 1}, out)
        assert exc.value.code == 1


# ── main() ───────────────────────────────────────────────────────────────────


class TestMain:
    def test_main_csv_output(self, db_with_trades, tmp_path, monkeypatch):
        """main() produces CSV output."""
        out = str(tmp_path / "test_output")
        monkeypatch.setattr(sys, "argv", [
            "export_trade_history.py",
            "--db", db_with_trades,
            "--bot", "test_bot",
            "--output", out,
        ])
        main()
        assert os.path.isfile(f"{out}_trades.csv")
        assert not os.path.isfile(f"{out}_summary.json")

    def test_main_json_output(self, db_with_trades, tmp_path, monkeypatch):
        """main() produces JSON output with --format json."""
        out = str(tmp_path / "test_output")
        monkeypatch.setattr(sys, "argv", [
            "export_trade_history.py",
            "--db", db_with_trades,
            "--bot", "test_bot",
            "--output", out,
            "--format", "json",
        ])
        main()
        assert not os.path.isfile(f"{out}_trades.csv")
        assert os.path.isfile(f"{out}_summary.json")

    def test_main_both_output(self, db_with_trades, tmp_path, monkeypatch):
        """main() produces both CSV and JSON with --format both."""
        out = str(tmp_path / "test_output")
        monkeypatch.setattr(sys, "argv", [
            "export_trade_history.py",
            "--db", db_with_trades,
            "--bot", "test_bot",
            "--output", out,
            "--format", "both",
        ])
        main()
        assert os.path.isfile(f"{out}_trades.csv")
        assert os.path.isfile(f"{out}_summary.json")

    def test_main_with_date_filters(self, db_with_trades, tmp_path, monkeypatch):
        """main() respects date filters."""
        out = str(tmp_path / "test_output")
        monkeypatch.setattr(sys, "argv", [
            "export_trade_history.py",
            "--db", db_with_trades,
            "--bot", "test_bot",
            "--output", out,
            "--since", "2026-01-05",
            "--until", "2026-01-06",
        ])
        main()
        with open(f"{out}_trades.csv", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 1  # only trade 3
            assert rows[0]["pair"] == "BTC/USDT"

    def test_main_empty_result(self, tmp_path, monkeypatch):
        """main() handles empty result gracefully — CSV only by default."""
        # Create db with no closed trades
        path = tmp_path / "empty.sqlite"
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE trades (
                id INTEGER, open_date TEXT, close_date TEXT, pair TEXT,
                profit_abs REAL, profit_ratio REAL, stake_amount REAL,
                open_rate REAL, close_rate REAL, is_open INTEGER,
                exchange TEXT, strategy TEXT
            )
        """)
        conn.commit()
        conn.close()

        out = str(tmp_path / "test_output")
        monkeypatch.setattr(sys, "argv", [
            "export_trade_history.py",
            "--db", str(path),
            "--bot", "test_bot",
            "--output", out,
        ])
        main()
        with open(f"{out}_trades.csv", newline="") as f:
            rows = list(csv.DictReader(f))
            assert len(rows) == 0
        # Default format is csv, so no summary.json is written
        assert not os.path.isfile(f"{out}_summary.json")

    def test_main_missing_db(self, tmp_path, monkeypatch):
        """main() exits with code 1 on missing db."""
        monkeypatch.setattr(sys, "argv", [
            "export_trade_history.py",
            "--db", str(tmp_path / "nonexistent.sqlite"),
            "--bot", "test_bot",
            "--output", str(tmp_path / "out"),
        ])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1

    def test_main_creates_output_dir(self, db_with_trades, tmp_path, monkeypatch):
        """main() creates output directory if it doesn't exist."""
        out = str(tmp_path / "new_dir" / "test_output")
        monkeypatch.setattr(sys, "argv", [
            "export_trade_history.py",
            "--db", db_with_trades,
            "--bot", "test_bot",
            "--output", out,
        ])
        main()
        assert os.path.isfile(f"{out}_trades.csv")

    def test_main_csv_content(self, db_with_trades, tmp_path, monkeypatch):
        """main() CSV contains correct trade data."""
        out = str(tmp_path / "test_output")
        monkeypatch.setattr(sys, "argv", [
            "export_trade_history.py",
            "--db", db_with_trades,
            "--bot", "test_bot",
            "--output", out,
        ])
        main()
        with open(f"{out}_trades.csv", newline="") as f:
            rows = list(csv.DictReader(f))
            assert len(rows) == 5
            assert rows[0]["pair"] == "BTC/USDT"
            assert rows[0]["trade_id"] == "1"
            assert float(rows[0]["profit_abs"]) == 100.0

    def test_main_summary_content(self, db_with_trades, tmp_path, monkeypatch):
        """main() JSON summary contains correct metrics."""
        out = str(tmp_path / "test_output")
        monkeypatch.setattr(sys, "argv", [
            "export_trade_history.py",
            "--db", db_with_trades,
            "--bot", "test_bot",
            "--output", out,
            "--format", "json",
        ])
        main()
        with open(f"{out}_summary.json") as f:
            data = json.load(f)
        assert data["total_trades"] == 5
        assert data["winning_trades"] == 3
        assert data["losing_trades"] == 2
        assert data["bot_name"] == "test_bot"
