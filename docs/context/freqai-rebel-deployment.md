# FreqAI RebelLiquidation Deployment

## Canonical Source Path

`/home/hermes/projects/trading/freqtrade/bots/freqai-rebel/`

This is the versioned source location. Runtime data lives in Docker named volume.

## Runtime Model

- Docker named volume: `freqai-rebel-data`
- Deploy script: `scripts/sync-to-volume.sh` (copies repo source into volume)
- Repository stores only source/config/deploy files, no runtime data

## Container

| Property | Value |
|----------|-------|
| Container name | `freqai-rebel` |
| Image | `freqtradeorg/freqtrade:2026.3_freqai` |
| Exchange | **bitget** (spot) |
| Host API port | `8087` |
| Container API port | `8080` |
| Strategy | `RebelLiquidation.py` |
| FreqAI model | XGBoostClassifier |
| Dry-run | **enabled** |
| Pairs | BTC/USDT, ETH/USDT |
| Timeframe | 5m (with 15m, 1h features) |
| DI_threshold | 0.9 |

## Deploy / Sync

```bash
/home/hermes/projects/trading/freqtrade/bots/freqai-rebel/scripts/sync-to-volume.sh
cd /home/hermes/projects/trading/freqtrade/bots/freqai-rebel
docker compose up -d
```

## Important Notes

- Hermes runs inside Docker, so host bind mounts are invisible to sibling containers. Named volume + sync script is the workaround.
- FreqAI bot starts in STOPPED state on first launch. It transitions to RUNNING on the next 5m candle cycle when training kicks in. This is normal FreqAI behavior.
- API is reachable internally via `docker exec freqai-rebel curl -s http://localhost:8080/api/v1/ping`.
- API credentials are dev-only (`rebel`/`rebel-dev-only`). Must be rotated before any public exposure.
- Old location `/home/hermes/freqai-rebel/` is preserved as backup but is no longer the source of truth.

## Git Exclusions

Runtime data excluded via `.gitignore`:
- FreqAI models, market data (.feather/.parquet)
- logs, backtest results, hyperopt results
- SQLite DBs, pickle/joblib/zip files
- .env, *.log

## Known Issues

1. **STOPPED after startup**: Normal for FreqAI on first cycle. Waits for next 5m candle.
2. **Host API unreachable from Hermes**: Hermes runs in its own container, `127.0.0.1:8087` doesn't route. Use `docker exec freqai-rebel curl ...` instead.
3. **No live trading**: dry_run=true enforced. No exchange credentials configured.

## Next Steps

1. Wait for first FreqAI training cycle to complete (~5-10 min after next candle)
2. Verify model artifacts in `/freqtrade/user_data/models/rebel-liquidation-v1/`
3. Run controlled backtests before any live trading changes
4. Rotate dev API credentials before exposure beyond localhost/Tailscale
