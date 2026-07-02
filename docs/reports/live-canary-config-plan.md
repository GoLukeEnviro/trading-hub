# Live Canary Config Plan

> **Status:** Draft · **C2** — required before live canary activation
> **Date:** 2026-07-02
> **Author:** SI v2 Meta-Orchestrator
> **Dependencies:** C1 — Human Approval Gate for Live Canary (complete)

---

## Purpose

This document defines the **planned config deltas** for transitioning the canary bot from dry-run to live mode. It is a **plan-only document** — no config changes are applied by this phase.

The plan selects exactly one canary target, documents every config delta, defines exchange-key boundaries, references B2 risk limits and B4 alerting gate, provides rollback references, and defines the measurement window for post-activation evaluation.

---

## Canary Target

| Property | Value |
|----------|-------|
| **Bot ID** | `freqtrade-freqforge-canary` |
| **Container** | `freqtrade-freqforge-canary` |
| **Strategy** | `FreqForge_Override` |
| **Exchange** | Bitget (futures, isolated margin) |
| **Current mode** | Dry-run |
| **Planned mode** | Live (after C3 activation ceremony) |

**Rationale:** The canary bot is the smallest, most conservative bot in the fleet. It has a proven dry-run track record, isolated pair set, and is the designated canary for live rollout per the deployment runbook.

---

## Prerequisites

| # | Prerequisite | Status | Evidence |
|---|--------------|--------|----------|
| 1 | C1 — Human Approval Gate | ✅ READY | `var/si_v2/live_canary_approval_gate/live_canary_approval_gate.json` |
| 2 | B2 — Production Risk Limits Spec | ✅ Exists | `docs/specs/production-risk-limits-spec.md` |
| 3 | B4 — Production Alerting Readiness Gate | ✅ Exists | `docs/reports/production-alerting-readiness-gate.md` |
| 4 | Rollback references | ✅ Exists | Deployment runbook, kill switch runbook, incident response runbook |
| 5 | No live config applied | ✅ Confirmed | No `config_canary_live.json` exists |

---

## Planned Config Deltas

The following changes are **documented but not applied**. They represent the planned delta between dry-run and live mode.

### dry_run

| Property | Value |
|----------|-------|
| **Current** | `true` |
| **Planned** | `false` |
| **Config key** | `dry_run` |
| **Config file** | `freqforge-canary/config/config_canary_dryrun.json` |
| **New config file** | `freqforge-canary/config/config_canary_live.json` |

**Notes:** A new config file `config_canary_live.json` will be created as a copy of `config_canary_dryrun.json` with `dry_run` set to `false`. The dry-run config is preserved for rollback.

### stake_amount

| Property | Value |
|----------|-------|
| **Current** | `25.0` |
| **Planned** | `25.0` (unchanged) |
| **Config key** | `stake_amount` |

**Notes:** Stake amount remains at 25 USDT per trade. This is within the B2 risk limit of 500 USDT max per bot and 200 USDT max notional per position.

### max_open_trades

| Property | Value |
|----------|-------|
| **Current** | `3` |
| **Planned** | `3` (unchanged) |
| **Config key** | `max_open_trades` |

**Notes:** Max open trades remains at 3. This is within the B2 risk limit of 3 max open trades per bot.

### dry_run_wallet

| Property | Value |
|----------|-------|
| **Current** | `500` |
| **Planned** | Removed |
| **Config key** | `dry_run_wallet` |

**Notes:** The `dry_run_wallet` field is removed in live mode. Real exchange balance is used instead. B2 risk limit caps live capital at 500 USDT per bot.

### exchange_api

| Property | Value |
|----------|-------|
| **Current** | No API keys (dry-run) |
| **Planned** | Bitget API keys required |
| **Config key** | `exchange.key` |

**Notes:** Live mode requires Bitget API keys with read-only and trade permissions. Keys are configured via environment variables or Freqtrade exchange sandbox. API keys are NEVER stored in config files. Exchange key boundaries: only Bitget spot/futures, only whitelisted pairs, no withdrawal permissions.

### db_url

| Property | Value |
|----------|-------|
| **Current** | `sqlite:////freqtrade/user_data/tradesv3.freqforge_canary.dryrun.sqlite` |
| **Planned** | `sqlite:////freqtrade/user_data/tradesv3.freqforge_canary.live.sqlite` |
| **Config key** | `db_url` |

**Notes:** A new live database file is used to keep dry-run trade history intact for comparison. The dry-run DB is preserved for rollback and post-mortem analysis.

### stoploss

| Property | Value |
|----------|-------|
| **Current** | `-0.09` |
| **Planned** | `-0.09` (unchanged) |
| **Config key** | `stoploss` |

