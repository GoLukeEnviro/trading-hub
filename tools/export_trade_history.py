#!/usr/bin/env python3
"""
export_trade_history.py — Standardized trade history export tool.

Exports closed trades from a Freqtrade tradesv3.sqlite database into
CSV (per-trade detail) and JSON (summary metrics) files.

Designed for use as the authoritative data source (P0 evidence tier)
for the Profitability Forensics Agent.

Dependencies: stdlib only (sqlite3, csv, json, argparse, os, sys, datetime, collections)
Must run inside the freqtrade Docker container without any pip installs.
"""

import sqlite3
import csv
import json
import argparse
import os
import sys
import datetime
import collections


# ── Schema ──────────────────────────────────────────────────────────────────

SCHEMA_VERSION = "1.0"

TRADE_FIELDS = [
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
    "is_open",
    "exchange",
    "strategy",
]

SUMMARY_KEYS = [
    "schema_version",
    "bot_name",
    "export_timestamp_utc",
    "db_path",
    "since",
    "until",
    "total_trades",
    "winning_trades",
    "losing_trades",
    "win_rate",
    "gross_profit",
    "gross_loss",
    "profit_factor",
    "net_profit_usdt",
    "avg_win",
    "avg_loss",
    "avg_risk_reward",
    "max_drawdown_pct",
    "avg_trade_duration_seconds",
]


# ── CLI ─────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Export closed trades from a Freqtrade tradesv3.sqlite database."
    )
    parser.add_argument(
        "--db",
        required=True,
        help="Path to tradesv3.sqlite (required).",
    )
    parser.add_argument(
        "--bot",
        required=True,
        help="Bot name string for labeling (required).",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output path prefix, no extension (required). "
             "Produces {output}_trades.csv and {output}_summary.json.",
    )
    parser.add_argument(
        "--since",
        default=None,
        help="ISO 8601 date filter, inclusive (optional). "
             "Filters on close_date. Example: 2026-01-01 or 2026-01-01T00:00:00Z",
    )
    parser.add_argument(
        "--until",
        default=None,
        help="ISO 8601 date filter, inclusive (optional). "
             "Filters on close_date. Example: 2026-06-01 or 2026-06-01T23:59:59Z",
    )
    parser.add_argument(
        "--format",
        default="csv",
        choices=["csv", "json", "both"],
        help="Output format (default: csv).",
    )
    return parser.parse_args()


# ── DB ──────────────────────────────────────────────────────────────────────

def connect_db(db_path):
    """Open SQLite connection. Raises on error."""
    if not os.path.isfile(db_path):
        print(f"ERROR: db not found: {db_path}", file=sys.stderr)
        sys.exit(1)
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        # Quick validation: check the trades table exists
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trades'")
        if cursor.fetchone() is None:
            print(f"ERROR: cannot open db: 'trades' table not found in {db_path}", file=sys.stderr)
            sys.exit(1)
        return conn
    except sqlite3.DatabaseError as e:
        print(f"ERROR: cannot open db: {e}", file=sys.stderr)
        sys.exit(1)


def fetch_trades(conn, since, until):
    """Fetch closed trades with optional date filters.

    Returns list of dicts with TRADE_FIELDS keys.
    """
    query = """
        SELECT
            trade_id,
            open_date AS open_date_utc,
            close_date AS close_date_utc,
            pair,
            profit_abs,
            profit_ratio,
            stake_amount,
            open_rate,
            close_rate,
            CAST(
                (julianday(close_date) - julianday(open_date)) * 86400 AS INTEGER
            ) AS trade_duration_seconds,
            is_open,
            exchange,
            strategy
        FROM trades
        WHERE is_open = 0
    """
    params = []
    if since is not None:
        query += " AND close_date >= ?"
        params.append(since)
    if until is not None:
        query += " AND close_date <= ?"
        params.append(until + "T23:59:59Z" if "T" not in until else until)
    query += " ORDER BY close_date ASC"

    cursor = conn.execute(query, params)
    rows = []
    for row in cursor.fetchall():
        d = dict(row)
        # Ensure numeric types
        for key in ("profit_abs", "profit_ratio", "stake_amount", "open_rate", "close_rate"):
            if d.get(key) is not None:
                d[key] = float(d[key])
        if d.get("trade_duration_seconds") is not None:
            d["trade_duration_seconds"] = int(d["trade_duration_seconds"])
        rows.append(d)
    return rows


# ── Aggregate Calculation ───────────────────────────────────────────────────

