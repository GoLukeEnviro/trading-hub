# Trading Hub v2.x GAP Audit — 2026-05-31

**Auditor:** Independent Systems Audit (Claude Agent)
**Date:** 2026-05-31 08:48 UTC
**Host:** Agent0 | **User:** hermes (uid=1337, gid=1337, groups: docker(110), ftuser(10000))
**Repo:** `/home/hermes/projects/trading` — dirty working tree, branch at `e7a43c5`
**Scope:** READ-ONLY — no destructive actions taken during audit

---

## Executive Verdict

**Trading Hub v2.x is NOT autonomous. Status: PARTIAL.**

The system is partially operational: 25 of 38 cron jobs execute, all 4 trading bots are running in dry-run mode, Docker access works from both host and container, and the external systemd guardian is healthy. However, **11 critical monitoring and alerting jobs have never executed** because the scheduler cannot read its own `jobs.json` file (owned by `root:root 0600`), and multiple state/log files are blocked by ownership mismatches. The documentation claim of "SELBSTREGENERIEREND — Self-Healing Level erreicht" is **false**.

---

## Top 5 Findings

### Finding 1: CRITICAL — Scheduler Cannot Read jobs.json
- **File:** `/opt/data/profiles/orchestrator/cron/jobs.json` (inside Hermes container)
- **Owner:** `root:root 0600`
- **Scheduler process:** `hermes gateway run` (PID 23, running as hermes user)
- **Evidence:** Continuous `ERROR cron.jobs: IOError reading jobs.json: [Errno 13] Permission denied` in container logs (every 60 seconds)
- **Impact:** 11 of 38 cron jobs have `last_run_at: None` — they have NEVER executed since creation
- **Affected jobs:** signal-heartbeat, smart-heartbeat, hermes-standby-monitor, config-diff-detector, fleetrisk-auto-params, riskguard-service, critical-event-watchdog, morning-brief-daily, morning-brief-1040, daily-backup, quality-hub-monitor

### Finding 2: HIGH — Root-Owned State/Log Files Block Writes
- **Directories owned by root:hermes (mode 755, no group write):**
  - `orchestrator/state/riskguard/` — `root:hermes drwxr-sr-x`
  - `orchestrator/state/config_diff/` — `root:hermes drwxr-sr-x`
  - `orchestrator/state/auto_params/` — `root:hermes drwxr-sr-x`
  - `orchestrator/state/standby/` — `root:hermes drwxr-sr-x`
- **Files owned by root (mode 644):**
  - `orchestrator/state/morning_brief.json` — `root:hermes -rw-r--r--`
  - `orchestrator/state/riskguard/riskguard_state.json` — `root:hermes -rw-r--r--`
  - `orchestrator/state/riskguard/riskguard_audit.jsonl` — `root:hermes -rw-r--r--`
  - `orchestrator/state/riskguard/riskguard_health.json` — `root:hermes -rw-r--r--`
  - `orchestrator/state/config_diff/config_drift.log` — `root:hermes -rw-r--r--`
  - `orchestrator/state/config_diff/config_diff_health.json` — `root:hermes -rw-r--r--`
  - `orchestrator/state/auto_params/auto_params_health.json` — `root:hermes -rw-r--r--`
  - `orchestrator/state/auto_params/auto_params_actions.jsonl` — `root:hermes -rw-r--r--`
  - `orchestrator/state/standby/hermes_health.json` — `root:hermes -rw-r--r--`
  - `orchestrator/state/standby/standby.lock` — `root:hermes -rw-r--r--`
- **Impact:** Telegram PermissionError reports for morning_brief.json and quality-hub-report.md are real — scripts running as hermes user cannot write to root-owned files
- **Root cause:** Container processes create files as root (container runs as uid=0), but the host-side hermes user (uid=1337) cannot modify them

