# FreqAI-Rebel Fix & Fleet Status Update — 2026-06-06

## Summary
FreqAI-Rebel crash-loop repariert (fehlende Python-Module datasieve + xgboost). 
0-Trade-Fehlalarm korrigiert: Bots handeln, die Health-Check-DB-Pfade waren falsch.

## Actions Taken

### Infrastructure
1. **Dockerfile.freqai-rebel erstellt** (`freqtrade/Dockerfile.freqai-rebel`):
   - Basis: `freqtradeorg/freqtrade:stable`
   - Zusätzliche Pakete: `pip install datasieve xgboost`
   - Image gebaut als `freqtrade-freqai-rebel:custom`

2. **docker-compose.yml angepasst** (freqai-rebel Sektion):
   - `image:` → `build:` mit `context: ./freqtrade, dockerfile: Dockerfile.freqai-rebel`
   - `image: freqtrade-freqai-rebel:custom`
   - Netzwerk: `hermes-net`

3. **Container neu erstellt**:
   - Alter Container gestoppt/entfernt
   - Neuer Container via direktem Docker-Socket gestartet (docker-compose CLI nicht verfügbar)
   - Netzwerk: `trading_hermes-net`
   - FreqAI-Rebel läuft jetzt, trainiert Modelle und inferiert ohne Fehler

### DB Path Fixes (2026-06-06 Session)
Alle generischen `tradesv3.sqlite` / `tradesv3.dryrun.sqlite` Referenzen in Monitoring-Scripts durch bot-spezifische Pfade ersetzt:

| Datei | Betroffener Bot | Änderung |
|-------|----------------|----------|
| `orchestrator/scripts/freqtrade_monitor.py` | FreqAI-Rebel | `tradesv3.dryrun.sqlite` → `tradesv3.freqai_rebel.dryrun.sqlite` |
| `orchestrator/scripts/quality_hub_monitor.py` | FreqForge | Stale fallback entfernt |
| `orchestrator/scripts/quality_hub_monitor.py` | FreqAI-Rebel | Generische Pfade → bot-spezifisch |
| `orchestrator/scripts/monthly_strategy_report.py` | FreqForge | Stale fallback entfernt |
| `orchestrator/scripts/monthly_strategy_report.py` | FreqAI-Rebel | Generische Pfade → bot-spezifisch |
| `orchestrator/scripts/rebel_30m_check.py` | FreqAI-Rebel | Docker-Volume-Pfad → Bind-Mount-Pfad |
| `orchestrator/scripts/system_optimizer.py` | FreqForge | Stale fallback entfernt |
| `orchestrator/scripts/system_optimizer.py` | FreqAI-Rebel | Generische Pfade → bot-spezifisch |
| `freqtrade/bots/regime-hybrid/config/research/automation/fleet_monitor.py` | FreqForge | Stale fallback entfernt |
| `freqtrade/bots/regime-hybrid/config/research/automation/fleet_monitor.py` | FreqAI-Rebel | Generische Pfade → bot-spezifisch |

### FreqAI-Rebel Config
- `db_url` in `config.json` hinzugefügt: `sqlite:////freqtrade/user_data/tradesv3.freqai_rebel.dryrun.sqlite`
- Bestehende `tradesv3.dryrun.sqlite` → `tradesv3.freqai_rebel.dryrun.sqlite` kopiert (Daten erhalten)
- Container nach Config-Change neu gestartet

### Restart Script
- Erstellt: `scripts/restart-freqai-rebel.sh`
- Direkter Docker-Socket (kein docker compose CLI nötig)
- Build + Run in einem Durchlauf

### Fleet Status Dashboard
- Erstellt: `scripts/fleet-status.sh`
- Container-Status / Trade-DBs / Disk / AI-Hedge-Fund Signal

## Fleet Profitability (korrigierte DB-Pfade)

| Bot | Closed | Open | PnL (USDT) |
|-----|--------|------|------------|
| FreqForge | 62 | 1 | +23.17 |
| FreqForge-Canary | 44 | 0 | +7.40 |
| Regime-Hybrid | 45 | 0 | -6.18 |
| FreqAI-Rebel | 0 | 0 | 0.00 (gerade neugestartet) |

## AI-Hedge-Fund Signal
- Alle 3 Pairs auf SHORT (BTC/ETH/SOL)
- ACCEPTED/WATCH_ONLY: Status wird über v04-Action-Schicht gesteuert
- Signal fresh: `2026-06-06T02:16:12 UTC`

## Files Changed
| File | Action |
|------|--------|
| `freqtrade/Dockerfile.freqai-rebel` | neu |
| `docker-compose.yml` | freqai-rebel build/image/networks |
| `orchestrator/scripts/freqtrade_monitor.py` | DB path fix |
| `orchestrator/scripts/quality_hub_monitor.py` | DB path fixes |
| `orchestrator/scripts/monthly_strategy_report.py` | DB path fixes |
| `orchestrator/scripts/rebel_30m_check.py` | DB path fix |
| `orchestrator/scripts/system_optimizer.py` | DB path fixes |
| `freqtrade/bots/regime-hybrid/config/research/automation/fleet_monitor.py` | DB path fixes |
| `freqtrade/bots/freqai-rebel/user_data/config.json` | db_url added |
| `scripts/restart-freqai-rebel.sh` | neu |
| `scripts/fleet-status.sh` | neu |

## Open Points
- FreqAI-Rebel hat 0 Trades (max_open_trades=0, intentionale Quarantäne)
- Keine weiteren P2+-Items offen
