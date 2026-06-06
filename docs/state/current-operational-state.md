# Current Operational State

Generated at: 2026-06-06T02:13:36.896080+00:00

Canonical status artifact:
- /home/hermes/projects/trading/docs/state/canonical-trading-status.md
- /home/hermes/projects/trading/orchestrator/reports/canonical_trading_status_latest.json

Overall verdict: WARNING
Runtime health: GREEN
Reporting health: WARNING
Live risk source: STALE / UNKNOWN (drawdown_state is not verified current)
Ledger risk source: WARNING (current secondary ledger; stale backtest source REMOVED 2026-06-05)
Paper book: SANDBOX_ONLY

## At a Glance

- Active trading bots: 4
- Dry-run only: yes
- Live trading enabled: no
- Signal core: 2026-06-05T09:47:04.312649+00:00
- Signal bridge: 2026-06-05T09:50:29+00:00 (reported age: 3.1 min)
- RiskGuard state: 2026-06-05T12:01:58.484167+00:00 (signal age: 15.1 min)
- Rebel classification: VISIBILITY_GAP

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
| RiskGuard State | 2026-06-05T12:01:58.484167+00:00 | reported_signal_age_minutes=15.1 |
| RiskGuard Health | 2026-06-05T12:01:58.485273+00:00 | fresh |
| Drawdown State | 2026-06-01T04:01:25.183014+00:00 | STALE (4d old, not verified current) |
| Ledger Risk | 2026-06-05T12:07:13.705954+00:00 | current (stale backtest source removed) |

## Risk Separation

| Scope | Timestamp | Status | Notes |
|-------|-----------|--------|-------|
| LIVE_RISK | 2026-06-01T04:01:25.183014+00:00 | STALE | Do not use until refreshed. 4d old, equity not verifiable. |
| LEDGER_RISK | 2026-06-05T12:07:13.705954+00:00 | WARNING | current secondary ledger; regime_hybrid_backtest source REMOVED; equity/drawdown recalculated. **INCOMPLETE**: rebel source MISSING (1061.62 USDT gap, see reconciliation audit 2026-06-05). |

## Risk Note: LEDGER drawdown threshold proximity

- LEDGER_RISK current_drawdown = 3.42%
- `fleet_risk_auto_params.py` R2 threshold = 3.0% (halve all stakes)
- Status: LEDGER view now sits above the R2 trigger threshold.
  This is a WATCH flag only — the auto-param-adjuster reads LIVE_RISK
  (drawdown_state) for its rules, not LEDGER_RISK. Confirm during next
  fleet_risk_auto_params audit.

## Legacy / Non-Canonical Surfaces

| Path | Status | Why |
|------|--------|-----|
| /home/hermes/projects/trading/docs/state/autopilot/latest.md | HISTORICAL | Older autopilot snapshot; not canonical. |
| /home/hermes/projects/trading/orchestrator/reports/fleet_health_latest.json | NON-CANONICAL | Diagnostic fleet report. |
| /home/hermes/projects/trading/orchestrator/reports/multicycle_validation_latest.json | NON-CANONICAL | Legacy validator output. |

## Decommissioned Inventory

| Bot | Artifact Present | Status | Path | Note |
|-----|------------------|--------|------|------|
| rsi | no | DECOMMISSIONED | /home/hermes/projects/trading/freqtrade/bots/rsi/user_data/primo_signal_state.json | No current state artifact found; excluded from live fleet. |
| momentum | yes | DECOMMISSIONED | /home/hermes/projects/trading/freqtrade/bots/momentum/user_data/primo_signal_state.json | Historical state artifact still present; excluded from live fleet. |

## Notes


- ledger-integrity-watchdog last run: 2026-06-05T12:44:46.327173+00:00 — ISSUES: freqai-rebel | drawdown > R2.
- Current live risk truth is not drawdown_state until it is refreshed and verified.
- Bitget MCP paper outputs are synthetic and must never be used for live decisions.
- Rebel remains a visibility gap; it is running and dry_run=true, but its audit surface is incomplete.
- Regime-hybrid-backtest stale source removal recorded in
  `docs/context/2026-06-05-regime-hybrid-backtest-source-removal.md` and
  embedded in `fleet_risk_state.json:_audit[0]`.
