#!/usr/bin/env python3
"""
portfolio_rebalancer.py — Portfolio weight rebalancing for active bots.

Runs weekly (Monday 06:00 UTC). Reads bot SQLite DBs, computes current
performance weights, and writes updated config suggestions to state.

Safety: dry_run=True always. No direct API calls.
"""

import json
import sqlite3
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

STATE_DIR = Path("/opt/data/profiles/orchestrator/state")
BOT_DB_BASE = Path("/home/hermes/projects/trading/freqtrade/bots")

BOTS = {
    "freqforge": {
        "name": "FreqForge",
        "container": "freqtrade-freqforge",
        "db_path": str(BOT_DB_BASE / "freqforge/user_data/tradesv3.freqforge.dryrun.sqlite"),
        "current_weight": 0.30,
        "max_open_trades_limit": 5,
        "stoploss": -0.05,
    },
    "canary": {
        "name": "FreqForge-Canary",
        "container": "freqtrade-freqforge-canary",
        "db_path": str(BOT_DB_BASE / "freqforge-canary/user_data/tradesv3.canary.dryrun.sqlite"),
        "current_weight": 0.20,
        "max_open_trades_limit": 3,
        "stoploss": -0.05,
    },
    "regime_hybrid": {
        "name": "Regime-Hybrid",
        "container": "freqtrade-regime-hybrid",
        "db_path": str(BOT_DB_BASE / "regime-hybrid/user_data/tradesv3.regime_hybrid.dryrun.sqlite"),
        "current_weight": 0.30,
        "max_open_trades_limit": 5,
        "stoploss": -0.06,
    },
    "rebel": {
        "name": "FreqAI-rebel",
        "container": "freqai-rebel",
        "db_path": str(BOT_DB_BASE / "freqai-rebel/user_data/tradesv3.rebel.dryrun.sqlite"),
        "current_weight": 0.20,
        "max_open_trades_limit": 2,
        "stoploss": -0.07,
    },
}


def ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def query_bot_stats(db_path: str) -> dict:
    """Read trade stats from bot SQLite DB."""
    if not os.path.exists(db_path):
        return {"error": f"DB not found: {db_path}", "total_profit": 0.0, "trade_count": 0, "win_rate": 0.0}
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*), SUM(close_profit_abs), "
            "SUM(CASE WHEN close_profit_abs > 0 THEN 1 ELSE 0 END) "
            "FROM trades WHERE is_open = 0"
        )
        row = cursor.fetchone()
        conn.close()
        count = row[0] or 0
        total_profit = row[1] or 0.0
        wins = row[2] or 0
        win_rate = (wins / count) if count > 0 else 0.0
        return {"trade_count": count, "total_profit": round(total_profit, 4), "win_rate": round(win_rate, 4)}
    except Exception as e:
        return {"error": str(e), "total_profit": 0.0, "trade_count": 0, "win_rate": 0.0}


def compute_weights(stats: dict) -> dict:
    """Compute new weights based on profit scores. Falls back to equal weight on errors."""
    scores = {}
    for bot_id, data in stats.items():
        if "error" in data:
            scores[bot_id] = 0.0
        else:
            # Score = win_rate * 0.5 + clipped_profit_factor * 0.5
            profit = max(min(data["total_profit"], 20.0), -20.0)
            profit_factor = (profit + 20.0) / 40.0
            scores[bot_id] = round(data["win_rate"] * 0.5 + profit_factor * 0.5, 4)

    total_score = sum(scores.values())
    if total_score <= 0:
        equal = round(1.0 / len(scores), 4)
        return {bot_id: equal for bot_id in scores}

    return {bot_id: round(score / total_score, 4) for bot_id, score in scores.items()}


def main():
    print(f"[{ts()}] portfolio_rebalancer.py — START")
    print(f"  Active bots: {list(BOTS.keys())}")

    stats = {}
    for bot_id, cfg in BOTS.items():
        stats[bot_id] = query_bot_stats(cfg["db_path"])
        print(f"  {bot_id}: {stats[bot_id]}")

    new_weights = compute_weights(stats)
    print(f"  Computed weights: {new_weights}")

    output = {
        "timestamp": ts(),
        "bots": {
            bot_id: {
                **BOTS[bot_id],
                "stats": stats[bot_id],
                "suggested_weight": new_weights[bot_id],
            }
            for bot_id in BOTS
        },
        "note": "dry_run=True — no live config changes applied",
    }

    out_path = STATE_DIR / "portfolio_rebalance_latest.json"
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"  Written: {out_path}")
    print(f"[{ts()}] portfolio_rebalancer.py — DONE")


if __name__ == "__main__":
    main()
