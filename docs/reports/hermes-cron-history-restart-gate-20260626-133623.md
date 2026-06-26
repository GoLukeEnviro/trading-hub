# Hermes Cron History — Restart Gate Required (YELLOW)

**Date (UTC):** 2026-06-26 13:36:23
**Auditor:** Hermes (orchestrator profile)
**Operation Level:** L3C observation (read-only)
**Final Status:** **YELLOW — restart_required=yes**
**Hook on disk:** ✅ deployed, verified, compiles
**Hook in running process:** ❌ not loaded (Python module cache)
**No restart performed.** Awaiting `APPROVE_RESTART` token from operator.

---

## Executive Verdict

**YELLOW — 92/100**

Disk-Deploy ist sauber durch: `scheduler.py` ist auf Runtime, SHA-verifiziert, kompiliert, Marker korrekt. Aber der **laufende Scheduler-Prozess** hat das Modul beim Start geladen und cached es im RAM — Filesystem-Änderungen werden ohne Prozess-Neustart nicht wirksam. Observation über 312 Sekunden zeigt: Scheduler tickt normal, `jobs.json` updated, **kein** neuer Eintrag in `cron_history.sqlite`. Klassischer YELLOW-Gate.

## Disk Deploy (Phase 5 — done)

| Check | Result |
| --- | --- |
| Runtime scheduler.py SHA | `ce820537e98bc25ae590eba20399bb6ead58297cbd5c2dd7b7cac6f28a99d74a` |
| Source (patched) SHA | `ce820537e98bc25ae590eba20399bb6ead58297cbd5c2dd7b7cac6f28a99d74a` ✅ match |
| Pre-deploy backup SHA | `f2816dea78a62445a3291f9ef77e1efd179bd963fc1c378b97d80de630524ce6` ✅ intact |
| Backup path | `/opt/data/profiles/orchestrator/state/cron_history_patches/scheduler.py.pre-deploy.bak` (97387 B, root:root, Jun 9 15:52) |
| `py_compile` (in-process, /tmp avoid) | PASS |
| Hook markers on Runtime | 1 import block (Z. 45–55), 2 call blocks (Z. 2141–2153, 2159–2171) |

## Verify (Phase 3 — done)

| Check | Result |
| --- | --- |
| `apply_cron_history_hook.py --status` | `state: patched`, `import: present`, `call: present (count=2)` ✅ |
| `apply_cron_history_hook.py --verify` | `ok: True`, `reason: py_compile passed` ✅ |
| Marker count grep | 1/1 import, 2/2 call ✅ |
| Hook call is `try/except` guarded | ✅ both call blocks wrap `_hermes_cron_run_with_history` in try/except |

## Observation (Phase 4 — done, 312s window)

### Baseline (T = 13:30:41 UTC)

| Source | Value |
| --- | --- |
| `cron_history.sqlite` rows | 1 (smoke-test `l3_smoke_20260626T120222Z`, external) |
| `cron_history.sqlite` SHA | `e3a12f7e1546057a8dd1338564c8d6da4e3cd14577e751de93684a3b7104df2c` |
| `jobs.json` SHA | `fec8adb5c5261d65f143150ddd416f956c43630d1cb6a4fe7bb528cbed39924b` |
| Enabled jobs | 44 |

### Post-Observation (T = 13:35:53 UTC, +312s)

| Source | Value | Change |
| --- | --- | --- |
| `cron_history.sqlite` rows | **1** (still smoke-test only) | **NO GROWTH** |
| `cron_history.sqlite` SHA | `e3a12f7e…` (unchanged) | — |
| `jobs.json` SHA | `b784ec939d209ce6a0497b24ec4032e40bab3567480db3c95f503a600187a818` | **CHANGED** |
| Jobs that ticked since baseline | 7 (e.g. `observation-runner` 13:35:01, `ledger-integrity-watchdog` 13:33:01, `Hermes Session Metrics` 13:35:01) | scheduler is alive and ticking |
| New scheduler-driven rows in DB | **0** | — |

### Classification

| Outcome | Observed |
| --- | --- |
| `cron_runs` grew | NO (1 → 1) |
| `jobs.json` advanced | YES (7 jobs) |
| New scheduler-driven row | NONE |
| Scheduler errors after patch | NONE (all 7 ticks returned `ok`) |
| Hook call executed | **NO** — process loaded `scheduler.py` before the deploy; module cache holds old code |

**Verdict:** The hook is correctly on disk and would work for any **fresh** scheduler process start. The currently-running scheduler process is unaffected by the file change because Python loads `.py` files into a module cache at import time and does not re-read them.

## Restart Gate

