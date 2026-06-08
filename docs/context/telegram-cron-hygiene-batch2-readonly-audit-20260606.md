# Telegram/Cron Hygiene — Batch 2 Read-only Audit

**Date:** 2026-06-06
**Auditor:** Claude Code (hermes user, read-only)
**Predecessor:** Batch 1 merged as 477e3b1, deployed, GREEN

---

## 1. Executive Verdict

**YELLOW** — All remaining issues are understood and a safe patch plan exists, but the **Telegram Polling Conflict** (P1) requires a design decision: assign unique bot tokens to each Hermes profile, or disable redundant s6-gateway services.

No secrets were exposed. No trading configs were touched. No containers were restarted.

---

## 2. Batch 1 Post-State Confirmation

| Check | Status |
|-------|--------|
| HEAD = 477e3b1 | OK |
| All 5 trading containers healthy | OK |
| hermes-fleet-dashboard unhealthy | PRE-EXISTING (missing host mount) |
| watchdog silent (no Telegram spam) | OK |
| Telegram stale-container-name spam stopped | OK |

---

## 3. Telegram Polling Conflict Findings

### Root Cause
Three Hermes profiles share the **same** Telegram bot token (`864294...`):
- `default`
- `mira`
- `trading`

The `orchestrator` profile has a **separate** token (`864897...`) and is unaffected.

### Architecture
- **hermes-green** container runs s6-supervised gateway services for 6 profiles
- Only **PID 160** (`gateway-default`) is stably running
- The other 5 s6-supervised gateways (`mira`, `trading`, `orchestrator`, `weather`, `weatherbot`) have **no active child processes** — their s6 supervisors are running but children crashed/stopped
- However, the s6 supervisors for `trading` and `mira` appear to be in a **restart loop**, briefly creating a `getUpdates` request on each attempt before crashing

### Impact
- **499 polling conflicts today** (2026-06-06)
- Conflicts logged as: `Conflict: terminated by other getUpdates request`
- Pattern: ~20-second intervals, consistent with s6 restart loop
- Gateway eventually recovers (retry 1/5 succeeds), but noise is significant

### Conflict Flow
```
PID 160 (default) → getUpdates on token 864294... (stable)
s6 restarts trading gateway → getUpdates on SAME token 864294... (conflict!)
s6 restarts mira gateway → getUpdates on SAME token 864294... (conflict!)
→ Both crash, s6 restarts, cycle repeats
```

---

## 4. Direct Telegram Sender Inventory

| Script | Method | Token | Frequency | Purpose |
|--------|--------|-------|-----------|---------|
| `drawdown_guard.py` | api.telegram.org/sendMessage | TradingOrchestrator bot | Every 30m (cron) | Drawdown alerts |
| `heartbeat_intelligence_wrapper.py` | api.telegram.org/sendMessage | TradingOrchestrator bot | Every 6h (cron) | Heartbeat report |
| `permission_autopilot_alert.py` | api.telegram.org/sendMessage | TradingOrchestrator bot | Every 15m (cron) | Permission drift alerts |
| `telegram_alerts.py` (fleet-dashboard container) | api.telegram.org/sendMessage | WeatherHermes bot (diff token) | 15s poll loop | Weather trade signals |

**Assessment:** All 4 are **send-only**. None call `getUpdates`. None contribute to the polling conflict. The WeatherHermes sidecar uses a different bot token entirely.

---

## 5. expected_state.json Findings

**Result: No expected_state.json file exists.** The pre-Batch-1 concern about stale container names in expected_state.json was either:
- Already resolved in a prior cleanup, or
- Was a hypothetical concern, not an actual file

The `container_watchdog_state.json` uses **current, correct** container names (updated in Batch 1 v4 fix). However, this state file was last updated **2026-06-02T04:01:29Z** (4 days ago), suggesting the Hermes-cron watchdog may not be executing reliably.

---

## 6. config-diff Blindspot Findings

### Current State
The `config_diff_detector.py` runs hourly and compares host-side config files against... themselves (HOST-ONLY mode):

```
trading-freqtrade-freqforge-1: HOST-ONLY (docker exec blocked, bind-mount assumed in sync)
trading-freqtrade-freqforge-canary-1: HOST-ONLY (docker exec blocked, bind-mount assumed in sync)
trading-freqtrade-regime-hybrid-1: HOST-ONLY (docker exec blocked, bind-mount assumed in sync)
trading-freqai-rebel-1: SKIP (no host path, docker exec blocked)
```

