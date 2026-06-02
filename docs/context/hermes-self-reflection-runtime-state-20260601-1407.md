# Hermes Self-Reflection: Runtime State Audit

**Generated:** 2026-06-01 14:07:55 UTC
**Mode:** READ-ONLY SELF-REFLECTION
**Model:** glm-5-turbo / zai
**Scope:** Full trading hub stack

---

## Executive Verdict

**WARNING** — The system is operational but has 6 known script drift issues, 5 stale error statuses on jobs that now work correctly, no docker-socket-proxy container, and 6 CRON_ONLY scripts not tracked in git. The core pipeline (signal -> fleet -> drawdown) is verified working. No live-money risk exists. The system is NOT BROKEN but also NOT STABLE — it is held together by the trading-guardian container compensating for structural permission drift and script version inconsistencies.

---

## What Works [VERIFIED]

| Component | Evidence | Classification |
|-----------|----------|----------------|
| hermes-green container | Up 3 hours, gateway running, Telegram connected | VERIFIED |
| ai-hedge-fund-crypto | Up 12h, healthy, signal age 1-10 min | VERIFIED |
| green-mem0 | Up 7h, healthy, Qdrant backend, extraction_policy=v1 | VERIFIED |
| green-qdrant | Up 3 days, 3 collections (hermes_memories, v2, mem0migrations) | VERIFIED |
| green-ollama | Up 3 days, 5 models loaded (incl. qwen3-embedding:4b, gpt-oss:120b) | VERIFIED |
| Freqtrade fleet (4 bots) | All up 9h, dry_run=True, NO API keys present | VERIFIED |
| Trading safety | All 4 bots: dry_run=True, apiKey=False, secret=False | VERIFIED |
| Signal freshness | hermes_signal.json updated <2 min ago | VERIFIED |
| Drawdown guard | Runs successfully, portfolio $3499.30, DD 0%, all 4 bots reachable | VERIFIED |
| Trading pipeline | Last run OK, runs every ~2 min | VERIFIED |
| System optimizer | Last run OK, runs every ~5 min | VERIFIED |
| Telegram delivery | Hermes gateway state: connected | VERIFIED |
| Cron scheduler | 37 jobs in jobs.json, scheduler dispatching at correct intervals | VERIFIED |
| Trading guardian | Up 11h, loop running every 5 min, all checks passing | VERIFIED |
| RiskGuard service | Last run OK at 13:32 | VERIFIED |
| Ghostbuster | Last run OK | VERIFIED |
| Container watchdog | Last run OK | VERIFIED |
| Fleet health | All 4 bots inspected, API ports responding | VERIFIED |
| Gateway processes | gateway run + dashboard + 2x MCP servers running | VERIFIED |

---

## What Does Not Work [BROKEN / WARNING]

### No docker-socket-proxy Container [WARNING]

The docker-socket-proxy container (tecnativa/docker-socket-proxy) does NOT exist. The trading-guardian container mounts `/var/run/docker.sock:ro` directly. This works because the guardian is the only container with socket access, but it violates the read-only proxy pattern recommended in the cron-ops skill. The docker socket is exposed to a container — albeit with `PERMISSION_GUARD_MODE=repair`.

Impact: Minor — guardian works without proxy. Risk: guardian could theoretically start/stop containers if its code changed.

### 5 Jobs with Stale ERROR Status [WARNING]

These 5 jobs show `last_status=error` in jobs.json but ALL run successfully when executed directly:

| Job | ID | Script | Exit Code | Root Cause |
|-----|-----|--------|-----------|------------|
| portfolio-rebalancer | a47e1c73 | portfolio_rebalancer.py | 0 (OK now) | Stale error from previous run |
| drawdown-guard | 7fcd1727 | drawdown_guard.py | 0 (OK now) | Stale error from previous run |
| signal-heartbeat | 76740f3b | ai_hedge_signal_heartbeat.sh | 0 (OK now) | Stale error from previous run |
| smart-heartbeat | 05ed4ddb | smart_heartbeat.py | 0 (OK now) | Stale error from previous run |
| daily-backup | 2e1e39f1 | backup_rotation.py | 0 (OK now) | Stale error from previous run |

These will self-heal on next scheduled tick but represent a misleading state snapshot. The Hermes cron scheduler does NOT auto-clear error status — it persists until the next successful execution. Since some of these run on long intervals (6h, 24h), the error status persists for hours.

