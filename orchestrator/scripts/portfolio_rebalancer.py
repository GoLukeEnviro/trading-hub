#!/usr/bin/env python3
"""
Portfolio Rebalancer v2 – Semi-automatisch
Shannon's Demon + Half-Kelly + Volatility-Drag-Korrektur

Liest SQLite-DBs direkt vom Host (bind-mounts).
KEIN numpy required – pure Python stdlib.
KEIN Live-Trading – gibt nur Empfehlungen aus.
"""

import json, sqlite3, math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict

REBALANCE_INTERVAL_DAYS = 7
LOOKBACK_DAYS = 30
HALF_KELLY_MULTIPLIER = 0.5
MIN_TRADES_FOR_KELLY = 15

BOTS = {
    "freqforge": {
        "name": "FreqForge MAIN",
        "container": "trading-freqtrade-freqforge-1",
        "db_path": "/home/hermes/projects/trading/freqforge/user_data/tradesv3.freqforge.dryrun.sqlite",
        "current_weight": 0.40,
        "max_open_trades_limit": 5,
        "stoploss": -0.09,
    },
    "canary": {
        "name": "FreqForge Canary",
        "container": "trading-freqtrade-freqforge-canary-1",
        "db_path": "/home/hermes/projects/trading/freqforge-canary/user_data/tradesv3.freqforge_canary.dryrun.sqlite",
        "current_weight": 0.25,
        "max_open_trades_limit": 3,
        "stoploss": -0.08,
    },
    "regime_hybrid": {
        "name": "Regime-Hybrid",
        "container": "trading-freqtrade-regime-hybrid-1",
        "db_path": "/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/user_data/tradesv3.regime_hybrid.dryrun.sqlite",
        "current_weight": 0.20,
        "max_open_trades_limit": 3,
        "stoploss": -0.07,
    },
    "momentum": {
        "name": "Momentum",
        "container": "freqtrade-momentum",
        "db_path": "/home/hermes/projects/trading/freqtrade/bots/momentum/user_data/tradesv3.momentum.dryrun.sqlite",
        "current_weight": 0.10,
        "max_open_trades_limit": 2,
        "stoploss": -0.06,
    },
    "rebel": {
        "name": "FreqAI-rebel",
        "container": "trading-freqai-rebel-1",
        "db_path": None,  # Uses Docker volume, not bind-mounted
        "current_weight": 0.05,
        "max_open_trades_limit": 3,
        "stoploss": -0.08,
    },
}

STATE_FILE = Path("/opt/data/profiles/orchestrator/state/rebalance_state.json")
LOG_FILE   = Path("/opt/data/profiles/orchestrator/logs/rebalancer.log")


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def get_bot_performance(db_path, days=30):
    """Read closed trade performance from SQLite. Pure Python, no numpy."""
    if not db_path or not Path(db_path).exists():
        return {"winrate": 0.5, "avg_win": 0.01, "avg_loss": -0.02,
                "trades": 0, "profit_std": 0.02, "valid": False}

    conn = sqlite3.connect(db_path)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    rows = [r[0] for r in conn.execute(
        "SELECT close_profit FROM trades WHERE close_date >= ? AND is_open = 0", (since,)
    ).fetchall()]
    conn.close()

    if len(rows) < 5:
        return {"winrate": 0.5, "avg_win": 0.01, "avg_loss": -0.02,
                "trades": len(rows), "profit_std": 0.02, "valid": False}

    wins = [r for r in rows if r > 0]
    losses = [r for r in rows if r < 0]
    mean = sum(rows) / len(rows)
    variance = sum((r - mean) ** 2 for r in rows) / len(rows)

    return {
        "winrate": len(wins) / len(rows),
        "avg_win":  sum(wins) / len(wins) if wins else 0.01,
        "avg_loss": sum(losses) / len(losses) if losses else -0.02,
        "trades": len(rows),
        "profit_std": math.sqrt(variance),
        "valid": len(rows) >= MIN_TRADES_FOR_KELLY,
    }


def calc_kelly(w, aw, al):
    """Kelly fraction: f* = W - (1-W)/R where R = |avg_win/avg_loss|"""
    if abs(al) < 1e-6:
        return 0.01
    R = abs(aw / al)
    return max(0.005, min(w - (1 - w) / R, 0.30))


def drag_adjust(weight, std):
    """Volatility-Drag-Korrektur: reduziert Weight bei hoher Volatilitaet"""
    return max(0.005, weight * (1 - (std ** 2) / 2))


def run_rebalancer(dry_run=True):
    log("=" * 60)
    log(f"Rebalancer START (dry_run={dry_run})")
    log(f"Method: Half-Kelly + Volatility-Drag + Shannon-Rebalancing")

    scores, total = {}, 0.0
    for bot_id, cfg in BOTS.items():
        perf = get_bot_performance(cfg["db_path"])
        kelly = calc_kelly(perf["winrate"], perf["avg_win"], perf["avg_loss"])
        hk = drag_adjust(kelly * HALF_KELLY_MULTIPLIER, perf["profit_std"])
        scores[bot_id] = {"perf": perf, "kelly": kelly, "hk": hk}
        total += hk
        log(f"  {cfg['name']:20s}: Kelly={kelly:.3f} HalfKelly={hk:.3f} "
            f"WR={perf['winrate']:.1%} Trades={perf['trades']:3d} "
            f"{'VALID' if perf['valid'] else 'LOW-N'}")

    if total == 0:
        total = 1.0
        log("  WARNING: total=0, normalizing to equal weight")

    recs = {}
    for bot_id, s in scores.items():
        cfg = BOTS[bot_id]
        tw = max(0.05, min(s["hk"] / total, 0.50))
        delta = tw - cfg["current_weight"]
        new_mot = max(1, min(int(round(tw * cfg["max_open_trades_limit"] / 0.40)),
                             cfg["max_open_trades_limit"]))
        action = "INCREASE" if delta > 0.05 else "DECREASE" if delta < -0.05 else "HOLD"
        recs[bot_id] = {
            "name": cfg["name"],
            "container": cfg["container"],
            "current_weight": cfg["current_weight"],
            "target_weight": round(tw, 4),
            "delta": round(delta, 4),
            "new_max_open_trades": new_mot,
            "action": action,
        }
        log(f"  -> {cfg['name']:20s}: {cfg['current_weight']:.0%} -> {tw:.0%} "
            f"({'+' if delta >= 0 else ''}{delta:.0%}) mot={new_mot} [{action}]")

    output = {
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "dry_run": dry_run,
        "method": "Half-Kelly + Volatility-Drag + Shannon-Rebalancing",
        "interval_days": REBALANCE_INTERVAL_DAYS,
        "min_trades_for_kelly": MIN_TRADES_FOR_KELLY,
        "recommendations": recs,
        "next_due": (datetime.now(timezone.utc) + timedelta(days=REBALANCE_INTERVAL_DAYS)).isoformat() + "Z",
    }

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(output, f, indent=2)
    log(f"State written -> {STATE_FILE}")

    # Summary
    active = sum(1 for r in recs.values() if r["action"] != "HOLD")
    log(f"Summary: {active}/{len(recs)} bots need rebalancing")
    log("Rebalancer END")
    return output


if __name__ == "__main__":
    import sys
    result = run_rebalancer(dry_run="--live" not in sys.argv)
    # Print final JSON for cron capture
    print("\n--- JSON OUTPUT ---")
    print(json.dumps(result, indent=2))
