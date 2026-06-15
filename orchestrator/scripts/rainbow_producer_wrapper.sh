#!/usr/bin/env bash
# Rainbow Producer Wrapper — durable process launcher
# Provides restart-on-fail lifecycle management for the Rainbow FastAPI producer.
#
# Usage:
#   ./rainbow_producer_wrapper.sh start   # Start in background (daemon)
#   ./rainbow_producer_wrapper.sh stop    # Stop gracefully
#   ./rainbow_producer_wrapper.sh status  # Check if running
#   ./rainbow_producer_wrapper.sh restart # Restart
#
# Add to @reboot cron:
#   crontab -e
#   @reboot /home/hermes/projects/trading/orchestrator/scripts/rainbow_producer_wrapper.sh start

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PRODUCER_DIR="/opt/data/ai4trade-bot"
VENV_PYTHON="$PRODUCER_DIR/.venv/bin/python3"
PIDFILE="/tmp/rainbow-producer.pid"
LOGFILE="/tmp/rainbow-producer.log"
CONFIG_FILE="$PRODUCER_DIR/rainbow/config.yaml"
HOST="127.0.0.1"
PORT="8000"

# Source env for SI v2 config
export SI_V2_RAINBOW_ENABLED=true
export SI_V2_RAINBOW_MODE=read_only
export SI_V2_RAINBOW_BASE_URL="http://127.0.0.1:8000"

start() {
    if [ -f "$PIDFILE" ]; then
        local pid
        pid=$(cat "$PIDFILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo "Rainbow producer already running (PID $pid)"
            return 0
        fi
        echo "Stale PID file found, removing"
        rm -f "$PIDFILE"
    fi

    echo "Starting Rainbow producer..."
    echo "  Working dir: $PRODUCER_DIR"
    echo "  Python:      $VENV_PYTHON"
    echo "  Config:      $CONFIG_FILE"
    echo "  Listening:   http://$HOST:$PORT"
    echo "  Log:         $LOGFILE"

    # uvicorn wrapper with restart loop
    nohup bash -c "
        while true; do
            echo \"[rainbow-producer] Starting uvicorn at \$(date -u '+%Y-%m-%dT%H:%M:%SZ')\" >> \"$LOGFILE\"
            cd \"$PRODUCER_DIR\"
            \"$VENV_PYTHON\" -m uvicorn rainbow.main:create_app \
                --host \"$HOST\" --port \"$PORT\" --factory \
                --log-level warning \
                >> \"$LOGFILE\" 2>&1
            EXIT_CODE=\$?
            echo \"[rainbow-producer] uvicorn exited with code \$EXIT_CODE at \$(date -u '+%Y-%m-%dT%H:%M:%SZ')\" >> \"$LOGFILE\"
            sleep 2
        done
    " > /dev/null 2>&1 &

    local bg_pid=$!
    echo "$bg_pid" > "$PIDFILE"
    echo "Started (PID $bg_pid)"
}

stop() {
    if [ ! -f "$PIDFILE" ]; then
        echo "Not running (no PID file)"
        return 0
    fi

    local pid
    pid=$(cat "$PIDFILE")
    echo "Stopping Rainbow producer (PID $pid)..."
    kill "$pid" 2>/dev/null || true

    # Wait for graceful shutdown
    for i in $(seq 1 10); do
        if ! kill -0 "$pid" 2>/dev/null; then
            echo "Stopped"
            rm -f "$PIDFILE"
            return 0
        fi
        sleep 1
    done

    # Force kill after 10s timeout
    echo "Timeout, force killing..."
    kill -9 "$pid" 2>/dev/null || true
    rm -f "$PIDFILE"
    echo "Force killed"
}

status() {
    if [ ! -f "$PIDFILE" ]; then
        echo "Rainbow producer: STOPPED (no PID file)"
        return 1
    fi
    local pid
    pid=$(cat "$PIDFILE")
    if ! kill -0 "$pid" 2>/dev/null; then
        echo "Rainbow producer: STOPPED (stale PID $pid)"
        rm -f "$PIDFILE"
        return 1
    fi
    local uptime
    uptime=$(ps -o etime= -p "$pid" 2>/dev/null | tr -d ' ' || echo "?")
    echo "Rainbow producer: RUNNING (PID $pid, uptime $uptime)"
    echo "  http://$HOST:$PORT/health"
    return 0
}

case "${1:-status}" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        stop
        sleep 1
        start
        ;;
    status)
        status
        ;;
    *)
        echo "Usage: $0 {start|stop|status|restart}"
        exit 1
        ;;
esac
