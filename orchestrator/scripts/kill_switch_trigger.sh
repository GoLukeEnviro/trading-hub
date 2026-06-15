#!/usr/bin/env bash
# =============================================================================
# kill_switch_trigger.sh  — Trading Hub Kill Switch CLI
# =============================================================================
# Usage:
#   ./kill_switch_trigger.sh status
#   ./kill_switch_trigger.sh halt   [reason]
#   ./kill_switch_trigger.sh emergency [reason]
#   ./kill_switch_trigger.sh clear  [reason]
#   ./kill_switch_trigger.sh auto-check   # used by drawdown_guard / cron
#
# Environment:
#   KILL_SWITCH_FILE       Override path to kill_switch.json
#   DD_HALT_THRESHOLD      Drawdown % triggering HALT_NEW   (default: 12)
#   DD_EMERGENCY_THRESHOLD Drawdown % triggering EMERGENCY  (default: 18)
#   PYTHON                 Python binary (default: python3)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
KILL_SWITCH_MODULE="${REPO_ROOT}/freqtrade/shared/kill_switch.py"
FLEET_RISK_STATE="${REPO_ROOT}/freqtrade/shared/fleet_risk_state.json"

PYTHON="${PYTHON:-python3}"
DD_HALT_THRESHOLD="${DD_HALT_THRESHOLD:-12}"
DD_EMERGENCY_THRESHOLD="${DD_EMERGENCY_THRESHOLD:-18}"
EXPORT_FILE="${KILL_SWITCH_FILE:-${REPO_ROOT}/var/kill_switch.json}"

RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; NC='\033[0m'
log()  { echo -e "[$(date -u +%H:%M:%S)] $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*" >&2; }
ok()   { echo -e "${GREEN}[OK]${NC} $*"; }

if [[ ! -f "${KILL_SWITCH_MODULE}" ]]; then
    err "kill_switch.py not found at: ${KILL_SWITCH_MODULE}"
    exit 1
fi

run_ks() {
    PYTHONPATH="${REPO_ROOT}/freqtrade/shared:${PYTHONPATH:-}" \
    KILL_SWITCH_FILE="${EXPORT_FILE}" \
        "${PYTHON}" "${KILL_SWITCH_MODULE}" "$@"
}

CMD="${1:-status}"
REASON="${*:2}"

case "${CMD}" in

  status)
    log "Kill Switch status:"
    run_ks status
    ;;

  halt)
    warn "Activating HALT_NEW — all new entries will be blocked."
    warn "Reason: ${REASON:-manual halt}"
    run_ks halt "${REASON:-manual halt}"
    ok "HALT_NEW active. Use './kill_switch_trigger.sh clear' to resume."
    ;;

  emergency)
    err  "!!! ACTIVATING EMERGENCY MODE !!!"
    warn "All entries blocked. Strategies will attempt to close open positions."
    warn "Reason: ${REASON:-manual emergency}"
    run_ks emergency "${REASON:-manual emergency}"
    ok "EMERGENCY active. Monitor via dashboard. Use 'clear' to resume."
    ;;

  clear)
    log "Clearing kill switch -> NORMAL"
    run_ks clear "${REASON:-manual clear}"
    ok "Kill switch cleared. Normal operation resumed."
    ;;

  auto-check)
    log "auto-check: reading fleet_risk_state.json"

    if [[ ! -f "${FLEET_RISK_STATE}" ]]; then
        warn "fleet_risk_state.json not found — skipping auto-check"
        exit 0
    fi

    WORST_DD=$(KILL_SWITCH_FILE="${EXPORT_FILE}" \
        "${PYTHON}" -c "
import json
try:
    state = json.load(open('${FLEET_RISK_STATE}'))
    bots = state.get('bots') or state.get('bot_states') or {}
    dds = [abs(float(b.get('current_drawdown_pct') or b.get('drawdown_pct') or 0.0)) for b in bots.values()]
    print(max(dds) if dds else 0.0)
except Exception:
    print(0.0)
")

    log "Worst drawdown detected: ${WORST_DD}%"

    IS_EMERGENCY=$(awk "BEGIN{print (${WORST_DD} >= ${DD_EMERGENCY_THRESHOLD}) ? 1 : 0}")
    IS_HALT=$(awk "BEGIN{print (${WORST_DD} >= ${DD_HALT_THRESHOLD}) ? 1 : 0}")

    CURRENT_MODE=$(run_ks status | "${PYTHON}" -c "import sys,json; d=json.load(sys.stdin); print(d.get('mode','NORMAL'))" 2>/dev/null || echo "NORMAL")

    if [[ "${CURRENT_MODE}" != "NORMAL" ]]; then
        log "Kill switch already active (${CURRENT_MODE}) — no change."
        exit 0
    fi

    if [[ "${IS_EMERGENCY}" == "1" ]]; then
        err "DD ${WORST_DD}% >= EMERGENCY threshold ${DD_EMERGENCY_THRESHOLD}% — activating EMERGENCY"
        run_ks emergency "auto-check: drawdown ${WORST_DD}%"
    elif [[ "${IS_HALT}" == "1" ]]; then
        warn "DD ${WORST_DD}% >= HALT threshold ${DD_HALT_THRESHOLD}% — activating HALT_NEW"
        run_ks halt "auto-check: drawdown ${WORST_DD}%"
    else
        ok "Drawdown ${WORST_DD}% within limits. No action."
    fi
    ;;

  *)
    err "Unknown command: ${CMD}"
    echo "Usage: $0 [status|halt|emergency|clear|auto-check] [reason]"
    exit 1
    ;;
esac
