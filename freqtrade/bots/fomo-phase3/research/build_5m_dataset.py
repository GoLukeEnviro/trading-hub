#!/usr/bin/env python3
"""
build_5m_dataset.py — Download echte 5m BTC/USDT:USDT OHLCV von Bitget (2022→heute)
+ merge Funding Rate aus 1h-Feather (forward-fill auf 5m)
+ synthetischer OI-Proxy (close * volume * konstante)

Output: research/data/btc_5m_feather
"""

import os, sys, time, json
from datetime import datetime, timezone

import ccxt
import pandas as pd
import numpy as np

# ── Config ──────────────────────────────────────────────────────────────
PAIR_CCXT = "BTC/USDT:USDT"
TIMEFRAME = "5m"
LIMIT = 200                     # Bitget max per call
START_DATE = "2022-01-01T00:00:00Z"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(OUTPUT_DIR, exist_ok=True)

FEATHER_PATH = os.path.join(OUTPUT_DIR, "btc_5m.feather")
CSV_PATH = os.path.join(OUTPUT_DIR, "btc_5m.csv")
STATS_PATH = os.path.join(OUTPUT_DIR, "btc_5m_stats.json")

# Funding rate feather (1h, open col = funding rate value)
FUNDING_FEATHER = (
    "/home/hermes/projects/trading/freqtrade/bots/"
    "regime-hybrid/user_data/data/bitget/futures/"
    "BTC_USDT_USDT-1h-funding_rate.feather"
)

# OI proxy constant (BTC ~ 10x leverage equivalent)
OI_PROXY_MULT = 10.0


def fetch_ohlcv_backward(exchange, pair, tf, limit, start_ts_ms):
    """
    Backward-paginated OHLCV fetch from Bitget.
    Starts from latest candle, walks backward until start_ts_ms.
    """
    all_candles = []

    # 1. Fetch latest batch (no since parameter)
    sys.stdout.write("  Fetching latest batch... ")
    sys.stdout.flush()
    batch = exchange.fetch_ohlcv(pair, tf, limit=limit)
    if not batch:
        raise RuntimeError("Empty response from exchange")
    all_candles.extend(batch)
    print(f"{len(batch)} candles (oldest: {datetime.utcfromtimestamp(batch[0][0]/1000).strftime('%Y-%m-%d')})")

    tf_ms = exchange.parse_timeframe(tf) * 1000
    total_batches = 1
    rate_limit_sleep = 0.1  # 100ms between calls

    while True:
        oldest_ts = all_candles[0][0]

        # Stop if we've reached our target start date
        if oldest_ts <= start_ts_ms:
            print(f"  ✓ Reached target start date ({datetime.utcfromtimestamp(start_ts_ms/1000).strftime('%Y-%m-%d')})")
            break

        since = oldest_ts - (limit * tf_ms)
        if since <= 0:
            since = 1

        time.sleep(rate_limit_sleep)
        batch = exchange.fetch_ohlcv(pair, tf, since=since, limit=limit)
        total_batches += 1

        if not batch:
            print("  ∅ Empty batch — reached beginning of data")
            break

        # Filter candles strictly older than current oldest
        new_candles = [c for c in batch if c[0] < oldest_ts]
        if not new_candles:
            print("  ∅ No new candles (overlap boundary)")
            break

        all_candles = new_candles + all_candles

        if total_batches % 50 == 0:
            oldest_dt = datetime.utcfromtimestamp(all_candles[0][0]/1000).strftime('%Y-%m-%d')
            sys.stdout.write(f"\r  ... batch {total_batches}, oldest: {oldest_dt} ({len(all_candles):,} candles)")
            sys.stdout.flush()

        # Stop if batch shorter than limit (reached end of available data)
        if len(batch) < limit:
            print(f"\n  ✓ Reached end of exchange data (batch < limit)")
            break

    print(f"\n  Done: {total_batches} batches, {len(all_candles):,} total candles")
    return all_candles


def build_dataframe(candles):
    """Convert raw candle list to DataFrame."""
    df = pd.DataFrame(candles, columns=[
        "timestamp", "open", "high", "low", "close", "volume"
    ])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df


def add_oi_proxy(df, multiplier=OI_PROXY_MULT):
    """Synthetic Open Interest proxy: close * volume * multiplier."""
    df["open_interest"] = df["close"] * df["volume"] * multiplier
    return df


