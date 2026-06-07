#!/usr/bin/env python3
"""Export closed trades and summary metrics from a Freqtrade SQLite database."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"
UNDEFINED_PF = "UNDEFINED_PF"

CSV_FIELDS = [
    "trade_id",
    "open_date_utc",
    "close_date_utc",
    "pair",
    "profit_abs",
    "profit_ratio",
    "stake_amount",
    "open_rate",
    "close_rate",
    "trade_duration_seconds",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export closed trade history and aggregate metrics from freqtrade SQLite.",
    )
    parser.add_argument("--db", required=True, help="Path to tradesv3.sqlite")
    parser.add_argument("--bot", required=True, help="Bot name label")
    parser.add_argument("--output", required=True, help="Output path prefix")
    parser.add_argument("--since", required=False, help="ISO 8601 lower bound for close_date filter")
    parser.add_argument("--until", required=False, help="ISO 8601 upper bound for close_date filter")
    return parser.parse_args()


def parse_iso8601(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        datetime.fromisoformat(normalized)
    except ValueError:
        raise ValueError(f"Invalid {field_name} value (expected ISO 8601): {value}")
    return value


def dt_from_db(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    if normalized.endswith("+00:00") and "." in normalized:
        # Keep fromisoformat behavior stable with microseconds from sqlite text fields.
        pass
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def duration_seconds(open_date: Any, close_date: Any) -> int | None:
    open_dt = dt_from_db(open_date)
    close_dt = dt_from_db(close_date)
    if open_dt is None or close_dt is None:
        return None
    return int((close_dt - open_dt).total_seconds())


def detect_date_columns(connection: sqlite3.Connection) -> tuple[str, str]:
    rows = connection.execute("PRAGMA table_info(trades)").fetchall()
    columns = {row[1] for row in rows}

    if "open_date_utc" in columns:
        open_col = "open_date_utc"
    elif "open_date" in columns:
        open_col = "open_date"
    else:
        raise sqlite3.OperationalError("trades table missing open_date/open_date_utc column")

    if "close_date_utc" in columns:
        close_col = "close_date_utc"
    elif "close_date" in columns:
        close_col = "close_date"
    else:
        raise sqlite3.OperationalError("trades table missing close_date/close_date_utc column")

    return open_col, close_col


def query_closed_trades(db_path: Path, since: str | None, until: str | None) -> list[sqlite3.Row]:
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        open_col, close_col = detect_date_columns(connection)
        where = ["is_open = 0"]
        params: list[Any] = []
        if since:
            where.append(f"{close_col} >= ?")
            params.append(since)
        if until:
            where.append(f"{close_col} <= ?")
            params.append(until)
        sql = (
            f"SELECT id, {open_col} AS open_date_utc, {close_col} AS close_date_utc, pair, "
            "close_profit_abs, close_profit, stake_amount, open_rate, close_rate "
            "FROM trades "
            f"WHERE {' AND '.join(where)} "
            f"ORDER BY {close_col} ASC, id ASC"
        )
        cursor = connection.execute(sql, params)
        return list(cursor.fetchall())
    finally:
        connection.close()


def compute_max_drawdown_pct(profits: list[float]) -> float | None:
    if not profits:
        return None
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0

    for profit in profits:
        cumulative += profit
        if cumulative > peak:
            peak = cumulative
        if peak > 0:
            drawdown = (peak - cumulative) / peak * 100.0
            if drawdown > max_drawdown:
                max_drawdown = drawdown

    return max_drawdown


def summarize_metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    if not trades:
        return {
            "profit_factor": None,
            "win_rate": None,
            "net_profit_usdt": None,
            "avg_risk_reward": None,
            "max_drawdown_pct": None,
            "trade_count": None,
            "NO_TRADE_DATA": True,
        }

    profits = [float(t["profit_abs"]) for t in trades]
    gross_profit = sum(p for p in profits if p > 0)
    gross_loss = sum(p for p in profits if p < 0)
    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p < 0]

    if gross_loss == 0:
        profit_factor: float | str = UNDEFINED_PF
    else:
        profit_factor = gross_profit / abs(gross_loss)

    win_rate = len(wins) / len(profits)
    avg_win = sum(wins) / len(wins) if wins else None
    avg_loss_abs = abs(sum(losses) / len(losses)) if losses else None
    avg_risk_reward = None
    if avg_win is not None and avg_loss_abs not in (None, 0):
        avg_risk_reward = avg_win / avg_loss_abs

    return {
        "profit_factor": profit_factor,
        "win_rate": win_rate,
        "net_profit_usdt": sum(profits),
        "avg_risk_reward": avg_risk_reward,
        "max_drawdown_pct": compute_max_drawdown_pct(profits),
        "trade_count": len(profits),
        "NO_TRADE_DATA": False,
    }


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_trades_csv(path: Path, trades: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in trades:
            writer.writerow(row)


def write_summary_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def main() -> int:
    try:
        args = parse_args()
        since = parse_iso8601(args.since, "--since")
        until = parse_iso8601(args.until, "--until")

        db_path = Path(args.db)
        if not db_path.exists():
            raise FileNotFoundError(f"Database file not found: {db_path}")

        rows = query_closed_trades(db_path, since, until)

        trades: list[dict[str, Any]] = []
        for row in rows:
            trades.append(
                {
                    "trade_id": row["id"],
                    "open_date_utc": row["open_date_utc"],
                    "close_date_utc": row["close_date_utc"],
                    "pair": row["pair"],
                    "profit_abs": row["close_profit_abs"],
                    "profit_ratio": row["close_profit"],
                    "stake_amount": row["stake_amount"],
                    "open_rate": row["open_rate"],
                    "close_rate": row["close_rate"],
                    "trade_duration_seconds": duration_seconds(row["open_date_utc"], row["close_date_utc"]),
                }
            )

        summary = summarize_metrics(trades)
        summary_payload = {
            "schema_version": SCHEMA_VERSION,
            "bot_name": args.bot,
            "export_timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "db_path": str(db_path),
            "since": since,
            "until": until,
            **summary,
        }

        output_prefix = Path(args.output)
        trades_path = Path(f"{output_prefix}_trades.csv")
        summary_path = Path(f"{output_prefix}_summary.json")

        write_trades_csv(trades_path, trades)
        write_summary_json(summary_path, summary_payload)

        print(f"Wrote {trades_path}")
        print(f"Wrote {summary_path}")
        return 0

    except (sqlite3.Error, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
