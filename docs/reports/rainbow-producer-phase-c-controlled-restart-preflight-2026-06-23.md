# Rainbow Producer Phase C — Controlled Restart Preflight

**Date:** 2026-06-23  
**Issue:** [#325](https://github.com/GoLukeEnviro/trading-hub/issues/325)  
**Status:** 🔒 **BLOCKED** — `RAINBOW_PHASE_C_APPROVAL_TOKEN` absent

---

## Phase A & B Baseline

| Phase | Repo | PR | Merge Commit |
|-------|------|----|-------------|
| A | trading-hub | [#326](https://github.com/GoLukeEnviro/trading-hub/pull/326) | `68bb9e9` |
| B | ai4trade-bot | [#62](https://github.com/GoLukeEnviro/ai4trade-bot/pull/62) | `f6c42c6` |

## Current State (Pre-Restart Snapshot)

| Metric | Value |
|--------|-------|
| Rainbow status | RUNNING (PID 171665, uptime ~2h57m) |
| Readiness | GREEN, exit 0 |
| Health | healthy |
| Signals | 50, age 111.9s |
| Freshness | `true` |
| Active PID path | `/tmp/rainbow-producer.pid` (7 bytes) |
| Active log path | `/tmp/rainbow-producer.log` (45 KB) |
| New PID dir | `/opt/data/rainbow/` does NOT exist |
| SI-v2 cycle | `20260623T061729Z`, GREEN, 4/4 bots, 4 proposals, 0 mutations |
| trading-hub HEAD | `68bb9e9` |
| ai4trade-bot HEAD | `f6c42c6` |

## After Restart — Expected

| Metric | Current Path | Expected Path |
|--------|-------------|---------------|
| PID file | `/tmp/rainbow-producer.pid` | `/opt/data/rainbow/rainbow-producer.pid` |
| Log file | `/tmp/rainbow-producer.log` | `/opt/data/rainbow/rainbow-producer.log` |
| Factory logging | NOT initialized in create_app() | **INITIALIZED** via `setup_logging()` |

## Restart Command

```bash
export RAINBOW_PHASE_C_APPROVAL_TOKEN="APPROVE_RAINBOW_PHASE_C_RESTART"

cd /home/hermes/projects/trading
bash orchestrator/scripts/rainbow_producer_manager.sh restart
```

## Post-Restart Validation Plan

| Gate | Check | Expected |
|------|-------|----------|
| Process | Manager status | RUNNING |
| Port | `ss -tlnp \| grep :8000` | Listening |
| Readiness | Readiness checker | GREEN, exit 0 |
| Health | `GET /health` | HTTP 200 |
| Signals | `GET /signals/latest` | 50 signals |
| Freshness | Age check | < 900s |
| New PID | `/opt/data/rainbow/rainbow-producer.pid` | Exists |
| New log | `/opt/data/rainbow/rainbow-producer.log` | Exists, growing |
| Factory logging | Log content | Contains collector/engine output |
| SI-v2 cycle | Active cycle runner | 4/4 bots, Rainbow fresh, 0 mutations |

## Approval Gate

**BLOCKED** until:
```bash
export RAINBOW_PHASE_C_APPROVAL_TOKEN="APPROVE_RAINBOW_PHASE_C_RESTART"
```

Without token: **no restart, no process mutation.**

## Non-Goals

- No auto-restart
- No cron/systemd/s6 enablement
- No Docker/Compose
- No Freqtrade restart
- No SI-v2 scoring change
- No strategy/config change
- No `dry_run=false`
- No live trading
