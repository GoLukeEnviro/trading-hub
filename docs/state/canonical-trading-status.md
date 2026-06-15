# Canonical Trading Status

Generated at: 2026-06-15T09:04:22.315820+00:00

Verdict: WARNING

## Health Scores

| Metric | Score | Status |
|--------|-------|--------|
| runtime_health_score | 92 | GREEN |
| reporting_health_score | 73 | WARNING |
| data_quality_score | 84 | WARNING |
| auditability_score | 80 | WARNING |
| overall_operational_score | 82 | WARNING |

## Truth Scopes

| Scope | Status | Source / Freshness | Notes |
|-------|--------|--------------------|-------|
| LIVE_FREQTRADE | GREEN | docker ps + active bot configs/state | 4 active bots, dry_run only. |
| SIGNAL_CORE | GREEN | 2026-06-05T09:47:04.312649+00:00 | Raw signal producer is fresh. |
| SIGNAL_BRIDGE | GREEN | 2026-06-05T09:50:29+00:00 (reported age 3.1 min) | Bridge lag acceptable. |
| LIVE_RISK | STALE | 2026-06-01T04:01:25.183014+00:00 | Not verified current; do not use as sole live source. |
| LEDGER_RISK | WARNING | 2026-06-15T09:04:22.315820+00:00 | Secondary ledger / historical view. Watchdog @ 2026-06-15T09:04:22.315820+00:00: no new findings (idempotent). |
| MCP_PAPER_SANDBOX | SANDBOX_ONLY | live paper balance snapshot | Synthetic prices, not market truth. |
| REPORTING_HEALTH | WARNING | fleet reports + docs | Legacy docs/reports remain non-canonical. |

## Active Fleet

| Bot | Container | Verdict | Classification | Dry-run | Strategy match | State file |
|-----|-----------|---------|----------------|---------|----------------|------------|
| freqforge | freqtrade-freqforge | GREEN | LIVE_RUNTIME | yes | True | True |
| regime-hybrid | freqtrade-regime-hybrid | GREEN | LIVE_RUNTIME | yes | True | True |
| freqforge-canary | freqtrade-freqforge-canary | GREEN | LIVE_RUNTIME | yes | True | True |
| freqai-rebel | freqai-rebel | YELLOW | VISIBILITY_GAP | yes | True | False |

## Source Freshness

| Source | Timestamp | Freshness |
|--------|-----------|-----------|
| Signal Core | 2026-06-05T09:47:04.312649+00:00 | fresh |
| Signal Bridge | 2026-06-05T09:50:29+00:00 | reported_age_minutes=3.1 |
| RiskGuard State | 2026-06-05T09:31:16.823573+00:00 | reported_signal_age_minutes=15.1 |
| RiskGuard Health | 2026-06-05T09:31:16.825070+00:00 | fresh |
| Drawdown State | 2026-06-01T04:01:25.183014+00:00 | stale / not verified current |
| Ledger Risk | 2026-06-05T12:07:13.705954+00:00 | current secondary ledger (stale backtest source removed) |

## Risk Separation

| Scope | Timestamp | Status | Notes |
|-------|-----------|--------|-------|
| LIVE_RISK | 2026-06-01T04:01:25.183014+00:00 | STALE | drawdown_state is stale / unverified. |
| LEDGER_RISK | 2026-06-05T12:20:02.200716+00:00 | WARNING | current secondary ledger; stale regime_hybrid_backtest source removed; equity/drawdown recalculated; **rebel source MISSING** (recon audit 2026-06-05). |

## MCP Paper Sandbox

| Metric | Value |
|--------|-------|
| Currency | USDT |
| Free | 1.8167 |
| Margin locked | 68805.7351 |
| uPnL | 324686.6678 |
| Equity | 324688.4845 |
| Total positions | 4 |
| Open orders | 0 |

Warning: Synthetic/sandbox prices. Not market truth. Not for live trading decisions.

| Symbol | Side | Entry | Mark | uPnL | Margin used | Liq. price |
|--------|------|-------|------|------|-------------|------------|
| BTC/USDT | short | 74774.44 | 1118.45 | 238628.57 | 24225.213 | 78513.16 |
| ETH/USDT | short | 2075.7 | 1677.72 | 43489.95 | 22682.8959 | 2179.49 |
| SOL/USDT | short | 82.24 | 66.23 | 42568.15 | 21867.6262 | 86.35 |
| AVAX/USDT | short | 150.0 | 150.0 | 0.0 | 30.0 | 157.5 |

