# Flotten-Gesundheitsbericht (Fleet Health Report) — Template

> **RSIP v3 — Finale Vorlage** | Generiert: `{{REPORT_TIMESTAMP}}` | Zyklus: `{{CRON_CYCLE}}`

---

## 1. Zusammenfassung (Executive Summary)

| Kennzahl | Wert | Schwelle | Urteil |
|----------|------|----------|--------|
| Fleet-Gesamturteil | `{{FLEET_VERDICT}}` | — | `{{FLEET_VERDICT_EMOJI}}` |
| Aktive Bot-Container | `{{ACTIVE_BOTS}}`/`{{TOTAL_BOTS}}` | ≥4 PASS | `{{ACTIVE_VERDICT}}` |
| Gesamter PnL (Dry-Run) | `{{TOTAL_PNL}}` USDT | ≥0 PASS | `{{PNL_VERDICT}}` |
| Offene Positionen | `{{OPEN_TRADES}}` | ≤6 PASS | `{{OPEN_VERDICT}}` |
| Signal-Frische | `{{SIGNAL_AGE_MIN}}` min | ≤45 PASS | `{{SIGNAL_VERDICT}}` |
| Quartz-Bots (WR=100%) | `{{QUARANTINE_COUNT}}` | 0 PASS | `{{QUARANTINE_VERDICT}}` |
| Heartbeat-Cron aktiv | `{{HEARTBEAT_CRON}}` | Ja PASS | `{{HEARTBEAT_VERDICT}}` |

### Urteil-Skala

| Symbol | Bedeutung | Kriterium |
|--------|----------|-----------|
| 🟢 PASS | Nominal | Alle Schwellen innerhalbNormalbereich |
| 🟡 WARN | Beobachtung | 1-2 Schwellen verletzt, kein Kapitalrisiko |
| 🔴 FAIL | Eingriff nötig | Kritische Schwelle verletzt ODER Kapitalrisiko |

---

## 2. Bot-Statustabelle (Bot Status Matrix)

| Bot | Container | Port | Modus | Uptime | Trades | WR% | PnL (USDT) | Offene Pos. | Signal-Gate | Urteil |
|-----|-----------|------|-------|--------|--------|-----|------------|-------------|-------------|--------|
| FreqForge | freqtrade-freqforge | 8086 | spot | `{{FF_UPTIME}}` | `{{FF_TRADES}}` | `{{FF_WR}}` | `{{FF_PNL}}` | `{{FF_OPEN}}` | — | `{{FF_VERDICT}}` |
| Regime-Hybrid | freqtrade-regime-hybrid | 8085 | futures | `{{RH_UPTIME}}` | `{{RH_TRADES}}` | `{{RH_WR}}` | `{{RH_PNL}}` | `{{RH_OPEN}}` | `{{RH_SIGNAL}}` | `{{RH_VERDICT}}` |
| Momentum | freqtrade-momentum | 8084 | futures | `{{MO_UPTIME}}` | `{{MO_TRADES}}` | `{{MO_WR}}` | `{{MO_PNL}}` | `{{MO_OPEN}}` | `{{MO_SIGNAL}}` | `{{MO_VERDICT}}` |
| RSI | freqtrade-rsi | 8081 | futures | `{{RS_UPTIME}}` | `{{RS_TRADES}}` | `{{RS_WR}}` | `{{RS_PNL}}` | `{{RS_OPEN}}` | `{{RS_SIGNAL}}` | `{{RS_VERDICT}}` |
| FreqAI-rebel | freqai-rebel | 8087 | futures | `{{RB_UPTIME}}` | `{{RB_TRADES}}` | `{{RB_WR}}` | `{{RB_PNL}}` | `{{RB_OPEN}}` | — | `{{RB_VERDICT}}` |

### Schwellen pro Bot

| Metrik | PASS | WARN | FAIL |
|--------|------|------|------|
| Win Rate (≥10 trades) | ≥60% | 40-59% | <40% |
| PnL (overall) | ≥0 | -3 bis 0 | <-3 USDT |
| Uptime | ≥24h | 12-24h | <12h |
| Offene Positionen | 1-3 | 4-5 | ≥6 |
| Trades letzte 24h | ≥1 | 0 (mit Signal) | 0 (kein Grund) |
| Signal-Gate | allow entries | partial block | total block |