### Finding 3: HIGH — Two Conflicting Cron Systems
- **Gateway cron (default):** `/opt/data/cron/jobs.json` — `hermes:hermes 0600`, contains `{"jobs": []}` (EMPTY)
- **Profile cron:** `/opt/data/profiles/orchestrator/cron/jobs.json` — `root:root 0600`, contains 38 jobs (11 stuck, 27 active)
- **Host-side copy:** `/opt/data/profiles/orchestrator/cron/jobs.json` on the HOST is a STALE 10-job copy from 2026-05-19
- **The bind mount:** `/opt/hermes-green/config -> /opt/data` means the container sees the same filesystem, but the HOST path `/opt/data/` may point to a different volume
- **Impact:** Confusion about which scheduler is active; the guardian script on the host reads the stale 10-job copy

### Finding 4: MEDIUM — All Docker Failures Are False Negatives
- **Live evidence:** All 5 containers are RUNNING:
  - `hermes-green`: Up 12h, `running true`
  - `freqtrade-freqforge`: Up 13h, `running true`
  - `freqtrade-freqforge-canary`: Up 13h, `running true`
  - `freqtrade-regime-hybrid`: Up 13h, `running true`
  - `freqai-rebel`: Up 13h, `running true`
- Docker socket IS mounted in Hermes container: `/var/run/docker.sock -> /var/run/docker.sock`
- Docker CLI IS available inside container and works as root
- **Telegram "0/4 bots" reports are FALSE** — caused by scheduler context not Docker failure
- **Telegram "Hermes container DOWN" is FALSE** — container is running, but watchdog scripts couldn't detect it due to scheduler issues

### Finding 5: MEDIUM — Script Version Drift
- Profile scripts (inside container) are OLDER versions than repo scripts:
  - `drawdown_guard.py` profile: v2 (16784 bytes, May 19) vs repo: v3 (28398 bytes, May 29)
  - `container_watchdog.sh` profile: 1462 bytes vs repo: 4229 bytes
- Some profile scripts are missing entirely from the profile dir (only in repo)
- The `trading_pipeline.py` profile version is 30873 bytes vs repo 33732 bytes

---

## Failure Timeline from Telegram

| Telegram Symptom | Root Cause Classification | Evidence |
|---|---|---|
| critical-event-watchdog exits code 1, Hermes container DOWN | **False negative** — container is running, script never dispatched | `docker inspect` shows running=true |
| Fleet: Only 0/4 bots running | **False negative** — all 4 bots running | `docker ps` shows all 4 Up 13h |
| drawdown-guard Docker=False / NO_DOCKER | **Scheduler context issue** — Docker works when run manually | Manual run shows `Docker=True` |
| container-watchdog probe stale, no Docker | **Scheduler context issue** — same root cause | Docker works from container |
| morning-brief PermissionError morning_brief.json | **Real permission wall** — file owned by root:hermes 644 | `namei -l` confirms ownership |
| quality-hub-monitor PermissionError quality-hub-report.md | **Intermittent** — file currently owned by hermes:hermes 664 | May have been root-owned earlier |
| fleet-auto-repair 0/4 bots not running | **False negative** — same Docker context issue | `docker ps` confirms all running |
| UID mismatch hermes 10000 vs 1337/root | **Confirmed** — container creates files as root (uid 0) | File ownership analysis |
| "Self-Healing: all green" contradiction | **Partial truth** — 25/38 jobs work, 11 never fired | jobs.json analysis |

---

## Cron Job Audit

### Total Jobs: 38 (profile cron)

| Category | Count | Details |
|---|---|---|
| Enabled, executing, status=ok | 25 | trading-pipeline, drawdown-guard, fleet-auto-repair, etc. |
| Enabled, never executed (last_run_at=None) | 11 | See Finding 1 |
| Disabled/paused | 1 | 72h Research Fleet Monitor (COMPLETED) |
| Error status | 0 | No jobs in error state |

### Stuck Jobs Detail (last_run_at = None)

