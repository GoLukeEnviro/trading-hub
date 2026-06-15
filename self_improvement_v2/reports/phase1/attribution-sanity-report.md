# Offline Attribution Sanity Report

**Date:** 2026-06-15
**Source:** `self_improvement_v2/tests/fixtures/attribution/scenarios.json`
**Schema Version:** 1

## Summary

| Metric | Value |
|--------|-------|
| Total scenarios | 7 |
| Complete metadata | 5 |
| Incomplete metadata | 2 |
| Winning | 2 |
| Losing | 2 |
| Neutral | 1 |
| Unknown | 2 |

## By Source

| Source ID | Scenarios | Wins | Losses |
|-----------|-----------|------|--------|
| freqtrade-freqforge | 2 | 1 | 0 |
| freqtrade-freqforge-canary | 2 | 1 | 0 |
| freqai-rebel | 2 | 0 | 1 |
| freqtrade-regime-hybrid | 1 | 0 | 1 |

## By Regime Label

| Regime | Count |
|--------|-------|
| Bullish | 2 |
| Bearish | 2 |
| Neutral | 2 |
| Missing | 1 |

## By Confidence Bucket

| Confidence | Count |
|------------|-------|
| High | 2 |
| Medium | 2 |
| Low | 1 |
| Missing | 2 |

## By Result Bucket

| Result | Count |
|--------|-------|
| Win | 2 |
| Loss | 2 |
| Neutral | 1 |
| Unknown | 2 |

## Incomplete Metadata Cases

| Scenario ID | Missing Fields |
|-------------|----------------|
| stale-missing-metadata | regime_label, confidence_bucket, pnl, duration_hours |
| incomplete-regime-only | confidence_bucket, pnl |

## Expected Aggregation Behavior

1. **Winning + High Confidence**: Should rank highest in attribution scores
2. **Losing + High Confidence**: Should trigger review despite high confidence
3. **Low Confidence**: Should be downweighted in attribution aggregation
4. **Incomplete Metadata**: Should be flagged for manual review, excluded from automated aggregation
5. **Stale Evidence**: Should be excluded if freshness threshold exceeded

## Safety Notes

- All fixture data is synthetic (generated, not from live trading)
- No secrets, credentials, or real exchange data
- No service calls required to load or validate
- Deterministic output — same results every run
