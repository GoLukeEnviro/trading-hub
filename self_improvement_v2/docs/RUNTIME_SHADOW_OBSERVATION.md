# Runtime Shadow-Mode Observation Design

**Status:** Design Document — No Implementation
**Date:** 2026-06-15
**Issue:** #29
**Parent:** #15 (Master Roadmap)

## Objective

Design future runtime shadow-mode observation while preserving the invariant that observation does not imply deployment. The shadow session may observe but never apply.

## Dependencies

- #17 — Controlled read-only runtime probe (proves connectivity without mutation)
- #21 — Read-only adapter prototypes (PRs #207/#208 — establishes safe REST adapters)
- #22 — Strategy mutation sandbox
- #28 — Live strategy mutation approval ceremony (establishes deployment gates)

## 1. Shadow Session Model

A shadow session is a time-bound, isolated observation of runtime behavior that produces evidence but never applies changes.

| Property | Value |
|----------|-------|
| Session ID | UUID v4, generated at session start |
| Duration | 1 Freqtrade cycle (configurable: 1-6 hours) |
| State | Ephemeral (no persistence across sessions) |
| Scope | Read-only: REST GET, file read, SQLite query |
| Output | Evidence bundle + ShadowLogger entry |

## 2. Inputs from Read-Only Adapters

| Adapter | Data | Source |
|---------|------|--------|
| Freqtrade REST | `/api/v1/ping`, `/api/v1/status`, `/api/v1/count` | `freqtrade_rest_readonly.py` |
| Market data adapter | OHLCV snapshots (file-based) | `marketdata/adapter.py` |
| Fleet analyzer | Per-bot telemetry decisions | `loop/fleet_analyzer.py` |
| Kill-switch | Current mode (NORMAL/HALT_NEW/EMERGENCY) | `kill_switch.py` |

**Hard rule:** All adapters are read-only. No POST/PUT/PATCH/DELETE. No Docker exec. No subprocess calls.

## 3. What Gets Logged

Every shadow session produces:

1. **Session manifest** (JSON)
   - `session_id`, `start_time`, `end_time`, `duration_minutes`
   - `bots_contacted: int`, `bots_reachable: int`
   - `adapters_used: list[str]`
   - `safety_result: str` (PASS_SHADOW_ONLY / BLOCKED)

2. **Evidence bundle** (JSON, written to `reports/phase2/evidence/`)
   - Per-bot telemetry snapshots
   - Per-bot decision (SHADOW_PROPOSAL / NO_PROPOSAL)
   - Fleet-level verdict (GREEN / YELLOW / RED)

3. **Shadow log** (JSONL, appended to `shadow_logs/`)
   - One entry per decision
   - Includes: timestamp, bot_id, decision_type, hypothesis

## 4. How Shadow Results Affect Future Proposals

| Shadow Result | Effect on Next Cycle |
|--------------|---------------------|
| GREEN — all bots reachable | No change — continue normal cycle |
| YELLOW — partial reachability | Flag for review, add to next proposal |
| RED — fleet unreachable | Block all proposals, escalate to human |

**Crucial invariant:** Shadow results are **advisory only**. They feed into proposal candidates but never bypass human approval.

## 5. Approval Requirement

Every shadow session requires:

| Gate | Required? | Detail |
|------|-----------|--------|
| Controller PAUSED | ✅ Yes | STATE.json must show no active work item |
| Queue EMPTY | ✅ Yes | No pending proposals |
| Kill-switch ARMED | ✅ Yes | EMERGENCY mode verified functional |
| Human approval | ✅ Yes | Explicit token per session |
| Dry-run only | ✅ Yes | All bots `dry_run=True` |

## 6. Fail-Closed Behavior

| Failure Mode | Action |
|-------------|--------|
| Adapter timeout | Log warning, mark bot as unreachable |
| Adapter HTTP error | Log error, no retry within session |
| Adapter auth failure | Mark bot as YELLOW, log env vars missing |
| Session crash | Abort session, no partial evidence used |
| Controller state change | Abort session immediately |

## 7. Session Lifecycle

```
START → Verify preconditions → Open session manifest
  → For each bot: collect evidence via adapters
  → Analyze evidence (fleet analyzer)
  → Build proposal candidates
  → Pass through safety gates (RiskGuard, ShadowLogger)
  → Close session manifest
  → Write evidence bundle
END
```

## Safety Guarantees

- Observation never triggers deployment
- No automatic scheduling — each session requires explicit approval
- All adapter calls are read-only
- Session aborts on any controller state change
- Results are advisory only, never applied without human approval
