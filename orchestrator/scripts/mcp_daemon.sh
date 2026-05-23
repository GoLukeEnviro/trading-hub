#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# MCP Bitget Paper Server — Daemon Wrapper v2
# Läuft in Endlos-Schleife mit nohup
# Wird von cron angestoßen, hält sich selbst am Leben
# ═══════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MCP_SCRIPT="${SCRIPT_DIR}/bitget_mcp_server.py"
PID_FILE="${SCRIPT_DIR}/.mcp_daemon.pid"
LOG_DIR="/home/hermes/projects/trading/orchestrator/logs/mcp"
LOG_FILE="${LOG_DIR}/mcp_daemon.log"
WATCHDOG_LOG="${LOG_DIR}/mcp_watchdog.log"

mkdir -p "${LOG_DIR}"

case "${1:-restart}" in
    start|ensure)
        # Kill duplicates first
        COUNT=$(ps aux | grep bitget_mcp_server.py | grep -v grep | wc -l)
        if [ "${COUNT}" -gt 0 ]; then
            # Check if at least one is alive
            ALIVE=$(ps aux | grep bitget_mcp_server.py | grep -v grep | awk '{print $2}' | head -1)
            kill $(ps aux | grep bitget_mcp_server.py | grep -v grep | awk '{print $2}' | tail -n +2) 2>/dev/null || true
            if [ -n "${ALIVE}" ] && kill -0 "${ALIVE}" 2>/dev/null; then
                echo "${ALIVE}" > "${PID_FILE}" 2>/dev/null || true
                echo "MCP daemon already running (PID: ${ALIVE})"
                exit 0
            fi
        fi

        # Start fresh
        rm -f "${PID_FILE}"
        export PAPER_LOG_DIR="${LOG_DIR}"
        export PYTHONUNBUFFERED=1

        # Wrap in while-loop so it auto-restarts on crash
        nohup bash -c '
            export PAPER_LOG_DIR="'"${LOG_DIR}"'"
            export PYTHONUNBUFFERED=1
            while true; do
                echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") | LOOP | restarting MCP server" >> "'"${WATCHDOG_LOG}"'"
                /opt/hermes/.venv/bin/python3 "'${MCP_SCRIPT}'" 2>&1
                EXIT_CODE=$?
                echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") | EXIT | code=${EXIT_CODE}, restarting in 2s" >> "'"${WATCHDOG_LOG}"'"
                sleep 2
            done
        ' >> "${LOG_FILE}" 2>&1 &
        PID=$!
        echo ${PID} > "${PID_FILE}"
        echo "MCP daemon started (PID: ${PID})"
        echo "$(date -u +'%Y-%m-%dT%H:%M:%SZ') | START | wrapper PID=${PID}" >> "${WATCHDOG_LOG}"
        ;;

    stop)
        pkill -f "bitget_mcp_server.py" 2>/dev/null || true
        pkill -f "mcp_daemon_wrapper" 2>/dev/null || true
        rm -f "${PID_FILE}" 2>/dev/null || true
        echo "MCP daemon stopped"
        echo "$(date -u +'%Y-%m-%dT%H:%M:%SZ') | STOP" >> "${WATCHDOG_LOG}"
        ;;

    status)
        WRAPPER_PID=""
        [ -f "${PID_FILE}" ] && WRAPPER_PID=$(cat "${PID_FILE}")
        
        MCP_PIDS=$(ps aux | grep bitget_mcp_server.py | grep -v grep | awk '{print $2}')
        MCP_COUNT=$(echo "${MCP_PIDS}" | wc -l)
        
        if [ -n "${MCP_PIDS}" ]; then
            echo "MCP daemon: RUNNING (${MCP_COUNT} process(es))"
            echo "PIDs: ${MCP_PIDS}"
            if [ -n "${WRAPPER_PID}" ]; then
                echo "Wrapper PID: ${WRAPPER_PID}"
                ps -p "${WRAPPER_PID}" -o etime,rss --no-headers 2>/dev/null || echo "Wrapper not running (stale PID file)"
            fi
        else
            echo "MCP daemon: STOPPED"
        fi
        ;;

    log)
        tail -n "${2:-50}" "${LOG_FILE}"
        ;;

    watch-log)
        tail -n "${2:-50}" "${WATCHDOG_LOG}"
        ;;

    *)
        echo "Usage: $0 {start|stop|status|log|watch-log}"
        exit 1
        ;;
esac
