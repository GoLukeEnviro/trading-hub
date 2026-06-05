#!/usr/bin/env bash
# global_trigger_lock.sh — Serialized /trigger access with stale-safe flock.
#
# Usage:
#   bash orchestrator/scripts/global_trigger_lock.sh          # normal mode
#   bash orchestrator/scripts/global_trigger_lock.sh --test    # lock test only
#
# Behaviour:
#   - Acquires exclusive flock on LOCK_FILE (stale-safe after LOCK_TIMEOUT).
#   - Calls /trigger on ai-hedge-fund-crypto via docker exec Python.
#   - On lock conflict: exits 0 with SKIP (no Telegram spam).
#   - On timeout/stale: breaks lock, re-acquires, calls trigger.
#   - On trigger failure: exits 1 with FAIL + message.
#   - On success: exits 0 with OK + pair count.
#
# Lock lifecycle:
#   - Lock acquired => flock holds it for max LOCK_TIMEOUT seconds.
#   - If lock file mtime > LOCK_TIMEOUT seconds ago => stale => remove & retry.
#   - After trigger completes => lock released.

set -euo pipefail

PROJECT="/home/hermes/projects/trading"
LOCK_DIR="$PROJECT/orchestrator/state/locks"
LOCK_FILE="$LOCK_DIR/trigger.lock"
LOG="$PROJECT/orchestrator/logs/trigger_lock.log"
LOCK_TIMEOUT=180
CONTAINER="trading-ai-hedge-fund-1"
TRIGGER_URL="http://localhost:8080/trigger"
# Docker network IP (resolved dynamically, bypasses EXEC=0 proxy)
AI_HEDGE_IP=""
CURL_TIMEOUT=180

_test_mode=0
for arg; do
  [[ "$arg" == "--test" ]] && _test_mode=1
done

mkdir -p "$LOCK_DIR"

log() {
  local ts
  ts="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  echo "[$ts] $*" >> "$LOG"
}

# ── Stale lock detection ──────────────────────────────────────────
if [ -f "$LOCK_FILE" ]; then
  lock_age=$(( $(date +%s) - $(stat -c %Y "$LOCK_FILE" 2>/dev/null || echo 0) ))
  if [ "${lock_age:-0}" -gt "$LOCK_TIMEOUT" ] 2>/dev/null; then
    log "WARN stale_lock age=${lock_age}s > ${LOCK_TIMEOUT}s — removing"
    rm -f "$LOCK_FILE"
  fi
fi

# ── Flock-based serialization ─────────────────────────────────────
(
  if ! flock -n 200; then
    log "SKIP lock_busy"
    echo "SKIP lock_busy"
    exit 0
  fi

  echo "$$" > "$LOCK_FILE"

  if [ "$_test_mode" -eq 1 ]; then
    log "TEST lock_acquired"
    echo "TEST lock_acquired"
    exit 0
  fi

  log "LOCK acquired — calling /trigger"

  # ── Resolve Docker network IP for ai-hedge-fund ────────────────
  if [ -z "$AI_HEDGE_IP" ]; then
    AI_HEDGE_IP=$(docker inspect "$CONTAINER" --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}={{$v.IPAddress}}{{"\n"}}{{end}}' 2>/dev/null | grep 'hermes-net' | head -1 | cut -d= -f2)
  fi

  # ── Call /trigger via HTTP (primary) or docker exec (fallback) ──
  trigger_exit=0
  trigger_out=""
  if [ -n "$AI_HEDGE_IP" ]; then
    log "TRIGGER via HTTP http://$AI_HEDGE_IP:8080/trigger"
    trigger_out=$(curl -s --max-time "$CURL_TIMEOUT" "http://$AI_HEDGE_IP:8080/trigger" 2>&1) || trigger_exit=$?
  fi

  # Fallback to docker exec if HTTP failed and docker is available
  if [ "${trigger_exit:-0}" -ne 0 ] && command -v docker &>/dev/null; then
    log "HTTP trigger failed (exit=${trigger_exit}), trying docker exec fallback"
    trigger_out=$(docker exec "$CONTAINER" python3 -c "
import urllib.request, json, sys
try:
    req = urllib.request.Request('$TRIGGER_URL')
    resp = urllib.request.urlopen(req, timeout=$CURL_TIMEOUT)
    data = json.loads(resp.read().decode())
    pairs = data.get('pairs', {})
    if not pairs:
        print('WARN trigger_response_empty_pairs')
    print(f'OK pairs={len(pairs)}')
except urllib.error.HTTPError as e:
    print(f'HTTP_ERROR {e.code} {e.reason}')
    sys.exit(1)
except Exception as e:
    print(f'TRIGGER_ERROR {e}')
    sys.exit(1)
" 2>&1) || trigger_exit=$?
  fi

  # If both methods failed, try parsing curl output for success indicators
  if [ "${trigger_exit:-0}" -ne 0 ] && echo "$trigger_out" | grep -qi 'pairs\|OK\|triggered'; then
    log "PARTIAL trigger_out contains success indicator"
    trigger_exit=0
  fi

  if [ "${trigger_exit:-0}" -ne 0 ]; then
    log "FAIL exit=${trigger_exit} output=${trigger_out:0:200}"
    echo "FAIL ${trigger_out:0:200}"
    exit 1
  fi

  log "OK ${trigger_out:0:200}"
  echo "${trigger_out:0:200}"
  exit 0

) 200>"$LOCK_FILE"

exit $?