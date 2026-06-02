# Watchdog Log Stale Repair
**Datum:** 2026-06-02T04:58Z
**Typ:** Path-Reconciliation (gleiches Muster wie portfolio-rebalancer)
**Autor:** Hermes Meta-Orchestrator

---

## Executive Verdict

**FIXED — OBSOLETE_LEGACY_LOG + ACTIVE_WRITER_WRONG_PATH**

`watchdog.log` war "stale" aus zwei Gruenden:
1. container_watchdog.sh schrieb LOG/STATE auf `/home/hermes/projects/trading/` (UID 1337) statt `/opt/data/profiles/orchestrator/` (hermes:hermes)
2. watchdog.log wird BY DESIGN nur bei ISSUES beschrieben — silent OK produziert keinen Log-Eintrag

Der echte Health-Indikator ist `container_watchdog_state.json`, der alle 30min aktualisiert wird.

---

## Confirmed Root Cause

| Problem | Details |
|---|---|
| LOG/STATE Pfad | container_watchdog.sh Zeile 16-17: `/home/hermes/projects/trading/` statt `/opt/data/profiles/orchestrator/` |
| mcp_watchdog.sh | Gleicher Fehler: LOG/STATE/SCRIPT auf `/home/hermes/projects/trading/` |
| Legacy Copy | `/opt/data/profiles/orchestrator/logs/watchdog.log` war eine verwaiste alte Kopie (6195 bytes, May 31 23:30Z) |
| Silent OK | watchdog.log wird nur bei ISSUES beschrieben. Keine Issues seit May 31 = keine neuen Eintraege |

---

## Canonical Watchdog and Log Path

| Komponente | Kanonischer Pfad |
|---|---|
| watchdog.log | `/opt/data/profiles/orchestrator/logs/watchdog.log` |
| container_watchdog_state.json | `/opt/data/profiles/orchestrator/state/container_watchdog_state.json` |
| mcp_watchdog.log | `/opt/data/profiles/orchestrator/logs/mcp_watchdog.log` |
| mcp_watchdog_state.json | `/opt/data/profiles/orchestrator/state/mcp_watchdog_state.json` |

---

## Files Changed

| Datei | Aenderung |
|---|---|
| `orchestrator/scripts/container_watchdog.sh` | LOG + STATE Pfad auf `/opt/data/profiles/orchestrator/` |
| `orchestrator/scripts/mcp_watchdog.sh` | LOG + WATCHDOG_LOG + STATE Pfad auf `/opt/data/profiles/orchestrator/` |

---

## Watchdog Inventory

| Name | Job ID | Schedule | Enabled | Status | Modified? |
|---|---|---|---|---|---|
| container-watchdog | 1d044920216f | */30 * * * * | Yes | ok | YES (path fix) |
| mem0-watchdog | d979aaaa0676 | 0 */2 * * * | Yes | ok | No |
| mot-floor-watchdog | ca4933892906 | */10 * * * * | Yes | ok | No |
| critical-event-watchdog | ae387e595ca0 | */10 * * * * | Yes | ok | No |
| mcp-watchdog | NOT in jobs.json | N/A | N/A | decommissioned | YES (path fix for consistency) |

---

## Validation Evidence

| Check | Status | Evidence |
|---|---|---|
| container_watchdog.sh Test-Run | PASS | exit 0, state updated 04:58:15Z |
| Source == Runtime | PASS | diff = 0 Zeilen nach deploy |
| Deploy Contract | PASS | hermes:hermes 0755 |
| Alle Container | PASS | 5/5 running |
| Trading Safety | PASS | 4/4 dry_run=True |
| Scheduler | PASS | nicht restartet |

---

## Safety Proof

- Kein Trading-Bot restartet
- dry_run unveraendert (4/4 True, direkte Config-Lesung)
- Keine Strategy geaendert
- Kein Mem0/Qdrant beruehrt
- Kein Scheduler-Core geaendert

---

## Rollback

```bash
git checkout HEAD~1 -- orchestrator/scripts/container_watchdog.sh orchestrator/scripts/mcp_watchdog.sh
bash orchestrator/scripts/deploy_cron_scripts.sh
```

---

## Remaining Follow-ups

- `/home/hermes/projects/trading/orchestrator/logs/watchdog.log` (88K, UID 1337) ist die alte Git-Pfad-Datei. Nicht geloescht — als Legacy markiert. Kann beim naechsten Cleanup archiviert werden.
- `deploy_cron_scripts.sh` bricht bei ghostbuster.py mit exit 1 ab und deployt nachfolgende Scripts nicht. Das ist ein separater P3-Issue im Deploy-Contract.

---

*Path fix, kein Code-Change, kein Container-Neustart, kein Trading-Bot beruehrt.*
