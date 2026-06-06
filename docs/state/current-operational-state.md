# Current Operational State

Generated at: 2026-06-06T02:45:00+00:00

Canonical status artifact:
- /home/hermes/projects/trading/docs/state/canonical-trading-status.md
- /home/hermes/projects/trading/orchestrator/reports/canonical_trading_status_latest.json

Overall verdict: WARNING
Runtime health: GREEN (all containers up)
Reporting health: WARNING (container naming drift in monitoring scripts)
Live risk source: STALE / UNKNOWN (drawdown_state not verified current)
Ledger risk source: WARNING
Paper book: SANDBOX_ONLY

## At a Glance

- Active trading bots: 4
- Dry-run only: yes
- Live trading enabled: no
- Signal core: 2026-06-06T02:31:10+00:00 (deepseek-v4-pro, fresh)
- Signal bridge: 2026-06-06T02:35:37+00:00 (processed, age: 4.4 min)
- RiskGuard state: 2026-06-06T02:35:37+00:00 (all SHORT, confidence 0.85)
- All containers: UP

## Active Fleet

| Bot | Container | Port | DB Name | Status | PnL | Notes |
|-----|-----------|------|---------|--------|-----|-------|
| FreqForge | trading-freqtrade-freqforge-1 | 8086 | tradesv3.freqforge.dryrun.sqlite | Nominal | +23.17 USDT | 63 Trades (1 open), WR 77.8% (72h) |
| Canary | trading-freqtrade-freqforge-canary-1 | 8081 | tradesv3.freqforge_canary.dryrun.sqlite | Nominal | +7.40 USDT | 44 Trades |
| Regime-Hybrid | trading-freqtrade-regime-hybrid-1 | 8085 | tradesv3.regime_hybrid.dryrun.sqlite | Watch | -6.18 USDT | 45 Trades |
| FreqAI-Rebel | trading-freqai-rebel-1 | 8087 | tradesv3.freqai_rebel.dryrun.sqlite | Trainingsphase | 0.00 USDT | Neu, 0 Trades |

## Container Naming — WARNING: Drift detected

The docker-compose project prefix (`trading-`) and suffix (`-1`) changed from simple names.
All monitoring scripts reference OLD container names → `docker exec` fails silently:

| Script | Old Name (broken) | Actual Name | Impact |
|--------|-------------------|-------------|--------|
| freqtrade_monitor.py | freqtrade-regime-hybrid | trading-freqtrade-regime-hybrid-1 | All 4 bots show ERROR |
| quality_hub_monitor.py | freqai-rebel | trading-freqai-rebel-1 | Rebel shows dry_run=F, VISIBILITY_GAP |
| external_cron_guardian.log | ai-hedge-fund-crypto | trading-ai-hedge-fund-1 | False CONTAINER_DOWN alerts |

→ Fix required: Update BOTS dicts in both monitor scripts.

## Source Freshness

| Source | Timestamp | Freshness |
|--------|-----------|-----------|
| Signal Core | 2026-06-06T02:31:10+00:00 | fresh (4.4 min) |
| Trading Pipeline | 2026-06-06T02:35:37+00:00 | processed |
| RiskGuard State | 2026-06-06T02:35:37+00:00 | all ACCEPTED SHORT, conf 0.85 |
| Drawdown State | 2026-06-01T04:01:25+00:00 | STALE |
| Ledger Risk | 2026-06-05T12:07:13+00:00 | current |

## AI-Override Metrics (72h FreqForge Test)

- Total PnL: +13.21 USDT | 9 Trades | WR: 77.8%
- Profit Factor: 5.28
- AI-Override-Anteil: 88.9% | Override-WR: 75%
- SOL: 4/4 Wins, +10.19 USDT ← best channel
- BTC: 1/2 Wins, -0.60 USDT ← weakest channel

## Open Issues (Stand 2026-06-06)

1. **P2**: Container naming drift in monitor scripts (freqtrade_monitor.py, quality_hub_monitor.py)
2. **P2**: FreqForge/Canary Config hat kein trailing_stop → 33% TS-Exit-Rate (Vorschlag erstellt)
3. **P3**: BTC 50% WR in AI-Override → per-pair confidence threshold vorgeschlagen
4. **P3**: Regime-Hybrid -6.18 USDT durch SHORT-Bias (Signal blockiert longs)
5. **P4**: Root-owned 0-byte primo_signal_state.json in freqai-rebel volume (cleanup pending, kein sudo)

## Notes

- ledger-integrity-watchdog last run: 2026-06-05T12:44:46
- Drawdown_state is stale since 2026-06-01 — needs refresh
- Bitget MCP paper outputs are synthetic
- Regime-Hybrid v0.4 Integration ist ein Veto-Modell (kein Force-Entry)
- FreqAI-Rebel läuft (dry_run=true) mit korrektem DB-Path (FIX-2026-06-06)
