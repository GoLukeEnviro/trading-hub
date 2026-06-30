# SI-v2 T4 Watcher Job Registration

## Purpose

Register the T4 measurement watcher as a **Hermes no_agent detector job** without enabling any Decision Engine, apply path, restart, or rollback.

This runbook is the repo-backed registration contract for PR #404.

## Safety Boundary

- Detection only
- No Measurement Decision Engine execution
- No `execute_apply`
- No Docker / Compose restart
- No rollback
- No `dry_run=false`
- No live trading

## Canonical Runtime Script

- Repo source: `/home/hermes/projects/trading/orchestrator/scripts/si_v2_t4_watcher_job.sh`
- Underlying detector: `/home/hermes/projects/trading/orchestrator/scripts/si_v2_t4_measurement_watcher.sh`
- Runtime logs: `/opt/data/logs/si-v2-t4-watcher/`

## Runtime Behavior Contract

| Underlying watcher exit | Meaning | Wrapper behavior | Scheduler result |
|---|---|---|---|
| `0` | `STILL_WAITING` | Silent, writes log only | `ok` |
| `10` | `MEASUREMENT_READY` | Emits local alert + writes log | `ok` |
| `20` | `SAFETY_BLOCKED` | Emits local alert + preserves non-zero exit | `error` |
| `30` | `DATA_UNAVAILABLE` | Emits local alert + preserves non-zero exit | `error` |
| `40` | `SCRIPT_ERROR` | Emits local alert + preserves non-zero exit | `error` |

## Recommended Hermes Job Spec

```json
{
  "name": "si-v2-t4-watcher (30m, detector-only)",
  "schedule": "every 30m",
  "script": "si_v2_t4_watcher_job.sh",
  "no_agent": true,
  "deliver": "local",
  "workdir": "/home/hermes/projects/trading"
}
```

## Registration Command

Use the Hermes cron tool payload below after explicit runtime approval. The repo PR does **not** execute this step.

```json
{
  "action": "create",
  "name": "si-v2-t4-watcher (30m, detector-only)",
  "schedule": "every 30m",
  "script": "si_v2_t4_watcher_job.sh",
  "no_agent": true,
  "deliver": "local",
  "workdir": "/home/hermes/projects/trading"
}
```

If the CLI path is preferred, create the job interactively with the same fields and then verify the stored job via `hermes cron list` or `cronjob(action='list')`.

## Validation

```bash
bash -n orchestrator/scripts/si_v2_t4_watcher_job.sh
python3 -m pytest tests/test_si_v2_t4_watcher_job.py tests/test_si_v2_scheduler_scripts.py -q
SI_V2_REPO_ROOT=/home/hermes/projects/trading bash orchestrator/scripts/si_v2_t4_watcher_job.sh
```

Expected outcomes:
- `STILL_WAITING` → exit `0`, no stdout, log file created under `/opt/data/logs/si-v2-t4-watcher/`
- `MEASUREMENT_READY` → exit `0`, visible alert on stdout, log file created
- blocked / data unavailable / script error → non-zero exit with alert text

## Rollback

- Pause or remove the Hermes job.
- Restore `jobs.json` from the last known-good backup if a revert is required.
- Remove runtime-deployed `si_v2_t4_watcher_job.sh` only via the standard runtime ownership path.

## Non-Goals

- No auto-handoff into a Decision Engine
- No runtime apply chain
- No container restart plan
- No strategy or risk mutation