| Job Name | Schedule | Script | no_agent |
|---|---|---|---|
| signal-heartbeat | */20 | ai_hedge_signal_heartbeat.sh | true |
| smart-heartbeat | */10 | smart_heartbeat.py | true |
| hermes-standby-monitor | */5 | hermes_standby_monitor.py | true |
| config-diff-detector | 0 * * * * | config_diff_detector.py | true |
| fleetrisk-auto-params | */15 | fleet_risk_auto_params.py | true |
| riskguard-service | */30 | riskguard_service.py | true |
| critical-event-watchdog | */10 | critical_event_watchdog.py | true |
| morning-brief-daily | 0 8 * * * | morning_brief.py | true |
| morning-brief-1040 | 40 10 * * * | morning_brief.py | true |
| daily-backup | 0 2 * * * | backup_rotation.py | true |
| quality-hub-monitor | 0 8 * * * | quality_hub_monitor.py | true |

### Host-side Guardian (systemd)

- **Timer:** `trading-cron-guardian.timer` — every 5 minutes, PERSISTENT
- **Service:** `trading-cron-guardian.service` — runs as `hermes`, supplementary group `docker`
- **Status:** HEALTHY — log shows continuous "All checks passed" every 5 minutes
- **Function:** Checks signal freshness, jobs.json integrity, missing scripts — does NOT execute profile cron jobs

---

## Permission and Ownership Audit

### Permission Matrix

| Path | Owner | Group | Mode | Writable by hermes? |
|---|---|---|---|---|
| orchestrator/state/ | hermes | hermes | 2775 | YES (group) |
| orchestrator/state/riskguard/ | root | hermes | 755 | NO |
| orchestrator/state/config_diff/ | root | hermes | 755 | NO |
| orchestrator/state/auto_params/ | root | hermes | 755 | NO |
| orchestrator/state/standby/ | root | hermes | 755 | NO |
| orchestrator/state/morning_brief.json | root | hermes | 644 | NO |
| orchestrator/logs/ | hermes | ftuser | 2775 | YES (hermes in ftuser group) |
| orchestrator/logs/quality-hub-report.md | hermes | hermes | 664 | YES |
| profile cron/jobs.json (container) | root | root | 600 | NO |
| default cron/jobs.json (container) | hermes | hermes | 600 | YES (but empty) |

---

## Docker Access Audit

- **Docker CLI:** Available at `/usr/bin/docker` on host and inside container
- **Docker socket:** `/var/run/docker.sock` owned by `root:docker`, hermes is in docker group
- **Container socket mount:** YES — `/var/run/docker.sock -> /var/run/docker.sock`
- **Container user:** Processes run as `hermes` (gateway) and `root` (CLI session)
- **Docker from container:** Works — `docker exec hermes-green docker ps` returns all 16 containers
- **Verdict:** Docker access is functional. All "Docker=False" reports are false negatives from scheduler context, not actual Docker failures.

---

## False Positives vs Real Failures

### False Positives (Telegram Spam)
1. "Hermes container DOWN" — container is UP
2. "Fleet: 0/4 bots running" — all 4 bots are UP
3. "Docker=False / NO_DOCKER" — Docker works from all contexts tested
4. "container-watchdog probe stale" — all containers healthy

### Real Failures
1. 11 cron jobs have NEVER executed (29% of scheduled jobs)
2. Permission walls block state/log writes for 6+ files
3. jobs.json ownership prevents the scheduler from reading job definitions
4. Documentation claims "self-healing" but 11 watchdog jobs are dead
5. Script version drift: profile has v2, repo has v3

---

## Security Risks

1. **jobs.json owned by root:root 0600** — while secure from read perspective, it blocks the legitimate scheduler. This is a misconfiguration, not a security feature.
2. **Container runs as root for CLI sessions** — PID 602 runs as root, creating root-owned files on the bind-mounted host filesystem
3. **Docker socket mounted in container** — container can control the host Docker daemon (expected for monitoring, but increases attack surface)
4. **No system crontab for hermes** — no fallback execution mechanism beyond systemd timer

---

