# P2 Job-Error Triage — 2026-06-01T18:06Z

**Analyse als hermes (10000:10000), read-only. Keine Fixes angewandt.**

---

## Executive Verdict

6 Jobs reportieren Error-Status. Davon sind **3 echte PermissionError-Bugs** (dieselbe Root-Ursache: hermes-Container-User hat keine chown/chmod-Rechte auf Host-owned Dateien), **2 ein Docker-Netzwerk-Problem** (ai-hedge-fund-crypto /trigger hängt), und **1 ein LLM-Provider-Konfigurationsfehler** (kein Modell konfiguriert). Kein dry_run-Bruch, kein Sicherheitsrisiko.

---

## Current Error Jobs

| # | Job | Schedule | Script | Last Run | Last Status | Error Summary |
|---|-----|----------|--------|----------|-------------|---------------|
| 1 | portfolio-rebalancer | Mo 06:00 | portfolio_rebalancer.py | 06:00 UTC | error | PermissionError auf rebalance_state.json |
| 2 | ghostbuster | */2h | ghostbuster.py | 18:01 UTC | error | PermissionError: chmod auf orchestrator/logs |
| 3 | signal-heartbeat | */20min | ai_hedge_signal_heartbeat.sh | 18:21 UTC | error | curl exit 23 (write error) + timeout |
| 4 | smart-heartbeat | */10min | smart_heartbeat.py | 18:22 UTC | error | exit 23 (delegiert an signal-heartbeat) |
| 5 | daily-backup | 02:00 | backup_rotation.py | 02:02 UTC | error | PermissionError auf backups/20260525-daily |
| 6 | daily-signal-confidence-monitor | */6h | None (prompt-only) | 18:01 UTC | error | RuntimeError 400: No models provided |

---

## Failure Classification Table

| # | Job | Classification | Root Cause | Severity |
|---|-----|---------------|------------|----------|
| 1 | portfolio-rebalancer | REAL_CODE_BUG | PermissionError: kann rebalance_state.json nicht schreiben (owner=1337:hermes, hermes=10000 hat keine Schreibrechte) | P2 |
| 2 | ghostbuster | REAL_CODE_BUG + SCRIPT_DRIFT | Runtime hat _lookup_hermes_ids/chown/chmod-Code den Git-Version nicht hat. Versucht chmod auf orchestrator/logs (owner=1337). EPERM. | P2 |
| 3 | signal-heartbeat | TIMEOUT + NETWORK | ai-hedge-fund-crypto /trigger endpoint hängt. curl exit 23 (write error) und timeout. Signal stale >150min. | P1 |
| 4 | smart-heartbeat | CASCADE | Delegiert an signal-heartbeat.sh. Fehlerpropagation. Selbst kein Bug. | P2 (Dependent) |
| 5 | daily-backup | REAL_CODE_BUG | PermissionError: shutil.rmtree auf backups/20260525-daily (nicht mehr existent oder permission drift) | P2 |
| 6 | daily-signal-confidence-monitor | LLM_CONFIG_ERROR | Prompt-only Job (kein Script). Hermes-LLM call mit Provider der kein Modell liefert. 400: "No models provided". | P2 |

---

## Evidence Per Job

### 1. portfolio-rebalancer

**Error:** `PermissionError: [Errno 13] Permission denied: /home/hermes/projects/trading/orchestrator/state/rebalance_state.json`
**File owner:** 1337:hermes, mode 664
**Container user:** hermes=10000
**Analysis:** Script läuft als UID 10000, will aber eine Datei schreiben die UID 1337 gehört. group=hermes hat rw (664), aber hermes=10000 ist nicht in der group hermes=1337 im Container. Löst den Konflikt: Container-UID 10000 kann nicht in Host-UID 1337-Dateien schreiben.
**Trigger:** Wöchentlich Mo 06:00. Nächst: 2026-06-08.

### 2. ghostbuster

**Error:** `PermissionError: [Errno 1] Operation not permitted: /home/hermes/projects/trading/orchestrator/logs`
**SCRIPT DRIFT DETECTED:** Runtime (16513 bytes) != Git (15696 bytes). Runtime-Version enthält zusätzliche `_lookup_hermes_ids()`, `os.chown()`, `os.chmod()` Aufrufe die in der Git-Version fehlen.
**Root cause:** Runtime-ghostbuster wurde außerhalb des Git-Deploy-Pfades modifiziert (möglicherweise vom Guardian deploy). Versucht `os.chmod()` auf ein Verzeichnis das nicht ihm gehört → EPERM.
**Trigger:** Alle 2h. Läuft weiter und fails consistently.

### 3. signal-heartbeat

**Error:** `Script exited with code 23`
**Evidence (heartbeat.log):** Consecutive `curl: (23) client returned ERROR on write` und ein `curl: (28) Operation timed out after 180s`.
**Root cause:** ai-hedge-fund-crypto Container /trigger-Endpoint hängt. HTTP-Requests timeout oder fail mit write error. Container ist alive (logs zeigen aktive Sentiment-Analyse), aber der HTTP-Server antwortet nicht auf /trigger.
**Cascade:** smart-heartbeat delegiert an dieses Script und propagiert exit code 23.
**Signal stale:** >150min (smart_heartbeat.log zeigt steigend: 51→160min).
**Trigger:** */20min. Fails seit mindestens 17:31 UTC.

### 4. smart-heartbeat

**Error:** `Script exited with code 23` → `smart_heartbeat failed: age=151.3min; exit=23`
**Analysis:** Kein eigener Bug. smart_heartbeat.py triggert ai_hedge_signal_heartbeat.sh und propagiert dessen exit code. Wenn signal-heartbeat gefixt ist, ist auch dieser OK.
**Trigger:** */10min. Cascading failure.

### 5. daily-backup

**Error:** `PermissionError: [Errno 13] Permission denied: PosixPath(/home/hermes/projects/trading/orchestrator/backups/20260525-daily)`
**Analysis:** `shutil.rmtree()` auf ein Backup-Dir das permission-gesperrt ist. Das Directory existiert nicht mehr (`ls` zeigt Permission denied, aber andere Backups sind sichtbar). Möglicherweise root-owned Unterverzeichnis.
**Trigger:** Täglich 02:00 UTC. Nächst: 2026-06-02 02:00.

### 6. daily-signal-confidence-monitor

**Error:** `RuntimeError: Error code: 400 - {error: {message: No