#!/usr/bin/env bash
# external_cron_guardian.sh — Independent watchdog outside Hermes cron scheduler
# Runs every 5 minutes as a persistent background loop.
# Checks: (1) Hermes jobs.json health, (2) signal freshness, (3) missing scripts
# Does NOT modify trading configs, strategies, or bot states.
# Logs to: orchestrator/logs/external_cron_guardian.log
set -euo pipefail

WORKDIR="/home/hermes/projects/trading"
LOGFILE="$WORKDIR/orchestrator/logs/external_cron_guardian.log"
SIGNAL_FILE="$WORKDIR/ai-hedge-fund-crypto/output/hermes_signal.json"
MAX_SIGNAL_AGE_MIN=30
MAX_STUCK_JOBS=3

# ── Detect host vs container paths ───────────────────────
# The Hermes container bind-mounts /opt/hermes/config → /opt/data.
# On the HOST, the canonical path is /opt/hermes/config/...
# Inside the CONTAINER, it's /opt/data/...
# Both may exist on the host, but only /opt/hermes/config is authoritative.
if [ -f "/opt/hermes/config/profiles/orchestrator/cron/jobs.json" ]; then
    # Running on the HOST — use the real mount source
    PROFILE_BASE="/opt/hermes/config/profiles/orchestrator"
elif [ -f "/opt/data/profiles/orchestrator/cron/jobs.json" ]; then
    # Running INSIDE the Hermes container
    PROFILE_BASE="/opt/data/profiles/orchestrator"
else
    # Neither found — will be detected in checks below
    PROFILE_BASE="/opt/hermes/config/profiles/orchestrator"
fi

JOBS_JSON="$PROFILE_BASE/cron/jobs.json"
BACKUP_JSON="$WORKDIR/orchestrator/config/cron_jobs_backup.json"
SCRIPTS_DIR="$PROFILE_BASE/scripts"

mkdir -p "$(dirname "$LOGFILE")"

ts() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }

log() { echo "[$(ts)] $*" >> "$LOGFILE"; }

alert_count=0

# ── 1. Check jobs.json exists and is valid JSON ──────────────────
if [ ! -f "$JOBS_JSON" ]; then
    log "CRITICAL: jobs.json MISSING — restoring from backup"
    if [ -f "$BACKUP_JSON" ]; then
        cp "$BACKUP_JSON" "$JOBS_JSON"
chown 10000:10000 "$JOBS_JSON" 2>/dev/null || true
chmod 600 "$JOBS_JSON" 2>/dev/null || true
        log "RESTORED: jobs.json from backup"
    else
        log "FATAL: No backup available either"
    fi
    alert_count=$((alert_count + 1))
elif ! python3 -c "import json; json.load(open('$JOBS_JSON'))" 2>/dev/null; then
    log "CRITICAL: jobs.json is invalid JSON — restoring from backup"
    if [ -f "$BACKUP_JSON" ]; then
        cp "$BACKUP_JSON" "$JOBS_JSON"
chown 10000:10000 "$JOBS_JSON" 2>/dev/null || true
chmod 600 "$JOBS_JSON" 2>/dev/null || true
        log "RESTORED: jobs.json from backup"
    fi
    alert_count=$((alert_count + 1))
fi

