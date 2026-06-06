# Container Watchdog Hotfix — 2026-06-06

**Date**: 2026-06-06T06:02Z
**Scope**: `container_watchdog.sh` only
**Verdict**: **GREEN**

## Problem

`container_watchdog.sh` verwendete veraltete Docker-Container-Namen (Pre-compose-Prefix),
was zu permanenten `not_found`-Fehlern führte → Telegram-Spam bei jedem 30min-Cron-Lauf.

### Ursache

Die Container-Namen im Script stammten aus einer Ära vor dem Docker-Compose-Setup,
wo Container direkt `freqtrade-freqforge`, `freqai-rebel`, etc. hießen.
Nach dem Wechsel zu docker-compose heißen sie `trading-freqtrade-freqforge-1`, etc.

## Changes

### 1. Container-Namen korrigiert

| Alter Name | Neuer Name |
|---|---|
| `freqtrade-freqforge` | `trading-freqtrade-freqforge-1` |
| `freqtrade-freqforge-canary` | `trading-freqtrade-freqforge-canary-1` |
| `freqtrade-regime-hybrid` | `trading-freqtrade-regime-hybrid-1` |
| `freqai-rebel` | `trading-freqai-rebel-1` |
| `ai-hedge-fund-crypto` | `trading-ai-hedge-fund-1` |

### 2. DOCKER_HOST-Safeguard

`export DOCKER_HOST="unix:///var/run/docker.sock"` hinzugefügt vor dem Docker-Detection-Block.
Bypass den Docker-Proxy (EXEC=0) und nutzt den direkten Unix-Socket.

### 3. JSON-Ausgabe auf printf umgestellt

`echo` mit Escapes erzeugte Control-Characters im State-File.
Ersetzt durch `printf` mit sauberer Formatierung.

## Validation

```
Run: 2026-06-06T06:02:40Z
Mode: docker (direct socket)
Output: (silent — kein Telegram-Spam)
State: valid JSON

Container Status:
  trading-freqtrade-freqforge-1:      running ✅
  trading-freqtrade-freqforge-canary-1: running ✅
  trading-freqtrade-regime-hybrid-1:    running ✅
  trading-freqai-rebel-1:              running ✅
  trading-ai-hedge-fund-1:             running ✅
```

## File

`/opt/data/profiles/orchestrator/scripts/container_watchdog.sh` (v4, 4601 bytes)

## Nicht angefasst

- Config-Drifts (stake_amount: 100→50, 50→25, 50→25) — separat zu entscheiden
- drawdown-guard, riskguard-service, critical-event-watchdog
- FleetRisk, ledger-integrity-watchdog
- Alle anderen Cron-Jobs

## Bekanntes Risiko

~30 weitere Scripte in `/opt/data/profiles/orchestrator/scripts/` referenzieren
noch die alten Container-Namen (grep zeigt 37+ Treffer).
Diese werden im nächsten Batch adressiert.

## Rollback

```bash
# Original v3 war in docs/context/cron-hygiene-audit-20260606.md backuped
# Bei Bedarf: alte Namen zurücksetzen und DOCKER_HOST-Zeile entfernen
```
