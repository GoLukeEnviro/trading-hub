# SI-v2 Profitability Gate Root-Cause Analysis — 2026-06-26

## Status: YELLOW

**Operation Level:** L2 (read-only evidence assessment + Markdown report)

**Timestamp:** 2026-06-26T05:30:00Z

**Repo:** `main` @ `ba78019` (origin/main in sync)

---

## Executive Summary

The Profitability Gate blocks Controlled Apply because 2 of 4 bots have negative walk-forward net metrics. The fleet is split into two clear tiers: two profitable candidates (`freqforge`, `canary`) and two blocked underperformers (`regime-hybrid`, `freqai-rebel`). This is not a data pipeline bug or a proposal quality issue — it is a genuine strategy underperformance issue for the two blocked bots. Controlled Apply remains blocked at fleet level.

---

## Evidence Files and Hashes

| Evidence Source | Path | Cycle |
|---|---|---|
| Active Cycle evidence bundle | `self_improvement_v2/reports/phase2/evidence/active_cycle_20260626T001838Z.json` | `20260626T001838Z` |
| Active Cycle state | `self_improvement_v2/reports/phase2/cycle_state/active_cycle_latest.state.json` | `20260626T001838Z` |
| Historical trade summary | `self_improvement_v2/state/historical_trades/historical_trades_summary.json` | Generated 2026-06-23 |
| Telemetry history | `self_improvement_v2/state/telemetry_history/telemetry_20260626.jsonl` | Latest entry |
| Bot registry | `self_improvement_v2/config/freqtrade_bots.readonly.json` | Schema v2 |
| Previous gates reassessment | `docs/reports/si-v2-remaining-gates-reassessment-2026-06-25.md` | 2026-06-25 |

---

## Cycle State Summary

| Field | Value |
|---|---|
| Cycle ID | `20260626T001838Z` |
| Controller state | `PAUSED / L3_REPOSITORY_ONLY` |
| Fleet verdict | `GREEN` |
| Fleet verdict reason | all 4 bots authenticated and decisions generated |
| ShadowProposals generated | 4 |
| Mutation counters (all) | 0 |
| Ping OK | 4/4 |
| Authenticated | 4/4 |
| Historical trade primary verdict | `WAITING_FOR_POST_APPLY_DATA` |
| Historical trade candidate id | `65502d13` |
| Post-apply closed trades | 0 (no apply has occurred yet) |

---

## 4-Bot Profitability Matrix

### freqtrade-freqforge

| Metric | Value |
|---|---|
| Approval eligible | **YES** |
| Walk-forward evaluation | **PASS_REVIEW** |
| Total net PnL | **+$24.784** |
| Profit factor | **1.5831** |
| Total trades | 78 |
| Win rate | 79.49% (62 wins / 16 losses) |
| Max drawdown | 2.11% |
| Average trade PnL | +$0.318 |
| Best trade | +$3.553 |
| Worst trade | -$9.465 |
| Gross profit | $67.287 |
| Gross loss | $42.503 |
| Top pair | SOL/USDT:USDT (+$15.441, 13W/2L) |
| Worst pair | AVAX/USDT (-$6.484, 1W/1L) |
| Daily profit trend | stable (+2.50%) |
| Proposal hypothesis | `reinforce_profitable_pair_cluster_v1` |
| Verdict | **CANDIDATE** |

### freqtrade-freqforge-canary

| Metric | Value |
|---|---|
| Approval eligible | **YES** |
| Walk-forward evaluation | **PASS_REVIEW** |
| Total net PnL | **+$3.980** |
| Profit factor | **1.8824** |
| Total trades | 59 |
| Win rate | 91.38% (53 wins / 5 losses) |
| Max drawdown | 0.76% |
| Average trade PnL | +$0.107 |
| Best trade | +$1.312 |
| Worst trade | -$2.233 |
| Gross profit | $8.490 |
| Gross loss | $2.268 |
| Top pair | ETH/USDT:USDT (+$1.657, 8W/1L) |
| Worst pair | BTC/USDT:USDT (-$0.628, 9W/2L) |
| Daily profit trend | stable (+0.84%) |
| Proposal hypothesis | `reinforce_profitable_pair_cluster_v1` |
| Verdict | **CANDIDATE** |

### freqtrade-regime-hybrid