---

## 3. Bot-Tiefenanalyse (Per-Bot Deep Dive)

### 3.1 FreqForge — `{{FF_VERDICT_EMOJI}}`

| Detail | Wert |
|--------|------|
| Strategie | FreqForge_Override |
| Modus | Spot (kein Leverage-Risiko) |
| Letzte 5 Trades | `{{FF_LAST5}}` |
| Avg Win | `{{FF_AVG_WIN}}` USDT |
| Avg Loss | `{{FF_AVG_LOSS}}` USDT |
| Max Drawdown | `{{FF_MAX_DD}}` |
| Bemerkung | Goldstandard-Referenzbot |

### 3.2 Regime-Hybrid — `{{RH_VERDICT_EMOJI}}`

| Detail | Wert |
|--------|------|
| Strategie | RegimeSwitchingHybrid_v7_v04_Integration |
| Avg Win / Avg Loss | +0.28 / -1.74 USDT |
| RRR (Realisiert) | `{{RH_RRR}}` |
| Stop-Loss-Events | `{{RH_SL_COUNT}}` |
| Gewinnfaktor | `{{RH_PROFIT_FACTOR}}` |
| Bemerkung | Hohe WR aber SL frisst alle Gewinne. RRR < 0.2 kritisch. |

### 3.3 Momentum — `{{MO_VERDICT_EMOJI}}`

| Detail | Wert |
|--------|------|
| Strategie | MomentumBG15_v1 |
| Blockierter Grund | primo_gate: allow_long_bias=false |
| Blockierte Paare | `{{MO_BLOCKED_PAIRS}}` |
| Letzter Trade | `{{MO_LAST_TRADE_TS}}` |
| Bemerkung | Signal-Layer-Problem, kein Strategie-Problem. |

### 3.4 RSI — `{{RS_VERDICT_EMOJI}}`

| Detail | Wert |
|--------|------|
| Strategie | SimpleRSIOnly_v1 |
| Status | **QUARANTINED** |
| Letzter Trade | `{{RS_LAST_TRADE_TS}}` |
| Bemerkung | Strategie tot. 0% WR über 3 Trades. Ersatz ausstehend. |

### 3.5 FreqAI-rebel — `{{RB_VERDICT_EMOJI}}`

| Detail | Wert |
|--------|------|
| Strategie | XGBoost (FreqAI) |
| Label-Schwelle | 0.2% (zu streng) |
| DI_threshold | 0.9 (unerreichbar, max DI=0.73) |
| Modell-Ausgabe | 93% "down" |
| Trades jemals | 0 |
| Bemerkung | Hyperparameter-Tuning nötig. Modell nicht handlungsfähig. |

---

## 4. Signalstapel (Signal Stack)

### 4.1 ai-hedge-fund-crypto (Port 8410)

| Prüfung | Wert | Schwelle | Urteil |
|---------|------|----------|--------|
| Container läuft | `{{AIHFC_RUNNING}}` | true | `{{AIHFC_RUN_V}}` |
| /health Status | `{{AIHFC_HEALTH}}` | 200 | `{{AIHFC_HEALTH_V}}` |
| Signal-Alter | `{{AIHFC_AGE}}` min | ≤45 min | `{{AIHFC_AGE_V}}` |
| Paare im Signal | `{{AIHFC_PAIRS}}` | ≥5 | `{{AIHFC_PAIRS_V}}` |
| Heartbeat-Cron | `{{AIHFC_CRON}}` | aktiv | `{{AIHFC_CRON_V}}` |
| Letzter Trigger | `{{AIHFC_LAST_TRIGGER}}` | — | — |
| Heartbeat-Skript | `orchestrator/scripts/ai_hedge_signal_heartbeat.sh` | — | — |
| Cron Job ID | `1bdc595f408e` | — | — |

### 4.2 Primo-Signalzustand (Primo Signal State)

