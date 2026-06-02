# Post-Migration Runtime Check — AI-Hedge-Trigger-Orchestration-Fix
## 2026-06-01 23:20 UTC

### Zusammenfassung

```
Architektur-Fix:           GREEN
Trigger-Race eliminiert:   GREEN
Trading Safety:            GREEN
Cron-Scheduler Execution:  FAIL (bekannter Cron Stall Bug)
```

### Ergebnisse im Einzelnen

| # | Check | Status | Detail |
|---|-------|--------|--------|
| 1 | unified-signal-heartbeat vom Scheduler ausgeführt | 🔴 FAIL | `last_run_at=None, last_status=None, next_run_at=23:00 (stuck)` |
| 2 | signal-heartbeat + smart-heartbeat paused | ✅ PASS | beide `enabled=False state=paused` mit REPLACED-Reason |
| 3 | Kein alter /trigger-Aufrufer aktiv | ✅ PASS | Kein anderer Job referenziert /trigger im Script/Namen |
| 4 | trigger_lock.log: keine parallelen Trigger | ✅ PASS | 3 sequentielle TEST-Aufrufe, 1 echter Trigger (force) |
| 5 | canonical + latest synchron | ✅ PASS | ts identisch: 2026-06-01T23:06:10 |
| 6 | ai-hedge-fund-crypto healthy | ✅ PASS | healthy, running seit 23:02 |
| 7 | 4/4 Trading-Bots dry_run=True | ✅ PASS | Forge/Canary/Hybrid/Rebel alle True |
| 8 | Permission-/Runtime-Drift | ✅ PASS | hermes:hermes, 755, deployed |
| 9 | jobs.json unified-signal-heartbeat | 🔴 FAIL | Job nicht vom Scheduler getickt |

### Cron Scheduler Stall — Bestätigung

Der `unified-signal-heartbeat` (job_id: 4f8b0d8feae7) wurde korrekt in jobs.json angelegt (enabled=true, */15 schedule), aber der Scheduler hat ihn **nicht ausgeführt**. `last_run_at=null` und `next_run_at=23:00:00` (in der Vergangenheit festhängend) sind das klassische Symptom des Cron-Scheduler-Stall-Bugs bei neu erstellten no_agent Jobs.

Das ist der gleiche Bug, der in `references/cron-scheduler-stall-detection-2026-05-30.md` dokumentiert ist.

### Nächster Schritt (vom User vorgegeben)

Keine Fixes, keine Restarts, kein chmod/chown, kein Deploy in diesem Durchlauf. Der Postcheck dient nur der Dokumentation.

Der Fix-Mechanismus ist bekannt:
1. `cronjob action=run` für den unified-signal-heartbeat (initialisiert den ersten Tick) — ODER
2. Delete + Recreate des Jobs (reset Zustand)

Danach läuft der Job selbstständig alle 15 Minuten weiter.