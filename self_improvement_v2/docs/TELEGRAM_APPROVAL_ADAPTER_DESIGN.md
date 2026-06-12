# Telegram Approval Live Adapter Design

> **Design document — NO implementation in this phase.**
> Defines the future live Telegram adapter contract for sending approval
> notifications and capturing human approval decisions.

**Status:** Ratified  
**Date:** 2026-06-10  
**Author:** SI v2 Meta-Orchestrator  
**Issue:** [#25 — Design Telegram approval live adapter with token isolation and dry-run fallback](https://github.com/GoLukeEnviro/trading-hub/issues/25)  
**Depends on:** [#22 — RiskGuard/ShadowLogger runtime safety contract](https://github.com/GoLukeEnviro/trading-hub/issues/22)

---

## Table of Contents

1. [Purpose](#1-purpose)
2. [Design Principles](#2-design-principles)
3. [Adapter Contract](#3-adapter-contract)
4. [Token Isolation](#4-token-isolation)
5. [Dry-Run Fallback](#5-dry-run-fallback)
6. [Message Schema](#6-message-schema)
7. [Approval Correlation](#7-approval-correlation)
8. [Timeout, Retry, and Failure](#8-timeout-retry-and-failure)
9. [Security Rules](#9-security-rules)
10. [Related Documents](#10-related-documents)

---

## 1. Purpose

This document defines the design for a **future** live Telegram adapter that:

1. Sends approval notifications to an operator via Telegram.
2. Captures human approval decisions (approve / reject / defer).
3. Correlates approvals with SI v2 pipeline phases.
4. Falls back to dry-run mode when Telegram credentials are unavailable.

> ⚠️ **No implementation in this phase.** The existing `DryRunTelegramAdapter`
> (in-memory capture) continues to be the only active implementation.

---

## 2. Design Principles

| Principle | Rule |
|-----------|------|
| **Token isolation** | Telegram tokens must never appear in source code, config files, logs, or audit trails. Sourced exclusively from environment or a sealed secret store. |
| **Fail-closed** | Missing or invalid token → no messages sent → operation blocked with clear error. |
| **Dry-run fallback** | Without valid token, the adapter captures messages in memory (current dry-run behavior). |
| **No background polling** | The adapter sends messages and polls for response. It must never start background threads or long-polling loops. |
| **No auto-approval** | Every approval requires explicit human response. No timeout-based auto-approve. |
| **Audit trail** | Every message and response is logged to ShadowLogger. |
| **Correlation** | Every approval message carries a unique correlation ID linking it to the SI v2 pipeline run. |

---

## 3. Adapter Contract

### 3.1 Protocol Extension

The adapter extends the existing `TelegramAdapter` protocol from
`src/si_v2/adapters/telegram_adapter.py`:

```python
class TelegramAdapter(Protocol):
    def send_message(self, chat_id_hint: str, message: str) -> TelegramMessage: ...
    def send_approval_request(
        self,
        chat_id_hint: str,
        bot_id: str,
        candidate_sha: str,
        backtest_summary: dict,
        walk_forward_summary: dict,
        risk_reason: str,
    ) -> TelegramMessage: ...
```

### 3.2 Additional Methods (Live Adapter Only)

The live adapter adds one method not in the base protocol:

| Method | Signature | Returns | Purpose |
|--------|-----------|---------|---------|
| `poll_for_approval` | `(correlation_id: str, timeout: int) -> ApprovalResponse` | `ApprovalResponse` | Wait for human decision |

### 3.3 ApprovalResponse Schema

```python
class ApprovalResponse(BaseModel):
    correlation_id: str          # Links to the original request
    decision: Literal["approved", "rejected", "deferred"]
    responder: str               # Telegram username or user ID
    responded_at: str            # ISO 8601 timestamp
    reason: str | None           # Optional human reason
```

---

## 4. Token Isolation

### 4.1 Token Sourcing

The Telegram bot token and chat ID MUST be sourced from **one** of these
locations, checked in order:

1. **Hermes secret store** — `~/.hermes/secrets/telegram.json`
   (preferred, most secure)
2. **Environment variable** — `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`
   (acceptable for containerized deployment)
3. **No token found** → switch to **dry-run fallback** (see §5)

### 4.2 Token Handling Rules

1. Tokens must never be logged, printed, or included in error messages.
2. Token reads must produce a `SHADOW_READ_SECRET` audit event (recording
   *that* a read occurred, not *what* was read).
3. Token values must never be written to disk, ShadowLogger, or any
   persistent store.
4. Token validation is format-only (checking length and prefix). No API
   call is made during initialization to verify the token.
5. Token is read once at adapter construction and held in memory for the
   lifetime of the adapter instance.

### 4.3 Failure Modes

| Condition | Behavior |
|-----------|----------|
| Token absent | Switch to dry-run fallback. Log WARNING (no token details). |
| Token malformed | Raise RuntimeError at construction. No fallback — operator must fix. |
| Token read error (file I/O) | Raise RuntimeError at construction. Escalate. |
| Chat ID absent | Switch to dry-run fallback. Log WARNING. |

---

## 5. Dry-Run Fallback

When Telegram credentials are unavailable, the adapter transparently
falls back to the existing `DryRunTelegramAdapter` behavior:

```
LiveTelegramAdapter
  ├── Token + Chat ID available → Real Telegram API (HTTPS)
  └── Token or Chat ID missing  → DryRunTelegramAdapter (in-memory)
```

### 5.1 Dry-Run Behavior

1. All messages are captured in memory (same as `DryRunTelegramAdapter`).
2. `poll_for_approval()` immediately returns a simulated
   `ApprovalResponse(decision="approved")` — allowing pipeline
   progression in test/dry-run mode.
3. A WARNING is logged on every dry-run message: "Telegram unavailable —
   running in dry-run mode."
4. The pipeline SHALL mark results produced during dry-run Telegram mode
   as `DEGRADED` in its output.

### 5.2 Dry-Run Escalation

If a pipeline is running in `proposal_only` mode (not dry-run mode) and
Telegram is in fallback, the pipeline MUST block deployment plans and
approvals. Read-only observation may continue with `DEGRADED` marking.

---

## 6. Message Schema

### 6.1 Approval Request Message

```
🧬 SI v2 Mutation Approval Required
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Bot:            freqforge
Candidate:      a1b2c3d4...
Parameters:
  max_open_trades: 5 → 8
  stoploss:      -0.05 → -0.08

Backtest Result:
  Total trades:  42
  Profit:        +3.2%
  Win rate:      71.4%
  Sharpe:        1.87

Walk-Forward Result:
  Total trades:  28
  Profit:        +1.9%
  Win rate:      64.3%

Risk Assessment:
  Correlation with existing bots: LOW
  Drawdown increase:              +0.3%
  Max risk score:                 2.1 / 10

─────────────────────────────────
Reply: /approve <id> or /reject <id> <reason>
Timeout: 30 minutes
```

### 6.2 Notification Message

```
🔔 SI v2 Pipeline Update
━━━━━━━━━━━━━━━━━━━━━━━━━
Phase:      Observe (Stage 1)
Bot:        regime-hybrid
Status:     ✅ Completed
Trades:     18
Duration:   2.3s
```

### 6.3 Error Alert Message

```
🚨 SI v2 Pipeline Error
━━━━━━━━━━━━━━━━━━━━━━━━
Phase:       Backtest (Stage 4)
Bot:         freqai-rebel
Error:       Container unreachable after 3 retries
Action:      Pipeline blocked. Manual intervention required.
```

---

## 7. Approval Correlation

### 7.1 Correlation ID Format

```
siv2-{run_id}-{stage}-{candidate_sha[:8]}
```

Example: `siv2-20260610-004-approve-a1b2c3d4`

### 7.2 Lifecycle

```
1. send_approval_request() called
   → Generates correlation_id
   → Logs SHADOW_APPROVAL_REQUEST event
   → Sends Telegram message with correlation_id

2. poll_for_approval() called
   → Waits for human response (polling, not long-poll)
   → Timeout after N minutes (configurable, default 30)
   → On timeout → returns deferred response
   → On response → logs SHADOW_APPROVAL_DECISION event

3. Pipeline consumes ApprovalResponse
   → approved: continue to next stage
   → rejected: block candidate, log reason
   → deferred: pause pipeline, retry later
```

### 7.3 No Auto-Approval

Under no circumstances does the adapter auto-approve. On timeout:
- The decision is `deferred`, never `approved`.
- The pipeline stores the deferred decision and retries on the next cycle.
- After 3 deferred cycles, the candidate is automatically rejected.

---

## 8. Timeout, Retry, and Failure

### 8.1 Timeouts

| Operation | Timeout | Behavior |
|-----------|---------|----------|
| `send_message` | 15s | Retry once, then fail-closed |
| `send_approval_request` | 15s | Retry once, then fail-closed |
| `poll_for_approval` | 30 min (configurable) | Return `deferred` on timeout |

### 8.2 Retry Policy

| Failure Type | Retry Count | Backoff |
|-------------|-------------|---------|
| Network error | 1 immediate retry | None |
| HTTP 5xx | 1 retry after 5s | Linear |
| HTTP 4xx (non-auth) | 0 retries | N/A |
| HTTP 401 (auth) | 0 retries | Fail permanently |

### 8.3 Circuit Breaker

After 3 consecutive failures (any operation), the adapter:
1. Enters `CIRCUIT_OPEN` state for 60 seconds.
2. All calls immediately return `deferred` without attempting network.
3. After 60 seconds, one test call is attempted ( `CIRCUIT_HALF_OPEN` ).
4. On success, returns to normal. On failure, back to `CIRCUIT_OPEN`.

---

## 9. Security Rules

1. **Never log tokens** — token values must never appear in logs, audit
   trails, error messages, or crash reports.
2. **Never store tokens** — tokens must never be written to disk by the
   adapter (env/secret-store only).
3. **Never echo tokens** — if a Telegram API error contains the token in
   its message, the error must be redacted before logging.
4. **No background threads** — the adapter must never start threads,
   timers, or long-polling loops.
5. **No auto-approve** — every approval requires a human response.
6. **Fail-closed on auth** — if the token is rejected by Telegram's API,
   the adapter must raise immediately and not fall back to dry-run mode.
7. **Rate limiting** — maximum 20 messages per 60 seconds (same as #20 contract).

---

## 10. Related Documents

| Document | Location | Relationship |
|----------|----------|-------------|
| TelegramAdapter Protocol | `src/si_v2/adapters/telegram_adapter.py` | Existing interface |
| Real Adapter Design | `self_improvement_v2/docs/REAL_ADAPTER_DESIGN.md` | Preconditions for real adapters |
| Runtime Safety Contract | `docs/specs/runtime-safety-contract.md` | Audit events, fail-closed |
| Read-Only Adapter Contracts | `self_improvement_v2/docs/READ_ONLY_ADAPTER_CONTRACTS.md` | Call budgets, audit events |
| Real Telegram Adapter Base | `src/si_v2/adapters/real_base.py` | Abstract base with env gate |
| Hermes Secret Store | `~/.hermes/secrets/` | Token storage location |
