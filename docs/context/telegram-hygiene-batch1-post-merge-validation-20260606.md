# Post-Merge Validation — Telegram/Cron Hygiene Batch 1

**Date:** 2026-06-06
**Merge Commit:** `477e3b1` (PR #6 → main)
**Validator:** claudio (read-only)

---

## 1. Git

| Check | Result |
|-------|--------|
| `main` HEAD | `477e3b1` — Merge pull request #6 |
| PR #6 Commits | `1515176` fix + `aa853a5` cleanup |
| Local main | Reset to `origin/main` (was 13 commits behind) |
| PR #5 | Closed (superseded by PR #6) |

## 2. Runtime vs Git Consistency

| File | Git Checksum | Runtime Checksum | Match? |
|------|-------------|------------------|--------|
| `container_watchdog.sh` | `5695e41` (v4, 4601B) | `0f9c7f0` (v3, 4229B) | **NO** |

**Analysis:** Runtime scripts in `/opt/data/profiles/orchestrator/scripts/` are **not auto-deployed** from git. They were last updated 2026-06-01 (pre-batch-1). The cron job (`container-watchdog`) references the runtime path and runs v3 with stale container names (`freqtrade-freqforge`, `freqai-rebel`, etc.). **A manual sync is needed.**

## 3. Container Status

```
trading-freqtrade-freqforge-1       Up 4h (healthy)
trading-freqtrade-freqforge-canary-1 Up 4h (healthy)
trading-freqtrade-regime-hybrid-1   Up 4h (healthy)
trading-freqai-rebel-1              Up 4h (healthy)
trading-freqtrade-webserver-1       Up 4h (healthy)
```

All 5 trading containers **running and healthy** with new `trading-*-1` naming convention.

## 4. Watchdog State

- Last state file: `2026-06-02T04:01:29Z` — stale (old names)
- Last log entry: `2026-05-31` — no entries since
- **V3 runtime has no DOCKER_HOST bypass** — docker exec may fail via proxy (EXEC=0)
- **Git v4 has DOCKER_HOST bypass** but is not deployed

## 5. Secrets / Scope Check

- Chat ID `610209401`: **not found** in any PR #6 file (redacted as planned)
- `self_improvement/`, `hermes-fleet-dashboard/`, `polymarket-fadi/`: **not present** in PR #6
- `trailing_stop`, `restart-freqai-rebel.sh`, `docker-compose.yml`: **not present** in PR #6
- `AGENTS.md`: only container name table updated (RiskGuard/ShadowLogger sections unchanged)

## 6. Deployments Needed

| Item | Action | Priority |
|------|--------|----------|
| container_watchdog.sh | Copy v4 → `/opt/data/profiles/orchestrator/scripts/` | HIGH |
| freqtrade_monitor.py + 18 other scripts | Sync v4 with new names + DOCKER_HOST | HIGH |
| Cron jobs (jobs.json) | Verify no stale script references | LOW |

**Not deployed in this session** as per validation scope.

## Verdict: YELLOW

- **PR #6 merge:** 🟢 GREEN
- **Runtime sync:** 🟡 YELLOW — scripts not deployed yet
- **Secrets leak:** 🟢 NONE
- **Scope creep:** 🟢 NONE

**Next step for Batch 2:** Deploy runtime scripts, then plan Batch 2 topics (polling conflict, expected_state.json names, config-diff blindspot).