**Notes:** Stoploss remains at -9%. This is within the B2 risk limit of 15% max drawdown per bot.

---

## Exchange Key Boundaries

| Property | Value |
|----------|-------|
| **Exchange** | Bitget |
| **Required permissions** | read_only (balance, orders, positions), trade (place, cancel, modify orders) |
| **Forbidden permissions** | withdraw, transfer, api_key_management |
| **Key storage** | Environment variables (`FREQTRADE__EXCHANGE__KEY` and `FREQTRADE__EXCHANGE__SECRET`) or Freqtrade exchange sandbox. Keys are NEVER stored in config files or version control. |
| **Key rotation** | API keys should be rotated before live activation and after any security incident. Rotation is a manual operator action. |
| **IP restriction** | Bitget API keys should be restricted to the trading server IP address where possible. |
| **Max capital per bot** | 500 USDT |
| **Whitelisted pairs** | BTC/USDT:USDT, ETH/USDT:USDT, SOL/USDT:USDT, LINK/USDT:USDT, DOT/USDT:USDT, ATOM/USDT:USDT, UNI/USDT:USDT, AAVE/USDT:USDT |

---

## B2 Risk Limits

| Limit | Value |
|-------|-------|
| **Document** | `docs/specs/production-risk-limits-spec.md` |
| **Max capital per bot** | 500 USDT |
| **Max open trades per bot** | 3 |
| **Max daily loss per bot** | 50 USDT |
| **Max notional per position** | 200 USDT |
| **Max drawdown per bot** | 15% |
| **Max drawdown fleet** | 10% |
| **Kill switch on drawdown breach** | EMERGENCY |

---

## B4 Alerting Gate

| Property | Value |
|----------|-------|
| **Document** | `docs/reports/production-alerting-readiness-gate.md` |
| **Required status** | `PRODUCTION_ALERTING_READY` |
| **Checks** | alert_config_evidence, delivery_proof, drawdown_alert_proof, runtime_failure_alert_proof |

---

## Rollback References

| Document | Path |
|----------|------|
| **Deployment runbook** | `docs/context/freqforge-canary-deployment-runbook.md` |
| **Kill switch runbook** | `docs/runbooks/kill-switch.md` |
| **Incident response runbook** | `docs/specs/incident-response-runbooks.md` |

### Rollback Steps

1. Activate kill switch: EMERGENCY mode to halt all trading
2. Stop canary container: `docker stop freqtrade-freqforge-canary`
3. Remove canary container: `docker rm freqtrade-freqforge-canary`
4. Restore dry-run config: use preserved `config_canary_dryrun.json`
5. Restart in dry-run mode: `docker compose up -d freqtrade-freqforge-canary`
6. Verify dry-run operation: check logs, DB, and API health
7. File incident report in `docs/incidents/`

**Precondition:** The dry-run config file (`config_canary_dryrun.json`) must be preserved and unmodified. The dry-run database must be preserved.

---

## Measurement Window

| Property | Value |
|----------|-------|
| **Duration** | 14 days |
| **Comparison baseline** | Dry-run performance from preceding 14 days |
| **Evaluation gate** | C4 — Live Canary Measurement and Decision |
| **Decision outcomes** | KEEP, EXTEND, ROLLBACK |

### Metrics

- total_trades
- win_rate
- profit_factor
- sharpe_ratio
- max_drawdown
- avg_profit_per_trade
- daily_loss
- notional_exposure

---

## Integration

```
C1 Human Approval Gate for Live Canary
  → C2 Live Canary Config Plan, No Activation  ← YOU ARE HERE
    → C3 Live Canary Activation Ceremony
      → C4 Live Canary Measurement and Decision
```

---

## Related Documents

| Document | Location |
|----------|----------|
| Live Canary Config Plan module | `self_improvement_v2/src/si_v2/live/live_canary_config_plan.py` |
| Live Canary Config Plan tests | `self_improvement_v2/tests/test_live_canary_config_plan.py` |
| Live Canary Approval Gate | `self_improvement_v2/src/si_v2/live/live_canary_approval_gate.py` |
| Production Risk Limits Spec | `docs/specs/production-risk-limits-spec.md` |
| Production Alerting Readiness Gate | `docs/reports/production-alerting-readiness-gate.md` |
| FreqForge-Canary Deployment Runbook | `docs/context/freqforge-canary-deployment-runbook.md` |
| Kill-Switch Runbook | `docs/runbooks/kill-switch.md` |
| Incident Response Runbooks | `docs/specs/incident-response-runbooks.md` |
