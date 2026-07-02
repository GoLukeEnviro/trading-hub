# Production Risk Limits Specification

> **Status:** Draft · **B2** — required before live canary transition
> **Date:** 2026-07-02
> **Author:** SI v2 Meta-Orchestrator
> **Dependencies:** B1 — Live Readiness Evidence Audit (complete)

---

## Purpose

Define **hard, non-negotiable live-risk limits** that must be configured and
verified before any exchange key activation. These limits apply to the live
canary bot and, by extension, any subsequent fleet bot that transitions to live
mode.

These limits are **not optional**. No live order may be placed unless every
limit below is configured, tested in dry-run, and verified by the
Production Alerting Gate (B4).

---

## 1. Max Capital per Bot

| Property | Value | Rationale |
|----------|-------|-----------|
| **Max stake per bot (USD)** | **500 USDT** | Initial live canary exposes minimal capital. Increased only after C4 measurement KEEP decision. |
| **Max total fleet capital (USD)** | **2,000 USDT** | Aggregate across all 4 bots. No single bot may exceed its per-bot cap. |
| **Unit** | `USDT` | Stablecoin only. No volatile-denominated capital. |

**Enforcement:**
- `config.json` → `stake_amount` must be set to the numeric cap (not `unlimited`).
- Fleet-level cap is enforced by RiskGuard portfolio guard.

**Override:** Only via explicit `APPROVED_CAPITAL_INCREASE` token + B4 gate bypass.

---

## 2. Max Open Trades per Bot

| Property | Value | Rationale |
|----------|-------|-----------|
| **Max open trades per bot** | **3** | Conservative for live canary. Matches baseline strategy. |
| **Max open trades fleet-wide** | **12** | 4 bots × 3 trades. Prevents runaway exposure. |

**Enforcement:**
- `config.json` → `max_open_trades` must be set.
- Freqtrade natively enforces per-bot limit.
- Fleet-wide enforcement via RiskGuard periodic scan.

**Override:** Only via explicit `APPROVED_MAX_OPEN_TRADES_INCREASE` token.

---

## 3. Max Daily Loss

| Property | Value | Rationale |
|----------|-------|-----------|
| **Max daily loss per bot (USD)** | **50 USDT** | 10% of per-bot capital. Limits single-day damage. |
| **Max daily loss fleet-wide (USD)** | **200 USDT** | 10% of fleet capital. Hard stop if aggregate exceeds. |

**Enforcement:**
- RiskGuard daily loss counter resets at 00:00 UTC.
- If any bot exceeds its daily loss limit → `HALT_NEW` kill switch is triggered fleet-wide.
- If fleet aggregate exceeds limit → `EMERGENCY` kill switch is triggered.

**Override:** Manual only. Requires explicit `APPROVED_DAILY_LOSS_OVERRIDE` token
and documented incident reason. Override auto-expires at next UTC midnight.

---

## 4. Max Notional Exposure

| Property | Value | Rationale |
|----------|-------|-----------|
| **Max notional exposure per position (USD)** | **200 USDT** | ~40% of per-bot capital per position. |
| **Max notional exposure per bot (USD)** | **500 USDT** | Full per-bot capital. |
| **Max notional exposure fleet-wide (USD)** | **2,000 USDT** | Full fleet capital. |

**Enforcement:**
- RiskGuard calculates notional as `entry_price × amount` for each open position.
- Position-level limit is enforced before entry.
- Bot-level and fleet-level limits are enforced via periodic scan.
- Positions exceeding limits trigger `HALT_NEW`.

**Override:** Not available for position-level limit. Bot/fleet overrides require
`APPROVED_EXPOSURE_INCREASE` token.

---

## 5. Max Drawdown Kill-Switch

| Property | Value | Rationale |
|----------|-------|-----------|
| **Max drawdown per bot (%)** | **15%** | Relative to bot's peak portfolio value since live activation. |
| **Max drawdown fleet-wide (%)** | **10%** | Relative to aggregate peak. Fleet drawdown is tighter. |
| **Action on breach** | **EMERGENCY kill switch** | All live trading stops immediately. |
| **Recovery** | Manual only | Requires incident review and explicit `APPROVED_RESUME_LIVE` token. |

**Enforcement:**
- RiskGuard tracks per-bot and fleet-wide peak portfolio value.
- Drawdown = (peak − current) / peak.
- Checked on every completed trade and at minimum every 60 minutes.
- Breach triggers file-based kill switch (`freqtrade/shared/kill_switch.py` → `EMERGENCY`).
- `EMERGENCY` cannot be reset to `NORMAL` without human approval.

**Override:** Not available. EMERGENCY is the hard stop.

---

## 6. Emergency Stop Procedure

