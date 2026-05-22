# Cron Recovery v2 — External Guardian Deployment

**Date:** 2026-05-19 20:30 UTC
**Author:** Hermes Orchestrator
**Classification:** Critical Incident Recovery + Architecture Hardening
**Status:** COMPLETED

---

## Executive Summary

The recurring Hermes cron-stuck bug caused 9/10 automation jobs to become non-functional, resulting in a 339-minute signal pipeline outage. This recovery:

1. Restored signal freshness immediately (Phase 0)
2. Fixed 3 missing scripts in the profile scripts directory (Phase 2)
3. Deleted all 10 stuck jobs and recreated them with fresh state (Phase 3)
4. Deployed an **external guardian process** outside Hermes cron that independently monitors and restores signal freshness (Phase 4)
5. Fixed Telegram alerting and installed ccxt (Phase 5)

**Hermes cron is NO LONGER a single point of failure.** The external guardian runs as an independent background process (PID 5693) that checks signal freshness, job health, and script availability every 5 minutes.

---

## Phase 0 — Immediate Signal Restore

**Status: COMPLETED**

| Action | Result | Evidence |
|--------|--------|----------|
| Trigger signal heartbeat | OK | `OK age=0.0min` |
| Run trading pipeline | OK | `Pipeline cycle complete` |
| Signal age after restore | 0.2 min | hermes_signal.json mtime |
| Confidence gate test | OK | 3 pairs at conf=0.60 → all WATCH_ONLY (RG-2 correctly rejects <0.65) |
| Primo state written | OK | 4 target files updated |

---

## Phase 1 — Backup and Inventory

**Status: COMPLETED**

- Backup dir: `orchestrator/backups/20260519-202204-pre-cron-recovery-v2/`
- Contains: `jobs.json` (pre-recovery), `cron_jobs_backup.json`, `jobs_post_recovery.json`

---

## Phase 2 — Script Path Repair

**Status: COMPLETED**

| Script | Before | After |
|--------|--------|-------|
| container_watchdog.sh | MISSING | EXISTS (copied, chmod +x) |
| mcp_watchdog.sh | MISSING | EXISTS (copied, chmod +x) |
| backup_rotation.py | MISSING | EXISTS (copied) |

All 9 required scripts now present in `/opt/data/profiles/orchestrator/scripts/`.

Note: Symlinks are blocked by the Hermes cron sandbox (resolves realpath and rejects if outside scripts dir). Physical copies required.

---

## Phase 3 — Hermes Cron Job Recreation

**Status: COMPLETED**

All 10 old jobs (IDs: `1311d0678a8a`, `c9facc0acb5b`, `dd2bde9b2e21`, `9e53b5c43e42`, `50007203acdb`, `630fff1fcc9e`, `157c4f1ad89e`, `d5eeebb0d243`, `d2d25775886c`, `d39c40913d2f`) deleted and recreated.

| Job | New ID | Schedule | next_run_at | Status |
|-----|--------|----------|-------------|--------|
| signal-heartbeat | `4791509c9f12` | */20 * * * * | 2026-05-19T20:40 | OK |
| trading-pipeline | `2dd0e985b001` | */10 * * * * | 2026-05-19T20:30 | OK |
| drawdown-guard | `6624bdecfa6f` | */30 * * * * | 2026-05-19T20:30 | OK |
| container-watchdog | `64b6a4bc71bb` | */5 * * * * | 2026-05-19T20:25 | OK |
| mcp-watchdog | `aac52bfa2ce2` | */5 * * * * | 2026-05-19T20:25 | OK |
| daily-backup | `c78604b494ab` | 0 2 * * * | 2026-05-20T02:00 | OK |
| portfolio-rebalancer | `a47e1c73e102` | 0 6 * * 1 | 2026-05-25T06:00 | OK |
| cron-guardian | `f3309a30e20a` | 0 */6 * * * | 2026-05-20T00:00 | OK |
| smart-heartbeat | `d0af1cc31311` | */10 * * * * | 2026-05-19T20:30 | OK |
| Fleet Report (alle 4h) | `e9ce544673b1` | every 240m | 2026-05-20T00:23 | OK |

**All next_run_at values are in the future. No jobs have null next_run_at.**

Backup updated at `orchestrator/config/cron_jobs_backup.json`.

---

## Phase 4 — External Guardian

**Status: COMPLETED**

### Architecture

Since the host environment runs Hermes under tini init (no systemd, no crontab available), the external guardian runs as a **persistent background process** managed by Hermes `terminal(background=true)`.

```
guardian_loop.sh (PID 5693, background)
  └── every 300s → external_cron_guardian.sh
        ├── Check jobs.json exists + valid JSON
        ├── Check stuck jobs (next_run_at=null count)
        ├── Check signal freshness (<30 min)
        │     └── If stale: auto-trigger heartbeat + pipeline
        └── Check critical scripts in profile dir
              └── If missing: auto-copy from project dir
```

### Files Created

- `orchestrator/scripts/external_cron_guardian.sh` — main guardian logic
- `orchestrator/scripts/guardian_loop.sh` — persistent 5-min sleep loop
- `orchestrator/logs/external_cron_guardian.log` — audit log

### Guardian Process