# ── 2. Check for stuck jobs (next_run_at=null on enabled jobs) ───
stuck_count=$(python3 -c "
import json, sys
try:
    with open('$JOBS_JSON') as f:
        data = json.load(f)
    jobs = data.get('jobs', data) if isinstance(data, dict) else data
    stuck = [j['name'] for j in jobs
             if j.get('enabled', False)
             and j.get('next_run_at') is None
             and j.get('no_agent', False)]
    print(len(stuck))
except Exception as e:
    print(f'ERROR: {e}')
" 2>/dev/null || echo "ERROR")

if [ "$stuck_count" != "ERROR" ] && [ "$stuck_count" -ge "$MAX_STUCK_JOBS" ]; then
    log "WARNING: $stuck_count stuck jobs detected (threshold=$MAX_STUCK_JOBS)"
    log "ACTION: Hermes cron needs manual recovery (delete+recreate stuck jobs)"
    alert_count=$((alert_count + 1))
elif [ "$stuck_count" = "ERROR" ]; then
    log "ERROR: Could not parse stuck job count"
fi

# ── 3. Check signal freshness ────────────────────────────────────
if [ -f "$SIGNAL_FILE" ]; then
    signal_age_min=$(python3 -c "
import time, os
age = (time.time() - os.path.getmtime('$SIGNAL_FILE')) / 60
print(f'{age:.1f}')
" 2>/dev/null || echo "ERROR")

    if [ "$signal_age_min" != "ERROR" ]; then
        # Compare as integer (bash can't do float comparison easily)
        signal_age_int=$(echo "$signal_age_min" | cut -d. -f1)
        if [ "$signal_age_int" -ge "$MAX_SIGNAL_AGE_MIN" ]; then
            log "ACTION: Signal stale (${signal_age_min}min >= ${MAX_SIGNAL_AGE_MIN}min) — triggering heartbeat + pipeline"
            # Trigger heartbeat
            if bash "$WORKDIR/orchestrator/scripts/ai_hedge_signal_heartbeat.sh" >> "$LOGFILE" 2>&1; then
                log "OK: Signal heartbeat triggered successfully"
            else
                log "ERROR: Signal heartbeat FAILED"
            fi
            # Trigger pipeline
            if python3 "$WORKDIR/orchestrator/scripts/trading_pipeline.py" >> "$LOGFILE" 2>&1; then
                log "OK: Trading pipeline triggered successfully"
            else
                log "ERROR: Trading pipeline FAILED"
            fi
            alert_count=$((alert_count + 1))
        else
            log "OK: Signal fresh (${signal_age_min}min < ${MAX_SIGNAL_AGE_MIN}min)"
        fi
    fi
else
    log "WARNING: Signal file not found — triggering heartbeat"
    bash "$WORKDIR/orchestrator/scripts/ai_hedge_signal_heartbeat.sh" >> "$LOGFILE" 2>&1 || true
    alert_count=$((alert_count + 1))
fi

# ── 4. Check critical scripts exist in profile dir ───────────────
for script in ai_hedge_signal_heartbeat.sh trading_pipeline.py drawdown_guard.py; do
    if [ ! -f "$SCRIPTS_DIR/$script" ]; then
        log "WARNING: Missing script $SCRIPTS_DIR/$script — copying from project"
        src="$WORKDIR/orchestrator/scripts/$script"
        if [ -f "$src" ]; then
            cp "$src" "$SCRIPTS_DIR/$script"
chown 10000:10000 "$SCRIPTS_DIR/$script" 2>/dev/null || true
chmod 755 "$SCRIPTS_DIR/$script" 2>/dev/null || true
            chmod +x "$SCRIPTS_DIR/$script" 2>/dev/null || true
            log "RESTORED: $script copied to profile dir"
        else
            log "FATAL: $script not found in project dir either"
        fi
    fi
done


# ── 5. Fix permission drift on config files ──────────────────────
# Hermes main process runs as root and creates root:root files.
# Cron jobs run as UID 10000 and can't read them.
# This block auto-corrects drift on each guardian cycle.
CONFIG_DIR="$PROFILE_BASE"
if [ -d "$CONFIG_DIR" ]; then
    # Fix non-executable files: root:root → root:10000, 640
    find "$CONFIG_DIR" -type f -user 0 -group 0 ! -executable         -exec chgrp 10000 {} \; -exec chmod 640 {} \; 2>/dev/null || true
    # Fix executable files: preserve +x bit
    find "$CONFIG_DIR" -type f -user 0 -group 0 -executable         -exec chgrp 10000 {} \; -exec chmod 750 {} \; 2>/dev/null || true
    # Fix directories: setgid so new files inherit group
    find "$CONFIG_DIR" -type d -user 0 -group 0         -exec chgrp 10000 {} \; -exec chmod 2775 {} \; 2>/dev/null || true
fi

# ── 6. Summary ───────────────────────────────────────────────────
if [ "$alert_count" -eq 0 ]; then
    log "OK: All checks passed (jobs healthy, signal fresh, scripts present)"
else
    log "SUMMARY: $alert_count issue(s) detected and acted upon"
fi