| Paar | Aktion | allow_long_bias | allow_short_bias | Alter (min) | Urteil |
|------|--------|-----------------|------------------|-------------|--------|
| `{{PAIR_1}}` | `{{PAIR_1_ACTION}}` | `{{PAIR_1_LONG}}` | `{{PAIR_1_SHORT}}` | `{{PAIR_1_AGE}}` | `{{PAIR_1_V}}` |
| `{{PAIR_2}}` | `{{PAIR_2_ACTION}}` | `{{PAIR_2_LONG}}` | `{{PAIR_2_SHORT}}` | `{{PAIR_2_AGE}}` | `{{PAIR_2_V}}` |
| ... | ... | ... | ... | ... | ... |

**Bewertung:** Signal-Alter >120min = 🟡 WARN. Alle HOLD mit false/false = 🔴 FAIL (Blockade).

---

## 5. Kritische Befunde (Critical Findings)

Nr. | Fund | Schwere | Bot | Beschreibung
----|------|---------|-----|-------------
`{{CF_1_ID}}` | `{{CF_1_TITLE}}` | `{{CF_1_SEVERITY}}` | `{{CF_1_BOT}}` | `{{CF_1_DESC}}`
`{{CF_2_ID}}` | `{{CF_2_TITLE}}` | `{{CF_2_SEVERITY}}` | `{{CF_2_BOT}}` | `{{CF_2_DESC}}`
...

### Aktuelle bekannte Befunde (Referenzdaten)

| # | Fund | Schwere | Bot |
|---|------|---------|-----|
| CF-001 | Signal-Blockade | 🔴 KRITISCH | Momentum |
| CF-002 | Strategie tot | 🔴 KRITISCH | RSI |
| CF-003 | Modell unkalibriert | 🟡 WARN | FreqAI-rebel |
| CF-004 | SL frisst Profit | 🟡 WARN | Regime-Hybrid |
| CF-005 | Signal-Alter >30h (behoben via Cron) | 🟢 GELÖST | ai-hedge-fund-crypto |

---

## 6. Maßnahmen (Action Items)

| # | Aktion | Priorität | Zuständig | Status | Frist |
|---|--------|-----------|-----------|--------|-------|
| AI-001 | Signal-Gate-Logik prüfen: allow_long_bias=false für alle Paare | P1 | Operator | `{{AI_001_STATUS}}` | Sofort |
| AI-002 | RSI-Bot dekommissionieren oder Strategie ersetzen | P1 | Operator | `{{AI_002_STATUS}}` | 24h |
| AI-003 | FreqAI-rebel Hyperparameter: Label auf 0.05%, DI_threshold auf 0.5 | P2 | Quant | `{{AI_003_STATUS}}` | 48h |
| AI-004 | Regime-Hybrid SL-Schwelle prüfen (avg loss 6.2x avg win) | P2 | Quant | `{{AI_004_STATUS}}` | 48h |
| AI-005 | Heartbeat-Cron auf 30min bestätigen (Job: 1bdc595f408e) | P1 | Operator | `{{AI_005_STATUS}}` | Erledigt |
| AI-006 | Nächster Flottenbericht (automatisch via Cron) | P3 | Hermes | `{{AI_006_STATUS}}` | `{{NEXT_REPORT_TS}}` |

---

## 7. Shell-Befehle zur Datenerhebung (Copy-Paste Executable)

> Alle Befehle sind idempotent, nur-lesend, ohne Seiteneffekte.

### 7.1 Container-Status

```bash
# Alle Bot-Container prüfen
echo "=== CONTAINER STATUS ==="
for c in freqtrade-freqforge freqtrade-regime-hybrid freqtrade-momentum freqtrade-rsi freqai-rebel ai-hedge-fund-crypto; do
  STATUS=$(docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null || echo "NOT_FOUND")
  UPTIME=$(docker inspect -f '{{.State.StartedAt}}' "$c" 2>/dev/null || echo "N/A")
  printf "%-30s running=%-8s since=%s\n" "$c" "$STATUS" "$UPTIME"
done
```

### 7.2 Bot-Trade-Statistiken (SQLite)

