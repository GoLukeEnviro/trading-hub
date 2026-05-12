#!/usr/bin/env python3
"""Audit: verify baseline identity in v1.3.3 CSV."""
import csv
from statistics import mean, median
from collections import defaultdict

CSV = "/home/hermes/primoagent/output/backtests/crypto_signal_backtest_v1_3_3.csv"

# Full scan
all_buy = 0; all_buy_id = 0
all_sell = 0; all_sell_id = 0
variant_oos = defaultdict(list)

with open(CSV) as f:
    reader = csv.DictReader(f)
    for row in reader:
        action = row["action"]
        net = float(row["net_return_pct"])
        bl_long = float(row["baseline_long_net_pct"])
        bl_short = float(row["baseline_short_net_pct"])
        
        if action == "BUY":
            all_buy += 1
            if abs(net - bl_long) < 1e-15:
                all_buy_id += 1
        elif action == "SELL":
            all_sell += 1
            if abs(net - bl_short) < 1e-15:
                all_sell_id += 1
        
        if row["split"] == "oos" and row["horizon_hours"] == "24":
            key = (row["variant"], row["timeframe"])
            variant_oos[key].append({
                "action": action,
                "net": net,
                "pair": row["pair"],
                "fold": int(row["fold_id"]),
            })

print("=" * 60)
print("BASELINE IDENTITY AUDIT — v1.3.3")
print("=" * 60)
print(f"\nALL BUY  net_return_pct == baseline_long_net_pct: {all_buy_id}/{all_buy}")
print(f"ALL SELL net_return_pct == baseline_short_net_pct: {all_sell_id}/{all_sell}")

if all_buy == all_buy_id and all_sell == all_sell_id:
    print("\n>>> CONFIRMED: Per-observation baseline fields are IDENTICAL to signal returns")
    print(">>> This is a STRUCTURAL artifact in the code (lines 331-334)")
else:
    print("\n>>> PARTIAL: Some observations differ — investigate")

print("\n" + "=" * 60)
print("OOS 24h SUMMARY BY VARIANT/TIMEFRAME")
print("=" * 60)
for (var, tf), rows in sorted(variant_oos.items()):
    nets = [r["net"] for r in rows]
    buys = [r for r in rows if r["action"] == "BUY"]
    sells = [r for r in rows if r["action"] == "SELL"]
    wr = sum(1 for n in nets if n > 0) / len(nets) * 100 if nets else 0
    print(f"\n{var} / {tf}:")
    print(f"  Signals: {len(rows)} (BUY: {len(buys)}, SELL: {len(sells)})")
    print(f"  Mean: {mean(nets):.4f}%, Median: {median(nets):.4f}%, WR: {wr:.1f}%")

print("\n" + "=" * 60)
print("RULE MUTATION CHECK")
print("=" * 60)
print("EXPANSION_THRESHOLD = 0.5 (line 251) — used by bb_expansion, atr_expansion, volume_impulse")
print("vb_compression_release_v1 uses bb_p > 0.3 (line 274) — DIFFERENT threshold")
print("Near-band multiplier: 0.999/1.001 (lines 257-258)")
print("Comment says 'Use 0.98' but code uses 0.999 — possible relaxation")
