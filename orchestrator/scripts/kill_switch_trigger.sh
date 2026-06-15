#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# kill_switch_trigger.sh — CLI wrapper around freqtrade/shared/kill_switch.py
#
# Commands:
#   status | check   Print current kill-switch state
#   halt [reason]    Activate HALT_NEW — block all new entries
#   emergency [reas] Activate EMERGENCY — block entries + close positions
#   clear [reason]   Revert to NORMAL
#   auto-check       Read fleet_risk_state.json, auto-activate if thresholds
#                    exceeded (DD_HALT_THRESHOLD / DD_EMERGENCY_THRESHOLD env)
#
# ⚠ Offline-only (CLI) — no Docker, no Freqtrade runtime mutation.
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Path resolution ──────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
KILL_SWITCH_PY="$PROJECT_ROOT/freqtrade/shared/kill_switch.py"
FLEET_RISK_STATE="$PROJECT_ROOT/freqtrade/shared/fleet_risk_state.json"

# Default thresholds (overridable via environment)
DD_HALT_THRESHOLD="${DD_HALT_THRESHOLD:-12}"
DD_EMERGENCY_THRESHOLD="${DD_EMERGENCY_THRESHOLD:-18}"

# ── Help ─────────────────────────────────────────────────────────────────────
usage() {
    cat <<EOF
Usage: $(basename "$0") <command> [reason]

Commands:
  status | check      Print current kill-switch mode and state
  halt [reason]       Set kill-switch to HALT_NEW (block new entries)
  emergency [reason]  Set kill-switch to EMERGENCY (block + close)
  clear [reason]      Revert kill-switch to NORMAL
  auto-check          Read fleet_risk_state.json, auto-activate if DD exceeds
                      thresholds (DD_HALT_THRESHOLD=$DD_HALT_THRESHOLD%,
                      DD_EMERGENCY_THRESHOLD=$DD_EMERGENCY_THRESHOLD%)

Environment:
  DD_HALT_THRESHOLD       Drawdown % for HALT_NEW (default: 12)
  DD_EMERGENCY_THRESHOLD  Drawdown % for EMERGENCY (default: 18)
  KILL_SWITCH_FILE        Override path to kill_switch.json state file
EOF
    exit 1
}

# ── Helpers ──────────────────────────────────────────────────────────────────
die() {
    echo "ERROR: $*" >&2
    exit 1
}

require_kill_switch_py() {
    if [[ ! -f "$KILL_SWITCH_PY" ]]; then
        die "kill_switch.py not found at $KILL_SWITCH_PY"
    fi
}

# Run kill_switch.py with the given arguments
ks() {
    require_kill_switch_py
    cd "$PROJECT_ROOT"
    python3 "$KILL_SWITCH_PY" "$@"
}

# Fetch the worst drawdown from fleet_risk_state.json
get_worst_drawdown() {
    if [[ ! -f "$FLEET_RISK_STATE" ]]; then
        echo "0"
        return
    fi
    python3 -c "
import json, sys
try:
    with open('$FLEET_RISK_STATE') as f:
        data = json.load(f)
    sources = data.get('portfolio', {}).get('sources', {})
    if not sources:
        print(0)
        sys.exit(0)
    worst = 0.0
    for name, src in sources.items():
        dd = float(src.get('drawdown_pct', src.get('max_drawdown_pct', 0)) or 0)
        if dd > worst:
            worst = dd
    print(f'{worst:.1f}')
except Exception:
    print(0)
"
}

# ── Commands ─────────────────────────────────────────────────────────────────
cmd_status() {
    ks status
}

cmd_check() {
    cmd_status
}

cmd_halt() {
    local reason="${1:-manual halt via trigger script}"
    ks halt "$reason"
    echo "Kill-switch set to HALT_NEW: $reason"
}

cmd_emergency() {
    local reason="${1:-emergency via trigger script}"
    ks emergency "$reason"
    echo "Kill-switch set to EMERGENCY: $reason"
}

cmd_clear() {
    local reason="${1:-cleared via trigger script}"
    ks clear "$reason"
    echo "Kill-switch cleared (NORMAL): $reason"
}

cmd_auto_check() {
    local worst_dd
    worst_dd="$(get_worst_drawdown)"
    echo "auto-check: worst drawdown = ${worst_dd}%"

    # Check current kill-switch state — skip if already active
    local current_mode
    current_mode="$(ks status 2>/dev/null | grep 'Mode:' | awk '{print $2}')"
    if [[ "$current_mode" == "HALT_NEW" || "$current_mode" == "EMERGENCY" ]]; then
        echo "auto-check: kill-switch already active (mode=$current_mode) — skipping"
        exit 0
    fi

    local dd_int
    dd_int="$(python3 -c "print(int(float('${worst_dd}')))")"

    if (( dd_int >= DD_EMERGENCY_THRESHOLD )); then
        echo "auto-check: EMERGENCY threshold exceeded (${worst_dd}% >= ${DD_EMERGENCY_THRESHOLD}%)"
        cmd_emergency "auto-check: drawdown ${worst_dd}% exceeded EMERGENCY threshold ${DD_EMERGENCY_THRESHOLD}%"
    elif (( dd_int >= DD_HALT_THRESHOLD )); then
        echo "auto-check: HALT threshold exceeded (${worst_dd}% >= ${DD_HALT_THRESHOLD}%)"
        cmd_halt "auto-check: drawdown ${worst_dd}% exceeded HALT threshold ${DD_HALT_THRESHOLD}%"
    else
        echo "auto-check: drawdown within thresholds (${worst_dd}% < ${DD_HALT_THRESHOLD}%) — no action"
    fi
}

# ── Dispatch ─────────────────────────────────────────────────────────────────
[[ $# -lt 1 ]] && usage

command="$1"
shift || true
reason="$*"

case "$command" in
    status)    cmd_status ;;
    check)     cmd_check ;;
    halt)      cmd_halt "$reason" ;;
    emergency) cmd_emergency "$reason" ;;
    clear)     cmd_clear "$reason" ;;
    auto-check) cmd_auto_check ;;
    *)         usage ;;
esac
