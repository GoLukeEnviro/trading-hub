# 2026-06-05 – regime_hybrid_backtest Stale Source Removal

## Summary
- **Action:** Removed stale `regime_hybrid_backtest` source from
  `freqtrade/shared/fleet_risk_state.json` → `portfolio.sources`.
- **Reason:** Source had static `current_equity=990.0`, `peak_equity=990.0`,
  `updated_at=2026-05-30T07:42:48.828444+00:00` (>5 days stale). It inflated
  the aggregated LEDGER_RISK `current_equity` and dampened `current_drawdown`.
- **User approval:** Option B (complete removal) chosen by luke-hermes at
  2026-06-05T12:05.
- **Code impact:** `fleet_risk_manager.py` does NOT reference the key directly
  (grep confirmed 0 matches). Removal is therefore safe and contained to
  the data file.

## Before vs After (LEDGER_RISK aggregates)

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| current_equity | 3426.6497 | 2436.6497 | -990.0000 |
| peak_equity | 3513.0494 | 2523.0494 | -990.0000 |
| current_drawdown | 2.46% | 3.42% | +0.96 pp |
| source_keys count | 4 | 3 | -1 |

The 990.0 USDT offset is the stale backtest source. The 3.42% drawdown is the
**true** LEDGER_RISK value (peak was inflated by the same stale key).

## Audit Trail
Embedded in `fleet_risk_state.json` under `_audit`:
- `action`: remove_stale_source
- `source_key`: regime_hybrid_backtest
- `equity_before` / `equity_after`
- `drawdown_before` / `drawdown_after`
- `snapshot` of removed entry (preserved for traceability)
- `ts`: 2026-06-05T12:06:31+00:00

## Files Touched
- `freqtrade/shared/fleet_risk_state.json` (edit + audit)
- `freqtrade/shared/fleet_risk_state.json.bak.2026-06-05T12-05-pre-remove-backtest` (backup)
- `orchestrator/reports/canonical_trading_status_latest.json` (canonical update)
- `docs/state/canonical-trading-status.md` (canonical update)
- `docs/context/2026-06-05-regime-hybrid-backtest-source-removal.md` (this report)

## Health Score Impact
- `reporting_health_score`: 68 → 73 (+5, stale source warning removed)
- `data_quality_score`:    79 → 84 (+5, sources now sum honestly)
- `overall_operational_score`: 81 → 83 (+2)
- `overall_status`: WARNING (unchanged, LIVE_RISK still STALE — separate issue)

## Historical Reference (removed entry)
```json
{
  "current_equity": 990.0,
  "peak_equity": 990.0,
  "updated_at": "2026-05-30T07:42:48.828444+00:00"
}
```
The full audit entry remains in `fleet_risk_state.json` under `_audit[0]`.

## What Remains Open
1. **LIVE_RISK stale** (`drawdown_state.json` from 2026-06-01) — separate issue,
   not touched here.
2. **Rebel VISIBILITY_GAP** — 0 trades, no audit trail; requires strategy/config
   change (out of scope for this repair).
3. **Permission errors** on orchestrator config files — separate issue.

## Verification Commands
```bash
# Confirm stale key gone
python3 -c "import json; d=json.load(open('/home/hermes/projects/trading/freqtrade/shared/fleet_risk_state.json')); assert 'regime_hybrid_backtest' not in d['portfolio']['sources']; print('OK')"

# Confirm source sum == current_equity
python3 -c "import json; d=json.load(open('/home/hermes/projects/trading/freqtrade/shared/fleet_risk_state.json')); s=sum(x['current_equity'] for x in d['portfolio']['sources'].values()); print('sum:', s, 'eq:', d['portfolio']['current_equity'])"
```