| Step | Action | Responsible | Time Target |
|------|--------|-------------|-------------|
| **1** | Kill switch automatically triggers `EMERGENCY` on drawdown breach | RiskGuard | < 1 min |
| **2** | Telegram alert sent to operator | Alerting Gate (B4) | < 1 min |
| **3** | All live bots `docker stop` executed via emergency script | Operator | < 5 min |
| **4** | Exchange API keys rotated (if breach suspected) | Operator | < 15 min |
| **5** | Incident report filed in `docs/incidents/` | Operator | < 60 min |
| **6** | Root cause analysis completed | Operator + Hermes | < 24 h |
| **7** | Recovery plan approved with explicit `APPROVED_RESUME_LIVE` | Human | After RCA |

**Emergency stop script location:**
```text
orchestrator/scripts/emergency_stop.sh
```

The emergency stop script must:
- Read the live canary bot ID from a tracked config file.
- Execute `docker stop <container>` for each live bot.
- Write a timestamped audit record to `var/si_v2/emergency/`.
- Not delete any data, configs, or databases.
- Not require any external credentials.

**Precondition:** The script must be tested in dry-run mode (against stopped
containers or non-production environment) before live activation.

---

## 7. Manual Approval Points

The following actions require **explicit human approval** via a documented
approval token in the format `APPROVED_<ACTION>_<SCOPE>`:

| # | Action | Token Pattern | Required Before |
|---|--------|---------------|-----------------|
| 1 | Live canary activation | `APPROVED_LIVE_CANARY_TRANSITION` | C1 gate |
| 2 | Live canary execution | `APPROVED_EXECUTE_LIVE_CANARY` | C3 ceremony |
| 3 | Capital increase per bot | `APPROVED_CAPITAL_INCREASE_<BOT_ID>` | Config change |
| 4 | Max open trades increase | `APPROVED_MAX_OPEN_TRADES_INCREASE` | Config change |
| 5 | Daily loss override | `APPROVED_DAILY_LOSS_OVERRIDE` | Before override use |
| 6 | Exposure increase | `APPROVED_EXPOSURE_INCREASE` | Config change |
| 7 | Resume after EMERGENCY | `APPROVED_RESUME_LIVE` | After RCA |
| 8 | Fleet rollout to next bot | `APPROVED_LIVE_FLEET_ROLLOUT` | D1 gate |

**Rules:**
- Each token is scope-specific. A generic `APPROVED` is never sufficient.
- Tokens must appear in a tracked file (`docs/decisions/` or issue comment)
  before the gated action may proceed.
- Tokens expire 7 days after issuance unless renewed.
- Token issuance must be logged in ShadowLogger.

---

## 8. Compliance Matrix

| Limit | Config Key | Hard Gate | Override Available | Override Token Required |
|-------|-----------|-----------|-------------------|------------------------|
| Max capital per bot | `stake_amount` | ✅ RiskGuard | ✅ | `APPROVED_CAPITAL_INCREASE` |
| Max open trades | `max_open_trades` | ✅ Freqtrade native | ✅ | `APPROVED_MAX_OPEN_TRADES_INCREASE` |
| Max daily loss (bot) | — | ✅ RiskGuard | ✅ | `APPROVED_DAILY_LOSS_OVERRIDE` |
| Max daily loss (fleet) | — | ✅ RiskGuard | ❌ | — |
| Max notional per position | — | ✅ RiskGuard | ❌ | — |
| Max notional per bot | — | ✅ RiskGuard | ✅ | `APPROVED_EXPOSURE_INCREASE` |
| Max notional fleet | — | ✅ RiskGuard | ✅ | `APPROVED_EXPOSURE_INCREASE` |
| Max drawdown per bot | — | ✅ Kill switch | ❌ | — |
| Max drawdown fleet | — | ✅ Kill switch | ❌ | — |

---

## 9. Migration Path

When a bot transitions from dry-run to live:

1. **Pre-activation:** All limits in this document are configured in the bot's
   `config.json` and verified by the Production Alerting Gate (B4).
2. **At activation:** RiskGuard validates limits on the first live trade.
3. **Post-activation:** RiskGuard enforces limits continuously via periodic scan
   and trade-completion hooks.
4. **On limit breach:** Kill switch activates per the severity table above.

---

## 10. Related Documents

| Document | Location |
|----------|----------|
| Runtime Safety Contract | `docs/specs/runtime-safety-contract.md` |
| Live Readiness Evidence Audit | `var/si_v2/live_readiness_audit/live_readiness_evidence_audit.md` |
| Incident Response Runbooks | `docs/specs/incident-response-runbooks.md` (B3) |
| Production Alerting Gate | `docs/specs/production-alerting-gate.md` (B4) |
| Kill Switch Procedure | `docs/references/freqtrade-kill-switch-procedure.md` |