### Hermes Cannot Reach ai-hedge-fund-crypto HTTP [WARNING]

From inside hermes-green, `curl` and `wget` cannot reach `http://ai-hedge-fund-crypto:8410/health`. The container IS on the ki-fabrik network alongside hermes-green, but the hermes-green container's python/node HTTP clients cannot resolve or reach it. However, Docker health checks pass. The drawdown_guard.py accesses ai-hedge-fund-crypto indirectly via the signal JSON file, not the HTTP API, so this does not break the pipeline.

Root cause: Likely DNS resolution or HTTP client issue within the hermes container's sandbox environment. The signal bridge reads the file directly (`/guardian/data/ai-hedge-fund-crypto/output/hermes_signal.json`), bypassing HTTP.

### No Blue Stack Containers Exist [VERIFIED STOPPED]

No containers with "blue" in the name exist at all — not stopped, not exited. They were fully removed. The "Blue Stack" concern is resolved: there is nothing to accidentally restart. This is VERIFIED SAFE.

---

## What Is Only Partially Working [PARTIAL]

### Script Version Drift: 8 Scripts Differ [PARTIAL]

Between the project tree (`/home/hermes/projects/trading/orchestrator/scripts/`) and the active cron scripts dir (`/opt/data/profiles/orchestrator/scripts/`):

| Script | Diff Size | Nature of Difference |
|--------|-----------|---------------------|
| external_cron_guardian.sh | 19 lines | Project has permission repair DISABLED; cron dir version has it ENABLED |
| memory_backfill.py | 208 lines | Major version drift — cron dir has significantly newer version |
| heartbeat_writer.py | 45 lines | Unknown — not inspected in detail |
| system_optimizer.py | 13 lines | Cron dir has updated container names (hermes-agent -> hermes-green, etc.) |
| ghostbuster.py | 19 lines | Unknown drift |
| fleet_auto_repair.py | 13 lines | Unknown drift |
| mem0_watchdog.py | 8 lines | Unknown drift |
| daily_heartbeat.py | 4 lines | Minor |
| smart_heartbeat.py | 4 lines | Minor |
| fleet_correlation_refresh.sh | 17 lines | Unknown drift |

**Critical finding:** The `external_cron_guardian.sh` in the cron dir STILL has the permission repair loop that the project tree version disabled. The trading-guardian container has its OWN baked-in copy. So there are THREE versions of this script:
1. Project tree: permission repair DISABLED
2. Cron scripts dir (`/opt/data/profiles/orchestrator/scripts/`): permission repair ENABLED
3. Trading-guardian baked-in: permission repair ENABLED (mode=repair)

The cron-dir version is what Hermes cron jobs run. The trading-guardian has its own independent copy. Both have repair enabled. The project tree is out of date.

### 6 CRON_ONLY Scripts [PARTIAL]

These scripts exist only in `/opt/data/profiles/orchestrator/scripts/` and NOT in the project tree:
- `riskguard_service.py`
- `morning_brief.py`
- `config_diff_detector.py`
- `fleet_risk_auto_params.py`
- `critical_event_watchdog.py`
- `log_rotation.py`

These are not tracked in git. If the orchestrator profile is wiped, these scripts are lost.

### Mem0 LLM Extraction [PARTIAL]

green-mem0 reports `extraction_policy=v1` and `llm_model=gpt-oss:120b` via Ollama. This was the fix from the earlier session (OLLAMA_API_KEY pass-through). The endpoint `/health` responds correctly from hermes-green. However, the Qdrant port (6336) is NOT accessible from the host (only from hermes-green via internal network). This is by design — Qdrant only needs to be reachable from green-mem0 and hermes-green, which it is.

---

## Wrong / Outdated Assumptions

### 1. "Dual-Copy / Dual-Path" Issue Was Misleading

**Previous assumption:** There are two profile paths: `/opt/data/profiles/orchestrator/` and `/opt/hermes-green/config/profiles/orchestrator/`, creating a dual-copy problem.

**Reality:** `/opt/hermes-green/config/profiles/orchestrator/` DOES NOT EXIST. The bind mount is:
```
/opt/hermes-green/config -> /opt/data (rw)
```

