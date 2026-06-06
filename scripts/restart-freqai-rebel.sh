#!/bin/bash
# Restart FreqAI-Rebel via direktem Docker-Socket (kein docker compose CLI)
set -e

DOCKER_HOST=unix:///var/run/docker.sock
COMPOSE_DIR="/home/hermes/projects/trading"

echo "=== FreqAI-Rebel Restart ==="
echo "[1/5] Stopping old container..."
docker stop freqai-rebel 2>/dev/null || true

echo "[2/5] Removing old container..."
docker rm freqai-rebel 2>/dev/null || true

echo "[3/5] Building custom image (freqtrade-freqai-rebel:custom)..."
docker build -t freqtrade-freqai-rebel:custom \
  -f "${COMPOSE_DIR}/freqtrade/Dockerfile.freqai-rebel" \
  "${COMPOSE_DIR}/freqtrade"

echo "[4/5] Starting new container..."
docker run -d \
  --name freqai-rebel \
  --network trading_hermes-net \
  --restart unless-stopped \
  -p 127.0.0.1:8087:8080 \
  -v "${COMPOSE_DIR}/freqtrade/bots/freqai-rebel/user_data:/freqtrade/user_data" \
  -v "${COMPOSE_DIR}/freqtrade/shared:/freqtrade/shared" \
  -v "${COMPOSE_DIR}/freqtrade/shared/primo_signal_state.json:/freqtrade/user_data/primo_signal_state.json:ro" \
  freqtrade-freqai-rebel:custom \
  trade --config /freqtrade/user_data/config.json --strategy RebelLiquidation

echo "[5/5] Waiting for container health..."
sleep 3
docker ps --filter name=freqai-rebel --format "Status: {{.Status}} | Ports: {{.Ports}}"

echo "=== FreqAI-Rebel restarted successfully ==="
