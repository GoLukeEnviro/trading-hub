#!/bin/bash
# Rainbow Producer Manager — canonical lifecycle script
# Usage: rainbow_producer_manager.sh {start|stop|status|restart|health}
#
# Canonical lifecycle manager for the Rainbow producer (uvicorn).
# This is the ONE source of truth for producer process management.
# Use `start` to launch, `stop` to clean up, `status` to check.

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
WORKDIR="/opt/data/ai4trade-bot"
VENV_PYTHON="$WORKDIR/.venv/bin/python3"
PIDFILE="/tmp/rainbow-producer.pid"
LOGFILE="/tmp/rainbow-producer.log"
PORT=8000
HOST="127.0.0.1"

# Color helpers
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

_health_check() {
    curl -sf "http://$HOST:$PORT/health" >/dev/null 2>&1
}

_get_uvicorn_pids() {
    # Find all uvicorn rainbow processes (not the manager itself)
    pgrep -f "uvicorn.*rainbow.main:create_app" 2>/dev/null | grep -v "^$$\$" || true
}

_get_pid() {
    # Try PID file first
    if [ -f "$PIDFILE" ]; then
        local pid
        pid=$(head -1 "$PIDFILE" 2>/dev/null | tr -d ' \n')
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            echo "$pid"
            return 0
        fi
        # Stale PID file
        rm -f "$PIDFILE"
    fi
    # Fallback: find uvicorn process
    _get_uvicorn_pids | head -1 || true
}

start() {
    local existing
    existing=$(_get_uvicorn_pids)
    if [ -n "$existing" ]; then
        local count
        count=$(echo "$existing" | wc -l)
        if [ "$count" -gt 1 ]; then
            warn "Found $count uvicorn processes — duplicate! Cleaning up..."
            echo "$existing" | xargs kill 2>/dev/null || true
            sleep 1
        elif _health_check; then
            info "Producer already running (PID $(echo "$existing" | head -1))"
            local pid
            pid=$(echo "$existing" | head -1)
            echo "$pid" > "$PIDFILE"
            return 0
        fi
    fi

    info "Starting Rainbow producer..."
    cd "$WORKDIR"

    # Use setsid to create a clean process group for reliable kill
    setsid "$VENV_PYTHON" -m uvicorn rainbow.main:create_app \
        --host "$HOST" --port "$PORT" \
        --factory --log-level info \
        >> "$LOGFILE" 2>&1 &
    local pid=$!
    echo "$pid" > "$PIDFILE"

    # Wait for health
    local attempt=0
    while [ $attempt -lt 15 ]; do
        sleep 1
        if _health_check; then
            info "Producer started (PID $pid, process group) — health check passed"
            return 0
        fi
        attempt=$((attempt + 1))
    done

    error "Health check failed after 15s — check log: $LOGFILE"
    return 1
}

stop() {
    local pid
    pid=$(_get_pid)
    if [ -z "$pid" ]; then
        warn "No producer process found"
        rm -f "$PIDFILE"
        return 0
    fi

    info "Stopping producer (PID $pid, process group)..."
    # Kill the entire process group (negative PID = PGID when using setsid)
    # The PGID equals the PID since setsid creates a new session
    local pgid
    pgid=$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ' || echo "$pid")
    if [ -n "$pgid" ] && [ "$pgid" != "0" ]; then
        # Kill process group
        kill -- "-$pgid" 2>/dev/null || kill "$pid" 2>/dev/null || true
    else
        kill "$pid" 2>/dev/null || true
    fi

    local wait=0
    while kill -0 "$pid" 2>/dev/null && [ $wait -lt 10 ]; do
        sleep 1
        wait=$((wait + 1))
    done
    if kill -0 "$pid" 2>/dev/null; then
        local pgid
        pgid=$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ' || echo "")
        if [ -n "$pgid" ] && [ "$pgid" != "0" ]; then
            kill -9 -- "-$pgid" 2>/dev/null || true
        fi
        kill -9 "$pid" 2>/dev/null || true
        info "Force killed PID $pid"
    fi
    rm -f "$PIDFILE"

    # Verify port is free
    sleep 1
    if _health_check 2>/dev/null; then
        error "Port $PORT still in use after stop — something else is listening"
        return 1
    fi
    info "Producer stopped. Port $PORT free."
}

status() {
    local pid
    pid=$(_get_pid)
    if [ -n "$pid" ]; then
        if _health_check; then
            local uptime
            uptime=$(ps -o etime= -p "$pid" 2>/dev/null | tr -d ' ' || echo "?")
            echo -e "${GREEN}RUNNING${NC} (PID $pid, uptime $uptime) — http://$HOST:$PORT/health"
            return 0
        else
            echo -e "${YELLOW}STALE${NC} (PID $pid) — process exists but /health unreachable"
            return 1
        fi
    else
        echo -e "${RED}STOPPED${NC}"
        return 1
    fi
}

restart() {
    info "Restarting producer..."
    stop || true
    sleep 2
    start
}

health() {
    if _health_check; then
        curl -s "http://$HOST:$PORT/health" 2>/dev/null || echo '{"status":"error"}'
        return 0
    else
        echo '{"status":"unreachable"}'
        return 1
    fi
}

case "${1:-}" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    status)
        status
        ;;
    restart)
        restart
        ;;
    health)
        health
        ;;
    *)
        echo "Usage: $SCRIPT_NAME {start|stop|status|restart|health}"
        echo ""
        echo "Canonical lifecycle manager for Rainbow producer (uvicorn)."
        echo "Log: $LOGFILE | PID: $PIDFILE | Port: $HOST:$PORT"
        exit 1
        ;;
esac
