#!/bin/bash
# memory-backfill-cron.sh — Wrapper for the Memory Backfill cron job
#
# Runs via Hermes scheduler (no_agent=true) every 6 hours.
# Uses flock to prevent concurrent runs.
# Logs to /home/hermes/projects/trading/orchestrator/logs/memory-backfill.log
#
# Usage:
#   ./memory-backfill-cron.sh [--since HOURS] [--dry-run] [--verbose]

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCRIPT_NAME="memory_backfill.py"
SCRIPT_DIR="/opt/data/profiles/orchestrator/scripts"
LOCK_FILE="/tmp/memory-backfill.lock"
SINCE_HOURS="${MEMORY_BACKFILL_SINCE:-48}"  # Default 48h, overridable via env

# ---------------------------------------------------------------------------
# Locking (flock)
# ---------------------------------------------------------------------------

exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    echo "SKIP: another instance is already running (lock: $LOCK_FILE)"
    exit 0
fi

# Cleanup trap
cleanup() {
    rm -f "$LOCK_FILE"
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Run the Python backfill script
# ---------------------------------------------------------------------------

cd "$SCRIPT_DIR"

# Pass --since if provided via env or args
EXTRA_ARGS=""
if [ -n "${MEMORY_BACKFILL_SINCE:-}" ]; then
    EXTRA_ARGS="--since ${MEMORY_BACKFILL_SINCE}"
fi

# Forward any script arguments
python3 "$SCRIPT_DIR/$SCRIPT_NAME" $EXTRA_ARGS "$@"

exit $?
