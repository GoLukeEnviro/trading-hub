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
| Exchange | **bitget** (futures, swap) |
| Trading mode | **futures** (isolated margin) |
| Host API port | `8087` |
| Container API port | `8080` |
| Strategy | `RebelLiquidation.py` |
| FreqAI model | XGBoostClassifier |
| Dry-run | **enabled** |
| Pairs | BTC/USDT:USDT, ETH/USDT:USDT |
| Timeframe | 5m (with 15m, 1h features) |
| DI_threshold | 0.9 |
| ccxt defaultType | swap |

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

1. **STOPPED after startup**: Current runtime remains in `STOPPED` heartbeats after the futures data download phase.
2. **Host API unreachable from Hermes**: Hermes runs in its own container, `127.0.0.1:8087` doesn't route. Use `docker exec freqai-rebel curl ...` instead.
3. **No live trading**: dry_run=true enforced. No exchange credentials configured.
4. **Spot->Futures migration (2026-05-14)**: Originally deployed as spot. Patched to futures (isolated margin, swap, `:USDT` pair format) to match the rest of the fleet. Old spot data purged and re-downloaded as futures data.
5. **Training not yet proven (verified 2026-05-14)**: No fatal traceback in recent logs, API ping returns `pong`, futures data files exist, but no fit/prediction logs were observed. Current model artifacts under `/freqtrade/user_data/models/rebel-liquidation-v1/` contain only `run_params.json`. Active volume config has `initial_state = None`.

## Next Steps

1. Determine whether `initial_state` should be explicitly set to `running` for this bot before expecting live FreqAI training
2. Re-verify logs after the next controlled restart or config change
3. Verify model artifacts in `/freqtrade/user_data/models/rebel-liquidation-v1/`
4. Monitor first predictions and compare signal quality
5. Run controlled backtests before any live trading changes
6. Rotate dev API credentials before exposure beyond localhost/Tailscale
