#!/bin/bash
# Rainbow Producer Manager — start/stop/status/restart
# Usage: rainbow_producer_manager.sh {start|stop|status|restart}
#
# Manages the Rainbow producer (uvicorn) for SI v2 scoring eligibility.
# Designed for container environments without systemd.

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
WORKDIR="/opt/data/ai4trade-bot"
VENV_PYTHON="$WORKDIR/.venv/bin/python3"
UVICORN="$WORKDIR/.venv/bin/uvicorn"
PIDFILE="/tmp/rainbow-producer.pid"
LOGFILE="/opt/data/ai4trade-bot/logs/rainbow-producer/current"
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

_get_pid() {
    # Try PID file first
    if [ -f "$PIDFILE" ]; then
        local pid
        pid=$(head -1 "$PIDFILE" 2>/dev/null | tr -d ' \n')
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            echo "$pid"
            return 0
        fi
    fi
    # Fallback: pgrep — take the first (parent) PID
    pgrep -f "uvicorn.*rainbow.main:create_app" 2>/dev/null | head -1 || true
}

start() {
    local existing
    existing=$(_get_pid)
    if [ -n "$existing" ]; then
        warn "Producer already running (PID $existing)"
        if _health_check; then
            info "Health check passed — already serving on $HOST:$PORT"
            return 0
        else
            warn "Process exists but health check failed — restarting"
            stop
        fi
    fi

    mkdir -p "$(dirname "$LOGFILE")"
    info "Starting Rainbow producer..."
    cd "$WORKDIR"
    exec "$VENV_PYTHON" -m uvicorn rainbow.main:create_app \
        --host "$HOST" --port "$PORT" \
        --factory --log-level info \
        >> "$LOGFILE" 2>&1 &
    local pid=$!
    echo "$pid" > "$PIDFILE"

    # Wait for health
    local attempt=0
    while [ $attempt -lt 10 ]; do
        sleep 1
        if _health_check; then
            info "Producer started (PID $pid) — health check passed"
            return 0
        fi
        attempt=$((attempt + 1))
    done

    error "Health check failed after 10s — check logs at $LOGFILE"
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

    info "Stopping producer (PID $pid)..."
    kill "$pid" 2>/dev/null || true
    local wait=0
    while kill -0 "$pid" 2>/dev/null && [ $wait -lt 10 ]; do
        sleep 1
        wait=$((wait + 1))
    done
    if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null || true
        info "Force killed PID $pid"
    fi
    rm -f "$PIDFILE"
    info "Producer stopped"
}

status() {
    local pid
    pid=$(_get_pid)
    if [ -n "$pid" ]; then
        if _health_check; then
            echo -e "${GREEN}RUNNING${NC} (PID $pid) — serving on http://$HOST:$PORT"
            return 0
        else
            echo -e "${YELLOW}STALE${NC} (PID $pid) — process exists but health endpoint unreachable"
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
    sleep 1
    start
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
    *)
        echo "Usage: $SCRIPT_NAME {start|stop|status|restart}"
        echo ""
        echo "Manages the Rainbow producer (uvicorn) for SI v2 scoring."
        echo "Logs: $LOGFILE"
        exit 1
        ;;
esac
