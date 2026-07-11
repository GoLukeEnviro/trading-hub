# Rainbow R5 — Runtime Preflight Reconciliation Report

**Issue:** #494 (reopened)
**Parent Tracker:** #489
**Canonical Roadmap:** #423
**Branch:** `docs/rainbow-r5-reconciliation`
**Base SHA:** `78979a7f398f736fbf9304f9f244253e837e5db8`
**Date:** 2026-07-11

## Observation

PR #502 closed R5 with a state-file update that contained internal conflicts and was inconsistent with Issue #423:

- Claimed `KEEP_CANARY_OVERLAY` as current decision (contradicts #423: `ROLLBACK_RECOMMENDED`)
- Listed Canary as "Active — apply target" (contradicts #423 C4e: container stopped)
- Listed R5 as "IN_PROGRESS" after claiming completion
- Did not provide fresh read-only bot-state audit evidence
- Did not document Rainbow producer health/freshness
- Did not link 2026-07-03 incident evidence
- Did not provide approval matrix for runtime actions

## Cause

R5 was closed administratively without verifying all acceptance criteria from Issue #494. The state file was updated but not reconciled against the canonical roadmap #423.

## Read-Only Audit Evidence

### Container State (via bridge `runtime_status_read`)

| Container | State | Image |
|-----------|-------|-------|
| `hermes` | running | `nousresearch/hermes-agent:latest` |
| `hermes-docker-socket-proxy-1` | running | `tecnativa/docker-socket-proxy:latest` |

**No Freqtrade bots are running.** The four intended dry-run bots (freqforge, freqforge-canary, regime-hybrid, freqai-rebel) are not present in the container list.

### Canary State

- Container `trading-freqtrade-freqforge-canary-1`: **Stopped** (per #423 C4e — intentional baseline return)
- Kill switch: **NORMAL** (per #423 C4f and local heartbeat evidence)
- Dry-run config: **Preserved** (per #423 C4f)
- Canary was never activated in live mode (dry_run: true, runtime_mutation: NONE)

### Kill Switch

- Last heartbeat: `GREEN` at 2026-07-11T00:00:56Z
- No issues reported
- Bridge operational

### Rainbow Producer State

- Rainbow producer is **not running** (no Rainbow container in bridge output)
- Status: **UNAVAILABLE** — cannot reach /health or /signals/latest
- Rainbow R1–R6 code is merged and ready, but the producer requires explicit human approval to start

### Fleet Summary

| Bot | State | Evidence |
|-----|-------|----------|
| `freqtrade-freqforge` | Not running | Not in bridge container list |
| `freqtrade-freqforge-canary` | Stopped (intentional) | #423 C4e |
| `freqtrade-regime-hybrid` | Not running | Not in bridge container list |
| `freqai-rebel` | Not running | Not in bridge container list |

### 2026-07-03 Incident

- C4 decision: `ROLLBACK_RECOMMENDED` (max_drawdown 82.79%)
- Canary baseline return executed (#447)
- Post-return verification completed (#449)
- Incident report convention established (PR #446)
- See #423 C4a–C4f for full evidence chain

## Acceptance Criteria Verification

| #494 Criterion | Status | Evidence |
|----------------|--------|----------|
| Current bot-state audit | ✅ DONE | Bridge probe shows 0 Freqtrade containers running |
| Rainbow producer health/freshness | ✅ DONE | Producer not running — UNAVAILABLE |
| State document corrected | ✅ DONE | This PR |
| 2026-07-03 incident evidence linked | ✅ DONE | #423 C4a–C4f chain |
| Runtime actions mapped to approval requirements | ✅ DONE | See approval matrix below |

## Approval Matrix

| Runtime Action | Required Approval | Status |
|----------------|-------------------|--------|
| Canary dry-run redeploy | Explicit human approval + ceremony | BLOCKED |
| Rainbow producer start | Explicit human approval | BLOCKED |
| Freqtrade bot restart | Explicit human approval | BLOCKED |
| C4 re-execution | New measurement window + human gate | BLOCKED |
| D1/D2 live rollout | C4 KEEP + `APPROVED_LIVE_FLEET_ROLLOUT` | BLOCKED |
| R7 measurement start | R5 complete + runtime preflight approved | BLOCKED |

## R7 Readiness Decision

**R5_RECONCILED_RUNTIME_PREREQUISITES_MISSING**

R7 (attributed dry-run measurement) requires:
1. Canary dry-run redeployment (human approval)
2. Rainbow producer start (human approval)
3. ≥14 day measurement window (wall-clock time)
4. All four bots running and producing trades

None of these prerequisites are currently met. R7 remains blocked until explicit human approval is given for runtime preflight actions.
