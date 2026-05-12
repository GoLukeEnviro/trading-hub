# FOMO Phase 3 — Foundation Context Document

**Created:** 2026-05-12 18:35 UTC
**Author:** Hermes Orchestrator
**Status:** Foundation complete. Strategy code NOT yet implemented.

## Purpose

This document records the creation of a clean, isolated technical deployment
foundation for a future FOMO (Fear Of Missing Out) / Open Interest / Funding Rate
trading strategy system on the VPS Freqtrade fleet.

The foundation was created in accordance with the strict constraints:
- No live trading activation
- No disruption to existing dry-run bots
- No implementation of actual strategy logic
- All changes are reversible and documented

## What Was Created

### Directory Structure

```
/home/hermes/projects/trading/freqtrade/bots/fomo-phase3/
├── config/
│   └── config_fomo_phase3_dryrun.json   → Dry-run Freqtrade config
├── user_data/
│   ├── strategies/
│   │   └── FOMO_Phase3_v0.py            → Placeholder strategy (skeleton)
│   ├── data/                             → For OHLCV data (empty)
│   ├── logs/                             → For container logs (empty)
│   ├── backtest_results/                 → For backtest output (empty)
│   └── hyperopt_results/                 → For hyperopt output (empty)
├── research/                             → For analysis notebooks (empty)
├── reports/                              → For generated reports (empty)
├── artifacts/                            → For model artifacts (empty)
├── scripts/
│   ├── validate_foundation.sh            → Structural validation (24 checks)
│   └── healthcheck_foundation.sh         → Runtime health check (8 checks)
├── docs/context/
│   └── fomo-phase3-foundation.md         → THIS FILE
├── docker-compose.fomo.yml               → Compose fragment for deployment
├── .env.example                           → Environment variable template
└── README.md                              → Quick-start guide
```

### Config Highlights

| Setting | Value | Reason |
|---------|-------|--------|
| `dry_run` | `true` | Mandatory — no live trading |
| `initial_state` | `stopped` | Bot won't auto-start on container launch |
| `strategy` | `FOMO_Phase3_v0` | Matches placeholder class name |
| `trading_mode` | `futures` | Isolated margin, consistent with regime-hybrid |
| `stoploss` | `-0.15` | Conservative (tighter than FreqForge's -0.09) |
| `max_open_trades` | `5` | Matches fleet standard |
| `stake_amount` | `50` | Half of FreqForge (100) — conservative start |
| `dry_run_wallet` | `1000` | Same as FreqForge baseline |
| API binding | `127.0.0.1:8087` | Local-only, verified free |
| `jwt_secret_key` | `CHANGE_ME_TO_A_RANDOM_SECRET_BEFORE_LIVE` | Placeholder |
| API password | `CHANGE_ME_BEFORE_LIVE` | Placeholder |
| Exchange credentials | **NONE** | No API keys anywhere |

## What Was Intentionally Left Untouched

| Component | Reason |
|-----------|--------|
| **freqtrade-freqforge** | Gold standard — 100% WR, 12 trades, +$10.84 |
| **freqtrade-regime-hybrid** | Active futures bot — 36 trades, recently fixed trailing stop bug |
| **freqtrade-momentum** | Inactive — 0 trades in 26h, replaced by new system later |
| **freqtrade-rsi** | Isolated on legacy network/mounts — separate migration task |
| **freqtrade-webserver** | Legacy config, no active role |
| **ai-hedge-fund-crypto** | Signal layer — feeding fleet with low-confidence signals |
| **freqforge user_data/** | Backtest results, OHLCV data — preserved intact |
| **All Docker volumes & networks** | No prune, no cleanup |
| **MVS orphan directory** | Not removed — separate decision |

## Assumptions Made

1. **FreqForge_Override as gold standard** — Its 100% WR (9 closed, 3 open) is the
   reference. The new strategy must eventually match or exceed this.
2. **ki-fabrik network** — The new bot will join this network. Verified working.
3. **Port 8087** — Verified free at creation time. Re-verify before deployment.
4. **$1,000 dry-run wallet** — Consistent with existing FreqForge baseline.
5. **Futures trading mode** — presumed for OI/Funding strategy. Changeable to spot.
6. **Bitget exchange** — Consistent with fleet. Changeable in config.
7. **No git repo** — The trading root is not under version control.
   Consider initializing git before making irreversible changes.

## Validation Results

**24/24 checks passed** at 2026-05-12 18:35 UTC:
- ✅ 12 directory paths
- ✅ 4 key files exist
- ✅ Config is valid JSON, dry_run=True, no exchange credentials,
     initial_state=stopped, API bound to localhost
- ✅ ki-fabrik network exists
- ✅ Port 8087 is free

## Next Steps (for Strategy Developer)

1. **Replace** `user_data/strategies/FOMO_Phase3_v0.py` with real strategy code
2. **Tune** config parameters in `config_fomo_phase3_dryrun.json`
3. **Download data**: `docker run --rm -v ... freqtradeorg/freqtrade:stable download-data ...`
4. **Backtest**: `docker run --rm -v ... freqtradeorg/freqtrade:stable backtesting ...`
5. **Start the container** (dry-run only):
   ```bash
   cd /home/hermes/projects/trading/freqtrade/bots/fomo-phase3
   docker compose -f docker-compose.fomo.yml up -d
   ```
6. **Run health check**:
   ```bash
   bash scripts/healthcheck_foundation.sh
   ```

## Rollback Instructions

To completely remove the FOMO Phase 3 foundation:

```bash
# If container is running
docker stop freqtrade-fomo-phase3 && docker rm freqtrade-fomo-phase3

# Delete all scaffold files
rm -rf /home/hermes/projects/trading/freqtrade/bots/fomo-phase3
```

This affects NO other container, volume, or configuration.
