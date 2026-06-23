# Rainbow Producer Phase C — Controlled Restart Runbook

**Issue:** [#325](https://github.com/GoLukeEnviro/trading-hub/issues/325)  
**Date:** 2026-06-23  
**Status:** **BLOCKED** — requires explicit approval token

---

## Approval Gate

Phase C is **blocked** until explicit approval. To execute:

```bash
export RAINBOW_PHASE_C_APPROVAL_TOKEN="APPROVE_RAINBOW_PHASE_C_RESTART"
```

Without this token: **abort, no restart, no process mutation.**

---

## What Phase C Does

A **controlled restart** of the Rainbow Producer via the canonical manager. After restart:

1. **Phase A hardening activates**: new persistent PID/log paths (`/opt/data/rainbow/`) become active
2. **Phase B hardening activates**: `setup_logging()` runs in `create_app()` factory path, collector logs are captured

**Not done**: no auto-restart, no cron/systemd/s6, no boot persistence.

---

## Pre-Restart Snapshot (2026-06-23 ~08:42 UTC)

| Metric | Value |
|--------|-------|
| Rainbow status | RUNNING (PID 171665, uptime 2h51m) |
| Health | healthy |
| Signals | 50, freshest 33.5s age |
| Readiness verdict | GREEN |
| Old PID file | `/tmp/rainbow-producer.pid` → 171665 |
| Old log file | `/tmp/rainbow-producer.log` → 45 KB |
| New PID dir | `/opt/data/rainbow/` does NOT exist |
| SI-v2 cycle | 20260623T061729Z, GREEN |

### Merges completed

| Phase | Repo | PR | Merge Commit |
|-------|------|----|-------------|
| A | trading-hub | [#326](https://github.com/GoLukeEnviro/trading-hub/pull/326) | `68bb9e9` |
| B | ai4trade-bot | [#62](https://github.com/GoLukeEnviro/ai4trade-bot/pull/62) | `f6c42c6` |

---

## Restart Command

```bash
cd /home/hermes/projects/trading

# Approval gate check
test "${RAINBOW_PHASE_C_APPROVAL_TOKEN:-}" = "APPROVE_RAINBOW_PHASE_C_RESTART" || {
  echo "ABORT: missing Phase C approval token" >&2
  exit 1
}

# Execute restart
bash orchestrator/scripts/rainbow_producer_manager.sh restart
```

---

## Post-Restart Validation Checklist

| Check | Command | Expected |
|-------|---------|----------|
| Manager status | `bash orchestrator/scripts/rainbow_producer_manager.sh status` | RUNNING |
| Readiness | `python3 orchestrator/scripts/rainbow_producer_readiness_check.py` | GREEN, exit 0 |
| Health endpoint | `curl -sf http://127.0.0.1:8000/health` | `{"status":"healthy"}` |
| Signals present | `curl -sf http://127.0.0.1:8000/signals/latest` | 50 signals |
| Freshness | Readiness checker | age < 900s |
| New PID file | `cat /opt/data/rainbow/rainbow-producer.pid` | PID exists, process alive |
| New log file | `ls -la /opt/data/rainbow/rainbow-producer.log` | File exists, growing |
| Old PID gone | `cat /tmp/rainbow-producer.pid` | No longer active default |
| Factory logging | `grep "RainbowEngine" /opt/data/rainbow/rainbow-producer.log` | Log output present |
| SI-v2 cycle | Active cycle runner | 4/4 bots, rainbow fresh=True, mutations 0 |

---

## Rollback

If the restart fails:

```bash
# Old manager would still reference /tmp paths.
# The manager script on 68bb9e9 uses /opt/data/rainbow/ paths.
# To rollback: git checkout the previous commit (a066815) for the manager,
# then restart.
cd /home/hermes/projects/trading
git show a066815:orchestrator/scripts/rainbow_producer_manager.sh > /tmp/rollback_manager.sh
bash /tmp/rollback_manager.sh restart
```

---

## Non-Goals (this phase does NOT)

- Enable auto-restart
- Enable cron/systemd/s6
- Touch Docker/Compose
- Restart Freqtrade
- Change SI-v2 scoring
- Change strategies/configs
- Enable boot persistence
- Set `dry_run=false`
- Enable live trading
