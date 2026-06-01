#!/usr/bin/env bash
# setup_permanent_permissions.sh — Report permission drift only
# Runs at container start and periodically. No repair actions.
set -euo pipefail

BASEDIR="/home/hermes/projects/trading"
GID=10000

ts() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }
log() { echo "[$(ts)] PERM_FIX: $*"; }

# ── 1. Shared directories: report-only ──
DIRS=(
    "$BASEDIR/freqtrade/shared"
    "$BASEDIR/freqtrade/shared/logs"
    "$BASEDIR/freqtrade/shared/config"
    "$BASEDIR/freqtrade/shared/signals"
    "$BASEDIR/freqtrade/shared/strategies"
    "$BASEDIR/freqtrade/shared/downloads"
    "$BASEDIR/freqtrade/shared/images"
    "$BASEDIR/freqtrade/shared/__pycache__"
    "$BASEDIR/freqtrade/logs"
    "$BASEDIR/orchestrator/logs"
    "$BASEDIR/orchestrator/state"
    "$BASEDIR/orchestrator/state/riskguard"
    "$BASEDIR/orchestrator/state/config_diff"
    "$BASEDIR/orchestrator/state/auto_params"
    "$BASEDIR/orchestrator/state/standby"
    "$BASEDIR/orchestrator/reports"
    "$BASEDIR/orchestrator/backups"
)

for d in "${DIRS[@]}"; do
    if [ -d "$d" ]; then
        owner_group=$(stat -c '%G' "$d" 2>/dev/null || echo "unknown")
        mode=$(stat -c '%a' "$d" 2>/dev/null || echo "0000")
        if [ "$owner_group" != "ftuser" ] || [ "$mode" != "2775" ]; then
            log "DIR_DRIFT: $d owner_group=$owner_group mode=$mode expected_group=ftuser expected_mode=2775"
        fi
    fi
done

# ── 2. Critical shared state files: report-only ──
FILES=(
    "$BASEDIR/freqtrade/shared/primo_signal_state.json"
    "$BASEDIR/freqtrade/shared/fleet_risk_state.json"
    "$BASEDIR/freqtrade/shared/fleet_correlation_matrix.json"
    "$BASEDIR/freqtrade/shared/fleet_risk_manager.py"
    "$BASEDIR/freqtrade/shared/fleet_watcher.py"
    "$BASEDIR/freqtrade/shared/fleetguard_v1.py"
    "$BASEDIR/freqtrade/shared/calculate_correlation_matrix.py"
)

for f in "${FILES[@]}"; do
    if [ -f "$f" ]; then
        owner_group=$(stat -c '%G' "$f" 2>/dev/null || echo "unknown")
        mode=$(stat -c '%a' "$f" 2>/dev/null || echo "0000")
        if [ "$owner_group" != "ftuser" ] || [ "$mode" != "664" ]; then
            log "FILE_DRIFT: $f owner_group=$owner_group mode=$mode expected_group=ftuser expected_mode=664"
        fi
    fi
done

# ── 3. Lock files: report-only ──
for lock in "$BASEDIR"/freqtrade/shared/.*.lock; do
    if [ -f "$lock" ]; then
        owner_group=$(stat -c '%G' "$lock" 2>/dev/null || echo "unknown")
        mode=$(stat -c '%a' "$lock" 2>/dev/null || echo "0000")
        if [ "$owner_group" != "ftuser" ] || [ "$mode" != "664" ]; then
            log "LOCK_DRIFT: $lock owner_group=$owner_group mode=$mode expected_group=ftuser expected_mode=664"
        fi
    fi
done

# ── 4. Log files: report-only ──
for logf in "$BASEDIR"/orchestrator/logs/*.log "$BASEDIR"/freqtrade/logs/*.log; do
    if [ -f "$logf" ]; then
        owner_group=$(stat -c '%G' "$logf" 2>/dev/null || echo "unknown")
        mode=$(stat -c '%a' "$logf" 2>/dev/null || echo "0000")
        if [ "$owner_group" != "ftuser" ] || [ "$mode" != "664" ]; then
            log "LOG_DRIFT: $logf owner_group=$owner_group mode=$mode expected_group=ftuser expected_mode=664"
        fi
    fi
done

# ── 5. Cron directory: report-only ──
CRON_DIR="/opt/data/profiles/orchestrator/cron"
if [ -d "$CRON_DIR" ]; then
    json_owner=$(stat -c '%U:%G' "$CRON_DIR/jobs.json" 2>/dev/null || echo "missing")
    json_mode=$(stat -c '%a' "$CRON_DIR/jobs.json" 2>/dev/null || echo "0000")
    if [ "$json_owner" != "root:ftuser" ] || [ "$json_mode" != "640" ]; then
        log "CRON_DRIFT: $CRON_DIR/jobs.json owner=$json_owner mode=$json_mode expected_owner=root:ftuser expected_mode=640"
    fi
fi

# ── 6. Scripts in profile dir: report-only ──
SCRIPTS_DIR="/opt/data/profiles/orchestrator/scripts"
if [ -d "$SCRIPTS_DIR" ]; then
    for f in "$SCRIPTS_DIR"/*; do
        [ -f "$f" ] || continue
        owner=$(stat -c '%U:%G' "$f" 2>/dev/null || echo "missing")
        mode=$(stat -c '%a' "$f" 2>/dev/null || echo "0000")
        if [ "$owner" != "10000:10000" ] || [ "$mode" != "755" ]; then
            log "SCRIPT_DRIFT: $f owner=$owner mode=$mode expected_owner=10000:10000 expected_mode=755"
        fi
    done
fi

log "Permission report complete (no changes made, GID=$GID)"