def add_funding_rate(df, funding_feather_path):
    """
    Merge 1h funding rate data (forward-filled to 5m).
    Funding rate file has 'date' and funding value in 'open' column.
    """
    if not os.path.exists(funding_feather_path):
        print(f"  ⚠ Funding rate file not found: {funding_feather_path}")
        df["funding_rate"] = 0.0
        return df

    fr = pd.read_feather(funding_feather_path)
    fr = fr.rename(columns={
        "date": "timestamp",
        "open": "funding_rate"
    })
    fr["timestamp"] = pd.to_datetime(fr["timestamp"], utc=True)
    fr = fr[["timestamp", "funding_rate"]].sort_values("timestamp").drop_duplicates()

    # Funding rate is published every 8h. Forward-fill to 5m.
    # Set timestamp as index for reindex
    full_range = pd.date_range(
        start=df["timestamp"].min(),
        end=df["timestamp"].max(),
        freq="5min",
        tz="UTC"
    )
    fr_idx = fr.set_index("timestamp").reindex(full_range, method="ffill")
    fr_idx.index.name = "timestamp"
    fr_idx = fr_idx.reset_index()

    # Merge into main df
    df = df.merge(fr_idx, on="timestamp", how="left")
    df["funding_rate"] = df["funding_rate"].fillna(0.0)

    # Stats
    funding_start = fr["timestamp"].min()
    funding_end = fr["timestamp"].max()
    has_funding = (df["timestamp"] >= funding_start) & (df["timestamp"] <= funding_end)
    print(f"  Funding rate: {funding_start} → {funding_end} ({has_funding.sum():,} of {len(df):,} 5m bars have real funding)")
    return df


def main():
    print("=" * 60)
    print(f"build_5m_dataset.py — BTC/USDT:USDT 5m OHLCV Download")
    print(f"Start: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    # ── Exchange setup ──
    exchange = ccxt.bitget({
        "enableRateLimit": True,
        "options": {"defaultType": "swap"},
    })

    start_ts_ms = exchange.parse8601(START_DATE)
    now_ts_ms = exchange.milliseconds()
    bars_estimate = (now_ts_ms - start_ts_ms) / (exchange.parse_timeframe(TIMEFRAME) * 1000)
    print(f"\nTarget: {START_DATE} → now = {int(bars_estimate):,} bars @ {TIMEFRAME}")
    print(f"API calls needed: ~{int(bars_estimate / LIMIT) + 1}")

    # ── Fetch OHLCV ──
    print(f"\n▶ Fetching OHLCV...")
    t0 = time.time()
    candles = fetch_ohlcv_backward(exchange, PAIR_CCXT, TIMEFRAME, LIMIT, start_ts_ms)
    elapsed = time.time() - t0
    print(f"  Fetch time: {elapsed:.1f}s ({elapsed/60:.1f}min)")

    # ── Build DataFrame ──
    print(f"\n▶ Building DataFrame...")
    df = build_dataframe(candles)
    print(f"  {len(df):,} rows, {df['timestamp'].min()} → {df['timestamp'].max()}")
    print(f"  {df.isna().sum().sum()} NaN values")

    # ── OI Proxy ──
    print(f"\n▶ Adding OI proxy (close × volume × {OI_PROXY_MULT})...")
    df = add_oi_proxy(df)

    # ── Funding Rate ──
    print(f"\n▶ Merging funding rate...")
    df = add_funding_rate(df, FUNDING_FEATHER)

    # ── Final validation ──
    print(f"\n▶ Final DataFrame:")
    print(f"  Shape: {df.shape}")
    print(f"  Columns: {list(df.columns)}")
    print(f"  Date range: {df['timestamp'].min()} → {df['timestamp'].max()}")
    print(f"  Memory: {df.memory_usage(deep=True).sum() / 1024**2:.1f} MB")
    print(f"  NaN check:")
    for col in df.columns:
        nans = df[col].isna().sum()
        if nans > 0:
            print(f"    {col}: {nans:,} NaN ({nans/len(df)*100:.1f}%)")

    # ── Save ──
    print(f"\n▶ Saving...")
    df.to_feather(FEATHER_PATH)
    df.to_csv(CSV_PATH, index=False)
    print(f"  Feather: {FEATHER_PATH}")
    print(f"  CSV:     {CSV_PATH}")

    # ── Stats ──
    stats = {
        "shape": list(df.shape),
        "columns": list(df.columns),
        "date_start": str(df["timestamp"].min()),
        "date_end": str(df["timestamp"].max()),
        "total_bars": len(df),
        "fetch_time_seconds": round(elapsed, 1),
        "fetch_time_minutes": round(elapsed / 60, 1),
        "api_calls_estimate": int(len(candles) / LIMIT) + 1,
    }
    with open(STATS_PATH, "w") as f:
        json.dump(stats, f, indent=2, default=str)
    print(f"  Stats:   {STATS_PATH}")

    print(f"\n{'=' * 60}")
    print(f"Done: {datetime.now(timezone.utc).isoformat()}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
