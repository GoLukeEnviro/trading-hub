#!/usr/bin/env bash
#
# SI v2 Active Cycle Runner — read_only One-Shot Cron Entrypoint
#
# Used by the one-shot proof job to exercise the Rainbow read_only
# path with the same wrapper that the permanent 6h job uses.
#
# - Sets SI_V2_RAINBOW_MODE=read_only before delegating.
# - Logs to the same /opt/data/logs/si-v2-active-cycle/ tree.
# - The permanent 6h job (script=si_v2_active_cycle_cron.sh) is NOT
#   modified — it still defaults to fixture mode for safety.
#
# Safety: read-only, proposal-only, no mutations, no live trading.
# The DB-backed stub runs in this same process tree, then is killed
# by the wrapper's cleanup trap.

set -euo pipefail

export SI_V2_RAINBOW_MODE=read_only

exec /opt/data/scripts/si-v2-active-cycle-runner.sh \
  >> /opt/data/logs/si-v2-active-cycle/cron-read-only.log 2>&1
