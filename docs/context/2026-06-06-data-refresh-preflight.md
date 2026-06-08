# Data Refresh Preflight — 2026-06-06

## System State
- Disk: 116G free (60% used)
- All 5 containers healthy
- All dry_run=true ✅
- Git: ahead 13, clean except docs

## Bot Details

| Bot | Config | Strategy | Exchange | Timeframe | Pairs | Data Files | Latest Data | Data Fresh? |
|-----|--------|----------|----------|-----------|-------|------------|-------------|-------------|
| **FreqForge** | freqforge/user_data/config.json | FreqForge_Override | bitget | 15m + 1h inf | BTC, ETH, SOL | 49 | 2026-05-17 | ❌ stale |
| **Canary** | freqforge-canary/user_data/config.json | FreqForge_Override | bitget | 15m + 1h inf | BTC, ETH, SOL, LINK, DOT, ATOM, UNI, AAVE | **0** | — | ❌ missing |
| **Regime-Hybrid** | freqtrade/bots/regime-hybrid/user_data/config.json | RegimeSwitchingHybrid_v7_v04 | bitget | 15m + 1h inf | BTC, SOL, AVAX, NEAR, ARB | 132 | 2026-05-30 | ❌ stale |
| **FreqAI-Rebel** | freqtrade/bots/freqai-rebel/user_data/config.json | RebelLiquidation | bitget | 5m + 15m/1h inf | BTC, ETH | 10 | 2026-05-17 | ❌ stale |

## Canary Data Gap Diagnosis
Canary uses its own user_data at `freqforge-canary/user_data/data/` which is EMPTY.
It does NOT share FreqForge's data directory. The docker-compose mounts:
- FreqForge: `./freqforge/user_data:/freqtrade/user_data`
- Canary: `./freqforge-canary/user_data:/freqtrade/user_data`

These are separate bind mounts. Canary needs its own download or a shared data volume.

## Download Plan
All bots use `exchange: bitget` and `trading_mode: futures`.

1. **FreqForge** — 180 days, BTC/ETH/SOL 15m + 1h
2. **Regime-Hybrid** — 180 days, BTC/SOL/AVAX/NEAR/ARB 15m + 1h
3. **FreqAI-Rebel** — 180 days, BTC/ETH 5m + 15m + 1h (needs all FreqAI timeframes)
4. **Canary** — investigate shared data approach (FreqForge has the data already — Canary needs same pairs)
