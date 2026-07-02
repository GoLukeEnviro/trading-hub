# Incident Response and Go-Live Runbooks

> **Status:** Draft · **B3** — required before live canary transition
> **Date:** 2026-07-02
> **Author:** SI v2 Meta-Orchestrator
> **Dependencies:** B1 (Live Readiness Audit), B2 (Production Risk Limits)

---

## Table of Contents

1. [Go-Live Checklist](#1-go-live-checklist)
2. [Emergency Stop Checklist](#2-emergency-stop-checklist)
3. [Live Rollback Checklist](#3-live-rollback-checklist)
4. [Exchange Incident Triage](#4-exchange-incident-triage)
5. [Alert Escalation Checklist](#5-alert-escalation-checklist)
6. [No-Live-Without-Approval Rule](#6-no-live-without-approval-rule)

---

## 1. Go-Live Checklist

Use this checklist **before** activating a live canary bot. Every item must be
verified and signed off.

### Pre-Flight

- [ ] **B1** — Live Readiness Evidence Audit passed (`LIVE_READINESS_PREP_READY`)
- [ ] **B2** — Production Risk Limits Spec exists and limits are configured
- [ ] **B3** — Incident Response Runbooks exist (this document)
- [ ] **B4** — Production Alerting Gate passes
- [ ] `APPROVED_LIVE_CANARY_TRANSITION` marker is present in a tracked file or issue comment
- [ ] Kill switch is `NORMAL` (not `HALT_NEW` or `EMERGENCY`)
- [ ] RiskGuard reports `PASS` for the target bot
- [ ] No active measurement window for this bot

### Configuration

- [ ] `config.json` sets `dry_run: false` (verified, not assumed)
- [ ] `config.json` sets `stake_amount: 500` (not `unlimited`)
- [ ] `config.json` sets `max_open_trades: 3`
- [ ] Exchange API key is a **read-only + trade-only** key (no withdraw)
- [ ] API key is scoped to a single trading pair or minimal pair list
- [ ] API key is stored in a tracked secrets file with restricted permissions (`0600`)
- [ ] API key is NOT hardcoded in any `.py` file, config committed to git, or log output
- [ ] API key is registered in the exchange's API key management with IP whitelist

### Connectivity

- [ ] Freqtrade can authenticate with the exchange (tested in dry-run mode with live key)
- [ ] Telegram alerting channel is configured and sending test messages
- [ ] Kill switch file path is writable by the bot's container
- [ ] Emergency stop script (`orchestrator/scripts/emergency_stop.sh`) exists and is executable
- [ ] Emergency stop script has been tested in dry-run mode

### Personnel

- [ ] At least one operator is on-call and reachable via Telegram
- [ ] Operator has the emergency stop script path and execution rights
- [ ] Operator can access the VPS host to run Docker commands if needed
- [ ] Incident response contact tree is documented and shared

### Final Sign-Off

- [ ] All pre-flight checks pass
- [ ] `APPROVED_EXECUTE_LIVE_CANARY` marker present
- [ ] Operator acknowledges readiness
- [ ] **Go decision recorded** in `docs/decisions/`

---

## 2. Emergency Stop Checklist

Use this checklist when the kill switch triggers `EMERGENCY` or an operator
decides to halt live trading manually.

### Immediate (within 5 minutes)

- [ ] **Verify kill switch state:** Check `freqtrade/shared/kill_switch.py` status
- [ ] **Confirm Telegram alert was sent** (if not, send one manually)
- [ ] **Stop live bot containers:**
  ```bash
  docker stop <live-bot-container-name>
  ```
- [ ] **Verify containers are stopped:**
  ```bash
  docker ps --filter name=<live-bot-container-name>
  ```
- [ ] **Write timestamped emergency record:**
  ```bash
  mkdir -p var/si_v2/emergency/
  echo '{"event":"emergency_stop","timestamp_utc":"<now>","trigger":"<reason>"}' \
    > var/si_v2/emergency/emergency_<timestamp>.json
  ```

### Short-Term (within 15 minutes)

- [ ] **If exchange breach suspected:** Rotate API key on exchange
- [ ] **Verify no open positions remain:**
  ```bash
  docker exec <live-bot-container> freqtrade status
  ```
- [ ] **If open positions exist:** Document position details (pair, size, entry price)
- [ ] **Notify all operators** via Telegram with the emergency summary

### Medium-Term (within 60 minutes)

- [ ] **File incident report** in `docs/incidents/incident-<YYYY-MM-DD>-<short-description>.md`
      containing:
  - Trigger event and timestamp
  - Kill switch state at time of trigger
  - All actions taken
  - Current bot/position state
  - Screenshots or logs if relevant
- [ ] **Assess whether to roll back** (see Section 3)

### Recovery (within 24 hours)

- [ ] **Root cause analysis** completed
- [ ] **Recovery plan** documented with explicit approval gates
- [ ] `APPROVED_RESUME_LIVE` token obtained before any live reactivation
- [ ] **Post-mortem** filed in `docs/incidents/`

---

## 3. Live Rollback Checklist

Use this checklist when a live canary bot must be returned to dry-run mode.

### Prerequisites

- [ ] Kill switch is `EMERGENCY` or operator has manually requested rollback
- [ ] Rollback plan exists (from Phase 5A rehearsal or manual plan)
- [ ] Rollback plan includes: pre-rollback snapshot path, rollback command,
      post-rollback proof path, audit path

### Execution

- [ ] **Take pre-rollback snapshot:**
  ```bash
  docker exec <live-bot-container> freqtrade trades > var/si_v2/rollback/pre_rollback_trades.json
  ```
- [ ] **Stop the live bot:**
  ```bash
  docker stop <live-bot-container>
  ```
- [ ] **Set `dry_run: true` in config.json** (restore pre-live config)
- [ ] **Restart the bot in dry-run mode:**
  ```bash
  docker start <live-bot-container>
  ```
- [ ] **Verify dry-run mode:**
  ```bash
  docker logs <live-bot-container> | grep "dry_run"
  ```

### Verification

- [ ] Bot reports `dry_run=true` in logs
- [ ] Bot is not placing live orders (verify via exchange API/UI)
- [ ] RiskGuard confirms dry-run status
- [ ] Kill switch set to `HALT_NEW` (prevent accidental re-activation)

### Documentation

- [ ] **Write rollback audit** in `var/si_v2/rollback/rollback_audit.json`
- [ ] **Write rollback effect proof** in `var/si_v2/rollback/rollback_effect_proof.json`
- [ ] **Update `docs/state/current-operational-state.md`** to reflect dry-run status
- [ ] **File incident report** if rollback was triggered by a problem

### Post-Rollback

- [ ] Measurement window starts (Phase 10.4 logic)
- [ ] Next iteration selector (Phase 10.6) considers this bot available again
- [ ] Human approval required for any future live transition

---

## 4. Exchange Incident Triage

Use this checklist when an exchange-related anomaly is detected.

### Classification

| Category | Examples | Severity |
|----------|----------|----------|
| **Connectivity** | API timeout, rate limit hit, WebSocket drop | 🟡 Medium |
| **Data** | Stale ticker, wrong OHLCV, missing pair | 🟡 Medium |
| **Order** | Order not filled, partial fill, unexpected reject | 🔴 High |
| **Account** | Balance mismatch, withdrawal restriction, API key error | 🔴 High |
| **Exchange-wide** | Maintenance, trading halt, delisting | 🔴 Critical |

### Triage Steps

1. **Check exchange status page** (e.g., status.bitget.com)
2. **Check Freqtrade logs** for exchange errors:
   ```bash
   docker logs <bot-container> 2>&1 | grep -i "exchange\|error\|timeout\|rate.limit"
   ```
3. **Check active orders** via exchange API/UI directly
4. **Check RiskGuard status** (`freqtrade/shared/kill_switch.py`)
5. **Classify severity** per table above

### By Severity

**🟡 Medium (Connectivity / Data):**
- Document in `docs/incidents/` as observation
- No immediate action required
- Re-check in 30 minutes
- If persists > 2 hours, escalate to 🔴

**🔴 High (Order / Account):**
- Trigger `HALT_NEW` kill switch
- Notify operator via Telegram immediately
- Investigate root cause within 60 minutes
- Do not resume until resolved

**🔴 Critical (Exchange-wide):**
- Trigger `EMERGENCY` kill switch
- Execute [Emergency Stop Checklist](#2-emergency-stop-checklist)
- Monitor exchange status page
- Do not resume until exchange confirms恢复正常 + 1 hour observation

---

## 5. Alert Escalation Checklist

### Alert Sources

| Source | Trigger | Initial Action |
|--------|---------|----------------|
| Kill switch | `HALT_NEW` or `EMERGENCY` set | Execute emergency or rollback checklist |
| RiskGuard | Limit breach (daily loss, drawdown, exposure) | Verify breach, execute emergency if drawdown |
| Freqtrade log error | Exchange error, trade error, config error | Investigate, classify, triage |
| Telegram manual | Operator observes anomaly | Investigate and document |
| Active Cycle | Missing cycle, stale evidence, fleet RED | Investigate scheduler/RiskGuard |

### Escalation Levels

| Level | Response Time | Actions |
|-------|---------------|---------|
| **L1 — Auto** | < 1 min | Kill switch auto-triggers. No human needed. |
| **L2 — Notify** | < 5 min | Telegram alert sent. Operator acknowledges. |
| **L3 — Investigate** | < 15 min | Operator investigates, classifies severity, documents findings. |
| **L4 — Respond** | < 30 min | Operator executes emergency/rollback checklist if required. |
| **L5 — Post-Mortem** | < 24 h | Root cause analysis, incident report, recovery plan. |

### Communication

| Channel | Purpose | Audience |
|---------|---------|----------|
| Telegram (private) | Auto-alerts from kill switch, RiskGuard, scheduler | Operator |
| Telegram (DM) | Manual escalation by operator | Operator + Backup |
| Incident file | Full documentation of all events | All (async) |

### Must-Respond Rules

- **EMERGENCY kill switch:** Must acknowledge within 5 minutes.
- **Daily loss limit breach:** Must acknowledge within 15 minutes.
- **HALT_NEW triggered:** Must acknowledge within 30 minutes.
- **Any 🔴 severity incident:** Must acknowledge within 15 minutes.
- **If no acknowledgment:** Escalate to backup operator via Telegram DM.

---

## 6. No-Live-Without-Approval Rule

This is a **hard, non-negotiable** operational rule:

> **No live trading may be initiated, resumed, or expanded without explicit,
> documented human approval.**

### What counts as "live trading"

- Setting `dry_run: false` on any bot
- Placing a real order on any exchange
- Deploying an exchange API key with trade permissions
- Activating a bot config that was previously in dry-run mode

### What counts as "explicit approval"

- An `APPROVED_*` token in a tracked file (`docs/decisions/` or issue comment)
  matching the scope of the action
- The token must be specific to the action (not a generic `APPROVED`)
- The token must have been issued within the last 7 days

### Violation handling

Any detected violation of this rule triggers:

1. **Immediate `EMERGENCY`** kill switch
2. **Mandatory incident report** within 60 minutes
3. **Mandatory post-mortem** within 24 hours
4. **Automatic rollback** to last known dry-run state
5. **Loss of live-trading privileges** until explicit human re-approval

### Exceptions

There are **no exceptions**. Every live action must have its own approval token.
A prior `APPROVED_LIVE_CANARY_TRANSITION` does not authorize a different bot's
transition. A prior `APPROVED_RESUME_LIVE` does not authorize a new bot.

---

## 7. Related Documents

| Document | Location |
|----------|----------|
| Production Risk Limits Spec | `docs/specs/production-risk-limits-spec.md` |
| Live Readiness Evidence Audit | `var/si_v2/live_readiness_audit/live_readiness_evidence_audit.md` |
| Production Alerting Gate | `docs/specs/production-alerting-gate.md` (B4) |
| Kill Switch Procedure | `docs/references/freqtrade-kill-switch-procedure.md` |
| Emergency Stop Script | `orchestrator/scripts/emergency_stop.sh` |
| Runtime Safety Contract | `docs/specs/runtime-safety-contract.md` |