```bash
# FreqForge
echo "=== FREQFORGE ==="
docker exec freqtrade-freqforge sqlite3 /freqtrade/user_data/tradesv3.freqforge.dryrun.sqlite \
  "SELECT count(*) as total,
          sum(case when close_profit>0 then 1 else 0 end) as wins,
          round(sum(close_profit_abs),2) as pnl,
          round(avg(case when close_profit>0 then close_profit_abs end),4) as avg_win,
          round(avg(case when close_profit<0 then close_profit_abs end),4) as avg_loss
   FROM trades WHERE is_open=0;"

# Regime-Hybrid
echo "=== REGIME-HYBRID ==="
docker exec freqtrade-regime-hybrid sqlite3 /freqtrade/user_data/tradesv3.regime_hybrid.dryrun.sqlite \
  "SELECT count(*) as total,
          sum(case when close_profit>0 then 1 else 0 end) as wins,
          round(sum(close_profit_abs),2) as pnl,
          round(avg(case when close_profit>0 then close_profit_abs end),4) as avg_win,
          round(avg(case when close_profit<0 then close_profit_abs end),4) as avg_loss
   FROM trades WHERE is_open=0;"

# Momentum
echo "=== MOMENTUM ==="
docker exec freqtrade-momentum sqlite3 /freqtrade/user_data/tradesv3.momentum.dryrun.sqlite \
  "SELECT count(*) as total,
          sum(case when close_profit>0 then 1 else 0 end) as wins,
          round(sum(close_profit_abs),2) as pnl
   FROM trades WHERE is_open=0;"

# RSI
echo "=== RSI ==="
docker exec freqtrade-rsi sqlite3 /freqtrade/tradesv3.dryrun.sqlite \
  "SELECT count(*) as total,
          sum(case when close_profit>0 then 1 else 0 end) as wins,
          round(sum(close_profit_abs),2) as pnl
   FROM trades WHERE is_open=0;"

# FreqAI-rebel
echo "=== FREQAI-REBEL ==="
docker exec freqai-rebel sqlite3 /freqtrade/user_data/tradesv3.dryrun.sqlite \
  "SELECT count(*) as total FROM trades;" 2>/dev/null || echo "0 trades or DB not found"
```

### 7.3 Offene Positionen

```bash
echo "=== OPEN TRADES ==="
for bot_info in "freqtrade-freqforge:/freqtrade/user_data/tradesv3.freqforge.dryrun.sqlite" \
                "freqtrade-regime-hybrid:/freqtrade/user_data/tradesv3.regime_hybrid.dryrun.sqlite" \
                "freqtrade-momentum:/freqtrade/user_data/tradesv3.momentum.dryrun.sqlite" \
                "freqtrade-rsi:/freqtrade/tradesv3.dryrun.sqlite"; do
  BOT="${bot_info%%:*}"
  DB="${bot_info##*:}"
  echo "--- $BOT ---"
  docker exec "$BOT" sqlite3 "$DB" \
    "SELECT pair, stake_amount, round(open_rate,4), open_date
     FROM trades WHERE is_open=1 ORDER BY open_date DESC;" 2>/dev/null || echo "  (no open trades or error)"
done
```

### 7.4 Signal-Layer Gesundheit

```bash
echo "=== AI-HEDGE-FUND-CRYPTO ==="
# Container health
docker inspect -f '{{.State.Status}}' ai-hedge-fund-crypto 2>/dev/null || echo "NOT_FOUND"

# Signal-Alter
python3 -c "
import json
from datetime import datetime, timezone
try:
    d = json.load(open('/home/hermes/projects/trading/ai-hedge-fund-crypto/output/latest/hermes_signal.json'))
    ts = datetime.fromisoformat(d['timestamp_utc'])
    age = (datetime.now(timezone.utc) - ts).total_seconds() / 60
    print(f'Signal age: {age:.0f} min | pairs: {len(d.get(\"pairs\",{}))} | verdict: {\"PASS\" if age<=45 else \"FAIL\"} ')
except Exception as e:
    print(f'ERROR: {e}')
"

# Primo-Signalzustand pro Bot
echo "=== PRIMO SIGNAL STATE ==="
for state_file in /home/hermes/projects/trading/freqtrade/bots/*/user_data/primo_signal_state.json; do
  BOT=$(echo "$state_file" | sed 's|.*/bots/\([^/]*\)/.*|\1|')
  echo "--- $BOT ---"
  python3 -c "
import json, sys
try:
    d = json.load(open('$state_file'))
    for pair, info in d.items():
        print(f'  {pair}: action={info.get(\"action\",\"?\")} long_bias={info.get(\"allow_long_bias\",\"?\")} short_bias={info.get(\"allow_short_bias\",\"?\")} age_min={info.get(\"age_minutes\",\"?\")}')
except Exception as e:
    print(f'  ERROR: {e}')
" 2>/dev/null || echo "  (no state file)"
done
```

