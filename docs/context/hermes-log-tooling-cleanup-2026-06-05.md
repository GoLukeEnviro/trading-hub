# Hermes Log/Tooling Failure Cleanup — 2026-06-05

**Author:** Hermes Orchestrator (glm-5.1 via Z.AI)
**Date:** 2026-06-05T09:19Z
**Scope:** Agent/tooling/logging hygiene only. No trading behavior changed.

---

## Executive Verdict

**PARTIAL CLEANUP COMPLETE.** The primary reporting hygiene issue (fleet_healthcheck reporting RED due to decommissioned bots) is fixed. Multiple systemic agent-level failure patterns are documented but require separate sessions for full remediation (permission fixes, MCP stderr noise, Mem0 timeout pattern).

---

## What Was Actually Wrong

### 1. fleet_healthcheck.py — Decommissioned Bots Poisoning Verdict (FIXED)

- **Problem:** BOT_CONFIGS listed `rsi` and `momentum` (decommissioned weeks ago). Both always showed `container_running=False` → verdict RED. This dragged the entire fleet verdict to RED every cycle.
- **Impact:** Every health check, cron job, and agent session that read `fleet_health_latest.json` saw RED and triggered unnecessary escalation.
- **Fix:** Replaced BOT_CONFIGS with the 4 active bots (freqforge, regime-hybrid, freqforge-canary, freqai-rebel). Updated strategy names (v6→v7). Added None-safe handling for bots without host-side mounts.
- **Result:** Fleet verdict changed from **RED → YELLOW** (freqai-rebel has no host-mount, which is a monitoring gap, not a trading failure).

### 2. fleet_healthcheck.py — Strategy Mismatch Treated as RED (FIXED)

- **Problem:** `determine_bot_verdict()` returned RED for strategy mismatches, which is overly aggressive for a non-critical config drift issue.
- **Fix:** Reclassified strategy mismatch from RED → YELLOW. Only `dry_run=false` and credential presence remain RED.

### 3. Permission Denied Errors — Systemic (3,786 occurrences in errors.log)

- **Source:** `/opt/data/profiles/orchestrator/cron/jobs.json` (2,284), `/opt/data/profiles/orchestrator/auth.json` (1,313), `/opt/data/profiles/orchestrator/config.yaml` (49+5).
- **Root cause:** Files owned by `hermes:hermes` with mode `0600`. The agent runtime reads these on every turn. Intermittent permission failures (possibly race condition with cron jobs writing the files).
- **Impact:** Agent loses config/auth context mid-session, falls back to defaults.
- **Status:** NOT FIXED in this session. Requires ACL investigation (files are already 600 owner hermes, user is hermes — possible file-lock contention).

### 4. Security Scanner Blocks — 857 occurrences in errors.log

- **Source:** LLM-generated commands piping `curl|python3`, `docker|python3`, `echo|python3`, `cat|python3`.
- **Root cause:** The agent (especially in cron jobs) generates unsafe pipe-to-interpreter commands that get blocked by the security scanner. It then retries with similar patterns.
- **Impact:** Wasted agent turns, failed tool calls, no actual security risk (scanner blocks correctly).
- **Status:** NOT FIXED in this session. Requires prompt hardening in cron job definitions.

### 5. Mem0 Sync Failures — 262 occurrences (212 errors.log + 50 agent.log)

- **Source:** `Mem0 sync failed: timed out` in `plugins.memory.mem0`.
- **Root cause:** Mem0 REST API timeout. Possibly green-mem0 container under load or network latency.
- **Impact:** Memory state becomes stale, but trading operations are unaffected.
- **Status:** NOT FIXED. Requires Mem0 health investigation.

### 6. Tool Loop Failures — 379 occurrences in errors.log

- **Source:** `same_tool_failure_warning` — agent retries failing tool path instead of switching method.
- **Root cause:** Most common in `skill_manage` patch attempts (36x "Could not find a match for old_string").
- **Impact:** Wasted agent turns. No trading impact.
- **Status:** NOT FIXED. Requires retry budget in agent prompts.

### 7. Path Discovery Failures — 190 occurrences in errors.log

- **Source:** Agent guesses paths like `/home/hermes/projects/trading/bridge/primo_signal_state.json` (does not exist).
- **Root cause:** Hardcoded path assumptions in generated commands instead of `find`-based discovery.
- **Status:** NOT FIXED. Requires prompt hardening.

### 8. SQLite Schema Mismatches — 26 occurrences in errors.log

- **Source:** `no such column: profit_pct` in SQLite queries.
- **Root cause:** Agent assumes column names without inspecting schema first.
- **Status:** NOT FIXED. Requires schema-first query pattern in agent prompts.

