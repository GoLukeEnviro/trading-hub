# FreqForge AI Override Re-enable + Regime-Hybrid Quarantine

Date: 2026-06-04
Status: applied to dry-run fleet only

## Scope

User-approved dry-run changes to recover FreqForge trade flow and stop continued bleed from Regime-Hybrid.
No live trading enabled. No credentials changed. No exchange secrets added.

## Files changed

1. `freqforge/user_data/strategies/FreqForge_Override.py`
2. `freqforge/config/config_freqforge_dryrun.json`
3. `freqtrade/bots/regime-hybrid/config/config_regime_hybrid_dryrun.json`

## What changed

### FreqForge strategy

- Re-enabled `_inject_ai_signal_override()` with canonical safety gates only.
- Override now reads `freqtrade/shared/primo_signal_state.json` via `load_signal_state()`.
- Override only applies to `BTC/USDT`, `ETH/USDT`, `SOL/USDT`.
- Override requires:
  - `verdict == ACCEPTED`
  - directional `action in {BUY, LONG, SELL, SHORT}`
  - `confidence >= 0.75` OR RiskGuard pass (`riskguard_reason` starts with `PASS`)
  - matching `allow_long_bias` / `allow_short_bias`
- Override only stamps the latest candle, so it behaves as forward dry-run logic instead of contaminating historical rows.
- Added explicit `ai_override_long` / `ai_override_short` entry tags.
- Disabled class-level trailing stop (`trailing_stop = False`).
- Loosened native TA gates to recover baseline flow when AI override is absent.
- Widened ROI ladder to let winners run longer.
- Replaced the old aggressive custom stoploss with slower tightening.
- Added `custom_exit()` so profitable trades can exit on exhaustion / trend fade / AI bias loss instead of relying on the removed trailing stop.

### FreqForge config

- Pairlist reduced to:
  - `BTC/USDT:USDT`
  - `ETH/USDT:USDT`
  - `SOL/USDT:USDT`
- `OP` was already absent in the active FreqForge config, so no config removal was needed there.

### Regime-Hybrid

- Set `max_open_trades = 0` in the dry-run config.
- Decision: quarantine instead of further strategy surgery.
- Reason: current edge is negative and too weak to justify another live dry-run iteration without a separate rebuild path.

## Verification performed

1. Python syntax check on `FreqForge_Override.py` passed (`py_compile`).
2. JSON validation on both modified configs passed.
3. Container import test confirmed override helper returns ACCEPTED short signals for BTC/ETH/SOL and `None` for ARB.
4. Restarted containers:
   - `freqtrade-freqforge`
   - `freqtrade-regime-hybrid`
5. Post-restart logs confirmed:
   - FreqForge loaded the new defaults (`adx_rel_threshold=0.9`, `rsi_oversold=32`, `trailing_stop=False` via startup summary / strategy load).
   - AI override fired immediately for BTC/ETH/SOL.
   - FreqForge opened dry-run short entries tagged `ai_override_short` on BTC and SOL right after restart.
   - Regime-Hybrid started with `max_open_trades: 0` and remained in dry-run RUNNING state.

## Immediate runtime proof

From FreqForge logs after restart:

- `[AIOverride] BTC/USDT -> SELL conf=0.90 verdict=ACCEPTED`
- `[AIOverride] ETH/USDT -> SELL conf=0.88 verdict=ACCEPTED`
- `[AIOverride] SOL/USDT -> SELL conf=0.92 verdict=ACCEPTED`
- `Short signal found ... BTC/USDT:USDT`
- `Short signal found ... SOL/USDT:USDT`
- Entries were recorded with tag `ai_override_short`

SQLite confirmation right after restart:

- Open trade 55: `BTC/USDT:USDT`, short, `ai_override_short`
- Open trade 56: `SOL/USDT:USDT`, short, `ai_override_short`
- Regime-Hybrid: zero open trades

## Operational note

This is still a dry-run experiment. The strategy now has restored signal flow, but profitability is not yet proven. The next decision gate is the 3-5 day observation window with trade-frequency and PnL thresholds.