### Assessment
- **freqai-rebel** is **completely unmonitored** — no host path, no docker exec, SKIP every run
- The other 3 bots are checked against their host-side bind-mount, which is the actual source of truth (docker-compose mounts host config into container)
- If someone edits config inside a running container, HOST-ONLY mode would miss it
- **Practical risk: LOW** — configs are bind-mounted, so container-internal edits would be lost on restart anyway
- **freqai-rebel blindspot: MEDIUM** — should at minimum have host-path monitoring

### Safe Options
1. **Accept HOST-ONLY** (lowest risk, bind-mounts ARE the source of truth)
2. **Add freqai-rebel host-path** for partial monitoring
3. **Allow controlled docker exec** via Docker proxy whitelist (higher risk, requires EXEC=1 for specific commands only)

---

## 7. SSH known_hosts Warning Findings

### Root Cause
The warning `Failed to add the host to the list of known hosts /opt/data/profiles/orchestrator/home/.ssh/known_hosts` occurs because:

1. **Container HOME mismatch**: Docker exec sets `HOME=/root`, but Hermes gateway runs as UID 10000 with `HOME=/opt/data`
2. The known_hosts file exists at `/opt/data/profiles/orchestrator/home/.ssh/known_hosts` (not at `/opt/data/.ssh/known_hosts`)
3. When git/SSH runs inside the container, it looks for `$HOME/.ssh/known_hosts` and either finds nothing or the wrong path

### Current State
- File permissions: `644 hermes:hermes` — readable by all, writable by owner
- Content: Only `github.com` key (already present)
- The warning is cosmetic — git operations still succeed (key already known)

### Impact
**COSMETIC** — no functional breakage. The warning appears in gateway logs but does not affect operations.

---

## 8. Scheduler/LLM Overhead Findings

### Total: 56 Hermes Cron Jobs

#### LLM-Heavy Jobs (6 jobs using external models)

| Job | Frequency | Model | Output | Classification |
|-----|-----------|-------|--------|----------------|
| Fleet Report | every 4h | deepseek-v4-flash | telegram | **KEEP** |
| System Health Check | every 8h | deepseek-v4-flash | local | **KEEP** |
| autonomous-health-loop | every 60m | glm-5.1 | local | **RATE_LIMIT** → 240m |
| Rebel Status Summary | every 12h | glm-5.1 | local | **KEEP** |
| daily-signal-confidence-monitor | every 6h | glm-5.1 | local | **KEEP** |
| trading-hub-deep-dive-validation | daily 9am | glm-5.1 | local | **KEEP** |

**LLM Cost Estimate (autonomous-health-loop):** 24 runs/day × glm-5.1 = significant API overhead for a health loop that overlaps with `System Health Check` and `Fleet Health Quickcheck`.

#### Overlapping Health/Watchdog Jobs

| Redundancy Group | Jobs | Frequency | Recommendation |
|------------------|------|-----------|----------------|
| **Health Checks** | autonomous-health-loop (60m), System Health Check (8h), Fleet Health Quickcheck (120m) | 3 health checkers | Reduce to 2 |
| **Container Monitoring** | container-watchdog (30m), critical-event-watchdog (10m) | 2 watchdogs | Keep both but increase critical-event to 15m |
| **Heartbeat** | heartbeat-intelligence-wrapper (6h), daily-heartbeat (daily 6am), heartbeat-writer (15m) | 3 heartbeat sources | Consolidate to 2 |
| **Observation** | observation-runner (5m), observation-watchdog (10m) | observation pair | Keep, but runner at 10m not 5m |

#### Very High Frequency Jobs (candidates for rate-limiting)

| Job | Frequency | Classification |
|-----|-----------|----------------|
| system-optimizer | every 5m | **PAUSE_CANDIDATE** — unclear value |
| observation-runner | every 5m | **RATE_LIMIT** → 10m |
| FleetRisk equity updater | every 5m | **KEEP** (trading-critical) |
| hermes-standby-monitor | every 5m | Already disabled |

#### Telegram Noise Producers (9 jobs sending to Telegram)

| Job | Frequency | Volume/day | Classification |
|-----|-----------|------------|----------------|
| Fleet Report | every 4h | 6 | **KEEP** |
| canary-position-monitor | every 30m | 48 | **RATE_LIMIT** → 60m |
| drawdown-guard | every 30m | 48 | **KEEP** (safety) |
| container-watchdog | every 30m | 48 | **KEEP** (silent=OK) |
| critical-event-watchdog | every 10m | 144 | **KEEP** (safety) |
| observation-watchdog | every 10m | 144 | **RATE_LIMIT** → 30m |
| daily-heartbeat | daily | 1 | **KEEP** |
| morning-brief-daily | daily | 1 | **KEEP** |
| fleet-auto-repair | every 2h | 12 | **KEEP** |

