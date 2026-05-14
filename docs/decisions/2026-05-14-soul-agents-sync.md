# ADR-2026-05-14: Documentation Architecture Decisions

**Datum:** 2026-05-14
**Status:** Akzeptiert
**Entscheider:** Luke

---

## Kontext

Im Rahmen der Konsolidierung der SOUL.md- und AGENTS.md-Dateien wurden mehrere grundlegende Fragen zur Dokumentationsarchitektur und Dateirole geklärt.

---

## Entscheidungen

### 1. Signal-Core: PrimoAgent → ai-hedge-fund-crypto

**Entscheidung:** `ai-hedge-fund-crypto` ist der aktive Signal-Core.

**Begründung:**
- `PrimoAgent` ist ein veralteter Begriff — PrimoGate/PrimoBridge sind deprecated
- `ai-hedge-fund-crypto` ist das aktive Container-System
- Bridge-Funktionalität über `primo_signal.py` wo zutreffend

**Betroffene Dateien:**
- `~/.hermes/profiles/orchestrator/SOUL.md` (Live-Identität)
- `/home/hermes/projects/trading/AGENTS.md` (Primärkontext)

---

### 2. Projekt-SOUL.md: Projekt-Mission, nicht Live-Identity

**Entscheidung:** `/home/hermes/projects/trading/SOUL.md` ist Projekt-Mission und strategische Regeln. Nicht als Live-Hermes-Identität zu behandeln.

**Begründung:**
- Hermes lädt SOUL.md nur aus `HERMES_HOME` (= aktives Profil)
- Projekt-SOUL.md ist nützlich als Referenz, wird aber nicht automatisch injiziert
- KLARE TRENNUNG: Profil-SOUL = Live-Identity; Projekt-SOUL = Dokumentation

**Betroffene Dateien:**
- `/home/hermes/projects/trading/SOUL.md` — als "Projekt-Mission" labeln

---

### 3. AGENTS.md bleibt primärer Projektkontext

**Entscheidung:** `AGENTS.md` ist die wichtigste Projektkontext-Datei. Keine `.hermes.md` anlegen.

**Begründung:**
- `.hermes.md` hat höhere Priorität als `AGENTS.md`
- Bei Konflikt würde `.hermes.md` die AGENTS.md verdrängen
- AGENTS.md enthält bereits alle relevanten Pfade, Ports, Architektur und Workflows
- Kein Bedarf für eine zusätzliche Datei

**Betroffene Dateien:**
- `/home/hermes/projects/trading/AGENTS.md` — bleibt primäre Projektdatei
- `.hermes.md` — NICHT erstellen

---

### 4. ORCHESTRATOR_CHARTER.md bleibt unverändert

**Entscheidung:** `ORCHESTRATOR_CHARTER.md` ist die verbindliche Betriebsverfassung, wird aber nicht als Hermes-SOUL behandelt.

**Begründung:**
- Enthält operative Regeln, Gates und Zuständigkeiten
- Wichtiges Referenzdokument
- Bereits korrekt in der Hierarchie eingeordnet

**Betroffene Dateien:**
- `/home/hermes/projects/trading/ORCHESTRATOR_CHARTER.md` — keine Änderungen

---

### 5. Dateihierarchie: Live vs. Dokumentation

| Datei | Rolle | Geladen von Hermes |
|-------|-------|-------------------|
| `~/.hermes/profiles/orchestrator/SOUL.md` | Live-Identität | ✅ JA |
| `~/.hermes/profiles/orchestrator/config.yaml` | Live-Konfiguration | ✅ JA |
| `/home/hermes/projects/trading/AGENTS.md` | Primärer Projektkontext | ✅ JA (bei CWD=trading) |
| `/home/hermes/projects/trading/ORCHESTRATOR_CHARTER.md` | Betriebsverfassung | Referenz |
| `/home/hermes/projects/trading/README.md` | Repo-Übersicht | Referenz |
| `/home/hermes/projects/trading/SOUL.md` | Projekt-Mission | Nein (Dokumentation) |
| `/home/hermes/projects/trading/docs/state/` | Operativer Zustand | Nein (Dokumentation) |
| `/home/hermes/projects/trading/docs/runbooks/` | Audit-Procedures | Nein (Dokumentation) |
| `/home/hermes/projects/trading/docs/decisions/` | Architektur-Entscheidungen | Nein (Dokumentation) |

---

## Umsetzung

- [x] Profil-SOUL.md: "PrimoAgent" → "ai-hedge-fund-crypto"
- [x] AGENTS.md: MVS = NOT_DEPLOYED
- [x] AGENTS.md: RSI = QUARANTINE
- [x] AGENTS.md: FOMO Phase 3 = NOT_DEPLOYED
- [x] AGENTS.md: Honcho Doc-Count aktualisiert (3,509)
- [x] SOUL.md: Strategie-Count (49)
- [x] README.md: Strategie-Count (49), MVS, FOMO Phase 3, docs/context
- [x] docs/state/current-operational-state.md erstellt
- [x] docs/runbooks/signal-staleness-audit.md erstellt
- [x] docs/runbooks/honcho-health-audit.md erstellt
- [ ] Dieses ADR in docs/decisions/ abgelegt (DIESES DOKUMENT)

---

## Offene Punkte (nicht in diesem Task adressiert)

| Thema | Status | Nächster Schritt |
|-------|--------|-----------------|
| Signal Staleness (~49h) | OFFEN | Separater Runtime-Audit |
| Honcho API Health | OFFEN | Separater Audit |
| 60 Paper-Trades Regel in Profil-SOUL | DESIGN-DECISION | Luke entscheidet |
| writeFrequency=session verifizieren | UNVERIFIED | Separat prüfen |

---

## Referenzen

- Hermes Agent Docs: https://hermes-agent.nousresearch.com/docs/
- Profil-SOUL: `~/.hermes/profiles/orchestrator/SOUL.md`
- Primärkontext: `/home/hermes/projects/trading/AGENTS.md`
- Betriebsverfassung: `/home/hermes/projects/trading/ORCHESTRATOR_CHARTER.md`