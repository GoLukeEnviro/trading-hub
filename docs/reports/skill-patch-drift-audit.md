# Skill-Patch-Drift Audit Report

> Session: hermes-skill-debug-2026-07-13 | Step 4/6 | Scope L2/A1
> Date: 2026-07-13

## Issue: skill_manage patch scheitert an "Could not find a match for old_string"

Der Hermes-Agent versucht, SKILL.md-Dateien via `skill_manage` zu patchen.
Die Operation schlaegt fehl, weil der `old_string` nicht exakt mit dem
aktuellen Dateiinhalt uebereinstimmt (Drift). Dokumentiert: 36x in
`docs/context/hermes-log-tooling-cleanup-2026-06-05.md`, 5x in der
aktuellen Session.

## Evidence

### 1. Skill-Dateien — Lokation

Keine SKILL.md-Dateien in den Git-Repositories (trading-hub, ai4trade-bot).
Skills sind reine Runtime-Artefakte im Hermes-Container:

```
/opt/data/hermes/profiles/normal/skills/
  software-development/   (12 skills)
    hermes-agent-skill-authoring/
    hermes-container-ops/
    hermes-self-check/
    node-inspect-debugger/
    plan/
    python-debugpy/
    requesting-code-review/
    simplify-code/
    spike/
    systematic-debugging/
    test-driven-development/
    trading-hub-operator-planning/   ← ~1000+ Zeilen, hoechste Drift-Wahrscheinlichkeit
  github/                  (6 skills)
    codebase-inspection/
    github-auth/
    github-code-review/
    github-issues/
    github-pr-workflow/
    github-repo-management/
  autonomous-ai-agents/    (4 skills)
    claude-code/
    codex/
    hermes-agent/
    opencode/
  media/                   (4 skills)
  apple/                   (4 skills)
  social-media/            (1 skill)
  email/                   (1 skill)
  computer-use/            (1 skill)
  dogfood/                 (1 skill)
```

### 2. Dokumentierte Drift-Historie

| Quelle | Datum | Fund |
|--------|-------|------|
| `docs/context/hermes-log-tooling-cleanup-2026-06-05.md` | 2026-06-05 | 36x "Could not find a match for old_string" in `skill_manage` patch attempts |
| `docs/context/config-fixes-20260602.md` | 2026-06-02 | `skill_manage` patch fuzzy match failure auf `local-memory-ops/SKILL.md` |
| `docs/context/phase1-completion-report-20260602.md` | 2026-06-02 | Transienter Agent-Fehler — fuzzy match gescheitert, Datei intakt |

### 3. Aktuelle Section-Header (Auszug, relevante Skills)

**trading-hub-operator-planning/SKILL.md** (groesste Skill-Datei):
```
# Trading-Hub Operator Planning (HermesTrader)
## When to load
## HermesTrader stand (durable facts)
## Hard constraints (anti-mutation contract)
```
Enthaelt umfangreiche Pitfall-Sektionen (Pitfall 18–40+), Output-Contracts,
Shapes A–G, und zahlreiche Referenzen auf andere Skills. Bei ~1000+ Zeilen
extrem anfaellig fuer Drift bei Patch-Versuchen.

**hermes-self-check/SKILL.md**:
```
# Hermes Environment Self-Check
## When to run this skill
## Core principle
## Procedure
### Step 1 — System & Environment
### Step 2 — Parallel batch: Core tools
...
```

### 4. skill_manage Mechanismus

`skill_manage` patcht SKILL.md-Dateien per exaktem String-Match (`old_string`
→ `new_string`). Der Mechanismus hat keine Fuzzy-Matching-Toleranz. Jede
Abweichung zwischen dem `old_string` im Patch-Befehl und dem tatsaechlichen
Dateiinhalt fuehrt zu "Could not find a match for old_string".

## Investigation

Geprueft:
- [x] trading-hub Repo auf SKILL.md → nur Drittanbieter (.venv/FastAPI)
- [x] ai4trade-bot Repo auf SKILL.md → keine
- [x] Hermes-Runtime auf SKILL.md → 28+ Skills in `/opt/data/hermes/profiles/normal/skills/`
- [x] Section-Header der Software-Development-Skills → erfasst (12 Skills)
- [x] Historische Drift-Dokumentation → 3 Docs mit 36+ dokumentierten Fehlern

