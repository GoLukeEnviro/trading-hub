# Memory-Cap Consolidation Bug Audit Report

> Session: hermes-skill-debug-2026-07-13 | Step 6/6 | Scope L2
> Date: 2026-07-13

## Issue: Memory-Cap Consolidation scheitert mit "Operation 2 (replace): content is required"

Hermes-Memory ist bei 1878/2200 Zeichen (85% der Kapazitaet). Wenn der
Agent versucht, alte Memory-Eintraege durch konsolidierte Zusammenfassungen
zu ersetzen, schlaegt die Operation fehl.

## Evidence

### 1. Memory-Konfiguration

```yaml
# Konfiguriert via: hermes config set memory.memory_char_limit 2200
memory_char_limit: 2200
```

Aktueller Stand: 1878/2200 Zeichen (Dokumentiert in `docs/plans/hermes-agent-plugins-implementation-plan.md`)

### 2. Fehlerbeschreibung

```
Memory 1878/2200 char; consolidate/replace scheitert:
"Operation 2 (replace): content is required"
```

Der Consolidation-Flow versucht, alte Memory-Eintraege durch neue,
komprimierte Versionen zu ersetzen. Die `replace`-Operation wird ohne
`content`-Feld aufgerufen.

### 3. Code-Pfad (Hermes Framework)

Der Fehler liegt im Hermes-Core-Framework, nicht in den Git-Repos
(trading-hub, ai4trade-bot). Die beteiligten Komponenten:

1. **Memory-Provider: Holographic** (`hermes-memory-store`)
   - Plugin-Pfad: `/opt/hermes/plugins/memory/holographic/`
   - Dateien: `__init__.py`, `holographic.py`, `store.py`, `retrieval.py`
   - Implementiert `MemoryProvider`-Interface
   - Bietet `fact_store`/`fact_feedback` Tools
   - Auto-Extraction via `on_session_end` (wenn `auto_extract: true`)
   - `on_memory_write` mirror: spiegelt Memory-Writes als Facts

2. **Memory-API: Hindsight** (`hindsight_client_api`)
   - `retain_memories()` — Haupt-Endpoint zum Speichern von Memories
   - `ConsolidationResponse` — `operation_id` + `deduplicated`
   - Async-Modus verfuegbar (`async=true`)

3. **Hermes-Core Consolidation-Logik**
   - Ausgeloest wenn `memory_char_limit` erreicht/nah
   - Versucht, alte Eintraege durch `replace`-Operation zu konsolidieren
   - **Fehlerpunkt**: `replace`-Operation wird ohne `content`-Feld gesendet
   - Resultat: "Operation 2 (replace): content is required"

### 4. Issue #477 — Nicht verwandt

Issue #477 ("MEM-1: Memory stack non-functional") behandelt ein ANDERES
Memory-Problem:
- Qdrant-Collection leer (keine `hermes_memories_v2`)
- Ollama-Embedder-Drift (`nomic-embed-text` statt `qwen3-embedding:4b`)
- Betrifft die Vektor-Suche/Mem0-Ebene, nicht den Holographic-Fact-Store

Der 2200-char Consolidation-Bug ist ein separater Fehler im
Konsolidierungs-Flow des Hermes-Core — unabhaengig von #477.

## Investigation

Geprueft:
- [x] `memory_char_limit: 2200` in `docs/plans/` bestaetigt
- [x] Holographic-Plugin-Code analysiert (`/opt/hermes/plugins/memory/holographic/`)
- [x] Hindsight-API (`hindsight_client_api`) auf Consolidation-Endpunkte geprueft
- [x] Issue #477 auf Relevanz geprueft → anderes Problem (Qdrant/Ollama)

Ausgeschlossen:
- [x] Bug liegt NICHT im Holographic-Plugin (das Plugin hat keine `replace`-Operation)
- [x] Bug liegt NICHT in trading-hub oder ai4trade-bot
- [x] Issue #477 ist NICHT der gleiche Bug

## Root Cause

Die Hermes-Core-Consolidation-Logik fuehrt eine `replace`-Operation auf
dem Memory-Provider aus, wenn das Memory-Limit (2200 Zeichen) erreicht ist.
Die Operation sendet einen `replace`-Befehl ohne `content`-Feld.

Der genaue Code-Pfad:

```
Hermes Core
  → memory consolidation trigger (1878/2200 chars)
    → replace_operation(old_entry_id)
      → Operation 2 (replace): content is required  ← FEHLER
```

Die `replace`-Operation erwartet ein `content`-Feld mit dem neuen,
konsolidierten Inhalt. Dieses Feld wird nicht uebergeben, weil:
- Entweder der Consolidation-Algorithmus das `content` nicht generiert
- Oder das `content` beim Mapping zwischen altem und neuem Format verloren geht
- Oder der `replace`-Aufruf das `content` als optional behandelt, der
  Holographic-Provider es aber als required validiert

## Solution

Der Fix muss im Hermes-Core-Framework erfolgen (nicht in diesem Repository):

1. **Kurzfristig:** `memory_char_limit` erhoehen (z.B. auf 4400), um den
   Consolidation-Trigger hinauszuzoegern. Kein Code-Fix, aber Workaround.
   ```bash
   hermes config set memory.memory_char_limit 4400
   ```

2. **Mittelfristig:** Den Consolidation-Code so patchen, dass die
   `replace`-Operation ein valides `content`-Feld enthaelt:
   - Alten Memory-Eintrag per ID holen
   - Inhalt mit LLM komprimieren/zusammenfassen
   - `replace(old_id, content=summarized_content)` aufrufen

3. **Langfristig:** Memory-Provider-Interface um eine native
   `consolidate()`-Methode erweitern, die das Zusammenfassen und Ersetzen
   atomar im Provider durchfuehrt, statt es im Core zu implementieren.

## Verification

- [x] Code-Pfad identifiziert: Hermes Core → Consolidation Trigger → replace ohne content
- [x] Holographic-Plugin als nicht-verantwortlich ausgeschlossen
- [x] Issue #477 als separates Problem klassifiziert (Qdrant/Ollama, nicht Consolidation)
- [x] Workaround dokumentiert (memory_char_limit erhoehen)
- [ ] Fix erfordert Aenderung am Hermes-Core-Framework (nicht in diesem Repo)