## Minimal Fix Plan (PROPOSED — NOT EXECUTED)

### Stage 1: Restore Scheduler Access (IMMEDIATE)

```bash
# PROPOSED COMMANDS — DO NOT EXECUTE WITHOUT USER APPROVAL

# Fix jobs.json ownership inside the container
docker exec -u root hermes-green chown hermes:hermes /opt/data/profiles/orchestrator/cron/jobs.json
docker exec -u root hermes-green chmod 600 /opt/data/profiles/orchestrator/cron/jobs.json

# Verify the scheduler can now read it
docker exec hermes-green cat /opt/data/profiles/orchestrator/cron/jobs.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Jobs: {len(d[\"jobs\"])}')"
```

### Stage 2: Fix Root-Owned State Files (IMMEDIATE)

```bash
# PROPOSED COMMANDS — DO NOT EXECUTE WITHOUT USER APPROVAL

# Fix state directories
sudo chown -R hermes:hermes /home/hermes/projects/trading/orchestrator/state/riskguard/
sudo chown -R hermes:hermes /home/hermes/projects/trading/orchestrator/state/config_diff/
sudo chown -R hermes:hermes /home/hermes/projects/trading/orchestrator/state/auto_params/
sudo chown -R hermes:hermes /home/hermes/projects/trading/orchestrator/state/standby/
sudo chown hermes:hermes /home/hermes/projects/trading/orchestrator/state/morning_brief.json

# Set group-write for collaborative access
sudo chmod 775 /home/hermes/projects/trading/orchestrator/state/riskguard/
sudo chmod 775 /home/hermes/projects/trading/orchestrator/state/config_diff/
sudo chmod 775 /home/hermes/projects/trading/orchestrator/state/auto_params/
sudo chmod 775 /home/hermes/projects/trading/orchestrator/state/standby/
```

### Stage 3: Sync Profile Scripts to Latest (SCHEDULED)

```bash
# PROPOSED COMMANDS — DO NOT EXECUTE WITHOUT USER APPROVAL

# Copy latest scripts from repo to profile dir
for script in drawdown_guard.py container_watchdog.sh trading_pipeline.py; do
  cp /home/hermes/projects/trading/orchestrator/scripts/$script \
     /opt/hermes-green/config/profiles/orchestrator/scripts/$script
  chown hermes:hermes /opt/hermes-green/config/profiles/orchestrator/scripts/$script
done
```

### Stage 4: Fix Recurring Root Ownership (PREVENTION)

```bash
# PROPOSED — Prevent future root ownership drift
# Option A: Run Hermes CLI session as hermes user instead of root
# Option B: Add a cron job that fixes ownership every hour
# Option C: Use setgid on directories to ensure new files inherit group

# Option C example:
sudo chmod g+s /home/hermes/projects/trading/orchestrator/state/riskguard/
sudo chmod g+s /home/hermes/projects/trading/orchestrator/state/config_diff/
sudo chmod g+s /home/hermes/projects/trading/orchestrator/state/auto_params/
sudo chmod g+s /home/hermes/projects/trading/orchestrator/state/standby/
```

### Stage 5: Documentation Correction

- Update `docs/state/current-operational-state.md` to reflect PARTIAL autonomy status
- Remove "SELBSTREGENERIEREND" claim until all 38 jobs execute reliably
- Add a health-check endpoint that verifies jobs.json readability

---

## Validation Plan After Fixes

1. Run `docker exec hermes-green cat /opt/data/profiles/orchestrator/cron/jobs.json` — should succeed without error
2. Wait 10 minutes, then check container logs for absence of Permission denied errors
3. Verify that stuck jobs now show `last_run_at != None`:
   ```bash
   docker exec hermes-green python3 -c "
   import json
   with open('/opt/data/profiles/orchestrator/cron/jobs.json') as f:
       d = json.load(f)
   stuck = [j['name'] for j in d['jobs'] if j.get('last_run_at') is None]
   print(f'Stuck: {len(stuck)} — {stuck}')
   "
   ```
