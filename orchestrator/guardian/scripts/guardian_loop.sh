#!/usr/bin/env bash
# guardian_loop.sh — Persistent 5-min loop for external_cron_guardian.sh
# Runs inside the trading-guardian Docker container.
# Mount layout:
#   /guardian/entrypoint  → baked-in scripts (guardian_loop.sh, external_cron_guardian.sh)
#   /guardian/data        → /home/hermes/projects/trading
#   /guardian/cron        → /opt/data/profiles/orchestrator/cron
#   /guardian/scripts     → /opt/data/profiles/orchestrator/scripts
#   /var/run/docker.sock  → Docker API access
set -euo pipefail

LOGDIR="/guardian/data/orchestrator/logs"
GUARDIAN="/guardian/entrypoint/external_cron_guardian.sh"

mkdir -p "$LOGDIR"

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] Guardian loop started (PID=$$) [trading-guardian container]" >> "$LOGDIR/external_cron_guardian.log"

while true; do
    bash "$GUARDIAN" 2>&1 || true
    sleep 300  # 5 minutes
done
