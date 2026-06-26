# Scheduler Patch: Cron History Hook

**Date:** 20260626_100608
**Source SHA256:** f2816dea78a62445
**Patch file:** `hermes-scheduler-cron-history-hook-f2816dea78a62445.patch`
**Durability Risk:** HIGH — /opt/hermes is NOT Git-tracked

## What This Patch Does

1. Adds `from orchestrator.scripts.cron_history_writer import record_cron_run` import
2. Captures no_agent stdout/stderr from `_run_job_script()` return value
3. Calls `record_cron_run()` after `mark_job_run()` in `_process_job()`

## Why Not Patched Directly

The Hermes scheduler at `/opt/hermes/cron/scheduler.py` is not in a Git
repository. Direct patching would be overwritten by `hermes update`.
The patch must reside in the trading repo and be re-applied after updates.

## How to Apply (L3)

```bash
# 1. Backup
cp /opt/hermes/cron/scheduler.py /opt/hermes/cron/scheduler.py.bak

# 2. Apply
cd /opt/hermes && patch -p1 < /home/hermes/projects/trading/orchestrator/patches/hermes-scheduler-cron-history-hook-f2816dea78a62445.patch

# 3. Verify
python3 -m py_compile /opt/hermes/cron/scheduler.py
grep -c 'record_cron_run' /opt/hermes/cron/scheduler.py  # should be > 0
```

## Rollback

```bash
cp /opt/hermes/cron/scheduler.py.bak /opt/hermes/cron/scheduler.py
```

## Verification

```python
python3 -c "
import hashlib
s = open('/opt/hermes/cron/scheduler.py').read()
print('record_cron_run imported:', 'record_cron_run' in s)
print('SHA256:', hashlib.sha256(s.encode()).hexdigest()[:16])
"
```
