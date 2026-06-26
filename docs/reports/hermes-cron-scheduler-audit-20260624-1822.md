# Hermes / Trading Hub Cron & Scheduler Audit

## Verdict
YELLOW

## Executive Summary
Der Hermes orchestrator gateway läuft (PID 158, Profile `orchestrator`, seit 22.06.) und managed **58 Cron-Jobs** aktiv. Der SI-v2 6h-Cycle produziert Evidence mit 4-Bot-Fleet-Abdeckung. 14 Legacy-Jobs sind deaktiviert. 1 Job (`Fleet correlation refresh`) schlägt fehl. Die Guardian-Container-Komponente hat einen false-positive Container-Down-Detection-Bug. Die Orchestrator-Cron-spezifischen Sub-Jobs (`*/20 * * * *` signal-heartbeat etc.) aus der ursprünglichen jobs.json werden **nicht** mehr verwendet — das live-System hat eine völlig andere, erweiterte Job-Liste.

**Kernerkenntnis:** Der SI-v2 Active Cycle (6h) läuft zuverlässig, produziert 4-Bot-Evidence und ShadowProposals. Die Automatisierung IST installiert und aktiv. Der Host-File-Cache (`/opt/data/profiles/orchestrator/cron/jobs.json`) war jedoch **stale** (12 statt 58 Jobs) — Live-Daten nur im Container verfügbar.

## Safety Scope
Read-only Audit. Keine Mutationen. Keine Cron-Edits. Keine Restarts. Keine apply-tokens.

## Repo State
| Check | Value |
|-------|-------|
| Branch | `main` |
| HEAD | `0cf5a4d30a8dc2a3d11e942b2f573e142d3acd71` |
| origin/main | `0cf5a4d30a8dc2a3d11e942b2f573e142d3acd71` |
| HEAD == origin/main | ✅ Yes |
| Worktree | Clean (untracked files only, no staged changes) |

## Scheduler Inventory

### Scheduler-Typen

| Typ | Status | Jobs |
|-----|--------|------|
| Hermes Orchestrator Cron (internal) | ✅ **Running** (PID 158, seit 22.06.) | 58 (44 enabled, 14 disabled) |
| User crontab (hermes) | ⚠️ **Frozen** (seit 11.06.) | 2 commented-out permission autopilot jobs |
| Root crontab | ✅ **Running** | 4 VPS-Backup-Jobs |
| `/etc/cron.d` | ✅ **Running** | 2 (qdrant-backup, delete-v2-collection historic) |
| Systemd Timers | ✅ **Running** | None related to trading |
| Docker Guardian (external_cron_guardian.sh) | ✅ **Running** | 5-min loop (signal freshness, container health) |
| User Systemd Timers | ✅ **Not used** | None |

### Aktive SI-v2-relevante Jobs (aus Hermes orchestrator cron, 58 total)

| Job Name | Schedule | Last Run | Status | Fleet Coverage |
|----------|----------|----------|--------|----------------|
| `si-v2-active-cycle (6h, log-only)` | 6h (:17) | 2026-06-24T12:17:57Z | ✅ ok | 4/4 bots |
| `trading-pipeline` | alle 10min | 2026-06-24T16:21:16Z | ✅ ok | 4/4 via signal |
| `unified-signal-heartbeat` | alle 20min | 2026-06-24T16:16:33Z | ✅ ok | signal layer |
| `Heartbeat Intelligence Report` | alle 6h | 2026-06-24T12:00:55Z | ✅ ok | 4/4 |
| `Fleet Report (alle 6h)` | alle 6h | 2026-06-24T13:54:01Z | ✅ ok | 4/4 (agent-run) |
| `System Health Check (alle 8h)` | alle 8h | 2026-06-24T16:03:04Z | ✅ ok | infrastructure |
| `Rebel Status Summary (12h Telegram)` | 12h | 2026-06-24T13:46:06Z | ✅ ok | rebel only |
| `autonomous-health-loop` | alle 30min | 2026-06-24T15:55:49Z | ✅ ok | infrastructure |
| `container-watchdog` | alle 5min | 2026-06-24T16:04:09Z | ✅ ok | infrastructure |
| `drawdown-guard` | alle 5min | 2026-06-24T16:04:09Z | ✅ ok | portfolio-level |
| `riskguard-service` | alle 5min | 2026-06-24T16:04:10Z | ✅ ok | signal integrity |
| `fleet-auto-repair` | alle 5min | 2026-06-24T16:04:06Z | ✅ ok | fleet-health |
| `observation-runner` | alle 30min | 2026-06-24T16:25:59Z | ✅ ok | data quality |

