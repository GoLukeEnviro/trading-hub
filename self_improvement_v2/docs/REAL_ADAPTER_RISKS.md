# Real Adapter Risk Analysis — SI v2 Phase E

> **Design Review — NO code implementation in this phase.**
> This document catalogues every risk associated with switching from
> `DryRunStub*` to real Docker/Freqtrade/Telegram adapters.

---

## 1. Risk Summary

| # | Risk | Likelihood | Impact | Overall | Mitigation | Residual |
|---|------|-----------|--------|---------|------------|----------|
| R1 | Network exposure | Low | Critical | High | ACLs, timeouts, budget | Low |
| R2 | Credential exposure | Low | Critical | High | Secret store, no hardcode | Low |
| R3 | Docker socket abuse | Low | Critical | High | Read-only Protocol, audit | Low |
| R4 | Rate limit cascade | Medium | High | High | Call budget, queue | Medium |
| R5 | State corruption | Low | Critical | High | Fail-closed, no write | Low |
| R6 | Live trading risk amplification | Low | Critical | High | proposal_only lock | Low |
| R7 | Backtest resource exhaustion | Medium | Medium | Medium | Timeout, 0 retry | Low |
| R8 | Approval message loss | Medium | Low | Low | Retry + queue | Low |
| R9 | Config divergence | Low | High | Medium | Snapshot + rollback | Low |
| R10 | Undetected adapter failure | Low | Medium | Low | Health check, audit log | Low |

---

## 2. Detailed Risk Analysis

### R1: Network Exposure

**Description:** Real adapters make network calls (Docker socket, Telegram API).
A compromised or misconfigured adapter could leak internal network topology.

**Likelihood:** Low (adapters make specific, bounded calls)
**Impact:** Critical (internal network access)

**Mitigations:**
- Docker socket ACLs (read-only user)
- Telegram API only to `api.telegram.org`
- No SSH, no database, no exchange connections from adapters
- All calls have bounded timeouts (30s default)

**Residual Risk:** Low

### R2: Credential Exposure

**Description:** Telegram bot token, Docker socket path, or other secrets
could be logged, printed, or leaked.

**Likelihood:** Low (no current secret handling in adapters)
**Impact:** Critical (bot token compromise → message spoofing)

**Mitigations:**
- Secrets NEVER in source code
- Secrets stored in Hermes profile config (encrypted at rest)
- Audit log REDACTs sensitive fields
- `RealTelegramAdapter` refuses to start without `SI_V2_ENABLE_REAL_ADAPTERS=1`

**Residual Risk:** Low

### R3: Docker Socket Abuse

**Description:** The Docker adapter could be used to execute arbitrary
commands inside trading containers.

**Likelihood:** Low (Protocol enforces read-only signature)
**Impact:** Critical (container escape, trade manipulation)

**Mitigations:**
- Protocol only has `exec_readonly`, `container_is_running`, `get_container_ip`
- No `exec_write`, `restart`, `stop`, `start` in Protocol
- Adapter validates command prefix (e.g., only `freqtrade ...`)
- Audit log records every command

**Residual Risk:** Low

### R4: Rate Limit Cascade

**Description:** Real adapters could hit Telegram API rate limits or
Docker socket connection limits during backtest bursts.

**Likelihood:** Medium (multiple bots × multiple phases × approvals)
**Impact:** High (delayed approvals, silent pipeline failures)

**Mitigations:**
- Call budget: max 60 calls/min per adapter
- Queued Telegram messages (batch send)
- Exponential backoff for Telegram retries
- Pipeline continues without approval if Telegram unavailable

**Residual Risk:** Medium

### R5: State Corruption

**Description:** A real adapter could accidentally modify Freqtrade state
(e.g., by running a backtest that writes to the live database).

**Likelihood:** Low (`run_backtest` does not modify live DB)
**Impact:** Critical (backtest overlay could corrupt config)