### 7.5 Heartbeat-Cron-Prüfung

```bash
echo "=== HEARTBEAT CRON ==="
crontab -l 2>/dev/null | grep -i "heartbeat\|ai_hedge" || echo "No heartbeat cron found"

# Heartbeat-Log letzte Einträge
tail -5 /home/hermes/projects/trading/ai-hedge-fund-crypto/output/logs/heartbeat.log 2>/dev/null || echo "No heartbeat log"
```

### 7.6 FreqAI-Modell-Status

```bash
echo "=== FREQAI-REBEL MODEL CHECK ==="
docker exec freqai-rebel python3 -c "
from freqtrade.configuration import Configuration
import json
# Quick check: model prediction distribution and DI values
print('Model check requires FreqTrade internals - check logs instead')
" 2>/dev/null

# Alternative: Letzte FreqAI-Logs
docker logs freqai-rebel --tail 50 2>&1 | grep -iE "prediction|di_threshold|label|train" | tail -10
```

### 7.7 API-Ping (Optional)

```bash
echo "=== API PING ==="
for port_info in "FreqForge:8086" "Regime:8085" "Momentum:8084" "RSI:8081" "Rebel:8087" "Signal:8410"; do
  NAME="${port_info%%:*}"
  PORT="${port_info##*:}"
  CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/api/v1/ping" --max-time 5 2>/dev/null || echo "000")
  printf "  %-15s port=%-5s status=%s\n" "$NAME" "$PORT" "$CODE"
done
```

---

## 8. Trend-Indikatoren (Vergleich mit Vorgänger)

| Metrik | Vorher | Aktuell | Δ | Trend |
|--------|--------|---------|---|-------|
| Fleet-Gesamturteil | `{{PREV_FLEET_V}}` | `{{FLEET_VERDICT}}` | `{{FLEET_DELTA}}` | `{{FLEET_TREND}}` |
| Gesamter PnL | `{{PREV_PNL}}` | `{{TOTAL_PNL}}` | `{{PNL_DELTA}}` | `{{PNL_TREND}}` |
| Offene Trades | `{{PREV_OPEN}}` | `{{OPEN_TRADES}}` | `{{OPEN_DELTA}}` | `{{OPEN_TREND}}` |
| Signal-Alter | `{{PREV_SIG_AGE}}` | `{{SIGNAL_AGE_MIN}}` | `{{SIG_DELTA}}` | `{{SIG_TREND}}` |
| Quarantäne-Bots | `{{PREV_QUAR}}` | `{{QUARANTINE_COUNT}}` | `{{QUAR_DELTA}}` | `{{QUAR_TREND}}` |

### Trend-Symbole

| Symbol | Bedeutung |
|--------|----------|
| 📈 | Verbesserung |
| ➡️ | Gleichbleibend |
| 📉 | Verschlechterung |

---

## 9. Automatisierung (Cron-Konfiguration)

### Einrichtung als wiederkehrender Hermes-Cron-Report

```bash
# Fleet Health Report alle 6 Stunden via Hermes Cron
# Erzeugt Bericht und speichert unter orchestrator/reports/

# Schritt 1: Bericht-Skript erstellen (falls nicht vorhanden)
cat > /home/hermes/projects/trading/orchestrator/scripts/generate_fleet_health_report.sh << 'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail

REPORT_DIR="/home/hermes/projects/trading/orchestrator/reports"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H-%M-%SZ")
REPORT_FILE="${REPORT_DIR}/fleet_health_${TIMESTAMP}.md"
LATEST_LINK="${REPORT_DIR}/fleet_health_latest.md"
TEMPLATE="/home/hermes/projects/trading/docs/context/fleet-health-report-template.md"

mkdir -p "$REPORT_DIR"

# Bestehendes healthcheck-Skript nutzen für JSON-Daten
python3 /home/hermes/projects/trading/orchestrator/scripts/fleet_healthcheck.py

# Template kopieren als Basis für manuelle Ausfüllung
cp "$TEMPLATE" "$REPORT_FILE"

# Symlink aktualisieren
ln -sf "$REPORT_FILE" "$LATEST_LINK"

echo "Fleet health report generated: $REPORT_FILE"
SCRIPT

chmod +x /home/hermes/projects/trading/orchestrator/scripts/generate_fleet_health_report.sh

# Schritt 2: Cron-Job registrieren (Hermes Cron-System)
# Der Befehl richtet einen Cron-Job ein, der alle 6 Stunden läuft:
# 0 */6 * * * /home/hermes/projects/trading/orchestrator/scripts/generate_fleet_health_report.sh >> /home/hermes/projects/trading/orchestrator/reports/fleet_health_cron.log 2>&1

# ODER via Hermes Cron-Tool:
# hermes-cron add --schedule "0 */6 * * *" --command "/home/hermes/projects/trading/orchestrator/scripts/generate_fleet_health_report.sh"
```

