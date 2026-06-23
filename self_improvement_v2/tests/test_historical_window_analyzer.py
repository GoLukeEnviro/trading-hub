"""Tests for the SI v2 historical window analyzer (P1).

Contract:

- Per-bot metrics: counts, PnL, winrate, profit factor, top/worst pairs.
- Fleet summary: aggregate across all bots.
- Window kinds: full / last_7d / last_14d / pre_apply / post_apply.
- Post-apply with zero closed trades must yield ``WAITING_FOR_POST_APPLY_DATA``.
- The bundle is JSON-serializable and contains no secrets.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from si_v2.analysis.historical_window_analyzer import (
    VERDICT_GREEN,
    VERDICT_WAITING,
    VERDICT_YELLOW,
    WINDOW_FULL,
    WINDOW_LAST_14D,
    WINDOW_LAST_7D,
    WINDOW_POST_APPLY,
    WINDOW_PRE_APPLY,
    FleetSummary,
    PairStats,
    WindowMetrics,
    analyze_windows,
    build_historical_evidence_window,
    compute_fleet_summary,
    compute_window_metrics,
)
from si_v2.backfill.historical_trade_reader import (
    SUPPORTED_SCHEMA_VERSION,
    TradeRecord,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rec(
    *,
    bot_id: str = "bot-a",
    pair: str = "BTC/USDT:USDT",
    is_open: int = 0,
    open_date: str = "2026-05-01 00:00:00",
    close_date: str = "2026-05-01 01:00:00",
    close_profit: float = 0.0,
    close_profit_abs: float = 0.0,
) -> TradeRecord:
    return TradeRecord(
        bot_id=bot_id,
        pair=pair,
        is_open=is_open,
        open_date=open_date,
        close_date=close_date if is_open == 0 else None,
        close_profit=close_profit,
        close_profit_abs=close_profit_abs,
    )


# ---------------------------------------------------------------------------
# Per-bot metrics
# ---------------------------------------------------------------------------


def test_compute_window_metrics_basic() -> None:
    records = [
        _rec(bot_id="x", pair="BTC/USDT:USDT", close_profit=0.05, close_profit_abs=5.0,
             open_date="2026-05-01 00:00:00", close_date="2026-05-02 00:00:00"),
        _rec(bot_id="x", pair="BTC/USDT:USDT", close_profit=-0.02, close_profit_abs=-2.0,
             open_date="2026-05-03 00:00:00", close_date="2026-05-04 00:00:00"),
        _rec(bot_id="x", pair="ETH/USDT:USDT", close_profit=0.10, close_profit_abs=10.0,
             open_date="2026-05-05 00:00:00", close_date="2026-05-06 00:00:00"),
    ]
    m = compute_window_metrics(records, bot_id="x", window_kind=WINDOW_FULL)
    assert m.total_trades == 3
    assert m.closed_trades == 3
    assert m.wins == 2
    assert m.losses == 1
    assert m.winrate == pytest.approx(2 / 3)
    assert m.sum_close_profit_abs == pytest.approx(13.0)
    assert m.gross_profit == pytest.approx(15.0)
    assert m.gross_loss == pytest.approx(2.0)
    assert m.profit_factor == pytest.approx(7.5)
    assert m.best_trade_abs == pytest.approx(10.0)
    assert m.worst_trade_abs == pytest.approx(-2.0)
    # Top pairs: BTC and ETH; ETH > BTC by pnl
    assert m.top_pairs[0].pair == "ETH/USDT:USDT"
    assert m.top_pairs[0].pnl_abs == pytest.approx(10.0)
    assert m.worst_pairs[0].pair == "BTC/USDT:USDT"
    assert m.worst_pairs[0].pnl_abs == pytest.approx(3.0)  # 5 - 2


def test_compute_window_metrics_handles_open_trades() -> None:
    records = [
        _rec(is_open=1, open_date="2026-05-01 00:00:00", close_profit=0.0, close_profit_abs=0.0),
        _rec(is_open=0, close_profit=0.05, close_profit_abs=5.0,
             open_date="2026-05-01 00:00:00", close_date="2026-05-02 00:00:00"),
    ]
    m = compute_window_metrics(records, bot_id="bot-a", window_kind=WINDOW_FULL)
    assert m.total_trades == 2
    assert m.open_trades == 1
    assert m.closed_trades == 1
    assert m.wins == 1
    assert m.losses == 0
    # No gross loss => profit_factor is "inf" (mathematical: profit only)
    assert m.profit_factor == float("inf")


def test_compute_window_metrics_no_trades() -> None:
    m = compute_window_metrics([], bot_id="bot-a", window_kind=WINDOW_FULL)
    assert m.closed_trades == 0
    assert m.winrate == 0.0
    assert m.profit_factor is None
    assert m.best_trade_abs is None
    assert m.worst_trade_abs is None
    assert m.top_pairs == []
    assert m.worst_pairs == []


# ---------------------------------------------------------------------------
# Fleet summary
# ---------------------------------------------------------------------------


def test_compute_fleet_summary_basic() -> None:
    m_a = WindowMetrics(bot_id="a", window_kind=WINDOW_FULL, closed_trades=2,
                        wins=2, sum_close_profit_abs=5.0, gross_profit=5.0,
                        oldest_open_date="2026-05-01 00:00:00",
                        newest_close_date="2026-05-02 00:00:00")
    m_b = WindowMetrics(bot_id="b", window_kind=WINDOW_FULL, closed_trades=1,
                        wins=0, losses=1, sum_close_profit_abs=-3.0, gross_loss=3.0,
                        oldest_open_date="2026-05-10 00:00:00",
                        newest_close_date="2026-05-10 02:00:00")
    fleet = compute_fleet_summary({"a": m_a, "b": m_b}, WINDOW_FULL)
    assert fleet.bots_covered == ["a", "b"]
    assert fleet.closed_trades == 3
    assert fleet.wins == 2
    assert fleet.losses == 1
    assert fleet.sum_close_profit_abs == pytest.approx(2.0)
    assert fleet.strongest_bot == "a"
    assert fleet.weakest_bot == "b"
    assert fleet.coverage_start == "2026-05-01 00:00:00"
    assert fleet.coverage_end == "2026-05-10 02:00:00"
    assert fleet.fleet_profit_factor == pytest.approx(5 / 3)


def test_compute_fleet_summary_empty() -> None:
    fleet = compute_fleet_summary({}, WINDOW_FULL)
    assert fleet.bots_covered == []
    assert fleet.data_completeness == "empty"
    assert fleet.fleet_profit_factor is None
    assert fleet.strongest_bot is None
    assert fleet.weakest_bot is None


# ---------------------------------------------------------------------------
# End-to-end analyzer over a fixture store
# ---------------------------------------------------------------------------


def _build_store(tmp_path: Path) -> Path:
    bot_a = tmp_path / "historical_trades_bot-a.jsonl"
    bot_b = tmp_path / "historical_trades_bot-b.jsonl"
    records_a = [
        ("2026-05-01 00:00:00", "2026-05-02 00:00:00", 0.05, 5.0, "BTC/USDT:USDT"),
        ("2026-05-03 00:00:00", "2026-05-04 00:00:00", -0.02, -2.0, "ETH/USDT:USDT"),
        ("2026-06-01 00:00:00", "2026-06-02 00:00:00", 0.10, 10.0, "BTC/USDT:USDT"),
        ("2026-06-15 00:00:00", "2026-06-16 00:00:00", -0.05, -5.0, "SOL/USDT:USDT"),
    ]
    for od, cd, cp, cpa, pair in records_a:
        with bot_a.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "schema_version": SUPPORTED_SCHEMA_VERSION,
                "bot_id": "bot-a",
                "pair": pair,
                "is_open": 0,
                "open_date": od,
                "close_date": cd,
                "close_profit": cp,
                "close_profit_abs": cpa,
            }) + "\n")
    # bot-b: 2 closed
    for od, cd, cp, cpa, pair in [
        ("2026-05-10 00:00:00", "2026-05-11 00:00:00", 0.03, 3.0, "XRP/USDT:USDT"),
        ("2026-06-18 00:00:00", "2026-06-19 00:00:00", 0.07, 7.0, "DOGE/USDT:USDT"),
    ]:
        with bot_b.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "schema_version": SUPPORTED_SCHEMA_VERSION,
                "bot_id": "bot-b",
                "pair": pair,
                "is_open": 0,
                "open_date": od,
                "close_date": cd,
                "close_profit": cp,
                "close_profit_abs": cpa,
            }) + "\n")
    return tmp_path


def test_analyze_windows_full(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    out = analyze_windows(store, activation_utc="2026-06-15T00:00:00+00:00")
    full = out["windows"][WINDOW_FULL]
    assert full["verdict"] == VERDICT_GREEN
    fleet = full["fleet"]
    assert fleet["total_trades"] == 6
    assert fleet["closed_trades"] == 6
    # bot-a: 5 - 2 + 10 - 5 = 8; bot-b: 3 + 7 = 10; bot-b strongest
    assert fleet["sum_close_profit_abs"] == pytest.approx(18.0)
    assert fleet["strongest_bot"] == "bot-b"
    assert fleet["weakest_bot"] == "bot-a"


def test_analyze_windows_pre_apply(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    out = analyze_windows(
        store, activation_utc="2026-06-15T00:00:00+00:00",
        windows=(WINDOW_PRE_APPLY,),
    )
    pre = out["windows"][WINDOW_PRE_APPLY]
    assert pre["verdict"] == VERDICT_GREEN
    # bot-a: 3 closed before 06-15 (05-01, 05-03, 06-01 = 5 - 2 + 10 = 13)
    # bot-b: 1 closed (05-10 = 3)
    assert pre["fleet"]["closed_trades"] == 4
    assert pre["fleet"]["sum_close_profit_abs"] == pytest.approx(16.0)
    assert pre["fleet"]["strongest_bot"] == "bot-a"
    assert pre["fleet"]["weakest_bot"] == "bot-b"


def test_analyze_windows_post_apply_zero_trades(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    # Use an activation timestamp AFTER every trade in the store.
    out = analyze_windows(
        store, activation_utc="2026-07-01T00:00:00+00:00",
        windows=(WINDOW_POST_APPLY,),
    )
    post = out["windows"][WINDOW_POST_APPLY]
    assert post["fleet"]["closed_trades"] == 0
    assert post["verdict"] == VERDICT_WAITING


def test_analyze_windows_post_apply_with_trades(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    out = analyze_windows(
        store, activation_utc="2026-06-10T00:00:00+00:00",
        windows=(WINDOW_POST_APPLY,),
    )
    post = out["windows"][WINDOW_POST_APPLY]
    # bot-a: 06-01 (BEFORE 06-10) and 06-15, 06-16
    # bot-b: 06-18, 06-19
    # All after 06-10: bot-a 06-15, 06-16 = 1 trade (-5); bot-b 06-18, 06-19 = 1 trade (7)
    assert post["fleet"]["closed_trades"] == 2
    assert post["verdict"] in (VERDICT_GREEN, VERDICT_YELLOW)
    assert post["fleet"]["sum_close_profit_abs"] == pytest.approx(-5 + 7)


def test_analyze_windows_last_7d_with_now(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    # Force "now" so the 7d window only contains 06-16T12:00Z..06-23T12:00Z.
    fixed_now = datetime(2026, 6, 23, 12, 0, 0, tzinfo=timezone.utc)
    out = analyze_windows(
        store, activation_utc="2026-06-10T00:00:00+00:00",
        windows=(WINDOW_LAST_7D,),
        now=fixed_now,
    )
    last7 = out["windows"][WINDOW_LAST_7D]
    # bot-a 06-15/06-16 -> close 06-16T00:00:00 < window start 06-16T12:00:00, excluded
    # bot-b 06-18/06-19 -> close 06-19T02:00:00 in window, included
    assert last7["fleet"]["closed_trades"] == 1
    assert last7["fleet"]["sum_close_profit_abs"] == pytest.approx(7.0)
    assert last7["fleet"]["bots_covered"] == ["bot-b"]


def test_analyze_windows_requires_activation_for_apply(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    with pytest.raises(ValueError):
        analyze_windows(store, windows=(WINDOW_PRE_APPLY,))


# ---------------------------------------------------------------------------
# build_historical_evidence_window
# ---------------------------------------------------------------------------


def test_build_historical_evidence_window_post_apply_waiting(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    # Activation after every trade -> post-apply has 0 closed
    bundle = build_historical_evidence_window(
        store,
        candidate_id="65502d13",
        activation_timestamp_utc="2026-07-01T00:00:00+00:00",
    )
    assert bundle["schema"] == "si_v2.historical_evidence_window/v1"
    assert bundle["candidate_id"] == "65502d13"
    assert bundle["primary_verdict"] == VERDICT_WAITING
    # Must be JSON-serializable for evidence bundles
    encoded = json.dumps(bundle)
    assert "primary_verdict" in encoded
    decoded = json.loads(encoded)
    assert decoded["primary_verdict"] == VERDICT_WAITING
    # No secrets fields
    for key in ("api_key", "password", "token", "secret"):
        assert key not in decoded
        for win in decoded["windows"].values():
            assert key not in win


def test_build_historical_evidence_window_with_post_apply_data(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    bundle = build_historical_evidence_window(
        store,
        candidate_id="65502d13",
        activation_timestamp_utc="2026-06-10T00:00:00+00:00",
    )
    # 2 closed trades after 06-10 -> verdict not WAITING
    assert bundle["primary_verdict"] in (VERDICT_GREEN, VERDICT_YELLOW)


# ---------------------------------------------------------------------------
# No-runtime-imports safety contract
# ---------------------------------------------------------------------------


def test_no_runtime_imports_in_analyzer() -> None:
    """Hard rule: no docker / freqtrade / exchange in import lines of the analyzer."""
    src = Path(
        "/home/hermes/projects/trading/self_improvement_v2/src/si_v2/analysis/historical_window_analyzer.py"
    ).read_text()
    for line in src.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("import ") or stripped.startswith("from ")):
            continue
        # ``from collections.abc`` etc are fine
        for forbidden in ("docker", "freqtrade", "exchange"):
            # Allow only the module-under-test import (``si_v2.backfill.historical_trade_reader``)
            # which does contain the word "historical" but not any of the forbidden substrings.
            assert forbidden not in stripped, f"Forbidden import: {stripped!r}"


def test_serializable_no_object_leak() -> None:
    """The bundle must round-trip through json.dumps without TypeError."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        store = _build_store(Path(td))
        bundle = build_historical_evidence_window(
            store,
            candidate_id="x",
            activation_timestamp_utc="2026-07-01T00:00:00+00:00",
        )
        # round-trip
        s = json.dumps(bundle)
        d = json.loads(s)
        assert "windows" in d
        for wname, w in d["windows"].items():
            assert "verdict" in w
            assert "per_bot" in w
            assert "fleet" in w
