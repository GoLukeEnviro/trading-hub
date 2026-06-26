# Trading Hub — Comprehensive Code & Project Audit

**Date:** 2026-06-22  
**Analyst:** Hermes Meta-Orchestrator (L0 read-only audit)  
**Repository:** `github.com/GoLukeEnviro/trading-hub` (private)  
**HEAD:** `3759352` (main)  
**Methodology:** Static analysis (ruff), automated secret scanning, subagent deep-dives, architecture review against documented ADRs  
**Scope:** 556 tracked Python files, 138,493 LOC, 3,176 tracked files total  

---

## 1. Projektübersicht

### 1.1 Tech-Stack

| Layer | Technology | Version / Notes |
|-------|-----------|-----------------|
| **Language** | Python | ≥3.11 (PEP 668 enforced) |
| **Package Manager** | uv | Lockfile present at root and ai-hedge-fund-crypto |
| **Linting** | ruff 0.15.x | E, F, W, I, B, SIM, RUF rules |
| **Testing** | pytest + pytest-cov | 20 test files in `tests/`, 10 in `self_improvement_v2/` |
| **Type Checking** | mypy | Cache present (partial adoption) |
| **Execution Engine** | Freqtrade | Docker containerized fleet, dry-run only |
| **Signal Generation** | ai-hedge-fund-crypto | LLM agents (OpenAI, Groq, Gemini, Anthropic, Ollama) |
| **LLM Inference** | Ollama (local) | hermes-green + green-ollama containers |
| **Vector DB** | Qdrant | green-qdrant container (Mem0 backend) |
| **Memory** | Mem0 | green-mem0 container |
| **Reverse Proxy** | Caddy | network_mode: host |
| **Self-Improvement** | SI v2 (custom) | 38 sub-modules, observation loop |
| **Audit Trail** | ShadowLock | JSONL append-only (not yet tamper-evident) |
| **Dashboard** | Flask (single-file) | dashboard.py :5000 |
| **Container Runtime** | Docker Compose | 12+ services, socket proxy via tecnativa |
| **CI** | GitHub Actions | 3 workflows (si-v2-offline-smoke, main-gate, si-v2-phase2-proposal-gate) |

### 1.2 Architekturdiagramm (Text)

