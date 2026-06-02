#!/usr/bin/env bash
set -uo pipefail

LOG="/opt/data/profiles/orchestrator/logs/fleet_correlation.log"
TARGET="/home/hermes/projects/trading/freqtrade/shared/fleet_correlation_matrix.json"
TMPFILE="/tmp/fleet_correlation_matrix.json.tmp"
mkdir -p "$(dirname "$LOG")"

# Check if Docker is available
if ! command -v docker &>/dev/null || ! docker info &>/dev/null; then
    echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] SKIP: Docker daemon not available" >> "$LOG"
    echo "SKIP: Docker not available"
    exit 0
fi

# Use freqtrade-hermes10000:stable (has pandas+pyarrow baked in).
# Container writes JSON to stdout, status/diagnostics to stderr.
# Wrapper writes to TMPFILE, validates JSON, then atomically moves to TARGET.
docker run --rm --entrypoint bash \
    -v /home/hermes/projects/trading:/work \
    -w /work/freqtrade \
    freqtrade-hermes10000:stable \
    -lc "python3 /work/freqtrade/shared/calculate_correlation_matrix.py --lookback 1000 --threshold 0.80" \
    > "$TMPFILE" 2>>"$LOG"
EXIT=$?

if [ $EXIT -ne 0 ]; then
    echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] FAIL: docker exit code $EXIT" >> "$LOG"
    rm -f "$TMPFILE"
    exit $EXIT
fi

# Validate JSON integrity before replacing target
if ! python3 -c "import json; json.load(open('$TMPFILE'))" 2>/dev/null; then
    echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] FAIL: output is not valid JSON" >> "$LOG"
    rm -f "$TMPFILE"
    exit 1
fi

# Atomic move: overwrite target with validated output
mv -f "$TMPFILE" "$TARGET"

PAIRS=$(python3 -c "import json; d=json.load(open('$TARGET')); print(f'pairs={d[\"pair_count\"]}, high_corr={len(d[\"high_corr_pairs\"])}, clusters={len(d[\"clusters\"])}')")
echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] OK: fleet correlation matrix refreshed ($PAIRS)" >> "$LOG"
echo "OK: fleet correlation matrix refreshed ($PAIRS)"
exit 0