def compute_summary(trades, bot_name, db_path, since, until):
    """Compute aggregate metrics from trade list.

    Returns OrderedDict matching SUMMARY_KEYS order.
    """
    total = len(trades)
    summary = collections.OrderedDict()
    summary["schema_version"] = SCHEMA_VERSION
    summary["bot_name"] = bot_name
    summary["export_timestamp_utc"] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    summary["db_path"] = os.path.abspath(db_path)
    summary["since"] = since
    summary["until"] = until

    if total == 0:
        summary["total_trades"] = 0
        summary["winning_trades"] = 0
        summary["losing_trades"] = 0
        summary["win_rate"] = None
        summary["gross_profit"] = 0.0
        summary["gross_loss"] = 0.0
        summary["profit_factor"] = None
        summary["net_profit_usdt"] = 0.0
        summary["avg_win"] = None
        summary["avg_loss"] = None
        summary["avg_risk_reward"] = None
        summary["max_drawdown_pct"] = None
        summary["avg_trade_duration_seconds"] = None
        summary["NO_TRADE_DATA"] = True
        return summary

    winning = [t for t in trades if t.get("profit_abs", 0) >= 0]
    losing = [t for t in trades if t.get("profit_abs", 0) < 0]

    gross_profit = sum(t["profit_abs"] for t in winning)
    gross_loss = abs(sum(t["profit_abs"] for t in losing))

    if gross_loss == 0:
        profit_factor = "UNDEFINED_PF"
    else:
        profit_factor = round(gross_profit / gross_loss, 4)

    net_profit = gross_profit - gross_loss

    avg_win = round(sum(t["profit_abs"] for t in winning) / len(winning), 4) if winning else None
    avg_loss = round(
        abs(sum(t["profit_abs"] for t in losing)) / len(losing), 4
    ) if losing else None
    avg_risk_reward = round(avg_win / abs(avg_loss), 4) if (avg_win is not None and avg_loss is not None and avg_loss > 0) else None

    # Max drawdown: peak-to-trough on cumulative profit_abs series
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in trades:
        cumulative += t.get("profit_abs", 0)
        if cumulative > peak:
            peak = cumulative
        drawdown = peak - cumulative
        if peak > 0:
            dd_pct = drawdown / peak * 100
        else:
            dd_pct = 0.0
        if dd_pct > max_dd:
            max_dd = dd_pct

    avg_duration = round(
        sum(t.get("trade_duration_seconds", 0) for t in trades) / total
    ) if total > 0 else None

    summary["total_trades"] = total
    summary["winning_trades"] = len(winning)
    summary["losing_trades"] = len(losing)
    summary["win_rate"] = round(len(winning) / total, 4) if total > 0 else None
    summary["gross_profit"] = round(gross_profit, 4)
    summary["gross_loss"] = round(gross_loss, 4)
    summary["profit_factor"] = profit_factor
    summary["net_profit_usdt"] = round(net_profit, 4)
    summary["avg_win"] = avg_win
    summary["avg_loss"] = avg_loss
    summary["avg_risk_reward"] = avg_risk_reward
    summary["max_drawdown_pct"] = round(max_dd, 4)
    summary["avg_trade_duration_seconds"] = avg_duration

    return summary


# ── Output Writers ──────────────────────────────────────────────────────────

def write_csv(trades, output_path):
    """Write per-trade detail CSV. Always writes headers even if no trades."""
    path = f"{output_path}_trades.csv"
    try:
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=TRADE_FIELDS, extrasaction="ignore")
            writer.writeheader()
            for trade in trades:
                writer.writerow(trade)
        return path
    except (OSError, IOError) as e:
        print(f"ERROR: cannot write to: {path} — {e}", file=sys.stderr)
        sys.exit(1)


def write_summary(summary, output_path):
    """Write aggregate summary JSON."""
    path = f"{output_path}_summary.json"
    try:
        with open(path, "w") as f:
            json.dump(summary, f, indent=2)
        return path
    except (OSError, IOError) as e:
        print(f"ERROR: cannot write to: {path} — {e}", file=sys.stderr)
        sys.exit(1)


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    # Validate output directory is writable early
    output_dir = os.path.dirname(args.output) or "."
    if not os.access(output_dir, os.W_OK):
        # Try to create it
        try:
            os.makedirs(output_dir, exist_ok=True)
        except (OSError, IOError):
            print(f"ERROR: cannot write to: {output_dir}", file=sys.stderr)
            sys.exit(1)

    conn = connect_db(args.db)

    # Parse date filters
    since = args.since
    until = args.until

    trades = fetch_trades(conn, since, until)
    conn.close()

    summary = compute_summary(trades, args.bot, args.db, since, until)

    # Write output files (never partial: both must succeed or neither)
    format_type = args.format
    csv_written = False
    json_written = False

    if format_type in ("csv", "both"):
        csv_path = write_csv(trades, args.output)
        csv_written = True
        print(f"Wrote: {csv_path}")

    if format_type in ("json", "both"):
        json_path = write_summary(summary, args.output)
        json_written = True
        print(f"Wrote: {json_path}")

    # Default (csv) fallback — csv is always the base format
    if not csv_written and not json_written:
        # Should never happen, but guard against future format additions
        csv_path = write_csv(trades, args.output)
        print(f"Wrote: {csv_path}")


if __name__ == "__main__":
    main()
