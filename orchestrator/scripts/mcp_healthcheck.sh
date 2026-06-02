#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# MCP Bitget Paper Server — Cron Health Check
# Läuft jede 5 Minuten, prüft MCP-Server, killed Duplikate
# ═══════════════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="${SCRIPT_DIR}/.mcp_daemon.pid"
WATCHDOG_LOG="/home/hermes/projects/trading/orchestrator/logs/mcp/mcp_watchdog.log"
LOG_DIR="/home/hermes/projects/trading/orchestrator/logs/mcp"

mkdir -p "${LOG_DIR}"

# ── 1. Kill duplicates: nur 1 bitget_mcp_server.py soll laufen ──
MCP_COUNT=$(ps aux | grep bitget_mcp_server.py | grep -v grep | wc -l)

if [ "${MCP_COUNT}" -gt 1 ]; then
    echo "$(date -u +'%Y-%m-%dT%H:%M:%SZ') | CLEANUP | ${MCP_COUNT} duplicates found, killing extras" >> "${WATCHDOG_LOG}"
    # Keep only the first PID, kill the rest
    FIRST_PID=$(ps aux | grep bitget_mcp_server.py | grep -v grep | awk '{print $2}' | head -1)
    echo "${FIRST_PID}" > "${PID_FILE}" 2>/dev/null || true
    ps aux | grep bitget_mcp_server.py | grep -v grep | awk '{print $2}' | tail -n +2 | xargs -r kill 2>/dev/null || true
fi

# ── 2. Health check ──
if [ -f "${PID_FILE}" ] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
    exit 0
fi

# Try to find any running MCP process
RUNNING_PID=$(ps aux | grep bitget_mcp_server.py | grep -v grep | awk '{print $2}' | head -1)

if [ -n "${RUNNING_PID}" ]; then
    echo "${RUNNING_PID}" > "${PID_FILE}"
    exit 0
fi

# ── 3. Restart if dead ──
echo "$(date -u +'%Y-%m-%dT%H:%M:%SZ') | RESTART | server was dead, restarting" >> "${WATCHDOG_LOG}"
rm -f "${PID_FILE}"
export PAPER_LOG_DIR="${LOG_DIR}"
export PYTHONUNBUFFERED=1
export DRY_RUN=true

nohup /home/hermes/projects/trading/.venv/bin/python3 /home/hermes/projects/trading/orchestrator/scripts/bitget_mcp_server.py \
    >> "${LOG_DIR}/mcp_daemon.log" 2>&1 &
PID=$!
echo ${PID} > "${PID_FILE}"
echo "$(date -u +'%Y-%m-%dT%H:%M:%SZ') | START | PID=${PID}" >> "${WATCHDOG_LOG}"