4. Manually trigger stuck jobs and verify output
5. Monitor Telegram for reduced false-positive alerts over 24h

---

## Rollback Plan

1. If fixes cause issues, revert ownership:
   ```bash
   sudo chown -R root:hermes /home/hermes/projects/trading/orchestrator/state/riskguard/
   # (repeat for each directory)
   ```
2. Restore original jobs.json from backup:
   ```bash
   docker exec hermes-green cp /opt/data/profiles/orchestrator/cron/jobs.json.bak.20260523T150144Z \
     /opt/data/profiles/orchestrator/cron/jobs.json
   ```
3. The systemd guardian continues working regardless — it reads the host-side copy

---

## Open Questions / Unknowns

1. **Why do 25 jobs execute if jobs.json is unreadable?** — Likely they run from a root-owned Claude CLI session (PID 602) that CAN read root-owned files, while the gateway scheduler (PID 23, hermes user) cannot.
2. **When did jobs.json become root-owned?** — File birth: 2026-05-31 08:37 (today). It was RECREATED by a root process, overwriting the previous hermes-owned version.
3. **Will the 11 stuck jobs auto-recover after permission fix?** — The scheduler has grace-based fast-forward logic. After fixing permissions, the jobs should fire on their next scheduled tick.
4. **Is there a risk of job stampede?** — If all 11 jobs fire simultaneously after fix, there could be a burst of Telegram messages and concurrent script execution. Monitor load after fix.
5. **Why is the host-side jobs.json stale (10 jobs vs 38)?** — The host sees `/opt/data/profiles/orchestrator/cron/jobs.json` which is NOT the bind mount target. The container sees a different file at the same path, suggesting a Docker volume overlay.

---

## Truth Table

| Subsystem | Telegram Claim | Live Evidence | Verdict | Impact | Fix Priority |
|---|---|---|---|---|---|
| Hermes container | DOWN | Up 12h, running=true | **False negative** | Spam alerts | P2 |
| FreqForge container | 0/4 bots running | Up 13h, running=true | **False negative** | Spam alerts | P2 |
| Canary container | 0/4 bots running | Up 13h, running=true | **False negative** | Spam alerts | P2 |
| Regime-Hybrid container | 0/4 bots running | Up 13h, running=true | **False negative** | Spam alerts | P2 |
| Rebel container | 0/4 bots running | Up 13h, running=true | **False negative** | Spam alerts | P2 |
| Docker access (cron context) | Docker=False | Works from host+container | **False negative** | Wrong diagnosis | P2 |
| State dir write access | PermissionError | root:hermes 755 dirs | **Real failure** | State not saved | P1 |
| Logs dir write access | PermissionError | Mostly OK now | **Intermittent** | Some logs lost | P2 |
| Morning brief | Fails | Runs OK manually | **Scheduler-blocked** | No daily brief | P1 |
| Critical watchdog | Exits code 1 | Runs OK manually | **Scheduler-blocked** | No monitoring | P1 |
| DrawdownGuard | Docker=False | Docker=True when manual | **False negative** | Wrong mode | P2 |
| Fleet auto repair | 0/4 bots | All 4 running | **False negative** | No repair needed | P2 |
| Config diff detector | Never runs | Runs OK manually | **Scheduler-blocked** | No drift detection | P1 |
| Auto params | Never runs | Runs OK manually | **Scheduler-blocked** | No auto-tuning | P1 |
| RiskGuard service | Never runs | Runs OK manually | **Scheduler-blocked** | No risk auditing | P1 |
| Quality hub monitor | PermissionError | Runs OK, writes OK | **Was real, may be fixed** | Quality gaps | P2 |
| Self-healing claims | "All green" | 11/38 jobs dead | **Partially false** | False confidence | P1 |
| Signal freshness | Stale reports | Fresh (signal_age < 10min) | **OK** | No issue | — |
| External guardian | Not mentioned | Healthy, every 5min | **OK** | Baseline monitor | — |