This means inside hermes-green: `/opt/data` IS `/opt/hermes-green/config`. There is only ONE physical path on the host: `/opt/hermes-green/config/profiles/orchestrator/`, which is what we see as `/opt/data/profiles/orchestrator/` from inside the container. The "dual-copy" concern was based on a non-existent second path. There is no dual-copy — there is only one profile directory.

**Correction:** The memory note about "dual-copy issue" is partially wrong. The correct concern is script drift between the project tree and the cron scripts dir, NOT between two profile locations.

### 2. "systemd Guardian" Does Not Exist

**Previous assumption:** A systemd Guardian service manages the system.

**Reality:** No systemd services or timers exist for hermes, guardian, trading, mem0, qdrant, ollama, or freqtrade. The external watchdog is a Docker container (`trading-guardian`) running a 5-minute bash loop, not a systemd service.

**Correction:** All references to "systemd Guardian" should be replaced with "trading-guardian Docker container."

### 3. Blue Stack "Stop-Only" Test

**Previous assumption:** Blue stack was stopped and might need to be kept stopped.

**Reality:** Blue stack containers were fully REMOVED — they don't exist at all. There is no "stop-only" state to maintain. This concern is stale.

### 4. Hermes config.yaml Has `cron_mode: deny`

The config shows `cron_mode: deny` in config.yaml, yet 37 cron jobs are running and dispatching correctly. This setting appears to be overridden or ignored by the gateway's internal scheduler. This is a discrepancy — either the setting is vestigial, or it controls something other than the Hermes scheduler.

---

## Canonical Runtime Truth

### Physical Paths on Host
| Purpose | Host Path |
|---------|-----------|
| Hermes profile (ACTIVE) | `/opt/hermes-green/config/profiles/orchestrator/` |
| Cron scripts (ACTIVE) | `/opt/hermes-green/config/profiles/orchestrator/scripts/` |
| Jobs.json (ACTIVE) | `/opt/hermes-green/config/profiles/orchestrator/cron/jobs.json` |
| Project tree (SOURCE) | `/home/hermes/projects/trading/` |
| Project scripts (SOURCE) | `/home/hermes/projects/trading/orchestrator/scripts/` |

### Inside hermes-green Container
| Host Path | Container Path |
|-----------|----------------|
| `/opt/hermes-green/config` | `/opt/data` |

So `/opt/data/profiles/orchestrator/scripts/` inside the container IS `/opt/hermes-green/config/profiles/orchestrator/scripts/` on the host. ONE location, two names.

### Scheduler Truth

The Hermes gateway (PID 30 inside hermes-green) runs the internal scheduler that dispatches all 37 jobs from jobs.json. This is the PRIMARY scheduler.

The `trading-guardian` container runs an INDEPENDENT 5-minute loop (`external_cron_guardian.sh`) that:
- Validates jobs.json integrity (restore from backup if corrupted)
- Checks signal freshness
- Verifies script existence
- Repairs permission drift
- Does NOT dispatch jobs (read-only watchdog)

The Hermes internal scheduler is the job dispatcher. The trading-guardian is the integrity watchdog. They are independent but complementary.

### Job Classification

| Type | Count | Description |
|------|-------|-------------|
| SCRIPT (no_agent=true) | 30 | Script-backed, no LLM, direct execution |
| AGENT-DELIVER | 1 | LLM agent job delivering to Telegram (Fleet Report) |
| AGENT-LOCAL | 6 | LLM agent jobs delivering to local only |

### Network Segmentation

| Network | Containers |
|---------|------------|
| ki-fabrik | hermes-green, ai-hedge-fund-crypto, freqtrade-freqforge, freqtrade-canary, freqtrade-regime-hybrid, claude-worker |
| hermes-green_green-net | hermes-green, green-mem0, green-qdrant, green-ollama |
| trading_hermes-net | trading-guardian |
| default | freqai-rebel, caddy, rizzcoach, a0-v2 |

**Note:** freqai-rebel is NOT on ki-fabrik — it's on the default network. This may affect signal delivery.

---

## Top 5 Blockers

### Blocker 1: 8 Script Drift Between Project Tree and Cron Scripts Dir
- **Evidence:** diff output showing 8 scripts with non-zero diff, 6 CRON_ONLY scripts
- **Impact:** Scripts running in production are not tracked in git. Project edits may not propagate to the active cron version.
- **Root cause:** Scripts were edited in `/opt/data/profiles/orchestrator/scripts/` directly without syncing back to the project tree.
- **Smallest safe next action:** `cp /opt/data/profiles/orchestrator/scripts/<script> /home/hermes/projects/trading/orchestrator/scripts/<script>` for each drifting script, then `git diff` to verify. Reverse sync: cron dir -> project tree.

