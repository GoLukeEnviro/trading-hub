# Background-Review Whitelist Audit Report

> Session: hermes-skill-debug-2026-07-13 | Step 3/6 | Scope L2
> Date: 2026-07-13

## Issue: BG-Review-Agent ruft nicht-whitelistete Tools auf

Der Hermes Background-Review-Agent ruft `read_file`/`search_files`/`patch` auf,
die nicht in der Tool-Whitelist des Background-Review-Pfads enthalten sind.
Diese Aufrufe werden vom Guardrail abgelehnt.

## Evidence

### 1. Whitelist-Definition im Repository

Eine formale Whitelist-Definition existiert NICHT als eigenständiges
Dokument oder AGENTS.md-Abschnitt. Die einzige Referenz ist:

`docs/context/mem0-background-whitelist-fix-20260518.md` (2026-05-18):
- Beschreibt einen Fix für `run_agent.py` im ai4trade-bot-Repository
- Die Whitelist wird dort dynamisch aus Toolset + Memory-Provider-Tools gebaut
- `set_thread_tool_whitelist(review_whitelist, ...)` setzt die erlaubten Tools
- Der Fix fügte `mem0_conclude` zur Whitelist hinzu (war vorher blockiert)

### 2. Aktuelles Problem

Der Background-Review-Agent (post-turn review path in Hermes) versucht:
- `read_file` — Dateien lesen (nicht whitelisted)
- `search_files` — Dateien suchen (nicht whitelisted)  
- `patch` — Dateien ändern (nicht whitelisted)

Diese Tools werden vom Guardrail blockiert. Der Review-Pfad kann daher weder
Dateien inspizieren noch Änderungen vornehmen.

### 3. AGENTS.md — Aktueller Stand

AGENTS.md enthält KEINEN Abschnitt zu Background-Review-Constraints. Es gibt
"Agent safety rules" (7 Regeln) und "System architecture boundaries", aber
keine Dokumentation, welche Tools der Background-Review-Agent verwenden darf.

## Investigation

Geprüft:
- [x] `git grep background_review` in trading-hub → nur Mem0-Fix-Doc (2026-05-18)
- [x] `git grep background_review` in ai4trade-bot → keine Treffer (Repo bei `6e850c8`)
- [x] AGENTS.md auf bestehende Constraints → kein Background-Review-Abschnitt
- [x] `git grep set_thread_tool_whitelist` → nur Mem0-Fix-Doc
- [x] `git grep bg.review` → keine Treffer

Ausgeschlossen:
- [x] Whitelist ist NICHT im trading-hub-Repository als Konfiguration dokumentiert
- [x] ai4trade-bot `main` (lock `6e850c8`) enthält keine `background_review`-Referenzen — 
  die Whitelist-Logik liegt entweder in neueren Commits oder in der Hermes-Runtime

## Root Cause

Die Background-Review-Tool-Whitelist wird dynamisch in der Hermes-Agent-Runtime
(`run_agent.py`, ai4trade-bot) aufgebaut. Sie ist:
1. Nicht im trading-hub-Repository dokumentiert
2. Nicht in AGENTS.md als Constraint festgehalten
3. Enthält nur `memory/*` und `skill/*` Tools, aber AGENTS.md dokumentiert
   diese Einschränkung nicht

Ohne dokumentierten Constraint versuchen Review-Agenten (oder menschliche
Entwickler, die AGENTS.md als Autorität lesen) Zugriff auf `read_file`/
`search_files`/`patch` im Review-Kontext — und scheitern am Guardrail.

## Solution

Ergänze einen knappen, stabilen Constraint-Abschnitt in AGENTS.md:

```markdown
## Background Review Constraints

Der Background-Review-Agent (post-turn review path) operiert mit einer
eingeschränkten Tool-Whitelist:

- **Erlaubt:** `memory/*` (Mem0/Holographic persist), `skill/*` (Skill-Management)
- **NICHT erlaubt:** `read_file`, `search_files`, `patch`, `terminal`,
  `execute_code`, `edit`, `write`

Der Review-Pfad dient der Memory-Persistenz und Skill-Verwaltung, nicht
der Code- oder Dateisystem-Inspektion. Datei-Änderungen und Code-Reviews
erfolgen im primären Agent-Pfad, nicht im Background-Review.
```

Platzierung: nach "Agent safety rules", vor "Proven SI-v2 4-bot loop".

## Verification

- AGENTS.md enthält den neuen Abschnitt "Background Review Constraints"
- Der Abschnitt listet erlaubte und nicht-erlaubte Tools explizit
- Keine Mutation an bestehenden AGENTS.md-Abschnitten
- Separater PR für AGENTS.md-Änderung (Root-Doc, kein Direkt-Merge)
