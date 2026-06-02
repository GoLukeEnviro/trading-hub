# PR #3 Clean/Main Rebuild — Completion Pass

**Datum:** 2026-06-02
**Status:** COMPLETED
**Typ:** Bug-Fixes + Dokumentation-Update

---

## Was wurde erledigt

### 1. deploy_cron_scripts.sh — pipefail Bug behoben

**Problem:** `diff "$src_file" "$dst_file" 2>/dev/null | wc -l` scheitert unter `set -euo pipefail`,
weil `diff` exit code 1 zurückgibt wenn Dateien unterschiedlich sind, und pipefail den Fehler
propagiert. Das Script brach beim ersten Drift-Fund ab.

**Fix:** Alle drei Vorkommen des Musters ersetzt durch:
```bash
diff_lines=$( { diff "$src_file" "$dst_file" 2>/dev/null || true; } | wc -l )
```
Das `{ ... || true; }` verhindert, dass pipefail den diff-Exitcode weiterpropagiert.

**Betroffen:** `check_drift()` (Zeile ~109), `deploy()` diff-Prüfung (Zeile ~165), `deploy()` Verify (Zeile ~180)

### 2. portfolio_rebalancer.py — dekommissionierten momentum-Bot entfernt

**Problem:** `BOTS`-Dict enthielt noch den `momentum`-Eintrag (`freqtrade-momentum`), obwohl
dieser Bot seit 2026-05-24 dekommissioniert ist. Das verursachte unnötige DB-Abfragen auf
nicht vorhandene Pfade und verfälschte die Gewichtungsberechnung.

**Fix:** `momentum`-Eintrag vollständig aus dem `BOTS`-Dict entfernt.
Die verbleibenden Bots (freqforge, canary, regime_hybrid, rebel) werden korrekt normalisiert.

### 3. docs/state/current-operational-state.md — aktualisiert

**Problem:** Das Dokument war vom 2026-05-30 20:50 UTC und spiegelte nicht den aktuellen
Systemstand (2026-06-02) wider. Seit dem 30. Mai wurden erhebliche Änderungen durchgeführt:
- MCP-Server-Migration (custom Python → npm bitget-mcp-server)
- Signal-Heartbeat-Konsolidierung (signal-heartbeat + smart-heartbeat → unified-signal-heartbeat)
- FleetRisk-Cursor-Fix
- daily-backup PermissionError-Fix
- Permission Autopilot und Git Guard hinzugefügt
- Container-Fleet-Status aktualisiert (exited hermes-ollama/qdrant, neuer trading-guardian)
- Cron-Job-Tabellen aktualisiert (~37 Jobs statt 33)

**Fix:** Vollständige Neuschreibung des Dokuments mit Stand 2026-06-02.

---

## Geänderte Dateien

```
orchestrator/scripts/deploy_cron_scripts.sh   pipefail-Bug (3 Stellen)
orchestrator/scripts/portfolio_rebalancer.py  momentum-Bot entfernt
docs/state/current-operational-state.md       vollständig aktualisiert
docs/context/pr3-completion-20260602.md       dieser Bericht
```

---

## Safety-Checks

| Check | Status |
|-------|--------|
| Kein Live-Trading aktiviert | ✅ |
| Keine Freqtrade-Configs geändert | ✅ |
| Keine Strategie-Änderungen | ✅ |
| Keine Container neugestartet | ✅ |
| Keine Secrets committed | ✅ |
| dry_run=True überall | ✅ |
