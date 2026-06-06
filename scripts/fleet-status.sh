#!/bin/bash
# Fleet-Status Dashboard — Übersicht über alle 4 Trading-Bots
# Usage: ./fleet-status.sh
set -e

DOCKER_HOST=unix:///var/run/docker.sock
PROJECT_ROOT="/home/hermes/projects/trading"
DB_DIRS=(
  "${PROJECT_ROOT}/freqforge/user_data"
  "${PROJECT_ROOT}/freqforge-canary/user_data"
  "${PROJECT_ROOT}/freqtrade/bots/regime-hybrid/user_data"
  "${PROJECT_ROOT}/freqtrade/bots/freqai-rebel/user_data"
)
DB_NAMES=(
  "tradesv3.freqforge.dryrun.sqlite"
  "tradesv3.freqforge_canary.dryrun.sqlite"
  "tradesv3.regime_hybrid.dryrun.sqlite"
  "tradesv3.freqai_rebel.dryrun.sqlite"
)
BOT_LABELS=("FreqForge" "Canary" "Regime-Hybrid" "Rebel")
CONTAINERS=("trading-freqtrade-freqforge-1" "trading-freqtrade-freqforge-canary-1" "trading-freqtrade-regime-hybrid-1" "trading-freqai-rebel-1")

echo "═══════════════════════════════════════════"
echo "  FLEET STATUS DASHBOARD"
echo "  $(date '+%Y-%m-%d %H:%M:%S UTC')"
echo "═══════════════════════════════════════════"
echo ""

# ─── 1. Container-Status ───
echo "─── CONTAINER STATUS ───"
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}' 2>/dev/null | grep -E 'freq|rebel|forge|Freq|Rebel' || echo "  (No matching containers running)"
echo ""

# ─── 2. Letzte Trade-Zeile aus jeder DB ───
echo "─── TRADE DATABASES ───"
for i in "${!BOT_LABELS[@]}"; do
  label="${BOT_LABELS[$i]}"
  container="${CONTAINERS[$i]}"
  db_path="/freqtrade/user_data/${DB_NAMES[$i]}"

  container_status=$(docker inspect -f '{{.State.Status}}' "$container" 2>/dev/null || echo "missing")

  if [ "$container_status" != "running" ]; then
    echo "  ${label}: container not running (${container_status})"
    continue
  fi

  # Total + Closed Trades + PnL
  result=$(docker exec "$container" sqlite3 "$db_path" "
    SELECT
      COALESCE(COUNT(*), 0),
      COALESCE(SUM(CASE WHEN is_open=0 THEN 1 ELSE 0 END), 0),
      COALESCE(SUM(CASE WHEN is_open=1 THEN 1 ELSE 0 END), 0),
      COALESCE(ROUND(SUM(close_profit_abs), 4), 0.0)
    FROM trades;
  " 2>/dev/null || echo "0|0|0|0.0")

  IFS='|' read -r total closed open pnl <<< "$result"

  # Letzter Trade (falls vorhanden)
  last_trade=$(docker exec "$container" sqlite3 "$db_path" "
    SELECT pair, close_profit_abs, close_date
    FROM trades WHERE is_open=0 AND close_date IS NOT NULL
    ORDER BY close_date DESC LIMIT 1;
  " 2>/dev/null || echo "")

  if [ -n "$last_trade" ] && [ "$last_trade" != "|" ]; then
    IFS='|' read -r last_pair last_pnl last_date <<< "$last_trade"
    last_trade_str=" | Last: ${last_pair} $(printf "%.2f" "${last_pnl:-0}") (${last_date})"
  else
    last_trade_str=" | (no closed trades)"
  fi

  printf "  %-15s | Trades: %4s | Closed: %4s | Open: %s | PnL: %+.2f USDT%s\n" \
    "${label}" "${total}" "${closed}" "${open}" "${pnl}" "${last_trade_str}"
done
echo ""

# ─── 3. Disk-Usage ───
echo "─── DISK USAGE ───"
du -sh "${PROJECT_ROOT}/" 2>/dev/null || echo "  (path not accessible)"
echo "  $(df -h / | tail -1 | awk '{print "Root: " $3 " / " $2 " (" $5 " used)"}')"
echo ""

# ─── 4. AI-Hedge-Fund Signal ───
echo "─── AI-HEDGE-FUND SIGNAL ───"
SIGNAL_FILE="${PROJECT_ROOT}/ai-hedge-fund-crypto/output/hermes_signal.json"
if [ -f "$SIGNAL_FILE" ]; then
  echo "  Signal Age: $(python3 -c "
import json, time
d = json.load(open('${SIGNAL_FILE}'))
ts = d.get('timestamp_utc', '')
print(f'timestamp_utc={ts}')
pairs = d.get('pairs', {})
accepted = sum(1 for p in pairs.values() if str(p.get('verdict','')).upper() == 'ACCEPTED')
watch = sum(1 for p in pairs.values() if str(p.get('verdict','')).upper() == 'WATCH_ONLY')
print(f'Pairs: {len(pairs)} | ACCEPTED: {accepted} | WATCH_ONLY: {watch}')
for pair, meta in list(pairs.items())[:3]:
  action = meta.get('action', 'hold')
  conf = meta.get('confidence', 0)
  verdict = meta.get('verdict', '')
  print(f'  {pair}: {action} (conf={conf}, verdict={verdict})')
" 2>/dev/null || echo "  (parse error)")"
else
  echo "  Signal file not found"
fi
echo ""
echo "═══════════════════════════════════════════"
echo "  Dashboard complete"
echo "═══════════════════════════════════════════"
