"""Tests for the historical Freqtrade trade reader (PR #339 follow-up).

Contract:

1. Load every ``historical_trades_<bot_id>.jsonl`` file.
2. Validate ``schema_version``.
3. Skip corrupt lines with warning metadata, do not crash.
4. Filter by ``bot_id``, time window, status, and pair.
5. Never read runtime DBs, never mutate store files.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from si_v2.backfill.historical_trade_reader import (
    ReadStats,
    SUPPORTED_SCHEMA_VERSION,
    TradeRecord,
    iter_pairs,
    list_bots,
    load_store,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_record(
    path: Path,
    *,
    schema_version: int = SUPPORTED_SCHEMA_VERSION,
    bot_id: str = "bot-a",
    pair: str = "BTC/USDT:USDT",
    is_open: int = 0,
    close_profit: float = 0.01,
    close_profit_abs: float = 1.0,
    open_date: str = "2026-05-01 00:00:00",
    close_date: str = "2026-05-01 01:00:00",
    extra: dict[str, object] | None = None,
) -> None:
    record: dict[str, object] = {
        "schema_version": schema_version,
        "imported_at_utc": "2026-06-23T00:00:00Z",
        "bot_id": bot_id,
        "source_db": "/tmp/synthetic.sqlite",
        "is_open": is_open,
        "pair": pair,
        "open_date": open_date,
        "close_date": close_date,
        "close_profit": close_profit,
        "close_profit_abs": close_profit_abs,
    }
    if extra:
        record.update(extra)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record))
        f.write("\n")


@pytest.fixture()
def store_dir(tmp_path: Path) -> Path:
    """Populate a synthetic 2-bot store with a known distribution of trades."""
    bot_a = tmp_path / "historical_trades_bot-a.jsonl"
    bot_b = tmp_path / "historical_trades_bot-b.jsonl"
    # bot-a: 4 closed, 1 open, mix of pairs, spread across dates
    _write_record(bot_a, bot_id="bot-a", pair="BTC/USDT:USDT", is_open=0,
                  close_profit=0.02, close_profit_abs=2.0,
                  open_date="2026-05-01 00:00:00", close_date="2026-05-01 01:00:00")
    _write_record(bot_a, bot_id="bot-a", pair="ETH/USDT:USDT", is_open=0,
                  close_profit=-0.01, close_profit_abs=-1.0,
                  open_date="2026-05-10 00:00:00", close_date="2026-05-10 02:00:00")
    _write_record(bot_a, bot_id="bot-a", pair="BTC/USDT:USDT", is_open=0,
                  close_profit=0.05, close_profit_abs=5.0,
                  open_date="2026-06-01 00:00:00", close_date="2026-06-01 04:00:00")
    _write_record(bot_a, bot_id="bot-a", pair="SOL/USDT:USDT", is_open=0,
                  close_profit=-0.02, close_profit_abs=-2.0,
                  open_date="2026-06-15 00:00:00", close_date="2026-06-15 01:00:00")
    _write_record(bot_a, bot_id="bot-a", pair="ETH/USDT:USDT", is_open=1,
                  open_date="2026-06-20 00:00:00", close_date="")
    # bot-b: 3 closed
    _write_record(bot_b, bot_id="bot-b", pair="DOGE/USDT:USDT", is_open=0,
                  close_profit=0.10, close_profit_abs=10.0,
                  open_date="2026-05-05 00:00:00", close_date="2026-05-05 02:00:00")
    _write_record(bot_b, bot_id="bot-b", pair="DOGE/USDT:USDT", is_open=0,
                  close_profit=-0.05, close_profit_abs=-5.0,
                  open_date="2026-05-25 00:00:00", close_date="2026-05-25 03:00:00")
    _write_record(bot_b, bot_id="bot-b", pair="XRP/USDT:USDT", is_open=0,
                  close_profit=0.03, close_profit_abs=3.0,
                  open_date="2026-06-18 00:00:00", close_date="2026-06-18 02:00:00")
    return tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_load_store_counts(store_dir: Path) -> None:
    records, stats = load_store(store_dir)
    assert stats.files_seen == 2
    assert stats.files_loaded == 2
    assert stats.lines_kept == 8
    assert stats.lines_skipped_corrupt == 0
    assert stats.lines_skipped_schema == 0
    assert sorted(stats.bots) == ["bot-a", "bot-b"]
    assert len(records) == 8


def test_load_store_bot_filter(store_dir: Path) -> None:
    records, stats = load_store(store_dir, bot_id="bot-a")
    assert all(r.bot_id == "bot-a" for r in records)
    assert stats.lines_kept == 5


def test_load_store_status_filter(store_dir: Path) -> None:
    closed, _ = load_store(store_dir, only_closed=True)
    assert all(r.is_closed for r in closed)
    assert len(closed) == 7
    open_recs, _ = load_store(store_dir, only_open=True)
    assert len(open_recs) == 1
    assert open_recs[0].pair == "ETH/USDT:USDT"


def test_load_store_pair_filter(store_dir: Path) -> None:
    records, _ = load_store(store_dir, pair="DOGE/USDT:USDT")
    assert len(records) == 2
    assert all(r.pair == "DOGE/USDT:USDT" for r in records)


def test_load_store_time_window(store_dir: Path) -> None:
    records, _ = load_store(
        store_dir,
        start_utc="2026-06-01T00:00:00+00:00",
        end_utc="2026-06-30T23:59:59+00:00",
    )
    # Expect: bot-a 06-01, 06-15, 06-20 (open); bot-b 06-18
    assert len(records) == 4
    dates = sorted(r.open_date for r in records)
    assert dates[0].startswith("2026-06-01")
    assert dates[-1].startswith("2026-06-20")


def test_load_store_corrupt_line_does_not_crash(tmp_path: Path) -> None:
    p = tmp_path / "historical_trades_bot-c.jsonl"
    p.write_text(
        "this is not json\n"
        + json.dumps({
            "schema_version": SUPPORTED_SCHEMA_VERSION,
            "bot_id": "bot-c",
            "pair": "XRP/USDT:USDT",
            "is_open": 0,
            "open_date": "2026-05-01 00:00:00",
            "close_date": "2026-05-01 01:00:00",
            "close_profit": 0.01,
            "close_profit_abs": 1.0,
        })
        + "\n"
    )
    records, stats = load_store(tmp_path)
    assert stats.lines_skipped_corrupt == 1
    assert stats.lines_kept == 1


def test_load_store_schema_mismatch_is_skipped(tmp_path: Path) -> None:
    p = tmp_path / "historical_trades_bot-d.jsonl"
    _write_record(p, bot_id="bot-d", schema_version=999)
    _write_record(p, bot_id="bot-d", schema_version=SUPPORTED_SCHEMA_VERSION)
    records, stats = load_store(tmp_path)
    assert stats.lines_skipped_schema == 1
    assert stats.lines_kept == 1


def test_load_store_invalid_dir(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_store(tmp_path / "does-not-exist")


def test_only_closed_and_only_open_mutually_exclusive(store_dir: Path) -> None:
    with pytest.raises(ValueError):
        load_store(store_dir, only_closed=True, only_open=True)


def test_list_bots_and_iter_pairs(store_dir: Path) -> None:
    bots = list_bots(store_dir)
    assert bots == ["bot-a", "bot-b"]
    records, _ = load_store(store_dir)
    pairs = iter_pairs(records)
    assert pairs == [
        "BTC/USDT:USDT",
        "DOGE/USDT:USDT",
        "ETH/USDT:USDT",
        "SOL/USDT:USDT",
        "XRP/USDT:USDT",
    ]


def test_no_runtime_imports_in_reader() -> None:
    """Hard rule: no docker / freqtrade / exchange in import lines of the reader."""
    src = Path(
        "/home/hermes/projects/trading/self_improvement_v2/src/si_v2/backfill/historical_trade_reader.py"
    ).read_text()
    for line in src.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("import ") or stripped.startswith("from ")):
            continue
        for forbidden in ("docker", "freqtrade", "exchange"):
            assert forbidden not in stripped, f"Forbidden import: {stripped!r}"


def test_trade_record_is_closed_helper() -> None:
    closed = TradeRecord(bot_id="x", pair="y", is_open=0,
                         open_date="o", close_date="c",
                         close_profit=0.0, close_profit_abs=0.0)
    open_rec = TradeRecord(bot_id="x", pair="y", is_open=1,
                            open_date="o", close_date=None,
                            close_profit=None, close_profit_abs=None)
    assert closed.is_closed is True
    assert open_rec.is_closed is False
