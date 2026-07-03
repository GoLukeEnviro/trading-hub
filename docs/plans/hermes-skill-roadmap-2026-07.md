# Hermes Skill Roadmap — Trading Hub 2026

> **Orchestrator-Analyse:** Welche Skills braucht das Projekt als nächstes?
> **Status:** Read-only Plan — keine Ausführung
> **Datum:** 2026-07-03
> **Basis:** `main` @ `20aee88` (PR #425), SI-v2 Phase 10.4 abgeschlossen

---

## 1. Aktuelle Lage

### Was läuft gut

| Bereich | Status |
|---------|--------|
| SI-v2 Loop | ✅ Vollständig implementiert (11 Module, 11 PRs, alle GREEN) |
| Autonomous Dry-Run | ✅ Policy-gated, canary-first, allowlist-based |
| Erster Canary Apply | ✅ Runtime-proven — `max_open_trades 3→2` auf Canary |
| RiskGuard / ShadowLogger | ✅ Operational |
| Kill Switch | ✅ NORMAL — einsatzbereit |
| Dokumentation | ~80 % Reifegrad |
| Sicherheitskultur | Stark — Safety-First-Prinzip in SOUL.md/AGENTS.md verankert |

### Bestehende Hermes Skills (trading-relevant)

| Skill | Zweck |
|-------|-------|
| `trading-hub-operations` | Umbrella für Freqtrade-Fleet-Management, Signal-Stack, Docker |
| `freqtrade-fleet-auditing-and-readiness` | Read-only Audit von Trades, Exit-Proximity, Lab-Readiness |
| `code-simplifier` | Code-Qualität und Vereinfachung (neu) |
| `safe-software-delivery-workflows` | Delivery-Pipelines, Code-Review, Debugging |
| `plan` | Plan-Mode und Spike-Experimente |

### Bekannte Lücken (aus GAP-Report 2026-06-15)

| Gap | Priorität | Bereich |
|-----|-----------|---------|
| Testabdeckung ~15 % | 🔴 Kritisch | Qualität |
| CI/CD deckt nur SI v2 ab | 🟠 Hoch | Prozesse |
| Pipeline/Fleet-Strategien ohne Tests | 🔴 Kritisch | Qualität |
| 7/20 Container unmanaged (Compose-Drift) | 🟠 Hoch | Technologie |
| Keine App-Auth auf HTTP-Endpoints | 🟠 Hoch | Sicherheit |
| Kill-Switch nicht vollständig zur Fleet gewired | 🔴 Kritisch | Sicherheit |

---

## 2. Skill-Roadmap — Priorisierte Phasen

### Phase A — Observability & Safety (Sofort, L0/L1)

**Ziel:** Was läuft, verstehen. Bevor wir etwas ändern, müssen wir sehen, was passiert.

#### A1 — `fleet-health-monitor`
- **Beschreibung:** Container-Health, Disk, Memory, Log-Rotation, API-Reachability prüfen
- **Warum:** 7/20 Container unmanaged — wir sehen nicht, wenn einer stirbt
- **Aufwand:** 🟡 Mittel (2-3h)
- **Abhängigkeiten:** Keine
- **L0/L1:** Read-only — inspiziert Docker, Logs, System-Resources

#### A2 — `trade-performance-reporter`
- **Beschreibung:** Per-Bot P&L, Drawdown, Win-Rate, Sharpe, Profit-Factor Reports
- **Warum:** Aktuelle Reports sind ad-hoc; ein standardisierter Report pro Bot fehlt
- **Aufwand:** 🟡 Mittel (2-3h)
- **Abhängigkeiten:** Keine
- **L0/L1:** Read-only — liest Freqtrade-API und SQLite

#### A3 — `incident-responder`
- **Beschreibung:** Incident-Analyse, Post-Mortem-Vorlage, Evidence-Sammlung
- **Warum:** Jeder Incident (Rebel-Telegram-404, Cron-Ausfälle) braucht strukturierte Analyse
- **Aufwand:** 🟢 Klein (~1h)
- **Abhängigkeiten:** Keine
- **L0/L1:** Read-only — dokumentiert, analysiert, empfiehlt

---

### Phase B — Quality & Testing (Nächstes, L1/L2)

**Ziel:** Die 15 % Testabdeckung erhöhen, bevor wir neue Features bauen.

#### B1 — `test-coverage-enforcer`
- **Beschreibung:** Coverage-Lücken identifizieren, Issues erstellen, Prioritäten vorschlagen
- **Warum:** 15 % Coverage ist das größte Risiko für Live-Readiness
- **Aufwand:** 🟢 Klein (~1h)
- **Abhängigkeiten:** Keine
- **L1/L2:** Läuft Coverage-Tools, erstellt Issues, ändert nichts am Code

#### B2 — `ci-gate-expander`
- **Beschreibung:** CI-Gates für Fleet-Pipeline, Docker-Compose, Strategien vorschlagen
- **Warum:** Aktuell deckt CI nur SI v2 ab — Fleet-Änderungen fliegen ungetestet durch
- **Aufwand:** 🟡 Mittel (2-3h)
- **Abhängigkeiten:** B1 (Coverage-Basis)
- **L2:** Schlägt CI-Konfigurationen vor, erstellt PRs

---

### Phase C — Runtime Safety (Mittelfristig, L2/L3)

**Ziel:** Safety-Gates schließen, die der GAP-Report identifiziert hat.

#### C1 — `kill-switch-operator`
- **Beschreibung:** Kill-Switch-Status prüfen, auslösen, dokumentieren, Auto-Clear
- **Warum:** Kill-Switch ist nicht vollständig zur Fleet gewired
- **Aufwand:** 🟡 Mittel (2-3h)
- **Abhängigkeiten:** A1 (Fleet-Health)
- **L2/L3:** Kann Kill-Switch setzen — braucht Approval

#### C2 — `config-snapshot-manager`
- **Beschreibung:** Config-Änderungen tracken, snapshotten, diff-en, rollback-vorbereiten
- **Warum:** Freqtrade-Configs werden selten geändert, aber wenn, dann riskant
- **Aufwand:** 🟢 Klein (~1h)
- **Abhängigkeiten:** Keine
- **L2:** Read-only Snapshots + Diffs

#### C3 — `docker-compose-sync`
- **Beschreibung:** Compose-Drift erkennen, dokumentieren, Sync-Vorschläge
- **Warum:** 35 % der Container ohne kanonische Konfiguration
- **Aufwand:** 🟡 Mittel (2-3h)
- **Abhängigkeiten:** A1 (Fleet-Health)
- **L2:** Read-only Audit + Report

---

### Phase D — Signal & Strategy (Langfristig, L1/L2)

**Ziel:** Signal-Qualität sichern, bevor Live-Trading in Reichweite kommt.

#### D1 — `signal-quality-gate`
- **Beschreibung:** Signal-Qualität vor Fleet-Weitergabe prüfen (Vollständigkeit, Aktualität, Plausibilität)
- **Warum:** Signals sind advisory only — aber wenn sie Müll liefern, handeln Bots trotzdem schlecht
- **Aufwand:** 🟡 Mittel (2-3h)
- **Abhängigkeiten:** A2 (Trade-Performance)
- **L1/L2:** Read-only Analyse + Report

#### D2 — `backtest-validator`
- **Beschreibung:** Walk-Forward + Backtest orchestrieren, Ergebnisse validieren, Reports generieren
- **Warum:** Backtests sind der Gatekeeper für Strategie-Änderungen — aber aktuell manuell
- **Aufwand:** 🟢 Groß (4h+)
- **Abhängigkeiten:** B1 (Test-Coverage), D1 (Signal-Quality)
- **L2:** Orchestriert Backtests, validiert Ergebnisse, ändert nichts

---

### Phase E — Live Readiness (Tor, L3)

**Ziel:** Checkliste abarbeiten, bevor Live-Trading überhaupt diskutiert wird.

#### E1 — `live-readiness-checker`
- **Beschreibung:** Checklisten-basierte Go/No-Go-Entscheidungen, Evidence-Sammlung, Report
- **Warum:** SOUL.md fordert Backtest + Walk-Forward + Shadow-Mode + explizite Freigabe
- **Aufwand:** 🟢 Klein (~1h)
- **Abhängigkeiten:** A1, A2, B1, C1, C2, D1, D2 (alle vorherigen Phasen)
- **L3:** Nur Report — keine Live-Aktivierung

---

## 3. Priorisierte Reihenfolge

```
JETZT                → NÄCHSTE WOCHE        → MITTELFRISTIG        → LANGERISTIG
──────────────────────────────────────────────────────────────────────────────
A1 fleet-health      B1 test-coverage       C1 kill-switch-op      D1 signal-quality
A2 trade-perf        B2 ci-gate-expander    C2 config-snapshot     D2 backtest-val
A3 incident-resp                            C3 docker-compose      E1 live-readiness
```

### Empfehlung: Nächste 3 Skills

1. **`fleet-health-monitor`** (A1) — Fundament. Ohne Sichtbarkeit keine Entscheidung.
2. **`trade-performance-reporter`** (A2) — Standardisierte Bot-Bewertung. Fehlt seit Monaten.
3. **`test-coverage-enforcer`** (B1) — Coverage von 15 % auf mindestens 40 % bringen.

---

## 4. Skill-Definitionen (Detail)

### A1 — fleet-health-monitor

```yaml
name: fleet-health-monitor
description: "Prüft Container-Health, Disk, Memory, Log-Rotation und API-Reachability der Freqtrade-Fleet. Read-only."
category: trading
platforms: [linux]
```

**Trigger:** `/health`, `/fleet status`, oder wenn ein Bot nicht erreichbar scheint.

**Procedure:**
1. `docker ps` — alle Container-Status prüfen
2. `docker inspect` — Restart-Count, Healthcheck-Status
3. Disk-Usage (`df -h`) und Memory (`free -m`)
4. Log-Rotation prüfen (Log-Größe, Alter)
5. API-Ping pro Bot (`/api/v1/ping`)
6. Report im Luke-Format (Einschätzung → Was-ist-gut → Blocker → Nächster-Schritt)

**Pitfalls:**
- Healthcheck ist nicht gleich API-Erreichbarkeit (Container läuft, aber API hängt)
- Docker-Restart-Policy kann tote Container automatisch neustarten — das ist kein „Gesund"

---

### A2 — trade-performance-reporter

```yaml
name: trade-performance-reporter
description: "Generiert standardisierte Performance-Reports pro Bot: P&L, Drawdown, Win-Rate, Sharpe, Profit-Factor. Read-only."
category: trading
platforms: [linux]
```

**Trigger:** `/report <bot>`, `/performance`, oder nach einem SI-v2 Cycle.

**Procedure:**
1. Freqtrade-API `/api/v1/performance` und `/api/v1/status` abrufen
2. SQLite-DB lesen (closed trades, open trades)
3. Metriken berechnen: Win-Rate, Profit-Factor, Sharpe, Max-Drawdown, Avg-Trade-Duration
4. Vergleich mit vorherigem Report (Trend)
5. Report im Luke-Format

**Pitfalls:**
- Freqtrade-API gibt nur aggregierte Daten — SQLite-Zugriff für Rohdaten nötig
- Drawdown-Berechnung braucht Equity-Kurve, nicht nur Trade-Liste
- Sharpe ohne risikofreien Zins ist semi-aussagekräftig

---

### A3 — incident-responder

```yaml
name: incident-responder
description: "Strukturierte Incident-Analyse mit Evidence-Sammlung, Timeline, Root-Cause und Post-Mortem. Read-only."
category: trading
platforms: [linux]
```

**Trigger:** `/incident`, oder wenn ein Fehler in Logs/Telegram auftaucht.

**Procedure:**
1. Evidence sammeln: Logs, Timestamps, Configs, Git-History
2. Timeline erstellen: Was passierte wann?
3. Root-Cause-Hypothese + Gegenbeweis
4. Post-Mortem-Vorlage befüllen
5. Nächster-Schritt: Fix oder Workaround vorschlagen

---

### B1 — test-coverage-enforcer

```yaml
name: test-coverage-enforcer
description: "Identifiziert Coverage-Lücken, erstellt Issues, priorisiert nach Risiko. Read-only."
category: software-development
platforms: [linux]
```

**Trigger:** `/coverage`, oder nach einem SI-v2 Cycle.

**Procedure:**
1. `pytest --cov` laufen lassen
2. Coverage-Report parsen (welche Module haben < 50 %?)
3. Nach Risiko priorisieren: Signal-Pipeline > Safety-Layer > Reporting
4. Issues erstellen oder bestehende updaten
5. Report mit konkreten Dateien und Ziel-Werten

---

## 5. Nicht bauen (bewusst weggelassen)

| Skill | Grund |
|-------|-------|
| **Telegram-Bot-Manager** | Telegram läuft stabil — kein Bedarf |
| **Docker-Compose-Editor** | L3 — zu riskant ohne menschliche Kontrolle |
| **Strategy-Optimizer** | Hyperopt ist Freqtrade-Sache, nicht Hermes |
| **Live-Trading-Enabler** | Explizit verboten (SOUL.md) |
| **Backtest-Automat** | Zu früh — erst Coverage und Signal-Qualität |
| **Portfolio-Rebalancer** | Braucht Live-Trading — irrelevant |
| **Market-Data-Feeder** | Bitget-Adapter existiert bereits |

---

## 6. Nächster konkreter Schritt

**Empfehlung:** Skill `fleet-health-monitor` (A1) als nächstes erstellen.

Begründung:
- Keine Abhängigkeiten — sofort umsetzbar
- L0/L1 — kein Risiko
- Schließt die größte Sichtbarkeitslücke (7/20 unmanaged Container)
- Fundament für alle folgenden Phasen

---

*Plan erstellt: 2026-07-03 | Read-only — keine Ausführung ohne Freigabe*
