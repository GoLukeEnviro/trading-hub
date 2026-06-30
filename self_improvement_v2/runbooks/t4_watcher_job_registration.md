# SI-v2 T4 Watcher Job Registration (repo-only)

## Purpose

Register the SI-v2 T4 watcher as a **repo-backed, read-only job definition** without mutating the live Hermes scheduler.

This runbook exists because the live Hermes registry artifacts are **runtime-only**:

- `/opt/data/profiles/orchestrator/cron/jobs.json` = live scheduler state
- `/home/hermes/projects/trading/orchestrator/config/cron_jobs_backup.json` = host mirror / local runtime artifact, **not tracked in Git**

A normal PR therefore cannot safely or reviewably modify the live/runtime-backed JSON. The tracked source-of-truth for this PR is the YAML definition under `self_improvement_v2/cron_defs/` plus the wrapper script under `orchestrator/scripts/`.

## Registered Artifacts

- `self_improvement_v2/cron_defs/t4_watcher_jobs.yaml`
- `orchestrator/scripts/si_v2_t4_watcher_cron.sh`
- `orchestrator/scripts/si_v2_t4_measurement_watcher.sh` (from PR #403)

## Intended Runtime Semantics

- cadence: every 30 minutes
- `STILL_WAITING` (`watcher rc=0`) = healthy / non-error / no stdout alert
- `MEASUREMENT_READY` (`watcher rc=10`) = local alert + local log, but wrapper exits 0
- `SAFETY_BLOCKED`, `DATA_UNAVAILABLE`, `SCRIPT_ERROR` = local alert + non-zero wrapper exit
- no Decision Engine execution
- no Apply
- no Restart
- no Rollback
- no trading mutation

## Local Log Paths

When deployed and activated later, the wrapper writes to:

- `/opt/data/logs/si-v2-t4-watcher/cron.log`
- `/opt/data/logs/si-v2-t4-watcher/runs/`
- `/opt/data/logs/si-v2-t4-watcher/alerts/`

## Why this PR stops at repo-only registration

Per `self_improvement_v2/docs/CRON_ACTIVATION_CEREMONY.md`, SI-v2 cron jobs stay disabled by default until a separate activation ceremony is approved.

That means this PR intentionally does **not**:

- edit live `jobs.json`
- edit the runtime-only `cron_jobs_backup.json` mirror
- deploy scripts into `/opt/data/profiles/orchestrator/scripts/`
- enable a live Hermes job

## Follow-up activation gate (separate approval)

A later approved activation step must:

1. deploy the two scripts into `/opt/data/profiles/orchestrator/scripts/`
2. insert the disabled job entry into live `jobs.json`
3. validate scheduler health
4. observe the disabled entry
5. enable only with explicit approval token

## Rollback

Rollback is runtime-only and separate from this PR:

- disable the live job entry in `jobs.json`, or
- remove the live job entry and restore the prior JSON snapshot

This repository PR remains purely declarative and reversible by Git revert.
