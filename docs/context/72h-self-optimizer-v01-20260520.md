# 72h Fleet Self-Optimizer v0.1 — 2026-05-20

## Scope

Implemented a read-only self-optimization advisory layer for the 72h live-readiness sprint.

Files:

- `/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/config/research/automation/self_optimizer.py`
- `/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/config/research/automation/fleet_monitor.py`
- `/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/config/research/automation/latest_fleet_monitor_report.json`
- `/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/config/research/automation/latest_self_optimization_proposals.json`
- `/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/config/research/automation/self_optimizer_state.json`
- `/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/config/research/automation/self_optimizer_events.jsonl`

No production configs were changed. No orders, restarts, live mode, or automatic pauses were executed.

## Algorithm 1 — Performance-Based Stake Scaling

Inputs:

- Closed trades from active Freqtrade SQLite DBs.
- Rolling 12h and 24h windows.
- Profit factor: `gross_win_abs / abs(gross_loss_abs)`.
- Max drawdown over closed-trade equity curve using visible dry-run capital assumptions:
  - FreqForge MAIN: 1000 USDT
  - Regime-Hybrid: 1000 USDT
  - Momentum: 1000 USDT
  - Canary: 500 USDT
  - Rebel: 1000 USDT

Rules:

- If 12h PF < 1.0 OR 12h DD > 4% → propose stake reduction.
- If 24h PF < 1.0 OR 24h DD > 4% → propose stake reduction.
- Target factor:
  - 0.50 for medium underperformance
  - 0.30 for high underperformance
- If 24h PF > 1.3, DD < 2%, >=3 trades, and no open trades → propose stake increase review to 1.25x.

Current output:

- Momentum: `stake_scale_down`, factor 0.30.
- Rebel: `stake_scale_down`, factor 0.30.
- Canary/Main: no stake-up because sample/open-risk gates block it.

## Algorithm 2 — Regime-Adaptive Risk Control

Inputs:

- Current canonical ai-hedge signal.
- Current Primo/RiskGuard state.
- Latest archived signal state via `HistoricalSignalLoader` from:
  `/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/config/research/signal_tools/signal_loader.py`.

Rules:

- Strong bearish regime when at least 2 of BTC/ETH/SOL are SHORT/bearish with confidence >= 0.80.
- Moderate bearish when at least 2 of BTC/ETH/SOL are SHORT/bearish with confidence >= 0.60.
- In strong bearish regime:
  - propose long-entry reduction/pause for long-capable bots.
  - alert on open correlated long exposure.
- In moderate bearish WATCH_ONLY regime:
  - propose no long exposure increase until ACCEPTED confidence >=0.80.

Current output:

- Regime: `strong_bearish`.
- BTC/ETH/SOL are SHORT/bearish, confidence 0.90, Primo verdict ACCEPTED.
- Fleet-level proposals: reduce or pause long entries across long-capable bots.
- Rebel has one correlated long exposure alert.

## Algorithm 3 — Dynamic Kill-Switch + Quarantine + Recovery

Inputs:

- Rolling 12h/24h metrics.
- Overall PF/PnL fallback for small samples.
- Consecutive loss streak in 24h.
- Optimizer state file for quarantine/recovery tracking.

Hard quarantine proposal thresholds:

- 24h PF < 0.6 with >=3 trades, OR
- 24h max drawdown > 8%, OR
- 24h consecutive losses >=3, OR
- overall PF <0.6 and cumulative PnL <0 when 24h sample is too small.

Momentum special case:

- Because user selected Momentum for `max_open_trades=0`, optimizer marks it as `momentum_explicit_quarantine_target`, but still proposal-only.

Recovery proposal:

- If previously quarantined and later:
  - 24h trades >=3
  - 24h PF >1.1
  - 24h DD <2%
  - no 12h loss streak
- then propose `recovery_review` at small stake first.

Current output:

- Momentum: `quarantine_recommended`, suggested action `set_max_open_trades_0_after_explicit_approval`.
- Rebel: `quarantine_recommended`, PF 0.3006 in 24h, 4 consecutive losses.
- Regime-Hybrid old dry-run: `quarantine_recommended` based on overall PF 0.5497; this applies to current old dry-run, not the v3 research strategy.

## Smoke Test

Command:

```bash
python3 -m py_compile \
  /home/hermes/projects/trading/freqtrade/bots/regime-hybrid/config/research/automation/fleet_monitor.py \
  /home/hermes/projects/trading/freqtrade/bots/regime-hybrid/config/research/automation/self_optimizer.py

python3 /home/hermes/projects/trading/freqtrade/bots/regime-hybrid/config/research/automation/fleet_monitor.py \
  --output /home/hermes/projects/trading/freqtrade/bots/regime-hybrid/config/research/automation/latest_fleet_monitor_report.json \
  --optimization-output /home/hermes/projects/trading/freqtrade/bots/regime-hybrid/config/research/automation/latest_self_optimization_proposals.json
```

Result:

```text
schema=fleet_monitor_research_v0.2
SelfOpt: regime=strong_bearish | proposals=11 (crit=2, high=9, med=0)
HISTORICAL_LOADER_ASSERTIONS PASS
historical_loader=6 latest_ts=2026-05-20T16:50:23.574539+00:00
```

## Next 48h Buildout

Can be semi-automated by Tag 3:

1. Proposal generation every hour — already enabled through the existing hourly monitor job.
2. Quarantine approval packet — generate exact config patch for Momentum/Rebel/old Regime-Hybrid, but do not apply automatically.
3. Stake scaling dry-run plan — create per-bot suggested stake_amount/max_open_trades changes as JSON patches.
4. Recovery tracking — state file already tracks quarantine candidates; next add "hours stable" counters.
5. Telegram 12h report — summarize only critical/high proposals in German.

Should NOT be fully automated by Tag 3 without explicit approval:

- Config writes.
- Container restarts.
- Force exits.
- dry_run=false.
- Any live-trading action.
