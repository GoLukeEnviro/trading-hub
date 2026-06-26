#!/usr/bin/env python3
"""
Heartbeat Intelligence Report Generator

Reads the SQLite Heartbeat-DB and generates a Markdown status report
for all bots tracked in the heartbeat table.

Usage:
    python3 heartbeat_intelligence.py [--db PATH] [--samples N] [--min-samples N]
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone


DEFAULT_DB = "/home/hermes/projects/trading/orchestrator/state/hermes_heartbeat.sqlite"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate a Heartbeat Intelligence Report from SQLite DB"
    )
    parser.add_argument(
        "--db",
        default=DEFAULT_DB,
        help=f"Path to SQLite heartbeat DB (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=24,
        help="Number of recent heartbeat rows per bot (default: 24)",
    )
    parser.add_argument(
        "--min-samples",
        type=int,
        default=4,
        help="Minimum samples required for a verdict (default: 4)",
    )
    return parser.parse_args()


def get_verdict(api_avail_pct, sample_count, min_samples):
    """Determine health verdict based on API availability percentage."""
    if sample_count < min_samples:
        return "UNKNOWN"
    if api_avail_pct >= 95.0:
        return "GREEN"
    if api_avail_pct >= 80.0:
        return "YELLOW"
    return "RED"


def fetch_bot_data(db_path, samples):
    """
    Fetch the last N heartbeat rows per bot from the database.

    Returns a dict: { bot_name: { 'rows': [...], 'api_avail': float, 'open_trades': int, 'ping_status': str } }
    """
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Discover all distinct bot names
    try:
        cursor.execute("SELECT DISTINCT bot_name FROM heartbeats ORDER BY bot_name")
        bots = [row["bot_name"] for row in cursor.fetchall()]
    except sqlite3.OperationalError:
        # Table might not exist yet
        conn.close()
        return {}

    result = {}

    for bot in bots:
        cursor.execute(
            """
            SELECT bot_name, timestamp, api_ok, open_trades, status
            FROM heartbeats
            WHERE bot_name = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (bot, samples),
        )
        rows = cursor.fetchall()

        if not rows:
            result[bot] = {
                "rows": [],
                "api_avail": 0.0,
                "open_trades": 0,
                "ping_status": "N/A",
                "sample_count": 0,
            }
            continue

        # API availability: percentage of rows where api_ok == 1
        api_ok_count = sum(1 for r in rows if r["api_ok"] == 1)
        sample_count = len(rows)
        api_avail = (api_ok_count / sample_count * 100.0) if sample_count > 0 else 0.0

        # Latest entry values
        latest = rows[0]
        open_trades = latest["open_trades"] if latest["open_trades"] is not None else 0
        ping_status = "pong" if latest["api_ok"] == 1 else "DOWN"

        result[bot] = {
            "rows": rows,
            "api_avail": api_avail,
            "open_trades": open_trades,
            "ping_status": ping_status,
            "sample_count": sample_count,
        }

    conn.close()
    return result


def generate_report(bot_data, min_samples):
    """Generate the Markdown report string."""
    now = datetime.now(timezone.utc)
    lines = []
    lines.append("# Heartbeat Intelligence Report")
    lines.append(f"Datum: {now.strftime('%Y-%m-%d %H:%M')} UTC")
    lines.append("")

    if not bot_data:
        lines.append("## Bot Status")
        lines.append("")
        lines.append("_Keine Bots in der Datenbank gefunden._")
        lines.append("")
        lines.append("## Gesamteinschätzung")
        lines.append("Keine Daten verfügbar.")
        print("\n".join(lines))
        return

    lines.append("## Bot Status")
    lines.append("")
    lines.append("| Bot | API % | Trades | Ping | Verdict |")
    lines.append("|-----|-------|--------|------|---------|")

    verdicts = []

    for bot in sorted(bot_data.keys()):
        data = bot_data[bot]
        api_pct = data["api_avail"]
        trades = data["open_trades"]
        ping = data["ping_status"]
        sample_count = data["sample_count"]
        verdict = get_verdict(api_pct, sample_count, min_samples)
        verdicts.append(verdict)

        lines.append(f"| {bot} | {api_pct:.1f}% | {trades} | {ping} | {verdict} |")

    lines.append("")

    # Gesamteinschätzung
    lines.append("## Gesamteinschätzung")
    lines.append("")

    total = len(verdicts)
    green = verdicts.count("GREEN")
    yellow = verdicts.count("YELLOW")
    red = verdicts.count("RED")
    unknown = verdicts.count("UNKNOWN")

    if total == 0:
        lines.append("Keine Bots vorhanden.")
    else:
        lines.append(f"{total} Bot(s) überwacht: "
                      f"{green} GREEN, {yellow} YELLOW, {red} RED, {unknown} UNKNOWN.")

        if red > 0:
            lines.append("")
            lines.append(f"**WARNUNG**: {red} Bot(s) mit RED-Status erkannt. "
                         "Sofortige Prüfung empfohlen.")
        elif yellow > 0:
            lines.append("")
            lines.append(f"Hinweis: {yellow} Bot(s) mit YELLOW-Status. "
                         "Beobachtung empfohlen.")

        if unknown > 0:
            lines.append("")
            lines.append(f"Hinweis: {unknown} Bot(s) mit UNKNOWN-Status "
                         "(zu wenige Samples für verlässliche Bewertung).")

        # Overall verdict
        lines.append("")
        if red > 0:
            lines.append("**Gesamtverdict: RED** — Mindestens ein Bot kritisch.")
        elif yellow > 0:
            lines.append("**Gesamtverdict: YELLOW** — Einschränkungen vorhanden.")
        elif unknown == total:
            lines.append("**Gesamtverdict: UNKNOWN** — Nicht genügend Daten.")
        else:
            lines.append("**Gesamtverdict: GREEN** — Alle Bots gesund.")

    print("\n".join(lines))


def main():
    args = parse_args()

    if not os.path.exists(args.db):
        print("DB not found", file=sys.stderr)
        sys.exit(0)

    bot_data = fetch_bot_data(args.db, args.samples)
    generate_report(bot_data, args.min_samples)

    sys.exit(0)


if __name__ == "__main__":
    main()
