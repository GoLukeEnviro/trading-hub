# Hermes Cron Wiring Repair — 2026-05-22

## Verdict: PARTIAL_FIX

## Root Cause

Hermes cron jobs run **inside the Hermes Docker container** which has:
- **No Docker socket** mounted (`/var/run/docker.sock` does not exist)
- **No network access** to trading bot REST APIs (ports bound to `127.0.0.1` on HOST only)
- **Not on `ki-fabrik` Docker network** with trading bots

All watchdog scripts (`container_watchdog.sh`, `drawdown_guard.py`, `heartbeat_writer.py`) used `docker exec` and `docker inspect` commands that fail silently, causing:
1. All containers reported as `not_found`
2. All bots reported as `unreachable`
3. False "KRITISCH: Kein Bot erreichbar" Telegram alerts every 5-30 minutes
4. `mcp_watchdog.sh` crashed with exit code 1 due to `set -euo pipefail` + `pgrep` returning non-zero

## What Was Fixed

### Scripts Rewritten (v2/v3)

| Script | Location | Change |
|--------|----------|--------|
| `container_watchdog.sh` | `/opt/data/profiles/orchestrator/scripts/` | v2: Docker detection + file-based probe fallback |
| `drawdown_guard.py` | same | v3: Docker detection + graceful no-Docker mode |
| `mcp_watchdog.sh` | same | v2: Fixed `pgrep` pipefail crash |
| `heartbeat_writer.py` | same | v2: Direct REST API + Docker detection |
| `honcho_memory_quality_guard.sh` | same | Renamed to `.disabled` |

### Key Behavior Changes

1. **container-watchdog**: In file-based mode, uses `primo_signal_state.json` freshness per-bot as liveness probe. No false `not_found` alerts.

2. **drawdown-guard**: Detects no-Docker mode, does NOT send "KRITISCH: Kein Bot erreichbar". Reports `NO_DOCKER` informational status. Signal freshness check still works (file-based).

3. **mcp-watchdog**: No longer crashes with exit code 1. Handles `pgrep` returning non-zero gracefully.

4. **heartbeat-writer**: Tries direct REST API first, then Docker exec fallback. Marks bots as `no_access` instead of `unreachable` when Docker is unavailable.

5. **Honcho**: Script disabled, no cron job references it. HONCHO WATCHDOG output was from LLM agent sessions, not from active cron jobs.

## Scheduler Inventory

### Active Jobs (7)
| ID | Name | Schedule | Status |
|----|------|----------|--------|
| 2dd0e985b001 | trading-pipeline | */10m | OK |
| c78604b494ab | daily-backup | 0 2 * * * | OK |
| a47e1c73e102 | portfolio-rebalancer | 0 6 * * 1 | never run |
| f3309a30e20a | cron-guardian | 0 */6 * * * | OK |
| 6fb7b35f951e | Heartbeat Intelligence | 120m | OK |
| 03ab84100557 | Memory Backfill | 0 */6 * * * | OK |
| 9d88d23cb9fd | Fleet correlation refresh | 4320m | never run |

### Paused Jobs (10) — kept paused pending Docker socket fix
| ID | Name | Schedule | Reason |
|----|------|----------|--------|
| 64b6a4bc71bb | container-watchdog | */5m | Script fixed; needs Docker socket for full functionality |
| 6624bdecfa6f | drawdown-guard | */30m | Script fixed; needs Docker socket for balance queries |
| aac52bfa2ce2 | mcp-watchdog | */5m | Script fixed; can be re-enabled (no Docker needed) |
| 4791509c9f12 | signal-heartbeat | */20m | Error state; needs investigation |
| d0af1cc31311 | smart-heartbeat | */10m | Error: age check failing |
| 275ece2d7592 | FleetRisk equity updater | 5m | Needs Docker |
| e9ce544673b1 | Fleet Report | 240m | Agent job; needs Docker for fleet status |
| c3d95433a636 | System Health Check | 120m | Agent job; was HONCHO WATCHDOG source |
| 31bbdb7708bd | 72h Research Fleet Monitor | 60m | Agent job; 26/72 done |
| 5ed59e6cf398 | Rebel Status Summary | 720m | Agent job |

## Files Changed

- `/opt/data/profiles/orchestrator/scripts/container_watchdog.sh` (rewritten v2)
- `/opt/data/profiles/orchestrator/scripts/drawdown_guard.py` (rewritten v3)
- `/opt/data/profiles/orchestrator/scripts/mcp_watchdog.sh` (rewritten v2)
- `/opt/data/profiles/orchestrator/scripts/heartbeat_writer.py` (rewritten v2)
- `/opt/data/profiles/orchestrator/scripts/honcho_memory_quality_guard.sh` → `.disabled`
- Synced copies to `/home/hermes/projects/trading/orchestrator/scripts/`

## Backups

All originals backed up to:
`/home/hermes/projects/trading/orchestrator/backups/20260522T065309Z-cron-wiring-repair/`

## Validation Results

| Test | Result |
|------|--------|
| container_watchdog.sh | 5/6 bots alive (file-based), 1 stale (ai-hedge-fund 132min) |
| drawdown_guard.py | Signal FRESH (4.9min), no false KRITISCH |
| mcp_watchdog.sh | Exit 0, reports MCP server down clearly |
| Signal pipeline | Running, signal file 4.9 min old |
| Honcho references | None in active scripts |
| Trading bots | NOT restarted, NOT affected |

## Telegram Output Expectation

- **Before**: False "not_found" every 5 min, "KRITISCH: Kein Bot erreichbar" every 30 min, MCP crash every 5 min, HONCHO WATCHDOG every 2h
- **After (jobs paused)**: Silence — no false alerts
- **After (jobs re-enabled with Docker socket)**: Accurate per-container status with file-based fallback

## Remaining Risks

1. **Docker socket not mounted**: The fundamental fix requires mounting `/var/run/docker.sock` into the Hermes container or adding Hermes to the `ki-fabrik` network. Without this, balance queries and authoritative container checks are impossible.

2. **Agent-based jobs**: System Health Check and Fleet Report prompts don't explicitly mention Honcho, but the LLM may still check it. Prompts should be updated to note "Honcho is decommissioned, use local Mem0/Qdrant" when these are re-enabled.

3. **MCP server not running**: `bitget_mcp_server.py` is down and restart fails. This may affect trading pipeline MCP features.

## Next Action

1. **Mount Docker socket** into Hermes container (HOST-side infrastructure change):
   ```yaml
   volumes:
     - /var/run/docker.sock:/var/run/docker.sock
   ```
2. After Docker socket mount, re-enable: container-watchdog, drawdown-guard, FleetRisk equity updater
3. mcp-watchdog can be re-enabled immediately (no Docker dependency)
4. Update agent job prompts to exclude Honcho references
