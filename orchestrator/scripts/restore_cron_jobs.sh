#!/usr/bin/env bash
# restore_cron_jobs.sh — thin wrapper around the merge-safe Python restore.
#
# This file remains the scheduler entrypoint (cron job 607f1890215d,
# "cron-guardian", runs every 6h) so the cron registry needs NO change.
# All restore logic lives in restore_cron_jobs.py (self-contained, unit-tested).
#
# Safety properties (see restore_cron_jobs.py):
#   * a backup without SI-v2 job 64866012641a is INVALID and never used
#   * restore is add-only / merge-safe (never removes or shrinks live registry)
#   * --dry-run never writes
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/restore_cron_jobs.py" "$@"
