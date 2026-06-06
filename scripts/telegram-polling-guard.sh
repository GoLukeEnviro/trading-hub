#!/usr/bin/env bash
# telegram-polling-guard.sh — Persistent Telegram polling conflict fix (Batch 2A)
#
# Controls which Hermes gateway profiles auto-start on container boot.
# Uses the gateway_state.json mechanism that the s6 reconciler reads.
#
# The state files live on the persistent Docker volume (/opt/hermes-green/config)
# and survive container restarts — unlike tmpfs s6 down files.
#
# Usage:
#   ./telegram-polling-guard.sh apply     # Disable redundant pollers
#   ./telegram-polling-guard.sh revert    # Re-enable all pollers
#   ./telegram-polling-guard.sh status    # Show current states
#
# Safety: Never touches default profile (canonical poller).
#         Never modifies trading configs or tokens.

set -euo pipefail

HERMES_CONFIG="/opt/hermes-green/config"
DISABLED_PROFILES=("trading" "mira" "orchestrator" "weather" "weatherbot")

redact_json() {
    sed 's/[0-9]\{8,\}:[A-Za-z0-9_-]\{20,\}/[REDACTED]/g'
}

set_gateway_state() {
    local profile="$1" new_state="$2"
    local state_file
    if [ "$profile" = "default" ]; then
        state_file="${HERMES_CONFIG}/gateway_state.json"
    else
        state_file="${HERMES_CONFIG}/profiles/${profile}/gateway_state.json"
    fi

    if [ ! -f "$state_file" ]; then
        echo "  SKIP: ${profile} (no gateway_state.json)"
        return 1
    fi

    local current_state
    current_state=$(python3 -c "
import json, sys
with open('${state_file}') as f:
    d = json.load(f)
print(d.get('gateway_state', 'unknown'))
" 2>/dev/null) || current_state="parse_error"

    if [ "$current_state" = "$new_state" ]; then
        echo "  OK: ${profile} already ${new_state}"
        return 0
    fi

    python3 -c "
import json
with open('${state_file}') as f:
    d = json.load(f)
d['gateway_state'] = '${new_state}'
d['exit_reason'] = 'telegram_polling_guard' if '${new_state}' == 'stopped' else None
with open('${state_file}', 'w') as f:
    json.dump(d, f, indent=2)
" 2>/dev/null && echo "  SET: ${profile} ${current_state} -> ${new_state}" || echo "  ERR: ${profile} failed to update"
}

cmd_status() {
    echo "=== Gateway Profile States ==="
    echo ""

    echo "--- default (canonical poller) ---"
    if [ -f "${HERMES_CONFIG}/gateway_state.json" ]; then
        python3 -c "
import json
with open('${HERMES_CONFIG}/gateway_state.json') as f:
    d = json.load(f)
print(f'  state: {d.get(\"gateway_state\", \"unknown\")}')
print(f'  exit_reason: {d.get(\"exit_reason\", \"none\")}')
" 2>/dev/null || echo "  (parse error)"
    else
        echo "  (no state file)"
    fi

    echo ""
    for profile in "${DISABLED_PROFILES[@]}"; do
        echo "--- ${profile} ---"
        local state_file="${HERMES_CONFIG}/profiles/${profile}/gateway_state.json"
        if [ -f "$state_file" ]; then
            python3 -c "
import json
with open('${state_file}') as f:
    d = json.load(f)
print(f'  state: {d.get(\"gateway_state\", \"unknown\")}')
print(f'  exit_reason: {d.get(\"exit_reason\", \"none\")}')
" 2>/dev/null || echo "  (parse error)"
        else
            echo "  (no state file)"
        fi
    done
}

cmd_apply() {
    echo "=== Applying Telegram Polling Guard ==="
    echo "Disabling redundant pollers..."
    echo ""
    for profile in "${DISABLED_PROFILES[@]}"; do
        set_gateway_state "$profile" "stopped"
    done
    echo ""
    echo "Canonical poller (default) preserved."
    echo ""
    echo "NOTE: Changes take effect on next container restart."
    echo "      For immediate effect, use s6-svc -d on running services."
}

cmd_revert() {
    echo "=== Reverting Telegram Polling Guard ==="
    echo "Re-enabling all pollers..."
    echo ""
    for profile in "${DISABLED_PROFILES[@]}"; do
        set_gateway_state "$profile" "running"
    done
    echo ""
    echo "All profiles set to 'running'."
    echo ""
    echo "NOTE: Changes take effect on next container restart."
    echo "      For immediate effect, use s6-svc -u on services."
}

case "${1:-status}" in
    apply)   cmd_apply ;;
    revert)  cmd_revert ;;
    status)  cmd_status ;;
    *)       echo "Usage: $0 {apply|revert|status}" ;;
esac
