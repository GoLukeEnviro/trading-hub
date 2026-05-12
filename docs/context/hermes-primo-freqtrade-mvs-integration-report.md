# Hermes-Primo-Freqtrade MVS Integration Report

**Date:** 2026-05-11 23:51 UTC
**Status:** PARTIAL (Architecture deployed, backtest shows technical-only negative edge — LLM layer pending)

## 1. Implementation Summary

Deployed a three-layer trading pipeline:
- **Layer 1: Hermes Agent** — orchestrator (unchanged, bridge script ready)
- **Layer 2: PrimoAgent** — containerized with FastAPI (`primo-agent:latest`, port 8420)
- **Layer 3: Freqtrade** — MinimalViableStrategy_v1 on `freqtrade-mvs` (port 8087)

All containers on `ki-fabrik` network, dry-run only, no live credentials.

## 2. Files Changed

| File | Action | Purpose |
|------|--------|---------|
| `primo/primo_api.py` | CREATED | FastAPI wrapper for PrimoAgent signal generation |
| `primo/Dockerfile` | CREATED | PrimoAgent container build (ccxt, fastapi, uvicorn, ta) |
| `orchestrator/scripts/hermes_primo_bridge.py` | CREATED | Hermes poller: fetch→validate→write signal bus |
| `freqtrade/shared/strategies/MinimalViableStrategy_v1.py` | CREATED | EMA9/21 crossover + Hermes signal gate + ATR stoploss |
| `freqtrade/bots/mvs/config/config.json` | CREATED | MVS bot dry-run config (futures, isolated, Bitget) |
| `freqtrade/bots/mvs/config/pairs.json` | CREATED | BTC/USDT:USDT, ETH/USDT:USDT, SOL/USDT:USDT |
| `docker-compose.pipeline.yml` | CREATED | Compose manifest: primo-agent + freqtrade-mvs |
| `primoagent/primo_api.py` | COPIED | Synced from projects/trading/primo/ for build context |

## 3. Architecture Decision Record

- **ADR-001:** Signal bus uses host bind mount (`shared/signals/`) not named volume — ensures Hermes (in `hermes-agent` container) can write signals that Freqtrade-MVS reads.
- **ADR-002:** Backtest bypasses Hermes signal gate (`runmode != live/dry_run`) — historical backtesting uses EMA crossover alone; live/dry-run requires fresh Hermes-approved signal.
- **ADR-003:** Primo deterministic-only in v1 — no LLM calls in the containerized API (ccxt data fetch + TA indicators + RiskGuard only).
- **ADR-004:** `use_custom_stoploss=False` (set in strategy class) — custom_stoploss method exists but is not invoked by Freqtrade. ATR-based dynamic stop is available when enabled.

## 4. Signal Flow

```
PrimoAgent (container) → GET /signal?pair=BTC/USDT:USDT
    ↓
Hermes Bridge (poll every 60s) → validate() → approve → write JSON
    ↓
shared/signals/latest_signal.json (bind mount)
    ↓
Freqtrade-MVS (populate_entry_trend) → read + freshness check
    → signal OK → EMA crossover → long_entry
    → signal missing/stale/vetoed → no entry
```

## 5. Validation Results

| Check | Result |
|-------|--------|
| `docker compose config` | PASS |
| `docker compose build primo-agent` | PASS |
| `docker compose up -d` | PASS |
| PrimoAgent `/health` | PASS (healthy, 3 pairs monitored) |
| PrimoAgent `/signal?pair=BTC/USDT:USDT` | PASS (returns valid schema) |
| Signal bus write (host) → read (container) | PASS |
| Freqtrade strategy load | PASS |
| Backtest (2024-01-03 → 2026-05-11) | PASS (734 trades, -44.43%) |
| No live trading enabled | CONFIRMED (dry_run=true, keys empty) |

### Backtest Detail (EMA Crossover Only)

| Metric | Value |
|--------|-------|
| Trades | 734 |
| Winrate | 63.5% |
| Total PnL | -44.43% |
| Max Drawdown | 49.06% |
| Profit Factor | ~0.76 (estimated) |

**Interpretation:** Pure EMA9/EMA21 crossover is negative expectancy. LLM signal filter (PrimoAgent LLM layer) is required to filter entries.

## 6. Known Limitations

1. **No LLM integration in container:** PrimoAgent container runs deterministic logic only — LLM calls require Ollama API key + network access to `ollama.com/v1`.
2. **custom_stoploss not invoked:** `use_custom_stoploss=False` means ATR dynamic stoploss is not active.
3. **Single-pair signal only:** GET `/signal` returns one pair at a time. Multi-pair batch available via POST `/signal`.
4. **Hermes bridge not running autonomously:** `hermes_primo_bridge.py` is ready but not deployed as a cron or service.
5. **Backtest negative:** Pure EMA crossover has negative expectancy — LLM filter layer needed for positive edge.

## 7. Rollback Instructions

```bash
# Stop and remove pipeline containers
cd /home/hermes/projects/trading
docker compose -f docker-compose.pipeline.yml down

# Remove images (optional)
docker rmi primo-agent:latest

# Restore original fleet only
cd /home/hermes/projects/trading/freqtrade
docker compose -f docker-compose.fleet.yml up -d
```

## 8. Start Commands

```bash
cd /home/hermes/projects/trading
docker compose -f docker-compose.pipeline.yml build primo-agent
docker compose -f docker-compose.pipeline.yml up -d
docker ps --filter "name=primo-agent" --filter "name=freqtrade-mvs"
```

## 9. Healthcheck Commands

```bash
# PrimoAgent
curl http://localhost:8420/health
curl "http://localhost:8420/signal?pair=BTC/USDT:USDT"

# Freqtrade
curl http://localhost:8087/api/v1/ping
docker exec freqtrade-mvs freqtrade list-strategies

# Signal bus
cat /home/hermes/projects/trading/freqtrade/shared/signals/latest_signal.json
```

## 10. Backtest Command

```bash
docker exec freqtrade-mvs freqtrade backtesting \
  --strategy MinimalViableStrategy_v1 \
  --timerange 20240101-20260511 \
  --config /freqtrade/config/config.json
```

## 11. Walk-Forward Validation Procedure

```bash
# Step 1: Download data (once)
docker exec freqtrade-mvs freqtrade download-data \
  --timerange 20220101-20260511 --timeframes 1h

# Step 2: Backtest in-sample (2022-01 → 2024-06)
docker exec freqtrade-mvs freqtrade backtesting \
  --strategy MinimalViableStrategy_v1 \
  --timerange 20220101-20240630

# Step 3: Backtest out-of-sample (2024-07 → 2026-05)
docker exec freqtrade-mvs freqtrade backtesting \
  --strategy MinimalViableStrategy_v1 \
  --timerange 20240701-20260511

# Step 4: Compare IS vs OOS metrics
# Target: PF > 1.2, Max DD < 15%, ≥70 trades in OOS
```

## 12. Next Steps

1. **Integrate LLM layer:** Wire Ollama Cloud API into PrimoAgent container for LLM-based signal filtering
2. **Deploy Hermes bridge:** Start `hermes_primo_bridge.py` as a service or cron inside hermes-agent
3. **24h dry-run observation:** Run with LLM-filtered signals in dry-run mode
4. **Re-evaluate backtest** with LLM-filtered signals before any live-trading discussion
