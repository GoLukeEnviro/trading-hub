#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/hermes/projects/trading"
WATCHER="$ROOT/freqtrade/shared/fleet_watcher.py"
LOG_DIR="$ROOT/freqtrade/shared/logs"
LOG_FILE="$LOG_DIR/fleet_watcher.log"

DURATION="${1:-30}"
INTERVAL="${2:-60}"
TAIL_LINES="${3:-80}"
MAX_BYTES="${4:-1048576}"
BACKUPS="${5:-5}"

mkdir -p "$LOG_DIR"

exec python3 "$WATCHER" \
  --daemon \
  --duration-minutes "$DURATION" \
  --interval "$INTERVAL" \
  --tail-lines "$TAIL_LINES" \
  --log-file "$LOG_FILE" \
  --log-max-bytes "$MAX_BYTES" \
  --log-backups "$BACKUPS"
