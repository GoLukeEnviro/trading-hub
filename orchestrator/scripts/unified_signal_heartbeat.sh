#!/usr/bin/env bash
# unified-signal-heartbeat.sh — Single authoritative signal freshness watchdog.
#
# This REPLACES both smart_heartbeat.py AND ai_hedge_signal_heartbeat.sh.
# It is the ONLY mechanism that calls /trigger.
#
# Behaviour:
#   1. Read CANONICAL signal (ai-hedge-fund-crypto/output/hermes_signal.json)
#   2. If fresh (age <= UNIFIED_TRIGGER_MIN): exit 0 — nothing to do.
#   3. If stale or missing: call /trigger via global_trigger_lock.sh.
#   4. After successful trigger: atomically sync CANONICAL -> LATEST.
#   5. Log everything to orchestrator/logs/unified_heartbeat.log.
#
# --test: safe mode — checks freshness and lock only, no trigger.
# --force: skip freshness check, trigger immediately (for manual use).
# --validate: check freshness, report status, no trigger.

set -euo pipefail

PROJECT="/home/hermes/projects/trading"
CANONICAL="$PROJECT/ai-hedge-fund-crypto/output/hermes_signal.json"
LATEST="$PROJECT/ai-hedge-fund-crypto/output/latest/hermes_signal.json"
LOCK_WRAPPER="$PROJECT/orchestrator/scripts/global_trigger_lock.sh"
LOG="$PROJECT/orchestrator/logs/unified_heartbeat.log"
UNIFIED_TRIGGER_MIN=16.0  # trigger if signal older than 16 minutes
                                     # pipeline hard block is 25min, heartbeat 20min
                                     # this sits between: catches before pipeline block

_mode="normal"
for arg; do
  case "$arg" in
    --test) _mode="test" ;;
    --force) _mode="force" ;;
    --validate) _mode="validate" ;;
  esac
done

mkdir -p "$(dirname "$LOG")" "$(dirname "$LATEST")"

log() {
  local ts
  ts="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  echo "[$ts] $*" >> "$LOG"
}

# ── Read signal and compute age (uses CANONICAL as truth) ─────────
signal_age_min=""
signal_ts=""
signal_pairs=""

if [ -f "$CANONICAL" ]; then
  read_signal=$(python3 -c "
import json, sys
from datetime import datetime, timezone
try:
    with open('$CANONICAL') as f:
        d = json.load(f)
    ts_s = d.get('timestamp_utc') or d.get('generated_at') or d.get('timestamp', '')
    ts = datetime.fromisoformat(ts_s.replace('Z', '+00:00'))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - ts).total_seconds() / 60.0
    pairs = len(d.get('pairs', {}))
    print(f'{age:.1f}|{ts_s}|{pairs}')
except Exception as e:
    print(f'ERROR|{e}|0')
" 2>/dev/null || true)

  IFS='|' read -r signal_age_min signal_ts signal_pairs <<< "$read_signal"
fi

_is_stale=false
_is_missing=false

if [ -z "$signal_age_min" ] || [ "$signal_age_min" = "ERROR" ] || [ ! -f "$CANONICAL" ]; then
  _is_missing=true
  log "STATE signal_missing"
elif (( $(echo "$signal_age_min > $UNIFIED_TRIGGER_MIN" | bc -l 2>/dev/null || echo 1) )); then
  _is_stale=true
  log "STATE stale age=${signal_age_min}min > ${UNIFIED_TRIGGER_MIN}min"
else
  log "STATE fresh age=${signal_age_min}min <= ${UNIFIED_TRIGGER_MIN}min pairs=${signal_pairs:-?}"
fi

# ── Validate mode — report only ────────────────────────────────────
if [ "$_mode" = "validate" ]; then
  if [ "$_is_missing" = true ]; then
    echo "VALIDATE MISSING canonical_signal_not_found"
  elif [ "$_is_stale" = true ]; then
    echo "VALIDATE STALE age=${signal_age_min}min threshold=${UNIFIED_TRIGGER_MIN}min"
  else
    echo "VALIDATE FRESH age=${signal_age_min}min pairs=${signal_pairs}"
  fi
  exit 0
fi

# ── Test mode — check lock wrapper only ────────────────────────────
if [ "$_mode" = "test" ]; then
  log "TEST mode — checking lock wrapper"
  lock_result=$(bash "$LOCK_WRAPPER" --test 2>&1) || true
  log "TEST lock_result=${lock_result}"
  echo "TEST ${lock_result}"
  exit 0
fi

# ── Decision: trigger or skip ─────────────────────────────────────
if [ "$_is_missing" = false ] && [ "$_is_stale" = false ] && [ "$_mode" != "force" ]; then
  log "SKIP signal_fresh age=${signal_age_min}min"
  exit 0
fi

# ── Trigger via global lock wrapper ───────────────────────────────
reason="stale"
[ "$_is_missing" = true ] && reason="missing"
[ "$_mode" = "force" ] && reason="force"
log "TRIGGER reason=${reason} age=${signal_age_min:-?}min"

trigger_result=$(bash "$LOCK_WRAPPER" 2>&1) || trigger_exit=$?

if [ "${trigger_exit:-0}" -ne 0 ]; then
  log "FAIL trigger_exit=${trigger_exit:-0} result=${trigger_result:0:200}"
  echo "FAIL ${trigger_result:0:200}"
  exit 1
fi

log "OK trigger_result=${trigger_result:0:200}"

# ── If trigger was SKIP'd (lock busy), exit cleanly — no sync ─────
if echo "$trigger_result" | grep -q "SKIP"; then
  log "SKIP trigger_skipped_lock_busy"
  exit 0
fi

# ── Atomic sync: CANONICAL -> LATEST ─────────────────────────────
# After successful trigger, canonical is fresh. Copy to latest/ atomically.
if [ -f "$CANONICAL" ]; then
  cp "$CANONICAL" "${LATEST}.tmp"
  mv "${LATEST}.tmp" "$LATEST"
  log "SYNC canonical_to_latest"

  # Verify sync
  latest_ts=$(python3 -c "
import json
try:
    with open('$LATEST') as f:
        d = json.load(f)
    print(d.get('timestamp_utc','?'))
except: print('?')
" 2>/dev/null || echo "?")
  log "SYNC_VERIFIED latest_ts=${latest_ts}"
fi

echo "OK triggered_and_synced age=${signal_age_min:-?}min"
exit 0