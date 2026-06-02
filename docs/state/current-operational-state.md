# Operational State — Trading Hub v2.x

**Stand:** 2026-06-02 23:00 UTC
**Quelle:** Live-Checks auf Host `Agent0` (synthetisiert aus Kontext 2026-06-01/02)
**Status:** ✅ SYSTEM_GREEN_DRYRUN_READY

> Dieses Dokument ist der offizielle System-Snapshot.
> Alle Bots laufen dry_run=True. Kein Live-Trading.

---

## 📋 INHALTSVERZEICHNIS

1. [System-Architektur](#1-system-architektur)
2. [Container-Fleet](#2-container-fleet)
3. [Auto-Reparatur & Selbstheilung](#3-auto-reparatur--selbstheilung)
4. [Signal Pipeline](#4-signal-pipeline)
5. [Safety & Risk Management](#5-safety--risk-management)
6. [Cron-Job-Übersicht](#6-cron-job-übersicht)
7. [Netzwerk-Topologie](#7-netzwerk-topologie)
8. [Speicher & Ressourcen](#8-speicher--ressourcen)
9. [Offene Risiken](#9-offene-risiken)
10. [Changelog](#10-changelog)

---

## 1. System-Architektur

```
                     ┌─────────────────────┐
                     │   ai-hedge-fund-    │
                     │   crypto (8410)     │
                     │  deepseek-v4-pro    │
                     └────────┬────────────┘
                              │ hermes_signal.json
                              ▼
┌─────────────────────────────────────────────────┐
│            TRADING PIPELINE (trading_pipeline)  │
│  ┌─────────┐  ┌──────────┐  ┌───────────────┐ │
│  │ BRIDGE  │→ │RISKGUARD │→ │ SHADOWLOGGER  │ │
│  │ (read)  │  │(RG-1..5) │  │ (append-only) │ │
│  └─────────┘  └────┬─────┘  └───────────────┘ │
│                    │                            │
│                    ▼                            │
│           ┌────────────────┐                    │
│           │  MCP EXECUTION │ (paper orders)    │
│           │  bitget-mcp-   │                    │
│           │  server npm    │                    │
│           └────────────────┘                    │
└─────────────────────┬──────────────────────────┘
                      │ primo_signal_state.json
                      ▼
┌────────────────────────────────────────────────┐
│           FREQTRADE FLEET (dry-run)             │
│  ┌────────┐ ┌────────┐ ┌──────┐ ┌──────┐      │
│  │FreqForge│ │ Canary │ │Regime│ │Rebel │      │
│  │ 8086   │ │ 8081   │ │ 8085 │ │ 8087 │      │
│  └────────┘ └────────┘ └──────┘ └──────┘      │
└────────────────────────────────────────────────┘

SELBSTHEILUNGS-SCHICHT:
┌─────────────────────────────────────────────────┐
│  Standby-Monitor (5min)  → Health + Auto-Restart│
│  Config-Diff (1h)        → Drift-Erkennung      │
│  Auto-Parameter (15min)  → MOT/Stake/Conf-Rules │
│  RiskGuard Service (30m) → Unabhängiges Audit   │
│  Heartbeat Writer (15min)→ Bot-Health-DB        │
│  FleetReport (4h)        → Telegram-Report      │
│  System Optimizer (5min) → Fleet-Optimierung    │
│  Log Rotation (täglich)  → Log-Management       │
│  Permission Autopilot    → Ownership-Stabilizer │
└─────────────────────────────────────────────────┘
```

---

## 2. Container-Fleet

| # | Container | Port | Status | Strategie |
|---|-----------|------|--------|-----------|
| 1 | `freqtrade-freqforge` | 8086 | ✅ Up | `FreqForge_Override` |
| 2 | `freqtrade-freqforge-canary` | 8081 | ✅ Up | `FreqForge_Override` |
| 3 | `freqtrade-regime-hybrid` | 8085 | ✅ Up | `RegimeSwitchingHybrid_v7_v04_Integration` |
| 4 | `freqai-rebel` | 8087 | ✅ Up (isolated net) | `RebelLiquidation + XGBoost` |
| 5 | `ai-hedge-fund-crypto` | 8410 | ✅ Healthy | Signal Generator |
| 6 | `hermes-green` | — | ✅ Up | Meta-Orchestrator |
| 7 | `green-mem0` | 8787 | ✅ Healthy | Memory-Stack |
| 8 | `green-ollama` | 11436 | ✅ Up | LLM-Inference |
| 9 | `green-qdrant` | 6333 | ✅ Up | Vector-DB |
| 10 | `freqtrade-webserver` | 8180 | ✅ Up | Web-UI |
| 11 | `caddy` | — | ✅ Up | Reverse Proxy |
| 12 | `trading-guardian` | — | ⚠️ Up (purpose unclear) | Guardian (isoliertes Netz) |

**Nicht mehr aktiv:**
- `freqtrade-momentum` — **DECOMMISSIONED** seit 2026-05-24
- `hermes-mem0-local-api`, `hermes-ollama`, `hermes-qdrant` — durch green-* Stack ersetzt (EXITED)

---

## 3. Auto-Reparatur & Selbstheilung

### 3.1 Standby-Hermes Monitor
- **Script:** `hermes_standby_monitor.py`
- **Cron:** Alle 5 Minuten
- **Funktion:** Prüft Container-Health + Scheduler-Prozesse
- **Failover:** Auto-Restart bei Container-Down. Bei >10min Ausfall: Emergency-Fallback

### 3.2 Config-Diff-Detektor
- **Script:** `config_diff_detector.py`
- **Cron:** Stündlich
- **Funktion:** Vergleicht Config-on-Disk mit Config-in-Container
- **Prüft:** `max_open_trades`, `stake_amount`, `dry_run`, `stoploss`, `trailing_stop`
- **Auto-Repair:** `--fix`-Modus → Config restaurieren + Container restarten

### 3.3 FleetRisk Auto-Parameter
- **Script:** `fleet_risk_auto_params.py`
- **Cron:** Alle 15 Minuten
- **6 Regeln:**

| Regel | Bedingung | Aktion |
|-------|-----------|--------|
| R1 | ConsecLoss > 3 | MOT = max(1, baseline-2) |
| R2 | Drawdown > 3% | Stakes halbieren |
| R3 | Drawdown > 5% | Alle Bots pausieren (MOT=0) |
| R4 | Drawdown < 1% + ConsecLoss < 2 | Baselines wiederherstellen |
| R5 | ConsecLoss > 6 | Confidence-Threshold 0.75 (24h) |
| R6 | Fleet PnL > +5% | Stakes +25% |

### 3.4 Heartbeat Writer
- **Script:** `heartbeat_writer.py`
- **Cron:** Alle 15 Minuten
- **DB:** `orchestrator/state/hermes_heartbeat.sqlite`
- **Alle 4 Bots:** api=1, running, open_trades tracked

### 3.5 RiskGuard Service (Standalone)
- **Script:** `riskguard_service.py`
- **Cron:** Alle 30 Minuten
- **State-Dir:** `orchestrator/state/riskguard/`
- **Files:** `riskguard_health.json`, `riskguard_state.json`, `riskguard_audit.jsonl`

### 3.6 Log-Rotation
- **Script:** `log_rotation.py`
- **Cron:** Täglich 03:00 UTC
- **Limit:** Rotation bei >5MB, Cleanup bei >30d

### 3.7 Permission Autopilot
- **Script:** `permission_autopilot.sh`
- **Modus:** Host-only, als root
- **Funktion:** Ownership-Drift-Erkennung und -Reparatur auf Runtime-Mount-Roots
- **Apply-Scope:** `freqtrade/shared/`, `freqtrade/logs/`, `orchestrator/logs/`, `orchestrator/state/`

### 3.8 Git Guard
- **Script:** `git_guard.sh`
- **Funktion:** Pre-commit Sanity-Check — prüft Ownership außerhalb von Runtime-Pfaden

---

## 4. Signal Pipeline

### Layer 1: Bridge (trading_pipeline.py)
- **Signal-Quellen:** `hermes_signal.json` (canonical), `latest/` (fallback)
- **Normalisierung:** Futures-Paare (`BTC/USDT:USDT` → `BTC/USDT`)
- **Stale-Block:** Signal >25min → PIPELINE_BLOCKED

### Layer 2: RiskGuard (5 Gates)
| Gate | Regel | Ergebnis |
|------|-------|----------|
| RG-1 | Signal stale (age > 25min) | WATCH_ONLY |
| RG-2 | Confidence < 0.65 | WATCH_ONLY + REJECTED |
| RG-3 | Bias nicht bullish/bearish | WATCH_ONLY |
| RG-4 | Max 5 concurrent signals überschritten | WATCH_ONLY |
| RG-5 | Quantity=0 trotz directional action | WATCH_ONLY |

### Layer 2.5: MCP Execution
- **Status:** ✅ AKTIV (npm bitget-mcp-server v1.1.0, read-only, --read-only flag)
- **Funktion:** Paper-Orders via offiziellen Bitget MCP (immer dry_run=true, keine API-Keys)
- **Migration:** Custom `bitget_mcp_server.py` durch offizielles npm Package ersetzt

### Layer 3: ShadowLogger
- **File:** `orchestrator/logs/shadow_decisions.jsonl`
- **Format:** Append-only JSONL, Schema v1.0
- **Inhalt:** Signal-Age, RiskGuard-Summary, Pair-Decisions, State-Writes

### Layer 4: Bridge-Write
- **State-Files:** 4 Zielpfade (regime-hybrid, freqforge, canary, freqai-rebel)
- **Atomic Write:** tmp+rename, chmod 644

---

## 5. Safety & Risk Management

### 5.1 Bot-Konfiguration

| Bot | dry_run | MOT | Stake | Strategie |
|-----|---------|-----|-------|-----------|
| FreqForge | ✅ True | 5 | 100 | `FreqForge_Override` |
| Canary | ✅ True | 3 | 50 | `FreqForge_Override` |
| Regime-Hybrid | ✅ True | 5 | 50 | `RegimeSwitchingHybrid_v7_v04_Integration` |
| Rebel | ✅ True | 2 | 50 | `RebelLiquidation + XGBoost` |

### 5.2 Fleet Performance (kumuliert, Stand 2026-06-02)

| Bot | PnL (USDT) | WR% | Open |
|-----|------------|-----|------|
| FreqForge | +8.94 | 86.5 | 1 |
| FreqForge-Canary | +3.23 | 90.9 | 3 |
| Regime-Hybrid | -7.08 | 77.3 | 0 |
| Rebel | -5.76 | 25.0 | 0 |
| **Fleet** | **-0.67** | — | **4** |

**MCP Paper Portfolio:** 4 offene Positionen, 399 Orders, 8.47 USDT Balance

---

## 6. Cron-Job-Übersicht

### 6.1 Kern-Pipeline
| Job | Intervall | Funktion |
|-----|-----------|----------|
| `trading-pipeline` | */10min | Signal-Bridge + RiskGuard + MCP |
| `system-optimizer` | 5min | Fleet-Optimierung + Guard-States |
| `FleetRisk equity updater` | 5min | Equity-Tracking |
| `unified-signal-heartbeat` | */15min | Unified Signal-Trigger (ersetzt signal-heartbeat + smart-heartbeat) |

### 6.2 Monitoring & Sicherheit
| Job | Intervall | Funktion |
|-----|-----------|----------|
| `hermes-standby-monitor` | 5min | Health-Check + Auto-Restart |
| `heartbeat-writer` | */15min | Bot-Health-DB |
| `critical-event-watchdog` | */10min | Kritische Event-Überwachung |
| `mot-floor-watchdog` | */10min | MOT-Untergrenze |
| `container-watchdog` | */30min | Container-Health |
| `drawdown-guard` | */30min | Drawdown-Schutz |
| `canary-position-monitor` | */30min | Canary-Positions |
| `fleetrisk-auto-params` | */15min | Dynamische Parameter |
| `riskguard-service` | */30min | Unabhängiges Signal-Audit |
| `config-diff-detector` | 1h | Config-Drift-Prüfung |

### 6.3 Reports & Wartung
| Job | Intervall | Funktion |
|-----|-----------|----------|
| `Fleet Report` | 4h | Telegram-Bericht |
| `autonomous-health-loop` | 30min | Autonomer Health-Check (LLM) |
| `fleet-auto-repair` | 2h | Auto-Reparatur |
| `ghostbuster` | 2h | Stale-Artifact-Cleanup |
| `mem0-watchdog` | 2h | Memory-Health |
| `Memory Backfill` | 2h | Memory-Recovery |
| `cron-guardian` | 6h | Cron-Job-Health |
| `Heartbeat Intelligence` | 6h | Bot-Intelligence-Report |
| `daily-signal-confidence-monitor` | 6h | Signal-Konfidenz (LLM) |
| `System Health Check` | 8h | System-Gesamtcheck (LLM) |
| `daily-heartbeat` | 06:00 UTC | Täglicher Heartbeat |
| `morning-brief-daily` | 08:00 UTC | Morning Brief |
| `morning-brief-1040` | 10:40 UTC | Morning Brief 2 |
| `quality-hub-monitor` | 08:00 UTC | Qualitätsprüfung |
| `daily-backup` | 02:00 UTC | Backup-Rotation |
| `log-rotation-daily` | 03:00 UTC | Log-Rotation |
| `trading-hub-deep-dive-validation` | täglich 09:00 | Validierung (LLM) |
| `Rebel Status Summary` | 12h | Rebel-Bericht |
| `Fleet correlation refresh` | 72h | Korrelations-Update |
| `monthly-strategy-report` | monatlich | Strategie-Report |
| `portfolio-rebalancer` | Montag 06:00 | Portfolio-Rebalancing |

**Gesamt:** ~37 Cron-Jobs

---

## 7. Netzwerk-Topologie

```
Host Agent0
├── hermes-green_green-net (172.23.0.0/24)
│   ├── hermes-green (172.23.0.5) — Meta-Orchestrator
│   ├── green-mem0 — Memory
│   ├── green-ollama — LLM
│   └── green-qdrant — Vector-DB
│
├── ki-fabrik (172.18.0.0/24)
│   ├── ai-hedge-fund-crypto — Signal-Generator
│   ├── freqtrade-freqforge — Bot
│   ├── freqtrade-freqforge-canary — Bot
│   ├── freqtrade-regime-hybrid — Bot
│   └── hermes-green (dual-homed)
│
└── trading_hermes-net (isoliert)
    └── trading-guardian (Zweck ungeklärt)

freqai-rebel: eigenes freqai-rebel-net (ISOLIERT)
```

**Besonderheiten:**
- Hermes-Container ist dual-homed: green-net + ki-fabrik
- Freqtrade FreqForge/Canary/Regime: ki-fabrik direkt erreichbar
- Rebel: Netzwerk-isoliert, nur via `docker exec` erreichbar
- trading-guardian: eigenes Netz, keine Logs, Zweck unklar

---

## 8. Speicher & Ressourcen

| Ressource | Wert | Status |
|-----------|------|--------|
| Disk (/) | ~182G/301G (63%) | ✅ ~107G frei |
| RAM | ~8.6G/30G (28%) | ✅ ~22G frei |
| Mem0 Memories | 1160 Einträge | ✅ Aktiv (hermes_memories_v2) |
| ShadowLogger | 170+ Einträge | ✅ Aktiv |
| Alert-Speicher | 883+ Dateien | ⚠️ Aufräumen empfohlen |

---

## 9. Offene Risiken

| ID | Risiko | Severity | Status |
|----|--------|----------|--------|
| R1 | Rebel permanent quarantined (MOT=2, isoliertes Netz) | NIEDRIG | Bewusst |
| R2 | trading-guardian Zweck ungeklärt | NIEDRIG | Zu dokumentieren |
| R3 | Alert-Speicher (883+ Dateien) wächst unkontrolliert | NIEDRIG | Rotation einführen |
| R4 | Dual Script-Repos (/opt/data vs. Projekt) | MITTEL | deploy_cron_scripts.sh als Sync-Tool |
| R5 | MCP Paper: keine API-Keys, nur public endpoints | KEINES | Bewusst (dry_run=true) |
| R6 | FreqAI-Rebel Netzwerk-Isolation | NIEDRIG | Kein ki-fabrik Zugriff |

---

## 10. Changelog

| Datum | Phase | Änderung |
|-------|-------|----------|
| 2026-05-30 | **1–6** | Heartbeat, FleetRisk, Signal-Bridge, Log-Rotation, RiskGuard, Standby-Monitor, Config-Diff, Auto-Params |
| 2026-05-30 | **Final** | Selbstheilungs-Level v1 erreicht. 33 Crons aktiv. |
| 2026-06-01 | **Stabilisierung** | Fleet-Idle-Diagnose, FleetRisk Phase 2-4, MCP+ShadowLogger Verifizierung, Permission-Drift-Lockdown |
| 2026-06-01 | **Recovery** | ai-hedge-trigger Orchestration Fix, Cron-Failure-Repair, Hermes Scheduler Recovery |
| 2026-06-02 | **Migration** | MCP Server: custom bitget_mcp_server.py → npm bitget-mcp-server v1.1.0 (read-only) |
| 2026-06-02 | **Fixes** | FleetRisk Cursor Fix (host_dbs), daily-backup PermissionError-tolerant, signal heartbeat unified |
| 2026-06-02 | **Automation** | permission_autopilot.sh + git_guard.sh hinzugefügt; portfolio_rebalancer momentum-Bot entfernt |
| 2026-06-02 | **State** | deploy_cron_scripts.sh pipefail-Bug behoben; current-operational-state.md aktualisiert |

---

*Letzte Aktualisierung: 2026-06-02 — synthetisiert aus Kontext 2026-06-01/02*
*Nächstes Update: nach der nächsten Phase oder bei kritischer Systemänderung*