### Legacy/Deaktivierte Jobs (14 total)

Alle `si-bot-*` Jobs (A/B/C/D: backtest, daily, walkforward) sind `enabled=False` mit `status=error`. Dies sind die alten SI-v1 Jobs, die durch den SI-v2 Cycle ersetzt wurden. Korrekt deaktiviert.

## Creation Provenance
- SI-v2 Active Cycle wurde via Git Commits `f14b286`, `9758a75`, `c45d6c5` et al. eingeführt
- Orchestrator-Gateway läuft via s6-Supervision (Container-Boot), Autostart-Script in `/etc/cont-init.d/01b-orchestrator-autostart`
- Gateway-Status: `running` (seit Container-Start am 22.06.)
- Kein einziger SI-v2-relevanter Job wurde via User/Root-Crontab installiert — alles läuft über Hermes internen Cron-Scheduler

## Execution Proof

### SI-v2 Active Cycle (6h)
Letzte 4 Zyklen:
| Cycle ID | Timestamp (UTC) | Fleet Verdict | 4-Bot Evidence | ShadowProposals | Mutations |
|----------|----------------|---------------|----------------|-----------------|-----------|
| `20260624T121756Z` | 12:17:56 | GREEN | ✅ 4/4 | 4 ✅ | 0 ✅ |
| `20260624T061755Z` | 06:17:55 | GREEN | ✅ 4/4 | 4 ✅ | 0 ✅ |
| `20260624T002122Z` | 00:21:22 | GREEN | ✅ 4/4 | 4 ✅ | 0 ✅ |
| `20260623T181740Z` | 18:17:40 | GREEN | ✅ 4/4 | 4 ✅ | 0 ✅ |

**Evidence-Artefakte vorhanden:** 
- 56+ Zyklen seit 15.06.2026 in `self_improvement_v2/reports/phase2/evidence/`
- Telemetry History: 57 Einträge seit 15.06. (täglich, alle 4 Bots)
- Latest: `active_cycle_20260624T121756Z.json` (12:17 UTC heute)
- Controller-State: `PAUSED / L3_REPOSITORY_ONLY` — keine Mutationen

### Signal Pipeline (trading-pipeline alle 10min)
- Letzter Run: `2026-06-24T16:21:16Z` (4 Minuten vor Audit)
- Signal fresh (Guardian-Log: "Signal fresh (4.9min < 30min)")
- RiskGuard aktiv und prüft Signal-Frische, Schema, Konfidenz

## Fleet Coverage
**✅ Vollständig:** Alle 4 Bots sind in SI-v2 Evidence enthalten:
- `freqtrade-freqforge`
- `freqtrade-freqforge-canary`
- `freqtrade-regime-hybrid`
- `freqai-rebel`

Keine 6-Bot-Referenzen mehr. Momentum/MVS sind historisch.

## Broken / Stale / Risky Items

| Item | Status | Impact | Fix |
|------|--------|--------|-----|
| `Fleet correlation refresh` | ❌ **error** | correlation data stale | Needs investigation |
| `hermes-standby-monitor` | ⚠️ disabled+error | minor | Manual review |
| `Hermes Error-Alert (5min)` | ⚠️ disabled | minor | Manual review |
| Guardian false-positive: `CONTAINER_DOWN: ai-hedge-fund-crypto` | ⚠️ **False alarm** (container `trading-ai-hedge-fund-1` läuft) | noise in logs | Guardian-Check fixen |
| Host `jobs.json` stale (12 vs 58 Jobs) | ⚠️ **Cache-Problem** | Verwirrung bei Audit | nächstes Backup aktualisieren |
| Gateway-State-File lag (/opt/data/gateway_state.json zeigt "stopped") | ⚠️ Legacy | kein Impact, active gateway läuft parallel | cleanup optional |
| SI-v2 Cycle Script fehlt (`si_v2_active_cycle_cron.sh` existiert nicht) | ⚠️ **Script-Drift** | Scheduler läuft trotzdem — vermutlich anderer Pfad/Methode | script anlegen oder Job fixen |