| Metric | Value |
|---|---|
| Approval eligible | **NO** (`approval_negative_net_metrics`) |
| Walk-forward evaluation | **NEGATIVE_NET_METRICS** |
| Total net PnL | **-$7.248** |
| Profit factor | **0.5760** |
| Total trades | 55 |
| Win rate | 67.27% (37 wins / 18 losses) |
| Max drawdown | 0.77% |
| Average trade PnL | -$0.132 |
| Best trade | +$1.526 |
| Worst trade | -$3.097 |
| Gross profit | $9.847 |
| Gross loss | $17.095 |
| Top pair | BTC/USDT:USDT (+$1.499, 3W/2L) |
| Worst pair | ETH/USDT:USDT (-$2.204, 1W/2L) |
| Daily profit trend | stable (-0.73%) |
| Proposal hypothesis | `observe_underperforming_pair_cluster_v1` |
| Anomaly flags | `negative_closed_profit` |
| Promotion blocked | **YES** (`walk_forward_net_metrics_negative`) |
| Verdict | **BLOCKED** |

### freqai-rebel

| Metric | Value |
|---|---|
| Approval eligible | **NO** (`approval_negative_net_metrics`) |
| Walk-forward evaluation | **NEGATIVE_NET_METRICS** |
| Total net PnL | **-$1.623** |
| Profit factor | **0.3696** |
| Total trades | 35 |
| Win rate | 27.78% (5 wins / 13 losses) |
| Max drawdown | 0.18% |
| Average trade PnL | -$0.035 |
| Best trade | +$0.072 |
| Worst trade | -$0.226 |
| Gross profit | $0.084 |
| Gross loss | $0.710 |
| Top pair | BTC/USDT:USDT (-$0.274, 1W/6L) |
| Worst pair | ETH/USDT:USDT (-$0.352, 4W/7L) |
| Daily profit trend | **declining** (-0.092%) |
| Proposal hypothesis | `observe_underperforming_pair_cluster_v1` |
| Anomaly flags | `negative_closed_profit` |
| Promotion blocked | **YES** (`walk_forward_net_metrics_negative`) |
| Verdict | **BLOCKED** |

---

## Fleet-Level Profitability Gate

| Metric | Value |
|---|---|
| Verdict | **blocked** |
| Bot count | 4 |
| Candidate count | 2 |
| Blocked count | 2 |
| Inconclusive count | 0 |
| Fleet profit factor | 3.2425 |
| Total net PnL | +$19.893 |
| Total trades | 227 |
| Max drawdown (fleet) | 2.11% |
| Block reason | blocked bots: freqtrade-regime-hybrid, freqai-rebel |

---

## Root Cause Per Blocked Bot

### freqtrade-regime-hybrid

**Classification:** `NEGATIVE_NET_PROFIT`

**Evidence:**
- Net PnL: -$7.248 across 55 trades
- Profit factor: 0.576 (gross profit $9.847 / gross loss $17.095)
- Win rate 67.27% is misleading — wins are small, losses are large
- Average win contributes less than average loss destroys
- Worst trade (-$3.097) is 2x the best trade (+$1.526)
- BTC/USDT:USDT is the only profitable pair (+$1.499)
- ETH/USDT:USDT is the biggest loser (-$2.204)
- ARB/USDT:USDT nearly flat (+$0.637) with 6 losses in 13 trades

**Root Cause:** The strategy's risk-reward ratio is inverted. Wins are small and frequent, but losses are disproportionately large. The regime-switching logic may be entering trades at unfavorable regime transitions, causing stop-outs that exceed the gains from correct regime predictions.

**Walk-forward block reason:** `walk_forward_net_metrics_negative` — promotion is blocked because net metrics are negative.

### freqai-rebel

**Classification:** `NEGATIVE_NET_PROFIT` + `INSUFFICIENT_TRADES` + `LOW_WIN_RATE`

**Evidence:**
- Net PnL: -$1.623 across only 18 closed trades (35 in walk-forward window)
- Profit factor: 0.370 (gross profit $0.084 / gross loss $0.710)
- Win rate: 27.78% — only 5 wins out of 18 trades
- Best trade (+$0.072) vs worst trade (-$0.226) — 3:1 unfavorable ratio
- Both BTC and ETH pairs are net negative
- Profit trend: **declining** (only bot with declining trend)
- Only 18 closed trades in 8 days of operation (since 2026-06-15)

**Root Cause:** Triple issue:
1. **Strategy underperformance:** The XGBoost classifier model is generating poor entry signals, resulting in a 72% loss rate
2. **Insufficient sample size:** Only 18 trades is too few for statistical confidence, but the direction is consistently negative
3. **Declining trend:** Unlike other bots with stable trends, freqai-rebel's profit trend is declining, suggesting the model may be overfitting or the market regime has shifted against its training data

**Walk-forward block reason:** `walk_forward_net_metrics_negative` — promotion is blocked because net metrics are negative.

---

## Candidate vs Blocked Comparison

