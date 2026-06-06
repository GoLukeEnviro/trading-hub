#!/bin/bash
set -e

echo "[ENTRYPOINT] Polymarket-Fadi Bot starting..."

# Copy .env into repo
cp /data/.env /app/repo/.env

# Copy .env also into log dir
mkdir -p /data/logs

cd /app/repo

# Install deps if not already done
if [ ! -d "node_modules" ]; then
    echo "[ENTRYPOINT] Installing npm dependencies..."
    npm install 2>&1 | tail -5
fi

# Build dashboard if not already done
if [ ! -d "dashboard/dist" ]; then
    echo "[ENTRYPOINT] Building dashboard..."
    cd dashboard
    npm install 2>&1 | tail -5
    npx vite build 2>&1 | tail -5
    cd /app/repo
fi

echo "[ENTRYPOINT] Starting bot..."
echo "  Mode: $(grep DRY_RUN .env | cut -d= -f2)"
echo "  Capital: $(grep CAPITAL_USD .env | cut -d= -f2)$"

# Start the bot
exec npx tsx bot-with-dashboard.ts 2>&1
