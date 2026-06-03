# Operational State — Trading Hub v2.x

**Stand:** 2026-05-30 20:50 UTC
**Quelle:** Live-Checks auf Host `Agent0`
**Status:** ✅ SELBSTREGENERIEREND — Self-Healing Level erreicht

> Dieses Dokument ist der offizielle System-Snapshot und dient als
> Geburtsurkunde für das selbstreparierende Trading Hub v2.x.
> Alle Phasen 1–6 sind abgeschlossen. Das System kann sich selbst
> überwachen, reparieren und anpassen.

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
│           │  Layer v1.0    │                    │
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
└─────────────────────────────────────────────────┘
```

---

## 2. Container-Fleet

| # | Container | Port | Status | Uptime | Strategie |
|---|-----------|------|--------|--------|-----------|
| 1 | `freqtrade-freqforge` | 8086 | ✅ Up | 44h | `FreqForge_Override` |
| 2 | `freqtrade-freqforge-canary` | 8081 | ✅ Up | 5d | `FreqForge_Override` |
| 3 | `freqtrade-regime-hybrid` | 8085 | ✅ Up | 12h | `RegimeSwitchingHybrid_v7_v04_Integration` |
| 4 | `freqai-rebel` | 8087 | ✅ Up | 3d | `RebelLiquidation + XGBoost` |
| 5 | `ai-hedge-fund-crypto` | 8410 | ✅ Healthy | 5d | Signal Generator |
| 6 | `hermes-green` | — | ✅ Up | 32h | Meta-Orchestrator |
| 7 | `green-mem0` | 8787 | ✅ Healthy | 32h | Memory-Stack |
| 8 | `green-ollama` | 11436 | ✅ Up | 32h | LLM-Inference |
| 9 | `green-qdrant` | 6333 | ✅ Up | 32h | Vector-DB |
| 10 | `hermes-mem0-local-api` | 8787 | ✅ Healthy | 5d | Fallback Memory |
| 11 | `freqtrade-webserver` | 8180 | ✅ Up | 2d | Web-UI |
| 12 | `caddy` | — | ✅ Up | 8d | Reverse Proxy |
| 13 | `claude-worker` | 5050 | ✅ Healthy | 7d | AI Worker |
| 14 | `hermes-ollama` | 11434 | ✅ Healthy | 11d | Local LLM |
| 15 | `hermes-qdrant` | 6333-4 | ✅ Healthy | 11d | Vector-DB |

**Nicht mehr aktiv:**
- `freqtrade-momentum` — **DECOMMISSIONED** seit 2026-05-24

---

## 3. Auto-Reparatur & Selbstheilung

### 3.1 Standby-Hermes Monitor
- **Script:** `hermes_standby_monitor.py`
- **Cron:** Alle 5 Minuten
- **Funktion:** Prüft Container-Health + Scheduler-Prozesse
- **Failover:** Auto-Restart bei Container-Down. Bei >10min Ausfall: Emergency-Fallback (kritische Scripts direkt)

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
- **Funktion:** Unabhängiges Signal-Audit + Health-Check

### 3.6 Log-Rotation
- **Script:** `log_rotation.py`
- **Cron:** Täglich 03:00 UTC
- **Limit:** Rotation bei >5MB, Cleanup bei >30d

---

## 4. Signal Pipeline

### Layer 1: Bridge (trading_pipeline.py)
- **Signal-Quellen:** `hermes_signal.json` (canonical), `latest/` (fallback), `shared/` (legacy)
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
- **Status:** ✅ AKTIV (v1.0)
- **Funktion:** Paper-Orders via Bitget MCP (immer dry_run=true)
- **Fix:** Shebang auf Hermes-venv umgestellt (ccxt im venv verfügbar)

### Layer 3: ShadowLogger
- **File:** `orchestrator/logs/shadow_decisions.jsonl`
- **Format:** Append-only JSONL, Schema v1.0
- **Inhalt:** Signal-Age, RiskGuard-Summary, Pair-Decisions, State-Writes
- **Einträge:** 170+, 276KB

### Layer 4: Bridge-Write
- **State-Files:** 5 Zielpfade (shared, momentum, regime-hybrid, freqforge, canary)
- **Atomic Write:** tmp+rename, chmod 644

---

## 5. Safety & Risk Management

### 5.1 State Files (alle aktiv)

| Datei | Pfad | Update | Inhalt |
|-------|------|--------|--------|
| `fleet_risk_state.json` | `freqtrade/shared/` | Echtzeit | Equity, Drawdown, Open Trades |
| `consec_loss_state.json` | `orchestrator/state/` | via Optimizer | Loss-Streak-Analyse |
| `drawdown_state.json` | `orchestrator/state/` | via drawdown_guard | Drawdown-Schutz |
| `riskguard_health.json` | `orchestrator/state/riskguard/` | via RiskGuard | Signal-Audit |
| `hermes_heartbeat.sqlite` | `orchestrator/state/` | via Heartbeat | Bot-Health |
| `config_diff_health.json` | `orchestrator/state/config_diff/` | via Diff-Detektor | Config-Drift |
| `auto_params_health.json` | `orchestrator/state/auto_params/` | via Auto-Params | Parameter-Anpassungen |
| `hermes_health.json` | `orchestrator/state/standby/` | via Standby | Hermes-Health |

### 5.2 Bot-Konfiguration

| Bot | dry_run | MOT | Stake | Strategie |
|-----|---------|-----|-------|-----------|
| FreqForge | ✅ True | 5 | 100 | `FreqForge_Override` |
| Canary | ✅ True | 3 | 50 | `FreqForge_Override` |
| Regime-Hybrid | ✅ True | 5 | 50 | `RegimeSwitchingHybrid_v7_v04_Integration` |
| Rebel | ✅ True | 2 | 50 | `RebelLiquidation + XGBoost` |

### 5.3 Fleet Performance (kumuliert)

| Bot | Trades | PnL | WR% | PF | Open |
|-----|--------|-----|-----|----|------|
| FreqForge | 52 | +7.96 | 86.3 | 1.25 | 1 |
| Regime-Hybrid | 43 | -7.10 | 76.7 | 0.55 | 0 |
| Canary | 33 | +3.19 | 90.6 | 104.3 | 1 |
| Rebel | 100 | -5.76 | 25.0 | 0.18 | 0 |
| **Fleet** | **228** | **-1.71** | — | — | **2** |

---

## 6. Cron-Job-Übersicht

### 6.1 Hochfrequenz (≤15min)
| Job | Intervall | Funktion |
|-----|-----------|----------|
| `trading-pipeline` | */10min | Signal-Bridge + RiskGuard + MCP |
| `system-optimizer` | 5min | Fleet-Optimierung + Guard-States |
| `hermes-standby-monitor` | 5min | Health-Check + Auto-Restart |
| `fleetrisk-auto-params` | 15min | Dynamische Parameter |
| `FleetRisk equity updater` | 5min | Equity-Tracking |
| `heartbeat-writer` | 15min | Bot-Health-DB |

### 6.2 Mittelfrequenz (30min–2h)
| Job | Intervall | Funktion |
|-----|-----------|----------|
| `riskguard-service` | 30min | Unabhängiges Signal-Audit |
| `canary-position-monitor` | 30min | Canary-Positions-Überwachung |
| `drawdown-guard` | 30min | Drawdown-Schutz |
| `container-watchdog` | 30min | Container-Health |
| `autonomous-health-loop` | 30min | Autonome Health-Checks |
| `Fleet Report (4h)` | 240min | Telegram-Report |
| `signal-heartbeat` | */20min | Signal-Trigger |
| `smart-heartbeat` | */10min | Defensiver Signal-Trigger |

### 6.3 Niedrigfrequenz (≥2h)
| Job | Intervall | Funktion |
|-----|-----------|----------|
| `config-diff-detector` | 1h | Config-Drift-Prüfung |
| `ghostbuster` | 2h | Stale-Artifact-Cleanup |
| `fleet-auto-repair` | 2h | Auto-Reparatur |
| `mem0-watchdog` | 2h | Memory-Health |
| `Memory Backfill` | 2h | Memory-Recovery |
| `Heartbeat Intelligence` | 6h | Bot-Intelligence-Report |
| `cron-guardian` | 6h | Cron-Job-Health |
| `daily-heartbeat` | 24h | Täglicher Heartbeat |
| `daily-backup` | 24h (02:00) | Backup-Rotation |
| `log-rotation-daily` | 24h (03:00) | Log-Rotation |
| `portfolio-rebalancer` | wöchentlich | Portfolio- Rebalancing |
| `monthly-strategy-report` | monatlich | Strategie-Report |

**Gesamt:** 33 Cron-Jobs aktiv

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
└── ki-fabrik (172.18.0.0/24)
    ├── ai-hedge-fund-crypto (172.18.0.6) — Signal-Generator
    ├── freqtrade-freqforge — Bot
    ├── freqtrade-freqforge-canary — Bot
    ├── freqtrade-regime-hybrid — Bot
    ├── freqai-rebel — Bot
    ├── hermes-green (172.18.0.5) — auch auf ki-fabrik
    ├── claude-worker — AI Worker
    ├── hermes-mem0-local-api — Memory-API
    └── hermes-ollama/hermes-qdrant — Fallback AI
```

