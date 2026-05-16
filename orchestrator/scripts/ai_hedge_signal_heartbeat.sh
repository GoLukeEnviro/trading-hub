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
CONTAINER="ai-hedge-fund-crypto"
CANONICAL="$SIGNAL_DIR/hermes_signal.json"
LATEST="$SIGNAL_DIR/latest/hermes_signal.json"
LOG="$SIGNAL_DIR/logs/heartbeat.log"
TEMP="${CANONICAL}.tmp.$$"

mkdir -p "$(dirname "$LATEST")" "$(dirname "$LOG")"

# --- Step 1: Trigger via container-internal localhost:8080 ---
echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] heartbeat start" >> "$LOG"

HTTP_CODE=$(docker exec "$CONTAINER" python3 -c "
import urllib.request, json, sys
try:
    r = urllib.request.urlopen('http://localhost:8080/trigger', timeout=120)
    data = r.read()
    # write to stdout for capture
    sys.stdout.buffer.write(data)
    sys.exit(0 if r.status == 200 else 1)
except Exception as e:
    print(f'ERROR: {e}', file=sys.stderr)
    sys.exit(1)
" 2>>"$LOG" > "$TEMP") && HTTP_OK=true || HTTP_OK=false

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