### Blocker 2: 5 Stale ERROR Statuses
- **Evidence:** 5 jobs show error in jobs.json but exit 0 when run directly
- **Impact:** Misleading system state. Health reports may flag false issues.
- **Root cause:** Hermes scheduler persists error status until next successful tick.
- **Smallest safe next action:** Wait for next scheduled tick (self-heals). For faster resolution: remove+recreate each job (per skill documentation).

### Blocker 3: No docker-socket-proxy
- **Evidence:** `docker ps | grep proxy` returns nothing
- **Impact:** trading-guardian has direct docker socket access (ro mount). Structural security concern.
- **Root cause:** Was never deployed, or was removed during a cleanup.
- **Smallest safe next action:** Deploy tecnativa/docker-socket-proxy per the cron-ops skill pattern. This is LOW priority since the guardian is the only container with socket access.

### Blocker 4: freqai-rebel Not on ki-fabrik Network
- **Evidence:** `docker inspect freqai-rebel` shows default network, not ki-fabrik
- **Impact:** Cannot reach ai-hedge-fund-crypto or other fleet containers by container name.
- **Root cause:** Likely launched with a different docker-compose or network configuration.
- **Smallest safe next action:** `docker network connect ki-fabrik freqai-rebel` (needs user approval — config change).

### Blocker 5: `cron_mode: deny` in config.yaml
- **Evidence:** Config shows `cron_mode: deny` yet 37 jobs dispatch correctly
- **Impact:** Confusion, potential future breakage if the setting is enforced.
- **Root cause:** Unknown — possibly vestigial or overridden by gateway internal logic.
- **Smallest safe next action:** Investigate what `cron_mode: deny` actually controls (needs user approval to change config).

---

## Smallest Safe Next Actions (Priority Order)

1. **Sync all 8 drifting scripts from cron dir -> project tree** (no restarts needed)
2. **Copy 6 CRON_ONLY scripts to project tree** (no restarts needed)
3. **Remove+recreate 5 stale-error jobs** (clears misleading status)
4. **Connect freqai-rebel to ki-fabrik network** (requires: `docker network connect ki-fabrik freqai-rebel`)
5. **Deploy docker-socket-proxy** (requires: docker run + network connect, low priority)
6. **Investigate `cron_mode: deny`** (requires: config.yaml read + Hermes docs, no change yet)

---

## Do-Not-Touch List

- Hermes config.yaml (user approval required for ANY change)
- Freqtrade configs (user approval required for ANY change)
- Container restart/stop commands
- Exchange credentials (none exist — keep it that way)
- dry_run settings (all True — do not change)
- jobs.json manual edits (use cronjob tool only)
- Trading strategies
- Git force-push / reset
- Any file in `/home/hermes/projects/trading/freqtrade/`

---

## Final Honest Self-Assessment

The system is in a **WARNING** state — functional but fragile. The core trading pipeline works: signal is fresh, fleet is healthy, drawdown guard passes, all bots are dry-run with no keys. The trading-guardian container compensates for structural permission drift issues. The dual-copy concern from previous sessions was based on a misunderstanding — there is only one profile directory, accessed via two mount-point names.

The biggest structural risk is script drift: 8 scripts differ between the git-tracked project tree and the active cron scripts directory. This means the "source of truth" is ambiguous — git has one version, production runs another. The 6 CRON_ONLY scripts are not tracked in git at all.

The stale error statuses are cosmetic but undermine trust in monitoring. The missing docker-socket-proxy is a defense-in-depth gap. freqai-rebel being on the wrong network may cause silent signal delivery failures.

Previous mistakes:
1. The "dual-copy profile path" narrative was wrong — there is only one path with two mount names.
2. The "systemd Guardian" does not exist — it's a Docker container.
3. The "Blue Stack stop-only" concern is stale — Blue containers don't exist.
4. Script edits were applied to the cron dir without syncing back to git.

The single most important fix before calling the system stable is: **establish a single source of truth for scripts** by syncing all cron-dir scripts back to the project tree and committing to git, then enforcing the sync pattern documented in the cron-ops skill.