**Hermes-Container ist dual-homed:** Beide Netzwerke direkt erreichbar.
**Freqtrade-Container:** Nur auf `ki-fabrik` → nicht direkt von Hermes aus HTTP-erreichbar
**Heartbeat-Zugriff:** `docker exec` (einziger verlässlicher Pfad)

---

## 8. Speicher & Ressourcen

| Ressource | Wert | Status |
|-----------|------|--------|
| Disk (/) | 182G/301G (63%) | ✅ 107G frei |
| RAM | 8.6G/30G (28%) | ✅ 22G frei |
| Docker Images | 26.3 GB | ⚠️ 2.6 GB reclaimable |
| Docker Volumes | 24.9 GB | ⚠️ 2.6 GB reclaimable |
| Build Cache | 5.5 GB | 🔄 komplett reclaimable |
| Container | 16 up / 0 down | ✅ |

---

## 9. Offene Risiken

| ID | Risiko | Severity | Status |
|----|--------|----------|--------|
| R1 | Rebel permanent quarantined (MOT=2) | NIEDRIG | Bewusst |
| R2 | AVAX/NEAR/ARB/OP ohne X-Sentiment (conf 0.2) | NIEDRIG | Fehlende Datenquelle |
| R3 | Equity-History erst 2 Datenpunkte | NIEDRIG | Füllt sich mit Zeit |
| R4 | MCP Execution Layer: Kein echter Trade | KEINES | dry_run=true Hardcoded |
| R5 | Kein Telegram-Alarm bei Auto-Params | NIEDRIG | Phase 7 Kandidat |
| R6 | Kein Hermes-Selbst-Update-Mechanismus | NIEDRIG | Phase 7 Kandidat |

