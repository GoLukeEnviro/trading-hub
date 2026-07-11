# Current Operational State

> **Letzte Aktualisierung:** 2026-07-11  
> **Warnung:** Diese Datei kann stale sein — agent0 läuft live auf dem Legacy-Stack.

## ⚠️ NOTE: R7A Status (2026-07-11)

- **agent0** läuft live auf Legacy `docker-compose.yml`; dieser State kann von der tatsächlichen VPS-Realität abweichen (R3 §2.8)
- **R7** ist weiterhin **BLOCKED** bis:
  1. `docker-compose.hermestrader-dryrun.yml` (Greenfield-Compose) gemergt ist (PR-2)
  2. Explizite User-Freigabe + `BACKUP_GATE_GREEN` auf HermesTrader
- **Rebel** (`freqai-rebel`) ist auf `profiles: ["rebel"]` gesetzt und startet **nicht** im Default-Deploy (NOT_REPRODUCIBLE, R3-Befund)
- **Rainbow** läuft standalone auf HermesTrader (:18080); Integration in trading-hub Stack erfolgt via PR-2

## Laufende Services (Stand: Legacy-Stack)

| Service | Status | Compose |
|---|---|---|
| freqtrade-freqforge | live (agent0) | `docker-compose.yml` |
| freqtrade-freqforge-canary | live (agent0) | `docker-compose.yml` |
| freqtrade-regime-hybrid | live (agent0) | `docker-compose.yml` |
| freqai-rebel | live (agent0) | `docker-compose.yml` |
| rainbow | standalone | `ai4trade-bot/docs/r4/standalone-rainbow.yml` |

## Geplante Änderungen (R7A)

| Aktion | Gate | Branch |
|---|---|---|
| Greenfield-Compose einführen | PR-2 merge | `feat/r7a-hermestrader-dryrun-topology` |
| Host-Deploy | BACKUP_GATE_GREEN + User-Freigabe | nach PR-1+2 merge |
| Live-Trading | #423 explizit | separates Gate |

## Dry-Run-Schutz

`dry_run: true` ist in allen Greenfield-Bot-Configs gesetzt.  
`dry_run=false` ist **verboten** ohne explizite Freigabe von Issue #423.
