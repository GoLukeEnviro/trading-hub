# Unified-Signal-Heartbeat Scheduler Init — Ergebnis
## 2026-06-01 23:25 UTC

## Ausgangslage

Nach dem Orchestrierungs-Umbau (Commit 8b30a80) wurde `unified-signal-heartbeat` als no_agent Cron-Job angelegt. Der Postcheck um 23:20 UTC zeigte: `last_run_at=null`.

## Vorgehen

1. `cronjob action=run` für job_id `4f8b0d8feae7` ausgeführt
2. `next_run_at` sprang auf `2026-06-01T23:23:54.496549+00:00`
3. Tick-Fenster abgewartet (23:23:54 - 23:25 UTC)
4. Status erneut geprüft

## Ergebnis

| Check | Status |
|-------|--------|
| `action=run` erfolgreich? | ✅ Ja — `next_run_at` aktualisiert |
| Tick um 23:23:54 gefeuert? | ❌ **NEIN** — `last_run_at` bleibt `null` |
| `last_status` nach Tick | `null` — nie ausgeführt |
| Cron-Scheduler-Stall bestätigt | ✅ Ja |

## Diagnose

Der bekannte Cron-Scheduler-Stall-Bug für neue no_agent Jobs hat zugeschlagen:
- `cronjob action=run` initialisiert den Job NICHT (setzt nur `next_run_at`)
- Der Scheduler tickt für diesen Job nicht weiter
- `last_run_at=null` bleibt bis der Job per Delete+Recreate oder Container-Restart initialisiert wird

Dieses Muster ist in `references/cron-scheduler-stall-detection-2026-05-30.md` dokumentiert:
> Delete-and-Recreate, NOT action=run. When error-status crons need clearing: remove + recreate is the only reliable fix.

## Konsequenz

Der Orchestrierungs-Umbau (Commit 8b30a80) ist **architektonisch korrekt und manuell validiert**, aber der `unified-signal-heartbeat` läuft nicht automatisch im Scheduler. Der alte Doppel-Heartbeat ist paused — es gibt aktuell KEINEN aktiven Signal-Heartbeat.

**Das Signal wird dennoch aktuell gehalten** durch:
- Die manuellen Force-Trigger (canonical fresh, latest sync)
- trading_pipeline Layer 3.75 (sync nach jedem Pipeline-Durchlauf)

## Nächster Schritt (laut User-Reihenfolge)

User entscheidet nach folgender Matrix:

| Ergebnis | Nächster Schritt |
|----------|-----------------|
| `action=run` erfolgreich + Tick läuft | Cursor-Stall-Fix |
| `action=run` erfolgreich, aber kein Folge-Tick | **Scheduler-Stall fixen** (aktuell) |
| `action=run` schlägt fehl | jobs.json prüfen |

Aktueller Zustand: **Scheduler-Stall fixen** — erforderlich bevor Cursor-Stall oder P2-Jobs angegangen werden.