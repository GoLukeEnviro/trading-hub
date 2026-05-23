#!/bin/bash
# restore_cron_jobs.sh — Restore all trading cron jobs from backup
# Usage: bash restore_cron_jobs.sh
# Runs after scheduler reset / container restart to re-register all jobs.
#
# Persistence: /opt/data/profiles/orchestrator/cron/jobs.json
# Backup:      /home/hermes/projects/trading/orchestrator/config/cron_jobs_backup.json

set -euo pipefail

JOBS_DB="/opt/data/profiles/orchestrator/cron/jobs.json"
BACKUP="/home/hermes/projects/trading/orchestrator/config/cron_jobs_backup.json"
LOG="/home/hermes/projects/trading/orchestrator/logs/cron_restore.log"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] restore_cron_jobs.sh started" >> "$LOG"

# Check if jobs already exist (more than just Fleet Report)
CURRENT_COUNT=$(python3 -c "
import json
try:
    with open('$JOBS_DB') as f:
        d = json.load(f)
    print(len(d.get('jobs',[])))
except:
    print(0)
" 2>/dev/null || echo "0")

if [ "$CURRENT_COUNT" -ge 10 ]; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Already $CURRENT_COUNT jobs registered. Skip." >> "$LOG"
    echo "OK: $CURRENT_COUNT jobs already present"
    exit 0
fi

# Restore from backup
if [ -f "$BACKUP" ]; then
    cp "$BACKUP" "$JOBS_DB"
    NEW_COUNT=$(python3 -c "
import json
with open('$JOBS_DB') as f:
    d = json.load(f)
print(len(d.get('jobs',[])))
" 2>/dev/null)
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Restored $NEW_COUNT jobs from backup" >> "$LOG"
    echo "OK: Restored $NEW_COUNT jobs"
else
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ERROR: Backup not found at $BACKUP" >> "$LOG"
    echo "ERROR: No backup file"
    exit 1
fi