---

## 10. Changelog

| Datum | Phase | Änderung |
|-------|-------|----------|
| 2026-05-30 | **1** | Heartbeat Writer fix (Docker exec statt REST), Error-Jobs reset, AGENTS.md Korrektur (Momentum raus, Canary-Strategie fix) |
| 2026-05-30 | **2** | FleetRisk Cursor reaktiviert (23. Mai → 30. Mai), Signal-Bridge Diskrepanz analysiert (kein Bug), Log-Rotation implementiert |
| 2026-05-30 | **3** | Equity Protection rückgängig (Stakes 100%), Canary SHORTs geprüft (alle gewinnbringend geschlossen), Signal-Heartbeat v3 (docker exec) |
| 2026-05-30 | **4** | FleetRisk-Status verifiziert (alle State-Files aktiv), Backup-Cron reset, Operational State Update |
| 2026-05-30 | **5** | **MCP Execution Layer fix** (ccxt via Hermes-venv), ShadowLogger verifiziert (170 Einträge), **RiskGuard Service deployt** (eigenständig mit Health-Check) |
| 2026-05-30 | **6** | **Standby-Hermes Monitor** (5min, Auto-Restart), **Config-Diff-Detektor** (stündlich, Drift-Prüfung), **FleetRisk Auto-Params** (15min, 6 Regeln) |
| 2026-05-30 | **Final** | Dokumentation abgeschlossen. 33 Crons aktiv. Selbstheilungs-Level erreicht. |
| 2026-06-02 | Observation Runner | `orchestrator/scripts/observation_runner.py` implementiert (report_only, Lock/Heartbeat/State/Report/Eskalation) und mit 10 Tests verifiziert. |

---

*Erstellt von Hermes Orchestrator (deepseek-v4-flash) am 2026-05-30 20:50 UTC*
*Nächstes Routin-Update: nach der nächsten Phase oder bei kritischer Systemänderung*
