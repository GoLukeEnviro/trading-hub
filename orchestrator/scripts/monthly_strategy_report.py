#!/usr/bin/env python3
"""
Monthly Strategy Report — generates a summary of best/worst strategies.
Runs on the 1st of each month. Output delivered via Hermes cron to user.
"""
import json, os, subprocess, sys
from datetime import datetime, timezone

BASE = "/home/hermes/projects/trading"

FLEET_BOTS = {
    "freqtrade-freqforge": {
        "dbs": ["/freqtrade/user_data/tradesv3.freqforge.dryrun.sqlite", "/freqtrade/tradesv3.dryrun.sqlite"],
        "label": "FreqForge",
        "strategy": "FreqForge_Override",
    },
    "freqtrade-regime-hybrid": {
        "dbs": ["/freqtrade/user_data/tradesv3.regime_hybrid.dryrun.sqlite"],
        "label": "Regime-Hybrid",
        "strategy": "RegimeSwitchingHybrid_v7",
    },
    "freqtrade-freqforge-canary": {
        "dbs": ["/freqtrade/user_data/tradesv3.freqforge_canary.dryrun.sqlite"],
        "label": "Canary",
        "strategy": "FreqForge_Override (Spot)",
    },
    "freqai-rebel": {
        "dbs": ["/freqtrade/tradesv3.dryrun.sqlite", "/freqtrade/user_data/tradesv3.dryrun.sqlite"],
        "label": "Rebel",
        "strategy": "RebelLiquidation+XGBoost",
    },
}

results = []

for container, info in FLEET_BOTS.items():
    for db in info["dbs"]:
        r = subprocess.run(
            ["docker", "exec", container, "sqlite3", db,
             "SELECT count(*), "
             "round(sum(close_profit_abs),4), "
             "round(100.0*sum(case when close_profit>0 then 1 else 0 end)/max(count(*),1),1), "
             "round(avg(case when close_profit>0 then close_profit_abs end),4), "
             "round(avg(case when close_profit<0 then close_profit_abs end),4), "
             "round(min(close_profit_abs),4), "
             "round(max(close_profit_abs),4) "
             "FROM trades WHERE is_open=0;"],
            capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and "|" in r.stdout.strip():
            parts = r.stdout.strip().split("|")
            n = int(parts[0])
            if n == 0:
                continue
            results.append({
                "label": info["label"],
                "strategy": info["strategy"],
                "trades": n,
                "pnl": float(parts[1]),
                "wr": float(parts[2]),
                "avg_win": float(parts[3]) if parts[3] else 0,
                "avg_loss": float(parts[4]) if parts[4] else 0,
                "worst": float(parts[5]) if parts[5] else 0,
                "best": float(parts[6]) if parts[6] else 0,
            })
            break

# Sort by PnL
results.sort(key=lambda x: x["pnl"], reverse=True)

now = datetime.now(timezone.utc)
print(f"=== MONATLICHER STRATEGIE-REPORT ({now.strftime('%B %Y')}) ===")
print()
print(f"{'Bot':15s} | {'Strategie':30s} | {'Trades':>6s} | {'PnL':>8s} | {'WR%':>5s} | {'Avg Win':>8s} | {'Avg Loss':>8s} | Verdict")
print("-" * 120)

for r in results:
    if r["pnl"] > 0 and r["wr"] > 60:
        verdict = "PROFITABLE"
    elif r["pnl"] > 0:
        verdict = "MARGINAL +"
    elif r["wr"] > 50:
        verdict = "LOSS ASYMM."
    else:
        verdict = "LOSING"
    print(f"{r['label']:15s} | {r['strategy']:30s} | {r['trades']:6d} | {r['pnl']:>8.2f} | {r['wr']:>5.1f} | {r['avg_win']:>8.4f} | {r['avg_loss']:>8.4f} | {verdict}")

print()
print("=== BESTE STRATEGIE ===")
if results:
    best = results[0]
    print(f"  {best['label']} ({best['strategy']}): PnL={best['pnl']:+.2f} USDT, WR={best['wr']}%, {best['trades']} Trades")

print()
print("=== SCHLECHTESTE STRATEGIE ===")
if results:
    worst = results[-1]
    print(f"  {worst['label']} ({worst['strategy']}): PnL={worst['pnl']:+.2f} USDT, WR={worst['wr']}%, {worst['trades']} Trades")

print()
print("=== EMPFEHLUNGEN ===")
for r in results:
    if r["pnl"] < 0 and r["wr"] < 35:
        print(f"  QUARANTINE: {r['label']} — WR {r['wr']}% < 35%, PnL {r['pnl']:+.2f}")
    elif r["pnl"] < 0 and r["wr"] > 60:
        print(f"  STOP-LOSS REVIEW: {r['label']} — WR {r['wr']}% gut aber PnL {r['pnl']:+.2f} (Loss-Asymmetrie)")
    elif r["pnl"] > 0:
        print(f"  BEHALTEN: {r['label']} — profitabel, PnL {r['pnl']:+.2f}")

print()
total_pnl = sum(r["pnl"] for r in results)
print(f"GESAMT PnL FLEET: {total_pnl:+.2f} USDT")
