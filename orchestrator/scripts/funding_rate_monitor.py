#!/usr/bin/env python3
"""
Funding Rate Monitor — liest aktuelle Funding Rates von Bitget,
erkennt extreme Rates, schreibt Report + loggt Alerts.

Cron: 0 */4 * * * (alle 4 Stunden)
Alert-Schwelle: |rate| > 0.001 (0.1%)
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import ccxt

PROJECT_ROOT = Path("/home/hermes/projects/trading")
REPORT_PATH = PROJECT_ROOT / "freqtrade" / "shared" / "funding_rate_report.json"
SHADOW_LOG = PROJECT_ROOT / "orchestrator" / "logs" / "shadow_decisions.jsonl"

SYMBOLS = [
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
    "AVAX/USDT:USDT",
    "NEAR/USDT:USDT",
    "ARB/USDT:USDT",
]

ALERT_THRESHOLD = 0.001  # |rate| > 0.1% = ALERT


def fetch_funding_rates() -> dict:
    exchange = ccxt.bitget({
        "options": {"defaultType": "swap"},
        "enableRateLimit": True,
    })

    results = {}
    for symbol in SYMBOLS:
        try:
            rate_data = exchange.fetch_funding_rate(symbol)
            current_rate = float(rate_data.get("fundingRate", 0))
            next_time = rate_data.get("nextFundingDatetime", "")
            annual_pct = round(current_rate * 3 * 365 * 100, 4)

            results[symbol] = {
                "current_rate": current_rate,
                "next_funding_time": next_time,
                "annual_pct": annual_pct,
                "is_extreme": abs(current_rate) > ALERT_THRESHOLD,
            }
        except Exception as e:
            results[symbol] = {"current_rate": 0, "error": str(e), "is_extreme": False}

    return results


def write_report(results: dict) -> dict:
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "alert_threshold": ALERT_THRESHOLD,
        "symbols": results,
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)

    extreme = {s: r for s, r in results.items() if r.get("is_extreme")}
    return extreme


def log_extreme_rates(extreme: dict):
    if not extreme:
        return

    for symbol, data in extreme.items():
        entry = {
            "schema_version": "1.0",
            "event": "funding_rate_alert",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            "current_rate": data["current_rate"],
            "annual_pct": data.get("annual_pct", 0),
            "alert": f"FUNDING RATE EXTREME: {symbol} rate={data['current_rate']:.6f}",
        }
        with open(SHADOW_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")


def main():
    print(f"[FundingRateMonitor] Start {datetime.now(timezone.utc).isoformat()}")

    results = fetch_funding_rates()
    extreme = write_report(results)
    log_extreme_rates(extreme)

    total = len(results)
    alert_count = len(extreme)
    print(f"[FundingRateMonitor] {total} Symbole geprueft, {alert_count} Alerts")

    if alert_count > 0:
        for sym, data in extreme.items():
            print(f"  ALERT: {sym} rate={data['current_rate']:.6f} ({data.get('annual_pct', 0):.2f}% p.a.)")


if __name__ == "__main__":
    main()
