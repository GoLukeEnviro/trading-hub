#!/bin/bash
# mcp_watchdog.sh v2 — Auto-restart bitget_mcp_server.py if dead
# Runs every 5min via Hermes cron. Only outputs on restart (silent = OK).
#
# v2 fix: handle pgrep pipefail correctly, don't crash on set -euo pipefail

LOG="/home/hermes/projects/trading/orchestrator/logs/mcp_server.log"
WATCHDOG_LOG="/home/hermes/projects/trading/orchestrator/logs/mcp_watchdog.log"
STATE="/home/hermes/projects/trading/orchestrator/state/mcp_watchdog_state.json"
SCRIPT="/home/hermes/projects/trading/orchestrator/scripts/bitget_mcp_server.py"

now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Check if script exists
if [ ! -f "$SCRIPT" ]; then
    echo "{\"timestamp\":\"${now}\",\"mcp_processes\":0,\"status\":\"script_missing\"}" > "$STATE"
    # Silent exit — no script to watch
    exit 0
fi

# Count processes (handle pgrep returning non-zero when no match)
count=$(pgrep -f bitget_mcp_server.py 2>/dev/null | wc -l) || count=0

# Write state always
echo "{\"timestamp\":\"${now}\",\"mcp_processes\":${count},\"status\":\"$([ ${count} -gt 0 ] && echo running || echo down)\"}" > "$STATE"

if [ "$count" -eq 0 ]; then
    echo "[${now}] MCP-Server down (0 processes), restarting..." >> "$WATCHDOG_LOG"
    nohup python3 "$SCRIPT" >> "$LOG" 2>&1 &
    sleep 2
    new_count=$(pgrep -f bitget_mcp_server.py 2>/dev/null | wc -l) || new_count=0
    if [ "$new_count" -gt 0 ]; then
        echo "🔄 MCP-Server restarted successfully (${new_count} processes)"
        echo "[${now}] Restart SUCCESS (${new_count} processes)" >> "$WATCHDOG_LOG"
    else
        echo "❌ MCP-Server restart FAILED"
        echo "[${now}] Restart FAILED" >> "$WATCHDOG_LOG"
    fi
    exit 0  # Output delivered as alert
fi

# Silent = all good
exit 0
