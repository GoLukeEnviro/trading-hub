#!/usr/bin/env bash
# external_cron_guardian.sh — Independent watchdog for Trading Hub
# Runs every 5 minutes via trading-guardian Docker container.
# Mount layout:
#   /guardian/entrypoint  → baked-in guardian scripts
#   /guardian/data        → /home/hermes/projects/trading
#   /guardian/cron        → /opt/data/profiles/orchestrator/cron
#   /guardian/scripts     → /opt/data/profiles/orchestrator/scripts
#   /var/run/docker.sock  → Docker API access
#
# Does NOT modify trading configs, strategies, or bot states.
set -euo pipefail

WORKDIR="/guardian/data"
JOBS_JSON="/guardian/cron/jobs.json"
BACKUP_JSON="/guardian/data/orchestrator/config/cron_jobs_backup.json"
LOGFILE="$WORKDIR/orchestrator/logs/external_cron_guardian.log"
SIGNAL_FILE="$WORKDIR/ai-hedge-fund-crypto/output/hermes_signal.json"
SCRIPTS_DIR="/guardian/scripts"
PROJECT_SCRIPTS_DIR="$WORKDIR/orchestrator/scripts"
MAX_SIGNAL_AGE_MIN=30
MAX_STUCK_JOBS=3

# ── Permission guard configuration ─────────────────────────────
# PERMISSION_GUARD_MODE=check  → report drift only, no changes
# PERMISSION_GUARD_MODE=repair → fix drift on explicitly listed paths
PERMISSION_GUARD_MODE="${PERMISSION_GUARD_MODE:-repair}"

mkdir -p "$(dirname "$LOGFILE")"

ts() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }
log() { echo "[$(ts)] $*" >> "$LOGFILE"; }

alert_count=0

# ── 1. Check jobs.json exists and is valid JSON ──────────────────
if [ ! -f "$JOBS_JSON" ]; then
    log "CRITICAL: jobs.json MISSING — restoring from backup"
    if [ -f "$BACKUP_JSON" ]; then
        cp "$BACKUP_JSON" "$JOBS_JSON"
        log "RESTORED: jobs.json from backup"
    else
        log "FATAL: No backup available either"
    fi
    alert_count=$((alert_count + 1))
elif ! python3 -c "import json; json.load(open('$JOBS_JSON'))" 2>/dev/null; then
    log "CRITICAL: jobs.json is invalid JSON — restoring from backup"
    if [ -f "$BACKUP_JSON" ]; then
        cp "$BACKUP_JSON" "$JOBS_JSON"
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
        signal_age_int=$(echo "$signal_age_min" | cut -d. -f1)
        if [ "$signal_age_int" -ge "$MAX_SIGNAL_AGE_MIN" ]; then
            log "ACTION: Signal stale (${signal_age_min}min >= ${MAX_SIGNAL_AGE_MIN}min) — triggering heartbeat via docker exec"

            # Trigger heartbeat via Docker API (container has docker socket)
            if docker exec ai-hedge-fund-crypto python3 -c \
               "import urllib.request; urllib.request.urlopen('http://localhost:8080/trigger')" 2>/dev/null; then
                log "OK: ai-hedge-fund-crypto /trigger called"
                sleep 15
                # Run pipeline via hermes-agent container
                if docker exec hermes-agent bash -c \
                   "cd /home/hermes/projects/trading && python3 orchestrator/scripts/trading_pipeline.py" 2>/dev/null; then
                    log "OK: trading_pipeline.py triggered via hermes-agent"
                else
                    log "WARN: Could not trigger pipeline via hermes-agent"
                fi
            else
                log "ERROR: Could not trigger ai-hedge-fund-crypto heartbeat"
            fi
            alert_count=$((alert_count + 1))
        else
            log "OK: Signal fresh (${signal_age_min}min < ${MAX_SIGNAL_AGE_MIN}min)"
        fi
    fi
else
    log "WARNING: Signal file not found — attempting heartbeat trigger"
    docker exec ai-hedge-fund-crypto python3 -c \
        "import urllib.request; urllib.request.urlopen('http://localhost:8080/trigger')" 2>/dev/null || true
    alert_count=$((alert_count + 1))
fi

# ── 4. Check critical scripts exist in profile dir ───────────────
for script in ai_hedge_signal_heartbeat.sh trading_pipeline.py drawdown_guard.py container_watchdog.sh mcp_watchdog.sh backup_rotation.py; do
    if [ ! -f "$SCRIPTS_DIR/$script" ]; then
        log "WARNING: Missing script $SCRIPTS_DIR/$script — copying from project"
        src="$PROJECT_SCRIPTS_DIR/$script"
        if [ -f "$src" ]; then
            cp "$src" "$SCRIPTS_DIR/$script"
            chmod +x "$SCRIPTS_DIR/$script" 2>/dev/null || true
            log "RESTORED: $script copied to profile dir"
        else
            log "FATAL: $script not found in project dir either"
        fi
    fi
done

# ── 5. Permission drift guard for trading runtime files ──────────
# Detects and repairs permission regressions on critical shared
# state files. Hermes main process (root) and container writers
# (UID 1000) can create files that break cron jobs (UID 10000).
#
# Scope: ONLY the explicitly listed files and directories below.
# Does NOT touch: configs, strategies, DBs, candle data, models,
# exchange keys, secrets, or any path not listed here.
#
# Modes:
#   PERMISSION_GUARD_MODE=check  → report only
#   PERMISSION_GUARD_MODE=repair → apply chmod/chgrp as needed

