#!/usr/bin/env bash
# guardian_loop.sh — Persistent 5-min loop for external_cron_guardian.sh
# Survives Hermes scheduler failures independently.
# Managed via: terminal(background=true)
set -euo pipefail
LOGDIR="/home/hermes/projects/trading/orchestrator/logs"
GUARDIAN="/home/hermes/projects/trading/orchestrator/scripts/external_cron_guardian.sh"
echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] Guardian loop started (PID=$$)" >> "$LOGDIR/external_cron_guardian.log"
while true; do
    bash "$GUARDIAN" 2>&1 || true
    sleep 300  # 5 minutes
done
