#!/bin/bash
set -e

DATA="${BTC5M_DATA:-/data}"
echo "[ENTRYPOINT] BTC 5-Min Bot — data at $DATA"

# Ensure data dirs
mkdir -p "$DATA/logs"

# Start dashboard
echo "[ENTRYPOINT] Starting dashboard on :9090..."
cd /app/dashboard
export PYTHONPATH=/app/dashboard:/app/bot:$DATA
python3 dashboard.py &
DASH_PID=$!

sleep 2
if ! kill -0 $DASH_PID 2>/dev/null; then
    echo "[ENTRYPOINT] FATAL: Dashboard failed to start"
    exit 1
fi

# Start bot — unbuffered output to log file
echo "[ENTRYPOINT] Starting BTC 5-Min bot..."
cd /app/bot
LOG_FILE="$DATA/logs/btc5m-$(date -u +%Y%m%d).log"
python3 -u btc5m_bot.py run >> "$LOG_FILE" 2>&1 &
BOT_PID=$!

echo "[ENTRYPOINT] All processes started. Dashboard=$DASH_PID, Bot=$BOT_PID"
wait
