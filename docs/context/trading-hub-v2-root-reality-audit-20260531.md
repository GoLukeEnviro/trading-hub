# Trading Hub v2.x Root Reality Audit 2026-05-31

## 1. Verdict
**PARTIAL**, not fully autonomous.

## 2. Hermes wirklich down?
**No.**

Evidence:
- `docker inspect hermes-green --format '{{.Name}} status={{.State.Status}} running={{.State.Running}} started={{.State.StartedAt}} pid={{.State.Pid}}'`
- Output: `/hermes-green status=running running=true started=2026-05-30T21:05:26.487017627Z pid=385346`
- `docker ps` shows `hermes-green Up 12 hours`.

## 3. Sind die 4 Bots wirklich down?
**No.**

Evidence from `docker ps`:
- `freqtrade-freqforge Up 13 hours`
- `freqtrade-freqforge-canary Up 13 hours`
- `freqtrade-regime-hybrid Up 13 hours`
- `freqai-rebel Up 13 hours`

Also live:
- `ai-hedge-fund-crypto Up 6 days (healthy)`

## 4. Docker-Zugriff gebrochen?
**Yes, in the `hermes-green` container when running as `hermes` (uid 10000).**

Evidence:
- Host: `/var/run/docker.sock` is `root docker` with mode `660`.
- Host `hermes`: `uid=1337(hermes) ... groups=1337(hermes),110(docker),10000(ftuser)`.
- Container `hermes`: `uid=10000(hermes) gid=10000(hermes) groups=10000(hermes)`.
- Inside container: `docker inspect hermes-green` returns `permission denied while trying to connect to the Docker daemon socket`.
- Inside container: `docker ps --format '{{.Names}} {{.Status}}'` returns `permission denied while trying to connect to the Docker daemon socket`.

Conclusion: the watchdogs that depend on Docker will misread live state when executed inside `hermes-green` as `hermes`.

## 5. Ist `jobs.json` ownership gebrochen?
**Yes.**

Host evidence:
- `stat -c '%A %U %G %u %g %n' /opt/data/profiles/orchestrator/cron/jobs.json`
- Output: `-rwxrwxr-x root ftuser 0 10000 /opt/data/profiles/orchestrator/cron/jobs.json`

Container evidence:
- `docker exec hermes-green stat -c '%A %U %G %u %g %n' /opt/data/profiles/orchestrator/cron/jobs.json`
- Output: `-rw------- root root 0 0 /opt/data/profiles/orchestrator/cron/jobs.json`
- `docker exec -u hermes hermes-green ...` returns `READ_FAIL` and `WRITE_FAIL`.
- `docker logs --tail 200 hermes-green | grep -iE 'permission|jobs.json|cron|scheduler|denied|traceback|error'`
- Output contains repeated: `ERROR cron.jobs: IOError reading jobs.json: [Errno 13] Permission denied: '/opt/data/profiles/orchestrator/cron/jobs.json'`

## 6. Welche Jobs sind failend und warum?

### A. `critical_event_watchdog.py`
Status: **false positive**.

Evidence:
- Run output: `Hermes container DOWN` and `Fleet: Only 0/4 bots running`.
- Live `docker ps` shows the container and all 4 bots are up.
- Inside `hermes-green` as `hermes`, `docker inspect hermes-green` fails with socket permission denied.
- Source logic:
  - `check_hermes()` uses `docker inspect hermes-green`.
  - `check_fleet_emergency()` uses `docker ps --format '{{.Names}}' | grep freqtrade | wc -l`.

Root cause: Docker is unavailable in the cron execution context, so the watchdog reads zero bots and a dead Hermes even though both are live.

### B. `morning_brief.py`
Status: **permission failure**.

Evidence:
- Traceback:
  - `PermissionError: [Errno 13] Permission denied: '/home/hermes/projects/trading/orchestrator/state/morning_brief.json'`
- Container write test:
  - `PermissionError [Errno 13] Permission denied: '/home/hermes/projects/trading/orchestrator/state/morning_brief.json'`
