# Current Operational State

Generated at: 2026-06-06T02:55:00+00:00

Canonical status artifact:
- /home/hermes/projects/trading/docs/state/canonical-trading-status.md
- /home/hermes/projects/trading/orchestrator/reports/canonical_trading_status_latest.json

Overall verdict: GREEN (WATCH: Regime-Hybrid -6.18)
Runtime health: GREEN (all containers up, all monitors working)
Reporting health: GREEN (naming drift fixed)
Live risk source: STALE / UNKNOWN (drawdown_state not refreshed since 2026-06-01)
Paper book: SANDBOX_ONLY

## At a Glance

- Active trading bots: 4
- Dry-run only: yes
- Live trading enabled: no
- Signal core: 2026-06-06T02:31:10+00:00 (deepseek-v4-pro, fresh)
- Trading Pipeline: 2026-06-06T02:35:37+00:00 (processed, age ~7 min)
- All containers: UP (trading-*-1 naming convention)
- Monitor scripts: Fixed (names + DOCKER_HOST + config paths)

## Active Fleet

| Bot | Container | Trades | PnL | Winrate | PF | Open | Status |
|-----|-----------|-------:|----:|-------:|---:|-----:|--------|
| FreqForge | trading-freqtrade-freqforge-1 | 62 | +23.17 U | 85.5% | 1.66 | 1 | OK |
| Canary | trading-freqtrade-freqforge-canary-1 | 44 | +7.40 U | 93.2% | 241.73 | 0 | OK |
| Regime-Hybrid | trading-freqtrade-regime-hybrid-1 | 45 | -6.18 U | 77.8% | 0.61 | 0 | LOSS |
| FreqAI-Rebel | trading-freqai-rebel-1 | 0 | 0.00 U | 0.0% | 0.00 | 0 | INFERENCE_ONLY |

## Changes Applied (2026-06-06)

### Task A — Container Naming Drift Fixed
- freqtrade_monitor.py: names + DOCKER_HOST fix + config paths
- quality_hub_monitor.py: names + DOCKER_HOST fix + rebel reference
- observation_checkpoint.py: names in BOTS, CONTAINERS, docker exec
- ai_hedge_signal_heartbeat.sh: container name fix

### Task B — Trailing Stop Added (FreqForge + Canary)
- Added trailing_stop: true, positive: 0.02, offset: 0.03, only_offset_is_reached: true
- Prevents premature trailing (33% TS exit rate → expected reduction)

### Task C — Per-Pair BTC Confidence Override
- Added `PAIR_CONFIDENCE_OVERRIDES = {"BTC/USDT:USDT": 0.85}`
- BTC needs 0.85 vs default 0.65 (50% WR in 72h test)

### Task D — Runbook for Root-Owned File
- docs/runbooks/fix-root-owned-primo-signal.md

## Open Issues

| Priority | Issue | Status |
|----------|-------|--------|
| P2 | Drawdown state stale since 2026-06-01 | Needs refresh |
| P3 | Regime-Hybrid -6.18 USDT (SHORT bias blocks longs) | Watch |
| P4 | Root-owned 0B primo_signal_state.json in rebel volume | Runbook exists, needs sudo |
| P5 | FreqAI-Rebel training phase (0 trades) | Expected |
