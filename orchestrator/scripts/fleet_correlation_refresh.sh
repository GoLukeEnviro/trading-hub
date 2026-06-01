#!/usr/bin/env bash
set -uo pipefail

LOG="/opt/data/profiles/orchestrator/logs/fleet_correlation.log"
mkdir -p "$(dirname "$LOG")"

# Check if Docker is available
if ! command -v docker &>/dev/null || ! docker info &>/dev/null; then
    echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] SKIP: Docker daemon not available" >> "$LOG"
    echo "SKIP: Docker not available"
    exit 0
fi

docker run --rm --entrypoint bash -v /home/hermes/projects/trading:/work -w /work/freqtrade freqtradeorg/freqtrade:stable -lc "python3 /work/freqtrade/shared/calculate_correlation_matrix.py --lookback 1000 --threshold 0.80" >> "$LOG" 2>&1