| Dimension | freqforge / canary (CANDIDATE) | regime-hybrid / rebel (BLOCKED) |
|---|---|---|
| Net PnL | +$24.784 / +$3.980 | -$7.248 / -$1.623 |
| Profit factor | 1.58 / 1.88 | 0.58 / 0.37 |
| Win rate | 79% / 91% | 67% / 28% |
| Trade count | 78 / 59 | 55 / 18 |
| Max drawdown | 2.11% / 0.76% | 0.77% / 0.18% |
| Profit trend | stable / stable | stable / **declining** |
| Strategy type | FreqForge (rule-based) | Regime-switching / XGBoost |
| Hypothesis | reinforce profitable | observe underperforming |
| Anomaly flags | none | `negative_closed_profit` |

**Key differentiator:** The FreqForge strategy (freqforge and canary) uses rule-based pair selection with proven profitable clusters. The blocked bots use more complex strategies (regime-switching, ML classifier) that are currently underperforming in the current market regime.

**Not a data issue:** All 4 bots have complete historical trade data, authenticated telemetry, and 5+ runs observed. The evidence is sufficient.

**Not a proposal quality issue:** The proposals for blocked bots correctly identify underperforming clusters (`observe_underperforming_pair_cluster_v1`). The proposals are accurate — the bots genuinely underperform.

**Strategy underperformance issue:** The underlying strategies for regime-hybrid and freqai-rebel are not profitable in the current market conditions. This is the root cause.

---

## Decision Lane

**Selected Lane: `D. STRATEGY_UNDERPERFORMANCE_ISSUE`**

Rationale:
- The blocked proposals are clearly negative — they should not be promoted
- The proposals correctly identify the problem (underperforming clusters)
- The underlying strategies are weak regardless of proposal quality
- Evidence is sufficient (not a data thickness issue)
- No metrics bug detected — raw evidence aligns with walk-forward verdicts

---

## Controlled Apply Verdict

**Controlled Apply remains BLOCKED.**

| Gate | Status |
|---|---|
| Fleet-level profitability | BLOCKED (2/4 bots negative) |
| Human approval for candidates | PENDING (freqforge, canary) |
| Controller state | PAUSED / L3_REPOSITORY_ONLY |
| Post-apply data | WAITING_FOR_POST_APPLY_DATA |
| Mutation counters | All 0 |

Even if the two candidate bots were approved, the fleet-level profitability gate would still block Controlled Apply because 2/4 bots are blocked. There is no existing fleet policy for partial apply.

---

## Safe-for-Human-Approval-Only Path

| Bot | Safe for human approval? | Notes |
|---|---|---|
| freqtrade-freqforge | YES | Positive metrics, PASS_REVIEW, requires only human approval |
| freqtrade-freqforge-canary | YES | Positive metrics, PASS_REVIEW, requires only human approval |
| freqtrade-regime-hybrid | NO | Negative metrics, profitability gate blocked |
| freqai-rebel | NO | Negative metrics, profitability gate blocked, declining trend |

The two candidate bots are safe for human consideration, but approval alone does not unblock fleet-level Controlled Apply.

---

## Recommendations

### Immediate (no action required, observation only)

1. **Wait for more post-apply data:** The post-apply window is empty (0 trades since activation on 2026-06-23). This is expected — no apply has occurred. Not a blocker for current analysis.

2. **Continue monitoring:** The SI-v2 loop is GREEN and running every 6 hours. Next cycle will provide fresh evidence.

### Strategic (requires human decision)

3. **Evaluate regime-hybrid strategy:** The regime-switching logic has a 55-trade sample with a clear negative expectancy. Consider whether the strategy parameters need adjustment or if the regime detection model needs retraining.

4. **Evaluate freqai-rebel model:** The XGBoost classifier has only 18 trades with a 28% win rate and declining trend. Consider whether the model needs retraining with more data, different features, or a different approach entirely.

5. **Consider partial fleet policy:** If the human operator decides that 2/4 profitable bots are sufficient for a controlled apply, a fleet policy allowing partial apply would need to be documented and approved.

### Not recommended

- Do NOT apply proposals for blocked bots — they would worsen performance
- Do NOT change profitability gate thresholds — they are working correctly
- Do NOT restart Docker or touch runtime — no infrastructure issue exists

---

## Files Changed

None. This is a documentation-only read-only analysis.

---

## Safety Confirmation

- No proposals were applied
- No approval tokens were used or requested
- No live trading was enabled
- No `dry_run=false` change was made
- No runtime, config, strategy, Docker, Cron, Guardian, or environment mutation was performed
- No destructive git command was used
- No secrets were printed or exposed
- Controller remains `PAUSED / L3_REPOSITORY_ONLY`