- File metadata in container:
  - `/home/hermes/projects/trading/orchestrator/state/morning_brief.json` is `root` owned, mode `0644`.

### C. `quality_hub_monitor.py`
Status: **permission failure**.

Evidence:
- Traceback:
  - `PermissionError: [Errno 13] Permission denied: '/home/hermes/projects/trading/orchestrator/logs/quality-hub-report.md'`
- Container write test:
  - `PermissionError [Errno 13] Permission denied: '/home/hermes/projects/trading/orchestrator/logs/quality-hub-report.md'`
- File metadata in container:
  - file exists, owner `1337:1337`, but container user is `uid 10000` and is not in group `1337`.

### D. `drawdown_guard.py`
Status: **partial / file-based only**.

Evidence:
- Source line 408: `mode = "docker" if docker_ok else "file-based"`
- Source line 490: `NO_DOCKER: Kein Docker-Zugriff...`
- Live inside `hermes-green` as `hermes`: `drawdown_guard.detect_docker()` returned `False`.
- Log grep shows many entries like `DrawdownGuard v3 START [mode: file-based]` and `NO_DOCKER: Kein Docker-Zugriff...`

Conclusion: the guard is working in its fallback mode, but it cannot validate the live fleet via Docker from this execution context.

### E. `smart_heartbeat.py`
Status: **real stale-signal alert**.

Evidence:
- Run output: `smart_heartbeat failed: age=63.4min; exit=23`
- `hermes_signal.json` mtime: `2026-05-31 08:09:58 UTC`
- Script threshold: `SMART_TRIGGER_MIN = 15.0`

Conclusion: this is not a permission error. The signal is genuinely stale.

### F. Current `jobs.json`
Status: **metadata not updating**.

Evidence:
- `job_count= 10`
- `enabled_count= 10`
- `error_count= 0`
- `last_run_at_none= 10`

This strongly suggests the scheduler state is not being updated from the live execution context.

## 7. Welche Fehler sind false positives?

- Hermes DOWN: false. Containers are up.
- 0/4 bots running: false. All 4 bots are up.
- Docker-related watchdog failures inside `hermes-green`: false positives caused by missing Docker access, not by dead containers.
- `smart_heartbeat.py`: not a false positive; it correctly detected a stale signal.

## 8. Minimaler Fix-Plan

### Must-fix now
1. Make the `hermes-green` runtime identity match the mounted files.
2. Grant the container execution context Docker access or move Docker-dependent checks to a context that actually has it.
3. Fix write ownership only for the proven broken paths.
4. Back up `jobs.json` before touching it.

### Nice-to-have cleanup
1. Add a cooldown so repeated identical Telegram alerts do not spam.
2. Remove stale job names that are no longer in the live cron DB.
3. Standardize file ownership/umask so root-created state files stop happening.

## 9. Proposed commands, not executed

```bash
cp -a /opt/data/profiles/orchestrator/cron/jobs.json /opt/data/profiles/orchestrator/cron/jobs.json.bak.$(date -u +%Y%m%dT%H%M%SZ)

# after UID/GID harmonisation for hermes-green
chown 1337:1337 /opt/data/profiles/orchestrator/cron/jobs.json
chmod 664 /opt/data/profiles/orchestrator/cron/jobs.json

chown 1337:1337 /home/hermes/projects/trading/orchestrator/state/morning_brief.json
chmod 664 /home/hermes/projects/trading/orchestrator/state/morning_brief.json

chown 1337:1337 /home/hermes/projects/trading/orchestrator/logs/quality-hub-report.md
chmod 664 /home/hermes/projects/trading/orchestrator/logs/quality-hub-report.md

# container runtime fix (example target)
# run the Hermes process with uid/gid 1337 and docker group 110
```

## 10. Files written
- `docs/context/trading-hub-v2-root-reality-audit-20260531.md`
- `docs/context/trading-hub-v2-root-reality-audit-20260531.json`