**Mitigations:**
- Backtest uses `--datadir` flag pointing to non-live data
- Backtest overlay is a temporary file, not live config
- No write operations exist in any Protocol
- `proposal_only` mode prevents config writes

**Residual Risk:** Low

### R6: Live Trading Risk Amplification

**Description:** If the SI v2 pipeline is paired with a live Freqtrade
instance, any adapter error could cascade to live trading.

**Likelihood:** Low (system is `proposal_only` by default)
**Impact:** Critical (real financial loss)

**Mitigations:**
- Runtime check: real adapters refuse to run unless mode is NOT `proposal_only`
- Human approval required for mode changes
- Shadow mode observation window (72h) before any live deployment

**Residual Risk:** Low

### R7: Backtest Resource Exhaustion

**Description:** Running backtests via `docker exec` on every mutation
candidate could consume container CPU/memory and starve the live bot.

**Likelihood:** Medium (concurrent backtests possible)
**Impact:** Medium (degraded live performance)

**Mitigations:**
- Maximum 1 concurrent backtest per bot
- Backtest timeout: 120s (killed if exceeded)
- 0 retries for backtest (no duplicate resource consumption)
- Cooldown between backtests (30s minimum)

**Residual Risk:** Low

### R8: Approval Message Loss

**Description:** Telegram messages could be lost due to network issues or
API rate limits, causing human approval to never reach the system.

**Likelihood:** Medium (Telegram API reliability)
**Impact:** Low (pipeline pauses, no harm)

**Mitigations:**
- Retry with exponential backoff (3 attempts)
- Approval status persisted in ShadowLogger
- Manual recovery possible via cron or CLI
- Pipeline stays in `pending_approval` until explicitly resolved

**Residual Risk:** Low

### R9: Config Divergence

**Description:** The config snapshot taken by `RollbackPlanManager` may
diverge from the actual live config if the bot is restarted or manually
configured between snapshot and rollback.

**Likelihood:** Low (snapshot is taken immediately before change)
**Impact:** High (rollback would restore stale config)

**Mitigations:**
- Snapshot timestamp recorded in every entry
- Rollback validates config hash before applying
- Manual verification required for rollback in Phase D

**Residual Risk:** Medium

### R10: Undetected Adapter Failure

**Description:** A real adapter could fail silently (returning default
values) without the pipeline noticing.

**Likelihood:** Low (tests verify non-default returns)
**Impact:** Medium (incorrect backtest results)

**Mitigations:**
- Every adapter method returns typed, validated schemas
- `BacktestRunner` uses pass criteria to reject bad results
- Audit log records success/failure per call
- Pipeline health check compares real vs expected call patterns

**Residual Risk:** Low

---

## 3. Go/No-Go Checklist

Before switching from `DryRunStub*` to real adapters:

| # | Check | Status |
|---|-------|--------|
| 1 | All 178+ Phase D tests pass | ☐ |
| 2 | System in `proposal_only` mode | ☐ |
| 3 | Docker socket accessible (health check) | ☐ |
| 4 | Freqtrade containers running (health check) | ☐ |
| 5 | Telegram bot token in Hermes secret store | ☐ |
| 6 | `SI_V2_ENABLE_REAL_ADAPTERS=1` documented | ☐ |
| 7 | Human approval in GitHub Issue | ☐ |
| 8 | Rollback plan documented for all 3 adapters | ☐ |
| 9 | Audit log path writable | ☐ |
| 10 | Call budget configured (default: 60/min) | ☐ |

> **Rule:** All 10 checks must pass before ANY real adapter is instantiated.

---

## 4. Escalation Triggers

Escalate immediately to human operator if:

1. **Any real adapter returns unexpected data** (e.g., backtest result
   with negative trades count)
2. **Docker socket unavailable** for more than 3 consecutive checks
3. **Telegram API returns 401** (token invalid or revoked)
4. **Call budget exceeded** repeatedly
5. **Audit log write fails** (silent operation without logging)
6. **Any exception in a real adapter method** that is not caught by the
   fail-closed handler