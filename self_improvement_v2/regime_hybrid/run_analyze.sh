#!/usr/bin/env bash
# Regime-Hybrid Analyze — SI v2
# Runs the performance analysis pipeline for the regime_hybrid bot.
# Triggered every 30 min by si_regime_hybrid_analyze.sh via Hermes cron.
set -euo pipefail

BOT_ID="regime_hybrid"
BOT_NAME="Regime Hybrid"
CONTAINER="trading-freqtrade-regime-hybrid-1"
SI_V2_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$SI_V2_DIR"

echo "[${BOT_ID}] SI v2 analyze run at $(date -u +%FT%TZ)"

# Phase 1: Fetch latest trades from container via REST API
TRADES_JSON=$(docker exec "$CONTAINER" python3 -c "
import json, urllib.request
try:
    req = urllib.request.Request('http://localhost:8080/api/v1/trades?limit=100')
    req.add_header('accept', 'application/json')
    resp = urllib.request.urlopen(req, timeout=10)
    data = json.loads(resp.read())
    trades = data.get('trades', data) if isinstance(data, dict) else data
    print(json.dumps([{
        'profit_pct': t.get('profit_ratio', 0) * 100,
        'profit_abs': t.get('profit_abs', 0),
        'close_date': t.get('close_date', '')
    } for t in (trades if isinstance(trades, list) else [])]))
except Exception as e:
    print(json.dumps({'error': str(e)}))
" 2>/dev/null) || TRADES_JSON='[]'

# Phase 2: Run performance analysis
if echo "$TRADES_JSON" | python3 -c "import json,sys; d=json.load(sys.stdin); exit(0 if isinstance(d,list) else 1)" 2>/dev/null; then
    echo "$TRADES_JSON" | python3 -c "
import json, sys
from si_v2.analyze.performance_analyzer import PerformanceAnalyzer

trades = json.load(sys.stdin)
analyzer = PerformanceAnalyzer()
result = analyzer.analyze(trades=trades, bot_id='${BOT_ID}', bot_name='${BOT_NAME}')
print(result.model_dump_json(indent=2))
"
    echo "[${BOT_ID}] Analysis complete"
else
    echo "[${BOT_ID}] WARNING: No trade data available (container unreachable or empty)"
fi

exit 0
