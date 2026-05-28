#!/usr/bin/env bash
set -euo pipefail
docker run --rm --entrypoint bash -v /home/hermes/projects/trading:/work -w /work/freqtrade freqtradeorg/freqtrade:stable -lc "python3 /work/freqtrade/shared/calculate_correlation_matrix.py --lookback 1000 --threshold 0.80" >> /opt/data/profiles/orchestrator/logs/fleet_correlation.log 2>&1
