# Live-Readiness Blocker Inventory

> **SI v2 — Blocker Inventory for Live Trading Readiness**
>
> **Live trading is strictly prohibited.**
> This document lists all blockers and prerequisites that must be
> resolved before any live-readiness assessment can begin.

---

## 1. Hard Blockers (Must Be Resolved Before Any Live Consideration)

| # | Blocker | Area | Description |
|---|---------|------|-------------|
| B-01 | **No live trading approval** | Governance | No human approval token has been issued for live trading. The system stays in `LIVE_FORBIDDEN` state. |
| B-02 | **No live exchange credentials** | Security | No exchange API keys, secrets, or live exchange configuration exists in the project. Dry-run only. |
| B-03 | **No live Freqtrade config** | Deployment | All Freqtrade bots operate in `dry_run=true`. There is no production config. |
| B-04 | **No Telegram bot token configured** | Safety | Telegram integration is explicitly disabled. No bot token is available in config. |
| B-05 | **Controlled dry-run rehearsal not performed** | Process | The controlled dry-run rehearsal (#125) must be completed before any live-readiness discussion. |
| B-06 | **No live-readiness assessment run** | Governance | A formal live-readiness assessment has not been performed. No report exists. |
| B-07 | **Human approval gate not signed** | Governance | The human approval gate checklist (#122) has not been signed off. |

## 2. Required Offline Artifacts (Must Exist Before Live Consideration)

| # | Artifact | Status | Reference |
|---|----------|--------|-----------|
| A-01 | CI smoke workflow passing | ☐ | #120 |
| A-02 | Failure taxonomy defined | ☐ | #121 |
| A-03 | Human approval gate checklist signed | ☐ | #122 |
| A-04 | Phase 1 readiness verdict GREEN or YELLOW | ☐ | #117 |
| A-05 | Quality gate verdict GREEN | ☐ | #112 |
| A-06 | All pipeline tests passing | ☐ | #120 |
| A-07 | Offline episode runs without RED | ☐ | #97 |
| A-08 | Controlled dry-run rehearsal completed | ☐ | #125 |
| A-09 | Runtime preflight completed | ☐ | #129 (upcoming) |
| A-10 | External adapter boundary audit completed | ☐ | #131 (upcoming) |

## 3. Required Dry-Run Evidence (Must Be Collected Before Live Consideration)

| # | Evidence | Required By |
|---|----------|-------------|
| E-01 | All Freqtrade bots confirmed in `dry_run=true` | Pre-rehearsal |
| E-02 | No `dry_run=false` in any config file | Pre-rehearsal |
| E-03 | No exchange API calls observed in dry-run logs | Rehearsal |
| E-04 | No outbound Telegram calls observed | Rehearsal |
| E-05 | RiskGuard override function verified in dry-run | Rehearsal |
| E-06 | ShadowLogger audit trail captured | Rehearsal |
| E-07 | Rehearsal stop conditions not triggered | Rehearsal |
| E-08 | Rollback procedure tested | Rehearsal |

## 4. Manual Approval Blockers

| # | Approval Requirement | Minimum Approver |
|---|---------------------|------------------|
| M-01 | Controlled dry-run rehearsal | Repository owner |
| M-02 | Read-only runtime probe | Repository owner |
| M-03 | Live-readiness assessment | Repository owner + second reviewer |
| M-04 | Live trading enablement | **Not approved at any phase** without separate explicit written approval |

## 5. Explicit No-Go States

If **any** of the following is true, live-readiness is **BLOCKED**:

- [ ] `dry_run=false` detected in any bot or config
- [ ] Real exchange credentials present in any config file
- [ ] Telegram bot token configured in any bot
- [ ] Live orders detected in any exchange account
- [ ] Human approval gate not signed
- [ ] Controlled dry-run rehearsal not completed
- [ ] Pipeline tests not all green
- [ ] Phase 1 readiness verdict is RED

## 6. Live-Trading Prohibition Statement

> **Live trading, real orders, real exchange API keys, real Telegram
> tokens, real wallet addresses, and any form of financial exposure
> are strictly prohibited at this phase.**
>
> The system remains in `LIVE_FORBIDDEN` state.
> No code change in this repository can enable live mode without
> bypassing multiple explicit safety gates.

---

*Inventory maintained at `self_improvement_v2/governance/live_readiness_blocker_inventory.md`*
*Created as part of #124 — Live-Readiness Blocker Inventory*