Ausgeschlossen:
- [x] Skills sind nicht versioniert (kein Git-Tracking)
- [x] Kein automatisierter Drift-Check zwischen Patch-Strings und Ist-Inhalt
- [x] Keine Skill-Versionierung oder Checksummen

## Root Cause

1. **Skills sind nicht im Git-Repo versioniert.** Sie existieren nur als
   Runtime-Dateien im Hermes-Container unter `/opt/data/hermes/profiles/`.
   Es gibt keinen Commit-Hash, kein Diff, keine History — damit auch keinen
   Schutz vor unbeabsichtigten Aenderungen.

2. **`skill_manage` verwendet exakten String-Match ohne Toleranz.** Wenn ein
   Skill durch `hermes update`, manuelle Bearbeitung oder einen anderen
   Agenten-Patch veraendert wurde, schlaegt der naechste Patch-Versuch fehl.

3. **Die groesste Skill-Datei (`trading-hub-operator-planning/SKILL.md`)
   ist ~1000+ Zeilen** mit vielen volatilen Sektionen (Pitfall-Nummern,
   Phase-Referenzen, Output-Contracts). Jede Aenderung an diesen Sektionen
   invalidiert alle `old_string`-Referenzen fuer zukuenftige Patches.

4. **Kein Pre-Patch-Drift-Check.** Der Agent prueft nicht, ob der
   `old_string` noch im aktuellen Dateiinhalt existiert, bevor er den
   Patch ausfuehrt.

## Solution

### Kurzfristig (Docs)

1. In `AGENTS.md` oder einer Skill-spezifischen Doku dokumentieren:
   - Skills liegen unter `/opt/data/hermes/profiles/normal/skills/`
   - Sie sind NICHT im Git versioniert
   - `skill_manage`-Patches brauchen exakten `old_string`-Match
   - Vor jedem Patch: aktuellen Dateiinhalt pruefen, `old_string` verifizieren

### Mittelfristig (Tooling)

2. Pre-Patch-Validation in den Agent-Workflow einbauen:
   - Vor `skill_manage patch`: `grep -F "old_string" <skill-path>` ausfuehren
   - Bei Missmatch: aktuellen Abschnitt auslesen, neuen Patch generieren
   - Fehlerrate dokumentieren (pro Skill, pro Session)

3. Skill-Dateigroessen reduzieren:
   - `trading-hub-operator-planning/SKILL.md` in mehrere kleinere Dateien
     aufteilen (z.B. shapes.md, pitfalls.md, references.md)
   - Volatile Sektionen (Pitfall-Nummern, Phase-Status) in separate
     Referenzdateien auslagern

### Langfristig (Architektur)

4. Skills in Git versionieren (z.B. in ai4trade-bot `skills/` Verzeichnis)
   und bei `hermes update` aus dem Repo deployen
5. Content-Addressing fuer Skill-Sektionen (SHA-basierte `old_string`
   Referenzen statt Volltext-Match)

## Per-Skill Drift-Risiko (Bewertung)

| Skill | Groesse | Drift-Risiko | Grund |
|-------|---------|-------------|-------|
| trading-hub-operator-planning | ~1000+ Zeilen | 🔴 HOCH | Viele volatile Sektionen, Pitfall-Nummern, Phase-Referenzen |
| hermes-self-check | ~200 Zeilen | 🟡 MITTEL | Verfahrensanweisungen, Tool-Pfade |
| systematic-debugging | ~150 Zeilen | 🟢 NIEDRIG | Stabile Methodik |
| plan | ~100 Zeilen | 🟢 NIEDRIG | Generische Plan-Methodik |
| github-* | 50–150 Zeilen | 🟢 NIEDRIG | Meist stabile CLI-Befehle |

## Verification

- [x] Alle 28+ Skill-Pfade identifiziert und kategorisiert
- [x] Section-Header der 12 Software-Development-Skills erfasst
- [x] Drift-Historie aus 3 Docs dokumentiert
- [x] Root-Cause: Skills nicht versioniert + exakter String-Match ohne Toleranz
- [x] 4-stufige Loesung (Docs → Tooling → Refactoring → Versionierung)
