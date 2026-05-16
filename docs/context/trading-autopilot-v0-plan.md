# Trading Autopilot v0 — Architecture Plan

## Status: ACTIVE (safe monitor mode only)

## Overview

The Trading Autopilot is a read-only monitoring layer that observes the fleet, validates signals, writes reports, and generates approval queues. It **never** autonomously changes runtime state.

## Modes

| Mode | Schedule | Purpose |
|------|----------|---------|
| `monitor` | Every 30m | Fleet snapshot, signal check, report + decision queue |
| `daily-report` | Daily 07:30 UTC | Extended summary with trend observations |
| `approval-preview` | On demand | Show pending approval items with approve commands |

## Architecture

```
Data Sources (read-only)
├── Docker container status (docker ps -a)
├── ai-hedge signal file (hermes_signal.json inside container)
├── Heartbeat log (ai-hedge container)
├── Freqtrade bot APIs (internal JWT auth)
│
Processing (no writes to runtime)
├── Signal freshness validation
├── Container health classification (GREEN/YELLOW/ORANGE/RED)
├── Momentum halt check
├── Rebel observation tracking
│
Outputs (write-only, non-runtime)
├── docs/state/autopilot/latest.md
├── docs/state/autopilot/daily_YYYYMMDD.md
├── orchestrator/state/decision_queue.json
```

## Safety Boundaries

### Autonomous (safe, no approval needed)
- Read container status
- Read signal files
- Validate signal freshness
- Query bot APIs (read-only)
- Write reports and decision queues
- Classify fleet health
- Append shadow logs

### Requires Approval
- Restart containers
- Change bot configs
- Change strategy logic
- Change FreqAI parameters
- Wire Signal Bridge
- Delete containers/volumes
- Enable live trading (NEVER without separate explicit approval)

## Color Classification

| Color | Signal Meaning | Container Meaning |
|-------|---------------|-------------------|
| GREEN | Fresh, valid signal | Running, dry_run=true |
| YELLOW | Signal aging (>60min) | Minor concern |
| ORANGE | Signal stale (>120min) | Concern |
| RED | No signal | Container down or dry_run=false |

## Files

| File | Purpose |
|------|---------|
| `orchestrator/trading_autopilot.py` | Main entrypoint |
| `docs/state/autopilot/latest.md` | Latest monitor report |
| `orchestrator/state/decision_queue.json` | Pending approval items |

## Reuse

The autopilot reuses existing orchestrator scripts where beneficial:
- `fleet_healthcheck.py` — comprehensive fleet health with GREEN/YELLOW/ORANGE/RED
- `freqtrade_monitor.py` — bot status via SQLite + API
- `master_trading_audit.py` — signal + fleet audit
- `ai_hedge_signal_heartbeat.sh` — signal heartbeat

## Cron Plan (not yet installed)

| Job | Schedule | Command |
|-----|----------|---------|
| trading-autopilot-monitor | Every 30m | `cd /home/hermes/projects/trading && python3 orchestrator/trading_autopilot.py --mode monitor` |
| trading-autopilot-daily | Daily 07:30 | `cd /home/hermes/projects/trading && python3 orchestrator/trading_autopilot.py --mode daily-report` |

## Rollback

Delete the two cron jobs. Remove `orchestrator/trading_autopilot.py`. All other fleet state is untouched.

## Future Phases

- **v0.1**: Monitor + report + decision queue (current)
- **v0.2**: Auto-execute safe actions (reports, shadow logs, stale classification)
- **v1.0**: Approval-loop integration (approve/reject commands via chat)
- **v2.0**: Signal Bridge consumer with RiskGuard gate