## Decision Sources

| Source | Path | Status | Timestamp | Freshness |
|--------|------|--------|-----------|-----------|
| SIGNAL_CORE | /home/hermes/projects/trading/ai-hedge-fund-crypto/output/hermes_signal.json | GREEN | 2026-06-05T09:47:04.312649+00:00 | fresh |
| SIGNAL_BRIDGE | /home/hermes/projects/trading/freqtrade/shared/primo_signal_state.json | GREEN | 2026-06-05T09:50:29+00:00 | reported_age_minutes=3.1 |
| LIVE_RISK_GATE | /home/hermes/projects/trading/orchestrator/state/riskguard/riskguard_state.json | ACTIVE | 2026-06-05T09:31:16.823573+00:00 | reported_signal_age_minutes=15.1 |
| LIVE_RISK_GATE_HEALTH | /home/hermes/projects/trading/orchestrator/state/riskguard/riskguard_health.json | OK | 2026-06-05T09:31:16.825070+00:00 | fresh |
| SHADOW_LOG | /home/hermes/projects/trading/orchestrator/logs/shadow_decisions.jsonl | APPEND_ONLY | 2026-06-05T09:50:29.649566+00:00 | fresh |
| freqforge | /home/hermes/projects/trading/freqforge/config/config_freqforge_dryrun.json | GREEN | n/a | n/a |
| freqforge | /home/hermes/projects/trading/freqforge/user_data/primo_signal_state.json | SAFE | n/a | n/a |
| regime-hybrid | /home/hermes/projects/trading/freqtrade/bots/regime-hybrid/config/config_regime_hybrid_dryrun.json | GREEN | n/a | n/a |
| regime-hybrid | /home/hermes/projects/trading/freqtrade/bots/regime-hybrid/user_data/primo_signal_state.json | SAFE | n/a | n/a |
| freqforge-canary | /home/hermes/projects/trading/freqforge-canary/config/config_canary_dryrun.json | GREEN | n/a | n/a |
| freqforge-canary | /home/hermes/projects/trading/freqforge-canary/user_data/primo_signal_state.json | SAFE | n/a | n/a |
| freqai-rebel | docker-exec-only | YELLOW | n/a | n/a |

## Do Not Use For Decisions

| Path | Status | Why |
|------|--------|-----|
| /opt/data/profiles/orchestrator/state/drawdown_state.json | STALE | Stale drawdown snapshot; not verified current. |
| /home/hermes/projects/trading/docs/state/autopilot/latest.md | HISTORICAL | Historical autopilot snapshot; not canonical. |
| /home/hermes/projects/trading/orchestrator/reports/fleet_health_latest.json | YELLOW | Diagnostic fleet report; current but non-canonical. |
| /home/hermes/projects/trading/orchestrator/reports/fleet_health_latest.md | YELLOW | Diagnostic fleet report markdown; current but non-canonical. |
| /home/hermes/projects/trading/orchestrator/reports/multicycle_validation_latest.json | RED | Legacy validator output; currently reports RED on legacy wrapper assumptions. |
| /home/hermes/projects/trading/orchestrator/reports/multicycle_validation_latest.md | RED | Legacy validator markdown; currently reports RED on legacy wrapper assumptions. |

## Decommissioned Inventory

| Bot | Artifact Present | Status | Path | Note |
|-----|------------------|--------|------|------|
| rsi | no | DECOMMISSIONED | /home/hermes/projects/trading/freqtrade/bots/rsi/user_data/primo_signal_state.json | No current state artifact found; excluded from live fleet. |
| momentum | yes | DECOMMISSIONED | /home/hermes/projects/trading/freqtrade/bots/momentum/user_data/primo_signal_state.json | Historical state artifact still present; excluded from live fleet. |

## Notes

- Rebel is classified as VISIBILITY_GAP, not RUNNING_INFERENCE_ONLY, because there is no explicit inference-only proof and the bot remains dry-run with incomplete visibility.
- Source clocks are not perfectly synchronized; prefer source timestamps and source-reported ages for relative freshness.
- MCP paper book values are synthetic and must remain SANDBOX_ONLY.
