#!/usr/bin/env bash
#
# SI v2 Active Cycle Runner — Cron Entrypoint (Hermes Scheduler)
#
# This script is invoked by the Hermes cronjob scheduler every 6 hours.
# It delegates to the hardened wrapper and redirects output to cron.log,
# matching the task spec's cron line semantics:
#
#   17 */6 * * * /opt/data/scripts/si-v2-active-cycle-runner.sh >> /opt/data/logs/si-v2-active-cycle/cron.log 2>&1
#
# Per-run detailed logs: /opt/data/logs/si-v2-active-cycle/cycle-<timestamp>.log
# Aggregate cron log:    /opt/data/logs/si-v2-active-cycle/cron.log
#
# Safety: read-only, proposal-only, no mutations, no live trading.
set -euo pipefail

exec /opt/data/scripts/si-v2-active-cycle-runner.sh \
  >> /opt/data/logs/si-v2-active-cycle/cron.log 2>&1
