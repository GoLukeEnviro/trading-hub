from __future__ import annotations

"""Central fleet equity updater for Freqtrade dry-run bots.

This script is intentionally stdlib-only so it can run from host cron without
needing pandas/pyarrow. It reads each bot's SQLite trades DB, estimates source
capital, and writes a shared fleet-risk snapshot via FleetRiskManager.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Tuple

from fleet_risk_manager import FleetRiskManager

ROOT = Path(__file__).resolve().parents[2]

BOT_SPECS = [
    {
        "name": "FreqForge MAIN",
        "source": "baseline_v1_freqforge",
        "config_path": ROOT / "freqforge" / "config" / "config_freqforge_dryrun.json",
        "db_path": ROOT / "freqforge" / "user_data" / "tradesv3.freqforge.dryrun.sqlite",
    },
    {
        "name": "FreqForge Canary",
        "source": "freqforge_canary_v1",
        "config_path": ROOT / "freqforge-canary" / "config" / "config_canary_dryrun.json",
        "db_path": ROOT / "freqforge-canary" / "user_data" / "tradesv3.freqforge_canary.dryrun.sqlite",
    },
    {
        "name": "Regime-Hybrid v3",
        "source": "regime_hybrid_dryrun",
        "config_path": ROOT / "freqtrade" / "bots" / "regime-hybrid" / "config" / "config_regime_hybrid_dryrun.json",
        "db_path": ROOT / "freqtrade" / "bots" / "regime-hybrid" / "user_data" / "tradesv3.regime_hybrid.dryrun.sqlite",
    },
]


def load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def query_trades(db_path: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float, int, int]:
    """Return (open_rows, closed_rows, closed_profit_sum, open_longs, open_shorts)."""
    if not db_path.exists():
        return [], [], 0.0, 0, 0

    open_rows: List[Dict[str, Any]] = []
    closed_rows: List[Dict[str, Any]] = []
    closed_profit = 0.0
    open_longs = 0
    open_shorts = 0

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, pair, is_short, stake_amount, close_profit, close_profit_abs,
                   realized_profit, open_date, close_date, is_open
            FROM trades
            ORDER BY id ASC
            """
        )
        for row in cur.fetchall():
            record = {
                "trade_id": row[0],
                "pair": row[1],
                "is_short": bool(row[2]),
                "stake_amount": row[3],
                "close_profit": row[4],
                "close_profit_abs": row[5],
                "realized_profit": row[6],
                "open_date": row[7],
                "close_date": row[8],
            }
            if row[9]:
                open_rows.append(record)
                if bool(row[2]):
                    open_shorts += 1
                else:
                    open_longs += 1
            else:
                closed_rows.append(record)
                closed_profit += float(row[6] or row[5] or row[4] or 0.0)
    finally:
        conn.close()

    return open_rows, closed_rows, closed_profit, open_longs, open_shorts


def main() -> int:
    rm = FleetRiskManager()
    total_equity = 0.0
    lines: List[str] = []

    for spec in BOT_SPECS:
        config = load_json(spec["config_path"])
        source = str(config.get("bot_name") or spec["source"])
        dry_run_wallet = float(config.get("dry_run_wallet", 1000.0))

        open_rows, closed_rows, closed_profit, open_longs, open_shorts = query_trades(spec["db_path"])
        if not spec["db_path"].exists():
            lines.append(f"[{spec['name']}] DB fehlt: {spec['db_path']}")
            continue

        source_equity = dry_run_wallet + closed_profit
        rm.update_source_equity(source, source_equity)
        rm.sync_trade_state(source=source, open_trades=open_rows, closed_trades=closed_rows)

        total_equity += source_equity
        lines.append(
            f"[{spec['name']}] source={source} equity={source_equity:.2f} "
            f"realized={closed_profit:+.2f} closed={len(closed_rows)} open={len(open_rows)} "
            f"long={open_longs} short={open_shorts}"
        )

    rm.update_portfolio_equity(total_equity)
    summary = rm.summarize_state()
    lines.append(
        f"FLEET equity={summary.get('current_equity', 0.0) or 0.0:.2f} "
        f"peak={summary.get('peak_equity', 0.0) or 0.0:.2f} "
        f"DD={float(summary.get('current_drawdown', 0.0) or 0.0):.2%} "
        f"level={summary.get('drawdown_level')} open={summary.get('open_trades', 0)} "
        f"history={summary.get('trade_history', 0)}"
    )

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
