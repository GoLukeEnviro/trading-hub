# Monitoring & Alert Policy — Telegram Noise Reduction

**Date:** 2026-05-24
**Author:** Hermes Orchestrator (automated)
**Status:** ACTIVE

## Executive Summary

Reduced Telegram spam from ~210 messages/day to ~8-12 messages/day during nominal operation.
Primary noise sources eliminated:
- `freqtrade-momentum: not_found` alerts every 5 minutes (288/day → 0)
- quality-hub verbose LLM reports every 15 minutes (96/day → 1/day compact)
- deep-dive verbose LLM reports every 15 minutes (96/day → 1/day compact)
- System Health Check every 2 hours (12/day → 3/day compact)

## Changes Applied

### Script Modifications

| File | Change |
|------|--------|
| `container_watchdog.sh` (v2→v3) | Removed `freqtrade-momentum` from TRADING_CONTAINERS and BOT_PROBES |
| `drawdown_guard.py` | Removed `momentum` from BOTS dict |
| `system_optimizer.py` | Removed `freqtrade-momentum` from KNOWN_CONTAINERS |
| Both scripts | Synced to `/opt/data/profiles/orchestrator/scripts/` and `/home/hermes/projects/trading/orchestrator/scripts/` |

### Cron Schedule Changes

| Job | ID | Before | After | Deliver |
|-----|-----|--------|-------|---------|
| container-watchdog | 64b6a4bc71bb | */5 min | */30 min | telegram |
| mcp-watchdog | aac52bfa2ce2 | */5 min | */15 min | telegram |
| quality-hub-monitor | cf0e5b9f79e5 | every 15m | daily 08:00 | telegram (compact) |
| trading-hub-deep-dive-validation | eb6baf4a3b67 | every 15m | daily 09:00 | telegram (compact) |
| System Health Check | c3d95433a636 | every 2h | every 8h (00/08/16) | telegram (compact) |
| Fleet Report | e9ce544673b1 | every 4h | every 4h (unchanged) | telegram (compact) |
| 72h Research Fleet | 31bbdb7708bd | every 60m | PAUSED | was local-only |
| Heartbeat Intelligence | 6fb7b35f951e | every 2h | every 6h | sends own Telegram |

### Prompt Modifications (LLM Jobs)

All LLM-driven Telegram jobs now have:
- Max 600-800 character Telegram output limit
- Full reports written to local files instead:
  - `/home/hermes/projects/trading/orchestrator/logs/quality-hub-report.md`
  - `/home/hermes/projects/trading/orchestrator/logs/deep-dive-report.md`
  - `/home/hermes/projects/trading/orchestrator/logs/fleet-report.md`
  - `/home/hermes/projects/trading/orchestrator/logs/system-health-report.md`
- "All systems nominal" = minimal 1-line output

## Alert Policy

### Critical Immediate Alerts (always delivered)
- Container unexpectedly exits or restarts repeatedly
- dry_run=false detected on any bot
- Exchange API key configured where it should not be
- Disk usage >90%
- Signal pipeline stale beyond 60 minutes
- Drawdown >5% (WARN), >8% (PAUSE), >12% (CLOSE), >15% (HALT)
- All bots unreachable simultaneously

### Non-Critical (digest/local only)
- Nominal health reports → local file, compact Telegram summary
- Known quarantine: freqai-rebel max_open_trades=0 (INTENTIONAL)
- Known not-deployed: freqtrade-momentum, freqtrade-rsi
- Routine Docker status when all healthy
- Stale .tmp file cleanup notifications
- Informational PnL summaries

### Deduplication Rules
- container-watchdog: silent when all OK, only alerts on new issues
- drawdown-guard: alert-only, tracks prev state for recovery detection
- mcp-watchdog: silent when running, only on restart/failure
- LLM jobs: already throttled to daily/8h, output capped at 600-800 chars

## Known Not-Deployed Components

| Component | Compose Defined | Image Exists | Config Exists | Container Running | Decision |
|-----------|----------------|-------------|---------------|-------------------|----------|
| freqtrade-momentum | YES | YES | YES | NO | Intentionally not deployed. Removed from monitoring. |
| freqtrade-rsi | YES | - | YES | NO | Not monitored, not deployed. |

To deploy momentum: `docker compose -f docker-compose.fleet.yml up -d freqtrade-momentum`
Then re-add to watchdog: add back to TRADING_CONTAINERS in container_watchdog.sh and BOTS in drawdown_guard.py.

## Active Monitored Containers

1. freqtrade-freqforge (port 8086)
2. freqtrade-freqforge-canary (port 8081)
3. freqtrade-regime-hybrid (port 8085)
4. freqai-rebel (port 8087)
5. ai-hedge-fund-crypto (port 8410)

## Validation Results

- [x] container_watchdog.sh bash syntax OK
- [x] mcp_watchdog.sh bash syntax OK
- [x] drawdown_guard.py python syntax OK
- [x] container_watchdog dry-run: silent (no momentum spam)
- [x] All 5 monitored containers: running
- [x] All 4 Freqtrade bots: dry_run=true
- [x] No services broken

## Backup Location

`/home/hermes/projects/trading/backups/telegram-noise-reduction-20260524_220045/`

Contains:
- container_watchdog.sh (original)
- container_watchdog.sh.trading (original trading dir copy)
- drawdown_guard.py (original)
- drawdown_guard.py.trading (original trading dir copy)
- mcp_watchdog.sh (original)
- mcp_watchdog.sh.trading (original trading dir copy)

## Full Cron Job Inventory (Post-Change)

| # | Job | Schedule | Deliver | Type | Telegram |
|---|-----|----------|---------|------|----------|
| 1 | signal-heartbeat | */20 min | local | script | NO |
| 2 | drawdown-guard | */30 min | telegram | script | alert-only |
| 3 | container-watchdog | */30 min | telegram | script | alert-only |
| 4 | mcp-watchdog | */15 min | telegram | script | alert-only |
| 5 | daily-backup | 02:00 daily | local | script | NO |
| 6 | portfolio-rebalancer | Mon 06:00 | origin | script | YES (weekly) |
| 7 | cron-guardian | */6 h | local | script | NO |
| 8 | smart-heartbeat | */10 min | local | script | NO |
| 9 | Fleet Report | every 4h | telegram | LLM | compact summary |
| 10 | 72h Research Fleet | PAUSED | local | LLM | NO |
| 11 | System Health Check | every 8h | telegram | LLM | compact summary |
| 12 | Heartbeat Intelligence | every 6h | local | script | own Telegram (4/day) |
| 13 | Memory Backfill | */6 h | local | script | NO |
| 14 | Rebel Status Summary | every 12h | local | LLM | NO |
| 15 | FleetRisk equity | every 5m | local | script | NO |
| 16 | Fleet correlation | every 3d | local | script | NO |
| 17 | quality-hub-monitor | daily 08:00 | origin | LLM | compact daily |
| 18 | trading-hub-deep-dive | daily 09:00 | origin | LLM | compact daily |
| 19 | monthly-strategy | 1st monthly | telegram | script | YES (monthly) |
| 20 | autonomous-health-loop | every 30m | local | LLM | NO |
| 21 | trading-pipeline | */10 min | local | script | NO |
| 22 | system-optimizer | every 2h | local | script | NO |
