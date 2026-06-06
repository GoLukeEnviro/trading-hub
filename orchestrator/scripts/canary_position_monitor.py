#!/usr/bin/env python3
"""
Canary Position Monitor v1 — Monitors open Canary short positions.
Runs every 30 minutes. Alerts on:
  - Stale positions > 48h
  - Drawdown > 5% on any open position
  - Profit > 3% (trailing stop recommendation)

Advisory only — no automatic position management.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

CANARY_CONTAINER = "trading-freqtrade-freqforge-canary-1"
CANARY_DB = "/freqtrade/user_data/tradesv3.freqforge_canary.dryrun.sqlite"

# Thresholds
STALE_HOURS = 48
PROFIT_TRAIL_PCT = 3.0
DD_ALERT_PCT = 5.0


def run_cmd(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.stderr.strip()
    except Exception:
        return "", "timeout"


def get_open_trades():
    """Get open trades from canary DB."""
    sql = f"""
    SELECT 
      pair,
      CASE WHEN is_short THEN 'SHORT' ELSE 'LONG' END as direction,
      ROUND(stake_amount, 2) as stake,
      ROUND(open_rate, 2) as entry_price,
      ROUND(stop_loss, 2) as stoploss_price,
      open_date,
      enter_tag
    FROM trades WHERE is_open = 1;
    """
    out, err = run_cmd(f'docker exec {CANARY_CONTAINER} sqlite3 -json "{CANARY_DB}" "{sql}"', timeout=15)
    if out:
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return []
    return []


def get_current_price(symbol):
    """Get current price from Bitget API."""
    out, _ = run_cmd(
        f"curl -s 'https://api.bitget.com/api/v2/mix/market/ticker?productType=USDT-Futures&symbol={symbol}'",
        timeout=10
    )
    if out:
        try:
            data = json.loads(out)
            if data.get("data"):
                return float(data["data"][0]["lastPr"])
        except (json.JSONDecodeError, ValueError, IndexError, KeyError):
            pass
    return None


def analyze_position(trade):
    """Analyze a single open position."""
    pair = trade.get("pair", "")
    direction = trade.get("direction", "LONG")
    entry = float(trade.get("entry_price", 0))
    sl = float(trade.get("stoploss_price", 0))
    stake = float(trade.get("stake_amount", 0))
    open_date_str = trade.get("open_date", "")

    # Parse symbol for API
    symbol = pair.replace("/", "").replace(":USDT", "").replace("USDT", "USDT")
    base = pair.split("/")[0]
    symbol = f"{base}USDT"

    current_price = get_current_price(symbol)
    if current_price is None:
        return {"pair": pair, "error": "price fetch failed"}

    # Calculate PnL
    if direction == "SHORT":
        pnl_pct = (entry - current_price) / entry * 100
        sl_pct = (sl - entry) / entry * 100  # positive = loss if hit
    else:
        pnl_pct = (current_price - entry) / entry * 100
        sl_pct = (entry - sl) / entry * 100

    pnl_usdt = stake * pnl_pct / 100

    # Calculate hours open
    now = datetime.now(timezone.utc)
    hours_open = 0
    try:
        open_dt = datetime.fromisoformat(open_date_str.replace(" ", "T"))
        if open_dt.tzinfo is None:
            open_dt = open_dt.replace(tzinfo=timezone.utc)
        hours_open = (now - open_dt).total_seconds() / 3600
    except (ValueError, TypeError):
        pass

    return {
        "pair": pair,
        "direction": direction,
        "entry": entry,
        "current": current_price,
        "stoploss": sl,
        "stake": stake,
        "pnl_pct": round(pnl_pct, 2),
        "pnl_usdt": round(pnl_usdt, 2),
        "sl_distance_pct": round(sl_pct, 2),
        "hours_open": round(hours_open, 1),
        "is_stale": hours_open > STALE_HOURS,
        "recommend_trail": pnl_pct > PROFIT_TRAIL_PCT,
        "dd_alert": pnl_pct < -DD_ALERT_PCT,
    }


def main():
    trades = get_open_trades()
    if not trades:
        # No open trades — silent
        sys.exit(0)

    alerts = []
    recommendations = []

    for trade in trades:
        analysis = analyze_position(trade)
        if "error" in analysis:
            alerts.append(f"{analysis['pair']}: {analysis['error']}")
            continue

        pair = analysis["pair"]
        pnl = analysis["pnl_pct"]
        pnl_u = analysis["pnl_usdt"]
        hours = analysis["hours_open"]

        if analysis["dd_alert"]:
            alerts.append(
                f"DD ALERT L2: {pair} {analysis['direction']} "
                f"PnL={pnl:+.2f}% ({pnl_u:+.2f}U) | open {hours:.0f}h"
            )

        if analysis["is_stale"]:
            alerts.append(
                f"STALE: {pair} open {hours:.0f}h | PnL={pnl:+.2f}%"
            )

        if analysis["recommend_trail"]:
            recommendations.append(
                f"TRAIL RECOMMEND: {pair} {analysis['direction']} "
                f"PnL={pnl:+.2f}% — Trailing-Stop enger setzen"
            )

    if not alerts and not recommendations:
        # Healthy — silent
        sys.exit(0)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"CANARY POSITION MONITOR - {now}", "=" * 40, ""]

    for t in trades:
        a = analyze_position(t)
        if "error" in a:
            continue
        lines.append(
            f"  {a['pair']} {a['direction']}: "
            f"PnL={a['pnl_pct']:+.2f}% ({a['pnl_usdt']:+.2f}U) | "
            f"SL={a['sl_distance_pct']:.1f}% away | "
            f"open {a['hours_open']:.0f}h"
        )

    if alerts:
        lines.extend(["", "ALERTS"])
        for a in alerts:
            lines.append(f"  {a}")

    if recommendations:
        lines.extend(["", "RECOMMENDATIONS"])
        for r in recommendations:
            lines.append(f"  {r}")

    print("\n".join(lines))


if __name__ == "__main__":
    main()
