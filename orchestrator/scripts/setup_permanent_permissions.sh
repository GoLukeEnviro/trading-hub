#!/usr/bin/env bash
# setup_permanent_permissions.sh — Fix ALL permission drift permanently
# Runs at container start and periodically. Idempotent. Safe for dry-run fleet.
set -euo pipefail

BASEDIR="/home/hermes/projects/trading"
GID=10000

ts() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }
log() { echo "[$(ts)] PERM_FIX: $*"; }

# ── 1. Shared directories: setgid 2775, group ftuser (GID 10000) ──
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
        chgrp "$GID" "$d" 2>/dev/null || true
        chmod 2775 "$d" 2>/dev/null || true
    fi
done

# ── 2. Critical shared state files: readable by ftuser (644 = guardian-consistent) ──
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
        chgrp "$GID" "$f" 2>/dev/null || true
        chmod 664 "$f" 2>/dev/null || true
    fi
done

# ── 3. Lock files: group-writable ──
for lock in "$BASEDIR"/freqtrade/shared/.*.lock; do
    if [ -f "$lock" ]; then
        chgrp "$GID" "$lock" 2>/dev/null || true
        chmod 664 "$lock" 2>/dev/null || true
    fi
done

# ── 4. Log files: group-writable ──
for logf in "$BASEDIR"/orchestrator/logs/*.log "$BASEDIR"/freqtrade/logs/*.log; do
    if [ -f "$logf" ]; then
        chgrp "$GID" "$logf" 2>/dev/null || true
        chmod 664 "$logf" 2>/dev/null || true
    fi
done

# ── 5. Cron directory: root:root → root:ftuser ──
CRON_DIR="/opt/data/profiles/orchestrator/cron"
if [ -d "$CRON_DIR" ]; then
    find "$CRON_DIR" -type f -user 0 -group 0 \
        -exec chgrp "$GID" {} \; -exec chmod 640 {} \; 2>/dev/null || true
fi

# ── 6. Scripts in profile dir: executable ──
SCRIPTS_DIR="/opt/data/profiles/orchestrator/scripts"
if [ -d "$SCRIPTS_DIR" ]; then
    find "$SCRIPTS_DIR" -type f \( -name "*.sh" -o -name "*.py" \) \
        -exec chmod +x {} \; 2>/dev/null || true
fi

log "All permissions fixed (GID=$GID, dirs=2775, state=644, logs=664, cron=640)"
