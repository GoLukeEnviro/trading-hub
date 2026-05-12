# FOMO Phase 3 — Strategy System Foundation

## What This Is

A clean, isolated deployment scaffold for a future FOMO / Open Interest / Funding Rate
trading strategy on the VPS Freqtrade fleet.

**This is NOT a trading strategy.** It is the infrastructure shell — directories,
config template, compose fragment, and placeholder code — so that strategy development
can focus purely on logic, not on DevOps.

## Directory Structure

```
freqtrade/bots/fomo-phase3/
├── config/
│   └── config_fomo_phase3_dryrun.json    # Dry-run Freqtrade config (DO NOT add real keys)
├── user_data/
│   ├── strategies/
│   │   └── FOMO_Phase3_v0.py             # ← PLACE YOUR STRATEGY CODE HERE
│   ├── data/                              # Downloaded OHLCV data (future)
│   ├── logs/                              # Container logs (bind-mounted)
│   ├── backtest_results/                  # Backtest output (future)
│   └── hyperopt_results/                  # Hyperopt output (future)
├── research/                              # Research notebooks, spreadsheets, analysis
├── reports/                               # Generated reports, metrics
├── artifacts/                             # Model artifacts, cached computations
├── scripts/
│   ├── validate_foundation.sh             # Read-only structural validation
│   └── healthcheck_foundation.sh          # Runtime health check (after container start)
├── docs/context/
│   └── fomo-phase3-foundation.md          # This document
├── docker-compose.fomo.yml               # Docker Compose fragment
├── .env.example                           # Environment variable template
└── README.md                              # This file
```

## How to Add Strategy Code

1. **Replace** `user_data/strategies/FOMO_Phase3_v0.py` with your actual strategy class.
   The class name **must** be `FOMO_Phase3_v0` (or update the config).

2. **Available shared infrastructure** (located in `/freqtrade/shared/` inside the container):
   - `fleetguard_v1.py` — Fleet-level entry safety layer
   - `exit_agent_v9.py` — Sentient exit agent
   - `primo_gate.py` — Legacy gate (optional)
   - `signals/latest_signal.json` — ai-hedge-fund-crypto signal relay

3. **Adjust config parameters** in `config/config_fomo_phase3_dryrun.json`:
   - `stoploss`, `minimal_roi`, `max_open_trades`, `stake_amount`
   - `pair_whitelist` (currently BTC, ETH, SOL)

## How to Deploy

### Prerequisites
- Freqtrade Docker image pulled: `docker pull freqtradeorg/freqtrade:stable`
- Docker network `ki-fabrik` exists
- Config validates with `scripts/validate_foundation.sh`
- Port 8087 is free (checked in validation)

### Start (dry-run only)
```bash
# Option A: Using compose fragment
cd /home/hermes/projects/trading/freqtrade/bots/fomo-phase3
docker compose -f docker-compose.fomo.yml up -d

# Option B: Using docker run
docker run -d --restart unless-stopped \
  --name freqtrade-fomo-phase3 \
  --network ki-fabrik \
  -p 127.0.0.1:8087:8087 \
  -v /home/hermes/projects/trading/freqtrade/bots/fomo-phase3/config:/freqtrade/config:ro \
  -v /home/hermes/projects/trading/freqtrade/bots/fomo-phase3/user_data:/freqtrade/user_data:rw \
  -v /home/hermes/projects/trading/freqtrade/logs:/freqtrade/logs:rw \
  -v /home/hermes/projects/trading/freqtrade/shared:/freqtrade/shared:ro \
  freqtradeorg/freqtrade:stable \
  trade --dry-run -v \
  --strategy FOMO_Phase3_v0 \
  --config /freqtrade/config/config_fomo_phase3_dryrun.json
```

### Health Check
```bash
bash /home/hermes/projects/trading/freqtrade/bots/fomo-phase3/scripts/healthcheck_foundation.sh
```

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| `initial_state: stopped` | Bot won't start trading until explicitly started (or config changed to "running") |
| API bound to `127.0.0.1` | No external network access to the API |
| `dry_run_wallet: 1000` | Consistent with FreqForge baseline |
| Separate directory per bot | Consistent with existing bots (regime-hybrid, momentum, rsi) |
| `/freqtrade/shared` volume | Access to FleetGuard, ExitAgent, signals without importing strategy code |
| Port 8087 | Verified free, sequential with existing bot ports |

## What Was Intentionally Left Untouched

- **freqtrade-freqforge** — Gold standard, 100% WR, 12 trades, untouched
- **freqtrade-regime-hybrid** — Active futures bot, untouched
- **freqtrade-momentum** — Inactive, not modified
- **freqtrade-rsi** — Legacy network/mounts, not migrated (separate task)
- **freqtrade-webserver** — Legacy config, not modified
- **ai-hedge-fund-crypto** — Signal layer, untouched
- **All existing configs, strategies, databases** — Preserved intact
- **Docker volumes, networks, images** — No prune or cleanup

## Rollback

To remove only this scaffold:
```bash
# Stop and remove container (if running)
docker stop freqtrade-fomo-phase3 && docker rm freqtrade-fomo-phase3

# Delete all scaffold files
rm -rf /home/hermes/projects/trading/freqtrade/bots/fomo-phase3
```

**This will NOT affect any other bot or container.**
