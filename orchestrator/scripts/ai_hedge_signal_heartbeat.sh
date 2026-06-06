#!/usr/bin/env bash
# ai_hedge_signal_heartbeat.sh — External heartbeat for ai-hedge-fund-crypto
#
# Triggers signal generation via /trigger endpoint,
# validates JSON, atomically updates canonical + latest copies.
#
# No trading bots, configs, or dry_run settings are modified.
# This script runs OUTSIDE the ai-hedge-fund-crypto container.
#
# Usage: ./ai_hedge_signal_heartbeat.sh
# Logs to: /home/hermes/projects/trading/ai-hedge-fund-crypto/output/logs/heartbeat.log
set -euo pipefail

SIGNAL_DIR="/home/hermes/projects/trading/ai-hedge-fund-crypto/output"
CONTAINER="trading-ai-hedge-fund-1"
CANONICAL="$SIGNAL_DIR/hermes_signal.json"
LATEST="$SIGNAL_DIR/latest/hermes_signal.json"
LOG="$SIGNAL_DIR/logs/heartbeat.log"
TEMP="${CANONICAL}.tmp.$$"

resolve_trigger_url() {
  if [ -n "${AI_HEDGE_HEARTBEAT_URL:-}" ]; then
    printf '%s\n' "$AI_HEDGE_HEARTBEAT_URL"
    return 0
  fi

  CONTAINER_IP=$(getent hosts "$CONTAINER" 2>/dev/null | awk 'NR==1{print $1; exit}' || true)
  if [ -n "$CONTAINER_IP" ]; then
    printf 'http://%s:8080/trigger\n' "$CONTAINER_IP"
    return 0
  fi

  if command -v docker >/dev/null 2>&1; then
    CONTAINER_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$CONTAINER" 2>/dev/null || true)
    if [ -n "$CONTAINER_IP" ]; then
      printf 'http://%s:8080/trigger\n' "$CONTAINER_IP"
      return 0
    fi
  fi

  printf '%s\n' "http://127.0.0.1:8410/trigger"
}

TARGET_URL="$(resolve_trigger_url)"

mkdir -p "$(dirname "$LATEST")" "$(dirname "$LOG")"

# --- Step 1: Trigger via docker-resolved ai-hedge-fund-crypto endpoint ---
echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] heartbeat start target=${TARGET_URL}" >> "$LOG"

HTTP_CODE=$(curl -sS -m 180 -o "$TEMP" -w '%{http_code}' "$TARGET_URL" 2>>"$LOG")
[ "$HTTP_CODE" = "200" ] && HTTP_OK=true || HTTP_OK=false

if [ "$HTTP_OK" != "true" ]; then
  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] ERROR: /trigger failed" >> "$LOG"
  rm -f "$TEMP"
  exit 1
fi

# --- Step 2: Validate JSON ---
if ! python3 -m json.tool "$TEMP" >/dev/null 2>&1; then
  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] ERROR: invalid JSON from /trigger" >> "$LOG"
  rm -f "$TEMP"
  exit 1
fi

# --- Step 3: Extract metadata ---
TS=$(python3 -c "
import json,sys
d=json.load(open(sys.argv[1]))
print(d.get('timestamp_utc','unknown'))
" "$TEMP" 2>/dev/null || echo "unknown")

PAIRS=$(python3 -c "
import json,sys
d=json.load(open(sys.argv[1]))
print(len(d.get('pairs',{})))
" "$TEMP" 2>/dev/null || echo "?")

# --- Step 4: Atomic update canonical ---
mv "$TEMP" "$CANONICAL"

# --- Step 5: Atomic update latest ---
cp "$CANONICAL" "${LATEST}.tmp"
mv "${LATEST}.tmp" "$LATEST"

# --- Step 6: Compute age for logging ---
AGE=$(python3 -c "
from datetime import datetime, timezone
import json
with open('$CANONICAL') as f:
    d = json.load(f)
ts = d.get('timestamp_utc', '')
if ts:
    dt = datetime.fromisoformat(ts)
    age = (datetime.now(timezone.utc) - dt).total_seconds() / 60
    print(f'{age:.1f}')
else:
    print('?')
" 2>/dev/null || echo "?")

echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] OK age=${AGE}min ts=${TS} pairs=${PAIRS}" >> "$LOG"
echo "OK age=${AGE}min"
exit 0