| Field | Value |
| --- | --- |
| `restart_required` | **yes** |
| Reason | The running Python scheduler process loaded `scheduler.py` before the patch was deployed; the module is cached in memory and not reloaded on file change. |
| Restart performed | **no** |
| Approval needed | `APPROVE_RESTART` (separate prompt, not granted in this run) |

### Restart Candidates

The scheduler is started by the Hermes dashboard/gateway process. The cleanest restart surface is **the gateway**, which restarts the scheduler as part of its lifecycle. Two safe options, both requiring their own approval:

#### Option 1 — Hermes dashboard/gateway restart (recommended)

The Hermes gateway restarts the cron scheduler as part of its normal lifecycle. Triggering a gateway restart causes the scheduler to re-import `scheduler.py` and pick up the patch.

**Concrete command proposal (for your approval only — not executed by this agent):**

```bash
sudo systemctl restart hermes-dashboard   # or the equivalent on this host
```

Exact service name and restart mechanism depends on how the gateway is supervised on this host (`systemd`, `pm2`, `supervisor`, manual docker container, …). Before issuing this command, you should confirm which supervisor runs the gateway and whether `systemctl` is the right tool.

#### Option 2 — Surgical SIGTERM on the scheduler PID only

If you prefer NOT to bounce the dashboard, you can find the scheduler Python process and SIGTERM it; the gateway will respawn it within seconds. The hook will load on the next start.

**Concrete command proposal (for your approval only — not executed by this agent):**

```bash
ps -ef | grep -E '[s]cheduler.py|[h]ermes.*scheduler' | awk '{print $2}'
# Pick the scheduler PID (NOT the dashboard PID), then:
sudo kill -TERM <SCHEDULER_PID>
# Wait 5s, then verify the new PID is alive and loaded the patched file:
ps -ef | grep -E '[s]cheduler.py'
```

**Risks:**
- A 5-second scheduler gap may delay up to 5 jobs by up to one tick (60s). Acceptable for a single restart.
- If the gateway does NOT auto-respawn the scheduler, every job will stop ticking until manual restart — verify auto-respawn behavior first.

### Rollback Path (if restart makes things worse)

```bash
sudo cp -p /opt/data/profiles/orchestrator/state/cron_history_patches/scheduler.py.pre-deploy.bak /opt/hermes/cron/scheduler.py
sudo chmod 644 /opt/hermes/cron/scheduler.py
sudo chown 10000:10000 /opt/hermes/cron/scheduler.py   # restore original owner
```

Then restart again so the old code is loaded.

## Runtime Safety Checklist

| Item | Status |
| --- | --- |
| `jobs.json` edited by agent | **no** |
| Service restart | **no** |
| Broad chmod/chown | **no** |
| Trading parameter changes | **no** |
| Secrets exposed | **no** |
| Scheduler process errors | **no** (7 ticks, all `ok`) |
| Hook marker leak / unredacted secrets in patch | **no** (no secret patterns in patched file) |

## What Must Happen Next

1. **You decide** which restart option to take (gateway restart vs. SIGTERM on scheduler PID).
2. **You confirm** the supervisor mechanism (systemd unit name or equivalent) so the command is accurate.
3. **You issue** `APPROVE_RESTART` in the next prompt. I will then:
   - capture pre-restart state again
   - execute the restart command exactly once
   - capture post-restart state
   - wait one full tick cycle (60s × N where N is the most-frequent job interval)
   - re-measure `cron_history.sqlite` rows
   - if row count grew and a new row has a `job_id` that exists in `jobs.json`, classify as **GREEN**
   - write the GREEN update to this same report, commit, push PR update
4. **If GREEN**: PR #369 (this YELLOW branch) gets an update commit with the GREEN evidence; merge when you sign off.
5. **If still no growth after restart**: stop and escalate — would indicate a deeper issue (writer import path wrong, DB perms, etc.).

## Acceptance Criteria Status

| Criterion | Status |
| --- | --- |
| Root credential never exposed | ✅ |
| Root deploy only after `APPROVE_ROOT_DEPLOY` | ✅ |
| Only approved helper command run as root | ✅ |
| `scheduler.py` verify + py_compile pass after deploy | ✅ |
| **No restart occurs** | ✅ (awaiting separate approval) |
| No `jobs.json` direct edit | ✅ |
| No secrets exposed | ✅ |
| Full GREEN requires real scheduler-written `cron_history.sqlite` row | ⏸ **DEFERRED** — disk-side ready, runtime-side needs restart |
| If restart is needed, stop and request `APPROVE_RESTART` | ✅ (this report) |

## Files in this PR

- `docs/reports/hermes-cron-history-restart-gate-20260626-133623.md` — this report (YELLOW)
- No runtime backups, no SQLite DBs, no logs, no env/secrets.

Commit message (when ready): `docs: record Hermes cron history restart gate (YELLOW — Python module cache holds pre-patch code)`.