## Failure Tree

1. Host vs Container jobs.json inkonsistent (stale Host-File, aktuelles Container-File)
2. Gateway-State-Legacy: alter Gateway-State auf "stopped", aktueller auf "running"
3. Guardian false-positive Container-Down-Detection (Namen mismatch)
4. `si_v2_active_cycle_cron.sh` Script-Missing — Job läuft trotzdem (via Hermes agent?)
5. Korrelierte Daten fehlen (`Fleet correlation refresh` schlägt fehl)
6. Legacy SI-v1 Jobs deaktiviert (korrekt, aber cleanup candidate)

## Single Next Repair Step
**Guardian Container-Namen-Fix korrigieren:** Der Guardian versucht Container `ai-hedge-fund-crypto` zu starten, aber der tatsächliche Name ist `trading-ai-hedge-fund-1` (Docker-Compose-Prefix). Das verursacht alle 5 Minuten einen false-positive Alarm. Fix: Container-Namen in Guardian-Konfiguration von `ai-hedge-fund-crypto` auf `trading-ai-hedge-fund-1` aktualisieren.

## Suggested Backlog Issues

### P1: Fleet correlation refresh reparieren
**Goal:** `Fleet correlation refresh` Job läuft mit `status=error` — Korrelationsdaten für SI-v2 werden nicht aktualisiert.
**AC:** Job läuft durch, Log zeigt Erfolg, correlation data ist aktuell.
**Effort:** M
**Relation:** SI-v2 Loop — Signal-Qualität

### P2: Guardian false-positive Container-Down beheben
**Goal:** Guardian alarmiert alle 5min `CONTAINER_DOWN: ai-hedge-fund-crypto`, obwohl Container `trading-ai-hedge-fund-1` läuft.
**AC:** Guardian-Log zeigt keine false-positive Container-Down-Alarme mehr.
**Effort:** S
**Relation:** Infrastructure — Signal-Reliability

### P2: SI-v2 Active Cycle Runner Script pflegen
**Goal:** `si_v2_active_cycle_cron.sh` existiert nicht auf Disk, wird aber vom Cron-Job referenziert.
**AC:** Script existiert oder Job-Referenz zeigt auf tatsächlichen Python-Einstiegspunkt.
**Effort:** S
**Relation:** SI-v2 Loop — Maintenance

### P3: Host jobs.json Cache aktualisieren
**Goal:** Host-Pfad `/opt/data/profiles/orchestrator/cron/jobs.json` zeigt 12 statt 58 Jobs (Container hat die aktuellen Daten).
**AC:** Host-Datei spiegelt aktuellen orchestrator-Job-Status wider.
**Effort:** S
**Relation:** Operability — Audit-Konsistenz

### P3: Legacy Gateway-State cleanup
**Goal:** `/opt/hermes-green/config/gateway_state.json` zeigt "stopped" vom alten Gateway. Aktueller Gateway läuft unter `/opt/hermes-green/config/profiles/orchestrator/gateway_state.json`.
**AC:** Legacy-File entfernt oder als historisch markiert.
**Effort:** S
**Relation:** Operability

## Final Verdict
**YELLOW** — Automation ist installiert, der SI-v2 Active Cycle (6h) läuft zuverlässig mit 4-Bot-Evidence und ShadowProposals. Die Signal-Pipeline und Fleet-Monitoring-Jobs sind aktiv. Es gibt 1 fehlschlagenden Job (Fleet correlation refresh), einen false-positive Guardian-Alarm, und ein fehlendes Shell-Script (ohne Runtime-Impact). Der Host-File-Cache ist stale, was frühere Verwirrung verursacht hat. Die Kern-Automation ist intakt.
