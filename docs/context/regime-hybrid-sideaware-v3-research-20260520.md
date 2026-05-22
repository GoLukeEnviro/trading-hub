# Regime-Hybrid SideAware v3 Research Variant — 2026-05-20

## Scope

Created a research-only Regime-Hybrid v3 variant after fixing the signal bridge canonical/latest source mismatch.

Files:

- `/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/user_data/strategies/research_regime_hybrid_sideaware_v3.py`
- `/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/config/research/config_regime_hybrid_sideaware_v3.json`

## Safety Boundary

- Research-only files.
- No active fleet strategy/config modified.
- No live trading enabled.
- Config is dry-run/futures/isolated with empty exchange credentials.
- Whitelist limited to BTC/ETH/SOL futures.

## v3 Design

- Uses `HistoricalSignalLoader` from `config/research/signal_tools/signal_loader.py`.
- Removes static signal fixture dependency.
- Implements `_historical_gate_allows(pair, candle_time, side)`.
- Gate fails closed if archive state is missing/stale, verdict is not ACCEPTED, confidence < 0.70, or side/action/bias do not match.
- Supports explicit `bias` but infers effective bias from `allow_long_bias` / `allow_short_bias` for `trading_pipeline_v1.0` bridge states.
- Emits only `research_trend_pullback_short` entries.
- Does not emit long entries in v3; long-side gate logic is present for future controlled variants.
- `can_short = True`.
- `use_custom_stoploss = True` with ATR-based dynamic stop and ~90 minute time-kill.
- `max_open_trades = 3` via config.

## Verification

Host-side checks completed:

- `python3 -m py_compile research_regime_hybrid_sideaware_v3.py` — PASS
- `python3 -m json.tool config_regime_hybrid_sideaware_v3.json` — PASS
- JSON assertions: dry_run true, futures, max_open_trades 3, strategy class correct, whitelist BTC/ETH/SOL — PASS
- Import smoke with host stubs — PASS
- Historical gate smoke against current archive:
  - BTC short: True
  - BTC long: False
  - ETH short: True
  - SOL short: True

## Next Test Plan

1. Container/Freqtrade strategy discovery smoke test only.
2. Short timerange backtest only after enough historical signal archive exists for the chosen timerange.
3. Use the existing walk-forward framework once the archive spans enough real signal cycles.
4. Require statistically meaningful trade count before drawing conclusions.
