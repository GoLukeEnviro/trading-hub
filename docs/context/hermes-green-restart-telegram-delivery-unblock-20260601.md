# Hermes-Green Restart: Telegram-Delivery Unblock -- 2026-06-01

## Kontext

Telegram-Delivery Scheduler Audit (2026-06-01 11:00 UTC) identifizierte:
- Hermes-Agent Telegram-Polling broken (TimedOut)
- LLM-Provider z.ai/glm-5.1 HTTP 429 Rate-Limit-Kaskade
- `deliver=telegram` Cron-Jobs seit ~04:00 UTC nicht mehr dispatcht
- `deliver=local` Jobs unbeeintraechtigt

## Aktion

**Kontrollierter Restart von `hermes-green`** um Telegram-Polling-Loop zu entsperren.

```bash
docker restart hermes-green
```

**Zeitpunkt:** 2026-06-01 11:14:58 - 11:15:09 UTC (11 Sekunden Downtime)

## Pre-State

| Container | Status |
|---|---|
| hermes-green | Up 12 hours |
| green-mem0 | Up 4 hours (healthy) |
| green-qdrant | Up 3 days |
| green-ollama | Up 3 days |
| freqtrade-freqforge | Up 6 hours |
| freqtrade-freqforge-canary | Up 7 hours |
| freqtrade-regime-hybrid | Up 6 hours |
| freqai-rebel | Up 6 hours |
| ai-hedge-fund-crypto | Up 9 hours (healthy) |
| Blue Stack | Exited (Stop-only Test) |

## Post-State

| Container | Status | Veraenderung |
|---|---|---|
| hermes-green | Up 13 seconds | RESTARTED |
| green-mem0 | Up 4 hours (healthy) | unveraendert |
| green-qdrant | Up 3 days | unveraendert |
| green-ollama | Up 3 days | unveraendert |
| Trading-Bots | alle Up | unveraendert |
| Blue Stack | Exited | unveraendert |

## Validierung

| Check | Ergebnis |
|---|---|
| Hermes Startup | sauber, keine TimedOut/429 Fehler |
| Telegram-Fehler im Startup | KEINE (vorher: TimedOut, Bad Gateway) |
| Cron Scheduler geladen | Ja ("Messaging platforms + cron scheduler") |
| Green Mem0 Health | ok, cloud_required=false |
| Trading Bots | 4/4 running, unveraendert |
| Blue Stack | 3/3 Exited, unveraendert |

## Erwartete Scheduler-Erholung

Nach Restart sollten folgende Jobs innerhalb ihrer Schedule-Intervalle wieder laufen:

| Job | Schedule | Erwarteter naechster Lauf |
|---|---|---|
| container-watchdog | */5 Min | innerhalb 5-10 Min |
| mcp-watchdog | */5 Min | innerhalb 5-10 Min |
| drawdown-guard | */30 Min | innerhalb 30-35 Min |
| Fleet Report | alle 4h | innerhalb 4h |

## Script-Fixes die jetzt greifen sollten

Die vorherigen P0/P1 Fixes sind noch aktiv und werden beim naechsten Dispatch greifen:

1. `fleet_api_client.py` im Profile-Dir vorhanden (drawdown-guard Import-Fix)
2. `drawdown_guard.py` synchronisiert mit hermes-green Referenz
3. `container_watchdog_state.json` auf hermes:ftuser 664
4. Guardian-Sync-Liste um fleet_api_client.py erweitert

## Beobachtungszeitraum

Naechste 30-35 Minuten pruefen:
- container_watchdog_state.json Timestamp aktualisiert sich
- drawdown_state.json Timestamp aktualisiert sich
- Keine neuen ModuleNotFoundError in Logs
- Keine Permission denied Fehler
- Telegram-Alerts kommen wieder durch