---

## 9. Recommended Batch 2 Scope

### Batch 2A: Telegram Polling Conflict (P1)
**Fix the s6 gateway restart loop causing 500+ daily polling conflicts.**

### Batch 2B: container_watchdog_state.json Staleness (P2)
**Investigate why the watchdog state file hasn't updated since June 2.**

### Batch 2C: config-diff freqai-rebel Blindspot (P2)
**Add host-path monitoring for freqai-rebel in config_diff_detector.py.**

### Batch 2D: autonomous-health-loop Frequency (P3)
**Reduce from 60m to 240m to cut LLM overhead by 75%.**

### Batch 2E: Cron Consolidation (P3)
**Consolidate overlapping health/heartbeat jobs.**

---

## 10. Explicitly Excluded From Batch 2

- Trading config changes (dry_run, pairs, stakes)
- Container restarts or deployments
- SSH known_hosts fix (cosmetic, no functional impact)
- system-optimizer pause (needs value assessment first)
- hermes-fleet-dashboard unhealthy (missing host mount, separate issue)
- WeatherHermes telegram_alerts.py (separate bot token, no conflict)

---

## 11. Patch Plan — NOT EXECUTED

### Patch 2A: Telegram Polling Conflict (P1)

**Option A: Disable redundant s6 gateway services (RECOMMENDED)**
- Stop s6 services: `gateway-trading`, `gateway-mira`, `gateway-weather`
- Keep only: `gateway-default` (main bot), `gateway-orchestrator` (separate token), `gateway-weatherbot` (if needed)
- Rollback: Re-enable s6 services
- Validation: `docker logs hermes-green --since 1h | grep "polling conflict" | wc -l` should be 0

**Option B: Assign unique bot tokens**
- Create separate Telegram bots for `trading`, `mira` profiles
- Update `.env` files with unique tokens
- Higher effort, more Telegram bots to manage

**Recommended: Option A** — simpler, immediate fix, no new bots needed.

### Patch 2B: Watchdog State Staleness (P2)
- Check if `container-watchdog` Hermes-cron job is actually executing
- If not, investigate cron executor error in gateway logs
- Rollback: N/A (investigation only)

### Patch 2C: freqai-rebel Config Monitoring (P2)
- Add freqai-rebel host config path to `config_diff_detector.py` BOT_CONFIGS
- Path: `/home/hermes/projects/trading/freqtrade/bots/freqai-rebel/user_data/config.json` (verify exists)
- If no host path exists (custom image), document as known blindspot
- Rollback: Remove added path
- Validation: config_diff_health.json shows freqai-rebel status instead of SKIP

### Patch 2D: autonomous-health-loop Rate Limit (P3)
- Change interval from 60m to 240m in jobs.json
- Reduces glm-5.1 API calls from 24/day to 6/day
- Overlap coverage: System Health Check (8h) + Fleet Health Quickcheck (2h) remain
- Rollback: Revert to 60m
- Validation: Check gateway logs for reduced LLM invocations

### Patch 2E: Cron Consolidation (P3)
- Consolidate `observation-runner` from 5m to 10m
- Consolidate `observation-watchdog` from 10m to 30m
- Add `si-bot-c-backtest-0307` to enabled=false→true verification
- Rollback: Revert job schedules
- Validation: Reduced cron execution count in gateway logs

---

## 12. Rollback Plan

All patches are additive or configuration-only:
1. **2A**: `s6-svc -u /run/service/gateway-trading` to re-enable
2. **2B**: Investigation only, no rollback needed
3. **2C**: Revert config_diff_detector.py via git
4. **2D**: Revert jobs.json interval via git
5. **2E**: Revert jobs.json schedules via git

General rollback: `git revert` on Batch 2 PR, redeploy runtime scripts.

---

## 13. Final Verdict: YELLOW

- **Telegram Polling Conflict** (P1) is the only active issue causing operational noise
- All other issues are low-impact or cosmetic
- Safe patch plan exists for each issue
- No secrets exposed, no trading configs at risk
- **Recommendation:** Execute Batch 2A first (P1), then 2B-2E in separate PRs
