# Backtest Smoke Results — 2026-06-06

## Tested Strategies

| Bot | Strategy | Timerange | Trades | PnL USDT | PnL % | Win% | Status |
|-----|----------|-----------|--------|----------|-------|------|--------|
| FreqForge | FreqForge_Override | 2026-05-01 → 2026-05-17 | 7 | -3.90 | -0.39% | 42.9% | ✅ Reproducible |
| Regime-Hybrid | RegimeSwitchingHybrid_v7_v04 | 2026-05-01 → 2026-05-30 | 57 | -2.64 | -0.26% | 19.3% | ✅ Reproducible |
| FreqAI-Rebel | RebelLiquidation | 2026-04-01 → 2026-06-01 | 405 | -9.95 | -1.00% | 29.6% | ✅ Reproducible |
| Canary | FreqForge_Override | — | — | — | — | — | ❌ No data |

## Key Findings
1. **All 3 strategies lose money** in backtest (short term, small sample)
2. **FreqAI-Rebel** had lowest WR (29.6%) and highest loss (-$9.95)
3. **Data stale**: newest data = May 30 (Regime-Hybrid), oldest = May 17 (FreqForge)
4. **Canary cannot backtest**: 0 data files in user_data/data/
5. **All strategies import from shared/**: backtests need PYTHONPATH=/freqtrade/shared

## Updated Healthscore

| Category | Before | After | Reason |
|----------|--------|-------|--------|
| Backtest/Hyperopt Evidence | 3/10 | **6/10** | ✅ All 3 active strategies reproducible (+3) |
| Data Pipeline | 8/10 | **7/10** | ⚠️ Data stale, Canary has 0 data (-1) |
| Strategy Validity | 5/10 | 5/10 | No change — strategies losing in backtest |
| **TOTAL** | **75** | **77** | **+2 (75→77)** |

### Pass/Fail Criteria
- ✅ Exit code = 0 → ALL 3 PASS
- ✅ Backtest completes within 30 minutes → ALL < 3 min
- ✅ Results file written to backtest_results/ → ALL 3
- ✅ No "Data not found" errors → ALL 3
- ✅ No strategy import errors → ALL 3 (with shared/ mount)

## Remaining Gaps (P0-P4)
- **P1**: No profitable strategy across all bots (all lose in backtest) — needs strategy review
- **P2**: Canary has 0 data files — needs data download
- **P2**: Data stale (last download May 12-30) — needs refresh
- **P3**: No walk-forward validation yet
- **P3**: No out-of-sample validation yet
- **P4**: Backtest timerange too short (1-2 months)
