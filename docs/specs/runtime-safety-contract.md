# Runtime Safety Contract — RiskGuard & ShadowLogger

**Status:** Ratified  
**Date:** 2026-06-10  
**Author:** SI v2 Meta-Orchestrator  
**Issue:** [#22 — Define RiskGuard and ShadowLogger runtime safety contract](https://github.com/GoLukeEnviro/trading-hub/issues/22)

---

## Table of Contents

1. [Purpose](#1-purpose)
2. [Terminology](#2-terminology)
3. [Component Responsibilities](#3-component-responsibilities)
4. [Required Audit Events](#4-required-audit-events)
5. [Unavailability Policy](#5-unavailability-policy)
6. [Fail-Closed Behavior](#6-fail-closed-behavior)
7. [Minimal Audit Trail Specification](#7-minimal-audit-trail-specification)
8. [Decision Flow with Safety Gates](#8-decision-flow-with-safety-gates)
9. [Test Requirements](#9-test-requirements)
10. [Related Documents](#10-related-documents)

---

## 1. Purpose

This document defines the **runtime safety contract** for the two core safety
components of the Self-Improvement Trading System:

- **RiskGuard** — the signal-level safety gate that validates every external
  signal before it reaches a trading decision.
- **ShadowLogger** — the append-only audit trail that records every
  safety-relevant event for later forensic analysis.

The contract governs how these components interact with every runtime-near
operation: signal ingestion, adapter calls, deployment plans, approval
decisions, and shadow observations.

> **Key principle:** RiskGuard and ShadowLogger are separate evidence classes.
> A green health check on one does not imply safety on the other.

---

## 2. Terminology

| Term | Definition |
|------|-----------|
| **Safety-relevant decision** | Any operation that could affect trading state, risk exposure, signal flow, deployment, or configuration. |
| **Fail-closed** | When a required safety component is unavailable, the operation is blocked rather than allowed to proceed without protection. |
| **Read-only operation** | Inspection that produces no side effects: file reads, SQLite `SELECT`, HTTP `GET /health`, config review. |
| **Write-adjacent operation** | Producing audit output (ShadowLogger append) or generating reports — observable side effects but no trading impact. |
| **Runtime-near action** | Any action that reaches into a running container, calls a live API, or touches a mounted runtime path. |
| **Evidence class** | Independent verification category. Container running does not imply health; health does not imply dry-run mode; dry-run mode does not imply RiskGuard availability. |

### 2.1 Component Boundaries

```
┌─────────────────────────────────────────────────────────┐
│                    Runtime Safety Layer                  │
│                                                          │
│  ┌──────────────┐    ┌──────────────────┐               │
│  │  RiskGuard   │    │  ShadowLogger    │               │
│  │  (gate)      │    │  (audit trail)   │               │
│  └──────┬───────┘    └────────┬─────────┘               │
│         │                     │                          │
│         ▼                     ▼                          │
│  ┌─────────────────────────────────────┐                │
│  │        Decision / Action            │                │
│  │  (probe, approve, deploy, observe)  │                │
│  └─────────────────────────────────────┘                │
│                                                          │
│  FleetRiskManager = fleet-level risk (separate concern) │
│  Guardian = permission / cron guard (separate concern)  │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Component Responsibilities

### 3.1 RiskGuard

RiskGuard is the **signal safety gate**. It validates every incoming trading
signal before it reaches a bot decision.

**Responsibilities:**

1. **Schema validation** — Verify signal structure matches the expected contract.
2. **Freshness check** — Reject signals older than `STALENESS_MINUTES` (defined
   in `FleetRiskManager.CONFIDENCE_MIN` / `STALENESS_MINUTES`).
3. **Confidence gate** — Reject signals below `CONFIDENCE_MIN`.
4. **Allowlist validation** — Verify the signal's pair/token is on the approved
   trading list.
5. **Action validation** — Verify the action is entry-safe:
   - `BUY` / `SELL` only for entries (with appropriate confidence threshold).
   - `TREND_HOLD` / `WATCH` must never force an entry.
   - `HOLD` blocks all entry activity.
6. **Baseline disagreement** — Flag strong repeated disagreement between
   signal core and baseline strategy.

**Output verdicts:**
| Verdict | Meaning |
|---------|---------|
| `ACCEPTED` | Signal passed all gates. May influence trading. |
| `WATCH_ONLY` | Signal has minor issues. Permitted for observation but must not influence entry decisions. |
| `BLOCK_ENTRY` | Signal failed a critical gate. Must not reach trading decisions. |

**Relationship to other risk components:**

- **FleetRiskManager** (`freqtrade/shared/fleet_risk_manager.py`) handles
  fleet-level exposure, correlation, drawdown protection. It is the second
  safety layer after RiskGuard and operates on a different abstraction level.
- **Guardian** (`trading-guardian` container) handles permission enforcement
  and cron guardrails. It is an infrastructure-level safety component.
- RiskGuard is the **signal-level** gate — the first checkpoint in the
  signal-to-decision pipeline.

### 3.2 ShadowLogger

ShadowLogger is the **append-only audit trail** for safety-relevant events.

**Responsibilities:**

1. **Record every safety-relevant event** with timestamp, source, decision, and
   evidence reference.
2. **Provide forensic traceability** — any past decision can be reconstructed
   from the audit trail.
3. **Support both in-memory (test) and file-backed (production) modes.**
4. **Never modify or delete entries** — strictly append-only.
5. **Never contain secrets, credentials, tokens, or API keys.**

**Output format:**

The canonical output is JSONL (one JSON object per line), written to
`orchestrator/logs/shadow_decisions.jsonl` for operational events and to
per-bot JSONL files for pipeline-phase events.

**Required fields per entry:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `timestamp_utc` | ISO 8601 | ✅ | When the event occurred |
| `event_type` | string | ✅ | One of the defined event types (see [§4](#4-required-audit-events)) |
| `source` | string | ✅ | Component or agent that produced the event |
| `decision` | string | ✅ | The outcome or verdict |
| `reason` | string | ✅ | Human-readable justification |
| `evidence_ref` | string | - | Path or reference to supporting evidence |
| `bot_id` | string | - | Affected bot (if applicable) |
| `phase` | string | - | Pipeline phase (if applicable) |

---

## 4. Required Audit Events

Every safety-relevant decision MUST produce a ShadowLogger entry BEFORE the
operation and AFTER the operation (or on failure).

### 4.1 Event Types

| Event Type | When Fired | Required Before | Required After | Required Fields |
|-----------|-----------|-----------------|----------------|-----------------|
| `signal_ingest` | Signal received from signal core | ✅ Before validation | ✅ After verdict | event_type, source, decision, reason, bot_id |
| `risk_assess` | RiskGate check performed | ✅ Before check | ✅ After verdict | event_type, source, decision, reason, confidence, freshness |
| `probe_start` | Read-only runtime probe begins | ✅ Before probe | ✅ After probe | event_type, source, decision, reason, probe_scope |
| `probe_result` | Each probe datum collected | ❌ No | ✅ After datum | event_type, source, decision, evidence_ref |
| `approval_request` | Human approval requested | ✅ Before request | ✅ After response | event_type, source, decision, reason, approval_id |
| `approval_decision` | Human approval granted/denied | ❌ No | ✅ After decision | event_type, source, decision, reason, approval_id |
| `adapter_call` | Any adapter method invoked | ✅ Before call | ✅ After result | event_type, source, decision, adapter_name, method, duration_ms |
| `deployment_plan` | Deployment plan created | ✅ Before apply | ✅ After apply or fail | event_type, source, decision, reason, plan_id, affected_bots |
| `shadow_observe` | Shadow observation cycle | ✅ Before cycle | ✅ After cycle | event_type, source, decision, reason, observation_window |
| `config_inspect` | Config read for analysis | ❌ No | ✅ After read | event_type, source, decision, target_path |
| `health_check` | Health check performed | ❌ No | ✅ After check | event_type, source, decision, component, status |
| `error` | Any unexpected error in a safety-relevant path | ❌ No | ✅ After error | event_type, source, decision="fail", reason, error_type |

### 4.2 Decision Values

Every event carries a `decision` field with one of:

| Decision | Meaning |
|----------|---------|
| `allow` | Operation permitted after gate check |
| `block` | Operation blocked by gate |
| `pass` | Step completed successfully |
| `fail` | Step failed or raised exception |
| `hold` | No action taken (neutral) |
| `watch` | Observation mode only |
| `pending` | Awaiting external input (e.g., human approval) |
| `deferred` | Decision postponed to later cycle |

---

## 5. Unavailability Policy

### 5.1 RiskGuard Unavailable

If RiskGuard is **unavailable** (not deployed, crashed, unreachable, or
returning errors):

| Operation Type | Behavior | Classification |
|---------------|----------|---------------|
| Read-only inspection | ✅ Continue with WARNING | `WARNING` |
| Signal validation | ❌ **BLOCKED** — no signal may reach trading decisions without RiskGuard | `BLOCKED` |
| Adapter call (read-only) | 🔶 Continue read-only with WARNING if RiskGuard would not affect safety | `WARNING` |
| Adapter call (write-adjacent) | ❌ **BLOCKED** | `BLOCKED` |
| Deployment plan | ❌ **BLOCKED** | `BLOCKED` |
| Approval decision | ❌ **BLOCKED** — cannot approve without risk assessment | `BLOCKED` |
| Shadow observation | 🔶 Continue read-only with WARNING | `WARNING` |
| Dry-run signal validation | 🔶 Continue with WARNING, but mark result as degraded | `WARNING` |

> **Rule:** RiskGuard unavailable means **fail-closed for any decision that
> affects trading or risk exposure.** Read-only evidence collection may
> continue if safe.

### 5.2 ShadowLogger Unavailable

If ShadowLogger is **unavailable** (cannot write, filesystem full, permissions
error, or in-memory mode with data loss risk):

| Operation Type | Behavior | Classification |
|---------------|----------|---------------|
| Read-only inspection | ✅ Continue with WARNING | `WARNING` |
| Signal validation | 🔶 Continue but note missing audit trail | `WARNING` |
| Adapter call (read-only) | 🔶 Continue with WARNING (audit will be incomplete) | `WARNING` |
| Adapter call (write-adjacent) | 🔶 Continue with WARNING but attempt to buffer or fall back | `WARNING` |
| Deployment plan | ❌ **BLOCKED** — no deployment without audit trail | `BLOCKED` |
| Approval decision | ❌ **BLOCKED** — cannot approve without audit trail | `BLOCKED` |
| Shadow observation | ❌ **BLOCKED** — observation requires audit trail | `BLOCKED` |
| Dry-run signal validation | 🔶 Continue with WARNING, results marked `DEGRADED` | `WARNING` |

> **Rule:** ShadowLogger unavailable means **no safety-relevant write or
> decision action may proceed.** Read-only evidence and non-decision writes
> may continue with WARNING.

### 5.3 Both Unavailable

| Operation Type | Behavior |
|---------------|----------|
| All operations not explicitly allowed below | ❌ **BLOCKED** |
| Read-only file/config inspection | ✅ Continue with WARNING (degraded safety context) |
| Error logging to alternative sink | ✅ Continue (attempt to preserve error context) |

---

## 6. Fail-Closed Behavior

### 6.1 Definition

Fail-closed means: if a safety component cannot confirm that an operation is
safe, the operation is **not performed**. This is the default behavior for
all trading-adjacent and risk-affecting operations.

### 6.2 Implementation Requirements

1. **RiskGuard gate check is required** before any signal reaches a Freqtrade
   bot decision. If RiskGuard does not respond or returns an error, the signal
   is rejected. No default-allow path exists for signals.

2. **ShadowLogger write is required** before a deployment plan is executed or
   an approval is recorded. If the write fails, the operation is rolled back
   where possible, and the error is escalated.

3. **Circuit breaker pattern:** If RiskGuard or ShadowLogger fails
   N times consecutively (configurable, default N=3), the calling component
   must escalate to a human operator and refuse further operations until
   explicitly cleared.

4. **Startup check:** An orchestrator or SI v2 pipeline that relies on
   RiskGuard or ShadowLogger must verify availability before beginning
   any safety-relevant work. If unavailable at startup, it must enter a
   degraded mode and escalate.

### 6.3 Exception: Read-Only Probe

The only exception to fail-closed is a **read-only runtime probe** that has
been explicitly approved with:
- Documented scope
- Known risk of degraded safety context
- Explicit acceptance that RiskGuard and/or ShadowLogger may be unavailable
- Rollback or stop condition pre-defined

Even then, the probe must note the missing component in its output and
classify results as `DEGRADED`.

---

## 7. Minimal Audit Trail Specification

Every safety-relevant action MUST produce at minimum:

### 7.1 Before Action (Pre-flight)

```
ENTRY:
  event_type: "{action_type}"
  timestamp_utc: "{now}"
  source: "{component}"
  decision: "pending"
  reason: "Pre-flight — intended action: {description}"
  evidence_ref: "{optional reference}"
```

### 7.2 After Action (Post-flight)

```
ENTRY:
  event_type: "{action_type}"
  timestamp_utc: "{now}"
  source: "{component}"
  decision: "{pass|fail|block|allow}"
  reason: "{outcome description}"
  evidence_ref: "{path to result or error}"
  duration_ms: "{elapsed milliseconds}"
```

### 7.3 On Error

```
ENTRY:
  event_type: "error"
  timestamp_utc: "{now}"
  source: "{component}"
  decision: "fail"
  reason: "{error message — NO SECRETS}"
  error_type: "{exception type or error code}"
  evidence_ref: "{optional reference}"
```

### 7.4 Audit Trail Integrity

- Entries are strictly append-only.
- Once written, entries must never be modified or deleted.
- Log rotation must preserve the trailing N entries (configurable minimum:
  10,000 entries or 30 days, whichever is greater).
- The audit trail must survive container restarts (persistent volume mount).
- The audit trail must be readable without the producing component (plain
  JSONL with documented schema).

---

## 8. Decision Flow with Safety Gates

```
                    ┌──────────────┐
                    │  Signal In   │
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
                    │  RiskGuard   │◄── Freshness, confidence, schema, allowlist
                    │  Validate    │
                    └──────┬───────┘
                           │
               ┌───────────┼───────────┐
               ▼           ▼           ▼
         ACCEPTED     WATCH_ONLY   BLOCK_ENTRY
               │           │           │
               │           ▼           ▼
               │     ┌──────────┐ ┌──────────┐
               │     │Observe   │ │ Shadow   │
               │     │only, no  │ │ Logger   │
               │     │entry     │ │ Block    │
               │     └──────────┘ └──────────┘
               ▼
     ┌──────────────────┐
     │  FleetRiskManager │── Second safety layer (fleet-level)
     │  (drawdown, corr) │
     └────────┬─────────┘
              ▼
     ┌──────────────────┐
     │  Bot Decision    │── Actual entry/exit logic
     │  (Freqtrade)     │
     └────────┬─────────┘
              ▼
     ┌──────────────────┐
     │  ShadowLogger    │── Append audit entry
     │  (post-hoc)      │
     └──────────────────┘
```

Every arrow in this flow requires a ShadowLogger entry before and after.

---

## 9. Test Requirements

### 9.1 Fail-Closed Tests

- [ ] **RiskGuard unavailable → signal validation blocked**: Test that when
  RiskGuard is unreachable, no signal passes through to Freqtrade.
- [ ] **ShadowLogger unavailable → decision blocked**: Test that when
  ShadowLogger cannot write, deployment plans and approvals are blocked.
- [ ] **Both unavailable → only read-only permitted**: Test that only file
  inspection passes when both are down.
- [ ] **Circuit breaker after N failures**: Test that the calling component
  escalates after N consecutive failures.

### 9.2 Audit Trail Tests

- [ ] **Every event type produces a valid entry**: Test that each defined
  event type generates a JSONL entry with all required fields.
- [ ] **Append-only invariant**: Test that entries are never modified or
  deleted after creation.
- [ ] **No secrets in entries**: Audit all entry generation paths for
  accidental secret inclusion.
- [ ] **Survives restart**: Test that persistent ShadowLogger data survives
  component restart.

### 9.3 Integration Tests

- [ ] **RiskGuard + ShadowLogger in probe flow**: Test that a simulated
  runtime probe produces correct before/after entries.
- [ ] **RiskGuard + ShadowLogger in approval flow**: Test that a simulated
  approval cycle produces correct entries.
- [ ] **RiskGuard + FleetRiskManager reconciliation**: Test that both gates
  can independently block and that their verdicts are both recorded.

---

## 10. Related Documents

| Document | Location | Relationship |
|----------|----------|-------------|
| AGENTS.md | `/home/hermes/projects/trading/AGENTS.md` | System architecture overview; RiskGuard/ShadowLogger described as SPEC ONLY (to be updated) |
| FleetRiskManager | `freqtrade/shared/fleet_risk_manager.py` | Fleet-level risk (second gate after RiskGuard) |
| ShadowLogger implementation | `self_improvement_v2/src/si_v2/deploy/shadow_logger.py` | Current SI v2 ShadowLogger code |
| SI v2 Real Adapter Design | `self_improvement_v2/docs/REAL_ADAPTER_DESIGN.md` | Adapter safety preconditions reference ShadowLogger |
| Controlled Runtime Probe Plan | `self_improvement_v2/docs/CONTROLLED_READ_ONLY_RUNTIME_PROBE_PLAN.md` | Probe safety rules, references RiskGuard/ShadowLogger unavailability |
| ADR: AI4Trade Integration Boundary | `self_improvement_v2/docs/ADR_AI4TRADE_INTEGRATION_BOUNDARY.md` | Defines integration boundary with SignalProviderProtocol |
| Full E2E Dry-Run Pipeline | `self_improvement_v2/docs/FULL_E2E_DRY_RUN_PIPELINE.md` | Pipeline stages; fail-closed per stage |
| docs/decisions/ | `docs/decisions/2026-05-14-soul-agents-sync.md` | Prior architecture decisions |
| SOUL.md | `/home/hermes/projects/trading/SOUL.md` | Project identity; RiskGuard is preferred risk authority |
| ORCHESTRATOR_CHARTER.md | `/home/hermes/projects/trading/ORCHESTRATOR_CHARTER.md` | Operating rules and escalation paths |
