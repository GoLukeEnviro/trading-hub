# Read-Only Runtime Adapter Contracts

> **Design document — NO implementation in this phase.**
> Defines the read-only adapter contracts for Docker, Freqtrade, and Telegram
> based on Phase M.2 runtime probe evidence.

**Status:** Ratified  
**Date:** 2026-06-10  
**Author:** SI v2 Meta-Orchestrator  
**Issue:** [#20 — Design read-only Docker/Freqtrade adapter contracts after runtime probe](https://github.com/GoLukeEnviro/trading-hub/issues/20)  
**Evidence base:** [Phase M.2 Runtime Signal Validation Report](../reports/runtime_probe/phase-m2-dryrun-signal-validation-20260610-001/runtime_signal_validation_report.md)

---

## Table of Contents

1. [Purpose](#1-purpose)
2. [Protocol Contracts](#2-protocol-contracts)
3. [Failure Behavior](#3-failure-behavior)
4. [Call Budgets](#4-call-budgets)
5. [Audit Events](#5-audit-events)
6. [Container Evidence from Probe](#6-container-evidence-from-probe)
7. [Implementation Rules](#7-implementation-rules)
8. [Related Documents](#8-related-documents)

---

## 1. Purpose

This document defines the **read-only adapter contracts** for the three runtime
integration points in SI v2:

- **DockerAdapter** — execute read-only commands inside containers
- **FreqtradeAdapter** — read Freqtrade config and trade history
- **TelegramAdapter** — send notifications (dry-run only in this phase)

These contracts are informed by the Phase M.2 controlled runtime probe
([probe report](../reports/runtime_probe/phase-m2-dryrun-signal-validation-20260610-001/runtime_signal_validation_report.md)),
which confirmed 18 running containers, 5 Freqtrade dry-run bots, and verified
that all bots operate in `dry_run=true` mode.

---

## 2. Protocol Contracts

### 2.1 DockerAdapter

**File:** `src/si_v2/adapters/docker_adapter.py` (Protocol exists)

| Method | Signature | Returns | Read-Only | Notes |
|--------|-----------|---------|-----------|-------|
| `exec_readonly` | `(container: str, command: list[str]) -> str` | Command stdout | ✅ | No interactive/attached commands |
| `container_is_running` | `(container: str) -> bool` | Running status | ✅ | No state change |
| `get_container_ip` | `(container: str) -> str` | IP address | ✅ | No state change |

**Forbidden methods (never add):**
- `restart()`, `stop()`, `start()`, `kill()`, `rm()`, `pause()`, `unpause()`
- `exec()` without "readonly" guard
- `cp()` (copy files in/out of containers)
- `login()`, `pull()`, `push()` (registry operations)

**Execution rules:**
1. Commands must be allowlisted per container. The current allowlist covers:
   - Freqtrade containers: `ls`, `cat config.json`, `freqtrade trade-history`
   - Signal containers: `cat signal.json`, `ls`
2. Commands must never include `env`, `printenv`, or secret-accessing commands.
3. `docker exec` must never be called with `-i` (interactive) or `-t` (tty) flags.
4. Command timeout: maximum 30 seconds.
5. No retry on failure — fail-closed.

**Validation (from Phase M.2 probe):**
- Container names confirmed: `trading-freqtrade-freqforge-1`, `trading-freqtrade-regime-hybrid-1`, etc.
- All containers run with `dry_run=true`
- All Freqtrade bots use port mapping `127.0.0.1:PORT->8080`

### 2.2 FreqtradeAdapter

**File:** `src/si_v2/adapters/freqtrade_adapter.py` (Protocol exists)

| Method | Signature | Returns | Read-Only | Notes |
|--------|-----------|---------|-----------|-------|
| `read_config` | `(bot_id: str) -> dict` | Config dict (copy) | ✅ | Never returns secrets |
| `get_trade_history` | `(bot_id: str, limit: int = 100) -> list[dict]` | Trade records | ✅ | From dry-run SQLite |
| `run_backtest` | `(bot_id: str, overlay: MutationOverlay) -> dict` | Backtest result | ✅ | Runs inside container |

**Forbidden methods (never add):**
- `write_config()`, `place_order()`, `cancel_order()`
- `set_dry_run(mode: bool)` — must never change dry-run mode
- `delete_trades()`, `force_entry()`, `force_exit()`

**Execution rules:**
1. `read_config` must redact or skip secret-containing keys (`api_key`, `secret`, `password`, `token`).
2. `get_trade_history` queries only the bot-specific SQLite database at
   `freqtrade/bots/{bot_id}/user_data/tradesv3.{bot_id}.dryrun.sqlite`.
   Never query a generic `tradesv3.sqlite`.
3. `run_backtest` must use `freqtrade backtesting --export trades` inside the
   bot container. Must never run backtesting outside the container.
4. All methods must fail-closed on error (exception → `BLOCKED` status).
5. Timeout: 30 seconds for reads, 300 seconds for backtests.

**Database evidence (from Phase M.2 probe):**
- Each bot has a custom `db_url`: `tradesv3.{name}.dryrun.sqlite`
- Freqtrade version: `freqtradeorg/freqtrade:stable` (all 4 main bots)
- FreqAI Rebel uses a custom image: `freqtrade-freqai-rebel:custom`

### 2.3 TelegramAdapter

**File:** `src/si_v2/adapters/telegram_adapter.py` (Protocol exists)

| Method | Signature | Returns | Read-Only | Notes |
|--------|-----------|---------|-----------|-------|
| `send_message` | `(chat_id_hint: str, message: str) -> TelegramMessage` | Captured message | ✅ | Dry-run only |
| `send_approval_request` | `(chat_id_hint, bot_id, candidate_sha, bt_summary, wf_summary, risk_reason) -> TelegramMessage` | Captured message | ✅ | Dry-run only |

**Forbidden:**
- Any method that makes real HTTP calls to `api.telegram.org`
- Any method that reads `TELEGRAM_BOT_TOKEN` or `TELEGRAM_CHAT_ID` from env
- Any method that sends messages to real Telegram chats

**Execution rules:**
1. The dry-run implementation captures all messages in memory.
2. A real Telegram adapter may only be added under a separate approval-gated issue
   (tracked in [#25](https://github.com/GoLukeEnviro/trading-hub/issues/25)).
3. All `TelegramMessage` objects must be logged to ShadowLogger for audit.

---

## 3. Failure Behavior

Every adapter method must follow the **fail-closed** policy defined in the
[Runtime Safety Contract](../specs/runtime-safety-contract.md):

| Scenario | Behavior | Classification |
|----------|----------|----------------|
| Container not found | Raise exception → stage `failed` | `BLOCKED` |
| Command timeout | Raise timeout exception → stage `failed` | `BLOCKED` |
| Command exits non-zero | Log stderr, return empty/error → stage `failed` | `BLOCKED` |
| Database not found | Raise exception → stage `failed` | `BLOCKED` |
| Database corrupted | Raise exception → stage `failed` | `BLOCKED` |
| Network error (Telegram) | Capture error message in memory → stage `failed` | `BLOCKED` |
| Secret detected in output | Redact, log warning, escalate | `ESCALATED` |

---

## 4. Call Budgets

Every adapter method must enforce a call budget to prevent abuse:

| Adapter | Per-Method Budget | Global Budget | Reset |
|---------|------------------|---------------|-------|
| DockerAdapter | 10 calls/min per method | 60 calls/min total | Rolling 60s window |
| FreqtradeAdapter | 10 calls/min per method | 30 calls/min total | Rolling 60s window |
| TelegramAdapter | 20 messages/min total | 100 messages/hour | Rolling 60s / 3600s windows |

**Call budget violation behavior:**
1. Log the violation to ShadowLogger.
2. Return `BLOCKED` status for the call.
3. Include remaining budget in the error message.
4. Do not retry automatically.

---

## 5. Audit Events

Every adapter call must produce a ShadowLogger entry BEFORE and AFTER:

### Pre-Call Event
```json
{
  "event_type": "adapter_call",
  "timestamp_utc": "<ISO timestamp>",
  "source": "DockerAdapter|FreqtradeAdapter|TelegramAdapter",
  "decision": "pending",
  "reason": "Intended call: {method}({args})",
  "adapter_name": "docker|freqtrade|telegram",
  "method": "method_name",
  "bot_id": "<if applicable>"
}
```

### Post-Call Event
```json
{
  "event_type": "adapter_call",
  "timestamp_utc": "<ISO timestamp>",
  "source": "DockerAdapter|FreqtradeAdapter|TelegramAdapter",
  "decision": "pass|fail",
  "reason": "{result summary or error}",
  "adapter_name": "docker|freqtrade|telegram",
  "method": "method_name",
  "duration_ms": "<elapsed milliseconds>",
  "call_budget_remaining": "<remaining calls for this window>"
}
```

### On Error
```json
{
  "event_type": "error",
  "timestamp_utc": "<ISO timestamp>",
  "source": "DockerAdapter|FreqtradeAdapter|TelegramAdapter",
  "decision": "fail",
  "reason": "{error message — NO SECRETS}",
  "adapter_name": "docker|freqtrade|telegram",
  "method": "method_name",
  "error_type": "{exception type}"
}
```

---

## 6. Container Evidence from Probe

The Phase M.2 probe confirmed the following container inventory relevant to
adapter contracts:

### Freqtrade Bots (read-config + trade-history targets)

| Bot ID | Container | Port | Image |
|--------|-----------|------|-------|
| `freqforge` | `trading-freqtrade-freqforge-1` | 8086 | `freqtradeorg/freqtrade:stable` |
| `regime-hybrid` | `trading-freqtrade-regime-hybrid-1` | 8085 | `freqtradeorg/freqtrade:stable` |
| `freqforge-canary` | `trading-freqtrade-freqforge-canary-1` | 8081 | `freqtradeorg/freqtrade:stable` |
| `freqai-rebel` | `trading-freqai-rebel-1` | 8087 | `freqtrade-freqai-rebel:custom` |

### Signal/Infrastructure (health-check targets)

| Container | Purpose | Health |
|-----------|---------|--------|
| `trading-ai-hedge-fund-1` | Signal generation | healthy |
| `trading-guardian` | RiskGuard authority | running |
| `trading-dashboard` | Dashboard UI | running |
| `btc5m-bot` | Polymarket bot | healthy |

---

## 7. Implementation Rules

### 7.1 When Real Adapters May Be Built

A real (non-stub) adapter MUST NOT be written unless ALL conditions in
[Real Adapter Design](./REAL_ADAPTER_DESIGN.md) §2 are met:

- [ ] `LIVE_FORBIDDEN` → `LIVE_APPROVED` state machine check exists
- [ ] The real adapter extends the existing Protocol
- [ ] Every method is wrapped with ShadowLogger audit
- [ ] Every method has a timeout (default: 30s)
- [ ] Every method has a call budget (max 60 calls/min)
- [ ] No retry for write-adjacent operations
- [ ] All Phase D tests pass on the target branch

### 7.2 Testing Requirements

- [ ] Each adapter method has at least one unit test
- [ ] Dry-run stubs return deterministic mock data
- [ ] Fail-closed behavior is tested (container missing, timeout, corrupt data)
- [ ] Call budget enforcement is tested
- [ ] Audit events are tested (before/after entries exist)
- [ ] No test calls real Docker, Freqtrade, or Telegram APIs

### 7.3 Secret Containment

- Adapter implementations must never: read `os.environ`, access `.env` files,
  or read secret-containing config keys.
- Adapter output must be scanned for secret patterns before logging.
- If a secret pattern is detected in output, the entire output is redacted
  and an escalation is triggered.

---

## 8. Related Documents

| Document | Location | Relationship |
|----------|----------|-------------|
| DockerAdapter Protocol | `src/si_v2/adapters/docker_adapter.py` | Existing interface |
| FreqtradeAdapter Protocol | `src/si_v2/adapters/freqtrade_adapter.py` | Existing interface |
| TelegramAdapter Protocol | `src/si_v2/adapters/telegram_adapter.py` | Existing interface |
| Dry-run stubs | `src/si_v2/adapters/dry_run_stub.py` | Current implementations |
| Real Adapter Design | `self_improvement_v2/docs/REAL_ADAPTER_DESIGN.md` | Preconditions for real adapters |
| Runtime Safety Contract | `docs/specs/runtime-safety-contract.md` | Fail-closed policy, audit events |
| Phase M.2 Probe Report | `reports/runtime_probe/phase-m2-dryrun-signal-validation-20260610-001/runtime_signal_validation_report.md` | Container evidence base |
| ADR: AI4Trade Integration | `self_improvement_v2/docs/ADR_AI4TRADE_INTEGRATION_BOUNDARY.md` | Integration boundary |
| Call Budget | `src/si_v2/adapters/call_budget.py` | Existing budget implementation |