```
┌──────────────────────────────────────────────────────────────────┐
│                    SIGNAL LAYER                                   │
│  ┌──────────────────┐     hermes_signal.json                       │
│  │ ai-hedge-fund-   │ ─────────────────────────────┐               │
│  │ crypto (:8410)   │                              │               │
│  └──────────────────┘                              │               │
│                          ┌───────────────────────┐│               │
│                          │ Primo API (:8080)      ││               │
│                          │ + LLM Signal Filter    ││               │
│                          └─────────┬─────────────┘│               │
│                                    │               │               │
├────────────────────────────────────────────────────┼───────────────┤
│                    SAFETY LAYER                     │               │
│                                    ▼               ▼               │
│  ┌──────────────┐  primo_gate  ┌──────────┐   ┌──────────────┐    │
│  │ Kill Switch  │────────────▶│ Bridge   │──▶│ ShadowLock   │    │
│  │ (JSON atomic)│              │ (poll)   │   │ (JSONL audit)│    │
│  └──────────────┘              └──────────┘   └──────────────┘    │
│         ▲                                                       │
│         │ (is_kill_active / is_emergency)                         │
│         │ (SINGLE enforcement point: primo_signal.py)            │
├──────────────────────────────────────────────────────────────────┤
│                    EXECUTION LAYER (dry-run)                      │
│                                                                  │
│  ┌────────────┐ ┌──────────────┐ ┌─────────────┐ ┌───────────┐  │
│  │ FreqForge  │ │ Regime-Hybrid│ │ Canary      │ │ FreqAI     │  │
│  │ (:8086)    │ │ (:8085)      │ │ (:8081)     │ │ Rebel      │  │
│  │ FreqForge_ │ │ RegimeSwitch │ │ FreqForge_  │ │ RebelLiq.  │  │
│  │ Override   │ │ Hybrid_v7_v04│ │ Override    │ │ + RebelXGB │  │
│  └────────────┘ └──────────────┘ └─────────────┘ └───────────┘  │
├──────────────────────────────────────────────────────────────────┤
│                    SI v2 OBSERVATION LAYER                        │
│                                                                  │
│  ┌──────────────┐   ┌───────────┐   ┌──────────┐   ┌─────────┐  │
│  │ ActiveCycle  │──▶│ Measurement│──▶│ Fleet    │──▶│ Shadow  │  │
│  │ Runner (6h)  │   │ Ledger    │   │ Analyzer │   │Proposal │  │
│  └──────────────┘   └───────────┘   └──────────┘   └─────────┘  │
│       │                                                          │
│       ▼                                                          │
│  ┌──────────────┐   ┌───────────┐   ┌──────────┐                │
│  │ Rainbow §5   │   │ Approval │   │ Shadow   │                │
│  │ (read_only)  │   │ Gate     │   │ Logger   │                │
│  └──────────────┘   └───────────┘   └──────────┘                │
│                                                                  │
│  Controller: PAUSED / L3_REPOSITORY_ONLY / HUMAN_ONLY merge     │
├──────────────────────────────────────────────────────────────────┤
│                    CONTROL / OBSERVABILITY                        │
│  ┌────────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ Dashboard  │  │ Hermes   │  │ Watchdog │  │ Docker Socket│  │
│  │ (:5000)    │  │ Green     │  │          │  │ Proxy        │  │
│  └────────────┘  └──────────┘  └──────────┘  └──────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### 1.3 Repository-Struktur

```
trading-hub/                          (monorepo, 3.0 GB)
├── self_improvement_v2/              (83K LOC) SI v2 observation loop — 38 sub-modules
│   └── src/si_v2/                   (main source: adapters, analysis, proposal, scoring, etc.)
├── orchestrator/                    (32K LOC) control plane, cron, alerts, backups (63MB)
│   └── scripts/                     operational scripts (pipeline, watchdog, healthcheck)
├── ai-hedge-fund-crypto/            (30K LOC) LLM signal generation (uv.lock)
│   └── docker/                      containerized HTTP service
├── Agenten_Auto_Trade/              (27K LOC) autonomous agents — LEGACY (not in compose)
├── freqtrade/                       (21K LOC) Freqtrade fleet configs + strategies
│   └── bots/                        freqforge, regime-hybrid, canary, rebel, momentum(mvs,rsi,fomo)
├── Polymarket-BTC-15-Minute/       (13K LOC) standalone repo — EXPERIMENTAL
├── weatherhermes_persistent/        (11K LOC) weather bot — separate concern
├── bridge/                          (392 LOC) signal bridge (Primo → Freqtrade)
├── primo/                           (694 LOC) LLM signal filter + API
├── shadowlock/                      (1,240 LOC) audit blackbox
├── dashboard.py                     (1,746 LOC, 62KB) Flask dashboard
├── tests/                           (20 files) contract tests
├── docs/                            (9.1M, 35+ subdirs) extensive documentation
├── docker-compose.yml               (369 lines) 12+ services
└── pyproject.toml                   root tooling deps (fastapi, httpx, pydantic, pyyaml)
```

---

## 2. Aktueller Stand — Fertigstellungsgrade je Modul

| # | Modul | LOC | Fertigstellungsgrad | Status | Begründung |
|---|-------|-----|---------------------|--------|-----------|
| 1 | **SI v2 Core** (self_improvement_v2) | 83,731 | **90%** | 🟢 Production-ready (observation) | 38 sub-modules, clean code, proper dry_run isolation, approval gate, scoring. Missing: real adapter activation (gated), full proposal→deployment cycle (controller PAUSED). |
| 2 | **Freqtrade Fleet** | 21,496 | **85%** | 🟢 Stable (dry-run) | 4 active bots with healthchecks, atomic signal delivery. Missing: non-root containers, env-var credentials, strategy test coverage. |
| 3 | **Kill Switch** | 285 | **85%** | 🟡 Functional with gaps | Atomic JSON state, mtime cache, 3 modes. Missing: fail-CLOSED consumer, defense-in-depth, fsync, read-path race fix. |
| 4 | **Orchestrator** | 32,027 | **80%** | 🟡 Mature but rough | Cron pipelines, watchdog, Telegram alerts. Missing: 129 broad exception handlers, 8× shell=True, 25 bare excepts, hardcoded credentials. |
| 5 | **Bridge** | 392 | **90%** | 🟢 Clean | Atomic writes, pair allowlist, graceful shutdown. Missing: thread-safe _state dict, char validation on pair→filename. |
| 6 | **Primo** | 694 | **85%** | 🟡 Solid | LLM fail-safe veto, input validation. Missing: unit tests, blocking LLM call in event loop. |
| 7 | **ShadowLock** | 1,240 | **70%** | 🟡 Incomplete | Functional append-only. Missing: hash chaining (NOT tamper-evident), seq-write-after-log race, per-write subprocess overhead. |
| 8 | **Dashboard** | 1,746 | **75%** | 🟡 Works, no auth | Flask single-file, SSTI-safe, no SQL injection. Missing: authentication, no tests, hardcoded paths, no tests. |
| 9 | **ai-hedge-fund-crypto** | 29,716 | **80%** | 🟢 Stable | LLM factory with retries, dockerized. Missing: blocking /trigger endpoint, no timeout on main analysis, fragile stdout parsing. |
| 10 | **Agenten_Auto_Trade** | 27,326 | **30%** | 🔴 Legacy/Dead | Not in docker-compose, no vcs lockfile, all deps unpinned. Effectively archived research code. |
| 11 | **Polymarket bots** | 14K | **20%** | 🔴 Experimental | Standalone repos, not integrated, broken requirements.txt encoding. |
| 12 | **Freqforge** | 1,290 | **95%** | 🟢 Stable | Active FreqForge_Override bot with healthcheck. |
| 13 | **FreqForge-Canary** | 398 | **95%** | 🟢 Stable | Canary deployment of same strategy. |
| 14 | **Tests** | 2,995 | **60%** | 🟡 Growing | 20 root tests + 10 SI v2 tests. Coverage report GREEN (2026-06-22). Missing: bridge, primo, dashboard, strategy tests. |
| 15 | **CI/CD** | — | **55%** | 🟡 Partial | 3 GitHub workflows cover SI v2 + main gate. Missing: fleet, docker-compose, strategy, dashboard CI. |
| 16 | **Documentation** | 9.1M | **85%** | 🟢 Excellent | 35+ doc subdirs, ADRs, runbooks, gap reports, phase tracking. Minor drift in some operational-state references. |

**Gesamtreifegrad (Production-Readiness): ~45–50%**  
**Gesamtreifegrad (Autonomie/Self-Improvement): ~60%**  
**Gesamtreifegrad (Observation & Audit): ~75%**

---

## 3. Risiken und Architektur-Drift

### 3.1 Kritische Sicherheitsrisiken

| ID | Schwere | Risiko | Pfad | Impact | Lösungsvorschlag |
|----|---------|--------|------|--------|-------------------|
| **S-1** | 🔴 CRIT | **Kill Switch FAIL-OPEN on import error** | `freqtrade/shared/primo_signal.py:34-46` | Wenn kill_switch.py fehlt/gestört ist, werden Trades nicht blockiert. Safety-Kritisch. | `return True` bei Import-Fehler (fail-CLOSED). Zweiter Kill-Switch-Check in `trading_pipeline.py`. |
| **S-2** | 🔴 CRIT | **Hartkodierte Freqtrade-Passwörter in git** | `orchestrator/scripts/drawdown_guard.py:46,55,64,74` | 4 API-Passwörter im Quellcode, pushed nach GitHub. Mittlerweile Rotations-Checklist existiert, aber Werte noch in Historie. | Env-Variablen, `git filter-repo` zur Bereinigung der Historie, Rotation. |
| **S-3** | 🔴 CRIT | **Plaintext JWT Secrets & Passwörter in ~15 Config-Dateien** | `freqtrade/bots/*/config*.json`, `freqforge/user_data/config.json` | JWT-Secrets (64 hex) + API-Passwörter (48 hex) im Klartext. Gitignored aber auf Platte lesbar. | `${ENV_VAR}` Substitution in Freqtrade-Configs, Secret-Store (Docker Secrets, Vault). |
| **S-4** | 🟠 HIGH | **ShadowLock NICHT manipulationssicher** | `shadowlock/shadowlock_writer.py:202-214`, `shadowlock_indexer.py:176` | Keine Hash-Verkettung (`prev_hash`). Angreifer können JSONL-Zeilen bearbeiten und Hash neu berechnen. | Hash-Chaining (`prev_entry_sha256`) + Verifikation bei Ingest. |
| **S-5** | 🟠 HIGH | **Kill Switch TOCTOU Race im Read-Path** | `kill_switch.py:136-148` | `load_kill_state()` schreibt NORMAL bei abgelaufenem auto_clear_at. Kann EMERGENCY überschreiben. | Auto-Clear nur im Writer/Cron-Pfad, nicht im Read-Path. |
| **S-6** | 🟠 HIGH | **hermes-green Container mit vollem Docker-Socket + Host-FS-Zugriff** | `docker-compose.yml:78-80` | Mountet `/var/run/docker.sock` (direkt, nicht über Proxy), `/home/hermes/projects:rw`, SSH-Keys. Container-Escape möglich. | Socket-Proxy nutzen, RW-Mount einschränken, SSH-Mount entfernen. |
| **S-7** | 🟠 HIGH | **Dashboard ohne Authentifizierung, bindet 0.0.0.0:5000** | `dashboard.py:1747` | Jeder im Netzwerk sieht Fleet-Trade-Daten, PnL, Docker-Container-Status. | Basic-Auth / Token-Auth über Caddy Reverse-Proxy. |
| **S-8** | 🟡 MED | **129 breite Exception-Handler, 25 bare except** | `orchestrator/` (watchdog, autopilot, healthcheck) | Maskiert echte Fehler. Der Watchdog `critical_event_watchdog.py` hat 9 bare excepts. | Typisierte Exception-Handler, zentrale Error-Logging-Pipeline. |
| **S-9** | 🟡 MED | **SHARED_CONSTANTS.py: fehlender `import os`** | `freqtrade/shared/SHARED_CONSTANTS.py:29-30` | `os.path.join()` ohne Import. Modul crasht bei Import. Aktuell nicht importiert (toter Code), aber latenter Bug. | `import os` hinzufügen oder Modul entfernen, falls ungenutzt. |
| **S-10** | 🟡 MED | **Auto-Params Health Report zeigt `dry_run: false`** | `orchestrator/state/auto_params/auto_params_health.json:15` | Irreführende Zustandsmeldung — Fleet ist dry-run-only. | Reporter reparieren: tatsächlichen dry_run-Wert aus Bot-Config lesen. |

### 3.2 Architektur-Drift gegenüber Soll-Vorgaben

| Drift | Dokumentiert in ARCHITECTURE.md | Ist-Zustand | Bewertung |
|-------|----------------------------------|-------------|-----------|
| **Kill Switch Enforcement** | "primo_gate_allows" als Gate zwischen Bridge und Fleet | Nur `primo_signal.py` prüft — Single Point of Failure. `trading_pipeline.py` hat keinen Check (defense-in-depth fehlt). | ⚠️ Moderate Drift — Gate existiert, aber Redundanz fehlt |
| **ShadowLock Tamper-Evidence** | "append-only JSONL Audit" | Append-only ja, aber KEINE Hash-Verkettung, KEINE Ingest-Verifikation | ❌ Signifikante Drift — Kernanforderung nicht erfüllt |
| **SI v2 Controller** | State Machine: PAUSED → QUEUE → ACTIVE → BLOCKED | PAUSED korrekt, aber Stage B Isolation (dedizierter Unix-User) nicht implementiert | ✅ Konform mit Dokumentation (Stage B explizit als "future" markiert) |
| **Docker Ownership** | ADR-2026-06-10: Canonicalize ownership | 5 von 12 Containern mit `container_name`, andere laufen mit Docker-generierten Namen | ⚠️ Partielle Drift — teilweise kanonisiert |
| **Non-Root Container** | Security-Hardening (Phase 2.2 target) | Alle Freqtrade-Container laufen als root (Default) | ❌ Nicht implementiert (Phase 2.2 pending) |
| **SI v2 Scoring Gate** | "13/10 (2026-06-16)" | Walk-Forward Net Metrics als PR #271 gemerged. Scoring-eligible cycles: 4/10 benötigt | ✅ Konform — awaiting scheduled cycles |

### 3.3 SOLID-Prinzipien-Bewertung

| Prinzip | Bewertung | Beobachtung |
|---------|-----------|-------------|
| **Single Responsibility** | ⚠️ Partial | SI v2: excellent module separation (38 modules). Dashboard.py: 62KB single file violates SRP. |
| **Open/Closed** | ✅ Good | SI v2 adapter pattern (dry_run_stub vs real adapters), scoring policy with pluggable thresholds. |
| **Liskov Substitution** | ✅ Good | FreqtradeAdapter protocol consistently implemented by dry_run_stub and real_freqtrade_adapter. |
| **Interface Segregation** | ⚠️ Partial | SI v2 adapters implement clean interfaces. Bridge has mixed HTTP + polling + file-writing concerns. |
| **Dependency Inversion** | ✅ Good | SI v2 depends on abstractions (adapter protocols), not concretions. config/gate.py enforces env-var gating for real adapters. |

---

## 4. Hidden Features & Legacy-Code

### 4.1 Tote / Inaktive Module

| Modul | Status | Risiko | Pfad |
|-------|--------|--------|------|
| **Agenten_Auto_Trade/** (27K LOC) | 🔴 Legacy — nicht in docker-compose, eigene docker-compose.yml | Niedrig (inaktiv), aber veraltet mit unpinned Dependencies | `/Agenten_Auto_Trade/` |
| **Momentum Bot** | DECOMMISSIONED per docs | 🟡 Mittel — Config mit Klartext-JWT/Passwörtern auf Platte | `freqtrade/bots/momentum/` |
| **MVS Bot** | NOT_DEPLOYED per docs | 🟡 Mittel — JWT-Secret als Plaintext `"dry-run-mvs-temp-key-change-in-production"` | `freqtrade/bots/mvs/` |
| **RSI Bot** | Nicht in docker-compose, vermutlich decommissioned | 🟡 Mittel — Config mit Secrets | `freqtrade/bots/rsi/` |
| **FOMO Phase 3** | Stub — Entry/Exit-Logik unimplementiert | Niedrig (deployed=nie handelnd) | `freqtrade/bots/fomo-phase3/user_data/strategies/FOMO_Phase3_v0.py` |
| **Polymarket-BTC-15-Min** | Standalone Repo, nicht integriert | Niedrig (isoliert) | `Polymarket-BTC-15-Minute-Trading-Bot/` (eigenes .git) |
| **polymarket-fadi/** | Minimal, experimentell | Niedrig | `polymarket-fadi/` |
| **weatherhermes_backup/** | Backup eines älteren Weather-Bot | Niedrig | `weatherhermes_backup/` |
| **weatherbot/** | 368 LOC, separater Concern | Niedrig | `weatherbot/` |

### 4.2 Toter Code in Aktiven Modulen

| Artifact | Typ | Pfad |
|----------|-----|------|
| `signal_bridge.py` | Deprecated shim (2026-05-21) | `orchestrator/scripts/signal_bridge.py:3,16` |
| `SHARED_CONSTANTS.py` | Defekt (fehlender `import os`), niemand importiert es | `freqtrade/shared/SHARED_CONSTANTS.py` |
| `fleet_risk_manager.py.bak.phase2` | Tracked backup file | `freqtrade/shared/fleet_risk_manager.py.bak.phase2` |
| 52 Strategie-Dateien, davon nur 4 aktiv | Orphaned strategies | `freqtrade/bots/regime-hybrid/user_data/strategies/` (41 Dateien, 1 aktiv) |
| `RegimeSwitchingHybrid_v9_1_Sentient.py` | Unvollständig (F821: `Trade` undefined) | `freqtrade/bots/regime-hybrid/user_data/strategies/` |
| `ghostbuster.py` | "Dangerous actions REMOVED from v1" — investigieren was entfernt wurde | `orchestrator/scripts/ghostbuster.py:18` |

### 4.3 TODO/FIXME/HACK Marker

| Pfad | Marker | Inhalt |
|------|--------|--------|
| `freqtrade/bots/fomo-phase3/.../FOMO_Phase3_v0.py:44` | TODO | "Replace this docstring with your strategy description" |
| `freqtrade/bots/fomo-phase3/.../FOMO_Phase3_v0.py:78` | TODO | "Add your FOMO / OI / Funding indicators here" |
| `freqtrade/bots/fomo-phase3/.../FOMO_Phase3_v0.py:99` | TODO | "Implement entry logic" |
| `freqtrade/bots/fomo-phase3/.../FOMO_Phase3_v0.py:118` | TODO | "Implement exit logic" |
| `Polymarket-BTC-15-Minute/.../polymarket_client.py:155` | TODO | "Implement actual market search" |
| `orchestrator/scripts/rebel_30m_check.py:6` | FIX-2026-06-06 | "bind-mount switch" |
| `orchestrator/scripts/signal_bridge.py:3` | DEPRECATED | 2026-05-21 |

> **Bemerkung:** SI v2 (83K LOC) hat **0 TODO/FIXME/HACK Marker** — bemerkenswert sauber.

### 4.4 Unbeabsichtigte Konfigurationsoptionen / Feature-Flags

| Feature | Pfad | Status |
|---------|------|--------|
| `SI_V2_ENABLE_REAL_ADAPTERS` | `self_improvement_v2/src/si_v2/config/gate.py` | Env-Gate für reale Adapter (aktuell `0`) |
| `MCP_DRY_RUN = True # HARDCODED` | `trading_pipeline.py:54` | Hardcoded dry-run enforcement |
| `HERMES_DASHBOARD_INSECURE: 1` | `docker-compose.yml:71` | Deaktiviert Dashboard-Sicherheit |
| `HERMES_METRICS.json` | Root-Level (113KB) | Automatische Metriken-Datei (30K+) |

---

## 5. Code-Qualitäts-Metriken

### 5.1 Ruff Lint-Statistik

**1581 Fehler in 556 Python-Dateien** (707 auto-fixable)

| Regel | Count | Kategorie |
|-------|-------|-----------|
| B007 (unused-loop-variable) | 9 | Bug-Risk |
| F821 (undefined-name) | 6 | **Runtime Crash** |
| RUF002 (ambiguous-unicode-docstring) | 6 | Style |
| RUF013 (implicit-optional) | 6 | Type-Safety |
| RUF100 (unused-noqa) | 5 | Style |
| F601 (multi-value-repeated-key) | 4 | **Potential Bug** |
| F811 (redefined-while-unused) | 3 | Bug-Risk |
| SIM114 (if-with-same-arms) | 3 | Simplification |
| SIM117 (multiple-with-statements) | 3 | Style |
| B009 (get-attr-with-constant) | 1 | Bug-Risk |
| B905 (zip-without-explicit-strict) | 1 | Bug-Risk |
| W605 (invalid-escape-sequence) | 1 | Syntax |

**Kritisch:** F821 (6 undefined names) und F601 (4 duplicate dict keys) können Runtime-Fehler verursachen.

### 5.2 Testabdeckung

| Component | Tests | Coverage | Status |
|-----------|-------|----------|--------|
| Root `tests/` | 20 files | GREEN (2026-06-22 audit) | Contract tests for kill-switch, shadowlock, pipeline, compose, endpoint auth, resilience |
| SI v2 internal | 10 files | Partial | proposal_scoring, weight_proposal, validation_gates, episode_report |
| Bridge | **0** | None | `hermes_primo_bridge.py` ungetestet |
| Primo | **0** | None | `llm_signal_filter.py` ungetestet |
| Dashboard | **0** | None | Keine Tests |
| Strategies | **0** | None | Keine Strategie-Tests (52 Dateien) |
| Drawdown Guard | **0** | None | Hardcoded Credentials, kein Test |
| Trading Pipeline | **1** | Partial | `test_pipeline_regression.py` |

### 5.3 Exception Handling

| Component | bare `except:` | `except Exception` | Bewertung |
|-----------|---------------|---------------------|-----------|
| SI v2 (`src/si_v2/`) | **0** | 31 (alle in network/proof-Code) | ✅ Excellent |
| Orchestrator | **25** | ~104 | ❌ Verbesserungsbedarf |
| Freqtrade shared | 0 | 2 | ✅ Good |
| Bridge/Primo | 0 | 1 | ✅ Good |

---

## 6. Offene Aufgaben — Priorisierte Tabelle

### 6.1 Kritisch (P0)

| # | Aufgabe | Aufwand | Abhängigkeiten | Details |
|---|---------|---------|----------------|---------|
| P0-1 | **Kill Switch fail-CLOSED implementieren** | S | Keine | `primo_signal.py:34-46`: bei ImportError `return True` statt `return False`. Zweiter Check in `trading_pipeline.py` für Defense-in-Depth. |
| P0-2 | **Kill Switch auto-clear aus Read-Path entfernen** | S | P0-1 | `kill_switch.py:136-148`: TOCTOU Race. Auto-clear nur im Writer/Cron-Pfad. |
| P0-3 | **Hartkodierte Passwörter in drawdown_guard.py rotieren** | M | Keine | `orchestrator/scripts/drawdown_guard.py:46,55,64,74`: 4 API-Passwörter → Env-Vars. `git filter-repo` für Historie. |
| P0-4 | **Freqtrade Configs auf Env-Var Substitution migrieren** | L | P0-3 | ~15 Config-Dateien: JWT-Secrets und Passwörter → `${ENV_VAR}`. Cred-Rotation + Docker-Compose Env-Passing. |
| P0-5 | **hermes-green Docker-Socket-Mount einschränken** | S | Keine | `docker-compose.yml:78-80`: Direkter Docker-Socket → Socket-Proxy. `/home/hermes/projects:rw` einschränken. SSH-Mount entfernen. |

### 6.2 Hoch (P1)

| # | Aufgabe | Aufwand | Abhängigkeiten | Details |
|---|---------|---------|----------------|---------|
| P1-1 | **ShadowLock Hash-Chaining implementieren** | M | Keine | `shadowlock_writer.py`: `prev_entry_sha256` Verkettung + Ingest-Verifikation. |
| P1-2 | **Dashboard Authentifizierung hinzufügen** | M | Keine | `dashboard.py:1747`: Token-/Basic-Auth über Caddy. |
| P1-3 | **Bare excepts in Orchestrator beheben** | L | Keine | 25 bare `except:` → typisierte Handler (watchdog, autopilot, healthcheck). |
| P1-4 | **shell=True → list-form in Orchestrator** | L | P1-3 | 8× `subprocess.run(..., shell=True)` in `fleet_healthcheck.py`, `critical_event_watchdog.py`, etc. |
| P1-5 | **Decommissioned Bot-Configs mit Secrets bereinigen** | M | P0-4 | `momentum/`, `mvs/`, `rsi/`, `fomo-phase3/`: Config-Dateien mit Klartext-Credentials löschen oder sanitizen. |
| P1-6 | **F821 undefined-name Errors beheben** | S | Keine | `SHARED_CONSTANTS.py` (fehlender `import os`), `RegimeSwitchingHybrid_v9_1_Sentient.py` (fehlender `Trade` Import). |
| P1-7 | **auto_params_health.json dry_run-Report reparieren** | S | Keine | Falsch meldet `dry_run: false` — Reporter an tatsächlichen Bot-Config anpassen. |

### 6.3 Mittel (P2)

| # | Aufgabe | Aufwand | Abhängigkeiten | Details |
|---|---------|---------|----------------|---------|
| P2-1 | **Orphaned Strategies archivieren** | M | P1-5 | 48 von 52 Strategy-Dateien in `regime-hybrid/strategies/` sind inaktiv. → `archive/` verschieben. |
| P2-2 | **Non-Root Container für Freqtrade Fleet** | L | Keine | `docker-compose.yml`: `user:` directive zu allen Freqtrade-Containern hinzufügen. |
| P2-3 | **SHARED_CONSTANTS.py reparieren oder entfernen** | S | P1-6 | Entweder `import os` hinzufügen oder Modul löschen (nobody imports it). |
| P2-4 | **ShadowLock per-write subprocess eliminieren** | M | P1-1 | `shadowlock_writer.py:385-395`: `_trigger_indexer()` startet subprocess pro Write → Event-Queue / Bulk-Indexing. |
| P2-5 | **Caddy network_mode: host → bridge** | M | Keine | `docker-compose.yml:308`: Host-Netzwerk hat keine Isolation. |
| P2-6 | **Polymarket requirements.txt Encoding reparieren** | S | Keine | UTF-16 → UTF-8 Konvertierung. |
| P2-7 | **Ruff: 707 auto-fixable Errors beheben** | M | Keine | `ruff check . --fix` für automatische Korrekturen. Manuelle Fixes für F821, F601. |
| P2-8 | **Bridge thread-safety** | S | Keine | `_state` dict in `hermes_primo_bridge.py` mit Lock absichern. |

### 6.4 Niedrig (P3)

| # | Aufgabe | Aufwand | Abhängigkeiten | Details |
|---|---------|---------|----------------|---------|
| P3-1 | **DEPRECATED signal_bridge.py entfernen** | S | Keine | Legacy-Shim seit 2026-05-21. |
| P3-2 | **FOMO_Phase3_v0.py löschen oder implementieren** | M | Keine | 4 unimplementierte TODOs — Skeleton-Strategy. |
| P3-3 | **tracked .bak.phase2 Datei entfernen** | S | Keine | `fleet_risk_manager.py.bak.phase2` aus git löschen. |
| P3-4 | **Deprecated datetime APIs ersetzen** | S | Keine | `datetime.utcfromtimestamp`, `datetime.utcnow` → `datetime.now(UTC)`. |
| P3-5 | **Agenten_Auto_Trade/ archivieren** | S | Keine | Nicht aktiv, unpinned deps, kein compose-Referenz. |
| P3-6 | **Kill Switch fsync hinzufügen** | S | P0-1 | `kill_switch.py:176-181`: `os.fsync()` für power-loss safety. |
| P3-7 | **orphaned docs/context/ ledger-watchdog Dateien aufräumen** | S | Keine | 12+ `ledger-watchdog-20*.md` Dateien als untracked. |

---

## 7. Architektur-Diagramm: Soll vs. Ist-Vergleich

### Soll (ARCHITECTURE.md)

```
Signal → Bridge → Kill Switch (per-pair gate) → Freqtrade Fleet (dry-run)
                ↓
           ShadowLock (tamper-evident) → Audit Trail
                ↓
        SI v2 Observation Loop → Measurement Ledger → Shadow Proposal
                ↓ (Controller PAUSED, no mutations)
```

### Ist (mit Drift-Markierungen)

```
Signal → Bridge → Kill Switch (FAIL-OPEN on import error) ⚠️ → Freqtrade Fleet (dry-run)
                ↓ [no defense-in-depth] ⚠️
           ShadowLock (append-only, NOT tamper-evident) ❌ → Audit Trail
                ↓
        SI v2 Observation Loop → Measurement Ledger → Shadow Proposal
                ↓ [Controller PAUSED, mutations=0, correct] ✅
```

---

## 8. Empfehlungen — Nächste Schritte (priorisiert)

### Sprint 1: Sicherheit (P0) — Geschätzt 2–3 Tage

1. **Kill Switch fail-CLOSED** (P0-1) — Einzeiler in `primo_signal.py`,高风险 aber trivial zu beheben
2. **Kill Switch auto-clear Race** (P0-2) — Read-Path sauber halten
3. **drawdown_guard.py Credentials externalisieren** (P0-3) — 4 Passwörter → Env
4. **hermes-green Mounts einschränken** (P0-5) — Docker-Compose Änderung

### Sprint 2: Security Deepening (P1) — Geschätzt 3–5 Tage

5. **ShadowLock Hash-Chaining** (P1-1) — Kernanforderung der Audit-Trail-Spezifikation
6. **Dashboard Auth** (P1-2) — Caddy Basic-Auth Konfiguration
7. **Freqtrade Config Credential Migration** (P0-4) — Größter Aufwand, aber kritisch
8. **Decommissioned Bot Cleanup** (P1-5) — Secret-Sanitization

### Sprint 3: Code-Qualität (P2) — Geschätzt 2–3 Tage

9. **Ruff auto-fix** (P2-7) + manuelle F821/F601 Fixes (P1-6)
10. **Bare excepts → typed handlers** (P1-3)
11. **shell=True → list-form** (P1-4)
12. **Orphaned strategies archivieren** (P2-1)

### Sprint 4: Hardening (P2/P3) — Geschätzt 2–4 Tage

13. **Non-root containers** (P2-2)
14. **Caddy network isolation** (P2-5)
15. **Dead code cleanup** (P3-1 bis P3-5)

### Fortlaufend: SI v2 Phase 2.1 Abschluss

- Scoring Gate: 1/10 Scheduled Cycle.persist benötigt → 10 geplante 6h-Zyklen
- Phase 2.2 (Observability, Hardening, Self-Healing) kann nach Sprint 1–2 beginnen

---

## 9. Annahmen & Einschränkungen

| # | Annahme | Risiko |
|---|---------|--------|
| A-1 | `.env`-Dateien sind korrekt gitignored und enthalten keine Credentials im Tracking. | Niedrig — verifiziert via `git ls-files '*.env*'` |
| A-2 | Die Freqtrade-Bot-Configs in `freqtrade/bots/*/config*.json` sind ebenfalls gitignored (via `.gitattributes` `-diff`). | Mittel — `-diff` verhindert nur Diff-Anzeige, nicht Tracking. `.gitignore` muss ebenfalls passen. |
| A-3 | `dry_run: true` wird korrekt von allen 4 aktiven Bots erzwungen. | Mittel — ein `auto_params_health.json` meldet `false`. Sollte verifiziert werden. |
| A-4 | Die `SHARED_CONSTANTS.py` wird von niemandem importiert. | Niedrig — verifiziert via grep (nur Docstring-Self-Referenz). |
| A-5 | `ai-hedge-fund-crypto` LLM-Fabrik nutzt ausschließlich genehmigte Provider. | Niedrig — Provider-Liste codiert in `src/llm/__init__.py`. |
| A-6 | Der GAP-Report vom 2026-06-15 bezieht sich auf Commit `9ceeedd`, dieser Audit auf `3759352`. | Bestätigt — 350+ Commits dazwischen (hohe Velocity). |

---

## 10. Vergleich mit GAP-Report 2026-06-15

| GAP-Report-Empfehlung | Status (2026-06-22) | Fortschritt |
|------------------------|----------------------|-------------|
| Hartkodierte Credentials → Env | ⚠️ Partially addressed (rotation checklist exists, values still present) | ~30% |
| Pipeline/Fleet-Strategien ohne Tests | ❌ Unverändert — 0 Strategie-Tests | 0% |
| Kill-Switch wiring | ⚠️ Wired, aber FAIL-OPEN und TOCTOU-Race | ~50% |
| CI/CD Fleet-Abdeckung | ❌ Unverändert — nur SI v2 + main-gate | 0% |
| App-Auth auf HTTP-Endpoints | ❌ Dashboard weiterhin ohne Auth | 0% |
| Unmanaged Container Drift | ✅ Dokumentiert und teilweise behoben (#200, #204) | ~70% |
| Doc-Drift | ✅ Verbessert — Operational-State aktualisiert | ~80% |
| ShadowLock Deployment | ✅ Deployed (Writer + Indexer), aber nicht tamper-evident | ~60% |

---

*Status: **OK** (read-only audit completed)*  
*Operation Level: **L0** (inspection only, no mutations)*  
*Evidence: Static analysis (ruff), subagent deep-dives, architecture review, git history analysis*  
*Risk: No financial exposure — all bots in dry-run mode (`LIVE_FORBIDDEN`)*  
*Next Step: Sprint 1 (P0 Security Fixes) nach User-Approval*  
*Log Reference: This report saved to `docs/reports/comprehensive-code-project-audit-2026-06-22.md`*
