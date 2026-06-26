# Hermes Stale Log Map

**Date:** 2026-06-26
**Author:** Hermes Orchestrator
**Operation Level:** L0/L1

## Methodology

For each log file in `/opt/data/profiles/orchestrator/logs/` older than 7 days,
we identify the owning script/job and classify the root cause.

## Stale Log Classification

| # | Log File | Age | Size | Class | Likely Cause |
|---|----------|----:|-----:|-------|-------------|
| 1 | `autonomous_controller.log` | 29d | 6 KB | JOB_DISABLED | Controller was disabled/stopped |
| 2 | `autonomous_controller_report_*.md` (5 files) | 29d | 440-454 B | OBSOLETE | Old report artifacts from disabled controller |
| 3 | `drawdown_guard.log` | 25d | 92 KB | ACTIVE_BUT_WRONG_PATH | Drawdown guard writes to ro-mount project path; this is stale backup path |
| 4 | `signal_bridge.log` | 25d | 354 KB | ACTIVE_BUT_WRONG_PATH | Signal bridge writes to ro-mount path; log stopped when ro-mount was activated |
| 5 | `signal_heartbeat.log` | 25d | 22 KB | ACTIVE_BUT_WRONG_PATH | Signal heartbeat same issue |
| 6 | `shadow_decisions.jsonl` | 25d | 1.2 MB | ACTIVE_BUT_WRONG_PATH | Shadow decisions accumulating in log dir (belongs in state/ likely) |
| 7 | `ghostbuster.log` | 24d | 99 KB | ACTIVE_BUT_WRONG_PATH | Ghostbuster writes to ro-mount or script disabled |
| 8 | `smart_heartbeat.log` | 24d | 57 KB | ACTIVE_BUT_WRONG_PATH | Smart heartbeat stopped writing (possibly ro-mount) |
| 9 | `cron_restore.log` | 24d | 1 KB | OBSOLETE | One-time restore operation log |
| 10 | `rebalancer.log` | 24d | 10 KB | JOB_DISABLED | Rebalancer job not running |
| 11 | `hermes-update.log` | 18d | 1 KB | OBSOLETE | One-time update log |
| 12 | `gateway-restart.log` | 15d | 636 B | OBSOLETE | One-time restart log |
| 13 | `watchdog.log` | 15d | 12 KB | ACTIVE_BUT_WRONG_PATH | Container watchdog writes to ro-mount path |
| 14 | `tui_gateway_crash.log` | 12d | 3 KB | OBSOLETE | Old crash diagnostic |

## Fresh Logs (healthy, <1 day)

| Log | Age | Status |
|-----|----:|:------:|
| `agent.log` | minutes | ✅ Rotating |
| `errors.log` | minutes | ✅ Rotating |
| `mcp-stderr.log` | minutes | ✅ Fresh |
| `memory-backfill.log` | minutes | ✅ Fresh |
| `observation.log` | minutes | ✅ Fresh |
| `observation_watchdog.log` | minutes | ✅ Fresh |
| `fleet_risk_update.log` | minutes | ✅ Fresh |
| `ledger_integrity_watchdog.log` | minutes | ✅ Fresh |
| `gui.log` | minutes | ✅ Fresh |

## Recommendations

### ACTIVE_BUT_WRONG_PATH (narrow fix required)

These scripts write to paths that are read-only in the cron container.
The fix is the same pattern as `heartbeat_writer.py` (Phase 3): change paths
to `/opt/data/profiles/orchestrator/logs/` or `state/`.

| Script | Current Path | Target Path |
|--------|-------------|-------------|
| `drawdown_guard.py` | project tree path | `/opt/data/profiles/orchestrator/logs/drawdown_guard.log` |
| `signal_bridge` scripts | project tree path | `/opt/data/profiles/orchestrator/logs/signal_bridge.log` |
| `ghostbuster.py` | project tree path | `/opt/data/profiles/orchestrator/logs/ghostbuster.log` |
| `smart_heartbeat.py` | project tree path | `/opt/data/profiles/orchestrator/logs/smart_heartbeat.log` |
| `watchdog.sh` | project tree path | `/opt/data/profiles/orchestrator/logs/watchdog.log` |

**Scope:** These fixes are outside the current campaign scope (cron history).
They should be addressed in a follow-up L2 campaign.

### JOB_DISABLED

| Script | Status | Action |
|--------|--------|--------|
| `autonomous_controller.py` | Disabled | Leave as-is, no action |
| `rebalancer.py` | Disabled | Leave as-is, no action |

### OBSOLETE

One-time or old artifact logs. No action needed; they will be rotated out
naturally or can be archived in L3 if desired.

## Root Cause Pattern

The dominant pattern is **ACTIVE_BUT_WRONG_PATH**: scripts writing to the
read-only Git mount (`/home/hermes/projects/trading/...`). This matches the
root cause from `heartbeat_writer.py` (F2). The fix is the same for all:
redirect to `/opt/data/profiles/orchestrator/{logs,state}/`.

## Out of Scope for Current Campaign

This log mapping is diagnostic only. Fixing the ACTIVE_BUT_WRONG_PATH scripts
(excluding `heartbeat_writer.py`, already fixed in Phase 3) is deferred to a
future campaign.
