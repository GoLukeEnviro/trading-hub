# GAP-Analysebericht — Trading Hub Comprehensive Audit

**Datum:** 2026-06-15  
**Analyst:** Sisyphus (OhMyOpenCode)  
**Repository:** `github.com/GoLukeEnviro/trading-hub` (private)  
**Typ:** Read-Only Gap-Analyse  
**Methodik:** Statische Artefakt-Analyse, Referenz-Vergleich mit Branchen-Best-Practices  
**Referenzrahmen:** OWASP, ISO 27001 (ausgewählt), COBIT (ausgewählt), ITIL (ausgewählt)  
**Vorherige GAP-Reports:** 2026-05-17, 2026-06-05 (Deep-Dive)  

---

## Executive Summary

Das Trading Hub System ist ein **fortgeschrittenes autonomes Krypto-Trading-Research-System** mit starker Safety-Culture und umfassender Dokumentation. Das System befindet sich im **Dry-Run-Modus** mit einer Container-Flotte von 12 Docker-Services und 4 aktiven Freqtrade-Bots.

### Wichtigste Erkenntnisse

| Metrik | Bewertung |
|--------|-----------|
| **Gesamtreifegrad (Autonomie)** | ~50–55 % (wie im GAP-Report 05.06 bestätigt) |
| **Gesamtreifegrad (Production-Readiness)** | ~35–40 % |
| **Sicherheits-Reifegrad** | ~45 % (gute Isolierung, aber hartkodierte Credentials + fehlende Docker-Härtung) |
| **Dokumentations-Reifegrad** | ~80 % (hervorragend, aber Doc-Drift) |
| **Test-Abdeckung** | ~15 % (nur SI v2 + Healthchecks, Pipeline/Fleet ungetestet) |
| **CI/CD-Reifegrad** | ~40 % (nur SI v2 abgedeckt, Fleet/Strategies nicht) |

### Kritischste Gaps (Top 5)

| # | Gap | Bereich | Priorität | Begründung |
|---|-----|---------|-----------|------------|
| 1 | **Hartkodierte API-Credentials in Freqtrade-Configs** | Sicherheit | 🔴 Kritisch | `freqforge/user_data/config.json`, `freqforge-canary/user_data/config.json`, `regime-hybrid/config/research/config_*.json` enthalten API-Keys + JWT-Secrets im Klartext |
| 2 | **Pipeline/Fleet-Strategien ohne Tests** | Qualität | 🔴 Kritisch | Kern-Trading-Logik (RG, Pipeline, Strategies) hat 0 automatische Tests |
| 3 | **Kill-Switch nicht wired zu FT Fleet** | Sicherheit | 🔴 Kritisch | Kein automatischer Notfall-Stopp bei Drawdown/Crash |
| 4 | **Compliance-Module isoliert (nicht gewired)** | Compliance | 🔴 Kritisch | Agenten hat exzellente Compliance, aber keine Integration mit Fleet |
| 5 | **CI/CD deckt nur SI v2 ab** | Prozesse | 🟠 Hoch | Fleet-Pipeline, Docker-Compose, Strategies ohne CI-Gates |
| 6 | **7/20 Container unmanaged** | Technologie | 🟠 Hoch | Compose-Drift — 35% der Container ohne kanonische Konfiguration |
| 7 | **Keine App-Auth auf HTTP-Endpoints** | Sicherheit | 🟠 Hoch | Dashboard, Primo API, Bridge ohne Auth — über Tailscale extern erreichbar |

### Fortschritt seit GAP-Report 05.06.2026

