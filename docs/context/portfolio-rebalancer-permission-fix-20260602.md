# Portfolio-Rebalancer Permission Fix
**Datum:** 2026-06-02T03:55Z
**Typ:** Code Fix (kein Root, kein Container-Neustart)
**Autor:** Hermes Meta-Orchestrator

---

## Executive Verdict

**FIXED — PermissionError behoben durch Code-Patch + Source-of-Truth reconciliation**

Der portfolio-rebalancer schrieb STATE_FILE und LOG_FILE auf einen Pfad, der UID 1337 gehoerte und vom Hermes-Laufzeit-User (UID 10000) nicht beschreibbar war. Fix: Pfade auf den etablierten Orchestrator-State-Pfad geaendert. Source-of-Truth (Git) und Runtime synchronisiert via deploy_cron_scripts.sh. Dry-Run erfolgreich, kein Trading-Bot beruehrt.

---

## Root Cause

`portfolio_rebalancer.py` verwendete hartcodierte Pfade unter `/home/hermes/projects/trading/orchestrator/state/` und `/home/hermes/projects/trading/orchestrator/logs/`. Diese Pfade wurden von Root-Sessions erstellt und gehoeren UID 1337. Der Hermes-Laufzeit-User (UID 10000) konnte daher nicht schreiben (PermissionError).

**Traceback:**
```
File "portfolio_rebalancer.py", line 173, in run_rebalancer
    with open(STATE_FILE, "w") as f:
PermissionError: [Errno 13] Permission denied: '/home/hermes/projects/trading/orchestrator/state/rebalance_state.json'
```

---

## State File Analysis

| Pfad | Owner | Mode | Problem |
|---|---|---|---|
| /home/.../orchestrator/state/rebalance_state.json | 1337:hermes | 0664 | ALT — Script kann nicht schreiben |
| /home/.../orchestrator/logs/rebalancer.log | 1337:hermes | — | ALT — gleicher Permission-Issue |
| /opt/data/profiles/orchestrator/state/ | hermes:hermes | 0755 | NEU — korrekter Pfad, beschreibbar |
| /opt/data/profiles/orchestrator/logs/ | hermes:hermes | 0755 | NEU — korrekter Pfad, beschreibbar |

---

## Fix Applied

**Datei:** `/opt/data/profiles/orchestrator/scripts/portfolio_rebalancer.py`
**Aenderung:** Zeilen 64-65 — STATE_FILE und LOG_FILE Pfade

```diff
-STATE_FILE = Path("/home/hermes/projects/trading/orchestrator/state/rebalance_state.json")
-LOG_FILE   = Path("/home/hermes/projects/trading/orchestrator/logs/rebalancer.log")
+STATE_FILE = Path("/opt/data/profiles/orchestrator/state/rebalance_state.json")
+LOG_FILE   = Path("/opt/data/profiles/orchestrator/logs/rebalancer.log")
```

Keine Root-Aktion noetig. Kein chown/chmod. Kein Container-Neustart.

---

## Validation Results

| Check | Status | Evidence |
|---|---|---|
| Syntax Check | PASS | py_compile: OK |
| Dry-Run | PASS | Exit code 0, State geschrieben |
| State File | PASS | /opt/data/profiles/orchestrator/state/rebalance_state.json geschrieben |
| PermissionError | GONE | Kein Fehler im Dry-Run |
| Kelly-Berechnung | PASS | 5 Bots bewertet, 2/5 Rebalancing empfohlen |
| utcnow DeprecationWarning | P3 | 3x Warning (nicht blockierend) |

---

## Trading Safety

| Bot | Status | dry_run | Changed? |
|---|---|---|---|
| FreqForge | Up 3h | true | NO |
| Regime-Hybrid | Up 3h | true | NO |
| FreqForge-Canary | Up 3h | true | NO |
| FreqAI-Rebel | Up 3h | true | NO |

Kein Bot restartet. Kein Config geaendert. dry_run unberuehrt.

---

## Naechster cron-Lauf

Der portfolio-rebalancer laeuft naechstes Mal am **2026-06-08T06:00:00Z** (Montag, woechentlich). Der Fix ist im laufenden Dateisystem aktiv — kein Neustart noetig.

---

*Fix abgeschlossen. Keine Root-Aktion. Kein Container-Neustart. Kein Trading-Bot beruehrt.*
