# Issue #463 Disabled Cron Job Cleanup — 2026-07-03

## Scope

Remove 12 disabled, obsolete Hermes Cron jobs: 11 SI-v1 bot jobs (decommissioned)
and 1 duplicate morning-brief job.

## Approval marker

```
APPROVED_CRON_DISABLED_JOB_CLEANUP_FOR_463
```

## Snapshot path

```
/home/hermes/projects/trading-cleanup-backups/issue-463/
  jobs.before-disabled-cleanup.20260703T104300Z.json
```

## Removed jobs (12)

All confirmed `enabled=False` before removal.

### SI-v1 bot jobs (11)

| Job name | Script | Reason |
|----------|--------|--------|
| `si-bot-a-backtest-0217` | `si_bot_a_backtest.sh` | SI-v1 decommissioned |
| `si-bot-a-daily-0810` | `si_bot_a_daily.sh` | SI-v1 decommissioned |
| `si-bot-b-backtest-0242` | `si_bot_b_backtest.sh` | SI-v1 decommissioned |
| `si-bot-b-daily-0820` | `si_bot_b_daily.sh` | SI-v1 decommissioned |
| `si-bot-b-walkforward-sun0415` | `si_bot_b_walkforward.sh` | SI-v1 decommissioned |
| `si-bot-c-backtest-0307` | `si_bot_c_backtest.sh` | SI-v1 decommissioned |
| `si-bot-c-daily-0830` | `si_bot_c_daily.sh` | SI-v1 decommissioned |
| `si-bot-c-walkforward-sun0445` | `si_bot_c_walkforward.sh` | SI-v1 decommissioned |
| `si-bot-d-backtest-0151` | `si_bot_d_backtest.sh` | SI-v1 decommissioned |
| `si-bot-d-daily-0840` | `si_bot_d_daily.sh` | SI-v1 decommissioned |
| `si-bot-d-walkforward-sun0510` | `si_bot_d_walkforward.sh` | SI-v1 decommissioned |

### Duplicate job (1)

| Job name | Script | Reason |
|----------|--------|--------|
| `morning-brief-1040 — disabled (duplicate of morning-brief-daily)` | `morning_brief.py` | Duplicate of `morning-brief-daily` |

## Jobs intentionally NOT removed

| Job name | enabled | Reason |
|----------|---------|--------|
| `hermes-standby-monitor` | False | Preserved as historical standby marker |
| `si-v2-t4-watcher (30m, detector-only)` | False | Preserved (may be re-enabled for T4 monitoring) |

## Pre/Post counts

| Metric | Before | After |
|--------|:------:|:-----:|
| Total jobs | 59 | 47 |
| Removed | — | 12 |

## Validation

```bash
# JSON validity
python3 -m json.tool /opt/data/profiles/orchestrator/cron/jobs.json → VALID JSON ✅

# No SI-bot jobs remain
grep -c "si-bot-" /opt/data/profiles/orchestrator/cron/jobs.json → 0 ✅

# Preserved jobs intact
grep -E "hermes-standby|si-v2-t4-watcher|morning-brief-daily" → found ✅

# Correct total
python3 -c "import json; print(len(json.load(...)['jobs']))" → 47 ✅
```

## Safety statement

```
No enabled=True jobs touched.
No Docker changes.
No Freqtrade config/strategy changes.
No script files deleted.
No runtime restarts.
No live trading.
Snapshot created before removal (see path above).
Rollback: restore /home/hermes/projects/trading-cleanup-backups/issue-463/jobs.before-disabled-cleanup.*.json to /opt/data/profiles/orchestrator/cron/jobs.json
```