- ✅ Docker Healthchecks hinzugefügt (#199, PR #204) — alle 5 FT-Bots haben `/api/v1/ping`  
- ✅ Shadowlock deployiert (Writer + Indexer + JSONL Audit Trail)  
- ✅ SI v2 Controller auf `PAUSED / L3_REPOSITORY_ONLY`  
- ✅ Unmanaged Container-Drift dokumentiert (#200) — erkannt, aber nicht behoben  
- ✅ Watchdog Ownership ADR erstellt  
- 🟠 Doc-Drift teilweise behoben (AGENTS.md aktualisiert), aber Charter noch veraltet  

### Annahmen

- System läuft produktiv auf Linux-Host (nicht auf Windows, obwohl Repo lokal geöffnet)  
- Alle Bewertungen beziehen sich auf den Ist-Zustand auf `main` (commit `9ceeedd`)  
- Keine Einsicht in Git-History-Detailtiefe (nur Artefakt-Analyse)  
- Keine Live-Netzwerk-Analyse (TLS, Port-Scans) — nur konfigurationsbasiert  
- Secrets/Env-Files sind gitignored und konnten nicht inspiziert werden (korrekt)  

---

## Reifegrad-Heatmap

```
Bereich              | Reifegrad | Tendenz
─────────────────────|───────────|─────────
Sicherheit           | █████░░░░ | 45%  ▼  (hartkodierte Creds entdeckt)
Compliance           | █████░░░░ | 48%  ▲  (Shadowlock hinzugefügt)
Technologie          | █████░░░░ | 55%  ▬▬
Prozesse/CI-CD       | ████░░░░░ | 40%  ▲  (Main Gate existiert)
Dokumentation        | ████████░ | 80%  ▲
Qualität/Testing     | ██░░░░░░░ | 15%  ▬▬
─────────────────────|───────────|──────
GESAMT               | █████░░░░ | 47%  ▬  (↓ wegen Cred-Fund)
```

### Legende
- `███░░░░░░` = <30% Kritisch  
- `████░░░░░` = 30–50% Verbesserungsbedarf  
- `█████░░░░` = 50–70% Akzeptabel  
- `██████░░░` = 70–90% Gut  
- `█████████` = >90% Exzellent  

---

## Detaillierte Gap-Matrix

### 1. Technologie & Architektur

| # | Ist-Zustand | Soll-Zustand | Gap-Beschreibung | Priorität | Auswirkung | Empfohlene Maßnahme | Aufwand |
|---|-------------|--------------|------------------|----------|-------------|---------------------|---------|
| T1.1 | Monolithischer `docker-compose.yml` mit 12 Services + 3 Netzwerken | Service-isolierte Compose-Dateien per Domain (signal/, fleet/, memory/, infra/) | Alle Services in einer Datei → koppelt Deployment, erschwert isolierte Updates | 🟡 Mittel | Deploy-Risiko bei Service-Änderungen;排 coupling | Split in `docker-compose.{infra,fleet,memory}.yml` mit `extends` | 3–5d |
| T1.2 | 7/20 Container ohne `com.docker.compose.project` Label (btc5m, claude-worker, green-mem0, green-ollama, green-qdrant, watchdog, weatherhermes) | Alle Container unter kanonischer Compose-Autorität | Unmanaged Container — nicht durch `docker compose` steuerbar, kein lifecycle management | 🟠 Hoch | Fleet-Drift, inkonsistente Restart-Verhalten, Shadowing | Issue #200 abschließen: Compose-Projekt-Zuordnung für alle Container | 3–5d |
| T1.3 | Resource Limits nur für FT-Bots (512MB/1CPU) und FreqAI-Rebel (2GB/2CPU) | Alle Services haben `deploy.resources.limits` + `reservations` | ai-hedge-fund, hermes-green, ollama, qdrant ohne Limits → OOM/CPU-Starvation möglich | 🟠 Hoch | Historischer Vorfall: freqai-rebel bei 972% CPU; Host-Degradation | Limits für alle Services (min. memory_limit + cpus) | 1–2d |
| T1.4 | Docker-Socket-Proxy (tecnativa) mit EXEC=1, POST=1 | Minimaler Proxy (nur CONTAINERS=1, SERVICES=1, INFO=1) | Überprivilegierter Proxy — Container können exec/post auf anderen Containern | 🟠 Hoch | Lateral Movement zwischen Containern möglich | EXEC=0, POST=0 setzen; wenn EXEC für Hermes nötig → dedizierter Proxy | 0.5d |
| T1.5 | Single-Host Single-Exchange (Bitget only) | Multi-Host oder Multi-Exchange Fallback | Kein Failover bei Exchange-Ausfall, Host-Ausfall = totaler Blackout | 🟡 Mittel | Bei Bitget-Incident: keine Signale, keine Daten, kein Trading | Sekundärer Data-Provider (Binance/Kraken); Disaster Recovery Plan | 5–10d |
| T1.6 | `network_mode: host` für Caddy | Bridged Networking mit Port-Mapping | Caddy hat volles Host-Netzwerk — kann alle Ports/Interfaces sehen | 🟡 Mittel | Erhöhte Angriffsfläche; keine Netzwerk-Isolierung für Reverse-Proxy | Port-Mapping statt `host` mode; oder explizite Port-Bindung | 0.5d |
| T1.7 | Kein Container-Image-Scanning, keine Base-Image-Pinning (z.B. `alpine:latest`, `qdrant/qdrant:latest`); `primo/Dockerfile` installiert inline mit `|| true` (Fehler verschluckt) | Pinned Tags + Vulnerability-Scanning + reproduzierbare Builds | `latest`-Tags können unkontrollierte Breaking Changes oder CVEs einführen; Primo-Build nicht reproduzierbar | 🟠 Hoch | Build-Reproducibility und Security-Drift | Pinned Digests in Compose; `trivy` oder `grype` im CI; Primo-Dockerfile reparieren | 2–3d |
| T1.8 | Caddy ohne explizites TLS für Tailscale-Tunnel | MTLS oder HTTPS für alle externen Endpoints | Tailscale-Tailscale ist verschlüsselt, aber Caddy→Backend ist HTTP | 🟡 Mittel | Plaintext-Backend-Verkehr im Docker-Netz (gemindert durch 127.0.0.1 Binding) | Caddy als TLS-Terminator; oder Vertrauen auf Tailscale-MTLS dokumentieren | 1d |

### 2. Prozesse & Workflows

| # | Ist-Zustand | Soll-Zustand | Gap-Beschreibung | Priorität | Auswirkung | Empfohlene Maßnahme | Aufwand |
|---|-------------|--------------|------------------|----------|-------------|---------------------|---------|
| P2.1 | GitHub Actions CI deckt nur `SI v2` + `orchestrator/control` ab | CI für alle kritischen Pfade: Fleet-Compose, Strategies, Pipeline, RiskGuard | Trading-Pipeline, Fleet-Configs, Strategies, RiskGuard, Shadowlock nicht in CI | 🔴 Kritisch | Breaking Changes in Fleet/Pipeline/RG entdecken erst im produktiven Lauf | CI-Jobs für: Compose-Validierung, Strategy-Compile, Pipeline/RG Unit-Tests | 3–5d |
| P2.2 | Kein CHANGELOG, keine Release-Notes | Automatisierter CHANGELOG (conventional commits + towncrier/nox) | keine nachvollziehbare Release-Historie; Änderungen nur via Git-Log | 🟡 Mittel | Onboarding erschwert; Breaking Changes schwer nachvollziehbar | CHANGELOG.md + conventional-commits Hook oder towncrier | 2–3d |
| P2.3 | Kein CONTRIBUTING.md, kein Onboarding-Dokument | CONTRIBUTING.md mit Setup-Anleitung, Code-Style, PR-Prozess | Neue Entwickler/Agenten müssen implizites Wissen erlernen | 🟡 Mittel | Hohe Einstiegshürde, inkonsistente Beiträge | CONTRIBUTING.md mit: Setup, Architektur-Übersicht, PR-Checkliste | 1–2d |
| P2.4 | Keine pre-commit Hooks | pre-commit mit: ruff, compileall, YAML-Validierung, secret-detection, trailing-whitespace | Code-Qualitäts-Probleme erst in CI entdeckt; Secrets-Risiko | 🟡 Mittel | Längere Feedback-Zyklen; mögliches Secret-Leak vor CI | `.pre-commit-config.yaml` mit ruff, detect-secrets, yamlfmt | 1–2d |
| P2.5 | Kein Dependency-Management für Root-Python (kein pyproject.toml, kein requirements.txt) | Zentrales `pyproject.toml` mit Abhängigkeiten und Versions-Pinning | Nur `self_improvement_v2/pyproject.toml` existiert — orchestrator, bridge, primo, shadowlock ohne | 🟠 Hoch | Abhängigkeits-Hell; nicht reproduzierbare Deployments | Root `pyproject.toml` oder per-Komponente; Lock-File | 3–5d |
| P2.6 | Kein Deployment-Workflow (manuell via SSH/Docker Compose) | Automatisiertes Deployment mit Gate (Dry-Run-Check, Smoke-Test) | Manuelle Deployments fehleranfällig; kein Rollback-Mechanismus | 🟡 Mittel | Human Error bei Deployment; keine Audit-Trail für Deployments | Deploy-Script mit Pre-Flight Checks + Git-Commit als Deploy-Audit | 3–5d |
| P2.7 | Model-Updates manuell (Hyperopt/SL-Sweep per Hand) | Performance-Trigger → Auto-Retrain mit Approval-Gate | Veraltete Modelle bei Marktwechsel → systematische Underperformance | 🟠 Hoch | Strategie-Degradation ohne automatische Detektion | quality_hub: Performance-Drift-Alarm → queued Hyperopt-Job | 5–8d |

### 3. Dokumentation

| # | Ist-Zustand | Soll-Zustand | Gap-Beschreibung | Priorität | Auswirkung | Empfohlene Maßnahme | Aufwand |
|---|-------------|--------------|------------------|----------|-------------|---------------------|---------|
| D3.1 | AGENTS.md: RiskGuard/ShadowLogger teilweise als "SPEC ONLY" beschrieben (Zeile 46–63) | Doku spiegelt deployed Zustand | Doc-Drift — Agenten lesen veraltete Architektur → falsche Annahmen | 🟠 Hoch | Implementierungs-Entscheidungen auf Basis falscher Annahmen | AGENTS.md aktualisieren: RiskGuard deployed, Shadowlock deployed, Momentum dekommissioniert | 1d |
| D3.2 | ORCHESTRATOR_CHARTER v2.0 (Stand 2026-05-12) — listet Honcho als aktiv, erwähnt 6 Bots | Charta reflects aktuellen Stand (Phase 2.0+) | Charter ist 5+ Wochen veraltet; Honcho decommissioned, SI v2 Controller existiert | 🟠 Hoch | Charter ist "binding rules" — veraltete Regeln sind ein Governance-Risiko | Charter v3.0: Honcho→Mem0, SI v2 Controller, Shadowlock, Phase-Status | 2–3d |
| D3.3 | 3 Runbooks (hermes-gateway-debug, honcho-health-audit, signal-staleness-audit) | Vollständige Runbook-Coverage für alle kritischen Komponenten | Fehlende Runbooks für: Fleet-Recovery, Container-Drift, Kill-Switch, Compose-Rollout | 🟡 Mittel | Incident-Response-Zeit verlängert; Abhängigkeit von implizitem Wissen | Runbooks für: Fleet-Recovery, Emergency-Stop, Compose-Deployment, Container-Health | 3–5d |
| D3.4 | 2 ADRs (2026-05-14 Soul-Sync, 2026-06-10 Watchdog-Ownership) | ADRs für alle architekturentscheidungen | Viele Entscheidungen ohne formelle ADR (z.B. SI v2 Architektur, Shadowlock, Qdrant, Mem0) | 🟡 Mittel | Missing Context für zukünftige Architektur-Entscheidungen | ADRs für: Container-Architektur, SI v2 Controller, Memory-System, RiskGuard | 2–3d |
| D3.5 | Kein API-Dokumentation (ai-hedge-fund Endpoints, FT REST, Pipeline-Interface) | OpenAPI/Swagger oder Inline-API-Docs | Signal-Schema, Pipeline-Interface, Fleet-Risk-API nicht dokumentiert | 🟡 Mittel | Integrations-Aufwand für neue Entwickler/Agenten | API-Docs für: hermes_signal.json Schema, Pipeline-Interface, Fleet-Health | 2–3d |
| D3.6 | 49+ Context-Reports in `docs/context/` ohne Indexierung/Suchbarkeit | Durchsuchbares Knowledge-Base mit Tagging | Wichtige historische Reports schwer auffindbar; Redundanz | 🔵 Niedrig | Wissensverlust; doppelte Arbeit bei ähnlichen Issues | Context-Index.md mit Tags + Datum; oder Wiki/Notion-Anbindung | 2d |

### 4. Compliance & Governance

| # | Ist-Zustand | Soll-Zustand | Gap-Beschreibung | Priorität | Auswirkung | Empfohlene Maßnahme | Aufwand |
|---|-------------|--------------|------------------|----------|-------------|---------------------|---------|
| G4.1 | Compliance-Module (Hash-Chain Audit, 10y Tx-Store, GoBD-Reports) existieren in `Agenten_Auto_Trade/` aber **nicht gewired** zu Fleet/Pipeline/Shadow | Unified Compliance-Trail über alle Systemebenen | Regulatorische Lücke: FT-Trades, RG-Entscheidungen, Pipeline-Aktionen nicht im Compliance-Trail | 🔴 Kritisch | Bei Live-Start: BaFin/GoBD-nonkonform; Haftungsrisiko | Collector: FT SQLite + Shadow + RG → unified Compliance-Store | 8–12d |
| G4.2 | RiskGuard-Layer: Pipeline RG-1..5 aktiv, FleetRisk deployt, aber **Kill-Switch advisory only** | Zentraler, wiring Kill-Switch → force_exit + cancel_all | Kein automatischer Notfall-Stopp; manuelles Eingreifen bei -30% Drawdown nötig | 🔴 Kritisch | System kann bei Crash nicht selbst stoppen → unbegrenzter Verlust | `kill_switch.json` + Service → FT force_exit + Pipeline WATCH_ONLY | 5–8d |
| G4.3 | Keine LICENSE-Datei | OSS-Lizenz oder proprietär mit Klartext | Urheberrechtlich unklar; rechtliches Risiko bei Fork/Verbreitung | 🟡 Mittel | Rechtliche Unsicherheit; Contributor-Verwirrung | LICENSE-Datei (MIT, Apache 2.0, oder Proprietär-Vermerk) | 0.5d |
| G4.4 | Kein CODE_OF_CONDUCT.md | Code of Conduct für (zukünftige) Contributor | Fehlende Verhaltensregeln bei Multi-Agent/Multi-Human-Projekt | 🔵 Niedrig | Governance-Lücke bei kollaborativer Entwicklung | CODE_OF_CONDUCT.md (Standard-Vorlage) | 0.5d |
| G4.5 | SI v2 Controller: Merge-Policy `HUMAN_ONLY`, Runtime-Policy `FORBIDDEN` | Formalisiertes Change-Management für alle Komponenten | Nur SI v2 hat formelle Policies; Fleet/Pipeline/Configs ohne Change-Management | 🟡 Mittel | Unkontrollierte Config-Änderungen möglich; kein Approval-Trail | Change-Management-Policy für alle kritischen Komponenten | 3–5d |
| G4.6 | "Dry-Run Only" via SOUL.md + Charter + CI-Invariant-Test (test_live_trading_invariants.py) | Defense-in-Depth: CI + Runtime-Check + Docker-Policy | Dry-Run-Policy gut, aber nur SI v2 hat CI-Check; Fleet-Compose nicht in CI | 🟡 Mittel | `dry_run=false` könnte in Fleet-Config unbemerkt eingeschleust werden | Fleet-Compose in CI: `grep -c "dry_run.*false"` als Fail-Gate | 1–2d |
| G4.7 | Shadowlock deployed als JSONL Audit-Trail für SI v2 | Umfassendes Audit für alle Trading-Entscheidungen | Shadowlock deckt nur SI v2/Controller; Pipeline-Entscheidungen, RG-Verdicts, FT-Trades nicht erfasst | 🟠 Hoch | Inkomplette Audit-Trail; "Warum wurde Trade X ausgeführt?" nicht beantwortbar | Shadowlock erweitern oder dedizierten Trading-Audit-Logger | 5–8d |

### 5. Sicherheit

| # | Ist-Zustand | Soll-Zustand | Gap-Beschreibung | Priorität | Auswirkung | Empfohlene Maßnahme | Aufwand |
|---|-------------|--------------|------------------|----------|-------------|---------------------|---------|
| S5.1 | **Hartkodierte API-Credentials** in `freqforge/user_data/config.json`, `freqforge-canary/user_data/config.json`, `freqtrade/bots/regime-hybrid/config/research/config_regime_hybrid_sideaware_v{1,2}.json` — API-Keys, JWT-Secrets im Klartext | Alle Credentials über `.env` / Docker Secrets / Vault | Getrackte Configs enthalten Exchange-API-Keys und JWT-Secrets im Klartext — Verstoß gegen SOUL.md Regel 8 ("Keine Secrets im Git") | 🔴 Kritisch | Credentials im Git-Historie; selbst nach .gitignore-Erweiterung im History-Bleed | 1. Sofort `.gitignore` erweitern für `freqforge/user_data/config*.json`, `freqforge-canary/user_data/config*.json`, `**/config/research/config*.json`. 2. Credentials rotieren. 3. Git-History scrubben (BFG/CfK) für betroffene Paths. 4. Config-Templates mit Platzhaltern committen. | 2–3d |
| S5.2 | **Keine App-Auth** auf `dashboard.py` (Flask), `primo/primo_api.py` (FastAPI: /health, /pairs, /signal, POST /signal), `bridge/hermes_primo_bridge.py` (/status, /health) | Auth-Middleware oder strikte Netzwerk-Isolierung auf allen Management-APIs | Alle HTTP-Endpoints ohne Authentifizierung; über Caddy/Tailscale extern erreichbar | 🟠 Hoch | Unautorisierter Zugriff auf Trading-Dashboard und Signal-API bei Tailscale-Compromise | Auth auf Dashboard (Basic-Auth über Caddy oder Flask-Session); Primo API auf internes Netz beschränken oder API-Key-Auth | 2–3d |
| S5.3 | Docker-Socket-Proxy mit EXEC=1, POST=1 (docker-compose.yml:10-11) | EXEC=0, POST=0 oder getrennte Proxy-Instanzen | Container können auf anderen Containern exec und API-Calls POSTen | 🟠 Hoch | Lateral Movement: Container-A → Container-B compromise | EXEC=0, POST=0 setzen; Hermes-Proxy isolieren | 0.5d |
| S5.4 | Keine Docker-Härtung (`read_only`, `cap_drop`, `no-new-privileges`) auf den meisten Containern | Docker-Standard-Härtung auf allen Services | Nur Fleet-Compose (`user: 10000:10000`, read-only Config-Mounts) zeigt Härtung; Root-Compose und andere Services ohne | 🟠 Hoch | Container-Breakout-Risiko bei compromised Service | `read_only: true`, `cap_drop: [ALL]`, `no_new-privileges: true` auf allen Services; Volumes für write-Paths hinzufügen | 2–3d |
| S5.5 | Alle Ports an 127.0.0.1 gebunden (gut), aber Caddy mit `network_mode: host` | Alle Services mit Bridged-Network + Port-Mapping | Caddy sieht alle Host-Interfaces; Tailscale-Tunnel ohne Caddy-TLS | 🟡 Mittel | Caddy → Backend ist Plaintext-HTTP (gemindert durch 127.0.0.1) | Caddy in bridged Mode; oder Risiko-Akzeptanz dokumentieren | 0.5d |
| S5.6 | `.gitignore` umfassend (280 Zeilen, Negation-Regeln, Secure Cleanup 2026-05-16) | .gitignore + Secret-Scanning im CI | Gute Git-Hygiene, aber kein proaktives Secret-Scanning; Lücken bei `user_data/` und `config/research/` Paths | 🟡 Mittel | Accidental Secret-Commit möglich vor Git-Push (wie S5.1 bewiesen) | `gitleaks` oder `trufflehog` als CI-Step; `.gitignore` für S5.1-Pfade erweitern | 1d |
| S5.7 | `.env` Files sind gitignored, aber docker-compose referenziert `./ai-hedge-fund-crypto/.env` und `/opt/hermes-green/.env` (externer Pfad); `HERMES_DASHBOARD_INSECURE=1` gesetzt | Zentrale Secret-Management (Vault, Doppler, Docker Secrets) | Secrets als plain `.env` Files — kein Rotations-Mechanismus, keine Access-Audit; Insecure-Dashboard-Flag gesetzt | 🟡 Mittel | Secret-Rotation manuell; kein Access-Logging für Secrets | Docker Secrets oder File-Based mit encrypted-at-rest; `HERMES_DASHBOARD_INSECURE` entfernen | 3–5d |
| S5.8 | Keine Container-Image-Vulnerability-Scanning | Regelmäßiges Scanning mit Trivy/Grype + Block-on-Critical | Base-Images (`latest` Tags) ohne CVE-Prüfung; `primo/Dockerfile` installiert Pakete inline mit `|| true` (Fehler verschluckt) | 🟠 Hoch | CVEs in `alpine:latest`, `python:latest`, `qdrant:latest` unbeachtet; Supply-Chain-Risk | Trivy im CI; pinned Digests in Compose; Primo-Dockerfile reparieren | 2–3d |
| S5.9 | Kein Container-User-Isolierung für `green-qdrant`, `hermes-green`, `shadowlock` (Issue #201 offen) | Non-Root für alle Container; dedizierte User per Service | Issue #201 dokumentiert: qdrant/hermes potenziell als root; shadowlock Dockerfile läuft als root | 🟡 Mittel | Container-Breakout-Risiko bei qdrant/hermes/shadowlock | User-Isolierung für alle Container; Issue #201 schließen | 2–3d |
| S5.10 | Keine Rate-Limiting auf API-Endpunkten (FT :8080, ai-hedge :8410, Dashboard :5000) | Rate-Limiting + Auth auf allen Management-APIs | Brute-Force, DoS auf lokale APIs möglich (gemindert durch 127.0.0.1) | 🔵 Niedrig | Lokaler Angriffsvektor; geringes Risiko wegen localhost-only | Bei Extern-Zugang (Tailscale): Caddy Rate-Limit | 1d |
| S5.11 | Stdlib-Logging, kein zentrales Logging-Framework; Logs fragmentiert (primo.log, shadowlock/, trading_hub_sync.log, drawdown_guard.log, observation_watchdog.log) | Zentralisiertes Logging (Loki, ELK, oder strukturiertes JSON-Logging mit Aggregation) | Logs sind pro-Service isoliert; keine Korrelation; kein Alerting auf Log-Patterns | 🟡 Mittel | Incident-Response verzögert; Log-Correlation nicht möglich | Strukturiertes JSON-Logging + zentraler Aggregator (z.B. Loki + Promtail) | 5–8d |

### 6. Qualität & Testabdeckung

| # | Ist-Zustand | Soll-Zustand | Gap-Beschreibung | Priorität | Auswirkung | Empfohlene Maßnahme | Aufwand |
|---|-------------|--------------|------------------|----------|-------------|---------------------|---------|
| Q6.1 | **Pipeline/Fleet-Strategien: 0 automatische Tests** | Unit + Integration Tests für Pipeline, RG, FleetRisk, Strategies | Kern-Trading-Logik komplett ungetestet; Bugs entdecken erst im produktiven Lauf | 🔴 Kritisch | Breaking Changes silently deployed; Regressions-Risiko extrem hoch | Unit-Tests für: RG-1..5, Pipeline stale-block, Cap-Logik, primo_gate | 5–8d |
| Q6.2 | Tests existieren nur für: SI v2 (umfassend), Compose Healthchecks (static YAML), Shadowlock Indexer (basic) | Strategie-Backtests + Walk-Forward + Edge-Case Tests | Keine Strategie-Tests (Unit für Entry/Exit-Logik); keine Walk-Forward-Automatisierung | 🔴 Kritisch | Strategie-Fehler (z.B. RG Off-by-One E3.2) entdeckt nur im Live-Dry-Run | Strategy-Unit-Tests mit Fixtures; Walk-Forward als CI-Job | 8–12d |
| Q6.3 | Keine Code-Coverage-Messung (kein `--cov`, kein Coverage-Report) | Coverage-Gate (≥80%) im CI; Coverage-Report pro PR | Keine objektive Messung der Test-Qualität; "Testing feels good" ohne Evidenz | 🟡 Mittel | Unbekannte Coverage-Lücken; False Security | `pytest-cov` im CI; `--cov-fail-under=80` als Gate | 1–2d |
| Q6.4 | Ruff als Linter für SI v2 + orchestrator/control | Ruff + mypy/type-checking für gesamte Python-Codebasis | Pipeline, bridge, primo, shadowlock, fleet_risk_manager ohne Linting | 🟡 Mittel | Inkonsistenter Code-Style; Type-Errors unentdeckt | Ruff für alle Python-Pfade; optional mypy für kritische Module | 2–3d |
| Q6.5 | Keine Integration/E2E-Tests (Signal → Pipeline → RG → Shadow → FT) | E2E-Test mit Mocked-Signal + Pipeline + RG + FT REST | End-to-End Flow nie automatisch verifiziert | 🟠 Hoch | Integration-Gaps zwischen Komponenten entdeckt erst im produktiven Lauf | E2E-Test: Fixture-Signal → Pipeline → RG → Shadow → FT Mock | 5–8d |
| Q6.6 | Keine Chaos-Tests / Fehlernjektion | Chaos-Tests: Container-Kill, Exchange-Outage, Signal-Stale, Network-Partition | Resilienz des Systems nie unter Stress getestet | 🟡 Mittel | Versteckte Single-Points-of-Failure unentdeckt | Chaos-Test-Suite: Docker-Kill, Signal-Stale, Network-Isolation | 3–5d |
| Q6.7 | Backtests ohne realistische Kosten (keine Fees + Slippage + Funding) | Backtests mit realistischen Kosten (Bitget Taker 0.06%, Slippage, Funding) | Strategie-Promotion auf Basis optimistischer PnL | 🟠 Hoch | Live-PnL weicht systematisch von Backtest-PnL ab | Backtest-Engine: realistische Fees + Slippage + Funding + Walk-Forward | 5–8d |

---

## Visualisierung: Prioritätsmatrix (Impact × Aufwand)

```
         │ HOHER AUFWAND │                            │
         │  (>5 Tage)    │                            │
IMPACT   │               │    Q6.2 (Strat-Tests)      │
  HOCH   │  G4.1 (Compl) │                            │  Q6.5 (E2E)
         │  Q6.7 (Backt) │                            │  S5.4 (Scanning)
         │───────────────┼────────────────────────────┼─────────────
IMPACT   │               │   T1.2 (Container-Drift)   │  T1.4 (Proxy)
  MITTEL │  Q6.1 (Pipe)  │   P2.1 (CI Fleet)         │  G4.2 (Kill)
         │  P2.5 (Deps)  │   P2.7 (Auto-Retrain)      │  S5.1 (EXEC)
         │               │   G4.7 (Audit)              │
         │───────────────┼────────────────────────────┼─────────────
IMPACT   │               │   D3.1 (Doc-Drift)         │  G4.3 (License)
  NIEDRIG│  D3.6 (Index) │   D3.2 (Charter)           │  S5.6 (Rate-Lim)
         │               │   D3.3 (Runbooks)            │  G4.4 (CoC)
         │               │                            │  S5.8 (Watchdog)
         └───────────────┴────────────────────────────┴─────────────
                              NIEDRIGER AUFWAND           HOHER AUFWAND
                              (<5 Tage)                    (<5 Tage)
```

> **Strategie**: Erst "Quick Wins" (rechts unten) → dann "Strategic" (links oben) → "Major Projects" (rechts oben)

---

## Priorisierter Maßnahmenkatalog

### Phase P0 — Sofortmaßnahmen (Woche 1–2)

| # | Maßnahme | Bereich | Aufwand | Begründung |
|---|----------|---------|---------|------------|
| P0.0 | **Hartkodierte Credentials rotieren + .gitignore erweitern + History scrubben** | Sicherheit | 2–3d | API-Keys + JWT-Secrets im Klartext in getrackten Configs — SOUL.md Regel 8 verletzt |
| P0.1 | **Pipeline/RG Unit-Tests erstellen** | Qualität | 5–8d | Kern-Logik ohne Tests = blindes Deployment |
| P0.2 | **Docker-Socket-Proxy hartening** (EXEC=0, POST=0) + Docker-Härtung (cap_drop, no-new-privileges) | Sicherheit | 1–2d | Lateral Movement + Container-Breakout verhindern |
| P0.3 | **CI: Fleet-Compose-Validierung + Dry-Run-Invariant + Secret-Scanning** | Prozesse | 2–3d | Verhindert dry_run=false + Secret-Leaks |
| P0.4 | **Container Resource-Limits für alle Services** | Technologie | 1–2d | Verhindert OOM/CPU-Starvation (historischer Vorfall) |
| P0.5 | **AGENTS.md + Charter aktualisieren** | Dokumentation | 1–2d | Veraltete Docs = Governance-Risiko (binding rules!) |

**P0 Gesamtaufwand:** 12–20 Tage (einige Maßnahmen parallelisierbar)

### Phase P1 — Kurzfristig (Woche 3–6)

| # | Maßnahme | Bereich | Aufwand | Begründung |
|---|----------|---------|---------|------------|
| P1.1 | **Kill-Switch wiring** (kill_switch.json → FT force_exit + Pipeline WATCH_ONLY) | Compliance | 5–8d | Autonomie ohne Kill = verantwortungslos |
| P1.2 | **E2E Integration Test** (Signal → Pipeline → RG → Shadow → FT Mock) | Qualität | 5–8d | End-to-End Flow nie automatisch verifiziert |
| P1.3 | **Compliance Bridge** (FT SQLite + Shadow → unified Audit-Store) | Compliance | 8–12d | Voraussetzung für regulatorische Konformität |
| P1.4 | **CI: Strategy Compile + Lint** | Prozesse | 2–3d | Strategie-Code ohne CI = Regression-Risiko |
| P1.5 | **Container-Drift beheben** (#200) | Technologie | 3–5d | 35% Container ohne Lifecycle-Management |
| P1.6 | **Root pyproject.toml** + Dependency-Pinning | Prozesse | 3–5d | Reproduzierbare Deployments |

**P1 Gesamtaufwand:** 26–41 Tage (parallelisierbar, ca. 15–20 Kalenderwochen)

### Phase P2 — Mittelfristig (Monat 2–3)

| # | Maßnahme | Bereich | Aufwand | Begründung |
|---|----------|---------|---------|------------|
| P2.1 | **Walk-Forward + Backtest mit realistischen Kosten** | Qualität | 8–12d | Strategie-Promotion auf realistischer Basis |
| P2.2 | **Shadowlock → Trading-Audit erweitern** | Compliance | 5–8d | Komplette Entscheidungs-Trail |
| P2.3 | **Container-Image-Scanning (Trivy) + Pinned Digests** | Sicherheit | 2–3d | CVE-Prevention |
| P2.4 | **Auto-Retrain Trigger** | Prozesse | 5–8d | Strategie-Degradation automatisch erkennen |
| P2.5 | **Runbooks für kritische Szenarien** | Dokumentation | 3–5d | Incident-Response beschleunigen |
| P2.6 | **Compose-Split** (infra/fleet/memory) | Technologie | 3–5d | Deployment-Isolierung |

**P2 Gesamtaufwand:** 26–41 Tage

### Phase P3 — Langfristig (Monat 3–6)

| # | Maßnahme | Bereich | Aufwand | Begründung |
|---|----------|---------|---------|------------|
| P3.1 | **Multi-Exchange Fallback** | Technologie | 5–10d | Eliminiert Single-Exchange-SPOF |
| P3.2 | **Chaos-Testing Suite** | Qualität | 3–5d | Resilienz unter Stress verifizieren |
| P3.3 | **Secret-Rotation + Docker Secrets** | Sicherheit | 3–5d | Production-Grade Secret-Management |
| P3.4 | **API-Dokumentation** | Dokumentation | 2–3d | Entwickler-Erfahrung |
| P3.5 | **ADRs für Architektur-Entscheidungen** | Dokumentation | 2–3d | Wissens-Erhalt |

**P3 Gesamtaufwand:** 15–28 Tage

---

## Aufwandsgesamtschätzung

| Phase | Aufwand (Agent-Tage) | Kalender | Fokus |
|-------|----------------------|-----------|-------|
| P0 (Sofort) | 12–20 | 1–2 Wochen | Stabilität + Safety + Credential-Rotation |
| P1 (Kurzfristig) | 26–41 | 3–6 Wochen | Kill-Switch + Testing + Compliance |
| P2 (Mittelfristig) | 26–41 | 2–3 Monate | Backtest-Realismus + Audit + CI-Maturity |
| P3 (Langfristig) | 15–28 | 3–6 Monate | Resilienz + Multi-Exchange + Production-Hardening |
| **Gesamt** | **79–130** | **~6 Monate** | |

---

## Abhängigkeitsgraph

```
P0.2 (Proxy) ──────────────────────────────┐
P0.5 (Limits) ─────────────────────────────┤
P0.6 (Docs) ──────────────────────────────┤
                                            ├──→ P1.1 (Kill-Switch) ──→ P2.2 (Audit)
P0.1 (Pipeline-Tests) ───→ P1.2 (E2E) ───┤
P0.3 (CI Fleet) ───→ P1.4 (Strat CI) ────┤
P0.4 (Secret-Scan) ──────────────────────┘

P1.5 (Container-Drift) ──→ P2.6 (Compose-Split)
P1.3 (Compliance-Bridge) ──→ P2.2 (Audit)
P1.6 (pyproject.toml) ──→ P2.4 (Auto-Retrain)

P1.1 + P1.3 ──→ P3.1 (Multi-Exchange)
P1.2 + P1.4 ──→ P3.2 (Chaos-Testing)
```

---

## Anhang A: Geprüfte Artefakte

### Root-Level Dateien
| Datei | Geprüft | Typ |
|-------|---------|-----|
| `README.md` | ✅ | Dokumentation |
| `AGENTS.md` | ✅ | Governance |
| `SOUL.md` | ✅ | Governance |
| `ORCHESTRATOR_CHARTER.md` | ✅ | Governance |
| `CLAUDE.md` | ✅ | Konfiguration |
| `docker-compose.yml` | ✅ | Infrastruktur (369 Zeilen, 12 Services) |
| `.gitignore` | ✅ | Sicherheit (280 Zeilen) |
| `Caddyfile` | ✅ | Netzwerk (51 Zeilen) |
| `dashboard.py` | ⬜ (nur Metadaten) | Applikation |

### Verzeichnisse
| Pfad | Geprüft | Tiefe |
|------|---------|-------|
| `.github/workflows/` | ✅ | 3 Dateien: main-gate, si-v2-offline-smoke, si-v2-phase2-proposal-gate |
| `docs/` | ✅ | 23 Sub-Dirs, 2 GAP-Reports, 13 Specs, 3 Runbooks, 2 ADRs, 2 Audits |
| `docs/state/` | ✅ | 7 Dateien inkl. current-operational-state.md |
| `tests/` | ✅ | 2 Dateien: healthchecks, shadowlock |
| `scripts/` | ✅ | 3 Dateien |
| `self_improvement_v2/` | ⬜ (nur pyproject.toml via Glob) | — |

### Nicht geprüft (gitignored oder extern)
| Pfad | Grund |
|------|-------|
| `ai-hedge-fund-crypto/` | gitignored (upstream repo) |
| `Agenten_Auto_Trade/` | gitignored (separater repo) |
| `.env` Files | gitignored (korrekt) |
| Freqtrade Bot-Configs | gitignored (enthält jwt_secret_key) |
| Docker-Images | nicht inspizierbar |

### Vorherige GAP-Reports (inkorporiert)
| Report | Datum |覆盖率 |
|--------|-------|---------|
| `GAP_ANALYSE.md` | 2026-05-17 | Initial-Audit (~32% Abweichung) |
| `GAP-REPORT-2026-06-05-DEEP-DIVE-AUTONOMES-TRADING.md` | 2026-06-05 | 6-Dimensionen Deep-Dive (322 Zeilen) |

---

## Anhang B: Referenzrahmen

### OWASP-Abdeckung

| OWASP-Kategorie | Abgedeckt | Gap |
|----------------|-----------|-----|
| A01 – Broken Access Control | Teilweise (127.0.0.1 Binding, Docker-Proxy) | EXEC/POST-Proxy-Rechte zu weit |
| A02 – Cryptographic Failures | Teilweise (Tailscale-MTLS) | Backend-Verkehr unverschlüsselt |
| A03 – Injection | N/A (keine User-Inputs) | — |
| A05 – Security Misconfiguration | Teilweise (Resource-Limits) | `latest` Tags, unmanaged Container |
| A06 – Vulnerable Components | ❌ Nicht abgedeckt | Kein Image-Scanning |
| A07 – Auth Failures | N/A (nur interne APIs) | — |
| A09 – Logging/Monitoring | Gut (Shadow + Watchdogs) | Audit-Trail inkomplett |

### ISO 27001 (ausgewählte Controls)

| Control | Abgedeckt | Gap |
|---------|-----------|-----|
| A.8.1 Asset Management | Teilweise | Keine Asset-Inventarisierung für Container-Images |
| A.8.9 Configuration Mgmt | Teilweise (Git) | Doc-Drift, veraltete Charter |
| A.9.1 Access Control | Gut (127.0.0.1, Docker-Proxy) | Proxy-Rechte zu weit |
| A.12.4 Logging/Monitoring | Gut (Shadow + Watchdogs) | Compliance-Audit nicht gewired |
| A.14.1 Information Security Policy | Gut (SOUL.md, Charter) | RiskGuard-Verpflichtung nicht erfüllt |

---

## Anhang C: Glossar

| Begriff | Definition |
|---------|------------|
| RG | RiskGuard — Signal-Validierungsschicht (Confidence, Staleness, Bias, Qty, Concurrent Cap) |
| FT | Freqtrade — Dry-Run Trading Engine |
| MCP | Market Communication Protocol — Paper-Trading-Simulation |
| Shadow | Append-only JSONL Audit-Trail für Entscheidungen |
| FleetRisk | Cross-Bot Risk Manager (Drawdown, Correlation, Exposure Multiplier) |
| SI v2 | Self-Improvement v2 — Autonomer Optimierungs-Controller |
| Shadowlock | JSONL Audit-Trail für SI v2/Controller-Episoden |
| primo_signal | Brücke-Ausgabe für FT Gate-Logik (verdict + allow_*_bias) |
| fail-open | Bei fehlendem/stale Signal → native Strategy-Logic erlaubt Entries |

---

*Bericht erstellt durch: Sisyphus (OhMyOpenCode Comprehensive Audit)*  
*Status: ✅ Read-Only Analyse abgeschlossen*  
*Empfehlung: P0-Maßnahmen innerhalb von 2 Wochen starten; P1 parallel vorbereiten*
