# ai-hedge-fund-crypto /trigger Recovery — 2026-06-01T18:50Z

**P1 Controlled Container Recovery. Als hermes (10000:10000) ausgeführt.**

---

## Executive Verdict

Container-Restart allein löst das Problem **nicht dauerhaft**. Die Root Cause ist ein architektonisches Problem: ai-hedge-fund-crypto hat keinen Request-Queueing-Mechanismus. Der HTTP-Server blockiert bei parallelen /trigger Requests, was zu einem Server-Freeze führt. Der Cron-Job signal-heartbeat (alle 20min) und smart-heartbeat (alle 10min) kollidieren regelmäßig.

**Ergebnis:** Container ist nach Restart funktionsfähig (generiert Signal in ~60s, /health antwortet), aber das System fällt innerhalb weniger Minuten wieder in denselben Blockade-Zustand zurück sobald parallele Triggers eintreffen.

**Echte Fix-Strategie (braucht Approval):**
1. Lock-File-Mechanismus im heartbeat.sh (verhindert parallele Triggers)
2. Oder: signal-heartbeat Interval von */20min auf */45min erhöhen
3. Oder: ai-hedge-fund-crypto /trigger-Endpoint mit Request-Queueing versehen

---

## Pre-State

| Item | Value |
|------|-------|
| ai-hedge-fund-crypto | Up 16 hours (healthy) |
| freqtrade-freqforge | Up 14 hours |
| freqtrade-freqforge-canary | Up 14 hours |
| freqtrade-regime-hybrid | Up 14 hours |
| freqai-rebel | Up 14 hours |
| hermes_signal.json age | 7.6 min |
| latest/hermes_signal.json age | 180.5 min (STALE) |
| 4/4 bots dry_run=True | Ja |
| /trigger | Hängend (timeout + curl exit 23) |
| /health | Nicht erreichbar via 127.0.0.1:8410 |

---

## Restart Result

**Erster Restart (18:51 UTC):**
- Container kam hoch, Startup-Signal generiert (7 pairs, 104.4s)
- /health antwortete über Container-IP 172.18.0.6:8080
- /trigger mit 120s Timeout: HTTP 200, 98.7s

**Problem:** Manuelle Trigger-Tests + Cron-Jobs überlasteten den Single-Threaded HTTP-Server. Container wurde unhealthy und /trigger blockierte erneut.

**Zweiter Restart (19:05 UTC):**
- Container kam hoch, Startup-Signal generiert (7 pairs, 59.3s)
- /health antwortete korrekt
- Keine manuellen Trigger-Aufrufe durchgeführt
- Cron-Job feuerte trotzdem nach 4min und blockierte Server erneut

---

## Trigger Recovery

**/trigger funktioniert prinzipiell:** HTTP 200, 7 pairs, ~60-100s Dauer.

**Problem:** Kein Queueing. Bei parallelen Requests:
1. Cron signal-heartbeat */20min → curl -m 180 → blockiert Server für ~100s
2. Währenddessen: /health timeout (Server beschäftigt)
3. Wenn nächste Trigger kommt: Connection reset / timeout / write error (curl 23)
4. Server stuck bis Container-Restart

**Port 8410:** Nach Restart nicht bindend. Docker Port-Mapping (8080→8410) funktioniert nicht. Heartbeat-Skript verwendet aber Container-IP (172.18.0.6:8080) — also kein direkter Blocker.

---

## Signal Freshness

| File | Pre-Restart | Nach Restart (clean) | Problem |
|------|------------|----------------------|---------|
| hermes_signal.json | 7.6min | 1-5min | OK (Startup-Signal) |
| latest/hermes_signal.json | 180.5min | 196-201min | **STALE — wird nie aktualisiert** |

**latest/-Bug:** Das heartbeat.sh kopiert nur nach `latest/` wenn der /trigger-Aufruf erfolgreich durchläuft. Da /trigger regelmäßig blockiert, wird `latest/` nicht mehr aktualisiert. Der smart_heartbeat.py liest aber `latest/hermes_signal.json` für die Age-Berechnung → perpetual cascade failure.

---

## Heartbeat Recovery

**signal-heartbeat (*/20min):** Kritisch. Jeder Aufruf dauert ~100-180s und blockiert den ai-hedge-fund-crypto HTTP-Server. Wenn ein Aufruf im Timeout läuft, startet der nächste und kollidiert.

**smart-heartbeat (*/10min):** Cascading. Delegiert an signal-heartbeat.sh. Propagiert exit code 23/28.

**Erwartung nach Fix:** Wenn Lock-File oder erhöhtes Interval implementiert wird, sollten beide Jobs stabil laufen.

---

## Trading Safety

| Check | Status |
|-------|--------|
| freqtrade-freqforge dry_run=True | ✅ |
| freqtrade-freqforge-canary dry_run=True | ✅ |
| freqtrade-regime-hybrid dry_run=True | ✅ |
| freqai-rebel dry_run=True | ✅ |
| Alle 4 Bots laufen | ✅ |
| Keine Config-Änderung | ✅ |
| Kein dry_run=False | ✅ |

**Kein Trading-Safety-Regression.**

---

## Remaining Issues

| # | Issue | Severity | Fix |
|---|-------|----------|-----|
| 1 | ai-hedge-fund-crypto /trigger hat kein Request-Queueing | P1-Architektur | Lock-File im heartbeat.sh ODER Interval erhöhen ODER Server-Q |
| 2 | latest/hermes_signal.json wird nicht aktualisiert | P2 | heartbeat.sh muss latest/-Copy auch bei startup-Signal machen |
| 3 | Port 8410 Docker-Mapping funktioniert nicht nach Restart | P3 | Container compose/port-Config prüfen |
| 4 | signal-heartbeat */20min ist zu aggressiv für ~100s Trigger | P1 | Interval auf */45min oder */60min erhöhen |
| 5 | smart-heartbeat */10min triggert signal-heartbeat noch öfter | P2 | Cascade-Intervall anpassen |

---

## Next Action

**Approval benötigt für:**
1. signal-heartbeat Interval: */20min → */45min (jobs.json Änderung)
2. heartbeat.sh: Lock-File-Mechanismus einbauen (Script-Änderung)
3. latest/-Copy bei Container-Startup sicherstellen

**Kein weiterer Container-Restart ohne Fix — das Problem ist architektonisch, nicht transient.**