PERM_DIRS=(
    "$WORKDIR/freqtrade/shared"
    "$WORKDIR/freqtrade/logs"
    "$WORKDIR/orchestrator/logs"
)

# file_path:expected_mode:expected_group
PERM_FILES=(
    "$WORKDIR/freqtrade/shared/primo_signal_state.json:0644:10000"
    "$WORKDIR/freqtrade/shared/fleet_risk_state.json:0644:10000"
    "$WORKDIR/freqtrade/shared/.fleet_risk_state.json.lock:0664:10000"
    "$WORKDIR/orchestrator/logs/memory-backfill.log:0664:10000"
    "$WORKDIR/freqtrade/logs/fleet_risk_update.log:0664:10000"
)

perm_drift_count=0

# ── 5a. Directory checks ────────────────────────────────────────
for d in "${PERM_DIRS[@]}"; do
    if [ ! -d "$d" ]; then
        log "PERM_SKIP: Directory $d does not exist"
        continue
    fi

    dir_mode=$(stat -c '%a' "$d" 2>/dev/null || echo "???")
    dir_gid=$(stat -c '%g' "$d" 2>/dev/null || echo "???")

    if [ "$dir_mode" != "2775" ] || [ "$dir_gid" != "10000" ]; then
        log "PERM_DRIFT_DIR: $d mode=$dir_mode gid=$dir_gid expected=2775:10000"
        perm_drift_count=$((perm_drift_count + 1))

        if [ "$PERMISSION_GUARD_MODE" = "repair" ]; then
            chgrp 10000 "$d" 2>/dev/null || true
            chmod 2775 "$d" 2>/dev/null || true
            after_mode=$(stat -c '%a' "$d" 2>/dev/null || echo "???")
            after_gid=$(stat -c '%g' "$d" 2>/dev/null || echo "???")
            log "PERM_FIXED_DIR: $d mode=$dir_mode->$after_mode gid=$dir_gid->$after_gid"
        fi
    fi
done

# ── 5b. File checks ─────────────────────────────────────────────
for entry in "${PERM_FILES[@]}"; do
    fpath="${entry%%:*}"
    rest="${entry#*:}"
    expected_mode="${rest%%:*}"
    expected_gid="${rest##*:}"

    if [ ! -f "$fpath" ]; then
        log "PERM_SKIP: File $fpath does not exist"
        continue
    fi

    cur_mode=$(stat -c '%a' "$fpath" 2>/dev/null || echo "???")
    cur_gid=$(stat -c '%g' "$fpath" 2>/dev/null || echo "???")

    drift=0

    # Normalize mode for comparison (strip leading zeros)
    cur_mode_norm=$((10#$cur_mode))
    expected_mode_norm=$((10#$expected_mode))

    if [ "$cur_mode_norm" != "$expected_mode_norm" ]; then
        drift=1
    fi
    if [ "$cur_gid" != "$expected_gid" ]; then
        drift=1
    fi

    if [ "$drift" -eq 1 ]; then
        log "PERM_DRIFT_FILE: $fpath mode=$cur_mode gid=$cur_gid expected=$expected_mode:$expected_gid"
        perm_drift_count=$((perm_drift_count + 1))

        if [ "$PERMISSION_GUARD_MODE" = "repair" ]; then
            chgrp "$expected_gid" "$fpath" 2>/dev/null || true
            chmod "$expected_mode" "$fpath" 2>/dev/null || true
            after_mode=$(stat -c '%a' "$fpath" 2>/dev/null || echo "???")
            after_gid=$(stat -c '%g' "$fpath" 2>/dev/null || echo "???")
            log "PERM_FIXED_FILE: $fpath mode=$cur_mode->$after_mode gid=$cur_gid->$after_gid"
        fi
    fi
done

# ── 5c. Fix root:root files in Hermes profile cron dir ──────────
# The Hermes gateway process writes cron/jobs.json as root:root 0600.
# Cron jobs (UID 10000) cannot read it. Auto-correct to root:10000 0640.
CRON_DIR="/guardian/cron"
if [ -d "$CRON_DIR" ]; then
    root_root_count=$(find "$CRON_DIR" -type f -user 0 -group 0 2>/dev/null | wc -l || echo "0")
    if [ "$root_root_count" -gt 0 ]; then
        log "PERM_DRIFT_CRON: $root_root_count root:root file(s) in $CRON_DIR"
        if [ "$PERMISSION_GUARD_MODE" = "repair" ]; then
            find "$CRON_DIR" -type f -user 0 -group 0 \
                -exec chgrp 10000 {} \; -exec chmod 640 {} \; 2>/dev/null || true
            log "PERM_FIXED_CRON: $root_root_count file(s) corrected to root:10000 640"
        fi
        perm_drift_count=$((perm_drift_count + root_root_count))
    fi
fi

if [ "$perm_drift_count" -gt 0 ]; then
    if [ "$PERMISSION_GUARD_MODE" = "check" ]; then
        log "PERM_CHECK: $perm_drift_count drift(s) detected (check mode — no changes applied)"
    else
        log "PERM_REPAIR: $perm_drift_count drift(s) detected and repaired"
    fi
fi

# ── 6. Summary ───────────────────────────────────────────────────
if [ "$alert_count" -eq 0 ] && [ "$perm_drift_count" -eq 0 ]; then
    log "OK: All checks passed (jobs healthy, signal fresh, scripts present, permissions clean)"
else
    total=$((alert_count + perm_drift_count))
    log "SUMMARY: $total issue(s) detected (alerts=$alert_count, perm_drift=$perm_drift_count, mode=$PERMISSION_GUARD_MODE)"
fi
