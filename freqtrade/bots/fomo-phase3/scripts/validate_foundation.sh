#!/usr/bin/env bash
# =============================================================================
# validate_foundation.sh — Read-only validation of FOMO Phase 3 foundation
# =============================================================================
# Run this AFTER creating the scaffold to verify structural integrity.
# Does NOT start the bot, place trades, or modify any files.
# =============================================================================

set -uo pipefail

BASE="/home/hermes/projects/trading/freqtrade/bots/fomo-phase3"
PASS=0
FAIL=0

green() { printf "  ✅ %s\n" "$1"; ((PASS++)); }
red()   { printf "  ❌ %s\n" "$1"; ((FAIL++)); }
check() { if [ "$1" -eq 0 ]; then green "$2"; else red "$2"; fi; }

echo "═══════════════════════════════════════════"
echo "  FOMO Phase 3 — Foundation Validation"
echo "  $(date -u '+%Y-%m-%d %H:%M UTC')"
echo "═══════════════════════════════════════════"

# --- 1. Directory structure ---
echo ""
echo "1. DIRECTORY STRUCTURE"

test -d "$BASE";                                      check $? "Base directory exists"
test -d "$BASE/config";                               check $? "  config/"
test -d "$BASE/user_data";                             check $? "  user_data/"
test -d "$BASE/user_data/strategies";                  check $? "  user_data/strategies/"
test -d "$BASE/user_data/data";                        check $? "  user_data/data/"
test -d "$BASE/user_data/logs";                        check $? "  user_data/logs/"
test -d "$BASE/user_data/backtest_results";            check $? "  user_data/backtest_results/"
test -d "$BASE/user_data/hyperopt_results";            check $? "  user_data/hyperopt_results/"
test -d "$BASE/research";                               check $? "  research/"
test -d "$BASE/reports";                                check $? "  reports/"
test -d "$BASE/artifacts";                              check $? "  artifacts/"
test -d "$BASE/scripts";                                check $? "  scripts/"
test -d "$BASE/docs/context";                           check $? "  docs/context/"

# --- 2. Key files ---
echo ""
echo "2. KEY FILES"

CONFIG="$BASE/config/config_fomo_phase3_dryrun.json"
test -f "$CONFIG";                                     check $? "Config file exists"
test -f "$BASE/user_data/strategies/FOMO_Phase3_v0.py"; check $? "Strategy placeholder exists"
test -f "$BASE/docker-compose.fomo.yml";               check $? "Compose fragment exists"
test -f "$BASE/.env.example";                           check $? ".env.example exists"

# --- 3. Config validation ---
echo ""
echo "3. CONFIG VALIDATION"

if [ -f "$CONFIG" ]; then
    # Parse JSON
    python3 -c "import json; json.load(open('$CONFIG'))" 2>/dev/null
    check $? "Config is valid JSON"

    # dry_run must be true
    DR=$(python3 -c "import json; print(json.load(open('$CONFIG')).get('dry_run','MISSING'))")
    if [ "$DR" = "True" ]; then
        green "  dry_run = True"
    else
        red "  dry_run = $DR (MUST be True!)"
    fi

    # No exchange keys
    HAS_KEY=$(python3 -c "
import json
c=json.load(open('$CONFIG'))
ex=c.get('exchange',{})
print('YES' if ex.get('key') or ex.get('secret') else 'NO')
")
    if [ "$HAS_KEY" = "NO" ]; then
        green "  No exchange credentials"
    else
        red "  WARNING: Exchange credentials found!"
    fi

    # Trading mode
    TM=$(python3 -c "import json; print(json.load(open('$CONFIG')).get('trading_mode','MISSING'))")
    echo "  Trading mode: $TM"

    # initial_state
    IS=$(python3 -c "import json; print(json.load(open('$CONFIG')).get('initial_state','MISSING'))")
    if [ "$IS" = "stopped" ]; then
        green "  initial_state = stopped (safe)"
    else
        echo "  ⚠️  initial_state = $IS (bot will auto-start)"
    fi

    # API server binding
    API_IP=$(python3 -c "
import json; c=json.load(open('$CONFIG'))
api=c.get('api_server',{})
print(api.get('listen_ip_address','MISSING'))
")
    if [ "$API_IP" = "127.0.0.1" ]; then
        green "  API server bound to 127.0.0.1 (local only)"
    else
        echo "  ⚠️  API binding: $API_IP"
    fi
fi

# --- 4. Docker network ---
echo ""
echo "4. DOCKER NETWORK"

docker network inspect ki-fabrik >/dev/null 2>&1
check $? "ki-fabrik network exists"

# --- 5. Port availability ---
echo ""
echo "5. PORT CHECK"

python3 -c "
import socket
s=socket.socket()
r=s.connect_ex(('127.0.0.1',8087))
print('AVAILABLE' if r!=0 else 'IN USE')
s.close()
" 2>/dev/null | grep AVAILABLE >/dev/null
check $? "Port 8087 is available"

# --- Summary ---
echo ""
echo "═══════════════════════════════════════════"
echo "  RESULTS: $PASS passed, $FAIL failed"
echo "═══════════════════════════════════════════"
exit $FAIL