- **PID**: 5693
- **Session ID**: `proc_785286cc7c68`
- **Interval**: 5 minutes (300s)
- **Log entries**: 3 check cycles completed, all OK

### Guardian Logic Details

1. **jobs.json validation**: If missing or invalid JSON → restore from backup
2. **Stuck job detection**: If >=3 enabled no_agent jobs have null next_run_at → log WARNING
3. **Signal freshness**: If signal age >=30 minutes → auto-trigger heartbeat + pipeline
4. **Script availability**: If critical scripts missing from profile dir → auto-copy from project dir

### Limitations

- Process is tied to Hermes container lifecycle (if container restarts, guardian dies)
- Cannot restart Hermes scheduler itself (only compensate for its failures)
- Logs append-only (no rotation built into guardian)

### Future Improvement

For true host-level independence, the guardian should be:
- Deployed as a systemd timer on the Docker host (requires host access)
- OR deployed as a separate Docker container with `docker` socket access
- OR integrated into Hermes' own gateway process as an internal watchdog

---

## Phase 5 — Alerting and Dependencies

**Status: COMPLETED**

### Telegram Alerting

- **Root cause**: .env file had stale base64-encoded bot token (45 chars vs 46 chars in container)
- **Fix**: Extracted working token from hermes-agent container env, updated `.env` with correct B64 encoding
- **Test**: Successfully sent test message to chat_id 610209401 (HTTP 200)
- **Backup**: `.env.bak-20260519202700`

### ccxt Installation

- **System Python**: ccxt v4.5.54 installed via `pip3 install --break-system-packages ccxt`
- **Hermes venv**: ccxt v4.5.54 installed via bootstrapped pip in `/opt/hermes/.venv/`
- **MCP server**: Can now import ccxt for paper trading operations

---

## Phase 6 — Final Validation

| Check | Result | Evidence |
|-------|--------|----------|
| Signal age < 10 min | PASS | 8.6 min |
| Primo state fresh | PASS | fresh=true, 8.4 min |
| 10/10 cron jobs | PASS | All exist with future next_run_at |
| No stuck jobs (null next_run_at) | PASS | 0 stuck |
| External guardian running | PASS | PID 5693, 3 cycles logged |
| Guardian log entries | PASS | All OK checks |
| Telegram test message | PASS | HTTP 200 sent |
| All bots dry_run=true | PASS | 4/4 configs verified |
| Drawdown state valid | PASS | DD=0.0%, PnL=+$26.54, 5/5 bots |
| ccxt available (system) | PASS | v4.5.54 |
| ccxt available (hermes venv) | PASS | v4.5.54 |
| All scripts in profile dir | PASS | 9/9 present, 0 missing |
| No live trading changes | PASS | Zero config modifications to bots |

---

## Before/After Summary

| Component | Before | After | Evidence | Remaining Action |
|-----------|--------|-------|----------|------------------|
| Signal age | 339 min (STALE) | 8.6 min (FRESH) | hermes_signal.json mtime | Monitor via guardian |
| Cron jobs running | 1/10 | 10/10 (fresh next_run_at) | jobs.json | Wait for first auto-fire |
| Missing scripts | 3 missing | 0 missing | ls profile scripts dir | None |
| External guardian | None | PID 5693, 5-min loop | guardian log, ps aux | None |
| Telegram alerts | HTTP 401 | HTTP 200 | Test message sent | None |
| ccxt | NOT INSTALLED | v4.5.54 (both envs) | import test | None |
| Confidence gate | Verified in code | Verified in code + live test | Pipeline log RG-2 | None |
| Stale blocking | Verified in code | Verified in code + live test | Pipeline log PIPELINE_BLOCKED | None |
| Drawdown guard | Worked manually | Now automated via cron | State file written | None |
| dry_run enforcement | All true | All true | Config files verified | None |

---

## Answer

**Live-ready: NO** — Same blockers remain from a trading-strategy perspective (Momentum -$17.42, FreqAI-Rebel 30% WR, RiskGuard/ShadowLogger not standalone). However, the **automation and safety infrastructure is now fully operational**.

**Hermes cron is NO LONGER a single point of failure.** The external guardian process (PID 5693) independently monitors signal freshness and will auto-trigger the heartbeat + pipeline if the Hermes scheduler fails again.

**Remaining architectural concern:** The guardian process itself is tied to the Hermes container lifecycle. If the container restarts, the guardian must be manually restarted (or the Hermes cron scheduler will be the sole fallback until it is). A future improvement should deploy the guardian as a Docker container or systemd timer on the host.

---

## Recovery Commands (for future incidents)

```bash
# Manual signal restore
bash /home/hermes/projects/trading/orchestrator/scripts/ai_hedge_signal_heartbeat.sh
python3 /home/hermes/projects/trading/orchestrator/scripts/trading_pipeline.py

# Restart guardian
bash /home/hermes/projects/trading/orchestrator/scripts/guardian_loop.sh &
# Or via Hermes: terminal(background=true) → bash .../guardian_loop.sh

# Check guardian status
ps aux | grep guardian_loop
tail -10 /home/hermes/projects/trading/orchestrator/logs/external_cron_guardian.log

# Full cron reset (delete all + recreate from backup)
# Use Hermes cronjob tool: action=remove for each stuck job, then action=create
```
