#!/usr/bin/env bash
# =============================================================================
# healthcheck_foundation.sh — Runtime health check for FOMO Phase 3
# =============================================================================
# Run THIS AFTER the bot container is started.
# Verifies paths, network, config, dry_run flags, and basic connectivity.
# =============================================================================

set -uo pipefail

CONTAINER="freqtrade-fomo-phase3"
BASE="/home/hermes/projects/trading/freqtrade/bots/fomo-phase3"
PASS=0
FAIL=0

green() { printf "  ✅ %s\n" "$1"; ((PASS++)); }
red()   { printf "  ❌ %s\n" "$1"; ((FAIL++)); }
check() { if [ "$1" -eq 0 ]; then green "$2"; else red "$2"; fi; }

echo "═══════════════════════════════════════════"
echo "  FOMO Phase 3 — Container Health Check"
echo "  $(date -u '+%Y-%m-%d %H:%M UTC')"
echo "═══════════════════════════════════════════"

# --- 1. Container status ---
echo ""
echo "1. CONTAINER STATUS"

docker ps --filter "name=$CONTAINER" --format '{{.Status}}' | grep -q "Up"
check $? "Container '$CONTAINER' is running"

# --- 2. Dry-run verification ---
echo ""
echo "2. DRY-RUN VERIFICATION"

DR=$(docker exec "$CONTAINER" python3 -c "
import json
c=json.load(open('/freqtrade/config/config_fomo_phase3_dryrun.json'))
print(c.get('dry_run','MISSING'))
" 2>/dev/null || echo "EXEC_FAILED")

if [ "$DR" = "True" ]; then
    green "dry_run = True (inside container)"
elif [ "$DR" = "EXEC_FAILED" ]; then
    red "Cannot exec into container"
else
    red "dry_run = $DR (MUST be True!)"
fi

# --- 3. Network connectivity ---
echo ""
echo "3. NETWORK"

docker inspect "$CONTAINER" --format '{{range $k,$v:=.NetworkSettings.Networks}}{{$k}} {{end}}' 2>/dev/null | grep -q "ki-fabrik"
check $? "Connected to ki-fabrik network"

# --- 4. Mount paths ---
echo ""
echo "4. MOUNT PATHS"

docker exec "$CONTAINER" test -d /freqtrade/config 2>/dev/null
check $? "/freqtrade/config mounted"

docker exec "$CONTAINER" test -d /freqtrade/user_data 2>/dev/null
check $? "/freqtrade/user_data mounted"

docker exec "$CONTAINER" test -f /freqtrade/config/config_fomo_phase3_dryrun.json 2>/dev/null
check $? "Config file accessible inside container"

docker exec "$CONTAINER" test -d /freqtrade/user_data/strategies 2>/dev/null
check $? "Strategies dir accessible inside container"

# --- 5. Strategy file ---
echo ""
echo "5. STRATEGY"

docker exec "$CONTAINER" ls /freqtrade/user_data/strategies/FOMO_Phase3_v0.py 2>/dev/null | grep -q ".py"
check $? "Strategy file present in container"

# --- 6. Shared volume ---
echo ""
echo "6. SHARED INFRASTRUCTURE"

docker exec "$CONTAINER" test -f /freqtrade/shared/fleetguard_v1.py 2>/dev/null
check $? "Shared FleetGuard accessible"

# --- 7. API server ---
echo ""
echo "7. API SERVER"

docker exec "$CONTAINER" curl -s -o /dev/null -w "%{http_code}" \
  http://127.0.0.1:8087/api/v1/ping 2>/dev/null | grep -q "200"
check $? "REST API responds at 127.0.0.1:8087"

# --- Summary ---
echo ""
echo "═══════════════════════════════════════════"
echo "  RESULTS: $PASS passed, $FAIL failed"
echo "═══════════════════════════════════════════"
exit $FAIL
