# Regime-Hybrid Side-Aware Gate Research — 2026-05-20

## Scope

Research-only implementation. Active Regime-Hybrid runtime strategy/config were not modified.

Created files:
- `freqtrade/bots/regime-hybrid/user_data/strategies/research_regime_hybrid_sideaware_v1.py`
- `freqtrade/bots/regime-hybrid/user_data/strategies/research_regime_hybrid_sideaware_v2.py`
- `freqtrade/bots/regime-hybrid/config/research/config_regime_hybrid_sideaware_v1.json`
- `freqtrade/bots/regime-hybrid/config/research/config_regime_hybrid_sideaware_v2.json`
- `freqtrade/bots/regime-hybrid/config/research/hermes_signal_fixture_20260520.json`

## Safety

- `dry_run=true` preserved.
- `trading_mode=futures`, `margin_mode=isolated` preserved.
- No exchange credentials added.
- No real orders placed.
- Active bot container was not restarted.
- Active strategy `RegimeSwitchingHybrid_v7_v04_Integration.py` unchanged.

## Implementation Notes

Corrections applied versus initial proposed package:

1. Freqtrade v3 does not use `populate_short_trend()`.
   Shorts must be created in `populate_entry_trend()` via `enter_short`.

2. The active bridge state file inside the Regime-Hybrid container was stale/empty:
   `/freqtrade/user_data/primo_signal_state.json` had `fresh=false`, `pairs={}`.
   For deterministic research backtests, a fixture was placed under `config/research/`.

3. Signal pair lookup must check both raw and normalized keys:
   - raw: `BTC/USDT:USDT`
   - normalized: `BTC/USDT`

## Backtests

Timerange requested: `20260301-20260520`.
Actual available data ended at `2026-05-17 06:45:00`.

### v1 — Side-aware gate + mirrored trend/range shorts + ATR stop

Result:
- Trades: 14
- Long / Short: 0 / 14
- PnL: -3.825 USDT
- Total profit: -0.38%
- Winrate: 21.4%
- Profit factor: 0.24
- Max drawdown: 0.39%

Entry tag breakdown:
- `research_range_reversion_short`: 10 trades, -5.0014 USDT, 1/10 wins
- `research_trend_pullback_short`: 4 trades, +1.1769 USDT, 2/4 wins

Diagnosis:
- The side-aware gate worked: no longs during bearish fixture.
- The mirrored range-reversion short logic is toxic.
- Losses came almost entirely from `research_range_reversion_short`.

### v2 — Range-reversion shorts disabled

Result:
- Trades: 6
- Long / Short: 0 / 6
- PnL: +1.326 USDT
- Total profit: +0.13%
- Winrate: 66.7%
- Profit factor: 2465.96 (misleading due two near-zero losses)
- Max drawdown: ~0.00%

Diagnosis:
- Removing range-reversion shorts flips the result positive.
- But 6 trades is far below the 60-80 trade statistical minimum.
- v2 is promising as a direction, but not deployable.

## Conclusion

Regime-Hybrid should not be patched directly into runtime based on this test.

The real fix direction is validated:
1. Side-aware gate prevents bearish signals from permitting longs.
2. Short support can work, but only trend-pullback shorts showed positive expectancy.
3. Mirrored range-reversion shorts must remain disabled unless redesigned.

## Next Required Tests

1. Build v3 with signal fixture coverage for all intended pairs only if the signal pipeline actually supports those pairs.
2. Test trend-pullback-short only over longer data and shifted windows.
3. Repair the bridge so `/freqtrade/user_data/primo_signal_state.json` contains non-empty `pairs` and correct freshness.
4. Do not deploy until trade count >= 60 and OOS PF >= 1.0, target PF >= 1.3.
