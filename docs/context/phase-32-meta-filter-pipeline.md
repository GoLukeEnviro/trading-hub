# Phase 32 — Meta-Filter Pipeline & Fleet Recovery

## Date
2026-05-09 19:35 UTC

## Summary
Kompletter Durchlauf: Cron-Fix, Meta-Filter Pipeline aufgesetzt, Fleet-Status neu erfasst.

## Changes Made

### 1. Fleet Monitor Script (freqtrade_monitor.py v2)
- **Path:** `/home/hermes/projects/trading/orchestrator/scripts/freqtrade_monitor.py`
- **Purpose:** Liest per Docker-Exec die SQLite-Trade-DBs aller 3 Freqtrade-Container aus
- **Output:** Strukturiertes JSON mit Trades/Winrate/Profit/offenen Trades pro Bot
- **Fix:** Column-Name von `profit_ratio` → `close_profit` korrigiert
- **DB-Pfade:** Korrekt auf bind-gemountete user_data-Verzeichnisse konfiguriert
- **Symlink:** `/home/hermes/.hermes/scripts/freqtrade_monitor.py` → Projektverzeichnis

### 2. Cron-Job: Fleet Snapshot (neu erstellt)
- **Cron-ID:** `27c0e7076b53`
- **Schedule:** Alle 240 Minuten
- **Script:** `freqtrade_monitor.py`
- **Prompt:** Deutsche 4h-Fleet-Snapshot-Zusammenfassung
- **Delivery:** Origin (aktuelle Konversation)

### 3. Meta-Filter Bridge (primo_meta_filter_bridge.py v1.0.0)
- **Path:** `/home/hermes/primoagent/primo_meta_filter_bridge.py`
- **Pipeline:**
  1. Load → PrimoAgent-Signal (`primo_multi_signal_latest.json`) laden
  2. Validate → RiskGuard v0.1 (7 Pairs, alle WATCH_ONLY aktuell)
  3. Log → ShadowLogger v0.1 (append-only JSONL, daily logs, summary)
  4. Convert → Freqtrade State Format (Schema v0.2: verdict + bias flags)
  5. Deploy → In alle Bot-Userdata + shared-Ordner
  6. Archive → Signals werden ins `archive/` verschoben
- **Patches an ShadowLogger:** `sys.exit(0)` entfernt (blockierte nachfolgende Pipeline-Schritte)
- **Symlink:** `/home/hermes/.hermes/scripts/primo_meta_filter_bridge.py` → PrimoAgent

### 4. Cron-Job: Primo Meta-Filter Pipeline (neu)
- **Cron-ID:** `3fe8adc7d579`
- **Schedule:** Alle 240 Minuten (synchron mit Fleet-Snapshot)
- **Script:** `primo_meta_filter_bridge.py`
- **Prompt:** Signal-Auswertung mit Benachrichtigung bei ACCEPTED/Fehlern

### 5. Fleet-Status (Live)
| Bot | Port | Trades | Winrate | PnL | Status |
|-----|------|--------|---------|-----|--------|
| momentum | 8084 | 0 | — | 0.00 | Leer (DB reset) |
| regime-hybrid | 8085 | 22 | 81.8% | -0.34 USDT | RUNNING, 1 NEAR Long open |
| rsi | 8081 | 0 | — | 0.00 | Leer/quarantiniert |

### 6. ShadowLogger behoben
- `sys.exit(0)` am Ende von `log_signals()` entfernt
- Gibt jetzt Dict mit `run_id` und `entries` zurueck statt Prozess zu terminieren

## Open Issues
- Momentum- und RSI-DBs sind leer (historische Trades verschwunden nach Container-Neustart)
- API-Passwoerter der Container sind inkonsistent (`***` als Literal-String)
- Signal-Format-Bruecke zwischen PrimoAgent (Schema v0.3) und Freqtrade (Schema v0.2) ist aktiv

## Cron Jobs (Live)
| Name | ID | Schedule | Script | Status |
|------|----|----------|--------|--------|
| Daily Data/Regime Report | aed6ed7fb2e0 | 0 7 * * * | — | OK |
| 4h Fleet Snapshot | 27c0e7076b53 | alle 240m | freqtrade_monitor.py | OK (neu) |
| Primo Meta-Filter Pipeline | 3fe8adc7d579 | alle 240m | primo_meta_filter_bridge.py | OK (neu) |

## Key Files
```
/home/hermes/primoagent/
├── primo_meta_filter_bridge.py      — Pipeline-Bridge (v1.0.0)
├── risk_guard_v0_1.py               — Signal-Validator
├── shadow_logger_v0_1.py            — Append-Only Logger (gepatcht: sys.exit entfernt)
└── output/
    ├── signals/
    │   ├── primo_multi_signal_latest.json     — PrimoAgent Raw
    │   ├── primo_risk_filtered_latest.json    — RiskGuard Output
    │   └── archive/                           — Historische Signale
    └── shadow/
        ├── primo_shadow_log.jsonl             — Globaler Log
        ├── daily/                             — Tages-Logs
        └── reports/                           — Shadow-Summaries

/home/hermes/projects/trading/
├── freqtrade/
│   ├── shared/primo_signal_state.json        — Meta-Filter State (Schema v0.2)
│   └── bots/*/user_data/primo_signal_state.json
├── orchestrator/scripts/freqtrade_monitor.py — Fleet Monitor (v2)
└── docs/context/phase-32-meta-filter-pipeline.md
```
