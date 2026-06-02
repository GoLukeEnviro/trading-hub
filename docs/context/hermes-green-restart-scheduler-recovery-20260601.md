# Hermes-Green Restart — Scheduler Recovery Check
## 2026-06-01 23:53 UTC

### Resultat: SCHEDULER STILL BROKEN — Permission Denied auf jobs.json

**Nicht** der Trigger-Fix war kaputt. **Nicht** der delete+recreate war falsch.
Der Restart hat eine Permission-Lücke sichtbar gemacht.

### Root Cause

`/opt/data/profiles/orchestrator/cron/jobs.json` hat Permissions `0600 root:root`.

Nach dem `hermes-green` Restart startet der Gateway-Prozess als User `hermes` (UID 10000) und kann jobs.json nicht lesen. Beweis aus den Gateway-Logs:

```
ERROR cron.jobs: IOError reading jobs.json: Permission denied
ERROR cron.jobs: IOError reading jobs.json: Permission denied
[mehrfach wiederholt]
```

Auch config.yaml ist betroffen:
```
Warning: config.yaml -> env bridge failed: Permission denied
```

Die Permission-Lücke entstand um 23:27:36 UTC beim `cronjob remove` + `cronjob create` des unified-signal-heartbeat (Delete+Recreate). Der Cronjob-Mechanismus schrieb jobs.json als root:root 0600.

### Container State

| Container | Status | Uptime |
|-----------|--------|--------|
| hermes-green | UP | 7 Min (Restart um 23:44 UTC) |
| ai-hedge-fund-crypto | UP, healthy | 49 Min |
| freqtrade-freqforge | UP | 19h |
| freqtrade-freqforge-canary | UP | 19h |
| freqtrade-regime-hybrid | UP | 19h |
| freqai-rebel | UP | 19h |

### Trading Safety

| Bot | dry_run |
|-----|---------|
| FreqForge | ✅ True |
| Canary | ✅ True |
| Regime-Hybrid | ✅ True |
| Rebel | ✅ True |

### Scheduler Evidence

| Messung | Wert |
|---------|------|
| jobs.json Permissions | 0600 root:root |
| jobs.json mtime | 2026-06-01 23:27:36 UTC (Delete+Recreate) |
| Gateway Log | "Permission denied" x8 beim jobs.json-Read |
| no_agent Jobs stuck | 19 Jobs mit last_run_at im 22:xx-Bereich |
| unified-signal-heartbeat | `last_run_at=null`, nie getickt |
| LLM-basierte Jobs | OK (laufen nicht über den no_agent Scheduler) |

### Fix (nicht in diesem Check ausgeführt)

Benötigt: `chmod 644 /opt/data/profiles/orchestrator/cron/jobs.json` (und vermutlich config.yaml)

Der Gateway läuft als User `hermes` (UID 10000) im Container. Die Dateien müssen lesbar sein für diesen User. Ein `chmod 644` als root macht jobs.json lesbar ohne die write-Fähigkeit für den Scheduler zu beeinträchtigen (der Scheduler schreibt nicht direkt in jobs.json, sondern nur über den cronjob API-Mechanismus).

### Nächster Schritt

Fix: `chmod 644` auf jobs.json + config.yaml → dann Scheduler prüft nach, ob er Jobs dispatchen kann.

Entscheidung beim User ob er diesen Fix freigibt.