### 9. Stale Lock Warnings — 312 occurrences in trigger_lock.log

- **Source:** Global trigger lock exceeds 180s threshold, gets removed.
- **Root cause:** Long-running trigger operations or lock contention.
- **Impact:** Trigger operations may run concurrently (race condition risk).
- **Status:** NOT FIXED. Lock timeout may need tuning.

### 10. Signal Bridge Write FAIL — 194 occurrences in signal_bridge.log

- **Source:** Old entries (May 24) writing to momentum/regime-hybrid/freqforge/canary paths with Permission denied.
- **Root cause:** UID mismatch on bot user_data directories.
- **Status:** Recent entries show OK. Historical issue, likely resolved by ACL work.

---

## What Was NOT a Trading Failure

All 10 items above are **agent/tooling/monitoring hygiene issues**. None affected:
- Trade entry/exit logic
- Signal generation (ai-hedge-fund-crypto)
- Bridge propagation (trading_pipeline.py)
- Dry-run execution (all bots confirmed dry_run=True)
- Risk parameters (drawdown guard, consec loss, fleet risk)

The fleet verdict RED was a **false positive** caused by monitoring stale data (decommissioned bots), not actual runtime danger.

---

## Failure Taxonomy

| # | Class | Count | Source | Trading Impact | Status |
|---|-------|-------|--------|---------------|--------|
| 1 | Permission denied (files) | 3,786 | errors.log | NO | Open |
| 2 | Security scanner block | 857 | errors.log | NO | Open |
| 3 | Tool loop / retry loop | 379 | errors.log | NO | Open |
| 4 | Path discovery failure | 190 | errors.log | NO | Open |
| 5 | Mem0 sync timeout | 262 | errors.log + agent.log | NO | Open |
| 6 | API timeout/stale call | 80 | errors.log | NO | Open |
| 7 | Patch target mismatch | 36 | errors.log | NO | Open |
| 8 | SQLite schema mismatch | 26 | errors.log | NO | Open |
| 9 | Oversized file read | 6 | errors.log | NO | Open |
| 10 | Stale trigger lock | 312 | trigger_lock.log | NO | Open |
| 11 | Signal bridge write fail | 194 | signal_bridge.log | NO | Historical |
| 12 | MCP unavailable (no ccxt) | 14 | guardian.log | NO | Open |
| 13 | No Docker (drawdown guard) | 551 | drawdown_guard.log | NO | Historical |
| 14 | Fleet health false RED | ~500 cycles | fleet_healthcheck | NO | **FIXED** |

---

## Files Changed

| File | Change | Trading Impact |
|------|--------|---------------|
| `orchestrator/scripts/fleet_healthcheck.py` | Removed decommissioned bots (rsi, momentum), added active fleet (freqforge, canary, rebel), fixed strategy name v6→v7, added None-safe host-mount handling, reclassified strategy mismatch as YELLOW | NONE — reporting only |
| `orchestrator/reports/fleet_health_latest.json` | Regenerated with correct bot list and verdict | NONE — reporting output |
| `orchestrator/reports/fleet_health_latest.md` | Regenerated with correct bot list and verdict | NONE — reporting output |

---

## Validation Evidence

```
- py_compile: PASS
- No strategy files changed: PASS
- No bot configs changed: PASS
- No dry_run=false added: PASS
- No secrets in diff: PASS (credentials check outputs "absent"/"no_host_mount" only)
- No unsafe pipe patterns in patch: PASS
```

Fleet verdict before patch: **RED** (false positive from rsi+momentum)
Fleet verdict after patch: **YELLOW** (freqai-rebel has no host-mount; 3/4 bots GREEN)

---

## Remaining Risks

1. **Permission denied on jobs.json/auth.json** — 3,786 errors. Agent intermittently loses config/auth context. Not investigated in this session.
2. **Security scanner blocks** — 857 occurrences. Agent generates unsafe commands in cron jobs. Needs prompt hardening.
3. **Mem0 sync timeouts** — 262 occurrences. Memory state may be stale. Requires Mem0 health check.
4. **Tool loop failures** — 379 occurrences. Agent retries failing paths. Needs retry budget in prompts.
5. **Stale trigger locks** — 312 occurrences. Possible race condition in trigger orchestration.
6. **MCP stderr noise** — 48,804 lines of ListToolsRequest logging. Benign but fills disk.

---

## Recommended Next Step

**Investigate and fix the permission denied errors on `/opt/data/profiles/orchestrator/cron/jobs.json`** — this is the highest-count failure class (2,284 occurrences) and directly affects agent reliability. Likely requires file-lock contention analysis or ACL adjustment.
