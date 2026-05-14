#!/usr/bin/env bash
set -euo pipefail

IMAGE="freqtradeorg/freqtrade:2026.3_freqai"
VOLUME="freqai-rebel-data"
SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[sync] Source: ${SRC_ROOT}"
echo "[sync] Volume: ${VOLUME}"

docker volume inspect "${VOLUME}" >/dev/null

docker run --rm \
  -v "${VOLUME}:/data" \
  -v "${SRC_ROOT}/user_data/config.json:/src/config.json:ro" \
  -v "${SRC_ROOT}/user_data/strategies/RebelLiquidation.py:/src/RebelLiquidation.py:ro" \
  --entrypoint bash \
  --user root \
  "${IMAGE}" \
  -c '
    set -euo pipefail
    mkdir -p /data/strategies /data/models /data/data /data/logs /data/backtest_results
    cp /src/config.json /data/config.json
    cp /src/RebelLiquidation.py /data/strategies/RebelLiquidation.py
    touch /data/strategies/__init__.py
    python3 -m json.tool /data/config.json >/dev/null
    python3 -m py_compile /data/strategies/RebelLiquidation.py
    chown -R 1000:1000 /data
    echo "[sync] Volume config and strategy updated successfully."
  '