### Integration mit Telegram-Benachrichtigung

```bash
# Nach Berichtserstellung: Kurzzusammenfassung an Telegram
# (Erfordert TELEGRAM_BOT_TOKEN und TELEGRAM_CHAT_ID in .env)

send_telegram_summary() {
  local VERDICT="$1"
  local PNL="$2"
  local OPEN="$3"
  local SIG_AGE="$4"

  local EMOJI="🟢"
  [[ "$VERDICT" == "WARN" ]] && EMOJI="🟡"
  [[ "$VERDICT" == "FAIL" ]] && EMOJI="🔴"

  local MSG="${EMOJI} Fleet Health: ${VERDICT}%0APnL: ${PNL} USDT%0AOpen: ${OPEN}%0ASignal: ${SIG_AGE} min"

  curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    -d chat_id="${TELEGRAM_CHAT_ID}" \
    -d text="$MSG" \
    -d parse_mode="HTML" > /dev/null 2>&1
}
```

---

## 10. Datenbankpfade (Referenz)

| Bot | Container | DB-Pfad (im Container) |
|-----|-----------|------------------------|
| FreqForge | freqtrade-freqforge | `/freqtrade/user_data/tradesv3.freqforge.dryrun.sqlite` |
| Regime-Hybrid | freqtrade-regime-hybrid | `/freqtrade/user_data/tradesv3.regime_hybrid.dryrun.sqlite` |
| Momentum | freqtrade-momentum | `/freqtrade/user_data/tradesv3.momentum.dryrun.sqlite` |
| RSI | freqtrade-rsi | `/freqtrade/tradesv3.dryrun.sqlite` |
| FreqAI-rebel | freqai-rebel | `/freqtrade/user_data/tradesv3.dryrun.sqlite` |

---

## 11. RSIP-Dokumentation (Prozess-Nachweis)

### Iteration 1 — Grundstruktur

Erzeugt: Abschnitte 1-6 (Zusammenfassung, Bot-Tabelle, Signalstapel, Befunde, Maßnahmen).

**Selbstkritik:**
1. Keine quantitativen Schwellen — PASS/WARN/FAIL subjektiv
2. Keine Shell-Befehle — nicht reproduzierbar
3. Kein Trend-Vergleich — keine Entwicklung erkennbar

### Iteration 2 — Klarheit/Logik

Hinzugefügt: Quantitative Schwellen (Abschnitt 2), Trend-Indikatoren (Abschnitt 8), Per-Bot Deep-Dive (Abschnitt 3).

**Selbstkritik:**
1. Nicht copy-paste-ausführbar — Befehle fehlen
2. Keine Farbsymbole/Emojis — visuelles Scanning erschwert
3. Nicht cron-tauglich — keine Automatisierungsanleitung

### Iteration 3 — Feinschliff

Hinzugefügt: Vollständige Shell-Befehle (Abschnitt 7), Emoji-Verdicts (Abschnitt 1-3), Cron-Automatisierung (Abschnitt 9), DB-Referenz (Abschnitt 10).

**Ergebnis:** Wiederverwendbare Vorlage, copy-paste-ausführbar, cron-kompatibel, mit quantitativen Schwellen und Trend-Tracking.

---

*Vorlage-Version: 3.0 | RSIP-abgeschlossen | Letzte Aktualisierung: 2026-05-15*
