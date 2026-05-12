# Phase 12.7 — 12-Hour Observation Schedule

- Observation start UTC: 2026-05-07T21:19:44.286292Z
- Observation end UTC: 2026-05-08T09:19:44.286292Z

## Fixed Runs
- Run 1: 2026-05-07T21:19:44.286292Z UTC (T+0h)
- Run 2: 2026-05-08T00:19:44.286292Z UTC (T+3h)
- Run 3: 2026-05-08T03:19:44.286292Z UTC (T+6h)
- Run 4: 2026-05-08T06:19:44.286292Z UTC (T+9h)
- Run 5: 2026-05-08T09:19:44.286292Z UTC (T+12h)

## Per-Run Commands
- fleet_healthcheck.py before wrapper
- count ShadowLogger lines before wrapper
- timeout 900 run_trading_cycle.sh
- validate raw PrimoAgent JSON
- validate RiskGuard JSON
- validate all three state files
- count ShadowLogger lines after wrapper
- multicycle_validator.py
- fleet_healthcheck.py after wrapper
- append ledger row

## Phase 13 Gate Criteria
- GO only if at least 4 successful scheduled runs are completed across the 12-hour window
- WAIT if observation completes with fewer than 4 successful scheduled runs
- BLOCKED if dry_run=false, credentials, invalid state JSON, invalid RiskGuard output, ShadowLogger failure, RED fleet health, unexpected cron changes, or container restarts appear

## Safety Rules
- No live trading
- No Freqtrade config or strategy changes
- No container restarts
- No cron migration or cron edits
- No secrets in output
